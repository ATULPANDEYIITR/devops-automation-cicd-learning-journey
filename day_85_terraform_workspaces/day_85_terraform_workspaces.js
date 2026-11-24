"use strict";

/*
 * Terraform Workspaces: Environment Separation and Workspace Strategies
 *
 * Event-driven workspace and deployment-policy simulator.
 * Runtime: Node.js 18+
 * Dependencies: Node.js standard library only.
 */

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");

class WorkspaceError extends Error {}
class ValidationError extends WorkspaceError {}
class ConflictError extends WorkspaceError {}
class ApprovalError extends WorkspaceError {}
class LockError extends WorkspaceError {}

const Environment = Object.freeze({
    DEVELOPMENT: "development",
    STAGING: "staging",
    PRODUCTION: "production"
});

const WorkspaceStatus = Object.freeze({
    ACTIVE: "active",
    LOCKED: "locked"
});

const DeploymentStatus = Object.freeze({
    APPLIED: "applied",
    REJECTED: "rejected"
});

const POLICIES = Object.freeze({
    development: {
        region: "ap-south-1",
        instanceType: "t3.micro",
        instanceCount: 1,
        approvalRequired: false,
        budget: 100
    },
    staging: {
        region: "ap-south-1",
        instanceType: "t3.small",
        instanceCount: 2,
        approvalRequired: false,
        budget: 500
    },
    production: {
        region: "ap-south-1",
        instanceType: "t3.medium",
        instanceCount: 3,
        approvalRequired: true,
        budget: 2000
    }
});

function validateWorkspaceName(name) {
    if (
        typeof name !== "string" ||
        !/^[a-z][a-z0-9_-]{0,62}$/.test(name)
    ) {
        throw new ValidationError("Invalid workspace name.");
    }
}

function validateResourceAddress(address) {
    if (
        typeof address !== "string" ||
        !/^[a-zA-Z][a-zA-Z0-9_.-]{0,127}$/.test(address)
    ) {
        throw new ValidationError("Invalid resource address.");
    }
}

function clone(value) {
    return structuredClone(value);
}

function hashState(resources) {
    return crypto
        .createHash("sha256")
        .update(JSON.stringify(resources))
        .digest("hex");
}

class AsyncStateLock {
    constructor() {
        this.locked = false;
        this.queue = [];
    }

    async acquire(owner) {
        if (!this.locked) {
            this.locked = true;
            this.owner = owner;
            return this.createRelease(owner);
        }

        return new Promise((resolve) => {
            this.queue.push({ owner, resolve });
        });
    }

    createRelease(owner) {
        let released = false;

        return () => {
            if (released || this.owner !== owner) {
                throw new LockError("Invalid state lock release.");
            }

            released = true;

            const next = this.queue.shift();

            if (next) {
                this.owner = next.owner;
                next.resolve(this.createRelease(next.owner));
            } else {
                this.owner = null;
                this.locked = false;
            }
        };
    }
}

class Workspace {
    constructor(name, environment) {
        validateWorkspaceName(name);

        if (!POLICIES[environment]) {
            throw new ValidationError("Unknown environment.");
        }

        this.name = name;
        this.environment = environment;
        this.config = clone(POLICIES[environment]);
        this.status = WorkspaceStatus.ACTIVE;

        this.state = {
            lineage: crypto.randomUUID(),
            serial: 0,
            resources: {},
            updatedAt: null
        };

        this.deployments = [];
        this.lock = new AsyncStateLock();
    }

    snapshot() {
        return Object.freeze({
            name: this.name,
            environment: this.environment,
            serial: this.state.serial,
            resources: clone(this.state.resources),
            fingerprint: hashState(this.state.resources)
        });
    }
}

class TerraformWorkspaceEngine extends EventEmitter {
    constructor() {
        super();

        this.workspaces = new Map();
        this.currentWorkspace = "default";

        this.workspaces.set(
            "default",
            new Workspace("default", Environment.DEVELOPMENT)
        );
    }

    create(name, environment) {
        validateWorkspaceName(name);

        if (this.workspaces.has(name)) {
            throw new ConflictError("Workspace already exists.");
        }

        const workspace = new Workspace(name, environment);
        this.workspaces.set(name, workspace);

        this.emit("workspace:created", workspace.snapshot());

        return workspace.snapshot();
    }

