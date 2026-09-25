"""
Git History: log, diff, show, reset, revert
============================================

A standalone study program for understanding Git history inspection and
history-changing operations.

This file teaches and demonstrates:

1. Git's commit model
2. References, HEAD, branches, and the working tree
3. git log
4. git show
5. git diff
6. git reset
7. git revert
8. The difference between working tree, staging area, and repository
9. Soft, mixed, and hard reset
10. Commit ranges and ancestry
11. Comparing commits, branches, and working states
12. Safe and destructive history operations
13. Merge-aware history
14. Reflog and recovery
15. Practical automation and diagnostics

The demonstrations use a temporary Git repository created by Python.
The Git executable must be installed and available on PATH.

The program deliberately uses subprocess rather than a third-party Git
library so that the examples correspond closely to the actual Git CLI.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


# ---------------------------------------------------------------------------
# Configuration and utility functions
# ---------------------------------------------------------------------------

@dataclass
class CommandResult:
    """Stores the result of a Git command."""

    command: list[str]
    return_code: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0


class GitDemoError(RuntimeError):
    """Raised when a demonstration operation cannot be completed."""


def run_command(
    command: list[str],
    cwd: Path | None = None,
    check: bool = True,
) -> CommandResult:
    """
    Execute a command and return its captured output.

    check=True raises GitDemoError when the command fails. This makes
    demonstrations fail explicitly rather than silently continuing with
    incorrect repository state.
    """
    completed = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )

    result = CommandResult(
        command=command,
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )

    if check and not result.succeeded:
        raise GitDemoError(
            f"Command failed ({result.return_code}): "
            f"{' '.join(command)}\n{result.stderr.strip()}"
        )

    return result


def git(
    repository: Path,
    *arguments: str,
    check: bool = True,
) -> CommandResult:
    """Run Git inside the selected repository."""
    return run_command(
        ["git", *arguments],
        cwd=repository,
        check=check,
    )


def write_file(repository: Path, relative_path: str, content: str) -> None:
    """Create or replace a text file inside the demonstration repository."""
    path = repository / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_file(repository: Path, relative_path: str) -> str:
    """Read a text file from the demonstration repository."""
    return (repository / relative_path).read_text(encoding="utf-8")


def section(title: str) -> None:
    """Print a visible section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def command_output(
    repository: Path,
    *arguments: str,
    check: bool = True,
) -> str:
    """Run Git and return stdout with trailing whitespace removed."""
    result = git(repository, *arguments, check=check)
    return result.stdout.strip()


def commit(
    repository: Path,
    message: str,
    *,
    add_all: bool = True,
) -> str:
    """
    Create a commit and return its full object ID.

    Git requires user identity in order to create commits. The demonstration
    repository sets a local identity, so the user's global Git configuration
    is not modified.
    """
    if add_all:
        git(repository, "add", "-A")

    git(repository, "commit", "-m", message)
    return command_output(repository, "rev-parse", "HEAD")


def short_commit_id(repository: Path, revision: str = "HEAD") -> str:
    """Return the abbreviated object ID for a revision."""
    return command_output(repository, "rev-parse", "--short", revision)


def show_status(repository: Path) -> None:
    """Display a compact repository state."""
    result = git(
        repository,
        "status",
        "--short",
        "--branch",
        check=True,
    )
    print(result.stdout.rstrip() or "(clean working tree)")


def print_file(repository: Path, relative_path: str) -> None:
    """Print a file's current contents."""
    print(f"\n--- {relative_path} ---")
    print(read_file(repository, relative_path), end="")


# ---------------------------------------------------------------------------
# Git model
# ---------------------------------------------------------------------------

def explain_git_model() -> None:
    section("1. Git history model")

    print(
        """
A Git repository is not simply a folder containing a sequence of file
snapshots. Git stores objects and relationships between commits.

A commit normally records:

  - a tree representing the tracked file state
  - one or more parent commits
  - author information
  - committer information
  - a timestamp
  - a commit message

A normal linear history can be visualized as:

    A --- B --- C --- D
          ^
          |
        parent relationship

Here D has C as its parent, C has B as its parent, and so on.

Important references:

  HEAD
      The currently checked-out position. It normally points to a branch.

  Branch
      A movable reference pointing to a commit.

  HEAD~1
      The first parent of HEAD.

  HEAD~2
      Two first-parent steps before HEAD.

  HEAD^
      The first parent of HEAD.

  HEAD^2
      The second parent of a merge commit, if one exists.

  HEAD:path/to/file
      The version of a path stored in the commit referenced by HEAD.

The three practical states are:

  Working tree
      Files currently present in the checked-out directory.

  Index / staging area
      The exact content prepared for the next commit.

  Repository
      Committed Git objects and references.

This distinction is essential for understanding diff and reset.
"""
    )


