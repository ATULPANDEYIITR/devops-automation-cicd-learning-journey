"use strict";

/**
 * Feature Flags: Deployment and Release Decoupling
 *
 * Node.js implementation featuring:
 * - Event-driven configuration management
 * - Asynchronous evaluation
 * - Targeting rules
 * - Deterministic percentage allocation
 * - Environment overrides
 * - Emergency kill switches
 * - Optimistic configuration updates
 * - Audit events
 * - Configuration snapshots
 */

const crypto = require("node:crypto");
const EventEmitter = require("node:events");

const FlagType = Object.freeze({
    BOOLEAN: "BOOLEAN",
    PERCENTAGE: "PERCENTAGE",
    TARGETED: "TARGETED"
});

const FlagStatus = Object.freeze({
    ACTIVE: "ACTIVE",
    DISABLED: "DISABLED",
    ARCHIVED: "ARCHIVED"
});

const Environment = Object.freeze({
    DEVELOPMENT: "development",
    STAGING: "staging",
    PRODUCTION: "production"
});

class FeatureFlagError extends Error {}

class FlagValidationError extends FeatureFlagError {}

class ConcurrentUpdateError extends FeatureFlagError {}

class FeatureFlag {
    constructor({
        key,
        description,
        type = FlagType.BOOLEAN,
        status = FlagStatus.ACTIVE,
        environments = [],
        percentage = 0,
        users = [],
        groups = [],
        defaultValue = false,
        owner = "platform-team",
        expiresAt = null,
        version = 1
    }) {
        this.key = key;
        this.description = description;
        this.type = type;
        this.status = status;
        this.environments = new Set(environments);
        this.percentage = percentage;
        this.users = new Set(users);
        this.groups = new Set(groups);
        this.defaultValue = defaultValue;
        this.owner = owner;
        this.expiresAt = expiresAt;
        this.version = version;

        this.validate();
    }

    validate() {
        if (
            typeof this.key !== "string" ||
            !/^[a-zA-Z][a-zA-Z0-9_-]*$/.test(this.key)
        ) {
            throw new FlagValidationError("Invalid feature flag key");
        }

        if (!Object.values(FlagType).includes(this.type)) {
            throw new FlagValidationError("Invalid flag type");
        }

        if (!Object.values(FlagStatus).includes(this.status)) {
            throw new FlagValidationError("Invalid flag status");
        }

        if (
            !Number.isFinite(this.percentage) ||
            this.percentage < 0 ||
            this.percentage > 100
        ) {
            throw new FlagValidationError(
                "Percentage must be between 0 and 100"
            );
        }

        if (typeof this.defaultValue !== "boolean") {
            throw new FlagValidationError(
                "Default value must be boolean"
            );
        }

        for (const environment of this.environments) {
            if (!Object.values(Environment).includes(environment)) {
                throw new FlagValidationError(
                    `Invalid environment: ${environment}`
                );
            }
        }

        if (this.expiresAt !== null) {
            const timestamp = Date.parse(this.expiresAt);

            if (!Number.isFinite(timestamp)) {
                throw new FlagValidationError(
                    "Invalid expiration timestamp"
                );
            }
        }
    }

    isExpired() {
        return this.expiresAt !== null &&
            Date.now() >= Date.parse(this.expiresAt);
    }

    snapshot() {
        return Object.freeze({
            key: this.key,
            description: this.description,
            type: this.type,
            status: this.status,
            environments: Object.freeze([...this.environments]),
            percentage: this.percentage,
            users: Object.freeze([...this.users]),
            groups: Object.freeze([...this.groups]),
            defaultValue: this.defaultValue,
            owner: this.owner,
            expiresAt: this.expiresAt,
            version: this.version
        });
    }
}

class FeatureFlagEngine extends EventEmitter {
    constructor() {
        super();

        this.flags = new Map();
        this.audit = [];
        this.sequence = 0;
    }

