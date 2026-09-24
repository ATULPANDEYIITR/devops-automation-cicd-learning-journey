/**
 * Git Conflicts: Detection, Resolution, and Merge Strategies
 * ============================================================
 *
 * A standalone JavaScript study program modeling Git's three-way merge
 * mechanics and demonstrating conflict detection and resolution.
 *
 * The program does not require npm packages.
 *
 * Run:
 *   node git-conflicts.js
 *
 * Optional real Git demonstration:
 *   RUN_REAL_GIT_DEMO=1 node git-conflicts.js
 *
 * On Windows PowerShell:
 *   $env:RUN_REAL_GIT_DEMO="1"; node git-conflicts.js
 */

"use strict";

const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync, spawnSync } = require("child_process");

// ---------------------------------------------------------------------------
// Basic snapshot representation
// ---------------------------------------------------------------------------

class FileSnapshot {
    constructor(content = null) {
        this.content = content;
    }

    get exists() {
        return this.content !== null;
    }

    static absent() {
        return new FileSnapshot(null);
    }
}

class Conflict {
    constructor(filePath, base, ours, theirs, type, explanation) {
        this.path = filePath;
        this.base = base;
        this.ours = ours;
        this.theirs = theirs;
        this.type = type;
        this.explanation = explanation;
        this.markers = createConflictMarkers(ours.content, theirs.content);
    }
}

class MergeResult {
    constructor(mergedTree, conflicts) {
        this.mergedTree = mergedTree;
        this.conflicts = conflicts;
    }

    get clean() {
        return this.conflicts.length === 0;
    }
}

function snapshot(content) {
    return new FileSnapshot(content);
}

function absent() {
    return FileSnapshot.absent();
}

function sameState(left, right) {
    return left.content === right.content;
}

function sha1(text) {
    return crypto.createHash("sha1").update(text, "utf8").digest("hex");
}

function createConflictMarkers(ours, theirs) {
    const oursText = ours ?? "";
    const theirsText = theirs ?? "";

    return (
        `<<<<<<< HEAD\n` +
        `${oursText}${oursText && !oursText.endsWith("\n") ? "\n" : ""}` +
        `=======\n` +
        `${theirsText}${theirsText && !theirsText.endsWith("\n") ? "\n" : ""}` +
        `>>>>>>> incoming\n`
    );
}

function printTree(title, tree) {
    console.log(`\n${title}`);
    console.log("-".repeat(title.length));

    for (const filePath of Object.keys(tree).sort()) {
        const state = tree[filePath];
        console.log(
            `${filePath}: ${state.exists ? JSON.stringify(state.content) : "<deleted>"}`
        );
    }
}

// ---------------------------------------------------------------------------
// Three-way merge
// ---------------------------------------------------------------------------

function classifyChange(base, side) {
    if (sameState(base, side)) {
        return "unchanged";
    }

    if (!base.exists && side.exists) {
        return "added";
    }

    if (base.exists && !side.exists) {
        return "deleted";
    }

    return "modified";
}

function detectFileConflict(filePath, base, ours, theirs) {
    if (sameState(ours, theirs)) {
        return null;
    }

    if (sameState(ours, base)) {
        return null;
    }

    if (sameState(theirs, base)) {
        return null;
    }

    let type;
    let explanation;

    if (!base.exists && ours.exists && theirs.exists) {
        type = "add/add";
        explanation = "Both branches created the same path differently.";
    } else if (base.exists && !ours.exists && theirs.exists) {
        type = "delete/modify";
        explanation = "Ours deleted the file while theirs modified it.";
    } else if (base.exists && ours.exists && !theirs.exists) {
        type = "modify/delete";
        explanation = "Ours modified the file while theirs deleted it.";
    } else {
        type = "content";
        explanation = "Both branches modified the same base state differently.";
    }

    return new Conflict(
        filePath,
        base,
        ours,
        theirs,
        type,
        explanation
    );
}

