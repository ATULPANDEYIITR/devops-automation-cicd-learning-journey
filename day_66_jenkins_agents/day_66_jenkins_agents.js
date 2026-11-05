"use strict";

/*
 * Jenkins Agents: Event-driven distributed build scheduler.
 *
 * Demonstrates:
 * - Persistent static agents.
 * - On-demand dynamic agents.
 * - Asynchronous build execution.
 * - Label-based scheduling.
 * - Executor limits.
 * - Provisioning failures.
 * - Build timeouts and retries.
 * - Dynamic-agent cleanup.
 *
 * Runtime: Node.js 18+
 */

const { EventEmitter } = require("node:events");
const { randomUUID } = require("node:crypto");

const AgentType = Object.freeze({
    STATIC: "STATIC",
    DYNAMIC: "DYNAMIC"
});

const AgentState = Object.freeze({
    ONLINE: "ONLINE",
    BUSY: "BUSY",
    OFFLINE: "OFFLINE",
    TERMINATED: "TERMINATED"
});

const BuildState = Object.freeze({
    QUEUED: "QUEUED",
    RUNNING: "RUNNING",
    SUCCESS: "SUCCESS",
    FAILED: "FAILED",
    CANCELLED: "CANCELLED"
});

class JenkinsError extends Error {
    constructor(message, code) {
        super(message);
        this.name = "JenkinsError";
        this.code = code;
    }
}

function validateLabels(labels) {
    if (!Array.isArray(labels) || labels.length === 0) {
        throw new JenkinsError(
            "At least one label is required.",
            "INVALID_LABELS"
        );
    }

    for (const label of labels) {
        if (
            typeof label !== "string" ||
            !/^[a-zA-Z0-9_.-]+$/.test(label)
        ) {
            throw new JenkinsError(
                `Invalid label: ${label}`,
                "INVALID_LABEL"
            );
        }
    }

    return new Set(labels);
}

class Build {
    constructor({
        id = randomUUID(),
        name,
        labels,
        durationMs = 100,
        maxRetries = 0
    }) {
        if (!name || !name.trim()) {
            throw new JenkinsError(
                "Build name is required.",
                "INVALID_BUILD"
            );
        }

        if (!Number.isInteger(durationMs) || durationMs <= 0) {
            throw new JenkinsError(
                "Build duration must be positive.",
                "INVALID_DURATION"
            );
        }

        if (!Number.isInteger(maxRetries) || maxRetries < 0) {
            throw new JenkinsError(
                "Retry count cannot be negative.",
                "INVALID_RETRIES"
            );
        }

        this.id = id;
        this.name = name;
        this.labels = validateLabels(labels);
        this.durationMs = durationMs;
        this.maxRetries = maxRetries;
        this.attempts = 0;
        this.state = BuildState.QUEUED;
        this.agentId = null;
        this.error = null;
    }
}

class Agent {
    constructor({
        id,
        type,
        labels,
        executors = 1,
        maxBuilds = Infinity
    }) {
        if (!id || !id.trim()) {
            throw new JenkinsError("Agent ID is required.");
        }

        if (!Object.values(AgentType).includes(type)) {
            throw new JenkinsError("Invalid agent type.");
        }

        if (!Number.isInteger(executors) || executors < 1) {
            throw new JenkinsError("Invalid executor count.");
        }

        this.id = id;
        this.type = type;
        this.labels = validateLabels(labels);
        this.executors = executors;
        this.maxBuilds = maxBuilds;
        this.completedBuilds = 0;
        this.activeBuilds = new Set();
        this.state = AgentState.ONLINE;
        this.lastUsed = Date.now();
    }

    supports(build) {
        return [...build.labels].every(
            label => this.labels.has(label)
        );
    }

    get availableExecutors() {
        return this.executors - this.activeBuilds.size;
    }

    get available() {
        return (
            this.state === AgentState.ONLINE &&
            this.availableExecutors > 0 &&
            this.completedBuilds + this.activeBuilds.size <
                this.maxBuilds
        );
    }
}

class DynamicAgentProvider {
    constructor({ maxAgents = 3, provisioningDelayMs = 20 } = {}) {
        this.maxAgents = maxAgents;
        this.provisioningDelayMs = provisioningDelayMs;
        this.active = new Map();
        this.sequence = 1;
        this.failNextProvision = false;
    }

    async provision(requiredLabels) {
        if (this.active.size >= this.maxAgents) {
            throw new JenkinsError(
                "Dynamic agent capacity exhausted.",
                "CAPACITY_EXCEEDED"
            );
        }

        await new Promise(resolve =>
            setTimeout(resolve, this.provisioningDelayMs)
        );

        if (this.failNextProvision) {
            this.failNextProvision = false;
            throw new JenkinsError(
                "Agent provisioning failed.",
                "PROVISIONING_FAILED"
            );
        }

        const id = `cloud-agent-${this.sequence++}`;

        const agent = new Agent({
            id,
            type: AgentType.DYNAMIC,
            labels: [...requiredLabels, "ephemeral"],
            executors: 1,
            maxBuilds: 1
        });

        this.active.set(id, agent);
        return agent;
    }

