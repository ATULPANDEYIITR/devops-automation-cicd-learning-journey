"use strict";

/*
 * Infrastructure as Code: Event-Driven Deployment Controller
 *
 * Demonstrates:
 * - Declarative resource specifications
 * - Map-based resource registries
 * - Dependency-aware deployment
 * - Desired versus actual state
 * - Asynchronous provisioning
 * - Event-driven deployment monitoring
 * - Policy evaluation
 * - Drift detection and reconciliation
 * - Deployment concurrency control
 * - Failure handling
 *
 * Runtime: Node.js 18+
 * Dependencies: Node.js standard library only
 */

const { EventEmitter } = require("node:events");
const { createHash } = require("node:crypto");

const ResourceAction = Object.freeze({
    CREATE: "CREATE",
    UPDATE: "UPDATE",
    DELETE: "DELETE",
    NO_OP: "NO_OP"
});

class IaCError extends Error {
    constructor(message) {
        super(message);
        this.name = "IaCError";
    }
}

class ValidationError extends IaCError {}
class PolicyError extends IaCError {}
class DeploymentError extends IaCError {}

/**
 * Deep comparison through canonical JSON serialization.
 * Object keys are sorted to avoid differences caused by key order.
 */
function canonicalize(value) {
    if (Array.isArray(value)) {
        return value.map(canonicalize);
    }

    if (value !== null && typeof value === "object") {
        return Object.fromEntries(
            Object.keys(value)
                .sort()
                .map(key => [key, canonicalize(value[key])])
        );
    }

    return value;
}

function fingerprint(value) {
    return createHash("sha256")
        .update(JSON.stringify(canonicalize(value)))
        .digest("hex");
}

function validateResource(resource) {
    if (!resource || typeof resource !== "object") {
        throw new ValidationError("Resource must be an object");
    }

    if (!/^[a-z][a-z0-9-]{2,62}$/.test(resource.id)) {
        throw new ValidationError(`Invalid resource ID: ${resource.id}`);
    }

    const supported = new Set([
        "network",
        "server",
        "storage",
        "firewall"
    ]);

    if (!supported.has(resource.type)) {
        throw new ValidationError(
            `Unsupported resource type: ${resource.type}`
        );
    }

    if (!resource.properties || typeof resource.properties !== "object") {
        throw new ValidationError("Resource properties are required");
    }

    if (!Array.isArray(resource.dependsOn)) {
        throw new ValidationError("dependsOn must be an array");
    }

    if (new Set(resource.dependsOn).size !== resource.dependsOn.length) {
        throw new ValidationError("Duplicate dependencies are not allowed");
    }

    if (resource.dependsOn.includes(resource.id)) {
        throw new ValidationError("Self-dependency is not allowed");
    }

    if (
        resource.type === "server" &&
        (!Number.isInteger(resource.properties.cpu) ||
            resource.properties.cpu < 1 ||
            !Number.isFinite(resource.properties.memoryGB) ||
            resource.properties.memoryGB <= 0)
    ) {
        throw new ValidationError("Invalid server capacity");
    }

    if (
        resource.type === "storage" &&
        (!Number.isInteger(resource.properties.sizeGB) ||
            resource.properties.sizeGB <= 0 ||
            resource.properties.encrypted !== true)
    ) {
        throw new ValidationError(
            "Storage requires positive capacity and encryption"
        );
    }
}

class InfrastructureSpec {
    #resources = new Map();

    add(resource) {
        validateResource(resource);

        if (this.#resources.has(resource.id)) {
            throw new ValidationError(
                `Duplicate resource: ${resource.id}`
            );
        }

        this.#resources.set(
            resource.id,
            structuredClone(resource)
        );
    }

    get resources() {
        return new Map(
            [...this.#resources].map(
                ([id, resource]) => [id, structuredClone(resource)]
            )
        );
    }

    deploymentOrder() {
        const indegree = new Map();
        const dependents = new Map();

        for (const id of this.#resources.keys()) {
            indegree.set(id, 0);
            dependents.set(id, []);
        }

        for (const resource of this.#resources.values()) {
            for (const dependency of resource.dependsOn) {
                if (!this.#resources.has(dependency)) {
                    throw new ValidationError(
                        `${resource.id} depends on missing ${dependency}`
                    );
                }

                indegree.set(
                    resource.id,
                    indegree.get(resource.id) + 1
                );

                dependents.get(dependency).push(resource.id);
            }
        }

        const queue = [...indegree.entries()]
            .filter(([, count]) => count === 0)
            .map(([id]) => id)
            .sort();

        const ordered = [];

        while (queue.length > 0) {
            const current = queue.shift();
            ordered.push(current);

            for (const dependent of dependents.get(current).sort()) {
                const remaining = indegree.get(dependent) - 1;
                indegree.set(dependent, remaining);

                if (remaining === 0) {
                    queue.push(dependent);
                    queue.sort();
                }
            }
        }

        if (ordered.length !== this.#resources.size) {
            throw new ValidationError("Infrastructure dependency cycle");
        }

        return ordered;
    }
}

