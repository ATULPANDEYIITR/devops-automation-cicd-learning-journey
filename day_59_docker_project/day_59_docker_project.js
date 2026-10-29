'use strict';

/**
 * Multi-service Docker application orchestration model.
 *
 * The implementation focuses on event-driven service lifecycle behavior,
 * dependency health, policy validation, network membership, and recovery.
 * It uses only Node.js standard-library features.
 */

const { EventEmitter } = require('node:events');

const ServiceState = Object.freeze({
  CREATED: 'created',
  STARTING: 'starting',
  HEALTHY: 'healthy',
  UNHEALTHY: 'unhealthy',
  STOPPED: 'stopped'
});

const DependencyCondition = Object.freeze({
  STARTED: 'service_started',
  HEALTHY: 'service_healthy'
});

class ConfigurationError extends Error {}

class DependencyError extends Error {}

class Service {
  constructor({
    name,
    image,
    hostPort = null,
    environment = {},
    dependencies = [],
    memoryMb = 256
  }) {
    this.name = name;
    this.image = image;
    this.hostPort = hostPort;
    this.environment = { ...environment };
    this.dependencies = dependencies.map((dependency) => ({ ...dependency }));
    this.memoryMb = memoryMb;
    this.state = ServiceState.CREATED;
    this.restartCount = 0;
  }

  validate() {
    if (!/^[a-z0-9][a-z0-9-]*$/.test(this.name)) {
      throw new ConfigurationError(`Invalid service name: ${this.name}`);
    }

    if (!this.image || !this.image.includes(':')) {
      throw new ConfigurationError(
        `${this.name}: image must use an explicit version tag`
      );
    }

    if (
      this.hostPort !== null &&
      (!Number.isInteger(this.hostPort) ||
        this.hostPort < 1 ||
        this.hostPort > 65535)
    ) {
      throw new ConfigurationError(
        `${this.name}: invalid host port ${this.hostPort}`
      );
    }

    if (!Number.isInteger(this.memoryMb) || this.memoryMb < 64) {
      throw new ConfigurationError(
        `${this.name}: memory allocation must be at least 64 MB`
      );
    }

    for (const [key, value] of Object.entries(this.environment)) {
      if (!/^[A-Z][A-Z0-9_]*$/.test(key)) {
        throw new ConfigurationError(
          `${this.name}: invalid environment variable ${key}`
        );
      }

      if (String(value).includes('\0')) {
        throw new ConfigurationError(
          `${this.name}: environment value contains NUL`
        );
      }
    }
  }
}

class ApplicationNetwork {
  constructor(name) {
    this.name = name;
    this.members = new Set();
  }

  connect(service) {
    this.members.add(service);
  }

  disconnect(service) {
    this.members.delete(service);
  }

  canReach(source, destination) {
    return this.members.has(source) && this.members.has(destination);
  }
}

class ComposePolicy {
  constructor(services) {
    this.services = new Map(services.map((service) => [service.name, service]));
  }

  validate() {
    if (this.services.size === 0) {
      throw new ConfigurationError('No services configured');
    }

    const ports = new Map();

    for (const service of this.services.values()) {
      service.validate();

      if (service.hostPort !== null) {
        if (ports.has(service.hostPort)) {
          throw new ConfigurationError(
            `Host port ${service.hostPort} is used by both ` +
            `${ports.get(service.hostPort)} and ${service.name}`
          );
        }

        ports.set(service.hostPort, service.name);
      }

      for (const dependency of service.dependencies) {
        if (!this.services.has(dependency.service)) {
          throw new ConfigurationError(
            `${service.name}: missing dependency ${dependency.service}`
          );
        }

        if (dependency.service === service.name) {
          throw new ConfigurationError(
            `${service.name}: self-dependency is not allowed`
          );
        }

        if (
          dependency.condition !== DependencyCondition.STARTED &&
          dependency.condition !== DependencyCondition.HEALTHY
        ) {
          throw new ConfigurationError(
            `${service.name}: unsupported dependency condition`
          );
        }
      }
    }

    this.#assertAcyclic();
  }

  #assertAcyclic() {
    const visiting = new Set();
    const visited = new Set();

