/*
 * Git Branching: Branches, checkout, switch, and merge
 * =====================================================
 *
 * This standalone JavaScript file provides executable demonstrations of Git
 * branching concepts. It models the essential repository mechanics instead
 * of invoking the Git executable itself.
 *
 * Topics demonstrated:
 *   - commits
 *   - branch references
 *   - HEAD
 *   - branch creation
 *   - checkout and switch concepts
 *   - divergent histories
 *   - fast-forward merges
 *   - three-way merges
 *   - merge conflicts
 *   - conflict resolution
 *   - detached HEAD
 *   - branch deletion
 *   - validation and testing
 *   - asynchronous branch analysis
 *
 * Run with:
 *   node git-branching.js
 */

"use strict";


// ============================================================================
// 1. BASIC UTILITIES
// ============================================================================

function printSection(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function printObject(label, value) {
    console.log(label, JSON.stringify(value, null, 2));
}

function cloneFiles(files) {
    return { ...files };
}


// ============================================================================
// 2. COMMIT MODEL
// ============================================================================

class Commit {
    constructor(id, message, parents, files) {
        this.id = id;
        this.message = message;
        this.parents = [...parents];
        this.files = cloneFiles(files);
    }

    shortId() {
        return this.id.slice(0, 8);
    }
}


// ============================================================================
// 3. REPOSITORY MODEL
// ============================================================================

class GitRepository {
    constructor() {
        this.commits = new Map();
        this.branches = new Map();
        this.headBranch = null;
        this.detachedHead = null;
        this.workingTree = {};
        this.stagingArea = {};
        this.sequence = 0;
    }

    createId(message, parents, files) {
        /*
         * Real Git calculates object IDs from object contents and metadata.
         * This educational model uses a deterministic sequence plus content
         * information. The important concept is that commits have identities
         * and parent relationships.
         */
        this.sequence += 1;

        const serialized = JSON.stringify({
            sequence: this.sequence,
            message,
            parents,
            files,
        });

        let hash = 0;

        for (let index = 0; index < serialized.length; index += 1) {
            hash = ((hash << 5) - hash) + serialized.charCodeAt(index);
            hash |= 0;
        }

        return Math.abs(hash).toString(16).padStart(8, "0");
    }

    initialize() {
        const files = {
            "README.md": "# Branching Demo\n",
            "app.js": 'console.log("Hello");\n',
        };

        const id = this.createId("Initial commit", [], files);

        this.commits.set(
            id,
            new Commit(id, "Initial commit", [], files)
        );

        this.branches.set("main", id);
        this.headBranch = "main";
        this.detachedHead = null;
        this.workingTree = cloneFiles(files);
    }

    get headCommitId() {
        if (this.headBranch !== null) {
            return this.branches.get(this.headBranch);
        }

        if (this.detachedHead !== null) {
            return this.detachedHead;
        }

        throw new Error("HEAD has no valid location.");
    }

    get headCommit() {
        return this.commits.get(this.headCommitId);
    }

    status() {
        console.log(`Branch: ${this.headBranch ?? "(detached HEAD)"}`);
        console.log(`HEAD: ${this.headCommit.shortId()}`);

        const changes = [];

        const paths = new Set([
            ...Object.keys(this.headCommit.files),
            ...Object.keys(this.workingTree),
        ]);

        for (const path of [...paths].sort()) {
            if (this.headCommit.files[path] !== this.workingTree[path]) {
                changes.push(path);
            }
        }

        if (changes.length === 0) {
            console.log("Working tree clean.");
        } else {
            console.log("Modified files:", changes);
        }
    }

    createBranch(name) {
        if (this.branches.has(name)) {
            throw new Error(`Branch '${name}' already exists.`);
        }

        this.branches.set(name, this.headCommitId);
    }

    switchBranch(name) {
        /*
         * This represents the modern branch-oriented idea behind:
         *
         *     git switch branch-name
         */
        if (!this.branches.has(name)) {
            throw new Error(`Branch '${name}' does not exist.`);
        }

        this.headBranch = name;
        this.detachedHead = null;

        this.workingTree = cloneFiles(
            this.commits.get(this.branches.get(name)).files
        );
    }

    switchCreate(name) {
        /*
         * Equivalent conceptually to:
         *
         *     git switch -c feature
         */
        this.createBranch(name);
        this.switchBranch(name);
    }

    checkout(target) {
        /*
         * checkout historically serves multiple purposes.
         *
         * A branch name attaches HEAD to that branch.
         * A commit ID produces detached HEAD.
         */
        if (this.branches.has(target)) {
            this.switchBranch(target);
            return;
        }

        if (this.commits.has(target)) {
            this.headBranch = null;
            this.detachedHead = target;
            this.workingTree = cloneFiles(
                this.commits.get(target).files
            );
            return;
        }

        throw new Error(`Unknown branch or commit: ${target}`);
    }

    edit(path, content) {
        this.workingTree[path] = content;
    }

    add(path) {
        if (!(path in this.workingTree)) {
            throw new Error(`Cannot stage missing file '${path}'.`);
        }

        this.stagingArea[path] = this.workingTree[path];
    }

    addAll() {
        this.stagingArea = cloneFiles(this.workingTree);
    }

    commit(message) {
        if (this.headBranch === null) {
            throw new Error(
                "Normal branch commits cannot be created from detached HEAD."
            );
        }

        if (Object.keys(this.stagingArea).length === 0) {
            throw new Error("Nothing is staged.");
        }

        const files = cloneFiles(this.headCommit.files);

        for (const [path, content] of Object.entries(this.stagingArea)) {
            files[path] = content;
        }

        const parent = this.headCommitId;
        const id = this.createId(message, [parent], files);

        this.commits.set(
            id,
            new Commit(id, message, [parent], files)
        );

        this.branches.set(this.headBranch, id);
        this.workingTree = cloneFiles(files);
        this.stagingArea = {};

        return id;
    }

    commitAll(message) {
        this.addAll();
        return this.commit(message);
    }

    ancestors(commitId) {
        const visited = new Set();
        const queue = [commitId];

        while (queue.length > 0) {
            const current = queue.shift();

            if (visited.has(current)) {
                continue;
            }

            visited.add(current);

            const commit = this.commits.get(current);

            for (const parent of commit.parents) {
                queue.push(parent);
            }
        }

        return visited;
    }

    isAncestor(ancestor, descendant) {
        return this.ancestors(descendant).has(ancestor);
    }

    findMergeBase(first, second) {
        const firstAncestors = this.ancestors(first);
        const queue = [second];
        const visited = new Set();

        while (queue.length > 0) {
            const current = queue.shift();

            if (visited.has(current)) {
                continue;
            }

            visited.add(current);

            if (firstAncestors.has(current)) {
                return current;
            }

            for (const parent of this.commits.get(current).parents) {
                queue.push(parent);
            }
        }

        return null;
    }

    merge(targetBranch, resolutions = {}) {
        if (this.headBranch === null) {
            throw new Error("Cannot merge from detached HEAD.");
        }

        if (!this.branches.has(targetBranch)) {
            throw new Error(`Unknown target branch '${targetBranch}'.`);
        }

        const currentId = this.headCommitId;
        const targetId = this.branches.get(targetBranch);

        if (currentId === targetId) {
            return {
                type: "already-up-to-date",
                conflicts: [],
            };
        }

        if (this.isAncestor(targetId, currentId)) {
            return {
                type: "already-up-to-date",
                conflicts: [],
            };
        }

        if (this.isAncestor(currentId, targetId)) {
            this.branches.set(this.headBranch, targetId);
            this.workingTree = cloneFiles(
                this.commits.get(targetId).files
            );

            return {
                type: "fast-forward",
                conflicts: [],
            };
        }

        const baseId = this.findMergeBase(currentId, targetId);

        if (baseId === null) {
            throw new Error("No common merge base.");
        }

        const base = this.commits.get(baseId);
        const current = this.commits.get(currentId);
        const target = this.commits.get(targetId);

        const merged = cloneFiles(base.files);
        const conflicts = [];

        const paths = new Set([
            ...Object.keys(base.files),
            ...Object.keys(current.files),
            ...Object.keys(target.files),
        ]);

        for (const path of [...paths].sort()) {
            const baseValue = base.files[path];
            const currentValue = current.files[path];
            const targetValue = target.files[path];

            const currentChanged = currentValue !== baseValue;
            const targetChanged = targetValue !== baseValue;

            if (currentChanged && targetChanged) {
                if (currentValue === targetValue) {
                    merged[path] = currentValue;
                } else if (path in resolutions) {
                    merged[path] = resolutions[path];
                } else {
                    conflicts.push(path);
                    merged[path] =
                        "<<<<<<< CURRENT\n" +
                        `${currentValue}\n` +
                        "=======\n" +
                        `${targetValue}\n` +
                        ">>>>>>> TARGET\n`;
                }
            } else if (currentChanged) {
                merged[path] = currentValue;
            } else if (targetChanged) {
                merged[path] = targetValue;
            }
        }

        if (conflicts.length > 0) {
            this.workingTree = merged;

            return {
                type: "conflict",
                conflicts,
            };
        }

        const message =
            `Merge branch '${targetBranch}' into '${this.headBranch}'`;

        const mergeId = this.createId(
            message,
            [currentId, targetId],
            merged
        );

        this.commits.set(
            mergeId,
            new Commit(
                mergeId,
                message,
                [currentId, targetId],
                merged
            )
        );

        this.branches.set(this.headBranch, mergeId);
        this.workingTree = cloneFiles(merged);

        return {
            type: "merge-commit",
            conflicts: [],
        };
    }

    deleteBranch(name, force = false) {
        if (!this.branches.has(name)) {
            throw new Error(`Branch '${name}' does not exist.`);
        }

        if (name === this.headBranch) {
            throw new Error("Cannot delete the checked-out branch.");
        }

        const targetId = this.branches.get(name);

        if (!force && !this.isAncestor(targetId, this.headCommitId)) {
            throw new Error(
                "Branch is not fully merged. Use force only intentionally."
            );
        }

        this.branches.delete(name);
    }

    showBranches() {
        console.log("\nBranches:");

        for (const [name, id] of [...this.branches.entries()].sort()) {
            const marker = name === this.headBranch ? "*" : " ";
            console.log(
                `${marker} ${name.padEnd(22)} -> ` +
                `${this.commits.get(id).shortId()} ` +
                this.commits.get(id).message
            );
        }
    }

    graph() {
        console.log("\nHistory:");

        const branchLabels = new Map();

        for (const [name, id] of this.branches.entries()) {
            if (!branchLabels.has(id)) {
                branchLabels.set(id, []);
            }

            branchLabels.get(id).push(name);
        }

        const visited = new Set();
        const queue = [this.headCommitId];

        while (queue.length > 0) {
            const id = queue.shift();

            if (visited.has(id)) {
                continue;
            }

            visited.add(id);

            const commit = this.commits.get(id);
            const labels = branchLabels.get(id) ?? [];

            console.log(
                `* ${commit.shortId()} ` +
                `${labels.length ? `[${labels.join(", ")}] ` : ""}` +
                commit.message
            );

            for (const parent of commit.parents) {
                queue.push(parent);
            }
        }
    }
}


// ============================================================================
// 4. BASIC BRANCH CREATION
// ============================================================================

printSection("1. Creating a branch");

const repository = new GitRepository();
repository.initialize();

repository.status();
repository.showBranches();

repository.edit(
    "README.md",
    "# Git Branching\n\nLearning branch fundamentals.\n"
);
repository.commitAll("Improve documentation");

repository.switchCreate("feature/login");

repository.edit(
    "login.js",
    [
        "function authenticate(username, password) {",
        "    return Boolean(username) && Boolean(password);",
        "}",
    ].join("\n") + "\n"
);

repository.commitAll("Add login authentication");

repository.showBranches();
repository.graph();


// ============================================================================
// 5. CHECKOUT AND SWITCH
// ============================================================================

printSection("2. checkout and switch");

console.log("Modern branch-oriented command:");
console.log("git switch main");

console.log("\nOlder multi-purpose command:");
console.log("git checkout main");

console.log("\nCreate and switch:");
console.log("git switch -c feature/search");

console.log("\nOlder equivalent:");
console.log("git checkout -b feature/search");

repository.switchBranch("main");
console.log(`\nCurrent branch: ${repository.headBranch}`);

repository.checkout("feature/login");
console.log(`After checkout: ${repository.headBranch}`);


// ============================================================================
// 6. DIVERGING BRANCHES
// ============================================================================

printSection("3. Divergent development");

const divergent = new GitRepository();
divergent.initialize();

divergent.edit(
    "app.js",
    'console.log("Main version");\n'
);
divergent.commitAll("Update main application");

divergent.switchCreate("feature/reporting");

divergent.edit(
    "report.js",
    [
        "function generateReport(data) {",
        "    return data.length;",
        "}",
    ].join("\n") + "\n"
);
divergent.commitAll("Add reporting feature");

divergent.switchBranch("main");

divergent.edit(
    "metrics.js",
    [
        "function calculateMetrics(values) {",
        "    return values.length;",
        "}",
    ].join("\n") + "\n"
);
divergent.commitAll("Add metrics");

divergent.graph();


// ============================================================================
// 7. FAST-FORWARD MERGE
// ============================================================================

printSection("4. Fast-forward merge");

const fastForward = new GitRepository();
fastForward.initialize();

fastForward.switchCreate("feature");

fastForward.edit("feature.txt", "Feature implementation\n");
fastForward.commitAll("Add feature");

fastForward.switchBranch("main");

const fastForwardResult = fastForward.merge("feature");

printObject("Merge result:", fastForwardResult);
fastForward.showBranches();


// ============================================================================
// 8. THREE-WAY MERGE
// ============================================================================

printSection("5. Three-way merge");

const threeWay = new GitRepository();
threeWay.initialize();

threeWay.switchCreate("feature");

threeWay.edit(
    "feature.txt",
    "Feature implementation\n"
);
threeWay.commitAll("Implement feature");

threeWay.switchBranch("main");

threeWay.edit(
    "main.txt",
    "Independent main development\n"
);
threeWay.commitAll("Continue main development");

const threeWayResult = threeWay.merge("feature");

printObject("Merge result:", threeWayResult);
threeWay.graph();


// ============================================================================
// 9. MERGE CONFLICT
// ============================================================================

printSection("6. Merge conflict");

const conflict = new GitRepository();
conflict.initialize();

conflict.edit(
    "config.txt",
    "mode=development\n"
);
conflict.commitAll("Add configuration");

conflict.switchCreate("feature");

conflict.edit(
    "config.txt",
    "mode=feature\n"
);
conflict.commitAll("Configure feature mode");

conflict.switchBranch("main");

conflict.edit(
    "config.txt",
    "mode=production\n"
);
conflict.commitAll("Configure production mode");

const conflictResult = conflict.merge("feature");

printObject("Merge result:", conflictResult);

if (conflictResult.conflicts.length > 0) {
    console.log("\nConflicted file:");
    console.log(conflict.workingTree["config.txt"]);
}


// ============================================================================
// 10. CONFLICT RESOLUTION
// ============================================================================

printSection("7. Conflict resolution");

const resolved = new GitRepository();
resolved.initialize();

resolved.edit("config.txt", "mode=development\n");
resolved.commitAll("Add configuration");

resolved.switchCreate("feature");
resolved.edit("config.txt", "mode=feature\n");
resolved.commitAll("Configure feature");

resolved.switchBranch("main");
resolved.edit("config.txt", "mode=production\n");
resolved.commitAll("Configure production");

const resolution = {
    "config.txt":
        "mode=production\n" +
        "feature_enabled=true\n",
};

const resolvedResult = resolved.merge("feature", resolution);

printObject("Resolved merge:", resolvedResult);
console.log("\nFinal configuration:");
console.log(resolved.workingTree["config.txt"]);


// ============================================================================
// 11. DETACHED HEAD
// ============================================================================

printSection("8. Detached HEAD");

const detached = new GitRepository();
detached.initialize();

detached.edit(
    "app.js",
    'console.log("Second version");\n'
);

const secondCommit = detached.commitAll("Second version");

detached.checkout(secondCommit);

console.log("HEAD branch:", detached.headBranch);
console.log("Detached commit:", detached.detachedHead);

console.log(
    "\nA detached HEAD is useful for inspecting or testing a historical " +
    "commit without moving a branch pointer."
);


// ============================================================================
// 12. BRANCH DELETION
// ============================================================================

printSection("9. Branch deletion");

const deletion = new GitRepository();
deletion.initialize();

deletion.switchCreate("completed-feature");

deletion.edit(
    "feature.txt",
    "Completed work\n"
);
deletion.commitAll("Complete feature");

deletion.switchBranch("main");
deletion.merge("completed-feature");

deletion.deleteBranch("completed-feature");

deletion.showBranches();


// ============================================================================
// 13. VALIDATION
// ============================================================================

printSection("10. Validation before integration");

function validatePullRequest(files) {
    const requiredFiles = ["README.md", "app.js"];

    const missing = requiredFiles.filter(
        (file) => !(file in files)
    );

    if (missing.length > 0) {
        return {
            valid: false,
            reason: `Missing files: ${missing.join(", ")}`,
        };
    }

    return {
        valid: true,
        reason: "Required files are present.",
    };
}

const validationExamples = [
    {
        "README.md": "# Project\n",
        "app.js": "console.log('ok');\n",
    },
    {
        "app.js": "console.log('incomplete');\n",
    },
];

for (const files of validationExamples) {
    printObject("Validation:", validatePullRequest(files));
}


// ============================================================================
// 14. FUNCTIONAL STYLE: BRANCH ANALYSIS
// ============================================================================

printSection("11. Functional branch analysis");

function branchDescriptions(repository) {
    return [...repository.branches.entries()]
        .map(([name, commitId]) => ({
            name,
            commit: repository.commits.get(commitId).shortId(),
            message: repository.commits.get(commitId).message,
        }))
        .sort((a, b) => a.name.localeCompare(b.name));
}

const branchReport = branchDescriptions(repository);

branchReport.forEach((branch) => {
    console.log(
        `${branch.name}: ${branch.commit} - ${branch.message}`
    );
});


// ============================================================================
// 15. ASYNCHRONOUS WORKFLOW SIMULATION
// ============================================================================

printSection("12. Asynchronous pre-merge checks");

function runCheck(name, delay, result = true) {
    return new Promise((resolve) => {
        setTimeout(() => {
            resolve({
                name,
                passed: result,
            });
        }, delay);
    });
}

async function runPreMergeChecks() {
    /*
     * Promise.all models independent checks running concurrently.
     * A real CI system may run tests, linting, security checks, and builds
     * independently before allowing a branch to merge.
     */
    const results = await Promise.all([
        runCheck("Unit tests", 20, true),
        runCheck("Linting", 10, true),
        runCheck("Build", 30, true),
        runCheck("Security validation", 15, true),
    ]);

    for (const result of results) {
        console.log(
            `${result.name}: ${result.passed ? "PASS" : "FAIL"}`
        );
    }

    return results.every((result) => result.passed);
}


// ============================================================================
// 16. EDGE CASES
// ============================================================================

printSection("13. Edge cases");

const edgeCaseRepository = new GitRepository();
edgeCaseRepository.initialize();

try {
    edgeCaseRepository.switchBranch("does-not-exist");
} catch (error) {
    console.log("Unknown branch:", error.message);
}

try {
    edgeCaseRepository.deleteBranch("main");
} catch (error) {
    console.log("Current branch deletion:", error.message);
}

try {
    edgeCaseRepository.checkout("invalid-commit");
} catch (error) {
    console.log("Unknown checkout target:", error.message);
}


// ============================================================================
// 17. PERFORMANCE CONSIDERATIONS
// ============================================================================

printSection("14. Performance considerations");

console.log(
    "Branch creation is conceptually inexpensive because a branch is a " +
    "reference to a commit rather than a full copy of the project."
);

console.log(
    "History traversal can become more expensive as repository graphs grow, " +
    "especially in large histories with many merge relationships."
);

console.log(
    "Large binary files, generated artifacts, and huge working trees can " +
    "affect repository performance more substantially than ordinary branch " +
    "creation."
);


// ============================================================================
// 18. SECURITY CONSIDERATIONS
// ============================================================================

printSection("15. Security considerations");

console.log(
    "Branches are organizational references, not security boundaries."
);

console.log(
    "A secret committed to Git history may remain in historical commits " +
    "even after the file is deleted."
);

console.log(
    "Credentials accidentally committed to a repository should be revoked " +
    "or rotated. History cleanup alone does not invalidate a leaked secret."
);


// ============================================================================
// 19. COMMON COMMAND REFERENCE
// ============================================================================

printSection("16. Command reference");

const commands = [
    ["git branch", "List branches"],
    ["git branch feature", "Create a branch"],
    ["git switch main", "Switch to main"],
    ["git switch -c feature", "Create and switch"],
    ["git checkout main", "Older branch switching command"],
    ["git checkout -b feature", "Older create-and-switch command"],
    ["git merge feature", "Merge feature into current branch"],
    ["git branch -d feature", "Safely delete merged branch"],
    ["git branch -D feature", "Force-delete branch"],
    ["git status", "Inspect working-tree state"],
    ["git log --graph --oneline --all", "Inspect branch history"],
];

for (const [command, meaning] of commands) {
    console.log(`${command.padEnd(38)} ${meaning}`);
}


// ============================================================================
// 20. SELF-TEST
// ============================================================================

printSection("17. Self-test");

function runSelfTest() {
    const test = new GitRepository();
    test.initialize();

    if (!test.branches.has("main")) {
        throw new Error("main branch was not created.");
    }

    test.switchCreate("feature");

    if (test.headBranch !== "feature") {
        throw new Error("Feature branch was not checked out.");
    }

    test.edit("feature.txt", "feature\n");
    const featureCommit = test.commitAll("Feature work");

    test.switchBranch("main");

    const result = test.merge("feature");

    if (result.type !== "fast-forward") {
        throw new Error("Expected a fast-forward merge.");
    }

    if (test.headCommitId !== featureCommit) {
        throw new Error("main did not advance to feature commit.");
    }

    console.log("All JavaScript self-tests passed.");
}


// ============================================================================
// 21. MAIN EXECUTION
// ============================================================================

(async function main() {
    const checksPassed = await runPreMergeChecks();

    if (!checksPassed) {
        throw new Error("Pre-merge checks failed.");
    }

    runSelfTest();

    printSection("18. Completed");

    console.log(
        "The executable examples demonstrated branch references, HEAD, " +
        "checkout, switch, divergent history, fast-forward merges, " +
        "three-way merges, conflicts, resolution, detached HEAD, " +
        "validation, asynchronous checks, and branch deletion."
    );
})();
