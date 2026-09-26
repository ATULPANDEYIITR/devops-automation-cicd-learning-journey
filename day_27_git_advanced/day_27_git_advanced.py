"""
Git Advanced: rebase, cherry-pick, stash, and reflog
=====================================================

A standalone executable study file covering four advanced Git mechanisms:

1. Rebase
2. Cherry-pick
3. Stash
4. Reflog

The demonstrations use a temporary Git repository created by Python, so the
examples are reproducible without modifying an existing project.

Prerequisite:
    Git must be installed and available as `git` on PATH.

Run:
    python git_advanced.py

The script teaches concepts through actual Git commands rather than merely
printing theoretical descriptions.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# SECTION 1: GENERAL UTILITIES
# ---------------------------------------------------------------------------

class GitError(RuntimeError):
    """Raised when a Git command fails unexpectedly."""


def run_command(
    command: list[str],
    cwd: Path,
    check: bool = True,
) -> str:
    """
    Execute a command and return its standard output.

    Git commands are intentionally executed as subprocesses because the
    purpose of this program is to demonstrate real Git behavior.
    """
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )

    if check and result.returncode != 0:
        raise GitError(
            f"Command failed: {' '.join(command)}\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )

    return result.stdout.strip()


def git(repo: Path, *arguments: str, check: bool = True) -> str:
    """Run a Git command inside a repository."""
    return run_command(["git", *arguments], repo, check=check)


def section(title: str) -> None:
    """Print a visually separated study section."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def subsection(title: str) -> None:
    print("\n" + "-" * 70)
    print(title)
    print("-" * 70)


def show(command: str, output: str) -> None:
    """Display an executed Git command and its result."""
    print(f"\n$ {command}")
    if output:
        print(output)


def write_file(repo: Path, filename: str, content: str) -> None:
    """Create or replace a repository file."""
    path = repo / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def append_file(repo: Path, filename: str, content: str) -> None:
    """Append text to a repository file."""
    path = repo / filename
    with path.open("a", encoding="utf-8") as file:
        file.write(content)


def commit(repo: Path, message: str) -> str:
    """Stage all changes and create a commit."""
    git(repo, "add", ".")
    git(repo, "commit", "-m", message)
    return git(repo, "rev-parse", "--short", "HEAD")


def log_graph(repo: Path) -> None:
    """Display a compact graphical history."""
    output = git(
        repo,
        "log",
        "--graph",
        "--oneline",
        "--decorate",
        "--all",
        "-20",
    )
    show("git log --graph --oneline --decorate --all -20", output)


def current_branch(repo: Path) -> str:
    return git(repo, "branch", "--show-current")


def commit_tree(repo: Path, ref: str = "HEAD") -> str:
    """Return a compact commit-parent description."""
    return git(
        repo,
        "show",
        "-s",
        "--format=%h %s | parent=%p",
        ref,
    )


def verify_git_available() -> None:
    """Fail early with a useful message if Git is unavailable."""
    result = subprocess.run(
        ["git", "--version"],
        text=True,
        capture_output=True,
        check=False,
    )

    if result.returncode != 0:
        raise SystemExit(
            "Git was not found on PATH. Install Git and run this script again."
        )

    print(result.stdout.strip())


def configure_repository(repo: Path) -> None:
    """
    Configure identity locally.

    Local configuration prevents the demonstration from changing the user's
    global Git identity.
    """
    git(repo, "config", "user.name", "Git Advanced Study")
    git(repo, "config", "user.email", "git-study@example.invalid")
    git(repo, "config", "init.defaultBranch", "main")


def create_repository() -> Path:
    """Create a temporary Git repository and configure it."""
    temporary_directory = tempfile.mkdtemp(prefix="git-advanced-study-")
    repo = Path(temporary_directory)

    git(repo, "init", "-b", "main")
    configure_repository(repo)

    write_file(
        repo,
        "README.txt",
        "Git Advanced Study Repository\n",
    )
    write_file(
        repo,
        "app.txt",
        "version 1\n",
    )
    commit(repo, "Initial project")

    return repo


