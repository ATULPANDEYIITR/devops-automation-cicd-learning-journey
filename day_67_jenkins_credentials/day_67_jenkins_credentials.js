"use strict";

/*
 * Jenkins Credentials Management
 *
 * Event-driven credential lifecycle and pipeline policy engine.
 * Requires Node.js 18 or later.
 *
 * All secrets in this demonstration are simulated.
 * Secret values are never included in audit events.
 */

const crypto = require("node:crypto");
const { EventEmitter } = require("node:events");

const CredentialType = Object.freeze({
    SECRET_TEXT: "secret_text",
    USERNAME_PASSWORD: "username_password",
    SSH_PRIVATE_KEY: "ssh_private_key",
    SECRET_FILE: "secret_file",
    CERTIFICATE: "certificate"
});

const CredentialScope = Object.freeze({
    GLOBAL: "global",
    SYSTEM: "system"
});

const Status = Object.freeze({
    ACTIVE: "active",
    EXPIRED: "expired",
    REVOKED: "revoked"
});

class CredentialError extends Error {}
class AccessDeniedError extends CredentialError {}
class ValidationError extends CredentialError {}
class NotFoundError extends CredentialError {}

function validateSecret(type, value) {
    if (type === CredentialType.USERNAME_PASSWORD) {
        if (
            typeof value !== "object" ||
            value === null ||
            typeof value.username !== "string" ||
            !value.username ||
            typeof value.password !== "string" ||
            !value.password
        ) {
            throw new ValidationError(
                "Valid username and password are required"
            );
        }
        return;
    }

    if (
        ![
            CredentialType.SECRET_TEXT,
            CredentialType.SSH_PRIVATE_KEY,
            CredentialType.SECRET_FILE,
            CredentialType.CERTIFICATE
        ].includes(type)
    ) {
        throw new ValidationError("Unsupported credential type");
    }

    if (typeof value !== "string" || value.length === 0) {
        throw new ValidationError("Secret must be a non-empty string");
    }
}

class CredentialRecord {
    constructor({
        id,
        description,
        type,
        scope,
        owner,
        expiresAt = null
    }) {
        this.id = id;
        this.description = description;
        this.type = type;
        this.scope = scope;
        this.owner = owner;
        this.createdAt = new Date();
        this.expiresAt = expiresAt;
        this.status = Status.ACTIVE;
        this.version = 1;
    }

    isValid() {
        return (
            this.status === Status.ACTIVE &&
            (
                this.expiresAt === null ||
                new Date() < this.expiresAt
            )
        );
    }

    metadata() {
        return Object.freeze({
            id: this.id,
            description: this.description,
            type: this.type,
            scope: this.scope,
            owner: this.owner,
            status: this.isValid() ? this.status : Status.EXPIRED,
            version: this.version,
            createdAt: this.createdAt.toISOString()
        });
    }
}

class InMemorySecretProvider {
    #values = new Map();

    set(id, value) {
        this.#values.set(id, structuredClone(value));
    }

    get(id) {
        if (!this.#values.has(id)) {
            throw new NotFoundError("Secret material not found");
        }

        return structuredClone(this.#values.get(id));
    }

    delete(id) {
        this.#values.delete(id);
    }

    fingerprint(id) {
        const value = JSON.stringify(this.get(id));

        return crypto
            .createHash("sha256")
            .update(value)
            .digest("hex")
            .slice(0, 16);
    }
}

class AuditLogger {
    #events = [];

    record(action, id, actor, outcome, details = "") {
        this.#events.push(Object.freeze({
            timestamp: new Date().toISOString(),
            action,
            credentialId: id,
            actor,
            outcome,
            details
        }));
    }

    getEvents() {
        return this.#events.map(event => ({ ...event }));
    }

    countByAction() {
        const result = new Map();

        for (const event of this.#events) {
            result.set(
                event.action,
                (result.get(event.action) || 0) + 1
            );
        }

        return Object.fromEntries(result);
    }
}

class CredentialStore extends EventEmitter {
    #records = new Map();
    #provider = new InMemorySecretProvider();
    #audit = new AuditLogger();

    static ID_PATTERN = /^[a-zA-Z0-9][a-zA-Z0-9_.-]{2,63}$/;

