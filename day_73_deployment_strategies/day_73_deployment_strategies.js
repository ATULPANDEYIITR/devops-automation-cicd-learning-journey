"use strict";

/*
 * Event-driven Deployment Orchestration Engine
 *
 * Node.js 18+
 * No external dependencies.
 *
 * Implements:
 * - Recreate deployment
 * - Rolling deployment
 * - Blue-green deployment
 * - Asynchronous provisioning
 * - Event-driven observability
 * - Traffic switching
 * - Health evaluation
 * - Rollback
 * - Deployment policy enforcement
 */

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");

const DeploymentStrategy = Object.freeze({
    RECREATE: "recreate",
    ROLLING: "rolling",
    BLUE_GREEN: "blue-green"
});

const DeploymentState = Object.freeze({
    PENDING: "pending",
    PROVISIONING: "provisioning",
    VALIDATING: "validating",
    SWITCHING: "switching",
    SUCCEEDED: "succeeded",
    FAILED: "failed",
    ROLLED_BACK: "rolled-back"
});

class DeploymentError extends Error {
    constructor(message, code = "DEPLOYMENT_ERROR") {
        super(message);
        this.name = "DeploymentError";
        this.code = code;
    }
}

class DeploymentPolicy {
    constructor({
        maxCapacity = 12,
        minHealthyPercent = 100,
        maxSurge = 1,
        maxUnavailable = 1,
        requireHealthChecks = true,
        allowRecreate = true
    } = {}) {
        this.maxCapacity = maxCapacity;
        this.minHealthyPercent = minHealthyPercent;
        this.maxSurge = maxSurge;
        this.maxUnavailable = maxUnavailable;
        this.requireHealthChecks = requireHealthChecks;
        this.allowRecreate = allowRecreate;

        this.validate();
    }

    validate() {
        if (!Number.isInteger(this.maxCapacity) ||
            this.maxCapacity < 1) {
            throw new TypeError("Invalid maximum capacity");
        }

        if (this.minHealthyPercent < 0 ||
            this.minHealthyPercent > 100) {
            throw new TypeError("Invalid health percentage");
        }

        if (this.maxSurge < 0 || this.maxUnavailable < 0) {
            throw new TypeError("Invalid deployment limits");
        }

        if (this.maxSurge + this.maxUnavailable < 1) {
            throw new TypeError("Rolling deployment cannot progress");
        }
    }

    evaluate(strategy, currentCount, desiredCount) {
        if (
            strategy === DeploymentStrategy.RECREATE &&
            !this.allowRecreate
        ) {
            throw new DeploymentError(
                "Recreate strategy is prohibited by policy",
                "POLICY_VIOLATION"
            );
        }

        if (desiredCount > this.maxCapacity) {
            throw new DeploymentError(
                "Desired capacity exceeds infrastructure limit",
                "CAPACITY_EXCEEDED"
            );
        }

        if (
            strategy === DeploymentStrategy.BLUE_GREEN &&
            currentCount + desiredCount > this.maxCapacity
        ) {
            throw new DeploymentError(
                "Blue-green deployment requires additional capacity",
                "CAPACITY_EXCEEDED"
            );
        }

        return true;
    }
}

class TrafficRouter {
    constructor(initialVersion) {
        this.weights = new Map([[initialVersion, 100]]);
    }

    setWeight(version, weight) {
        if (!Number.isInteger(weight) ||
            weight < 0 ||
            weight > 100) {
            throw new RangeError("Invalid traffic weight");
        }

        this.weights.set(version, weight);
    }

    route(version) {
        return this.weights.get(version) || 0;
    }

    switchVersion(version) {
        this.weights.clear();
        this.weights.set(version, 100);
    }

    shiftTraffic(oldVersion, newVersion, newWeight) {
        if (
            !Number.isInteger(newWeight) ||
            newWeight < 0 ||
            newWeight > 100
        ) {
            throw new RangeError("Traffic weight must be 0-100");
        }

        this.weights.clear();

        if (newWeight < 100) {
            this.weights.set(oldVersion, 100 - newWeight);
        }

        if (newWeight > 0) {
            this.weights.set(newVersion, newWeight);
        }

        const total = [...this.weights.values()]
            .reduce((sum, value) => sum + value, 0);

        if (total !== 100) {
            throw new DeploymentError("Traffic weights are inconsistent");
        }
    }

