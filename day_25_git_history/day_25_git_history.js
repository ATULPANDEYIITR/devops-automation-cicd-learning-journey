/*
 * Git History: log, diff, show, reset, revert
 *
 * This file demonstrates Git history concepts through a temporary repository.
 * It uses only Node.js built-in modules and the Git command-line executable.
 *
 * The demonstration covers:
 *   - repository creation
 *   - commit history
 *   - git log
 *   - git show
 *   - git diff
 *   - git reset
 *   - git revert
 *   - revision expressions
 *   - merge history
 *   - reflog
 *   - file-specific history
 *   - automation and machine-readable output
 *
 * The user's existing repositories are never modified.
 */

"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync, spawnSync } = require("child_process");

class GitDemoError extends Error {
    constructor(message) {
        super(message);
        this.name = "GitDemoError";
    }
}

function section(title) {
    console.log(`\n${"=".repeat(78)}`);
    console.log(title);
    console.log("=".repeat(78));
}

function runCommand(command, args = [], cwd = undefined, options = {}) {
    const result = spawnSync(command, args, {
        cwd,
        encoding: "utf8",
        stdio: ["pipe", "pipe", "pipe"],
        ...options
    });

    if (result.error) {
        throw new GitDemoError(
            `Unable to execute ${command}: ${result.error.message}`
        );
    }

    const stdout = result.stdout || "";
    const stderr = result.stderr || "";

    if (result.status !== 0 && options.check !== false) {
        throw new GitDemoError(
            `Command failed: ${command} ${args.join(" ")}\n${stderr.trim()}`
        );
    }

    return {
        status: result.status,
        stdout,
        stderr
    };
}

function git(repository, ...args) {
    return runCommand("git", args, repository);
}

function gitText(repository, ...args) {
    return git(repository, ...args).stdout.trim();
}

function writeFile(repository, relativePath, content) {
    const target = path.join(repository, relativePath);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, content, "utf8");
}

function readFile(repository, relativePath) {
    return fs.readFileSync(path.join(repository, relativePath), "utf8");
}

function showStatus(repository) {
    const output = gitText(repository, "status", "--short", "--branch");
    console.log(output || "(clean working tree)");
}

function commit(repository, message) {
    git(repository, "add", "-A");
    git(repository, "commit", "-m", message);
    return gitText(repository, "rev-parse", "HEAD");
}

function shortHash(repository, revision = "HEAD") {
    return gitText(repository, "rev-parse", "--short", revision);
}

function verifyGit() {
    const result = runCommand("git", ["--version"]);
    console.log(`Using ${result.stdout.trim()}`);
}

function explainModel() {
    section("1. Git history model");

    console.log(`
Git records snapshots and relationships between snapshots.

A normal history looks like:

    A --- B --- C --- D

Each commit has a parent relationship to the previous commit.

Important concepts:

  HEAD
      The current checkout position.

  Branch
      A movable reference pointing to a commit.

  Working tree
      The files currently checked out on disk.

  Index
      The staging area containing the exact content prepared for the next
      commit.

  Repository
      The Git object database and references.

Common revision expressions:

  HEAD
      Current commit.

  HEAD~1
      First-parent ancestor.

  HEAD~2
      Two first-parent steps backward.

  HEAD^
      First parent.

  HEAD^2
      Second parent of a merge commit.

This distinction between working tree, index, and HEAD explains most everyday
Git history behavior.
`);
}

function createRepository(parentDirectory) {
    const repository = path.join(parentDirectory, "git-history-demo");

    fs.mkdirSync(repository, { recursive: true });

    git(repository, "init", "-b", "main");
    git(repository, "config", "user.name", "Git History Demonstration");
    git(repository, "config", "user.email", "git-history-demo@example.invalid");

    writeFile(
        repository,
        "README.md",
        "# Git History Demonstration\n\nInitial project.\n"
    );

    writeFile(repository, "app.txt", "Application version 1\n");
    commit(repository, "Initial project");

    writeFile(
        repository,
        "app.txt",
        "Application version 1\nFeature A enabled\n"
    );
    commit(repository, "Add feature A");

    writeFile(
        repository,
        "config.txt",
        "mode=development\nlogging=basic\n"
    );
    commit(repository, "Add development configuration");

    return repository;
}

