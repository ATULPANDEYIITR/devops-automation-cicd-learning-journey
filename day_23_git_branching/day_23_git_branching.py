"""
Git Branching: Branches, checkout, switch, and merge
====================================================

This standalone study script teaches Git branching from beginner to advanced
concepts through executable Python simulations.

The script does not execute Git commands on the user's computer. Instead, it
models the important internal ideas behind branches, commits, HEAD movement,
checkout, switch, fast-forward merges, three-way merges, merge conflicts,
conflict resolution, branch deletion, and history inspection.

It is intentionally self-contained and uses only the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple
import copy
import hashlib
import textwrap


# ============================================================================
# 1. BASIC GIT TERMINOLOGY
# ============================================================================

def print_section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def explain(message: str) -> None:
    print(textwrap.dedent(message).strip())


print_section("1. Git branching fundamentals")

explain(
    """
    A Git repository stores commits as snapshots connected by parent
    relationships.

    A branch is not a second copy of the project. Conceptually, a branch is
    simply a movable name pointing to a commit.

    HEAD identifies the commit or branch currently checked out.

    For example:

        main -> C
        HEAD -> main -> C

    Creating a branch does not copy all project files. It creates another
    reference to the current commit:

        main    -> C
        feature -> C
        HEAD    -> feature

    A new commit on feature moves only feature:

        main    -> C
        feature -> D
        HEAD    -> feature

    This distinction is fundamental to understanding Git branching.
    """
)


# ============================================================================
# 2. A SMALL COMMIT OBJECT
# ============================================================================

@dataclass
class Commit:
    commit_id: str
    message: str
    parents: List[str]
    files: Dict[str, str]

    def short_id(self) -> str:
        return self.commit_id[:8]


def generate_commit_id(
    message: str,
    parents: List[str],
    files: Dict[str, str],
) -> str:
    """Create a deterministic content-based identifier for our simulation."""
    material = (
        message
        + "|"
        + ",".join(parents)
        + "|"
        + repr(sorted(files.items()))
    )
    return hashlib.sha1(material.encode("utf-8")).hexdigest()


# ============================================================================
# 3. A MINIATURE GIT REPOSITORY
# ============================================================================

@dataclass
class Repository:
    commits: Dict[str, Commit] = field(default_factory=dict)
    branches: Dict[str, str] = field(default_factory=dict)
    head_branch: Optional[str] = None
    detached_head: Optional[str] = None
    working_tree: Dict[str, str] = field(default_factory=dict)
    staging_area: Dict[str, str] = field(default_factory=dict)

    def initialize(self) -> None:
        """Create the equivalent of an initial repository commit."""
        initial_files = {
            "README.md": "# Branching Demo\n",
            "app.py": 'print("Hello")\n',
        }

        commit_id = generate_commit_id(
            "Initial commit",
            [],
            initial_files,
        )

        self.commits[commit_id] = Commit(
            commit_id=commit_id,
            message="Initial commit",
            parents=[],
            files=copy.deepcopy(initial_files),
        )

        self.branches["main"] = commit_id
        self.head_branch = "main"
        self.detached_head = None
        self.working_tree = copy.deepcopy(initial_files)
        self.staging_area = {}

    @property
    def head_commit_id(self) -> str:
        if self.head_branch is not None:
            return self.branches[self.head_branch]
        if self.detached_head is not None:
            return self.detached_head
        raise RuntimeError("HEAD is not attached to a branch or commit.")

    @property
    def head_commit(self) -> Commit:
        return self.commits[self.head_commit_id]

    def status(self) -> None:
        """Display a simplified equivalent of `git status`."""
        print(f"On branch: {self.head_branch or '(detached HEAD)'}")
        print(f"HEAD: {self.head_commit.short_id()}")

        changes = []

        all_paths = (
            set(self.head_commit.files)
            | set(self.working_tree)
            | set(self.staging_area)
        )

        for path in sorted(all_paths):
            committed = self.head_commit.files.get(path)
            working = self.working_tree.get(path)
            staged = self.staging_area.get(path)

            if staged is not None and staged != committed:
                changes.append(f"staged: {path}")
            elif working != committed:
                changes.append(f"modified: {path}")

        if changes:
            print("Changes:")
            for change in changes:
                print("  " + change)
        else:
            print("Working tree clean.")

    def create_branch(self, name: str, start_point: Optional[str] = None) -> None:
        """Equivalent to `git branch <name>`."""
        if name in self.branches:
            raise ValueError(f"Branch '{name}' already exists.")

        target = start_point or self.head_commit_id

        if target not in self.commits:
            raise ValueError("The requested starting commit does not exist.")

        self.branches[name] = target

    def checkout(self, target: str) -> None:
        """
        Simplified `git checkout`.

        If target is a branch, HEAD attaches to that branch.
        If target is a commit, HEAD becomes detached.
        """
        if self.working_tree != self.head_commit.files:
            raise RuntimeError(
                "Cannot switch with uncommitted changes in this simulation."
            )

        if target in self.branches:
            self.head_branch = target
            self.detached_head = None
            self.working_tree = copy.deepcopy(
                self.commits[self.branches[target]].files
            )
            return

        if target in self.commits:
            self.head_branch = None
            self.detached_head = target
            self.working_tree = copy.deepcopy(self.commits[target].files)
            return

        raise ValueError(f"Unknown branch or commit: {target}")

    def switch(self, target: str, create: bool = False) -> None:
        """
        Simplified `git switch`.

        `git switch <branch>` changes branches.
        `git switch -c <branch>` creates and switches to a branch.
        """
        if create:
            self.create_branch(target)

        if target not in self.branches:
            raise ValueError(
                f"Branch '{target}' does not exist. "
                "Use create=True to create it."
            )

        self.checkout(target)

    def edit_file(self, path: str, content: str) -> None:
        """Modify a file in the simulated working tree."""
        self.working_tree[path] = content

    def add(self, path: str) -> None:
        """Equivalent to `git add <path>`."""
        if path not in self.working_tree:
            raise FileNotFoundError(path)

        self.staging_area[path] = self.working_tree[path]

    def add_all(self) -> None:
        """Simplified equivalent of `git add .`."""
        self.staging_area = copy.deepcopy(self.working_tree)

    def commit(self, message: str) -> str:
        """Create a commit from staged changes."""
        if not self.staging_area:
            raise RuntimeError("Nothing is staged for commit.")

        if self.head_branch is None:
            raise RuntimeError(
                "Cannot commit normally while HEAD is detached."
            )

        new_files = copy.deepcopy(self.head_commit.files)

        for path, content in self.staging_area.items():
            new_files[path] = content

        parent = self.head_commit_id

        commit_id = generate_commit_id(
            message,
            [parent],
            new_files,
        )

        self.commits[commit_id] = Commit(
            commit_id=commit_id,
            message=message,
            parents=[parent],
            files=new_files,
        )

        self.branches[self.head_branch] = commit_id
        self.working_tree = copy.deepcopy(new_files)
        self.staging_area.clear()

        return commit_id

    def commit_all(self, message: str) -> str:
        """Convenience function equivalent to add all + commit."""
        self.add_all()
        return self.commit(message)

    def ancestors(self, commit_id: str) -> Set[str]:
        """Return all ancestors of a commit, including the commit itself."""
        visited: Set[str] = set()
        stack = [commit_id]

        while stack:
            current = stack.pop()

            if current in visited:
                continue

            visited.add(current)
            stack.extend(self.commits[current].parents)

        return visited

    def is_ancestor(self, possible_ancestor: str, commit_id: str) -> bool:
        return possible_ancestor in self.ancestors(commit_id)

    def find_merge_base(self, first: str, second: str) -> Optional[str]:
        """
        Find a common ancestor.

        This simplified implementation selects the first common ancestor
        discovered from first's ancestry. Real Git's merge-base algorithm is
        optimized and handles complex DAGs more carefully.
        """
        first_ancestors = self.ancestors(first)

        queue = [second]
        visited: Set[str] = set()

        while queue:
            current = queue.pop(0)

            if current in visited:
                continue

            visited.add(current)

            if current in first_ancestors:
                return current

            queue.extend(self.commits[current].parents)

        return None

    def merge(
        self,
        target_branch: str,
        message: Optional[str] = None,
        conflict_resolutions: Optional[Dict[str, str]] = None,
    ) -> Tuple[str, List[str]]:
        """
        Merge target_branch into the currently checked-out branch.

        Returns:
            (result_type, conflicts)

        result_type is one of:
            already-up-to-date
            fast-forward
            merge-commit
        """
        if self.head_branch is None:
            raise RuntimeError("Cannot merge while HEAD is detached.")

        if self.working_tree != self.head_commit.files:
            raise RuntimeError(
                "Commit or discard local changes before merging."
            )

        if target_branch not in self.branches:
            raise ValueError(f"Unknown branch: {target_branch}")

        current_id = self.head_commit_id
        target_id = self.branches[target_branch]

        if current_id == target_id:
            return "already-up-to-date", []

        # Target is already contained in the current history.
        if self.is_ancestor(target_id, current_id):
            return "already-up-to-date", []

        # Current branch can simply move forward.
        if self.is_ancestor(current_id, target_id):
            self.branches[self.head_branch] = target_id
            self.working_tree = copy.deepcopy(
                self.commits[target_id].files
            )
            return "fast-forward", []

        base_id = self.find_merge_base(current_id, target_id)

        if base_id is None:
            raise RuntimeError("No common ancestor found.")

        base = self.commits[base_id]
        current = self.commits[current_id]
        target = self.commits[target_id]

        merged_files = copy.deepcopy(base.files)
        conflicts: List[str] = []

        all_paths = (
            set(base.files)
            | set(current.files)
            | set(target.files)
        )

        for path in sorted(all_paths):
            base_value = base.files.get(path)
            current_value = current.files.get(path)
            target_value = target.files.get(path)

            current_changed = current_value != base_value
            target_changed = target_value != base_value

            if current_changed and target_changed:
                if current_value == target_value:
                    merged_files[path] = current_value
                else:
                    conflicts.append(path)

                    if conflict_resolutions and path in conflict_resolutions:
                        merged_files[path] = conflict_resolutions[path]
                    else:
                        merged_files[path] = (
                            "<<<<<<< CURRENT\n"
                            + str(current_value)
                            + "=======\n"
                            + str(target_value)
                            + ">>>>>>> TARGET\n"
                        )

            elif current_changed:
                if current_value is None:
                    merged_files.pop(path, None)
                else:
                    merged_files[path] = current_value

            elif target_changed:
                if target_value is None:
                    merged_files.pop(path, None)
                else:
                    merged_files[path] = target_value

        if conflicts and not conflict_resolutions:
            self.working_tree = merged_files
            return "conflict", conflicts

        merge_message = message or (
            f"Merge branch '{target_branch}' into '{self.head_branch}'"
        )

        merge_commit_id = generate_commit_id(
            merge_message,
            [current_id, target_id],
            merged_files,
        )

        self.commits[merge_commit_id] = Commit(
            commit_id=merge_commit_id,
            message=merge_message,
            parents=[current_id, target_id],
            files=merged_files,
        )

        self.branches[self.head_branch] = merge_commit_id
        self.working_tree = copy.deepcopy(merged_files)
        self.staging_area.clear()

        return "merge-commit", conflicts

    def delete_branch(self, name: str) -> None:
        """Equivalent to `git branch -d <name>` with safety checking."""
        if name not in self.branches:
            raise ValueError(f"Branch '{name}' does not exist.")

        if name == self.head_branch:
            raise RuntimeError("Cannot delete the currently checked-out branch.")

        target = self.branches[name]
        current = self.head_commit_id

        if not self.is_ancestor(target, current):
            raise RuntimeError(
                "Branch is not fully merged. "
                "Use a forced deletion only when you intentionally accept "
                "the risk of losing the branch reference."
            )

        del self.branches[name]

    def force_delete_branch(self, name: str) -> None:
        """Equivalent to the conceptual behavior of `git branch -D`."""
        if name not in self.branches:
            raise ValueError(f"Branch '{name}' does not exist.")

        if name == self.head_branch:
            raise RuntimeError("Cannot delete the current branch.")

        del self.branches[name]

    def log(self, limit: int = 20) -> None:
        """Display a compact history from HEAD."""
        print("\nCommit history:")

        visited: Set[str] = set()
        queue = [self.head_commit_id]
        shown = 0

        while queue and shown < limit:
            current_id = queue.pop(0)

            if current_id in visited:
                continue

            visited.add(current_id)
            commit = self.commits[current_id]

            print(
                f"* {commit.short_id()} "
                f"{commit.message}"
            )

            if commit.parents:
                print(
                    "  parents: "
                    + ", ".join(parent[:8] for parent in commit.parents)
                )

            queue.extend(commit.parents)
            shown += 1

    def show_branches(self) -> None:
        """Display branch pointers."""
        print("\nBranches:")

        for name, commit_id in sorted(self.branches.items()):
            marker = "*" if name == self.head_branch else " "
            print(
                f"{marker} {name:<15} -> "
                f"{self.commits[commit_id].short_id()} "
                f"{self.commits[commit_id].message}"
            )

    def graph(self) -> None:
        """Print a simple textual representation of the commit graph."""
        print("\nCommit graph:")

        branch_targets: Dict[str, List[str]] = {}

        for branch, commit_id in self.branches.items():
            branch_targets.setdefault(commit_id, []).append(branch)

        visited: Set[str] = set()
        queue = [self.head_commit_id]

        while queue:
            commit_id = queue.pop(0)

            if commit_id in visited:
                continue

            visited.add(commit_id)
            commit = self.commits[commit_id]

            labels = branch_targets.get(commit_id, [])

            label_text = ""
            if labels:
                label_text = " [" + ", ".join(labels) + "]"

            print(
                f"* {commit.short_id()}{label_text}: "
                f"{commit.message}"
            )

            for parent in commit.parents:
                queue.append(parent)


# ============================================================================
# 4. BASIC REPOSITORY WORKFLOW
# ============================================================================

print_section("2. Creating commits and branches")

repo = Repository()
repo.initialize()

print("Initial repository:")
repo.show_branches()
repo.status()

repo.edit_file(
    "README.md",
    "# Branching Demo\n\nThis repository demonstrates Git branching.\n",
)
repo.commit_all("Expand README")

repo.edit_file(
    "app.py",
    'def hello():\n'
    '    return "Hello from main"\n',
)
repo.commit_all("Add hello function")

repo.show_branches()
repo.log()


# ============================================================================
# 5. CREATING A FEATURE BRANCH
# ============================================================================

print_section("3. Creating and switching to a feature branch")

repo.switch("feature/login", create=True)

print("After `git switch -c feature/login`:")
repo.show_branches()

repo.edit_file(
    "login.py",
    """
