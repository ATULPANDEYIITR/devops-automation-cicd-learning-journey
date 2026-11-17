"use strict";

/*
 * Pipeline Security Engine
 *
 * Event-driven implementation of:
 * 1. Secret access controls
 * 2. Permission evaluation
 * 3. Dependency integrity
 * 4. Supply-chain risk assessment
 * 5. Artifact provenance
 * 6. Pipeline policy evaluation
 * 7. Security event monitoring
 *
 * Runtime: Node.js 18+
 * Dependencies: Node.js standard library only.
 */

const crypto = require("node:crypto");
const EventEmitter = require("node:events");
const assert = require("node:assert/strict");


class SecurityError extends Error {}
class AuthorizationError extends SecurityError {}
class SecretError extends SecurityError {}
class SupplyChainError extends SecurityError {}
class PolicyError extends SecurityError {}


const PipelineState = Object.freeze({
    CREATED: "CREATED",
    VALIDATING: "VALIDATING",
    RUNNING: "RUNNING",
    BLOCKED: "BLOCKED",
    SUCCEEDED: "SUCCEEDED",
    FAILED: "FAILED"
});


const Severity = Object.freeze({
    LOW: 1,
    MEDIUM: 2,
    HIGH: 3,
    CRITICAL: 4
});


const Permissions = Object.freeze({
    CONTENT_READ: "contents:read",
    CONTENT_WRITE: "contents:write",
    ACTIONS_READ: "actions:read",
    ACTIONS_WRITE: "actions:write",
    DEPLOYMENTS_READ: "deployments:read",
    DEPLOYMENTS_WRITE: "deployments:write",
    PACKAGES_READ: "packages:read",
    PACKAGES_WRITE: "packages:write",
    IDENTITY_WRITE: "id-token:write"
});


// ============================================================
// 1. Audit Event System
// ============================================================

class SecurityEventBus extends EventEmitter {

    constructor() {
        super();
        this.setMaxListeners(100);
    }

    publish(type, payload) {

        const event = Object.freeze({
            id: crypto.randomUUID(),
            type,
            timestamp: new Date().toISOString(),
            ...payload
        });

        this.emit("security-event", event);

        return event;
    }
}


class AuditRepository {

    constructor(eventBus) {

        this.events = [];

        eventBus.on("security-event", event => {
            this.events.push(event);
        });
    }

    query({ type, actor, outcome } = {}) {

        return this.events.filter(event => {

            return (!type || event.type === type) &&
                (!actor || event.actor === actor) &&
                (!outcome || event.outcome === outcome);
        });
    }

    countFailures() {

        return this.events.filter(
            event => event.outcome === "DENIED" ||
                event.outcome === "FAILED"
        ).length;
    }
}


// ============================================================
// 2. Secret Vault
// ============================================================

class SecretVault {

    #records = new Map();

    constructor(eventBus) {
        this.eventBus = eventBus;
    }

    static validateName(name) {

        if (!/^[A-Z][A-Z0-9_]{1,63}$/.test(name)) {
            throw new SecretError("Invalid secret identifier");
        }
    }

    store(name, value, actor, expiresAt = null) {

        SecretVault.validateName(name);

        if (typeof value !== "string" ||
            value.length === 0 ||
            value.length > 16384) {

            throw new SecretError("Invalid secret value");
        }

        if (expiresAt !== null) {

            const expiration = new Date(expiresAt);

            if (Number.isNaN(expiration.getTime()) ||
                expiration.getTime() <= Date.now()) {

                throw new SecretError(
                    "Secret expiration must be a future date"
                );
            }
        }

        const previous = this.#records.get(name);

        const record = {
            name,
            value,
            version: previous ? previous.version + 1 : 1,
            enabled: true,
            expiresAt
        };

        this.#records.set(name, record);

        this.eventBus.publish("SECRET_STORED", {
            actor,
            resource: name,
            outcome: "SUCCESS",
            version: record.version
        });

        return Object.freeze({
            name,
            version: record.version
        });
    }

