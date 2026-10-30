import { EventEmitter } from "node:events";
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { join, resolve, relative, dirname } from "node:path";
import {
  mkdir,
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
  copyFile,
} from "node:fs/promises";

const APP_SOURCE = String.raw`
import { createServer } from "node:http";
import { fileURLToPath } from "node:url";
import { resolve } from "node:path";

export class InventoryStore {
  #items = new Map();

  add(sku, quantity) {
    if (typeof sku !== "string" || !/^[A-Z0-9][A-Z0-9-]{0,31}$/.test(sku)) {
      throw new TypeError("Invalid SKU");
    }

    if (!Number.isSafeInteger(quantity) || quantity <= 0) {
      throw new TypeError("Quantity must be a positive safe integer");
    }

    if (this.#items.has(sku)) {
      throw new Error("Duplicate SKU");
    }

    this.#items.set(sku, quantity);
  }

  list() {
    return [...this.#items.entries()]
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([sku, quantity]) => ({ sku, quantity }));
  }
}

export function createInventoryServer(store = new InventoryStore()) {
  return createServer((request, response) => {
    if (request.method !== "GET") {
      response.writeHead(405, { "content-type": "application/json" });
      response.end(JSON.stringify({ error: "method_not_allowed" }));
      return;
    }

    if (request.url === "/health") {
      response.writeHead(200, {
        "content-type": "application/json",
        "x-content-type-options": "nosniff",
      });
      response.end(JSON.stringify({ status: "ok" }));
      return;
    }

    if (request.url === "/inventory") {
      response.writeHead(200, {
        "content-type": "application/json",
        "x-content-type-options": "nosniff",
      });
      response.end(JSON.stringify({ items: store.list() }));
      return;
    }

    response.writeHead(404, { "content-type": "application/json" });
    response.end(JSON.stringify({ error: "not_found" }));
  });
}

function startServer() {
  const port = Number(process.env.PORT ?? 8080);

  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new Error("PORT must be an integer between 1 and 65535");
  }

  const store = new InventoryStore();
  store.add("SKU-100", 25);
  store.add("SKU-200", 12);

  const server = createInventoryServer(store);
  server.listen(port, "0.0.0.0", () => {
    console.log("Inventory service listening on port " + port);
  });

  for (const signal of ["SIGINT", "SIGTERM"]) {
    process.on(signal, () => {
      server.close(() => process.exit(0));
    });
  }
}

const currentFile = process.argv[1]
  ? resolve(process.argv[1])
  : "";

if (currentFile === fileURLToPath(import.meta.url)) {
  startServer();
}
`;

const TEST_SOURCE = String.raw`
import test from "node:test";
import assert from "node:assert/strict";
import {
  InventoryStore,
  createInventoryServer,
} from "../src/server.mjs";

test("inventory entries are sorted", () => {
  const store = new InventoryStore();
  store.add("SKU-20", 4);
  store.add("SKU-10", 8);

  assert.deepEqual(store.list(), [
    { sku: "SKU-10", quantity: 8 },
    { sku: "SKU-20", quantity: 4 },
  ]);
});

test("duplicate SKU is rejected", () => {
  const store = new InventoryStore();
  store.add("SKU-10", 2);

  assert.throws(() => store.add("SKU-10", 5), /Duplicate SKU/);
});

test("invalid input is rejected", () => {
  const store = new InventoryStore();

  assert.throws(() => store.add("invalid sku", 1), /Invalid SKU/);
  assert.throws(() => store.add("SKU-10", 0), /positive safe integer/);
  assert.throws(() => store.add("SKU-11", Number.MAX_SAFE_INTEGER + 1));
});

test("health endpoint returns a successful response", async () => {
  const server = createInventoryServer();
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });

  try {
    const address = server.address();
    const response = await fetch("http://127.0.0.1:" + address.port + "/health");

    assert.equal(response.status, 200);
    assert.deepEqual(await response.json(), { status: "ok" });
  } finally {
    await new Promise((resolve, reject) => {
      server.close(error => error ? reject(error) : resolve());
    });
  }
});
`;

const PACKAGE_JSON = {
  name: "inventory-health-service",
  version: "1.0.0",
  private: true,
  type: "module",
  scripts: {
    test: "node --test test/service.test.mjs",
    start: "node src/server.mjs",
  },
  engines: {
    node: ">=18",
  },
};

const DOCKERFILE = `\
FROM node:22-alpine

ENV NODE_ENV=production
ENV PORT=8080

WORKDIR /app

COPY --chown=node:node package.json ./package.json
COPY --chown=node:node src/ ./src/

USER node

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\
  CMD node -e "fetch('http://127.0.0.1:8080/health').then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1))"

CMD ["node", "src/server.mjs"]
`;

const MARKER = ".ci_cd_js_workspace";
const MAX_OUTPUT = 64 * 1024;

class PipelineError extends Error {}

function timestamp() {
  return new Date().toISOString();
}

function sha256(buffer) {
  return createHash("sha256").update(buffer).digest("hex");
}