# ---------------------------------------------------------------------------
# Repository creation
# ---------------------------------------------------------------------------

def create_demo_repository(base_directory: Path) -> Path:
    """
    Create a temporary repository with a deliberately small but useful
    history.
    """
    repository = base_directory / "git-history-demo"
    repository.mkdir(parents=True, exist_ok=True)

    git(repository, "init", "-b", "main")

    # Local identity only. The user's real Git configuration is untouched.
    git(repository, "config", "user.name", "Git History Demonstration")
    git(repository, "config", "user.email", "git-history-demo@example.invalid")

    write_file(
        repository,
        "README.md",
        "# Git History Demonstration\n\nInitial project.\n",
    )
    write_file(
        repository,
        "app.txt",
        "Application version 1\n",
    )
    commit(repository, "Initial project")

    write_file(
        repository,
        "app.txt",
        "Application version 1\nFeature A enabled\n",
    )
    commit(repository, "Add feature A")

    write_file(
        repository,
        "config.txt",
        "mode=development\nlogging=basic\n",
    )
    commit(repository, "Add development configuration")

    return repository


# ---------------------------------------------------------------------------
# git log
# ---------------------------------------------------------------------------

def demonstrate_log(repository: Path) -> None:
    section("2. git log")

    print(
        """
git log answers questions about commit history.

Basic form:

    git log

Useful variants:

    git log --oneline
    git log --graph --decorate --oneline --all
    git log --stat
    git log --patch
    git log --name-status
    git log -n 5
    git log --since="2026-01-01"
    git log --author="name"
    git log -- path/to/file

The following commands show several practical forms.
"""
    )

    print("\nFull commit information:")
    print(command_output(repository, "log"))

    print("\nCompact history:")
    print(
        command_output(
            repository,
            "log",
            "--oneline",
            "--decorate",
        )
    )

    print("\nHistory with graph and references:")
    print(
        command_output(
            repository,
            "log",
            "--graph",
            "--decorate",
            "--oneline",
            "--all",
        )
    )

    print("\nLast two commits:")
    print(command_output(repository, "log", "-2", "--oneline"))

    print("\nHistory affecting app.txt:")
    print(
        command_output(
            repository,
            "log",
            "--oneline",
            "--",
            "app.txt",
        )
    )

    print(
        """
Important distinction:

    git log
        Primarily answers "what commits exist?"

    git show
        Primarily answers "what does this particular commit contain?"

    git diff
        Primarily answers "how do two states differ?"
"""
    )


# ---------------------------------------------------------------------------
# git show
# ---------------------------------------------------------------------------

def demonstrate_show(repository: Path) -> None:
    section("3. git show")

    print(
        """
git show displays information about an object, most commonly a commit.

For a commit, it can show:

  - commit ID
  - author
  - date
  - commit message
  - patch introduced by the commit

Examples:

    git show HEAD
    git show HEAD~1
    git show --stat HEAD
    git show --name-status HEAD
    git show HEAD:path/to/file

The final form is especially useful because it retrieves the content of
a path as stored in a historical commit.
"""
    )

    print("\nMost recent commit:")
    print(command_output(repository, "show", "--stat", "HEAD"))

    print("\nMost recent commit with patch:")
    print(command_output(repository, "show", "--format=fuller", "HEAD"))

    print("\nHistorical app.txt at HEAD:")
    print(
        command_output(
            repository,
            "show",
            "HEAD:app.txt",
        )
    )


# ---------------------------------------------------------------------------
# git diff
# ---------------------------------------------------------------------------

