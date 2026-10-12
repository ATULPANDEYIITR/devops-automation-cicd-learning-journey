"use strict";

/*
 * Event-driven testing automation for a deployment pipeline.
 * Run with Node.js 18 or later: node testing-automation.js
 *
 * The model separates test execution, deployment state, and release policy.
 * All external effects are simulated so the file runs without dependencies.
 */

const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const { performance } = require("node:perf_hooks");

class PipelineError extends Error {}
class InvalidTransitionError extends PipelineError {}
class TestExecutionError extends PipelineError {}

const TestKind = Object.freeze({
  UNIT: "unit",
  INTEGRATION: "integration",
  SMOKE: "smoke",
  REGRESSION: "regression",
});

const PipelineState = Object.freeze({
  CREATED: "created",
  VALIDATING: "validating",
  TESTING: "testing",
  READY: "ready",
  DEPLOYING: "deploying",
  DEPLOYED: "deployed",
  FAILED: "failed",
  ROLLED_BACK: "rolled_back",
});

const ALLOWED_TRANSITIONS = Object.freeze({
  created: new Set(["validating", "failed"]),
  validating: new Set(["testing", "failed"]),
  testing: new Set(["ready", "failed"]),
  ready: new Set(["deploying", "failed"]),
  deploying: new Set(["deployed", "failed", "rolled_back"]),
  deployed: new Set(),
  failed: new Set(["rolled_back"]),
  rolled_back: new Set(),
});

class TestCase {
  constructor({ name, kind, run, critical = true, tags = [] }) {
    if (!name || typeof name !== "string") {
      throw new TypeError("Test name must be a non-empty string.");
    }
    if (!Object.values(TestKind).includes(kind)) {
      throw new TypeError(`Unsupported test kind: ${kind}`);
    }
    if (typeof run !== "function") {
      throw new TypeError("Each test requires an executable function.");
    }
    this.name = name;
    this.kind = kind;
    this.run = run;
    this.critical = Boolean(critical);
    this.tags = [...new Set(tags)];
  }

  async execute(context) {
    const startedAt = performance.now();
    try {
      await this.run(context);
      return {
        name: this.name,
        kind: this.kind,
        status: "passed",
        critical: this.critical,
        durationMs: Number((performance.now() - startedAt).toFixed(3)),
      };
    } catch (error) {
      return {
        name: this.name,
        kind: this.kind,
        status: "failed",
        critical: this.critical,
        durationMs: Number((performance.now() - startedAt).toFixed(3)),
        error: error instanceof Error ? error.message : String(error),
      };
    }
  }
}

class TestSuite {
  constructor(name, cases = []) {
    this.name = name;
    this.cases = [];
    this.names = new Set();
    for (const testCase of cases) this.add(testCase);
  }

  add(testCase) {
    if (!(testCase instanceof TestCase)) {
      throw new TypeError("Suite members must be TestCase instances.");
    }
    if (this.names.has(testCase.name)) {
      throw new Error(`Duplicate test name: ${testCase.name}`);
    }
    this.names.add(testCase.name);
    this.cases.push(testCase);
  }

  select({ kinds = Object.values(TestKind), tags = [] } = {}) {
    const allowedKinds = new Set(kinds);
    const requiredTags = new Set(tags);
    return this.cases.filter((testCase) => {
      const kindMatches = allowedKinds.has(testCase.kind);
      const tagsMatch = [...requiredTags].every((tag) =>
        testCase.tags.includes(tag)
      );
      return kindMatches && tagsMatch;
    });
  }

  async run(context, options = {}) {
    const selected = this.select(options);
    const results = [];

    // Sequential execution keeps shared test fixtures deterministic. Tests
    // that share a database or external resource should not run concurrently
    // unless their isolation strategy has been designed explicitly.
    for (const testCase of selected) {
      results.push(await testCase.execute(context));
    }

    return {
      suite: this.name,
      selected: selected.length,
      passed: results.filter((result) => result.status === "passed").length,
      failed: results.filter((result) => result.status === "failed").length,
      criticalFailures: results.filter(
        (result) => result.status === "failed" && result.critical
      ).length,
      results,
    };
  }
}

class DeploymentPipeline extends EventEmitter {
  constructor({ suite, context, deploy, rollback, requiredKinds }) {
    super();
    if (!(suite instanceof TestSuite)) {
      throw new TypeError("A valid test suite is required.");
    }
    if (typeof deploy !== "function" || typeof rollback !== "function") {
      throw new TypeError("Deployment and rollback handlers are required.");
    }

    this.suite = suite;
    this.context = context;
    this.deploy = deploy;
    this.rollback = rollback;
    this.requiredKinds = [...new Set(requiredKinds)];
    this.state = PipelineState.CREATED;
    this.history = [];
    this.testReport = null;
  }

  transition(nextState, details = {}) {
    const permitted = ALLOWED_TRANSITIONS[this.state];
    if (!permitted || !permitted.has(nextState)) {
      throw new InvalidTransitionError(
        `Cannot transition from ${this.state} to ${nextState}.`
      );
    }

    const event = Object.freeze({
      previous: this.state,
      current: nextState,
      at: new Date().toISOString(),
      details: Object.freeze({ ...details }),
    });

    this.state = nextState;
    this.history.push(event);
    this.emit("stateChanged", event);
  }

