"use strict";

/**
 * Code Quality Workflow for JavaScript Repositories
 *
 * Demonstrates the different roles of formatting, linting, and static
 * analysis through an event-driven pull-request quality gate.
 *
 * Runtime: Node.js 18+
 *
 * Run:
 *   node code-quality.js
 *   node code-quality.js --self-test
 */

const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");
const { pathToFileURL } = require("node:url");

const DEFAULT_POLICY = Object.freeze({
  maxLineLength: 100,
  requireFinalNewline: true,
  blockConsoleLog: false,
  blockDebugger: true,
  requireTests: true,
  requireLint: true,
  requireFormat: true,
  requireStaticAnalysis: true,
});

class Finding {
  constructor(rule, severity, message, line = 1, column = 1) {
    this.rule = rule;
    this.severity = severity;
    this.message = message;
    this.line = line;
    this.column = column;
  }
}

class QualityReport {
  constructor(file) {
    this.file = file;
    this.findings = [];
  }

  add(rule, severity, message, line, column) {
    this.findings.push(
      new Finding(rule, severity, message, line, column)
    );
  }

  count(severity) {
    return this.findings.filter(
      (finding) => finding.severity === severity
    ).length;
  }

  toJSON() {
    return {
      file: this.file,
      counts: {
        errors: this.count("error"),
        warnings: this.count("warning"),
        info: this.count("info"),
      },
      findings: this.findings,
    };
  }
}

function normalizeSource(source) {
  // CRLF and CR line endings can produce noisy formatting diffs across OSes.
  return source.replace(/\r\n?/g, "\n");
}

function formatSource(source) {
  const normalized = normalizeSource(source);
  const trimmedLines = normalized
    .split("\n")
    .map((line) => line.replace(/[ \t]+$/g, ""));

  while (trimmedLines.length > 0 && trimmedLines.at(-1) === "") {
    trimmedLines.pop();
  }

  return trimmedLines.length === 0
    ? ""
    : `${trimmedLines.join("\n")}\n`;
}

