#!/usr/bin/env python3
"""
Git Commands: init, clone, status, add, commit, push, pull

A comprehensive, executable study program for learning the core Git workflow.
The program uses temporary local repositories and, where available, a local
bare repository to demonstrate the commands without modifying an existing
user repository.

Requirements:
    Python 3.9+

Git requirement:
    Git must be installed and available on PATH.

The examples intentionally use temporary directories so that the demonstrations
do not modify the user's normal projects.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Sequence


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

class GitCommandError(RuntimeError):
    """Raised when a Git command fails unexpectedly."""


def run_command(
    command: Sequence[str],
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """
    Execute a command and return its completed process object.

    Git is fundamentally a command-line program. Calling Git through
    subprocess lets this Python program demonstrate the same commands a
    learner would execute in PowerShell, Command Prompt, or a Unix shell.
    """
    result = subprocess.run(
        list(command),
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
    )

    if check and result.returncode != 0:
        message = (
            f"Command failed with exit code {result.returncode}\n"
            f"Command: {' '.join(command)}\n"
            f"STDOUT:\n{result.stdout}\n"
            f"STDERR:\n{result.stderr}"
        )
        raise GitCommandError(message)

    return result


def git(
    *arguments: str,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a Git command."""
    return run_command(["git", *arguments], cwd=cwd, check=check)


def print_section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def print_command(command: Iterable[str]) -> None:
    print("$ " + " ".join(command))


