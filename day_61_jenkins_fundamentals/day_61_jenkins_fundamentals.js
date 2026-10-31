#!/usr/bin/env node
"use strict";

/*
 * Jenkins Fundamentals:
 * controller, agents, jobs, executors, queue events, workspaces,
 * status checks, failures, and policy evaluation.
 *
 * The implementation uses Node.js standard-library features only.
 */

const fs = require("fs/promises");
const os = require("os");
const path = require("path");
const { EventEmitter } = require("events");
const crypto = require("crypto");

const BuildStatus = Object.freeze({
  QUEUED: "queued",
  RUNNING: "running",
  SUCCESS: "success",
  FAILURE: "failure",
  ABORTED: "aborted"
});

class ValidationError extends Error {}
class SchedulingError extends Error {}
class BuildExecutionError extends Error {}

class Agent {
  constructor({ name, labels, executors = 1, online = true }) {
    if (!name || !name.trim()) {
      throw new ValidationError("Agent name is required.");
    }
    if (!Number.isInteger(executors) || executors < 1) {
      throw new ValidationError("Executors must be a positive integer.");
    }

    this.name = name;
    this.labels = new Set(labels);
    this.executors = executors;
    this.online = online;
    this.activeBuilds = new Map();
  }

  canRun(requiredLabels) {
    return (
      this.online &&
      [...requiredLabels].every((label) => this.labels.has(label)) &&
      this.activeBuilds.size < this.executors
    );
  }

  load() {
    return this.activeBuilds.size / this.executors;
  }
}

class Job {
  constructor({ name, kind, labels = [], enabled = true }) {
    if (!name || !name.trim()) {
      throw new ValidationError("Job name is required.");
    }

    this.name = name;
    this.kind = kind;
    this.requiredLabels = new Set(labels);
    this.enabled = enabled;
    this.nextBuildNumber = 1;
    this.history = [];
  }
}

class Build {
  constructor(job, commit) {
    if (!/^[0-9a-f]{7,40}$/i.test(commit.sha)) {
      throw new ValidationError("Commit SHA must contain 7 to 40 hexadecimal characters.");
    }
    if (!commit.message || !commit.message.trim()) {
      throw new ValidationError("Commit message is required.");
    }

    this.id = crypto.randomUUID();
    this.number = job.nextBuildNumber++;
    this.jobName = job.name;
    this.commit = Object.freeze({ ...commit });
    this.status = BuildStatus.QUEUED;
    this.agent = null;
    this.workspace = null;
    this.logs = [];
    this.startedAt = null;
    this.finishedAt = null;
  }

  log(message) {
    this.logs.push({
      timestamp: new Date().toISOString(),
      message
    });
  }

  durationMs() {
    if (this.startedAt === null || this.finishedAt === null) {
      return null;
    }
    return this.finishedAt - this.startedAt;
  }
}

class JenkinsController extends EventEmitter {
  constructor() {
    super();
    this.jobs = new Map();
    this.agents = new Map();
    this.queue = [];
    this.workspaceRoot = null;

    this.on("buildQueued", (build) => {
      console.log(`[event] queued ${build.jobName} #${build.number}`);
    });

    this.on("buildFinished", (build) => {
      console.log(
        `[event] finished ${build.jobName} #${build.number}: ${build.status}`
      );
    });
  }

  async initialize() {
    this.workspaceRoot = await fs.mkdtemp(
      path.join(os.tmpdir(), "jenkins-node-")
    );
  }

  addAgent(agent) {
    if (this.agents.has(agent.name)) {
      throw new ValidationError(`Agent already exists: ${agent.name}`);
    }
    this.agents.set(agent.name, agent);
  }

  addJob(job) {
    if (this.jobs.has(job.name)) {
      throw new ValidationError(`Job already exists: ${job.name}`);
    }
    this.jobs.set(job.name, job);
  }

  queueBuild(jobName, commit) {
    const job = this.jobs.get(jobName);
    if (!job) {
      throw new ValidationError(`Unknown job: ${jobName}`);
    }
    if (!job.enabled) {
      throw new SchedulingError(`Job is disabled: ${jobName}`);
    }

    const build = new Build(job, commit);
    this.queue.push(build);
    this.emit("buildQueued", build);
    return build;
  }

  chooseAgent(job) {
    const candidates = [...this.agents.values()]
      .filter((agent) => agent.canRun(job.requiredLabels))
      .sort((a, b) => a.load() - b.load());

    return candidates[0] ?? null;
  }

  async createWorkspace(agent, build) {
    const safeJobName = build.jobName.replace(/[^a-zA-Z0-9._-]/g, "_");
    const directory = path.join(
      this.workspaceRoot,
      agent.name,
      `${safeJobName}-${build.number}`
    );

    await fs.mkdir(directory, { recursive: true });
    build.workspace = directory;
    return directory;
  }

