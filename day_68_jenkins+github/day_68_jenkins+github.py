#!/usr/bin/env python3
"""
Jenkins + GitHub Integration
Webhook automation, SCM polling, pull-request governance and CI/CD simulation.

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
import re
import time
import unittest

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger("jenkins_github")


# ============================================================
# 1. DOMAIN TYPES
# ============================================================

class EventType(str, Enum):
    PUSH = "push"
    PULL_REQUEST = "pull_request"
    PULL_REQUEST_REVIEW = "pull_request_review"
    STATUS_CHECK = "status_check"
    PING = "ping"


class PRState(str, Enum):
    OPEN = "open"
    DRAFT = "draft"
    CLOSED = "closed"
    MERGED = "merged"


class ReviewState(str, Enum):
    APPROVED = "approved"
    CHANGES_REQUESTED = "changes_requested"
    COMMENTED = "commented"
    DISMISSED = "dismissed"


class CheckState(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PENDING = "pending"
    ERROR = "error"


class BuildStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    ABORTED = "aborted"


class TriggerType(str, Enum):
    WEBHOOK = "webhook"
    SCM_POLL = "scm_poll"
    MANUAL = "manual"


# ============================================================
# 2. DATA MODELS
# ============================================================

@dataclass(frozen=True)
class Commit:
    sha: str
    message: str
    author: str

    def __post_init__(self):
        if not re.fullmatch(r"[0-9a-f]{7,64}", self.sha):
            raise ValueError("Invalid commit SHA")
        if not self.message.strip():
            raise ValueError("Commit message cannot be empty")


@dataclass
class Branch:
    name: str
    head_sha: str
    protected: bool = False
    allows_force_push: bool = False
    allows_deletion: bool = False

    def __post_init__(self):
        if not self.name or self.name.startswith("-"):
            raise ValueError("Invalid branch name")


@dataclass
class Review:
    reviewer: str
    state: ReviewState
    commit_sha: str
    submitted_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass
class StatusCheck:
    name: str
    state: CheckState
    commit_sha: str
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )


@dataclass
class PullRequest:
    number: int
    source_branch: str
    target_branch: str
    source_sha: str
    target_sha: str
    state: PRState = PRState.OPEN
    commits: list[Commit] = field(default_factory=list)
    reviews: list[Review] = field(default_factory=list)
    checks: dict[str, StatusCheck] = field(default_factory=dict)
    unresolved_discussions: int = 0
    merge_conflict: bool = False
    base_synchronized: bool = True

    def __post_init__(self):
        if self.number <= 0:
            raise ValueError("PR number must be positive")
        if self.source_branch == self.target_branch:
            raise ValueError("Source and target branches must differ")


@dataclass(frozen=True)
class BranchProtection:
    branch_name: str
    required_reviews: int = 1
    required_checks: frozenset[str] = frozenset()
    require_conversation_resolution: bool = True
    require_up_to_date_branch: bool = True
    require_linear_history: bool = False
    allow_direct_push: bool = False
    allow_force_push: bool = False
    allow_deletion: bool = False
    require_code_owner_review: bool = False
    dismiss_stale_approvals: bool = True
    allow_administrator_bypass: bool = False

    def __post_init__(self):
        if self.required_reviews < 0:
            raise ValueError("Required reviews cannot be negative")


@dataclass
class Repository:
    name: str
    branches: dict[str, Branch]
    protection: dict[str, BranchProtection]
    commits: dict[str, Commit] = field(default_factory=dict)
    pull_requests: dict[int, PullRequest] = field(default_factory=dict)
    eligible_reviewers: set[str] = field(default_factory=set)
    code_owners: set[str] = field(default_factory=set)


@dataclass
class Build:
    build_id: int
    repository: str
    commit_sha: str
    branch: str
    trigger: TriggerType
    status: BuildStatus = BuildStatus.QUEUED
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


# ============================================================
# 3. WEBHOOK SECURITY
# ============================================================

class WebhookSecurityError(Exception):
    pass


class WebhookVerifier:
    """
    Verifies GitHub webhook signatures.

    GitHub sends:
        X-Hub-Signature-256: sha256=<hexadecimal digest>

    The signature must be computed over the original raw body.
    """

    def __init__(self, secret: str):
        if len(secret) < 16:
            raise ValueError("Webhook secret must contain at least 16 characters")
        self.secret = secret.encode("utf-8")

    def verify(self, raw_body: bytes, signature: str) -> bool:
        if not signature.startswith("sha256="):
            return False

        supplied = signature.removeprefix("sha256=")

        if not re.fullmatch(r"[0-9a-fA-F]{64}", supplied):
            return False

        expected = hmac.new(
            self.secret,
            raw_body,
            hashlib.sha256
        ).hexdigest()

        return hmac.compare_digest(expected, supplied)

    def require_valid(self, raw_body: bytes, signature: str):
        if not self.verify(raw_body, signature):
            raise WebhookSecurityError("Invalid webhook signature")


# ============================================================
# 4. EVENT DEDUPLICATION
# ============================================================

class EventDeduplicator:
    """
    Prevents repeated delivery of the same GitHub webhook.

    Production deployments should persist delivery IDs in a
    database or durable queue.
    """

    def __init__(self, maximum_entries: int = 10000):
        self.seen: dict[str, float] = {}
        self.maximum_entries = maximum_entries

    def accept(self, delivery_id: str) -> bool:
        if not delivery_id:
            raise ValueError("Missing delivery ID")

        if delivery_id in self.seen:
            return False

        if len(self.seen) >= self.maximum_entries:
            oldest = min(self.seen, key=self.seen.get)
            del self.seen[oldest]

        self.seen[delivery_id] = time.monotonic()
        return True


# ============================================================
# 5. PULL REQUEST GOVERNANCE
# ============================================================

@dataclass
class MergeDecision:
    eligible: bool
    reasons: list[str]


class MergeEligibilityService:

    @staticmethod
    def evaluate(
        repository: Repository,
        pr: PullRequest,
        administrator: bool = False
    ) -> MergeDecision:

        reasons = []

        if pr.state != PRState.OPEN:
            reasons.append("Pull Request is not open")

        if pr.state == PRState.DRAFT:
            reasons.append("Draft Pull Requests cannot be merged")

        policy = repository.protection.get(pr.target_branch)

        if policy is None:
            if reasons:
                return MergeDecision(False, reasons)
            return MergeDecision(True, [])

        if administrator and policy.allow_administrator_bypass:
            if pr.state == PRState.OPEN and not pr.merge_conflict:
                return MergeDecision(True, [])
            return MergeDecision(False, reasons)

        if pr.merge_conflict:
            reasons.append("Merge conflicts must be resolved")

        if policy.require_up_to_date_branch and not pr.base_synchronized:
            reasons.append("Source branch must be synchronized with target")

        if policy.require_conversation_resolution:
            if pr.unresolved_discussions > 0:
                reasons.append("Unresolved review discussions exist")

        if policy.required_checks:
            for check_name in policy.required_checks:
                check = pr.checks.get(check_name)

                if check is None:
                    reasons.append(f"Missing required check: {check_name}")
                elif check.state != CheckState.SUCCESS:
                    reasons.append(
                        f"Required check {check_name} is {check.state.value}"
                    )
                elif check.commit_sha != pr.source_sha:
                    reasons.append(
                        f"Required check {check_name} is stale"
                    )

        valid_approvals = {}

        for review in pr.reviews:
            if review.reviewer not in repository.eligible_reviewers:
                continue

            if review.commit_sha != pr.source_sha:
                continue

            if review.state == ReviewState.APPROVED:
                valid_approvals[review.reviewer] = review

            elif review.state == ReviewState.CHANGES_REQUESTED:
                valid_approvals.pop(review.reviewer, None)

        if policy.dismiss_stale_approvals:
            valid_approvals = {
                reviewer: review
                for reviewer, review in valid_approvals.items()
                if review.commit_sha == pr.source_sha
            }

        if policy.require_code_owner_review:
            code_owner_approved = any(
                reviewer in repository.code_owners
                for reviewer in valid_approvals
            )

            if not code_owner_approved:
                reasons.append("Code owner approval is required")

        if len(valid_approvals) < policy.required_reviews:
            reasons.append(
                f"Insufficient approvals: "
                f"{len(valid_approvals)}/{policy.required_reviews}"
            )

        return MergeDecision(not reasons, reasons)


# ============================================================
# 6. JENKINS BUILD ORCHESTRATION
# ============================================================

class JenkinsBuildManager:

    def __init__(self, repository: Repository):
        self.repository = repository
        self.builds: list[Build] = []
        self.next_build_id = 1
        self.processed_events: set[str] = set()

    def trigger(
        self,
        commit_sha: str,
        branch: str,
        trigger_type: TriggerType,
        event_id: Optional[str] = None
    ) -> Optional[Build]:

        if event_id:
            if event_id in self.processed_events:
                logger.warning("Duplicate event ignored: %s", event_id)
                return None

            self.processed_events.add(event_id)

        if branch not in self.repository.branches:
            raise ValueError(f"Unknown branch: {branch}")

        if commit_sha not in self.repository.commits:
            raise ValueError(f"Unknown commit: {commit_sha}")

        build = Build(
            build_id=self.next_build_id,
            repository=self.repository.name,
            commit_sha=commit_sha,
            branch=branch,
            trigger=trigger_type
        )

        self.next_build_id += 1
        self.builds.append(build)

        logger.info(
            "Jenkins build #%s queued for %s",
            build.build_id,
            commit_sha
        )

        return build

    def execute(
        self,
        build: Build,
        pipeline_success: bool = True
    ) -> Build:

        if build.status != BuildStatus.QUEUED:
            raise ValueError("Only queued builds can execute")

        build.status = BuildStatus.RUNNING
        build.started_at = datetime.now(timezone.utc)

        try:
            if not pipeline_success:
                raise RuntimeError("Pipeline execution failed")

            build.status = BuildStatus.SUCCESS

        except Exception:
            build.status = BuildStatus.FAILURE
            logger.exception("Build #%s failed", build.build_id)

        finally:
            build.finished_at = datetime.now(timezone.utc)

        return build


# ============================================================
# 7. WEBHOOK EVENT PROCESSOR
# ============================================================

class GitHubEventProcessor:

    def __init__(self, build_manager: JenkinsBuildManager):
        self.build_manager = build_manager

    def process(
        self,
        event_type: EventType,
        payload: dict,
        delivery_id: str
    ) -> Optional[Build]:

        if event_type == EventType.PING:
            logger.info("GitHub webhook connection verified")
            return None

        if event_type == EventType.PUSH:
            branch_ref = payload.get("ref", "")
            branch = branch_ref.removeprefix("refs/heads/")
            commit_sha = payload.get("after")

            if not branch or not commit_sha:
                raise ValueError("Invalid push payload")

            if commit_sha == "0" * 40:
                logger.info("Branch deletion event ignored")
                return None

            return self.build_manager.trigger(
                commit_sha,
                branch,
                TriggerType.WEBHOOK,
                delivery_id
            )

        if event_type == EventType.PULL_REQUEST:
            action = payload.get("action")
            pr = payload.get("pull_request", {})

            if action not in {
                "opened",
                "synchronize",
                "reopened",
                "ready_for_review"
            }:
                logger.info("PR action does not require a build")
                return None

            if pr.get("draft", False):
                logger.info("Draft PR build skipped by policy")
                return None

            branch = pr.get("head", {}).get("ref")
            sha = pr.get("head", {}).get("sha")

            if not branch or not sha:
                raise ValueError("Invalid pull request payload")

            return self.build_manager.trigger(
                sha,
                branch,
                TriggerType.WEBHOOK,
                delivery_id
            )

        logger.info("Event recorded without triggering a build")
        return None


# ============================================================
# 8. SCM POLLING
# ============================================================

class SCMPoller:
    """
    Compares observed remote commit IDs with previously
    observed IDs.

    Actual Git operations are intentionally separated from
    polling state management.
    """

    def __init__(self):
        self.last_seen: dict[str, str] = {}

    def poll(
        self,
        branch: str,
        remote_commit_sha: str
    ) -> bool:

        if not branch:
            raise ValueError("Branch cannot be empty")

        if not re.fullmatch(r"[0-9a-f]{7,64}", remote_commit_sha):
            raise ValueError("Invalid remote commit SHA")

        previous = self.last_seen.get(branch)

        if previous == remote_commit_sha:
            return False

        self.last_seen[branch] = remote_commit_sha

        logger.info(
            "SCM change detected: %s (%s -> %s)",
            branch,
            previous,
            remote_commit_sha
        )

        return True


# ============================================================
# 9. REPOSITORY WORKFLOW
# ============================================================

class RepositoryWorkflow:

    def __init__(self, repository: Repository):
        self.repository = repository
        self.merge_service = MergeEligibilityService()

    def create_pull_request(
        self,
        number: int,
        source_branch: str,
        target_branch: str,
        commits: list[Commit]
    ) -> PullRequest:

        if source_branch not in self.repository.branches:
            raise ValueError("Unknown source branch")

        if target_branch not in self.repository.branches:
            raise ValueError("Unknown target branch")

        if number in self.repository.pull_requests:
            raise ValueError("Pull Request number already exists")

        if not commits:
            raise ValueError("Pull Request must contain commits")

        source = self.repository.branches[source_branch]
        target = self.repository.branches[target_branch]

        for commit in commits:
            self.repository.commits[commit.sha] = commit

        pr = PullRequest(
            number=number,
            source_branch=source_branch,
            target_branch=target_branch,
            source_sha=source.head_sha,
            target_sha=target.head_sha,
            commits=commits
        )

        self.repository.pull_requests[number] = pr
        return pr

    def submit_review(
        self,
        pr_number: int,
        reviewer: str,
        state: ReviewState
    ) -> None:

        pr = self.repository.pull_requests[pr_number]

        if reviewer not in self.repository.eligible_reviewers:
            raise PermissionError("Reviewer is not eligible")

        if pr.state != PRState.OPEN:
            raise ValueError("Cannot review a closed Pull Request")

        if state == ReviewState.DISMISSED:
            raise ValueError("Dismissal must target an existing review")

        pr.reviews.append(
            Review(
                reviewer=reviewer,
                state=state,
                commit_sha=pr.source_sha
            )
        )

    def update_check(
        self,
        pr_number: int,
        name: str,
        state: CheckState
    ) -> None:

        pr = self.repository.pull_requests[pr_number]

        pr.checks[name] = StatusCheck(
            name=name,
            state=state,
            commit_sha=pr.source_sha
        )

    def merge(
        self,
        pr_number: int,
        merge_commit_sha: str
    ) -> MergeDecision:

        pr = self.repository.pull_requests[pr_number]

        decision = self.merge_service.evaluate(
            self.repository,
            pr
        )

        if not decision.eligible:
            return decision

        if not re.fullmatch(r"[0-9a-f]{7,64}", merge_commit_sha):
            raise ValueError("Invalid merge commit SHA")

        pr.state = PRState.MERGED

        target = self.repository.branches[pr.target_branch]
        target.head_sha = merge_commit_sha

        self.repository.commits[merge_commit_sha] = Commit(
            sha=merge_commit_sha,
            message=f"Merge pull request #{pr.number}",
            author="jenkins"
        )

        return decision


# ============================================================
# 10. SAMPLE REPOSITORY
# ============================================================

def build_sample_repository() -> Repository:

    main_sha = "a" * 40
    feature_sha = "b" * 40

    repository = Repository(
        name="payment-service",
        branches={
            "main": Branch(
                name="main",
                head_sha=main_sha,
                protected=True
            ),
            "feature/payment-validation": Branch(
                name="feature/payment-validation",
                head_sha=feature_sha
            )
        },
        protection={
            "main": BranchProtection(
                branch_name="main",
                required_reviews=2,
                required_checks=frozenset({
                    "unit-tests",
                    "security-scan",
                    "integration-tests"
                }),
                require_conversation_resolution=True,
                require_up_to_date_branch=True,
                dismiss_stale_approvals=True,
                require_code_owner_review=True
            )
        },
        eligible_reviewers={
            "reviewer-alice",
            "reviewer-bob",
            "reviewer-charlie"
        },
        code_owners={
            "reviewer-alice",
            "reviewer-charlie"
        }
    )

    repository.commits[main_sha] = Commit(
        main_sha,
        "Initial production release",
        "platform-team"
    )

    repository.commits[feature_sha] = Commit(
        feature_sha,
        "Add payment validation",
        "developer"
    )

    return repository


# ============================================================
# 11. TESTS
# ============================================================

class IntegrationTests(unittest.TestCase):

    def setUp(self):
        self.repository = build_sample_repository()
        self.workflow = RepositoryWorkflow(self.repository)

    def create_pr(self):
        commit = self.repository.commits["b" * 40]

        return self.workflow.create_pull_request(
            101,
            "feature/payment-validation",
            "main",
            [commit]
        )

    def approve_and_check(self, pr):
        for reviewer in ["reviewer-alice", "reviewer-bob"]:
            self.workflow.submit_review(
                pr.number,
                reviewer,
                ReviewState.APPROVED
            )

        for name in [
            "unit-tests",
            "security-scan",
            "integration-tests"
        ]:
            self.workflow.update_check(
                pr.number,
                name,
                CheckState.SUCCESS
            )

    def test_merge_eligible(self):
        pr = self.create_pr()
        self.approve_and_check(pr)

        decision = self.workflow.merge(
            pr.number,
            "c" * 40
        )

        self.assertTrue(decision.eligible)
        self.assertEqual(pr.state, PRState.MERGED)

    def test_missing_approval(self):
        pr = self.create_pr()

        decision = self.workflow.merge(
            pr.number,
            "c" * 40
        )

        self.assertFalse(decision.eligible)

    def test_failed_status_check(self):
        pr = self.create_pr()
        self.approve_and_check(pr)

        self.workflow.update_check(
            pr.number,
            "security-scan",
            CheckState.FAILURE
        )

        decision = self.workflow.merge(
            pr.number,
            "c" * 40
        )

        self.assertFalse(decision.eligible)

    def test_stale_approval(self):
        pr = self.create_pr()
        self.approve_and_check(pr)

        pr.source_sha = "d" * 40

        decision = self.workflow.merge(
            pr.number,
            "e" * 40
        )

        self.assertFalse(decision.eligible)

    def test_unresolved_discussion(self):
        pr = self.create_pr()
        self.approve_and_check(pr)
        pr.unresolved_discussions = 1

        decision = self.workflow.merge(
            pr.number,
            "c" * 40
        )

        self.assertFalse(decision.eligible)

    def test_webhook_signature(self):
        verifier = WebhookVerifier("production-secret-12345")
        body = b'{"ref":"refs/heads/main"}'

        signature = "sha256=" + hmac.new(
            b"production-secret-12345",
            body,
            hashlib.sha256
        ).hexdigest()

        self.assertTrue(verifier.verify(body, signature))
        self.assertFalse(verifier.verify(body, "sha256=" + "0" * 64))

    def test_duplicate_event(self):
        deduplicator = EventDeduplicator()

        self.assertTrue(deduplicator.accept("delivery-001"))
        self.assertFalse(deduplicator.accept("delivery-001"))

    def test_scm_polling(self):
        poller = SCMPoller()

        self.assertTrue(poller.poll("main", "a" * 40))
        self.assertFalse(poller.poll("main", "a" * 40))
        self.assertTrue(poller.poll("main", "b" * 40))


# ============================================================
# 12. EXECUTION
# ============================================================

def demonstrate_jenkins_integration():

    print("\n=== JENKINS + GITHUB INTEGRATION ===")

    repository = build_sample_repository()

    workflow = RepositoryWorkflow(repository)
    build_manager = JenkinsBuildManager(repository)
    processor = GitHubEventProcessor(build_manager)

    # Simulate a GitHub push webhook.
    event = processor.process(
        EventType.PUSH,
        {
            "ref": "refs/heads/feature/payment-validation",
            "after": "b" * 40
        },
        "github-delivery-001"
    )

    if event:
        build_manager.execute(event, pipeline_success=True)

    # Simulate pull request creation.
    pr = workflow.create_pull_request(
        101,
        "feature/payment-validation",
        "main",
        [repository.commits["b" * 40]]
    )

    # Simulate two independent review decisions.
    workflow.submit_review(
        101,
        "reviewer-alice",
        ReviewState.APPROVED
    )

    workflow.submit_review(
        101,
        "reviewer-bob",
        ReviewState.APPROVED
    )

    # Simulate Jenkins pipeline status checks.
    for check in [
        "unit-tests",
        "security-scan",
        "integration-tests"
    ]:
        workflow.update_check(
            101,
            check,
            CheckState.SUCCESS
        )

    decision = workflow.merge(
        101,
        "c" * 40
    )

    print("\nMerge eligibility:", decision.eligible)

    if decision.eligible:
        print("Pull Request successfully merged")
    else:
        print("Merge blocked:")
        for reason in decision.reasons:
            print(" -", reason)

    print("\nJenkins build history:")

    for build in build_manager.builds:
        print(
            f"Build #{build.build_id}: "
            f"{build.branch}, "
            f"{build.trigger.value}, "
            f"{build.status.value}"
        )


if __name__ == "__main__":
    demonstrate_jenkins_integration()

    print("\n=== AUTOMATED TESTS ===")
    unittest.main(argv=["program"], exit=False, verbosity=2)