    retrieve(name, identity) {

        const record = this.#records.get(name);

        if (!identity.allowedSecrets.has(name)) {

            this.eventBus.publish("SECRET_ACCESS", {
                actor: identity.name,
                resource: name,
                outcome: "DENIED"
            });

            throw new AuthorizationError(
                "Secret access is not authorized"
            );
        }

        if (!record || !record.enabled) {
            throw new SecretError("Secret is unavailable");
        }

        if (record.expiresAt &&
            Date.now() >= new Date(record.expiresAt).getTime()) {

            throw new SecretError("Secret has expired");
        }

        this.eventBus.publish("SECRET_ACCESS", {
            actor: identity.name,
            resource: name,
            outcome: "SUCCESS",
            version: record.version
        });

        return record.value;
    }

    rotate(name, value, actor) {

        if (!this.#records.has(name)) {
            throw new SecretError("Cannot rotate unknown secret");
        }

        return this.store(name, value, actor);
    }

    revoke(name, actor) {

        const record = this.#records.get(name);

        if (!record) {
            throw new SecretError("Unknown secret");
        }

        record.enabled = false;

        this.eventBus.publish("SECRET_REVOKED", {
            actor,
            resource: name,
            outcome: "SUCCESS"
        });
    }

    metadata() {

        return [...this.#records.values()].map(record => ({
            name: record.name,
            version: record.version,
            enabled: record.enabled,
            expiresAt: record.expiresAt
        }));
    }

    mask(message) {

        let result = String(message);

        const values = [...this.#records.values()]
            .map(record => record.value)
            .filter(Boolean)
            .sort((a, b) => b.length - a.length);

        for (const value of values) {

            result = result.split(value).join("***REDACTED***");
        }

        return result;
    }
}


// ============================================================
// 3. Permission and Identity Evaluation
// ============================================================

class PipelineIdentity {

    constructor({
        name,
        permissions = [],
        allowedSecrets = []
    }) {

        if (!name || typeof name !== "string") {
            throw new AuthorizationError("Invalid job identity");
        }

        this.name = name;
        this.permissions = new Set(permissions);
        this.allowedSecrets = new Set(allowedSecrets);

        Object.freeze(this);
    }
}


class PermissionPolicy {

    constructor(eventBus, maximumPermissions = 5) {

        this.eventBus = eventBus;
        this.maximumPermissions = maximumPermissions;
    }

    authorize(identity, permission, resource) {

        const allowed =
            identity.permissions.has(permission);

        this.eventBus.publish("PERMISSION_CHECK", {
            actor: identity.name,
            resource,
            permission,
            outcome: allowed ? "SUCCESS" : "DENIED"
        });

        if (!allowed) {
            throw new AuthorizationError(
                `${identity.name} lacks ${permission}`
            );
        }

        return true;
    }

    validate(identity) {

        const errors = [];

        if (identity.permissions.size > this.maximumPermissions) {
            errors.push("Excessive pipeline permissions");
        }

        if (identity.allowedSecrets.size > 20) {
            errors.push("Excessive secret access");
        }

        if (
            identity.permissions.has(Permissions.CONTENT_WRITE) &&
            !identity.permissions.has(Permissions.CONTENT_READ)
        ) {
            errors.push("Content write requires content read");
        }

        return errors;
    }
}


// ============================================================
// 4. Dependency Integrity and Supply-Chain Evaluation
// ============================================================

class DependencyRegistry {

    constructor({ blockedSources = [] } = {}) {

        this.blockedSources = new Set(blockedSources);
    }

    validate(dependency) {

        const {
            name,
            version,
            expectedHash,
            actualHash,
            source,
            severity
        } = dependency;

        if (!/^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$/.test(name)) {
            throw new SupplyChainError("Invalid dependency name");
        }

        if (!/^[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}$/.test(version)) {
            throw new SupplyChainError("Invalid dependency version");
        }

        if (this.blockedSources.has(source)) {

            return {
                dependency: name,
                status: "BLOCKED",
                reason: "Unapproved dependency source"
            };
        }

        if (
            !/^[a-fA-F0-9]{64}$/.test(expectedHash) ||
            !/^[a-fA-F0-9]{64}$/.test(actualHash)
        ) {
            throw new SupplyChainError("Invalid SHA-256 digest");
        }

        const matches = crypto.timingSafeEqual(
            Buffer.from(expectedHash.toLowerCase(), "hex"),
            Buffer.from(actualHash.toLowerCase(), "hex")
        );

        if (!matches) {

            return {
                dependency: name,
                status: "UNVERIFIED",
                reason: "Digest mismatch"
            };
        }

        if (
            !Object.values(Severity).includes(severity)
        ) {
            throw new SupplyChainError("Invalid severity value");
        }

        if (severity >= Severity.HIGH) {

            return {
                dependency: name,
                status: "VULNERABLE",
                reason: "High or critical vulnerability"
            };
        }

        return {
            dependency: name,
            status: "VERIFIED",
            reason: "Integrity and severity checks passed"
        };
    }

