'use strict';

/*
 * Actions Secrets: secrets, credentials, and secure configuration.
 *
 * This Node.js program models a GitHub Actions-style secret workflow.
 * It intentionally uses an in-memory store so that it is executable without
 * external services. The design separates secret metadata from secret values,
 * evaluates scoped configuration, emits lifecycle events, masks logs, and
 * enforces environment-aware access.
 */

const crypto = require('node:crypto');
const { EventEmitter } = require('node:events');

const SecretScope = Object.freeze({
  ORGANIZATION: 'organization',
  REPOSITORY: 'repository',
  ENVIRONMENT: 'environment'
});

const AccessLevel = Object.freeze({
  READ: 'read',
  WRITE: 'write',
  ADMIN: 'admin'
});

const SecretState = Object.freeze({
  ACTIVE: 'active',
  DISABLED: 'disabled',
  EXPIRED: 'expired'
});

function now() {
  return new Date();
}

function generateCredential(prefix) {
  return `${prefix}_${crypto.randomBytes(32).toString('base64url')}`;
}

function fingerprint(value) {
  return crypto
    .createHash('sha256')
    .update(value, 'utf8')
    .digest('hex')
    .slice(0, 16);
}

function safeEqual(left, right) {
  const leftBuffer = Buffer.from(left, 'utf8');
  const rightBuffer = Buffer.from(right, 'utf8');

  if (leftBuffer.length !== rightBuffer.length) {
    return false;
  }

  return crypto.timingSafeEqual(leftBuffer, rightBuffer);
}

function validateSecretName(name) {
  if (!/^[A-Z][A-Z0-9_]{1,99}$/.test(name)) {
    throw new Error(
      'Secret names must begin with an uppercase letter and contain only uppercase letters, digits, and underscores.'
    );
  }

  if (['PASSWORD', 'SECRET', 'TOKEN', 'KEY'].includes(name)) {
    throw new Error(`Secret name "${name}" is too generic.`);
  }
}

function validateSecretValue(value) {
  if (typeof value !== 'string' || value.length < 12) {
    throw new Error('Secret values must contain at least 12 characters.');
  }

  if (/[\r\n]/.test(value)) {
    throw new Error(
      'Unexpected newline in secret value. Handle multiline credentials explicitly.'
    );
  }
}

class SecretRecord {
  constructor({
    name,
    scope,
    value,
    repository = null,
    environment = null,
    expiresAt = null
  }) {
    this.name = name;
    this.scope = scope;
    this.value = value;
    this.repository = repository;
    this.environment = environment;
    this.createdAt = now();
    this.rotatedAt = null;
    this.expiresAt = expiresAt;
    this.state = SecretState.ACTIVE;
  }

  isUsable() {
    if (this.state !== SecretState.ACTIVE) {
      return false;
    }

    if (this.expiresAt && this.expiresAt <= now()) {
      return false;
    }

    return true;
  }

  metadata() {
    return {
      name: this.name,
      scope: this.scope,
      repository: this.repository,
      environment: this.environment,
      createdAt: this.createdAt.toISOString(),
      rotatedAt: this.rotatedAt?.toISOString() ?? null,
      expiresAt: this.expiresAt?.toISOString() ?? null,
      state: this.state
    };
  }
}

class SecretManager extends EventEmitter {
  constructor() {
    super();
    this.records = new Map();
    this.auditLog = [];

    this.on('secret.created', event => {
      this.auditLog.push({ ...event, action: 'create' });
    });

    this.on('secret.rotated', event => {
      this.auditLog.push({ ...event, action: 'rotate' });
    });

    this.on('secret.read', event => {
      this.auditLog.push({ ...event, action: 'read' });
    });

    this.on('secret.denied', event => {
      this.auditLog.push({ ...event, action: 'denied' });
    });
  }

  key(scope, name, repository, environment) {
    return JSON.stringify([
      scope,
      name,
      repository ?? null,
      environment ?? null
    ]);
  }

  canManage(actor, repository) {
    if (actor.access === AccessLevel.ADMIN) {
      return true;
    }

    return (
      actor.access === AccessLevel.WRITE &&
      repository !== null &&
      actor.repositories.has(repository)
    );
  }

  canRead(actor, repository, environment) {
    if (actor.access === AccessLevel.ADMIN) {
      return true;
    }

    if (!actor.repositories.has(repository)) {
      return false;
    }

    if (environment && actor.environments.size > 0) {
      return actor.environments.has(environment);
    }

    return actor.access === AccessLevel.READ || actor.access === AccessLevel.WRITE;
  }

