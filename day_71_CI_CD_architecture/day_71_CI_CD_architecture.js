"use strict";

/*
 * CI/CD Architecture and Repository Governance
 * Node.js 18+
 *
 * Event-driven pipeline orchestration, runner scheduling,
 * immutable artifacts, environment promotion, and repository policy.
 */

const crypto = require("node:crypto");
const fs = require("node:fs/promises");
const path = require("node:path");
const EventEmitter = require("node:events");
const assert = require("node:assert/strict");

class DomainError extends Error {}
class ValidationError extends DomainError {}
class AuthorizationError extends DomainError {}
class TransitionError extends DomainError {}
class PipelineError extends DomainError {}

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

const JobState = Object.freeze({
    QUEUED: "queued",
    RUNNING: "running",
    SUCCESS: "success",
    FAILURE: "failure",
    CANCELLED: "cancelled"
});

const Environment = Object.freeze({
    DEVELOPMENT: "development",
    STAGING: "staging",
    PRODUCTION: "production"
});

const MergeStrategy = Object.freeze({
    MERGE_COMMIT: "merge_commit",
    SQUASH: "squash",
    REBASE: "rebase"
});

function requireValue(value, message) {
    if (value === undefined || value === null || value === "") {
        throw new ValidationError(message);
    }
}

function sha256(value) {
    return crypto.createHash("sha256").update(value).digest("hex");
}

class Branch {
    constructor(name, commits = []) {
        requireValue(name, "Branch name is required.");
        this.name = name;
        this.commits = [...commits];
    }

    get head() {
        return this.commits.at(-1) ?? null;
    }

    append(commit) {
        if (this.commits.some(item => item.sha === commit.sha)) {
            throw new ValidationError("Duplicate commit.");
        }
        this.commits.push(Object.freeze({ ...commit }));
    }
}

class Review {
    constructor({ reviewer, state, commitSha, comments = [] }) {
        requireValue(reviewer, "Reviewer is required.");

        if (!Object.values(ReviewState).includes(state)) {
            throw new ValidationError("Invalid review state.");
        }

        this.reviewer = reviewer;
        this.state = state;
        this.commitSha = commitSha;
        this.comments = [...comments];
        this.dismissed = false;
        this.submittedAt = Date.now();
    }

    get effectiveState() {
        return this.dismissed ? ReviewState.DISMISSED : this.state;
    }
}

class PullRequest {
    constructor({
        id,
        title,
        author,
        sourceBranch,
        targetBranch,
        baseSha,
        draft = true
    }) {
        requireValue(title, "PR title is required.");

        this.id = id;
        this.title = title;
        this.author = author;
        this.sourceBranch = sourceBranch;
        this.targetBranch = targetBranch;
        this.baseSha = baseSha;
        this.state = draft ? PRState.DRAFT : PRState.OPEN;
        this.commits = [];
        this.reviews = [];
        this.comments = new Map();
        this.requestedReviewers = new Set();
        this.checks = new Map();
        this.mergedSha = null;
        this.version = 1;
    }

    open() {
        if (![PRState.DRAFT, PRState.CLOSED].includes(this.state)) {
            throw new TransitionError("PR cannot be opened.");
        }
        this.state = PRState.OPEN;
        this.version++;
    }

    addCommit(sha, dismissStaleApprovals) {
        if (this.state !== PRState.OPEN) {
            throw new TransitionError("PR is not open.");
        }

        if (this.commits.includes(sha)) {
            throw new ValidationError("Commit already exists in PR.");
        }

        this.commits.push(sha);

        if (dismissStaleApprovals) {
            for (const review of this.reviews) {
                if (review.state === ReviewState.APPROVED) {
                    review.dismissed = true;
                }
            }
        }

        this.version++;
    }

    addReview(review, reviewers) {
        if (this.state !== PRState.OPEN) {
            throw new TransitionError("PR is not open.");
        }

        const reviewer = reviewers.get(review.reviewer);

        if (
            !reviewer ||
            !reviewer.active ||
            !reviewer.roles.some(role =>
                ["reviewer", "maintainer", "security"].includes(role)
            )
        ) {
            throw new AuthorizationError("Reviewer is not eligible.");
        }

        if (review.reviewer === this.author) {
            throw new AuthorizationError("Self-approval is prohibited.");
        }

        if (!this.commits.includes(review.commitSha)) {
            throw new ValidationError("Review references an invalid commit.");
        }

        this.reviews.push(review);
        this.version++;
    }

