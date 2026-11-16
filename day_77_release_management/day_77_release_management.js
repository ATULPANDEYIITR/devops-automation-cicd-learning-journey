"use strict";

/*
 * Release Management Engine
 * Event-driven release orchestration, semantic versioning,
 * asynchronous validation, approval governance, deployment,
 * immutable event history, and rollback.
 *
 * Runtime: Node.js 18+
 * Dependencies: Node.js standard library only.
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const EventEmitter = require("node:events");

class ReleaseError extends Error {}
class ValidationError extends ReleaseError {}
class PolicyError extends ReleaseError {}
class StateError extends ReleaseError {}

const ReleaseState = Object.freeze({
    DRAFT: "DRAFT",
    CANDIDATE: "CANDIDATE",
    APPROVED: "APPROVED",
    RELEASED: "RELEASED",
    ROLLED_BACK: "ROLLED_BACK",
    REJECTED: "REJECTED"
});

const Decision = Object.freeze({
    APPROVED: "APPROVED",
    REJECTED: "REJECTED"
});

const CheckStatus = Object.freeze({
    PASSED: "PASSED",
    FAILED: "FAILED",
    PENDING: "PENDING"
});

const Environment = Object.freeze({
    STAGING: "STAGING",
    PRODUCTION: "PRODUCTION"
});

function parseVersion(value) {
    const match = /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z.-]+))?$/.exec(value);

    if (!match) {
        throw new ValidationError(`Invalid semantic version: ${value}`);
    }

    return Object.freeze({
        major: Number(match[1]),
        minor: Number(match[2]),
        patch: Number(match[3]),
        prerelease: match[4] || null,
        text: value
    });
}

function compareVersions(left, right) {
    const a = typeof left === "string" ? parseVersion(left) : left;
    const b = typeof right === "string" ? parseVersion(right) : right;

    for (const field of ["major", "minor", "patch"]) {
        if (a[field] !== b[field]) {
            return a[field] < b[field] ? -1 : 1;
        }
    }

    if (a.prerelease === b.prerelease) return 0;
    if (a.prerelease === null) return 1;
    if (b.prerelease === null) return -1;

    return a.prerelease.localeCompare(b.prerelease);
}

function validateReleaseInput(input) {
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]{2,63}$/.test(input.id)) {
        throw new ValidationError("Invalid release ID.");
    }

    if (!input.product || !input.product.trim()) {
        throw new ValidationError("Product is required.");
    }

    parseVersion(input.version);

    if (!/^[a-fA-F0-9]{7,64}$/.test(input.commit)) {
        throw new ValidationError("Invalid source commit.");
    }

    if (!Buffer.isBuffer(input.artifact) || input.artifact.length === 0) {
        throw new ValidationError("A non-empty build artifact is required.");
    }

    if (typeof input.releaseNotes !== "string" || !input.releaseNotes.trim()) {
        throw new ValidationError("Release notes are required.");
    }
}

class Release {
    constructor(input) {
        validateReleaseInput(input);

        this.id = input.id;
        this.product = input.product.trim();
        this.version = parseVersion(input.version);
        this.commit = input.commit.toLowerCase();
        this.digest = crypto
            .createHash("sha256")
            .update(input.artifact)
            .digest("hex");

        this.releaseNotes = input.releaseNotes;
        this.environment = input.environment || Environment.STAGING;
        this.state = ReleaseState.DRAFT;
        this.approvals = new Map();
        this.checks = new Map();
        this.events = [];
        this.rollbackVersion = null;
    }

    log(type, actor, details = {}) {
        const event = Object.freeze({
            sequence: this.events.length + 1,
            timestamp: new Date().toISOString(),
            type,
            actor,
            details: Object.freeze({ ...details })
        });

        this.events.push(event);
        return event;
    }
}

class ReleaseGovernance {
    constructor(options = {}) {
        this.policy = Object.freeze({
            requiredApprovals: options.requiredApprovals ?? 2,
            requiredChecks: Object.freeze([
                ...(options.requiredChecks ?? [
                    "unit_tests",
                    "integration_tests",
                    "security_scan",
                    "dependency_audit"
                ])
            ]),
            allowedRoles: new Set(options.allowedRoles ?? [
                "security_lead",
                "engineering_lead",
                "qa_lead",
                "product_owner"
            ]),
            allowPrereleaseProduction:
                options.allowPrereleaseProduction ?? false
        });

        if (!Number.isInteger(this.policy.requiredApprovals) ||
            this.policy.requiredApprovals < 1) {
            throw new ValidationError("Invalid approval threshold.");
        }

        if (this.policy.requiredChecks.length === 0 ||
            new Set(this.policy.requiredChecks).size !==
                this.policy.requiredChecks.length) {
            throw new ValidationError("Required checks must be unique and non-empty.");
        }

        this.releases = new Map();
        this.published = new Map();
        this.production = new Map();
        this.events = new EventEmitter();
    }

    create(input) {
        if (this.releases.has(input.id)) {
            throw new ValidationError("Duplicate release ID.");
        }

        const release = new Release(input);
        this.releases.set(release.id, release);

        release.log("CREATED", "release_service", {
            version: release.version.text,
            digest: release.digest
        });

        this.events.emit("release:created", release);
        return release;
    }

    get(id) {
        const release = this.releases.get(id);
        if (!release) throw new ValidationError(`Unknown release: ${id}`);
        return release;
    }

    submit(id) {
        const release = this.get(id);

        if (release.state !== ReleaseState.DRAFT) {
            throw new StateError("Only draft releases can be submitted.");
        }

        const versions = this.published.get(release.product) ?? new Set();

        if (versions.has(release.version.text)) {
            throw new PolicyError("Version has already been published.");
        }

        release.state = ReleaseState.CANDIDATE;
        release.log("SUBMITTED", "release_service");
        this.events.emit("release:submitted", release);

        return release;
    }

    async executeChecks(id, checkFunctions) {
        const release = this.get(id);

        if (release.state !== ReleaseState.CANDIDATE) {
            throw new StateError("Checks require a candidate release.");
        }

        const names = this.policy.requiredChecks;

        // Each check has an isolated failure result.
        // Promise.allSettled prevents one failure from hiding other results.
        const results = await Promise.allSettled(
            names.map(async name => {
                const check = checkFunctions[name];

                if (typeof check !== "function") {
                    throw new ValidationError(`Missing check implementation: ${name}`);
                }

                return {
                    name,
                    status: await check(release)
                };
            })
        );

        results.forEach((result, index) => {
            const name = names[index];

            let status = CheckStatus.FAILED;
            let details = "Check execution failed.";

            if (result.status === "fulfilled") {
                status = result.value.status;
                details = "Check completed.";

                if (!Object.values(CheckStatus).includes(status)) {
                    status = CheckStatus.FAILED;
                    details = "Check returned an invalid status.";
                }
            } else {
                details = String(result.reason?.message ?? result.reason);
            }

            release.checks.set(name, Object.freeze({
                status,
                details
            }));

            release.log("CHECK_COMPLETED", "ci_pipeline", {
                name,
                status,
                details
            });
        });

        return this.evaluate(id);
    }

    addApproval(id, reviewer, role, decision, comment = "") {
        const release = this.get(id);

        if (release.state !== ReleaseState.CANDIDATE) {
            throw new StateError("Approvals require candidate state.");
        }

        if (!reviewer || !reviewer.trim()) {
            throw new ValidationError("Reviewer identity is required.");
        }

        if (!this.policy.allowedRoles.has(role)) {
            throw new PolicyError("Reviewer role is not eligible.");
        }

        if (!Object.values(Decision).includes(decision)) {
            throw new ValidationError("Invalid approval decision.");
        }

        if (release.approvals.has(reviewer)) {
            throw new PolicyError("Reviewer has already submitted a decision.");
        }

        const approval = Object.freeze({
            reviewer,
            role,
            decision,
            comment,
            timestamp: new Date().toISOString()
        });

        release.approvals.set(reviewer, approval);

        release.log("APPROVAL_RECORDED", reviewer, {
            role,
            decision,
            comment
        });

        this.events.emit("release:approval", { release, approval });
    }

    evaluate(id) {
        const release = this.get(id);
        const blockers = [];

        if (release.state !== ReleaseState.CANDIDATE) {
            blockers.push("Release must be a candidate.");
        }

        if (!/^[a-f0-9]{64}$/.test(release.digest)) {
            blockers.push("Artifact digest is invalid.");
        }

        if (!release.releaseNotes.trim()) {
            blockers.push("Release notes are missing.");
        }

        const approvals = [...release.approvals.values()];

        if (approvals.some(a => a.decision === Decision.REJECTED)) {
            blockers.push("A reviewer has rejected the release.");
        }

        const approved = approvals.filter(
            a => a.decision === Decision.APPROVED
        );

        if (approved.length < this.policy.requiredApprovals) {
            blockers.push("Required approval threshold not met.");
        }

        for (const name of this.policy.requiredChecks) {
            const result = release.checks.get(name);

            if (!result) {
                blockers.push(`Missing check: ${name}`);
            } else if (result.status !== CheckStatus.PASSED) {
                blockers.push(`Unsuccessful check: ${name}`);
            }
        }

        if (
            release.environment === Environment.PRODUCTION &&
            release.version.prerelease &&
            !this.policy.allowPrereleaseProduction
        ) {
            blockers.push("Prerelease production deployment is prohibited.");
        }

        return Object.freeze({
            eligible: blockers.length === 0,
            blockers: Object.freeze(blockers),
            approvalCount: approved.length,
            requiredApprovals: this.policy.requiredApprovals
        });
    }

    approveForDeployment(id) {
        const release = this.get(id);
        const result = this.evaluate(id);

        if (!result.eligible) {
            throw new PolicyError(result.blockers.join("; "));
        }

        release.state = ReleaseState.APPROVED;
        release.log("GOVERNANCE_APPROVED", "governance_service");
        this.events.emit("release:approved", release);

        return release;
    }

    deploy(id, actor) {
        const release = this.get(id);

        if (release.state !== ReleaseState.APPROVED) {
            throw new StateError("Release is not approved.");
        }

        if (release.environment !== Environment.PRODUCTION) {
            throw new PolicyError("Release target is not production.");
        }

        const current = this.production.get(release.product);

        if (current && compareVersions(release.version, current) <= 0) {
            throw new PolicyError("Production version must increase.");
        }

        this.published.set(
            release.product,
            this.published.get(release.product) ?? new Set()
        );

        this.published.get(release.product).add(release.version.text);
        this.production.set(release.product, release.version);

        release.state = ReleaseState.RELEASED;
        release.log("DEPLOYED", actor, {
            version: release.version.text,
            digest: release.digest
        });

        this.events.emit("release:deployed", release);
    }

    rollback(id, previousVersion, actor) {
        const release = this.get(id);

        if (release.state !== ReleaseState.RELEASED) {
            throw new StateError("Only deployed releases can be rolled back.");
        }

        parseVersion(previousVersion);

        const known = this.published.get(release.product);

        if (!known?.has(previousVersion)) {
            throw new PolicyError("Rollback target is not a published version.");
        }

        if (previousVersion === release.version.text) {
            throw new PolicyError("Cannot roll back to the current release.");
        }

        release.rollbackVersion = previousVersion;
        release.state = ReleaseState.ROLLED_BACK;
        this.production.set(release.product, parseVersion(previousVersion));

        release.log("ROLLED_BACK", actor, {
            restoredVersion: previousVersion
        });

        this.events.emit("release:rolled_back", release);
    }

    async exportAudit(path) {
        const records = [...this.releases.values()].map(release => ({
            id: release.id,
            product: release.product,
            version: release.version.text,
            state: release.state,
            commit: release.commit,
            digest: release.digest,
            approvals: [...release.approvals.values()],
            checks: Object.fromEntries(release.checks),
            events: release.events,
            rollbackVersion: release.rollbackVersion
        }));

        await fs.writeFile(
            path,
            JSON.stringify({
                generatedAt: new Date().toISOString(),
                releases: records
            }, null, 2),
            { encoding: "utf8", mode: 0o600 }
        );
    }
}

async function main() {
    const manager = new ReleaseGovernance({
        requiredApprovals: 2
    });

    manager.events.on("release:created", release => {
        console.log("Created:", release.id);
    });

    manager.events.on("release:deployed", release => {
        console.log("Production deployment:", release.version.text);
    });

    const release = manager.create({
        id: "REL_2026_001",
        product: "BankingPlatform",
        version: "3.2.0",
        commit: "a".repeat(40),
        artifact: Buffer.from("banking-platform-production-build"),
        releaseNotes: "Security and transaction-processing improvements.",
        environment: Environment.PRODUCTION
    });

    manager.submit(release.id);

    const checks = {
        unit_tests: async () => CheckStatus.PASSED,
        integration_tests: async () => CheckStatus.PASSED,
        security_scan: async () => CheckStatus.PASSED,
        dependency_audit: async () => CheckStatus.PASSED
    };

    const evaluation = await manager.executeChecks(release.id, checks);
    console.log("Initial evaluation:", evaluation);

    manager.addApproval(
        release.id,
        "security_reviewer",
        "security_lead",
        Decision.APPROVED,
        "Security controls verified."
    );

    manager.addApproval(
        release.id,
        "engineering_reviewer",
        "engineering_lead",
        Decision.APPROVED,
        "Release candidate validated."
    );

    console.log("Final evaluation:", manager.evaluate(release.id));

    manager.approveForDeployment(release.id);
    manager.deploy(release.id, "deployment_service");

    // A second candidate demonstrates a blocking security failure.
    const failedRelease = manager.create({
        id: "REL_2026_002",
        product: "BankingPlatform",
        version: "3.3.0",
        commit: "b".repeat(40),
        artifact: Buffer.from("banking-platform-next-build"),
        releaseNotes: "New transaction processing features.",
        environment: Environment.PRODUCTION
    });

    manager.submit(failedRelease.id);

    const failedChecks = {
        unit_tests: async () => CheckStatus.PASSED,
        integration_tests: async () => CheckStatus.PASSED,
        security_scan: async () => CheckStatus.FAILED,
        dependency_audit: async () => CheckStatus.PASSED
    };

    const failedEvaluation = await manager.executeChecks(
        failedRelease.id,
        failedChecks
    );

    console.log("Second release eligible:", failedEvaluation.eligible);
    console.log("Blocking conditions:", failedEvaluation.blockers);

    await manager.exportAudit("release-audit.json");
    console.log("Audit exported.");
}

main().catch(error => {
    console.error(`${error.constructor.name}: ${error.message}`);
    process.exitCode = 1;
});
