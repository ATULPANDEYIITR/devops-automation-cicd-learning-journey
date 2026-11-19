"use strict";

/*
 * Enterprise Multi-Stage CI/CD Platform
 *
 * Node.js 18+
 * Standard library only.
 *
 * Features:
 * - Event-driven pipeline orchestration
 * - Concurrent pipeline execution
 * - Pull Request lifecycle
 * - Code review and approval evaluation
 * - Branch protection
 * - Build, test and security stages
 * - Artifact generation and hashing
 * - Environment promotion
 * - Deployment approvals
 * - Health checks and rollback
 * - Audit events
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const EventEmitter = require("node:events");


// ============================================================
// ENUMERATIONS
// ============================================================

const PRState = Object.freeze({
    DRAFT: "draft",
    OPEN: "open",
    MERGED: "merged",
    CLOSED: "closed"
});

const ReviewState = Object.freeze({
    APPROVED: "approved",
    CHANGES_REQUESTED: "changes_requested",
    COMMENTED: "commented",
    DISMISSED: "dismissed"
});

const PipelineState = Object.freeze({
    QUEUED: "queued",
    RUNNING: "running",
    SUCCESS: "success",
    FAILURE: "failure"
});

const DeploymentState = Object.freeze({
    PENDING: "pending",
    APPROVED: "approved",
    DEPLOYING: "deploying",
    SUCCESS: "success",
    FAILURE: "failure",
    ROLLED_BACK: "rolled_back"
});

const CheckState = Object.freeze({
    SUCCESS: "success",
    FAILURE: "failure",
    PENDING: "pending"
});


// ============================================================
// CUSTOM ERRORS
// ============================================================

class CICDError extends Error {}
class ValidationError extends CICDError {}
class PolicyError extends CICDError {}
class PipelineError extends CICDError {}


// ============================================================
// UTILITIES
// ============================================================

function identifier(prefix) {
    return `${prefix}-${crypto.randomUUID().slice(0, 10)}`;
}

function validateString(value, name) {
    if (
        typeof value !== "string" ||
        value.trim().length === 0 ||
        value.length > 255
    ) {
        throw new ValidationError(`Invalid ${name}`);
    }
}

function sha256(value) {
    return crypto
        .createHash("sha256")
        .update(value)
        .digest("hex");
}


// ============================================================
// REPOSITORY
// ============================================================

class Repository extends EventEmitter {
    constructor(name) {
        super();

        validateString(name, "repository name");

        this.name = name;
        this.branches = new Map();
        this.commits = new Map();
        this.pullRequests = new Map();
        this.policies = new Map();
        this.audit = [];

        this.branches.set("main", {
            name: "main",
            head: null,
            commits: [],
            protected: true
        });

        this.policies.set("main", {
            requiredReviews: 2,
            requiredChecks: [
                "build",
                "unit_tests",
                "security_scan"
            ],
            requireResolvedConversations: true,
            requireLinearHistory: true,
            allowDirectPush: false,
            allowForcePush: false,
            allowDeletion: false,
            dismissStaleApprovals: true
        });
    }

    record(actor, action, resource, details = {}) {
        const event = {
            id: identifier("event"),
            actor,
            action,
            resource,
            details,
            timestamp: new Date().toISOString()
        };

        this.audit.push(event);
        this.emit("audit", event);
    }

    createBranch(name, base = "main") {
        validateString(name, "branch name");

        if (this.branches.has(name)) {
            throw new ValidationError("Branch already exists");
        }

        const source = this.branches.get(base);

        if (!source) {
            throw new ValidationError("Base branch not found");
        }

        this.branches.set(name, {
            name,
            head: source.head,
            commits: [...source.commits],
            protected: false
        });

        this.record("system", "branch_created", name, { base });
    }

    addCommit(branchName, message, author, files) {
        const branch = this.branches.get(branchName);

        if (!branch) {
            throw new ValidationError("Unknown branch");
        }

        if (branch.protected) {
            const policy = this.policies.get(branchName);

            if (!policy.allowDirectPush) {
                throw new PolicyError("Direct push rejected");
            }
        }

        validateString(message, "commit message");
        validateString(author, "author");

        if (!Array.isArray(files) || files.length === 0) {
            throw new ValidationError("Commit must contain files");
        }

        for (const file of files) {
            if (
                typeof file !== "string" ||
                file.startsWith("/") ||
                file.split("/").includes("..")
            ) {
                throw new ValidationError("Unsafe file path");
            }
        }

        const commit = {
            id: identifier("commit"),
            message,
            author,
            files: [...new Set(files)],
            timestamp: new Date().toISOString()
        };

        this.commits.set(commit.id, commit);
        branch.commits.push(commit.id);
        branch.head = commit.id;

        this.record(author, "commit_added", branchName, {
            commitId: commit.id
        });

        return commit;
    }

    createPullRequest(source, target, author, draft = false) {
        const sourceBranch = this.branches.get(source);
        const targetBranch = this.branches.get(target);

        if (!sourceBranch || !targetBranch || source === target) {
            throw new ValidationError("Invalid PR branches");
        }

        const targetCommits = new Set(targetBranch.commits);

        const proposedCommits = sourceBranch.commits.filter(
            commit => !targetCommits.has(commit)
        );

        if (proposedCommits.length === 0) {
            throw new ValidationError("No proposed changes");
        }

        const pr = {
            id: identifier("pr"),
            source,
            target,
            author,
            state: draft ? PRState.DRAFT : PRState.OPEN,
            commits: proposedCommits,
            reviews: [],
            conversations: [],
            createdAt: new Date().toISOString()
        };

        this.pullRequests.set(pr.id, pr);

        this.record(author, "pull_request_created", pr.id, {
            source,
            target
        });

        return pr;
    }

    getOpenPR(id) {
        const pr = this.pullRequests.get(id);

        if (!pr || pr.state !== PRState.OPEN) {
            throw new PolicyError("Pull Request is not open");
        }

        return pr;
    }

    markReady(id) {
        const pr = this.pullRequests.get(id);

        if (!pr || pr.state !== PRState.DRAFT) {
            throw new PolicyError("Only draft PRs can become ready");
        }

        pr.state = PRState.OPEN;
        this.record("author", "pull_request_ready", id);
    }

    addReview(id, reviewer, state, comments = []) {
        const pr = this.getOpenPR(id);

        validateString(reviewer, "reviewer");

        if (reviewer === pr.author) {
            throw new PolicyError("Self-approval is prohibited");
        }

        if (!Object.values(ReviewState).includes(state)) {
            throw new ValidationError("Invalid review state");
        }

        const review = {
            reviewer,
            state,
            commitId: this.branches.get(pr.source).head,
            comments,
            submittedAt: new Date().toISOString()
        };

        pr.reviews.push(review);

        this.record(reviewer, "review_submitted", id, {
            state,
            commitId: review.commitId
        });

        return review;
    }

    addConversation(id, file, line, reviewer, body) {
        const pr = this.getOpenPR(id);

        if (!Number.isInteger(line) || line < 1) {
            throw new ValidationError("Invalid inline comment line");
        }

        validateString(file, "file");
        validateString(body, "comment");

        const conversation = {
            id: identifier("conversation"),
            file,
            line,
            reviewer,
            body,
            resolved: false
        };

        pr.conversations.push(conversation);
        return conversation;
    }

    resolveConversation(id, conversationId) {
        const pr = this.getOpenPR(id);

        const conversation = pr.conversations.find(
            item => item.id === conversationId
        );

        if (!conversation) {
            throw new ValidationError("Conversation not found");
        }

        conversation.resolved = true;
    }

    closePR(id) {
        const pr = this.getOpenPR(id);
        pr.state = PRState.CLOSED;
        this.record("maintainer", "pull_request_closed", id);
    }

    reopenPR(id) {
        const pr = this.pullRequests.get(id);

        if (!pr || pr.state !== PRState.CLOSED) {
            throw new PolicyError("PR cannot be reopened");
        }

        pr.state = PRState.OPEN;
        this.record("maintainer", "pull_request_reopened", id);
    }

    updateProtection(branchName, policy) {
        if (!this.branches.has(branchName)) {
            throw new ValidationError("Unknown branch");
        }

        if (
            !Number.isInteger(policy.requiredReviews) ||
            policy.requiredReviews < 0
        ) {
            throw new ValidationError("Invalid review threshold");
        }

        this.policies.set(branchName, Object.freeze({
            ...policy,
            requiredChecks: Object.freeze([
                ...policy.requiredChecks
            ])
        }));

        this.branches.get(branchName).protected = true;
    }

    evaluateMerge(id, checks) {
        const pr = this.getOpenPR(id);
        const policy = this.policies.get(pr.target);

        if (!policy) {
            return { eligible: true, reasons: [] };
        }

        const reasons = [];
        const head = this.branches.get(pr.source).head;

        const validReviews = new Map();

        for (const review of pr.reviews) {
            if (review.commitId !== head) continue;

            if (review.state === ReviewState.CHANGES_REQUESTED) {
                reasons.push(
                    `Changes requested by ${review.reviewer}`
                );
            }

            if (review.state === ReviewState.APPROVED) {
                validReviews.set(review.reviewer, review);
            }
        }

        if (validReviews.size < policy.requiredReviews) {
            reasons.push(
                `Requires ${policy.requiredReviews} approvals`
            );
        }

        if (
            policy.requireResolvedConversations &&
            pr.conversations.some(item => !item.resolved)
        ) {
            reasons.push("Unresolved conversations");
        }

        const currentChecks = new Map(
            checks
                .filter(check => check.commitId === head)
                .map(check => [check.name, check])
        );

        for (const name of policy.requiredChecks) {
            const check = currentChecks.get(name);

            if (!check || check.state !== CheckState.SUCCESS) {
                reasons.push(`Required check failed or missing: ${name}`);
            }
        }

        return {
            eligible: reasons.length === 0,
            reasons
        };
    }

    merge(id) {
        const pr = this.getOpenPR(id);
        const source = this.branches.get(pr.source);
        const target = this.branches.get(pr.target);

        target.commits.push(
            ...pr.commits.filter(commit => !target.commits.includes(commit))
        );

        target.head = source.head;
        pr.state = PRState.MERGED;

        this.record("maintainer", "pull_request_merged", id);
    }
}


// ============================================================
// PIPELINE ORCHESTRATOR
// ============================================================

class PipelineOrchestrator extends EventEmitter {
    constructor(repository, concurrency = 2) {
        super();

        if (!Number.isInteger(concurrency) || concurrency < 1) {
            throw new ValidationError("Invalid concurrency");
        }

        this.repository = repository;
        this.concurrency = concurrency;
        this.active = 0;
        this.queue = [];
        this.history = new Map();

        this.stages = [
            {
                name: "checkout",
                run: async pipeline => {
                    if (!repository.commits.has(pipeline.commitId)) {
                        throw new PipelineError("Commit unavailable");
                    }
                    return "Checkout successful";
                }
            },
            {
                name: "build",
                run: async () => "Build successful"
            },
            {
                name: "unit_tests",
                run: async () => "42 tests passed"
            },
            {
                name: "integration_tests",
                run: async () => "18 integration tests passed"
            },
            {
                name: "security_scan",
                run: async pipeline => {
                    const commit = repository.commits.get(
                        pipeline.commitId
                    );

                    const prohibited = new Set([
                        ".env",
                        "private.key",
                        "id_rsa",
                        "credentials.json"
                    ]);

                    const violations = commit.files.filter(file =>
                        prohibited.has(file.split("/").pop())
                    );

                    if (violations.length) {
                        throw new PipelineError(
                            `Sensitive files: ${violations.join(", ")}`
                        );
                    }

                    return "Security checks passed";
                }
            },
            {
                name: "package",
                run: async pipeline => {
                    pipeline.artifactHash = sha256(
                        pipeline.commitId
                    );
                    return pipeline.artifactHash;
                }
            }
        ];
    }

    enqueue(commitId) {
        if (!this.repository.commits.has(commitId)) {
            throw new ValidationError("Unknown commit");
        }

        const pipeline = {
            id: identifier("pipeline"),
            commitId,
            state: PipelineState.QUEUED,
            stages: [],
            artifactHash: null,
            startedAt: null,
            completedAt: null
        };

        this.history.set(pipeline.id, pipeline);
        this.queue.push(pipeline);

        this.emit("queued", pipeline);
        this.processQueue();

        return pipeline;
    }

    processQueue() {
        while (
            this.active < this.concurrency &&
            this.queue.length > 0
        ) {
            const pipeline = this.queue.shift();

            this.active++;

            this.run(pipeline)
                .catch(error => {
                    pipeline.state = PipelineState.FAILURE;
                    this.emit("error", error, pipeline);
                })
                .finally(() => {
                    this.active--;
                    this.processQueue();
                });
        }
    }

    async run(pipeline) {
        pipeline.state = PipelineState.RUNNING;
        pipeline.startedAt = new Date().toISOString();

        this.emit("started", pipeline);

        for (const stage of this.stages) {
            const record = {
                name: stage.name,
                state: "running",
                output: null,
                durationMs: 0
            };

            pipeline.stages.push(record);

            const start = performance.now();

            try {
                record.output = await stage.run(pipeline);
                record.state = "success";

            } catch (error) {
                record.state = "failure";
                record.output = error.message;
                pipeline.state = PipelineState.FAILURE;

            } finally {
                record.durationMs = performance.now() - start;
            }

            this.emit("stage", {
                pipelineId: pipeline.id,
                ...record
            });

            if (record.state === "failure") break;
        }

        if (pipeline.state !== PipelineState.FAILURE) {
            pipeline.state = PipelineState.SUCCESS;
        }

        pipeline.completedAt = new Date().toISOString();

        this.emit("completed", pipeline);

        return pipeline;
    }

    getChecks(commitId) {
        const checks = [];

        for (const pipeline of this.history.values()) {
            if (pipeline.commitId !== commitId) continue;

            for (const stage of pipeline.stages) {
                checks.push({
                    name: stage.name,
                    state: stage.state === "success"
                        ? CheckState.SUCCESS
                        : stage.state === "failure"
                            ? CheckState.FAILURE
                            : CheckState.PENDING,
                    commitId
                });
            }
        }

        return checks;
    }
}


// ============================================================
// DEPLOYMENT MANAGER
// ============================================================

class DeploymentManager extends EventEmitter {
    constructor() {
        super();

        this.environments = new Map([
            ["development", "0.0.0"],
            ["staging", "0.0.0"],
            ["production", "0.0.0"]
        ]);

        this.deployments = new Map();
    }

    request(pipeline, environment, version) {
        if (pipeline.state !== PipelineState.SUCCESS) {
            throw new PolicyError("Pipeline must succeed before deployment");
        }

        if (!this.environments.has(environment)) {
            throw new ValidationError("Unknown environment");
        }

        if (!/^\d+\.\d+\.\d+$/.test(version)) {
            throw new ValidationError("Invalid semantic version");
        }

        const deployment = {
            id: identifier("deployment"),
            pipelineId: pipeline.id,
            environment,
            version,
            previousVersion: this.environments.get(environment),
            state: DeploymentState.PENDING,
            approver: null
        };

        this.deployments.set(deployment.id, deployment);

        this.emit("requested", deployment);
        return deployment;
    }

    approve(id, user, role) {
        const deployment = this.deployments.get(id);

        if (!deployment || deployment.state !== DeploymentState.PENDING) {
            throw new PolicyError("Deployment is not pending");
        }

        validateString(user, "approver");

        if (
            deployment.environment === "production" &&
            !["release_manager", "platform_admin"].includes(role)
        ) {
            throw new PolicyError("Unauthorized production approval");
        }

        deployment.approver = user;
        deployment.state = DeploymentState.APPROVED;

        this.emit("approved", deployment);
    }

    async deploy(id, healthCheck) {
        const deployment = this.deployments.get(id);

        if (
            !deployment ||
            deployment.state !== DeploymentState.APPROVED
        ) {
            throw new PolicyError("Deployment is not approved");
        }

        deployment.state = DeploymentState.DEPLOYING;

        try {
            if (typeof healthCheck !== "function") {
                throw new ValidationError("Health check function required");
            }

            const healthy = await healthCheck(deployment);

            if (!healthy) {
                throw new PipelineError("Health check failed");
            }

            this.environments.set(
                deployment.environment,
                deployment.version
            );

            deployment.state = DeploymentState.SUCCESS;

        } catch (error) {
            this.environments.set(
                deployment.environment,
                deployment.previousVersion
            );

            deployment.state = DeploymentState.ROLLED_BACK;
            deployment.failureReason = error.message;
        }

        this.emit("deployment_completed", deployment);
        return deployment;
    }
}


// ============================================================
// EXECUTABLE DEMONSTRATION
// ============================================================

async function main() {
    console.log("\nENTERPRISE CI/CD PLATFORM");
    console.log("=".repeat(65));

    const repository = new Repository("enterprise-platform");

    repository.on("audit", event => {
        console.log(
            `[AUDIT] ${event.action}: ${event.resource}`
        );
    });

    repository.createBranch("feature/order-service");

    const commit = repository.addCommit(
        "feature/order-service",
        "Implement order processing",
        "developer-01",
        [
            "src/orders.js",
            "tests/orders.test.js",
            "package.json"
        ]
    );

    const pr = repository.createPullRequest(
        "feature/order-service",
        "main",
        "developer-01"
    );

    repository.addReview(
        pr.id,
        "reviewer-01",
        ReviewState.APPROVED
    );

    repository.addReview(
        pr.id,
        "reviewer-02",
        ReviewState.APPROVED
    );

    const pipelineEngine = new PipelineOrchestrator(
        repository,
        2
    );

    pipelineEngine.on("stage", stage => {
        console.log(
            `[CI] ${stage.name}: ${stage.state}`
        );
    });

    const pipeline = pipelineEngine.enqueue(commit.id);

    await new Promise((resolve, reject) => {
        pipelineEngine.on("completed", completed => {
            if (completed.id === pipeline.id) resolve();
        });

        pipelineEngine.on("error", error => reject(error));
    });

    repository.updateProtection("main", {
        requiredReviews: 2,
        requiredChecks: [
            "build",
            "unit_tests",
            "security_scan"
        ],
        requireResolvedConversations: true,
        requireLinearHistory: true,
        allowDirectPush: false,
        allowForcePush: false,
        allowDeletion: false,
        dismissStaleApprovals: true
    });

    const mergeResult = repository.evaluateMerge(
        pr.id,
        pipelineEngine.getChecks(commit.id)
    );

    console.log("\nMERGE EVALUATION");
    console.log(mergeResult);

    if (mergeResult.eligible) {
        repository.merge(pr.id);
    }

    const deployments = new DeploymentManager();

    const staging = deployments.request(
        pipeline,
        "staging",
        "1.0.0"
    );

    deployments.approve(
        staging.id,
        "release-operator",
        "release_manager"
    );

    await deployments.deploy(async () => true);

    const production = deployments.request(
        pipeline,
        "production",
        "1.0.0"
    );

    deployments.approve(
        production.id,
        "production-manager",
        "release_manager"
    );

    await deployments.deploy(async () => false);

    console.log("\nDEPLOYMENT RESULTS");

    for (const deployment of deployments.deployments.values()) {
        console.log({
            environment: deployment.environment,
            version: deployment.version,
            state: deployment.state
        });
    }

    console.log("\nENVIRONMENT VERSIONS");

    console.log(Object.fromEntries(deployments.environments));

    await fs.writeFile(
        "cicd-audit.json",
        JSON.stringify(repository.audit, null, 2),
        { encoding: "utf8", mode: 0o600 }
    );

    console.log("\nAudit events saved to cicd-audit.json");
}

main().catch(error => {
    console.error("CI/CD execution failed:", error.message);
    process.exitCode = 1;
});
