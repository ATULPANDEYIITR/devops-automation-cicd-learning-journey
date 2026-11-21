"use strict";

/*
 * Terraform Fundamentals: Event-Driven Infrastructure Configuration.
 *
 * Demonstrates:
 * - Provider registration and configuration
 * - Variable resolution and validation
 * - Resource registration
 * - Dependency-aware planning
 * - Event-driven provisioning
 * - State transitions
 * - Output evaluation
 * - Policy enforcement and error recovery
 *
 * Runtime: Node.js 18+
 * Execute: node terraform_fundamentals.js
 */

const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");

class TerraformError extends Error {
    constructor(message, code = "TERRAFORM_ERROR") {
        super(message);
        this.name = "TerraformError";
        this.code = code;
    }
}

class ProviderRegistry {
    constructor() {
        this.providers = new Map();
    }

    register(name, configuration) {
        if (!/^[a-z][a-z0-9_-]*$/.test(name)) {
            throw new TerraformError("Invalid provider identifier.");
        }

        if (this.providers.has(name)) {
            throw new TerraformError(
                `Provider ${name} is already registered.`
            );
        }

        const { region, version, authentication } = configuration;

        if (!region || !/^[a-z0-9-]+$/.test(region)) {
            throw new TerraformError("Invalid provider region.");
        }

        if (!/^\d+\.\d+\.\d+$/.test(version)) {
            throw new TerraformError("Invalid provider version.");
        }

        if (!["environment", "workload_identity"].includes(authentication)) {
            throw new TerraformError("Unsupported authentication method.");
        }

        this.providers.set(name, Object.freeze({
            name,
            region,
            version,
            authentication
        }));
    }

    get(name) {
        const provider = this.providers.get(name);

        if (!provider) {
            throw new TerraformError(`Provider ${name} is not configured.`);
        }

        return provider;
    }
}

class VariableSchema {
    constructor(definitions) {
        this.definitions = new Map();

        for (const definition of definitions) {
            if (this.definitions.has(definition.name)) {
                throw new TerraformError(
                    `Duplicate variable: ${definition.name}`
                );
            }

            this.definitions.set(definition.name, definition);
        }
    }

    resolve(supplied) {
        for (const key of Object.keys(supplied)) {
            if (!this.definitions.has(key)) {
                throw new TerraformError(`Unknown variable: ${key}`);
            }
        }

        const result = new Map();

        for (const [name, definition] of this.definitions) {
            const exists = Object.hasOwn(supplied, name);

            if (!exists && definition.required) {
                throw new TerraformError(
                    `Required variable ${name} is missing.`
                );
            }

            const value = exists ? supplied[name] : definition.default;

            if (typeof value !== definition.type) {
                throw new TerraformError(
                    `${name} must have type ${definition.type}.`
                );
            }

            if (definition.validate && !definition.validate(value)) {
                throw new TerraformError(
                    `Variable ${name} failed validation.`
                );
            }

            result.set(name, value);
        }

        return result;
    }

    display(values) {
        return Object.fromEntries(
            [...values].map(([name, value]) => {
                const definition = this.definitions.get(name);

                return [
                    name,
                    definition.sensitive ? "[REDACTED]" : value
                ];
            })
        );
    }
}

class ResourceDefinition {
    constructor({
        name,
        type,
        provider,
        attributes,
        dependencies = []
    }) {
        this.name = name;
        this.type = type;
        this.provider = provider;
        this.attributes = Object.freeze({ ...attributes });
        this.dependencies = [...dependencies];

        if (!/^[a-z][a-z0-9_]*$/.test(name)) {
            throw new TerraformError("Invalid resource name.");
        }

        if (!/^[a-z][a-z0-9_]*_[a-z][a-z0-9_]*$/.test(type)) {
            throw new TerraformError("Invalid resource type.");
        }

        if (dependencies.includes(this.address)) {
            throw new TerraformError("Resource cannot depend on itself.");
        }
    }

    get address() {
        return `${this.type}.${this.name}`;
    }
}

class InfrastructureState {
    constructor() {
        this.resources = new Map();
        this.revision = 0;
    }

    get(address) {
        return this.resources.get(address);
    }

    set(address, record) {
        this.resources.set(address, Object.freeze({ ...record }));
        this.revision++;
    }

    delete(address) {
        if (this.resources.delete(address)) {
            this.revision++;
        }
    }

    snapshot() {
        return {
            resources: new Map(this.resources),
            revision: this.revision
        };
    }

    restore(snapshot) {
        this.resources = new Map(snapshot.resources);
        this.revision = snapshot.revision;
    }

    serialize() {
        return {
            revision: this.revision,
            resources: Object.fromEntries(this.resources)
        };
    }
}

