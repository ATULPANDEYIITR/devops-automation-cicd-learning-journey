"use strict";

/*
 * Pull Requests, Code Review, Approvals, and Branch Protection
 * ==============================================================
 *
 * A standalone JavaScript study file demonstrating the lifecycle of a pull
 * request and the policy decisions that can control whether it may merge.
 *
 * Run with:
 *     node pull_requests.js
 *
 * No external npm packages are required.
 *
 * The implementation progresses through:
 *   1. Repository and branch concepts
 *   2. Pull-request modeling
 *   3. Diffs
 *   4. Reviews and approvals
 *   5. Status checks
 *   6. Branch protection
 *   7. Stale approvals
 *   8. Code ownership
 *   9. Security checks
 *  10. Complete policy evaluation
 *  11. Asynchronous CI simulation
 *  12. Tests and edge cases
 */

// ============================================================================
// 1. BASIC DATA MODELS
// ============================================================================

class Commit {
    constructor({ id, author, message, files }) {
        this.id = id;
        this.author = author;
        this.message = message;
        this.files = { ...files };
    }

    static create(author, message, files) {
        /*
         * JavaScript's built-in crypto module is deliberately avoided here.
         * The identifier is a deterministic educational value rather than a
         * reproduction of Git's actual object hashing algorithm.
         */
        const normalized = Object.keys(files)
            .sort()
            .map((name) => `${name}\n${files[name]}`)
            .join("\n");

        let hash = 2166136261;
        const input = `${author}\n${message}\n${normalized}`;

        for (let i = 0; i < input.length; i += 1) {
            hash ^= input.charCodeAt(i);
            hash = Math.imul(hash, 16777619);
        }

        const id = (hash >>> 0).toString(16).padStart(8, "0");

        return new Commit({
            id,
            author,
            message,
            files,
        });
    }
}

class Branch {
    constructor(name, head) {
        this.name = name;
        this.head = head;
    }
}

class Repository {
    constructor(name) {
        this.name = name;
        this.branches = new Map();
    }

    createBranch(name, sourceBranch) {
        if (this.branches.has(name)) {
            throw new Error(`Branch already exists: ${name}`);
        }

        const source = this.branches.get(sourceBranch);

        if (!source) {
            throw new Error(`Unknown source branch: ${sourceBranch}`);
        }

        const branch = new Branch(name, source.head);
        this.branches.set(name, branch);
        return branch;
    }

    updateBranch(name, commit) {
        const branch = this.branches.get(name);

        if (!branch) {
            throw new Error(`Unknown branch: ${name}`);
        }

        branch.head = commit;
    }
}

function createDemoRepository() {
    const files = {
        "README.md": "# Payment Service\n",
        "payment.js":
            "function calculateTotal(amount, tax) {\n" +
            "    return amount + tax;\n" +
            "}\n",
        "test/payment.test.js":
            "if (calculateTotal(100, 10) !== 110) throw new Error('test failed');\n",
    };

    const initialCommit = Commit.create(
        "system",
        "Initial payment service",
        files
    );

    const repository = new Repository("payment-service");
    repository.branches.set("main", new Branch("main", initialCommit));

    return repository;
}

// ============================================================================
// 2. DIFF GENERATION
// ============================================================================

function simpleLineDiff(oldText, newText) {
    const oldLines = oldText.split("\n");
    const newLines = newText.split("\n");
    const output = [];

    const maxLength = Math.max(oldLines.length, newLines.length);

    for (let index = 0; index < maxLength; index += 1) {
        const oldLine = oldLines[index];
        const newLine = newLines[index];

        if (oldLine === newLine) {
            if (oldLine !== undefined) {
                output.push(`  ${oldLine}`);
            }
        } else {
            if (oldLine !== undefined) {
                output.push(`- ${oldLine}`);
            }

            if (newLine !== undefined) {
                output.push(`+ ${newLine}`);
            }
        }
    }

    return output.join("\n");
}

