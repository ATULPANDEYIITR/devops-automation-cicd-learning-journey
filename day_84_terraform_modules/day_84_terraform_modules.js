"use strict";

/**
 * Terraform Modules: Event-driven module orchestration.
 *
 * Demonstrates:
 * - Reusable module contracts
 * - Version resolution
 * - Input and output validation
 * - Module dependency graphs
 * - Asynchronous execution
 * - Deployment event handling
 * - Retry handling and deployment locking
 * - Immutable deployment snapshots
 *
 * Runtime: Node.js 18+
 */

const { EventEmitter } = require("node:events");
const crypto = require("node:crypto");

class ModuleError extends Error {}
class ValidationError extends ModuleError {}
class DependencyError extends ModuleError {}
class DeploymentError extends ModuleError {}

const DeploymentStatus = Object.freeze({
    PENDING: "PENDING",
    VALIDATING: "VALIDATING",
    PLANNING: "PLANNING",
    APPLYING: "APPLYING",
    SUCCEEDED: "SUCCEEDED",
    FAILED: "FAILED"
});

function parseVersion(version) {
    const match = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.exec(version);

    if (!match) {
        throw new ValidationError(`Invalid version: ${version}`);
    }

    return match.slice(1).map(Number);
}

function compareVersions(a, b) {
    const left = parseVersion(a);
    const right = parseVersion(b);

    for (let i = 0; i < 3; i++) {
        if (left[i] !== right[i]) {
            return left[i] - right[i];
        }
    }

    return 0;
}

function matchesConstraint(version, constraint) {
    if (constraint.startsWith("=")) {
        return version === constraint.slice(1).trim();
    }

    const match = /^~>\s*(\d+)\.(\d+)(?:\.(\d+))?$/.exec(constraint);

    if (!match) {
        throw new ValidationError(
            `Unsupported version constraint: ${constraint}`
        );
    }

    const [major, minor, patch] = parseVersion(version);
    const requestedMajor = Number(match[1]);
    const requestedMinor = Number(match[2]);

    if (major !== requestedMajor) {
        return false;
    }

    if (match[3] !== undefined) {
        return (
            minor === requestedMinor &&
            patch >= Number(match[3])
        );
    }

    return minor >= requestedMinor;
}

function deepFreeze(value) {
    if (value && typeof value === "object" && !Object.isFrozen(value)) {
        Object.freeze(value);

        for (const child of Object.values(value)) {
            deepFreeze(child);
        }
    }

    return value;
}

class ModuleDefinition {
    constructor({
        name,
        version,
        source,
        inputs,
        outputs,
        resources,
        dependencies = []
    }) {
        if (!name || !source) {
            throw new ValidationError("Module name and source are required.");
        }

        parseVersion(version);

        this.name = name;
        this.version = version;
        this.source = source;
        this.inputs = structuredClone(inputs);
        this.outputs = structuredClone(outputs);
        this.resources = structuredClone(resources);
        this.dependencies = [...dependencies];

        deepFreeze(this.inputs);
        deepFreeze(this.outputs);
        deepFreeze(this.resources);
        Object.freeze(this.dependencies);
    }

    validateInputs(values) {
        const result = {};

        for (const supplied of Object.keys(values)) {
            if (!Object.hasOwn(this.inputs, supplied)) {
                throw new ValidationError(
                    `Unknown input '${supplied}' in ${this.name}.`
                );
            }
        }

        for (const [name, definition] of Object.entries(this.inputs)) {
            let value = values[name];

            if (value === undefined) {
                value = definition.default;
            }

            if (value === undefined || value === null) {
                if (definition.required) {
                    throw new ValidationError(
                        `Required input '${name}' is missing.`
                    );
                }

                result[name] = null;
                continue;
            }

            const validTypes = {
                string: typeof value === "string",
                number: typeof value === "number" && Number.isFinite(value),
                boolean: typeof value === "boolean",
                array: Array.isArray(value),
                object:
                    typeof value === "object" &&
                    !Array.isArray(value) &&
                    value !== null
            };

            if (!validTypes[definition.type]) {
                throw new ValidationError(
                    `Input '${name}' must be ${definition.type}.`
                );
            }

            if (
                definition.allowed &&
                !definition.allowed.includes(value)
            ) {
                throw new ValidationError(
                    `Invalid value for '${name}'.`
                );
            }

            result[name] = value;
        }

        return deepFreeze(result);
    }