class InfrastructureEngine extends EventEmitter {
    constructor(providerRegistry, variableSchema, suppliedVariables) {
        super();

        this.providerRegistry = providerRegistry;
        this.variableSchema = variableSchema;
        this.variables = variableSchema.resolve(suppliedVariables);

        this.resources = new Map();
        this.state = new InfrastructureState();
        this.busy = false;
    }

    addResource(definition) {
        if (!(definition instanceof ResourceDefinition)) {
            throw new TerraformError("Invalid resource definition.");
        }

        this.providerRegistry.get(definition.provider);

        if (this.resources.has(definition.address)) {
            throw new TerraformError(
                `Duplicate resource ${definition.address}.`
            );
        }

        this.resources.set(definition.address, definition);
    }

    interpolate(value) {
        if (typeof value === "string") {
            return value.replace(
                /\$\{var\.([a-zA-Z_][a-zA-Z0-9_]*)\}/g,
                (_, variableName) => {
                    if (!this.variables.has(variableName)) {
                        throw new TerraformError(
                            `Unknown variable reference: ${variableName}`
                        );
                    }

                    return String(this.variables.get(variableName));
                }
            );
        }

        if (Array.isArray(value)) {
            return value.map(item => this.interpolate(item));
        }

        if (value && typeof value === "object") {
            return Object.fromEntries(
                Object.entries(value).map(([key, item]) => [
                    key,
                    this.interpolate(item)
                ])
            );
        }

        return value;
    }

    dependencyOrder() {
        const result = [];
        const completed = new Set();
        const active = new Set();

        const visit = address => {
            if (active.has(address)) {
                throw new TerraformError(
                    `Circular dependency detected: ${address}`
                );
            }

            if (completed.has(address)) {
                return;
            }

            const resource = this.resources.get(address);

            if (!resource) {
                throw new TerraformError(
                    `Unknown dependency: ${address}`
                );
            }

            active.add(address);

            for (const dependency of resource.dependencies) {
                visit(dependency);
            }

            active.delete(address);
            completed.add(address);
            result.push(address);
        };

        for (const address of [...this.resources.keys()].sort()) {
            visit(address);
        }

        return result;
    }

    createPlan() {
        const entries = [];

        for (const address of this.dependencyOrder()) {
            const resource = this.resources.get(address);
            const desired = this.interpolate(resource.attributes);
            const current = this.state.get(address);

            let action;

            if (!current) {
                action = "CREATE";
            } else if (
                JSON.stringify(current.attributes) ===
                JSON.stringify(desired)
            ) {
                action = "NO_CHANGE";
            } else {
                action = "UPDATE";
            }

            entries.push({
                address,
                action,
                desired,
                previous: current?.attributes ?? null
            });
        }

        for (const address of this.state.resources.keys()) {
            if (!this.resources.has(address)) {
                entries.push({
                    address,
                    action: "DESTROY",
                    desired: null,
                    previous: this.state.get(address).attributes
                });
            }
        }

        this.emit("plan:created", entries);
        return entries;
    }

    async provision(entry) {
        const resource = this.resources.get(entry.address);

        if (entry.action === "DESTROY") {
            this.state.delete(entry.address);
            this.emit("resource:destroyed", entry.address);
            return;
        }

        if (entry.action === "NO_CHANGE") {
            this.emit("resource:unchanged", entry.address);
            return;
        }

        if (!resource) {
            throw new TerraformError(
                `Resource configuration missing: ${entry.address}`
            );
        }

        const provider = this.providerRegistry.get(resource.provider);

        // Simulated asynchronous provider operation.
        await new Promise(resolve => setImmediate(resolve));

        if (entry.desired.simulateFailure === true) {
            throw new TerraformError(
                `Provisioning failed for ${entry.address}`,
                "PROVIDER_FAILURE"
            );
        }

        const attributes = { ...entry.desired };
        delete attributes.simulateFailure;

        const digest = crypto
            .createHash("sha256")
            .update(JSON.stringify({
                address: entry.address,
                attributes
            }))
            .digest("hex")
            .slice(0, 16);

        const record = {
            id: `resource-${digest}`,
            address: entry.address,
            provider: provider.name,
            region: provider.region,
            attributes
        };

        this.state.set(entry.address, record);

        this.emit("resource:provisioned", {
            address: entry.address,
            id: record.id
        });
    }

    async apply(plan) {
        if (this.busy) {
            throw new TerraformError("An apply operation is already running.");
        }

        if (!Array.isArray(plan)) {
            throw new TerraformError("Invalid execution plan.");
        }

        this.busy = true;
        const snapshot = this.state.snapshot();

        this.emit("apply:started", plan.length);

        try {
            for (const entry of plan) {
                await this.provision(entry);
            }

            this.emit("apply:completed", this.state.revision);
        } catch (error) {
            this.state.restore(snapshot);
            this.emit("apply:rolled_back", error.message);
            throw error;
        } finally {
            this.busy = false;
        }
    }