async function hashFile(path) {
  return sha256(await readFile(path));
}

async function ensureWorkspace(requestedPath) {
  const root = resolve(requestedPath);

  try {
    const details = await stat(root);
    if (details.isSymbolicLink()) {
      throw new PipelineError("Workspace must not be a symbolic link.");
    }
  } catch (error) {
    if (error.code !== "ENOENT") throw error;
  }

  await mkdir(root, { recursive: true });

  const entries = await readdir(root);
  const markerPath = join(root, MARKER);

  if (entries.includes(MARKER)) {
    const markerDetails = await stat(markerPath);
    if (!markerDetails.isFile()) {
      throw new PipelineError("Workspace marker must be a regular file.");
    }
  } else if (entries.length > 0) {
    throw new PipelineError(
      "Refusing to use a non-empty directory without the CI/CD workspace marker.",
    );
  } else {
    await writeFile(
      markerPath,
      "Managed by the JavaScript CI/CD demonstration pipeline.\n",
      { flag: "wx" },
    );
  }

  return root;
}

async function prepareWorkspace(root) {
  for (const directory of ["build", "dist", "docker-context"]) {
    await rm(join(root, directory), { recursive: true, force: true });
  }

  await mkdir(join(root, "src"), { recursive: true });
  await mkdir(join(root, "test"), { recursive: true });

  await writeFile(join(root, "src/server.mjs"), APP_SOURCE, "utf8");
  await writeFile(
    join(root, "test/service.test.mjs"),
    TEST_SOURCE,
    "utf8",
  );
  await writeFile(
    join(root, "package.json"),
    JSON.stringify(PACKAGE_JSON, null, 2) + "\n",
    "utf8",
  );
}

function runCommand(command, args, cwd, timeoutMs = 60_000) {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, {
      cwd,
      shell: false,
      windowsHide: true,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let output = "";
    let finished = false;

    const append = chunk => {
      output += chunk.toString();
      if (output.length > MAX_OUTPUT) {
        output = output.slice(-MAX_OUTPUT);
      }
    };

    child.stdout.on("data", append);
    child.stderr.on("data", append);

    const timeout = setTimeout(() => {
      if (!finished) {
        child.kill("SIGTERM");
        setTimeout(() => {
          if (!child.killed) child.kill("SIGKILL");
        }, 2_000).unref();
      }
    }, timeoutMs);

    child.once("error", error => {
      if (finished) return;
      finished = true;
      clearTimeout(timeout);
      rejectPromise(new PipelineError(`Unable to execute ${command}: ${error.message}`));
    });

    child.once("close", (code, signal) => {
      if (finished) return;
      finished = true;
      clearTimeout(timeout);

      if (code !== 0) {
        rejectPromise(
          new PipelineError(
            `${command} failed (exit=${code}, signal=${signal ?? "none"}).\n${output}`,
          ),
        );
      } else {
        resolvePromise(output.trim());
      }
    });
  });
}

class Pipeline extends EventEmitter {
  constructor(config) {
    super();
    this.config = config;
    this.results = [];
    this.state = new Map();
  }

  async executeStage(name, action) {
    const startedAt = timestamp();
    this.state.set(name, "running");
    this.emit("stage", { name, status: "running", startedAt });

    try {
      const detail = await action();
      const result = {
        name,
        status: "succeeded",
        startedAt,
        finishedAt: timestamp(),
        detail,
      };

      this.state.set(name, "succeeded");
      this.results.push(result);
      this.emit("stage", result);
      return result;
    } catch (error) {
      const result = {
        name,
        status: "failed",
        startedAt,
        finishedAt: timestamp(),
        detail: `${error.name}: ${error.message}`,
      };

      this.state.set(name, "failed");
      this.results.push(result);
      this.emit("stage", result);
      return result;
    }
  }

  async build() {
    const output = await runCommand(
      process.execPath,
      ["--check", "src/server.mjs"],
      this.config.workspace,
    );

    await runCommand(
      process.execPath,
      ["--check", "test/service.test.mjs"],
      this.config.workspace,
    );

    return `Source and test syntax checks passed. ${output}`;
  }

  async test() {
    const output = await runCommand(
      process.execPath,
      ["--test", "test/service.test.mjs"],
      this.config.workspace,
    );

    return output || "Node.js test suite completed successfully.";
  }