    register(configuration, actor = "system") {
        const flag = new FeatureFlag(configuration);

        if (this.flags.has(flag.key)) {
            throw new FlagValidationError(
                `Flag already exists: ${flag.key}`
            );
        }

        this.flags.set(flag.key, flag);

        this.record(flag.key, "CREATED", actor, {
            version: flag.version
        });

        return flag.snapshot();
    }

    record(key, action, actor, details = {}) {
        const event = Object.freeze({
            id: ++this.sequence,
            key,
            action,
            actor,
            timestamp: new Date().toISOString(),
            details: Object.freeze({ ...details })
        });

        this.audit.push(event);

        this.emit("audit", event);
        this.emit(`flag:${key}`, event);
    }

    percentageBucket(key, userId) {
        const digest = crypto
            .createHash("sha256")
            .update(`${key}:${userId}`)
            .digest();

        const value = digest.readUInt32BE(0);

        return value / 4294967296 * 100;
    }

    async evaluate(key, context) {
        // Yield control to support asynchronous consumers.
        await Promise.resolve();

        const flag = this.flags.get(key);

        if (!flag) {
            this.emit("evaluation:error", {
                key,
                reason: "UNKNOWN_FLAG"
            });

            return false;
        }

        if (!context || typeof context.userId !== "string" ||
            context.userId.trim() === "") {
            throw new FlagValidationError(
                "A valid userId is required"
            );
        }

        if (!Object.values(Environment).includes(context.environment)) {
            throw new FlagValidationError(
                "Invalid evaluation environment"
            );
        }

        if (flag.status !== FlagStatus.ACTIVE || flag.isExpired()) {
            return false;
        }

        if (!flag.environments.has(context.environment)) {
            return false;
        }

        const groups = new Set(context.groups || []);

        let result = false;

        // Targeting rules are evaluated before percentage rollout.
        if (flag.users.has(context.userId)) {
            result = true;
        } else if ([...groups].some(group => flag.groups.has(group))) {
            result = true;
        } else if (flag.type === FlagType.BOOLEAN) {
            result = flag.defaultValue;
        } else if (flag.type === FlagType.TARGETED) {
            result = false;
        } else if (flag.type === FlagType.PERCENTAGE) {
            result = this.percentageBucket(
                key,
                context.userId
            ) < flag.percentage;
        }

        this.emit("evaluation", {
            key,
            userId: context.userId,
            environment: context.environment,
            result
        });

        return result;
    }

    update(key, changes, expectedVersion, actor) {
        const current = this.flags.get(key);

        if (!current) {
            throw new FlagValidationError(`Unknown flag: ${key}`);
        }

        if (current.version !== expectedVersion) {
            throw new ConcurrentUpdateError(
                `Expected version ${expectedVersion}, found ${current.version}`
            );
        }

        const allowedFields = new Set([
            "type",
            "status",
            "percentage",
            "defaultValue",
            "environments",
            "users",
            "groups",
            "expiresAt",
            "description"
        ]);

        for (const field of Object.keys(changes)) {
            if (!allowedFields.has(field)) {
                throw new FlagValidationError(
                    `Field cannot be updated: ${field}`
                );
            }
        }

        const updated = new FeatureFlag({
            ...current.snapshot(),
            ...changes,
            version: current.version + 1
        });

        this.flags.set(key, updated);

        this.record(key, "UPDATED", actor, {
            version: updated.version,
            changes: Object.keys(changes)
        });

        return updated.snapshot();
    }

    async setKillSwitch(key, actor) {
        const flag = this.flags.get(key);

        if (!flag) {
            throw new FlagValidationError(`Unknown flag: ${key}`);
        }

        return this.update(
            key,
            { status: FlagStatus.DISABLED },
            flag.version,
            actor
        );
    }

    async restore(key, actor) {
        const flag = this.flags.get(key);

        if (!flag) {
            throw new FlagValidationError(`Unknown flag: ${key}`);
        }

        if (flag.isExpired()) {
            throw new FlagValidationError(
                "Expired flags cannot be restored"
            );
        }

        return this.update(
            key,
            { status: FlagStatus.ACTIVE },
            flag.version,
            actor
        );
    }