  setSecret(actor, options) {
    const {
      name,
      value,
      scope,
      repository = null,
      environment = null,
      ttlDays = 90
    } = options;

    validateSecretName(name);
    validateSecretValue(value);

    if (scope === SecretScope.REPOSITORY && !repository) {
      throw new Error('Repository scope requires a repository.');
    }

    if (
      scope === SecretScope.ENVIRONMENT &&
      (!repository || !environment)
    ) {
      throw new Error(
        'Environment scope requires both repository and environment.'
      );
    }

    if (!this.canManage(actor, repository)) {
      throw new Error(`${actor.username} cannot manage this secret.`);
    }

    const key = this.key(scope, name, repository, environment);
    const existing = this.records.get(key);
    const expiresAt = ttlDays === null
      ? null
      : new Date(Date.now() + ttlDays * 24 * 60 * 60 * 1000);

    if (existing) {
      existing.value = value;
      existing.rotatedAt = now();
      existing.expiresAt = expiresAt;
      existing.state = SecretState.ACTIVE;

      this.emit('secret.rotated', {
        timestamp: now().toISOString(),
        actor: actor.username,
        name,
        scope,
        repository,
        environment
      });

      return existing;
    }

    const record = new SecretRecord({
      name,
      value,
      scope,
      repository,
      environment,
      expiresAt
    });

    this.records.set(key, record);

    this.emit('secret.created', {
      timestamp: now().toISOString(),
      actor: actor.username,
      name,
      scope,
      repository,
      environment
    });

    return record;
  }

  resolve(actor, name, repository, environment = null) {
    const candidates = [
      this.key(SecretScope.ENVIRONMENT, name, repository, environment),
      this.key(SecretScope.REPOSITORY, name, repository, null),
      this.key(SecretScope.ORGANIZATION, name, null, null)
    ];

    for (const key of candidates) {
      const record = this.records.get(key);

      if (!record || !record.isUsable()) {
        continue;
      }

      if (!this.canRead(actor, repository, environment)) {
        this.emit('secret.denied', {
          timestamp: now().toISOString(),
          actor: actor.username,
          name,
          scope: record.scope,
          repository,
          environment
        });
        throw new Error('Secret access denied.');
      }

      this.emit('secret.read', {
        timestamp: now().toISOString(),
        actor: actor.username,
        name,
        scope: record.scope,
        repository,
        environment
      });

      return record.value;
    }

    throw new Error(
      `No active secret ${name} for ${repository}/${environment ?? 'default'}.`
    );
  }

  disable(actor, record) {
    if (!this.canManage(actor, record.repository)) {
      throw new Error('Actor cannot disable this secret.');
    }

    record.state = SecretState.DISABLED;
  }

  metadata() {
    return [...this.records.values()].map(record => record.metadata());
  }
}

class SecretMasker {
  constructor(values) {
    this.values = [...new Set(values)]
      .filter(value => value.length >= 4)
      .sort((a, b) => b.length - a.length);
  }

  mask(text) {
    let masked = text;

    for (const value of this.values) {
      masked = masked.split(value).join('***');
    }

    return masked;
  }
}

class ActionsJob {
  constructor(manager, actor, repository, environment) {
    this.manager = manager;
    this.actor = actor;
    this.repository = repository;
    this.environment = environment;
    this.runtimeSecrets = new Map();
  }

  loadSecret(name) {
    const value = this.manager.resolve(
      this.actor,
      name,
      this.repository,
      this.environment
    );

    this.runtimeSecrets.set(name, value);
  }

  runDeployment() {
    this.loadSecret('DEPLOY_TOKEN');

    const token = this.runtimeSecrets.get('DEPLOY_TOKEN');

    const simulatedRunnerOutput =
      `deployment authorization=Bearer ${token} result=success`;

    const masker = new SecretMasker(this.runtimeSecrets.values());

    console.log('Deployment started');
    console.log(`Repository: ${this.repository}`);
    console.log(`Environment: ${this.environment}`);
    console.log(`Credential loaded: ${Boolean(token)}`);
    console.log('Runner output:', masker.mask(simulatedRunnerOutput));

    // Clear runtime references after the job completes. This does not replace
    // process isolation, secret-store controls, or operating-system security.
    this.runtimeSecrets.clear();
  }
}

function evaluateConfiguration(manager, actor, repository, environment, names) {
  return names.map(name => {
    try {
      const value = manager.resolve(
        actor,
        name,
        repository,
        environment
      );

      return {
        name,
        available: true,
        fingerprint: fingerprint(value)
      };
    } catch (error) {
      return {
        name,
        available: false,
        reason: error.message
      };
    }
  });
}