    terminate(id) {
        const agent = this.active.get(id);

        if (!agent) {
            return false;
        }

        if (agent.activeBuilds.size !== 0) {
            throw new JenkinsError(
                "Cannot terminate an agent executing builds.",
                "AGENT_BUSY"
            );
        }

        agent.state = AgentState.TERMINATED;
        this.active.delete(id);
        return true;
    }
}

class JenkinsController extends EventEmitter {
    constructor({
        provider,
        buildTimeoutMs = 5000,
        idleTimeoutMs = 30000
    }) {
        super();

        if (!provider) {
            throw new JenkinsError(
                "A dynamic agent provider is required."
            );
        }

        this.provider = provider;
        this.buildTimeoutMs = buildTimeoutMs;
        this.idleTimeoutMs = idleTimeoutMs;

        this.agents = new Map();
        this.builds = new Map();
        this.queue = [];
        this.completed = [];
        this.metrics = {
            submitted: 0,
            successful: 0,
            failed: 0,
            provisioningFailures: 0,
            retries: 0
        };
    }

    registerStaticAgent(agent) {
        if (agent.type !== AgentType.STATIC) {
            throw new JenkinsError(
                "Only static agents can be registered manually."
            );
        }

        if (this.agents.has(agent.id)) {
            throw new JenkinsError("Duplicate agent ID.");
        }

        this.agents.set(agent.id, agent);
        this.emit("agent:registered", agent);
    }

    submit(build) {
        if (this.builds.has(build.id)) {
            throw new JenkinsError("Duplicate build ID.");
        }

        this.builds.set(build.id, build);
        this.queue.push(build);

        this.metrics.submitted++;
        this.emit("build:queued", build);
    }

    findCompatibleAgent(build) {
        const candidates = [...this.agents.values()]
            .filter(agent =>
                agent.available && agent.supports(build)
            );

        // Prefer static agents to avoid unnecessary cloud provisioning.
        candidates.sort((a, b) => {
            if (a.type !== b.type) {
                return a.type === AgentType.STATIC ? -1 : 1;
            }

            return b.availableExecutors - a.availableExecutors;
        });

        return candidates[0] || null;
    }

    async acquireAgent(build) {
        const existing = this.findCompatibleAgent(build);

        if (existing) {
            return existing;
        }

        try {
            const dynamic = await this.provider.provision(
                build.labels
            );

            this.agents.set(dynamic.id, dynamic);
            this.emit("agent:provisioned", dynamic);

            return dynamic;
        } catch (error) {
            this.metrics.provisioningFailures++;
            this.emit("agent:provisioning-failed", {
                buildId: build.id,
                message: error.message
            });

            return null;
        }
    }

    async runBuild(build, agent) {
        build.state = BuildState.RUNNING;
        build.agentId = agent.id;
        build.attempts++;

        agent.activeBuilds.add(build.id);
        agent.state = AgentState.BUSY;

        this.emit("build:started", { build, agent });

        let timer;

        try {
            const execution = new Promise((resolve, reject) => {
                timer = setTimeout(() => {
                    reject(
                        new JenkinsError(
                            "Build execution timed out.",
                            "BUILD_TIMEOUT"
                        )
                    );
                }, this.buildTimeoutMs);

                setTimeout(resolve, build.durationMs);
            });

            await execution;

            build.state = BuildState.SUCCESS;
            build.error = null;
            this.metrics.successful++;
            this.emit("build:success", build);
        } catch (error) {
            build.error = error.message;

            if (build.attempts <= build.maxRetries) {
                build.state = BuildState.QUEUED;
                build.agentId = null;
                this.metrics.retries++;
                this.queue.push(build);

                this.emit("build:retry", {
                    build,
                    error: error.message
                });
            } else {
                build.state = BuildState.FAILED;
                this.metrics.failed++;
                this.emit("build:failed", build);
            }
        } finally {
            clearTimeout(timer);

            agent.activeBuilds.delete(build.id);
            agent.completedBuilds++;
            agent.lastUsed = Date.now();

            if (agent.state !== AgentState.OFFLINE) {
                agent.state = AgentState.ONLINE;
            }

            if (
                build.state === BuildState.SUCCESS ||
                build.state === BuildState.FAILED
            ) {
                this.completed.push(build);
            }
        }
    }

