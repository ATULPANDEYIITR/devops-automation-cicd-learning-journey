"use strict";

/*
 * Event-driven model of reusable GitHub Actions workflows and composite actions.
 *
 * A reusable workflow is invoked at job level and can define multiple jobs.
 * A composite action is invoked as a step and executes a sequence of steps
 * inside the caller's job. These abstractions have different execution scopes.
 *
 * Run with Node.js 18 or later:
 *   node actions-reuse.js
 */

const crypto = require("node:crypto");
const assert = require("node:assert/strict");

class ConfigurationError extends Error {}
class WorkflowExecutionError extends Error {}
class PolicyError extends Error {}

const WorkflowState = Object.freeze({
  CREATED: "created",
  RUNNING: "running",
  SUCCEEDED: "succeeded",
  FAILED: "failed",
  CANCELLED: "cancelled",
});

const PullRequestCheck = Object.freeze({
  PENDING: "pending",
  PASSED: "passed",
  FAILED: "failed",
});

class EventBus {
  #listeners = new Map();

  on(eventName, listener) {
    if (typeof listener !== "function") {
      throw new TypeError("An event listener must be a function.");
    }

    const listeners = this.#listeners.get(eventName) ?? [];
    listeners.push(listener);
    this.#listeners.set(eventName, listeners);
  }