  async execute() {
    try {
      this.transition(PipelineState.VALIDATING);
      assert.ok(this.context.releaseId, "Release ID is required.");
      assert.ok(this.context.environment, "Target environment is required.");

      this.transition(PipelineState.TESTING);
      this.testReport = await this.suite.run(this.context);

      const executedKinds = new Set(
        this.testReport.results
          .filter((result) => result.status === "passed")
          .map((result) => result.kind)
      );

      const missingKinds = this.requiredKinds.filter(
        (kind) => !executedKinds.has(kind)
      );
      if (missingKinds.length > 0) {
        throw new TestExecutionError(
          `Required test categories missing or failed: ${missingKinds.join(", ")}`
        );
      }

      if (this.testReport.criticalFailures > 0) {
        throw new TestExecutionError(
          `${this.testReport.criticalFailures} critical test(s) failed.`
        );
      }

      this.transition(PipelineState.READY, {
        testsPassed: this.testReport.passed,
      });
      this.transition(PipelineState.DEPLOYING);

      await this.deploy(this.context);
      this.transition(PipelineState.DEPLOYED);
      return this.report();
    } catch (error) {
      if (
        this.state !== PipelineState.FAILED &&
        this.state !== PipelineState.ROLLED_BACK &&
        this.state !== PipelineState.DEPLOYED
      ) {
        this.transition(PipelineState.FAILED, {
          reason: error instanceof Error ? error.message : String(error),
        });
      }

      if (this.state === PipelineState.FAILED && this.context.rollbackRequired) {
        try {
          await this.rollback(this.context);
          this.transition(PipelineState.ROLLED_BACK);
        } catch (rollbackError) {
          this.emit("rollbackFailed", rollbackError);
        }
      }

      return this.report(error);
    }
  }

  report(error = null) {
    return {
      releaseId: this.context.releaseId,
      environment: this.context.environment,
      state: this.state,
      testReport: this.testReport,
      history: [...this.history],
      error: error ? String(error.message || error) : null,
    };
  }
}

function buildOrderTestingSuite() {
  const products = new Map([
    ["SSD-1TB", { price: 89.99, stock: 10 }],
    ["RAM-16G", { price: 42.5, stock: 20 }],
  ]);

  const suite = new TestSuite("order-service-release-gate");

  suite.add(
    new TestCase({
      name: "unit: monetary total",
      kind: TestKind.UNIT,
      tags: ["fast", "business-rule"],
      run: ({ calculateTotal }) => {
        assert.equal(calculateTotal(89.99, 3), 269.97);
      },
    })
  );

  suite.add(
    new TestCase({
      name: "unit: reject invalid quantity",
      kind: TestKind.UNIT,
      tags: ["fast", "validation"],
      run: ({ calculateTotal }) => {
        assert.throws(() => calculateTotal(89.99, 0), /positive integer/);
      },
    })
  );

  suite.add(
    new TestCase({
      name: "integration: inventory and order persistence",
      kind: TestKind.INTEGRATION,
      tags: ["database"],
      run: async ({ placeOrder }) => {
        const order = await placeOrder("JS-100", "SSD-1TB", 2);
        assert.equal(order.status, "CONFIRMED");
        assert.equal(order.total, 179.98);
      },
    })
  );

  suite.add(
    new TestCase({
      name: "smoke: service readiness",
      kind: TestKind.SMOKE,
      tags: ["deployment"],
      run: async ({ healthCheck }) => {
        const response = await healthCheck();
        assert.equal(response.status, 200);
        assert.equal(response.body.ready, true);
      },
    })
  );

  suite.add(
    new TestCase({
      name: "regression: failed order does not oversell",
      kind: TestKind.REGRESSION,
      tags: ["inventory", "business-rule"],
      run: ({ placeOrder }) => {
        return assert.rejects(
          () => placeOrder("JS-101", "SSD-1TB", 999),
          /insufficient inventory/
        );
      },
    })
  );

  return { suite, products };
}

async function main() {
  const { suite, products } = buildOrderTestingSuite();

  const context = {
    releaseId: "release-2026.10.12",
    environment: "staging",
    rollbackRequired: true,

    calculateTotal(price, quantity) {
      if (!Number.isFinite(price) || price < 0) {
        throw new TypeError("Price must be a finite non-negative number.");
      }
      if (!Number.isSafeInteger(quantity) || quantity <= 0) {
        throw new TypeError("Quantity must be a positive integer.");
      }
      // Integer cents avoid many binary floating-point currency errors.
      const cents = Math.round(price * 100) * quantity;
      return Number((cents / 100).toFixed(2));
    },

    async placeOrder(orderId, sku, quantity) {
      const product = products.get(sku);
      if (!product) throw new Error(`Unknown SKU: ${sku}`);
      if (!Number.isSafeInteger(quantity) || quantity <= 0) {
        throw new Error("Quantity must be a positive integer.");
      }
      if (product.stock < quantity) {
        throw new Error("insufficient inventory");
      }

      const total = context.calculateTotal(product.price, quantity);
      product.stock -= quantity;
      return { orderId, sku, quantity, total, status: "CONFIRMED" };
    },

    async healthCheck() {
      return { status: 200, body: { ready: true } };
    },
  };

  const pipeline = new DeploymentPipeline({
    suite,
    context,
    requiredKinds: Object.values(TestKind),
    deploy: async (deploymentContext) => {
      // This is a deterministic deployment simulation. A production adapter
      // should call a deployment API and verify the resulting release version.
      deploymentContext.deployedVersion = deploymentContext.releaseId;
    },
    rollback: async (deploymentContext) => {
      deploymentContext.rollbackPerformed = true;
    },
  });

  pipeline.on("stateChanged", (event) => {
    console.log(`${event.previous} -> ${event.current}`);
  });

  const report = await pipeline.execute();
  console.log(JSON.stringify(report, null, 2));

  if (report.state !== PipelineState.DEPLOYED) {
    process.exitCode = 1;
  }
}

main().catch((error) => {
  console.error("Uncaught testing automation error:", error);
  process.exitCode = 1;
});