function demonstrateLog(repository) {
    section("2. git log");

    console.log(`
git log primarily answers:

    "What commits exist in this history?"

Useful forms include:

    git log
    git log --oneline
    git log --graph --decorate --oneline --all
    git log -n 5
    git log --stat
    git log -p
    git log -- path/to/file
`);

    console.log("\nFull log:");
    console.log(gitText(repository, "log"));

    console.log("\nCompact log:");
    console.log(gitText(repository, "log", "--oneline", "--decorate"));

    console.log("\nGraph:");
    console.log(
        gitText(
            repository,
            "log",
            "--graph",
            "--decorate",
            "--oneline",
            "--all"
        )
    );

    console.log("\nHistory affecting app.txt:");
    console.log(
        gitText(
            repository,
            "log",
            "--oneline",
            "--",
            "app.txt"
        )
    );
}

function demonstrateShow(repository) {
    section("3. git show");

    console.log(`
git show is useful when one particular object needs inspection.

Examples:

    git show HEAD
    git show HEAD~1
    git show --stat HEAD
    git show HEAD:path/to/file
`);

    console.log("\nLatest commit summary:");
    console.log(gitText(repository, "show", "--stat", "HEAD"));

    console.log("\nHistorical contents of app.txt:");
    console.log(
        gitText(repository, "show", "HEAD:app.txt")
    );
}

function demonstrateDiff(repository) {
    section("4. git diff");

    console.log(`
Git diff compares states.

The common comparisons are:

    git diff
        Working tree versus index.

    git diff --cached
        Index versus HEAD.

    git diff HEAD
        Working tree and index versus HEAD.

    git diff A B
        Commit A versus commit B.
`);

    writeFile(
        repository,
        "app.txt",
        "Application version 1\nFeature A enabled\nFeature B experimental\n"
    );

    console.log("\nUnstaged change:");
    showStatus(repository);

    console.log("\ngit diff:");
    console.log(gitText(repository, "diff"));

    git(repository, "add", "app.txt");

    console.log("\nAfter staging:");
    showStatus(repository);

    console.log("\ngit diff:");
    console.log(
        git(repository, "diff").stdout || "(none)"
    );

    console.log("\ngit diff --cached:");
    console.log(gitText(repository, "diff", "--cached"));

    console.log("\ngit diff HEAD:");
    console.log(gitText(repository, "diff", "HEAD"));

    // Restore the temporary demonstration change.
    git(repository, "restore", "--staged", "app.txt");
    git(repository, "restore", "app.txt");

    console.log("\nRestored:");
    showStatus(repository);

    console.log("\nCommitted-state comparison:");
    console.log(
        gitText(repository, "diff", "HEAD~2", "HEAD")
    );
}

function demonstrateReset(repository) {
    section("5. git reset");

    console.log(`
reset can move the current branch and optionally change the index and
working tree.

Three important modes:

    --soft
        Move the branch reference only.

    --mixed
        Move the branch and reset the index while preserving working-tree
        files. This is the default mode.

    --hard
        Move the branch, reset the index, and make the working tree match.
        Uncommitted changes can be destroyed.

Conceptually:

    mode       HEAD       index       working tree
    ---------  ---------  ----------  -------------
    --soft     moved      unchanged   unchanged
    --mixed    moved      reset       unchanged
    --hard     moved      reset       reset
`);

    writeFile(
        repository,
        "reset-demo.txt",
        "Temporary reset demonstration commit.\n"
    );

    const temporaryCommit = commit(
        repository,
        "Temporary reset demonstration commit"
    );

    console.log(`Temporary commit: ${temporaryCommit}`);

    writeFile(
        repository,
        "reset-demo.txt",
        "Temporary reset demonstration commit.\n" +
        "Uncommitted local modification.\n"
    );

    git(repository, "reset", "--mixed", "HEAD~1");

    console.log("\nAfter mixed reset:");
    showStatus(repository);
    console.log(readFile(repository, "reset-demo.txt"));

    git(repository, "restore", "reset-demo.txt");
    git(repository, "clean", "-fd");

    // Soft reset demonstration.
    writeFile(
        repository,
        "soft-demo.txt",
        "This commit will be moved back with soft reset.\n"
    );

    commit(repository, "Temporary soft-reset commit");

    git(repository, "reset", "--soft", "HEAD~1");

    console.log("\nAfter soft reset:");
    showStatus(repository);

    // Return to a clean state for subsequent examples.
    git(repository, "reset", "--mixed", "HEAD");
    git(repository, "restore", ".");
    git(repository, "clean", "-fd");
}