    scan(dependencies) {

        const names = new Set();

        return dependencies.map(dependency => {

            const key = dependency.name.toLowerCase();

            if (names.has(key)) {
                throw new SupplyChainError(
                    `Duplicate dependency: ${key}`
                );
            }

            names.add(key);

            return this.validate(dependency);
        });
    }
}


// ============================================================
// 5. Artifact Provenance
// ============================================================

class ProvenanceService {

    constructor(signingKey) {

        if (!Buffer.isBuffer(signingKey) ||
            signingKey.length < 32) {

            throw new PolicyError(
                "Signing key must contain at least 32 bytes"
            );
        }

        this.signingKey = Buffer.from(signingKey);
    }

    canonicalize(artifact) {

        return JSON.stringify({
            name: artifact.name,
            digest: artifact.digest,
            sourceCommit: artifact.sourceCommit,
            builderIdentity: artifact.builderIdentity,
            dependencies: [...artifact.dependencies].sort(),
            createdAt: artifact.createdAt
        });
    }

    sign(artifact) {

        return crypto
            .createHmac("sha256", this.signingKey)
            .update(this.canonicalize(artifact))
            .digest("hex");
    }

    verify(artifact, signature) {

        if (!/^[a-fA-F0-9]{64}$/.test(signature)) {
            return false;
        }

        const expected = Buffer.from(
            this.sign(artifact),
            "hex"
        );

        const received = Buffer.from(signature, "hex");

        return crypto.timingSafeEqual(expected, received);
    }
}


// ============================================================
// 6. Action Reference and Workflow Configuration
// ============================================================

class WorkflowValidator {

    static validateAction(action) {

        if (!action.name || !action.reference) {
            throw new PolicyError("Incomplete action reference");
        }

        if (!/^[a-fA-F0-9]{40}$/.test(action.reference)) {

            throw new PolicyError(
                `Action ${action.name} must use a full commit SHA`
            );
        }

        return true;
    }

