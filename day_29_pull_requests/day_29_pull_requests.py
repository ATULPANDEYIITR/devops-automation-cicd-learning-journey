"""
Pull Requests, Code Review, Approvals, and Branch Protection
==============================================================

A standalone study program that teaches the concepts behind collaborative
Git workflows centered on pull requests, code review, approvals, and protected
branches.

The examples are intentionally modeled as a small repository workflow so that
the concepts can be executed rather than only described.

The script progresses through:
1. Git and repository vocabulary
2. Branches and pull requests
3. Diffs and review comments
4. Review states and approval rules
5. Required reviewers
6. Branch protection policy
7. Status checks
8. Mergeability
9. Draft pull requests
10. Review dismissal and stale approvals
11. Security-oriented branch policies
12. A complete pull-request simulation
13. Automated tests for the policy engine
14. Performance and design observations

No third-party packages are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Set, Tuple
import difflib
import hashlib
import re
import unittest


# ============================================================================
# 1. FUNDAMENTAL VOCABULARY
# ============================================================================

def explain_fundamentals() -> None:
    """
    Print foundational terminology.

    These definitions are deliberately kept close to the executable examples
    later in the file so the program can also serve as a study reference.
    """
    print("\n" + "=" * 78)
    print("1. FUNDAMENTAL PULL-REQUEST CONCEPTS")
    print("=" * 78)

    concepts = {
        "Repository": (
            "A version-controlled project containing files and Git history."
        ),
        "Branch": (
            "A movable Git reference used to develop a line of work separately "
            "from another branch."
        ),
        "Base branch": (
            "The branch that receives the proposed changes, commonly main."
        ),
        "Head branch": (
            "The branch containing the proposed changes."
        ),
        "Pull request": (
            "A collaboration object proposing that changes from one branch "
            "be integrated into another branch."
        ),
        "Commit": (
            "A recorded snapshot of repository changes identified by a hash."
        ),
        "Diff": (
            "A representation of differences between two versions of files."
        ),
        "Code review": (
            "A structured examination of proposed changes before integration."
        ),
        "Approval": (
            "A review state indicating that a reviewer has approved the "
            "current proposed changes under the repository's rules."
        ),
        "Status check": (
            "An automated or externally reported result associated with a "
            "commit or pull request."
        ),
        "Branch protection": (
            "Rules that restrict how changes may enter a protected branch."
        ),
        "Merge": (
            "The operation that integrates the proposed changes into the "
            "target branch according to the selected merge strategy."
        ),
    }

    for term, definition in concepts.items():
        print(f"{term:20} {definition}")


# ============================================================================
# 2. BASIC REPOSITORY MODEL
# ============================================================================

@dataclass(frozen=True)
class Commit:
    """A simplified immutable representation of a Git commit."""

    commit_id: str
    author: str
    message: str
    files: Dict[str, str]

    @staticmethod
    def create(author: str, message: str, files: Dict[str, str]) -> "Commit":
        """
        Create a deterministic educational commit identifier.

        Real Git object IDs are computed from Git's object model. This example
        uses SHA-1 over a simplified representation only to make the simulation
        reproducible and easy to understand.
        """
        normalized = "\n".join(
            f"{name}\n{files[name]}" for name in sorted(files)
        )
        payload = f"{author}\n{message}\n{normalized}".encode("utf-8")
        commit_id = hashlib.sha1(payload).hexdigest()
        return Commit(commit_id, author, message, dict(files))


@dataclass
class Branch:
    """A branch points to a particular commit in this simplified model."""

    name: str
    head: Commit


@dataclass
class Repository:
    """A minimal repository model containing branches and commits."""

    name: str
    branches: Dict[str, Branch] = field(default_factory=dict)

    def create_branch(self, name: str, source_branch: str) -> Branch:
        if name in self.branches:
            raise ValueError(f"Branch already exists: {name}")
        if source_branch not in self.branches:
            raise ValueError(f"Unknown source branch: {source_branch}")

        branch = Branch(name, self.branches[source_branch].head)
        self.branches[name] = branch
        return branch

    def update_branch(self, name: str, commit: Commit) -> None:
        if name not in self.branches:
            raise ValueError(f"Unknown branch: {name}")
        self.branches[name].head = commit


def create_demo_repository() -> Repository:
    """Build a small repository used throughout the examples."""
    initial_files = {
        "README.md": "# Payment Service\n",
        "payment.py": (
            "def calculate_total(amount, tax):\n"
            "    return amount + tax\n"
        ),
        "tests/test_payment.py": (
            "def test_calculate_total():\n"
            "    assert calculate_total(100, 10) == 110\n"
        ),
    }

    initial_commit = Commit.create(
        author="system",
        message="Initial payment service",
        files=initial_files,
    )

    return Repository(
        name="payment-service",
        branches={
            "main": Branch("main", initial_commit),
        },
    )


# ============================================================================
# 3. DIFF GENERATION
# ============================================================================

def generate_diff(base: Commit, head: Commit) -> str:
    """
    Produce a unified diff between two commits.

    This models the information reviewers inspect when evaluating a PR.
    """
    output: List[str] = []
    all_files = sorted(set(base.files) | set(head.files))

    for filename in all_files:
        old = base.files.get(filename, "").splitlines(keepends=True)
        new = head.files.get(filename, "").splitlines(keepends=True)

        if old == new:
            continue

        output.extend(
            difflib.unified_diff(
                old,
                new,
                fromfile=f"a/{filename}",
                tofile=f"b/{filename}",
            )
        )

    return "".join(output)


def demonstrate_diff() -> None:
    print("\n" + "=" * 78)
    print("2. DIFFS: WHAT A REVIEWER ACTUALLY INSPECTS")
    print("=" * 78)

    repository = create_demo_repository()

    changed_files = dict(repository.branches["main"].head.files)
    changed_files["payment.py"] = (
        "def calculate_total(amount, tax):\n"
        "    if amount < 0 or tax < 0:\n"
        "        raise ValueError('amount and tax must be non-negative')\n"
        "    return amount + tax\n"
    )

    feature_commit = Commit.create(
        author="alice",
        message="Validate payment amounts",
        files=changed_files,
    )

    print(generate_diff(repository.branches["main"].head, feature_commit))


# ============================================================================
# 4. REVIEW STATES
# ============================================================================

class ReviewState(Enum):
    """Common logical review states."""

    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    COMMENTED = "commented"
    DISMISSED = "dismissed"


@dataclass
class Review:
    reviewer: str
    state: ReviewState
    commit_id: str
    comment: str = ""


def review_is_current(review: Review, pull_request_head: str) -> bool:
    """
    An approval tied to an older commit may become stale depending on policy.

    This distinction is important: approval is not automatically equivalent
    to approval of every future version of a pull request.
    """
    return review.commit_id == pull_request_head


# ============================================================================
# 5. REVIEW COMMENTS
# ============================================================================

@dataclass
class ReviewComment:
    reviewer: str
    filename: str
    line_number: int
    body: str
    resolved: bool = False


def demonstrate_review_comments() -> None:
    print("\n" + "=" * 78)
    print("3. REVIEW COMMENTS AND RESOLUTION")
    print("=" * 78)

    comments = [
        ReviewComment(
            reviewer="bob",
            filename="payment.py",
            line_number=3,
            body="Please use a domain-specific exception or document why ValueError is sufficient.",
        ),
        ReviewComment(
            reviewer="carol",
            filename="tests/test_payment.py",
            line_number=2,
            body="Please add a negative-input test.",
        ),
    ]

    for comment in comments:
        status = "resolved" if comment.resolved else "open"
        print(
            f"{comment.filename}:{comment.line_number} "
            f"[{status}] {comment.reviewer}: {comment.body}"
        )

    comments[0].resolved = True
    print("\nAfter resolving the first comment:")
    for comment in comments:
        status = "resolved" if comment.resolved else "open"
        print(f"{comment.filename}:{comment.line_number} [{status}]")


# ============================================================================
# 6. BRANCH PROTECTION POLICY
# ============================================================================

@dataclass(frozen=True)
class BranchProtectionPolicy:
    """
    A simplified branch-protection configuration.

    Real repository platforms expose more controls. The purpose here is to
    model the core decision logic in a transparent, testable way.
    """

    protected_branch: str = "main"
    required_approvals: int = 1
    require_code_owner_review: bool = False
    required_status_checks: Tuple[str, ...] = (
        "unit-tests",
        "lint",
    )
    dismiss_stale_approvals: bool = True
    require_conversation_resolution: bool = True
    require_up_to_date_branch: bool = True
    allow_force_push: bool = False
    allow_deletions: bool = False
    require_signed_commits: bool = False
    require_linear_history: bool = False
    allow_direct_push: bool = False


@dataclass
class StatusCheck:
    name: str
    passed: bool
    commit_id: str


@dataclass
class PullRequest:
    number: int
    title: str
    author: str
    base_branch: str
    head_branch: str
    base_commit_id: str
    head_commit: Commit
    draft: bool = False
    merged: bool = False
    closed: bool = False
    reviews: List[Review] = field(default_factory=list)
    comments: List[ReviewComment] = field(default_factory=list)
    status_checks: List[StatusCheck] = field(default_factory=list)
    code_owners_approved: Set[str] = field(default_factory=set)
    branch_is_up_to_date: bool = True

    @property
    def head_commit_id(self) -> str:
        return self.head_commit.commit_id


@dataclass
class PolicyResult:
    allowed: bool
    reasons: List[str]

    def __str__(self) -> str:
        if self.allowed:
            return "MERGE ALLOWED"
        return "MERGE BLOCKED:\n- " + "\n- ".join(self.reasons)


# ============================================================================
# 7. POLICY ENGINE
# ============================================================================

class PullRequestPolicyEngine:
    """
    Evaluate whether a pull request satisfies the configured merge policy.

    Separating policy evaluation from the PR object makes the design easier
    to test and extend.
    """

    def __init__(self, policy: BranchProtectionPolicy):
        self.policy = policy

    def _current_approvals(self, pull_request: PullRequest) -> Set[str]:
        """
        Return reviewers whose approvals are current for the PR's HEAD.

        A reviewer cannot satisfy the approval requirement with an approval
        that belongs to a stale commit when stale approvals are dismissed.
        """
        approved_reviewers: Set[str] = set()

        for review in pull_request.reviews:
            if review.state != ReviewState.APPROVED:
                continue

            if self.policy.dismiss_stale_approvals:
                if not review_is_current(review, pull_request.head_commit_id):
                    continue

            approved_reviewers.add(review.reviewer)

        return approved_reviewers

    def _has_current_change_request(self, pull_request: PullRequest) -> bool:
        for review in pull_request.reviews:
            if review.state != ReviewState.CHANGES_REQUESTED:
                continue

            if self.policy.dismiss_stale_approvals:
                if not review_is_current(review, pull_request.head_commit_id):
                    continue

            return True

        return False

    def _required_checks_passed(self, pull_request: PullRequest) -> bool:
        checks_for_head = {
            check.name: check.passed
            for check in pull_request.status_checks
            if check.commit_id == pull_request.head_commit_id
        }

        return all(
            checks_for_head.get(required_check, False)
            for required_check in self.policy.required_status_checks
        )

    def evaluate(
        self,
        pull_request: PullRequest,
        current_base_commit_id: str,
    ) -> PolicyResult:
        reasons: List[str] = []

        if pull_request.merged:
            reasons.append("Pull request is already merged.")

        if pull_request.closed:
            reasons.append("Pull request is closed.")

        if pull_request.draft:
            reasons.append("Draft pull requests cannot be merged under this policy.")

        if pull_request.base_branch != self.policy.protected_branch:
            reasons.append(
                f"Expected protected branch "
                f"{self.policy.protected_branch!r}, "
                f"received {pull_request.base_branch!r}."
            )

        if self.policy.require_up_to_date_branch:
            if not pull_request.branch_is_up_to_date:
                reasons.append("Head branch must be up to date with the base branch.")

            if pull_request.base_commit_id != current_base_commit_id:
                reasons.append("Pull request was opened against an outdated base commit.")

        if self._has_current_change_request(pull_request):
            reasons.append("A current review requests changes.")

        approvals = self._current_approvals(pull_request)

        # A pull request author is not counted as an independent reviewer.
        independent_approvals = {
            reviewer
            for reviewer in approvals
            if reviewer != pull_request.author
        }

        if len(independent_approvals) < self.policy.required_approvals:
            reasons.append(
                f"At least {self.policy.required_approvals} "
                f"independent current approval(s) are required; "
                f"found {len(independent_approvals)}."
            )

        if self.policy.require_code_owner_review:
            if not pull_request.code_owners_approved:
                reasons.append("At least one code-owner approval is required.")

        if self.policy.require_conversation_resolution:
            unresolved = [
                comment
                for comment in pull_request.comments
                if not comment.resolved
            ]
            if unresolved:
                reasons.append(
                    f"{len(unresolved)} review conversation(s) remain unresolved."
                )

        if not self._required_checks_passed(pull_request):
            reasons.append("One or more required status checks have not passed.")

        return PolicyResult(
            allowed=not reasons,
            reasons=reasons,
        )


# ============================================================================
# 8. MERGE STRATEGIES
# ============================================================================

class MergeStrategy(Enum):
    MERGE_COMMIT = "merge commit"
    SQUASH = "squash"
    REBASE = "rebase"


def describe_merge_strategies() -> None:
    print("\n" + "=" * 78)
    print("4. MERGE STRATEGIES")
    print("=" * 78)

    descriptions = {
        MergeStrategy.MERGE_COMMIT: (
            "Preserves the branch topology and creates a merge commit."
        ),
        MergeStrategy.SQUASH: (
            "Combines the PR's changes into one commit before integration."
        ),
        MergeStrategy.REBASE: (
            "Replays commits onto a new base, producing a linearized history "
            "when combined with a fast-forward style integration."
        ),
    }

    for strategy, description in descriptions.items():
        print(f"{strategy.value:15} {description}")


# ============================================================================
# 9. CODE OWNERSHIP
# ============================================================================

@dataclass(frozen=True)
class CodeOwnerRule:
    pattern: str
    owners: Tuple[str, ...]


def path_matches_pattern(path: str, pattern: str) -> bool:
    """
    Implement a small subset of CODEOWNERS-like matching for education.

    This is not intended to reproduce every platform-specific CODEOWNERS
    pattern rule.
    """
    if pattern == "*":
        return True

    if pattern.endswith("/"):
        return path.startswith(pattern)

    if pattern.startswith("*."):
        return path.endswith(pattern[1:])

    return path == pattern


def required_code_owners(
    changed_paths: Iterable[str],
    rules: Iterable[CodeOwnerRule],
) -> Set[str]:
    owners: Set[str] = set()

    for path in changed_paths:
        for rule in rules:
            if path_matches_pattern(path, rule.pattern):
                owners.update(rule.owners)

    return owners


# ============================================================================
# 10. SECURITY-ORIENTED REVIEW RULES
# ============================================================================

@dataclass(frozen=True)
class SecurityFinding:
    filename: str
    line_number: int
    severity: str
    message: str


SECRET_PATTERNS = (
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"password\s*=\s*['\"][^'\"]+['\"]", re.IGNORECASE),
)


def scan_for_obvious_secrets(files: Dict[str, str]) -> List[SecurityFinding]:
    """
    A tiny educational secret scanner.

    Production secret detection should use mature tooling and should not rely
    on a few regular expressions.
    """
    findings: List[SecurityFinding] = []

    for filename, content in files.items():
        for line_number, line in enumerate(content.splitlines(), start=1):
            for pattern in SECRET_PATTERNS:
                if pattern.search(line):
                    findings.append(
                        SecurityFinding(
                            filename=filename,
                            line_number=line_number,
                            severity="high",
                            message="Potential credential or private key detected.",
                        )
                    )

    return findings


# ============================================================================
# 11. STATUS CHECK SIMULATION
# ============================================================================

def run_unit_tests(commit: Commit) -> StatusCheck:
    """
    Simulate a CI unit-test check.

    The check fails if a deliberately broken marker appears in the source.
    """
    broken_marker = "INTENTIONALLY_BROKEN"
    passed = not any(
        broken_marker in content
        for content in commit.files.values()
    )

    return StatusCheck(
        name="unit-tests",
        passed=passed,
        commit_id=commit.commit_id,
    )


def run_linter(commit: Commit) -> StatusCheck:
    """
    Simulate a simple lint check.

    This is intentionally small. A real CI pipeline might invoke Ruff,
    ESLint, clang-tidy, compiler warnings, formatting tools, and other
    project-specific checks.
    """
    passed = True

    for filename, content in commit.files.items():
        if filename.endswith(".py"):
            if "\t" in content:
                passed = False

    return StatusCheck(
        name="lint",
        passed=passed,
        commit_id=commit.commit_id,
    )


# ============================================================================
# 12. COMPLETE PULL-REQUEST WORKFLOW
# ============================================================================

def build_feature_commit(
    base_commit: Commit,
    author: str,
    secure: bool = True,
    broken: bool = False,
) -> Commit:
    """
    Build a realistic feature commit from the current base.

    The 'secure' and 'broken' flags allow the workflow simulation to exercise
    both successful and failed policy states.
    """
    files = dict(base_commit.files)

    if secure:
        implementation = (
            "def calculate_total(amount, tax):\n"
            "    if amount < 0 or tax < 0:\n"
            "        raise ValueError('amount and tax must be non-negative')\n"
            "    return amount + tax\n"
        )
    else:
        implementation = (
            "API_PASSWORD = 'hard-coded-secret'\n\n"
            "def calculate_total(amount, tax):\n"
            "    return amount + tax\n"
        )

    if broken:
        implementation += "\nINTENTIONALLY_BROKEN = True\n"

    files["payment.py"] = implementation

    files["tests/test_payment.py"] = (
        "def test_calculate_total():\n"
        "    assert calculate_total(100, 10) == 110\n\n"
        "def test_reject_negative_amount():\n"
        "    try:\n"
        "        calculate_total(-1, 10)\n"
        "    except ValueError:\n"
        "        pass\n"
        "    else:\n"
        "        raise AssertionError('negative amount was accepted')\n"
    )

    return Commit.create(
        author=author,
        message="Validate payment totals",
        files=files,
    )


def create_pull_request(
    repository: Repository,
    number: int,
    author: str,
) -> PullRequest:
    base = repository.branches["main"].head
    feature = repository.create_branch("feature/payment-validation", "main")

    feature_commit = build_feature_commit(base, author)

    repository.update_branch(feature.name, feature_commit)

    return PullRequest(
        number=number,
        title="Validate payment totals",
        author=author,
        base_branch="main",
        head_branch=feature.name,
        base_commit_id=base.commit_id,
        head_commit=feature_commit,
    )


def run_complete_workflow() -> None:
    print("\n" + "=" * 78)
    print("5. COMPLETE PULL-REQUEST WORKFLOW")
    print("=" * 78)

    repository = create_demo_repository()

    pull_request = create_pull_request(
        repository=repository,
        number=42,
        author="alice",
    )

    print(f"PR #{pull_request.number}: {pull_request.title}")
    print(f"Base: {pull_request.base_branch}")
    print(f"Head: {pull_request.head_branch}")
    print(f"Head commit: {pull_request.head_commit_id[:12]}")

    print("\nChanged files:")
    diff = generate_diff(
        repository.branches["main"].head,
        pull_request.head_commit,
    )
    print(diff)

    # Reviewer Bob performs a review of the exact current commit.
    pull_request.reviews.append(
        Review(
            reviewer="bob",
            state=ReviewState.APPROVED,
            commit_id=pull_request.head_commit_id,
            comment="Implementation and tests look correct.",
        )
    )

    # Resolve all review conversations.
    pull_request.comments.append(
        ReviewComment(
            reviewer="bob",
            filename="payment.py",
            line_number=2,
            body="Please confirm that negative tax values are rejected.",
            resolved=True,
        )
    )

    pull_request.status_checks.extend(
        [
            run_unit_tests(pull_request.head_commit),
            run_linter(pull_request.head_commit),
        ]
    )

    policy = BranchProtectionPolicy(
        protected_branch="main",
        required_approvals=1,
        required_status_checks=("unit-tests", "lint"),
        dismiss_stale_approvals=True,
        require_conversation_resolution=True,
        require_up_to_date_branch=True,
        allow_force_push=False,
        allow_deletions=False,
        require_signed_commits=False,
        require_linear_history=False,
        allow_direct_push=False,
    )

    engine = PullRequestPolicyEngine(policy)

    result = engine.evaluate(
        pull_request,
        current_base_commit_id=repository.branches["main"].head.commit_id,
    )

    print("\nPolicy evaluation:")
    print(result)

    if result.allowed:
        pull_request.merged = True
        repository.update_branch("main", pull_request.head_commit)
        print("\nPR merged. The protected branch now points to the approved commit.")


# ============================================================================
# 13. STALE APPROVAL SCENARIO
# ============================================================================

def demonstrate_stale_approval() -> None:
    print("\n" + "=" * 78)
    print("6. STALE APPROVALS")
    print("=" * 78)

    repository = create_demo_repository()
    pull_request = create_pull_request(repository, 43, "alice")

    original_head = pull_request.head_commit_id

    pull_request.reviews.append(
        Review(
            reviewer="bob",
            state=ReviewState.APPROVED,
            commit_id=original_head,
        )
    )

    print(f"Bob approved commit {original_head[:12]}.")

    updated_files = dict(pull_request.head_commit.files)
    updated_files["payment.py"] += (
        "\n\ndef format_receipt(total):\n"
        "    return f'Total: {total:.2f}'\n"
    )

    new_commit = Commit.create(
        author="alice",
        message="Address review follow-up",
        files=updated_files,
    )

    pull_request.head_commit = new_commit

    print(f"New commit added: {new_commit.commit_id[:12]}")

    policy = BranchProtectionPolicy(
        required_approvals=1,
        dismiss_stale_approvals=True,
        required_status_checks=(),
        require_conversation_resolution=False,
        require_up_to_date_branch=False,
    )

    engine = PullRequestPolicyEngine(policy)
    result = engine.evaluate(
        pull_request,
        current_base_commit_id=pull_request.base_commit_id,
    )

    print(result)
    print(
        "\nThe important distinction is that the approval belongs to the "
        "older commit, not necessarily to the modified code."
    )


# ============================================================================
# 14. DRAFT PULL REQUESTS
# ============================================================================

def demonstrate_draft_pr() -> None:
    print("\n" + "=" * 78)
    print("7. DRAFT PULL REQUESTS")
    print("=" * 78)

    repository = create_demo_repository()
    pull_request = create_pull_request(repository, 44, "alice")
    pull_request.draft = True

    pull_request.reviews.append(
        Review(
            reviewer="bob",
            state=ReviewState.APPROVED,
            commit_id=pull_request.head_commit_id,
        )
    )

    policy = BranchProtectionPolicy(
        required_approvals=1,
        required_status_checks=(),
        require_conversation_resolution=False,
        require_up_to_date_branch=False,
    )

    result = PullRequestPolicyEngine(policy).evaluate(
        pull_request,
        repository.branches["main"].head.commit_id,
    )

    print(result)
    print(
        "\nA draft PR is useful for sharing work early without presenting it "
        "as ready for integration."
    )


# ============================================================================
# 15. DIRECT PUSH VS PULL REQUEST
# ============================================================================

def demonstrate_direct_push_policy() -> None:
    print("\n" + "=" * 78)
    print("8. DIRECT PUSH AND PROTECTED BRANCHES")
    print("=" * 78)

    policy = BranchProtectionPolicy(
        allow_direct_push=False,
        allow_force_push=False,
        allow_deletions=False,
    )

    print(f"Protected branch: {policy.protected_branch}")
    print(f"Direct pushes allowed: {policy.allow_direct_push}")
    print(f"Force pushes allowed: {policy.allow_force_push}")
    print(f"Branch deletion allowed: {policy.allow_deletions}")

    print(
        "\nThe purpose of protection is to make the normal path for important "
        "changes pass through controlled checks and review."
    )


# ============================================================================
# 16. CODEOWNERS EXAMPLE
# ============================================================================

def demonstrate_code_owners() -> None:
    print("\n" + "=" * 78)
    print("9. CODE OWNERSHIP")
    print("=" * 78)

    rules = [
        CodeOwnerRule(
            pattern="payment.py",
            owners=("alice", "security-team"),
        ),
        CodeOwnerRule(
            pattern="*.md",
            owners=("documentation-team",),
        ),
    ]

    changed_paths = [
        "payment.py",
        "README.md",
    ]

    owners = required_code_owners(changed_paths, rules)

    print("Changed paths:")
    for path in changed_paths:
        print(f"  - {path}")

    print("\nPotential required owners:")
    for owner in sorted(owners):
        print(f"  - {owner}")


# ============================================================================
# 17. SECURITY SCANNING
# ============================================================================

def demonstrate_security_scan() -> None:
    print("\n" + "=" * 78)
    print("10. SECURITY CHECK BEFORE MERGE")
    print("=" * 78)

    files = {
        "payment.py": (
            "def calculate_total(amount, tax):\n"
            "    return amount + tax\n"
        ),
        "config.py": (
            "API_PASSWORD = 'do-not-commit-secrets'\n"
        ),
    }

    findings = scan_for_obvious_secrets(files)

    for finding in findings:
        print(
            f"{finding.severity.upper()} "
            f"{finding.filename}:{finding.line_number} "
            f"{finding.message}"
        )

    if not findings:
        print("No obvious secrets detected.")

    print(
        "\nImportant limitation: a regular-expression scanner can produce "
        "false positives and false negatives. Secret management should use "
        "dedicated tooling, credential rotation, and secure storage."
    )


# ============================================================================
# 18. POLICY FAILURE MATRIX
# ============================================================================

def demonstrate_policy_failures() -> None:
    print("\n" + "=" * 78)
    print("11. COMMON REASONS A PR IS BLOCKED")
    print("=" * 78)

    repository = create_demo_repository()
    pull_request = create_pull_request(repository, 45, "alice")

    policy = BranchProtectionPolicy(
        required_approvals=2,
        required_status_checks=("unit-tests", "lint"),
        dismiss_stale_approvals=True,
        require_conversation_resolution=True,
        require_up_to_date_branch=True,
    )

    result = PullRequestPolicyEngine(policy).evaluate(
        pull_request,
        repository.branches["main"].head.commit_id,
    )

    print(result)

    print("\nTypical blocking conditions include:")
    conditions = [
        "No required approval",
        "Too few independent approvals",
        "Changes requested",
        "Stale approvals",
        "Failed required checks",
        "Missing required check",
        "Unresolved review conversations",
        "Out-of-date branch",
        "Required code-owner approval missing",
        "Draft status",
        "Protected branch policy violation",
    ]

    for condition in conditions:
        print(f"  - {condition}")


# ============================================================================
# 19. ADVANCED REVIEW DESIGN
# ============================================================================

@dataclass(frozen=True)
class ReviewRequirement:
    """
    Represents a generalized review requirement.

    This abstraction demonstrates that approval count and reviewer identity
    are separate dimensions.
    """

    minimum_count: int
    eligible_reviewers: Optional[Set[str]] = None

    def satisfied_by(self, approvals: Set[str]) -> bool:
        if self.eligible_reviewers is not None:
            approvals = approvals & self.eligible_reviewers
        return len(approvals) >= self.minimum_count


def demonstrate_review_requirements() -> None:
    print("\n" + "=" * 78)
    print("12. REVIEWER ELIGIBILITY")
    print("=" * 78)

    security_requirement = ReviewRequirement(
        minimum_count=1,
        eligible_reviewers={"security-team", "security-lead"},
    )

    approvals = {"bob", "security-lead"}

    print(f"Approvals received: {sorted(approvals)}")
    print(
        "Security requirement satisfied:",
        security_requirement.satisfied_by(approvals),
    )

    print(
        "\nThis illustrates why a policy may require not just a number of "
        "approvals but approval from a particular group."
    )


# ============================================================================
# 20. REVIEWER INDEPENDENCE
# ============================================================================

def demonstrate_reviewer_independence() -> None:
    print("\n" + "=" * 78)
    print("13. REVIEWER INDEPENDENCE")
    print("=" * 78)

    repository = create_demo_repository()
    pull_request = create_pull_request(repository, 46, "alice")

    pull_request.reviews.append(
        Review(
            reviewer="alice",
            state=ReviewState.APPROVED,
            commit_id=pull_request.head_commit_id,
        )
    )

    pull_request.status_checks.extend(
        [
            run_unit_tests(pull_request.head_commit),
            run_linter(pull_request.head_commit),
        ]
    )

    policy = BranchProtectionPolicy(
        required_approvals=1,
        required_status_checks=("unit-tests", "lint"),
        require_conversation_resolution=False,
        require_up_to_date_branch=True,
    )

    result = PullRequestPolicyEngine(policy).evaluate(
        pull_request,
        repository.branches["main"].head.commit_id,
    )

    print(result)
    print(
        "\nThe policy engine deliberately excludes the pull-request author "
        "from the independent reviewer count."
    )


# ============================================================================
# 21. EDGE CASES
# ============================================================================

def demonstrate_edge_cases() -> None:
    print("\n" + "=" * 78)
    print("14. EDGE CASES")
    print("=" * 78)

    edge_cases = {
        "No changed files": (
            "A PR may technically have little or no effective change; "
            "automation should still evaluate its actual state."
        ),
        "Binary files": (
            "Text diff algorithms cannot meaningfully explain every binary "
            "change, so specialized review may be required."
        ),
        "Renamed files": (
            "Rename detection is different from simply treating a path as "
            "deleted and another path as created."
        ),
        "Conflicting changes": (
            "A PR can satisfy review requirements yet still require conflict "
            "resolution before it can be merged."
        ),
        "Force pushes": (
            "Force pushes can rewrite branch history and should generally be "
            "restricted on important shared branches."
        ),
        "Approval after new commits": (
            "A new commit can invalidate assumptions made during review."
        ),
        "Self approval": (
            "A repository policy may restrict authors from satisfying "
            "independent review requirements with their own approval."
        ),
        "Failed checks after approval": (
            "Review approval does not replace automated verification."
        ),
    }

    for case, explanation in edge_cases.items():
        print(f"{case}: {explanation}")


# ============================================================================
# 22. PERFORMANCE CONSIDERATIONS
# ============================================================================

def complexity_notes() -> None:
    print("\n" + "=" * 78)
    print("15. PERFORMANCE AND SCALABILITY")
    print("=" * 78)

    notes = [
        "Diff generation is proportional to the amount of content examined.",
        "Approval lookup can be near O(R) for R review records.",
        "Using a set makes unique reviewer membership checks approximately O(1).",
        "Status checks can be indexed by commit ID and check name.",
        "Large repositories benefit from incremental CI instead of rebuilding everything.",
        "Parallel CI jobs can reduce wall-clock feedback time.",
        "Review policy evaluation should remain deterministic and auditable.",
    ]

    for note in notes:
        print(f"- {note}")


# ============================================================================
# 23. TESTABLE POLICY EXAMPLES
# ============================================================================

class PullRequestPolicyTests(unittest.TestCase):
    """Unit tests for the educational policy engine."""

    def setUp(self) -> None:
        self.repository = create_demo_repository()
        self.pull_request = create_pull_request(
            self.repository,
            number=100,
            author="alice",
        )

        self.policy = BranchProtectionPolicy(
            required_approvals=1,
            required_status_checks=("unit-tests", "lint"),
            dismiss_stale_approvals=True,
            require_conversation_resolution=True,
            require_up_to_date_branch=True,
        )

        self.engine = PullRequestPolicyEngine(self.policy)

    def add_approval(self, reviewer: str = "bob") -> None:
        self.pull_request.reviews.append(
            Review(
                reviewer=reviewer,
                state=ReviewState.APPROVED,
                commit_id=self.pull_request.head_commit_id,
            )
        )

    def add_passing_checks(self) -> None:
        self.pull_request.status_checks.extend(
            [
                run_unit_tests(self.pull_request.head_commit),
                run_linter(self.pull_request.head_commit),
            ]
        )

    def test_complete_pr_can_merge(self) -> None:
        self.add_approval()
        self.add_passing_checks()

        result = self.engine.evaluate(
            self.pull_request,
            self.repository.branches["main"].head.commit_id,
        )

        self.assertTrue(result.allowed)

    def test_missing_approval_blocks_merge(self) -> None:
        self.add_passing_checks()

        result = self.engine.evaluate(
            self.pull_request,
            self.repository.branches["main"].head.commit_id,
        )

        self.assertFalse(result.allowed)
        self.assertTrue(
            any("approval" in reason.lower() for reason in result.reasons)
        )

    def test_failed_check_blocks_merge(self) -> None:
        self.add_approval()

        self.pull_request.status_checks.extend(
            [
                StatusCheck(
                    name="unit-tests",
                    passed=False,
                    commit_id=self.pull_request.head_commit_id,
                ),
                run_linter(self.pull_request.head_commit),
            ]
        )

        result = self.engine.evaluate(
            self.pull_request,
            self.repository.branches["main"].head.commit_id,
        )

        self.assertFalse(result.allowed)

    def test_unresolved_comment_blocks_merge(self) -> None:
        self.add_approval()
        self.add_passing_checks()

        self.pull_request.comments.append(
            ReviewComment(
                reviewer="bob",
                filename="payment.py",
                line_number=2,
                body="Please explain this validation rule.",
                resolved=False,
            )
        )

        result = self.engine.evaluate(
            self.pull_request,
            self.repository.branches["main"].head.commit_id,
        )

        self.assertFalse(result.allowed)

    def test_draft_pr_blocks_merge(self) -> None:
        self.pull_request.draft = True
        self.add_approval()
        self.add_passing_checks()

        result = self.engine.evaluate(
            self.pull_request,
            self.repository.branches["main"].head.commit_id,
        )

        self.assertFalse(result.allowed)

    def test_stale_approval_does_not_count(self) -> None:
        self.add_approval()

        updated_files = dict(self.pull_request.head_commit.files)
        updated_files["README.md"] += "\nUpdated documentation.\n"

        self.pull_request.head_commit = Commit.create(
            author="alice",
            message="Update documentation",
            files=updated_files,
        )

        self.add_passing_checks()

        result = self.engine.evaluate(
            self.pull_request,
            self.repository.branches["main"].head.commit_id,
        )

        self.assertFalse(result.allowed)

    def test_author_approval_does_not_count(self) -> None:
        self.add_approval(reviewer="alice")
        self.add_passing_checks()

        result = self.engine.evaluate(
            self.pull_request,
            self.repository.branches["main"].head.commit_id,
        )

        self.assertFalse(result.allowed)


def run_tests() -> None:
    print("\n" + "=" * 78)
    print("16. AUTOMATED POLICY TESTS")
    print("=" * 78)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        PullRequestPolicyTests
    )
    result = unittest.TextTestRunner(verbosity=1).run(suite)

    print(
        f"\nTests run: {result.testsRun}; "
        f"failures: {len(result.failures)}; "
        f"errors: {len(result.errors)}"
    )


# ============================================================================
# 24. COMPLETE STUDY RUNNER
# ============================================================================

def main() -> None:
    explain_fundamentals()
    demonstrate_diff()
    demonstrate_review_comments()
    describe_merge_strategies()
    run_complete_workflow()
    demonstrate_stale_approval()
    demonstrate_draft_pr()
    demonstrate_direct_push_policy()
    demonstrate_code_owners()
    demonstrate_security_scan()
    demonstrate_policy_failures()
    demonstrate_review_requirements()
    demonstrate_reviewer_independence()
    demonstrate_edge_cases()
    complexity_notes()
    run_tests()

    print("\n" + "=" * 78)
    print("STUDY FILE EXECUTION COMPLETE")
    print("=" * 78)
    print(
        "The key model is: branch -> pull request -> diff -> review -> "
        "checks -> branch policy -> merge."
    )


if __name__ == "__main__":
    main()
