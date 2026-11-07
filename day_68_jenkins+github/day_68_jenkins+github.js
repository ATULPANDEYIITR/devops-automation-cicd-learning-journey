'use strict';

/**
 * Jenkins + GitHub event-driven integration.
 *
 * Features:
 * - GitHub webhook signature verification
 * - Delivery deduplication
 * - Push and pull_request event handling
 * - Jenkins build dispatch
 * - SCM polling
 * - Pull Request review governance
 * - Branch protection evaluation
 * - Asynchronous build execution
 *
 * Runtime: Node.js 18+
 * Dependencies: Node.js standard library only
 */

const http = require('node:http');
const crypto = require('node:crypto');
const { EventEmitter } = require('node:events');


/* ============================================================
   1. CONFIGURATION
   ============================================================ */

const CONFIG = Object.freeze({
    port: Number(process.env.PORT || 8080),
    webhookSecret: process.env.GITHUB_WEBHOOK_SECRET || '',
    maxBodyBytes: 1024 * 1024,
    requiredChecks: [
        'unit-tests',
        'integration-tests',
        'security-scan'
    ],
    requiredApprovals: 2
});


/* ============================================================
   2. CUSTOM ERRORS
   ============================================================ */

class ValidationError extends Error {}
class AuthenticationError extends Error {}
class DuplicateDeliveryError extends Error {}
class WorkflowError extends Error {}


/* ============================================================
   3. VALIDATION UTILITIES
   ============================================================ */

const isValidSHA = sha =>
    typeof sha === 'string' &&
    /^[0-9a-f]{7,64}$/.test(sha);

const validateBranch = branch => {
    if (
        typeof branch !== 'string' ||
        !branch ||
        branch.startsWith('-') ||
        branch.length > 255 ||
        branch.includes('..') ||
        branch.includes(' ')
    ) {
        throw new ValidationError('Invalid branch name');
    }

    return branch;
};

const validatePRNumber = number => {
    if (!Number.isInteger(number) || number <= 0) {
        throw new ValidationError('Invalid Pull Request number');
    }

    return number;
};


/* ============================================================
   4. WEBHOOK AUTHENTICATION
   ============================================================ */

class WebhookAuthenticator {

    constructor(secret) {
        if (typeof secret !== 'string' || secret.length < 16) {
            throw new ValidationError(
                'Webhook secret must contain at least 16 characters'
            );
        }

        this.secret = Buffer.from(secret, 'utf8');
    }

    verify(rawBody, signature) {
        if (
            typeof signature !== 'string' ||
            !/^sha256=[0-9a-f]{64}$/i.test(signature)
        ) {
            return false;
        }

        const supplied = Buffer.from(
            signature.substring(7),
            'hex'
        );

        const expected = crypto
            .createHmac('sha256', this.secret)
            .update(rawBody)
            .digest();

        return (
            supplied.length === expected.length &&
            crypto.timingSafeEqual(supplied, expected)
        );
    }
}


/* ============================================================
   5. WEBHOOK DELIVERY DEDUPLICATION
   ============================================================ */

class DeliveryRegistry {

    constructor(maxEntries = 20000) {
        this.deliveries = new Map();
        this.maxEntries = maxEntries;
    }

    register(deliveryId) {
        if (
            typeof deliveryId !== 'string' ||
            !deliveryId.trim()
        ) {
            throw new ValidationError('Missing delivery ID');
        }

        if (this.deliveries.has(deliveryId)) {
            return false;
        }

        if (this.deliveries.size >= this.maxEntries) {
            const oldest = this.deliveries.keys().next().value;
            this.deliveries.delete(oldest);
        }

        this.deliveries.set(deliveryId, Date.now());

        return true;
    }
}


/* ============================================================
   6. BUILD DOMAIN
   ============================================================ */

const BuildState = Object.freeze({
    QUEUED: 'queued',
    RUNNING: 'running',
    SUCCESS: 'success',
    FAILURE: 'failure'
});

class Build {

    constructor({
        id,
        repository,
        branch,
        commitSHA,
        trigger
    }) {
        if (!isValidSHA(commitSHA)) {
            throw new ValidationError('Invalid build commit SHA');
        }

        this.id = id;
        this.repository = repository;
        this.branch = validateBranch(branch);
        this.commitSHA = commitSHA;
        this.trigger = trigger;
        this.state = BuildState.QUEUED;
        this.createdAt = new Date();
        this.startedAt = null;
        this.finishedAt = null;
        this.error = null;
    }
}


/* ============================================================
   7. JENKINS DISPATCHER
   ============================================================ */