# ---------------------------------------------------------------------------
# SECTION 2: GIT FUNDAMENTALS REQUIRED FOR ADVANCED OPERATIONS
# ---------------------------------------------------------------------------

def demonstrate_git_model(repo: Path) -> None:
    section("1. Git's Object and Reference Model")

    print(
        """
Git advanced commands become easier to understand when four ideas are kept
separate:

- Working tree: files currently checked out on disk.
- Index/staging area: the proposed contents for the next commit.
- Commit: an immutable snapshot identified by a hash.
- Reference: a movable name such as main, feature/login, HEAD, or a tag.

HEAD normally identifies the current checkout. A branch name points to a
commit. Creating a new commit advances the current branch reference.

A commit also stores parent commit references. This parent relationship is
what makes operations such as rebase and cherry-pick meaningful.
"""
    )

    show(
        "git status --short --branch",
        git(repo, "status", "--short", "--branch"),
    )
    show(
        "git rev-parse HEAD",
        git(repo, "rev-parse", "HEAD"),
    )
    show(
        "git rev-parse --short HEAD",
        git(repo, "rev-parse", "--short", "HEAD"),
    )
    show(
        "git show --stat --oneline HEAD",
        git(repo, "show", "--stat", "--oneline", "HEAD"),
    )


# ---------------------------------------------------------------------------
# SECTION 3: BRANCH CREATION
# ---------------------------------------------------------------------------

def demonstrate_branching(repo: Path) -> None:
    section("2. Branches and Divergent History")

    git(repo, "switch", "-c", "feature/profile")

    append_file(repo, "app.txt", "profile feature\n")
    profile_commit = commit(repo, "Add profile feature")

    write_file(repo, "profile.txt", "profile configuration\n")
    profile_commit_2 = commit(repo, "Add profile configuration")

    print(f"Feature commits: {profile_commit}, {profile_commit_2}")

    git(repo, "switch", "main")

    append_file(repo, "app.txt", "main improvement\n")
    main_commit = commit(repo, "Add main improvement")

    print(f"Main commit: {main_commit}")

    print(
        """
At this point the histories have diverged:

        profile: A --- P1 --- P2
                 /
        main: A --- M1

The exact commit IDs are different on every repository, but the topology is
the important part.
"""
    )

    log_graph(repo)


# ---------------------------------------------------------------------------
# SECTION 4: REBASE
# ---------------------------------------------------------------------------

def demonstrate_rebase(repo: Path) -> None:
    section("3. Rebase")

    subsection("3.1 What rebase means")

    print(
        """
Rebase takes commits from one line of development and replays them on top of
another base commit.

Before:

    A --- M1                 main
     \
      P1 --- P2              feature

After rebasing feature onto main:

    A --- M1 --- P1' --- P2' feature

P1' and P2' are NEW commits. They may contain the same changes as P1 and P2,
but their commit identities are different because their parent relationships
changed.

This is fundamentally different from moving a branch label. Rebase rewrites
commit history.
"""
    )

    git(repo, "switch", "feature/profile")

    before_rebase = git(repo, "rev-parse", "HEAD")

    show(
        "git rebase main",
        git(repo, "rebase", "main"),
    )

    after_rebase = git(repo, "rev-parse", "HEAD")

    print(f"\nFeature tip before rebase: {before_rebase}")
    print(f"Feature tip after rebase:  {after_rebase}")
    print("The feature tip changed because the feature commits were recreated.")

    log_graph(repo)

    subsection("3.2 Inspecting ancestry")

    show(
        "git merge-base main feature/profile",
        git(repo, "merge-base", "main", "feature/profile"),
    )

    show(
        "git log main..feature/profile --oneline",
        git(repo, "log", "main..feature/profile", "--oneline"),
    )

    show(
        "git diff main...feature/profile",
        git(repo, "diff", "main...feature/profile"),
    )

    subsection("3.3 Rebase versus merge")

    print(
        """
Merge:
    - combines histories by creating a merge commit when necessary
    - preserves the existing branch topology
    - does not rewrite existing commits

Rebase:
    - replays commits onto a different base
    - produces new commit objects
    - can create a linear history
    - rewrites the rebased commits

Neither operation is universally correct. The appropriate choice depends on
team workflow, history policy, review practices, and whether commits have
already been shared.
"""
    )

    subsection("3.4 Interactive rebase concepts")

    print(
        """
Interactive rebase is commonly used to edit a sequence of commits.

Typical actions include:

    pick    keep a commit
    reword  change its commit message
    edit    stop and modify a commit
    squash  combine it with the previous commit
    fixup   combine it while discarding its message
    drop    remove the commit

Example command:

    git rebase -i HEAD~4

The command opens an editor containing the last four commits. The developer
can reorder or transform those commits before Git replays them.

Interactive rebase is particularly useful for cleaning local work before
sharing it.
"""
    )

    subsection("3.5 Rebase conflicts")

    print(
        """
A conflict occurs when Git cannot automatically determine how a replayed
change should be applied.

During a rebase:

    git status

helps identify the conflicted files.

After resolving a conflict:

    git add <resolved-file>
    git rebase --continue

To abandon the entire rebase:

    git rebase --abort

To inspect rebase state:

    git status
    git rebase --show-current-patch

The critical safety principle is to understand which operation is currently
active before issuing another command.
"""
    )


