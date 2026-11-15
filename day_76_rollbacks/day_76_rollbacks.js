"use strict";

/*
 * Automated Rollback Strategies and Release Recovery
 * Node.js 18+
 * Standard library only.
 *
 * Event-driven release controller with canary analysis,
 * health policies, circuit breaking, rollback and recovery.
 */

const fs = require("node:fs/promises");
const crypto = require("node:crypto");
const EventEmitter = require("node:events");

const ReleaseState = Object.freeze({
    CREATED: "CREATED",
    DEPLOYING: "DEPLOYING",
    ACTIVE: "ACTIVE",
    FAILED: "FAILED",
    ROLLING_BACK: "ROLLING_BACK",
    ROLLED_BACK: "ROLLED_BACK",
    RECOVERED: "RECOVERED"
});

class DeploymentError extends Error {}
class PolicyError extends Error {}
class RecoveryError extends Error {}

function validateDigest(digest) {
    if (!/^sha256:[a-f0-9]{64}$/i.test(digest)) {
        throw new TypeError("Invalid SHA-256 artifact digest");
    }
}

class Release {
    constructor(version, digest) {
        if (typeof version !== "string" || !version.trim()) {
            throw new TypeError("Release version is required");
        }

        validateDigest(digest);

        this.id = crypto.randomUUID();
        this.version = version;
        this.digest = digest;
        this.createdAt = new Date().toISOString();

        Object.freeze(this);
    }
}

class HealthPolicy {
    constructor({
        maxErrorRate = 0.05,
        maxLatencyMs = 500,
        minAvailability = 0.99,
        maxFailedChecks = 2,
        consecutiveFailures = 2
    } = {}) {
        if (
            maxErrorRate < 0 || maxErrorRate > 1 ||
            maxLatencyMs <= 0 ||
            minAvailability <= 0 || minAvailability > 1 ||
            maxFailedChecks < 0 ||
            !Number.isInteger(consecutiveFailures) ||
            consecutiveFailures < 1
        ) {
            throw new PolicyError("Invalid health policy");
        }

        Object.assign(this, {
            maxErrorRate,
            maxLatencyMs,
            minAvailability,
            maxFailedChecks,
            consecutiveFailures
        });

        Object.freeze(this);
    }

    evaluate(metrics) {
        const failures = [];

        if (!Number.isFinite(metrics.errorRate) ||
            metrics.errorRate < 0 || metrics.errorRate > 1) {
            failures.push("invalid_error_rate");
        }

        if (!Number.isFinite(metrics.latencyMs) ||
            metrics.latencyMs < 0) {
            failures.push("invalid_latency");
        }

        if (!Number.isFinite(metrics.availability) ||
            metrics.availability < 0 || metrics.availability > 1) {
            failures.push("invalid_availability");
        }

        if (!Number.isInteger(metrics.failedChecks) ||
            metrics.failedChecks < 0) {
            failures.push("invalid_failed_checks");
        }

        if (failures.length) {
            return { healthy: false, failures };
        }

        if (metrics.errorRate > this.maxErrorRate) {
            failures.push("error_rate");
        }

        if (metrics.latencyMs > this.maxLatencyMs) {
            failures.push("latency");
        }

        if (metrics.availability < this.minAvailability) {
            failures.push("availability");
        }

        if (metrics.failedChecks > this.maxFailedChecks) {
            failures.push("failed_checks");
        }

        return {
            healthy: failures.length === 0,
            failures
        };
    }
}

class ReleaseController extends EventEmitter {
    constructor(policy, options = {}) {
        super();

        this.policy = policy;
        this.releases = new Map();
        this.activeRelease = null;
        this.previousRelease = null;
        this.audit = [];
        this.maxConcurrentDeployments = options.maxConcurrentDeployments ?? 1;
        this.runningDeployments = 0;
        this.historyFile = options.historyFile ?? "release-history.json";

        if (this.maxConcurrentDeployments < 1) {
            throw new PolicyError("Invalid concurrency limit");
        }
    }

    log(event, data = {}) {
        const record = {
            timestamp: new Date().toISOString(),
            event,
            ...data
        };

        this.audit.push(record);
        this.emit("release-event", record);
    }

