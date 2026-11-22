"use strict";

/*
 * Terraform State Management
 *
 * Event-driven state management implementation.
 *
 * Features:
 * - State snapshots and immutable revisions
 * - Local and remote backend abstractions
 * - Asynchronous distributed-lock simulation
 * - Promise-based concurrency control
 * - Optimistic concurrency checks
 * - Workspace isolation
 * - State lineage
 * - State migration
 * - State integrity verification
 * - Infrastructure drift detection
 * - Sensitive output redaction
 * - Event-driven audit records
 *
 * Runtime: Node.js 18+
 * Dependencies: None
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const os = require("node:os");
const EventEmitter = require("node:events");


// ============================================================
// ERRORS
// ============================================================

class StateError extends Error {}
class ValidationError extends StateError {}
class LockError extends StateError {}
class ConcurrencyError extends StateError {}
class IntegrityError extends StateError {}
class BackendError extends StateError {}


// ============================================================
// ENUMERATIONS
// ============================================================

const Operation = Object.freeze({
    PLAN: "PLAN",
    APPLY: "APPLY",
    REFRESH: "REFRESH",
    MIGRATE: "MIGRATE",
    IMPORT: "IMPORT"
});

const Action = Object.freeze({
    CREATE: "CREATE",
    UPDATE: "UPDATE",
    DELETE: "DELETE",
    NO_CHANGE: "NO_CHANGE"
});


// ============================================================
// UTILITY FUNCTIONS
// ============================================================

function generateId() {
    return crypto.randomUUID();
}

function now() {
    return new Date().toISOString();
}

function clone(value) {
    return structuredClone(value);
}

function checksum(value) {
    return crypto
        .createHash("sha256")
        .update(JSON.stringify(value))
        .digest("hex");
}

function validateWorkspace(name) {
    if (
        typeof name !== "string" ||
        !/^[a-zA-Z0-9_-]+$/.test(name)
    ) {
        throw new ValidationError(
            "Invalid workspace identifier."
        );
    }
}

function validateSerial(serial) {
    if (
        !Number.isSafeInteger(serial) ||
        serial < 0
    ) {
        throw new ValidationError(
            "State serial must be a non-negative safe integer."
        );
    }
}


// ============================================================
// ASYNCHRONOUS MUTEX
// ============================================================

class AsyncMutex {

    constructor() {
        this.locked = false;
        this.waiters = [];
    }

    async acquire(timeoutMs = 5000) {

        if (!Number.isFinite(timeoutMs) || timeoutMs < 0) {
            throw new ValidationError(
                "Invalid mutex timeout."
            );
        }

        if (!this.locked) {
            this.locked = true;
            return this.createRelease();
        }

        return new Promise((resolve, reject) => {

            let completed = false;

            const waiter = {
                resolve: release => {
                    if (completed) return;
                    completed = true;
                    resolve(release);
                },
                reject: error => {
                    if (completed) return;
                    completed = true;
                    reject(error);
                },
                timer: null
            };

            waiter.timer = setTimeout(() => {

                const index = this.waiters.indexOf(waiter);

                if (index !== -1) {
                    this.waiters.splice(index, 1);
                }

                waiter.reject(
                    new LockError(
                        "Timed out waiting for state lock."
                    )
                );

            }, timeoutMs);

            this.waiters.push(waiter);
        });
    }

    createRelease() {

        let released = false;

        return () => {

            if (released) {
                throw new LockError(
                    "Mutex already released."
                );
            }

            released = true;

            while (this.waiters.length > 0) {

                const next = this.waiters.shift();

                if (!next) continue;

                clearTimeout(next.timer);

                next.resolve(this.createRelease());
                return;
            }

            this.locked = false;
        };
    }
}


// ============================================================
// STATE VALIDATION
// ============================================================

function validateResource(resource) {

    if (!resource || typeof resource !== "object") {
        throw new ValidationError(
            "Resource must be an object."
        );
    }

    if (
        typeof resource.address !== "string" ||
        !resource.address.includes(".")
    ) {
        throw new ValidationError(
            "Invalid Terraform resource address."
        );
    }

    if (!resource.type || !resource.provider || !resource.id) {
        throw new ValidationError(
            "Resource type, provider and ID are required."
        );
    }

    if (
        !resource.attributes ||
        typeof resource.attributes !== "object" ||
        Array.isArray(resource.attributes)
    ) {
        throw new ValidationError(
            "Resource attributes must be an object."
        );
    }

    const sensitive = resource.sensitiveAttributes || [];

    for (const key of sensitive) {
        if (!Object.hasOwn(resource.attributes, key)) {
            throw new ValidationError(
                `Unknown sensitive attribute: ${key}`
            );
        }
    }
}

function validateState(state) {

    if (state.version !== 4) {
        throw new ValidationError(
            "Unsupported Terraform state format."
        );
    }

    validateSerial(state.serial);
    validateWorkspace(state.workspace);

    if (!state.lineage) {
        throw new ValidationError(
            "State lineage is required."
        );
    }

    if (!state.resources || typeof state.resources !== "object") {
        throw new ValidationError(
            "State resources must be an object."
        );
    }

    for (const [address, resource] of Object.entries(
        state.resources
    )) {

        validateResource(resource);

        if (address !== resource.address) {
            throw new ValidationError(
                "Resource address mismatch."
            );
        }
    }

    if (!state.outputs || typeof state.outputs !== "object") {
        throw new ValidationError(
            "State outputs must be an object."
        );
    }
}


// ============================================================
// STATE FACTORY
// ============================================================

function createState(workspace = "default") {

    validateWorkspace(workspace);

    return {
        version: 4,
        terraformVersion: "1.10.0",
        lineage: generateId(),
        serial: 0,
        workspace,
        resources: {},
        outputs: {},
        updatedAt: now()
    };
}


// ============================================================
// STATE LOCK MANAGER
// ============================================================

class StateLockManager extends EventEmitter {

    constructor() {
        super();
        this.locks = new Map();
        this.mutexes = new Map();
    }

    getMutex(workspace) {

        if (!this.mutexes.has(workspace)) {
            this.mutexes.set(
                workspace,
                new AsyncMutex()
            );
        }

        return this.mutexes.get(workspace);
    }

    async acquire(
        workspace,
        operation,
        owner,
        timeoutMs = 5000
    ) {

        validateWorkspace(workspace);

        if (!owner || !operation) {
            throw new ValidationError(
                "Lock owner and operation are required."
            );
        }

        const releaseMutex = await this
            .getMutex(workspace)
            .acquire(timeoutMs);

        const lock = {
            id: generateId(),
            workspace,
            operation,
            owner,
            hostname: os.hostname(),
            createdAt: now()
        };

        this.locks.set(workspace, lock);

        this.emit("lock:acquired", clone(lock));

        return {
            lock: clone(lock),

            release: () => {

                const active = this.locks.get(workspace);

                if (!active || active.id !== lock.id) {
                    throw new LockError(
                        "Lock ownership verification failed."
                    );
                }

                this.locks.delete(workspace);
                releaseMutex();

                this.emit(
                    "lock:released",
                    clone(lock)
                );
            }
        };
    }

    getActiveLock(workspace) {
        return this.locks.has(workspace)
            ? clone(this.locks.get(workspace))
            : null;
    }
}


// ============================================================
// BACKEND BASE CLASS
// ============================================================

class StateBackend {

    constructor() {
        this.events = new EventEmitter();
        this.lockManager = new StateLockManager();
    }

    async read() {
        throw new Error("read() not implemented.");
    }

    async write() {
        throw new Error("write() not implemented.");
    }

    async acquireLock(
        workspace,
        operation,
        owner,
        timeoutMs
    ) {
        return this.lockManager.acquire(
            workspace,
            operation,
            owner,
            timeoutMs
        );
    }
}


// ============================================================
// LOCAL BACKEND
// ============================================================

class LocalBackend extends StateBackend {

    constructor(directory) {
        super();
        this.directory = directory;
    }

    getPath(workspace) {

        validateWorkspace(workspace);

        const filename = workspace === "default"
            ? "terraform.tfstate"
            : `terraform.${workspace}.tfstate`;

        return path.join(this.directory, filename);
    }

    async read(workspace) {

        try {

            const file = await fs.readFile(
                this.getPath(workspace),
                "utf8"
            );

            const state = JSON.parse(file);

            validateState(state);

            if (state.workspace !== workspace) {
                throw new IntegrityError(
                    "Workspace mismatch."
                );
            }

            return state;

        } catch (error) {

            if (error.code === "ENOENT") {
                return createState(workspace);
            }

            if (error instanceof StateError) {
                throw error;
            }

            throw new BackendError(
                `Unable to read state: ${error.message}`
            );
        }
    }

    async write(
        workspace,
        nextState,
        expectedSerial
    ) {

        validateState(nextState);

        const current = await this.read(workspace);

        if (current.serial !== expectedSerial) {
            throw new ConcurrencyError(
                "State serial changed."
            );
        }

        if (current.lineage !== nextState.lineage) {
            throw new ConcurrencyError(
                "State lineage changed."
            );
        }

        if (nextState.serial !== expectedSerial + 1) {
            throw new ValidationError(
                "Invalid serial transition."
            );
        }

        const target = this.getPath(workspace);

        await fs.mkdir(
            this.directory,
            { recursive: true }
        );

        const temporary = `${target}.${generateId()}.tmp`;

        try {

            await fs.writeFile(
                temporary,
                JSON.stringify(nextState, null, 2),
                { flag: "wx", mode: 0o600 }
            );

            await fs.rename(temporary, target);

            this.events.emit(
                "state:written",
                {
                    workspace,
                    serial: nextState.serial
                }
            );

        } catch (error) {

            await fs.rm(
                temporary,
                { force: true }
            );

            throw new BackendError(
                `State persistence failed: ${error.message}`
            );
        }
    }
}


// ============================================================
// REMOTE BACKEND
// ============================================================

class RemoteBackend extends StateBackend {

    constructor() {
        super();

        this.states = new Map();
        this.history = new Map();
    }

    async read(workspace) {

        validateWorkspace(workspace);

        const state = this.states.get(workspace);

        return state
            ? clone(state)
            : createState(workspace);
    }

    async write(
        workspace,
        nextState,
        expectedSerial
    ) {

        validateState(nextState);

        const current = await this.read(workspace);

        if (current.serial !== expectedSerial) {
            throw new ConcurrencyError(
                "Remote state serial conflict."
            );
        }

        if (current.lineage !== nextState.lineage) {
            throw new ConcurrencyError(
                "Remote state lineage conflict."
            );
        }

        if (nextState.serial !== expectedSerial + 1) {
            throw new ValidationError(
                "Remote state serial must increment by one."
            );
        }

        this.states.set(
            workspace,
            clone(nextState)
        );

        if (!this.history.has(workspace)) {
            this.history.set(workspace, []);
        }

        this.history.get(workspace).push(
            clone(nextState)
        );

        this.events.emit(
            "state:published",
            {
                workspace,
                serial: nextState.serial
            }
        );
    }

    getHistory(workspace) {
        return clone(
            this.history.get(workspace) || []
        );
    }
}


// ============================================================
// INFRASTRUCTURE INVENTORY
// ============================================================

class InfrastructureInventory extends EventEmitter {

    constructor() {
        super();
        this.resources = new Map();
    }

    create(resource) {

        validateResource(resource);

        if (this.resources.has(resource.address)) {
            throw new StateError(
                "Infrastructure resource already exists."
            );
        }

        this.resources.set(
            resource.address,
            clone(resource)
        );

        this.emit("resource:created", resource.address);
    }

    update(address, attributes) {

        const resource = this.resources.get(address);

        if (!resource) {
            throw new StateError(
                "Infrastructure resource not found."
            );
        }

        resource.attributes = {
            ...resource.attributes,
            ...clone(attributes)
        };

        this.emit("resource:updated", address);
    }

    delete(address) {

        if (!this.resources.delete(address)) {
            throw new StateError(
                "Infrastructure resource not found."
            );
        }

        this.emit("resource:deleted", address);
    }

    get(address) {
        const resource = this.resources.get(address);
        return resource ? clone(resource) : null;
    }

    snapshot() {
        return Object.fromEntries(
            [...this.resources.entries()].map(
                ([key, value]) => [key, clone(value)]
            )
        );
    }
}


// ============================================================
// PLAN ENGINE
// ============================================================

class PlanEngine {

    static generate(state, desired) {

        validateState(state);

        const changes = [];

        const existingAddresses = new Set(
            Object.keys(state.resources)
        );

        const desiredAddresses = new Set(
            Object.keys(desired)
        );

        for (const address of desiredAddresses) {

            validateResource(desired[address]);

            if (!existingAddresses.has(address)) {

                changes.push({
                    address,
                    action: Action.CREATE,
                    after: clone(desired[address])
                });

            } else {

                const before = state.resources[address];
                const after = desired[address];

                if (
                    JSON.stringify(before.attributes) !==
                    JSON.stringify(after.attributes)
                ) {

                    changes.push({
                        address,
                        action: Action.UPDATE,
                        before: clone(before),
                        after: clone(after)
                    });
                }
            }
        }

        for (const address of existingAddresses) {

            if (!desiredAddresses.has(address)) {

                changes.push({
                    address,
                    action: Action.DELETE,
                    before: clone(state.resources[address])
                });
            }
        }

        return Object.freeze({
            workspace: state.workspace,
            lineage: state.lineage,
            baseSerial: state.serial,
            changes: Object.freeze(changes)
        });
    }
}


// ============================================================
// STATE SERVICE
// ============================================================

class TerraformStateService extends EventEmitter {

    constructor(backend, inventory) {
        super();

        this.backend = backend;
        this.inventory = inventory;
    }

    async apply(
        plan,
        owner = "deployment-runner"
    ) {

        const session = await this.backend.acquireLock(
            plan.workspace,
            Operation.APPLY,
            owner
        );

        try {

            const current = await this.backend.read(
                plan.workspace
            );

            if (
                current.serial !== plan.baseSerial ||
                current.lineage !== plan.lineage
            ) {
                throw new ConcurrencyError(
                    "Plan is stale. Re-plan before applying."
                );
            }

            const next = clone(current);

            for (const change of plan.changes) {

                switch (change.action) {

                    case Action.CREATE:

                        this.inventory.create(
                            change.after
                        );

                        next.resources[change.address] =
                            clone(change.after);

                        break;

                    case Action.UPDATE:

                        this.inventory.update(
                            change.address,
                            change.after.attributes
                        );

                        next.resources[change.address] =
                            clone(change.after);

                        break;

                    case Action.DELETE:

                        this.inventory.delete(
                            change.address
                        );

                        delete next.resources[change.address];

                        break;

                    default:
                        throw new ValidationError(
                            "Unknown plan action."
                        );
                }
            }

            if (plan.changes.length > 0) {

                next.serial = current.serial + 1;
                next.updatedAt = now();

                await this.backend.write(
                    plan.workspace,
                    next,
                    current.serial
                );
            }

            this.emit("apply:completed", {
                workspace: plan.workspace,
                serial: next.serial,
                changes: plan.changes.length
            });

            return next;

        } finally {
            session.release();
        }
    }

    async refresh(workspace) {

        const session = await this.backend.acquireLock(
            workspace,
            Operation.REFRESH,
            "refresh-service"
        );

        try {

            const current = await this.backend.read(workspace);
            const actual = this.inventory.snapshot();

            const next = clone(current);

            for (const [address, resource] of Object.entries(
                next.resources
            )) {

                const actualResource = actual[address];

                if (!actualResource) {
                    throw new StateError(
                        `Infrastructure resource missing: ${address}`
                    );
                }

                resource.id = actualResource.id;

                resource.attributes = clone(
                    actualResource.attributes
                );
            }

            next.serial++;
            next.updatedAt = now();

            await this.backend.write(
                workspace,
                next,
                current.serial
            );

            return next;

        } finally {
            session.release();
        }
    }

    async setOutput(
        workspace,
        name,
        value,
        sensitive = false
    ) {

        if (!name) {
            throw new ValidationError(
                "Output name is required."
            );
        }

        const session = await this.backend.acquireLock(
            workspace,
            Operation.APPLY,
            "output-service"
        );

        try {

            const current = await this.backend.read(workspace);
            const next = clone(current);

            next.outputs[name] = {
                value: clone(value),
                sensitive
            };

            next.serial++;
            next.updatedAt = now();

            await this.backend.write(
                workspace,
                next,
                current.serial
            );

            return next;

        } finally {
            session.release();
        }
    }

    async inspectOutputs(workspace) {

        const state = await this.backend.read(workspace);

        return Object.fromEntries(
            Object.entries(state.outputs).map(
                ([name, output]) => [
                    name,
                    output.sensitive
                        ? "[REDACTED]"
                        : output.value
                ]
            )
        );
    }

    async detectDrift(workspace) {

        const state = await this.backend.read(workspace);
        const actual = this.inventory.snapshot();

        const report = {
            missing: [],
            modified: [],
            untracked: []
        };

        for (const [address, resource] of Object.entries(
            state.resources
        )) {

            const actualResource = actual[address];

            if (!actualResource) {
                report.missing.push(address);
                continue;
            }

            if (
                resource.id !== actualResource.id ||
                JSON.stringify(resource.attributes) !==
                JSON.stringify(actualResource.attributes)
            ) {
                report.modified.push(address);
            }
        }

        for (const address of Object.keys(actual)) {
            if (!state.resources[address]) {
                report.untracked.push(address);
            }
        }

        return report;
    }

    async migrate(
        sourceBackend,
        targetBackend,
        workspace
    ) {

        const sourceSession = await sourceBackend.acquireLock(
            workspace,
            Operation.MIGRATE,
            "migration-service"
        );

        try {

            const source = await sourceBackend.read(workspace);
            const target = await targetBackend.read(workspace);

            if (target.serial !== 0 || Object.keys(
                target.resources
            ).length > 0) {
                throw new ConcurrencyError(
                    "Target backend is not empty."
                );
            }

            if (target.lineage !== source.lineage) {
                throw new ConcurrencyError(
                    "Target backend lineage differs."
                );
            }

            const migrated = clone(source);

            migrated.serial = target.serial + 1;
            migrated.updatedAt = now();

            const targetSession = await targetBackend.acquireLock(
                workspace,
                Operation.MIGRATE,
                "migration-service"
            );

            try {

                await targetBackend.write(
                    workspace,
                    migrated,
                    target.serial
                );

            } finally {
                targetSession.release();
            }

            this.emit("migration:completed", {
                workspace,
                serial: migrated.serial
            });

            return migrated;

        } finally {
            sourceSession.release();
        }
    }
}


// ============================================================
// STATE INTEGRITY
// ============================================================

function createIntegrityEnvelope(state) {

    validateState(state);

    const payload = clone(state);

    return {
        payload,
        checksum: checksum(payload)
    };
}

function verifyIntegrity(envelope) {

    const actual = checksum(envelope.payload);

    if (actual !== envelope.checksum) {
        throw new IntegrityError(
            "State integrity verification failed."
        );
    }

    validateState(envelope.payload);

    return clone(envelope.payload);
}


// ============================================================
// DEMONSTRATION
// ============================================================

async function main() {

    const backend = new RemoteBackend();
    const inventory = new InfrastructureInventory();

    const service = new TerraformStateService(
        backend,
        inventory
    );

    service.on("apply:completed", event => {
        console.log("APPLY EVENT:", event);
    });

    backend.events.on("state:published", event => {
        console.log("REMOTE STATE EVENT:", event);
    });

    const workspace = "production";

    const initialState = createState(workspace);

    // Seed a valid remote state.
    const initialEnvelope = createIntegrityEnvelope(
        initialState
    );

    const verified = verifyIntegrity(initialEnvelope);

    console.log(
        "\nINITIAL STATE LINEAGE:",
        verified.lineage
    );

    // Desired infrastructure configuration.
    const desired = {
        "aws_instance.api": {
            address: "aws_instance.api",
            type: "aws_instance",
            provider: "hashicorp/aws",
            id: "i-api-001",
            attributes: {
                instanceType: "t3.medium",
                region: "ap-south-1"
            },
            sensitiveAttributes: []
        },

        "aws_s3_bucket.assets": {
            address: "aws_s3_bucket.assets",
            type: "aws_s3_bucket",
            provider: "hashicorp/aws",
            id: "assets-bucket-001",
            attributes: {
                versioning: true,
                encryption: "AES256"
            },
            sensitiveAttributes: []
        }
    };

    // Create an initial plan.
    const plan = PlanEngine.generate(
        await backend.read(workspace),
        desired
    );

    console.log("\nPLAN");

    for (const change of plan.changes) {
        console.log(change.action, change.address);
    }

    // Apply changes.
    const applied = await service.apply(plan);

    console.log("\nAPPLIED SERIAL:", applied.serial);

    // Store outputs.
    await service.setOutput(
        workspace,
        "api_instance_id",
        "i-api-001"
    );

    await service.setOutput(
        workspace,
        "database_password",
        "example-secret",
        true
    );

    console.log("\nOUTPUTS");
    console.log(
        await service.inspectOutputs(workspace)
    );

    // Simulate external infrastructure modification.
    inventory.update(
        "aws_instance.api",
        { instanceType: "t3.large" }
    );

    console.log("\nDRIFT");
    console.log(
        await service.detectDrift(workspace)
    );

    // Refresh updates the recorded state.
    const refreshed = await service.refresh(workspace);

    console.log(
        "\nREFRESHED SERIAL:",
        refreshed.serial
    );

    // Concurrent execution test.
    console.log("\nCONCURRENCY TEST");

    const first = await backend.acquireLock(
        workspace,
        Operation.APPLY,
        "pipeline-A"
    );

    const secondPromise = backend.acquireLock(
        workspace,
        Operation.APPLY,
        "pipeline-B",
        100
    );

    try {

        await secondPromise;

        throw new Error(
            "Expected the second operation to time out."
        );

    } catch (error) {

        if (!(error instanceof LockError)) {
            throw error;
        }

        console.log("Second operation rejected:", error.message);

    } finally {
        first.release();
    }

    // Verify state history.
    console.log(
        "\nREMOTE SNAPSHOTS:",
        backend.getHistory(workspace).length
    );

    // Test integrity failure.
    const corrupted = createIntegrityEnvelope(refreshed);

    corrupted.payload.serial = 999;

    try {

        verifyIntegrity(corrupted);

    } catch (error) {

        console.log(
            "\nCORRUPTION DETECTED:",
            error.message
        );
    }

    console.log("\nWORKFLOW COMPLETED");
}


// ============================================================
// EXECUTION
// ============================================================

main().catch(error => {
    console.error("FATAL ERROR:", error.message);
    process.exitCode = 1;
});