function lintSource(source, fileName = "<memory>", policy = DEFAULT_POLICY) {
  const normalized = normalizeSource(source);
  const report = new QualityReport(fileName);
  const lines = normalized.split("\n");

  if (
    policy.requireFinalNewline &&
    normalized.length > 0 &&
    !normalized.endsWith("\n")
  ) {
    report.add(
      "JS001",
      "warning",
      "Source file must end with a newline.",
      lines.length,
      1
    );
  }

  lines.forEach((line, index) => {
    const lineNumber = index + 1;

    if (line.length > policy.maxLineLength) {
      report.add(
        "JS002",
        "warning",
        `Line length ${line.length} exceeds ${policy.maxLineLength}.`,
        lineNumber,
        policy.maxLineLength + 1
      );
    }

    if (/[ \t]+$/.test(line)) {
      report.add(
        "JS003",
        "warning",
        "Trailing whitespace detected.",
        lineNumber,
        line.length
      );
    }

    if (policy.blockDebugger && /\bdebugger\s*;?/.test(line)) {
      report.add(
        "JS004",
        "error",
        "Remove debugger statements before merging.",
        lineNumber,
        line.indexOf("debugger") + 1
      );
    }

    if (policy.blockConsoleLog && /\bconsole\.log\s*\(/.test(line)) {
      report.add(
        "JS005",
        "warning",
        "Use the project's approved logging mechanism.",
        lineNumber,
        line.indexOf("console.log") + 1
      );
    }

    if (/==(?!=)/.test(line) && !/===/.test(line)) {
      report.add(
        "JS006",
        "warning",
        "Prefer strict equality to avoid implicit type coercion.",
        lineNumber,
        line.indexOf("==") + 1
      );
    }

    if (/\beval\s*\(/.test(line)) {
      report.add(
        "JS007",
        "error",
        "Dynamic eval complicates security review and static analysis.",
        lineNumber,
        line.indexOf("eval") + 1
      );
    }

    if (/catch\s*\(\s*\w+\s*\)\s*\{\s*\}/.test(line)) {
      report.add(
        "JS008",
        "warning",
        "Empty catch block silently discards failures.",
        lineNumber,
        line.indexOf("catch") + 1
      );
    }
  });

  // This is a deliberately lightweight rule engine, not a complete parser.
  // Use ESLint or another parser-based tool for scope-aware analysis.
  return report;
}

function evaluateQualityGate(evidence, policy = DEFAULT_POLICY) {
  const failures = [];
  const warnings = [];

  if (policy.requireTests && evidence.tests !== "passed") {
    failures.push(`Tests are not passing: ${evidence.tests}.`);
  }

  if (policy.requireLint && evidence.lint !== "passed") {
    failures.push(`Lint status is not passing: ${evidence.lint}.`);
  }

  if (policy.requireFormat && evidence.format !== "passed") {
    failures.push(`Formatting status is not passing: ${evidence.format}.`);
  }

  if (
    policy.requireStaticAnalysis &&
    evidence.staticAnalysis !== "passed"
  ) {
    failures.push(
      `Static analysis status is not passing: ${evidence.staticAnalysis}.`
    );
  }

  if (evidence.openReviewThreads > 0) {
    failures.push(
      `${evidence.openReviewThreads} review thread(s) remain unresolved.`
    );
  }

  if (evidence.approvals < evidence.requiredApprovals) {
    failures.push(
      `Approvals ${evidence.approvals}/${evidence.requiredApprovals}.`
    );
  }

  if (evidence.staleApproval === true) {
    failures.push("An approval became stale after new commits were pushed.");
  }

  if (evidence.mergeConflicts === true) {
    failures.push("The pull request has merge conflicts.");
  }

  if (evidence.isDraft === true) {
    failures.push("Draft pull requests are not mergeable.");
  }

  if (evidence.baseBranchProtected !== true) {
    warnings.push(
      "The target branch is not recorded as protected by this policy model."
    );
  }

  return {
    eligible: failures.length === 0,
    failures,
    warnings,
  };
}

class PullRequestQualityWorkflow {
  #events = [];
  #policy;

  constructor(policy = DEFAULT_POLICY) {
    this.#policy = Object.freeze({ ...policy });
  }

  record(event, payload = {}) {
    const entry = Object.freeze({
      event,
      payload: Object.freeze({ ...payload }),
      timestamp: new Date().toISOString(),
    });

    this.#events.push(entry);
    return entry;
  }

  get events() {
    return this.#events.map((entry) => ({
      ...entry,
      payload: { ...entry.payload },
    }));
  }

  async inspectFile(filePath) {
    const absolutePath = path.resolve(filePath);
    const source = await fs.readFile(absolutePath, "utf8");
    const report = lintSource(source, path.basename(absolutePath), this.#policy);

    this.record("file-inspected", {
      file: absolutePath,
      findings: report.findings.length,
    });

    return report;
  }

  evaluatePullRequest(evidence) {
    const result = evaluateQualityGate(evidence, this.#policy);

    this.record("quality-gate-evaluated", {
      eligible: result.eligible,
      failures: result.failures.length,
    });

    return result;
  }
}

function sampleEvidence(overrides = {}) {
  return {
    tests: "passed",
    lint: "passed",
    format: "passed",
    staticAnalysis: "passed",
    openReviewThreads: 0,
    approvals: 2,
    requiredApprovals: 2,
    staleApproval: false,
    mergeConflicts: false,
    isDraft: false,
    baseBranchProtected: true,
    ...overrides,
  };
}

function runSelfTests() {
  const source = [
    "const enabled = true;  ",
    "if (enabled == 1) {",
    "  debugger;",
    "}",
  ].join("\n");

  const report = lintSource(source, "release.js");
  const rules = new Set(report.findings.map((finding) => finding.rule));

  assert.ok(rules.has("JS001"));
  assert.ok(rules.has("JS003"));
  assert.ok(rules.has("JS004"));
  assert.ok(rules.has("JS006"));

  const formatted = formatSource("const value = 1;  \r\n");
  assert.equal(formatted, "const value = 1;\n");
  assert.equal(formatSource(formatted), formatted);

  const passing = evaluateQualityGate(sampleEvidence());
  assert.equal(passing.eligible, true);

  const failing = evaluateQualityGate(
    sampleEvidence({
      approvals: 1,
      staleApproval: true,
      openReviewThreads: 2,
    })
  );
  assert.equal(failing.eligible, false);
  assert.equal(failing.failures.length, 3);

  const workflow = new PullRequestQualityWorkflow();
  workflow.record("pull-request-opened", {
    number: 42,
    base: "main",
    head: "feature/release-checks",
  });
  assert.equal(workflow.events.length, 1);

  console.log("All JavaScript quality tests passed.");
}

async function main() {
  const args = process.argv.slice(2);

  if (args.includes("--self-test")) {
    runSelfTests();
    return;
  }

  const workflow = new PullRequestQualityWorkflow();

  const evidence = sampleEvidence({
    approvals: 1,
    requiredApprovals: 2,
    openReviewThreads: 1,
    staticAnalysis: "failed",
  });

  const gate = workflow.evaluatePullRequest(evidence);

  console.log("Pull request quality gate");
  console.log(JSON.stringify(gate, null, 2));

  const demoSource = [
    "function canMerge(checks, approvals) {",
    "  if (checks == true && approvals > 0) {",
    "    debugger;",
    "    return true;",
    "  }",
    "  return false;",
    "}",
  ].join("\n");

  const report = lintSource(demoSource, "merge-policy.js");
  console.log("\nLint findings");
  console.log(JSON.stringify(report.toJSON(), null, 2));

  if (args.includes("--inspect")) {
    const index = args.indexOf("--inspect");
    const fileName = args[index + 1];

    if (!fileName) {
      throw new Error("--inspect requires a JavaScript file path.");
    }

    const fileReport = await workflow.inspectFile(fileName);
    console.log(JSON.stringify(fileReport.toJSON(), null, 2));
  }
}

if (require.main === module) {
  main().catch((error) => {
    console.error(`Quality workflow failed: ${error.message}`);
    process.exitCode = 1;
  });
}

module.exports = {
  Finding,
  QualityReport,
  PullRequestQualityWorkflow,
  evaluateQualityGate,
  formatSource,
  lintSource,
  sampleEvidence,
};
