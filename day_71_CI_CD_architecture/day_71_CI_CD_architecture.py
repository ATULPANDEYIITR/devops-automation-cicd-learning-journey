#!/usr/bin/env python3
"""
CI/CD Architecture and Repository Governance
Pipeline orchestration, runners, artifacts, environments, Pull Requests,
Code Reviews, approvals, branch protection, and merge eligibility.

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import tempfile
import time
import unittest

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("cicd")


class DomainError(Exception):
    """Base exception for repository workflow errors."""


class ValidationError(DomainError):
    pass


class TransitionError(DomainError):
    pass


class AuthorizationError(DomainError):
    pass


class PipelineError(DomainError):
    pass


class PRState(str, Enum):
    DRAFT = "draft"
    OPEN = "open"
    MERGED = "merged"
    CLOSED = "closed"


class ReviewState(str, Enum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    COMMENTED = "commented"
    DISMISSED = "dismissed"


class CheckState(str, Enum):
    PENDING = "pending"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


class PipelineState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class MergeStrategy(str, Enum):
    MERGE_COMMIT = "merge_commit"
    SQUASH = "squash"
    REBASE = "rebase"


@dataclass(frozen=True)
class Commit:
    sha: str
    message: str
    author: str
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def __post_init__(self):
        if not re.fullmatch(r"[0-9a-f]{7,40}", self.sha):
            raise ValidationError("Invalid commit SHA.")
        if not self.message.strip() or not self.author.strip():
            raise ValidationError("Commit message and author are required.")


@dataclass
class Branch:
    name: str
    commits: list[Commit] = field(default_factory=list)

    @property
    def head(self) -> Optional[str]:
        return self.commits[-1].sha if self.commits else None

    def add_commit(self, commit: Commit) -> None:
        if any(c.sha == commit.sha for c in self.commits):
            raise ValidationError("Duplicate commit.")
        self.commits.append(commit)


@dataclass(frozen=True)
class Reviewer:
    username: str
    active: bool = True
    roles: frozenset[str] = frozenset({"developer"})

    @property
    def eligible(self) -> bool:
        return self.active and bool(
            self.roles & {"maintainer", "reviewer", "security"}
        )


@dataclass
class Review:
    reviewer: str
    state: ReviewState
    commit_sha: str
    comments: list[str] = field(default_factory=list)
    dismissed: bool = False
    submitted_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def effective_state(self) -> ReviewState:
        return ReviewState.DISMISSED if self.dismissed else self.state


@dataclass
class StatusCheck:
    name: str
    state: CheckState
    commit_sha: str
    details: str = ""


@dataclass
class Artifact:
    name: str
    digest: str
    commit_sha: str
    size_bytes: int
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass
class Runner:
    runner_id: str
    labels: set[str]
    capacity: int = 1
    active: bool = True
    current_jobs: int = 0

    def can_execute(self, required_labels: set[str]) -> bool:
        return (
            self.active
            and self.current_jobs < self.capacity
            and required_labels.issubset(self.labels)
        )


@dataclass
class PipelineJob:
    job_id: str
    name: str
    required_labels: set[str]
    state: PipelineState = PipelineState.QUEUED
    runner_id: Optional[str] = None
    duration_seconds: float = 0.0


@dataclass
class Pipeline:
    pipeline_id: str
    commit_sha: str
    jobs: list[PipelineJob]
    state: PipelineState = PipelineState.QUEUED
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def evaluate(self) -> PipelineState:
        states = {job.state for job in self.jobs}

        if PipelineState.FAILURE in states:
            self.state = PipelineState.FAILURE
        elif PipelineState.CANCELLED in states:
            self.state = PipelineState.CANCELLED
        elif all(job.state == PipelineState.SUCCESS for job in self.jobs):
            self.state = PipelineState.SUCCESS
        elif PipelineState.RUNNING in states:
            self.state = PipelineState.RUNNING
        else:
            self.state = PipelineState.QUEUED

        return self.state


@dataclass
class BranchProtection:
    branch_name: str
    required_reviews: int = 2
    required_checks: set[str] = field(
        default_factory=lambda: {"unit-tests", "security-scan"}
    )
    require_conversation_resolution: bool = True
    require_linear_history: bool = False
    allow_direct_push: bool = False
    allow_force_push: bool = False
    allow_deletion: bool = False
    dismiss_stale_reviews: bool = True
    enforce_admins: bool = True
    allowed_merge_strategies: set[MergeStrategy] = field(
        default_factory=lambda: {
            MergeStrategy.SQUASH,
            MergeStrategy.MERGE_COMMIT,
        }
    )


@dataclass
class PullRequest:
    pr_id: int
    title: str
    author: str
    source_branch: str
    target_branch: str
    base_sha: str
    state: PRState = PRState.DRAFT
    reviews: list[Review] = field(default_factory=list)
    checks: list[StatusCheck] = field(default_factory=list)
    conversations: dict[str, bool] = field(default_factory=dict)
    commits: list[str] = field(default_factory=list)
    requested_reviewers: set[str] = field(default_factory=set)
    merged_sha: Optional[str] = None
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    def open(self) -> None:
        if self.state not in {PRState.DRAFT, PRState.CLOSED}:
            raise TransitionError("Pull Request cannot be opened.")
        self.state = PRState.OPEN
        self.updated_at = datetime.now(timezone.utc)

    def add_commit(self, commit_sha: str, protection: BranchProtection):
        if self.state != PRState.OPEN:
            raise TransitionError("PR must be open.")
        if commit_sha in self.commits:
            raise ValidationError("Commit already attached.")

        self.commits.append(commit_sha)
        self.updated_at = datetime.now(timezone.utc)

        if protection.dismiss_stale_reviews:
            for review in self.reviews:
                if review.state == ReviewState.APPROVED:
                    review.dismissed = True

    def add_review(self, review: Review, reviewers: dict[str, Reviewer]):
        if self.state != PRState.OPEN:
            raise TransitionError("PR must be open.")

        reviewer = reviewers.get(review.reviewer)
        if reviewer is None or not reviewer.eligible:
            raise AuthorizationError("Reviewer is not eligible.")

        if review.reviewer == self.author:
            raise AuthorizationError("Authors cannot approve their own PR.")

        if review.commit_sha not in self.commits:
            raise ValidationError("Review references an unrelated commit.")

        self.reviews.append(review)

    def add_conversation(self, conversation_id: str):
        if self.state != PRState.OPEN:
            raise TransitionError("PR must be open.")
        self.conversations[conversation_id] = False

    def resolve_conversation(self, conversation_id: str):
        if conversation_id not in self.conversations:
            raise ValidationError("Unknown conversation.")
        self.conversations[conversation_id] = True

    def latest_reviews(self) -> dict[str, Review]:
        latest = {}
        for review in sorted(self.reviews, key=lambda r: r.submitted_at):
            latest[review.reviewer] = review
        return latest


@dataclass
class MergeDecision:
    eligible: bool
    reasons: list[str]


class Repository:
    def __init__(self, name: str):
        self.name = name
        self.branches: dict[str, Branch] = {}
        self.pull_requests: dict[int, PullRequest] = {}
        self.reviewers: dict[str, Reviewer] = {}
        self.protections: dict[str, BranchProtection] = {}
        self.artifacts: dict[str, Artifact] = {}
        self.runners: dict[str, Runner] = {}
        self.pipelines: dict[str, Pipeline] = {}
        self.next_pr_id = 1

    def add_branch(self, branch: Branch):
        if branch.name in self.branches:
            raise ValidationError("Branch already exists.")
        self.branches[branch.name] = branch

    def protect_branch(self, protection: BranchProtection):
        if protection.branch_name not in self.branches:
            raise ValidationError("Protected branch does not exist.")
        if protection.required_reviews < 0:
            raise ValidationError("Invalid review requirement.")
        self.protections[protection.branch_name] = protection

    def register_reviewer(self, reviewer: Reviewer):
        self.reviewers[reviewer.username] = reviewer

    def create_pr(
        self,
        title: str,
        author: str,
        source: str,
        target: str,
        draft: bool = True,
    ) -> PullRequest:
        if not title.strip():
            raise ValidationError("PR title is required.")
        if source == target:
            raise ValidationError("Source and target must differ.")
        if source not in self.branches or target not in self.branches:
            raise ValidationError("Unknown branch.")

        pr = PullRequest(
            self.next_pr_id,
            title,
            author,
            source,
            target,
            self.branches[target].head or "",
        )

        self.next_pr_id += 1
        pr.commits = [
            c.sha for c in self.branches[source].commits
            if c.sha not in {
                item.sha for item in self.branches[target].commits
            }
        ]

        if not draft:
            pr.open()

        self.pull_requests[pr.pr_id] = pr
        return pr

    def synchronize_base(self, pr_id: int):
        pr = self.pull_requests[pr_id]
        if pr.state != PRState.OPEN:
            raise TransitionError("Only open PRs can be synchronized.")

        pr.base_sha = self.branches[pr.target_branch].head or ""

    def merge_eligibility(self, pr: PullRequest) -> MergeDecision:
        reasons = []

        if pr.state != PRState.OPEN:
            reasons.append("Pull Request is not open.")
            return MergeDecision(False, reasons)

        protection = self.protections.get(pr.target_branch)

        if protection is None:
            reasons.append("Target branch has no protection policy.")
            return MergeDecision(False, reasons)

        source = self.branches[pr.source_branch]
        target = self.branches[pr.target_branch]

        if pr.base_sha != (target.head or ""):
            reasons.append("Target branch has changed; synchronize the PR.")

        if not pr.commits:
            reasons.append("No proposed commits.")

        source_shas = {c.sha for c in source.commits}
        if not set(pr.commits).issubset(source_shas):
            reasons.append("Proposed commits are no longer in source branch.")

        if any(c.sha == target.head for c in source.commits):
            if protection.require_linear_history:
                reasons.append("Linear-history policy requires verification.")

        latest = pr.latest_reviews()
        approvals = {
            username
            for username, review in latest.items()
            if review.effective_state == ReviewState.APPROVED
            and review.commit_sha == source.head
            and self.reviewers.get(username)
            and self.reviewers[username].eligible
        }

        if len(approvals) < protection.required_reviews:
            reasons.append(
                f"Insufficient current approvals: "
                f"{len(approvals)}/{protection.required_reviews}."
            )

        if any(
            review.effective_state == ReviewState.CHANGES_REQUESTED
            and review.commit_sha == source.head
            for review in latest.values()
        ):
            reasons.append("An active reviewer requested changes.")

        check_map = {check.name: check for check in pr.checks}

        for required in protection.required_checks:
            check = check_map.get(required)
            if (
                check is None
                or check.state != CheckState.SUCCESS
                or check.commit_sha != source.head
            ):
                reasons.append(f"Required check not successful: {required}.")

        if (
            protection.require_conversation_resolution
            and not all(pr.conversations.values())
        ):
            reasons.append("Unresolved review conversations exist.")

        return MergeDecision(not reasons, reasons)

    def merge(
        self,
        pr_id: int,
        strategy: MergeStrategy,
    ) -> str:
        pr = self.pull_requests[pr_id]
        protection = self.protections.get(pr.target_branch)

        if protection is None:
            raise AuthorizationError("No merge policy.")

        if strategy not in protection.allowed_merge_strategies:
            raise AuthorizationError("Merge strategy is prohibited.")

        decision = self.merge_eligibility(pr)

        if not decision.eligible:
            raise AuthorizationError("; ".join(decision.reasons))

        target = self.branches[pr.target_branch]
        source = self.branches[pr.source_branch]

        material = (
            f"{self.name}:{pr.pr_id}:{strategy.value}:"
            f"{target.head}:{source.head}"
        )
        merged_sha = hashlib.sha1(material.encode()).hexdigest()

        commit = Commit(
            merged_sha,
            f"Merge PR #{pr.pr_id}: {pr.title}",
            "repository-service",
        )
        target.add_commit(commit)

        pr.state = PRState.MERGED
        pr.merged_sha = merged_sha
        return merged_sha

    def close_pr(self, pr_id: int):
        pr = self.pull_requests[pr_id]
        if pr.state in {PRState.MERGED, PRState.CLOSED}:
            raise TransitionError("PR cannot be closed.")
        pr.state = PRState.CLOSED

    def reopen_pr(self, pr_id: int):
        pr = self.pull_requests[pr_id]
        if pr.state != PRState.CLOSED:
            raise TransitionError("Only closed PRs can be reopened.")
        pr.open()

    def register_runner(self, runner: Runner):
        if runner.capacity < 1:
            raise ValidationError("Runner capacity must be positive.")
        self.runners[runner.runner_id] = runner

    def dispatch_job(self, job: PipelineJob) -> bool:
        candidates = sorted(
            self.runners.values(),
            key=lambda r: (r.current_jobs, r.runner_id),
        )

        for runner in candidates:
            if runner.can_execute(job.required_labels):
                runner.current_jobs += 1
                job.runner_id = runner.runner_id
                job.state = PipelineState.RUNNING
                return True

        return False

    def complete_job(
        self,
        job: PipelineJob,
        success: bool,
        duration: float,
    ):
        if job.state != PipelineState.RUNNING or not job.runner_id:
            raise TransitionError("Job is not running.")

        runner = self.runners[job.runner_id]
        runner.current_jobs -= 1

        if duration < 0:
            raise ValidationError("Invalid job duration.")

        job.duration_seconds = duration
        job.state = (
            PipelineState.SUCCESS if success
            else PipelineState.FAILURE
        )

    def store_artifact(
        self,
        name: str,
        content: bytes,
        commit_sha: str,
    ) -> Artifact:
        if not name.strip() or not content:
            raise ValidationError("Artifact name and content are required.")
        if len(content) > 50 * 1024 * 1024:
            raise ValidationError("Artifact exceeds 50 MB limit.")

        artifact = Artifact(
            name,
            hashlib.sha256(content).hexdigest(),
            commit_sha,
            len(content),
        )
        self.artifacts[artifact.digest] = artifact
        return artifact

    def deploy(
        self,
        artifact_digest: str,
        environment: Environment,
        pipeline: Pipeline,
        production_approved: bool = False,
    ) -> bool:
        artifact = self.artifacts.get(artifact_digest)

        if artifact is None:
            raise ValidationError("Unknown artifact.")

        if pipeline.state != PipelineState.SUCCESS:
            raise PipelineError("Deployment requires a successful pipeline.")

        if pipeline.commit_sha != artifact.commit_sha:
            raise PipelineError("Artifact and pipeline commit differ.")

        if (
            environment == Environment.PRODUCTION
            and not production_approved
        ):
            raise AuthorizationError(
                "Production deployment requires explicit authorization."
            )

        logger.info(
            "Deploying artifact %s to %s",
            artifact.name,
            environment.value,
        )
        return True


def run_tests():
    class GovernanceTests(unittest.TestCase):
        def setUp(self):
            self.repo = Repository("payment-platform")

            base = Branch("main")
            base.add_commit(
                Commit("aaaaaaa", "Initial release", "admin")
            )
            self.repo.add_branch(base)

            feature = Branch("feature/security")
            feature.add_commit(
                Commit("bbbbbbb", "Add security validation", "developer")
            )
            self.repo.add_branch(feature)

            self.repo.register_reviewer(
                Reviewer("reviewer1", roles=frozenset({"reviewer"}))
            )
            self.repo.register_reviewer(
                Reviewer("reviewer2", roles=frozenset({"maintainer"}))
            )

            self.repo.protect_branch(
                BranchProtection("main", required_reviews=2)
            )

            self.pr = self.repo.create_pr(
                "Add payment validation",
                "developer",
                "feature/security",
                "main",
                draft=False,
            )

        def approve(self):
            for username in ("reviewer1", "reviewer2"):
                self.pr.add_review(
                    Review(
                        username,
                        ReviewState.APPROVED,
                        "bbbbbbb",
                    ),
                    self.repo.reviewers,
                )

            self.pr.checks = [
                StatusCheck("unit-tests", CheckState.SUCCESS, "bbbbbbb"),
                StatusCheck("security-scan", CheckState.SUCCESS, "bbbbbbb"),
            ]

        def test_merge_requires_governance(self):
            self.assertFalse(
                self.repo.merge_eligibility(self.pr).eligible
            )

        def test_successful_merge(self):
            self.approve()
            decision = self.repo.merge_eligibility(self.pr)
            self.assertTrue(decision.eligible)
            sha = self.repo.merge(self.pr.pr_id, MergeStrategy.SQUASH)
            self.assertEqual(len(sha), 40)
            self.assertEqual(self.pr.state, PRState.MERGED)

        def test_stale_approval(self):
            self.approve()
            self.pr.add_commit("ccccccc",
                               self.repo.protections["main"])
            self.assertFalse(
                self.repo.merge_eligibility(self.pr).eligible
            )

        def test_unresolved_conversation(self):
            self.approve()
            self.pr.add_conversation("discussion-1")
            self.assertFalse(
                self.repo.merge_eligibility(self.pr).eligible
            )

        def test_self_approval_rejected(self):
            with self.assertRaises(AuthorizationError):
                self.pr.add_review(
                    Review("developer", ReviewState.APPROVED, "bbbbbbb"),
                    self.repo.reviewers,
                )

        def test_invalid_production_deployment(self):
            with self.assertRaises(AuthorizationError):
                self.repo.deploy(
                    "unknown",
                    Environment.PRODUCTION,
                    Pipeline("p", "bbbbbbb", []),
                )

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        GovernanceTests
    )
    result = unittest.TextTestRunner(verbosity=2).run(suite)

    if not result.wasSuccessful():
        raise SystemExit(1)


def demonstration():
    repo = Repository("payment-platform")

    main = Branch("main")
    main.add_commit(Commit("aaaaaaa", "Initial release", "admin"))
    repo.add_branch(main)

    feature = Branch("feature/payment-validation")
    feature.add_commit(
        Commit("bbbbbbb", "Implement validation", "developer")
    )
    repo.add_branch(feature)

    repo.register_reviewer(
        Reviewer("alice", roles=frozenset({"reviewer"}))
    )
    repo.register_reviewer(
        Reviewer("bob", roles=frozenset({"maintainer"}))
    )

    repo.protect_branch(
        BranchProtection(
            "main",
            required_reviews=2,
            required_checks={"unit-tests", "security-scan"},
            require_conversation_resolution=True,
            allow_direct_push=False,
        )
    )

    pr = repo.create_pr(
        "Implement payment validation",
        "developer",
        "feature/payment-validation",
        "main",
        draft=True,
    )

    pr.open()
    pr.requested_reviewers.update({"alice", "bob"})

    pr.add_review(
        Review("alice", ReviewState.APPROVED, "bbbbbbb"),
        repo.reviewers,
    )
    pr.add_review(
        Review("bob", ReviewState.APPROVED, "bbbbbbb"),
        repo.reviewers,
    )

    pr.checks = [
        StatusCheck("unit-tests", CheckState.SUCCESS, "bbbbbbb"),
        StatusCheck("security-scan", CheckState.SUCCESS, "bbbbbbb"),
    ]

    pr.add_conversation("security-review")
    pr.resolve_conversation("security-review")

    decision = repo.merge_eligibility(pr)

    print("\nPULL REQUEST GOVERNANCE")
    print("Repository:", repo.name)
    print("PR:", pr.pr_id)
    print("State:", pr.state.value)
    print("Proposed commits:", pr.commits)
    print("Merge eligible:", decision.eligible)
    print("Reasons:", decision.reasons)

    if decision.eligible:
        print(
            "Merged commit:",
            repo.merge(pr.pr_id, MergeStrategy.SQUASH),
        )

    runner = Runner("linux-runner-01", {"linux", "python", "docker"})
    repo.register_runner(runner)

    jobs = [
        PipelineJob("job-1", "unit-tests", {"linux", "python"}),
        PipelineJob("job-2", "container-build", {"linux", "docker"}),
    ]

    print("\nCI/CD PIPELINE")
    for job in jobs:
        if repo.dispatch_job(job):
            repo.complete_job(job, True, 12.5)
            print(job.name, job.state.value, job.runner_id)
        else:
            print(job.name, "queued: no compatible runner")

    pipeline = Pipeline(
        "pipeline-001",
        "bbbbbbb",
        jobs,
    )
    pipeline.evaluate()
    print("Pipeline state:", pipeline.state.value)

    artifact = repo.store_artifact(
        "payment-service.tar",
        b"compiled-payment-service-v1",
        "bbbbbbb",
    )

    print("Artifact SHA-256:", artifact.digest)

    repo.deploy(
        artifact.digest,
        Environment.STAGING,
        pipeline,
    )


if __name__ == "__main__":
    demonstration()
    print("\nRUNNING TESTS")
    run_tests()
