'use strict';

const crypto = require('node:crypto');
const { EventEmitter } = require('node:events');

const PullRequestState = Object.freeze({
    DRAFT: 'draft',
    OPEN: 'open',
    CLOSED: 'closed',
    MERGED: 'merged'
});

const ReviewState = Object.freeze({
    COMMENTED: 'commented',
    APPROVED: 'approved',
    CHANGES_REQUESTED: 'changes_requested',
    DISMISSED: 'dismissed'
});

const CheckState = Object.freeze({
    PENDING: 'pending',
    PASSED: 'passed',
    FAILED: 'failed'
});

const Severity = Object.freeze({
    LOW: 1,
    MEDIUM: 2,
    HIGH: 3,
    CRITICAL: 4
});

class ValidationError extends Error {}

class RepositoryEventBus extends EventEmitter {}

class ContainerImage {
    constructor({ name, user, secrets = [], vulnerabilities = [] }) {
        if (!name || typeof name !== 'string') {
            throw new ValidationError('image name is required');
        }

        if (user === undefined || user === null) {
            throw new ValidationError('container user is required');
        }

        this.name = name;
        this.user = String(user);
        this.secrets = [...secrets];
        this.vulnerabilities = vulnerabilities.map(v => ({
            package: v.package,
            severity: String(v.severity).toLowerCase(),
            fixedVersion: v.fixedVersion ?? null
        }));
    }

    securityFindings() {
        const findings = [];

        if (this.user === 'root' || this.user === '0' || this.user === '') {
            findings.push('container runs as root');
        }

        if (this.secrets.length > 0) {
            findings.push(`secrets detected: ${this.secrets.join(', ')}`);
        }

        for (const vulnerability of this.vulnerabilities) {
            if (!(vulnerability.severity.toUpperCase() in Severity)) {
                throw new ValidationError(
                    `unknown vulnerability severity: ${vulnerability.severity}`
                );
            }

            if (vulnerability.severity === 'critical') {
                findings.push(
                    `critical vulnerability in ${vulnerability.package}`
                );
            } else if (vulnerability.severity === 'high') {
                findings.push(
                    `high vulnerability in ${vulnerability.package}`
                );
            }
        }

        return findings;
    }

    isSecure() {
        return this.securityFindings().length === 0;
    }
}

class SecretScanner {
    static patterns = [
        /\b(?:password|passwd|secret|api[_-]?key)\b\s*[:=]\s*["'][^"']+["']/gi,
        /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/gi,
        /\baws_secret_access_key\b\s*[:=]\s*\S+/gi
    ];

    static scan(text) {
        if (typeof text !== 'string') {
            throw new ValidationError('scan input must be a string');
        }

        const findings = [];

        for (let index = 0; index < this.patterns.length; index += 1) {
            if (this.patterns[index].test(text)) {
                findings.push(`potential secret pattern ${index + 1}`);
            }

            this.patterns[index].lastIndex = 0;
        }

        return findings;
    }
}

class Review {
    constructor({ reviewer, state, commitSha, comments = [] }) {
        this.reviewer = reviewer;
        this.state = state;
        this.commitSha = commitSha;
        this.comments = [...comments];
    }
}

class PullRequest {
    constructor({
        number,
        author,
        sourceBranch,
        targetBranch,
        headSha,
        draft = false
    }) {
        this.number = number;
        this.author = author;
        this.sourceBranch = sourceBranch;
        this.targetBranch = targetBranch;
        this.headSha = headSha;
        this.draft = draft;
        this.state = PullRequestState.OPEN;
        this.reviews = [];
        this.checks = new Map();
        this.openConversations = 0;
        this.mergeConflict = false;
        this.baseSynced = true;
        this.approvalsStale = false;
    }

    addCheck(name, state, details = '') {
        this.checks.set(name, { name, state, details });
    }

    addReview(review) {
        this.reviews.push(review);
    }
}

class BranchProtectionPolicy {
    constructor({
        requiredApprovals = 2,
        requiredChecks = [
            'container-build',
            'container-vulnerability-scan',
            'container-secret-scan'
        ],
        requireResolvedConversations = true,
        restrictDirectPush = true,
        restrictForcePush = true,
        restrictDeletion = true,
        requireLinearHistory = true,
        allowAdminBypass = false
    } = {}) {
        this.requiredApprovals = requiredApprovals;
        this.requiredChecks = new Set(requiredChecks);
        this.requireResolvedConversations = requireResolvedConversations;
        this.restrictDirectPush = restrictDirectPush;
        this.restrictForcePush = restrictForcePush;
        this.restrictDeletion = restrictDeletion;
        this.requireLinearHistory = requireLinearHistory;
        this.allowAdminBypass = allowAdminBypass;
    }
}

class MergePolicyEngine {
    constructor({ users, branchPolicies }) {
        this.users = users;
        this.branchPolicies = branchPolicies;
    }

    eligibleApprovals(pr) {
        const latestByReviewer = new Map();

        for (const review of pr.reviews) {
            latestByReviewer.set(review.reviewer, review);
        }

        return [...latestByReviewer.values()].filter(review => {
            return (
                review.state === ReviewState.APPROVED &&
                review.reviewer !== pr.author &&
                this.users.has(review.reviewer) &&
                review.commitSha === pr.headSha
            );
        });
    }