function threeWayMerge(baseTree, oursTree, theirsTree) {
    const allPaths = new Set([
        ...Object.keys(baseTree),
        ...Object.keys(oursTree),
        ...Object.keys(theirsTree),
    ]);

    const mergedTree = {};
    const conflicts = [];

    for (const filePath of [...allPaths].sort()) {
        const base = baseTree[filePath] ?? absent();
        const ours = oursTree[filePath] ?? absent();
        const theirs = theirsTree[filePath] ?? absent();

        const conflict = detectFileConflict(
            filePath,
            base,
            ours,
            theirs
        );

        if (conflict) {
            conflicts.push(conflict);
            continue;
        }

        const result = sameState(ours, base) ? theirs : ours;

        if (result.exists) {
            mergedTree[filePath] = result;
        }
    }

    return new MergeResult(mergedTree, conflicts);
}

// ---------------------------------------------------------------------------
// Beginner example
// ---------------------------------------------------------------------------

function demonstrateCleanMerge() {
    console.log("\n=== CLEAN THREE-WAY MERGE ===");

    const base = {
        "README.md": snapshot("# Project\n"),
        "app.js": snapshot("console.log('hello');\n"),
    };

    const ours = {
        "README.md": snapshot("# Project\n\nJavaScript implementation\n"),
        "app.js": base["app.js"],
    };

    const theirs = {
        "README.md": base["README.md"],
        "app.js": snapshot("console.log('hello world');\n"),
    };

    const result = threeWayMerge(base, ours, theirs);

    console.log(`Clean merge: ${result.clean}`);
    printTree("Merged tree", result.mergedTree);
}

// ---------------------------------------------------------------------------
// Content conflict
// ---------------------------------------------------------------------------

function demonstrateContentConflict() {
    console.log("\n=== CONTENT CONFLICT ===");

    const base = {
        "config.txt": snapshot("timeout=30\nmode=standard\n"),
    };

    const ours = {
        "config.txt": snapshot("timeout=60\nmode=standard\n"),
    };

    const theirs = {
        "config.txt": snapshot("timeout=120\nmode=standard\n"),
    };

    const result = threeWayMerge(base, ours, theirs);

    console.log(`Clean merge: ${result.clean}`);

    for (const conflict of result.conflicts) {
        console.log(`Path: ${conflict.path}`);
        console.log(`Type: ${conflict.type}`);
        console.log(`Reason: ${conflict.explanation}`);
        console.log(conflict.markers);
    }
}

// ---------------------------------------------------------------------------
// Line-level comparison
// ---------------------------------------------------------------------------

function lines(text) {
    return text.split(/\r?\n/);
}

function lineChangeRanges(base, changed) {
    const a = lines(base);
    const b = lines(changed);

    // JavaScript's standard library does not contain a built-in SequenceMatcher,
    // so this implementation uses a dynamic-programming LCS table.
    const table = Array.from(
        { length: a.length + 1 },
        () => new Array(b.length + 1).fill(0)
    );

    for (let i = a.length - 1; i >= 0; i--) {
        for (let j = b.length - 1; j >= 0; j--) {
            table[i][j] =
                a[i] === b[j]
                    ? table[i + 1][j + 1] + 1
                    : Math.max(table[i + 1][j], table[i][j + 1]);
        }
    }

    const ranges = [];
    let i = 0;
    let j = 0;

    while (i < a.length || j < b.length) {
        if (i < a.length && j < b.length && a[i] === b[j]) {
            i++;
            j++;
            continue;
        }

        const start = i;

        while (
            i < a.length &&
            (j >= b.length || table[i + 1][j] >= table[i][j + 1])
        ) {
            i++;
        }

        while (
            j < b.length &&
            (i >= a.length || table[i][j + 1] >= table[i + 1]?.[j] ?? 0)
        ) {
            j++;
        }

        if (i !== start) {
            ranges.push([start, i]);
        }
    }

    return ranges;
}

function demonstrateLineReasoning() {
    console.log("\n=== LINE-LEVEL REASONING ===");

    const base =
        "name=service\n" +
        "port=8000\n" +
        "workers=2\n" +
        "debug=false\n";

    const ours =
        "name=service\n" +
        "port=9000\n" +
        "workers=2\n" +
        "debug=false\n";

    const theirs =
        "name=service\n" +
        "port=7000\n" +
        "workers=2\n" +
        "debug=false\n";

    console.log("Ours changed ranges:", lineChangeRanges(base, ours));
    console.log("Theirs changed ranges:", lineChangeRanges(base, theirs));
    console.log(
        "Both changes affect the port line. Domain knowledge is required " +
        "to choose an appropriate final value."
    );
}