    latestReviews() {
        const latest = new Map();

        for (const review of this.reviews) {
            const previous = latest.get(review.reviewer);

            if (!previous || review.submittedAt > previous.submittedAt) {
                latest.set(review.reviewer, review);
            }
        }

        return latest;
    }

    addComment(id, resolved = false) {
        if (this.state !== PRState.OPEN) {
            throw new TransitionError("PR is not open.");
        }
        if (this.comments.has(id)) {
            throw new ValidationError("Duplicate conversation.");
        }

        this.comments.set(id, resolved);
    }

    resolveComment(id) {
        if (!this.comments.has(id)) {
            throw new ValidationError("Conversation does not exist.");
        }
        this.comments.set(id, true);
    }

    close() {
        if (![PRState.OPEN, PRState.DRAFT].includes(this.state)) {
            throw new TransitionError("PR cannot be closed.");
        }
        this.state = PRState.CLOSED;
    }

    setCheck(name, state, commitSha) {
        if (!Object.values(JobState).includes(state)) {
            throw new ValidationError("Invalid check state.");
        }

        this.checks.set(name, { state, commitSha });
    }
}

class BranchProtection {
    constructor({
        requiredReviews = 2,
        requiredChecks = ["unit-tests", "security-scan"],
        requireConversationResolution = true,
        requireLinearHistory = false,
        allowDirectPush = false,
        allowForcePush = false,
        allowDeletion = false,
        dismissStaleApprovals = true,
        enforceAdmins = true,
        allowedMergeStrategies = [MergeStrategy.SQUASH]
    } = {}) {
        if (!Number.isInteger(requiredReviews) || requiredReviews < 0) {
            throw new ValidationError("Invalid approval requirement.");
        }

        this.requiredReviews = requiredReviews;
        this.requiredChecks = new Set(requiredChecks);
        this.requireConversationResolution = requireConversationResolution;
        this.requireLinearHistory = requireLinearHistory;
        this.allowDirectPush = allowDirectPush;
        this.allowForcePush = allowForcePush;
        this.allowDeletion = allowDeletion;
        this.dismissStaleApprovals = dismissStaleApprovals;
        this.enforceAdmins = enforceAdmins;
        this.allowedMergeStrategies = new Set(allowedMergeStrategies);
    }
}

class GovernanceService {
    constructor() {
        this.branches = new Map();
        this.reviewers = new Map();
        this.pullRequests = new Map();
        this.protections = new Map();
        this.nextId = 1;
    }

    addBranch(branch) {
        if (this.branches.has(branch.name)) {
            throw new ValidationError("Branch already exists.");
        }
        this.branches.set(branch.name, branch);
    }

    protect(name, policy) {
        if (!this.branches.has(name)) {
            throw new ValidationError("Branch does not exist.");
        }
        this.protections.set(name, policy);
    }

    registerReviewer(reviewer) {
        this.reviewers.set(reviewer.username, reviewer);
    }

    createPullRequest(data) {
        const source = this.branches.get(data.sourceBranch);
        const target = this.branches.get(data.targetBranch);

        if (!source || !target) {
            throw new ValidationError("Unknown source or target branch.");
        }

        if (source === target) {
            throw new ValidationError("Source and target must differ.");
        }

        const pr = new PullRequest({
            ...data,
            id: this.nextId++,
            baseSha: target.head?.sha ?? null
        });

        const targetShas = new Set(target.commits.map(c => c.sha));

        pr.commits = source.commits
            .filter(c => !targetShas.has(c.sha))
            .map(c => c.sha);

        this.pullRequests.set(pr.id, pr);
        return pr;
    }

