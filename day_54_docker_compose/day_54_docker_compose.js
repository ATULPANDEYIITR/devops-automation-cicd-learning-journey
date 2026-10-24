"use strict";

/**
 * Event-driven Docker Compose policy and lifecycle simulator.
 * Runs with Node.js 18+ and no external packages.
 *
 * This is an educational model, not a replacement for the Docker Engine.
 */

const { EventEmitter } = require("node:events");

const STATES = Object.freeze({
  CREATED: "created",
  STARTING: "starting",
  HEALTHY: "healthy",
  UNHEALTHY: "unhealthy",
  STOPPED: "stopped",
  FAILED: "failed",
});

class ComposeError extends Error {}
class ConfigurationError extends ComposeError {}
class LifecycleError extends ComposeError {}

function validateName(name, kind) {
  if (
    typeof name !== "string" ||
    !/^[a-zA-Z0-9][a-zA-Z0-9_.-]*$/.test(name)
  ) {
    throw new ConfigurationError(`Invalid ${kind} name: ${name}`);
  }
}

class ServiceDefinition {
  constructor({
    name,
    image,
    networks,
    dependsOn = [],
    healthcheck = null,
    restart = "no",
    environment = {},
  }) {
    validateName(name, "service");

    if (typeof image !== "string" || image.trim() === "") {
      throw new ConfigurationError(`${name} requires an image`);
    }

    if (!Array.isArray(networks) || networks.length === 0) {
      throw new ConfigurationError(`${name} must join a network`);
    }

    if (!["no", "on-failure", "always", "unless-stopped"].includes(restart)) {
      throw new ConfigurationError(`Invalid restart policy: ${restart}`);
    }

    for (const dependency of dependsOn) {
      if (!dependency || typeof dependency.service !== "string") {
        throw new ConfigurationError(`Invalid dependency for ${name}`);
      }

      if (!["service_started", "service_healthy"].includes(dependency.condition)) {
        throw new ConfigurationError(
          `Invalid dependency condition for ${name}`
        );
      }
    }

    for (const [key, value] of Object.entries(environment)) {
      if (
        /_(PASSWORD|TOKEN|SECRET)$/.test(key) &&
        (typeof value !== "string" || value.length === 0)
      ) {
        throw new ConfigurationError(`Empty secret variable ${key}`);
      }
    }

    this.name = name;
    this.image = image;
    this.networks = new Set(networks);
    this.dependsOn = dependsOn.map((dependency) => Object.freeze({ ...dependency }));
    this.healthcheck = healthcheck;
    this.restart = restart;
    this.environment = Object.freeze({ ...environment });
    this.state = STATES.CREATED;
    this.attempts = 0;
  }
}

class ComposeProject extends EventEmitter {
  constructor({ name, networks, services }) {
    super();
    validateName(name, "project");

    this.name = name;
    this.networks = new Map();
    this.services = new Map();
    this.events = [];
    this.running = false;

    for (const network of networks) {
      validateName(network.name, "network");

      if (this.networks.has(network.name)) {
        throw new ConfigurationError(`Duplicate network ${network.name}`);
      }

      this.networks.set(
        network.name,
        Object.freeze({
          name: network.name,
          internal: Boolean(network.internal),
          driver: network.driver || "bridge",
        })
      );
    }

    for (const definition of services) {
      if (this.services.has(definition.name)) {
        throw new ConfigurationError(`Duplicate service ${definition.name}`);
      }
      this.services.set(definition.name, definition);
    }
  }

  record(service, event, details = {}) {
    const entry = Object.freeze({
      timestamp: new Date().toISOString(),
      service,
      event,
      details: { ...details },
    });

    this.events.push(entry);
    this.emit("lifecycle", entry);
  }

  validate() {
    if (this.services.size === 0) {
      throw new ConfigurationError("Project has no services");
    }

    for (const service of this.services.values()) {
      for (const network of service.networks) {
        if (!this.networks.has(network)) {
          throw new ConfigurationError(
            `${service.name} references unknown network ${network}`
          );
        }
      }

      for (const dependency of service.dependsOn) {
        const target = this.services.get(dependency.service);

        if (!target || target === service) {
          throw new ConfigurationError(
            `Invalid dependency ${service.name} -> ${dependency.service}`
          );
        }

        if (
          dependency.condition === "service_healthy" &&
          typeof target.healthcheck !== "function"
        ) {
          throw new ConfigurationError(
            `${target.name} requires a healthcheck function`
          );
        }
      }
    }

    this.startupOrder();
    return true;
  }

  startupOrder() {
    const indegree = new Map();
    const dependents = new Map();

    for (const name of this.services.keys()) {
      indegree.set(name, 0);
      dependents.set(name, []);
    }

    for (const service of this.services.values()) {
      for (const dependency of service.dependsOn) {
        indegree.set(service.name, indegree.get(service.name) + 1);
        dependents.get(dependency.service).push(service.name);
      }
    }

    const ready = [...indegree.entries()]
      .filter(([, count]) => count === 0)
      .map(([name]) => name)
      .sort();

    const order = [];

    while (ready.length > 0) {
      const current = ready.shift();
      order.push(current);

      for (const dependent of dependents.get(current).sort()) {
        indegree.set(dependent, indegree.get(dependent) - 1);

        if (indegree.get(dependent) === 0) {
          ready.push(dependent);
          ready.sort();
        }
      }
    }

    if (order.length !== this.services.size) {
      throw new ConfigurationError("Circular dependency detected");
    }

    return order;
  }