function demonstrateRevert(repository) {
    section("6. git revert");

    console.log(`
revert creates a NEW commit that reverses an earlier commit.

If:

    A --- B --- C

is reverted at C, the result is conceptually:

    A --- B --- C --- D

where D contains the inverse of C.

This preserves the original commit C in the history. That distinction makes
revert particularly useful when an existing history has already been shared.
`);

    writeFile(
        repository,
        "revert-demo.txt",
        "Feature intentionally introduced for revert demonstration.\n"
    );

    const target = commit(
        repository,
        "Add feature that will be reverted"
    );

    console.log(`Commit being reverted: ${target}`);

    git(repository, "revert", "--no-edit", target);

    console.log("\nHistory after revert:");
    console.log(
        gitText(repository, "log", "--oneline", "-5")
    );

    console.log("\nFile after revert:");
    console.log(readFile(repository, "revert-demo.txt"));
}

function demonstrateRevisionSyntax(repository) {
    section("7. Revision expressions");

    console.log(`
Revision expressions let commands identify commits precisely.

Examples:

    HEAD
    HEAD~1
    HEAD~2
    HEAD^
    branch-name
    tag-name
    commit-id

Ranges:

    A..B
        Commits reachable from B but not A.

    A...B
        Symmetric difference between the two histories.

For diff, three-dot syntax is especially important because:

    git diff A...B

uses the merge base of A and B as the comparison starting point.
`);

    console.log("\nHEAD:");
    console.log(gitText(repository, "rev-parse", "HEAD"));

    console.log("\nHEAD~1:");
    console.log(gitText(repository, "rev-parse", "HEAD~1"));

    console.log("\nParent-aware history:");
    console.log(
        gitText(
            repository,
            "log",
            "--oneline",
            "--parents",
            "-5"
        )
    );
}

function demonstrateMergeHistory(repository) {
    section("8. Merge-aware history");

    console.log(`
Merge commits can have multiple parents.

Example:

              C --- D
             /       \
    A --- B --------- M

M has B as its first parent and D as its second parent.

Therefore:

    M^
        first parent

    M^2
        second parent

` + "`git log --first-parent`" + ` follows the mainline parent chain.
`);

    const originalBranch = gitText(
        repository,
        "branch",
        "--show-current"
    );

    git(repository, "switch", "-c", "history-feature");

    writeFile(
        repository,
        "feature.txt",
        "Feature branch change.\n"
    );
    commit(repository, "Add feature branch change");

    git(repository, "switch", originalBranch);

    writeFile(
        repository,
        "mainline.txt",
        "Main branch change.\n"
    );
    commit(repository, "Add mainline change");

    git(
        repository,
        "merge",
        "--no-ff",
        "history-feature",
        "-m",
        "Merge history feature"
    );

    console.log("\nMerged graph:");
    console.log(
        gitText(
            repository,
            "log",
            "--graph",
            "--decorate",
            "--oneline",
            "--all"
        )
    );

    console.log("\nFirst-parent history:");
    console.log(
        gitText(
            repository,
            "log",
            "--first-parent",
            "--oneline",
            "-8"
        )
    );

    git(repository, "branch", "-D", "history-feature");
}

function demonstrateFileHistory(repository) {
    section("9. File-specific history");

    console.log(`
History can be restricted to paths.

Examples:

    git log -- path
    git log -p -- path
    git log --follow -- path

` + "`--follow`" + ` is primarily useful for tracking one path through a rename.
`);

    console.log("\napp.txt history:");
    console.log(
        gitText(repository, "log", "--oneline", "--", "app.txt")
    );

    console.log("\napp.txt patch history:");
    console.log(
        gitText(repository, "log", "-p", "--", "app.txt")
    );

    console.log("\nLine attribution:");
    console.log(
        gitText(repository, "blame", "app.txt")
    );
}

function demonstratePrettyFormats(repository) {
    section("10. Machine-friendly log formats");

    console.log(`
Human-oriented Git output is excellent for interactive use, but automation
should prefer a stable explicit format.

Useful placeholders include:

    %H   full hash
    %h   abbreviated hash
    %an  author name
    %ae  author email
    %ad  author date
    %s   subject
    %p   parents
`);

    console.log(
        gitText(
            repository,
            "log",
            "--pretty=format:%h | %ad | %an | %s",
            "--date=short",
            "-10"
        )
    );
}