class JenkinsDispatcher extends EventEmitter {

    constructor() {
        super();

        this.builds = new Map();
        this.nextId = 1;
        this.pendingKeys = new Set();
    }

    enqueue(event) {
        const key = `${event.repository}:${event.commitSHA}`;

        // Avoid duplicate builds for the same repository and commit
        // while a build is already queued or running.
        if (this.pendingKeys.has(key)) {
            return null;
        }

        const build = new Build({
            id: this.nextId++,
            ...event
        });

        this.builds.set(build.id, build);
        this.pendingKeys.add(key);

        this.emit('build:queued', build);

        return build;
    }

    async execute(build, pipeline) {
        if (build.state !== BuildState.QUEUED) {
            throw new WorkflowError(
                'Only queued builds can execute'
            );
        }

        build.state = BuildState.RUNNING;
        build.startedAt = new Date();

        this.emit('build:started', build);

        try {
            await pipeline(build);

            build.state = BuildState.SUCCESS;
            this.emit('build:success', build);

        } catch (error) {
            build.state = BuildState.FAILURE;
            build.error = error.message;

            this.emit('build:failure', build);

        } finally {
            build.finishedAt = new Date();

            this.pendingKeys.delete(
                `${build.repository}:${build.commitSHA}`
            );
        }

        return build;
    }

    history(repository) {
        return [...this.builds.values()]
            .filter(build => build.repository === repository)
            .sort((a, b) => b.id - a.id);
    }
}


/* ============================================================
   8. SCM POLLING
   ============================================================ */

class SCMMonitor extends EventEmitter {

    constructor() {
        super();
        this.observedCommits = new Map();
    }

    observe(repository, branch, remoteSHA) {
        validateBranch(branch);

        if (!isValidSHA(remoteSHA)) {
            throw new ValidationError('Invalid remote commit SHA');
        }

        const key = `${repository}:${branch}`;
        const previous = this.observedCommits.get(key);

        if (previous === remoteSHA) {
            return false;
        }

        this.observedCommits.set(key, remoteSHA);

        this.emit('scm:changed', {
            repository,
            branch,
            previous,
            commitSHA: remoteSHA
        });

        return true;
    }
}


/* ============================================================
   9. PULL REQUEST DOMAIN
   ============================================================ */

const ReviewState = Object.freeze({
    APPROVED: 'approved',
    CHANGES_REQUESTED: 'changes_requested',
    COMMENTED: 'commented',
    DISMISSED: 'dismissed'
});

class PullRequest {

    constructor({
        number,
        sourceBranch,
        targetBranch,
        sourceSHA,
        targetSHA,
        draft = false
    }) {
        this.number = validatePRNumber(number);
        this.sourceBranch = validateBranch(sourceBranch);
        this.targetBranch = validateBranch(targetBranch);

        if (sourceBranch === targetBranch) {
            throw new ValidationError(
                'Source and target branches must differ'
            );
        }

        if (!isValidSHA(sourceSHA) || !isValidSHA(targetSHA)) {
            throw new ValidationError('Invalid branch commit SHA');
        }

        this.sourceSHA = sourceSHA;
        this.targetSHA = targetSHA;
        this.draft = draft;
        this.state = 'open';
        this.mergeConflict = false;
        this.baseSynchronized = true;
        this.unresolvedDiscussions = 0;
        this.reviews = [];
        this.checks = new Map();
    }

    addReview(reviewer, state) {
        if (this.state !== 'open') {
            throw new WorkflowError('PR is not open');
        }

        if (!Object.values(ReviewState).includes(state)) {
            throw new ValidationError('Invalid review state');
        }

        this.reviews.push({
            reviewer,
            state,
            commitSHA: this.sourceSHA,
            submittedAt: new Date()
        });
    }

    updateCheck(name, state) {
        const allowed = [
            'success',
            'failure',
            'pending',
            'error'
        ];

        if (!allowed.includes(state)) {
            throw new ValidationError('Invalid status check state');
        }

        this.checks.set(name, {
            state,
            commitSHA: this.sourceSHA,
            updatedAt: new Date()
        });
    }

    synchronizeBase(newTargetSHA) {
        if (!isValidSHA(newTargetSHA)) {
            throw new ValidationError('Invalid target SHA');
        }

        this.targetSHA = newTargetSHA;
        this.baseSynchronized = true;
    }

    updateSourceCommit(newSourceSHA) {
        if (!isValidSHA(newSourceSHA)) {
            throw new ValidationError('Invalid source SHA');
        }

        this.sourceSHA = newSourceSHA;
    }

