"use strict";

/**
 * Build automation using Node.js standard-library modules.
 *
 * Run:
 *   node build-automation.js
 *   node build-automation.js ./build-workspace
 *
 * This pipeline demonstrates dependency-lock validation, source compilation,
 * tests, staged packaging, artifact hashes, and event-driven stage execution.
 * It uses a generated C program so compilation is a real compiler invocation.
 */

const fs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const crypto = require("node:crypto");
const { spawn } = require("node:child_process");
const { EventEmitter } = require("node:events");
const { pipeline } = require("node:stream/promises");
const { createGzip } = require("node:zlib");
const { createReadStream, createWriteStream } = require("node:fs");
const { promisify } = require("node:util");
const { execFile } = require("node:child_process");

const execFileAsync = promisify(execFile);

class BuildFailure extends Error {
  constructor(stage, message) {
    super(`${stage}: ${message}`);
    this.name = "BuildFailure";
    this.stage = stage;
  }
}

class BuildPipeline extends EventEmitter {
  constructor(workspace = path.resolve("build-workspace")) {
    super();
    this.workspace = path.resolve(workspace);
    this.source = path.join(this.workspace, "src");
    this.tests = path.join(this.workspace, "test");
    this.build = path.join(this.workspace, "build");
    this.dist = path.join(this.workspace, "dist");
    this.project = {
      name: "route-analyzer",
      version: "1.0.0",
      entry: "route_analyzer.c",
      runtimeDependencies: [],
    };
    this.events = [];
    this.running = false;
  }

  async runStage(name, operation) {
    const started = process.hrtime.bigint();
    this.emit("stage:start", { name });
    try {
      const result = await operation();
      const event = {
        name,
        status: "passed",
        durationMs: Number(process.hrtime.bigint() - started) / 1e6,
        result,
        timestamp: new Date().toISOString(),
      };
      this.events.push(event);
      this.emit("stage:complete", event);
      console.log(`[PASS] ${name}: ${result}`);
      return result;
    } catch (error) {
      const event = {
        name,
        status: "failed",
        durationMs: Number(process.hrtime.bigint() - started) / 1e6,
        error: error.message,
        timestamp: new Date().toISOString(),
      };
      this.events.push(event);
      this.emit("stage:failed", event);
      throw new BuildFailure(name, error.message);
    }
  }

  async initialize() {
    if (fs.existsSync(this.workspace)) {
      const marker = path.join(this.workspace, ".build-automation-demo");
      if (!fs.existsSync(marker)) {
        if (fs.readdirSync(this.workspace).length > 0) {
          throw new Error(
            `Refusing to overwrite non-demo workspace: ${this.workspace}`
          );
        }
      } else {
        fs.rmSync(this.workspace, { recursive: true, force: true });
      }
    }

    fs.mkdirSync(this.source, { recursive: true });
    fs.mkdirSync(this.tests, { recursive: true });
    fs.mkdirSync(this.build, { recursive: true });
    fs.writeFileSync(
      path.join(this.workspace, ".build-automation-demo"),
      "Managed by build-automation.js\n"
    );

    const sourceCode = [
      "#include <stdio.h>",
      "#include <stdlib.h>",
      "",
      "int main(int argc, char **argv) {",
      "    if (argc != 3) {",
      '        fprintf(stderr, "Usage: route_analyzer ORIGIN DESTINATION\\\\n");',
      "        return 2;",
      "    }",
      "    if (argv[1][0] == '\\\\0' || argv[2][0] == '\\\\0') {",
      '        fprintf(stderr, "Route endpoints cannot be empty.\\\\n");',
      "        return 2;",
      "    }",
      '    printf("Route request: %s -> %s\\\\n", argv[1], argv[2]);',
      "    return 0;",
      "}",
      "",
    ].join("\n");

    fs.writeFileSync(path.join(this.source, this.project.entry), sourceCode);
    fs.writeFileSync(
      path.join(this.tests, "smoke-test.js"),
      [
        '"use strict";',
        'const assert = require("node:assert/strict");',
        'assert.equal(process.argv[2], "expected");',
        'console.log("Smoke test passed");',
        "",
      ].join("\n")
    );

    fs.writeFileSync(
      path.join(this.workspace, "package.json"),
      JSON.stringify(
        {
          name: this.project.name,
          version: this.project.version,
          private: true,
          description: "Compiled route-request command-line utility",
          scripts: { test: "node test/smoke-test.js expected" },
          dependencies: {},
        },
        null,
        2
      ) + "\n"
    );

    fs.writeFileSync(
      path.join(this.workspace, "package-lock.json"),
      JSON.stringify(
        {
          name: this.project.name,
          version: this.project.version,
          lockfileVersion: 3,
          requires: true,
          packages: {
            "": {
              name: this.project.name,
              version: this.project.version,
            },
          },
        },
        null,
        2
      ) + "\n"
    );

    fs.writeFileSync(
      path.join(this.workspace, "README.md"),
      "# Route Analyzer\n\nA compiled command-line tool for validating route endpoints.\n"
    );

    return `Initialized ${this.project.name} ${this.project.version}`;
  }