# ---------------------------------------------------------------------------
# SECTION 5: CHERRY-PICK
# ---------------------------------------------------------------------------

def demonstrate_cherry_pick(repo: Path) -> None:
    section("4. Cherry-pick")

    subsection("4.1 Purpose")

    print(
        """
Cherry-pick applies the change introduced by an existing commit onto the
current branch.

It does NOT move the original commit.

Conceptually:

    main:    A --- M1
                    \
                     ?   <- cherry-pick target

    source:  A --- S1

After cherry-pick:

    main:    A --- M1 --- S1'
    source:  A --- S1

S1' is a new commit containing the patch represented by S1.
"""
    )

    # Create a source branch containing a focused change.
    git(repo, "switch", "main")
    git(repo, "switch", "-c", "feature/urgent-fix")

    write_file(
        repo,
        "urgent_fix.txt",
        "Critical validation fix\n",
    )
    source_commit = commit(repo, "Add urgent validation fix")

    print(f"Source commit: {source_commit}")

    # Return to main and create unrelated work.
    git(repo, "switch", "main")

    write_file(
        repo,
        "release.txt",
        "Release preparation\n",
    )
    commit(repo, "Prepare release")

    target_before = git(repo, "rev-parse", "HEAD")

    cherry_output = git(repo, "cherry-pick", source_commit)

    target_after = git(repo, "rev-parse", "HEAD")

    show(f"git cherry-pick {source_commit}", cherry_output)

    print(f"\nTarget before cherry-pick: {target_before}")
    print(f"Target after cherry-pick:  {target_after}")

    log_graph(repo)

    subsection("4.2 Cherry-pick versus merge versus rebase")

    print(
        """
Cherry-pick:
    Selects specific commits and applies their changes elsewhere.

Merge:
    Combines branch histories, usually preserving the complete topology.

Rebase:
    Replays a sequence of commits on a new base and rewrites their identities.

Cherry-pick is useful when a specific fix is needed on a maintenance or
release branch without bringing every change from another branch.
"""
    )

    subsection("4.3 Cherry-pick conflicts")

    print(
        """
If the selected patch conflicts with the target branch:

    git status

shows the conflict.

After resolution:

    git add <resolved-file>
    git cherry-pick --continue

To cancel the cherry-pick:

    git cherry-pick --abort

If the selected commit turns out to have no useful changes because the target
already contains equivalent content, Git can report an empty cherry-pick.
Depending on the situation, the operation can be skipped with:

    git cherry-pick --skip
"""
    )


# ---------------------------------------------------------------------------
# SECTION 6: STASH
# ---------------------------------------------------------------------------

