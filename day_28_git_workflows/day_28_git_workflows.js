/*
 * Git Workflows: Feature Branches, GitHub Flow, and Trunk-Based Development
 *
 * This standalone JavaScript program models Git workflow concepts and provides
 * executable demonstrations of branch lifecycles, pull requests, quality
 * gates, conflicts, feature flags, integration policies, and CI design.
 *
 * Runtime: Node.js 18+ recommended.
 *
 * The program does not modify an actual repository unless a user intentionally
 * adapts the command examples for a real project.
 */

"use strict";

const readline = require("node:readline");

// =============================================================================
// 1. BASIC PRESENTATION HELPERS
// =============================================================================

function section(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function explain(lines) {
    console.log(lines.trim());
}

function printObject(object) {
    console.log(JSON.stringify(object, null, 2));
}

// =============================================================================
// 2. BASIC GIT CONCEPTS
// =============================================================================

function demonstrateGitBasics() {
    section("1. Git Workflow Fundamentals");

    explain(`
Git is a distributed version-control system.

A workflow defines how changes move from development to shared integration,
review, testing, release, and deployment.

Core terms:

  Repository:
      The Git-managed project and its history.

  Working tree:
      Files currently checked out on disk.

  Commit:
      A recorded snapshot of changes.

  Branch:
      A movable reference to a commit.

  Remote:
      Another repository location, often called origin.

  Fetch:
      Downloads remote objects and references without changing the current
      working tree.

  Pull:
      Usually fetches and integrates remote changes.

  Merge:
      Combines histories.

  Rebase:
      Replays commits onto another base and creates new commit identities.

  Pull request:
      A review and integration mechanism provided by hosting platforms.

A workflow is larger than a list of Git commands. It also includes review,
testing, branch protection, deployment, recovery, and team conventions.
`);

    const commands = [
        ["Create branch", "git switch -c feature/login"],
        ["Check status", "git status"],
        ["Stage changes", "git add ."],
        ["Commit", 'git commit -m "Add login validation"'],
        ["Fetch", "git fetch origin"],
        ["Push", "git push -u origin feature/login"],
        ["Switch", "git switch main"],
        ["Merge", "git merge feature/login"],
        ["Rebase", "git rebase main"]
    ];

    console.log("\nCommon commands:");
    for (const [purpose, command] of commands) {
        console.log(`${purpose.padEnd(18)} ${command}`);
    }
}

// =============================================================================
// 3. COMMIT AND BRANCH CLASSES
// =============================================================================

class Commit {
    constructor(id, message, author, parents = [], filesChanged = []) {
        this.id = id;
        this.message = message;
        this.author = author;
        this.parents = [...parents];
        this.filesChanged = [...filesChanged];
    }

    shortId() {
        return this.id.slice(0, 10);
    }
}

class Branch {
    constructor(name, head = "", protectedBranch = false) {
        this.name = name;
        this.head = head;
        this.protected = protectedBranch;
    }

    describe() {
        const protection = this.protected ? "protected" : "unprotected";
        return `${this.name} -> ${this.head.slice(0, 10)} (${protection})`;
    }
}

class CommitGraph {
    constructor() {
        this.commits = new Map();
        this.branches = new Map();
        this.sequence = 0;
    }

    newId() {
        this.sequence += 1;
        return `commit-${String(this.sequence).padStart(4, "0")}-abcdef`;
    }

    initialize() {
        if (this.branches.size > 0) {
            return;
        }

        this.branches.set(
            "main",
            new Branch("main", "", true)
        );

        this.createCommit(
            "main",
            "Initial project structure",
            "system",
            ["README.md"]
        );
    }

    createCommit(branchName, message, author, filesChanged = []) {
        const branch = this.branches.get(branchName);

        if (!branch) {
            throw new Error(`Unknown branch: ${branchName}`);
        }

        const id = this.newId();
        const parents = branch.head ? [branch.head] : [];

        const commit = new Commit(
            id,
            message,
            author,
            parents,
            filesChanged
        );

        this.commits.set(id, commit);
        branch.head = id;

        return commit;
    }

    createBranch(branchName, fromBranch = "main", protectedBranch = false) {
        if (this.branches.has(branchName)) {
            throw new Error(`Branch already exists: ${branchName}`);
        }

        const source = this.branches.get(fromBranch);

        if (!source) {
            throw new Error(`Source branch does not exist: ${fromBranch}`);
        }

        const branch = new Branch(
            branchName,
            source.head,
            protectedBranch
        );

        this.branches.set(branchName, branch);
        return branch;
    }

    ancestors(commitId) {
        if (!this.commits.has(commitId)) {
            throw new Error(`Unknown commit: ${commitId}`);
        }

        const found = new Set();
        const stack = [commitId];

        while (stack.length > 0) {
            const current = stack.pop();

            if (found.has(current)) {
                continue;
            }

            found.add(current);

            const commit = this.commits.get(current);
            stack.push(...commit.parents);
        }

        return found;
    }

    commonAncestor(firstId, secondId) {
        const first = this.ancestors(firstId);
        const second = this.ancestors(secondId);

        const common = [...first].filter((id) => second.has(id));

        if (common.length === 0) {
            return null;
        }

        // This model uses numeric commit sequence as a simple approximation.
        // Real Git uses graph-generation information and optimized traversal.
        return common.sort().at(-1);
    }

    print() {
        console.log("\nCommits:");

        for (const commit of this.commits.values()) {
            const parents = commit.parents.length
                ? commit.parents.map((id) => id.slice(0, 10)).join(", ")
                : "none";

            console.log(
                `${commit.shortId()} | ${commit.message} | parents: ${parents}`
            );
        }

        console.log("\nBranches:");

        for (const branch of this.branches.values()) {
            console.log(`  ${branch.describe()}`);
        }
    }
}

function demonstrateCommitGraph() {
    section("2. Commit Graph and Branch Mechanics");

    const graph = new CommitGraph();
    graph.initialize();

    graph.createCommit(
        "main",
        "Add application skeleton",
        "Developer B",
        ["src/app.js"]
    );

    graph.createBranch("feature/auth");

    graph.createCommit(
        "feature/auth",
        "Add authentication model",
        "Developer A",
        ["src/auth.js"]
    );

    graph.createCommit(
        "feature/auth",
        "Add authentication validation",
        "Developer A",
        ["src/auth.js", "tests/auth.test.js"]
    );

    graph.createCommit(
        "main",
        "Improve documentation",
        "Developer B",
        ["README.md"]
    );

    graph.print();

    const featureHead = graph.branches.get("feature/auth").head;
    const mainHead = graph.branches.get("main").head;

    const ancestor = graph.commonAncestor(featureHead, mainHead);

    console.log(
        "\nSimplified common ancestor:",
        ancestor ? ancestor.slice(0, 10) : "none"
    );
}

// =============================================================================
// 4. BRANCH NAME VALIDATION
// =============================================================================

class BranchNameValidator {
    static prefixes = new Set([
        "feature",
        "bugfix",
        "hotfix",
        "chore",
        "docs",
        "refactor",
        "test"
    ]);

    static validate(branchName) {
        if (typeof branchName !== "string" || branchName.length === 0) {
            return [false, "Branch name must be a non-empty string."];
        }

        if (["main", "master", "develop"].includes(branchName)) {
            return [true, "Shared branch."];
        }

        const slashIndex = branchName.indexOf("/");

        if (slashIndex === -1) {
            return [false, "Use a prefix such as feature/login."];
        }

        const prefix = branchName.slice(0, slashIndex);
        const name = branchName.slice(slashIndex + 1);

        if (!this.prefixes.has(prefix)) {
            return [false, `Unknown prefix: ${prefix}`];
        }

        if (!name) {
            return [false, "Branch description cannot be empty."];
        }

        if (name.startsWith("-") || name.endsWith("-")) {
            return [false, "Avoid leading or trailing hyphens."];
        }

        if (/\s/.test(name)) {
            return [false, "Spaces are discouraged in branch names."];
        }

        return [true, "Valid workflow branch name."];
    }
}

function demonstrateBranchValidation() {
    section("3. Branch Naming");

    const examples = [
        "feature/user-login",
        "bugfix/payment-timeout",
        "hotfix/security-patch",
        "feature/",
        "unknown/new-feature",
        "feature/user login",
        "main"
    ];

    for (const branch of examples) {
        const [valid, message] = BranchNameValidator.validate(branch);

        console.log(
            `${branch.padEnd(30)} ${valid ? "VALID" : "INVALID"}: ${message}`
        );
    }
}

// =============================================================================
// 5. FEATURE BRANCH WORKFLOW
// =============================================================================

function demonstrateFeatureBranchWorkflow() {
    section("4. Feature Branch Workflow");

    explain(`
A feature branch isolates a logical change from the shared integration branch.

Typical lifecycle:

  1. Update main.
  2. Create a short-lived branch.
  3. Implement a small change.
  4. Commit logical units.
  5. Push the branch.
  6. Open a pull request.
  7. Run automated checks.
  8. Review the change.
  9. Resolve feedback.
 10. Integrate into main.
 11. Delete the temporary branch.

The workflow reduces interference between unrelated changes, but branches that
remain open for a long time can diverge and create harder integration problems.
`);

    const graph = new CommitGraph();
    graph.initialize();
    graph.createBranch("feature/search");

    graph.createCommit(
        "feature/search",
        "Add search input",
        "Developer",
        ["search.js"]
    );

    graph.createCommit(
        "feature/search",
        "Validate search input",
        "Developer",
        ["search.js", "search.test.js"]
    );

    console.log(
        "Feature branch:",
        graph.branches.get("feature/search").describe()
    );

    console.log(
        "Main branch:",
        graph.branches.get("main").describe()
    );
}

// =============================================================================
// 6. PULL REQUEST MODEL
// =============================================================================

class PullRequest {
    constructor(number, source, target, title) {
        this.number = number;
        this.source = source;
        this.target = target;
        this.title = title;
        this.approvals = 0;
        this.checksPassed = false;
        this.merged = false;
        this.reviewComments = [];
    }

    addApproval() {
        this.approvals += 1;
    }

    addComment(comment) {
        this.reviewComments.push(comment);
    }

    isMergeable(requiredApprovals = 1) {
        return (
            !this.merged &&
            this.checksPassed &&
            this.approvals >= requiredApprovals
        );
    }

    merge(requiredApprovals = 1) {
        if (!this.isMergeable(requiredApprovals)) {
            throw new Error("Pull request does not satisfy merge requirements.");
        }

        this.merged = true;
    }
}

function demonstratePullRequest() {
    section("5. Pull Requests and GitHub Flow");

    const pullRequest = new PullRequest(
        101,
        "feature/search",
        "main",
        "Implement product search"
    );

    console.log(
        `PR #${pullRequest.number}: ${pullRequest.title}`
    );

    console.log(
        "Initially mergeable:",
        pullRequest.isMergeable()
    );

    pullRequest.checksPassed = true;
    pullRequest.addApproval();

    console.log(
        "After CI and review:",
        pullRequest.isMergeable()
    );

    pullRequest.merge();

    console.log(
        "Merged:",
        pullRequest.merged
    );
}

// =============================================================================
// 7. GITHUB FLOW
// =============================================================================

function demonstrateGitHubFlow() {
    section("6. GitHub Flow");

    explain(`
GitHub Flow is commonly centered on a primary branch and short-lived branches.

The general model is:

  main
    |
    +--> branch
           |
           +--> commits
           |
           +--> pull request
                    |
                    +--> CI
                    |
                    +--> review
                    |
                    +--> merge
                             |
                             +--> deployment

The workflow can be combined with branch protection, required status checks,
required reviews, feature flags, release tags, and automated deployment.

GitHub is a hosting and collaboration platform. GitHub Flow is a workflow
pattern. They are related but not the same concept.
`);
}

// =============================================================================
// 8. TRUNK-BASED DEVELOPMENT
// =============================================================================

function demonstrateTrunkBasedDevelopment() {
    section("7. Trunk-Based Development");

    explain(`
Trunk-based development emphasizes frequent integration into a shared trunk.

Two broad patterns are common:

  Direct integration:
      Small changes enter the trunk directly under the team's controls.

  Very short-lived branches:
      A developer creates a small branch, validates it, integrates it quickly,
      and removes it.

Supporting practices commonly include:

  - Fast automated tests.
  - Strong CI.
  - Small changes.
  - Feature flags.
  - Frequent synchronization.
  - Reliable deployment automation.

Trunk-based development does not inherently mean skipping review, testing,
security controls, or branch protection.
`);

    const graph = new CommitGraph();
    graph.initialize();

    for (let index = 1; index <= 4; index += 1) {
        graph.createCommit(
            "main",
            `Small trunk change ${index}`,
            "Developer",
            [`src/module-${index}.js`]
        );
    }

    console.log(
        "Current trunk:",
        graph.branches.get("main").head.slice(0, 10)
    );
}

// =============================================================================
// 9. WORKFLOW COMPARISON
// =============================================================================

function compareWorkflows() {
    section("8. Workflow Comparison");

    const rows = [
        [
            "Integration model",
            "Shared branch plus feature branches",
            "Main-centered PR workflow",
            "Frequent integration to trunk"
        ],
        [
            "Typical branch lifetime",
            "Short to medium",
            "Short",
            "Very short when branches are used"
        ],
        [
            "Review",
            "Often PR-based",
            "Central PR mechanism",
            "PR-based or direct, depending on policy"
        ],
        [
            "Integration frequency",
            "Varies",
            "Frequent",
            "Very frequent"
        ],
        [
            "Feature flags",
            "Useful",
            "Useful",
            "Often important"
        ],
        [
            "Typical challenge",
            "Branch divergence",
            "PR queue or weak controls",
            "Insufficient automation"
        ]
    ];

    const headers = [
        "Dimension",
        "Feature Branch",
        "GitHub Flow",
        "Trunk-Based"
    ];

    const widths = [24, 31, 31, 38];

    console.log(
        headers
            .map((header, index) => header.padEnd(widths[index]))
            .join(" | ")
    );

    console.log("-".repeat(135));

    for (const row of rows) {
        console.log(
            row
                .map((value, index) => value.padEnd(widths[index]))
                .join(" | ")
        );
    }

    explain(`
These are descriptive patterns rather than mutually exclusive categories.
A team can use short-lived feature branches, pull requests, strong CI, feature
flags, protected main, and continuous deployment simultaneously.
`);
}

// =============================================================================
// 10. MERGE, REBASE, AND SQUASH
// =============================================================================

function demonstrateIntegrationStrategies() {
    section("9. Merge, Rebase, and Squash");

    explain(`
Merge:
  Combines histories. A non-fast-forward merge can create a merge commit.

Rebase:
  Replays commits onto another base. Replayed commits receive new identities.

Squash:
  Combines multiple commits into a smaller logical history during integration.

Fast-forward:
  The target reference moves forward because it is already an ancestor of the
  source branch.

Conflict:
  Git cannot automatically determine a safe combination of competing changes.

A key safety rule is to understand who depends on a commit before rewriting
history. A rebase changes commit identities.
`);

    const strategies = [
        {
            name: "merge",
            preservesBranchStructure: true,
            rewritesExistingCommits: false
        },
        {
            name: "rebase",
            preservesBranchStructure: false,
            rewritesExistingCommits: true
        },
        {
            name: "squash",
            preservesBranchStructure: false,
            rewritesLogicalHistory: true
        }
    ];

    printObject(strategies);
}

// =============================================================================
// 11. CONFLICT DETECTION
// =============================================================================

function detectSimpleConflict(base, ours, theirs) {
    if (
        base.path !== ours.path ||
        ours.path !== theirs.path
    ) {
        throw new Error("All file paths must be identical.");
    }

    const oursChanged = ours.content !== base.content;
    const theirsChanged = theirs.content !== base.content;

    return (
        oursChanged &&
        theirsChanged &&
        ours.content !== theirs.content
    );
}

function demonstrateConflict() {
    section("10. Merge Conflicts");

    const base = {
        path: "config.txt",
        content: "timeout=30\n"
    };

    const ours = {
        path: "config.txt",
        content: "timeout=60\n"
    };

    const theirs = {
        path: "config.txt",
        content: "timeout=120\n"
    };

    console.log("Base:", JSON.stringify(base.content));
    console.log("Ours:", JSON.stringify(ours.content));
    console.log("Theirs:", JSON.stringify(theirs.content));
    console.log(
        "Conflict:",
        detectSimpleConflict(base, ours, theirs)
    );

    explain(`
In a real repository, a developer should inspect the conflicting context,
understand the intended behavior, edit the file, test it, and then continue
the merge or rebase.

Useful commands include:

  git status
  git diff
  git add <file>
  git merge --continue
  git rebase --continue
  git merge --abort
  git rebase --abort
`);
}

// =============================================================================
// 12. FEATURE FLAGS
// =============================================================================

class FeatureFlagService {
    constructor(initialFlags = {}) {
        this.flags = new Map(Object.entries(initialFlags));
    }

    enabled(flagName, defaultValue = false) {
        return this.flags.has(flagName)
            ? this.flags.get(flagName)
            : defaultValue;
    }

    set(flagName, enabled) {
        if (typeof enabled !== "boolean") {
            throw new TypeError("Feature flag value must be boolean.");
        }

        this.flags.set(flagName, enabled);
    }
}

function demonstrateFeatureFlags() {
    section("11. Feature Flags");

    const flags = new FeatureFlagService({
        "new-search": false
    });

    console.log(
        "New search enabled:",
        flags.enabled("new-search")
    );

    flags.set("new-search", true);

    console.log(
        "New search enabled after change:",
        flags.enabled("new-search")
    );

    explain(`
Feature flags can separate code integration from user-visible activation.

They are not free. Long-lived flags increase conditional complexity, require
ownership, and can become difficult to reason about. Production flags should
have access control, observability, a removal plan, and appropriate tests.
`);
}

// =============================================================================
// 13. QUALITY GATES
// =============================================================================

class QualityGate {
    constructor({
        testsPassed = false,
        lintPassed = false,
        securityScanPassed = false,
        requiredApprovals = 1,
        actualApprovals = 0
    } = {}) {
        this.testsPassed = testsPassed;
        this.lintPassed = lintPassed;
        this.securityScanPassed = securityScanPassed;
        this.requiredApprovals = requiredApprovals;
        this.actualApprovals = actualApprovals;
    }

    passes() {
        return (
            this.testsPassed &&
            this.lintPassed &&
            this.securityScanPassed &&
            this.actualApprovals >= this.requiredApprovals
        );
    }
}

function demonstrateQualityGates() {
    section("12. CI and Pull Request Quality Gates");

    const gate = new QualityGate({
        testsPassed: true,
        lintPassed: true,
        securityScanPassed: true,
        requiredApprovals: 2,
        actualApprovals: 1
    });

    console.log("Before second approval:", gate.passes());

    gate.actualApprovals = 2;

    console.log("After second approval:", gate.passes());

    explain(`
Common automated gates include:

  - Unit tests.
  - Integration tests.
  - Formatting checks.
  - Static analysis.
  - Dependency validation.
  - Security scanning.
  - Build verification.
  - Artifact validation.

A required check should fail when the requirement is not satisfied. A warning
should not silently substitute for a mandatory correctness or security gate.
`);
}

// =============================================================================
// 14. BRANCH POLICY
// =============================================================================

class BranchPolicy {
    constructor({
        maximumAgeDays,
        requirePullRequest,
        requireCI,
        deleteAfterMerge,
        requireLinearHistory = false
    }) {
        this.maximumAgeDays = maximumAgeDays;
        this.requirePullRequest = requirePullRequest;
        this.requireCI = requireCI;
        this.deleteAfterMerge = deleteAfterMerge;
        this.requireLinearHistory = requireLinearHistory;
    }

    validate() {
        const errors = [];

        if (!Number.isInteger(this.maximumAgeDays) || this.maximumAgeDays <= 0) {
            errors.push("maximumAgeDays must be a positive integer.");
        }

        if (!this.requirePullRequest) {
            errors.push("Pull-request review is disabled.");
        }

        if (!this.requireCI) {
            errors.push("CI validation is disabled.");
        }

        return errors;
    }
}

function demonstrateBranchPolicy() {
    section("13. Workflow Policy");

    const policy = new BranchPolicy({
        maximumAgeDays: 3,
        requirePullRequest: true,
        requireCI: true,
        deleteAfterMerge: true,
        requireLinearHistory: false
    });

    console.log(
        "Policy validation:",
        policy.validate().length === 0 ? "valid" : policy.validate()
    );

    printObject(policy);
}

// =============================================================================
// 15. CI PIPELINE
// =============================================================================

function createCIPipeline() {
    return [
        "Fetch repository state",
        "Install dependencies",
        "Validate formatting",
        "Run static analysis",
        "Run unit tests",
        "Run integration tests",
        "Run security checks",
        "Build artifact",
        "Publish test results",
        "Deploy to an approved environment"
    ];
}

function demonstrateCIPipeline() {
    section("14. CI Pipeline Design");

    createCIPipeline().forEach(
        (stage, index) => console.log(
            `${String(index + 1).padStart(2, "0")}. ${stage}`
        )
    );

    explain(`
CI feedback has a human productivity cost. Fast checks should normally run
before slower checks when their results can prevent unnecessary work.

Pipelines should also produce reproducible diagnostics. A developer should be
able to identify the failed stage, inspect relevant output, and reproduce the
failure locally where practical.
`);
}

// =============================================================================
// 16. ASYNCHRONOUS CI SIMULATION
// =============================================================================

function delay(milliseconds) {
    return new Promise((resolve) => {
        setTimeout(resolve, milliseconds);
    });
}

async function runCICheck(name, duration, shouldPass = true) {
    console.log(`Starting: ${name}`);

    await delay(duration);

    if (!shouldPass) {
        throw new Error(`${name} failed.`);
    }

    console.log(`Passed: ${name}`);
    return name;
}

async function demonstrateAsyncCI() {
    section("15. Asynchronous CI Behavior");

    explain(`
JavaScript is useful for demonstrating event-driven and asynchronous workflow
automation. A real CI system may execute independent checks concurrently.

Promise.all rejects when one promise rejects, while individual tasks may still
have already started. Production orchestration may require explicit cancellation,
cleanup, retry, and artifact handling.
`);

    const checks = [
        runCICheck("Unit tests", 80),
        runCICheck("Lint", 50),
        runCICheck("Security scan", 100)
    ];

    const results = await Promise.all(checks);

    console.log("Completed checks:", results.join(", "));
}

// =============================================================================
// 17. ASYNC FAILURE HANDLING
// =============================================================================

async function demonstrateAsyncFailureHandling() {
    section("16. CI Failure Handling");

    const checks = [
        runCICheck("Unit tests", 40, true),
        runCICheck("Integration tests", 70, false),
        runCICheck("Static analysis", 30, true)
    ];

    const results = await Promise.allSettled(checks);

    for (const result of results) {
        if (result.status === "fulfilled") {
            console.log("SUCCESS:", result.value);
        } else {
            console.log("FAILURE:", result.reason.message);
        }
    }

    explain(`
Promise.allSettled is useful when an orchestration layer needs the outcome of
every independent check instead of stopping at the first rejected promise.
`);
}

// =============================================================================
// 18. RELEASE AND HOTFIX MODEL
// =============================================================================

class Release {
    constructor(version, commitId) {
        this.version = version;
        this.commitId = commitId;
        this.createdAt = new Date().toISOString();
    }

    tagName() {
        return `v${this.version}`;
    }
}

class Hotfix {
    constructor(issue, sourceCommit) {
        this.issue = issue;
        this.sourceCommit = sourceCommit;
        this.status = "open";
    }

    close() {
        this.status = "closed";
    }
}

function demonstrateReleaseFlow() {
    section("17. Releases and Hotfixes");

    const release = new Release("2.4.0", "commit-0042-abcdef");
    console.log("Release tag:", release.tagName());
    console.log("Release commit:", release.commitId);

    const hotfix = new Hotfix(
        "Production timeout defect",
        release.commitId
    );

    console.log("Hotfix status:", hotfix.status);

    hotfix.close();

    console.log("Hotfix status after validation:", hotfix.status);

    explain(`
A release process must define which commit becomes production, how the release
is identified, how deployment is validated, and how a failure is recovered.

A hotfix strategy must also address whether the correction needs to be
propagated into another active development line.
`);
}

// =============================================================================
// 19. SECURITY
// =============================================================================

function demonstrateSecurity() {
    section("18. Security Considerations");

    const securityRules = [
        "Never commit passwords or API tokens.",
        "Protect the primary branch.",
        "Review changes to CI configuration carefully.",
        "Limit who can bypass repository protections.",
        "Avoid exposing secrets to untrusted pull-request code.",
        "Use short-lived credentials where practical.",
        "Rotate credentials after accidental exposure.",
        "Validate dependencies and generated artifacts.",
        "Audit privileged repository actions."
    ];

    for (const rule of securityRules) {
        console.log(`- ${rule}`);
    }

    explain(`
Removing a secret from the newest commit does not necessarily remove it from
repository history. A credential that has been exposed should generally be
considered compromised until it has been rotated or revoked.

CI configuration deserves special attention because workflow files can control
build credentials, deployment credentials, permissions, and release behavior.
`);
}

// =============================================================================
// 20. MONOREPO PATH ANALYSIS
// =============================================================================

function affectedComponents(changedFiles) {
    const components = new Set();

    for (const file of changedFiles) {
        const parts = file.split("/");

        if (parts[0] === "services" && parts.length >= 2) {
            components.add(parts[1]);
        }
    }

    return [...components].sort();
}

function demonstrateMonorepo() {
    section("19. Monorepo and Path-Based CI");

    const changedFiles = [
        "services/payments/payment.js",
        "services/payments/payment.test.js",
        "services/accounts/account.js",
        "docs/payments.md"
    ];

    console.log("Changed files:");

    for (const file of changedFiles) {
        console.log(`  ${file}`);
    }

    console.log(
        "Affected service components:",
        affectedComponents(changedFiles)
    );

    explain(`
A monorepo can use changed-path analysis to avoid rebuilding unrelated
components. Real systems usually combine this with dependency graphs because
one component can affect another even when no file in the second component
changed directly.
`);
}

// =============================================================================
// 21. DATABASE MIGRATION
// =============================================================================

function demonstrateDatabaseMigration() {
    section("20. Database Migration and Workflow Design");

    const migrationStages = [
        "Expand schema with backward-compatible capability",
        "Deploy code that supports old and new representations",
        "Migrate existing data",
        "Switch application behavior",
        "Verify production behavior",
        "Remove obsolete schema later"
    ];

    migrationStages.forEach(
        (stage, index) => console.log(`${index + 1}. ${stage}`)
    );

    explain(`
The expand-and-contract pattern separates incompatible changes into stages.
Git branch strategy alone cannot make a database migration safe because
database state persists independently of source-code history.

Rollback planning must account for both code and data.
`);
}

// =============================================================================
// 22. OPERATIONAL METRICS
// =============================================================================

class DeliveryMetrics {
    constructor({
        deploymentFrequency,
        leadTimeHours,
        changeFailureRate,
        recoveryTimeHours
    }) {
        this.deploymentFrequency = deploymentFrequency;
        this.leadTimeHours = leadTimeHours;
        this.changeFailureRate = changeFailureRate;
        this.recoveryTimeHours = recoveryTimeHours;
    }

    validate() {
        if (this.deploymentFrequency < 0) {
            throw new RangeError("Deployment frequency cannot be negative.");
        }

        if (this.leadTimeHours < 0) {
            throw new RangeError("Lead time cannot be negative.");
        }

        if (
            this.changeFailureRate < 0 ||
            this.changeFailureRate > 1
        ) {
            throw new RangeError(
                "Change failure rate must be between 0 and 1."
            );
        }

        if (this.recoveryTimeHours < 0) {
            throw new RangeError("Recovery time cannot be negative.");
        }
    }
}

function demonstrateDeliveryMetrics() {
    section("21. Delivery Metrics");

    const metrics = new DeliveryMetrics({
        deploymentFrequency: 12,
        leadTimeHours: 8,
        changeFailureRate: 0.05,
        recoveryTimeHours: 2
    });

    metrics.validate();

    printObject(metrics);

    explain(`
Metrics need precise definitions, collection periods, and consistent
measurement methods. A single metric does not describe every property of a
software delivery system.
`);
}

// =============================================================================
// 23. RECOVERY COMMANDS
// =============================================================================

function demonstrateDebugging() {
    section("22. Debugging Workflow State");

    const commands = [
        ["git status", "Inspect current state and active operations."],
        ["git branch --show-current", "Confirm current branch."],
        [
            "git log --oneline --decorate --graph --all",
            "Inspect recent graph structure."
        ],
        ["git remote -v", "Inspect configured remotes."],
        ["git fetch --prune", "Refresh remote references."],
        ["git diff", "Inspect unstaged changes."],
        ["git diff --staged", "Inspect staged changes."],
        ["git reflog", "Inspect local reference movement."]
    ];

    for (const [command, purpose] of commands) {
        console.log(`${command.padEnd(50)} ${purpose}`);
    }

    explain(`
Reflog can help locate previous local branch positions after operations such
as reset or rebase. Recovery is safer when the developer first stops changing
repository state and identifies the exact current state.
`);
}

// =============================================================================
// 24. REBASE SAFETY
// =============================================================================

function demonstrateRebaseSafety() {
    section("23. Rebase Safety");

    explain(`
Suppose the history is:

    A -- B -- C      main
          \
           D -- E    feature

Rebasing the feature onto C conceptually creates:

    A -- B -- C -- D' -- E'

D' and E' are new commits. They are not the original D and E.

When updating a remote branch after a deliberate rebase, a safer force-update
form is often:

    git push --force-with-lease

It checks that the remote reference has not moved unexpectedly since the local
repository last observed it.

History rewriting remains a coordination decision, especially for shared
branches.
`);
}

// =============================================================================
// 25. WORKFLOW POLICY EVALUATION
// =============================================================================

function validateProjectCharacteristics(characteristics) {
    const allowed = {
        deploymentFrequency: new Set(["low", "medium", "high"]),
        teamSize: new Set(["small", "medium", "large"]),
        complianceLevel: new Set(["low", "medium", "high"]),
        ciMaturity: new Set(["low", "medium", "high"]),
        releaseCadence: new Set(["manual", "scheduled", "continuous"])
    };

    const errors = [];

    for (const [field, values] of Object.entries(allowed)) {
        if (!values.has(characteristics[field])) {
            errors.push(
                `${field} must be one of: ${[...values].join(", ")}`
            );
        }
    }

    return errors;
}

function demonstrateDesignFactors() {
    section("24. Workflow Design Factors");

    const characteristics = {
        deploymentFrequency: "high",
        teamSize: "medium",
        complianceLevel: "medium",
        ciMaturity: "high",
        releaseCadence: "continuous"
    };

    const errors = validateProjectCharacteristics(characteristics);

    console.log(
        "Validation:",
        errors.length === 0 ? "valid" : errors
    );

    printObject(characteristics);

    explain(`
Workflow design depends on context.

Relevant factors include deployment frequency, team size, CI maturity,
compliance requirements, release cadence, architecture, production risk,
ownership boundaries, and required auditability.

These factors describe engineering constraints. They do not produce a universal
workflow choice by themselves.
`);
}

// =============================================================================
// 26. INTERACTIVE WORKFLOW SIMULATION
// =============================================================================

class WorkflowSimulator {
    constructor() {
        this.currentBranch = "main";
        this.branches = new Set(["main"]);
        this.commits = [];
        this.pullRequests = [];
    }

    createBranch(name) {
        if (this.branches.has(name)) {
            throw new Error(`Branch already exists: ${name}`);
        }

        const [valid, message] = BranchNameValidator.validate(name);

        if (!valid) {
            throw new Error(message);
        }

        this.branches.add(name);
        this.currentBranch = name;
    }

    commit(message) {
        if (!message || !message.trim()) {
            throw new Error("Commit message cannot be empty.");
        }

        this.commits.push({
            branch: this.currentBranch,
            message: message.trim(),
            timestamp: new Date().toISOString()
        });
    }

    switchBranch(name) {
        if (!this.branches.has(name)) {
            throw new Error(`Branch does not exist: ${name}`);
        }

        this.currentBranch = name;
    }

    openPullRequest(title, target = "main") {
        if (!this.branches.has(this.currentBranch)) {
            throw new Error("Current branch does not exist.");
        }

        if (!this.branches.has(target)) {
            throw new Error(`Target branch does not exist: ${target}`);
        }

        if (this.currentBranch === target) {
            throw new Error("A branch cannot open a PR against itself.");
        }

        const pullRequest = new PullRequest(
            this.pullRequests.length + 1,
            this.currentBranch,
            target,
            title
        );

        this.pullRequests.push(pullRequest);
        return pullRequest;
    }

    status() {
        return {
            currentBranch: this.currentBranch,
            branches: [...this.branches].sort(),
            commitCount: this.commits.length,
            pullRequestCount: this.pullRequests.length
        };
    }
}

function demonstrateWorkflowSimulator() {
    section("25. Workflow Simulator");

    const simulator = new WorkflowSimulator();

    simulator.commit("Initial application structure");
    simulator.createBranch("feature/audit-log");
    simulator.commit("Add audit event model");
    simulator.commit("Validate audit events");

    const pullRequest = simulator.openPullRequest(
        "Add audit logging"
    );

    pullRequest.checksPassed = true;
    pullRequest.addApproval();

    console.log("Pull request mergeable:", pullRequest.isMergeable());

    if (pullRequest.isMergeable()) {
        pullRequest.merge();
    }

    printObject(simulator.status());
}

// =============================================================================
// 27. UNIT TESTS
// =============================================================================

function assert(condition, message) {
    if (!condition) {
        throw new Error(`Assertion failed: ${message}`);
    }
}

function runTests() {
    section("26. Automated Tests");

    const tests = [
        function branchNameTest() {
            const [valid] =
                BranchNameValidator.validate("feature/login");

            assert(valid, "feature/login should be valid");
        },

        function invalidBranchTest() {
            const [valid] =
                BranchNameValidator.validate("feature/");

            assert(!valid, "feature/ should be invalid");
        },

        function pullRequestTest() {
            const pr = new PullRequest(
                1,
                "feature/a",
                "main",
                "Test"
            );

            assert(
                !pr.isMergeable(),
                "PR without checks should not merge"
            );

            pr.checksPassed = true;
            pr.addApproval();

            assert(
                pr.isMergeable(),
                "PR should merge after required validation"
            );
        },

        function conflictTest() {
            const base = { path: "x", content: "A" };
            const ours = { path: "x", content: "B" };
            const theirs = { path: "x", content: "C" };

            assert(
                detectSimpleConflict(base, ours, theirs),
                "conflicting changes should be detected"
            );
        },

        function featureFlagTest() {
            const flags = new FeatureFlagService();

            assert(
                !flags.enabled("missing"),
                "missing feature flag should use default false"
            );

            flags.set("search", true);

            assert(
                flags.enabled("search"),
                "enabled flag should return true"
            );
        },

        function policyTest() {
            const policy = new BranchPolicy({
                maximumAgeDays: 3,
                requirePullRequest: true,
                requireCI: true,
                deleteAfterMerge: true
            });

            assert(
                policy.validate().length === 0,
                "valid policy should have no errors"
            );
        }
    ];

    let passed = 0;

    for (const test of tests) {
        try {
            test();
            passed += 1;
            console.log(`PASS: ${test.name}`);
        } catch (error) {
            console.log(`FAIL: ${test.name}`);
            console.log(`      ${error.message}`);
        }
    }

    console.log(
        `\nTests passed: ${passed}/${tests.length}`
    );

    return passed === tests.length;
}

// =============================================================================
// 28. COMMAND-LINE GIT EXAMPLES
// =============================================================================

function printCommandReference() {
    section("27. Git Command Reference");

    const commands = [
        "git clone <repository>",
        "git status",
        "git switch main",
        "git pull --ff-only origin main",
        "git switch -c feature/my-change",
        "git add <files>",
        'git commit -m "Describe the logical change"',
        "git fetch origin",
        "git rebase origin/main",
        "git push -u origin feature/my-change",
        "git merge <branch>",
        "git log --oneline --decorate --graph --all",
        "git reflog",
        "git branch --delete feature/my-change"
    ];

    commands.forEach(
        (command, index) =>
            console.log(`${String(index + 1).padStart(2, "0")}. ${command}`)
    );
}

// =============================================================================
// 29. PRACTICAL EXERCISES
// =============================================================================

function practicalExercises() {
    section("28. Practical Exercises");

    const exercises = [
        "Create a feature branch from an updated main branch.",
        "Make two small logical commits.",
        "Open a pull request and identify its required checks.",
        "Create a three-way conflict and resolve it intentionally.",
        "Compare merge and rebase histories.",
        "Use a feature flag to hide incomplete functionality.",
        "Design a branch-age policy.",
        "Design CI stages for a pull request.",
        "Create a production hotfix procedure.",
        "Explain how a database migration changes deployment order.",
        "Use reflog to investigate a mistaken reset.",
        "Measure branch lifetime and CI feedback time."
    ];

    exercises.forEach(
        (exercise, index) =>
            console.log(`${String(index + 1).padStart(2, "0")}. ${exercise}`)
    );
}

// =============================================================================
// 30. MAIN
// =============================================================================

async function main() {
    demonstrateGitBasics();
    demonstrateCommitGraph();
    demonstrateBranchValidation();
    demonstrateFeatureBranchWorkflow();
    demonstratePullRequest();
    demonstrateGitHubFlow();
    demonstrateTrunkBasedDevelopment();
    compareWorkflows();
    demonstrateIntegrationStrategies();
    demonstrateConflict();
    demonstrateFeatureFlags();
    demonstrateQualityGates();
    demonstrateBranchPolicy();
    demonstrateCIPipeline();
    await demonstrateAsyncCI();
    await demonstrateAsyncFailureHandling();
    demonstrateReleaseFlow();
    demonstrateSecurity();
    demonstrateMonorepo();
    demonstrateDatabaseMigration();
    demonstrateDeliveryMetrics();
    demonstrateDebugging();
    demonstrateRebaseSafety();
    demonstrateDesignFactors();
    demonstrateWorkflowSimulator();

    const testsPassed = runTests();

    printCommandReference();
    practicalExercises();

    console.log(
        `\nWorkflow study completed. Automated tests: ${
            testsPassed ? "PASS" : "FAIL"
        }.`
    );
}

if (require.main === module) {
    main().catch((error) => {
        console.error("\nProgram failed:", error.message);
        process.exitCode = 1;
    });
}
