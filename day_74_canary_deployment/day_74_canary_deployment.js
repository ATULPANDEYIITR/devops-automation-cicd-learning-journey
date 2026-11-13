"use strict";

/**
 * Canary deployment control plane.
 * Node.js 18+; no external dependencies.
 *
 * Models event-driven rollout coordination, traffic allocation,
 * health policies, concurrency protection, and rollback.
 */

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");

class DeploymentError extends Error {
    constructor(message, code = "DEPLOYMENT_ERROR") {
        super(message);
        this.name = "DeploymentError";
        this.code = code;
    }
}

const State = Object.freeze({
    CREATED: "CREATED",
    RUNNING: "RUNNING",
    PROMOTED: "PROMOTED",
    ROLLED_BACK: "ROLLED_BACK",
    FAILED: "FAILED"
});

class HealthPolicy {
    constructor({
        stages = [5, 10, 25, 50, 100],
        maximumErrorRate = 0.02,
        maximumP95Latency = 500,
        maximumErrorRegression = 0.015,
        minimumRequests = 100
    } = {}) {
        if (!Array.isArray(stages) || stages.length === 0 ||
            stages.at(-1) !== 100) {
            throw new TypeError("Stages must end at 100.");
        }

        if (stages.some((value, index) =>
            !Number.isInteger(value) ||
            value < 1 ||
            value > 100 ||
            (index > 0 && value <= stages[index - 1])
        )) {
            throw new TypeError("Stages must be strictly increasing.");
        }

        if (!(maximumErrorRate > 0 && maximumErrorRate < 1) ||
            !(maximumP95Latency > 0) ||
            !(maximumErrorRegression >= 0) ||
            !Number.isInteger(minimumRequests) ||
            minimumRequests < 1) {
            throw new TypeError("Invalid health policy.");
        }

        this.stages = Object.freeze([...stages]);
        this.maximumErrorRate = maximumErrorRate;
        this.maximumP95Latency = maximumP95Latency;
        this.maximumErrorRegression = maximumErrorRegression;
        this.minimumRequests = minimumRequests;
        Object.freeze(this);
    }

    evaluate(candidate, baseline) {
        const failures = [];

        if (!Number.isSafeInteger(candidate.requests) ||
            !Number.isSafeInteger(candidate.errors) ||
            candidate.requests < this.minimumRequests ||
            candidate.errors < 0 ||
            candidate.errors > candidate.requests) {
            failures.push("invalid_or_insufficient_observations");
            return failures;
        }

        if (!Number.isFinite(candidate.p95Latency) ||
            candidate.p95Latency < 0) {
            failures.push("invalid_latency");
            return failures;
        }

        const errorRate = candidate.errors / candidate.requests;
        const baselineRate = baseline.errors / baseline.requests;

        if (errorRate > this.maximumErrorRate) {
            failures.push("error_rate");
        }

        if (candidate.p95Latency > this.maximumP95Latency) {
            failures.push("latency");
        }

        if (errorRate - baselineRate >
            this.maximumErrorRegression) {
            failures.push("baseline_regression");
        }

        return failures;
    }
}

class Deployment extends EventEmitter {
    #mutex = Promise.resolve();

    constructor(id, version, policy, baseline, previousVersion) {
        super();

        if (!id || !version) {
            throw new TypeError("Deployment ID and version are required.");
        }

        this.id = id;
        this.version = version;
        this.policy = policy;
        this.baseline = Object.freeze({ ...baseline });
        this.previousVersion = previousVersion;
        this.state = State.CREATED;
        this.stageIndex = -1;
        this.trafficPercent = 0;
        this.history = [];
        this.revision = 0;
    }