def demonstrate_diff(repository: Path) -> None:
    section("4. git diff")

    print(
        """
git diff compares states.

The most important everyday forms are:

    git diff
        Working tree versus index.

    git diff --cached
        Index versus HEAD.

    git diff HEAD
        Working tree plus index versus HEAD.

    git diff COMMIT_A COMMIT_B
        Difference between two committed states.

    git diff COMMIT -- path
        Difference for one path.

These comparisons are different because Git has three important content
locations: HEAD, index, and working tree.
"""
    )

    # Working-tree change.
    write_file(
        repository,
        "app.txt",
        "Application version 1\nFeature A enabled\nFeature B experimental\n",
    )

    print("\nWorking tree modified, but not staged:")
    show_status(repository)

    print("\ngit diff:")
    print(command_output(repository, "diff"))

    # Stage the change.
    git(repository, "add", "app.txt")

    print("\nChange staged:")
    show_status(repository)

    print("\ngit diff now:")
    diff_after_staging = git(repository, "diff")
    print(diff_after_staging.stdout or "(empty: working tree equals index)")

    print("\ngit diff --cached:")
    print(command_output(repository, "diff", "--cached"))

    print("\ngit diff HEAD:")
    print(command_output(repository, "diff", "HEAD"))

    # Restore the staged change through a history-preserving operation.
    git(repository, "restore", "--staged", "app.txt")
    git(repository, "restore", "app.txt")

    print("\nRepository restored to HEAD:")
    show_status(repository)

    first = short_commit_id(repository, "HEAD~2")
    latest = short_commit_id(repository, "HEAD")

    print(f"\nComparing commits {first} and {latest}:")
    print(
        command_output(
            repository,
            "diff",
            "HEAD~2",
            "HEAD",
        )
    )


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

def demonstrate_reset(repository: Path) -> None:
    section("5. git reset")

    print(
        """
git reset moves the current branch reference and can also change the index
and working tree depending on the selected mode.

Three central modes:

    git reset --soft <commit>
        Move HEAD/branch only.
        Keep index and working tree unchanged.

    git reset --mixed <commit>
        Move HEAD/branch and reset the index.
        Keep working-tree files unchanged.
        This is the default mode.

    git reset --hard <commit>
        Move HEAD/branch, reset the index, and make the working tree match.
        Uncommitted changes can be destroyed.

Conceptually:

                      HEAD       INDEX       WORKING TREE

    --soft            moved       kept        kept

    --mixed            moved       reset      kept

    --hard             moved       reset      reset

Reset changes local history. This makes it fundamentally different from
revert, which creates a new commit that reverses an earlier commit.
"""
    )

    # Add a temporary commit so reset can move the branch safely.
    write_file(
        repository,
        "reset-demo.txt",
        "Temporary commit created to demonstrate reset.\n",
    )
    reset_commit = commit(repository, "Temporary reset demonstration commit")

    print(f"\nCreated temporary commit: {reset_commit}")
    print(command_output(repository, "log", "--oneline", "-4"))

    # Create an uncommitted working-tree change.
    write_file(
        repository,
        "reset-demo.txt",
        "Temporary commit created to demonstrate reset.\n"
        "Uncommitted local modification.\n",
    )

    # --mixed: branch moves back; working tree remains modified.
    target = "HEAD~1"
    print("\nApplying --mixed reset to HEAD~1:")
    git(repository, "reset", "--mixed", target)
    show_status(repository)
    print_file(repository, "reset-demo.txt")

    # Clean up the uncommitted file without affecting history.
    git(repository, "restore", "reset-demo.txt")
    git(repository, "clean", "-fd")

    # Demonstrate --soft.
    write_file(
        repository,
        "soft-demo.txt",
        "This commit will be undone with soft reset.\n",
    )
    soft_commit = commit(repository, "Temporary soft-reset commit")

    print(f"\nSoft-reset demonstration commit: {soft_commit}")
    git(repository, "reset", "--soft", "HEAD~1")

    print("After --soft reset:")
    show_status(repository)

    print(
        "\nThe file remains staged because --soft moves the branch but leaves "
        "the index intact."
    )

    git(repository, "reset", "--mixed", "HEAD")
    git(repository, "restore", ".")
    git(repository, "clean", "-fd")

    print("\nAfter cleanup:")
    show_status(repository)


# ---------------------------------------------------------------------------
# Revert
# ---------------------------------------------------------------------------