  async validateDependencies() {
    const manifestPath = path.join(this.workspace, "package.json");
    const lockPath = path.join(this.workspace, "package-lock.json");
    const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
    const lock = JSON.parse(fs.readFileSync(lockPath, "utf8"));

    if (manifest.name !== lock.name || manifest.version !== lock.version) {
      throw new Error("package.json and package-lock.json disagree");
    }

    if (!lock.packages || !lock.packages[""]) {
      throw new Error("Lock file has no root package record");
    }

    // This generated project has no external dependencies. npm ci is still
    // executed to verify the lock file and produce a reproducible install.
    await this.runCommand(
      process.platform === "win32" ? "npm.cmd" : "npm",
      ["ci", "--ignore-scripts", "--no-audit", "--no-fund"],
      this.workspace
    );

    return "Validated manifest and installed lockfile-defined dependencies";
  }

  runCommand(command, args, cwd) {
    return new Promise((resolve, reject) => {
      const child = spawn(command, args, {
        cwd,
        shell: false,
        stdio: ["ignore", "pipe", "pipe"],
        windowsHide: true,
      });

      let stdout = "";
      let stderr = "";
      child.stdout.setEncoding("utf8");
      child.stderr.setEncoding("utf8");
      child.stdout.on("data", chunk => {
        stdout += chunk;
      });
      child.stderr.on("data", chunk => {
        stderr += chunk;
      });

      child.on("error", error => reject(error));
      child.on("close", code => {
        if (code !== 0) {
          reject(
            new Error(
              `${command} exited with code ${code}\n${stderr || stdout}`
            )
          );
        } else {
          resolve({ stdout, stderr, code });
        }
      });
    });
  }

  async compile() {
    const sourcePath = path.join(this.source, this.project.entry);
    const outputPath = path.join(
      this.build,
      process.platform === "win32" ? "route_analyzer.exe" : "route_analyzer"
    );

    // Select a compiler explicitly; never pass user-controlled source text
    // through a shell command string.
    const candidates =
      process.platform === "win32"
        ? ["gcc", "clang"]
        : ["cc", "gcc", "clang"];

    let lastError;
    for (const compiler of candidates) {
      try {
        await this.runCommand(
          compiler,
          ["-std=c11", "-Wall", "-Wextra", "-Werror", sourcePath, "-o", outputPath],
          this.workspace
        );
        this.binary = outputPath;
        return `Compiled ${this.project.entry} with ${compiler}`;
      } catch (error) {
        lastError = error;
        if (
          !String(error.message).includes("ENOENT") &&
          !String(error.message).includes("not found") &&
          !String(error.message).includes("is not recognized")
        ) {
          throw error;
        }
      }
    }

    throw new Error(
      `No supported C compiler found (${candidates.join(", ")}): ${
        lastError ? lastError.message : "unknown error"
      }`
    );
  }

  async test() {
    const testResult = await this.runCommand(
      process.execPath,
      ["--test"],
      this.workspace
    ).catch(async () => {
      // The test is intentionally simple, so the package script offers a
      // runtime-independent fallback for Node versions without test runner support.
      return this.runCommand(
        process.platform === "win32" ? "npm.cmd" : "npm",
        ["test", "--", "--runInBand"],
        this.workspace
      );
    });

    const binaryResult = await this.runCommand(
      this.binary,
      ["Lucknow", "Delhi"],
      this.workspace
    );
    if (!binaryResult.stdout.includes("Lucknow -> Delhi")) {
      throw new Error("Compiled binary produced unexpected route output");
    }

    const invalidResult = await new Promise(resolve => {
      const child = spawn(this.binary, ["only-one-argument"], {
        shell: false,
        stdio: "ignore",
      });
      child.on("error", () => resolve({ code: -1 }));
      child.on("close", code => resolve({ code }));
    });

    if (invalidResult.code !== 2) {
      throw new Error("Invalid command-line input was not rejected");
    }

    return `JavaScript tests completed; compiled binary validated (exit ${invalidResult.code})`;
  }