def show_git(
    *arguments: str,
    cwd: Path | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """
    Display and execute a Git command.

    This makes the connection between the Python demonstration and the
    actual Git CLI visible to the learner.
    """
    command = ["git", *arguments]
    print_command(command)
    result = git(*arguments, cwd=cwd, check=check)

    if result.stdout.strip():
        print(result.stdout.rstrip())

    if result.stderr.strip():
        print(result.stderr.rstrip())

    return result


def write_text(path: Path, content: str) -> None:
    """Create or replace a text file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_text(path: Path) -> str:
    """Read UTF-8 text."""
    return path.read_text(encoding="utf-8")


def configure_identity(repo: Path, name: str, email: str) -> None:
    """
    Configure repository-local identity.

    Git records an author identity in commits. Repository-local configuration
    is used here so the demonstration does not alter the user's global Git
    configuration.
    """
    show_git("config", "user.name", name, cwd=repo)
    show_git("config", "user.email", email, cwd=repo)


# ---------------------------------------------------------------------------
# Git concepts
# ---------------------------------------------------------------------------

def explain_git_model() -> None:
    print_section("1. Git's basic model")

    print(
        """
Git is a distributed version control system.

The important objects for the commands in this lesson are:

Working tree
    The files currently visible in the project directory.

Untracked file
    A file that exists in the working tree but is not yet tracked by Git.

Modified file
    A tracked file whose working-tree contents differ from the committed
    version.

Staging area
    Also called the index. It records exactly which changes will be included
    in the next commit.

Commit
    A permanent snapshot recorded in the local repository history.

Local repository
    The .git directory containing Git's database and metadata.

Remote repository
    Another Git repository, commonly hosted on a server such as GitHub.

Remote-tracking branch
    A local reference representing the last known state of a remote branch,
    such as origin/main.

The fundamental workflow is:

    working tree
        |
        | git add
        v
    staging area
        |
        | git commit
        v
    local repository
        |
        | git push
        v
    remote repository

A separate synchronization direction is:

    remote repository
        |
        | git pull
        v
    local branch + working tree

A useful mental distinction is:

    git add      = select changes for the next commit
    git commit   = save those staged changes locally
    git push     = send local commits to a remote
    git pull     = obtain remote changes and integrate them locally
"""
    )


# ---------------------------------------------------------------------------
# Git version and environment
# ---------------------------------------------------------------------------

def check_git_installation() -> bool:
    print_section("2. Checking whether Git is installed")

    try:
        result = show_git("--version")
        print(f"\nGit detected: {result.stdout.strip()}")
        return True
    except (FileNotFoundError, GitCommandError) as error:
        print("\nGit could not be executed.")
        print("Install Git and make sure the git command is available on PATH.")
        print(f"Technical detail: {error}")
        return False


# ---------------------------------------------------------------------------
# git init
# ---------------------------------------------------------------------------

def demonstrate_init(base: Path) -> Path:
    print_section("3. git init")

    project = base / "init-demo"
    project.mkdir()

    print("Before initialization:")
    print(f"Project directory: {project}")
    print(f".git exists: {(project / '.git').exists()}")

    show_git("init", cwd=project)

    print("\nAfter initialization:")
    print(f".git exists: {(project / '.git').exists()}")

    write_text(project / "README.md", "# Init Demo\n")
    write_text(project / "app.py", 'print("Hello from Git")\n')

    print("\nInitial status:")
    show_git("status", "--short", cwd=project)

    print(
        """
git init creates a new local Git repository in the current directory.

Important behavior:
    - It does not automatically commit files.
    - It does not automatically push anything.
    - It normally creates a .git directory.
    - Existing files remain in the working tree.
    - Existing files become untracked until they are staged.

Use git init when you already have a local directory and want to start
tracking it with Git.
"""
    )

    return project


# ---------------------------------------------------------------------------
# git status
# ---------------------------------------------------------------------------

def demonstrate_status(repo: Path) -> None:
    print_section("4. git status")

    print("Repository status immediately after creating files:")
    show_git("status", cwd=repo)

    print("\nShort status:")
    show_git("status", "--short", cwd=repo)

    write_text(
        repo / "README.md",
        "# Init Demo\n\nThis file has been modified after initialization.\n",
    )

    print("\nAfter modifying README.md:")
    show_git("status", "--short", cwd=repo)

    print(
        """
git status answers an essential question:

    What is different between my working tree, staging area, and latest
    commit?

Common short-status indicators include:

    ?? file.txt
        Untracked file.

    M  file.txt
        File is staged as modified.

     M file.txt
        File is modified in the working tree but not staged.

    MM file.txt
        The file has staged changes and additional unstaged changes.

    A  file.txt
        A new file is staged for addition.

Before committing, git status is one of the most useful commands because it
shows what Git believes has changed and what will be included in the next
commit.
"""
    )


# ---------------------------------------------------------------------------
# git add
# ---------------------------------------------------------------------------

def demonstrate_add(repo: Path) -> None:
    print_section("5. git add")

    print("Before staging:")
    show_git("status", "--short", cwd=repo)

    show_git("add", "README.md", cwd=repo)

    print("\nAfter staging README.md:")
    show_git("status", "--short", cwd=repo)

    write_text(
        repo / "app.py",
        'print("Version 2")\n',
    )

    print("\nAfter creating another untracked file:")
    show_git("status", "--short", cwd=repo)

    show_git("add", "app.py", cwd=repo)

    print("\nAfter staging both files:")
    show_git("status", "--short", cwd=repo)

    print(
        """
git add does not mean "save permanently".

It moves a selected version of a file into the staging area.

Examples:

    git add file.txt
        Stage one file.

    git add file1.txt file2.txt
        Stage selected files.

    git add .
        Stage changes below the current directory.

    git add -A
        Stage changes throughout the repository.

A critical detail is that staging captures the contents at the time git add
runs. If you stage a file and then modify it again, the newer modification
can remain unstaged.

That is why this sequence is common:

    git status
    git add <files>
    git status
    git commit -m "Meaningful message"
"""
    )


# ---------------------------------------------------------------------------
# git commit
# ---------------------------------------------------------------------------

def demonstrate_commit(repo: Path) -> None:
    print_section("6. git commit")

    configure_identity(
        repo,
        "Git Learning Demo",
        "git-learning@example.invalid",
    )

    print("Committing staged changes:")
    show_git(
        "commit",
        "-m",
        "Create initial project files",
        cwd=repo,
    )

    print("\nStatus after commit:")
    show_git("status", cwd=repo)

    print("\nRecent history:")
    show_git(
        "log",
        "--oneline",
        "--decorate",
        "-5",
        cwd=repo,
    )

    write_text(
        repo / "app.py",
        'print("Version 3 with a new feature")\n',
    )

    show_git("add", "app.py", cwd=repo)

    show_git(
        "commit",
        "-m",
        "Update application behavior",
        cwd=repo,
    )

    print("\nHistory after the second commit:")
    show_git(
        "log",
        "--oneline",
        "--decorate",
        "-5",
        cwd=repo,
    )

    print(
        """
A commit is a local history object.

Important properties:

    - A commit is created locally.
    - A commit does not automatically reach GitHub.
    - A commit has an identifier called a commit hash.
    - A commit records parent history.
    - A commit has author and committer metadata.
    - A commit represents the staged snapshot.

The normal separation is intentional:

    add     -> choose content
    commit  -> record content locally
    push    -> transfer commits to a remote

A good commit message explains the change rather than merely saying
"changes" or "update".
"""
    )


# ---------------------------------------------------------------------------
# Local remote and git push
# ---------------------------------------------------------------------------

def demonstrate_push_and_pull(base: Path) -> None:
    print_section("7. git clone, push, and pull using a local remote")

    remote = base / "remote.git"
    source = base / "source"
    clone = base / "clone"

    show_git("init", "--bare", cwd=base / "remote-placeholder")

    # The previous command requires an existing directory. Replace that
    # temporary setup with the actual bare repository.
    placeholder = base / "remote-placeholder"
    shutil.rmtree(placeholder)

    show_git("init", "--bare", str(remote), cwd=base)

    source.mkdir()
    show_git("init", cwd=source)

    configure_identity(
        source,
        "Source Developer",
        "source@example.invalid",
    )

    write_text(
        source / "project.txt",
        "Initial project content\n",
    )

    show_git("add", "project.txt", cwd=source)
    show_git(
        "commit",
        "-m",
        "Create project",
        cwd=source,
    )

    print("\nAdding a remote named origin:")
    show_git(
        "remote",
        "add",
        "origin",
        str(remote),
        cwd=source,
    )

    print("\nInspecting configured remotes:")
    show_git("remote", "-v", cwd=source)

    branch = (
        git("branch", "--show-current", cwd=source)
        .stdout.strip()
        or "master"
    )

    print(f"\nCurrent branch detected: {branch}")

    show_git(
        "push",
        "-u",
        "origin",
        branch,
        cwd=source,
    )

    print(
        """
git push transfers commits from the local repository to the remote
repository.

The form:

    git push origin main

means:

    remote = origin
    branch = main

The option:

    -u

sets an upstream relationship. After an upstream is established, later
pushes can often be performed simply with:

    git push

"""
    )

    print("\nCloning the remote repository:")
    show_git(
        "clone",
        str(remote),
        str(clone),
        cwd=base,
    )

    configure_identity(
        clone,
        "Clone Developer",
        "clone@example.invalid",
    )

    print("\nStatus of the cloned repository:")
    show_git("status", cwd=clone)

    print("\nRemote configuration in the clone:")
    show_git("remote", "-v", cwd=clone)

    write_text(
        source / "project.txt",
        "Initial project content\nA change made in the source repository.\n",
    )

    show_git("add", "project.txt", cwd=source)
    show_git(
        "commit",
        "-m",
        "Add second project line",
        cwd=source,
    )
    show_git(
        "push",
        cwd=source,
    )

    print("\nPulling the new commit into the clone:")
    show_git("pull", cwd=clone)

    print("\nContents after pull:")
    print(read_text(clone / "project.txt"))

    print(
        """
git clone is different from git init.

git init:
    Creates a new repository in an existing directory.

git clone:
    Copies an existing repository and configures a remote, commonly named
    origin.

git push:
    Sends local commits to a remote.

git pull:
    Fetches changes from a remote and integrates them into the current
    branch.

The simplified relationship is:

    git pull
        approximately combines:
            git fetch
            git merge

Modern Git workflows can also configure pull behavior around rebasing,
but the essential beginner-level distinction is that pull obtains remote
history and integrates it into the current local work.
"""
    )


# ---------------------------------------------------------------------------
# Push and pull safety
# ---------------------------------------------------------------------------

def demonstrate_push_pull_safety(base: Path) -> None:
    print_section("8. Push/pull edge cases and safety concepts")

    remote = base / "safety-remote.git"
    developer_a = base / "developer-a"
    developer_b = base / "developer-b"

    show_git("init", "--bare", str(remote), cwd=base)

    for repo in (developer_a, developer_b):
        show_git("clone", str(remote), str(repo), cwd=base)

    configure_identity(
        developer_a,
        "Developer A",
        "developer-a@example.invalid",
    )
    configure_identity(
        developer_b,
        "Developer B",
        "developer-b@example.invalid",
    )

    write_text(
        developer_a / "shared.txt",
        "Created by Developer A\n",
    )

    show_git("add", "shared.txt", cwd=developer_a)
    show_git(
        "commit",
        "-m",
        "Create shared file",
        cwd=developer_a,
    )

    branch_a = (
        git("branch", "--show-current", cwd=developer_a)
        .stdout.strip()
    )

    show_git(
        "push",
        "-u",
        "origin",
        branch_a,
        cwd=developer_a,
    )

    print(
        "\nDeveloper B updates the local view of the remote before editing:"
    )
    show_git("pull", cwd=developer_b)

    write_text(
        developer_b / "shared.txt",
        "Created by Developer A\nUpdated by Developer B\n",
    )

    show_git("add", "shared.txt", cwd=developer_b)
    show_git(
        "commit",
        "-m",
        "Update shared file",
        cwd=developer_b,
    )
    show_git("push", cwd=developer_b)

    print(
        """
A push can be rejected when the remote branch contains commits that the
local branch does not contain.

This protection is important. It prevents Git from silently replacing
remote history with an incompatible local history.

A common response is:

    git pull

resolve any conflicts if necessary, create or complete the resulting
integration, and then:

    git push

A non-fast-forward rejection is therefore not automatically a sign that
Git is broken. It often means the local repository is behind the remote.
"""
    )


# ---------------------------------------------------------------------------
# Demonstrate partial staging
# ---------------------------------------------------------------------------

def demonstrate_staging_behavior(base: Path) -> None:
    print_section("9. Important staging behavior")

    repo = base / "staging-demo"
    repo.mkdir()

    show_git("init", cwd=repo)
    configure_identity(
        repo,
        "Staging Demo",
        "staging@example.invalid",
    )

    file_path = repo / "notes.txt"
    write_text(file_path, "Line one\n")

    show_git("add", "notes.txt", cwd=repo)
    show_git(
        "commit",
        "-m",
        "Create notes",
        cwd=repo,
    )

    write_text(
        file_path,
        "Line one\nLine two\n",
    )

    print("\nA modification exists:")
    show_git("status", "--short", cwd=repo)

    show_git("add", "notes.txt", cwd=repo)

    write_text(
        file_path,
        "Line one\nLine two\nLine three\n",
    )

    print(
        """
The file was staged after Line Two was added, then modified again.

Therefore the repository can simultaneously contain:

    staged version:
        Line one
        Line two

    working-tree version:
        Line one
        Line two
        Line three
"""
    )

    show_git("status", "--short", cwd=repo)

    print(
        "\nThe important lesson: git add stages a snapshot; it does not create "
        "a permanent connection between the file and the staging area."
    )


# ---------------------------------------------------------------------------
# Common command patterns
# ---------------------------------------------------------------------------

def print_command_reference() -> None:
    print_section("10. Core command reference")

    commands = [
        ("git init", "Create a new local repository."),
        ("git clone <url>", "Copy an existing repository."),
        ("git status", "Inspect working-tree and staging state."),
        ("git add <file>", "Stage a specific file."),
        ("git add .", "Stage changes under the current directory."),
        ("git commit -m \"message\"", "Create a local commit."),
        ("git remote -v", "Display configured remote URLs."),
        ("git push", "Send local commits to the configured upstream."),
        ("git push -u origin main", "Push main and establish upstream."),
        ("git pull", "Fetch and integrate remote changes."),
        ("git log --oneline", "View compact commit history."),
    ]

    for command, purpose in commands:
        print(f"{command:<35} {purpose}")


# ---------------------------------------------------------------------------
# Advanced concepts
# ---------------------------------------------------------------------------

def explain_advanced_concepts() -> None:
    print_section("11. Advanced concepts connected to the core commands")

    print(
        """
1. HEAD
   HEAD normally identifies the currently checked-out commit or branch
   position.

2. Branch
   A branch is a movable reference to a line of development. The commands
   in this lesson normally operate on the currently checked-out branch.

3. origin
   origin is a conventional remote name. It is only a name; another name
   could be used.

4. Upstream
   An upstream branch tells Git which remote branch should be used by
   default for operations such as a plain git push or git pull.

5. Fast-forward
   A fast-forward occurs when a branch reference can move forward without
   creating a merge commit.

6. Non-fast-forward
   A push may be rejected when the remote branch has history that is not
   present locally.

7. Fetch versus pull
   git fetch obtains remote information without integrating it into the
   current branch.
   git pull performs a fetch followed by an integration strategy.

8. Merge versus rebase
   Pulling can be configured to merge or rebase. Merge preserves the
   existing branch topology, while rebase rewrites local commit ancestry.
   Rebase requires particular care when commits have already been shared.

9. Commit identity
   Git commits contain cryptographic object identifiers derived from their
   content and metadata. Modern Git may use SHA-1 or SHA-256 repository
   object formats depending on repository configuration and Git version.

10. Detached HEAD
    HEAD can point directly to a commit rather than a branch. This can be
    useful for inspection but requires care when creating new commits.

11. Remote-tracking references
    origin/main is normally a local reference representing the last known
    state of the main branch on origin.

12. Hooks
    Git hooks can execute local programs at selected points in a Git
    workflow. Hooks can enforce checks, but they should not be treated as
    a substitute for server-side validation.

13. Authentication
    Push to hosted services may use HTTPS credentials, credential helpers,
    personal access tokens, SSH keys, or provider-specific authentication.
    Credentials should never be committed into repository files.

14. Branch protection
    Hosting platforms can enforce rules such as required reviews, status
    checks, or restrictions on direct pushes. These are remote-service
    controls rather than behaviors of git commit itself.

15. Atomicity of commits
    A commit records a complete staged snapshot. This makes commits useful
    as logical units of change and simplifies review and rollback.
"""
    )


# ---------------------------------------------------------------------------
# Common mistakes
# ---------------------------------------------------------------------------

def print_common_mistakes() -> None:
    print_section("12. Common mistakes and diagnosis")

    mistakes = {
        "git: command not found / git is not recognized":
            "Git is not installed or its executable is not available on PATH.",

        "nothing to commit":
            "The working tree has no changes staged for the current commit.",

        "changes not staged for commit":
            "Tracked files changed, but git add has not staged those changes.",

        "untracked files":
            "Files exist in the working tree but have not been added to Git.",

        "src refspec main does not match any":
            "The local branch named main may not exist, or there may be no "
            "commit yet. Check git branch and git status.",

        "rejected non-fast-forward":
            "The remote branch has commits missing locally. Synchronize and "
            "integrate the remote history before pushing.",

        "fatal: not a git repository":
            "The current directory is not inside a Git repository.",

        "Author identity unknown":
            "Git does not have the required user.name and user.email values "
            "for creating the commit.",
    }

    for error, explanation in mistakes.items():
        print(f"\n{error}\n  {explanation}")


# ---------------------------------------------------------------------------
# Production-oriented workflow
# ---------------------------------------------------------------------------

def explain_production_workflow() -> None:
    print_section("13. A disciplined workflow")

    print(
        """
For an existing repository:

    git pull
    git status
    edit files
    git status
    git add <specific files>
    git status
    git commit -m "Describe the logical change"
    git push

For a brand-new local project:

    mkdir project
    cd project
    git init
    edit files
    git status
    git add .
    git commit -m "Initial project"
    git remote add origin <remote-url>
    git push -u origin main

The exact branch name may differ. Some repositories use main, while older
repositories may use master or another branch name.

Good practices include:

    - Inspect status before committing.
    - Stage intentionally.
    - Keep commits logically focused.
    - Write meaningful commit messages.
    - Pull or otherwise synchronize before publishing work when appropriate.
    - Never commit passwords, private keys, API tokens, or other secrets.
    - Use .gitignore for files that should not be tracked.
    - Understand whether a command affects the working tree, index, local
      repository, or remote repository.
    - Do not assume that a local commit has been backed up remotely until
      push succeeds.
"""
    )


# ---------------------------------------------------------------------------
# Main program
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 78)
    print("GIT COMMANDS LAB")
    print("init | clone | status | add | commit | push | pull")
    print("=" * 78)

    if not check_git_installation():
        return

    explain_git_model()

    with tempfile.TemporaryDirectory(prefix="git-learning-") as temp_dir:
        base = Path(temp_dir)

        print(f"\nAll demonstrations are isolated under:\n{base}")

        init_repo = demonstrate_init(base)
        demonstrate_status(init_repo)
        demonstrate_add(init_repo)
        demonstrate_commit(init_repo)

        demonstrate_push_and_pull(base)
        demonstrate_push_pull_safety(base)
        demonstrate_staging_behavior(base)

        print_command_reference()
        explain_advanced_concepts()
        print_common_mistakes()
        explain_production_workflow()

        print_section("14. Lab completed")
        print(
            "The demonstrations used temporary repositories. "
            "They can be safely removed after this program exits."
        )


if __name__ == "__main__":
    main()