def demonstrate_revert(repository: Path) -> None:
    section("6. git revert")

    print(
        """
git revert creates a NEW commit that reverses the effect of an existing
commit.

This is different from reset.

Suppose history is:

    A --- B --- C

If C is undesirable:

    reset:
        A --- B
              ^
            branch

    revert:
        A --- B --- C --- D
                      D reverses C

Reset is commonly used when rewriting local/private history is appropriate.
Revert is commonly used when the existing history has already been shared,
because it preserves the existing commits and records the reversal.

The exact effect of a revert depends on the patch being reversed and on
subsequent changes. Git may require conflict resolution.
"""
    )

    write_file(
        repository,
        "revert-demo.txt",
        "This feature was intentionally added.\n",
    )
    feature_commit = commit(repository, "Add feature that will be reverted")

    print(f"\nCommit to reverse: {feature_commit}")
    print_file(repository, "revert-demo.txt")

    git(repository, "revert", "--no-edit", feature_commit)

    print("\nAfter revert:")
    show_status(repository)

    print("\nRecent history:")
    print(command_output(repository, "log", "--oneline", "-5"))

    print("\nFile after revert:")
    print_file(repository, "revert-demo.txt")


# ---------------------------------------------------------------------------
# Reset versus revert
# ---------------------------------------------------------------------------

def compare_reset_and_revert() -> None:
    section("7. Reset versus revert")

    comparison = """
Operation     Primary effect                         History preserved?
------------  -------------------------------------  ------------------
reset         Moves a branch reference              No, branch history moves
revert        Creates a new inverse commit          Yes
soft reset    Moves branch, keeps index/worktree     No
mixed reset   Moves branch, resets index            No
hard reset    Moves branch and resets files         No; local changes may be lost

A practical decision model:

    Need to remove or reorganize unshared local commits?
        reset may be appropriate.

    Need to undo an already-published commit while preserving history?
        revert is generally the relevant operation.

Neither operation should be selected merely because it produces a desired
visual history. The appropriate operation depends on whether the commits
have been shared and whether preserving existing history is important.
"""
    print(comparison)


# ---------------------------------------------------------------------------
# Revision syntax
# ---------------------------------------------------------------------------

def demonstrate_revision_syntax(repository: Path) -> None:
    section("8. Revision syntax")

    print(
        """
Git has a compact language for identifying commits.

Examples:

    HEAD
        Current commit.

    HEAD~1
        First-parent ancestor.

    HEAD~2
        Two first-parent steps back.

    HEAD^
        First parent.

    branch-name
        Commit currently referenced by a branch.

    tag-name
        Commit referenced by a tag.

    abc1234
        Abbreviated object ID when it uniquely identifies an object.

Ranges are especially important:

    A..B
        Commits reachable from B but not from A.

    A...B
        Symmetric difference of histories, commonly useful for finding
        changes unique to either side.

For example:

    git log main..feature
        Commits in feature that are not reachable from main.

    git diff main...feature
        Commonly compares the feature branch against its merge base,
        which is different from simply comparing the tips.
"""
    )

    print("\nCurrent HEAD:")
    print(command_output(repository, "rev-parse", "HEAD"))

    print("\nHEAD~1:")
    print(command_output(repository, "rev-parse", "HEAD~1"))

    print("\nRecent history with parent relationships:")
    print(
        command_output(
            repository,
            "log",
            "--oneline",
            "--parents",
            "-5",
        )
    )


# ---------------------------------------------------------------------------
# Reflog and recovery
# ---------------------------------------------------------------------------

def demonstrate_reflog(repository: Path) -> None:
    section("9. Reflog and recovery")

    print(
        """
The reflog records movements of references such as HEAD in the local
repository.

Typical command:

    git reflog

It can help locate a commit after operations such as reset.

For example, if:

    A --- B --- C

and a reset moves the branch back to B, commit C may no longer be reachable
from the branch. The reflog can still contain the earlier HEAD position.

A recovery workflow is often:

    git reflog
    git show <recovered-object>
    git branch recovery <recovered-object>

Reflog is local repository metadata. It is not a replacement for a remote
backup and it is subject to Git's retention and garbage-collection behavior.
"""
    )

    print(command_output(repository, "reflog", "-10"))


# ---------------------------------------------------------------------------
# Merge-aware history
# ---------------------------------------------------------------------------

