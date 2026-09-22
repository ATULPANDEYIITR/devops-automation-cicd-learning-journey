#!/usr/bin/env node
"use strict";

/*
 * Git Commands: init, clone, status, add, commit, push, pull
 *
 * This file demonstrates the core Git workflow using Node.js and the
 * standard-library child_process and fs modules.
 *
 * Requirements:
 *   - Node.js 18+
 *   - Git installed and available on PATH
 *
 * All repositories are created inside a temporary directory so that the
 * demonstration does not modify an existing user project.
 */

const fs = require("fs");
const os = require("os");
const path = require("path");
const { execFileSync } = require("child_process");

function section(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}

function run(command, args = [], cwd = undefined, options = {}) {
    /*
     * execFileSync avoids shell parsing. Passing arguments separately is
     * safer than constructing one large shell command string.
     */
    console.log("$", command, ...args);

    try {
        const output = execFileSync(command, args, {
            cwd,
            encoding: "utf8",
            stdio: ["ignore", "pipe", "pipe"],
            ...options
        });

        if (output.trim()) {
            console.log(output.trimEnd());
        }

        return output;
    } catch (error) {
        console.error("Command failed.");
        console.error(`Exit status: ${error.status ?? "unknown"}`);

        if (error.stdout) {
            console.error("STDOUT:");
            console.error(error.stdout.toString());
        }

        if (error.stderr) {
            console.error("STDERR:");
            console.error(error.stderr.toString());
        }

        throw error;
    }
}

function git(args, cwd = undefined) {
    return run("git", args, cwd);
}

function writeFile(filePath, content) {
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content, "utf8");
}

function readFile(filePath) {
    return fs.readFileSync(filePath, "utf8");
}

function configureIdentity(repository, name, email) {
    git(["config", "user.name", name], repository);
    git(["config", "user.email", email], repository);
}

function currentBranch(repository) {
    return git(["branch", "--show-current"], repository).trim();
}

function explainModel() {
    section("1. Git's basic model");

    console.log(`
Git is a distributed version control system.

The core workflow contains several different states:

Working tree
    Files currently present in the project directory.

Staging area
    The set of file contents selected for the next commit.

Local repository
    Git's database containing commits and related metadata.

Remote repository
    Another Git repository used to share or synchronize history.

The fundamental movement is:

    Working tree
         |
         | git add
         v
    Staging area
         |
         | git commit
         v
    Local repository
         |
         | git push
         v
    Remote repository

The reverse synchronization operation is commonly:

    git pull

which obtains remote history and integrates it into the current local
branch according to the configured pull strategy.
`);
}

function checkGit() {
    section("2. Verify Git installation");

    try {
        git(["--version"]);
        return true;
    } catch {
        console.error(
            "\nGit is not available. Install Git and make sure it is on PATH."
        );
        return false;
    }
}

function demonstrateInitAndStatus(base) {
    section("3. git init and git status");

    const repository = path.join(base, "init-status-demo");
    fs.mkdirSync(repository);

    console.log("Before initialization:");
    console.log(
        "Has .git directory:",
        fs.existsSync(path.join(repository, ".git"))
    );

    git(["init"], repository);

    console.log("\nAfter initialization:");
    console.log(
        "Has .git directory:",
        fs.existsSync(path.join(repository, ".git"))
    );

    writeFile(
        path.join(repository, "README.md"),
        "# Git Learning Project\n"
    );

    writeFile(
        path.join(repository, "app.js"),
        'console.log("Hello from Git");\n'
    );

    console.log("\nInitial status:");
    git(["status", "--short"], repository);

    console.log(`
git init creates a new Git repository in the current directory.

It does not:
    - create a commit automatically,
    - push files to GitHub,
    - make files automatically tracked.

git status reports the relationship between the working tree, staging area,
and repository history.
`);

    writeFile(
        path.join(repository, "README.md"),
        "# Git Learning Project\n\nREADME modified after initialization.\n"
    );

    console.log("\nStatus after modifying README.md:");
    git(["status", "--short"], repository);

    return repository;
}