  async scan() {
    const sourcePath = join(this.config.workspace, "src/server.mjs");
    const source = await readFile(sourcePath, "utf8");

    const rules = [
      {
        name: "dynamic evaluation",
        expression: /\beval\s*\(|new\s+Function\s*\(/,
      },
      {
        name: "shell or child-process dependency",
        expression: /\bchild_process\b|execSync\s*\(|execFileSync\s*\(/,
      },
      {
        name: "hard-coded credential",
        expression: /(?:api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*["'][^"']{8,}/i,
      },
    ];

    const findings = rules
      .filter(rule => rule.expression.test(source))
      .map(rule => rule.name);

    if (findings.length > 0) {
      throw new PipelineError(
        `Static security policy failed: ${findings.join(", ")}`,
      );
    }

    return "Scanned application source against configured static security rules.";
  }

  async package() {
    const root = this.config.workspace;
    const packageDirectory = join(root, "dist", "package");
    const sourceDirectory = join(packageDirectory, "src");

    await mkdir(sourceDirectory, { recursive: true });

    await copyFile(
      join(root, "src/server.mjs"),
      join(sourceDirectory, "server.mjs"),
    );
    await copyFile(
      join(root, "package.json"),
      join(packageDirectory, "package.json"),
    );

    const files = ["package.json", "src/server.mjs"];
    const entries = [];

    for (const file of files) {
      const fullPath = join(packageDirectory, file);
      entries.push({
        path: file,
        sizeBytes: (await stat(fullPath)).size,
        sha256: await hashFile(fullPath),
      });
    }

    const manifest = {
      application: PACKAGE_JSON.name,
      version: PACKAGE_JSON.version,
      createdAt: timestamp(),
      files: entries,
    };

    await writeFile(
      join(packageDirectory, "manifest.json"),
      JSON.stringify(manifest, null, 2) + "\n",
      "utf8",
    );

    return `Created release directory ${packageDirectory} with SHA-256 file checksums.`;
  }

  async dockerize() {
    const root = this.config.workspace;
    const packageDirectory = join(root, "dist", "package");
    const context = join(root, "docker-context");

    await mkdir(context, { recursive: true });
    await copyFile(
      join(packageDirectory, "package.json"),
      join(context, "package.json"),
    );
    await mkdir(join(context, "src"), { recursive: true });
    await copyFile(
      join(packageDirectory, "src/server.mjs"),
      join(context, "src/server.mjs"),
    );
    await writeFile(join(context, "Dockerfile"), DOCKERFILE, "utf8");

    if (!this.config.dockerEnabled) {
      return `Dockerfile and build context created at ${context}; image build not requested.`;
    }

    const output = await runCommand(
      "docker",
      ["build", "--tag", this.config.imageTag, context],
      root,
      600_000,
    );

    return `Built image ${this.config.imageTag}. ${output}`;
  }

  async run() {
    const stages = [
      ["Build", () => this.build()],
      ["Test", () => this.test()],
      ["Scan", () => this.scan()],
      ["Package", () => this.package()],
      ["Dockerize", () => this.dockerize()],
    ];

    for (let index = 0; index < stages.length; index += 1) {
      const [name, action] = stages[index];
      const result = await this.executeStage(name, action);

      if (result.status === "failed") {
        for (const [skippedName] of stages.slice(index + 1)) {
          const skipped = {
            name: skippedName,
            status: "skipped",
            startedAt: null,
            finishedAt: null,
            detail: "A preceding required stage failed.",
          };
          this.state.set(skippedName, "skipped");
          this.results.push(skipped);
          this.emit("stage", skipped);
        }
        return false;
      }
    }

    return true;
  }
}

function parseArguments(argv) {
  const options = {
    workspace: "ci_cd_js_workspace",
    docker: false,
    tag: "inventory-health-service:1.0.0",
  };

  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];

    if (argument === "--docker") {
      options.docker = true;
    } else if (argument === "--workspace" && argv[index + 1]) {
      options.workspace = argv[++index];
    } else if (argument === "--tag" && argv[index + 1]) {
      options.tag = argv[++index];
    } else {
      throw new PipelineError(`Unknown or incomplete argument: ${argument}`);
    }
  }

  if (!/^[a-z0-9][a-z0-9._/-]*:[A-Za-z0-9][A-Za-z0-9._-]*$/.test(options.tag)) {
    throw new PipelineError("Invalid Docker image tag.");
  }

  return options;
}

async function main() {
  try {
    const options = parseArguments(process.argv.slice(2));
    const workspace = await ensureWorkspace(options.workspace);

    await prepareWorkspace(workspace);

    const pipeline = new Pipeline({
      workspace,
      dockerEnabled: options.docker,
      imageTag: options.tag,
    });

    pipeline.on("stage", event => {
      console.log(`[${event.status.toUpperCase()}] ${event.name}: ${event.detail ?? ""}`);
    });

    const success = await pipeline.run();

    const report = {
      pipeline: "Build -> Test -> Scan -> Package -> Dockerize",
      status: success ? "succeeded" : "failed",
      workspace,
      stages: pipeline.results,
    };

    const reportPath = join(workspace, "pipeline-report.json");
    await writeFile(
      reportPath,
      JSON.stringify(report, null, 2) + "\n",
      "utf8",
    );

    console.log(`Pipeline report: ${reportPath}`);
    process.exitCode = success ? 0 : 1;
  } catch (error) {
    console.error(`Pipeline initialization failed: ${error.message}`);
    process.exitCode = 1;
  }
}

const runningFile = process.argv[1]
  ? resolve(process.argv[1])
  : "";

if (runningFile === fileURLToPath(import.meta.url)) {
  await main();
}