def authenticate(username, password):
    return bool(username) and bool(password)
""".strip()
    + "\n",
)
repo.commit_all("Add login authentication")

repo.show_branches()
repo.log()


# ============================================================================
# 6. MAIN AND FEATURE BRANCHES DIVERGE
# ============================================================================

print_section("4. Diverging branches")

repo.switch("main")

repo.edit_file(
    "app.py",
    'def hello():\n'
    '    return "Hello from main application"\n',
)
repo.commit_all("Improve main application message")

print("Main now has work that feature/login does not have:")
repo.graph()

repo.switch("feature/login")

repo.edit_file(
    "login.py",
    """
def authenticate(username, password):
    if not isinstance(username, str):
        return False

    if not isinstance(password, str):
        return False

    return bool(username.strip()) and bool(password)
""".strip()
    + "\n",
)
repo.commit_all("Validate login input")

repo.graph()


# ============================================================================
# 7. FAST-FORWARD MERGE
# ============================================================================

print_section("5. Fast-forward merge")

fast_forward_repo = Repository()
fast_forward_repo.initialize()

fast_forward_repo.switch("feature", create=True)

fast_forward_repo.edit_file(
    "feature.txt",
    "Feature work\n",
)
fast_forward_repo.commit_all("Add feature")

print("Before merging:")
fast_forward_repo.show_branches()

fast_forward_repo.switch("main")
result, conflicts = fast_forward_repo.merge("feature")

print(f"\nMerge result: {result}")
print(f"Conflicts: {conflicts}")
fast_forward_repo.show_branches()
fast_forward_repo.graph()

explain(
    """
    A fast-forward merge happens when the current branch has no commits that
    are absent from the branch being merged.

    Example:

        A---B---C   feature
            ^
            main

    After the merge:

        A---B---C   main, feature

    No new merge commit is necessary. The main branch reference simply moves
    to C.
    """
)


# ============================================================================
# 8. THREE-WAY MERGE
# ============================================================================

print_section("6. Three-way merge")

merge_repo = Repository()
merge_repo.initialize()

merge_repo.switch("feature", create=True)

merge_repo.edit_file(
    "feature.txt",
    "Feature implementation\n",
)
merge_repo.commit_all("Implement feature")

merge_repo.switch("main")

merge_repo.edit_file(
    "main.txt",
    "Independent main development\n",
)
merge_repo.commit_all("Continue main development")

merge_repo.switch("feature")

print("Before merge:")
merge_repo.graph()

merge_repo.switch("main")
result, conflicts = merge_repo.merge("feature")

print(f"\nMerge result: {result}")
print(f"Conflicts: {conflicts}")

merge_repo.graph()

explain(
    """
    A three-way merge uses three snapshots:

        1. The merge base
        2. The current branch tip
        3. The branch being merged

    Git compares what changed from the common ancestor on both sides.

    If different files changed, Git can normally combine those changes.

    If the same file changed in incompatible ways, Git may report a conflict.
    """
)


# ============================================================================
# 9. MERGE CONFLICT
# ============================================================================

print_section("7. Demonstrating a merge conflict")

conflict_repo = Repository()
conflict_repo.initialize()

conflict_repo.edit_file(
    "config.txt",
    "mode=development\n",
)
conflict_repo.commit_all("Add configuration")

conflict_repo.switch("feature", create=True)

conflict_repo.edit_file(
    "config.txt",
    "mode=feature\n",
)
conflict_repo.commit_all("Configure feature mode")

conflict_repo.switch("main")

conflict_repo.edit_file(
    "config.txt",
    "mode=production\n",
)
conflict_repo.commit_all("Configure production mode")

result, conflicts = conflict_repo.merge("feature")

print(f"Merge result: {result}")
print(f"Conflicting files: {conflicts}")
print("\nConflict representation:")
print(conflict_repo.working_tree["config.txt"])

explain(
    """
    A conflict is not automatically a data-loss event.

    Git stops because it cannot determine which version expresses the intended
    result.

    A human must decide what the final content should be.

    A typical conflict-resolution workflow is:

        git status
        edit the conflicted file
        git add <file>
        git commit

    Modern Git also provides `git merge --abort` to abandon an in-progress
    merge when the user decides to return to the pre-merge state.
    """
)


# ============================================================================
# 10. RESOLVING A CONFLICT
# ============================================================================

print_section("8. Resolving a conflict")

resolved_repo = Repository()
resolved_repo.initialize()

resolved_repo.edit_file(
    "config.txt",
    "mode=development\n",
)
resolved_repo.commit_all("Add configuration")

resolved_repo.switch("feature", create=True)

resolved_repo.edit_file(
    "config.txt",
    "mode=feature\n",
)
resolved_repo.commit_all("Configure feature")

resolved_repo.switch("main")

resolved_repo.edit_file(
    "config.txt",
    "mode=production\n",
)
resolved_repo.commit_all("Configure production")

resolution = {
    "config.txt": (
        "mode=production\n"
        "feature_enabled=true\n"
    )
}

result, conflicts = resolved_repo.merge(
    "feature",
    message="Merge feature configuration",
    conflict_resolutions=resolution,
)

print(f"Merge result: {result}")
print(f"Conflicts after resolution: {conflicts}")
print("Resolved file:")
print(resolved_repo.working_tree["config.txt"])
resolved_repo.graph()


# ============================================================================
# 11. CHECKOUT VERSUS SWITCH
# ============================================================================

print_section("9. `checkout` versus `switch`")

explain(
    """
    `git checkout` is an older multi-purpose command.

    It can:
        * switch branches
        * restore files
        * detach HEAD at a commit

    `git switch` was introduced to make branch switching clearer.

    Examples:

        git checkout main
        git switch main

    Both can switch to an existing branch.

    Creating and switching to a branch can be expressed as:

        git checkout -b feature
        git switch -c feature

    The modern `switch` command communicates branch operations more clearly,
    while `checkout` remains widely used and supported.
    """
)

comparison = {
    "Existing branch": {
        "checkout": "git checkout main",
        "switch": "git switch main",
    },
    "Create + switch": {
        "checkout": "git checkout -b feature",
        "switch": "git switch -c feature",
    },
    "Detached commit": {
        "checkout": "git checkout <commit>",
        "switch": "git switch --detach <commit>",
    },
}

for operation, commands in comparison.items():
    print(f"\n{operation}")
    for command_name, command in commands.items():
        print(f"  {command_name:<10}: {command}")


# ============================================================================
# 12. DETACHED HEAD
# ============================================================================

print_section("10. Detached HEAD")

detached_repo = Repository()
detached_repo.initialize()

detached_repo.edit_file(
    "app.py",
    'print("Second version")\n',
)
second_commit = detached_repo.commit_all("Second version")

detached_repo.checkout(second_commit)

print(
    f"HEAD branch: {detached_repo.head_branch}, "
    f"detached commit: {detached_repo.detached_head[:8]}"
)

explain(
    """
    Detached HEAD means HEAD points directly to a commit rather than to a
    branch name.

    It is useful for examining historical versions, testing old code, or
    temporarily experimenting with a previous commit.

    Commits created while detached are not automatically attached to a branch.
    If those commits matter, create a branch pointing to them before losing
    the reference.
    """
)


# ============================================================================
# 13. BRANCH DELETION
# ============================================================================

print_section("11. Safe and forced branch deletion")

delete_repo = Repository()
delete_repo.initialize()

delete_repo.switch("feature", create=True)

delete_repo.edit_file(
    "feature.txt",
    "Completed feature\n",
)
delete_repo.commit_all("Complete feature")

delete_repo.switch("main")
delete_repo.merge("feature")

delete_repo.delete_branch("feature")

print("After safe deletion:")
delete_repo.show_branches()

delete_repo.switch("experimental", create=True)
delete_repo.edit_file(
    "experimental.txt",
    "Unmerged experiment\n",
)
delete_repo.commit_all("Experimental work")

delete_repo.switch("main")

try:
    delete_repo.delete_branch("experimental")
except RuntimeError as error:
    print("\nSafe deletion prevented:")
    print(error)

delete_repo.force_delete_branch("experimental")

print("\nAfter forced deletion:")
delete_repo.show_branches()

explain(
    """
    `git branch -d branch-name` performs a safety-oriented deletion.

    `git branch -D branch-name` forces deletion.

    A deleted branch is primarily a deleted reference. The underlying commits
    may remain temporarily because Git's object database and garbage
    collection determine when unreachable objects are eventually removed.
    """
)


# ============================================================================
# 14. COMMON BRANCHING WORKFLOW
# ============================================================================

print_section("12. A practical feature-branch workflow")

workflow = [
    "git status",
    "git switch main",
    "git pull",
    "git switch -c feature/user-login",
    "edit files",
    "git status",
    "git add .",
    'git commit -m "Add user login"',
    "git switch main",
    "git pull",
    "git merge feature/user-login",
    "git push",
    "git branch -d feature/user-login",
]

for step_number, command in enumerate(workflow, start=1):
    print(f"{step_number:02}. {command}")


# ============================================================================
# 15. COMMON MISTAKES
# ============================================================================

print_section("13. Common branching mistakes")

mistakes = [
    (
        "Working directly on main",
        "Create a focused feature branch when independent development is useful."
    ),
    (
        "Switching with uncommitted work",
        "Commit, stash, or otherwise safely handle the changes before switching."
    ),
    (
        "Creating branches from the wrong commit",
        "Check the current branch and history before creating the branch."
    ),
    (
        "Deleting an unmerged branch accidentally",
        "Prefer `git branch -d` unless intentional forced deletion is required."
    ),
    (
        "Ignoring merge conflicts",
        "Inspect every conflicted file and test the resolved result."
    ),
    (
        "Merging stale branches",
        "Update the target branch and integrate recent changes deliberately."
    ),
    (
        "Using vague commit messages",
        "Describe the actual change clearly and concisely."
    ),
]

for mistake, prevention in mistakes:
    print(f"\nMistake: {mistake}")
    print(f"Practice: {prevention}")


# ============================================================================
# 16. ADVANCED BRANCHING CONCEPTS
# ============================================================================

print_section("14. Advanced branching concepts")

advanced_topics = {
    "Branch pointer":
        "A branch is a movable reference to a commit.",
    "HEAD":
        "HEAD identifies the current checkout position.",
    "Remote-tracking branch":
        "A local reference such as origin/main records a remote branch state.",
    "Upstream":
        "A local branch can track a remote branch for pull/push defaults.",
    "Fast-forward":
        "The target branch is directly ahead, so no merge commit is needed.",
    "Three-way merge":
        "Git compares the merge base, current tip, and target tip.",
    "Merge commit":
        "A commit with multiple parents records a non-fast-forward merge.",
    "Detached HEAD":
        "HEAD points directly at a commit instead of a branch.",
    "Branch divergence":
        "Branches contain commits absent from each other's histories.",
    "Conflict":
        "Git cannot automatically reconcile incompatible changes.",
}

for concept, definition in advanced_topics.items():
    print(f"\n{concept}")
    print(f"  {definition}")


# ============================================================================
# 17. PERFORMANCE AND DESIGN CONSIDERATIONS
# ============================================================================

print_section("15. Performance and repository design")

explain(
    """
    Git branching is lightweight because branches are references rather than
    complete copies of working directories.

    The expensive operations in real repositories can instead involve:

        * large binary files
        * enormous histories
        * generated artifacts
        * poorly managed dependencies
        * large working trees
        * frequent conflict-heavy merges

    Good repository design keeps generated files out of source control when
    appropriate, uses meaningful commit boundaries, and keeps branch
    lifetimes understandable.

    Branch strategy is a team design decision. Different organizations use
    feature branches, short-lived integration branches, release branches,
    trunk-based development, or combinations of these patterns.
    """
)


# ============================================================================
# 18. SECURITY CONSIDERATIONS
# ============================================================================

print_section("16. Security considerations")

explain(
    """
    Branching itself is not a security boundary.

    A secret committed to a branch can remain in repository history even after
    the file is deleted in a later commit.

    Therefore:

        * Do not commit passwords, API keys, private keys, or access tokens.
        * Use secret-management systems for sensitive configuration.
        * Review branches before sharing or merging them.
        * Understand that deleting a branch does not necessarily erase
          objects immediately.
        * Treat repository history as persistent data.

    If a secret is accidentally committed, removing the visible file is not
    enough. The credential should be revoked or rotated, and history rewriting
    may be required depending on the situation.
    """
)


# ============================================================================
# 19. TESTING A BRANCH BEFORE MERGING
# ============================================================================

print_section("17. Testing before merge")

def validate_configuration(configuration: Dict[str, str]) -> bool:
    """Simple validation function used as a pre-merge quality check."""
    required_keys = {"environment", "version"}

    if not required_keys.issubset(configuration):
        return False

    if configuration["environment"] not in {
        "development",
        "testing",
        "production",
    }:
        return False

    return bool(configuration["version"])


test_cases = [
    {
        "environment": "development",
        "version": "1.0",
    },
    {
        "environment": "production",
        "version": "2.1",
    },
    {
        "environment": "unknown",
        "version": "2.1",
    },
    {
        "environment": "testing",
    },
]

for case in test_cases:
    print(f"{case} -> valid={validate_configuration(case)}")


# ============================================================================
# 20. A SIMPLE BRANCHING STRATEGY SIMULATION
# ============================================================================

print_section("18. Industry-style branching simulation")

project = Repository()
project.initialize()

# Stable branch.
project.edit_file(
    "service.py",
    """