function generateDiff(baseCommit, headCommit) {
    const files = new Set([
        ...Object.keys(baseCommit.files),
        ...Object.keys(headCommit.files),
    ]);

    const output = [];

    for (const filename of [...files].sort()) {
        const oldContent = baseCommit.files[filename] ?? "";
        const newContent = headCommit.files[filename] ?? "";

        if (oldContent === newContent) {
            continue;
        }

        output.push(`--- a/${filename}`);
        output.push(`+++ b/${filename}`);
        output.push(simpleLineDiff(oldContent, newContent));
    }

    return output.join("\n");
}

// ============================================================================
// 3. REVIEW STATES
// ============================================================================

const ReviewState = Object.freeze({
    APPROVED: "approved",
    CHANGES_REQUESTED: "changes_requested",
    COMMENTED: "commented",
    DISMISSED: "dismissed",
});

class Review {
    constructor({ reviewer, state, commitId, comment = "" }) {
        this.reviewer = reviewer;
        this.state = state;
        this.commitId = commitId;
        this.comment = comment;
    }
}

class ReviewComment {
    constructor({
        reviewer,
        filename,
        lineNumber,
        body,
        resolved = false,
    }) {
        this.reviewer = reviewer;
        this.filename = filename;
        this.lineNumber = lineNumber;
        this.body = body;
        this.resolved = resolved;
    }
}

// ============================================================================
// 4. STATUS CHECKS
// ============================================================================

class StatusCheck {
    constructor({ name, passed, commitId }) {
        this.name = name;
        this.passed = passed;
        this.commitId = commitId;
    }
}

function runUnitTests(commit) {
    /*
     * This simulates CI. Real systems execute the project's actual test suite.
     * A deliberately inserted marker makes failure easy to demonstrate.
     */
    const passed = !Object.values(commit.files).some((content) =>
        content.includes("INTENTIONALLY_BROKEN")
    );

    return new StatusCheck({
        name: "unit-tests",
        passed,
        commitId: commit.id,
    });
}

function runLint(commit) {
    /*
     * The example checks for tab characters in JavaScript source. A production
     * linter would enforce a much richer set of language-specific rules.
     */
    const passed = Object.entries(commit.files).every(
        ([filename, content]) =>
            !filename.endsWith(".js") || !content.includes("\t")
    );

    return new StatusCheck({
        name: "lint",
        passed,
        commitId: commit.id,
    });
}

// ============================================================================
// 5. PULL REQUEST MODEL
// ============================================================================

class PullRequest {
    constructor({
        number,
        title,
        author,
        baseBranch,
        headBranch,
        baseCommitId,
        headCommit,
    }) {
        this.number = number;
        this.title = title;
        this.author = author;
        this.baseBranch = baseBranch;
        this.headBranch = headBranch;
        this.baseCommitId = baseCommitId;
        this.headCommit = headCommit;

        this.draft = false;
        this.merged = false;
        this.closed = false;
        this.branchIsUpToDate = true;

        this.reviews = [];
        this.comments = [];
        this.statusChecks = [];
        this.codeOwnersApproved = new Set();
    }

    get headCommitId() {
        return this.headCommit.id;
    }
}

// ============================================================================
// 6. BRANCH PROTECTION
// ============================================================================

class BranchProtectionPolicy {
    constructor(options = {}) {
        this.protectedBranch = options.protectedBranch ?? "main";
        this.requiredApprovals = options.requiredApprovals ?? 1;
        this.requiredStatusChecks =
            options.requiredStatusChecks ?? ["unit-tests", "lint"];

        this.requireCodeOwnerReview =
            options.requireCodeOwnerReview ?? false;

        this.dismissStaleApprovals =
            options.dismissStaleApprovals ?? true;

        this.requireConversationResolution =
            options.requireConversationResolution ?? true;

        this.requireUpToDateBranch =
            options.requireUpToDateBranch ?? true;

        this.allowForcePush = options.allowForcePush ?? false;
        this.allowDeletions = options.allowDeletions ?? false;
        this.requireSignedCommits =
            options.requireSignedCommits ?? false;

        this.requireLinearHistory =
            options.requireLinearHistory ?? false;

        this.allowDirectPush = options.allowDirectPush ?? false;
    }
}