    evaluate(pr, image) {
        const reasons = [];
        const policy = this.branchPolicies.get(pr.targetBranch);

        if (!policy) {
            reasons.push('target branch has no protection policy');
            return { eligible: false, reasons };
        }

        if (pr.state !== PullRequestState.OPEN) {
            reasons.push(`pull request is ${pr.state}`);
        }

        if (pr.draft) {
            reasons.push('pull request is a draft');
        }

        if (pr.mergeConflict) {
            reasons.push('merge conflict must be resolved');
        }

        if (!pr.baseSynced) {
            reasons.push('source branch is not synchronized with base');
        }

        if (
            policy.requireResolvedConversations &&
            pr.openConversations > 0
        ) {
            reasons.push(
                `${pr.openConversations} review conversations remain unresolved`
            );
        }

        if (pr.approvalsStale) {
            reasons.push('approvals are stale');
        }

        const approvals = this.eligibleApprovals(pr);
        if (approvals.length < policy.requiredApprovals) {
            reasons.push(
                `requires ${policy.requiredApprovals} approvals; ` +
                `found ${approvals.length}`
            );
        }

        for (const requiredCheck of policy.requiredChecks) {
            const check = pr.checks.get(requiredCheck);

            if (!check) {
                reasons.push(`missing required check: ${requiredCheck}`);
            } else if (check.state !== CheckState.PASSED) {
                reasons.push(
                    `failed required check: ${requiredCheck}`
                );
            }
        }

        const containerFindings = image.securityFindings();

        for (const finding of containerFindings) {
            reasons.push(`container security: ${finding}`);
        }

        return {
            eligible: reasons.length === 0,
            reasons
        };
    }
}

class ContainerSecurityWorkflow extends RepositoryEventBus {
    constructor(engine) {
        super();
        this.engine = engine;
    }

    async process(pr, image) {
        this.emit('workflow.started', {
            pullRequest: pr.number,
            image: image.name
        });

        const scan = await Promise.resolve().then(() => ({
            findings: image.securityFindings()
        }));

        this.emit('container.scan.completed', {
            pullRequest: pr.number,
            findings: scan.findings
        });

        const result = this.engine.evaluate(pr, image);

        this.emit('merge.evaluated', {
            pullRequest: pr.number,
            eligible: result.eligible,
            reasons: result.reasons
        });

        return result;
    }
}

function commitSha(author, message, files) {
    return crypto
        .createHash('sha256')
        .update(JSON.stringify({ author, message, files }))
        .digest('hex')
        .slice(0, 12);
}

function printResult(title, result) {
    console.log(`\n=== ${title} ===`);
    console.log(`merge eligible: ${result.eligible}`);

    if (result.reasons.length === 0) {
        console.log('  - all required conditions passed');
    } else {
        for (const reason of result.reasons) {
            console.log(`  - ${reason}`);
        }
    }
}

async function main() {
    const users = new Map([
        ['alice', { teams: ['developers'] }],
        ['bob', { teams: ['security-reviewers'] }],
        ['carol', { teams: ['platform-reviewers'] }]
    ]);

    const branchPolicies = new Map([
        [
            'main',
            new BranchProtectionPolicy({
                requiredApprovals: 2
            })
        ]
    ]);

    const engine = new MergePolicyEngine({
        users,
        branchPolicies
    });

    const headSha = commitSha(
        'alice',
        'Harden production container',
        ['Dockerfile', 'app.js']
    );

    const pr = new PullRequest({
        number: 77,
        author: 'alice',
        sourceBranch: 'feature/container-hardening',
        targetBranch: 'main',
        headSha
    });

    pr.addCheck('container-build', CheckState.PASSED);
    pr.addCheck('container-vulnerability-scan', CheckState.PASSED);
    pr.addCheck('container-secret-scan', CheckState.PASSED);

    pr.addReview(
        new Review({
            reviewer: 'bob',
            state: ReviewState.APPROVED,
            commitSha: headSha
        })
    );

    pr.addReview(
        new Review({
            reviewer: 'carol',
            state: ReviewState.APPROVED,
            commitSha: headSha
        })
    );

    const workflow = new ContainerSecurityWorkflow(engine);

    workflow.on('workflow.started', event => {
        console.log(
            `workflow started for PR #${event.pullRequest}, image=${event.image}`
        );
    });

    workflow.on('container.scan.completed', event => {
        console.log(
            `container scan completed: ${event.findings.length} findings`
        );
    });

    workflow.on('merge.evaluated', event => {
        console.log(
            `merge evaluation completed: ${event.eligible}`
        );
    });

    const secureImage = new ContainerImage({
        name: 'payments:77',
        user: '10001',
        vulnerabilities: [
            {
                package: 'openssl',
                severity: 'medium',
                fixedVersion: '3.2.1'
            }
        ]
    });

    const secureResult = await workflow.process(pr, secureImage);
    printResult('secure image', secureResult);

    const insecureImage = new ContainerImage({
        name: 'payments:77',
        user: 'root',
        secrets: ['DATABASE_PASSWORD'],
        vulnerabilities: [
            {
                package: 'openssl',
                severity: 'critical',
                fixedVersion: '3.2.1'
            },
            {
                package: 'curl',
                severity: 'high',
                fixedVersion: '8.10.0'
            }
        ]
    });

    const insecureResult = await workflow.process(pr, insecureImage);
    printResult('insecure image', insecureResult);

    const source = `
        database_password = "production-password"
        application_mode = "production"
    `;

    const secretFindings = SecretScanner.scan(source);

    console.log('\n=== secret scan ===');
    console.log(`findings: ${secretFindings.length}`);

    for (const finding of secretFindings) {
        console.log(`  - ${finding}`);
    }

    console.log(
        '\nProduction controls: use numeric non-root UIDs, immutable image ' +
        'references, external secret stores, vulnerability gates, and ' +
        'protected deployment branches.'
    );
}

main().catch(error => {
    console.error(`fatal error: ${error.message}`);
    process.exitCode = 1;
});