    async exclusive(operation) {
        const previous = this.#mutex;

        let release;
        this.#mutex = new Promise(resolve => {
            release = resolve;
        });

        await previous;

        try {
            return await operation();
        } finally {
            release();
        }
    }

    record(event, details = {}) {
        const entry = Object.freeze({
            revision: ++this.revision,
            timestamp: new Date().toISOString(),
            event,
            details: Object.freeze({ ...details })
        });

        this.history.push(entry);
        this.emit("deployment-event", entry);
    }

    async start() {
        return this.exclusive(async () => {
            if (this.state !== State.CREATED) {
                throw new DeploymentError(
                    "Deployment cannot be started twice.",
                    "INVALID_TRANSITION"
                );
            }

            this.state = State.RUNNING;
            this.stageIndex = 0;
            this.trafficPercent = this.policy.stages[0];

            this.record("started", {
                trafficPercent: this.trafficPercent
            });

            return this.snapshot();
        });
    }

    async observe(metrics) {
        return this.exclusive(async () => {
            if (this.state !== State.RUNNING) {
                throw new DeploymentError(
                    "Deployment is not running.",
                    "INVALID_TRANSITION"
                );
            }

            const failures = this.policy.evaluate(
                metrics,
                this.baseline
            );

            if (failures.length > 0) {
                return this.rollbackInternal(failures);
            }

            this.record("health_passed", {
                requests: metrics.requests,
                errors: metrics.errors,
                p95Latency: metrics.p95Latency
            });

            this.stageIndex++;

            if (this.stageIndex >= this.policy.stages.length) {
                this.state = State.PROMOTED;
                this.trafficPercent = 100;

                this.record("promoted", {
                    version: this.version
                });
            } else {
                this.trafficPercent =
                    this.policy.stages[this.stageIndex];

                this.record("traffic_increased", {
                    trafficPercent: this.trafficPercent
                });
            }

            return this.snapshot();
        });
    }

    async rollback(reason) {
        return this.exclusive(async () => {
            if (this.state !== State.RUNNING) {
                throw new DeploymentError(
                    "Only running deployments can roll back."
                );
            }

            return this.rollbackInternal([String(reason)]);
        });
    }

    rollbackInternal(reasons) {
        this.state = State.ROLLED_BACK;
        this.trafficPercent = 0;

        this.record("rolled_back", {
            reasons,
            restoredVersion: this.previousVersion
        });

        return this.snapshot();
    }

    snapshot() {
        return Object.freeze({
            id: this.id,
            version: this.version,
            state: this.state,
            trafficPercent: this.trafficPercent,
            previousVersion: this.previousVersion,
            revision: this.revision
        });
    }
}

class TrafficRouter {
    constructor() {
        this.activeVersion = "v1.0.0";
        this.deployment = null;
    }

    attach(deployment) {
        if (deployment.state !== State.CREATED) {
            throw new DeploymentError(
                "Attach a deployment before starting it."
            );
        }

        this.deployment = deployment;
    }

    route(requestKey) {
        if (typeof requestKey !== "string" ||
            requestKey.length === 0) {
            throw new TypeError("A routing key is required.");
        }

        const deployment = this.deployment;

        if (!deployment || deployment.state !== State.RUNNING) {
            return this.activeVersion;
        }

        const digest = crypto.createHash("sha256")
            .update(requestKey)
            .digest();

        const bucket = digest.readUInt32BE(0) % 100;

        return bucket < deployment.trafficPercent
            ? deployment.version
            : this.activeVersion;
    }

    synchronize(deployment) {
        if (deployment.state === State.PROMOTED) {
            this.activeVersion = deployment.version;
        } else if (deployment.state === State.ROLLED_BACK) {
            this.activeVersion = deployment.previousVersion;
        }
    }
}

class CanaryPlatform {
    constructor(policy = new HealthPolicy()) {
        this.policy = policy;
        this.router = new TrafficRouter();
        this.deployments = new Map();
    }

    createRelease(id, version, baseline) {
        if (this.deployments.has(id)) {
            throw new DeploymentError("Duplicate release ID.");
        }

        if (!Number.isSafeInteger(baseline.requests) ||
            !Number.isSafeInteger(baseline.errors) ||
            baseline.requests < this.policy.minimumRequests ||
            baseline.errors < 0 ||
            baseline.errors > baseline.requests) {
            throw new TypeError("Invalid baseline observations.");
        }

        const deployment = new Deployment(
            id,
            version,
            this.policy,
            baseline,
            this.router.activeVersion
        );

        deployment.on("deployment-event", event => {
            process.stdout.write(
                `[${event.event}] revision=${event.revision}\n`
            );
        });

        this.deployments.set(id, deployment);
        this.router.attach(deployment);

        return deployment;
    }

