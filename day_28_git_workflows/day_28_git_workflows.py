"""
Git Workflows: Feature Branches, GitHub Flow, and Trunk-Based Development

A standalone study and demonstration program covering Git workflow concepts from
absolute beginner through advanced practical usage.

The program is intentionally self-contained. It does not execute Git commands
against the user's repository. Instead, it models workflow behavior safely and
uses real subprocess examples only when the user explicitly chooses the
optional local Git demonstration.

Recommended Python version: 3.10+
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable, Optional
import argparse
import subprocess
import tempfile
import textwrap
import unittest


# =============================================================================
# 1. FUNDAMENTALS
# =============================================================================

def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def explain(message: str) -> None:
    print(textwrap.dedent(message).strip())


def beginner_basics() -> None:
    section("1. Git Workflow Fundamentals")

    explain(
        """
        Git is a distributed version-control system. A Git workflow is a set of
        conventions describing how people create changes, review them, integrate
        them, release them, and recover from failures.

        Important terms:

        Repository:
            The complete Git-managed project history and working data.

        Working tree:
            Files currently checked out on disk.

        Commit:
            A recorded snapshot of project changes.

        Branch:
            A movable reference to a commit. A branch is not inherently a
            separate copy of the repository.

        Remote:
            Another repository location, commonly named "origin".

        Pull:
            In everyday Git usage, "git pull" fetches remote changes and then
            integrates them into the current branch.

        Fetch:
            Downloads remote references and objects without changing the current
            working tree.

        Merge:
            Combines histories and can create a merge commit.

        Rebase:
            Replays commits onto a different base, producing new commit IDs.

        Pull request:
            A collaboration mechanism, commonly provided by Git hosting
            platforms, for reviewing and integrating proposed changes.

        Continuous integration:
            Automated validation performed when changes are submitted.

        Deployment:
            Making a validated version available in an environment.

        Git workflow design is primarily about controlling how changes move from
        individual work to shared code and eventually to production.
        """
    )

    commands = {
        "Create repository": "git init",
        "Check state": "git status",
        "Create branch": "git switch -c feature/login",
        "Stage files": "git add .",
        "Commit": 'git commit -m "Add login validation"',
        "Show branches": "git branch",
        "Fetch remote": "git fetch origin",
        "Push branch": "git push -u origin feature/login",
        "Switch branch": "git switch main",
        "Merge": "git merge feature/login",
        "Rebase": "git rebase main",
    }

    print("\nCommon commands:")
    for purpose, command in commands.items():
        print(f"  {purpose:20} {command}")


# =============================================================================
# 2. DOMAIN MODEL
# =============================================================================

class WorkflowType(Enum):
    FEATURE_BRANCH = "Feature Branch Workflow"
    GITHUB_FLOW = "GitHub Flow"
    TRUNK_BASED = "Trunk-Based Development"


class IntegrationMethod(Enum):
    MERGE = "merge"
    REBASE = "rebase"
    SQUASH = "squash"


@dataclass
class Commit:
    commit_id: str
    message: str
    author: str
    parents: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)

    def short_id(self) -> str:
        return self.commit_id[:7]


@dataclass
class Branch:
    name: str
    head: str
    protected: bool = False

    def describe(self) -> str:
        protection = "protected" if self.protected else "unprotected"
        return f"{self.name} -> {self.head[:7]} ({protection})"


@dataclass
class PullRequest:
    number: int
    source_branch: str
    target_branch: str
    title: str
    approvals: int = 0
    checks_passed: bool = False
    merged: bool = False

    def is_mergeable(self, required_approvals: int = 1) -> bool:
        return (
            self.approvals >= required_approvals
            and self.checks_passed
            and not self.merged
        )


# =============================================================================
# 3. GIT GRAPH MODEL
# =============================================================================

class CommitGraph:
    """
    A small in-memory model of Git's commit graph.

    Real Git stores objects and references on disk. This model focuses on the
    relationships needed to reason about workflows.
    """

    def __init__(self) -> None:
        self.commits: dict[str, Commit] = {}
        self.branches: dict[str, Branch] = {}
        self._sequence = 0

    def _new_id(self) -> str:
        self._sequence += 1
        return f"commit-{self._sequence:04d}-abcdef"

    def create_commit(
        self,
        branch_name: str,
        message: str,
        author: str,
        files_changed: Optional[list[str]] = None,
    ) -> Commit:
        if branch_name not in self.branches:
            raise ValueError(f"Unknown branch: {branch_name}")

        branch = self.branches[branch_name]
        commit_id = self._new_id()
        parents = [] if branch.head == "" else [branch.head]

        commit = Commit(
            commit_id=commit_id,
            message=message,
            author=author,
            parents=parents,
            files_changed=files_changed or [],
        )

        self.commits[commit_id] = commit
        branch.head = commit_id
        return commit

    def create_branch(
        self,
        branch_name: str,
        from_branch: str = "main",
        protected: bool = False,
    ) -> Branch:
        if branch_name in self.branches:
            raise ValueError(f"Branch already exists: {branch_name}")

        if from_branch not in self.branches:
            raise ValueError(f"Source branch does not exist: {from_branch}")

        source = self.branches[from_branch]
        branch = Branch(
            name=branch_name,
            head=source.head,
            protected=protected,
        )
        self.branches[branch_name] = branch
        return branch

    def initialize(self) -> None:
        if self.branches:
            return

        self.branches["main"] = Branch(
            name="main",
            head="",
            protected=True,
        )

        self.create_commit(
            "main",
            "Initial project structure",
            "system",
            ["README.md"],
        )

    def show(self) -> None:
        print("\nCommit graph:")
        for commit in self.commits.values():
            parents = ", ".join(parent[:7] for parent in commit.parents) or "none"
            print(
                f"  {commit.short_id()} | {commit.message} | "
                f"parent(s): {parents}"
            )

        print("\nBranches:")
        for branch in self.branches.values():
            print(f"  {branch.describe()}")

    def ancestors(self, commit_id: str) -> set[str]:
        """
        Return all ancestors of a commit.

        This illustrates why Git histories are graphs rather than simple lists.
        """
        if commit_id not in self.commits:
            raise ValueError(f"Unknown commit: {commit_id}")

        found: set[str] = set()
        stack = [commit_id]

        while stack:
            current = stack.pop()
            if current in found:
                continue

            found.add(current)
            stack.extend(self.commits[current].parents)

        return found

    def common_ancestor(self, first: str, second: str) -> Optional[str]:
        first_ancestors = self.ancestors(first)
        second_ancestors = self.ancestors(second)

        common = first_ancestors & second_ancestors
        if not common:
            return None

        # This simplified model uses commit creation order to choose the newest
        # common ancestor. Real Git performs graph traversal with generation
        # information and other optimizations.
        return max(
            common,
            key=lambda commit_id: self.commits[commit_id].commit_id,
        )


def demonstrate_commit_graph() -> None:
    section("2. Commit Graph and Branch Mechanics")

    graph = CommitGraph()
    graph.initialize()

    graph.create_commit(
        "main",
        "Add application skeleton",
        "Atul",
        ["src/app.py"],
    )

    graph.create_branch("feature/auth")

    graph.create_commit(
        "feature/auth",
        "Add authentication model",
        "Developer A",
        ["src/auth.py"],
    )

    graph.create_commit(
        "feature/auth",
        "Validate authentication input",
        "Developer A",
        ["src/auth.py", "tests/test_auth.py"],
    )

    graph.create_commit(
        "main",
        "Update documentation",
        "Developer B",
        ["README.md"],
    )

    graph.show()

    feature_head = graph.branches["feature/auth"].head
    main_head = graph.branches["main"].head
    ancestor = graph.common_ancestor(feature_head, main_head)

    print(
        "\nSimplified common ancestor:",
        ancestor[:7] if ancestor else "none",
    )


# =============================================================================
# 4. BRANCH NAMING AND VALIDATION
# =============================================================================

class BranchNameValidator:
    """
    Workflow-oriented branch naming rules.

    Git itself has detailed reference-name rules. These application-level rules
    are intentionally stricter to produce predictable team conventions.
    """

    PREFIXES = {
        "feature",
        "bugfix",
        "hotfix",
        "chore",
        "docs",
        "refactor",
        "test",
    }

    @classmethod
    def validate(cls, branch_name: str) -> tuple[bool, str]:
        if not branch_name:
            return False, "Branch name cannot be empty."

        if branch_name in {"main", "master", "develop"}:
            return True, "Shared branch."

        parts = branch_name.split("/", 1)

        if len(parts) != 2:
            return False, "Use a category prefix such as feature/login."

        prefix, name = parts

        if prefix not in cls.PREFIXES:
            return False, f"Unknown prefix: {prefix}"

        if not name:
            return False, "Branch description cannot be empty."

        if name.startswith("-") or name.endswith("-"):
            return False, "Avoid leading or trailing hyphens."

        if " " in name:
            return False, "Spaces are discouraged in branch names."

        return True, "Valid workflow branch name."


def demonstrate_branch_validation() -> None:
    section("3. Branch Naming")

    examples = [
        "feature/user-login",
        "bugfix/payment-timeout",
        "hotfix/security-patch",
        "feature/",
        "unknown/new-feature",
        "feature/user login",
        "main",
    ]

    for branch in examples:
        valid, message = BranchNameValidator.validate(branch)
        print(f"{branch:30} {'VALID' if valid else 'INVALID'}: {message}")


# =============================================================================
# 5. FEATURE BRANCH WORKFLOW
# =============================================================================

def feature_branch_workflow() -> None:
    section("4. Feature Branch Workflow")

    explain(
        """
        A feature branch workflow keeps a shared branch stable while developers
        work on isolated branches.

        Typical lifecycle:

            1. Start from the current main branch.
            2. Create a short-lived feature branch.
            3. Make small commits.
            4. Push the branch.
            5. Open a pull request.
            6. Run automated checks.
            7. Review the change.
            8. Resolve requested changes.
            9. Integrate into main.
           10. Delete the feature branch.

        Advantages:
            - Isolation between incomplete changes.
            - Natural review boundary.
            - Easier ownership of a change.
            - Compatible with continuous integration.

        Costs:
            - Long-lived branches can drift.
            - Merge conflicts can increase.
            - Integration can be delayed.
            - Developers may mistakenly treat a branch as a long-term
              development environment.

        A feature branch is a mechanism, not a complete delivery strategy.
        The surrounding review, testing, release, and deployment policies matter.
        """
    )

    graph = CommitGraph()
    graph.initialize()
    graph.create_branch("feature/search")

    graph.create_commit(
        "feature/search",
        "Add search input",
        "Developer",
        ["search.py"],
    )

    graph.create_commit(
        "feature/search",
        "Add search validation",
        "Developer",
        ["search.py", "test_search.py"],
    )

    print("\nFeature branch head:", graph.branches["feature/search"].head[:7])
    print("Main remains at:", graph.branches["main"].head[:7])


# =============================================================================
# 6. GITHUB FLOW
# =============================================================================

def github_flow() -> None:
    section("5. GitHub Flow")

    explain(
        """
        GitHub Flow is a lightweight branch-based workflow commonly centered on
        one continuously maintained primary branch.

        A typical flow is:

            main
              |
              +--> feature branch
                        |
                        +--> commits
                        |
                        +--> pull request
                                  |
                                  +--> automated checks
                                  |
                                  +--> review
                                  |
                                  +--> merge
                                            |
                                            +--> deployment

        The important idea is that work is proposed through a pull request and
        the primary branch remains the main integration point.

        GitHub Flow is not identical to "using GitHub". GitHub is a platform,
        while a workflow is a set of development and integration practices.

        Teams can adapt the workflow with branch protection, required reviews,
        status checks, deployment environments, release tags, and rollback
        procedures.
        """
    )

    pull_request = PullRequest(
        number=101,
        source_branch="feature/search",
        target_branch="main",
        title="Implement product search",
    )

    print(f"PR #{pull_request.number}: {pull_request.title}")
    print("Initially mergeable:", pull_request.is_mergeable())

    pull_request.checks_passed = True
    pull_request.approvals = 1

    print("After checks and approval:", pull_request.is_mergeable())


# =============================================================================
# 7. TRUNK-BASED DEVELOPMENT
# =============================================================================

def trunk_based_development() -> None:
    section("6. Trunk-Based Development")

    explain(
        """
        Trunk-based development emphasizes frequent integration into one shared
        trunk, usually called main or trunk.

        Two common forms are:

            A. Direct integration:
               Developers integrate very small changes directly into the trunk,
               subject to the team's controls.

            B. Very short-lived branches:
               Developers create branches for small changes, integrate them
               quickly, and remove them.

        Important supporting practices often include:

            - Strong automated tests.
            - Fast CI feedback.
            - Small changes.
            - Feature flags for incomplete functionality.
            - Frequent synchronization with the trunk.
            - High confidence in deployment automation.

        Trunk-based development reduces the time changes remain divergent from
        the shared integration point. It does not mean "no review", "no tests",
        or "everyone edits production directly".
        """
    )

    graph = CommitGraph()
    graph.initialize()

    for index in range(1, 4):
        graph.create_commit(
            "main",
            f"Small trunk change {index}",
            "Developer",
            [f"src/module_{index}.py"],
        )

    print("Trunk contains", len(graph.commits), "commits in this demonstration.")
    print("Current trunk:", graph.branches["main"].head[:7])


# =============================================================================
# 8. COMPARISON
# =============================================================================

def compare_workflows() -> None:
    section("7. Workflow Comparison")

    comparison = [
        (
            "Primary integration model",
            "Shared main plus feature branches",
            "Main-centered PR workflow",
            "Frequent integration to trunk",
        ),
        (
            "Typical branch lifetime",
            "Short to medium",
            "Short",
            "Very short when branches are used",
        ),
        (
            "Review mechanism",
            "Often pull request",
            "Pull request is central",
            "Can be PR-based or direct, depending on controls",
        ),
        (
            "Integration frequency",
            "Varies by team",
            "Frequent",
            "Very frequent",
        ),
        (
            "Feature flags",
            "Useful",
            "Useful",
            "Often particularly important",
        ),
        (
            "Main risk",
            "Branch divergence",
            "Poorly controlled PR integration",
            "Insufficient automated validation",
        ),
    ]

    widths = [26, 31, 31, 38]
    header = ["Dimension", "Feature Branch", "GitHub Flow", "Trunk-Based"]

    print(
        " | ".join(
            f"{value:<{width}}"
            for value, width in zip(header, widths)
        )
    )
    print("-" * sum(widths) + "-" * 9)

    for row in comparison:
        print(
            " | ".join(
                f"{value:<{width}}"
                for value, width in zip(row, widths)
            )
        )

    explain(
        """
        These descriptions are patterns rather than mandatory definitions.
        Real organizations frequently combine practices. For example, a team
        may use short-lived feature branches, pull requests, mandatory CI,
        feature flags, and continuous deployment at the same time.
        """
    )


# =============================================================================
# 9. MERGE, REBASE, AND SQUASH
# =============================================================================

def integration_strategies() -> None:
    section("8. Merge, Rebase, and Squash")

    explain(
        """
        Merge:
            Combines two histories. A non-fast-forward merge may create a merge
            commit. Merge preserves the fact that two lines of development
            existed.

        Rebase:
            Replays commits onto another base. The resulting commits have new
            identities. Rebase can create a linear-looking history.

        Squash:
            Combines multiple changes into fewer commits, often one logical
            commit during pull-request integration.

        A critical rule:
            Do not rewrite commits that other people are already depending on
            without understanding the consequences. Rebase changes commit
            identities.

        Fast-forward:
            If the target branch is an ancestor of the source branch, the target
            reference can move forward without creating a merge commit.

        Conflict:
            Git cannot automatically determine how competing changes should be
            combined. A human must resolve the conflicting content and then
            continue or abort the operation.
        """
    )

    strategies = [
        IntegrationMethod.MERGE,
        IntegrationMethod.REBASE,
        IntegrationMethod.SQUASH,
    ]

    for strategy in strategies:
        print(f"- {strategy.value}: selected for a different history policy.")


# =============================================================================
# 10. CONFLICT MODEL
# =============================================================================

@dataclass
class FileVersion:
    path: str
    content: str


def detect_simple_conflict(
    base: FileVersion,
    ours: FileVersion,
    theirs: FileVersion,
) -> bool:
    """
    A simplified three-way conflict detector.

    The logic demonstrates the underlying idea:
    if both sides changed the same base content differently, automatic
    combination is unsafe.

    Real Git uses line-oriented merge algorithms and much more sophisticated
    rules.
    """
    if ours.path != theirs.path or base.path != ours.path:
        raise ValueError("All file paths must match.")

    ours_changed = ours.content != base.content
    theirs_changed = theirs.content != base.content

    return ours_changed and theirs_changed and ours.content != theirs.content


def conflict_demo() -> None:
    section("9. Merge Conflict")

    base = FileVersion("config.txt", "timeout=30\n")
    ours = FileVersion("config.txt", "timeout=60\n")
    theirs = FileVersion("config.txt", "timeout=120\n")

    conflict = detect_simple_conflict(base, ours, theirs)

    print("Base:", repr(base.content))
    print("Ours:", repr(ours.content))
    print("Theirs:", repr(theirs.content))
    print("Conflict detected:", conflict)

    explain(
        """
        A conflict should be resolved by understanding the intended behavior,
        not simply by choosing "ours" or "theirs" mechanically.

        After resolving a real Git conflict, the normal process is:

            git status
            inspect conflict markers
            edit the file
            git add <file>
            git merge --continue

        For a rebase, the continuation command is normally:

            git rebase --continue

        An operation can be abandoned with the corresponding abort command when
        the developer decides that continuing is unsafe or unnecessary.
        """
    )


# =============================================================================
# 11. FEATURE FLAGS
# =============================================================================

class FeatureFlagService:
    """
    Minimal feature-flag implementation.

    Feature flags can decouple code integration from feature exposure.
    """

    def __init__(self, flags: Optional[dict[str, bool]] = None) -> None:
        self.flags = flags or {}

    def enabled(self, flag_name: str, default: bool = False) -> bool:
        return self.flags.get(flag_name, default)

    def set(self, flag_name: str, enabled: bool) -> None:
        self.flags[flag_name] = enabled


def feature_flag_demo() -> None:
    section("10. Feature Flags and Incomplete Work")

    flags = FeatureFlagService({"new-search": False})

    if flags.enabled("new-search"):
        print("New search is exposed.")
    else:
        print("New search code may exist, but exposure is disabled.")

    flags.set("new-search", True)

    if flags.enabled("new-search"):
        print("New search is now exposed.")

    explain(
        """
        Feature flags are useful in trunk-oriented development because code can
        be integrated before the corresponding user-visible behavior is enabled.

        Production feature flags require lifecycle management. Old flags should
        be removed, access should be controlled, and flag evaluation should be
        observable when behavior differs by environment or user group.
        """
    )


# =============================================================================
# 12. CI/CD QUALITY GATES
# =============================================================================

@dataclass
class QualityGate:
    tests_passed: bool
    lint_passed: bool
    security_scan_passed: bool
    required_review_count: int
    actual_review_count: int

    def passes(self) -> bool:
        return (
            self.tests_passed
            and self.lint_passed
            and self.security_scan_passed
            and self.actual_review_count >= self.required_review_count
        )


def quality_gate_demo() -> None:
    section("11. Pull Request Quality Gates")

    gate = QualityGate(
        tests_passed=True,
        lint_passed=True,
        security_scan_passed=True,
        required_review_count=2,
        actual_review_count=1,
    )

    print("First evaluation:", gate.passes())

    gate.actual_review_count = 2
    print("After required review:", gate.passes())

    explain(
        """
        A protected main branch can require checks before integration. Typical
        checks include unit tests, integration tests, formatting, static
        analysis, dependency checks, build validation, and security scanning.

        Required checks should be fast enough to provide useful feedback.
        Expensive validation can be separated into stages where appropriate.
        """
    )


# =============================================================================
# 13. GIT COMMAND SIMULATION
# =============================================================================

def simulate_git_session() -> None:
    section("12. End-to-End Git Session Simulation")

    commands = [
        "git clone https://github.com/example/project.git",
        "cd project",
        "git switch main",
        "git pull --ff-only origin main",
        "git switch -c feature/account-validation",
        "git status",
        "git add src/account.py tests/test_account.py",
        'git commit -m "Add account validation"',
        "git push -u origin feature/account-validation",
        "Open pull request from feature/account-validation into main",
        "Run CI checks",
        "Review and update the pull request",
        "Merge according to repository policy",
        "git switch main",
        "git pull --ff-only origin main",
        "git branch -d feature/account-validation",
    ]

    for number, command in enumerate(commands, 1):
        print(f"{number:02}. {command}")

    explain(
        """
        The exact merge command should not be blindly copied into every project.
        Repository settings may enforce merge commits, squash merges, rebases,
        required approvals, signed commits, linear history, or deployment checks.
        """
    )


# =============================================================================
# 14. REBASE SAFETY
# =============================================================================

def rebase_safety_demo() -> None:
    section("13. Rebase Safety")

    explain(
        """
        Suppose a branch contains:

            A -- B -- C       main
                  \
                   D -- E     feature

        Rebasing feature onto C conceptually produces:

            A -- B -- C -- D' -- E'

        D' and E' are new commits. They are not the same objects as D and E.

        This is why a pushed branch may require a force update after rebase.
        When a force update is necessary, a safer form is generally:

            git push --force-with-lease

        "force-with-lease" asks Git to protect against overwriting remote work
        that the local repository does not know about.

        Even with that protection, history rewriting should be governed by team
        policy.
        """
    )


# =============================================================================
# 15. SHORT-LIVED BRANCH POLICY
# =============================================================================

@dataclass
class BranchPolicy:
    maximum_age_days: int
    require_pull_request: bool
    require_ci: bool
    delete_after_merge: bool
    require_linear_history: bool = False

    def validate(self) -> list[str]:
        errors: list[str] = []

        if self.maximum_age_days <= 0:
            errors.append("Maximum branch age must be positive.")

        if not self.require_pull_request:
            errors.append("Pull-request review is disabled by this policy.")

        if not self.require_ci:
            errors.append("CI validation is disabled by this policy.")

        return errors


def policy_demo() -> None:
    section("14. Workflow Policy as Code")

    policy = BranchPolicy(
        maximum_age_days=3,
        require_pull_request=True,
        require_ci=True,
        delete_after_merge=True,
        require_linear_history=False,
    )

    errors = policy.validate()

    print("Policy errors:", errors if errors else "none")
    print("Maximum branch age:", policy.maximum_age_days, "days")
    print("Delete merged branches:", policy.delete_after_merge)


# =============================================================================
# 16. RELEASE AND HOTFIX FLOW
# =============================================================================

def release_and_hotfix_demo() -> None:
    section("15. Release and Hotfix Considerations")

    explain(
        """
        A production incident may require a small, urgent fix. The exact branch
        strategy depends on the organization's release model.

        In a main-centered workflow, a hotfix may be created from the production
        commit or the protected main branch, validated quickly, merged, and
        deployed.

        In a release-branch model, a production fix may need to be applied to
        both the release line and the main development line. Failure to propagate
        the fix can create a regression when the development branch is later
        released.

        Tags are useful immutable references for identifying release points:

            git tag -a v2.4.0 -m "Release 2.4.0"
            git push origin v2.4.0

        The correct release procedure is a repository and organization policy,
        not an intrinsic requirement of GitHub Flow or trunk-based development.
        """
    )


# =============================================================================
# 17. MONOREPO AND MULTI-TEAM CONSIDERATIONS
# =============================================================================

def monorepo_demo() -> None:
    section("16. Large Repository Considerations")

    explain(
        """
        In a monorepo, many applications or services may share one repository.
        A workflow must control ownership and integration without making every
        change depend on every component.

        Useful mechanisms include:

            - CODEOWNERS-style ownership.
            - Path-specific CI.
            - Dependency-aware testing.
            - Small pull requests.
            - Component-level build caching.
            - Clear service boundaries.
            - Automated impact analysis.

        A trunk-based strategy can work in a monorepo, but its success depends
        heavily on reliable automation and disciplined integration practices.
        """
    )

    changed_files = [
        "services/payments/payment.py",
        "services/payments/test_payment.py",
        "docs/payments.md",
    ]

    affected_components = {
        path.split("/")[1]
        for path in changed_files
        if path.startswith("services/")
    }

    print("Changed files:")
    for path in changed_files:
        print(" ", path)

    print("Affected service components:", sorted(affected_components))


# =============================================================================
# 18. PERFORMANCE CONSIDERATIONS
# =============================================================================

def performance_considerations() -> None:
    section("17. Performance and Scaling")

    explain(
        """
        Workflow performance is primarily about feedback latency rather than
        only Git command execution speed.

        Important measurements include:

            - Time from commit to CI result.
            - Pull-request review time.
            - Time a branch remains divergent.
            - Build duration.
            - Test duration.
            - Deployment duration.
            - Mean time to restore service after a failed release.

        Git itself is highly optimized, but repositories can still become
        expensive to operate when they contain very large histories, generated
        artifacts, binary files, or inefficient CI pipelines.

        Git LFS can be appropriate for large binary assets when supported by the
        hosting and organizational setup.

        Shallow clones can reduce initial CI transfer cost, but they remove
        historical information that some tools and release operations require.
        """
    )


# =============================================================================
# 19. SECURITY
# =============================================================================

def security_considerations() -> None:
    section("18. Security Considerations")

    explain(
        """
        Git workflows are security controls as well as collaboration controls.

        Important practices include:

            - Never commit passwords, API keys, private keys, or tokens.
            - Protect the primary branch.
            - Require appropriate review for sensitive changes.
            - Restrict who can bypass branch protections.
            - Use short-lived credentials where possible.
            - Validate dependencies and build artifacts.
            - Review CI workflow changes carefully.
            - Treat pull-request code as potentially untrusted.
            - Avoid exposing secrets to untrusted pull-request execution.
            - Audit privileged repository actions.

        Removing a secret from the latest commit is not necessarily enough.
        If a secret was committed historically, it may remain in repository
        history, caches, forks, or clones. Credential rotation is therefore
        important when a secret has been exposed.

        Git history is durable by design. Security remediation may require
        history rewriting, repository coordination, and credential rotation.
        """
    )


# =============================================================================
# 20. CI SCRIPT GENERATION
# =============================================================================

def generate_ci_commands() -> list[str]:
    """
    Return a technology-neutral CI sequence.

    The commands are examples rather than a GitHub Actions implementation so
    that the teaching script remains dependency-free.
    """
    return [
        "git fetch --prune origin",
        "validate branch policy",
        "install dependencies",
        "run formatter check",
        "run static analysis",
        "run unit tests",
        "run integration tests",
        "run security checks",
        "build artifact",
        "publish test results",
    ]


def ci_pipeline_demo() -> None:
    section("19. CI Pipeline Design")

    for stage, command in enumerate(generate_ci_commands(), 1):
        print(f"{stage:02}. {command}")

    explain(
        """
        A good CI pipeline should make failure actionable. A failed test should
        identify the relevant test and produce enough diagnostic output for a
        developer to reproduce the problem locally.

        Pipelines should fail closed for critical validation. A warning is not
        equivalent to a passing security or correctness requirement.
        """
    )


# =============================================================================
# 21. DORA-STYLE OPERATIONAL THINKING
# =============================================================================

@dataclass
class DeliveryMetrics:
    deployment_frequency: float
    lead_time_hours: float
    change_failure_rate: float
    recovery_time_hours: float

    def validate(self) -> None:
        if self.deployment_frequency < 0:
            raise ValueError("Deployment frequency cannot be negative.")

        if self.lead_time_hours < 0:
            raise ValueError("Lead time cannot be negative.")

        if not 0 <= self.change_failure_rate <= 1:
            raise ValueError("Failure rate must be between 0 and 1.")

        if self.recovery_time_hours < 0:
            raise ValueError("Recovery time cannot be negative.")


def delivery_metrics_demo() -> None:
    section("20. Measuring Workflow Outcomes")

    metrics = DeliveryMetrics(
        deployment_frequency=12,
        lead_time_hours=8,
        change_failure_rate=0.05,
        recovery_time_hours=2,
    )

    metrics.validate()

    print("Deployments per measurement period:", metrics.deployment_frequency)
    print("Median-style example lead time:", metrics.lead_time_hours, "hours")
    print("Example change failure rate:", metrics.change_failure_rate)
    print("Example recovery time:", metrics.recovery_time_hours, "hours")

    explain(
        """
        Metrics should be interpreted with their definitions, collection period,
        population, and measurement method. A workflow should not be judged from
        one metric alone. Speed without reliability can create operational risk,
        while excessive process controls can increase delivery latency.
        """
    )


# =============================================================================
# 22. REAL LOCAL GIT DEMONSTRATION
# =============================================================================

def run_local_git_demo() -> None:
    """
    Create a temporary repository and execute real Git commands.

    This demonstration is isolated inside a temporary directory and therefore
    does not modify the user's normal repository.
    """
    section("21. Real Git Demonstration in a Temporary Repository")

    git_check = subprocess.run(
        ["git", "--version"],
        capture_output=True,
        text=True,
        check=False,
    )

    if git_check.returncode != 0:
        print("Git executable was not found. Skipping real Git demonstration.")
        return

    print("Using:", git_check.stdout.strip())

    with tempfile.TemporaryDirectory(prefix="git-workflow-study-") as directory:
        repo = Path(directory)

        def run_git(*arguments: str) -> str:
            result = subprocess.run(
                ["git", *arguments],
                cwd=repo,
                capture_output=True,
                text=True,
                check=False,
            )

            if result.returncode != 0:
                raise RuntimeError(
                    f"Git command failed: git {' '.join(arguments)}\n"
                    f"{result.stderr.strip()}"
                )

            return result.stdout.strip()

        run_git("init", "-b", "main")
        run_git("config", "user.name", "Workflow Study")
        run_git("config", "user.email", "workflow@example.invalid")

        (repo / "README.md").write_text(
            "# Temporary Workflow Demo\n",
            encoding="utf-8",
        )

        run_git("add", "README.md")
        run_git("commit", "-m", "Initial commit")

        run_git("switch", "-c", "feature/example")

        (repo / "feature.txt").write_text(
            "Feature branch change\n",
            encoding="utf-8",
        )

        run_git("add", "feature.txt")
        run_git("commit", "-m", "Add example feature")

        print("\nFeature branch log:")
        print(run_git("log", "--oneline", "--decorate", "--graph", "--all"))

        run_git("switch", "main")
        run_git("merge", "--no-ff", "feature/example", "-m", "Merge example feature")

        print("\nAfter merge:")
        print(run_git("log", "--oneline", "--decorate", "--graph", "--all"))

        print("\nFinal status:")
        print(run_git("status", "--short") or "clean")


# =============================================================================
# 23. COMMON MISTAKES
# =============================================================================

def common_mistakes() -> None:
    section("22. Common Workflow Mistakes")

    mistakes = {
        "Long-lived feature branches":
            "Increase divergence and conflict risk.",
        "Huge pull requests":
            "Make review and testing harder.",
        "Skipping CI":
            "Allows defects to reach shared branches more easily.",
        "Direct pushes to protected code":
            "Bypass review and automated controls.",
        "Rebasing shared history":
            "Can invalidate other developers' commit references.",
        "Committing secrets":
            "Can expose credentials through durable repository history.",
        "Keeping stale branches":
            "Creates clutter and makes active work harder to identify.",
        "No rollback plan":
            "Turns release failures into longer incidents.",
        "Feature flags without cleanup":
            "Creates configuration debt and conditional complexity.",
        "Using Git commands mechanically":
            "Can cause data loss when repository state is misunderstood.",
    }

    for mistake, consequence in mistakes.items():
        print(f"- {mistake}: {consequence}")


# =============================================================================
# 24. DEBUGGING WORKFLOW STATE
# =============================================================================

def debugging_checklist() -> None:
    section("23. Debugging Git Workflow Problems")

    commands = [
        ("git status", "Understand current branch and unresolved operations."),
        ("git branch --show-current", "Confirm the current branch."),
        ("git log --oneline --decorate --graph --all", "Inspect recent history."),
        ("git remote -v", "Inspect configured remotes."),
        ("git fetch --prune", "Refresh remote references and remove stale ones."),
        ("git diff", "Inspect unstaged changes."),
        ("git diff --staged", "Inspect staged changes."),
        ("git reflog", "Inspect local reference movement and recovery points."),
    ]

    for command, purpose in commands:
        print(f"{command:48} {purpose}")

    explain(
        """
        Reflog is particularly important for recovery because branch references
        can move while objects remain temporarily reachable. It can help locate
        commits after an accidental reset or rebase.

        Recovery is easier when developers stop changing repository state and
        first inspect what happened.
        """
    )


# =============================================================================
# 25. ADVANCED WORKFLOW DESIGN
# =============================================================================

def advanced_design() -> None:
    section("24. Advanced Workflow Design")

    explain(
        """
        A production-grade workflow can be modeled as a control system:

            Developer change
                  |
                  v
            Local validation
                  |
                  v
            Pull request / integration
                  |
                  v
            Automated quality gates
                  |
                  v
            Human review where required
                  |
                  v
            Protected integration branch
                  |
                  v
            Build artifact
                  |
                  v
            Deployment environment
                  |
                  v
            Monitoring and verification
                  |
                  v
            Roll forward or rollback

        Key design questions:

            1. How quickly must changes integrate?
            2. Which branches can receive direct pushes?
            3. Which changes require review?
            4. Which checks are mandatory?
            5. How are incomplete features hidden?
            6. How are releases identified?
            7. How is a bad release reversed?
            8. How are secrets protected?
            9. How are database migrations coordinated?
           10. How are emergency changes handled?
           11. How are ownership boundaries enforced?
           12. How is workflow effectiveness measured?

        The workflow should fit the architecture. A regulated environment may
        require controls that a small internal project does not. A high-frequency
        deployment environment may require much faster automation than a project
        with infrequent releases.
        """
    )


# =============================================================================
# 26. DATABASE MIGRATION CONSIDERATIONS
# =============================================================================

def database_migration_demo() -> None:
    section("25. Database Migration and Git Workflows")

    explain(
        """
        Application code and database schema changes can have different
        deployment lifecycles.

        A safer compatibility-oriented migration often follows:

            1. Add new schema capability.
            2. Deploy code that can work with both old and new forms.
            3. Migrate data if required.
            4. Switch behavior.
            5. Remove obsolete schema later.

        This is sometimes called an expand-and-contract pattern.

        A Git branch strategy cannot by itself make a database migration safe.
        The application, schema, deployment order, rollback strategy, and data
        compatibility must be considered together.
        """
    )


# =============================================================================
# 27. AUTOMATED WORKFLOW DECISION MODEL
# =============================================================================

@dataclass
class ProjectCharacteristics:
    deployment_frequency: str
    team_size: str
    compliance_level: str
    ci_maturity: str
    release_cadence: str

    def validate(self) -> None:
        allowed = {
            "deployment_frequency": {"low", "medium", "high"},
            "team_size": {"small", "medium", "large"},
            "compliance_level": {"low", "medium", "high"},
            "ci_maturity": {"low", "medium", "high"},
            "release_cadence": {"manual", "scheduled", "continuous"},
        }

        values = {
            "deployment_frequency": self.deployment_frequency,
            "team_size": self.team_size,
            "compliance_level": self.compliance_level,
            "ci_maturity": self.ci_maturity,
            "release_cadence": self.release_cadence,
        }

        for field_name, value in values.items():
            if value not in allowed[field_name]:
                raise ValueError(
                    f"Invalid {field_name}: {value}. "
                    f"Expected one of {sorted(allowed[field_name])}."
                )


def workflow_design_factors_demo() -> None:
    section("26. Choosing a Workflow: Decision Factors")

    characteristics = ProjectCharacteristics(
        deployment_frequency="high",
        team_size="medium",
        compliance_level="medium",
        ci_maturity="high",
        release_cadence="continuous",
    )

    characteristics.validate()

    for field_name, value in vars(characteristics).items():
        print(f"{field_name:24}: {value}")

    explain(
        """
        There is no universal workflow selection formula. The relevant factors
        are descriptive inputs for engineering design.

        High deployment frequency generally increases the value of short-lived
        divergence and fast automated validation. Strong compliance requirements
        may introduce additional approvals, audit records, separation of duties,
        or release controls. Low CI maturity can make highly frequent
        integration difficult until the validation system becomes reliable.

        These are engineering relationships, not absolute rules.
        """
    )


# =============================================================================
# 28. TESTING
# =============================================================================

class WorkflowTests(unittest.TestCase):
    def test_branch_name(self) -> None:
        valid, _ = BranchNameValidator.validate("feature/login")
        self.assertTrue(valid)

    def test_invalid_branch_name(self) -> None:
        valid, _ = BranchNameValidator.validate("feature/")
        self.assertFalse(valid)

    def test_pull_request_requires_approval_and_ci(self) -> None:
        pull_request = PullRequest(
            number=1,
            source_branch="feature/a",
            target_branch="main",
            title="Test",
            approvals=1,
            checks_passed=False,
        )

        self.assertFalse(pull_request.is_mergeable())

        pull_request.checks_passed = True
        self.assertTrue(pull_request.is_mergeable())

    def test_conflict_detection(self) -> None:
        base = FileVersion("file.txt", "A")
        ours = FileVersion("file.txt", "B")
        theirs = FileVersion("file.txt", "C")

        self.assertTrue(detect_simple_conflict(base, ours, theirs))

    def test_no_conflict_when_only_one_side_changes(self) -> None:
        base = FileVersion("file.txt", "A")
        ours = FileVersion("file.txt", "B")
        theirs = FileVersion("file.txt", "A")

        self.assertFalse(detect_simple_conflict(base, ours, theirs))

    def test_policy(self) -> None:
        policy = BranchPolicy(
            maximum_age_days=3,
            require_pull_request=True,
            require_ci=True,
            delete_after_merge=True,
        )

        self.assertEqual(policy.validate(), [])


def run_tests() -> None:
    section("27. Automated Tests")

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(WorkflowTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    print(
        f"\nTests run: {result.testsRun}; "
        f"failures: {len(result.failures)}; "
        f"errors: {len(result.errors)}"
    )


# =============================================================================
# 29. STUDY EXERCISES
# =============================================================================

def study_exercises() -> None:
    section("28. Practical Exercises")

    exercises = [
        "Create a feature branch from an updated main branch.",
        "Make two logically separate commits.",
        "Open a pull request and identify its required quality gates.",
        "Simulate a merge conflict and explain the base, ours, and theirs.",
        "Compare a merge-based history with a rebase-based history.",
        "Introduce a feature flag for incomplete functionality.",
        "Design a short-lived branch policy.",
        "Identify which CI checks should block main integration.",
        "Design a hotfix procedure for a production defect.",
        "Explain how a database migration affects deployment ordering.",
        "Use git reflog to reason about recovery after a mistaken reset.",
        "Measure branch lifetime and CI feedback time in a real project.",
    ]

    for index, exercise in enumerate(exercises, 1):
        print(f"{index:02}. {exercise}")


# =============================================================================
# 30. MAIN PROGRAM
# =============================================================================

def run_course() -> None:
    beginner_basics()
    demonstrate_commit_graph()
    demonstrate_branch_validation()
    feature_branch_workflow()
    github_flow()
    trunk_based_development()
    compare_workflows()
    integration_strategies()
    conflict_demo()
    feature_flag_demo()
    quality_gate_demo()
    simulate_git_session()
    rebase_safety_demo()
    policy_demo()
    release_and_hotfix_demo()
    monorepo_demo()
    performance_considerations()
    security_considerations()
    ci_pipeline_demo()
    delivery_metrics_demo()
    common_mistakes()
    debugging_checklist()
    advanced_design()
    database_migration_demo()
    workflow_design_factors_demo()
    run_tests()
    study_exercises()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Comprehensive Git workflow study and demonstration."
    )
    parser.add_argument(
        "--real-git-demo",
        action="store_true",
        help="Run an isolated real Git demonstration in a temporary directory.",
    )
    parser.add_argument(
        "--tests-only",
        action="store_true",
        help="Run only the built-in tests.",
    )

    args = parser.parse_args()

    if args.tests_only:
        run_tests()
        return

    run_course()

    if args.real_git_demo:
        run_local_git_demo()


if __name__ == "__main__":
    main()