function demonstrateAddAndCommit(repository) {
    section("4. git add and git commit");

    console.log("Before staging:");
    git(["status", "--short"], repository);

    git(["add", "README.md"], repository);

    console.log("\nAfter staging README.md:");
    git(["status", "--short"], repository);

    writeFile(
        path.join(repository, "app.js"),
        'console.log("Version 2");\n'
    );

    console.log("\nAfter modifying app.js:");
    git(["status", "--short"], repository);

    git(["add", "app.js"], repository);

    console.log("\nAfter staging app.js:");
    git(["status", "--short"], repository);

    configureIdentity(
        repository,
        "JavaScript Git Lab",
        "javascript-git@example.invalid"
    );

    git(
        ["commit", "-m", "Create initial project files"],
        repository
    );

    console.log("\nStatus after commit:");
    git(["status"], repository);

    console.log("\nCommit history:");
    git(["log", "--oneline", "--decorate", "-5"], repository);

    console.log(`
git add selects file contents for the next commit.

git commit creates a local historical snapshot from the staging area.

The separation is important:

    git add
        Selects content.

    git commit
        Records selected content locally.

    git push
        Sends local commits to a remote.

A commit is not automatically published to GitHub simply because it was
created successfully.
`);

    return repository;
}

function demonstrateClonePushPull(base) {
    section("5. git clone, git push, and git pull");

    const remote = path.join(base, "remote.git");
    const source = path.join(base, "source");
    const clone = path.join(base, "clone");

    git(["init", "--bare", remote], base);
    fs.mkdirSync(source);

    git(["init"], source);

    configureIdentity(
        source,
        "Source Developer",
        "source@example.invalid"
    );

    writeFile(
        path.join(source, "project.txt"),
        "Initial project content\n"
    );

    git(["add", "project.txt"], source);

    git(
        ["commit", "-m", "Create initial project"],
        source
    );

    git(
        ["remote", "add", "origin", remote],
        source
    );

    console.log("\nConfigured remotes:");
    git(["remote", "-v"], source);

    const branch = currentBranch(source);

    console.log(`\nCurrent source branch: ${branch}`);

    git(
        ["push", "-u", "origin", branch],
        source
    );

    console.log(`
git push transfers commits from a local repository to a remote repository.

The -u option establishes an upstream relationship. After this relationship
exists, a later git push can often omit the remote and branch.
`);

    console.log("\nCloning the repository:");
    git(["clone", remote, clone], base);

    configureIdentity(
        clone,
        "Clone Developer",
        "clone@example.invalid"
    );

    console.log("\nClone status:");
    git(["status"], clone);

    console.log("\nClone remotes:");
    git(["remote", "-v"], clone);

    writeFile(
        path.join(source, "project.txt"),
        "Initial project content\nSecond line from source.\n"
    );

    git(["add", "project.txt"], source);

    git(
        ["commit", "-m", "Add second project line"],
        source
    );

    git(["push"], source);

    console.log("\nPulling source changes into clone:");
    git(["pull"], clone);

    console.log("\nFile after pull:");
    console.log(readFile(path.join(clone, "project.txt")));

    console.log(`
git init and git clone serve different purposes.

git init:
    Start a repository in an existing directory.

git clone:
    Create a new working copy from an existing repository.

git push:
    Publish local commits to the configured remote.

git pull:
    Obtain remote changes and integrate them into the current branch.

The common conceptual model is:

    pull ≈ fetch + integration

The exact integration behavior can involve merge or rebase depending on
configuration and command options.
`);
}

function demonstrateStagingSnapshot(base) {
    section("6. Staging is a snapshot, not a permanent pointer");

    const repository = path.join(base, "staging-demo");
    fs.mkdirSync(repository);

    git(["init"], repository);

    configureIdentity(
        repository,
        "Staging Demonstrator",
        "staging@example.invalid"
    );

    const notes = path.join(repository, "notes.txt");

    writeFile(notes, "Line one\n");

    git(["add", "notes.txt"], repository);
    git(["commit", "-m", "Create notes"], repository);

    writeFile(notes, "Line one\nLine two\n");
    git(["add", "notes.txt"], repository);

    writeFile(notes, "Line one\nLine two\nLine three\n");

    console.log(`
The file was staged after Line Two was written.

Then the working tree changed again.

Therefore the staging area contains a different snapshot from the working
tree. Git status exposes this distinction.
`);

    git(["status", "--short"], repository);
}

function demonstrateEdgeCases(base) {
    section("7. Edge cases and failure conditions");

    const repository = path.join(base, "edge-case-demo");
    fs.mkdirSync(repository);

    git(["init"], repository);

    configureIdentity(
        repository,
        "Edge Case Demonstrator",
        "edge@example.invalid"
    );

    console.log(`
Case 1: untracked file
----------------------
A file can exist on disk without being part of Git history.
`);

    writeFile(
        path.join(repository, "untracked.txt"),
        "Not tracked yet.\n"
    );

    git(["status", "--short"], repository);

    console.log(`
Case 2: staged file
-------------------
git add changes the file's state from untracked or modified to staged.
`);

    git(["add", "untracked.txt"], repository);
    git(["status", "--short"], repository);

    console.log(`
Case 3: commit requires identity
--------------------------------
Git commits require author and committer information. Repository-local
configuration avoids changing the user's global configuration in this lab.
`);

    git(
        ["commit", "-m", "Track untracked file"],
        repository
    );

    console.log(`
Case 4: remote synchronization
--------------------------------
If another repository pushes a commit that the current repository does not
have, a later push can be rejected as non-fast-forward.

The safe conceptual response is to inspect the remote changes, integrate them
appropriately, resolve conflicts when required, and then push again.
`);

    console.log(`
Case 5: no commit yet
---------------------
A newly initialized repository has no commit until git commit succeeds.
This distinction matters when configuring branches and pushing the first
commit.
`);
}