def health_check():
    return {"status": "ok"}
""".strip()
    + "\n",
)
project.commit_all("Add health check")

# Feature branch.
project.switch("feature/authentication", create=True)

project.edit_file(
    "auth.py",
    """
def authenticate(username, password):
    return username == "admin" and password == "demo"
""".strip()
    + "\n",
)
project.commit_all("Add authentication")

project.edit_file(
    "service.py",
    """
def health_check():
    return {"status": "ok", "service": "api"}
""".strip()
    + "\n",
)
project.commit_all("Add service metadata")

# Main continues independently.
project.switch("main")

project.edit_file(
    "service.py",
    """
def health_check():
    return {"status": "ok", "version": "1.0"}
""".strip()
    + "\n",
)
project.commit_all("Add service version")

print("\nBefore integration:")
project.graph()

result, conflicts = project.merge(
    "feature/authentication",
    message="Merge authentication feature",
    conflict_resolutions={
        "service.py": (
            'def health_check():\n'
            '    return {\n'
            '        "status": "ok",\n'
            '        "version": "1.0",\n'
            '        "service": "api",\n'
            '    }\n'
        )
    },
)

print(f"\nIntegration result: {result}")
print(f"Conflicts resolved: {conflicts}")
print("\nAfter integration:")
project.graph()


# ============================================================================
# 21. MINI SELF-TEST
# ============================================================================

print_section("19. Self-test")

def run_assertions() -> None:
    test_repo = Repository()
    test_repo.initialize()

    assert "main" in test_repo.branches

    test_repo.switch("feature", create=True)
    assert test_repo.head_branch == "feature"

    test_repo.edit_file("feature.txt", "hello")
    test_repo.commit_all("Feature commit")

    feature_tip = test_repo.head_commit_id

    test_repo.switch("main")
    assert test_repo.head_commit_id != feature_tip

    result, conflicts = test_repo.merge("feature")
    assert result == "fast-forward"
    assert not conflicts
    assert test_repo.head_commit_id == feature_tip

    print("All self-tests passed.")


run_assertions()


# ============================================================================
# 22. FINAL CONCEPT CHECK
# ============================================================================

print_section("20. Concept check")

questions = [
    (
        "What does a branch point to?",
        "A commit reference."
    ),
    (
        "Does creating a branch copy the complete repository?",
        "No. It creates another reference to a commit."
    ),
    (
        "What does HEAD identify?",
        "The current checkout position."
    ),
    (
        "What is a fast-forward merge?",
        "Moving the current branch pointer forward without creating a merge commit."
    ),
    (
        "What is a three-way merge?",
        "A merge based on the common ancestor and the two branch tips."
    ),
    (
        "What causes a merge conflict?",
        "Git cannot automatically reconcile incompatible changes."
    ),
    (
        "What does `git switch -c feature` do?",
        "Creates a new branch and switches to it."
    ),
    (
        "What is detached HEAD?",
        "HEAD points directly to a commit instead of a branch."
    ),
]

for question, answer in questions:
    print(f"\nQ: {question}")
    print(f"A: {answer}")


print_section("21. Key command reference")

commands = [
    ("git branch", "List local branches"),
    ("git branch <name>", "Create a branch"),
    ("git switch <name>", "Switch to an existing branch"),
    ("git switch -c <name>", "Create and switch to a branch"),
    ("git checkout <name>", "Older multi-purpose command for switching"),
    ("git checkout -b <name>", "Older command to create and switch"),
    ("git merge <branch>", "Merge another branch into the current branch"),
    ("git branch -d <name>", "Safely delete a merged branch"),
    ("git branch -D <name>", "Force-delete a branch"),
    ("git status", "Show working-tree and staging state"),
    ("git log --oneline --graph --decorate --all", "Inspect commit graph"),
]

for command, purpose in commands:
    print(f"{command:<45} {purpose}")

print("\nStudy script completed successfully.")