  async runBuild(build) {
    const job = this.jobs.get(build.jobName);
    if (!job) {
      throw new SchedulingError(`Job disappeared: ${build.jobName}`);
    }

    const agent = this.chooseAgent(job);
    if (!agent) {
      return false;
    }

    const queueIndex = this.queue.indexOf(build);
    if (queueIndex >= 0) {
      this.queue.splice(queueIndex, 1);
    }

    build.status = BuildStatus.RUNNING;
    build.agent = agent.name;
    build.startedAt = Date.now();
    agent.activeBuilds.set(build.id, build);

    try {
      const workspace = await this.createWorkspace(agent, build);

      build.log(`Assigned to agent ${agent.name}.`);
      build.log(`Preparing workspace ${workspace}.`);

      await fs.writeFile(
        path.join(workspace, "commit.json"),
        JSON.stringify(build.commit, null, 2),
        "utf8"
      );

      const stored = JSON.parse(
        await fs.readFile(path.join(workspace, "commit.json"), "utf8")
      );

      if (stored.sha !== build.commit.sha) {
        throw new BuildExecutionError("Checkout integrity validation failed.");
      }

      build.log("Checkout validation passed.");

      if (build.commit.message.toUpperCase().includes("[FAIL]")) {
        throw new BuildExecutionError(
          "Build failed because the commit requested a failure path."
        );
      }

      await this.runPolicyCheck(job, build);

      build.status = BuildStatus.SUCCESS;
      build.log("Build completed successfully.");
    } catch (error) {
      build.status = BuildStatus.FAILURE;
      build.log(error.message);
    } finally {
      build.finishedAt = Date.now();
      agent.activeBuilds.delete(build.id);
      job.history.push(build);
      this.emit("buildFinished", build);
    }

    return true;
  }

  async runPolicyCheck(job, build) {
    if (job.kind === "pipeline" && !build.commit.message.trim()) {
      throw new BuildExecutionError("Pipeline commit message cannot be empty.");
    }

    build.log(`Policy check passed for ${job.kind} job.`);
  }

  async drainQueue() {
    while (this.queue.length > 0) {
      const candidate = this.queue.find((build) => {
        const job = this.jobs.get(build.jobName);
        return Boolean(job && this.chooseAgent(job));
      });

      if (!candidate) {
        throw new SchedulingError(
          "Queued builds cannot currently be assigned to compatible agents."
        );
      }

      await this.runBuild(candidate);
    }
  }

  status() {
    return {
      jobs: Object.fromEntries(
        [...this.jobs.entries()].map(([name, job]) => [
          name,
          {
            kind: job.kind,
            enabled: job.enabled,
            builds: job.history.map((build) => ({
              number: build.number,
              status: build.status,
              agent: build.agent,
              durationMs: build.durationMs()
            }))
          }
        ])
      ),
      agents: Object.fromEntries(
        [...this.agents.entries()].map(([name, agent]) => [
          name,
          {
            online: agent.online,
            labels: [...agent.labels].sort(),
            executors: agent.executors,
            busy: agent.activeBuilds.size
          }
        ])
      ),
      queued: this.queue.length
    };
  }
}

async function main() {
  const controller = new JenkinsController();
  await controller.initialize();

  controller.addAgent(
    new Agent({
      name: "linux-python",
      labels: ["linux", "python", "container"],
      executors: 2
    })
  );

  controller.addAgent(
    new Agent({
      name: "linux-java",
      labels: ["linux", "java"],
      executors: 1
    })
  );

  controller.addAgent(
    new Agent({
      name: "offline",
      labels: ["linux", "python"],
      online: false
    })
  );

  controller.addJob(
    new Job({
      name: "python-service",
      kind: "pipeline",
      labels: ["linux", "python"]
    })
  );

  controller.addJob(
    new Job({
      name: "java-service",
      kind: "freestyle",
      labels: ["linux", "java"]
    })
  );

  const commits = [
    {
      sha: "a1b2c3d4",
      message: "Validate service configuration"
    },
    {
      sha: "e5f6a7b8",
      message: "[FAIL] exercise deterministic failure handling"
    },
    {
      sha: "11223344",
      message: "Improve Java build validation"
    }
  ];

  controller.queueBuild("python-service", commits[0]);
  controller.queueBuild("python-service", commits[1]);
  controller.queueBuild("java-service", commits[2]);

  await controller.drainQueue();

  const state = controller.status();

  for (const [name, job] of Object.entries(state.jobs)) {
    for (const build of job.builds) {
      console.log(
        `${name} #${build.number}: ${build.status}, ` +
        `agent=${build.agent}, duration=${build.durationMs}ms`
      );
    }
  }

  console.log("\nController state:");
  console.log(JSON.stringify(state, null, 2));

  if (state.queued !== 0) {
    throw new Error("Queue should be empty after drainQueue().");
  }

  console.log("\nOperational checks passed.");
}

main().catch((error) => {
  console.error(`Fatal error: ${error.message}`);
  process.exitCode = 1;
});
