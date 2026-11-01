#!/usr/bin/env node

"use strict";

/*
 * Jenkins installation, configuration, and plugin policy simulator.
 *
 * The implementation uses Node.js standard-library features and models:
 * - controller configuration
 * - plugin dependency resolution
 * - asynchronous plugin installation
 * - event-driven audit logging
 * - credential references
 * - pipeline job validation
 * - build execution
 * - merge-safe configuration reporting
 *
 * Secrets are deliberately excluded from exported configuration.
 */

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");

const InstallationState = Object.freeze({
  NEW: "new",
  VALIDATED: "validated",
  INSTALLED: "installed",
  FAILED: "failed",
});

const BuildState = Object.freeze({
  QUEUED: "queued",
  RUNNING: "running",
  SUCCESS: "success",
  FAILED: "failed",
});

class JenkinsError extends Error {}

class ValidationError extends JenkinsError {}

class PluginError extends JenkinsError {}

class BuildError extends JenkinsError {}

class PluginCatalog {
  constructor() {
    this.plugins = new Map();
    this.installed = new Set();
  }

  register(plugin) {
    if (!plugin.name || this.plugins.has(plugin.name)) {
      throw new PluginError(`Duplicate or invalid plugin: ${plugin.name}`);
    }

    if (!/^\d+\.\d+/.test(plugin.version)) {
      throw new PluginError(`Invalid plugin version: ${plugin.name}`);
    }

    this.plugins.set(plugin.name, Object.freeze({
      dependencies: [],
      securityLevel: "approved",
      requiredJava: 17,
      ...plugin,
    }));
  }

  resolve(requested, javaMajor) {
    const resolved = [];
    const visiting = new Set();
    const visited = new Set();

    const visit = (name) => {
      if (visited.has(name)) return;

      if (visiting.has(name)) {
        throw new PluginError(`Circular dependency detected at ${name}`);
      }

      const plugin = this.plugins.get(name);

      if (!plugin) {
        throw new PluginError(`Unknown plugin: ${name}`);
      }

      if (plugin.requiredJava > javaMajor) {
        throw new PluginError(
          `${name} requires Java ${plugin.requiredJava}, ` +
          `but controller uses Java ${javaMajor}.`
        );
      }

      if (plugin.securityLevel !== "approved") {
        throw new PluginError(`Plugin ${name} is not security-approved.`);
      }

      visiting.add(name);

      for (const dependency of plugin.dependencies) {
        visit(dependency);
      }

      visiting.delete(name);
      visited.add(name);
      resolved.push(plugin);
    };

    for (const name of requested) visit(name);
    return resolved;
  }

  async install(requested, javaMajor) {
    const resolved = this.resolve(requested, javaMajor);

    for (const plugin of resolved) {
      await new Promise((resolve) => setTimeout(resolve, 5));
      this.installed.add(plugin.name);
    }

    return resolved;
  }
}

class JenkinsController extends EventEmitter {
  constructor(config) {
    super();

    this.config = Object.freeze({ ...config });
    this.state = InstallationState.NEW;
    this.catalog = new PluginCatalog();
    this.credentials = new Map();
    this.jobs = new Map();
    this.builds = new Map();
    this.audit = [];
  }

  record(event, data = {}) {
    const entry = {
      timestamp: new Date().toISOString(),
      event,
      ...data,
    };

    this.audit.push(entry);
    this.emit("audit", entry);
  }