    fingerprint() {
        const serialized = JSON.stringify({
            name: this.name,
            version: this.version,
            source: this.source,
            inputs: this.inputs,
            outputs: this.outputs,
            resources: this.resources,
            dependencies: this.dependencies
        });

        return crypto
            .createHash("sha256")
            .update(serialized)
            .digest("hex");
    }
}

class ModuleRegistry {
    constructor() {
        this.modules = new Map();
    }

    register(module) {
        if (!(module instanceof ModuleDefinition)) {
            throw new ValidationError("Invalid module definition.");
        }

        if (!this.modules.has(module.name)) {
            this.modules.set(module.name, new Map());
        }

        const versions = this.modules.get(module.name);

        if (versions.has(module.version)) {
            throw new ValidationError("Duplicate module version.");
        }

        versions.set(module.version, module);
    }

    resolve(name, constraint) {
        const versions = this.modules.get(name);

        if (!versions) {
            throw new ValidationError(`Unknown module: ${name}`);
        }

        const compatible = [...versions.values()]
            .filter(module =>
                matchesConstraint(module.version, constraint)
            )
            .sort((a, b) =>
                compareVersions(b.version, a.version)
            );

        if (!compatible.length) {
            throw new ValidationError(
                `No compatible version for ${name}: ${constraint}`
            );
        }

        return compatible[0];
    }
}

class DependencyGraph {
    static order(graph) {
        const visited = new Set();
        const active = new Set();
        const ordered = [];

        const visit = node => {
            if (active.has(node)) {
                throw new DependencyError(
                    `Circular dependency at ${node}.`
                );
            }

            if (visited.has(node)) {
                return;
            }

            active.add(node);

            for (const dependency of graph.get(node) ?? []) {
                if (!graph.has(dependency)) {
                    throw new DependencyError(
                        `Missing dependency: ${dependency}`
                    );
                }

                visit(dependency);
            }

            active.delete(node);
            visited.add(node);
            ordered.push(node);
        };

        for (const node of graph.keys()) {
            visit(node);
        }

        return ordered;
    }
}

class DeploymentEngine extends EventEmitter {
    constructor(registry) {
        super();

        this.registry = registry;
        this.state = new Map();
        this.deployments = new Map();
        this.locked = false;
    }

    async executeWithRetry(operation, attempts = 3) {
        let lastError;

        for (let attempt = 1; attempt <= attempts; attempt++) {
            try {
                return await operation();
            } catch (error) {
                lastError = error;

                if (attempt < attempts) {
                    await new Promise(resolve =>
                        setTimeout(resolve, attempt * 50)
                    );
                }
            }
        }

        throw lastError;
    }

    createPlan(calls) {
        const instances = new Map();
        const graph = new Map();

        for (const call of calls) {
            if (instances.has(call.instance)) {
                throw new ValidationError(
                    `Duplicate instance: ${call.instance}`
                );
            }

            const definition = this.registry.resolve(
                call.module,
                call.version
            );

            instances.set(call.instance, {
                definition,
                inputs: definition.validateInputs(call.inputs)
            });

            graph.set(
                call.instance,
                [...definition.dependencies]
            );
        }

        const order = DependencyGraph.order(graph);
        const plan = [];

        for (const instance of order) {
            const entry = instances.get(instance);
            const { definition, inputs } = entry;

            for (const resource of definition.resources) {
                const address =
                    `module.${instance}.${resource.type}.${resource.name}`;

                const desired = {
                    ...resource.configuration,
                    inputs,
                    fingerprint: definition.fingerprint()
                };

                const previous = this.state.get(address);

                let action = "CREATE";

                if (previous) {
                    action =
                        JSON.stringify(previous) === JSON.stringify(desired)
                            ? "NO_CHANGE"
                            : "UPDATE";
                }

                plan.push({
                    address,
                    action,
                    desired
                });
            }
        }

        return plan;
    }