    evaluate(pr) {
        const reasons = [];

        if (pr.state !== PRState.OPEN) {
            return {
                eligible: false,
                reasons: ["PR is not open."]
            };
        }

        const source = this.branches.get(pr.sourceBranch);
        const target = this.branches.get(pr.targetBranch);
        const policy = this.protections.get(pr.targetBranch);

        if (!policy) {
            return {
                eligible: false,
                reasons: ["No branch protection policy."]
            };
        }

        if ((target.head?.sha ?? null) !== pr.baseSha) {
            reasons.push("Target branch changed; synchronize the PR.");
        }

        if (pr.commits.length === 0) {
            reasons.push("No proposed commits.");
        }

        const sourceShas = new Set(source.commits.map(c => c.sha));

        if (!pr.commits.every(sha => sourceShas.has(sha))) {
            reasons.push("Proposed commit is absent from source branch.");
        }

        const latest = pr.latestReviews();
        let approvals = 0;

        for (const [username, review] of latest) {
            const reviewer = this.reviewers.get(username);

            if (
                review.effectiveState === ReviewState.APPROVED &&
                review.commitSha === source.head?.sha &&
                reviewer?.active &&
                reviewer.roles.some(role =>
                    ["reviewer", "maintainer", "security"].includes(role)
                ) &&
                username !== pr.author
            ) {
                approvals++;
            }

            if (
                review.effectiveState === ReviewState.CHANGES_REQUESTED &&
                review.commitSha === source.head?.sha
            ) {
                reasons.push(`Changes requested by ${username}.`);
            }
        }

        if (approvals < policy.requiredReviews) {
            reasons.push(
                `Approval requirement not met: ${approvals}/${policy.requiredReviews}.`
            );
        }

        for (const required of policy.requiredChecks) {
            const check = pr.checks.get(required);

            if (
                !check ||
                check.state !== JobState.SUCCESS ||
                check.commitSha !== source.head?.sha
            ) {
                reasons.push(`Required check failed or missing: ${required}.`);
            }
        }

        if (
            policy.requireConversationResolution &&
            [...pr.comments.values()].some(resolved => !resolved)
        ) {
            reasons.push("Unresolved review conversations exist.");
        }

        return {
            eligible: reasons.length === 0,
            reasons,
            approvals
        };
    }

    merge(prId, strategy) {
        const pr = this.pullRequests.get(prId);

        if (!pr) {
            throw new ValidationError("Unknown PR.");
        }

        const policy = this.protections.get(pr.targetBranch);

        if (!policy?.allowedMergeStrategies.has(strategy)) {
            throw new AuthorizationError("Merge strategy is prohibited.");
        }

        const decision = this.evaluate(pr);

        if (!decision.eligible) {
            throw new AuthorizationError(decision.reasons.join(" "));
        }

        const source = this.branches.get(pr.sourceBranch);
        const target = this.branches.get(pr.targetBranch);

        const mergedSha = sha256([
            pr.id,
            strategy,
            target.head?.sha,
            source.head?.sha
        ].join(":"));

        target.append({
            sha: mergedSha,
            message: `Merge PR #${pr.id}: ${pr.title}`,
            author: "repository-service",
            timestamp: Date.now()
        });

        pr.mergedSha = mergedSha;
        pr.state = PRState.MERGED;
        return mergedSha;
    }

    synchronize(pr) {
        if (pr.state !== PRState.OPEN) {
            throw new TransitionError("Only open PRs can synchronize.");
        }

        const target = this.branches.get(pr.targetBranch);
        pr.baseSha = target.head?.sha ?? null;
        pr.version++;
    }
}

class RunnerPool extends EventEmitter {
    constructor() {
        super();
        this.runners = new Map();
        this.queue = [];
        this.running = new Map();
    }

    register({ id, labels, capacity = 1 }) {
        if (!id || !Array.isArray(labels) || capacity < 1) {
            throw new ValidationError("Invalid runner configuration.");
        }

        if (this.runners.has(id)) {
            throw new ValidationError("Runner ID already registered.");
        }

        this.runners.set(id, {
            id,
            labels: new Set(labels),
            capacity,
            active: true,
            running: 0
        });
    }

    submit(job) {
        if (!job.id || !job.name) {
            throw new ValidationError("Job ID and name are required.");
        }

        if (
            this.queue.some(item => item.id === job.id) ||
            this.running.has(job.id)
        ) {
            throw new ValidationError("Duplicate job ID.");
        }

        const record = {
            ...job,
            requiredLabels: new Set(job.requiredLabels ?? []),
            state: JobState.QUEUED,
            runnerId: null
        };

        this.queue.push(record);
        this.emit("job:queued", record);
        return record;
    }