function commandReference() {
    section("8. Command reference");

    const commands = [
        ["git init", "Create a local repository."],
        ["git clone <url>", "Copy an existing repository."],
        ["git status", "Inspect repository state."],
        ["git add <file>", "Stage a selected file."],
        ["git add .", "Stage changes below the current directory."],
        ["git commit -m \"message\"", "Create a local commit."],
        ["git remote -v", "Show configured remote URLs."],
        ["git push", "Send local commits to the upstream."],
        ["git push -u origin main", "Push and establish upstream."],
        ["git pull", "Fetch and integrate remote changes."],
        ["git log --oneline", "Display compact history."]
    ];

    for (const [command, purpose] of commands) {
        console.log(`${command.padEnd(36)} ${purpose}`);
    }
}

function advancedConcepts() {
    section("9. Advanced concepts");

    console.log(`
HEAD
    HEAD normally identifies the current checkout position.

Branch
    A movable reference to a line of development.

origin
    A conventional remote name. It is only a local name and can be changed.

Upstream
    The remote branch associated with a local branch for default
    synchronization operations.

Fast-forward
    A branch reference can move directly forward because no divergent local
    history needs to be combined.

Non-fast-forward
    The destination contains history that the source does not contain.
    Git can reject a push to prevent accidental history loss.

Remote-tracking branch
    A reference such as origin/main represents the last fetched knowledge of
    the remote main branch.

Fetch
    Downloads remote objects and updates remote-tracking references without
    automatically integrating them into the current branch.

Pull
    Fetches and then integrates remote changes according to configuration.

Merge
    Combines histories while preserving their existing ancestry.

Rebase
    Replays commits onto another base and changes commit ancestry. It is
    powerful but should be used carefully with already-published commits.

Commit hash
    A commit has an object identifier derived from its content and metadata.

Authentication
    Remote hosting can use mechanisms such as SSH keys, HTTPS credentials,
    credential helpers, or provider-specific authentication.

Security
    Git does not make secrets safe merely because a repository is private.
    Passwords, private keys, access tokens, and other credentials should not
    be committed.

Git history
    Removing a secret from the current file does not necessarily remove it
    from earlier commits. Sensitive data accidentally committed to a shared
    repository requires deliberate remediation.
`);
}

function productionWorkflow() {
    section("10. Practical workflow");

    console.log(`
For an existing project:

    git pull
    git status
    edit files
    git status
    git add <specific files>
    git status
    git commit -m "Describe the logical change"
    git push

For a new project:

    git init
    git status
    git add .
    git commit -m "Initial project"
    git remote add origin <remote-url>
    git push -u origin main

Important distinctions:

    init    = create local repository
    clone   = copy existing repository
    status  = inspect state
    add     = stage content
    commit  = record local history
    push    = publish local commits
    pull    = synchronize remote changes into local work

A disciplined Git user repeatedly checks status rather than guessing what
Git is about to commit or push.
`);
}

function main() {
    console.log("=".repeat(78));
    console.log("GIT COMMANDS LAB");
    console.log("init | clone | status | add | commit | push | pull");
    console.log("=".repeat(78));

    if (!checkGit()) {
        return;
    }

    explainModel();

    const base = fs.mkdtempSync(
        path.join(os.tmpdir(), "git-learning-")
    );

    console.log(`\nTemporary laboratory directory:\n${base}`);

    try {
        const repository = demonstrateInitAndStatus(base);
        demonstrateAddAndCommit(repository);
        demonstrateClonePushPull(base);
        demonstrateStagingSnapshot(base);
        demonstrateEdgeCases(base);
        commandReference();
        advancedConcepts();
        productionWorkflow();

        section("11. Lab completed");
        console.log(
            "All repositories were created in a temporary directory."
        );
    } finally {
        fs.rmSync(base, {
            recursive: true,
            force: true
        });

        console.log("\nTemporary repositories removed.");
    }
}

main();