def demonstrate_stash(repo: Path) -> None:
    section("5. Stash")

    subsection("5.1 Working tree versus committed history")

    print(
        """
A stash temporarily records work that is not ready to become a normal
commit.

It is especially useful when:

    - unfinished changes exist
    - another branch must be checked out
    - a clean working tree is temporarily required
    - an urgent fix must be inspected or applied

A stash is not a replacement for normal versioned commits. A meaningful unit
of completed work is usually safer when represented by a commit.
"""
    )

    git(repo, "switch", "main")

    write_file(
        repo,
        "draft.txt",
        "unfinished draft\n",
    )
    append_file(repo, "app.txt", "unfinished application change\n")

    show(
        "git status --short",
        git(repo, "status", "--short"),
    )

    stash_output = git(
        repo,
        "stash",
        "push",
        "-m",
        "WIP: unfinished application change",
    )

    show(
        'git stash push -m "WIP: unfinished application change"',
        stash_output,
    )

    show(
        "git status --short",
        git(repo, "status", "--short"),
    )

    subsection("5.2 Stash inspection")

    show(
        "git stash list",
        git(repo, "stash", "list"),
    )

    show(
        "git stash show --stat stash@{0}",
        git(repo, "stash", "show", "--stat", "stash@{0}"),
    )

    show(
        "git stash show --patch stash@{0}",
        git(repo, "stash", "show", "--patch", "stash@{0}"),
    )

    subsection("5.3 Apply versus pop")

    print(
        """
git stash apply:
    Reapplies a stash but keeps the stash entry.

git stash pop:
    Reapplies a stash and attempts to remove that stash entry.

A practical safety pattern is to use `apply` when you want to inspect the
result before deciding whether the stash should be removed.
"""
    )

    git(repo, "stash", "apply", "stash@{0}")

    show(
        "git status --short",
        git(repo, "status", "--short"),
    )

    # Clean the applied changes so later demonstrations remain deterministic.
    git(repo, "restore", "--worktree", "--staged", ".")
    git(repo, "clean", "-fd")

    subsection("5.4 Stashing staged and untracked files")

    write_file(repo, "tracked_change.txt", "tracked modification\n")
    commit(repo, "Add tracked example")

    append_file(repo, "tracked_change.txt", "unstaged modification\n")
    write_file(repo, "untracked.txt", "untracked work\n")

    show(
        "git status --short",
        git(repo, "status", "--short"),
    )

    git(repo, "stash", "push", "-u", "-m", "Include untracked work")

    show(
        "git stash list",
        git(repo, "stash", "list"),
    )

    print(
        """
The `-u` option includes untracked files.

By default, ordinary `git stash push` handles tracked working-tree changes.
Ignored files require stronger options such as `-a`, which includes ignored
files as well. Use that deliberately because build artifacts and generated
files can substantially increase stash contents.
"""
    )

    # Restore the latest stash and then remove it explicitly.
    git(repo, "stash", "pop")

    show(
        "git status --short",
        git(repo, "status", "--short"),
    )

    git(repo, "restore", "--worktree", "--staged", ".")
    git(repo, "clean", "-fd")

    subsection("5.5 Stash branch")

    write_file(repo, "branch_work.txt", "work that needs a dedicated branch\n")
    git(repo, "stash", "push", "-m", "Work requiring dedicated branch")

    stash_branch_output = git(
        repo,
        "stash",
        "branch",
        "recovered-work",
        "stash@{0}",
    )

    show(
        "git stash branch recovered-work stash@{0}",
        stash_branch_output,
    )

    print(
        """
`git stash branch <branch> <stash>` creates a new branch from the commit that
was current when the stash was created and reapplies the stash there.

This can be useful when the original branch has moved and the unfinished work
fits more naturally on a separate branch.
"""
    )

    # Leave repository on main for the following demonstrations.
    git(repo, "switch", "main")


# ---------------------------------------------------------------------------
# SECTION 7: REFLOG
# ---------------------------------------------------------------------------