class PolicyResult {
    constructor(allowed, reasons = []) {
        this.allowed = allowed;
        this.reasons = reasons;
    }

    toString() {
        if (this.allowed) {
            return "MERGE ALLOWED";
        }

        return `MERGE BLOCKED:\n${this.reasons
            .map((reason) => `- ${reason}`)
            .join("\n")}`;
    }
}

class PullRequestPolicyEngine {
    constructor(policy) {
        this.policy = policy;
    }

    currentApprovals(pullRequest) {
        const reviewers = new Set();

        for (const review of pullRequest.reviews) {
            if (review.state !== ReviewState.APPROVED) {
                continue;
            }

            if (
                this.policy.dismissStaleApprovals &&
                review.commitId !== pullRequest.headCommitId
            ) {
                continue;
            }

            reviewers.add(review.reviewer);
        }

        return reviewers;
    }

    hasCurrentChangeRequest(pullRequest) {
        return pullRequest.reviews.some((review) => {
            if (review.state !== ReviewState.CHANGES_REQUESTED) {
                return false;
            }

            if (
                this.policy.dismissStaleApprovals &&
                review.commitId !== pullRequest.headCommitId
            ) {
                return false;
            }

            return true;
        });
    }

    requiredChecksPassed(pullRequest) {
        const checks = new Map();

        for (const check of pullRequest.statusChecks) {
            if (check.commitId === pullRequest.headCommitId) {
                checks.set(check.name, check.passed);
            }
        }

        return this.policy.requiredStatusChecks.every(
            (checkName) => checks.get(checkName) === true
        );
    }

    evaluate(pullRequest, currentBaseCommitId) {
        const reasons = [];

        if (pullRequest.merged) {
            reasons.push("Pull request is already merged.");
        }

        if (pullRequest.closed) {
            reasons.push("Pull request is closed.");
        }

        if (pullRequest.draft) {
            reasons.push(
                "Draft pull requests cannot be merged under this policy."
            );
        }

        if (
            pullRequest.baseBranch !==
            this.policy.protectedBranch
        ) {
            reasons.push(
                `Expected protected branch ${this.policy.protectedBranch}, ` +
                `but received ${pullRequest.baseBranch}.`
            );
        }

        if (this.policy.requireUpToDateBranch) {
            if (!pullRequest.branchIsUpToDate) {
                reasons.push(
                    "The head branch must be up to date with the base branch."
                );
            }

            if (pullRequest.baseCommitId !== currentBaseCommitId) {
                reasons.push(
                    "The pull request targets an outdated base commit."
                );
            }
        }

        if (this.hasCurrentChangeRequest(pullRequest)) {
            reasons.push("A current review requests changes.");
        }

        const approvals = this.currentApprovals(pullRequest);

        /*
         * The pull-request author is excluded from the independent approval
         * count. This is a policy decision, not an inherent property of Git.
         */
        approvals.delete(pullRequest.author);

        if (approvals.size < this.policy.requiredApprovals) {
            reasons.push(
                `At least ${this.policy.requiredApprovals} ` +
                `independent current approval(s) are required; ` +
                `found ${approvals.size}.`
            );
        }

        if (
            this.policy.requireCodeOwnerReview &&
            pullRequest.codeOwnersApproved.size === 0
        ) {
            reasons.push("A code-owner approval is required.");
        }

        if (this.policy.requireConversationResolution) {
            const unresolved = pullRequest.comments.filter(
                (comment) => !comment.resolved
            );

            if (unresolved.length > 0) {
                reasons.push(
                    `${unresolved.length} review conversation(s) remain unresolved.`
                );
            }
        }

        if (!this.requiredChecksPassed(pullRequest)) {
            reasons.push(
                "One or more required status checks have not passed."
            );
        }

        return new PolicyResult(reasons.length === 0, reasons);
    }
}

// ============================================================================
// 7. CODE OWNERSHIP
// ============================================================================