// ---------------------------------------------------------------------------
// Conflict categories
// ---------------------------------------------------------------------------

function demonstrateConflictTypes() {
    console.log("\n=== CONFLICT TYPES ===");

    const cases = {
        "add/add": [
            absent(),
            snapshot("ours\n"),
            snapshot("theirs\n"),
        ],
        "modify/delete": [
            snapshot("original\n"),
            snapshot("changed by ours\n"),
            absent(),
        ],
        "delete/modify": [
            snapshot("original\n"),
            absent(),
            snapshot("changed by theirs\n"),
        ],
        "content": [
            snapshot("original\n"),
            snapshot("ours\n"),
            snapshot("theirs\n"),
        ],
    };

    for (const [expected, states] of Object.entries(cases)) {
        const conflict = detectFileConflict(
            `${expected}.txt`,
            ...states
        );

        console.log(
            `${expected.padEnd(15)} -> ${conflict?.type ?? "none"}`
        );
    }
}

// ---------------------------------------------------------------------------
// Explicit resolution
// ---------------------------------------------------------------------------

const ResolutionPolicy = Object.freeze({
    OURS: "ours",
    THEIRS: "theirs",
    MANUAL: "manual",
});

function resolveConflict(conflict, policy, manualContent = null) {
    if (policy === ResolutionPolicy.OURS) {
        return conflict.ours;
    }

    if (policy === ResolutionPolicy.THEIRS) {
        return conflict.theirs;
    }

    if (policy === ResolutionPolicy.MANUAL) {
        if (manualContent === null) {
            throw new Error("Manual resolution requires content.");
        }
        return snapshot(manualContent);
    }

    throw new Error(`Unsupported resolution policy: ${policy}`);
}

function applyResolutions(result, resolutions) {
    const conflictPaths = new Set(
        result.conflicts.map(conflict => conflict.path)
    );

    const resolutionPaths = new Set(Object.keys(resolutions));

    if (
        conflictPaths.size !== resolutionPaths.size ||
        [...conflictPaths].some(pathName => !resolutionPaths.has(pathName))
    ) {
        throw new Error("Every conflict must have exactly one resolution.");
    }

    const mergedTree = { ...result.mergedTree };

    for (const [filePath, fileState] of Object.entries(resolutions)) {
        if (fileState.exists) {
            mergedTree[filePath] = fileState;
        } else {
            delete mergedTree[filePath];
        }
    }

    return mergedTree;
}

function demonstrateManualResolution() {
    console.log("\n=== MANUAL RESOLUTION ===");

    const base = {
        "settings.ini": snapshot("workers=2\n"),
    };

    const ours = {
        "settings.ini": snapshot("workers=4\n"),
    };

    const theirs = {
        "settings.ini": snapshot("workers=8\n"),
    };

    const result = threeWayMerge(base, ours, theirs);
    const conflict = result.conflicts[0];

    const resolution = resolveConflict(
        conflict,
        ResolutionPolicy.MANUAL,
        "workers=6\n"
    );

    const resolvedTree = applyResolutions(
        result,
        { "settings.ini": resolution }
    );

    printTree("Resolved tree", resolvedTree);
}

// ---------------------------------------------------------------------------
// Merge-base graph
// ---------------------------------------------------------------------------

class Commit {
    constructor(id, parents, message, tree) {
        this.id = id;
        this.parents = parents;
        this.message = message;
        this.tree = { ...tree };
    }
}

function makeCommit(message, parents, tree) {
    const serialized =
        message +
        "|" +
        Object.keys(tree)
            .sort()
            .map(filePath => `${filePath}=${tree[filePath].content}`)
            .join("|");

    return new Commit(
        sha1(serialized).slice(0, 12),
        [...parents],
        message,
        tree
    );
}

class RepositoryGraph {
    constructor(commits) {
        this.commits = new Map(commits.map(commit => [commit.id, commit]));
    }

    distances(start) {
        const distances = new Map([[start, 0]]);
        const queue = [start];

        while (queue.length > 0) {
            const current = queue.shift();
            const distance = distances.get(current);

            for (const parent of this.commits.get(current).parents) {
                if (!distances.has(parent)) {
                    distances.set(parent, distance + 1);
                    queue.push(parent);
                }
            }
        }

        return distances;
    }

