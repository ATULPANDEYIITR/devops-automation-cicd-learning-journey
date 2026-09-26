/*
 * Git Advanced: rebase, cherry-pick, stash, and reflog
 * =====================================================
 *
 * This standalone Node.js program complements the Python study script by
 * demonstrating Git operations from an application/automation perspective.
 *
 * It:
 *   1. Creates an isolated temporary repository.
 *   2. Executes real Git commands through Node's child_process API.
 *   3. Builds divergent branches.
 *   4. Demonstrates rebase.
 *   5. Demonstrates cherry-pick.
 *   6. Demonstrates stash and stash inspection.
 *   7. Demonstrates reflog and recovery concepts.
 *   8. Demonstrates automated validation and failure handling.
 *
 * Requirements:
 *   - Node.js 18+
 *   - Git installed and available on PATH
 *
 * Run:
 *   node git-advanced.js
 */

"use strict";

const fs = require("fs");
const os = require("os");
const path = require("path");
const {
    execFileSync,
    spawnSync
} = require("child_process");


// ---------------------------------------------------------------------------
// SECTION 1: COMMAND EXECUTION
// ---------------------------------------------------------------------------

class GitCommandError extends Error {
    constructor(command, result) {
        super(
            `Git command failed: ${command.join(" ")}\n` +
            `stdout:\n${result.stdout}\n` +
            `stderr:\n${result.stderr}`
        );

        this.command = command;
        this.stdout = result.stdout;
        this.stderr = result.stderr;
        this.status = result.status;
    }
}


function runCommand(command, workingDirectory, allowFailure = false) {
    const result = spawnSync(command[0], command.slice(1), {
        cwd: workingDirectory,
        encoding: "utf8"
    });

    const stdout = result.stdout || "";
    const stderr = result.stderr || "";

    if (result.error) {
        throw result.error;
    }

    if (!allowFailure && result.status !== 0) {
        throw new GitCommandError(command, {
            stdout,
            stderr,
            status: result.status
        });
    }

    return {
        stdout: stdout.trim(),
        stderr: stderr.trim(),
        status: result.status
    };
}


function git(repo, ...argumentsList) {
    return runCommand(
        ["git", ...argumentsList],
        repo
    ).stdout;
}


function gitAllowFailure(repo, ...argumentsList) {
    return runCommand(
        ["git", ...argumentsList],
        repo,
        true
    );
}


function printCommand(command, output = "") {
    console.log(`\n$ ${command}`);

    if (output) {
        console.log(output);
    }
}


function section(title) {
    console.log("\n" + "=".repeat(78));
    console.log(title);
    console.log("=".repeat(78));
}


function subsection(title) {
    console.log("\n" + "-".repeat(70));
    console.log(title);
    console.log("-".repeat(70));
}


// ---------------------------------------------------------------------------
// SECTION 2: FILE AND REPOSITORY UTILITIES
// ---------------------------------------------------------------------------

function writeFile(repo, filename, content) {
    const filePath = path.join(repo, filename);
    fs.mkdirSync(path.dirname(filePath), { recursive: true });
    fs.writeFileSync(filePath, content, "utf8");
}


function appendFile(repo, filename, content) {
    const filePath = path.join(repo, filename);
    fs.appendFileSync(filePath, content, "utf8");
}


function createCommit(repo, message) {
    git(repo, "add", ".");
    git(repo, "commit", "-m", message);
    return git(repo, "rev-parse", "--short", "HEAD");
}


function showGraph(repo) {
    printCommand(
        "git log --graph --oneline --decorate --all",
        git(repo, "log", "--graph", "--oneline", "--decorate", "--all")
    );
}


function configureRepository(repo) {
    git(repo, "config", "user.name", "Git Advanced JavaScript Study");
    git(repo, "config", "user.email", "javascript-git-study@example.invalid");
}


function createRepository() {
    const temporaryDirectory = fs.mkdtempSync(
        path.join(os.tmpdir(), "git-advanced-js-")
    );

    git(temporaryDirectory, "init", "-b", "main");
    configureRepository(temporaryDirectory);

    writeFile(
        temporaryDirectory,
        "README.txt",
        "Git advanced Node.js study repository\n"
    );

    writeFile(
        temporaryDirectory,
        "service.txt",
        "service version 1\n"
    );

    createCommit(temporaryDirectory, "Initial service");

    return temporaryDirectory;
}