class CodeOwnerRule {
    constructor(pattern, owners) {
        this.pattern = pattern;
        this.owners = new Set(owners);
    }
}

function pathMatches(path, pattern) {
    if (pattern === "*") {
        return true;
    }

    if (pattern.endsWith("/")) {
        return path.startsWith(pattern);
    }

    if (pattern.startsWith("*.")) {
        return path.endsWith(pattern.slice(1));
    }

    return path === pattern;
}

function findPotentialCodeOwners(changedPaths, rules) {
    const owners = new Set();

    for (const path of changedPaths) {
        for (const rule of rules) {
            if (pathMatches(path, rule.pattern)) {
                for (const owner of rule.owners) {
                    owners.add(owner);
                }
            }
        }
    }

    return owners;
}

// ============================================================================
// 8. SECURITY CHECK
// ============================================================================

const SECRET_PATTERNS = [
    /AKIA[0-9A-Z]{16}/,
    /-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----/,
    /password\s*=\s*["'][^"']+["']/i,
];

function scanForObviousSecrets(files) {
    const findings = [];

    for (const [filename, content] of Object.entries(files)) {
        const lines = content.split("\n");

        lines.forEach((line, index) => {
            for (const pattern of SECRET_PATTERNS) {
                if (pattern.test(line)) {
                    findings.push({
                        filename,
                        lineNumber: index + 1,
                        severity: "high",
                        message:
                            "Potential credential or private key detected.",
                    });
                }
            }
        });
    }

    return findings;
}

// ============================================================================
// 9. BUILD FEATURE COMMIT
// ============================================================================

function buildFeatureCommit(baseCommit, author, options = {}) {
    const secure = options.secure ?? true;
    const broken = options.broken ?? false;

    const files = { ...baseCommit.files };

    files["payment.js"] = secure
        ? [
              "function calculateTotal(amount, tax) {",
              "    if (amount < 0 || tax < 0) {",
              "        throw new Error('amount and tax must be non-negative');",
              "    }",
              "    return amount + tax;",
              "}",
              "",
          ].join("\n")
        : [
              "const API_PASSWORD = 'hard-coded-secret';",
              "",
              "function calculateTotal(amount, tax) {",
              "    return amount + tax;",
              "}",
              "",
          ].join("\n");

    if (broken) {
        files["payment.js"] += "const INTENTIONALLY_BROKEN = true;\n";
    }

    files["test/payment.test.js"] = [
        "function testCalculateTotal() {",
        "    if (calculateTotal(100, 10) !== 110) {",
        "        throw new Error('calculateTotal failed');",
        "    }",
        "}",
        "",
        "function testNegativeAmount() {",
        "    let failed = false;",
        "    try {",
        "        calculateTotal(-1, 10);",
        "    } catch (error) {",
        "        failed = true;",
        "    }",
        "    if (!failed) throw new Error('negative amount accepted');",
        "}",
        "",
    ].join("\n");

    return Commit.create(
        author,
        "Validate payment totals",
        files
    );
}

// ============================================================================
// 10. COMPLETE WORKFLOW
// ============================================================================

function createPullRequest(repository, number, author) {
    const base = repository.branches.get("main").head;

    const branch = repository.createBranch(
        "feature/payment-validation",
        "main"
    );

    const featureCommit = buildFeatureCommit(base, author);

    repository.updateBranch(branch.name, featureCommit);

    return new PullRequest({
        number,
        title: "Validate payment totals",
        author,
        baseBranch: "main",
        headBranch: branch.name,
        baseCommitId: base.id,
        headCommit: featureCommit,
    });
}