def demonstrate_reflog(repo: Path) -> None:
    section("6. Reflog")

    subsection("6.1 What reflog records")

    print(
        """
The reflog records movements of references in a local repository.

Examples include:

    - committing
    - switching branches
    - resetting
    - rebasing
    - checking out different commits
    - moving branch references

Typical command:

    git reflog

Unlike the normal commit graph, reflog information is local and is primarily
a recovery mechanism for references that have moved.

The reflog can often locate a commit that is no longer reachable from a
current branch name.
"""
    )

    write_file(repo, "reflog_example.txt", "recoverable content\n")
    recovery_commit = commit(repo, "Create recoverable commit")

    print(f"Commit intentionally created for recovery demonstration: {recovery_commit}")

    show(
        "git reflog --date=local",
        git(repo, "reflog", "--date=local"),
    )

    subsection("6.2 Reset and recovery concept")

    before_reset = git(repo, "rev-parse", "HEAD")

    write_file(repo, "temporary_history.txt", "temporary history\n")
    temporary_commit = commit(repo, "Create temporary history")

    print(f"Before reset: {before_reset}")
    print(f"Temporary commit: {temporary_commit}")

    git(repo, "reset", "--hard", "HEAD~1")

    print("\nAfter reset --hard HEAD~1:")
    show(
        "git log --oneline -5",
        git(repo, "log", "--oneline", "-5"),
    )

    print(
        """
The branch name no longer points to the temporary commit, but the reflog
normally retains a record of where HEAD and the branch reference previously
pointed.

Inspect:

    git reflog

Then identify the desired commit and recover it with an appropriate command,
for example:

    git reset --hard <commit>

or create a new branch first:

    git switch -c recovery <commit>

Creating a recovery branch is often the safer choice because it preserves the
recovered commit without immediately moving an existing branch.
"""
    )

    show(
        "git reflog --oneline",
        git(repo, "reflog", "--oneline"),
    )

    # Recover the intentionally reset commit by identifying it from reflog.
    # The temporary commit is the second recent HEAD state.
    recovered_ref = git(
        repo,
        "reflog",
        "-n",
        "5",
        "--format=%H",
    ).splitlines()

    if recovered_ref:
        candidate = recovered_ref[1] if len(recovered_ref) > 1 else recovered_ref[0]
        print(f"\nCandidate recovery commit from reflog: {candidate[:12]}")

    subsection("6.3 Reflog versus log")

    print(
        """
git log:
    Shows commits reachable through the selected history.

git reflog:
    Shows local movements of references.

A commit can disappear from the normal `git log` of a branch after a reset or
rebase while still being discoverable through reflog for a period of time.

Reflog is therefore one of Git's most important local recovery mechanisms.
"""
    )


# ---------------------------------------------------------------------------
# SECTION 8: ADVANCED WORKFLOWS
# ---------------------------------------------------------------------------

def demonstrate_advanced_workflows(repo: Path) -> None:
    section("7. Advanced Workflows")

    subsection("7.1 Updating a feature branch with rebase")

    print(
        """
A common workflow is:

    git switch feature
    git fetch origin
    git rebase origin/main

The feature commits are replayed onto the latest main.

If conflicts occur:

    git status
    # resolve files
    git add <files>
    git rebase --continue

If the operation should be abandoned:

    git rebase --abort

If the feature branch was already pushed and rebased, updating the remote
usually requires a force push. Prefer:

    git push --force-with-lease

over an unconditional force push. `--force-with-lease` checks whether the
remote reference still has the expected value, reducing the chance of
overwriting someone else's newly pushed work.
"""
    )

    subsection("7.2 Moving one fix across release branches")

    print(
        """
A maintenance workflow can be:

    git switch release/1.2
    git cherry-pick <fix-commit>
    git push

This selectively transfers a fix without merging unrelated development.

The team should verify that the selected commit is sufficiently self-contained.
A commit that depends on several other commits may not cherry-pick cleanly or
may produce behavior that is incomplete even if the operation succeeds.
"""
    )

    subsection("7.3 Temporarily changing context with stash")

    print(
        """
A typical interruption workflow:

    git stash push -m "WIP: current feature"
    git switch maintenance
    # perform urgent work
    git switch feature
    git stash pop

For valuable unfinished work, a temporary commit on a private branch can be
more explicit and durable than a stash.
"""
    )

    subsection("7.4 Recovering after destructive history editing")

    print(
        """
A recovery workflow can be:

    git reflog
    git show <candidate>
    git switch -c recovery <candidate>

Only after verifying the recovered history should an existing branch be
rewritten.

The important idea is that Git operations should be understood as movements
of references and creation of new commit objects, rather than as mysterious
changes to a single linear file history.
"""
    )