    mergeBase(ours, theirs) {
        const oursDistances = this.distances(ours);
        const theirsDistances = this.distances(theirs);

        const candidates = [...oursDistances.keys()]
            .filter(id => theirsDistances.has(id));

        if (candidates.length === 0) {
            return null;
        }

        candidates.sort((a, b) => {
            const scoreA =
                oursDistances.get(a) + theirsDistances.get(a);
            const scoreB =
                oursDistances.get(b) + theirsDistances.get(b);

            return scoreA - scoreB;
        });

        return candidates[0];
    }
}

function demonstrateMergeBase() {
    console.log("\n=== MERGE BASE ===");

    const root = makeCommit(
        "initial",
        [],
        { "app.txt": snapshot("version 1\n") }
    );

    const main = makeCommit(
        "main change",
        [root.id],
        { "app.txt": snapshot("version 2 main\n") }
    );

    const feature = makeCommit(
        "feature change",
        [root.id],
        { "app.txt": snapshot("version 2 feature\n") }
    );

    const graph = new RepositoryGraph([root, main, feature]);

    console.log("Root:", root.id);
    console.log("Main:", main.id);
    console.log("Feature:", feature.id);
    console.log("Merge base:", graph.mergeBase(main.id, feature.id));
}

// ---------------------------------------------------------------------------
// Strategy comparison
// ---------------------------------------------------------------------------

const MergeStrategy = Object.freeze({
    FAST_FORWARD: "fast-forward",
    THREE_WAY: "three-way",
    OURS: "ours",
    THEIRS: "theirs",
});

function describeStrategy(strategy) {
    const descriptions = {
        [MergeStrategy.FAST_FORWARD]:
            "Move the branch pointer when no divergent merge commit is required.",
        [MergeStrategy.THREE_WAY]:
            "Compare the merge base with both branch tips and construct a merge result.",
        [MergeStrategy.OURS]:
            "An ours-oriented strategy can record a merge relationship while using the current tree as the result.",
        [MergeStrategy.THEIRS]:
            "Choosing incoming content is a resolution policy; exact semantics depend on the Git operation and options.",
    };

    return descriptions[strategy];
}

function demonstrateStrategies() {
    console.log("\n=== MERGE STRATEGIES ===");

    for (const strategy of Object.values(MergeStrategy)) {
        console.log(
            `${strategy.padEnd(15)} -> ${describeStrategy(strategy)}`
        );
    }
}

// ---------------------------------------------------------------------------
// Validation
// ---------------------------------------------------------------------------

function findConflictMarkers(tree) {
    const markers = ["<<<<<<<", "=======", ">>>>>>>"];
    const files = [];

    for (const [filePath, fileState] of Object.entries(tree)) {
        if (!fileState.exists) {
            continue;
        }

        if (markers.some(marker => fileState.content.includes(marker))) {
            files.push(filePath);
        }
    }

    return files;
}

function validateJson(text) {
    try {
        JSON.parse(text);
        return { valid: true, message: "JSON syntax is valid." };
    } catch (error) {
        return { valid: false, message: error.message };
    }
}

function demonstrateValidation() {
    console.log("\n=== VALIDATION ===");

    const tree = {
        "good.json": snapshot('{"workers": 4}\n'),
        "bad.json": snapshot(
            "<<<<<<< HEAD\n{\"workers\": 2}\n=======\n{\"workers\": 8}\n>>>>>>> incoming\n"
        ),
    };

    console.log(
        "Unresolved-marker files:",
        findConflictMarkers(tree)
    );

    console.log(validateJson(tree["good.json"].content));
    console.log(validateJson('{"workers": }\n'));
}

// ---------------------------------------------------------------------------
// Rerere concept
// ---------------------------------------------------------------------------

class ConflictResolutionCache {
    constructor() {
        this.cache = new Map();
    }

    key(conflict) {
        return sha1(
            [
                conflict.path,
                conflict.base.content,
                conflict.ours.content,
                conflict.theirs.content,
            ].join("\0")
        );
    }

    record(conflict, resolution) {
        this.cache.set(this.key(conflict), resolution);
    }