    resolveDiscussion() {
        if (this.unresolvedDiscussions <= 0) {
            throw new WorkflowError(
                'No unresolved discussions exist'
            );
        }

        this.unresolvedDiscussions--;
    }
}


/* ============================================================
   10. BRANCH PROTECTION
   ============================================================ */

class BranchProtectionPolicy {

    constructor({
        branch,
        requiredApprovals,
        requiredChecks,
        requireConversationResolution = true,
        requireUpToDate = true,
        requireCodeOwnerApproval = false,
        dismissStaleApprovals = true,
        allowAdministratorBypass = false
    }) {
        this.branch = validateBranch(branch);

        if (
            !Number.isInteger(requiredApprovals) ||
            requiredApprovals < 0
        ) {
            throw new ValidationError(
                'Invalid required approval count'
            );
        }

        this.requiredApprovals = requiredApprovals;
        this.requiredChecks = new Set(requiredChecks);
        this.requireConversationResolution =
            requireConversationResolution;
        this.requireUpToDate = requireUpToDate;
        this.requireCodeOwnerApproval =
            requireCodeOwnerApproval;
        this.dismissStaleApprovals = dismissStaleApprovals;
        this.allowAdministratorBypass =
            allowAdministratorBypass;
    }
}


/* ============================================================
   11. MERGE ELIGIBILITY ENGINE
   ============================================================ */

class MergePolicyEngine {

    evaluate(pr, policy, reviewers, codeOwners = new Set()) {
        const reasons = [];

        if (pr.state !== 'open') {
            reasons.push('PR is not open');
        }

        if (pr.draft) {
            reasons.push('Draft PR cannot be merged');
        }

        if (pr.mergeConflict) {
            reasons.push('Merge conflict exists');
        }

        if (
            policy.requireUpToDate &&
            !pr.baseSynchronized
        ) {
            reasons.push('Branch is not synchronized');
        }

        if (
            policy.requireConversationResolution &&
            pr.unresolvedDiscussions > 0
        ) {
            reasons.push('Unresolved review discussions exist');
        }

        for (const required of policy.requiredChecks) {
            const check = pr.checks.get(required);

            if (!check) {
                reasons.push(`Missing check: ${required}`);
            } else if (check.state !== 'success') {
                reasons.push(
                    `Check ${required} is ${check.state}`
                );
            } else if (check.commitSHA !== pr.sourceSHA) {
                reasons.push(`Check ${required} is stale`);
            }
        }

        const latestReviews = new Map();

        for (const review of pr.reviews) {
            if (!reviewers.has(review.reviewer)) {
                continue;
            }

            if (
                policy.dismissStaleApprovals &&
                review.commitSHA !== pr.sourceSHA
            ) {
                continue;
            }

            latestReviews.set(review.reviewer, review);
        }

        const approvals = [...latestReviews.values()]
            .filter(review =>
                review.state === ReviewState.APPROVED
            );

        if (approvals.length < policy.requiredApprovals) {
            reasons.push(
                `Approvals insufficient: ${approvals.length}/` +
                `${policy.requiredApprovals}`
            );
        }

        if (
            policy.requireCodeOwnerApproval &&
            !approvals.some(review =>
                codeOwners.has(review.reviewer)
            )
        ) {
            reasons.push('Code owner approval required');
        }

        return {
            eligible: reasons.length === 0,
            reasons
        };
    }
}


/* ============================================================
   12. GITHUB EVENT ROUTER
   ============================================================ */

class GitHubEventRouter {

    constructor(dispatcher) {
        this.dispatcher = dispatcher;
    }

    route(eventName, payload) {
        if (eventName === 'ping') {
            return {
                accepted: true,
                message: 'Webhook connection verified'
            };
        }

        if (eventName === 'push') {
            const branch = payload.ref?.replace(
                /^refs\/heads\//,
                ''
            );

            const sha = payload.after;

            if (!branch || !sha) {
                throw new ValidationError('Invalid push payload');
            }

            if (sha === '0'.repeat(40)) {
                return {
                    accepted: true,
                    message: 'Branch deletion ignored'
                };
            }

            const build = this.dispatcher.enqueue({
                repository: payload.repository?.name || 'unknown',
                branch,
                commitSHA: sha,
                trigger: 'webhook'
            });

            return {
                accepted: true,
                buildId: build?.id ?? null
            };
        }

        if (eventName === 'pull_request') {
            const action = payload.action;

            const allowedActions = new Set([
                'opened',
                'synchronize',
                'reopened',
                'ready_for_review'
            ]);

            if (!allowedActions.has(action)) {
                return {
                    accepted: true,
                    message: `PR action ${action} ignored`
                };
            }

            const pr = payload.pull_request;

            if (!pr || pr.draft) {
                return {
                    accepted: true,
                    message: 'Draft or invalid PR ignored'
                };
            }

            const build = this.dispatcher.enqueue({
                repository: payload.repository?.name || 'unknown',
                branch: pr.head.ref,
                commitSHA: pr.head.sha,
                trigger: 'pull_request'
            });

            return {
                accepted: true,
                buildId: build?.id ?? null
            };
        }

        return {
            accepted: true,
            message: `Event ${eventName} recorded without build`
        };
    }
}


