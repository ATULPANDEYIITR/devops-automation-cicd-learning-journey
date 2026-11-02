'use strict';

const fs = require('node:fs/promises');
const os = require('node:os');
const path = require('node:path');

const JobStatus = Object.freeze({
  ENABLED: 'enabled',
  DISABLED: 'disabled'
});

const BuildStatus = Object.freeze({
  SUCCESS: 'SUCCESS',
  FAILURE: 'FAILURE',
  ABORTED: 'ABORTED'
});

const TriggerType = Object.freeze({
  MANUAL: 'manual',
  TIMER: 'timer',
  SCM: 'scm',
  UPSTREAM: 'upstream'
});

class JobError extends Error {}

class ParameterDefinition {
  constructor(name, defaultValue, { required = true, choices = [] } = {}) {
    if (!name || !String(name).trim()) {
      throw new JobError('Parameter name cannot be empty');
    }

    this.name = String(name);
    this.defaultValue = String(defaultValue ?? '');
    this.required = required;
    this.choices = new Set(choices.map(String));
  }

  validate(value) {
    const normalized = String(value ?? '').trim();

    if (this.required && normalized.length === 0) {
      throw new JobError(`Parameter ${this.name} cannot be empty`);
    }

    if (this.choices.size > 0 && !this.choices.has(normalized)) {
      throw new JobError(
        `Parameter ${this.name} must be one of: ${[
          ...this.choices
        ].join(', ')}`
      );
    }

    return normalized;
  }
}

class FreestyleJob {
  constructor(name, description, workspaceRoot) {
    this.name = name;
    this.description = description;
    this.workspaceRoot = workspaceRoot;
    this.status = JobStatus.ENABLED;
    this.parameters = new Map();
    this.triggers = new Set();
    this.builders = [];
    this.builds = [];
  }

  addParameter(definition) {
    if (this.parameters.has(definition.name)) {
      throw new JobError(`Duplicate parameter: ${definition.name}`);
    }
    this.parameters.set(definition.name, definition);
  }

  addTrigger(trigger) {
    this.triggers.add(trigger);
  }

  addBuilder(builder) {
    if (typeof builder !== 'function') {
      throw new JobError('Builder must be a function');
    }
    this.builders.push(builder);
  }

  resolveParameters(input = {}) {
    const supplied = new Set(Object.keys(input));

    for (const name of supplied) {
      if (!this.parameters.has(name)) {
        throw new JobError(`Unknown parameter: ${name}`);
      }
    }

    const resolved = {};
    for (const [name, definition] of this.parameters) {
      const value = Object.hasOwn(input, name)
        ? input[name]
        : definition.defaultValue;
      resolved[name] = definition.validate(value);
    }

    return resolved;
  }

  async run(input = {}, trigger = TriggerType.MANUAL) {
    if (this.status !== JobStatus.ENABLED) {
      throw new JobError(`Job ${this.name} is disabled`);
    }

    if (
      trigger !== TriggerType.MANUAL &&
      !this.triggers.has(trigger)
    ) {
      throw new JobError(
        `Trigger ${trigger} is not configured for ${this.name}`
      );
    }

    const parameters = this.resolveParameters(input);
    const number = this.builds.length + 1;
    const workspace = path.join(
      this.workspaceRoot,
      this.name,
      `build-${number}`
    );

    await fs.mkdir(workspace, { recursive: true });

    const build = {
      number,
      parameters,
      trigger,
      workspace,
      status: BuildStatus.SUCCESS,
      log: [],
      startedAt: new Date().toISOString(),
      finishedAt: null
    };

    build.log.push(
      `BUILD #${number} started by ${trigger} trigger`
    );
    build.log.push(`Workspace: ${workspace}`);
    build.log.push(
      `Parameters: ${JSON.stringify(parameters)}`
    );

    try {
      for (const builder of this.builders) {
        await builder(parameters, workspace, build.log);
      }
      build.log.push('Build completed successfully');
    } catch (error) {
      build.status = BuildStatus.FAILURE;
      build.log.push(`Build failed: ${error.message}`);
    } finally {
      build.finishedAt = new Date().toISOString();
      this.builds.push(build);
    }

    return build;
  }
}

