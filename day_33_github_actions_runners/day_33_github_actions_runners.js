#!/usr/bin/env node

/**
 * GitHub Actions Runner Architecture Laboratory
 *
 * This file uses JavaScript-specific event-driven patterns to model:
 * - hosted and self-hosted runners
 * - runner labels and routing
 * - asynchronous job queues
 * - runner lifecycle events
 * - status reporting
 * - ephemeral versus persistent execution
 * - capacity and failure behavior
 *
 * Runtime: Node.js 18+
 * External packages: none
 */

"use strict";

const { EventEmitter } = require("node:events");
const os = require("node:os");
const crypto = require("node:crypto");

const RunnerKind = Object.freeze({
  HOSTED: "github-hosted",
  SELF_HOSTED: "self-hosted",
});

const RunnerState = Object.freeze({
  OFFLINE: "offline",
  IDLE: "idle",
  BUSY: "busy",
  DRAINING: "draining",
});

const JobState = Object.freeze({
  QUEUED: "queued",
  RUNNING: "running",
  SUCCEEDED: "succeeded",
  FAILED: "failed",
  CANCELLED: "cancelled",
});

function delay(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

class Runner {
  constructor({
    id = crypto.randomUUID(),
    name,
    kind,
    labels = [],
    operatingSystem,
    architecture,
    tools = [],
    ephemeral = true,
    group = "default",
    trusted = false,
  }) {
    this.id = id;
    this.name = name;
    this.kind = kind;
    this.labels = new Set(labels);
    this.operatingSystem = operatingSystem;
    this.architecture = architecture;
    this.tools = new Set(tools);
    this.ephemeral = ephemeral;
    this.group = group;
    this.trusted = trusted;
    this.state = RunnerState.IDLE;
    this.online = true;
    this.currentJob = null;
    this.completedJobs = 0;
  }

  supports(job) {
    if (!this.online) {
      return { ok: false, reason: "runner is offline" };
    }

    if (this.state !== RunnerState.IDLE) {
      return { ok: false, reason: `runner is ${this.state}` };
    }

    for (const label of job.labels) {
      if (!this.labels.has(label)) {
        return { ok: false, reason: `missing label: ${label}` };
      }
    }

    for (const tool of job.requiredTools) {
      if (!this.tools.has(tool)) {
        return { ok: false, reason: `missing tool: ${tool}` };
      }
    }

    return { ok: true, reason: "compatible" };
  }

  start(job) {
    const result = this.supports(job);

    if (!result.ok) {
      throw new Error(`${this.name}: ${result.reason}`);
    }

    this.state = RunnerState.BUSY;
    this.currentJob = job.id;
  }

  finish() {
    this.state = RunnerState.IDLE;
    this.currentJob = null;
    this.completedJobs += 1;
  }

  drain() {
    if (this.state === RunnerState.BUSY) {
      throw new Error(`${this.name} cannot drain while executing a job`);
    }

    this.state = RunnerState.DRAINING;
  }

  goOffline() {
    if (this.state === RunnerState.BUSY) {
      throw new Error(`${this.name} cannot go offline while busy`);
    }

    this.online = false;
    this.state = RunnerState.OFFLINE;
  }

  resetEphemeralState() {
    if (this.ephemeral) {
      // An ephemeral runner represents a fresh environment per workload.
      // Clearing job-related state models the architectural goal of avoiding
      // accidental persistence between independent jobs.
      this.currentJob = null;
      this.completedJobs = 0;
    }
  }
}

class WorkflowJob {
  constructor({
    name,
    labels = [],
    requiredTools = [],
    durationMs = 50,
    shouldFail = false,
    secretsRequired = false,
  }) {
    this.id = crypto.randomUUID();
    this.name = name;
    this.labels = new Set(labels);
    this.requiredTools = new Set(requiredTools);
    this.durationMs = durationMs;
    this.shouldFail = shouldFail;
    this.secretsRequired = secretsRequired;
    this.state = JobState.QUEUED;
    this.runnerName = null;
    this.failureReason = null;
    this.startedAt = null;
    this.finishedAt = null;
  }
}

class RunnerScheduler extends EventEmitter {
  constructor() {
    super();
    this.runners = new Map();
    this.queue = [];
    this.history = [];
  }

  registerRunner(runner) {
    if (this.runners.has(runner.name)) {
      throw new Error(`Runner already registered: ${runner.name}`);
    }

    this.runners.set(runner.name, runner);
    this.emit("runner:registered", runner);
  }

  submit(job) {
    if (job.state !== JobState.QUEUED) {
      throw new Error("Only queued jobs can be submitted");
    }

    this.queue.push(job);
    this.emit("job:queued", job);
  }

  findRunner(job) {
    const diagnostics = [];

    for (const runner of this.runners.values()) {
      const result = runner.supports(job);
      diagnostics.push({
        runner: runner.name,
        compatible: result.ok,
        reason: result.reason,
      });

      if (result.ok) {
        return { runner, diagnostics };
      }
    }

    return { runner: null, diagnostics };
  }

  async dispatchOne() {
    if (this.queue.length === 0) {
      return null;
    }

    const job = this.queue[0];
    const { runner, diagnostics } = this.findRunner(job);

    if (!runner) {
      this.emit("job:waiting", { job, diagnostics });
      return null;
    }

    this.queue.shift();
    await this.execute(job, runner);
    return job;
  }

  async execute(job, runner) {
    job.state = JobState.RUNNING;
    job.runnerName = runner.name;
    job.startedAt = new Date().toISOString();

    runner.start(job);

    this.emit("job:started", { job, runner });

    try {
      await delay(job.durationMs);

      if (job.shouldFail) {
        throw new Error("simulated build/test failure");
      }

      job.state = JobState.SUCCEEDED;
      this.emit("job:succeeded", { job, runner });
    } catch (error) {
      job.state = JobState.FAILED;
      job.failureReason = error.message;
      this.emit("job:failed", { job, runner, error });
    } finally {
      job.finishedAt = new Date().toISOString();
      runner.finish();
      runner.resetEphemeralState();
      this.history.push(job);
      this.emit("runner:idle", runner);
    }
  }

  async dispatchAvailable() {
    // Repeatedly launch work while capacity exists. Promise.all models
    // concurrent jobs rather than serial execution on one runner.
    const active = [];

    while (this.queue.length > 0) {
      const job = this.queue[0];
      const { runner } = this.findRunner(job);

      if (!runner) {
        break;
      }

      this.queue.shift();
      active.push(this.execute(job, runner));
    }

    await Promise.all(active);
  }

  inventory() {
    return [...this.runners.values()].map((runner) => ({
      name: runner.name,
      kind: runner.kind,
      state: runner.state,
      online: runner.online,
      labels: [...runner.labels].sort(),
      group: runner.group,
      operatingSystem: runner.operatingSystem,
      architecture: runner.architecture,
      ephemeral: runner.ephemeral,
      trusted: runner.trusted,
      completedJobs: runner.completedJobs,
    }));
  }
}

function printHeading(text) {
  console.log(`\n=== ${text} ===`);
}

function demonstrateEventDrivenLifecycle() {
  printHeading("Event-driven runner lifecycle");

  const scheduler = new RunnerScheduler();

  scheduler.on("runner:registered", (runner) => {
    console.log(`[REGISTER] ${runner.name}`);
  });

  scheduler.on("job:queued", (job) => {
    console.log(`[QUEUE] ${job.name}`);
  });

  scheduler.on("job:started", ({ job, runner }) => {
    console.log(`[START] ${job.name} on ${runner.name}`);
  });

  scheduler.on("job:succeeded", ({ job, runner }) => {
    console.log(`[SUCCESS] ${job.name} on ${runner.name}`);
  });

  scheduler.on("job:failed", ({ job, runner, error }) => {
    console.log(`[FAIL] ${job.name} on ${runner.name}: ${error.message}`);
  });

  scheduler.on("runner:idle", (runner) => {
    console.log(`[IDLE] ${runner.name}`);
  });

  return scheduler;
}

function buildFleet(scheduler) {
  scheduler.registerRunner(
    new Runner({
      name: "hosted-linux-x64",
      kind: RunnerKind.HOSTED,
      labels: ["linux", "x64", "docker"],
      operatingSystem: "Linux",
      architecture: "x64",
      tools: ["git", "node", "python", "docker"],
      ephemeral: true,
      group: "github-hosted",
    })
  );

  scheduler.registerRunner(
    new Runner({
      name: "self-hosted-internal",
      kind: RunnerKind.SELF_HOSTED,
      labels: ["self-hosted", "linux", "x64", "internal"],
      operatingSystem: "Linux",
      architecture: "x64",
      tools: ["git", "node", "python", "internal-sdk"],
      ephemeral: false,
      group: "internal-builders",
      trusted: true,
    })
  );

  scheduler.registerRunner(
    new Runner({
      name: "gpu-builder",
      kind: RunnerKind.SELF_HOSTED,
      labels: ["self-hosted", "linux", "x64", "gpu"],
      operatingSystem: "Linux",
      architecture: "x64",
      tools: ["git", "python", "cuda"],
      ephemeral: false,
      group: "accelerated-builders",
      trusted: true,
    })
  );
}

function demonstrateRouting(scheduler) {
  printHeading("Routing by labels and capabilities");

  const jobs = [
    new WorkflowJob({
      name: "web-tests",
      labels: ["linux", "x64"],
      requiredTools: ["node"],
    }),
    new WorkflowJob({
      name: "internal-sdk-build",
      labels: ["self-hosted", "linux", "x64", "internal"],
      requiredTools: ["internal-sdk"],
    }),
    new WorkflowJob({
      name: "gpu-tests",
      labels: ["self-hosted", "linux", "x64", "gpu"],
      requiredTools: ["cuda"],
    }),
  ];

  for (const job of jobs) {
    const { runner, diagnostics } = scheduler.findRunner(job);

    console.log(
      `${job.name}: ${runner ? `selected ${runner.name}` : "no runner"}`
    );

    if (!runner) {
      console.log(
        diagnostics
          .map((item) => `  ${item.runner}: ${item.reason}`)
          .join("\n")
      );
    }
  }

  return jobs;
}

async function demonstrateConcurrentExecution(scheduler) {
  printHeading("Concurrent execution and queue behavior");

  scheduler.submit(
    new WorkflowJob({
      name: "linux-unit-tests",
      labels: ["linux", "x64"],
      requiredTools: ["node"],
      durationMs: 100,
    })
  );

  scheduler.submit(
    new WorkflowJob({
      name: "internal-build",
      labels: ["self-hosted", "linux", "x64", "internal"],
      requiredTools: ["internal-sdk"],
      durationMs: 150,
    })
  );

  scheduler.submit(
    new WorkflowJob({
      name: "intentional-failure",
      labels: ["linux", "x64"],
      requiredTools: ["node"],
      durationMs: 80,
      shouldFail: true,
    })
  );

  await scheduler.dispatchAvailable();

  console.log(`Remaining queue length: ${scheduler.queue.length}`);
  console.log(`History entries: ${scheduler.history.length}`);
}

function demonstrateDrainAndOffline(scheduler) {
  printHeading("Draining and offline transitions");

  const runner = scheduler.runners.get("gpu-builder");

  runner.drain();

  const job = new WorkflowJob({
    name: "gpu-maintenance-test",
    labels: ["self-hosted", "linux", "x64", "gpu"],
    requiredTools: ["cuda"],
  });

  const result = runner.supports(job);

  console.log(
    `After drain: compatible=${result.ok}, reason=${result.reason}`
  );

  runner.state = RunnerState.IDLE;
  runner.goOffline();

  console.log(
    `After offline transition: state=${runner.state}, online=${runner.online}`
  );
}

function demonstrateSecurityModel() {
  printHeading("Security boundary");

  const securityRules = {
    hosted: [
      "Treat hosted execution as an ephemeral compute environment.",
      "Do not assume workspace state survives between jobs.",
      "Pass only the credentials required by the workflow.",
    ],
    selfHosted: [
      "Treat the runner host as part of the trusted computing boundary.",
      "Use least-privilege service accounts and restrictive network access.",
      "Patch the operating system and runner software.",
      "Avoid placing untrusted pull-request workloads on privileged persistent hosts.",
      "Clean credentials and workspaces after jobs where persistence is possible.",
    ],
  };

  console.log(JSON.stringify(securityRules, null, 2));

  console.log(
    `\nNode.js process architecture: ${process.arch}; platform: ${process.platform}; CPUs: ${os.cpus().length}`
  );
}

function demonstrateCapacity(scheduler) {
  printHeading("Fleet capacity");

  const idle = [...scheduler.runners.values()].filter(
    (runner) => runner.online && runner.state === RunnerState.IDLE
  );

  const jobs = scheduler.history.length + scheduler.queue.length;

  console.log(`Runner capacity currently available: ${idle.length}`);
  console.log(`Jobs observed by the scheduler: ${jobs}`);

  console.log(
    "Capacity is multidimensional: operating system, architecture, labels, "
    "tools, trust boundaries, and concurrency all constrain effective capacity."
  );
}

function demonstrateFailedRouting(scheduler) {
  printHeading("Unroutable job");

  const job = new WorkflowJob({
    name: "unsupported-arm-gpu-job",
    labels: ["self-hosted", "linux", "arm64", "gpu"],
    requiredTools: ["cuda"],
  });

  scheduler.submit(job);

  const { runner, diagnostics } = scheduler.findRunner(job);

  console.log(`Selected runner: ${runner ? runner.name : "none"}`);

  if (!runner) {
    for (const diagnostic of diagnostics) {
      console.log(
        `${diagnostic.runner}: ${diagnostic.reason}`
      );
    }
  }
}

async function main() {
  console.log("GitHub Actions Runner Architecture Laboratory");
  console.log("==============================================");

  const scheduler = demonstrateEventDrivenLifecycle();
  buildFleet(scheduler);

  demonstrateRouting(scheduler);
  await demonstrateConcurrentExecution(scheduler);
  demonstrateDrainAndOffline(scheduler);
  demonstrateSecurityModel();
  demonstrateCapacity(scheduler);
  demonstrateFailedRouting(scheduler);

  printHeading("Final runner inventory");
  console.log(JSON.stringify(scheduler.inventory(), null, 2));

  printHeading("Architectural relationships");
  console.log(
    [
      "Workflow job -> scheduling constraints -> eligible runner",
      "Runner -> operating system + architecture + tools + labels",
      "Hosted runner -> managed execution lifecycle",
      "Self-hosted runner -> organization-managed infrastructure lifecycle",
      "Ephemeral execution -> reduced state persistence",
      "Persistent self-hosted execution -> stronger operational and security obligations",
    ].join("\n")
  );
}

main().catch((error) => {
  console.error(`Fatal scheduler error: ${error.message}`);
  process.exitCode = 1;
});