function demonstrateReflog(repository) {
    section("11. Reflog");

    console.log(`
The reflog records local movements of references.

Typical recovery process:

    git reflog
    git show <candidate>
    git branch recovery <candidate>

Reflog is local metadata. It is not a substitute for a remote backup and
entries can eventually expire.
`);

    console.log(
        gitText(repository, "reflog", "-10")
    );
}

function diagnose(repository) {
    section("12. Repository diagnostic");

    const branch = gitText(repository, "branch", "--show-current");
    const head = gitText(repository, "rev-parse", "--short", "HEAD");

    const upstream = runCommand(
        "git",
        ["rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{u}"],
        repository,
        { check: false }
    );

    console.log(`Branch: ${branch}`);
    console.log(`HEAD:   ${head}`);
    console.log(
        `Upstream: ${upstream.status === 0 ? upstream.stdout.trim() : "not configured"}`
    );

    console.log("\nStatus:");
    showStatus(repository);

    console.log("\nRecent history:");
    console.log(
        gitText(
            repository,
            "log",
            "--decorate",
            "--oneline",
            "-6"
        )
    );

    console.log("\nUnstaged diff statistics:");
    console.log(
        gitText(repository, "diff", "--stat") || "(none)"
    );

    console.log("\nStaged diff statistics:");
    console.log(
        gitText(repository, "diff", "--cached", "--stat") || "(none)"
    );
}

function runChecks(repository) {
    section("13. Automated checks");

    const checks = [];

    const head = runCommand(
        "git",
        ["rev-parse", "HEAD"],
        repository,
        { check: false }
    );

    checks.push([
        "HEAD resolves",
        head.status === 0 && head.stdout.trim().length > 0
    ]);

    const count = Number(
        gitText(repository, "rev-list", "--count", "HEAD")
    );

    checks.push([
        "History contains at least three commits",
        count >= 3
    ]);

    const parent = runCommand(
        "git",
        ["rev-parse", "HEAD~1"],
        repository,
        { check: false }
    );

    checks.push([
        "HEAD~1 resolves",
        parent.status === 0
    ]);

    const show = runCommand(
        "git",
        ["show", "--quiet", "HEAD"],
        repository,
        { check: false }
    );

    checks.push([
        "git show can inspect HEAD",
        show.status === 0
    ]);

    const status = gitText(repository, "status", "--porcelain");

    checks.push([
        "Working tree is clean",
        status.length === 0
    ]);

    for (const [description, passed] of checks) {
        console.log(`[${passed ? "PASS" : "FAIL"}] ${description}`);
    }

    if (!checks.every(([, passed]) => passed)) {
        throw new GitDemoError("One or more automated checks failed.");
    }
}

function cleanup(repository) {
    if (fs.existsSync(repository)) {
        fs.rmSync(repository, {
            recursive: true,
            force: true
        });
    }
}

function main() {
    verifyGit();
    explainModel();

    const temporaryDirectory = fs.mkdtempSync(
        path.join(os.tmpdir(), "git-history-learning-")
    );

    const repository = createRepository(temporaryDirectory);

    console.log(`\nTemporary repository: ${repository}`);

    try {
        demonstrateLog(repository);
        demonstrateShow(repository);
        demonstrateDiff(repository);
        demonstrateReset(repository);
        demonstrateRevert(repository);
        demonstrateRevisionSyntax(repository);
        demonstrateMergeHistory(repository);
        demonstrateFileHistory(repository);
        demonstratePrettyFormats(repository);
        demonstrateReflog(repository);
        diagnose(repository);
        runChecks(repository);

        section("14. Final state");
        console.log(
            gitText(
                repository,
                "log",
                "--graph",
                "--decorate",
                "--oneline",
                "--all"
            )
        );
        showStatus(repository);
    } finally {
        cleanup(temporaryDirectory);
    }

    section("15. End");
    console.log(
        "The demonstration completed in a temporary repository. " +
        "No existing repository was modified."
    );
}

try {
    main();
} catch (error) {
    console.error(`\nERROR: ${error.message}`);
    process.exitCode = 1;
}