// ---------------------------------------------------------------------------
// SECTION 3: BEGINNER GIT MODEL
// ---------------------------------------------------------------------------

function demonstrateGitModel(repo) {
    section("1. Git Model from a Node.js Automation Perspective");

    console.log(`
A Node.js application can automate Git by treating Git as an external
process.

The important Git objects and concepts are:

  Working tree -> files on disk
  Index        -> staged snapshot preparation
  Commit       -> immutable snapshot plus parent information
  Branch       -> movable reference to a commit
  HEAD         -> symbolic reference describing the current checkout

Node's child_process APIs allow scripts to inspect and manipulate this state.
`);

    printCommand(
        "git status --short --branch",
        git(repo, "status", "--short", "--branch")
    );

    printCommand(
        "git rev-parse --short HEAD",
        git(repo, "rev-parse", "--short", "HEAD")
    );

    printCommand(
        "git show --stat --oneline HEAD",
        git(repo, "show", "--stat", "--oneline", "HEAD")
    );
}


// ---------------------------------------------------------------------------
// SECTION 4: BRANCHING AND REBASE
// ---------------------------------------------------------------------------

function demonstrateRebase(repo) {
    section("2. Rebase");

    console.log(`
Rebase changes the base of a sequence of commits.

Conceptually:

    A --- M1                 main
     \\
      F1 --- F2              feature

After:

    A --- M1 --- F1' --- F2' feature

The feature commits are recreated. Their resulting commit IDs differ because
their parent relationship has changed.

This is why rebase is history rewriting rather than simple branch movement.
`);

    git(repo, "switch", "-c", "feature/dashboard");

    writeFile(
        repo,
        "dashboard.txt",
        "dashboard implementation\n"
    );

    const featureCommit1 = createCommit(
        repo,
        "Add dashboard implementation"
    );

    appendFile(
        repo,
        "dashboard.txt",
        "dashboard validation\n"
    );

    const featureCommit2 = createCommit(
        repo,
        "Add dashboard validation"
    );

    git(repo, "switch", "main");

    appendFile(
        repo,
        "service.txt",
        "main branch improvement\n"
    );

    const mainCommit = createCommit(
        repo,
        "Improve service on main"
    );

    console.log(`
Feature commits before rebase:
  ${featureCommit1}
  ${featureCommit2}

Main commit:
  ${mainCommit}
`);

    git(repo, "switch", "feature/dashboard");

    const oldFeatureTip = git(repo, "rev-parse", "HEAD");

    printCommand(
        "git rebase main",
        git(repo, "rebase", "main")
    );

    const newFeatureTip = git(repo, "rev-parse", "HEAD");

    console.log(`
Feature tip before rebase: ${oldFeatureTip}
Feature tip after rebase:  ${newFeatureTip}

The tip changed because the feature commits were recreated.
`);

    showGraph(repo);

    subsection("Interactive rebase");

    console.log(`
Interactive rebase uses a todo list to transform a sequence of commits.

Common actions:

  pick    keep a commit
  reword  change its message
  edit    stop for manual modification
  squash  combine with previous commit
  fixup   combine and discard the selected message
  drop    remove a commit

Typical command:

  git rebase -i HEAD~4

Interactive rebase is particularly useful for organizing local commits before
they become shared history.
`);
}


// ---------------------------------------------------------------------------
// SECTION 5: CHERRY-PICK
// ---------------------------------------------------------------------------