  validateConfiguration() {
    const c = this.config;

    if (!Number.isInteger(c.javaMajor) || c.javaMajor < 17) {
      throw new ValidationError("Java 17 or newer is required.");
    }

    if (!Number.isInteger(c.httpPort) ||
        c.httpPort < 1024 ||
        c.httpPort > 65535) {
      throw new ValidationError("HTTP port must be between 1024 and 65535.");
    }

    if (!Number.isInteger(c.executors) ||
        c.executors < 1 ||
        c.executors > 32) {
      throw new ValidationError("Executors must be between 1 and 32.");
    }

    if (!c.csrfProtection) {
      throw new ValidationError("CSRF protection must be enabled.");
    }

    if (c.anonymousRead || c.allowSignup) {
      throw new ValidationError(
        "Anonymous access and public signup are disabled."
      );
    }

    if (!/^https?:\/\/.+\/$/.test(c.url)) {
      throw new ValidationError("Controller URL must end with '/'.");
    }

    this.state = InstallationState.VALIDATED;
    this.record("controller.validated");
  }

  install() {
    if (this.state !== InstallationState.VALIDATED) {
      throw new ValidationError("Controller must be validated first.");
    }

    this.state = InstallationState.INSTALLED;
    this.record("controller.installed", {
      controller: this.config.name,
    });
  }

  registerPlugins(plugins) {
    for (const plugin of plugins) {
      this.catalog.register(plugin);
    }
  }

  async installPlugins(pluginNames) {
    if (this.state !== InstallationState.INSTALLED) {
      throw new PluginError("Controller is not installed.");
    }

    const installed = await this.catalog.install(
      pluginNames,
      this.config.javaMajor
    );

    for (const plugin of installed) {
      this.record("plugin.installed", {
        name: plugin.name,
        version: plugin.version,
      });
    }
  }

  addCredential({ id, kind, owner, secret }) {
    if (!/^[A-Za-z0-9._-]{3,64}$/.test(id)) {
      throw new ValidationError("Invalid credential ID.");
    }

    if (!secret || secret.length < 8) {
      throw new ValidationError("Credential secret is too short.");
    }

    if (this.credentials.has(id)) {
      throw new ValidationError(`Credential already exists: ${id}`);
    }

    /*
     * A cryptographic fingerprint permits duplicate detection without
     * exposing the credential value in audit records.
     */
    const fingerprint = crypto
      .createHash("sha256")
      .update(secret)
      .digest("hex");

    this.credentials.set(id, {
      id,
      kind,
      owner,
      fingerprint,
    });

    this.record("credential.registered", { id, kind, owner });
  }

  addJob(job) {
    if (!/^[A-Za-z0-9._/-]{1,120}$/.test(job.name)) {
      throw new ValidationError("Invalid job name.");
    }

    if (!/^https:\/\//.test(job.repository)) {
      throw new ValidationError("Only HTTPS repositories are allowed.");
    }

    if (!job.branch) {
      throw new ValidationError("Branch is required.");
    }

    if (this.jobs.has(job.name)) {
      throw new ValidationError(`Job already exists: ${job.name}`);
    }

    for (const plugin of job.requiredPlugins) {
      if (!this.catalog.installed.has(plugin)) {
        throw new ValidationError(
          `Required plugin is not installed: ${plugin}`
        );
      }
    }

    if (
      job.credentialId &&
      !this.credentials.has(job.credentialId)
    ) {
      throw new ValidationError(
        `Unknown credential: ${job.credentialId}`
      );
    }

    this.jobs.set(job.name, {
      ...job,
      state: BuildState.QUEUED,
      buildNumber: 0,
    });

    this.record("job.created", { job: job.name });
  }

  async runBuild(jobName, testPasses = true) {
    const job = this.jobs.get(jobName);

    if (!job) {
      throw new BuildError(`Unknown job: ${jobName}`);
    }

    job.buildNumber += 1;
    const buildNumber = job.buildNumber;

    job.state = BuildState.RUNNING;
    this.emit("build.started", {
      job: jobName,
      buildNumber,
    });

    const stages = [];

    const executeStage = async (name, action) => {
      await new Promise((resolve) => setTimeout(resolve, 5));

      try {
        action();
        stages.push({ name, status: "SUCCESS" });
      } catch (error) {
        stages.push({
          name,
          status: "FAILED",
          error: error.message,
        });
        throw error;
      }
    };

    try {
      await executeStage("Checkout", () => {});
      await executeStage("Dependency Validation", () => {});

      await executeStage("Test", () => {
        if (!testPasses) {
          throw new BuildError("Automated tests failed.");
        }
      });

      await executeStage("Package", () => {});

      job.state = BuildState.SUCCESS;
    } catch (error) {
      job.state = BuildState.FAILED;
    }

    const result = {
      job: jobName,
      buildNumber,
      state: job.state,
      stages,
    };

    this.builds.set(`${jobName}#${buildNumber}`, result);

    this.record("build.completed", {
      job: jobName,
      buildNumber,
      state: job.state,
    });

    return result;
  }