function demonstrateCompleteWorkflow() {
    console.log("\n" + "=".repeat(78));
    console.log("1. COMPLETE PULL-REQUEST WORKFLOW");
    console.log("=".repeat(78));

    const repository = createDemoRepository();

    const pullRequest = createPullRequest(
        repository,
        42,
        "alice"
    );

    console.log(`PR #${pullRequest.number}: ${pullRequest.title}`);
    console.log(`Base branch: ${pullRequest.baseBranch}`);
    console.log(`Head branch: ${pullRequest.headBranch}`);
    console.log(`HEAD commit: ${pullRequest.headCommitId}`);

    console.log("\nReview diff:");
    console.log(
        generateDiff(
            repository.branches.get("main").head,
            pullRequest.headCommit
        )
    );

    pullRequest.reviews.push(
        new Review({
            reviewer: "bob",
            state: ReviewState.APPROVED,
            commitId: pullRequest.headCommitId,
            comment: "Implementation and tests look correct.",
        })
    );

    pullRequest.comments.push(
        new ReviewComment({
            reviewer: "bob",
            filename: "payment.js",
            lineNumber: 2,
            body: "Please validate negative values.",
            resolved: true,
        })
    );

    pullRequest.statusChecks.push(
        runUnitTests(pullRequest.headCommit),
        runLint(pullRequest.headCommit)
    );

    const policy = new BranchProtectionPolicy({
        protectedBranch: "main",
        requiredApprovals: 1,
        requiredStatusChecks: ["unit-tests", "lint"],
        dismissStaleApprovals: true,
        requireConversationResolution: true,
        requireUpToDateBranch: true,
        allowForcePush: false,
        allowDeletions: false,
    });

    const engine = new PullRequestPolicyEngine(policy);

    const result = engine.evaluate(
        pullRequest,
        repository.branches.get("main").head.id
    );

    console.log("\nPolicy result:");
    console.log(result.toString());

    if (result.allowed) {
        pullRequest.merged = true;
        repository.updateBranch("main", pullRequest.headCommit);
        console.log("\nMerge completed.");
    }
}

// ============================================================================
// 11. STALE APPROVAL DEMONSTRATION
// ============================================================================

function demonstrateStaleApproval() {
    console.log("\n" + "=".repeat(78));
    console.log("2. STALE APPROVALS");
    console.log("=".repeat(78));

    const repository = createDemoRepository();
    const pullRequest = createPullRequest(
        repository,
        43,
        "alice"
    );

    const approvedCommit = pullRequest.headCommitId;

    pullRequest.reviews.push(
        new Review({
            reviewer: "bob",
            state: ReviewState.APPROVED,
            commitId: approvedCommit,
        })
    );

    console.log(`Approved commit: ${approvedCommit}`);

    const modifiedFiles = {
        ...pullRequest.headCommit.files,
        "README.md":
            pullRequest.headCommit.files["README.md"] +
            "\nUpdated documentation.\n",
    };

    pullRequest.headCommit = Commit.create(
        "alice",
        "Update documentation",
        modifiedFiles
    );

    console.log(`New commit: ${pullRequest.headCommitId}`);

    const policy = new BranchProtectionPolicy({
        requiredApprovals: 1,
        requiredStatusChecks: [],
        requireConversationResolution: false,
        requireUpToDateBranch: false,
        dismissStaleApprovals: true,
    });

    const result = new PullRequestPolicyEngine(policy).evaluate(
        pullRequest,
        repository.branches.get("main").head.id
    );

    console.log(result.toString());
}

// ============================================================================
// 12. ASYNCHRONOUS CI
// ============================================================================

function runAsynchronousCheck(name, commit, delay, shouldPass = true) {
    return new Promise((resolve) => {
        setTimeout(() => {
            resolve(
                new StatusCheck({
                    name,
                    passed: shouldPass,
                    commitId: commit.id,
                })
            );
        }, delay);
    });
}

async function demonstrateAsyncCI() {
    console.log("\n" + "=".repeat(78));
    console.log("3. ASYNCHRONOUS CI CHECKS");
    console.log("=".repeat(78));

    const repository = createDemoRepository();
    const pullRequest = createPullRequest(
        repository,
        44,
        "alice"
    );

    console.log("Starting independent CI jobs...");

    /*
     * Promise.all models parallel CI jobs. In a real CI system these jobs may
     * execute on separate runners or workers.
     */
    const checks = await Promise.all([
        runAsynchronousCheck(
            "unit-tests",
            pullRequest.headCommit,
            100,
            true
        ),
        runAsynchronousCheck(
            "lint",
            pullRequest.headCommit,
            50,
            true
        ),
        runAsynchronousCheck(
            "security-scan",
            pullRequest.headCommit,
            75,
            true
        ),
    ]);

    pullRequest.statusChecks.push(...checks);

    for (const check of checks) {
        console.log(
            `${check.name}: ${check.passed ? "PASS" : "FAIL"}`
        );
    }
}