function demonstrateCherryPick(repo) {
    section("3. Cherry-pick");

    console.log(`
Cherry-pick applies the patch introduced by a selected commit to the current
branch.

It does not transfer the original commit object as the current branch tip.
Git creates a new commit representing the applied change.

This is useful when a particular fix must move to a release or maintenance
branch without merging an entire feature branch.
`);

    git(repo, "switch", "main");
    git(repo, "switch", "-c", "feature/security-fix");

    writeFile(
        repo,
        "validation.txt",
        "strict input validation\n"
    );

    const sourceCommit = createCommit(
        repo,
        "Add strict input validation"
    );

    git(repo, "switch", "main");

    writeFile(
        repo,
        "release.txt",
        "release preparation\n"
    );

    createCommit(repo, "Prepare release");

    const mainBeforeCherryPick = git(repo, "rev-parse", "HEAD");

    printCommand(
        `git cherry-pick ${sourceCommit}`,
        git(repo, "cherry-pick", sourceCommit)
    );

    const mainAfterCherryPick = git(repo, "rev-parse", "HEAD");

    console.log(`
Source commit:             ${sourceCommit}
Main before cherry-pick:  ${mainBeforeCherryPick}
Main after cherry-pick:   ${mainAfterCherryPick}
`);

    showGraph(repo);

    subsection("Selecting multiple commits");

    console.log(`
Specific commits can be selected individually:

  git cherry-pick <commit-a> <commit-b>

A contiguous range can also be expressed using revision notation, for example:

  git cherry-pick <oldest>^..<newest>

Care is required when commits depend on earlier changes that are not present
on the target branch.
`);

    subsection("Cherry-pick failure states");

    console.log(`
If a conflict occurs:

  git status
  # resolve the conflicted files
  git add <resolved-files>
  git cherry-pick --continue

To abandon:

  git cherry-pick --abort

If the operation becomes empty because equivalent changes already exist:

  git cherry-pick --skip

Automated tooling must inspect exit status rather than assuming a successful
return from every Git command.
`);
}


// ---------------------------------------------------------------------------
// SECTION 6: STASH
// ---------------------------------------------------------------------------

function demonstrateStash(repo) {
    section("4. Stash");

    console.log(`
A stash temporarily stores changes from the working tree.

It is useful when a developer needs a clean checkout without turning unfinished
work into a permanent branch commit.

A stash should generally be considered short-lived working storage rather than
the primary historical record of valuable work.
`);

    git(repo, "switch", "main");

    appendFile(
        repo,
        "service.txt",
        "unfinished service work\n"
    );

    writeFile(
        repo,
        "draft.txt",
        "unfinished draft\n"
    );

    printCommand(
        "git status --short",
        git(repo, "status", "--short")
    );

    printCommand(
        'git stash push -u -m "WIP: unfinished service work"',
        git(
            repo,
            "stash",
            "push",
            "-u",
            "-m",
            "WIP: unfinished service work"
        )
    );

    printCommand(
        "git status --short",
        git(repo, "status", "--short")
    );

    subsection("Stash inspection");

    printCommand(
        "git stash list",
        git(repo, "stash", "list")
    );

    printCommand(
        "git stash show --stat stash@{0}",
        git(repo, "stash", "show", "--stat", "stash@{0}")
    );

    printCommand(
        "git stash show --patch stash@{0}",
        git(repo, "stash", "show", "--patch", "stash@{0}")
    );

    subsection("Apply versus pop");

    console.log(`
git stash apply:
  Reapplies the stash while retaining the stash entry.

git stash pop:
  Reapplies the stash and normally removes the entry if application succeeds.

For cautious inspection, apply is useful because the original stash remains
available until explicitly dropped.
`);

    git(repo, "stash", "apply", "stash@{0}");

    printCommand(
        "git status --short",
        git(repo, "status", "--short")
    );

    // Return the working tree to a clean state.
    git(repo, "restore", "--worktree", "--staged", ".");
    git(repo, "clean", "-fd");

    subsection("Untracked files");

    writeFile(
        repo,
        "tracked-example.txt",
        "tracked file\n"
    );

    createCommit(repo, "Add tracked stash example");

    appendFile(
        repo,
        "tracked-example.txt",
        "unstaged modification\n"
    );

    writeFile(
        repo,
        "untracked-example.txt",
        "untracked work\n"
    );

    printCommand(
        "git status --short",
        git(repo, "status", "--short")
    );

    git(
        repo,
        "stash",
        "push",
        "-u",
        "-m",
        "Tracked and untracked example"
    );

    printCommand(
        "git stash list",
        git(repo, "stash", "list")
    );

    git(repo, "stash", "pop");

    printCommand(
        "git status --short",
        git(repo, "status", "--short")
    );

    git(repo, "restore", "--worktree", "--staged", ".");
    git(repo, "clean", "-fd");

    subsection("Stash branch");

    writeFile(
        repo,
        "recovered-draft.txt",
        "draft requiring its own branch\n"
    );

    git(
        repo,
        "stash",
        "push",
        "-m",
        "Draft requiring dedicated branch"
    );

    printCommand(
        "git stash branch recovered-draft stash@{0}",
        git(
            repo,
            "stash",
            "branch",
            "recovered-draft",
            "stash@{0}"
        )
    );

    console.log(`
The stash branch operation creates a branch from the commit that was checked
out when the stash was created and reapplies the saved work.

This can be useful when unfinished work belongs on a separate branch.
`);

    git(repo, "switch", "main");
}