    dispatch() {
        const remaining = [];

        for (const job of this.queue) {
            const candidates = [...this.runners.values()]
                .filter(runner =>
                    runner.active &&
                    runner.running < runner.capacity &&
                    [...job.requiredLabels].every(label =>
                        runner.labels.has(label)
                    )
                )
                .sort((a, b) =>
                    a.running - b.running || a.id.localeCompare(b.id)
                );

            const runner = candidates[0];

            if (!runner) {
                remaining.push(job);
                continue;
            }

            runner.running++;
            job.runnerId = runner.id;
            job.state = JobState.RUNNING;
            this.running.set(job.id, job);
            this.emit("job:started", job);
        }

        this.queue = remaining;
    }

    complete(jobId, success, result = {}) {
        const job = this.running.get(jobId);

        if (!job) {
            throw new TransitionError("Job is not running.");
        }

        const runner = this.runners.get(job.runnerId);
        runner.running--;

        job.state = success ? JobState.SUCCESS : JobState.FAILURE;
        job.result = result;
        job.completedAt = Date.now();

        this.running.delete(jobId);

        this.emit(
            success ? "job:succeeded" : "job:failed",
            job
        );

        return job;
    }

    cancel(jobId) {
        const queued = this.queue.find(job => job.id === jobId);

        if (queued) {
            queued.state = JobState.CANCELLED;
            this.queue = this.queue.filter(job => job.id !== jobId);
            this.emit("job:cancelled", queued);
            return;
        }

        throw new TransitionError(
            "Running jobs require executor-specific cancellation."
        );
    }
}

class Pipeline {
    constructor(id, commitSha, runnerPool, stages) {
        this.id = id;
        this.commitSha = commitSha;
        this.runnerPool = runnerPool;
        this.stages = stages;
        this.state = JobState.QUEUED;
        this.jobs = [];
        this.startedAt = null;
        this.completedAt = null;
    }

    async execute() {
        this.state = JobState.RUNNING;
        this.startedAt = Date.now();

        try {
            for (const stage of this.stages) {
                const stageResults = await Promise.all(
                    stage.map(async definition => {
                        const job = this.runnerPool.submit(definition);

                        this.runnerPool.dispatch();

                        if (job.state !== JobState.RUNNING) {
                            throw new PipelineError(
                                `No runner available for ${job.name}.`
                            );
                        }

                        try {
                            const result = await definition.run();
                            this.runnerPool.complete(job.id, true, result);
                            this.jobs.push(job);
                            return result;
                        } catch (error) {
                            this.runnerPool.complete(job.id, false, {
                                message: error.message
                            });
                            this.jobs.push(job);
                            throw error;
                        }
                    })
                );

                void stageResults;
            }

            this.state = JobState.SUCCESS;
        } catch (error) {
            this.state = JobState.FAILURE;
            this.error = error.message;
            throw error;
        } finally {
            this.completedAt = Date.now();
        }

        return this;
    }
}

class ArtifactStore {
    constructor(rootDirectory, maxBytes = 50 * 1024 * 1024) {
        this.rootDirectory = rootDirectory;
        this.maxBytes = maxBytes;
        this.metadata = new Map();
    }

    async initialize() {
        await fs.mkdir(this.rootDirectory, {
            recursive: true,
            mode: 0o700
        });
    }

    async publish(name, content, commitSha) {
        requireValue(name, "Artifact name required.");
        requireValue(commitSha, "Commit SHA required.");

        const buffer = Buffer.isBuffer(content)
            ? content
            : Buffer.from(content);

        if (buffer.length === 0 || buffer.length > this.maxBytes) {
            throw new ValidationError("Artifact size is invalid.");
        }

        const digest = sha256(buffer);
        const filename = `${digest}.artifact`;
        const destination = path.join(this.rootDirectory, filename);

        // Digest-based naming prevents untrusted artifact names from
        // controlling filesystem paths.
        await fs.writeFile(destination, buffer, {
            flag: "wx",
            mode: 0o600
        }).catch(async error => {
            if (error.code !== "EEXIST") {
                throw error;
            }
        });

        const metadata = Object.freeze({
            name,
            digest,
            commitSha,
            size: buffer.length,
            path: destination,
            createdAt: Date.now()
        });

        this.metadata.set(digest, metadata);
        return metadata;
    }