function main() {
  console.log('=== Actions Secrets and Secure Configuration ===');

  const manager = new SecretManager();

  const administrator = {
    username: 'platform-admin',
    access: AccessLevel.ADMIN,
    repositories: new Set(['acme/payments']),
    environments: new Set(['development', 'staging', 'production'])
  };

  const developer = {
    username: 'developer-a',
    access: AccessLevel.WRITE,
    repositories: new Set(['acme/payments']),
    environments: new Set(['development', 'staging'])
  };

  const productionRunner = {
    username: 'production-runner',
    access: AccessLevel.READ,
    repositories: new Set(['acme/payments']),
    environments: new Set(['production'])
  };

  console.log('\n=== Creating scoped configuration ===');

  manager.setSecret(administrator, {
    name: 'NPM_PUBLISH_TOKEN',
    value: generateCredential('npm'),
    scope: SecretScope.ORGANIZATION
  });

  manager.setSecret(administrator, {
    name: 'DATABASE_PASSWORD',
    value: generateCredential('staging-db'),
    scope: SecretScope.REPOSITORY,
    repository: 'acme/payments',
    ttlDays: 60
  });

  manager.setSecret(administrator, {
    name: 'DATABASE_PASSWORD',
    value: generateCredential('production-db'),
    scope: SecretScope.ENVIRONMENT,
    repository: 'acme/payments',
    environment: 'production',
    ttlDays: 30
  });

  manager.setSecret(administrator, {
    name: 'DEPLOY_TOKEN',
    value: generateCredential('production-deploy'),
    scope: SecretScope.ENVIRONMENT,
    repository: 'acme/payments',
    environment: 'production',
    ttlDays: 14
  });

  console.table(manager.metadata());

  console.log('\n=== Scoped resolution ===');

  const stagingPassword = manager.resolve(
    developer,
    'DATABASE_PASSWORD',
    'acme/payments',
    'staging'
  );

  const productionPassword = manager.resolve(
    productionRunner,
    'DATABASE_PASSWORD',
    'acme/payments',
    'production'
  );

  console.log('Staging fingerprint:', fingerprint(stagingPassword));
  console.log('Production fingerprint:', fingerprint(productionPassword));
  console.log(
    'Different credentials:',
    !safeEqual(stagingPassword, productionPassword)
  );

  console.log('\n=== Configuration readiness ===');

  console.table(
    evaluateConfiguration(
      manager,
      productionRunner,
      'acme/payments',
      'production',
      ['DATABASE_PASSWORD', 'DEPLOY_TOKEN', 'NPM_PUBLISH_TOKEN']
    )
  );

  console.log('\n=== Event-driven deployment ===');

  const job = new ActionsJob(
    manager,
    productionRunner,
    'acme/payments',
    'production'
  );

  job.runDeployment();

  console.log('\n=== Unauthorized access ===');

  const externalContributor = {
    username: 'external-contributor',
    access: AccessLevel.READ,
    repositories: new Set(),
    environments: new Set()
  };

  try {
    manager.resolve(
      externalContributor,
      'DATABASE_PASSWORD',
      'acme/payments',
      'production'
    );
  } catch (error) {
    console.log('Access rejected:', error.message);
  }

  console.log('\n=== Rotation ===');

  const beforeRotation = manager.metadata().find(
    item => item.name === 'DEPLOY_TOKEN'
  );

  console.log('Previous metadata:', beforeRotation);

  manager.setSecret(administrator, {
    name: 'DEPLOY_TOKEN',
    value: generateCredential('rotated-production-deploy'),
    scope: SecretScope.ENVIRONMENT,
    repository: 'acme/payments',
    environment: 'production',
    ttlDays: 14
  });

  const afterRotation = manager.metadata().find(
    item => item.name === 'DEPLOY_TOKEN'
  );

  console.log('Rotated metadata:', afterRotation);

  console.log('\n=== Audit events ===');
  console.table(manager.auditLog);

  console.log('\n=== Security properties ===');
  console.log(
    [
      'Secret values are absent from metadata output.',
      'Environment scope separates production credentials from repository defaults.',
      'Access decisions depend on repository and environment authorization.',
      'Rotation replaces the credential while retaining lifecycle metadata.',
      'Event logs record access decisions without storing plaintext values.',
      'Masking is applied to simulated runner output before display.',
      'Short-lived credentials reduce the useful lifetime of leaked values.'
    ]
  );
}

main();
