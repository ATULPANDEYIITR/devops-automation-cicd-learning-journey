from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Set, Tuple
import hashlib
import json
import re


class PullRequestState(Enum):
    DRAFT = "draft"
    OPEN = "open"
    CLOSED = "closed"
    MERGED = "merged"


class ReviewState(Enum):
    COMMENTED = "commented"
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    DISMISSED = "dismissed"


class CheckState(Enum):
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


@dataclass(frozen=True)
class User:
    username: str
    teams: Set[str] = field(default_factory=set)


@dataclass
class Commit:
    sha: str
    message: str
    author: str
    files: List[str]


@dataclass
class Review:
    reviewer: str
    state: ReviewState
    commit_sha: str
    comments: List[str] = field(default_factory=list)


@dataclass
class StatusCheck:
    name: str
    state: CheckState
    details: str = ""


@dataclass
class Vulnerability:
    package: str
    severity: str
    fixed_version: str | None = None


@dataclass
class ContainerImage:
    name: str
    user: str
    exposed_secrets: List[str]
    vulnerabilities: List[Vulnerability]

    def security_findings(self) -> List[str]:
        findings: List[str] = []

        if self.user.lower() in {"root", "0", ""}:
            findings.append("container runs as root")

        if self.exposed_secrets:
            findings.append(
                "secrets detected: " + ", ".join(sorted(self.exposed_secrets))
            )

        critical = sum(
            1 for v in self.vulnerabilities if v.severity.lower() == "critical"
        )
        high = sum(
            1 for v in self.vulnerabilities if v.severity.lower() == "high"
        )

        if critical:
            findings.append(f"{critical} critical vulnerabilities")
        if high:
            findings.append(f"{high} high vulnerabilities")

        return findings

    def is_secure(self) -> bool:
        return not self.security_findings()


@dataclass
class BranchProtection:
    require_pull_request: bool = True
    required_approvals: int = 2
    required_checks: Set[str] = field(
        default_factory=lambda: {
            "container-build",
            "container-vulnerability-scan",
            "container-secret-scan",
        }
    )
    restrict_direct_push: bool = True
    restrict_force_push: bool = True
    restrict_branch_deletion: bool = True
    require_conversations_resolved: bool = True
    require_linear_history: bool = True
    allow_admin_bypass: bool = False


@dataclass
class Branch:
    name: str
    protected: bool = False
    head_sha: str = ""


@dataclass
class Repository:
    name: str
    branches: Dict[str, Branch]
    users: Dict[str, User]
    protection: Dict[str, BranchProtection]


@dataclass
class PullRequest:
    number: int
    source_branch: str
    target_branch: str
    author: str
    head_sha: str
    state: PullRequestState = PullRequestState.OPEN
    draft: bool = False
    commits: List[Commit] = field(default_factory=list)
    reviews: List[Review] = field(default_factory=list)
    checks: List[StatusCheck] = field(default_factory=list)
    conversations_open: int = 0
    merge_conflict: bool = False
    base_synced: bool = True
    approvals_stale: bool = False
    security_findings: List[str] = field(default_factory=list)


class RepositorySecurityError(Exception):
    pass


class MergeEligibilityEngine:
    SEVERITY_ORDER = {
        "low": 1,
        "medium": 2,
        "high": 3,
        "critical": 4,
    }

    def __init__(self, repository: Repository):
        self.repository = repository

    def validate_container(self, image: ContainerImage) -> List[str]:
        findings = image.security_findings()

        for vulnerability in image.vulnerabilities:
            if vulnerability.severity.lower() not in self.SEVERITY_ORDER:
                raise RepositorySecurityError(
                    f"unknown vulnerability severity: {vulnerability.severity}"
                )

        return findings

    def evaluate(
        self,
        pr: PullRequest,
        image: ContainerImage,
    ) -> Tuple[bool, List[str]]:
        reasons: List[str] = []

        if pr.state != PullRequestState.OPEN:
            reasons.append(f"pull request state is {pr.state.value}")

        if pr.draft:
            reasons.append("pull request is still a draft")

        target = self.repository.branches.get(pr.target_branch)
        if target is None:
            reasons.append("target branch does not exist")
            return False, reasons

        policy = self.repository.protection.get(pr.target_branch)

        if policy is None:
            reasons.append("target branch has no protection policy")
        else:
            if policy.require_pull_request and not pr.number:
                reasons.append("protected branch requires a pull request")

            if pr.merge_conflict:
                reasons.append("merge conflicts must be resolved")

            if not pr.base_synced:
                reasons.append("source branch is not synchronized with base")

            if policy.require_conversations_resolved and pr.conversations_open:
                reasons.append(
                    f"{pr.conversations_open} review conversations remain unresolved"
                )

            eligible_approvals = self._eligible_approvals(pr)
            if len(eligible_approvals) < policy.required_approvals:
                reasons.append(
                    f"requires {policy.required_approvals} eligible approvals; "
                    f"only {len(eligible_approvals)} available"
                )

            if pr.approvals_stale:
                reasons.append("existing approvals are stale")

            check_map = {check.name: check for check in pr.checks}
            for required in policy.required_checks:
                check = check_map.get(required)
                if check is None:
                    reasons.append(f"required check missing: {required}")
                elif check.state != CheckState.PASSED:
                    reasons.append(
                        f"required check not passed: {required} ({check.state.value})"
                    )

            if policy.require_linear_history:
                if len(pr.commits) > 1 and self._has_merge_commit(pr):
                    reasons.append("linear history is required")

        findings = self.validate_container(image)
        pr.security_findings = findings

        if findings:
            reasons.extend(f"container security: {finding}" for finding in findings)

        return not reasons, reasons

    def _eligible_approvals(self, pr: PullRequest) -> List[Review]:
        approvals: List[Review] = []
        for review in pr.reviews:
            if review.state != ReviewState.APPROVED:
                continue

            reviewer = self.repository.users.get(review.reviewer)
            if reviewer is None:
                continue

            if review.reviewer == pr.author:
                continue

            if review.commit_sha != pr.head_sha:
                continue

            if review.state == ReviewState.DISMISSED:
                continue

            approvals.append(review)

        unique_reviewers = {}
        for approval in approvals:
            unique_reviewers[approval.reviewer] = approval

        return list(unique_reviewers.values())

    @staticmethod
    def _has_merge_commit(pr: PullRequest) -> bool:
        return any(
            len(commit.message.splitlines()) > 1
            or "merge" in commit.message.lower()
            for commit in pr.commits
        )