// ---------------------------------------------------------------------------
// SECTION 7: REFLOG AND RECOVERY
// ---------------------------------------------------------------------------

function demonstrateReflog(repo) {
    section("5. Reflog");

    console.log(`
The reflog records local reference movement.

Typical events include:

  - new commits
  - branch switching
  - reset
  - rebase
  - checkout
  - other reference updates

The reflog is different from git log. A normal log emphasizes commits
reachable through a reference, while the reflog records local movements of
references such as HEAD.
`);

    writeFile(
        repo,
        "recoverable.txt",
        "content intended for recovery demonstration\n"
    );

    const recoverableCommit = createCommit(
        repo,
        "Create recoverable commit"
    );

    console.log(`Recoverable commit: ${recoverableCommit}`);

    printCommand(
        "git reflog --oneline",
        git(repo, "reflog", "--oneline")
    );

    subsection("Intentional reset");

    writeFile(
        repo,
        "temporary-history.txt",
        "temporary history\n"
    );

    const temporaryCommit = createCommit(
        repo,
        "Create temporary history"
    );

    console.log(`Temporary commit: ${temporaryCommit}`);

    git(repo, "reset", "--hard", "HEAD~1");

    printCommand(
        "git log --oneline -5",
        git(repo, "log", "--oneline", "-5")
    );

    printCommand(
        "git reflog --oneline -10",
        git(repo, "reflog", "--oneline", "-10")
    );

    console.log(`
The branch no longer points to the temporary commit after reset.

The reflog can still provide the previous reference position. Once a desired
commit is identified, a cautious recovery technique is:

  git switch -c recovery <commit>

This creates a new branch without immediately rewriting an existing branch.

Another possible recovery action is:

  git reset --hard <commit>

That should only be performed after confirming the intended target.
`);

    subsection("Why reflog is local");

    console.log(`
Reflog is not a shared remote history mechanism.

A different clone does not automatically receive your local reflog entries.
Reflog entries can also expire according to Git's maintenance and expiration
configuration.

For durable recovery, important commits should exist on an appropriate branch
and be pushed to a controlled remote when policy permits.
`);
}


// ---------------------------------------------------------------------------
// SECTION 8: AUTOMATION SAFETY
// ---------------------------------------------------------------------------

function demonstrateAutomationSafety(repo) {
    section("6. Automation Safety and Error Handling");

    console.log(`
A production Node.js Git automation script should treat Git as an external
system whose commands can fail.

Important practices include:

  - check process exit status
  - capture stdout and stderr
  - do not automatically continue after a conflict
  - verify the current branch before destructive operations
  - avoid hard-coded assumptions about commit IDs
  - quote or safely pass arguments as separate process arguments
  - log the operation being attempted
`);

    subsection("Detecting an invalid operation");

    const failure = gitAllowFailure(
        repo,
        "rebase",
        "branch-that-does-not-exist"
    );

    console.log(`Command exit status: ${failure.status}`);

    if (failure.status !== 0) {
        console.log("Failure detected without terminating the program.");
        console.log(`Git stderr: ${failure.stderr}`);
    }

    subsection("Checking repository state");

    printCommand(
        "git status --porcelain=v1 --branch",
        git(repo, "status", "--porcelain=v1", "--branch")
    );

    printCommand(
        "git branch --show-current",
        git(repo, "branch", "--show-current")
    );
}


// ---------------------------------------------------------------------------
// SECTION 9: PERFORMANCE AND SECURITY
// ---------------------------------------------------------------------------

