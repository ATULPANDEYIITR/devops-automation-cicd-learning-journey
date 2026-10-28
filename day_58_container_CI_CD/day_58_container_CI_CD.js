#!/usr/bin/env node

"use strict";

const fs = require("node:fs/promises");
const path = require("node:path");
const crypto = require("node:crypto");
const { spawn } = require("node:child_process");

const State = Object.freeze({
  CREATED: "created",
  BUILT: "built",
  TESTED: "tested",
  SCANNED: "scanned",
  PUBLISHED: "published",
  FAILED: "failed"
});

class PipelineError extends Error {
  constructor(message, command = null) {
    super(message);
    this.name = "PipelineError";
    this.command = command;
  }
}

class CommandRunner {
  run(command, args = [], options = {}) {
    const { allowFailure = false } = options;

    return new Promise((resolve, reject) => {
      const child = spawn(command, args, {
        stdio: ["ignore", "pipe", "pipe"],
        shell: false
      });

      let stdout = "";
      let stderr = "";

      child.stdout.on("data", data => {
        const text = data.toString();
        stdout += text;
        process.stdout.write(text);
      });

      child.stderr.on("data", data => {
        const text = data.toString();
        stderr += text;
        process.stderr.write(text);
      });

      child.on("error", error => {
        reject(
          new PipelineError(
            `Unable to start ${command}: ${error.message}`,
            [command, ...args]
          )
        );
      });

      child.on("close", code => {
        if (code !== 0 && !allowFailure) {
          reject(
            new PipelineError(
              `Command exited with status ${code}`,
              [command, ...args]
            )
          );
          return;
        }

        resolve({ code, stdout, stderr });
      });
    });
  }
}

class ImagePolicy {
  constructor() {
    this.requiredStages = ["build", "test", "scan"];
    this.blockedTags = new Set(["latest", "production", "prod"]);
  }

  validate({ repository, tag, registry }) {
    if (!/^[a-z0-9][a-z0-9._/-]*$/.test(repository)) {
      throw new Error("Invalid image repository");
    }

    if (!/^[A-Za-z0-9_.-]+$/.test(tag)) {
      throw new Error("Invalid image tag");
    }

    if (this.blockedTags.has(tag.toLowerCase())) {
      throw new Error(
        "Mutable production-style tags are not permitted by the pipeline policy"
      );
    }

    if (!/^https?:\/\/|^[A-Za-z0-9.-]+(?::[0-9]+)?$/.test(registry)) {
      throw new Error("Invalid registry");
    }
  }
}

class ContainerPipeline {
  constructor(config, runner = new CommandRunner()) {
    this.config = Object.freeze({ ...config });
    this.runner = runner;
    this.policy = new ImagePolicy();
    this.state = State.CREATED;
    this.events = new Map();
    this.findings = [];
    this.digest = null;

    this.policy.validate(config);

    if (!this.config.imageRef) {
      this.config.imageRef =
        `${this.config.registry}/${this.config.repository}:${this.config.tag}`;
    }
  }

  on(eventName, callback) {
    if (!this.events.has(eventName)) {
      this.events.set(eventName, new Set());
    }
    this.events.get(eventName).add(callback);
    return () => this.events.get(eventName)?.delete(callback);
  }

  emit(eventName, payload = {}) {
    for (const callback of this.events.get(eventName) ?? []) {
      try {
        callback({ eventName, state: this.state, ...payload });
      } catch (error) {
        this.findings.push(`Event listener failed: ${error.message}`);
      }
    }
  }

  transition(nextState) {
    this.state = nextState;
    this.emit("stateChanged", { nextState });
  }

  async validateContext() {
    const context = path.resolve(this.config.context);
    const dockerfile = path.resolve(context, this.config.dockerfile);

    const [contextStat, dockerfileStat] = await Promise.all([
      fs.stat(context),
      fs.stat(dockerfile)
    ]);

    if (!contextStat.isDirectory()) {
      throw new Error("Build context is not a directory");
    }

    if (!dockerfileStat.isFile()) {
      throw new Error("Dockerfile is not a regular file");
    }
  }

  async build() {
    await this.validateContext();

    await this.runner.run("docker", [
      "build",
      "--pull",
      "--tag",
      this.config.imageRef,
      "--file",
      path.join(this.config.context, this.config.dockerfile),
      this.config.context
    ]);

    this.transition(State.BUILT);
  }