class SecretScanner:
    SECRET_PATTERNS = [
        re.compile(r"(?i)(password|passwd|secret|api[_-]?key)\s*[:=]\s*['\"][^'\"]+['\"]"),
        re.compile(r"(?i)-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
        re.compile(r"(?i)aws_secret_access_key\s*[:=]\s*\S+"),
    ]

    @classmethod
    def scan(cls, text: str) -> List[str]:
        return [
            f"potential secret at pattern {index + 1}"
            for index, pattern in enumerate(cls.SECRET_PATTERNS)
            if pattern.search(text)
        ]


def digest_commit(author: str, message: str, files: List[str]) -> str:
    payload = json.dumps(
        {"author": author, "message": message, "files": files},
        sort_keys=True,
    ).encode()
    return hashlib.sha256(payload).hexdigest()[:12]


def print_evaluation(
    title: str,
    eligible: bool,
    reasons: List[str],
) -> None:
    print(f"\n=== {title} ===")
    print(f"merge eligible: {eligible}")
    if reasons:
        for reason in reasons:
            print(f"  - {reason}")
    else:
        print("  - all repository and container-security conditions passed")


def main() -> None:
    users = {
        "alice": User("alice", {"developers"}),
        "bob": User("bob", {"security-reviewers"}),
        "carol": User("carol", {"platform-reviewers"}),
    }

    repository = Repository(
        name="payments-service",
        branches={
            "main": Branch("main", protected=True),
            "feature/container-hardening": Branch(
                "feature/container-hardening",
                protected=False,
            ),
        },
        users=users,
        protection={
            "main": BranchProtection(
                required_approvals=2,
                required_checks={
                    "container-build",
                    "container-vulnerability-scan",
                    "container-secret-scan",
                },
            )
        },
    )

    engine = MergeEligibilityEngine(repository)

    commit = Commit(
        sha=digest_commit(
            "alice",
            "Harden production container",
            ["Dockerfile", "app.py"],
        ),
        message="Harden production container",
        author="alice",
        files=["Dockerfile", "app.py"],
    )

    pr = PullRequest(
        number=42,
        source_branch="feature/container-hardening",
        target_branch="main",
        author="alice",
        head_sha=commit.sha,
        commits=[commit],
        checks=[
            StatusCheck("container-build", CheckState.PASSED),
            StatusCheck("container-vulnerability-scan", CheckState.PASSED),
            StatusCheck("container-secret-scan", CheckState.PASSED),
        ],
    )

    secure_image = ContainerImage(
        name="payments:42",
        user="10001",
        exposed_secrets=[],
        vulnerabilities=[
            Vulnerability("openssl", "medium", "3.2.1"),
        ],
    )

    pr.reviews = [
        Review("bob", ReviewState.APPROVED, commit.sha),
        Review("carol", ReviewState.APPROVED, commit.sha),
    ]

    eligible, reasons = engine.evaluate(pr, secure_image)
    print_evaluation("secure container", eligible, reasons)

    insecure_image = ContainerImage(
        name="payments:42",
        user="root",
        exposed_secrets=["DATABASE_PASSWORD"],
        vulnerabilities=[
            Vulnerability("openssl", "critical", "3.2.1"),
            Vulnerability("curl", "high", "8.10.0"),
        ],
    )

    eligible, reasons = engine.evaluate(pr, insecure_image)
    print_evaluation("insecure container", eligible, reasons)

    secret_text = """
    database_password = "production-password"
    normal_configuration = "safe"
    """

    secret_findings = SecretScanner.scan(secret_text)
    print("\n=== secret scanner ===")
    print(f"findings: {len(secret_findings)}")
    for finding in secret_findings:
        print(f"  - {finding}")

    assert not engine.evaluate(pr, secure_image)[1]
    assert not engine.evaluate(pr, insecure_image)[0]
    assert secret_findings

    print("\nAssertions passed.")
    print(
        "Production controls should use immutable image references, "
        "least-privilege container users, external secret stores, "
        "continuous vulnerability scanning, and protected deployment branches."
    )


if __name__ == "__main__":
    main()