    async start(id) {
        return this.get(id).start();
    }

    async observe(id, metrics) {
        const deployment = this.get(id);
        const result = await deployment.observe(metrics);

        this.router.synchronize(deployment);

        return result;
    }

    async rollback(id, reason) {
        const deployment = this.get(id);
        const result = await deployment.rollback(reason);

        this.router.synchronize(deployment);

        return result;
    }

    get(id) {
        const deployment = this.deployments.get(id);

        if (!deployment) {
            throw new DeploymentError("Unknown release ID.");
        }

        return deployment;
    }

    report() {
        return {
            activeVersion: this.router.activeVersion,
            releases: Array.from(this.deployments.values())
                .map(deployment => ({
                    ...deployment.snapshot(),
                    history: deployment.history
                }))
        };
    }
}

async function runTests() {
    const platform = new CanaryPlatform(
        new HealthPolicy({ minimumRequests: 100 })
    );

    const baseline = { requests: 5000, errors: 50 };

    const release = platform.createRelease(
        "release-001",
        "v2.0.0",
        baseline
    );

    await platform.start(release.id);

    if (release.trafficPercent !== 5) {
        throw new Error("Initial traffic allocation failed.");
    }

    for (let index = 0; index < 5; index++) {
        await platform.observe(release.id, {
            requests: 1000,
            errors: 12,
            p95Latency: 200
        });
    }

    if (release.state !== State.PROMOTED ||
        platform.router.activeVersion !== "v2.0.0") {
        throw new Error("Successful promotion failed.");
    }

    const failed = platform.createRelease(
        "release-002",
        "v3.0.0",
        baseline
    );

    await platform.start(failed.id);

    await platform.observe(failed.id, {
        requests: 1000,
        errors: 200,
        p95Latency: 900
    });

    if (failed.state !== State.ROLLED_BACK ||
        platform.router.activeVersion !== "v2.0.0") {
        throw new Error("Rollback failed.");
    }

    let rejected = false;

    try {
        await platform.observe(failed.id, {
            requests: 1000,
            errors: 0,
            p95Latency: 100
        });
    } catch (error) {
        rejected = error.code === "INVALID_TRANSITION";
    }

    if (!rejected) {
        throw new Error("Invalid transition was not rejected.");
    }

    console.log("All JavaScript tests passed.");
    return platform;
}

async function main() {
    const platform = await runTests();

    const deployment = platform.createRelease(
        "production-2026-11",
        "v2.1.0",
        { requests: 10000, errors: 100 }
    );

    await platform.start(deployment.id);

    const observations = [
        { requests: 1000, errors: 12, p95Latency: 210 },
        { requests: 1000, errors: 15, p95Latency: 230 },
        { requests: 1000, errors: 14, p95Latency: 240 },
        { requests: 1000, errors: 13, p95Latency: 250 },
        { requests: 1000, errors: 11, p95Latency: 220 }
    ];

    for (const metrics of observations) {
        if (deployment.state !== State.RUNNING) break;

        const result = await platform.observe(
            deployment.id,
            metrics
        );

        console.log("Deployment:", result);
    }

    console.log(
        "Routing:",
        ["customer-001", "customer-002", "customer-003"]
            .map(key => ({
                key,
                version: platform.router.route(key)
            }))
    );

    const report = JSON.stringify(platform.report(), null, 2);

    await fs.writeFile(
        "canary_deployment_report.json",
        report,
        { encoding: "utf8", mode: 0o600 }
    );

    console.log("Report written successfully.");
}

main().catch(error => {
    console.error("Canary platform failure:", error.message);
    process.exitCode = 1;
});