async function writeManifest(parameters, workspace, log) {
  const manifest = {
    parameters,
    workspace,
    files: []
  };

  await fs.writeFile(
    path.join(workspace, 'manifest.json'),
    JSON.stringify(manifest, null, 2),
    'utf8'
  );

  log.push('Created manifest.json');
}

async function validateRelease(parameters, _workspace, log) {
  if (
    parameters.ENVIRONMENT === 'production' &&
    parameters.VERSION.startsWith('dev-')
  ) {
    throw new JobError(
      'Production builds cannot use development versions'
    );
  }

  log.push(
    `Release validation passed for ${parameters.ENVIRONMENT}`
  );
}

async function packageArtifact(parameters, workspace, log) {
  const filename =
    `application-${parameters.VERSION}-` +
    `${parameters.ENVIRONMENT}.txt`;

  const content = [
    'Freestyle build artifact',
    `version=${parameters.VERSION}`,
    `environment=${parameters.ENVIRONMENT}`,
    ''
  ].join('\n');

  await fs.writeFile(
    path.join(workspace, filename),
    content,
    'utf8'
  );

  log.push(`Created artifact: ${filename}`);
}

async function archiveHistory(job) {
  const archive = path.join(
    job.workspaceRoot,
    job.name,
    'build-history.json'
  );

  await fs.writeFile(
    archive,
    JSON.stringify(job.builds, null, 2),
    'utf8'
  );

  return archive;
}

async function main() {
  const root = await fs.mkdtemp(
    path.join(os.tmpdir(), 'jenkins-freestyle-')
  );

  const job = new FreestyleJob(
    'release-application',
    'Parameterized Freestyle release workflow',
    root
  );

  job.addParameter(
    new ParameterDefinition('ENVIRONMENT', 'staging', {
      choices: ['development', 'staging', 'production']
    })
  );

  job.addParameter(
    new ParameterDefinition('VERSION', '1.0.0')
  );

  job.addTrigger(TriggerType.TIMER);
  job.addTrigger(TriggerType.SCM);
  job.addTrigger(TriggerType.UPSTREAM);

  job.addBuilder(writeManifest);
  job.addBuilder(validateRelease);
  job.addBuilder(packageArtifact);

  const successfulBuild = await job.run(
    { ENVIRONMENT: 'staging', VERSION: '1.4.0' },
    TriggerType.SCM
  );

  if (successfulBuild.status !== BuildStatus.SUCCESS) {
    throw new Error('Expected first build to succeed');
  }

  const failedBuild = await job.run(
    { ENVIRONMENT: 'production', VERSION: 'dev-2.0.0' },
    TriggerType.UPSTREAM
  );

  if (failedBuild.status !== BuildStatus.FAILURE) {
    throw new Error('Expected invalid production build to fail');
  }

  const productionBuild = await job.run(
    { ENVIRONMENT: 'production', VERSION: '2.0.0' },
    TriggerType.MANUAL
  );

  if (productionBuild.status !== BuildStatus.SUCCESS) {
    throw new Error('Expected production build to succeed');
  }

  const historyFile = await archiveHistory(job);

  console.log('Jenkins Freestyle Job Simulation');
  console.log('================================');
  console.log(`Job: ${job.name}`);
  console.log(
    `Triggers: ${[...job.triggers].sort().join(', ')}`
  );
  console.log(`Build count: ${job.builds.length}`);
  console.log(`History: ${historyFile}`);

  for (const build of job.builds) {
    console.log(
      `\nBuild #${build.number}: ${build.status} ` +
      JSON.stringify(build.parameters)
    );

    for (const line of build.log) {
      console.log(`  ${line}`);
    }
  }
}

main().catch((error) => {
  console.error(`Fatal error: ${error.message}`);
  process.exitCode = 1;
});