    lookup(conflict) {
        return this.cache.get(this.key(conflict)) ?? null;
    }
}

function demonstrateRerere() {
    console.log("\n=== RERERE CONCEPT ===");

    const base = {
        "policy.txt": snapshot("mode=standard\n"),
    };

    const ours = {
        "policy.txt": snapshot("mode=fast\n"),
    };

    const theirs = {
        "policy.txt": snapshot("mode=safe\n"),
    };

    const result = threeWayMerge(base, ours, theirs);
    const conflict = result.conflicts[0];

    const cache = new ConflictResolutionCache();
    cache.record(conflict, "mode=balanced\n");

    console.log("Stored resolution:", cache.lookup(conflict));
}

// ---------------------------------------------------------------------------
// Rename detection model
// ---------------------------------------------------------------------------

function demonstrateRenameSimilarity() {
    console.log("\n=== RENAME SIMILARITY ===");

    const oldContent = "timeout=30\nretries=3\n";
    const newContent = "timeout=60\nretries=3\n";

    // A simple character-level similarity metric for education.
    const sameCharacters = [...oldContent].filter(
        (character, index) => character === newContent[index]
    ).length;

    const denominator = Math.max(
        oldContent.length,
        newContent.length
    );

    console.log(
        "Approximate positional similarity:",
        (sameCharacters / denominator).toFixed(3)
    );

    console.log(
        "Git can infer renames by comparing deleted and added paths; " +
        "rename detection is based on similarity rather than a simple " +
        "immutable rename object."
    );
}

// ---------------------------------------------------------------------------
// Real Git integration
// ---------------------------------------------------------------------------

function runGit(args, cwd) {
    const result = spawnSync("git", args, {
        cwd,
        encoding: "utf8",
        shell: false,
    });

    return {
        code: result.status ?? 127,
        stdout: result.stdout ?? "",
        stderr: result.stderr ?? "",
    };
}

function createRealConflictRepository() {
    const directory = fs.mkdtempSync(
        path.join(os.tmpdir(), "git-conflict-demo-")
    );

    const setup = [
        ["init", "-b", "main"],
        ["config", "user.name", "Git Conflict Demo"],
        ["config", "user.email", "demo@example.invalid"],
    ];

    for (const command of setup) {
        const result = runGit(command, directory);
        if (result.code !== 0) {
            throw new Error(result.stderr || "Git setup failed.");
        }
    }

    fs.writeFileSync(
        path.join(directory, "settings.txt"),
        "timeout=30\n"
    );

    const initialCommands = [
        ["add", "settings.txt"],
        ["commit", "-m", "Initial settings"],
        ["switch", "-c", "feature"],
    ];

    for (const command of initialCommands) {
        const result = runGit(command, directory);
        if (result.code !== 0) {
            throw new Error(result.stderr || "Git command failed.");
        }
    }

    fs.writeFileSync(
        path.join(directory, "settings.txt"),
        "timeout=60\n"
    );

    for (const command of [
        ["add", "settings.txt"],
        ["commit", "-m", "Feature timeout"],
        ["switch", "main"],
    ]) {
        const result = runGit(command, directory);
        if (result.code !== 0) {
            throw new Error(result.stderr || "Git command failed.");
        }
    }

    fs.writeFileSync(
        path.join(directory, "settings.txt"),
        "timeout=120\n"
    );

    for (const command of [
        ["add", "settings.txt"],
        ["commit", "-m", "Main timeout"],
    ]) {
        const result = runGit(command, directory);
        if (result.code !== 0) {
            throw new Error(result.stderr || "Git command failed.");
        }
    }

    return directory;
}

function inspectRealRepository(directory) {
    console.log("\nRepository:", directory);

    for (const command of [
        ["status", "--short", "--branch"],
        ["diff", "--name-only", "--diff-filter=U"],
        ["branch", "--show-current"],
    ]) {
        const result = runGit(command, directory);

        console.log(`\n$ git ${command.join(" ")}`);

        if (result.stdout.trim()) {
            console.log(result.stdout.trim());
        }

        if (result.stderr.trim()) {
            console.log(result.stderr.trim());
        }
    }
}

