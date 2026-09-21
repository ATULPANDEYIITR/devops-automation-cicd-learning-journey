```python
"""
Git Fundamentals: Repository, Working Tree, and Staging Area

This standalone script teaches Git from absolute beginner concepts through
advanced practical behavior. It models Git's three most important local areas:

    1. Repository data (.git)
    2. Working tree (files currently visible in the project directory)
    3. Staging area (the proposed contents of the next commit)

It also demonstrates real Git commands when Git is installed, while keeping
the main teaching model independent of external packages and safe to execute.

The script is intentionally educational. It does not modify an existing Git
repository unless the user explicitly chooses the optional command demo.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# Section 1: Basic terminology
# ---------------------------------------------------------------------------

def print_section(title: str) -> None:
    """Print a clear section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def explain_basic_terminology() -> None:
    print_section("1. Git fundamentals: essential terminology")

    terms = {
        "Git": (
            "A distributed version control system. It records changes to "
            "files and lets developers create versions, compare changes, "
            "restore earlier states, and collaborate."
        ),
        "Repository": (
            "A project together with its Git history and metadata. The "
            "hidden .git directory is the local Git repository."
        ),
        "Working tree": (
            "The ordinary project files and directories that you currently "
            "see and edit."
        ),
        "Staging area": (
            "An intermediate snapshot of the changes selected for the next "
            "commit. It is also called the index."
        ),
        "Commit": (
            "A recorded snapshot of the staged project state. A commit has "
            "an identifier and points to parent commit(s), except for a "
            "root commit."
        ),
        "Branch": (
            "A movable reference to a commit. A branch normally represents "
            "a line of development."
        ),
        "HEAD": (
            "Git's symbolic reference to the currently checked-out commit "
            "or, commonly, the current branch."
        ),
        "Tracked file": (
            "A file Git already knows about through its index and/or "
            "history."
        ),
        "Untracked file": (
            "A file present in the working tree that Git is not currently "
            "tracking."
        ),
        "Modified file": (
            "A tracked file whose working-tree contents differ from the "
            "version represented by the index or current commit."
        ),
    }

    for name, meaning in terms.items():
        print(f"\n{name}")
        print(f"  {meaning}")


# ---------------------------------------------------------------------------
# Section 2: The three-area model
# ---------------------------------------------------------------------------

@dataclass
class FileState:
    """Represent the content of one file in the teaching model."""

    content: str
    tracked: bool = False


@dataclass
class GitLearningModel:
    """
    A small in-memory model of Git's three local areas.

    committed:
        Approximation of the current commit's tree.

    staged:
        Approximation of Git's index.

    working:
        Approximation of the files currently in the working tree.
    """

    committed: Dict[str, str] = field(default_factory=dict)
    staged: Dict[str, str] = field(default_factory=dict)
    working: Dict[str, str] = field(default_factory=dict)

    def status(self) -> Dict[str, str]:
        """Calculate simplified status categories."""
        result: Dict[str, str] = {}
        all_paths = set(self.committed) | set(self.staged) | set(self.working)

        for path in sorted(all_paths):
            in_commit = path in self.committed
            in_stage = path in self.staged
            in_working = path in self.working

            if not in_commit and not in_stage and in_working:
                result[path] = "untracked"

            elif in_commit and not in_stage and not in_working:
                result[path] = "deleted and staged"

            elif in_commit and in_stage and not in_working:
                result[path] = "deleted in working tree"

            elif not in_commit and in_stage and in_working:
                result[path] = "new file staged"

            elif in_commit and in_stage and in_working:
                staged_difference = self.staged[path] != self.committed[path]
                working_difference = self.working[path] != self.staged[path]

                if staged_difference and working_difference:
                    result[path] = "staged and additionally modified"

                elif staged_difference:
                    result[path] = "modified and staged"

                elif working_difference:
                    result[path] = "modified"

                else:
                    result[path] = "clean"

            elif in_commit and not in_stage and in_working:
                result[path] = "modified"

        return result

    def show_status(self) -> None:
        print("\nCurrent three-area state:")
        for path, state in self.status().items():
            print(f"  {state:35} {path}")

    def create_file(self, path: str, content: str) -> None:
        """Create a new working-tree file."""
        self.working[path] = content

    def edit_file(self, path: str, content: str) -> None:
        """Edit an existing or new working-tree file."""
        if path not in self.working:
            raise FileNotFoundError(f"Working-tree file does not exist: {path}")
        self.working[path] = content

    def git_add(self, *paths: str) -> None:
        """
        Model `git add`.

        The important idea is that git add does not merely mark a file
        "selected". It copies the file's current working-tree content into
        the staging area.
        """
        for path in paths:
            if path not in self.working:
                raise FileNotFoundError(
                    f"Cannot stage '{path}': it is absent from the working tree."
                )
            self.staged[path] = self.working[path]

    def git_restore_staged(self, *paths: str) -> None:
        """
        Model `git restore --staged`.

        This moves the selected path's staged version back toward the current
        commit. It does not normally discard the working-tree edit.
        """
        for path in paths:
            if path in self.committed:
                self.staged[path] = self.committed[path]
            else:
                self.staged.pop(path, None)

    def git_restore_worktree(self, *paths: str) -> None:
        """
        Model restoring the working tree from the staged/current index state.

        In real Git, exact behavior depends on the command and options.
        Here the purpose is to visualize the fundamental direction of data.
        """
        for path in paths:
            if path in self.staged:
                self.working[path] = self.staged[path]
            elif path in self.committed:
                self.working[path] = self.committed[path]
            else:
                self.working.pop(path, None)

    def commit(self, message: str) -> None:
        """
        Create a new simplified commit by copying the staged snapshot.

        A real Git commit stores objects, metadata, parent relationships,
        author information, timestamps, and a tree. This teaching model
        concentrates on the content flow.
        """
        if not message.strip():
            raise ValueError("A commit message should not be empty.")

        self.committed = dict(self.staged)

        print(f"\nCreated teaching-model commit: {message}")

    def diff_commit_to_stage(self) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
        """Show what is staged relative to the current commit."""
        paths = set(self.committed) | set(self.staged)
        differences = {}

        for path in sorted(paths):
            old = self.committed.get(path)
            new = self.staged.get(path)
            if old != new:
                differences[path] = (old, new)

        return differences

    def diff_stage_to_working(
        self,
    ) -> Dict[str, Tuple[Optional[str], Optional[str]]]:
        """Show working-tree changes relative to the staging area."""
        paths = set(self.staged) | set(self.working)
        differences = {}

        for path in sorted(paths):
            old = self.staged.get(path)
            new = self.working.get(path)
            if old != new:
                differences[path] = (old, new)

        return differences


def demonstrate_three_area_model() -> None:
    print_section("2. The repository, working tree, and staging area")

    model = GitLearningModel(
        committed={
            "README.md": "# Project\n",
            "app.py": 'print("version 1")\n',
        },
        staged={
            "README.md": "# Project\n",
            "app.py": 'print("version 1")\n',
        },
        working={
            "README.md": "# Project\n",
            "app.py": 'print("version 1")\n',
        },
    )

    print("Initial state:")
    model.show_status()

    print("\nStep 1: edit app.py in the working tree.")
    model.edit_file("app.py", 'print("version 2")\n')
    model.show_status()

    print("\nStep 2: stage app.py with the conceptual equivalent of git add.")
    model.git_add("app.py")
    model.show_status()

    print("\nStep 3: edit app.py again after staging.")
    model.edit_file("app.py", 'print("version 3")\n')
    model.show_status()

    print("\nAt this point two different changes exist:")
    print("  Commit -> Stage:")
    print(model.diff_commit_to_stage())
    print("  Stage -> Working tree:")
    print(model.diff_stage_to_working())

    print("\nThis is one of the most important Git ideas:")
    print("a file can simultaneously have staged changes and unstaged changes.")

    print("\nStep 4: commit the staged version.")
    model.commit("Update application")
    model.show_status()

    print(
        "\nThe working tree still contains version 3, while the commit contains "
        "the staged version 2."
    )


# ---------------------------------------------------------------------------
# Section 3: File lifecycle
# ---------------------------------------------------------------------------

def demonstrate_file_lifecycle() -> None:
    print_section("3. File lifecycle: untracked -> staged -> committed -> modified")

    model = GitLearningModel()

    print("\nCreate a new file.")
    model.create_file("notes.txt", "First line\n")
    model.show_status()

    print("\nStage it.")
    model.git_add("notes.txt")
    model.show_status()

    print("\nCommit it.")
    model.commit("Add notes")
    model.show_status()

    print("\nModify the committed file.")
    model.edit_file("notes.txt", "First line\nSecond line\n")
    model.show_status()

    print("\nStage the modification.")
    model.git_add("notes.txt")
    model.show_status()


# ---------------------------------------------------------------------------
# Section 4: Diff concepts
# ---------------------------------------------------------------------------

def display_differences(
    differences: Dict[str, Tuple[Optional[str], Optional[str]]],
    title: str,
) -> None:
    print(f"\n{title}")

    if not differences:
        print("  No differences.")
        return

    for path, (old, new) in differences.items():
        print(f"\n  File: {path}")
        print(f"    OLD: {old!r}")
        print(f"    NEW: {new!r}")


def demonstrate_two_types_of_diff() -> None:
    print_section("4. Two important comparisons")

    model = GitLearningModel(
        committed={"app.py": "print('old')\n"},
        staged={"app.py": "print('staged')\n"},
        working={"app.py": "print('working')\n"},
    )

    display_differences(
        model.diff_commit_to_stage(),
        "Commit versus staging area: conceptually similar to git diff --cached",
    )

    display_differences(
        model.diff_stage_to_working(),
        "Staging area versus working tree: conceptually similar to git diff",
    )

    print(
        "\nRemember:\n"
        "  git diff          -> what is changed but not staged\n"
        "  git diff --cached -> what is staged for the next commit"
    )


# ---------------------------------------------------------------------------
# Section 5: Partial staging
# ---------------------------------------------------------------------------

def demonstrate_partial_staging() -> None:
    print_section("5. Partial staging and why the staging area matters")

    model = GitLearningModel(
        committed={
            "app.py": (
                "def calculate_total(items):\n"
                "    return sum(items)\n"
            )
        },
        staged={
            "app.py": (
                "def calculate_total(items):\n"
                "    return sum(items)\n"
            )
        },
        working={
            "app.py": (
                "def calculate_total(items):\n"
                "    total = sum(items)\n"
                "    print(f'Total: {total}')\n"
                "    return total\n"
            )
        },
    )

    print(
        "Suppose the developer wants to commit only the calculation change, "
        "not the debugging print."
    )

    print("\nThe real Git command `git add -p` can interactively stage selected hunks.")
    print(
        "The simplified model below stages a deliberately constructed version "
        "representing the selected part."
    )

    selected_version = (
        "def calculate_total(items):\n"
        "    total = sum(items)\n"
        "    return total\n"
    )

    model.staged["app.py"] = selected_version

    display_differences(
        model.diff_commit_to_stage(),
        "Selected staged change",
    )

    display_differences(
        model.diff_stage_to_working(),
        "Remaining unstaged change",
    )


# ---------------------------------------------------------------------------
# Section 6: Hashing and content identity
# ---------------------------------------------------------------------------

def sha1_text(text: str) -> str:
    """Return a SHA-1 hash, useful for illustrating Git's historical object IDs."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()


def demonstrate_hashing() -> None:
    print_section("6. Content hashing and Git object identity")

    examples = [
        "",
        "hello",
        "hello\n",
        "Hello",
        "hello world",
    ]

    for value in examples:
        print(f"{value!r:15} -> {sha1_text(value)}")

    print(
        "\nA tiny content change produces a completely different hash. "
        "Modern Git can use SHA-256 repositories as well, but SHA-1 remains "
        "common in existing Git repositories."
    )

    first = sha1_text("important file")
    second = sha1_text("important file.")

    print(f"\nHash A: {first}")
    print(f"Hash B: {second}")
    print(f"Hashes equal? {first == second}")


# ---------------------------------------------------------------------------
# Section 7: A simplified object database
# ---------------------------------------------------------------------------

@dataclass
class GitObject:
    object_type: str
    content: bytes


class MiniObjectDatabase:
    """
    A conceptual object database.

    Real Git stores objects such as blobs, trees, commits, and annotated tags.
    This miniature implementation demonstrates the central content-addressed
    idea without pretending to be a full Git implementation.
    """

    def __init__(self) -> None:
        self.objects: Dict[str, GitObject] = {}

    @staticmethod
    def object_id(object_type: str, content: bytes) -> str:
        header = f"{object_type} {len(content)}\0".encode("utf-8")
        return hashlib.sha1(header + content).hexdigest()

    def write(self, object_type: str, content: bytes) -> str:
        object_id = self.object_id(object_type, content)
        self.objects[object_id] = GitObject(object_type, content)
        return object_id

    def read(self, object_id: str) -> GitObject:
        if object_id not in self.objects:
            raise KeyError(f"Unknown object: {object_id}")
        return self.objects[object_id]


def demonstrate_object_database() -> None:
    print_section("7. Simplified Git object database")

    database = MiniObjectDatabase()

    blob_id = database.write("blob", b"hello Git\n")
    tree_content = f"100644 README.md blob {blob_id}\n".encode("utf-8")
    tree_id = database.write("tree", tree_content)

    commit_content = (
        f"tree {tree_id}\n"
        "author Student <student@example.com>\n"
        "committer Student <student@example.com>\n"
        "\n"
        "Initial commit\n"
    ).encode("utf-8")
    commit_id = database.write("commit", commit_content)

    print(f"Blob object:   {blob_id}")
    print(f"Tree object:   {tree_id}")
    print(f"Commit object: {commit_id}")

    print("\nStored object types:")
    for object_id, obj in database.objects.items():
        print(f"  {object_id[:12]}... -> {obj.object_type}")

    print(
        "\nThe important relationship is:\n"
        "  blob  -> file content\n"
        "  tree  -> directory structure and blob references\n"
        "  commit -> tree plus metadata and parent commit references"
    )


# ---------------------------------------------------------------------------
# Section 8: Real Git command execution
# ---------------------------------------------------------------------------

def git_available() -> bool:
    """Check whether Git is available without raising an exception."""
    try:
        result = subprocess.run(
            ["git", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except OSError:
        return False


def run_git(
    arguments: List[str],
    cwd: Path,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    """Run a Git command and return its completed-process object."""
    return subprocess.run(
        ["git", *arguments],
        cwd=cwd,
        capture_output=True,
        text=True,
        check=check,
    )


def demonstrate_real_git_safely() -> None:
    print_section("8. Real Git commands in a temporary repository")

    if not git_available():
        print("Git is not available in PATH.")
        print("The rest of the educational script does not require Git.")
        return

    with tempfile.TemporaryDirectory(prefix="git-fundamentals-") as directory:
        repo = Path(directory)

        print(f"Temporary repository: {repo}")

        run_git(["init"], repo)

        run_git(
            ["config", "user.name", "Git Fundamentals Student"],
            repo,
        )
        run_git(
            ["config", "user.email", "student@example.com"],
            repo,
        )

        readme = repo / "README.md"
        app = repo / "app.py"

        readme.write_text("# Git Fundamentals\n", encoding="utf-8")
        app.write_text("print('version 1')\n", encoding="utf-8")

        print("\nAfter creating files:")
        result = run_git(["status", "--short"], repo)
        print(result.stdout.strip())

        run_git(["add", "README.md", "app.py"], repo)

        print("\nAfter git add:")
        result = run_git(["status", "--short"], repo)
        print(result.stdout.strip())

        print("\nStaged diff:")
        result = run_git(["diff", "--cached"], repo)
        print(result.stdout.rstrip())

        run_git(["commit", "-m", "Initial project"], repo)

        print("\nAfter commit:")
        result = run_git(["status", "--short"], repo)
        print(result.stdout.strip() or "Working tree clean.")

        app.write_text(
            "print('version 2')\n",
            encoding="utf-8",
        )

        print("\nAfter modifying app.py without staging:")
        result = run_git(["status", "--short"], repo)
        print(result.stdout.strip())

        print("\nUnstaged diff:")
        result = run_git(["diff"], repo)
        print(result.stdout.rstrip())

        run_git(["add", "app.py"], repo)

        print("\nAfter staging the modification:")
        result = run_git(["status", "--short"], repo)
        print(result.stdout.strip())

        print("\nStaged diff:")
        result = run_git(["diff", "--cached"], repo)
        print(result.stdout.rstrip())

        print("\nCommit history:")
        result = run_git(
            ["log", "--oneline", "--decorate", "--all"],
            repo,
        )
        print(result.stdout.rstrip())

        print("\nRepository internals:")
        result = run_git(
            ["rev-parse", "--git-dir"],
            repo,
        )
        print(f"  .git location: {result.stdout.strip()}")

        print("\nHEAD:")
        result = run_git(["symbolic-ref", "--short", "HEAD"], repo, check=False)
        if result.returncode == 0:
            print(f"  Current branch: {result.stdout.strip()}")

        print(
            "\nThe temporary repository is automatically deleted when this "
            "demonstration ends."
        )


# ---------------------------------------------------------------------------
# Section 9: Common mistakes
# ---------------------------------------------------------------------------

def demonstrate_common_mistakes() -> None:
    print_section("9. Common beginner mistakes")

    mistakes = [
        (
            "Editing a file and expecting the edit to be in the next commit",
            "Git commits staged content, not every current working-tree edit.",
        ),
        (
            "Thinking git add means 'save permanently'",
            "git add updates the index. A commit records the staged snapshot.",
        ),
        (
            "Running git add . without checking the result",
            "This may stage files you did not intend to include.",
        ),
        (
            "Using git restore carelessly",
            "Some restore operations can discard uncommitted working-tree changes.",
        ),
        (
            "Confusing git diff and git diff --cached",
            "They compare different boundaries: working tree vs index, and index vs commit.",
        ),
        (
            "Committing generated files or secrets",
            "Build artifacts, credentials, API keys, and environment files may not belong in history.",
        ),
        (
            "Assuming .gitignore removes an already tracked file",
            ".gitignore mainly controls untracked files; it does not automatically untrack a file.",
        ),
        (
            "Thinking a branch is a complete independent copy",
            "A branch is primarily a reference to a commit. Git objects may be shared.",
        ),
    ]

    for mistake, correction in mistakes:
        print(f"\nMistake: {mistake}")
        print(f"Correction: {correction}")


# ---------------------------------------------------------------------------
# Section 10: .gitignore demonstration
# ---------------------------------------------------------------------------

def demonstrate_gitignore_rules() -> None:
    print_section("10. .gitignore: what it does and does not do")

    rules = [
        "*.pyc",
        "__pycache__/",
        ".venv/",
        ".env",
        "build/",
        "*.log",
    ]

    sample_paths = [
        "main.py",
        "main.pyc",
        "__pycache__/main.cpython-314.pyc",
        ".venv/Scripts/python.exe",
        ".env",
        "build/app.exe",
        "logs/application.log",
    ]

    def ignored(path: str) -> bool:
        normalized = path.replace("\\", "/")

        if normalized == ".env":
            return True
        if normalized.startswith("__pycache__/"):
            return True
        if normalized.startswith(".venv/"):
            return True
        if normalized.startswith("build/"):
            return True
        if normalized.endswith(".pyc"):
            return True
        if normalized.endswith(".log"):
            return True
        return False

    print("Example ignore rules:")
    for rule in rules:
        print(f"  {rule}")

    print("\nConceptual matching:")
    for path in sample_paths:
        print(f"  {'IGNORED' if ignored(path) else 'NOT IGNORED':11} {path}")

    print(
        "\nSecurity point: ignoring a secret file does not erase a secret that "
        "was already committed. Removing sensitive data from Git history is "
        "a separate task."
    )


# ---------------------------------------------------------------------------
# Section 11: Commit model
# ---------------------------------------------------------------------------

@dataclass
class CommitNode:
    commit_id: str
    message: str
    parents: List[str]


def create_teaching_commit(
    message: str,
    parents: List[str],
    counter: int,
) -> CommitNode:
    payload = (
        message
        + "|"
        + ",".join(parents)
        + "|"
        + str(counter)
    )
    commit_id = hashlib.sha1(payload.encode("utf-8")).hexdigest()[:12]
    return CommitNode(commit_id, message, parents)


def demonstrate_commit_graph() -> None:
    print_section("11. Commit graph and parent relationships")

    root = create_teaching_commit("Initial project", [], 1)
    second = create_teaching_commit("Add feature", [root.commit_id], 2)
    third = create_teaching_commit("Fix bug", [second.commit_id], 3)

    feature = create_teaching_commit(
        "Experiment with feature",
        [second.commit_id],
        4,
    )

    merge = create_teaching_commit(
        "Merge feature",
        [third.commit_id, feature.commit_id],
        5,
    )

    commits = [root, second, third, feature, merge]

    for commit in commits:
        parents = ", ".join(commit.parents) if commit.parents else "none"
        print(
            f"{commit.commit_id}  parents=[{parents}]  "
            f"message={commit.message!r}"
        )

    print(
        "\nA normal commit usually has one parent. A merge commit can have "
        "two or more parents, which records the convergence of histories."
    )


# ---------------------------------------------------------------------------
# Section 12: HEAD and branches
# ---------------------------------------------------------------------------

@dataclass
class BranchModel:
    branches: Dict[str, str]
    head_branch: str

    @property
    def head_commit(self) -> str:
        return self.branches[self.head_branch]

    def create_branch(self, name: str) -> None:
        if name in self.branches:
            raise ValueError(f"Branch already exists: {name}")
        self.branches[name] = self.head_commit

    def switch(self, name: str) -> None:
        if name not in self.branches:
            raise ValueError(f"Unknown branch: {name}")
        self.head_branch = name

    def advance_current_branch(self, commit_id: str) -> None:
        self.branches[self.head_branch] = commit_id


def demonstrate_branches() -> None:
    print_section("12. Branches and HEAD")

    branches = BranchModel(
        branches={"main": "a1b2c3d4"},
        head_branch="main",
    )

    print(f"HEAD -> {branches.head_branch} -> {branches.head_commit}")

    branches.create_branch("feature/login")

    print("\nCreated feature/login.")
    print(branches.branches)

    branches.switch("feature/login")
    print(f"\nAfter switching: HEAD -> {branches.head_branch}")

    branches.advance_current_branch("e5f6g7h8")

    print("\nFeature branch advanced:")
    print(branches.branches)

    print(
        "\nNotice that creating a branch did not copy every file into a new "
        "directory. It created another reference to a commit."
    )


# ---------------------------------------------------------------------------
# Section 13: Performance and storage concepts
# ---------------------------------------------------------------------------

def demonstrate_performance_considerations() -> None:
    print_section("13. Performance and storage considerations")

    considerations = {
        "Small commits": (
            "Usually make review, debugging, rollback, and history analysis easier."
        ),
        "Large binary files": (
            "Can make repositories large because ordinary Git history is optimized "
            "primarily for source-like content rather than frequently changing binaries."
        ),
        "Many ignored build files": (
            "Keeping generated files out of the index reduces accidental commits "
            "and unnecessary repository content."
        ),
        "git status": (
            "Git may inspect working-tree metadata and file contents to determine "
            "changes. Very large repositories can require optimization strategies."
        ),
        "Object packing": (
            "Git can pack objects to reduce storage and improve transfer efficiency."
        ),
        "History size": (
            "Deleting a file from the latest commit does not automatically remove "
            "old copies from repository history."
        ),
    }

    for topic, explanation in considerations.items():
        print(f"\n{topic}:")
        print(f"  {explanation}")


# ---------------------------------------------------------------------------
# Section 14: Security
# ---------------------------------------------------------------------------

def demonstrate_security_considerations() -> None:
    print_section("14. Security considerations")

    security_rules = [
        "Never intentionally commit passwords, private keys, API tokens, or access credentials.",
        "Use .gitignore to reduce accidental tracking of local secret files, but do not treat it as a security boundary.",
        "Review staged changes before committing sensitive projects.",
        "A secret already present in Git history may remain in older commits even after deletion from the current branch.",
        "Repository access controls and remote hosting permissions are separate from local Git commands.",
        "Signed commits can provide stronger authorship and integrity signals, but signing does not make malicious content safe.",
        "A commit hash identifies content and metadata in the Git object model; it is not an authorization mechanism.",
    ]

    for index, rule in enumerate(security_rules, start=1):
        print(f"{index}. {rule}")


# ---------------------------------------------------------------------------
# Section 15: Practical workflow
# ---------------------------------------------------------------------------

def demonstrate_standard_workflow() -> None:
    print_section("15. Standard local Git workflow")

    workflow = [
        ("1", "Inspect", "git status"),
        ("2", "Review unstaged changes", "git diff"),
        ("3", "Select changes", "git add <file>"),
        ("4", "Review staged changes", "git diff --cached"),
        ("5", "Record a snapshot", "git commit -m \"Clear message\""),
        ("6", "Inspect history", "git log --oneline"),
    ]

    for number, action, command in workflow:
        print(f"{number}. {action:28} {command}")

    print(
        "\nThe important discipline is the review between editing, staging, "
        "and committing."
    )


# ---------------------------------------------------------------------------
# Section 16: Edge cases
# ---------------------------------------------------------------------------

def demonstrate_edge_cases() -> None:
    print_section("16. Important edge cases")

    model = GitLearningModel(
        committed={"data.txt": "A\n"},
        staged={"data.txt": "A\n"},
        working={"data.txt": "A\n"},
    )

    print("\nCase 1: edit and then return exactly to the committed content.")
    model.edit_file("data.txt", "B\n")
    model.edit_file("data.txt", "A\n")
    model.show_status()

    print("\nCase 2: stage a change, then undo the working-tree change.")
    model.edit_file("data.txt", "C\n")
    model.git_add("data.txt")
    model.edit_file("data.txt", "A\n")
    model.show_status()

    print(
        "\nThe staged area still contains C while the working tree contains A."
    )

    print("\nCase 3: unstage while keeping the working edit.")
    model.git_restore_staged("data.txt")
    model.show_status()

    print(
        "\nThe exact behavior of restore, reset, checkout, and related commands "
        "depends on their options and the Git version. Always understand the "
        "source and destination of the data before using a destructive command."
    )


# ---------------------------------------------------------------------------
# Section 17: Testing the teaching model
# ---------------------------------------------------------------------------

def assert_equal(actual, expected, description: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{description}\nExpected: {expected!r}\nActual: {actual!r}"
        )


def run_self_tests() -> None:
    print_section("17. Self-tests")

    model = GitLearningModel()

    model.create_file("a.txt", "one")
    assert_equal(
        model.status()["a.txt"],
        "untracked",
        "A newly created file should be untracked.",
    )

    model.git_add("a.txt")
    assert_equal(
        model.status()["a.txt"],
        "new file staged",
        "A new file should become staged after git add.",
    )

    model.commit("Add a")
    assert_equal(
        model.status()["a.txt"],
        "clean",
        "A committed file should be clean.",
    )

    model.edit_file("a.txt", "two")
    assert_equal(
        model.status()["a.txt"],
        "modified",
        "Editing a tracked file should make it modified.",
    )

    model.git_add("a.txt")
    assert_equal(
        model.status()["a.txt"],
        "modified and staged",
        "Staging a modification should make it staged.",
    )

    model.edit_file("a.txt", "three")
    assert_equal(
        model.status()["a.txt"],
        "staged and additionally modified",
        "A second edit after staging should produce two change boundaries.",
    )

    print("All self-tests passed.")


# ---------------------------------------------------------------------------
# Section 18: Command reference
# ---------------------------------------------------------------------------

def print_command_reference() -> None:
    print_section("18. Core Git command reference")

    commands = [
        ("git init", "Create a new local repository."),
        ("git status", "Inspect working-tree and staging-area state."),
        ("git add file", "Copy the current file contents into the index."),
        ("git add .", "Stage changes under the current directory; review carefully."),
        ("git diff", "Show unstaged working-tree changes."),
        ("git diff --cached", "Show staged changes relative to the current commit."),
        ("git commit -m \"message\"", "Create a commit from staged contents."),
        ("git log --oneline", "Inspect compact commit history."),
        ("git branch", "List branches."),
        ("git branch name", "Create a branch at the current commit."),
        ("git switch name", "Switch to another branch."),
        ("git restore --staged file", "Unstage a path while generally preserving its working edit."),
        ("git restore file", "Restore a working-tree path from the index; may discard edits."),
        ("git show <commit>", "Inspect a commit and its changes."),
        ("git rev-parse HEAD", "Resolve HEAD to a commit identifier."),
        ("git rev-parse --show-toplevel", "Find the repository's top-level directory."),
    ]

    longest = max(len(command) for command, _ in commands)

    for command, description in commands:
        print(f"{command:<{longest}}  {description}")


# ---------------------------------------------------------------------------
# Section 19: Main program
# ---------------------------------------------------------------------------

def main() -> None:
    print("=" * 78)
    print("GIT FUNDAMENTALS")
    print("Repository, Working Tree, and Staging Area")
    print("=" * 78)

    explain_basic_terminology()
    demonstrate_three_area_model()
    demonstrate_file_lifecycle()
    demonstrate_two_types_of_diff()
    demonstrate_partial_staging()
    demonstrate_hashing()
    demonstrate_object_database()
    demonstrate_real_git_safely()
    demonstrate_common_mistakes()
    demonstrate_gitignore_rules()
    demonstrate_commit_graph()
    demonstrate_branches()
    demonstrate_performance_considerations()
    demonstrate_security_considerations()
    demonstrate_standard_workflow()
    demonstrate_edge_cases()
    run_self_tests()
    print_command_reference()

    print_section("20. Final conceptual model")
    print(
        "Think about Git as a controlled flow of snapshots:\n\n"
        "Working tree\n"
        "    |\n"
        "    | git add\n"
        "    v\n"
        "Staging area / index\n"
        "    |\n"
        "    | git commit\n"
        "    v\n"
        "Repository history\n\n"
        "The staging area is what makes Git's workflow especially powerful: "
        "you can decide exactly which changes belong in the next commit."
    )


if __name__ == "__main__":
    main()
```