    snapshot() {
        return Object.fromEntries(this.weights);
    }
}

class DeploymentEngine extends EventEmitter {
    constructor({
        initialVersion = "1.0.0",
        replicas = 4,
        policy = new DeploymentPolicy(),
        startupFailureRate = 0,
        healthFailureRate = 0
    } = {}) {
        super();

        if (!Number.isInteger(replicas) || replicas < 1) {
            throw new TypeError("Invalid replica count");
        }

        this.policy = policy;
        this.startupFailureRate = startupFailureRate;
        this.healthFailureRate = healthFailureRate;

        this.validateFailureRates();

        this.instances = Array.from(
            { length: replicas },
            (_, index) => ({
                id: `node-${index + 1}`,
                version: initialVersion,
                state: "healthy"
            })
        );

        this.activeVersion = initialVersion;
        this.previousVersion = null;
        this.router = new TrafficRouter(initialVersion);
        this.history = [];
        this.locked = false;
    }

    validateFailureRates() {
        for (const rate of [
            this.startupFailureRate,
            this.healthFailureRate
        ]) {
            if (!Number.isFinite(rate) || rate < 0 || rate > 1) {
                throw new RangeError("Failure rate must be between 0 and 1");
            }
        }
    }

    emitEvent(type, details = {}) {
        const event = Object.freeze({
            timestamp: new Date().toISOString(),
            type,
            details
        });

        this.emit("deployment-event", event);
    }

    delay() {
        return new Promise(resolve => setImmediate(resolve));
    }

    async provision(version, id) {
        await this.delay();

        if (Math.random() < this.startupFailureRate) {
            throw new DeploymentError(
                `Instance ${id} failed startup`,
                "STARTUP_FAILURE"
            );
        }

        return {
            id,
            version,
            state: "healthy"
        };
    }

    async healthCheck(instances) {
        await this.delay();

        if (!instances.length) {
            return false;
        }

        const failed = Math.random() < this.healthFailureRate;

        if (failed) {
            instances[0].state = "unhealthy";
        }

        const healthy = instances.filter(
            instance => instance.state === "healthy"
        ).length;

        const percentage = healthy / instances.length * 100;

        this.emitEvent("health-check", {
            healthy,
            total: instances.length,
            percentage
        });

        return (
            percentage >= this.policy.minHealthyPercent &&
            instances.every(instance => instance.state === "healthy")
        );
    }

    assertHealthy(result, message) {
        if (!result) {
            throw new DeploymentError(
                message,
                "HEALTH_CHECK_FAILED"
            );
        }
    }

    async recreate(version, desiredCount) {
        const oldInstances = this.instances;

        this.emitEvent("old-environment-stopped", {
            count: oldInstances.length
        });

        this.instances = [];

        try {
            const replacement = [];

            for (let index = 0; index < desiredCount; index++) {
                replacement.push(
                    await this.provision(version, `recreate-${index + 1}`)
                );
            }

            this.assertHealthy(
                await this.healthCheck(replacement),
                "Recreated environment is unhealthy"
            );

            this.instances = replacement;

        } catch (error) {
            this.instances = oldInstances;
            throw error;
        }
    }