    select(name) {
        const workspace = this.workspaces.get(name);

        if (!workspace) {
            throw new ValidationError("Workspace does not exist.");
        }

        if (workspace.status !== WorkspaceStatus.ACTIVE) {
            throw new ConflictError("Workspace is not active.");
        }

        this.currentWorkspace = name;
        this.emit("workspace:selected", workspace.snapshot());

        return workspace.snapshot();
    }

    current() {
        const workspace = this.workspaces.get(this.currentWorkspace);

        if (!workspace) {
            throw new ValidationError("Current workspace is unavailable.");
        }

        return workspace;
    }

    plan(desiredResources) {
        const workspace = this.current();

        if (
            !desiredResources ||
            typeof desiredResources !== "object" ||
            Array.isArray(desiredResources) ||
            Object.keys(desiredResources).length === 0
        ) {
            throw new ValidationError("Invalid desired resource map.");
        }

        const operations = [];

        for (const [address, desired] of Object.entries(desiredResources)) {
            validateResourceAddress(address);

            if (
                desired !== null &&
                (typeof desired !== "object" || Array.isArray(desired))
            ) {
                throw new ValidationError(
                    `Invalid configuration for ${address}.`
                );
            }

            const existing = workspace.state.resources[address];

            let action;

            if (desired === null) {
                action = existing ? "destroy" : "no_change";
            } else if (existing === undefined) {
                action = "create";
            } else if (JSON.stringify(existing) !== JSON.stringify(desired)) {
                action = "update";
            } else {
                action = "no_change";
            }

            operations.push({
                address,
                action,
                desired: desired === null ? null : clone(desired)
            });
        }

        const plan = {
            id: crypto.randomUUID(),
            workspace: workspace.name,
            environment: workspace.environment,
            expectedSerial: workspace.state.serial,
            expectedFingerprint: hashState(workspace.state.resources),
            approvalRequired: workspace.config.approvalRequired,
            operations
        };

        this.emit("deployment:planned", {
            id: plan.id,
            workspace: plan.workspace,
            operations: operations.length
        });

        return plan;
    }

    async apply(plan, options = {}) {
        const workspace = this.current();

        if (plan.workspace !== workspace.name) {
            throw new ConflictError("Plan belongs to another workspace.");
        }

        if (plan.approvalRequired && options.approved !== true) {
            throw new ApprovalError(
                "Production deployment requires explicit approval."
            );
        }

        const release = await workspace.lock.acquire(
            `deployment-${plan.id}`
        );

        try {
            if (workspace.state.serial !== plan.expectedSerial) {
                throw new ConflictError("Stale plan: state serial changed.");
            }

            if (
                hashState(workspace.state.resources) !==
                plan.expectedFingerprint
            ) {
                throw new ConflictError("State fingerprint mismatch.");
            }

            const nextResources = clone(workspace.state.resources);

            for (const operation of plan.operations) {
                validateResourceAddress(operation.address);

                if (operation.action === "destroy") {
                    delete nextResources[operation.address];
                } else if (
                    operation.action === "create" ||
                    operation.action === "update"
                ) {
                    if (!operation.desired) {
                        throw new ValidationError(
                            "Missing desired resource configuration."
                        );
                    }

                    nextResources[operation.address] =
                        clone(operation.desired);
                } else if (operation.action !== "no_change") {
                    throw new ValidationError("Unknown plan operation.");
                }
            }

            // Commit the new state only after all operations validate.
            workspace.state.resources = nextResources;
            workspace.state.serial++;
            workspace.state.updatedAt = new Date().toISOString();

            const deployment = {
                id: plan.id,
                workspace: workspace.name,
                status: DeploymentStatus.APPLIED,
                stateSerial: workspace.state.serial,
                timestamp: workspace.state.updatedAt
            };

            workspace.deployments.push(deployment);

            this.emit("deployment:applied", deployment);

            return deployment;
        } finally {
            release();
        }
    }

