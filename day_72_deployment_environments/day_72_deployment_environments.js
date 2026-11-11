"use strict";

/**
 * Deployment Environment Orchestrator
 *
 * Models environment-specific deployment policies, asynchronous
 * deployment execution, promotion, approvals, health checks,
 * rollback, and event-driven audit history.
 *
 * Runtime: Node.js 18+
 * Dependencies: Node.js standard library only.
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const EventEmitter = require("node:events");

const Environment = Object.freeze({
    DEVELOPMENT: "development",
    QA: "qa",
    STAGING: "staging",
    PRODUCTION: "production"
});

const DeploymentStatus = Object.freeze({
    PENDING: "pending",
    SUCCEEDED: "succeeded",
    FAILED: "failed",
    ROLLED_BACK: "rolled_back"
});

const ENVIRONMENT_ORDER = Object.freeze([
    Environment.DEVELOPMENT,
    Environment.QA,
    Environment.STAGING,
    Environment.PRODUCTION
]);

class DeploymentError extends Error {
    constructor(message) {
        super(message);
        this.name = "DeploymentError";
    }
}

class PolicyError extends DeploymentError {
    constructor(message) {
        super(message);
        this.name = "PolicyError";
    }
}

class Artifact {
    constructor({ name, version, commitSha, content }) {
        if (!/^[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}$/.test(name)) {
            throw new TypeError("Invalid artifact name.");
        }

        if (!/^\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?$/.test(version)) {
            throw new TypeError("Invalid semantic version.");
        }

        if (!/^[a-f0-9]{7,40}$/.test(commitSha)) {
            throw new TypeError("Invalid commit SHA.");
        }

        if (!Buffer.isBuffer(content)) {
            throw new TypeError("Artifact content must be a Buffer.");
        }

        this.name = name;
        this.version = version;
        this.commitSha = commitSha;
        this.checksum = crypto
            .createHash("sha256")
            .update(content)
            .digest("hex");

        this.createdAt = new Date().toISOString();

        Object.freeze(this);
    }

    get identity() {
        return `${this.name}:${this.version}:${this.checksum}`;
    }
}

class EnvironmentPolicy {
    constructor({
        name,
        endpoint,
        replicas,
        approvalRequired,
        requiredChecks,
        allowedDeployers
    }) {
        if (!ENVIRONMENT_ORDER.includes(name)) {
            throw new PolicyError(`Unknown environment: ${name}`);
        }

        const url = new URL(endpoint);

        if (url.protocol !== "https:") {
            throw new PolicyError("Environment endpoint must use HTTPS.");
        }

        if (!Number.isInteger(replicas) || replicas < 1 || replicas > 100) {
            throw new PolicyError("Invalid replica count.");
        }

        this.name = name;
        this.endpoint = url.toString();
        this.replicas = replicas;
        this.approvalRequired = approvalRequired;
        this.requiredChecks = new Set(requiredChecks);
        this.allowedDeployers = new Set(allowedDeployers);
    }
}

class DeploymentOrchestrator extends EventEmitter {
    #policies = new Map();
    #current = new Map();
    #history = [];
    #checks = new Map();
    #nextId = 1;
    #inProgress = new Set();

    constructor(policies) {
        super();

        for (const policy of policies) {
            if (this.#policies.has(policy.name)) {
                throw new PolicyError("Duplicate environment policy.");
            }

            this.#policies.set(policy.name, policy);
        }

        if (this.#policies.size !== ENVIRONMENT_ORDER.length) {
            throw new PolicyError("All four environment policies are required.");
        }
    }

    registerChecks(artifact, checks) {
        this.#checks.set(artifact.identity, new Set(checks));
        this.emit("checks:registered", {
            artifact: artifact.identity,
            checks: [...checks]
        });
    }

    #validate({ environment, artifact, deployer, approver }) {
        const policy = this.#policies.get(environment);

        if (!policy) {
            throw new PolicyError("Environment policy not found.");
        }

        if (!policy.allowedDeployers.has(deployer)) {
            throw new PolicyError(`Deployer ${deployer} is not authorized.`);
        }

        if (
            policy.approvalRequired &&
            (!approver || approver.trim().length === 0)
        ) {
            throw new PolicyError("An authorized approval is required.");
        }

        if (approver && approver === deployer) {
            throw new PolicyError("Deployer cannot approve their own release.");
        }

        const position = ENVIRONMENT_ORDER.indexOf(environment);

        if (position > 0) {
            const previousEnvironment = ENVIRONMENT_ORDER[position - 1];
            const previous = this.#current.get(previousEnvironment);

            if (!previous) {
                throw new PolicyError(
                    `${previousEnvironment} must be deployed first.`
                );
            }

            if (previous.identity !== artifact.identity) {
                throw new PolicyError(
                    "Artifact differs from the previous environment."
                );
            }
        }

        const available = this.#checks.get(artifact.identity) ?? new Set();

        const missing = [...policy.requiredChecks].filter(
            check => !available.has(check)
        );

        if (missing.length > 0) {
            throw new PolicyError(
                `Missing checks: ${missing.join(", ")}`
            );
        }
    }

    async deploy({
        environment,
        artifact,
        deployer,
        approver = null,
        healthCheck = async () => true
    }) {
        this.#validate({
            environment,
            artifact,
            deployer,
            approver
        });

        if (this.#inProgress.has(environment)) {
            throw new DeploymentError(
                `Deployment already running in ${environment}.`
            );
        }

        this.#inProgress.add(environment);

        const previous = this.#current.get(environment) ?? null;

        const record = {
            id: this.#nextId++,
            environment,
            artifact: artifact.identity,
            status: DeploymentStatus.PENDING,
            deployer,
            approver,
            previousArtifact: previous?.identity ?? null,
            startedAt: new Date().toISOString(),
            completedAt: null,
            error: null
        };

        this.#history.push(record);
        this.emit("deployment:started", { ...record });

        try {
            // A production adapter would execute an actual deployment.
            // The health check must verify readiness, not just process startup.
            const healthy = await healthCheck({
                artifact,
                environment,
                endpoint: this.#policies.get(environment).endpoint
            });

            if (healthy !== true) {
                throw new DeploymentError("Health check failed.");
            }

            this.#current.set(environment, artifact);

            record.status = DeploymentStatus.SUCCEEDED;
            record.completedAt = new Date().toISOString();

            this.emit("deployment:succeeded", { ...record });

        } catch (error) {
            record.status = DeploymentStatus.FAILED;
            record.error = error.message;
            record.completedAt = new Date().toISOString();

            this.emit("deployment:failed", { ...record });

        } finally {
            this.#inProgress.delete(environment);
        }

        return Object.freeze({ ...record });
    }

    async rollback({ environment, deployer, healthCheck = async () => true }) {
        if (this.#inProgress.has(environment)) {
            throw new DeploymentError("Cannot roll back during deployment.");
        }

        const policy = this.#policies.get(environment);

        if (!policy || !policy.allowedDeployers.has(deployer)) {
            throw new PolicyError("Unauthorized rollback.");
        }

        const current = this.#current.get(environment);

        if (!current) {
            throw new DeploymentError("Environment has no active release.");
        }

        const previousRecord = [...this.#history]
            .reverse()
            .find(record =>
                record.environment === environment &&
                record.status === DeploymentStatus.ROLLED_BACK
                    ? false
                    : record.environment === environment &&
                      record.status === DeploymentStatus.SUCCEEDED &&
                      record.artifact !== current.identity
            );

        if (!previousRecord) {
            throw new DeploymentError("No previous successful release exists.");
        }

        const previous = this.#history.find(
            record =>
                record.artifact === previousRecord.artifact &&
                record.status === DeploymentStatus.SUCCEEDED
        );

        if (!previous) {
            throw new DeploymentError("Previous release metadata is unavailable.");
        }

        const rollbackArtifact = previous.artifact;

        const record = {
            id: this.#nextId++,
            environment,
            artifact: rollbackArtifact,
            status: DeploymentStatus.PENDING,
            deployer,
            approver: null,
            previousArtifact: current.identity,
            startedAt: new Date().toISOString(),
            completedAt: null,
            error: null
        };

        this.#history.push(record);
        this.#inProgress.add(environment);

        try {
            const healthy = await healthCheck({
                environment,
                artifactIdentity: rollbackArtifact
            });

            if (healthy !== true) {
                throw new DeploymentError("Rollback health check failed.");
            }

            // The previous artifact is resolved through immutable history.
            const artifactObject = this.#artifactRegistry.get(rollbackArtifact);

            if (!artifactObject) {
                throw new DeploymentError("Rollback artifact is unavailable.");
            }

            this.#current.set(environment, artifactObject);

            record.status = DeploymentStatus.SUCCEEDED;
            record.completedAt = new Date().toISOString();

            for (const oldRecord of [...this.#history].reverse()) {
                if (
                    oldRecord.environment === environment &&
                    oldRecord.artifact === current.identity &&
                    oldRecord.status === DeploymentStatus.SUCCEEDED
                ) {
                    oldRecord.status = DeploymentStatus.ROLLED_BACK;
                    break;
                }
            }

            this.emit("deployment:rolled-back", { ...record });

        } catch (error) {
            record.status = DeploymentStatus.FAILED;
            record.error = error.message;
            record.completedAt = new Date().toISOString();

            this.emit("deployment:failed", { ...record });

        } finally {
            this.#inProgress.delete(environment);
        }

        return Object.freeze({ ...record });
    }

    #artifactRegistry = new Map();

    registerArtifact(artifact) {
        this.#artifactRegistry.set(artifact.identity, artifact);
    }

    snapshot() {
        return {
            environments: Object.fromEntries(
                ENVIRONMENT_ORDER.map(environment => [
                    environment,
                    this.#current.get(environment)?.identity ?? null
                ])
            ),
            history: this.#history.map(record => ({ ...record }))
        };
    }

    async saveReport(filename) {
        const target = path.resolve(filename);
        const temporary = `${target}.${crypto.randomUUID()}.tmp`;

        try {
            await fs.writeFile(
                temporary,
                JSON.stringify(this.snapshot(), null, 2),
                { encoding: "utf8", flag: "wx", mode: 0o600 }
            );

            await fs.rename(temporary, target);
        } catch (error) {
            await fs.rm(temporary, { force: true }).catch(() => {});
            throw error;
        }
    }
}

function createPolicies() {
    const deployers = ["developer", "qa-bot", "release-bot", "operator"];

    return [
        new EnvironmentPolicy({
            name: Environment.DEVELOPMENT,
            endpoint: "https://dev.example.internal",
            replicas: 1,
            approvalRequired: false,
            requiredChecks: ["build", "unit_tests"],
            allowedDeployers: deployers
        }),
        new EnvironmentPolicy({
            name: Environment.QA,
            endpoint: "https://qa.example.internal",
            replicas: 2,
            approvalRequired: false,
            requiredChecks: [
                "build",
                "unit_tests",
                "integration_tests",
                "security_scan"
            ],
            allowedDeployers: deployers
        }),
        new EnvironmentPolicy({
            name: Environment.STAGING,
            endpoint: "https://staging.example.internal",
            replicas: 3,
            approvalRequired: true,
            requiredChecks: [
                "build",
                "unit_tests",
                "integration_tests",
                "security_scan",
                "load_tests"
            ],
            allowedDeployers: deployers
        }),
        new EnvironmentPolicy({
            name: Environment.PRODUCTION,
            endpoint: "https://production.example.com",
            replicas: 5,
            approvalRequired: true,
            requiredChecks: [
                "build",
                "unit_tests",
                "integration_tests",
                "security_scan",
                "load_tests",
                "acceptance_tests"
            ],
            allowedDeployers: deployers
        })
    ];
}

async function main() {
    const orchestrator = new DeploymentOrchestrator(createPolicies());

    for (const event of [
        "deployment:started",
        "deployment:succeeded",
        "deployment:failed",
        "deployment:rolled-back"
    ]) {
        orchestrator.on(event, record => {
            console.log(`[EVENT] ${event}:`, record.id, record.environment);
        });
    }

    const artifact = new Artifact({
        name: "payment-service",
        version: "1.0.0",
        commitSha: "a".repeat(40),
        content: Buffer.from("payment service release 1.0.0")
    });

    orchestrator.registerArtifact(artifact);

    orchestrator.registerChecks(artifact, [
        "build",
        "unit_tests",
        "integration_tests",
        "security_scan",
        "load_tests",
        "acceptance_tests"
    ]);

    const environments = ENVIRONMENT_ORDER;

    for (const environment of environments) {
        const approver = [
            Environment.STAGING,
            Environment.PRODUCTION
        ].includes(environment) ? "release-manager" : null;

        const result = await orchestrator.deploy({
            environment,
            artifact,
            deployer: "release-bot",
            approver,
            healthCheck: async () => true
        });

        if (result.status !== DeploymentStatus.SUCCEEDED) {
            throw new DeploymentError(
                `Promotion stopped at ${environment}.`
            );
        }
    }

    const nextArtifact = new Artifact({
        name: "payment-service",
        version: "1.1.0",
        commitSha: "b".repeat(40),
        content: Buffer.from("payment service release 1.1.0")
    });

    orchestrator.registerArtifact(nextArtifact);

    orchestrator.registerChecks(nextArtifact, [
        "build",
        "unit_tests",
        "integration_tests",
        "security_scan",
        "load_tests",
        "acceptance_tests"
    ]);

    // Demonstrate a failed deployment without replacing the active version.
    const failed = await orchestrator.deploy({
        environment: Environment.DEVELOPMENT,
        artifact: nextArtifact,
        deployer: "developer",
        healthCheck: async () => false
    });

    console.log("Failure simulation:", failed.status);

    // Demonstrate rejection of an unapproved production release.
    try {
        await orchestrator.deploy({
            environment: Environment.PRODUCTION,
            artifact,
            deployer: "release-bot"
        });
    } catch (error) {
        console.log("Expected policy rejection:", error.message);
    }

    await orchestrator.saveReport("deployment-report.json");

    console.log(JSON.stringify(orchestrator.snapshot(), null, 2));
}

main().catch(error => {
    console.error("Orchestration failed:", error.message);
    process.exitCode = 1;
});