    register(release) {
        if (this.releases.has(release.id)) {
            throw new DeploymentError("Duplicate release");
        }

        this.releases.set(release.id, {
            release,
            state: ReleaseState.CREATED,
            traffic: 0,
            history: [],
            failureReason: null
        });

        this.log("release_registered", {
            releaseId: release.id,
            version: release.version
        });

        return release.id;
    }

    getDeployment(id) {
        const deployment = this.releases.get(id);

        if (!deployment) {
            throw new DeploymentError("Unknown release");
        }

        return deployment;
    }

    setTraffic(id, percentage) {
        if (!Number.isInteger(percentage) ||
            percentage < 0 || percentage > 100) {
            throw new RangeError("Traffic must be between 0 and 100");
        }

        const deployment = this.getDeployment(id);
        deployment.traffic = percentage;

        this.log("traffic_changed", {
            releaseId: id,
            percentage
        });
    }

    validateWindow(deployment, metrics) {
        const result = this.policy.evaluate(metrics);
        deployment.history.push({
            ...metrics,
            evaluatedAt: new Date().toISOString()
        });

        this.log("health_evaluated", {
            releaseId: deployment.release.id,
            healthy: result.healthy,
            failures: result.failures
        });

        if (!result.healthy) {
            throw new DeploymentError(
                `Health gate failed: ${result.failures.join(", ")}`
            );
        }
    }

    async delay(ms) {
        await new Promise(resolve => setTimeout(resolve, ms));
    }

    async deploy(id, metricsWindows, strategy = "CANARY") {
        if (this.runningDeployments >= this.maxConcurrentDeployments) {
            throw new DeploymentError("Deployment concurrency limit reached");
        }

        const deployment = this.getDeployment(id);

        if (![ReleaseState.CREATED, ReleaseState.ROLLED_BACK].includes(
            deployment.state
        )) {
            throw new DeploymentError("Invalid deployment state");
        }

        const stages = strategy === "CANARY"
            ? [5, 25, 50, 100]
            : strategy === "PROGRESSIVE"
                ? [10, 30, 60, 100]
                : [100];

        if (!Array.isArray(metricsWindows) ||
            metricsWindows.length < stages.length) {
            throw new DeploymentError("Insufficient health measurements");
        }

        this.runningDeployments++;
        deployment.state = ReleaseState.DEPLOYING;

        this.log("deployment_started", {
            releaseId: id,
            strategy
        });

        try {
            if (strategy === "BLUE_GREEN") {
                // Validate the inactive environment before switching traffic.
                for (const metrics of metricsWindows) {
                    this.validateWindow(deployment, metrics);
                }

                this.setTraffic(id, 100);
            } else {
                for (let i = 0; i < stages.length; i++) {
                    this.setTraffic(id, stages[i]);
                    this.validateWindow(deployment, metricsWindows[i]);

                    if (i !== stages.length - 1) {
                        await this.delay(10);
                    }
                }
            }

            const previous = this.activeRelease;

            if (previous && previous !== id) {
                this.previousRelease = previous;
            }

            this.activeRelease = id;
            deployment.state = ReleaseState.ACTIVE;

            this.log("deployment_activated", {
                releaseId: id
            });

            return deployment;

        } catch (error) {
            deployment.state = ReleaseState.FAILED;
            deployment.failureReason = error.message;

            this.log("deployment_failed", {
                releaseId: id,
                reason: error.message
            });

            if (this.previousRelease) {
                await this.rollback(id, this.previousRelease);
            }

            throw error;

        } finally {
            this.runningDeployments--;
        }
    }

    async rollback(failedId, targetId) {
        const failed = this.getDeployment(failedId);
        const target = this.getDeployment(targetId);

        if (![ReleaseState.ACTIVE, ReleaseState.RECOVERED,
            ReleaseState.ROLLED_BACK].includes(target.state)) {
            throw new RecoveryError("Rollback target is not validated");
        }

        failed.state = ReleaseState.ROLLING_BACK;

        this.log("rollback_started", {
            failedId,
            targetId
        });

        try {
            // Production routing is changed only after target validation.
            this.setTraffic(failedId, 0);
            this.setTraffic(targetId, 100);

            this.activeRelease = targetId;
            failed.state = ReleaseState.ROLLED_BACK;

            this.log("rollback_completed", {
                failedId,
                targetId
            });

        } catch (error) {
            failed.state = ReleaseState.FAILED;
            this.log("rollback_failed", {
                failedId,
                reason: error.message
            });

            throw new RecoveryError(error.message);
        }
    }