    async rolling(version, desiredCount, batchSize) {
        const original = this.instances.map(
            instance => ({ ...instance })
        );

        try {
            let position = 0;

            while (position < original.length) {
                const batch = original.slice(
                    position,
                    position + batchSize
                );

                const unavailable = Math.min(
                    batch.length,
                    this.policy.maxUnavailable
                );

                const surge = Math.min(
                    batch.length,
                    this.policy.maxSurge
                );

                const replaceCount = Math.min(
                    batch.length,
                    unavailable + surge
                );

                if (replaceCount < 1) {
                    throw new DeploymentError(
                        "Rolling policy prevents progress"
                    );
                }

                const removed = batch.slice(0, replaceCount);

                this.instances = this.instances.filter(
                    instance => !removed.some(
                        old => old.id === instance.id
                    )
                );

                const replacements = [];

                for (let index = 0; index < replaceCount; index++) {
                    if (
                        this.instances.length + 1 >
                        this.policy.maxCapacity
                    ) {
                        throw new DeploymentError(
                            "Rolling capacity exceeded"
                        );
                    }

                    replacements.push(
                        await this.provision(
                            version,
                            `rolling-${position + index + 1}`
                        )
                    );

                    this.instances.push(replacements[index]);
                }

                this.assertHealthy(
                    await this.healthCheck(replacements),
                    "Rolling batch failed health validation"
                );

                this.emitEvent("rolling-batch-completed", {
                    position,
                    replacements: replacements.length,
                    remaining: original.length -
                        position - replaceCount
                });

                position += replaceCount;
            }

            if (this.instances.length !== desiredCount) {
                throw new DeploymentError(
                    "Final replica count differs from desired count"
                );
            }

            this.assertHealthy(
                await this.healthCheck(this.instances),
                "Final rolling environment is unhealthy"
            );

        } catch (error) {
            this.instances = original;
            throw error;
        }
    }

    async blueGreen(version, desiredCount, trafficWeight) {
        const original = this.instances;
        const oldTraffic = this.router.snapshot();

        this.policy.evaluate(
            DeploymentStrategy.BLUE_GREEN,
            original.length,
            desiredCount
        );

        try {
            this.emitEvent("green-provisioning", { version });

            const green = [];

            for (let index = 0; index < desiredCount; index++) {
                green.push(
                    await this.provision(version, `green-${index + 1}`)
                );
            }

            this.assertHealthy(
                await this.healthCheck(green),
                "Green environment failed health validation"
            );

            this.emitEvent("traffic-shift-started", {
                version,
                weight: trafficWeight
            });

            this.router.shiftTraffic(
                this.activeVersion,
                version,
                trafficWeight
            );

            if (trafficWeight !== 100) {
                this.instances = original.concat(green);
                this.emitEvent("canary-state", {
                    traffic: this.router.snapshot()
                });
                return;
            }

            this.instances = green;

        } catch (error) {
            this.instances = original;

            const previous = Object.entries(oldTraffic);
            this.router.weights.clear();

            for (const [key, value] of previous) {
                this.router.setWeight(key, value);
            }

            throw error;
        }
    }

    async deploy({
        version,
        strategy,
        replicas = 4,
        batchSize = 1,
        trafficWeight = 100
    }) {
        if (this.locked) {
            throw new DeploymentError(
                "Another deployment is already running",
                "DEPLOYMENT_LOCKED"
            );
        }

        if (!version || version.trim() === "") {
            throw new TypeError("Version is required");
        }

        if (!Object.values(DeploymentStrategy).includes(strategy)) {
            throw new TypeError("Unknown deployment strategy");
        }

        if (!Number.isInteger(replicas) || replicas < 1) {
            throw new TypeError("Invalid desired replica count");
        }

        if (!Number.isInteger(batchSize) || batchSize < 1) {
            throw new TypeError("Invalid batch size");
        }

        if (version === this.activeVersion) {
            throw new DeploymentError(
                "Version is already active"
            );
        }

        this.policy.evaluate(
            strategy,
            this.instances.length,
            replicas
        );

        const deployment = {
            id: crypto.randomUUID(),
            version,
            strategy,
            state: DeploymentState.PENDING,
            startedAt: new Date().toISOString(),
            previousVersion: this.activeVersion,
            error: null
        };

        this.locked = true;
        this.history.push(deployment);

        const oldInstances = this.instances.map(
            instance => ({ ...instance })
        );

        const oldRouter = this.router.snapshot();

        try {
            deployment.state = DeploymentState.PROVISIONING;

            this.emitEvent("deployment-started", {
                id: deployment.id,
                strategy,
                version
            });

            switch (strategy) {
                case DeploymentStrategy.RECREATE:
                    await this.recreate(version, replicas);
                    break;

                case DeploymentStrategy.ROLLING:
                    await this.rolling(
                        version,
                        replicas,
                        batchSize
                    );
                    break;

                case DeploymentStrategy.BLUE_GREEN:
                    deployment.state = DeploymentState.VALIDATING;

                    await this.blueGreen(
                        version,
                        replicas,
                        trafficWeight
                    );
                    break;
            }

            if (strategy !== DeploymentStrategy.BLUE_GREEN ||
                trafficWeight === 100) {
                this.previousVersion = this.activeVersion;
                this.activeVersion = version;
                this.router.switchVersion(version);
                deployment.state = DeploymentState.SUCCEEDED;
            } else {
                deployment.state = DeploymentState.VALIDATING;
            }

            this.emitEvent("deployment-state-changed", {
                id: deployment.id,
                state: deployment.state
            });

            return deployment;

        } catch (error) {
            this.instances = oldInstances;
            this.router.weights.clear();

            for (const [key, value] of Object.entries(oldRouter)) {
                this.router.setWeight(key, value);
            }

            deployment.state = DeploymentState.FAILED;
            deployment.error = error.message;

            this.emitEvent("deployment-failed", {
                id: deployment.id,
                error: error.message
            });

            throw error;

        } finally {
            deployment.completedAt = new Date().toISOString();
            this.locked = false;
        }
    }