/* ============================================================
   13. RAW HTTP BODY READER
   ============================================================ */

function readRawBody(request, limit) {
    return new Promise((resolve, reject) => {
        const chunks = [];
        let size = 0;

        request.on('data', chunk => {
            size += chunk.length;

            if (size > limit) {
                reject(new ValidationError('Request body too large'));
                request.destroy();
                return;
            }

            chunks.push(chunk);
        });

        request.on('end', () => {
            resolve(Buffer.concat(chunks));
        });

        request.on('error', reject);
    });
}


/* ============================================================
   14. APPLICATION SERVICES
   ============================================================ */

const dispatcher = new JenkinsDispatcher();
const scmMonitor = new SCMMonitor();
const deduplicator = new DeliveryRegistry();

const router = new GitHubEventRouter(dispatcher);

dispatcher.on('build:queued', build => {
    console.log(
        `[Jenkins] Build #${build.id} queued for ${build.commitSHA}`
    );
});

dispatcher.on('build:success', build => {
    console.log(`[Jenkins] Build #${build.id} passed`);
});

dispatcher.on('build:failure', build => {
    console.error(
        `[Jenkins] Build #${build.id} failed: ${build.error}`
    );
});

scmMonitor.on('scm:changed', event => {
    console.log(
        `[SCM] Change detected on ${event.branch}: ${event.commitSHA}`
    );

    const build = dispatcher.enqueue({
        repository: event.repository,
        branch: event.branch,
        commitSHA: event.commitSHA,
        trigger: 'scm_poll'
    });

    if (build) {
        void dispatcher.execute(
            build,
            async currentBuild => {
                await runPipeline(currentBuild);
            }
        );
    }
});


/* ============================================================
   15. PIPELINE EXECUTION
   ============================================================ */

async function runPipeline(build) {
    const stages = [
        'checkout',
        'dependency-installation',
        'unit-tests',
        'integration-tests',
        'security-scan',
        'artifact-build'
    ];

    for (const stage of stages) {
        console.log(
            `[Jenkins] Build #${build.id}: ${stage}`
        );

        // Replace stage execution with actual isolated
        // Jenkins agents and trusted pipeline steps.
        await Promise.resolve();
    }
}


/* ============================================================
   16. WEBHOOK HTTP SERVER
   ============================================================ */

function createWebhookServer() {
    const authenticator = new WebhookAuthenticator(
        CONFIG.webhookSecret
    );

    return http.createServer(async (request, response) => {
        if (
            request.method !== 'POST' ||
            request.url !== '/github-webhook'
        ) {
            response.writeHead(404);
            response.end('Not found');
            return;
        }

        try {
            const rawBody = await readRawBody(
                request,
                CONFIG.maxBodyBytes
            );

            const signature = request.headers[
                'x-hub-signature-256'
            ];

            if (!authenticator.verify(rawBody, signature)) {
                throw new AuthenticationError(
                    'Webhook signature verification failed'
                );
            }

            const deliveryId = request.headers[
                'x-github-delivery'
            ];

            if (!deduplicator.register(deliveryId)) {
                response.writeHead(200, {
                    'Content-Type': 'application/json'
                });

                response.end(JSON.stringify({
                    accepted: true,
                    duplicate: true
                }));

                return;
            }

            const eventName = request.headers[
                'x-github-event'
            ];

            if (!eventName) {
                throw new ValidationError(
                    'Missing GitHub event header'
                );
            }

            const payload = JSON.parse(rawBody.toString('utf8'));

            const result = router.route(
                eventName,
                payload
            );

            response.writeHead(202, {
                'Content-Type': 'application/json'
            });

            response.end(JSON.stringify(result));

            // Dispatch asynchronously after accepting the event.
            if (result.buildId) {
                const build = dispatcher.builds.get(
                    result.buildId
                );

                if (build) {
                    void dispatcher.execute(
                        build,
                        runPipeline
                    );
                }
            }

        } catch (error) {
            const status =
                error instanceof AuthenticationError ? 401 :
                error instanceof ValidationError ? 400 :
                500;

            console.error('[Webhook]', error.message);

            if (!response.headersSent) {
                response.writeHead(status, {
                    'Content-Type': 'application/json'
                });

                response.end(JSON.stringify({
                    error: error.message
                }));
            }
        }
    });
}