    archive(key, actor) {
        const flag = this.flags.get(key);

        if (!flag) {
            throw new FlagValidationError(`Unknown flag: ${key}`);
        }

        return this.update(
            key,
            { status: FlagStatus.ARCHIVED },
            flag.version,
            actor
        );
    }

    async evaluateBatch(keys, context) {
        const results = await Promise.all(
            keys.map(async key => ({
                key,
                enabled: await this.evaluate(key, context)
            }))
        );

        return Object.fromEntries(
            results.map(item => [item.key, item.enabled])
        );
    }

    getAuditLog(key = null) {
        return this.audit.filter(
            event => key === null || event.key === key
        );
    }

    exportConfiguration() {
        return [...this.flags.values()].map(
            flag => flag.snapshot()
        );
    }
}

async function main() {
    const engine = new FeatureFlagEngine();

    engine.on("audit", event => {
        console.log(
            `[AUDIT] ${event.action} | ${event.key} | ${event.actor}`
        );
    });

    engine.on("evaluation:error", event => {
        console.error("Evaluation error:", event);
    });

    engine.register({
        key: "new_checkout",
        description: "New checkout implementation",
        type: FlagType.PERCENTAGE,
        environments: [
            Environment.STAGING,
            Environment.PRODUCTION
        ],
        percentage: 30,
        users: ["admin_001"],
        groups: ["beta_testers"],
        owner: "payments-team"
    });

    engine.register({
        key: "new_search",
        description: "Improved search engine",
        type: FlagType.BOOLEAN,
        environments: [Environment.STAGING],
        defaultValue: true
    });

    const users = [
        {
            userId: "user_001",
            environment: Environment.PRODUCTION,
            groups: ["standard"]
        },
        {
            userId: "user_002",
            environment: Environment.PRODUCTION,
            groups: ["beta_testers"]
        },
        {
            userId: "admin_001",
            environment: Environment.PRODUCTION,
            groups: ["standard"]
        },
        {
            userId: "user_003",
            environment: Environment.STAGING,
            groups: ["standard"]
        }
    ];

    console.log("\nBATCH EVALUATION");

    const results = await Promise.all(
        users.map(async context => ({
            user: context.userId,
            result: await engine.evaluate(
                "new_checkout",
                context
            )
        }))
    );

    console.table(results);

    const context = users[0];

    const first = await engine.evaluate(
        "new_checkout",
        context
    );

    const second = await engine.evaluate(
        "new_checkout",
        context
    );

    if (first !== second) {
        throw new Error("Deterministic evaluation failed");
    }

    const before = engine.flags.get("new_checkout").version;

    engine.update(
        "new_checkout",
        { percentage: 60 },
        before,
        "release-manager"
    );

    // Reject stale concurrent configuration updates.
    try {
        engine.update(
            "new_checkout",
            { percentage: 80 },
            before,
            "another-manager"
        );
    } catch (error) {
        if (!(error instanceof ConcurrentUpdateError)) {
            throw error;
        }

        console.log("\nStale update rejected:", error.message);
    }

    // Emergency kill switch.
    await engine.setKillSwitch(
        "new_checkout",
        "incident-commander"
    );

    const afterKill = await engine.evaluate(
        "new_checkout",
        users[1]
    );

    if (afterKill !== false) {
        throw new Error("Kill switch failed");
    }

    await engine.restore(
        "new_checkout",
        "release-manager"
    );

    console.log("\nCONFIGURATION SNAPSHOT");

    console.dir(
        engine.exportConfiguration(),
        { depth: 4 }
    );

    console.log("\nAUDIT COUNT:", engine.getAuditLog().length);

    console.log("\nAll JavaScript checks passed.");
}

main().catch(error => {
    console.error("Application failure:", error.message);
    process.exitCode = 1;
});