    static validateShellInput(value) {

        const dangerous = [
            /\$\{\{\s*github\.event\.issue\.title/i,
            /\$\{\{\s*github\.event\.pull_request\.title/i,
            /\$\{\{\s*github\.event\.comment\.body/i
        ];

        if (dangerous.some(pattern => pattern.test(value))) {

            throw new PolicyError(
                "Untrusted event data cannot be interpolated "
                + "directly into shell commands"
            );
        }

        return true;
    }
}


// ============================================================
// 7. Pipeline Policy Engine
// ============================================================

class PipelinePolicyEngine {

    constructor({
        eventBus,
        permissionPolicy,
        dependencyRegistry,
        provenanceService,
        policy = {}
    }) {

        this.eventBus = eventBus;
        this.permissionPolicy = permissionPolicy;
        this.dependencyRegistry = dependencyRegistry;
        this.provenanceService = provenanceService;

        this.policy = Object.freeze({
            minimumReviews: 1,
            requireVerifiedDependencies: true,
            requireProvenance: true,
            allowUntrustedSecrets: false,
            ...policy
        });
    }

    evaluate(run) {

        const errors = [];

        errors.push(
            ...this.permissionPolicy.validate(run.identity)
        );

        if (
            run.reviewerCount < this.policy.minimumReviews
        ) {
            errors.push("Insufficient reviews");
        }

        if (
            run.untrustedPullRequest &&
            !this.policy.allowUntrustedSecrets &&
            run.identity.allowedSecrets.size > 0
        ) {
            errors.push(
                "Untrusted pull request cannot access secrets"
            );
        }

        if (this.policy.requireVerifiedDependencies) {

            try {

                const results =
                    this.dependencyRegistry.scan(run.dependencies);

                for (const result of results) {

                    if (result.status !== "VERIFIED") {
                        errors.push(
                            `${result.dependency}: ${result.reason}`
                        );
                    }
                }

            } catch (error) {
                errors.push(error.message);
            }
        }

        if (this.policy.requireProvenance) {

            if (!run.artifact || !run.attestation) {

                errors.push("Missing artifact provenance");

            } else if (
                !this.provenanceService.verify(
                    run.artifact,
                    run.attestation
                )
            ) {
                errors.push("Artifact attestation is invalid");
            }
        }

        return Object.freeze({
            eligible: errors.length === 0,
            errors: Object.freeze(errors)
        });
    }
}


// ============================================================
// 8. Asynchronous Pipeline Execution
// ============================================================

class PipelineExecutor {

    constructor(engine, eventBus, permissionPolicy) {

        this.engine = engine;
        this.eventBus = eventBus;
        this.permissionPolicy = permissionPolicy;

        this.processedRuns = new Set();
    }

    async execute(run) {

        if (this.processedRuns.has(run.id)) {
            throw new PolicyError("Duplicate pipeline run");
        }

        if (run.state !== PipelineState.CREATED) {
            throw new PolicyError("Invalid initial pipeline state");
        }

        this.processedRuns.add(run.id);

        run.state = PipelineState.VALIDATING;

        this.eventBus.publish("PIPELINE_STARTED", {
            actor: run.identity.name,
            resource: run.id,
            outcome: "SUCCESS"
        });

        try {

            // Yield control to allow event-driven observers to process events.
            await Promise.resolve();

            const result = this.engine.evaluate(run);

            if (!result.eligible) {

                run.state = PipelineState.BLOCKED;
                run.errors = [...result.errors];

                this.eventBus.publish("PIPELINE_BLOCKED", {
                    actor: run.identity.name,
                    resource: run.id,
                    outcome: "FAILED",
                    errors: run.errors
                });

                return run;
            }

            run.state = PipelineState.RUNNING;

            this.permissionPolicy.authorize(
                run.identity,
                Permissions.DEPLOYMENTS_WRITE,
                run.targetBranch
            );

            // A real deployment adapter would execute the authorized
            // deployment operation here.
            await Promise.resolve();

            run.state = PipelineState.SUCCEEDED;

            this.eventBus.publish("PIPELINE_SUCCEEDED", {
                actor: run.identity.name,
                resource: run.id,
                outcome: "SUCCESS"
            });

        } catch (error) {

            run.state = PipelineState.FAILED;
            run.errors = [error.message];

            this.eventBus.publish("PIPELINE_FAILED", {
                actor: run.identity.name,
                resource: run.id,
                outcome: "FAILED",
                error: error.message
            });
        }

        return run;
    }
}


// ============================================================
// 9. Demonstration and Tests
// ============================================================

async function main() {

    const eventBus = new SecurityEventBus();
    const audit = new AuditRepository(eventBus);

    const vault = new SecretVault(eventBus);

    const permissions = new PermissionPolicy(
        eventBus,
        5
    );

    const dependencyRegistry = new DependencyRegistry({
        blockedSources: ["untrusted-mirror"]
    });

    const provenance = new ProvenanceService(
        crypto.randomBytes(32)
    );

    vault.store(
        "PRODUCTION_TOKEN",
        crypto.randomBytes(32).toString("hex"),
        "security-admin"
    );

    const identity = new PipelineIdentity({
        name: "production-deployment",
        permissions: [
            Permissions.CONTENT_READ,
            Permissions.DEPLOYMENTS_WRITE
        ],
        allowedSecrets: []
    });

    const artifact = {
        name: "application-release",
        digest: crypto
            .createHash("sha256")
            .update("application-release")
            .digest("hex"),
        sourceCommit: "a".repeat(40),
        builderIdentity: "trusted-ci-builder",
        dependencies: ["framework@1.2.0"],
        createdAt: new Date().toISOString()
    };

    const attestation = provenance.sign(artifact);

    const engine = new PipelinePolicyEngine({
        eventBus,
        permissionPolicy: permissions,
        dependencyRegistry,
        provenanceService: provenance,
        policy: {
            minimumReviews: 2,
            requireVerifiedDependencies: true,
            requireProvenance: true
        }
    });

    const executor = new PipelineExecutor(
        engine,
        eventBus,
        permissions
    );

    const dependency = {
        name: "framework",
        version: "1.2.0",
        expectedHash: crypto
            .createHash("sha256")
            .update("framework")
            .digest("hex"),
        actualHash: crypto
            .createHash("sha256")
            .update("framework")
            .digest("hex"),
        source: "approved-registry",
        severity: Severity.LOW
    };

    const run = {
        id: "RUN-2001",
        sourceBranch: "release/1.0",
        targetBranch: "production",
        identity,
        reviewerCount: 2,
        untrustedPullRequest: false,
        dependencies: [dependency],
        artifact,
        attestation,
        state: PipelineState.CREATED,
        errors: []
    };

    const result = await executor.execute(run);

    console.log("\nPIPELINE RESULT");
    console.log({
        id: result.id,
        state: result.state,
        errors: result.errors
    });

    assert.equal(result.state, PipelineState.SUCCEEDED);

    // Test 1: Secret access without authorization.
    const unauthorized = new PipelineIdentity({
        name: "untrusted-job",
        permissions: [],
        allowedSecrets: []
    });

    assert.throws(
        () => vault.retrieve(
            "PRODUCTION_TOKEN",
            unauthorized
        ),
        AuthorizationError
    );

    // Test 2: Digest mismatch.
    const compromised = {
        ...dependency,
        actualHash: crypto
            .createHash("sha256")
            .update("tampered")
            .digest("hex")
    };

    assert.equal(
        dependencyRegistry.validate(compromised).status,
        "UNVERIFIED"
    );

    // Test 3: Critical vulnerability.
    const vulnerable = {
        ...dependency,
        severity: Severity.CRITICAL
    };

    assert.equal(
        dependencyRegistry.validate(vulnerable).status,
        "VULNERABLE"
    );

    // Test 4: Untrusted pull request secret access.
    const untrustedRun = {
        ...run,
        id: "RUN-2002",
        identity: new PipelineIdentity({
            name: "external-job",
            permissions: [
                Permissions.CONTENT_READ,
                Permissions.DEPLOYMENTS_WRITE
            ],
            allowedSecrets: ["PRODUCTION_TOKEN"]
        }),
        untrustedPullRequest: true,
        state: PipelineState.CREATED
    };

    const blocked = await executor.execute(untrustedRun);

    assert.equal(blocked.state, PipelineState.BLOCKED);

    // Test 5: Tampered provenance.
    const modifiedArtifact = {
        ...artifact,
        digest: "f".repeat(64)
    };

    assert.equal(
        provenance.verify(modifiedArtifact, attestation),
        false
    );

    // Test 6: Mutable third-party action.
    assert.throws(
        () => WorkflowValidator.validateAction({
            name: "third-party/action",
            reference: "v2"
        }),
        PolicyError
    );

    // Test 7: Untrusted shell interpolation.
    assert.throws(
        () => WorkflowValidator.validateShellInput(
            "${{ github.event.issue.title }}"
        ),
        PolicyError
    );

    // Test 8: Secret masking.
    const secret = vault.retrieve(
        "PRODUCTION_TOKEN",
        new PipelineIdentity({
            name: "authorized-job",
            permissions: [],
            allowedSecrets: ["PRODUCTION_TOKEN"]
        })
    );

    assert.ok(
        !vault.mask(`Token: ${secret}`).includes(secret)
    );

    console.log("\nSECURITY TESTS: ALL PASSED");

    console.log("\nAUDIT REPORT");
    console.log({
        totalEvents: audit.events.length,
        deniedEvents: audit.countFailures(),
        secretAccessEvents: audit.query({
            type: "SECRET_ACCESS"
        }).length,
        blockedRuns: audit.query({
            type: "PIPELINE_BLOCKED"
        }).length
    });
}


main().catch(error => {

    console.error("Fatal pipeline security error:", error.message);
    process.exitCode = 1;
});