    async recoverForward(failedId, version, digest, windows) {
        const failed = this.getDeployment(failedId);

        if (![ReleaseState.FAILED, ReleaseState.ROLLED_BACK].includes(
            failed.state
        )) {
            throw new RecoveryError("Invalid forward recovery state");
        }

        const replacement = new Release(version, digest);
        const id = this.register(replacement);

        try {
            const result = await this.deploy(id, windows, "CANARY");
            result.state = ReleaseState.RECOVERED;

            this.log("forward_recovery_completed", {
                failedId,
                replacementId: id
            });

            return result;

        } catch (error) {
            this.log("forward_recovery_failed", {
                failedId,
                replacementId: id,
                reason: error.message
            });

            throw error;
        }
    }

    async persist() {
        const data = {
            activeRelease: this.activeRelease,
            previousRelease: this.previousRelease,
            deployments: Array.from(this.releases.values()).map(d => ({
                release: d.release,
                state: d.state,
                traffic: d.traffic,
                history: d.history,
                failureReason: d.failureReason
            })),
            audit: this.audit
        };

        const temporary = `${this.historyFile}.tmp`;

        try {
            await fs.writeFile(
                temporary,
                JSON.stringify(data, null, 2),
                { encoding: "utf8", mode: 0o600 }
            );

            await fs.rename(temporary, this.historyFile);

        } catch (error) {
            await fs.rm(temporary, { force: true }).catch(() => {});
            throw new RecoveryError(`Persistence failed: ${error.message}`);
        }
    }

    report() {
        return Array.from(this.releases.values()).map(d => ({
            version: d.release.version,
            state: d.state,
            traffic: d.traffic,
            observations: d.history.length,
            failure: d.failureReason
        }));
    }
}

async function main() {
    const controller = new ReleaseController(
        new HealthPolicy(),
        {
            maxConcurrentDeployments: 1,
            historyFile: "release-history.json"
        }
    );

    controller.on("release-event", event => {
        console.log(
            `[EVENT] ${event.event}`,
            event.releaseId ?? ""
        );
    });

    const healthy = [
        { errorRate: 0.01, latencyMs: 120, availability: 0.999, failedChecks: 0 },
        { errorRate: 0.02, latencyMs: 150, availability: 0.998, failedChecks: 0 },
        { errorRate: 0.015, latencyMs: 130, availability: 0.999, failedChecks: 0 },
        { errorRate: 0.01, latencyMs: 125, availability: 0.999, failedChecks: 0 }
    ];

    const v1 = new Release("1.0.0", `sha256:${"a".repeat(64)}`);
    const v1Id = controller.register(v1);

    await controller.deploy(v1Id, [
        healthy[0], healthy[1]
    ], "IMMEDIATE");

    const v2 = new Release("2.0.0", `sha256:${"b".repeat(64)}`);
    const v2Id = controller.register(v2);

    const degraded = [
        healthy[0],
        healthy[1],
        { errorRate: 0.25, latencyMs: 1200, availability: 0.90, failedChecks: 5 },
        healthy[3]
    ];

    try {
        await controller.deploy(v2Id, degraded, "CANARY");
    } catch (error) {
        console.error("Deployment rejected:", error.message);
    }

    if (controller.activeRelease !== v1Id) {
        throw new Error("Rollback verification failed");
    }

    const v3 = await controller.recoverForward(
        v2Id,
        "2.0.1",
        `sha256:${"c".repeat(64)}`,
        healthy
    );

    console.log("\nFINAL RELEASE REPORT");
    console.table(controller.report());
    console.log("Active release:", controller.activeRelease);
    console.log("Recovered version:", v3.release.version);

    await controller.persist();
}

main().catch(error => {
    console.error("Fatal release controller error:", error);
    process.exitCode = 1;
});