def demonstrate_merge_history(repository: Path) -> None:
    section("10. Merge-aware history")

    print(
        """
A merge commit can have two parents.

Example:

              C --- D   feature
             /       \
    A --- B --------- M   main

M has:

    first parent  = B
    second parent = D

This is why HEAD^ and HEAD^2 can identify different commits.

The --first-parent option tells log to follow only the first-parent chain.
This is useful for understanding the mainline history of a branch containing
many merges.
"""
    )

    current_branch = command_output(repository, "branch", "--show-current")

    git(repository, "switch", "-c", "history-feature")

    write_file(
        repository,
        "merge-demo.txt",
        "Feature branch content.\n",
    )
    commit(repository, "Add feature branch change")

    git(repository, "switch", current_branch)

    write_file(
        repository,
        "mainline-demo.txt",
        "Main branch content.\n",
    )
    commit(repository, "Add mainline change")

    git(repository, "merge", "--no-ff", "history-feature", "-m", "Merge history feature")

    print("\nMerged history:")
    print(
        command_output(
            repository,
            "log",
            "--graph",
            "--decorate",
            "--oneline",
            "--all",
        )
    )

    print("\nFirst-parent history:")
    print(
        command_output(
            repository,
            "log",
            "--first-parent",
            "--oneline",
            "-8",
        )
    )

    print("\nMerge commit parents:")
    print(
        command_output(
            repository,
            "log",
            "-1",
            "--pretty=%H%n%P",
        )
    )

    git(repository, "branch", "-D", "history-feature")


# ---------------------------------------------------------------------------
# File-specific history
# ---------------------------------------------------------------------------

def demonstrate_file_history(repository: Path) -> None:
    section("11. File-specific history")

    print(
        """
Git can restrict history inspection to a path.

Useful commands:

    git log -- path/to/file
    git log -p -- path/to/file
    git log --follow -- path/to/file

--follow is particularly useful for tracking a file through a rename,
although its behavior has limitations and is primarily designed for a
single path.

git blame is related to history analysis. It identifies the commit and
author associated with each line, but it answers a different question from
git log.
"""
    )

    print("\nCommits affecting app.txt:")
    print(
        command_output(
            repository,
            "log",
            "--oneline",
            "--",
            "app.txt",
        )
    )

    print("\nPatch history for app.txt:")
    print(
        command_output(
            repository,
            "log",
            "-p",
            "--",
            "app.txt",
        )
    )

    print("\nLine attribution:")
    print(
        command_output(
            repository,
            "blame",
            "app.txt",
        )
    )


# ---------------------------------------------------------------------------
# Pretty formats
# ---------------------------------------------------------------------------

def demonstrate_pretty_formats(repository: Path) -> None:
    section("12. Custom log formats")

    print(
        """
git log supports --pretty formats.

Useful placeholders include:

    %H   full commit hash
    %h   abbreviated hash
    %an  author name
    %ae  author email
    %ad  author date
    %s   subject
    %p   parent hashes

A stable machine-readable format can be preferable to parsing human-oriented
default output in automation.
"""
    )

    print(
        command_output(
            repository,
            "log",
            "--pretty=format:%h | %ad | %an | %s",
            "--date=short",
            "-10",
        )
    )


# ---------------------------------------------------------------------------
# Edge cases and safety demonstrations
# ---------------------------------------------------------------------------

def demonstrate_edge_cases(repository: Path) -> None:
    section("13. Edge cases and common mistakes")

    print(
        """
1. An empty working-tree diff does not mean there are no staged changes.
   Check both `git diff` and `git diff --cached`.

2. `git diff HEAD` includes both staged and unstaged differences relative
   to the current commit.

3. A reset does not automatically mean files disappear. The mode determines
   what happens to the index and working tree.

4. `git reset --hard` can discard uncommitted changes. It should be treated
   as destructive.

5. Reverting a commit can produce conflicts if later changes overlap with
   the changes being reversed.

6. A merge commit has multiple parents, so parent notation matters.

7. `HEAD~2` follows first-parent ancestry. It is not identical to saying
   "the second-oldest commit visible in the graph."

8. Short hashes are convenient but should be sufficiently unambiguous.
   Git checks whether the abbreviation uniquely identifies an object.

9. A commit ID identifies content and metadata through Git's object model.
   Changing a commit's parent, message, tree, author, or related metadata
   produces a different commit ID.

10. Local reflog data should not be treated as a permanent backup.

11. Git history is content-addressed. A commit references its tree and
    parents, so changing history creates new object identities.

12. `git show` can display more than commits. Git objects include blobs,
    trees, commits, and annotated tags.

13. File paths beginning with a hyphen can be interpreted as options.
    Use `--` before paths when needed.

14. A clean working tree only describes tracked-file differences. Untracked
    files require status or clean-specific inspection.
"""
    )

    print("\nRepository status:")
    show_status(repository)

    print("\nTracked files:")
    print(command_output(repository, "ls-files"))


# ---------------------------------------------------------------------------
# Practical diagnostic function
# ---------------------------------------------------------------------------