    add({
        id,
        description,
        type,
        scope,
        owner,
        value,
        expiresAt = null
    }) {
        if (!CredentialStore.ID_PATTERN.test(id)) {
            throw new ValidationError("Invalid credential ID");
        }

        if (this.#records.has(id)) {
            throw new ValidationError("Credential already exists");
        }

        if (!description?.trim() || !owner?.trim()) {
            throw new ValidationError("Description and owner are required");
        }

        if (!Object.values(CredentialType).includes(type)) {
            throw new ValidationError("Invalid credential type");
        }

        if (!Object.values(CredentialScope).includes(scope)) {
            throw new ValidationError("Invalid credential scope");
        }

        if (
            expiresAt !== null &&
            (
                !(expiresAt instanceof Date) ||
                Number.isNaN(expiresAt.getTime()) ||
                expiresAt <= new Date()
            )
        ) {
            throw new ValidationError("Invalid expiration date");
        }

        validateSecret(type, value);

        const record = new CredentialRecord({
            id,
            description,
            type,
            scope,
            owner,
            expiresAt
        });

        this.#provider.set(id, value);
        this.#records.set(id, record);

        this.#audit.record("CREATE", id, owner, "SUCCESS");

        this.emit("credential.created", record.metadata());

        return record.metadata();
    }

    get(id) {
        const record = this.#records.get(id);

        if (!record) {
            throw new NotFoundError(`Credential ${id} not found`);
        }

        return record;
    }

    list() {
        return [...this.#records.values()].map(
            record => record.metadata()
        );
    }

    async withCredential({
        id,
        pipeline,
        actor,
        requiredType = null,
        allowSystem = false
    }, callback) {
        if (typeof callback !== "function") {
            throw new ValidationError("Callback is required");
        }

        const record = this.get(id);

        if (!record.isValid()) {
            this.#audit.record(
                "BIND",
                id,
                actor,
                "DENIED",
                "Inactive credential"
            );

            throw new AccessDeniedError("Credential is inactive");
        }

        if (
            record.scope === CredentialScope.SYSTEM &&
            !allowSystem
        ) {
            this.#audit.record(
                "BIND",
                id,
                actor,
                "DENIED",
                "System scope restriction"
            );

            throw new AccessDeniedError("System credential restricted");
        }

        if (requiredType && record.type !== requiredType) {
            throw new AccessDeniedError("Credential type mismatch");
        }

        if (!pipeline?.trim() || !actor?.trim()) {
            throw new ValidationError("Pipeline and actor are required");
        }

        const secret = this.#provider.get(id);

        this.#audit.record(
            "BIND",
            id,
            actor,
            "SUCCESS",
            `Pipeline: ${pipeline}`
        );

        try {
            return await callback(secret);
        } finally {
            // The local variable is released, but JavaScript does not
            // guarantee memory zeroization.
        }
    }

    rotate(id, newValue, actor) {
        const record = this.get(id);

        if (record.status === Status.REVOKED) {
            throw new AccessDeniedError(
                "Revoked credentials cannot be rotated"
            );
        }

        validateSecret(record.type, newValue);

        this.#provider.set(id, newValue);
        record.version += 1;
        record.status = Status.ACTIVE;
        record.expiresAt = null;

        this.#audit.record(
            "ROTATE",
            id,
            actor,
            "SUCCESS",
            `Version ${record.version}`
        );

        this.emit("credential.rotated", record.metadata());

        return record.metadata();
    }

    revoke(id, actor) {
        const record = this.get(id);

        record.status = Status.REVOKED;
        this.#provider.delete(id);

        this.#audit.record("REVOKE", id, actor, "SUCCESS");

        this.emit("credential.revoked", record.metadata());
    }

    getAudit() {
        return this.#audit.getEvents();
    }

    getAuditStatistics() {
        return this.#audit.countByAction();
    }

    getFingerprint(id) {
        return this.#provider.fingerprint(id);
    }
}

class PipelinePolicy {
    constructor(store) {
        this.store = store;
    }

    evaluate({
        pipeline,
        credentialIds,
        actor
    }) {
        const failures = [];
        const uniqueIds = new Set(credentialIds);

        if (!pipeline?.trim()) {
            failures.push("Pipeline name is required");
        }

        if (!actor?.trim()) {
            failures.push("Actor is required");
        }

        if (uniqueIds.size !== credentialIds.length) {
            failures.push("Duplicate credential references");
        }

        for (const id of uniqueIds) {
            try {
                const record = this.store.get(id);

                if (!record.isValid()) {
                    failures.push(`${id}: inactive or expired`);
                }

                if (record.scope === CredentialScope.SYSTEM) {
                    failures.push(`${id}: system scope not permitted`);
                }
            } catch (error) {
                failures.push(`${id}: ${error.message}`);
            }
        }

        return Object.freeze({
            allowed: failures.length === 0,
            pipeline,
            failures
        });
    }