# ---------------------------------------------------------------------------
# SECTION 9: EDGE CASES AND FAILURE MODES
# ---------------------------------------------------------------------------

def demonstrate_edge_cases(repo: Path) -> None:
    section("8. Edge Cases and Failure Conditions")

    print(
        """
1. Rebase with uncommitted changes
   --------------------------------
   Git may refuse to start a rebase if local changes would be overwritten.
   Stash or commit the changes first, or use a workflow that deliberately
   preserves them.

2. Rebase conflict
   ----------------
   A replayed patch may no longer apply cleanly. Resolve, stage, and continue,
   or abort.

3. Cherry-pick conflict
   --------------------
   A selected patch may conflict with the target branch. Resolve and continue,
   or abort.

4. Empty cherry-pick
   ------------------
   Equivalent changes may already exist on the target. Git may report that
   the cherry-pick is empty.

5. Stash conflict
   ---------------
   Applying a stash can conflict with changes made after the stash was
   created. A stash is a set of changes, not a guarantee of conflict-free
   restoration.

6. Reflog availability
   --------------------
   Reflog is primarily local. It is not a replacement for a remote backup or
   a shared branch history. Reflog entries can eventually expire according to
   repository configuration and Git maintenance.

7. Rebase of public history
   -------------------------
   Rewriting commits that other developers have based work on can force
   coordination and reconciliation. Shared branch policy matters.

8. Force pushing
   ---------------
   Rewriting a remote branch and then using `--force` can overwrite remote
   work. `--force-with-lease` provides a useful safety check.

9. Commit dependency
   -----------------
   Cherry-picking one commit can be misleading if that commit assumes earlier
   commits that are absent from the target branch.

10. Stash as long-term storage
    ---------------------------
    A large collection of forgotten stashes can become difficult to manage.
    Important work should have a durable branch and commit history.
"""
    )

    subsection("Demonstrate command failure without terminating the study")

    failure = git(
        repo,
        "rebase",
        "nonexistent-branch",
        check=False,
    )

    print("\nAttempted invalid rebase:")
    print(failure if failure else "Git produced no standard output.")

    print(
        """
Using subprocess return codes is important in automation. A production
automation script should inspect failures instead of assuming every Git
operation succeeded.
"""
    )


# ---------------------------------------------------------------------------
# SECTION 10: PERFORMANCE AND DESIGN
# ---------------------------------------------------------------------------

def explain_performance_and_design() -> None:
    section("9. Performance, Design, and Production Considerations")

    print(
        """
REBASE
------
Rebase may rewrite many commits. Large histories can require substantial
processing, especially when many patches conflict or when large binary files
are involved.

Useful design practices:
    - keep commits focused
    - avoid mixing unrelated changes
    - rebase regularly when team policy supports it
    - avoid rebasing commits that other people depend on

CHERRY-PICK
----------
Cherry-pick usually targets a small number of commits, but complex patches
can still cause expensive conflict resolution.

Useful design practices:
    - create cohesive commits
    - make fixes independently applicable when practical
    - document dependencies between related changes

STASH
-----
Stash is generally lightweight for normal source changes, but repository
contents and change size matter. Stashing ignored/generated files can be
particularly large.

Useful design practices:
    - use descriptive stash messages
    - keep stash lifetime short
    - use `-u` deliberately
    - use `-a` only when ignored files genuinely need preservation

REFLOG
------
Reflog is valuable for recovery, but it should not be treated as guaranteed
long-term backup storage.

Production repositories should still use:
    - appropriate remote repositories
    - branch protection
    - backups
    - review controls
    - documented recovery procedures

SECURITY
--------
Git operations can expose sensitive information if secrets are committed.
Rebase and cherry-pick do not magically remove sensitive data from every
repository object or remote copy.

If a secret has been committed:
    - revoke or rotate the secret
    - assess where it was pushed
    - remove sensitive history using an appropriate history-rewriting process
    - coordinate cleanup of affected clones and caches

Simply creating a new commit that deletes a secret does not mean the secret
never existed in Git history.
"""
    )


