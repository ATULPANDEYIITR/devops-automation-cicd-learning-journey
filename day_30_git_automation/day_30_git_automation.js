"use strict";

/*
 * Git Automation: hooks, commit validation, and automated checks.
 *
 * This Node.js program models a repository automation pipeline without
 * requiring third-party packages. It demonstrates:
 *   - commit-message validation
 *   - staged-file inspection
 *   - secret-pattern detection
 *   - event-driven automation
 *   - asynchronous validation
 *   - pre-commit and commit-msg hook concepts
 *   - CI-style policy evaluation
 *   - machine-readable audit output
 *
 * The program operates on a temporary demonstration repository.
 */

const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");
const { execFile } = require("node:child_process");
const { promisify } = require("node:util");

const execFileAsync = promisify(execFile);

const commitPattern =
  /^(feat|fix|docs|refactor|test|build|ci|chore|perf|style|revert)(\([a-z0-9._/-]+\))?!?: .{1,100}$/;

const secretPatterns = [
  /\bgithub_pat_[A-Za-z0-9_]{20,}/i,
  /\bghp_[A-Za-z0-9]{20,}/i,
  /\baws(.{0,20})?(access[_-]?key|secret)[^\n]{0,80}/i,
  /\b(api[_-]?key|secret[_-]?key)\s*[:=]\s*["'][^"']{8,}/i,
];

const supportedTextExtensions = new Set([
  ".py",
  ".js",
  ".ts",
  ".tsx",
  ".jsx",
  ".cpp",
  ".h",
  ".hpp",
  ".md",
  ".txt",
  ".json",
  ".yaml",
  ".yml",
  ".toml",
]);

class CheckResult {
  constructor(name, passed, message, details = []) {
    this.name = name;
    this.passed = passed;
    this.message = message;
    this.details = details;
  }

  toString() {
    const status = this.passed ? "PASS" : "FAIL";
    const details =
      this.details.length > 0 ? ` | ${this.details.join("; ")}` : "";
    return `[${status}] ${this.name}: ${this.message}${details}`;
  }
}

class AutomationEngine {
  constructor(repositoryPath) {
    this.repositoryPath = repositoryPath;
    this.events = new Map();
  }

  on(eventName, listener) {
    if (!this.events.has(eventName)) {
      this.events.set(eventName, []);
    }

    this.events.get(eventName).push(listener);
  }

  /*
   * The event emitter is deliberately small because the interesting behavior
   * is the Git workflow: one lifecycle event can trigger several independent
   * checks without tightly coupling the checks to one another.
   */
  async emit(eventName, payload = {}) {
    const listeners = this.events.get(eventName) || [];
    const results = [];

    for (const listener of listeners) {
      results.push(await listener(payload));
    }

    return results;
  }

  async runGit(...argumentsList) {
    try {
      const result = await execFileAsync("git", argumentsList, {
        cwd: this.repositoryPath,
        maxBuffer: 1024 * 1024,
      });

      return {
        code: 0,
        stdout: result.stdout.trim(),
        stderr: result.stderr.trim(),
      };
    } catch (error) {
      return {
        code: typeof error.code === "number" ? error.code : 1,
        stdout: error.stdout ? String(error.stdout).trim() : "",
        stderr: error.stderr ? String(error.stderr).trim() : error.message,
      };
    }
  }

  async stagedFiles() {
    const result = await this.runGit(
      "diff",
      "--cached",
      "--name-only",
      "--diff-filter=ACMR"
    );

    if (result.code !== 0) {
      throw new Error(result.stderr || "Unable to inspect Git index");
    }

    return result.stdout
      .split(/\r?\n/)
      .map((file) => file.trim())
      .filter(Boolean);
  }

  validateCommitMessage(message) {
    const subject = message.trim().split(/\r?\n/, 1)[0] || "";

    if (!subject) {
      return new CheckResult(
        "commit-message",
        false,
        "The commit subject is empty."
      );
    }

    if (!commitPattern.test(subject)) {
      return new CheckResult(
        "commit-message",
        false,
        "The commit subject violates the configured format.",
        ["Expected example: fix(parser): reject malformed input"]
      );
    }

    return new CheckResult(
      "commit-message",
      true,
      "The commit subject satisfies the configured format."
    );
  }

  async validateStagedPaths() {
    const files = await this.stagedFiles();
    const violations = [];

    for (const file of files) {
      const normalized = file.replaceAll("\\", "/");

      if (
        normalized.split("/").some((part) =>
          [".git", "node_modules", "__pycache__", ".venv"].includes(part)
        )
      ) {
        violations.push(`${file}: generated or dependency path`);
      }

      if (path.isAbsolute(file)) {
        violations.push(`${file}: absolute path`);
      }
    }

    return new CheckResult(
      "staged-path-policy",
      violations.length === 0,
      violations.length === 0
        ? "Staged paths satisfy repository policy."
        : "Staged paths contain policy violations.",
      violations
    );
  }

  async validateFileSizes() {
    const files = await this.stagedFiles();
    const limit = 512 * 1024;
    const violations = [];

    for (const file of files) {
      const absolutePath = path.join(this.repositoryPath, file);

      try {
        const stat = await fs.stat(absolutePath);
        if (stat.isFile() && stat.size > limit) {
          violations.push(`${file}: exceeds ${limit} bytes`);
        }
      } catch {
        // A deleted or concurrently changed path is handled by Git itself.
      }
    }

    return new CheckResult(
      "file-size-policy",
      violations.length === 0,
      violations.length === 0
        ? "Staged files are below the configured size limit."
        : "A staged file exceeds the configured size limit.",
      violations
    );
  }

  async scanSecrets() {
    const files = await this.stagedFiles();
    const findings = [];

    for (const file of files) {
      const extension = path.extname(file).toLowerCase();

      if (!supportedTextExtensions.has(extension)) {
        continue;
      }

      try {
        const content = await fs.readFile(
          path.join(this.repositoryPath, file),
          "utf8"
        );

        for (const pattern of secretPatterns) {
          if (pattern.test(content)) {
            findings.push(`Potential secret in ${file}`);
            break;
          }
        }
      } catch {
        // Binary or unavailable content is not treated as a secret finding.
      }
    }

    return new CheckResult(
      "secret-scan",
      findings.length === 0,
      findings.length === 0
        ? "No configured secret patterns were detected."
        : "Potential credential material was detected.",
      findings
    );
  }

  async checkWhitespace() {
    const files = await this.stagedFiles();
    const findings = [];

    for (const file of files) {
      const extension = path.extname(file).toLowerCase();

      if (!supportedTextExtensions.has(extension)) {
        continue;
      }

      try {
        const content = await fs.readFile(
          path.join(this.repositoryPath, file),
          "utf8"
        );

        content.split(/\r?\n/).forEach((line, index) => {
          if (/[ \t]$/.test(line)) {
            findings.push(`${file}:${index + 1}`);
          }
        });
      } catch {
        // Non-text content is outside this whitespace check.
      }
    }

    return new CheckResult(
      "whitespace",
      findings.length === 0,
      findings.length === 0
        ? "No trailing whitespace was found."
        : "Trailing whitespace was found.",
      findings
    );
  }

  async runTests() {
    /*
     * The check executes a tiny Node test directly instead of requiring npm
     * dependencies. In a production project this event could invoke the
     * repository's existing test command.
     */
    const testScript = `
      function add(a, b) {
        return a + b;
      }

      if (add(2, 3) !== 5) {
        process.exit(1);
      }

      if (add(-5, 8) !== 3) {
        process.exit(1);
      }
    `;

    const temporaryTest = path.join(
      this.repositoryPath,
      ".automation-node-test.js"
    );

    await fs.writeFile(temporaryTest, testScript, "utf8");

    try {
      const result = await new Promise((resolve) => {
        execFile(
          process.execPath,
          [temporaryTest],
          { cwd: this.repositoryPath },
          (error, stdout, stderr) => {
            resolve({
              passed: !error,
              stdout: stdout.trim(),
              stderr: stderr.trim(),
            });
          }
        );
      });

      return new CheckResult(
        "automated-tests",
        result.passed,
        result.passed ? "Automated tests passed." : "Automated tests failed.",
        result.passed
          ? []
          : [result.stderr || result.stdout || "No diagnostic output"]
      );
    } finally {
      await fs.rm(temporaryTest, { force: true });
    }
  }

  async runPreCommit() {
    const results = [];
    results.push(await this.validateStagedPaths());
    results.push(await this.validateFileSizes());
    results.push(await this.scanSecrets());
    results.push(await this.checkWhitespace());
    results.push(await this.runTests());

    return results;
  }

  async runCI() {
    /*
     * CI repeats important checks independently. A developer can disable or
     * bypass a local hook, so client-side automation alone cannot enforce a
     * repository-wide policy.
     */
    const results = await this.runPreCommit();
    const integrity = await this.runGit("fsck", "--no-progress");

    results.push(
      new CheckResult(
        "git-integrity",
        integrity.code === 0,
        integrity.code === 0
          ? "Git object integrity check passed."
          : "Git object integrity check failed.",
        integrity.code === 0
          ? []
          : [integrity.stderr || integrity.stdout]
      )
    );

    return results;
  }
}

function printResults(title, results) {
  console.log(`\n=== ${title} ===`);

  for (const result of results) {
    console.log(result.toString());
  }

  const passed = results.every((result) => result.passed);
  console.log(`Result: ${passed ? "PASS" : "FAIL"}`);

  return passed;
}

async function initializeRepository(repositoryPath) {
  await fs.mkdir(path.join(repositoryPath, "src"), { recursive: true });
  await fs.mkdir(path.join(repositoryPath, "tests"), { recursive: true });

  const commands = [
    ["init", "-b", "main"],
    ["config", "user.name", "Node Automation Demo"],
    ["config", "user.email", "node-automation@example.invalid"],
  ];

  for (const command of commands) {
    const result = await new AutomationEngine(repositoryPath).runGit(...command);

    if (result.code !== 0) {
      throw new Error(result.stderr || result.stdout);
    }
  }

  await fs.writeFile(
    path.join(repositoryPath, "src", "parser.js"),
    `function parsePort(value) {
  const port = Number(value);

  if (!Number.isInteger(port) || port < 1 || port > 65535) {
    throw new RangeError("Port must be an integer between 1 and 65535");
  }

  return port;
}

module.exports = { parsePort };
`,
    "utf8"
  );

  await fs.writeFile(
    path.join(repositoryPath, "README.md"),
    "# Git Automation Demo\n\nNode.js repository automation example.\n",
    "utf8"
  );

  const engine = new AutomationEngine(repositoryPath);
  let result = await engine.runGit("add", ".");
  if (result.code !== 0) {
    throw new Error(result.stderr || result.stdout);
  }

  result = await engine.runGit(
    "commit",
    "-m",
    "chore: initialize node automation demo"
  );

  if (result.code !== 0) {
    throw new Error(result.stderr || result.stdout);
  }
}

async function demonstrateEventDrivenHooks(engine) {
  /*
   * Git hooks are event boundaries. The event-driven model makes it possible
   * to attach different checks to different lifecycle points without mixing
   * commit-message validation with staged-content validation.
   */
  engine.on("commit-msg", ({ message }) => {
    return engine.validateCommitMessage(message);
  });

  engine.on("pre-commit", async () => {
    const results = await engine.runPreCommit();
    return results;
  });

  console.log("\n=== commit-msg Event ===");

  const invalid = await engine.emit("commit-msg", {
    message: "changed files",
  });
  printResults("Invalid Commit Message", invalid);

  const valid = await engine.emit("commit-msg", {
    message: "fix(parser): validate port boundaries",
  });
  printResults("Valid Commit Message", valid);
}

async function demonstrateFailureAndRepair(engine) {
  const readme = path.join(engine.repositoryPath, "README.md");
  const original = await fs.readFile(readme, "utf8");

  await fs.writeFile(readme, `${original.trimEnd()}   \n`, "utf8");

  let result = await engine.runGit("add", "README.md");
  if (result.code !== 0) {
    throw new Error(result.stderr || result.stdout);
  }

  const failingChecks = await engine.emit("pre-commit");
  printResults("Pre-Commit Failure", failingChecks.flat());

  await fs.writeFile(readme, original, "utf8");

  result = await engine.runGit("add", "README.md");
  if (result.code !== 0) {
    throw new Error(result.stderr || result.stdout);
  }

  const passingChecks = await engine.emit("pre-commit");
  printResults("Repaired Pre-Commit", passingChecks.flat());
}

async function demonstrateCommit(engine) {
  const file = path.join(engine.repositoryPath, "README.md");
  const current = await fs.readFile(file, "utf8");

  await fs.writeFile(
    file,
    `${current.trimEnd()}\n\nValidation is executed before the commit.\n`,
    "utf8"
  );

  let result = await engine.runGit("add", "README.md");

  if (result.code !== 0) {
    throw new Error(result.stderr || result.stdout);
  }

  const message = "docs(automation): record validation behavior";
  const messageCheck = engine.validateCommitMessage(message);

  console.log("\n=== Commit Gate ===");
  console.log(messageCheck.toString());

  if (!messageCheck.passed) {
    throw new Error("The commit must not proceed.");
  }

  result = await engine.runGit("commit", "-m", message);

  if (result.code !== 0) {
    throw new Error(result.stderr || result.stdout);
  }

  console.log("Automated commit completed.");
}

async function createAudit(engine, results) {
  const audit = {
    repository: path.basename(engine.repositoryPath),
    timestamp: new Date().toISOString(),
    localHooks: {
      "pre-commit":
        "validate staged paths, file sizes, secrets, whitespace, and tests",
      "commit-msg": "validate commit subject",
    },
    checks: results.map((result) => ({
      name: result.name,
      passed: result.passed,
      message: result.message,
      details: result.details,
    })),
    passed: results.every((result) => result.passed),
  };

  const auditPath = path.join(engine.repositoryPath, "automation-audit.json");
  await fs.writeFile(auditPath, JSON.stringify(audit, null, 2), "utf8");

  return auditPath;
}

async function main() {
  const repositoryPath = await fs.mkdtemp(
    path.join(os.tmpdir(), "git-automation-js-")
  );

  try {
    await initializeRepository(repositoryPath);

    const engine = new AutomationEngine(repositoryPath);

    await demonstrateEventDrivenHooks(engine);
    await demonstrateFailureAndRepair(engine);
    await demonstrateCommit(engine);

    const ciResults = await engine.runCI();
    printResults("Independent CI-Style Validation", ciResults);

    const auditPath = await createAudit(engine, ciResults);
    console.log(`\nAudit written to: ${auditPath}`);

    const history = await engine.runGit(
      "log",
      "--oneline",
      "--decorate",
      "-5"
    );

    console.log("\n=== Repository History ===");
    console.log(history.stdout);
  } finally {
    await fs.rm(repositoryPath, { recursive: true, force: true });
    console.log("\nTemporary repository removed.");
  }
}

main().catch((error) => {
  console.error(`Automation failed: ${error.message}`);
  process.exitCode = 1;
});