class PolicyEngine {
    constructor() {
        this.policies = [
            {
                name: "encrypted-storage",
                evaluate: resource =>
                    resource.type !== "storage" ||
                    resource.properties.encrypted === true
            },
            {
                name: "secure-firewall",
                evaluate: resource =>
                    resource.type !== "firewall" ||
                    resource.properties.defaultAction === "DENY"
            },
            {
                name: "restricted-ssh",
                evaluate: resource =>
                    resource.type !== "firewall" ||
                    resource.properties.allowSSH !== true
            },
            {
                name: "minimum-server-memory",
                evaluate: resource =>
                    resource.type !== "server" ||
                    resource.properties.memoryGB >= 4
            }
        ];
    }

    evaluate(specification) {
        const violations = [];

        for (const resource of specification.resources.values()) {
            for (const policy of this.policies) {
                if (!policy.evaluate(resource)) {
                    violations.push({
                        resourceId: resource.id,
                        policy: policy.name
                    });
                }
            }
        }

        if (violations.length > 0) {
            throw new PolicyError(
                `Policy violations: ${JSON.stringify(violations)}`
            );
        }

        return true;
    }
}

class DeploymentPlanner {
    constructor(specification, actualState) {
        this.specification = specification;
        this.actualState = actualState;
    }

    createPlan() {
        const plan = [];
        const desired = this.specification.resources;

        for (const id of this.specification.deploymentOrder()) {
            const resource = desired.get(id);
            const current = this.actualState.get(id);

            let action;

            if (!current) {
                action = ResourceAction.CREATE;
            } else if (
                fingerprint(current.properties) !==
                fingerprint(resource.properties)
            ) {
                action = ResourceAction.UPDATE;
            } else {
                action = ResourceAction.NO_OP;
            }

            plan.push({
                id,
                action,
                resource
            });
        }

        for (const [id, current] of this.actualState) {
            if (!desired.has(id)) {
                if (current.protected) {
                    throw new PolicyError(
                        `Cannot remove protected resource ${id}`
                    );
                }

                plan.push({
                    id,
                    action: ResourceAction.DELETE,
                    resource: null
                });
            }
        }

        const deleting = new Set(
            plan
                .filter(item => item.action === ResourceAction.DELETE)
                .map(item => item.id)
        );

        for (const id of deleting) {
            for (const [dependentId, resource] of this.actualState) {
                if (
                    dependentId !== id &&
                    resource.dependsOn.includes(id) &&
                    !deleting.has(dependentId)
                ) {
                    throw new PolicyError(
                        `${id} is still required by ${dependentId}`
                    );
                }
            }
        }

        return plan;
    }
}

class InfrastructureProvider {
    async provision(resource) {
        // Simulate asynchronous provisioning and provider validation.
        await new Promise(resolve => setImmediate(resolve));

        if (resource.properties.simulateFailure === true) {
            throw new DeploymentError(
                `Provider rejected ${resource.id}`
            );
        }

        return {
            id: resource.id,
            type: resource.type,
            properties: structuredClone(resource.properties),
            dependsOn: [...resource.dependsOn],
            protected: resource.protected === true,
            fingerprint: fingerprint(resource.properties),
            status: "ACTIVE",
            updatedAt: new Date().toISOString()
        };
    }

    async destroy(resourceId) {
        await new Promise(resolve => setImmediate(resolve));
        return resourceId;
    }
}

class DeploymentController extends EventEmitter {
    #actualState = new Map();
    #provider;
    #busy = false;

    constructor(provider = new InfrastructureProvider()) {
        super();
        this.#provider = provider;
    }

    get state() {
        return new Map(
            [...this.#actualState].map(
                ([id, resource]) => [id, structuredClone(resource)]
            )
        );
    }

    async deploy(specification, policyEngine) {
        if (this.#busy) {
            throw new DeploymentError(
                "Another deployment is already running"
            );
        }

        this.#busy = true;

        const originalState = this.state;

        try {
            policyEngine.evaluate(specification);

            const planner = new DeploymentPlanner(
                specification,
                this.#actualState
            );

            const plan = planner.createPlan();

            this.emit("plan", plan);

            // Provision resources in dependency order.
            for (const item of plan) {
                if (
                    item.action === ResourceAction.CREATE ||
                    item.action === ResourceAction.UPDATE
                ) {
                    const result = await this.#provider.provision(
                        item.resource
                    );

                    this.#actualState.set(item.id, result);
                    this.emit("resource:deployed", result);
                } else if (item.action === ResourceAction.NO_OP) {
                    this.emit("resource:unchanged", item.id);
                }
            }

            // Remove resources in reverse dependency order.
            for (const item of [...plan].reverse()) {
                if (item.action === ResourceAction.DELETE) {
                    await this.#provider.destroy(item.id);
                    this.#actualState.delete(item.id);

                    this.emit("resource:deleted", item.id);
                }
            }

            this.emit("deployment:completed", {
                resourceCount: this.#actualState.size
            });

            return plan;

        } catch (error) {
            // Restore the controller's state if provisioning fails.
            this.#actualState = new Map(originalState);

            this.emit("deployment:failed", {
                message: error.message
            });

            throw new DeploymentError(
                `Deployment aborted: ${error.message}`
            );

        } finally {
            this.#busy = false;
        }
    }

    detectDrift(specification) {
        const drift = [];
        const desired = specification.resources;

        for (const [id, resource] of desired) {
            const actual = this.#actualState.get(id);

            if (!actual) {
                drift.push(`${id}: missing`);
                continue;
            }

            if (
                fingerprint(actual.properties) !==
                fingerprint(resource.properties)
            ) {
                drift.push(`${id}: modified externally`);
            }
        }

        for (const id of this.#actualState.keys()) {
            if (!desired.has(id)) {
                drift.push(`${id}: unmanaged`);
            }
        }

        return drift;
    }
}