    async destroyWorkspaceResources(name) {
        const workspace = this.workspaces.get(name);

        if (!workspace) {
            throw new ValidationError("Workspace does not exist.");
        }

        const release = await workspace.lock.acquire(`destroy-${name}`);

        try {
            workspace.state.resources = {};
            workspace.state.serial++;
            workspace.state.updatedAt = new Date().toISOString();
        } finally {
            release();
        }
    }

    delete(name) {
        if (name === "default") {
            throw new ConflictError("Default workspace cannot be deleted.");
        }

        if (name === this.currentWorkspace) {
            throw new ConflictError(
                "Select another workspace before deletion."
            );
        }

        const workspace = this.workspaces.get(name);

        if (!workspace) {
            throw new ValidationError("Workspace does not exist.");
        }

        if (Object.keys(workspace.state.resources).length > 0) {
            throw new ConflictError(
                "Destroy managed resources before deleting the workspace."
            );
        }

        this.workspaces.delete(name);
        this.emit("workspace:deleted", { name });
    }

    report() {
        return [...this.workspaces.values()].map((workspace) => ({
            workspace: workspace.name,
            environment: workspace.environment,
            stateSerial: workspace.state.serial,
            resourceCount: Object.keys(workspace.state.resources).length,
            fingerprint: hashState(workspace.state.resources)
        }));
    }

    async exportState(directory) {
        await fs.mkdir(directory, { recursive: true, mode: 0o700 });

        for (const workspace of this.workspaces.values()) {
            const destination = path.join(
                directory,
                `${workspace.name}.state.json`
            );

            const serialized = JSON.stringify({
                ...workspace.state,
                workspace: workspace.name,
                environment: workspace.environment
            }, null, 2);

            await fs.writeFile(destination, serialized, {
                mode: 0o600,
                flag: "w"
            });
        }
    }
}

async function main() {
    const engine = new TerraformWorkspaceEngine();

    engine.on("workspace:created", (event) => {
        console.log("Created:", event.name);
    });

    engine.on("deployment:applied", (event) => {
        console.log(
            `Applied ${event.workspace}, serial ${event.stateSerial}`
        );
    });

    engine.create("development", Environment.DEVELOPMENT);
    engine.create("staging", Environment.STAGING);
    engine.create("production", Environment.PRODUCTION);

    const scenarios = [
        {
            workspace: "development",
            resources: {
                "aws_instance.application": {
                    instance_type: "t3.micro",
                    count: 1
                }
            }
        },
        {
            workspace: "staging",
            resources: {
                "aws_instance.application": {
                    instance_type: "t3.small",
                    count: 2
                },
                "aws_db_instance.main": {
                    engine: "postgres",
                    storage_gb: 30
                }
            }
        },
        {
            workspace: "production",
            resources: {
                "aws_instance.application": {
                    instance_type: "t3.medium",
                    count: 3
                }
            }
        }
    ];

    for (const scenario of scenarios) {
        engine.select(scenario.workspace);

        const plan = engine.plan(scenario.resources);

        try {
            const result = await engine.apply(plan, {
                approved: scenario.workspace === "production"
            });

            console.log(result);
        } catch (error) {
            console.error("Deployment rejected:", error.message);
        }
    }

    // Production approval enforcement.
    engine.select("production");

    try {
        await engine.apply(
            engine.plan({
                "aws_instance.application": {
                    instance_type: "t3.medium",
                    count: 4
                }
            }),
            { approved: false }
        );
    } catch (error) {
        console.log("Expected policy rejection:", error.message);
    }

    // Concurrent state updates are serialized by the lock.
    engine.select("development");

    const firstPlan = engine.plan({
        "aws_instance.application": {
            instance_type: "t3.micro",
            count: 2
        }
    });

    const secondPlan = engine.plan({
        "aws_instance.application": {
            instance_type: "t3.micro",
            count: 3
        }
    });

    const results = await Promise.allSettled([
        engine.apply(firstPlan),
        engine.apply(secondPlan)
    ]);

    console.log(
        "Concurrent operations:",
        results.map((result) => result.status)
    );

    console.log("\nEnvironment report:");
    console.table(engine.report());

    // Exporting state is a demonstration. Real Terraform state should be
    // stored in an authenticated, encrypted remote backend.
    await engine.exportState("./terraform-workspace-output");
}

main().catch((error) => {
    console.error("Execution failed:", error.message);
    process.exitCode = 1;
});