  exportSafeConfiguration() {
    return JSON.stringify(
      {
        controller: this.config,
        plugins: [...this.catalog.installed],
        credentials: [...this.credentials.values()].map(
          ({ id, kind, owner, fingerprint }) => ({
            id,
            kind,
            owner,
            fingerprint,
          })
        ),
        jobs: [...this.jobs.values()].map((job) => ({
          name: job.name,
          repository: job.repository,
          branch: job.branch,
          credentialId: job.credentialId ?? null,
          requiredPlugins: [...job.requiredPlugins],
        })),
      },
      null,
      2
    );
  }
}

async function main() {
  const controller = new JenkinsController({
    name: "ci-controller-prod",
    jenkinsVersion: "2.5xx",
    javaMajor: 21,
    httpPort: 8080,
    executors: 4,
    csrfProtection: true,
    anonymousRead: false,
    allowSignup: false,
    url: "http://localhost:8080/",
  });

  controller.on("audit", (entry) => {
    if (entry.event === "credential.registered") {
      console.log(`AUDIT: credential ${entry.id} registered`);
    }
  });

  controller.on("build.started", ({ job, buildNumber }) => {
    console.log(`BUILD STARTED: ${job}#${buildNumber}`);
  });

  controller.validateConfiguration();
  controller.install();

  controller.registerPlugins([
    {
      name: "git",
      version: "5.6.0",
      requiredJava: 17,
      dependencies: [],
    },
    {
      name: "credentials",
      version: "1400.1",
      requiredJava: 17,
      dependencies: [],
    },
    {
      name: "workflow-api",
      version: "1400.1",
      requiredJava: 17,
      dependencies: [],
    },
    {
      name: "workflow-job",
      version: "1500.1",
      requiredJava: 17,
      dependencies: ["workflow-api"],
    },
    {
      name: "pipeline-model-definition",
      version: "2.22.0",
      requiredJava: 17,
      dependencies: ["workflow-job", "credentials"],
    },
  ]);

  await controller.installPlugins([
    "git",
    "credentials",
    "pipeline-model-definition",
  ]);

  controller.addCredential({
    id: "git-readonly",
    kind: "username-password",
    owner: "ci-service",
    secret: "example-secret-not-exported",
  });

  controller.addJob({
    name: "orders-service-main",
    repository: "https://git.example.internal/orders-service.git",
    branch: "main",
    credentialId: "git-readonly",
    requiredPlugins: new Set([
      "git",
      "credentials",
      "pipeline-model-definition",
    ]),
  });

  const successfulBuild = await controller.runBuild(
    "orders-service-main",
    true
  );

  const failedBuild = await controller.runBuild(
    "orders-service-main",
    false
  );

  const exported = controller.exportSafeConfiguration();

  if (exported.includes("example-secret-not-exported")) {
    throw new Error("Security failure: credential leaked.");
  }

  console.log("\nSuccessful build:");
  console.log(JSON.stringify(successfulBuild, null, 2));

  console.log("\nFailed build:");
  console.log(JSON.stringify(failedBuild, null, 2));

  console.log("\nSafe controller configuration:");
  console.log(exported);

  console.log("\nAudit event count:", controller.audit.length);
}

main().catch((error) => {
  console.error(`FATAL: ${error.message}`);
  process.exitCode = 1;
});