    async schedule() {
        const pending = this.queue.splice(0);

        for (const build of pending) {
            if (build.state !== BuildState.QUEUED) {
                continue;
            }

            const agent = await this.acquireAgent(build);

            if (!agent) {
                this.queue.push(build);
                continue;
            }

            // Provisioning is asynchronous, so recheck capacity
            // immediately before assigning the build.
            if (!agent.available || !agent.supports(build)) {
                this.queue.push(build);
                continue;
            }

            await this.runBuild(build, agent);
        }
    }

    cancel(buildId) {
        const build = this.builds.get(buildId);

        if (!build) {
            throw new JenkinsError("Unknown build ID.");
        }

        if (
            build.state !== BuildState.QUEUED &&
            build.state !== BuildState.RUNNING
        ) {
            throw new JenkinsError(
                "Build is already in a final state."
            );
        }

        if (build.state === BuildState.RUNNING) {
            throw new JenkinsError(
                "Running cancellation requires an execution abort signal."
            );
        }

        this.queue = this.queue.filter(
            item => item.id !== buildId
        );

        build.state = BuildState.CANCELLED;
        this.completed.push(build);

        this.emit("build:cancelled", build);
    }

    cleanupIdleAgents() {
        const now = Date.now();

        for (const [id, agent] of this.agents) {
            if (agent.type !== AgentType.DYNAMIC) {
                continue;
            }

            if (agent.activeBuilds.size > 0) {
                continue;
            }

            if (now - agent.lastUsed < this.idleTimeoutMs) {
                continue;
            }

            this.provider.terminate(id);
            this.agents.delete(id);

            this.emit("agent:terminated", id);
        }
    }

    report() {
        console.log("\n========== JENKINS CONTROLLER ==========");

        console.log("Agent inventory:");

        for (const agent of this.agents.values()) {
            console.log({
                id: agent.id,
                type: agent.type,
                state: agent.state,
                executors: agent.executors,
                activeBuilds: agent.activeBuilds.size,
                labels: [...agent.labels]
            });
        }

        console.log("\nMetrics:", this.metrics);
        console.log("Queued builds:", this.queue.length);
    }
}

async function main() {
    const provider = new DynamicAgentProvider({
        maxAgents: 3,
        provisioningDelayMs: 10
    });

    const controller = new JenkinsController({
        provider,
        buildTimeoutMs: 1000,
        idleTimeoutMs: 0
    });

    controller.on("build:success", build => {
        console.log(`[SUCCESS] ${build.name}`);
    });

    controller.on("build:failed", build => {
        console.log(`[FAILED] ${build.name}: ${build.error}`);
    });

    controller.on("agent:provisioned", agent => {
        console.log(`[PROVISIONED] ${agent.id}`);
    });

    controller.on("build:retry", event => {
        console.log(
            `[RETRY] ${event.build.name}: ${event.error}`
        );
    });

    controller.registerStaticAgent(
        new Agent({
            id: "linux-static-01",
            type: AgentType.STATIC,
            labels: ["linux", "python", "docker"],
            executors: 2
        })
    );

    controller.registerStaticAgent(
        new Agent({
            id: "windows-static-01",
            type: AgentType.STATIC,
            labels: ["windows", "dotnet"],
            executors: 1
        })
    );

    const jobs = [
        new Build({
            name: "Python Unit Tests",
            labels: ["linux", "python"],
            durationMs: 100
        }),
        new Build({
            name: "Docker Build",
            labels: ["linux", "docker"],
            durationMs: 150
        }),
        new Build({
            name: "Windows Integration",
            labels: ["windows", "dotnet"],
            durationMs: 120
        }),
        new Build({
            name: "Security Scan",
            labels: ["linux", "security"],
            durationMs: 100
        }),
        new Build({
            name: "Cloud Deployment",
            labels: ["linux", "deployment"],
            durationMs: 120,
            maxRetries: 1
        }),
        new Build({
            name: "Slow Integration Test",
            labels: ["linux", "integration"],
            durationMs: 1500,
            maxRetries: 0
        })
    ];

    for (const job of jobs) {
        controller.submit(job);
    }

    console.log("\n--- Executing distributed workload ---");

    // A production controller would run a persistent scheduler.
    // This simulation processes batches until the queue is empty
    // or provisioning capacity prevents further progress.
    let previousQueueLength = -1;

    for (let round = 0; round < 10; round++) {
        await controller.schedule();

        if (controller.queue.length === 0) {
            break;
        }

        if (controller.queue.length === previousQueueLength) {
            break;
        }

        previousQueueLength = controller.queue.length;
    }

    console.log("\n--- Infrastructure cleanup ---");

    controller.cleanupIdleAgents();
    controller.report();

    console.log("\n--- Build results ---");

    for (const build of controller.builds.values()) {
        console.log({
            name: build.name,
            state: build.state,
            attempts: build.attempts,
            agent: build.agentId,
            error: build.error
        });
    }
}

main().catch(error => {
    console.error("Controller failure:", error.message);
    process.exitCode = 1;
});