    const visit = (name) => {
      if (visiting.has(name)) {
        throw new ConfigurationError('Dependency cycle detected');
      }

      if (visited.has(name)) {
        return;
      }

      visiting.add(name);

      for (const dependency of this.services.get(name).dependencies) {
        visit(dependency.service);
      }

      visiting.delete(name);
      visited.add(name);
    };

    for (const name of this.services.keys()) {
      visit(name);
    }
  }

  startupOrder() {
    const indegree = new Map();
    const graph = new Map();

    for (const name of this.services.keys()) {
      indegree.set(name, 0);
      graph.set(name, []);
    }

    for (const service of this.services.values()) {
      for (const dependency of service.dependencies) {
        graph.get(dependency.service).push(service.name);
        indegree.set(service.name, indegree.get(service.name) + 1);
      }
    }

    const queue = [...indegree.entries()]
      .filter(([, degree]) => degree === 0)
      .map(([name]) => name);

    const result = [];

    while (queue.length > 0) {
      const current = queue.shift();
      result.push(current);

      for (const dependent of graph.get(current)) {
        indegree.set(dependent, indegree.get(dependent) - 1);

        if (indegree.get(dependent) === 0) {
          queue.push(dependent);
        }
      }
    }

    if (result.length !== this.services.size) {
      throw new ConfigurationError('Unable to resolve startup order');
    }

    return result;
  }
}

class Orchestrator extends EventEmitter {
  constructor(services) {
    super();

    this.services = new Map(
      services.map((service) => [service.name, service])
    );

    this.policy = new ComposePolicy(services);
    this.network = new ApplicationNetwork('application-network');

    this.on('service-started', ({ name }) => {
      console.log(`[event] ${name} started`);
    });

    this.on('service-healthy', ({ name }) => {
      console.log(`[event] ${name} is healthy`);
    });

    this.on('service-stopped', ({ name }) => {
      console.log(`[event] ${name} stopped`);
    });

    this.on('service-restarted', ({ name, count }) => {
      console.log(`[event] ${name} restarted, count=${count}`);
    });
  }

  validate() {
    this.policy.validate();
  }

  dependenciesReady(service) {
    return service.dependencies.every((dependency) => {
      const target = this.services.get(dependency.service);

      if (dependency.condition === DependencyCondition.STARTED) {
        return (
          target.state === ServiceState.STARTING ||
          target.state === ServiceState.HEALTHY
        );
      }

      return target.state === ServiceState.HEALTHY;
    });
  }

  async start(name) {
    const service = this.services.get(name);

    if (!service) {
      throw new DependencyError(`Unknown service ${name}`);
    }

    if (service.state === ServiceState.HEALTHY) {
      return;
    }

    if (!this.dependenciesReady(service)) {
      throw new DependencyError(
        `${name}: dependencies are not ready`
      );
    }

    service.state = ServiceState.STARTING;
    this.network.connect(name);
    this.emit('service-started', { name });

    // A Promise models asynchronous container startup.
    await new Promise((resolve) => setTimeout(resolve, 10));

    service.state = ServiceState.HEALTHY;
    this.emit('service-healthy', { name });
  }

  async startAll() {
    this.validate();

    const order = this.policy.startupOrder();

    for (const name of order) {
      await this.start(name);
    }

    return order;
  }

  stop(name) {
    const service = this.services.get(name);

    if (!service) {
      throw new DependencyError(`Unknown service ${name}`);
    }

    service.state = ServiceState.STOPPED;
    this.network.disconnect(name);
    this.emit('service-stopped', { name });
  }

  async restart(name) {
    const service = this.services.get(name);

    if (!service) {
      throw new DependencyError(`Unknown service ${name}`);
    }

    this.stop(name);
    service.restartCount += 1;
    await this.start(name);

    this.emit('service-restarted', {
      name,
      count: service.restartCount
    });
  }

  setHealth(name, healthy) {
    const service = this.services.get(name);

    if (!service) {
      throw new DependencyError(`Unknown service ${name}`);
    }

    service.state = healthy
      ? ServiceState.HEALTHY
      : ServiceState.UNHEALTHY;
  }