    async deploy(deploymentId, calls) {
        if (this.locked) {
            throw new DeploymentError(
                "Another deployment is currently running."
            );
        }

        if (this.deployments.has(deploymentId)) {
            throw new DeploymentError(
                "Deployment identifier already exists."
            );
        }

        this.locked = true;

        const deployment = {
            id: deploymentId,
            status: DeploymentStatus.PENDING,
            startedAt: new Date().toISOString(),
            events: []
        };

        this.deployments.set(deploymentId, deployment);

        const emitStatus = (status, details = {}) => {
            deployment.status = status;

            const event = {
                deploymentId,
                status,
                timestamp: new Date().toISOString(),
                ...details
            };

            deployment.events.push(event);
            this.emit("deployment", event);
        };

        try {
            emitStatus(DeploymentStatus.VALIDATING);

            const plan = await this.executeWithRetry(
                async () => this.createPlan(calls)
            );

            emitStatus(DeploymentStatus.PLANNING, {
                resourceCount: plan.length
            });

            // Stage changes before updating the authoritative state.
            const staged = new Map(this.state);

            emitStatus(DeploymentStatus.APPLYING);

            for (const item of plan) {
                if (item.action !== "NO_CHANGE") {
                    staged.set(item.address, item.desired);
                }
            }

            // Commit the staged deployment only after planning succeeds.
            this.state = staged;

            emitStatus(DeploymentStatus.SUCCEEDED, {
                revision: this.state.size,
                changes: plan.filter(
                    item => item.action !== "NO_CHANGE"
                ).length
            });

            return {
                id: deploymentId,
                status: deployment.status,
                plan
            };
        } catch (error) {
            emitStatus(DeploymentStatus.FAILED, {
                error: error.message
            });

            throw error instanceof ModuleError
                ? error
                : new DeploymentError(error.message);
        } finally {
            this.locked = false;
        }
    }

    detectDrift(actualState) {
        const drift = [];

        for (const [address, expected] of this.state) {
            const actual = actualState.get(address);

            if (JSON.stringify(expected) !== JSON.stringify(actual)) {
                drift.push(address);
            }
        }

        return drift;
    }
}

async function main() {
    const registry = new ModuleRegistry();

    registry.register(new ModuleDefinition({
        name: "network",
        version: "1.2.0",
        source: "registry.example.com/platform/network",
        inputs: {
            environment: {
                type: "string",
                required: true,
                allowed: ["development", "staging", "production"]
            },
            cidr: {
                type: "string",
                required: true
            }
        },
        outputs: {
            network_id: { type: "string" }
        },
        resources: [
            {
                type: "aws_vpc",
                name: "main",
                configuration: {
                    enable_dns_support: true,
                    enable_dns_hostnames: true
                }
            }
        ]
    }));

    registry.register(new ModuleDefinition({
        name: "application",
        version: "2.0.0",
        source: "registry.example.com/platform/application",
        inputs: {
            environment: { type: "string", required: true },
            instance_type: {
                type: "string",
                required: false,
                default: "t3.small"
            }
        },
        outputs: {
            application_id: { type: "string" }
        },
        dependencies: ["network"],
        resources: [
            {
                type: "aws_instance",
                name: "web",
                configuration: {
                    encrypted_volume: true,
                    monitoring: true
                }
            }
        ]
    }));

    const engine = new DeploymentEngine(registry);

    engine.on("deployment", event => {
        console.log(
            `[${event.status}] ${event.deploymentId}`
        );
    });

    const calls = [
        {
            instance: "network",
            module: "network",
            version: "~> 1.2.0",
            inputs: {
                environment: "production",
                cidr: "10.30.0.0/16"
            }
        },
        {
            instance: "application",
            module: "application",
            version: "= 2.0.0",
            inputs: {
                environment: "production",
                instance_type: "t3.medium"
            }
        }
    ];

    const result = await engine.deploy("deployment-001", calls);

    console.log("\nDeployment plan:");

    for (const item of result.plan) {
        console.log(`${item.action.padEnd(12)} ${item.address}`);
    }

    console.log("\nManaged resources:", engine.state.size);

    const actual = new Map(engine.state);

    const first = actual.keys().next().value;

    actual.set(first, {
        ...actual.get(first),
        enable_dns_support: false
    });

    console.log("Drift:", engine.detectDrift(actual));

    try {
        registry.resolve("network", "= 9.0.0");
    } catch (error) {
        console.log("Expected error:", error.message);
    }
}

main().catch(error => {
    console.error("Execution failed:", error.message);
    process.exitCode = 1;
});