# ---------------------------------------------------------------------------
# SECTION 11: COMMAND REFERENCE
# ---------------------------------------------------------------------------

def print_command_reference() -> None:
    section("10. Practical Command Reference")

    commands = {
        "Inspect history": [
            "git log --graph --oneline --decorate --all",
            "git show <commit>",
            "git diff <base>...<branch>",
            "git merge-base <branch-a> <branch-b>",
        ],
        "Rebase": [
            "git rebase <base>",
            "git rebase -i HEAD~N",
            "git rebase --continue",
            "git rebase --skip",
            "git rebase --abort",
            "git rebase --show-current-patch",
        ],
        "Cherry-pick": [
            "git cherry-pick <commit>",
            "git cherry-pick <commit-a> <commit-b>",
            "git cherry-pick <oldest>^..<newest>",
            "git cherry-pick --continue",
            "git cherry-pick --skip",
            "git cherry-pick --abort",
        ],
        "Stash": [
            "git stash push -m \"message\"",
            "git stash push -u -m \"message\"",
            "git stash list",
            "git stash show --stat stash@{0}",
            "git stash show --patch stash@{0}",
            "git stash apply stash@{0}",
            "git stash pop stash@{0}",
            "git stash drop stash@{0}",
            "git stash branch <branch> stash@{0}",
        ],
        "Reflog and recovery": [
            "git reflog",
            "git reflog show <branch>",
            "git show <reflog-commit>",
            "git switch -c recovery <commit>",
            "git reset --hard <commit>",
        ],
        "Safer publication after intentional rewrite": [
            "git push --force-with-lease",
        ],
    }

    for category, category_commands in commands.items():
        print(f"\n{category}:")
        for command in category_commands:
            print(f"  {command}")


# ---------------------------------------------------------------------------
# SECTION 12: MINI KNOWLEDGE TEST
# ---------------------------------------------------------------------------

def knowledge_test() -> None:
    section("11. Knowledge Check")

    questions = [
        (
            "Which operation replays existing commits onto a new base?",
            "rebase",
        ),
        (
            "Which operation applies the change from a selected commit onto "
            "the current branch?",
            "cherry-pick",
        ),
        (
            "Which mechanism temporarily stores unfinished working changes?",
            "stash",
        ),
        (
            "Which mechanism records local movements of references?",
            "reflog",
        ),
    ]

    correct = 0

    for question, expected in questions:
        print(f"\nQuestion: {question}")
        answer = input("Answer: ").strip().lower()

        if expected in answer:
            print("Correct.")
            correct += 1
        else:
            print(f"Expected concept: {expected}")

    print(f"\nScore: {correct}/{len(questions)}")


# ---------------------------------------------------------------------------
# SECTION 13: MAIN PROGRAM
# ---------------------------------------------------------------------------

def main() -> None:
    verify_git_available()

    repo = create_repository()

    try:
        print(f"\nTemporary repository: {repo}")

        demonstrate_git_model(repo)
        demonstrate_branching(repo)
        demonstrate_rebase(repo)
        demonstrate_cherry_pick(repo)
        demonstrate_stash(repo)
        demonstrate_reflog(repo)
        demonstrate_advanced_workflows(repo)
        demonstrate_edge_cases(repo)
        explain_performance_and_design()
        print_command_reference()

        print(
            """
======================================================================
STUDY COMPLETE
======================================================================

The demonstrations covered:

    Rebase      -> rewrite/replay a sequence of commits on a new base
    Cherry-pick -> apply a selected commit's change elsewhere
    Stash       -> temporarily preserve unfinished working changes
    Reflog      -> inspect local reference movement and recover history

The temporary repository will now be removed.
"""
        )

    finally:
        shutil.rmtree(repo, ignore_errors=True)


if __name__ == "__main__":
    main()