function demonstrateRealGit() {
    if (process.env.RUN_REAL_GIT_DEMO !== "1") {
        console.log(
            "\nReal Git demonstration skipped. Set RUN_REAL_GIT_DEMO=1 to enable it."
        );
        return;
    }

    let directory;

    try {
        directory = createRealConflictRepository();

        const merge = runGit(["merge", "feature"], directory);

        console.log("\n=== ACTUAL GIT MERGE ===");
        console.log("Exit code:", merge.code);

        if (merge.stdout.trim()) {
            console.log(merge.stdout.trim());
        }

        if (merge.stderr.trim()) {
            console.log(merge.stderr.trim());
        }

        inspectRealRepository(directory);

        const diff = runGit(["diff", "--", "settings.txt"], directory);

        console.log("\n=== CONFLICT DIFF ===");

        if (diff.stdout.trim()) {
            console.log(diff.stdout.trim());
        }

        runGit(["merge", "--abort"], directory);

        console.log(
            "\nTemporary repository retained at:",
            directory
        );
    } catch (error) {
        console.error("Real Git demo failed:", error.message);
    }
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

function assert(condition, message) {
    if (!condition) {
        throw new Error(`Assertion failed: ${message}`);
    }
}

function testCleanMerge() {
    const base = { "a.txt": snapshot("base\n") };
    const ours = { "a.txt": snapshot("ours\n") };
    const theirs = { "a.txt": snapshot("base\n") };

    const result = threeWayMerge(base, ours, theirs);

    assert(result.clean, "merge should be clean");
    assert(
        result.mergedTree["a.txt"].content === "ours\n",
        "ours change should survive"
    );
}

function testIdenticalChanges() {
    const base = { "a.txt": snapshot("base\n") };
    const ours = { "a.txt": snapshot("same\n") };
    const theirs = { "a.txt": snapshot("same\n") };

    const result = threeWayMerge(base, ours, theirs);

    assert(result.clean, "identical changes should merge cleanly");
    assert(
        result.mergedTree["a.txt"].content === "same\n",
        "identical content should be retained"
    );
}

function testContentConflict() {
    const base = { "a.txt": snapshot("base\n") };
    const ours = { "a.txt": snapshot("ours\n") };
    const theirs = { "a.txt": snapshot("theirs\n") };

    const result = threeWayMerge(base, ours, theirs);

    assert(!result.clean, "different changes should conflict");
    assert(
        result.conflicts[0].type === "content",
        "conflict type should be content"
    );
}

function testAddAddConflict() {
    const result = threeWayMerge(
        {},
        { "new.txt": snapshot("ours\n") },
        { "new.txt": snapshot("theirs\n") }
    );

    assert(!result.clean, "different additions should conflict");
    assert(
        result.conflicts[0].type === "add/add",
        "type should be add/add"
    );
}

function runTests() {
    console.log("\n=== TESTS ===");

    const tests = [
        testCleanMerge,
        testIdenticalChanges,
        testContentConflict,
        testAddAddConflict,
    ];

    for (const test of tests) {
        test();
        console.log(`PASS: ${test.name}`);
    }

    console.log(`${tests.length} tests passed.`);
}

// ---------------------------------------------------------------------------
// Main
// ---------------------------------------------------------------------------

function main() {
    console.log("=".repeat(78));
    console.log("GIT CONFLICTS: DETECTION, RESOLUTION, AND MERGE STRATEGIES");
    console.log("=".repeat(78));

    console.log(
        "\nA conflict occurs when Git cannot safely combine divergent " +
        "changes using its merge rules."
    );

    demonstrateCleanMerge();
    demonstrateContentConflict();
    demonstrateLineReasoning();
    demonstrateConflictTypes();
    demonstrateManualResolution();
    demonstrateMergeBase();
    demonstrateStrategies();
    demonstrateValidation();
    demonstrateRerere();
    demonstrateRenameSimilarity();
    runTests();
    demonstrateRealGit();

    console.log("\n=== PRACTICAL COMMANDS ===");
    console.log("git status");
    console.log("git diff");
    console.log("git diff --cc");
    console.log("git diff --name-only --diff-filter=U");
    console.log("git ls-files -u");
    console.log("git add <resolved-file>");
    console.log("git merge --abort");
    console.log("git merge --continue");
    console.log("git rebase --continue");
    console.log("git rebase --abort");
}

main();