    scanJenkinsfile(source) {
        const rules = [
            {
                name: "Hardcoded password or token",
                pattern: /(?:password|secret|api_key|token)\s*=\s*['"][^'"]+/i
            },
            {
                name: "Private key material",
                pattern: /-----BEGIN [A-Z ]*PRIVATE KEY-----/
            },
            {
                name: "Bearer token",
                pattern: /authorization\s*:\s*bearer\s+\S+/i
            }
        ];

        return rules
            .filter(rule => rule.pattern.test(source))
            .map(rule => rule.name);
    }
}

async function demonstrate() {
    console.log("JENKINS CREDENTIALS MANAGEMENT");
    console.log("=".repeat(55));

    const store = new CredentialStore();

    store.on("credential.created", event => {
        console.log(`Created: ${event.id}`);
    });

    store.on("credential.rotated", event => {
        console.log(`Rotated: ${event.id}, version ${event.version}`);
    });

    store.on("credential.revoked", event => {
        console.log(`Revoked: ${event.id}`);
    });

    store.add({
        id: "github-deploy-token",
        description: "GitHub deployment token",
        type: CredentialType.SECRET_TEXT,
        scope: CredentialScope.GLOBAL,
        owner: "devops",
        value: "SIMULATED_GITHUB_TOKEN"
    });

    store.add({
        id: "docker-registry",
        description: "Docker registry login",
        type: CredentialType.USERNAME_PASSWORD,
        scope: CredentialScope.GLOBAL,
        owner: "platform",
        value: {
            username: "build-user",
            password: "SIMULATED_PASSWORD"
        }
    });

    store.add({
        id: "production-ssh",
        description: "Production SSH key",
        type: CredentialType.SSH_PRIVATE_KEY,
        scope: CredentialScope.SYSTEM,
        owner: "infrastructure",
        value: "SIMULATED_PRIVATE_KEY"
    });

    console.log("\nCredential metadata:");

    console.table(store.list());

    const policy = new PipelinePolicy(store);

    console.log("\nPipeline policy:");

    const decision = policy.evaluate({
        pipeline: "release-pipeline",
        credentialIds: [
            "github-deploy-token",
            "docker-registry"
        ],
        actor: "build-agent"
    });

    console.log(decision);

    console.log("\nTemporary credential binding:");

    const result = await store.withCredential({
        id: "docker-registry",
        pipeline: "release-pipeline",
        actor: "build-agent",
        requiredType: CredentialType.USERNAME_PASSWORD
    }, async credential => {
        await new Promise(resolve => setTimeout(resolve, 10));

        return `Authenticated as ${credential.username}`;
    });

    console.log(result);

    console.log("\nJenkinsfile inspection:");

    const jenkinsfile = `
        pipeline {
            stages {
                stage('Build') {
                    steps {
                        echo 'Building application'
                    }
                }
            }
        }
    `;

    console.log(policy.scanJenkinsfile(jenkinsfile));

    console.log("\nCredential rotation:");

    store.rotate(
        "github-deploy-token",
        "SIMULATED_ROTATED_TOKEN",
        "security-admin"
    );

    console.log("\nRestricted system credential:");

    try {
        await store.withCredential({
            id: "production-ssh",
            pipeline: "release-pipeline",
            actor: "build-agent"
        }, async () => "connected");
    } catch (error) {
        console.log("Denied:", error.message);
    }

    console.log("\nRevocation:");

    store.revoke("github-deploy-token", "security-admin");

    try {
        await store.withCredential({
            id: "github-deploy-token",
            pipeline: "release-pipeline",
            actor: "build-agent"
        }, async () => "connected");
    } catch (error) {
        console.log("Denied:", error.message);
    }

    console.log("\nAudit statistics:");

    console.log(store.getAuditStatistics());

    console.log("\nAudit events:");

    console.table(store.getAudit());

    console.log("\nValidation tests:");

    if (!decision.allowed) {
        throw new Error("Valid pipeline unexpectedly rejected");
    }

    if (store.get("github-deploy-token").version !== 2) {
        throw new Error("Credential rotation failed");
    }

    if (store.get("github-deploy-token").status !== Status.REVOKED) {
        throw new Error("Credential revocation failed");
    }

    console.log("All checks passed.");
}

demonstrate().catch(error => {
    console.error("Execution failed:", error.message);
    process.exitCode = 1;
});