    async rollback() {
        if (!this.previousVersion) {
            throw new DeploymentError(
                "No previous release is available"
            );
        }

        const target = this.previousVersion;

        const replacements = [];

        for (let index = 0; index < 4; index++) {
            replacements.push(
                await this.provision(target, `rollback-${index + 1}`)
            );
        }

        this.assertHealthy(
            await this.healthCheck(replacements),
            "Rollback environment is unhealthy"
        );

        this.instances = replacements;

        const current = this.activeVersion;
        this.activeVersion = target;
        this.previousVersion = current;
        this.router.switchVersion(target);

        this.emitEvent("rollback-completed", {
            version: target
        });
    }

    async exportHistory(filename = "deployment-history.json") {
        const content = JSON.stringify({
            activeVersion: this.activeVersion,
            traffic: this.router.snapshot(),
            history: this.history
        }, null, 2);

        await fs.writeFile(filename, content, {
            encoding: "utf8",
            mode: 0o600
        });
    }
}

async function main() {
    const engine = new DeploymentEngine({
        initialVersion: "1.0.0",
        replicas: 4,
        policy: new DeploymentPolicy({
            maxCapacity: 12,
            minHealthyPercent: 100,
            maxSurge: 1,
            maxUnavailable: 1
        })
    });

    engine.on("deployment-event", event => {
        console.log(
            `[${event.type}]`,
            JSON.stringify(event.details)
        );
    });

    const scenarios = [
        {
            version: "1.1.0",
            strategy: DeploymentStrategy.ROLLING,
            replicas: 4,
            batchSize: 1
        },
        {
            version: "1.2.0",
            strategy: DeploymentStrategy.BLUE_GREEN,
            replicas: 4
        },
        {
            version: "1.3.0",
            strategy: DeploymentStrategy.RECREATE,
            replicas: 4
        }
    ];

    for (const scenario of scenarios) {
        try {
            const result = await engine.deploy(scenario);

            console.log(
                "Deployment result:",
                result.state,
                result.version
            );
        } catch (error) {
            console.error(
                "Deployment rejected:",
                error.code || error.message
            );
        }
    }

    await engine.exportHistory();

    console.log("Active version:", engine.activeVersion);
    console.log("Traffic:", engine.router.snapshot());
}

async function test() {
    const engine = new DeploymentEngine({
        initialVersion: "1.0.0",
        replicas: 4,
        policy: new DeploymentPolicy({
            maxCapacity: 12,
            maxSurge: 1,
            maxUnavailable: 1
        })
    });

    const result = await engine.deploy({
        version: "2.0.0",
        strategy: DeploymentStrategy.BLUE_GREEN,
        replicas: 4
    });

    if (result.state !== DeploymentState.SUCCEEDED) {
        throw new Error("Blue-green deployment test failed");
    }

    if (engine.activeVersion !== "2.0.0") {
        throw new Error("Active version assertion failed");
    }

    console.log("All JavaScript tests passed.");
}

if (require.main === module) {
    (async () => {
        await test();
        await main();
    })().catch(error => {
        console.error(error);
        process.exitCode = 1;
    });
}

module.exports = {
    DeploymentEngine,
    DeploymentPolicy,
    DeploymentStrategy,
    DeploymentState,
    TrafficRouter,
    DeploymentError
};