// ============================================================================
// 13. CODE OWNERSHIP
// ============================================================================

function demonstrateCodeOwners() {
    console.log("\n" + "=".repeat(78));
    console.log("4. CODE OWNERSHIP");
    console.log("=".repeat(78));

    const rules = [
        new CodeOwnerRule(
            "payment.js",
            ["alice", "security-team"]
        ),
        new CodeOwnerRule(
            "*.md",
            ["documentation-team"]
        ),
    ];

    const changedPaths = [
        "payment.js",
        "README.md",
    ];

    const owners = findPotentialCodeOwners(
        changedPaths,
        rules
    );

    console.log("Changed paths:");
    for (const path of changedPaths) {
        console.log(`  - ${path}`);
    }

    console.log("\nPotential owners:");
    for (const owner of owners) {
        console.log(`  - ${owner}`);
    }
}

// ============================================================================
// 14. SECURITY REVIEW
// ============================================================================

function demonstrateSecurityReview() {
    console.log("\n" + "=".repeat(78));
    console.log("5. SECURITY REVIEW");
    console.log("=".repeat(78));

    const repository = createDemoRepository();
    const base = repository.branches.get("main").head;

    const insecureCommit = buildFeatureCommit(
        base,
        "alice",
        { secure: false }
    );

    const findings = scanForObviousSecrets(
        insecureCommit.files
    );

    if (findings.length === 0) {
        console.log("No obvious secrets detected.");
        return;
    }

    for (const finding of findings) {
        console.log(
            `${finding.severity.toUpperCase()} ` +
            `${finding.filename}:${finding.lineNumber} ` +
            `${finding.message}`
        );
    }

    console.log(
        "\nThis scanner is intentionally simple and should not be treated as "
        + "a complete production secret-detection system."
    );
}

// ============================================================================
// 15. DRAFT PR
// ============================================================================

function demonstrateDraftPullRequest() {
    console.log("\n" + "=".repeat(78));
    console.log("6. DRAFT PULL REQUEST");
    console.log("=".repeat(78));

    const repository = createDemoRepository();
    const pullRequest = createPullRequest(
        repository,
        45,
        "alice"
    );

    pullRequest.draft = true;

    pullRequest.reviews.push(
        new Review({
            reviewer: "bob",
            state: ReviewState.APPROVED,
            commitId: pullRequest.headCommitId,
        })
    );

    pullRequest.statusChecks.push(
        runUnitTests(pullRequest.headCommit),
        runLint(pullRequest.headCommit)
    );

    const policy = new BranchProtectionPolicy({
        requiredApprovals: 1,
        requiredStatusChecks: ["unit-tests", "lint"],
        requireConversationResolution: false,
        requireUpToDateBranch: true,
    });

    const result = new PullRequestPolicyEngine(policy).evaluate(
        pullRequest,
        repository.branches.get("main").head.id
    );

    console.log(result.toString());
}

// ============================================================================
// 16. REVIEW REQUESTING CHANGES
// ============================================================================

function demonstrateChangesRequested() {
    console.log("\n" + "=".repeat(78));
    console.log("7. CHANGES REQUESTED");
    console.log("=".repeat(78));

    const repository = createDemoRepository();
    const pullRequest = createPullRequest(
        repository,
        46,
        "alice"
    );

    pullRequest.reviews.push(
        new Review({
            reviewer: "bob",
            state: ReviewState.CHANGES_REQUESTED,
            commitId: pullRequest.headCommitId,
            comment: "Please add validation tests.",
        })
    );

    pullRequest.statusChecks.push(
        runUnitTests(pullRequest.headCommit),
        runLint(pullRequest.headCommit)
    );

    const policy = new BranchProtectionPolicy({
        requiredApprovals: 1,
        requiredStatusChecks: ["unit-tests", "lint"],
        requireConversationResolution: false,
    });

    const result = new PullRequestPolicyEngine(policy).evaluate(
        pullRequest,
        repository.branches.get("main").head.id
    );

    console.log(result.toString());
}