  async test() {
    if (this.state !== State.BUILT) {
      throw new PipelineError("Tests require a successful image build");
    }

    await this.runner.run("docker", [
      "run",
      "--rm",
      "--read-only",
      "--cap-drop=ALL",
      this.config.imageRef,
      "node",
      "--test",
      "/app/test"
    ]);

    this.transition(State.TESTED);
  }

  async scan() {
    if (this.state !== State.TESTED) {
      throw new PipelineError("Security scanning requires passing tests");
    }

    const scanner = process.env.CONTAINER_SCANNER || "trivy";

    await this.runner.run(scanner, [
      "image",
      "--exit-code",
      "1",
      "--severity",
      "HIGH,CRITICAL",
      this.config.imageRef
    ]);

    this.transition(State.SCANNED);
  }

  async fingerprint() {
    const { stdout } = await this.runner.run("docker", [
      "image",
      "inspect",
      this.config.imageRef,
      "--format",
      "{{json .RepoDigests}}"
    ]);

    this.digest = crypto
      .createHash("sha256")
      .update(stdout)
      .digest("hex");

    return `sha256:${this.digest}`;
  }

  async publish() {
    if (this.state !== State.SCANNED) {
      throw new PipelineError("Publishing requires a clean security scan");
    }

    await this.runner.run("docker", [
      "push",
      this.config.imageRef
    ]);

    await this.fingerprint();
    this.transition(State.PUBLISHED);
  }

  async run({ publish = false } = {}) {
    try {
      await this.build();
      await this.test();
      await this.scan();

      if (publish) {
        await this.publish();
      } else {
        await this.fingerprint();
      }

      return this.report();
    } catch (error) {
      this.findings.push(error.message);
      this.transition(State.FAILED);
      return this.report();
    }
  }

  report() {
    return {
      state: this.state,
      image: this.config.imageRef,
      digest: this.digest,
      findings: [...this.findings]
    };
  }
}

async function createDemoProject() {
  const root = await fs.mkdtemp(path.join(require("node:os").tmpdir(), "node-ci-"));
  const app = path.join(root, "app");
  const tests = path.join(app, "test");

  await fs.mkdir(tests, { recursive: true });

  await fs.writeFile(
    path.join(app, "app.js"),
    "function multiply(a, b) { return a * b; }\nmodule.exports = { multiply };\n"
  );

  await fs.writeFile(
    path.join(tests, "app.test.js"),
    "const test = require('node:test');\n" +
    "const assert = require('node:assert/strict');\n" +
    "const { multiply } = require('../app');\n" +
    "test('multiply', () => assert.equal(multiply(6, 7), 42));\n"
  );

  await fs.writeFile(
    path.join(app, "Dockerfile"),
    "FROM node:22-alpine\n" +
    "WORKDIR /app\n" +
    "COPY . /app\n" +
    "CMD [\"node\", \"--test\", \"/app/test\"]\n"
  );

  return {
    root,
    context: app,
    dockerfile: "Dockerfile"
  };
}

async function main() {
  const publish = process.argv.includes("--publish");
  const userContext = process.argv.find(
    argument => !argument.startsWith("--")
  );

  let demo = null;

  try {
    let context;
    let dockerfile;

    if (userContext) {
      context = path.resolve(userContext);
      dockerfile = "Dockerfile";
    } else {
      demo = await createDemoProject();
      context = demo.context;
      dockerfile = demo.dockerfile;
    }

    const registry = process.env.CONTAINER_REGISTRY || "registry.example.com";
    const repository = process.env.IMAGE_REPOSITORY || "ci-demo/node-app";
    const tag = process.env.IMAGE_TAG || "pipeline";

    const pipeline = new ContainerPipeline({
      context,
      dockerfile,
      registry,
      repository,
      tag,
      imageRef: `${registry}/${repository}:${tag}`
    });

    pipeline.on("stateChanged", event => {
      console.log(`[pipeline] state=${event.nextState}`);
    });

    const result = await pipeline.run({ publish });
    console.log(JSON.stringify(result, null, 2));

    process.exitCode = result.state === State.FAILED ? 1 : 0;
  } finally {
    if (demo) {
      await fs.rm(demo.root, { recursive: true, force: true });
    }
  }
}

main().catch(error => {
  console.error(error.message);
  process.exitCode = 1;
});
