'use strict';

/*
 * GitHub Actions Basics
 *
 * This Node.js program provides a JavaScript-specific event-driven model of
 * GitHub Actions. It focuses on workflow files, events, jobs, and steps while
 * showing how asynchronous execution, event emitters, job dependencies,
 * conditions, matrices, outputs, and failure handling fit together.
 *
 * Run with:
 *   node github-actions-basics.js
 *
 * No npm packages are required.
 */

const { EventEmitter } = require('node:events');
const { execFile } = require('node:child_process');
const { promisify } = require('node:util');

const execFileAsync = promisify(execFile);

// -----------------------------------------------------------------------------
// Small formatting helpers
// -----------------------------------------------------------------------------

function heading(title) {
  console.log(`\n${'='.repeat(76)}\n${title}\n${'='.repeat(76)}`);
}

function sleep(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function printObject(label, value) {
  console.log(`${label}: ${JSON.stringify(value, null, 2)}`);
}

// -----------------------------------------------------------------------------
// Event model
// -----------------------------------------------------------------------------

class RepositoryEvent extends EventEmitter {
  /*
   * GitHub Actions starts workflows in response to events. EventEmitter is a
   * natural JavaScript representation because Node.js applications commonly
   * model asynchronous events through subscriptions and emitted payloads.
   */
  emitRepositoryEvent(eventName, payload = {}) {
    const event = {
      name: eventName,
      timestamp: new Date().toISOString(),
      ...payload,
    };

    this.emit(eventName, event);
    this.emit('*', event);
    return event;
  }
}

function createPushEvent(branch, actor) {
  return {
    name: 'push',
    branch,
    actor,
    commit: 'abc1234',
    changedFiles: ['src/app.js', 'tests/app.test.js'],
  };
}

function createPullRequestEvent(action, branch, actor) {
  return {
    name: 'pull_request',
    action,
    branch,
    actor,
    pullRequest: {
      number: 42,
      title: 'Improve payment validation',
      draft: false,
    },
  };
}

function eventMatchesTrigger(trigger, event) {
  /*
   * A workflow trigger can contain an event name and optional branch filters.
   * Matching the event is distinct from executing any jobs.
   */
  if (!Object.prototype.hasOwnProperty.call(trigger, event.name)) {
    return false;
  }

  const configuration = trigger[event.name];

  if (
    configuration &&
    Array.isArray(configuration.branches) &&
    !configuration.branches.includes(event.branch)
  ) {
    return false;
  }

  return true;
}

// -----------------------------------------------------------------------------
// Step model
// -----------------------------------------------------------------------------

class WorkflowStep {
  constructor({
    name,
    run,
    uses = null,
    condition = async () => true,
    continueOnError = false,
    env = {},
  }) {
    if (!name) {
      throw new Error('Every workflow step needs a name.');
    }

    if (typeof run !== 'function' && !uses) {
      throw new Error(`Step "${name}" needs a run function or uses value.`);
    }

    this.name = name;
    this.run = run;
    this.uses = uses;
    this.condition = condition;
    this.continueOnError = continueOnError;
    this.env = { ...env };
  }

  async execute(context) {
    /*
     * A step executes in the context of its job. It receives the job's
     * workspace and environment, which demonstrates why several steps within
     * one job can build on state produced by earlier steps.
     */
    const shouldRun = await this.condition(context);

    if (!shouldRun) {
      return {
        name: this.name,
        status: 'skipped',
      };
    }

    const environment = {
      ...context.environment,
      ...this.env,
    };

    try {
      if (this.uses) {
        context.log(`Action reference: ${this.uses}`);
        await context.executeAction(this.uses, environment);
      } else {
        await this.run({
          ...context,
          environment,
        });
      }

      return {
        name: this.name,
        status: 'success',
      };
    } catch (error) {
      context.log(`Step error: ${error.message}`);

      if (this.continueOnError) {
        return {
          name: this.name,
          status: 'failure-continued',
          error: error.message,
        };
      }

      return {
        name: this.name,
        status: 'failure',
        error: error.message,
      };
    }
  }
}

// -----------------------------------------------------------------------------
// Job model
// -----------------------------------------------------------------------------

class WorkflowJob {
  constructor({
    id,
    name,
    runsOn,
    needs = [],
    steps = [],
    condition = async () => true,
    matrix = null,
    env = {},
  }) {
    if (!id) {
      throw new Error('A job needs an identifier.');
    }

    if (!runsOn) {
      throw new Error(`Job "${id}" is missing runs-on.`);
    }

    if (!steps.length) {
      throw new Error(`Job "${id}" needs at least one step.`);
    }

    this.id = id;
    this.name = name || id;
    this.runsOn = runsOn;
    this.needs = [...needs];
    this.steps = [...steps];
    this.condition = condition;
    this.matrix = matrix;
    this.env = { ...env };
    this.outputs = {};
  }

  createMatrixVariants() {
    if (!this.matrix) {
      return [{}];
    }

    /*
     * JavaScript's reduce/forEach pattern makes the Cartesian-product
     * expansion explicit. Every combination becomes a separate concrete job.
     */
    const dimensions = Object.entries(this.matrix);

    return dimensions.reduce(
      (combinations, [dimensionName, values]) => {
        if (!Array.isArray(values) || values.length === 0) {
          throw new Error(`Matrix dimension "${dimensionName}" has no values.`);
        }

        const expanded = [];

        for (const existing of combinations) {
          for (const value of values) {
            expanded.push({
              ...existing,
              [dimensionName]: value,
            });
          }
        }

        return expanded;
      },
      [{}],
    );
  }
}

// -----------------------------------------------------------------------------
// Workflow engine
// -----------------------------------------------------------------------------

class WorkflowEngine {
  constructor(workflow) {
    this.workflow = workflow;
    this.results = new Map();
    this.outputs = new Map();
    this.actions = new Map();

    /*
     * Action implementations are registered instead of installing npm
     * packages. This keeps the simulator self-contained while still showing
     * the conceptual "uses" mechanism.
     */
    this.registerAction('actions/checkout', async (context) => {
      context.log(`Checking out repository on ${context.job.runsOn}`);
      context.workspace.files.push('src/app.js');
      context.workspace.files.push('tests/app.test.js');
    });

    this.registerAction('actions/setup-node', async (context, environment) => {
      context.log(`Preparing Node.js ${environment.NODE_VERSION || 'default'}`);
    });
  }

  registerAction(name, implementation) {
    this.actions.set(name, implementation);
  }

  async executeAction(name, environment, context) {
    const implementation = this.actions.get(name);

    if (!implementation) {
      throw new Error(`Unknown action reference: ${name}`);
    }

    await implementation(context, environment);
  }

  validateWorkflow() {
    const errors = [];

    if (!this.workflow.name) {
      errors.push('Workflow name is required.');
    }

    if (!this.workflow.on) {
      errors.push('Workflow trigger configuration is required.');
    }

    if (!this.workflow.jobs || Object.keys(this.workflow.jobs).length === 0) {
      errors.push('At least one job is required.');
      return errors;
    }

    for (const [jobId, job] of Object.entries(this.workflow.jobs)) {
      if (!/^[A-Za-z_][A-Za-z0-9_-]*$/.test(jobId)) {
        errors.push(`Invalid job identifier: ${jobId}`);
      }

      for (const dependency of job.needs) {
        if (!this.workflow.jobs[dependency]) {
          errors.push(
            `Job "${jobId}" references unknown dependency "${dependency}".`,
          );
        }
      }
    }

    try {
      this.topologicalOrder();
    } catch (error) {
      errors.push(error.message);
    }

    return errors;
  }

  topologicalOrder() {
    /*
     * Jobs form a directed acyclic graph. A depth-first traversal detects
     * cycles before execution, preventing a dependency chain that can never
     * become ready.
     */
    const temporary = new Set();
    const permanent = new Set();
    const order = [];

    const visit = (jobId) => {
      if (permanent.has(jobId)) {
        return;
      }

      if (temporary.has(jobId)) {
        throw new Error(`Cyclic job dependency detected at "${jobId}".`);
      }

      const job = this.workflow.jobs[jobId];
      if (!job) {
        throw new Error(`Unknown job "${jobId}".`);
      }

      temporary.add(jobId);

      for (const dependency of job.needs) {
        visit(dependency);
      }

      temporary.delete(jobId);
      permanent.add(jobId);
      order.push(jobId);
    };

    for (const jobId of Object.keys(this.workflow.jobs)) {
      visit(jobId);
    }

    return order;
  }

  async executeJob(job, event, matrixValues = {}) {
    const shouldRun = await job.condition({
      event,
      job,
      previousResults: this.results,
    });

    const variantLabel = Object.entries(matrixValues)
      .map(([key, value]) => `${key}=${value}`)
      .join(', ');

    const displayName = variantLabel
      ? `${job.name} [${variantLabel}]`
      : job.name;

    if (!shouldRun) {
      console.log(`  Job "${displayName}" -> SKIPPED`);
      return 'skipped';
    }

    console.log(`  Job "${displayName}" -> RUNNING`);

    const workspace = {
      files: [],
      generatedArtifacts: [],
    };

    const environment = {
      CI: 'true',
      GITHUB_EVENT_NAME: event.name,
      GITHUB_REF_NAME: event.branch,
      GITHUB_ACTOR: event.actor,
      RUNNER_OS: job.runsOn,
      ...job.env,
      ...Object.fromEntries(
        Object.entries(matrixValues).map(([key, value]) => [
          key.toUpperCase(),
          String(value),
        ]),
      ),
    };

    const context = {
      event,
      job,
      workspace,
      environment,
      outputs: {},
      log(message) {
        console.log(`    ${message}`);
      },
      setOutput(name, value) {
        context.outputs[name] = String(value);
        job.outputs[name] = String(value);
      },
      executeAction: async (name, actionEnvironment) => {
        await this.executeAction(name, actionEnvironment, context);
      },
    };

    for (const step of job.steps) {
      console.log(`    Step "${step.name}" -> RUNNING`);

      const result = await step.execute(context);

      if (result.status === 'skipped') {
        console.log(`    Step "${step.name}" -> SKIPPED`);
        continue;
      }

      if (result.status === 'failure') {
        console.log(`    Step "${step.name}" -> FAILURE`);
        console.log(`  Job "${displayName}" -> FAILURE`);
        return 'failure';
      }

      if (result.status === 'failure-continued') {
        console.log(
          `    Step "${step.name}" -> FAILURE (continue-on-error)`,
        );
        continue;
      }

      console.log(`    Step "${step.name}" -> SUCCESS`);
    }

    this.outputs.set(job.id, { ...job.outputs });
    console.log(`  Job "${displayName}" -> SUCCESS`);
    return 'success';
  }

  async execute(event) {
    heading(`WORKFLOW: ${this.workflow.name}`);

    if (!eventMatchesTrigger(this.workflow.on, event)) {
      console.log(
        `Ignored ${event.name} on branch ${event.branch}; trigger did not match.`,
      );
      return;
    }

    const validationErrors = this.validateWorkflow();

    if (validationErrors.length) {
      throw new Error(
        `Workflow validation failed:\n${validationErrors
          .map((error) => `  - ${error}`)
          .join('\n')}`,
      );
    }

    for (const jobId of this.topologicalOrder()) {
      const job = this.workflow.jobs[jobId];

      const dependencyFailed = job.needs.some(
        (dependency) =>
          this.results.get(dependency) === 'failure' ||
          this.results.get(dependency) === 'cancelled',
      );

      if (dependencyFailed) {
        this.results.set(jobId, 'skipped');
        console.log(
          `  Job "${job.name}" -> SKIPPED because a dependency failed.`,
        );
        continue;
      }

      const variants = job.createMatrixVariants();
      const statuses = [];

      for (const variant of variants) {
        const status = await this.executeJob(job, event, variant);
        statuses.push(status);
      }

      const finalStatus = statuses.includes('failure')
        ? 'failure'
        : statuses.every((status) => status === 'skipped')
          ? 'skipped'
          : 'success';

      this.results.set(jobId, finalStatus);
    }

    console.log('\nWorkflow result:');
    for (const [jobId, status] of this.results.entries()) {
      console.log(`  ${jobId.padEnd(18)} ${status}`);
    }

    printObject(
      'Job outputs',
      Object.fromEntries(this.outputs.entries()),
    );
  }
}

// -----------------------------------------------------------------------------
// Workflow construction
// -----------------------------------------------------------------------------

function buildContinuousIntegrationWorkflow() {
  const checkout = new WorkflowStep({
    name: 'Checkout repository',
    uses: 'actions/checkout',
  });

  const setupNode = new WorkflowStep({
    name: 'Set up Node.js',
    uses: 'actions/setup-node',
    env: {
      NODE_VERSION: '22',
    },
  });

  const lint = new WorkflowStep({
    name: 'Lint changed JavaScript',
    run: async ({ log, workspace }) => {
      /*
       * This models an actual lint phase. A production workflow could replace
       * this function with a command such as npm ci && npm run lint.
       */
      const source = workspace.files.find((file) => file.endsWith('.js'));

      if (!source) {
        throw new Error('No JavaScript source file was checked out.');
      }

      log(`Linted ${source}`);
    },
  });

  const tests = new WorkflowStep({
    name: 'Run tests',
    run: async ({ log, workspace, setOutput }) => {
      await sleep(50);

      if (!workspace.files.some((file) => file.includes('app.test.js'))) {
        throw new Error('Test suite was not checked out.');
      }

      setOutput('test_status', 'passed');
      log('Unit tests passed.');
    },
  });

  const build = new WorkflowStep({
    name: 'Build application',
    run: async ({ log, workspace }) => {
      /*
       * Jobs receive separate execution contexts. The build job therefore
       * checks out the repository again rather than assuming that the lint
       * job's workspace still exists.
       */
      workspace.generatedArtifacts.push('dist/application.bundle.js');
      log('Created dist/application.bundle.js');
    },
  });

  const deploy = new WorkflowStep({
    name: 'Deploy',
    run: async ({ log, event }) => {
      if (event.branch !== 'main') {
        throw new Error('Production deployment requires main.');
      }

      log(`Deployment permitted for ${event.branch}.`);
    },
  });

  return {
    name: 'JavaScript CI and Delivery',
    on: {
      push: {
        branches: ['main', 'develop'],
      },
      pull_request: {},
    },
    jobs: {
      lint: new WorkflowJob({
        id: 'lint',
        runsOn: 'ubuntu-latest',
        steps: [checkout, setupNode, lint],
      }),

      test: new WorkflowJob({
        id: 'test',
        runsOn: 'ubuntu-latest',
        matrix: {
          node: ['20', '22'],
        },
        steps: [checkout, setupNode, tests],
      }),

      build: new WorkflowJob({
        id: 'build',
        runsOn: 'ubuntu-latest',
        needs: ['lint', 'test'],
        steps: [
          new WorkflowStep({
            name: 'Checkout repository',
            uses: 'actions/checkout',
          }),
          build,
        ],
      }),

      deploy: new WorkflowJob({
        id: 'deploy',
        runsOn: 'ubuntu-latest',
        needs: ['build'],
        condition: async ({ event }) =>
          event.name === 'push' && event.branch === 'main',
        steps: [deploy],
      }),
    },
  };
}

// -----------------------------------------------------------------------------
// Asynchronous event-driven demonstration
// -----------------------------------------------------------------------------

async function demonstrateEvents() {
  heading('EVENT-DRIVEN WORKFLOW START');

  const eventBus = new RepositoryEvent();

  eventBus.on('pull_request', (event) => {
    console.log(
      `Pull request event received: #${event.pullRequest.number} ${event.action}`,
    );
  });

  eventBus.on('push', (event) => {
    console.log(`Push event received for branch ${event.branch}`);
  });

  eventBus.emitRepositoryEvent(
    'pull_request',
    createPullRequestEvent('opened', 'main', 'contributor'),
  );

  eventBus.emitRepositoryEvent(
    'push',
    createPushEvent('main', 'release-bot'),
  );
}

// -----------------------------------------------------------------------------
// Matrix demonstration
// -----------------------------------------------------------------------------

function demonstrateMatrixExpansion() {
  heading('MATRIX EXPANSION');

  const matrix = {
    node: ['20', '22'],
    database: ['postgres', 'sqlite'],
  };

  const dimensions = Object.entries(matrix);

  const combinations = dimensions.reduce(
    (current, [name, values]) =>
      current.flatMap((combination) =>
        values.map((value) => ({
          ...combination,
          [name]: value,
        })),
      ),
    [{}],
  );

  for (const combination of combinations) {
    console.log(
      `  variant -> Node ${combination.node}, ${combination.database}`,
    );
  }

  console.log(
    `\n${combinations.length} concrete job variants were produced from one job definition.`,
  );
}

// -----------------------------------------------------------------------------
// Failure and continue-on-error
// -----------------------------------------------------------------------------

async function demonstrateFailureHandling() {
  heading('FAILURE HANDLING AND CONTINUE-ON-ERROR');

  const failingStep = new WorkflowStep({
    name: 'Required security check',
    run: async () => {
      throw new Error('Dependency vulnerability threshold exceeded.');
    },
  });

  const diagnosticStep = new WorkflowStep({
    name: 'Optional diagnostic',
    continueOnError: true,
    run: async () => {
      throw new Error('Diagnostic service unavailable.');
    },
  });

  const recoveryStep = new WorkflowStep({
    name: 'Continue execution',
    run: async ({ log }) => {
      log('This step runs after the non-blocking diagnostic.');
    },
  });

  for (const step of [failingStep, diagnosticStep, recoveryStep]) {
    const result = await step.execute({
      environment: {},
      workspace: { files: [] },
      job: { runsOn: 'ubuntu-latest' },
      event: { name: 'push', branch: 'main' },
      log(message) {
        console.log(`  ${message}`);
      },
      setOutput() {},
      executeAction: async () => {},
    });

    console.log(`  ${step.name}: ${result.status}`);

    if (result.status === 'failure') {
      console.log('  Job execution would stop at this required failure.');
      break;
    }
  }
}

// -----------------------------------------------------------------------------
// Shell execution demonstration
// -----------------------------------------------------------------------------

async function demonstrateNodeExecution() {
  heading('REAL NODE.JS COMMAND EXECUTION');

  /*
   * execFile avoids shell interpretation. This is preferable when arguments
   * originate from variables because it avoids unnecessary shell expansion.
   */
  try {
    const { stdout } = await execFileAsync(
      process.execPath,
      ['-e', 'console.log("Node runner step executed successfully")'],
      {
        env: {
          ...process.env,
          CI: 'true',
        },
      },
    );

    console.log(stdout.trim());
  } catch (error) {
    console.error(`Node command failed: ${error.message}`);
  }

  console.log(
    'Use shell commands deliberately in CI; never place untrusted event data directly into shell source.',
  );
}

// -----------------------------------------------------------------------------
// Workflow configuration inspection
// -----------------------------------------------------------------------------

function inspectWorkflowDefinition(workflow) {
  heading('WORKFLOW FILE SEMANTICS');

  console.log(`Workflow: ${workflow.name}`);
  console.log(`Trigger events: ${Object.keys(workflow.on).join(', ')}`);

  for (const [id, job] of Object.entries(workflow.jobs)) {
    console.log(`\nJob: ${id}`);
    console.log(`  Runner: ${job.runsOn}`);
    console.log(`  Needs: ${job.needs.length ? job.needs.join(', ') : 'none'}`);
    console.log(
      `  Matrix: ${job.matrix ? JSON.stringify(job.matrix) : 'none'}`,
    );

    for (const step of job.steps) {
      const mechanism = step.uses ? `uses: ${step.uses}` : 'run function';
      console.log(`  Step: ${step.name} (${mechanism})`);
    }
  }
}

// -----------------------------------------------------------------------------
// Main program
// -----------------------------------------------------------------------------

async function main() {
  heading('GITHUB ACTIONS BASICS');
  console.log(
    'A JavaScript event-driven model of workflows, events, jobs, and steps.',
  );

  await demonstrateEvents();
  demonstrateMatrixExpansion();

  const workflow = buildContinuousIntegrationWorkflow();
  inspectWorkflowDefinition(workflow);

  heading('PULL REQUEST EVENT');

  const pullRequestEvent = createPullRequestEvent(
    'synchronize',
    'main',
    'contributor',
  );

  const pullRequestEngine = new WorkflowEngine(workflow);
  await pullRequestEngine.execute(pullRequestEvent);

  heading('PUSH TO MAIN');

  /*
   * The same workflow definition receives a different event. The deployment
   * job is conditional, so it runs for a main push but not for a pull request.
   */
  const pushEvent = createPushEvent('main', 'release-bot');

  const pushEngine = new WorkflowEngine(workflow);
  await pushEngine.execute(pushEvent);

  await demonstrateFailureHandling();
  await demonstrateNodeExecution();

  heading('CORE RELATIONSHIP');

  console.log(
    [
      'Workflow file: declares when automation may start and which jobs exist.',
      'Event: supplies the occurrence that can trigger a matching workflow.',
      'Job: defines an isolated execution unit and selects its runner.',
      'Step: performs ordered work inside one job.',
      'needs: creates a dependency graph between jobs.',
      'matrix: expands one job definition into multiple variants.',
      'condition: controls execution based on event or workflow state.',
      'output: exposes selected results from a completed job.',
    ].join('\n'),
  );
}

main().catch((error) => {
  console.error(`\nWorkflow program terminated: ${error.message}`);
  process.exitCode = 1;
});