  canCommunicate(first, second) {
    const left = this.services.get(first);
    const right = this.services.get(second);

    if (!left || !right) return false;

    for (const network of left.networks) {
      if (right.networks.has(network)) return true;
    }

    return false;
  }

  async start({ maxAttempts = 3, delay = async () => {} } = {}) {
    this.validate();

    if (!Number.isInteger(maxAttempts) || maxAttempts < 1 || maxAttempts > 10) {
      throw new ConfigurationError("maxAttempts must be between 1 and 10");
    }

    const started = [];

    try {
      for (const name of this.startupOrder()) {
        const service = this.services.get(name);

        for (const dependency of service.dependsOn) {
          const parent = this.services.get(dependency.service);

          if (
            dependency.condition === "service_healthy" &&
            parent.state !== STATES.HEALTHY
          ) {
            throw new LifecycleError(
              `${name} requires healthy service ${parent.name}`
            );
          }

          if (
            dependency.condition === "service_started" &&
            ![STATES.STARTING, STATES.HEALTHY, STATES.UNHEALTHY].includes(
              parent.state
            )
          ) {
            throw new LifecycleError(
              `${name} requires started service ${parent.name}`
            );
          }
        }

        service.state = STATES.STARTING;
        this.record(name, "starting");
        started.push(name);

        let healthy = false;

        for (let attempt = 1; attempt <= maxAttempts; attempt += 1) {
          service.attempts += 1;

          try {
            healthy = await service.healthcheck();
          } catch (error) {
            this.record(name, "healthcheck-error", {
              attempt,
              message: error.message,
            });
          }

          if (healthy) break;
          await delay(attempt);
        }

        if (!healthy) {
          service.state = STATES.UNHEALTHY;
          this.record(name, "unhealthy");
          throw new LifecycleError(
            `${name} failed ${maxAttempts} health-check attempts`
          );
        }

        service.state = STATES.HEALTHY;
        this.record(name, "healthy", { attempts: service.attempts });
      }

      this.running = true;
      return this.snapshot();
    } catch (error) {
      for (const name of started.reverse()) {
        const service = this.services.get(name);
        service.state = STATES.STOPPED;
        this.record(name, "rollback-stop");
      }

      this.running = false;
      throw error;
    }
  }

  stop() {
    for (const name of this.startupOrder().reverse()) {
      const service = this.services.get(name);

      if (service.state !== STATES.STOPPED) {
        service.state = STATES.STOPPED;
        this.record(name, "stopped");
      }
    }

    this.running = false;
    return this.snapshot();
  }

  snapshot() {
    return [...this.services.values()]
      .sort((a, b) => a.name.localeCompare(b.name))
      .map((service) => ({
        name: service.name,
        image: service.image,
        state: service.state,
        networks: [...service.networks].sort(),
        attempts: service.attempts,
      }));
  }
}

function createOrdersProject() {
  const networks = [
    { name: "frontend", internal: false },
    { name: "backend", internal: true },
  ];

  const services = [
    new ServiceDefinition({
      name: "db",
      image: "postgres:18",
      networks: ["backend"],
      restart: "unless-stopped",
      environment: {
        POSTGRES_DB: "orders",
        POSTGRES_USER: "app",
      },
      healthcheck: async () => true,
    }),
    new ServiceDefinition({
      name: "api",
      image: "node:22-alpine",
      networks: ["frontend", "backend"],
      dependsOn: [
        { service: "db", condition: "service_healthy" },
      ],
      healthcheck: async () => true,
      restart: "on-failure",
    }),
    new ServiceDefinition({
      name: "web",
      image: "nginx:alpine",
      networks: ["frontend"],
      dependsOn: [
        { service: "api", condition: "service_healthy" },
      ],
      healthcheck: async () => true,
      restart: "unless-stopped",
    }),
  ];

  return new ComposeProject({
    name: "orders-stack",
    networks,
    services,
  });
}

async function main() {
  const project = createOrdersProject();

  project.on("lifecycle", (event) => {
    console.log(
      `${event.service.padEnd(5)} ${event.event}`,
      Object.keys(event.details).length ? event.details : ""
    );
  });

  console.log("Startup order:", project.startupOrder().join(" -> "));
  console.log("API to DB:", project.canCommunicate("api", "db"));
  console.log("Web to DB:", project.canCommunicate("web", "db"));

  await project.start();
  console.log("Running state:", JSON.stringify(project.snapshot(), null, 2));
  project.stop();

  // An unhealthy database prevents dependent services from starting.
  const failing = createOrdersProject();
  failing.services.get("db").healthcheck = async () => false;

  try {
    await failing.start({
      maxAttempts: 2,
      delay: async () => {},
    });
  } catch (error) {
    if (!(error instanceof LifecycleError)) throw error;
    console.log("Expected failure:", error.message);
    console.log("After rollback:", JSON.stringify(failing.snapshot(), null, 2));
  }
}

main().catch((error) => {
  console.error("Fatal error:", error.message);
  process.exitCode = 1;
});