// ============================================================================
// 17. SIMPLE ASSERTION TESTS
// ============================================================================

function assert(condition, message) {
    if (!condition) {
        throw new Error(`Assertion failed: ${message}`);
    }
}

function buildReadyPullRequest() {
    const repository = createDemoRepository();
    const pullRequest = createPullRequest(
        repository,
        999,
        "alice"
    );

    pullRequest.reviews.push(
        new Review({
            reviewer: "bob",
            state: ReviewState.APPROVED,
            commitId: pullRequest.headCommitId,
        })
    );

    pullRequest.statusChecks.push(
        runUnitTests(pullRequest.headCommit),
        runLint(pullRequest.headCommit)
    );

    return { repository, pullRequest };
}

function runTests() {
    console.log("\n" + "=".repeat(78));
    console.log("8. POLICY TESTS");
    console.log("=".repeat(78));

    let passed = 0;
    let failed = 0;

    const tests = [
        {
            name: "ready PR can merge",
            run() {
                const { repository, pullRequest } =
                    buildReadyPullRequest();

                const policy = new BranchProtectionPolicy();

                const result =
                    new PullRequestPolicyEngine(policy).evaluate(
                        pullRequest,
                        repository.branches.get("main").head.id
                    );

                assert(result.allowed, "ready PR should be mergeable");
            },
        },
        {
            name: "missing approval blocks merge",
            run() {
                const repository = createDemoRepository();
                const pullRequest = createPullRequest(
                    repository,
                    1000,
                    "alice"
                );

                pullRequest.statusChecks.push(
                    runUnitTests(pullRequest.headCommit),
                    runLint(pullRequest.headCommit)
                );

                const result =
                    new PullRequestPolicyEngine(
                        new BranchProtectionPolicy()
                    ).evaluate(
                        pullRequest,
                        repository.branches.get("main").head.id
                    );

                assert(
                    !result.allowed,
                    "missing approval should block"
                );
            },
        },
        {
            name: "failed status check blocks merge",
            run() {
                const { repository, pullRequest } =
                    buildReadyPullRequest();

                pullRequest.statusChecks = [
                    new StatusCheck({
                        name: "unit-tests",
                        passed: false,
                        commitId: pullRequest.headCommitId,
                    }),
                    runLint(pullRequest.headCommit),
                ];

                const result =
                    new PullRequestPolicyEngine(
                        new BranchProtectionPolicy()
                    ).evaluate(
                        pullRequest,
                        repository.branches.get("main").head.id
                    );

                assert(
                    !result.allowed,
                    "failed check should block"
                );
            },
        },
        {
            name: "unresolved conversation blocks merge",
            run() {
                const { repository, pullRequest } =
                    buildReadyPullRequest();

                pullRequest.comments.push(
                    new ReviewComment({
                        reviewer: "bob",
                        filename: "payment.js",
                        lineNumber: 2,
                        body: "Please explain this condition.",
                        resolved: false,
                    })
                );

                const result =
                    new PullRequestPolicyEngine(
                        new BranchProtectionPolicy()
                    ).evaluate(
                        pullRequest,
                        repository.branches.get("main").head.id
                    );

                assert(
                    !result.allowed,
                    "unresolved conversation should block"
                );
            },
        },
        {
            name: "author approval is not independent",
            run() {
                const repository = createDemoRepository();
                const pullRequest = createPullRequest(
                    repository,
                    1001,
                    "alice"
                );

                pullRequest.reviews.push(
                    new Review({
                        reviewer: "alice",
                        state: ReviewState.APPROVED,
                        commitId: pullRequest.headCommitId,
                    })
                );

                pullRequest.statusChecks.push(
                    runUnitTests(pullRequest.headCommit),
                    runLint(pullRequest.headCommit)
                );

                const result =
                    new PullRequestPolicyEngine(
                        new BranchProtectionPolicy()
                    ).evaluate(
                        pullRequest,
                        repository.branches.get("main").head.id
                    );

                assert(
                    !result.allowed,
                    "author approval should not count"
                );
            },
        },
        {
            name: "stale approval does not count",
            run() {
                const repository = createDemoRepository();
                const pullRequest = createPullRequest(
                    repository,
                    1002,
                    "alice"
                );

                pullRequest.reviews.push(
                    new Review({
                        reviewer: "bob",
                        state: ReviewState.APPROVED,
                        commitId: pullRequest.headCommitId,
                    })
                );

                pullRequest.headCommit = Commit.create(
                    "alice",
                    "New change after review",
                    {
                        ...pullRequest.headCommit.files,
                        "README.md":
                            "# Payment Service\nUpdated.\n",
                    }
                );

                const policy = new BranchProtectionPolicy({
                    requiredStatusChecks: [],
                    requireConversationResolution: false,
                });

                const result =
                    new PullRequestPolicyEngine(policy).evaluate(
                        pullRequest,
                        repository.branches.get("main").head.id
                    );

                assert(
                    !result.allowed,
                    "stale approval should not count"
                );
            },
        },
    ];

    for (const test of tests) {
        try {
            test.run();
            passed += 1;
            console.log(`PASS: ${test.name}`);
        } catch (error) {
            failed += 1;
            console.log(`FAIL: ${test.name}`);
            console.log(`      ${error.message}`);
        }
    }

    console.log(
        `\nTests: ${passed + failed}, Passed: ${passed}, Failed: ${failed}`
    );
}

