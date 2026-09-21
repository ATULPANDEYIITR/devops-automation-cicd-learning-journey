```javascript
"use strict";

/*
 * Git Fundamentals: Repository, Working Tree, and Staging Area
 *
 * This standalone JavaScript file teaches the same core Git model from a
 * different implementation perspective.
 *
 * It uses:
 *   - objects and classes
 *   - Maps and Sets
 *   - functional transformations
 *   - validation
 *   - asynchronous process execution
 *   - filesystem operations
 *   - a miniature content-addressed object store
 *
 * Node.js is required for the complete demonstration because the final
 * sections execute real Git commands inside a temporary directory.
 */

const fs = require("fs");
const fsp = require("fs/promises");
const os = require("os");
const path = require("path");
const crypto = require("crypto");
const { execFile } = require("child_process");
const { promisify } = require("util");

const execFileAsync = promisify(execFile);


/* -------------------------------------------------------------------------
 * 1. Output helpers
 * ---------------------------------------------------------------------- */

function printSection(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function printKeyValue(title, value) {
    console.log(`${title}: ${value}`);
}


/* -------------------------------------------------------------------------
 * 2. Fundamental terminology
 * ---------------------------------------------------------------------- */

function explainTerminology() {
    printSection("1. Git fundamentals");

    const terms = new Map([
        [
            "Git",
            "A distributed version control system for recording and managing changes."
        ],
        [
            "Repository",
            "The project history and Git metadata, normally represented locally by .git."
        ],
        [
            "Working tree",
            "The files and directories currently available for editing."
        ],
        [
            "Staging area",
            "The index: the proposed contents of the next commit."
        ],
        [
            "Commit",
            "A recorded snapshot with metadata and links to parent commit(s)."
        ],
        [
            "Branch",
            "A movable reference pointing to a commit."
        ],
        [
            "HEAD",
            "The reference representing the currently checked-out location."
        ],
        [
            "Tracked",
            "A path Git already knows about through its index and/or history."
        ],
        [
            "Untracked",
            "A working-tree path not currently tracked by Git."
        ]
    ]);

    for (const [term, definition] of terms) {
        console.log(`\n${term}`);
        console.log(`  ${definition}`);
    }
}


/* -------------------------------------------------------------------------
 * 3. Three-area model
 * ---------------------------------------------------------------------- */

class GitThreeAreaModel {
    constructor({ committed = {}, staged = {}, working = {} } = {}) {
        this.committed = new Map(Object.entries(committed));
        this.staged = new Map(Object.entries(staged));
        this.working = new Map(Object.entries(working));
    }

    createFile(filePath, content) {
        validatePath(filePath);
        this.working.set(filePath, String(content));
    }

    editFile(filePath, content) {
        if (!this.working.has(filePath)) {
            throw new Error(`Working-tree file does not exist: ${filePath}`);
        }

        this.working.set(filePath, String(content));
    }

    add(...filePaths) {
        for (const filePath of filePaths) {
            if (!this.working.has(filePath)) {
                throw new Error(
                    `Cannot stage ${filePath}: file is absent from the working tree.`
                );
            }

            // git add copies the current working-tree content into the index.
            this.staged.set(filePath, this.working.get(filePath));
        }
    }

    unstage(...filePaths) {
        for (const filePath of filePaths) {
            if (this.committed.has(filePath)) {
                this.staged.set(filePath, this.committed.get(filePath));
            } else {
                this.staged.delete(filePath);
            }
        }
    }

    restoreWorkingTree(...filePaths) {
        for (const filePath of filePaths) {
            if (this.staged.has(filePath)) {
                this.working.set(filePath, this.staged.get(filePath));
            } else if (this.committed.has(filePath)) {
                this.working.set(filePath, this.committed.get(filePath));
            } else {
                this.working.delete(filePath);
            }
        }
    }

    commit(message) {
        if (typeof message !== "string" || message.trim() === "") {
            throw new Error("Commit message must be a non-empty string.");
        }

        this.committed = new Map(this.staged);
    }

    status() {
        const allPaths = new Set([
            ...this.committed.keys(),
            ...this.staged.keys(),
            ...this.working.keys()
        ]);

        const result = new Map();

        for (const filePath of [...allPaths].sort()) {
            const inCommit = this.committed.has(filePath);
            const inStage = this.staged.has(filePath);
            const inWorking = this.working.has(filePath);

            if (!inCommit && !inStage && inWorking) {
                result.set(filePath, "untracked");
                continue;
            }

            if (inCommit && inStage && inWorking) {
                const stageChanged =
                    this.staged.get(filePath) !== this.committed.get(filePath);

                const workingChanged =
                    this.working.get(filePath) !== this.staged.get(filePath);

                if (stageChanged && workingChanged) {
                    result.set(filePath, "staged and additionally modified");
                } else if (stageChanged) {
                    result.set(filePath, "modified and staged");
                } else if (workingChanged) {
                    result.set(filePath, "modified");
                } else {
                    result.set(filePath, "clean");
                }

                continue;
            }

            if (!inCommit && inStage && inWorking) {
                result.set(filePath, "new file staged");
                continue;
            }

            if (inCommit && !inWorking) {
                result.set(filePath, "deleted from working tree");
                continue;
            }

            result.set(filePath, "unusual state");
        }

        return result;
    }

    diff(left, right) {
        const paths = new Set([
            ...left.keys(),
            ...right.keys()
        ]);

        const differences = [];

        for (const filePath of [...paths].sort()) {
            const oldValue = left.get(filePath);
            const newValue = right.get(filePath);

            if (oldValue !== newValue) {
                differences.push({
                    filePath,
                    oldValue,
                    newValue
                });
            }
        }

        return differences;
    }

    diffCommitToStage() {
        return this.diff(this.committed, this.staged);
    }

    diffStageToWorking() {
        return this.diff(this.staged, this.working);
    }

    showStatus() {
        console.log("\nThree-area status:");

        for (const [filePath, state] of this.status()) {
            console.log(`  ${state.padEnd(38)} ${filePath}`);
        }
    }
}

function validatePath(filePath) {
    if (typeof filePath !== "string" || filePath.trim() === "") {
        throw new TypeError("A file path must be a non-empty string.");
    }
}

function showDiff(differences, title) {
    console.log(`\n${title}`);

    if (differences.length === 0) {
        console.log("  No differences.");
        return;
    }

    for (const difference of differences) {
        console.log(`\n  ${difference.filePath}`);
        console.log(`    OLD: ${JSON.stringify(difference.oldValue)}`);
        console.log(`    NEW: ${JSON.stringify(difference.newValue)}`);
    }
}


/* -------------------------------------------------------------------------
 * 4. Demonstrate the three areas
 * ---------------------------------------------------------------------- */

function demonstrateThreeAreas() {
    printSection("2. Working tree -> staging area -> repository");

    const model = new GitThreeAreaModel({
        committed: {
            "app.js": "console.log('version 1');\n"
        },
        staged: {
            "app.js": "console.log('version 1');\n"
        },
        working: {
            "app.js": "console.log('version 1');\n"
        }
    });

    console.log("\nInitial state:");
    model.showStatus();

    console.log("\nEdit the working tree:");
    model.editFile("app.js", "console.log('version 2');\n");
    model.showStatus();

    console.log("\nStage the edit:");
    model.add("app.js");
    model.showStatus();

    console.log("\nEdit the same file again:");
    model.editFile("app.js", "console.log('version 3');\n");
    model.showStatus();

    showDiff(
        model.diffCommitToStage(),
        "Commit -> staging area"
    );

    showDiff(
        model.diffStageToWorking(),
        "Staging area -> working tree"
    );

    console.log("\nCommit only the staged version:");
    model.commit("Update application");
    model.showStatus();

    console.log(
        "\nThis demonstrates why staged and unstaged changes can coexist."
    );
}


/* -------------------------------------------------------------------------
 * 5. Functional programming view of Git status
 * ---------------------------------------------------------------------- */

function classifyFile({
    inCommit,
    inStage,
    inWorking,
    commitContent,
    stageContent,
    workingContent
}) {
    if (!inCommit && !inStage && inWorking) {
        return "untracked";
    }

    if (inCommit && inStage && inWorking) {
        const stagedChanged = commitContent !== stageContent;
        const workingChanged = stageContent !== workingContent;

        if (stagedChanged && workingChanged) {
            return "staged and additionally modified";
        }

        if (stagedChanged) {
            return "modified and staged";
        }

        if (workingChanged) {
            return "modified";
        }

        return "clean";
    }

    if (!inCommit && inStage && inWorking) {
        return "new file staged";
    }

    return "other";
}

function demonstrateFunctionalClassification() {
    printSection("3. Functional view of status classification");

    const examples = [
        {
            name: "new file",
            inCommit: false,
            inStage: false,
            inWorking: true
        },
        {
            name: "modified but unstaged",
            inCommit: true,
            inStage: true,
            inWorking: true,
            commitContent: "A",
            stageContent: "A",
            workingContent: "B"
        },
        {
            name: "modified and staged",
            inCommit: true,
            inStage: true,
            inWorking: true,
            commitContent: "A",
            stageContent: "B",
            workingContent: "B"
        },
        {
            name: "staged and then edited again",
            inCommit: true,
            inStage: true,
            inWorking: true,
            commitContent: "A",
            stageContent: "B",
            workingContent: "C"
        }
    ];

    for (const example of examples) {
        console.log(
            `${example.name.padEnd(32)} -> ${classifyFile(example)}`
        );
    }
}


/* -------------------------------------------------------------------------
 * 6. Content-addressed storage
 * ---------------------------------------------------------------------- */

function sha1(bufferOrString) {
    return crypto
        .createHash("sha1")
        .update(bufferOrString)
        .digest("hex");
}

function gitObjectId(type, content) {
    const data = Buffer.isBuffer(content)
        ? content
        : Buffer.from(String(content), "utf8");

    const header = Buffer.from(
        `${type} ${data.length}\0`,
        "utf8"
    );

    return sha1(Buffer.concat([header, data]));
}

class MiniObjectDatabase {
    constructor() {
        this.objects = new Map();
    }

    write(type, content) {
        const id = gitObjectId(type, content);

        const data = Buffer.isBuffer(content)
            ? Buffer.from(content)
            : Buffer.from(String(content), "utf8");

        this.objects.set(id, {
            type,
            content: data
        });

        return id;
    }

    read(id) {
        const object = this.objects.get(id);

        if (!object) {
            throw new Error(`Unknown object: ${id}`);
        }

        return object;
    }
}

function demonstrateObjectDatabase() {
    printSection("4. Simplified Git object database");

    const database = new MiniObjectDatabase();

    const blobId = database.write(
        "blob",
        "Hello Git\n"
    );

    const treeContent =
        `100644 README.md blob ${blobId}\n`;

    const treeId = database.write(
        "tree",
        treeContent
    );

    const commitContent =
        `tree ${treeId}\n` +
        `author Student <student@example.com>\n` +
        `committer Student <student@example.com>\n\n` +
        `Initial commit\n`;

    const commitId = database.write(
        "commit",
        commitContent
    );

    console.log(`Blob:   ${blobId}`);
    console.log(`Tree:   ${treeId}`);
    console.log(`Commit: ${commitId}`);

    for (const [id, object] of database.objects) {
        console.log(
            `${id.slice(0, 12)}... -> ${object.type}`
        );
    }

    console.log(
        "\nGit uses content-addressed objects. The object ID is derived "
        + "from the object type and content."
    );
}


/* -------------------------------------------------------------------------
 * 7. Branches and HEAD
 * ---------------------------------------------------------------------- */

class BranchState {
    constructor(initialBranch, initialCommit) {
        this.branches = new Map([
            [initialBranch, initialCommit]
        ]);

        this.headBranch = initialBranch;
    }

    get headCommit() {
        return this.branches.get(this.headBranch);
    }

    createBranch(name) {
        if (this.branches.has(name)) {
            throw new Error(`Branch already exists: ${name}`);
        }

        this.branches.set(name, this.headCommit);
    }

    switchBranch(name) {
        if (!this.branches.has(name)) {
            throw new Error(`Unknown branch: ${name}`);
        }

        this.headBranch = name;
    }

    advance(commitId) {
        this.branches.set(this.headBranch, commitId);
    }
}

function demonstrateBranches() {
    printSection("5. Branches and HEAD");

    const state = new BranchState(
        "main",
        "a1b2c3d4"
    );

    console.log(
        `HEAD -> ${state.headBranch} -> ${state.headCommit}`
    );

    state.createBranch("feature/login");

    console.log(
        `Created branch feature/login at ${state.branches.get("feature/login")}`
    );

    state.switchBranch("feature/login");

    console.log(
        `HEAD -> ${state.headBranch} -> ${state.headCommit}`
    );

    state.advance("e5f6g7h8");

    console.log(
        `Feature branch now points to ${state.headCommit}`
    );

    console.log(
        "\nA branch is fundamentally a movable reference to a commit."
    );
}


/* -------------------------------------------------------------------------
 * 8. Commit graph
 * ---------------------------------------------------------------------- */

class CommitGraph {
    constructor() {
        this.commits = new Map();
    }

    addCommit(message, parents = []) {
        const payload = JSON.stringify({
            message,
            parents,
            sequence: this.commits.size + 1
        });

        const id = sha1(payload).slice(0, 12);

        this.commits.set(id, {
            id,
            message,
            parents: [...parents]
        });

        return id;
    }

    print() {
        for (const commit of this.commits.values()) {
            console.log(
                `${commit.id}  parents=${JSON.stringify(commit.parents)}  `
                + `message=${commit.message}`
            );
        }
    }
}

function demonstrateCommitGraph() {
    printSection("6. Commit graph");

    const graph = new CommitGraph();

    const root = graph.addCommit("Initial project");
    const featureBase = graph.addCommit(
        "Add feature",
        [root]
    );

    const mainFix = graph.addCommit(
        "Fix bug",
        [featureBase]
    );

    const featureWork = graph.addCommit(
        "Implement experiment",
        [featureBase]
    );

    graph.addCommit(
        "Merge experiment",
        [mainFix, featureWork]
    );

    graph.print();

    console.log(
        "\nMerge commits normally have multiple parents, which preserves "
        + "the relationship between histories."
    );
}


/* -------------------------------------------------------------------------
 * 9. .gitignore conceptual matcher
 * ---------------------------------------------------------------------- */

function isIgnored(filePath) {
    const normalized = filePath.replaceAll("\\", "/");

    return (
        normalized === ".env" ||
        normalized.startsWith(".venv/") ||
        normalized.startsWith("__pycache__/") ||
        normalized.startsWith("build/") ||
        normalized.endsWith(".pyc") ||
        normalized.endsWith(".log")
    );
}

function demonstrateGitignore() {
    printSection("7. .gitignore");

    const paths = [
        "app.js",
        ".env",
        ".venv/bin/node",
        "__pycache__/cache.pyc",
        "build/output.js",
        "logs/server.log",
        "src/index.js"
    ];

    for (const filePath of paths) {
        console.log(
            `${isIgnored(filePath) ? "IGNORED" : "VISIBLE"}  ${filePath}`
        );
    }

    console.log(
        "\nA .gitignore rule does not automatically remove a file that "
        + "is already tracked."
    );
}


/* -------------------------------------------------------------------------
 * 10. Validation and error handling
 * ---------------------------------------------------------------------- */

function demonstrateValidation() {
    printSection("8. Validation and failure handling");

    const model = new GitThreeAreaModel();

    const operations = [
        () => model.add("missing.txt"),
        () => model.editFile("missing.txt", "data"),
        () => model.commit("")
    ];

    for (const operation of operations) {
        try {
            operation();
        } catch (error) {
            console.log(`Handled error: ${error.message}`);
        }
    }

    console.log(
        "\nGood tooling should fail clearly rather than silently changing "
        + "the wrong state."
    );
}


/* -------------------------------------------------------------------------
 * 11. Real Git command execution
 * ---------------------------------------------------------------------- */

async function gitAvailable() {
    try {
        const result = await execFileAsync(
            "git",
            ["--version"],
            { windowsHide: true }
        );

        return result.stdout.trim();
    } catch {
        return null;
    }
}

async function runGit(cwd, args, options = {}) {
    try {
        const result = await execFileAsync(
            "git",
            args,
            {
                cwd,
                windowsHide: true,
                maxBuffer: 1024 * 1024,
                ...options
            }
        );

        return {
            stdout: result.stdout,
            stderr: result.stderr
        };
    } catch (error) {
        const detail =
            error.stderr ||
            error.stdout ||
            error.message;

        throw new Error(
            `Git command failed: git ${args.join(" ")}\n${detail}`
        );
    }
}

async function demonstrateRealGit() {
    printSection("9. Real Git commands in a temporary repository");

    const version = await gitAvailable();

    if (!version) {
        console.log(
            "Git is not available in PATH. Skipping real Git execution."
        );
        return;
    }

    console.log(`Detected: ${version}`);

    const temporaryRoot = await fsp.mkdtemp(
        path.join(os.tmpdir(), "git-fundamentals-")
    );

    try {
        await runGit(
            temporaryRoot,
            ["init"]
        );

        await runGit(
            temporaryRoot,
            ["config", "user.name", "Git Fundamentals Student"]
        );

        await runGit(
            temporaryRoot,
            ["config", "user.email", "student@example.com"]
        );

        const readmePath = path.join(
            temporaryRoot,
            "README.md"
        );

        const appPath = path.join(
            temporaryRoot,
            "app.js"
        );

        await fsp.writeFile(
            readmePath,
            "# Git Fundamentals\n",
            "utf8"
        );

        await fsp.writeFile(
            appPath,
            "console.log('version 1');\n",
            "utf8"
        );

        let result = await runGit(
            temporaryRoot,
            ["status", "--short"]
        );

        console.log("\nInitial status:");
        console.log(result.stdout.trim());

        await runGit(
            temporaryRoot,
            ["add", "README.md", "app.js"]
        );

        result = await runGit(
            temporaryRoot,
            ["status", "--short"]
        );

        console.log("\nAfter git add:");
        console.log(result.stdout.trim());

        result = await runGit(
            temporaryRoot,
            ["diff", "--cached"]
        );

        console.log("\nStaged diff:");
        console.log(result.stdout.trim());

        await runGit(
            temporaryRoot,
            ["commit", "-m", "Initial project"]
        );

        result = await runGit(
            temporaryRoot,
            ["status", "--short"]
        );

        console.log("\nAfter commit:");
        console.log(result.stdout.trim() || "Working tree clean.");

        await fsp.writeFile(
            appPath,
            "console.log('version 2');\n",
            "utf8"
        );

        result = await runGit(
            temporaryRoot,
            ["status", "--short"]
        );

        console.log("\nAfter working-tree modification:");
        console.log(result.stdout.trim());

        result = await runGit(
            temporaryRoot,
            ["diff"]
        );

        console.log("\nUnstaged diff:");
        console.log(result.stdout.trim());

        await runGit(
            temporaryRoot,
            ["add", "app.js"]
        );

        result = await runGit(
            temporaryRoot,
            ["diff", "--cached"]
        );

        console.log("\nStaged diff:");
        console.log(result.stdout.trim());

        result = await runGit(
            temporaryRoot,
            ["log", "--oneline", "--decorate"]
        );

        console.log("\nHistory:");
        console.log(result.stdout.trim());

        result = await runGit(
            temporaryRoot,
            ["rev-parse", "--git-dir"]
        );

        console.log(`\nGit directory: ${result.stdout.trim()}`);
    } finally {
        await fsp.rm(
            temporaryRoot,
            {
                recursive: true,
                force: true
            }
        );

        console.log(
            "\nTemporary repository removed."
        );
    }
}


/* -------------------------------------------------------------------------
 * 12. Edge cases
 * ---------------------------------------------------------------------- */

function demonstrateEdgeCases() {
    printSection("10. Edge cases");

    const model = new GitThreeAreaModel({
        committed: {
            "data.txt": "A\n"
        },
        staged: {
            "data.txt": "A\n"
        },
        working: {
            "data.txt": "A\n"
        }
    });

    model.editFile("data.txt", "B\n");
    model.add("data.txt");
    model.editFile("data.txt", "C\n");

    console.log(
        "After stage B and edit again to C:"
    );

    model.showStatus();

    showDiff(
        model.diffCommitToStage(),
        "Commit -> staging area"
    );

    showDiff(
        model.diffStageToWorking(),
        "Staging area -> working tree"
    );

    model.unstage("data.txt");

    console.log(
        "\nAfter unstage:"
    );

    model.showStatus();

    console.log(
        "\nThe exact behavior of destructive commands depends on the "
        + "specific command and options. Verify the intended source and "
        + "destination before discarding changes."
    );
}


/* -------------------------------------------------------------------------
 * 13. Performance discussion
 * ---------------------------------------------------------------------- */

function demonstratePerformance() {
    printSection("11. Performance considerations");

    const topics = {
        "Repository size":
            "History accumulates objects, so repositories containing large or frequently changing binaries can become expensive.",
        "Object reuse":
            "Content-addressed storage allows identical objects to be reused rather than represented as unrelated content.",
        "Packing":
            "Git can pack objects to reduce storage and improve transfer efficiency.",
        "Working tree":
            "Status and diff operations may inspect filesystem state, so very large projects can require careful tooling and repository organization.",
        "Commit granularity":
            "Focused commits make history easier to inspect and can simplify debugging and review."
    };

    for (const [topic, explanation] of Object.entries(topics)) {
        console.log(`\n${topic}:`);
        console.log(`  ${explanation}`);
    }
}


/* -------------------------------------------------------------------------
 * 14. Security
 * ---------------------------------------------------------------------- */

function demonstrateSecurity() {
    printSection("12. Security considerations");

    const rules = [
        "Do not commit passwords, API tokens, private keys, or other credentials.",
        "Use .gitignore to reduce accidental tracking of local secret files.",
        "Review git diff and git diff --cached before committing sensitive work.",
        "Deleting a secret in a later commit does not necessarily remove it from older history.",
        "Remote repository permissions are separate from local Git permissions.",
        "Commit signing can provide cryptographic evidence associated with a commit, but signing does not validate the safety of the code itself.",
        "Git object IDs provide integrity-oriented content addressing, not authorization."
    ];

    rules.forEach(
        (rule, index) => console.log(`${index + 1}. ${rule}`)
    );
}


/* -------------------------------------------------------------------------
 * 15. Tests
 * ---------------------------------------------------------------------- */

function assertEqual(actual, expected, message) {
    if (actual !== expected) {
        throw new Error(
            `${message}\nExpected: ${expected}\nActual: ${actual}`
        );
    }
}

function runSelfTests() {
    printSection("13. Self-tests");

    const model = new GitThreeAreaModel();

    model.createFile("a.txt", "one");

    assertEqual(
        model.status().get("a.txt"),
        "untracked",
        "New files should initially be untracked."
    );

    model.add("a.txt");

    assertEqual(
        model.status().get("a.txt"),
        "new file staged",
        "git add should place a new file in the staging area."
    );

    model.commit("Add file");

    assertEqual(
        model.status().get("a.txt"),
        "clean",
        "A committed file should be clean."
    );

    model.editFile("a.txt", "two");

    assertEqual(
        model.status().get("a.txt"),
        "modified",
        "An edited tracked file should be modified."
    );

    model.add("a.txt");

    assertEqual(
        model.status().get("a.txt"),
        "modified and staged",
        "A staged modification should be reported as staged."
    );

    model.editFile("a.txt", "three");

    assertEqual(
        model.status().get("a.txt"),
        "staged and additionally modified",
        "A second edit after staging creates two change boundaries."
    );

    console.log("All JavaScript self-tests passed.");
}


/* -------------------------------------------------------------------------
 * 16. Main
 * ---------------------------------------------------------------------- */

async function main() {
    console.log("=".repeat(78));
    console.log("GIT FUNDAMENTALS");
    console.log("Repository, Working Tree, and Staging Area");
    console.log("=".repeat(78));

    explainTerminology();
    demonstrateThreeAreas();
    demonstrateFunctionalClassification();
    demonstrateObjectDatabase();
    demonstrateBranches();
    demonstrateCommitGraph();
    demonstrateGitignore();
    demonstrateValidation();
    demonstrateEdgeCases();
    demonstratePerformance();
    demonstrateSecurity();
    runSelfTests();
    await demonstrateRealGit();

    printSection("14. Core conceptual model");

    console.log(`
Working tree
     |
     | git add
     v
Staging area / index
     |
     | git commit
     v
Repository history

Important distinctions:
  git diff          = working tree compared with the index
  git diff --cached = index compared with the current commit
  git commit        = records the staged snapshot
  branch            = movable reference to a commit
  HEAD              = current checkout reference
`);
}

main().catch((error) => {
    console.error("\nFatal error:");
    console.error(error.message);
    process.exitCode = 1;
});
```