/* ============================================================
   17. SCM POLLING DEMONSTRATION
   ============================================================ */

function demonstrateSCMPolling() {
    const repository = 'payment-service';

    console.log('\n=== SCM POLLING ===');

    scmMonitor.observe(
        repository,
        'main',
        'a'.repeat(40)
    );

    scmMonitor.observe(
        repository,
        'main',
        'a'.repeat(40)
    );

    scmMonitor.observe(
        repository,
        'main',
        'b'.repeat(40)
    );
}


/* ============================================================
   18. GOVERNANCE DEMONSTRATION
   ============================================================ */

function demonstrateGovernance() {
    console.log('\n=== PULL REQUEST GOVERNANCE ===');

    const pr = new PullRequest({
        number: 42,
        sourceBranch: 'feature/payment',
        targetBranch: 'main',
        sourceSHA: 'a'.repeat(40),
        targetSHA: 'b'.repeat(40)
    });

    pr.addReview('alice', ReviewState.APPROVED);
    pr.addReview('bob', ReviewState.APPROVED);

    for (const check of CONFIG.requiredChecks) {
        pr.updateCheck(check, 'success');
    }

    const policy = new BranchProtectionPolicy({
        branch: 'main',
        requiredApprovals: 2,
        requiredChecks: CONFIG.requiredChecks,
        requireConversationResolution: true,
        requireUpToDate: true,
        requireCodeOwnerApproval: true
    });

    const engine = new MergePolicyEngine();

    const result = engine.evaluate(
        pr,
        policy,
        new Set(['alice', 'bob']),
        new Set(['alice'])
    );

    console.log('Merge eligible:', result.eligible);
    console.log('Reasons:', result.reasons);
}


/* ============================================================
   19. SELF-TESTS
   ============================================================ */

async function runTests() {
    const assert = require('node:assert/strict');

    const registry = new DeliveryRegistry();

    assert.equal(registry.register('event-1'), true);
    assert.equal(registry.register('event-1'), false);

    const monitor = new SCMMonitor();

    assert.equal(
        monitor.observe('repo', 'main', 'a'.repeat(40)),
        true
    );

    assert.equal(
        monitor.observe('repo', 'main', 'a'.repeat(40)),
        false
    );

    const pr = new PullRequest({
        number: 10,
        sourceBranch: 'feature/test',
        targetBranch: 'main',
        sourceSHA: 'c'.repeat(40),
        targetSHA: 'd'.repeat(40)
    });

    const policy = new BranchProtectionPolicy({
        branch: 'main',
        requiredApprovals: 1,
        requiredChecks: ['unit-tests']
    });

    const engine = new MergePolicyEngine();

    let result = engine.evaluate(
        pr,
        policy,
        new Set(['alice'])
    );

    assert.equal(result.eligible, false);

    pr.addReview('alice', ReviewState.APPROVED);
    pr.updateCheck('unit-tests', 'success');

    result = engine.evaluate(
        pr,
        policy,
        new Set(['alice'])
    );

    assert.equal(result.eligible, true);

    pr.updateSourceCommit('e'.repeat(40));

    result = engine.evaluate(
        pr,
        policy,
        new Set(['alice'])
    );

    assert.equal(result.eligible, false);

    console.log('\nAll JavaScript tests passed.');
}


/* ============================================================
   20. STARTUP
   ============================================================ */

async function main() {
    await runTests();

    demonstrateSCMPolling();
    demonstrateGovernance();

    if (process.env.START_SERVER === 'true') {
        if (!CONFIG.webhookSecret) {
            throw new ValidationError(
                'Set GITHUB_WEBHOOK_SECRET before starting server'
            );
        }

        const server = createWebhookServer();

        server.listen(CONFIG.port, () => {
            console.log(
                `GitHub webhook receiver listening on ${CONFIG.port}`
            );
        });

        process.on('SIGTERM', () => {
            server.close(() => process.exit(0));
        });
    } else {
        console.log(
            '\nHTTP server not started. Set START_SERVER=true to enable it.'
        );
    }
}

main().catch(error => {
    console.error('Application startup failed:', error);
    process.exitCode = 1;
});