  emit(eventName, payload) {
    // Copy the list so a listener can subscribe without mutating this dispatch.
    for (const listener of [...(this.#listeners.get(eventName) ?? [])]) {
      listener(Object.freeze({ ...payload }));
    }
  }
}

class InputContract {
  constructor(definitions) {
    this.definitions = new Map(
      definitions.map((definition) => [definition.name, definition])
    );
  }

  resolve(supplied = {}) {
    for (const name of Object.keys(supplied)) {
      if (!this.definitions.has(name)) {
        throw new ConfigurationError(`Undeclared input: ${name}`);
      }
    }

    const result = {};

    for (const [name, definition] of this.definitions) {
      const raw = Object.hasOwn(supplied, name)
        ? supplied[name]
        : definition.defaultValue;

      if (definition.required && (raw === undefined || raw === "" || raw === null)) {
        throw new ConfigurationError(`Required input ${name} is missing.`);
      }

      if (raw === undefined || raw === null) {
        result[name] = "";
        continue;
      }

      const value = String(raw);

      if (definition.allowedValues && !definition.allowedValues.includes(value)) {
        throw new ConfigurationError(
          `Invalid ${name}: ${value}. Allowed values: ` +
            definition.allowedValues.join(", ")
        );
      }

      result[name] = value;
    }

    return Object.freeze(result);
  }
}

class CompositeAction {
  constructor({ name, inputContract, steps }) {
    this.name = name;
    this.inputContract = inputContract;
    this.steps = [...steps];
  }

  async execute(suppliedInputs, callerContext) {
    const inputs = this.inputContract.resolve(suppliedInputs);
    const localOutputs = {};
    const actionContext = Object.freeze({
      inputs,
      environment: callerContext.environment,
      log: callerContext.log,
      outputs: localOutputs,
    });

    for (const step of this.steps) {
      try {
        callerContext.log(`Action ${this.name}: ${step.name}`);
        await step.run(actionContext);
      } catch (error) {
        if (step.continueOnError) {
          callerContext.log(`Optional step failed: ${step.name}`);
          continue;
        }

        throw new WorkflowExecutionError(
          `Action ${this.name}, step ${step.name} failed: ${error.message}`
        );
      }
    }

    return Object.freeze({ ...localOutputs });
  }
}

class ReusableWorkflow {
  constructor({ name, inputContract, requiredSecrets, jobs, bus }) {
    this.name = name;
    this.inputContract = inputContract;
    this.requiredSecrets = [...requiredSecrets];
    this.jobs = new Map(jobs.map((job) => [job.id, job]));
    this.bus = bus;
    this.state = WorkflowState.CREATED;

    if (this.jobs.size !== jobs.length) {
      throw new ConfigurationError("Workflow job identifiers must be unique.");
    }

    this.#validateDependencies();
  }

  #validateDependencies() {
    const visited = new Set();
    const active = new Set();

    const visit = (jobId) => {
      if (!this.jobs.has(jobId)) {
        throw new ConfigurationError(`Unknown job dependency: ${jobId}`);
      }

      if (active.has(jobId)) {
        throw new ConfigurationError(`Cyclic dependency at job ${jobId}`);
      }

      if (visited.has(jobId)) return;

      active.add(jobId);

      for (const dependency of this.jobs.get(jobId).needs ?? []) {
        visit(dependency);
      }

      active.delete(jobId);
      visited.add(jobId);
    };

    for (const jobId of this.jobs.keys()) visit(jobId);
  }

  async invoke({ inputs = {}, secrets = {}, environment = {} }) {
    if (this.state === WorkflowState.RUNNING) {
      throw new WorkflowExecutionError("This workflow instance is already running.");
    }

    const resolvedInputs = this.inputContract.resolve(inputs);

    for (const secretName of this.requiredSecrets) {
      if (typeof secrets[secretName] !== "string" || !secrets[secretName]) {
        throw new ConfigurationError(`Missing secret: ${secretName}`);
      }
    }

    this.state = WorkflowState.RUNNING;
    const logEntries = [];
    const outputs = {};

    // The caller supplies secrets through a separate object. Logs never
    // serialize that object, reducing accidental credential exposure.
    const context = {
      inputs: resolvedInputs,
      secrets: Object.freeze({ ...secrets }),
      environment: Object.freeze({ ...environment }),
      outputs,
      log(message) {
        let safe = String(message);
        for (const secret of Object.values(secrets)) {
          if (secret) safe = safe.split(secret).join("***");
        }
        logEntries.push(safe);
      },
    };

    const pending = new Set(this.jobs.keys());
    const statuses = new Map(
      [...this.jobs.keys()].map((id) => [id, WorkflowState.CREATED])
    );

    try {
      while (pending.size > 0) {
        let progressed = false;

        for (const jobId of [...pending]) {
          const job = this.jobs.get(jobId);
          const dependencies = job.needs ?? [];

          if (
            dependencies.some((dependency) =>
              [WorkflowState.FAILED, WorkflowState.CANCELLED].includes(
                statuses.get(dependency)
              )
            )
          ) {
            statuses.set(jobId, WorkflowState.CANCELLED);
            pending.delete(jobId);
            context.log(`Skipped job ${jobId}: dependency failed.`);
            progressed = true;
            continue;
          }

          if (
            !dependencies.every(
              (dependency) => statuses.get(dependency) === WorkflowState.SUCCEEDED
            )
          ) {
            continue;
          }

          statuses.set(jobId, WorkflowState.RUNNING);
          context.log(`Starting job ${jobId}.`);

          try {
            const result = await job.run(context);
            if (result && typeof result === "object") {
              Object.assign(outputs, result);
            }
            statuses.set(jobId, WorkflowState.SUCCEEDED);
            context.log(`Completed job ${jobId}.`);
            this.bus.emit("job.succeeded", { workflow: this.name, jobId });
          } catch (error) {
            statuses.set(jobId, WorkflowState.FAILED);
            context.log(`Job ${jobId} failed: ${error.message}`);
            this.bus.emit("job.failed", {
              workflow: this.name,
              jobId,
              reason: error.message,
            });
          }

          pending.delete(jobId);
          progressed = true;
        }

        if (!progressed) {
          throw new WorkflowExecutionError(
            `Workflow scheduler stalled: ${[...pending].join(", ")}`
          );
        }
      }

      const failed = [...statuses.values()].some(
        (status) => status === WorkflowState.FAILED
      );

      this.state = failed ? WorkflowState.FAILED : WorkflowState.SUCCEEDED;

      return Object.freeze({
        state: this.state,
        statuses: Object.fromEntries(statuses),
        outputs: Object.freeze({ ...outputs }),
        logs: Object.freeze([...logEntries]),
      });
    } catch (error) {
      this.state = WorkflowState.FAILED;
      throw error;
    }
  }
}

function createReleaseWorkflow(bus) {
  const deploymentAction = new CompositeAction({
    name: "deploy-service",
    inputContract: new InputContract([
      {
        name: "target",
        required: true,
        allowedValues: ["staging", "production"],
      },
      { name: "version", required: true },
    ]),
    steps: [
      {
        name: "validate revision",
        async run({ environment, log }) {
          if (!/^[0-9a-f]{7,64}$/i.test(environment.GITHUB_SHA ?? "")) {
            throw new PolicyError("A valid commit SHA is required.");
          }
          log(`Validated revision ${environment.GITHUB_SHA.slice(0, 12)}.`);
        },
      },
      {
        name: "validate release version",
        async run({ inputs, outputs, log }) {
          if (!/^\d+\.\d+\.\d+$/.test(inputs.version)) {
            throw new PolicyError("Version must be MAJOR.MINOR.PATCH.");
          }

          outputs.artifact = `service-${inputs.version}.tar`;
          log(`Prepared artifact ${outputs.artifact}.`);
        },
      },
      {
        name: "authorize deployment",
        async run({ inputs, environment, log }) {
          if (
            inputs.target === "production" &&
            environment.PRODUCTION_APPROVED !== "true"
          ) {
            throw new PolicyError("Production approval is required.");
          }

          log(`Deployment policy passed for ${inputs.target}.`);
        },
      },
    ],
  });

  return new ReusableWorkflow({
    name: "reusable-release",
    inputContract: new InputContract([
      { name: "version", required: true },
      {
        name: "target",
        required: false,
        defaultValue: "staging",
        allowedValues: ["staging", "production"],
      },
    ]),
    requiredSecrets: ["DEPLOY_TOKEN"],
    bus,
    jobs: [
      {
        id: "test",
        async run({ inputs, log }) {
          log(`Validated release request for version ${inputs.version}.`);
          return { testResult: "passed" };
        },
      },
      {
        id: "release",
        needs: ["test"],
        async run(context) {
          const result = await deploymentAction.execute(
            {
              target: context.inputs.target,
              version: context.inputs.version,
            },
            context
          );

          return {
            artifact: result.artifact,
            deployedTo: context.inputs.target,
          };
        },
      },
      {
        id: "audit",
        needs: ["release"],
        async run({ outputs, log }) {
          if (!outputs.artifact) {
            throw new WorkflowExecutionError("Release artifact is missing.");
          }

          const auditId = crypto
            .createHash("sha256")
            .update(outputs.artifact)
            .digest("hex")
            .slice(0, 12);

          log(`Recorded audit reference ${auditId}.`);
          return { auditReference: auditId };
        },
      },
    ],
  });
}

async function main() {
  const bus = new EventBus();
  const observedEvents = [];

  bus.on("job.succeeded", (event) => {
    observedEvents.push(`SUCCESS:${event.jobId}`);
  });

  bus.on("job.failed", (event) => {
    observedEvents.push(`FAILURE:${event.jobId}`);
  });

  const workflow = createReleaseWorkflow(bus);
  const common = {
    inputs: { version: "2.4.1", target: "staging" },
    secrets: { DEPLOY_TOKEN: "local-demo-token-12345" },
    environment: {
      GITHUB_SHA: "a4c31e98d01234567890abcdef1234567890abcd",
      PRODUCTION_APPROVED: "false",
    },
  };

  const result = await workflow.invoke(common);

  console.log("Successful reusable workflow invocation");
  console.log(JSON.stringify(result, null, 2));
  console.log("Observed events:", observedEvents.join(", "));

  assert.equal(result.state, WorkflowState.SUCCEEDED);
  assert.equal(result.outputs.deployedTo, "staging");
  assert.ok(result.outputs.auditReference);

  const productionWorkflow = createReleaseWorkflow(new EventBus());
  const blocked = await productionWorkflow.invoke({
    ...common,
    inputs: { version: "2.4.1", target: "production" },
  });

  console.log("\nProduction deployment without approval");
  console.log(JSON.stringify(blocked, null, 2));
  assert.equal(blocked.statuses.release, WorkflowState.FAILED);
  assert.equal(blocked.statuses.audit, WorkflowState.CANCELLED);

  const invalidWorkflow = createReleaseWorkflow(new EventBus());

  await assert.rejects(
    () =>
      invalidWorkflow.invoke({
        ...common,
        inputs: { version: "../untrusted", target: "staging" },
      }),
    ConfigurationError
  );

  console.log("\nInput validation and dependency failure checks passed.");
}

main().catch((error) => {
  console.error(`${error.name}: ${error.message}`);
  process.exitCode = 1;
});