// ============================================================================
// 18. EDGE CASES
// ============================================================================

function demonstrateEdgeCases() {
    console.log("\n" + "=".repeat(78));
    console.log("9. IMPORTANT EDGE CASES");
    console.log("=".repeat(78));

    const cases = [
        [
            "Merge conflict",
            "A PR may satisfy review rules but still require conflict resolution.",
        ],
        [
            "New commit after approval",
            "The approval may become stale depending on policy.",
        ],
        [
            "Failed CI after approval",
            "Review approval does not override failed required checks.",
        ],
        [
            "Deleted branch",
            "Repository workflow must define what happens to the PR head.",
        ],
        [
            "Force push",
            "History can be rewritten, which complicates review traceability.",
        ],
        [
            "Binary file",
            "Text-oriented diff review may not adequately explain binary changes.",
        ],
        [
            "Renamed file",
            "Rename detection is more nuanced than simple delete/create semantics.",
        ],
        [
            "Draft PR",
            "A draft can be intentionally excluded from merge readiness.",
        ],
        [
            "Self approval",
            "A policy can require independent reviewers.",
        ],
    ];

    for (const [name, explanation] of cases) {
        console.log(`${name}: ${explanation}`);
    }
}

// ============================================================================
// 19. EXECUTION
// ============================================================================

async function main() {
    console.log("PULL REQUESTS, CODE REVIEW, APPROVALS, AND BRANCH PROTECTION");
    console.log("===============================================================");

    demonstrateCompleteWorkflow();
    demonstrateStaleApproval();
    await demonstrateAsyncCI();
    demonstrateCodeOwners();
    demonstrateSecurityReview();
    demonstrateDraftPullRequest();
    demonstrateChangesRequested();
    runTests();
    demonstrateEdgeCases();

    console.log("\n" + "=".repeat(78));
    console.log("EXECUTION COMPLETE");
    console.log("=".repeat(78));
    console.log(
        "Core workflow: branch -> pull request -> diff -> review -> checks -> " +
        "policy evaluation -> merge."
    );
}

main().catch((error) => {
    console.error("Fatal error:", error.message);
    process.exitCode = 1;
});