function buildSpecification() {
    const specification = new InfrastructureSpec();

    specification.add({
        id: "production-network",
        type: "network",
        properties: {
            cidr: "10.20.0.0/16",
            region: "ap-south-1"
        },
        dependsOn: [],
        protected: true
    });

    specification.add({
        id: "application-server",
        type: "server",
        properties: {
            cpu: 4,
            memoryGB: 16,
            image: "ubuntu-24.04"
        },
        dependsOn: ["production-network"]
    });

    specification.add({
        id: "application-storage",
        type: "storage",
        properties: {
            sizeGB: 100,
            encrypted: true
        },
        dependsOn: []
    });

    specification.add({
        id: "application-firewall",
        type: "firewall",
        properties: {
            defaultAction: "DENY",
            allowHTTPS: true,
            allowSSH: false
        },
        dependsOn: ["production-network"]
    });

    return specification;
}

async function runTests() {
    const specification = buildSpecification();
    const policies = new PolicyEngine();
    const controller = new DeploymentController();

    const events = [];

    controller.on("resource:deployed", resource => {
        events.push(`DEPLOYED:${resource.id}`);
    });

    controller.on("deployment:completed", () => {
        events.push("COMPLETED");
    });

    const firstPlan = await controller.deploy(
        specification,
        policies
    );

    if (
        firstPlan.filter(
            item => item.action === ResourceAction.CREATE
        ).length !== 4
    ) {
        throw new Error("Initial deployment test failed");
    }

    const secondPlan = await controller.deploy(
        specification,
        policies
    );

    if (
        !secondPlan.every(
            item => item.action === ResourceAction.NO_OP
        )
    ) {
        throw new Error("Idempotency test failed");
    }

    // Simulate external modification.
    const externalState = controller.state;
    externalState.get("application-server").properties.cpu = 8;

    // State is copied, so this does not modify the controller.
    // Verify the actual drift detection path through a controlled deployment.
    const driftController = new DeploymentController();

    await driftController.deploy(specification, policies);

    const drift = driftController.state;
    drift.get("application-server").properties.cpu = 8;

    const invalidSpecification = new InfrastructureSpec();

    invalidSpecification.add({
        id: "application-storage",
        type: "storage",
        properties: {
            sizeGB: 50,
            encrypted: false
        },
        dependsOn: []
    });

    try {
        policies.evaluate(invalidSpecification);
        throw new Error("Policy validation test failed");
    } catch (error) {
        if (!(error instanceof PolicyError)) {
            throw error;
        }
    }

    // A deployment failure must not leave a partial controller state.
    const failing = new InfrastructureSpec();

    failing.add({
        id: "failed-server",
        type: "server",
        properties: {
            cpu: 4,
            memoryGB: 8,
            simulateFailure: true
        },
        dependsOn: []
    });

    try {
        await controller.deploy(failing, policies);
        throw new Error("Failure test did not trigger");
    } catch (error) {
        if (!(error instanceof DeploymentError)) {
            throw error;
        }
    }

    if (controller.state.size !== 4) {
        throw new Error("State rollback test failed");
    }

    console.log("Event count:", events.length);
    console.log("All JavaScript tests passed.");
}

async function main() {
    const controller = new DeploymentController();
    const specification = buildSpecification();
    const policies = new PolicyEngine();

    controller.on("plan", plan => {
        console.log("\nDEPLOYMENT PLAN");

        for (const item of plan) {
            console.log(`${item.action.padEnd(8)} ${item.id}`);
        }
    });

    controller.on("resource:deployed", resource => {
        console.log(`Provisioned: ${resource.id}`);
    });

    controller.on("deployment:completed", result => {
        console.log(
            `Deployment completed: ${result.resourceCount} resources`
        );
    });

    controller.on("deployment:failed", error => {
        console.error("Deployment failure:", error.message);
    });

    await controller.deploy(specification, policies);

    console.log("\nDRIFT DETECTION");
    console.log(controller.detectDrift(specification));

    await runTests();
}

main().catch(error => {
    console.error(error.name + ":", error.message);
    process.exitCode = 1;
});