function explainProductionConsiderations() {
    section("7. Performance, Security, and Production Considerations");

    console.log(`
REBASE
------
Rebase can require replaying many commits. Focused commits and manageable
branch histories make conflict resolution easier.

CHERRY-PICK
----------
Cherry-pick is selective, but selecting a commit without its dependencies can
produce an incomplete change. Commit design matters.

STASH
-----
Stashing normal source changes is usually straightforward. Including ignored
files with `git stash -a` can capture large build artifacts and generated
content.

REFLOG
------
Reflog is excellent for local recovery but is not a backup system.

FORCE PUSHING
-------------
After intentional history rewriting, `git push --force-with-lease` is safer
than unconditional `git push --force` because it checks the remote reference
against the expected state.

SECURITY
--------
Git history can contain secrets even after a later commit deletes them.

If a secret enters history:
  1. Rotate or revoke the exposed secret.
  2. Determine where the repository history was copied.
  3. Remove sensitive history using an appropriate history-rewriting process.
  4. Coordinate repository cleanup.

A normal deletion commit does not erase the earlier object from Git history.

AUTOMATION
----------
Never construct shell commands by concatenating untrusted strings. This
program passes Git arguments as separate process arguments through
spawnSync(), avoiding an unnecessary shell interpretation layer.
`);
}


// ---------------------------------------------------------------------------
// SECTION 10: COMMAND REFERENCE
// ---------------------------------------------------------------------------

function printCommandReference() {
    section("8. Command Reference");

    const reference = {
        "History inspection": [
            "git log --graph --oneline --decorate --all",
            "git show <commit>",
            "git diff <base>...<branch>",
            "git merge-base <branch-a> <branch-b>"
        ],

        "Rebase": [
            "git rebase <base>",
            "git rebase -i HEAD~N",
            "git rebase --continue",
            "git rebase --skip",
            "git rebase --abort",
            "git rebase --show-current-patch"
        ],

        "Cherry-pick": [
            "git cherry-pick <commit>",
            "git cherry-pick <commit-a> <commit-b>",
            "git cherry-pick --continue",
            "git cherry-pick --skip",
            "git cherry-pick --abort"
        ],

        "Stash": [
            'git stash push -m "message"',
            'git stash push -u -m "message"',
            "git stash list",
            "git stash show --stat stash@{0}",
            "git stash show --patch stash@{0}",
            "git stash apply stash@{0}",
            "git stash pop stash@{0}",
            "git stash drop stash@{0}",
            "git stash branch <branch> stash@{0}"
        ],

        "Reflog": [
            "git reflog",
            "git reflog show <branch>",
            "git show <commit>",
            "git switch -c recovery <commit>",
            "git reset --hard <commit>"
        ],

        "Publishing rewritten history": [
            "git push --force-with-lease"
        ]
    };

    for (const [category, commands] of Object.entries(reference)) {
        console.log(`\n${category}:`);
        for (const command of commands) {
            console.log(`  ${command}`);
        }
    }
}


// ---------------------------------------------------------------------------
// SECTION 11: MAIN
// ---------------------------------------------------------------------------

function main() {
    try {
        const gitVersion = execFileSync(
            "git",
            ["--version"],
            { encoding: "utf8" }
        ).trim();

        console.log(gitVersion);

        const repo = createRepository();

        console.log(`Temporary repository: ${repo}`);

        try {
            demonstrateGitModel(repo);
            demonstrateRebase(repo);
            demonstrateCherryPick(repo);
            demonstrateStash(repo);
            demonstrateReflog(repo);
            demonstrateAutomationSafety(repo);
            explainProductionConsiderations();
            printCommandReference();

            console.log(`
==============================================================================
STUDY COMPLETE
==============================================================================

The Node.js implementation demonstrated:

  Rebase       -> replay commits onto a different base
  Cherry-pick  -> selectively apply a commit's patch
  Stash        -> temporarily preserve unfinished work
  Reflog       -> inspect reference movement and recovery opportunities

The temporary repository is being removed.
`);
        } finally {
            fs.rmSync(repo, {
                recursive: true,
                force: true
            });
        }
    } catch (error) {
        console.error("\nExecution failed.");

        if (error instanceof GitCommandError) {
            console.error(error.message);
        } else {
            console.error(error.message || error);
        }

        process.exitCode = 1;
    }
}


main();