    async verify(digest) {
        const metadata = this.metadata.get(digest);

        if (!metadata) {
            throw new ValidationError("Artifact not found.");
        }

        const content = await fs.readFile(metadata.path);

        if (sha256(content) !== digest) {
            throw new PipelineError("Artifact integrity verification failed.");
        }

        return metadata;
    }
}

class DeploymentService extends EventEmitter {
    constructor(artifactStore) {
        super();
        this.artifactStore = artifactStore;
        this.environments = new Map([
            [Environment.DEVELOPMENT, null],
            [Environment.STAGING, null],
            [Environment.PRODUCTION, null]
        ]);
        this.history = [];
    }

    async deploy({
        digest,
        environment,
        pipeline,
        authorized = false,
        expectedCurrentDigest = undefined
    }) {
        if (!Object.values(Environment).includes(environment)) {
            throw new ValidationError("Unknown environment.");
        }

        if (pipeline.state !== JobState.SUCCESS) {
            throw new PipelineError("Pipeline must succeed before deployment.");
        }

        const artifact = await this.artifactStore.verify(digest);

        if (artifact.commitSha !== pipeline.commitSha) {
            throw new PipelineError("Artifact commit mismatch.");
        }

        if (
            environment === Environment.PRODUCTION &&
            !authorized
        ) {
            throw new AuthorizationError(
                "Production deployment needs explicit authorization."
            );
        }

        const current = this.environments.get(environment);

        // Optimistic concurrency prevents two deployment requests from
        // silently overwriting each other's promotion.
        if (
            expectedCurrentDigest !== undefined &&
            current?.digest !== expectedCurrentDigest
        ) {
            throw new TransitionError("Environment changed concurrently.");
        }

        const deployment = Object.freeze({
            digest,
            environment,
            commitSha: artifact.commitSha,
            deployedAt: Date.now(),
            previousDigest: current?.digest ?? null
        });

        this.environments.set(environment, deployment);
        this.history.push(deployment);
        this.emit("deployment:completed", deployment);

        return deployment;
    }

    rollback(environment) {
        const previous = [...this.history]
            .reverse()
            .find(item =>
                item.environment === environment &&
                item.digest !== this.environments.get(environment)?.digest
            );

        if (!previous) {
            throw new TransitionError("No previous deployment available.");
        }

        this.environments.set(environment, previous);
        this.emit("deployment:rolled-back", previous);
        return previous;
    }
}