  status() {
    return [...this.services.values()]
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((service) => ({
        name: service.name,
        state: service.state,
        image: service.image,
        memoryMb: service.memoryMb,
        restartCount: service.restartCount
      }));
  }

  printStatus() {
    console.table(this.status());

    console.log(
      `network members: ${[...this.network.members].sort().join(', ')}`
    );
  }
}

function buildApplication() {
  return [
    new Service({
      name: 'db',
      image: 'postgres:18',
      hostPort: 5432,
      environment: {
        POSTGRES_DB: 'orders',
        POSTGRES_USER: 'app',
        POSTGRES_PASSWORD: 'development-only-secret'
      },
      memoryMb: 512
    }),

    new Service({
      name: 'redis',
      image: 'redis:8',
      hostPort: 6379,
      memoryMb: 256
    }),

    new Service({
      name: 'api',
      image: 'orders-api:1.0',
      hostPort: 8080,
      environment: {
        DATABASE_HOST: 'db',
        REDIS_HOST: 'redis'
      },
      dependencies: [
        {
          service: 'db',
          condition: DependencyCondition.HEALTHY
        },
        {
          service: 'redis',
          condition: DependencyCondition.HEALTHY
        }
      ],
      memoryMb: 512
    }),

    new Service({
      name: 'worker',
      image: 'orders-worker:1.0',
      environment: {
        DATABASE_HOST: 'db',
        REDIS_HOST: 'redis'
      },
      dependencies: [
        {
          service: 'db',
          condition: DependencyCondition.HEALTHY
        },
        {
          service: 'redis',
          condition: DependencyCondition.HEALTHY
        }
      ],
      memoryMb: 384
    }),

    new Service({
      name: 'frontend',
      image: 'orders-frontend:1.0',
      hostPort: 3000,
      environment: {
        API_BASE_URL: 'http://api:8080'
      },
      dependencies: [
        {
          service: 'api',
          condition: DependencyCondition.HEALTHY
        }
      ],
      memoryMb: 256
    })
  ];
}

function runValidationTests() {
  const invalid = new Service({
    name: 'api',
    image: 'api',
    hostPort: 8080
  });

  try {
    new ComposePolicy([invalid]).validate();
    throw new Error('Expected invalid image validation to fail');
  } catch (error) {
    if (!(error instanceof ConfigurationError)) {
      throw error;
    }
  }

  const a = new Service({
    name: 'a',
    image: 'a:1',
    dependencies: [{ service: 'b', condition: DependencyCondition.STARTED }]
  });

  const b = new Service({
    name: 'b',
    image: 'b:1',
    dependencies: [{ service: 'a', condition: DependencyCondition.STARTED }]
  });

  try {
    new ComposePolicy([a, b]).validate();
    throw new Error('Expected dependency cycle validation to fail');
  } catch (error) {
    if (!(error instanceof ConfigurationError)) {
      throw error;
    }
  }
}

async function main() {
  runValidationTests();

  const orchestrator = new Orchestrator(buildApplication());

  console.log('VALIDATING CONFIGURATION');
  orchestrator.validate();

  console.log('\nSTARTING APPLICATION');
  const order = await orchestrator.startAll();

  console.log(`startup order: ${order.join(' -> ')}`);
  orchestrator.printStatus();

  if (!orchestrator.network.canReach('frontend', 'api')) {
    throw new Error('frontend must reach api');
  }

  if (!orchestrator.network.canReach('api', 'db')) {
    throw new Error('api must reach db');
  }

  if (orchestrator.network.canReach('frontend', 'db')) {
    throw new Error(
      'Frontend should not depend directly on the database'
    );
  }

  console.log('\nSIMULATING REDIS FAILURE');
  orchestrator.setHealth('redis', false);
  orchestrator.printStatus();

  console.log('\nRECOVERING REDIS');
  await orchestrator.restart('redis');
  orchestrator.printStatus();

  console.log('\nSTOPPING FRONTEND');
  orchestrator.stop('frontend');
  orchestrator.printStatus();

  console.log('\nAPPLICATION RUN COMPLETE');
}

main().catch((error) => {
  console.error(`fatal: ${error.message}`);
  process.exitCode = 1;
});