def diagnose_repository(repository: Path) -> None:
    section("14. Practical history diagnostic")

    """
    This function models a common developer task: inspect the repository
    before deciding whether a change should be committed, reset, or reverted.
    """
    branch = command_output(repository, "branch", "--show-current")
    head = command_output(repository, "rev-parse", "--short", "HEAD")
    upstream = git(
        repository,
        "rev-parse",
        "--abbrev-ref",
        "--symbolic-full-name",
        "@{u}",
        check=False,
    )

    print(f"Current branch : {branch}")
    print(f"Current HEAD   : {head}")

    if upstream.succeeded:
        print(f"Upstream       : {upstream.stdout.strip()}")
    else:
        print("Upstream       : not configured")

    print("\nStatus:")
    show_status(repository)

    print("\nRecent commits:")
    print(
        command_output(
            repository,
            "log",
            "--decorate",
            "--oneline",
            "-5",
        )
    )

    print("\nUncommitted changes:")
    result = git(repository, "diff", "--stat")
    print(result.stdout.strip() or "(none)")

    print("\nStaged changes:")
    result = git(repository, "diff", "--cached", "--stat")
    print(result.stdout.strip() or "(none)")


# ---------------------------------------------------------------------------
# Automated learning checks
# ---------------------------------------------------------------------------

def run_learning_checks(repository: Path) -> None:
    section("15. Automated learning checks")

    checks: list[tuple[str, bool]] = []

    # Check that HEAD resolves.
    head_exists = bool(command_output(repository, "rev-parse", "HEAD"))
    checks.append(("HEAD resolves to a commit", head_exists))

    # Check that log can find at least three commits.
    log_count = int(
        command_output(
            repository,
            "rev-list",
            "--count",
            "HEAD",
        )
    )
    checks.append(("History contains at least three commits", log_count >= 3))

    # Check that HEAD~1 exists.
    parent_exists = git(
        repository,
        "rev-parse",
        "HEAD~1",
        check=False,
    ).succeeded
    checks.append(("HEAD~1 resolves", parent_exists))

    # Check that show can inspect HEAD.
    show_works = git(
        repository,
        "show",
        "--quiet",
        "HEAD",
        check=False,
    ).succeeded
    checks.append(("git show can inspect HEAD", show_works))

    # Check that the working tree is clean.
    clean = not bool(
        command_output(
            repository,
            "status",
            "--porcelain",
        )
    )
    checks.append(("Working tree is clean", clean))

    for description, passed in checks:
        print(f"[{'PASS' if passed else 'FAIL'}] {description}")

    if not all(passed for _, passed in checks):
        raise GitDemoError("One or more learning checks failed.")


# ---------------------------------------------------------------------------
# Main program
# ---------------------------------------------------------------------------

def verify_git_available() -> None:
    """Ensure the Git executable is available."""
    if shutil.which("git") is None:
        raise GitDemoError(
            "Git was not found on PATH. Install Git and run this script again."
        )

    version = run_command(["git", "--version"])
    print(f"Using {version.stdout.strip()}")


def main() -> None:
    """
    Run all demonstrations inside a temporary directory.

    No existing user repository is modified.
    """
    verify_git_available()
    explain_git_model()

    with tempfile.TemporaryDirectory(prefix="git_history_learning_") as temp:
        base_directory = Path(temp)
        repository = create_demo_repository(base_directory)

        print(f"\nTemporary repository: {repository}")

        demonstrate_log(repository)
        demonstrate_show(repository)
        demonstrate_diff(repository)
        demonstrate_reset(repository)
        demonstrate_revert(repository)
        compare_reset_and_revert()
        demonstrate_revision_syntax(repository)
        demonstrate_reflog(repository)
        demonstrate_merge_history(repository)
        demonstrate_file_history(repository)
        demonstrate_pretty_formats(repository)
        demonstrate_edge_cases(repository)
        diagnose_repository(repository)
        run_learning_checks(repository)

        section("16. Final repository state")
        print(command_output(repository, "log", "--graph", "--decorate", "--oneline", "--all"))
        show_status(repository)

    section("17. End of demonstration")
    print(
        "All examples were executed in a temporary repository. "
        "No existing repository was modified."
    )


if __name__ == "__main__":
    try:
        main()
    except GitDemoError as error:
        print(f"\nERROR: {error}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nExecution interrupted by user.", file=sys.stderr)
        sys.exit(130)