async function runTests() {
    const pool = new RunnerPool();

    pool.register({
        id: "linux-runner-01",
        labels: ["linux", "node"],
        capacity: 2
    });

    const governance = new GovernanceService();

    const main = new Branch("main", [
        { sha: "aaaaaaa", message: "Initial release" }
    ]);

    const feature = new Branch("feature/security", [
        { sha: "aaaaaaa", message: "Initial release" },
        { sha: "bbbbbbb", message: "Add security validation" }
    ]);

    governance.addBranch(main);
    governance.addBranch(feature);

    governance.protect(
        "main",
        new BranchProtection({ requiredReviews: 2 })
    );

    governance.registerReviewer({
        username: "alice",
        active: true,
        roles: ["reviewer"]
    });

    governance.registerReviewer({
        username: "bob",
        active: true,
        roles: ["maintainer"]
    });

    const pr = governance.createPullRequest({
        title: "Security validation",
        author: "developer",
        sourceBranch: "feature/security",
        targetBranch: "main",
        draft: false
    });

    for (const username of ["alice", "bob"]) {
        pr.addReview(
            new Review({
                reviewer: username,
                state: ReviewState.APPROVED,
                commitSha: "bbbbbbb"
            }),
            governance.reviewers
        );
    }

    pr.setCheck("unit-tests", JobState.SUCCESS, "bbbbbbb");
    pr.setCheck("security-scan", JobState.SUCCESS, "bbbbbbb");

    assert.equal(governance.evaluate(pr).eligible, true);

    const merged = governance.merge(pr.id, MergeStrategy.SQUASH);
    assert.equal(merged.length, 64);
    assert.equal(pr.state, PRState.MERGED);

    assert.throws(
        () => governance.merge(pr.id, MergeStrategy.REBASE),
        TransitionError
    );

    const artifactDirectory = path.join(
        process.cwd(),
        `.cicd-test-${process.pid}`
    );

    const store = new ArtifactStore(artifactDirectory);
    await store.initialize();

    const artifact = await store.publish(
        "service.tar",
        Buffer.from("immutable-build-content"),
        "bbbbbbb"
    );

    const pipeline = new Pipeline(
        "pipeline-001",
        "bbbbbbb",
        pool,
        [
            [{
                id: "build-1",
                name: "build",
                requiredLabels: ["linux", "node"],
                run: async () => ({ output: "build complete" })
            }],
            [{
                id: "test-1",
                name: "test",
                requiredLabels: ["linux", "node"],
                run: async () => ({ tests: 25, passed: 25 })
            }]
        ]
    );

    await pipeline.execute();
    assert.equal(pipeline.state, JobState.SUCCESS);

    const deployment = new DeploymentService(store);

    await deployment.deploy({
        digest: artifact.digest,
        environment: Environment.STAGING,
        pipeline
    });

    assert.equal(
        deployment.environments.get(Environment.STAGING).digest,
        artifact.digest
    );

    await assert.rejects(
        () => deployment.deploy({
            digest: artifact.digest,
            environment: Environment.PRODUCTION,
            pipeline
        }),
        AuthorizationError
    );

    console.log("All JavaScript CI/CD tests passed.");

    await fs.rm(artifactDirectory, {
        recursive: true,
        force: true
    });
}

async function demonstration() {
    const runnerPool = new RunnerPool();

    runnerPool.on("job:queued", job => {
        console.log("Queued:", job.name);
    });

    runnerPool.on("job:started", job => {
        console.log("Started:", job.name, "on", job.runnerId);
    });

    runnerPool.on("job:succeeded", job => {
        console.log("Succeeded:", job.name);
    });

    runnerPool.register({
        id: "ubuntu-runner-01",
        labels: ["linux", "node", "docker"],
        capacity: 2
    });

    const pipeline = new Pipeline(
        "payment-pipeline-001",
        "bbbbbbb",
        runnerPool,
        [
            [{
                id: "lint-001",
                name: "lint",
                requiredLabels: ["linux", "node"],
                run: async () => ({ warnings: 0 })
            }],
            [{
                id: "test-001",
                name: "unit-tests",
                requiredLabels: ["linux", "node"],
                run: async () => ({ passed: 125, failed: 0 })
            }],
            [{
                id: "build-001",
                name: "container-build",
                requiredLabels: ["linux", "docker"],
                run: async () => ({ image: "payment-service:v1" })
            }]
        ]
    );

    await pipeline.execute();

    const directory = path.join(
        process.cwd(),
        ".cicd-artifacts"
    );

    const store = new ArtifactStore(directory);
    await store.initialize();

    const artifact = await store.publish(
        "payment-service.tar",
        Buffer.from("payment-service-build-v1"),
        "bbbbbbb"
    );

    const deployment = new DeploymentService(store);

    await deployment.deploy({
        digest: artifact.digest,
        environment: Environment.STAGING,
        pipeline
    });

    console.log("\nPIPELINE:", pipeline.state);
    console.log("ARTIFACT:", artifact.digest);
    console.log("DEPLOYMENT:", deployment.environments.get(
        Environment.STAGING
    ));
}

if (require.main === module) {
    demonstration()
        .then(runTests)
        .catch(error => {
            console.error("CI/CD execution failed:", error.message);
            process.exitCode = 1;
        });
}

module.exports = {
    Branch,
    Review,
    PullRequest,
    BranchProtection,
    GovernanceService,
    RunnerPool,
    Pipeline,
    ArtifactStore,
    DeploymentService,
    PRState,
    ReviewState,
    JobState,
    Environment,
    MergeStrategy
};