    evaluateOutputs(definitions) {
        const result = {};

        for (const [name, reference] of Object.entries(definitions)) {
            const record = this.state.get(reference.resource);

            if (!record) {
                throw new TerraformError(
                    `Output ${name} references missing resource.`
                );
            }

            if (!Object.hasOwn(record.attributes, reference.attribute)) {
                throw new TerraformError(
                    `Output attribute does not exist: ${reference.attribute}`
                );
            }

            result[name] = record.attributes[reference.attribute];
        }

        return result;
    }
}

async function main() {
    const providers = new ProviderRegistry();

    providers.register("aws", {
        region: "ap-south-1",
        version: "5.80.0",
        authentication: "environment"
    });

    const schema = new VariableSchema([
        {
            name: "environment",
            type: "string",
            default: "development",
            validate: value =>
                ["development", "staging", "production"].includes(value)
        },
        {
            name: "instance_type",
            type: "string",
            default: "t3.small",
            validate: value => /^[a-z0-9]+\.[a-z0-9]+$/.test(value)
        },
        {
            name: "instance_count",
            type: "number",
            default: 2,
            validate: value =>
                Number.isInteger(value) && value >= 1 && value <= 10
        },
        {
            name: "database_password",
            type: "string",
            required: true,
            sensitive: true,
            validate: value => value.length >= 12
        }
    ]);

    const engine = new InfrastructureEngine(
        providers,
        schema,
        {
            environment: "development",
            instance_type: "t3.small",
            instance_count: 2,
            database_password: "SecurePassword123!"
        }
    );

    // Event listeners provide observability without coupling the provider
    // implementation to reporting logic.
    engine.on("plan:created", plan => {
        console.log("\nPlan created:");

        for (const entry of plan) {
            console.log(`${entry.action.padEnd(12)} ${entry.address}`);
        }
    });

    engine.on("resource:provisioned", event => {
        console.log(`Provisioned ${event.address}: ${event.id}`);
    });

    engine.on("resource:destroyed", address => {
        console.log(`Destroyed ${address}`);
    });

    engine.on("apply:completed", revision => {
        console.log(`Apply completed. State revision: ${revision}`);
    });

    engine.on("apply:rolled_back", reason => {
        console.log(`Apply rolled back: ${reason}`);
    });

    engine.addResource(new ResourceDefinition({
        name: "network",
        type: "aws_vpc",
        provider: "aws",
        attributes: {
            cidr_block: "10.0.0.0/16",
            environment: "${var.environment}"
        }
    }));

    engine.addResource(new ResourceDefinition({
        name: "application",
        type: "aws_instance",
        provider: "aws",
        attributes: {
            instance_type: "${var.instance_type}",
            instance_count: "${var.instance_count}",
            environment: "${var.environment}"
        },
        dependencies: ["aws_vpc.network"]
    }));

    engine.addResource(new ResourceDefinition({
        name: "database",
        type: "aws_db_instance",
        provider: "aws",
        attributes: {
            engine: "postgres",
            password_configured: true,
            environment: "${var.environment}"
        },
        dependencies: ["aws_vpc.network"]
    }));

    console.log("Resolved variables:");
    console.log(schema.display(engine.variables));

    console.log("\nDependency order:");
    console.log(engine.dependencyOrder());

    const plan = engine.createPlan();

    await engine.apply(plan);

    console.log("\nOutputs:");

    console.log(engine.evaluateOutputs({
        network_cidr: {
            resource: "aws_vpc.network",
            attribute: "cidr_block"
        },
        instance_type: {
            resource: "aws_instance.application",
            attribute: "instance_type"
        }
    }));

    console.log("\nSecond plan:");
    engine.createPlan().forEach(entry => {
        console.log(`${entry.action.padEnd(12)} ${entry.address}`);
    });

    console.log("\nSerialized state:");
    console.log(JSON.stringify(engine.state.serialize(), null, 2));

    // Demonstrate failed provisioning and state rollback.
    const beforeFailure = engine.state.serialize();

    engine.addResource(new ResourceDefinition({
        name: "failed_instance",
        type: "aws_instance",
        provider: "aws",
        attributes: {
            instance_type: "t3.small",
            simulateFailure: true
        }
    }));

    try {
        await engine.apply(engine.createPlan());
    } catch (error) {
        console.log(`Expected failure: ${error.message}`);
    }

    console.log(
        "\nExisting resources preserved:",
        engine.state.resources.size ===
        Object.keys(beforeFailure.resources).length
    );

    // Invalid configuration must fail before provisioning.
    try {
        schema.resolve({
            environment: "unknown",
            instance_type: "t3.small",
            instance_count: 50,
            database_password: "short"
        });
    } catch (error) {
        console.log(`Expected validation error: ${error.message}`);
    }
}

main().catch(error => {
    console.error("Infrastructure execution failed:", error.message);
    process.exitCode = 1;
});