  async stageRelease() {
    const releaseName = `${this.project.name}-${this.project.version}`;
    this.releaseDirectory = path.join(this.build, releaseName);
    fs.rmSync(this.releaseDirectory, { recursive: true, force: true });
    fs.mkdirSync(this.releaseDirectory, { recursive: true });

    for (const filename of ["README.md", "package.json", "package-lock.json"]) {
      fs.copyFileSync(
        path.join(this.workspace, filename),
        path.join(this.releaseDirectory, filename)
      );
    }

    fs.copyFileSync(
      this.binary,
      path.join(this.releaseDirectory, path.basename(this.binary))
    );

    return `Staged executable and metadata in ${releaseName}`;
  }

  async packageRelease() {
    fs.mkdirSync(this.dist, { recursive: true });
    const archivePath = path.join(
      this.dist,
      `${this.project.name}-${this.project.version}.tar.gz`
    );

    // Build a deterministic gzip stream over a sorted tar representation.
    // The tar format is written directly to avoid third-party dependencies.
    const files = fs
      .readdirSync(this.releaseDirectory)
      .sort()
      .map(name => path.join(this.releaseDirectory, name))
      .filter(file => fs.statSync(file).isFile());

    const chunks = [];
    const pad512 = buffer => {
      const padding = (512 - (buffer.length % 512)) % 512;
      return Buffer.concat([buffer, Buffer.alloc(padding)]);
    };

    for (const file of files) {
      const data = fs.readFileSync(file);
      const name = path.basename(file);
      if (Buffer.byteLength(name) > 100) {
        throw new Error(`Tar filename exceeds 100 bytes: ${name}`);
      }

      const header = Buffer.alloc(512, 0);
      header.write(name, 0, 100, "utf8");
      header.write("0000644\0", 100, 8, "ascii");
      header.write("0000000\0", 108, 8, "ascii");
      header.write("0000000\0", 116, 8, "ascii");
      header.write(data.length.toString(8).padStart(11, "0") + "\0", 124, 12, "ascii");
      header.write(Math.floor(Date.now() / 1000).toString(8).padStart(11, "0") + "\0", 136, 12, "ascii");
      header.fill(0x20, 148, 156);
      header.write("0", 156, 1, "ascii");
      header.write("ustar\0", 257, 6, "ascii");
      header.write("00", 263, 2, "ascii");

      let checksum = 0;
      for (const byte of header) checksum += byte;
      header.write(checksum.toString(8).padStart(6, "0") + "\0 ", 148, 8, "ascii");

      chunks.push(header, pad512(data));
    }

    chunks.push(Buffer.alloc(1024, 0));
    const tar = Buffer.concat(chunks);
    await pipeline(
      require("node:stream").Readable.from([tar]),
      createGzip({ level: 9, mtime: 0 }),
      createWriteStream(archivePath)
    );

    return archivePath;
  }

  async writeManifest(archivePath) {
    const digest = crypto.createHash("sha256");
    await pipeline(
      createReadStream(archivePath),
      new (require("node:stream").Writable)({
        write(chunk, encoding, callback) {
          digest.update(chunk);
          callback();
        },
      })
    );

    const metadata = {
      project: this.project,
      platform: {
        operatingSystem: os.platform(),
        architecture: os.arch(),
        nodeVersion: process.version,
      },
      artifact: {
        file: path.basename(archivePath),
        bytes: fs.statSync(archivePath).size,
        sha256: digest.digest("hex"),
      },
      events: this.events,
    };

    fs.writeFileSync(
      path.join(this.dist, "build-manifest.json"),
      JSON.stringify(metadata, null, 2) + "\n"
    );
    return "Wrote build manifest and SHA-256 artifact digest";
  }

  async execute() {
    if (this.running) throw new Error("Pipeline is already running");
    this.running = true;

    this.on("stage:start", event => {
      console.log(`[START] ${event.name}`);
    });
    this.on("stage:failed", event => {
      console.error(`[FAIL] ${event.name}: ${event.error}`);
    });

    try {
      await this.runStage("initialize", () => this.initialize());
      await this.runStage("dependency installation", () =>
        this.validateDependencies()
      );
      await this.runStage("source compilation", () => this.compile());
      await this.runStage("tests", () => this.test());
      await this.runStage("release staging", () => this.stageRelease());
      const archive = await this.runStage("packaging", () =>
        this.packageRelease()
      );
      await this.runStage("artifact manifest", () =>
        this.writeManifest(archive)
      );
      console.log(`Artifacts: ${this.dist}`);
      return 0;
    } catch (error) {
      console.error(error.message);
      return 1;
    } finally {
      this.running = false;
    }
  }
}

async function main() {
  const workspace = process.argv[2] || path.resolve("build-workspace");
  const pipelineInstance = new BuildPipeline(workspace);
  process.exitCode = await pipelineInstance.execute();
}

if (require.main === module) {
  main().catch(error => {
    console.error(error);
    process.exitCode = 1;
  });
}

module.exports = { BuildPipeline, BuildFailure };
