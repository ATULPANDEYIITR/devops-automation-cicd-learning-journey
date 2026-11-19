#!/usr/bin/env python3
"""
Enterprise CI/CD Project: Multi-Stage Continuous Integration and
Continuous Delivery Platform.

Implements:
- Repository and branch management
- Pull Request lifecycle
- Code review and approval policies
- Branch protection
- Automated CI pipelines
- Build, test, security scan and artifact stages
- Deployment approvals
- Staging and production environments
- Deployment health checks and rollback
- Pipeline execution history
- Audit events and failure handling

Python 3.10+
Standard-library only.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger("enterprise-cicd")


# ============================================================
# ENUMERATIONS
# ============================================================

class PullRequestState(str, Enum):
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


class StageState(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class DeploymentState(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DEPLOYING = "deploying"
    SUCCESS = "success"
    FAILURE = "failure"
    ROLLED_BACK = "rolled_back"


class MergeStrategy(str, Enum):
    MERGE_COMMIT = "merge_commit"
    SQUASH = "squash"
    REBASE = "rebase"


# ============================================================
# EXCEPTIONS
# ============================================================

class CICDError(Exception):
    pass


class ValidationError(CICDError):
    pass


class PolicyViolation(CICDError):
    pass


class StateTransitionError(CICDError):
    pass


class PipelineError(CICDError):
    pass


# ============================================================
# UTILITIES
# ============================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def generate_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def validate_name(value: str, field_name: str) -> None:
    if not isinstance(value, str) or not re.fullmatch(
        r"[A-Za-z0-9][A-Za-z0-9._/-]{0,99}", value
    ):
        raise ValidationError(f"Invalid {field_name}: {value!r}")


def safe_json_write(path: Path, data: Any) -> None:
    """Write through a temporary file to avoid partial JSON files."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")

    with temporary.open("w", encoding="utf-8") as file:
        json.dump(data, file, indent=2, default=str)
        file.flush()

    temporary.replace(path)


# ============================================================
# DOMAIN MODELS
# ============================================================

@dataclass
class Commit:
    commit_id: str
    message: str
    author: str
    files: tuple[str, ...]
    timestamp: str = field(default_factory=utc_now)

    @classmethod
    def create(
        cls,
        message: str,
        author: str,
        files: list[str]
    ) -> "Commit":
        if not message.strip() or not author.strip():
            raise ValidationError("Commit message and author are required.")

        if not files:
            raise ValidationError("A commit must contain changed files.")

        for filename in files:
            if filename.startswith("/") or ".." in Path(filename).parts:
                raise ValidationError("Unsafe repository file path.")

        return cls(
            commit_id=generate_id("commit"),
            message=message,
            author=author,
            files=tuple(sorted(set(files)))
        )


@dataclass
class Branch:
    name: str
    head: Optional[str] = None
    protected: bool = False
    deleted: bool = False
    commits: list[str] = field(default_factory=list)


@dataclass
class Review:
    reviewer: str
    state: ReviewState
    commit_id: str
    comments: list[str] = field(default_factory=list)
    submitted_at: str = field(default_factory=utc_now)
    dismissed: bool = False


@dataclass
class PullRequest:
    pr_id: str
    source_branch: str
    target_branch: str
    author: str
    state: PullRequestState
    commits: list[str]
    reviews: list[Review] = field(default_factory=list)
    conversations_resolved: bool = False
    merge_strategy: MergeStrategy = MergeStrategy.SQUASH
    created_at: str = field(default_factory=utc_now)


@dataclass
class BranchProtection:
    required_reviews: int = 2
    required_checks: tuple[str, ...] = (
        "build",
        "unit_tests",
        "security_scan"
    )
    require_resolved_conversations: bool = True
    require_linear_history: bool = True
    allow_direct_push: bool = False
    allow_force_push: bool = False
    allow_deletion: bool = False
    dismiss_stale_approvals: bool = True
    allow_admin_bypass: bool = False


@dataclass
class StatusCheck:
    name: str
    state: CheckState
    details: str = ""
    commit_id: str = ""


@dataclass
class PipelineStage:
    name: str
    state: StageState = StageState.PENDING
    duration_seconds: float = 0.0
    output: str = ""


@dataclass
class Pipeline:
    pipeline_id: str
    repository: str
    commit_id: str
    state: PipelineState = PipelineState.QUEUED
    stages: list[PipelineStage] = field(default_factory=list)
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    artifact_hash: Optional[str] = None


@dataclass
class Deployment:
    deployment_id: str
    pipeline_id: str
    environment: Environment
    version: str
    state: DeploymentState
    approved_by: Optional[str] = None
    previous_version: Optional[str] = None
    created_at: str = field(default_factory=utc_now)


@dataclass
class AuditEvent:
    event_id: str
    actor: str
    action: str
    resource: str
    details: dict[str, Any]
    timestamp: str = field(default_factory=utc_now)


# ============================================================
# REPOSITORY SERVICE
# ============================================================

class Repository:
    def __init__(self, name: str):
        validate_name(name, "repository name")

        self.name = name
        self.branches: dict[str, Branch] = {}
        self.commits: dict[str, Commit] = {}
        self.pull_requests: dict[str, PullRequest] = {}
        self.protection: dict[str, BranchProtection] = {}
        self.audit_log: list[AuditEvent] = []

        self.create_branch("main")
        self.branches["main"].protected = True
        self.protection["main"] = BranchProtection()

    def audit(
        self,
        actor: str,
        action: str,
        resource: str,
        details: dict[str, Any]
    ) -> None:
        self.audit_log.append(
            AuditEvent(
                generate_id("event"),
                actor,
                action,
                resource,
                details
            )
        )

    def create_branch(self, name: str, base: str = "main") -> Branch:
        validate_name(name, "branch name")

        if name in self.branches and not self.branches[name].deleted:
            raise ValidationError(f"Branch already exists: {name}")

        if base not in self.branches or self.branches[base].deleted:
            raise ValidationError(f"Base branch does not exist: {base}")

        branch = Branch(
            name=name,
            head=self.branches[base].head,
            commits=list(self.branches[base].commits)
        )

        self.branches[name] = branch
        self.audit("system", "branch_created", name, {"base": base})
        return branch

    def add_commit(
        self,
        branch_name: str,
        commit: Commit,
        actor: str
    ) -> None:
        branch = self.branches.get(branch_name)

        if branch is None or branch.deleted:
            raise ValidationError("Branch does not exist.")

        if branch.protected:
            policy = self.protection[branch_name]
            if not policy.allow_direct_push:
                raise PolicyViolation("Direct push to protected branch denied.")

        if commit.commit_id in self.commits:
            raise ValidationError("Duplicate commit identifier.")

        self.commits[commit.commit_id] = commit
        branch.commits.append(commit.commit_id)
        branch.head = commit.commit_id

        self.audit(actor, "commit_added", branch_name, {
            "commit_id": commit.commit_id
        })

    def configure_protection(
        self,
        branch_name: str,
        policy: BranchProtection
    ) -> None:
        if branch_name not in self.branches:
            raise ValidationError("Unknown branch.")

        if policy.required_reviews < 0:
            raise ValidationError("Required reviews cannot be negative.")

        self.branches[branch_name].protected = True
        self.protection[branch_name] = policy

        self.audit("administrator", "protection_updated", branch_name, {
            "required_reviews": policy.required_reviews,
            "required_checks": policy.required_checks
        })

    def delete_branch(self, branch_name: str) -> None:
        branch = self.branches.get(branch_name)

        if branch is None or branch.deleted:
            raise ValidationError("Branch does not exist.")

        if branch.protected:
            policy = self.protection[branch_name]
            if not policy.allow_deletion:
                raise PolicyViolation("Protected branch deletion denied.")

        branch.deleted = True
        self.audit("administrator", "branch_deleted", branch_name, {})

    def create_pull_request(
        self,
        source: str,
        target: str,
        author: str,
        draft: bool = False
    ) -> PullRequest:
        if source == target:
            raise ValidationError("Source and target branches must differ.")

        for name in (source, target):
            if name not in self.branches or self.branches[name].deleted:
                raise ValidationError(f"Unknown branch: {name}")

        source_branch = self.branches[source]
        target_branch = self.branches[target]

        if source_branch.head == target_branch.head:
            raise ValidationError("No proposed changes exist.")

        source_commits = set(source_branch.commits)
        target_commits = set(target_branch.commits)

        proposed = [
            commit_id
            for commit_id in source_branch.commits
            if commit_id not in target_commits
        ]

        if not proposed:
            raise ValidationError("No commits unique to source branch.")

        pr = PullRequest(
            pr_id=generate_id("pr"),
            source_branch=source,
            target_branch=target,
            author=author,
            state=(
                PullRequestState.DRAFT
                if draft else PullRequestState.OPEN
            ),
            commits=proposed
        )

        self.pull_requests[pr.pr_id] = pr

        self.audit(author, "pull_request_created", pr.pr_id, {
            "source": source,
            "target": target,
            "proposed_commits": proposed
        })

        return pr

    def add_review(
        self,
        pr_id: str,
        reviewer: str,
        state: ReviewState,
        comments: Optional[list[str]] = None
    ) -> Review:
        pr = self.get_open_pr(pr_id)

        if reviewer == pr.author:
            raise PolicyViolation("Authors cannot approve their own PR.")

        if not reviewer.strip():
            raise ValidationError("Reviewer identity is required.")

        current_head = self.branches[pr.source_branch].head

        review = Review(
            reviewer=reviewer,
            state=state,
            commit_id=current_head or "",
            comments=comments or []
        )

        pr.reviews.append(review)

        self.audit(reviewer, "review_submitted", pr_id, {
            "state": state.value,
            "commit_id": review.commit_id
        })

        return review

    def resolve_conversations(self, pr_id: str) -> None:
        pr = self.get_open_pr(pr_id)
        pr.conversations_resolved = True

        self.audit("maintainer", "conversations_resolved", pr_id, {})

    def reopen_pull_request(self, pr_id: str) -> None:
        pr = self.pull_requests.get(pr_id)

        if pr is None or pr.state != PullRequestState.CLOSED:
            raise StateTransitionError("Only closed PRs can be reopened.")

        pr.state = PullRequestState.OPEN
        self.audit("maintainer", "pull_request_reopened", pr_id, {})

    def close_pull_request(self, pr_id: str) -> None:
        pr = self.get_open_pr(pr_id)
        pr.state = PullRequestState.CLOSED
        self.audit("maintainer", "pull_request_closed", pr_id, {})

    def get_open_pr(self, pr_id: str) -> PullRequest:
        pr = self.pull_requests.get(pr_id)

        if pr is None or pr.state != PullRequestState.OPEN:
            raise StateTransitionError("Pull Request is not open.")

        return pr


# ============================================================
# MERGE ELIGIBILITY SERVICE
# ============================================================

class MergeEligibilityService:

    @staticmethod
    def evaluate(
        repository: Repository,
        pr_id: str,
        checks: list[StatusCheck]
    ) -> tuple[bool, list[str]]:
        pr = repository.get_open_pr(pr_id)
        policy = repository.protection.get(pr.target_branch)

        if policy is None:
            return True, []

        reasons: list[str] = []

        latest_head = repository.branches[pr.source_branch].head

        # An approval against an older source commit is stale.
        approvals: dict[str, Review] = {}

        for review in pr.reviews:
            if review.dismissed:
                continue

            if review.commit_id != latest_head:
                continue

            if review.state == ReviewState.CHANGES_REQUESTED:
                reasons.append(
                    f"Changes requested by {review.reviewer}"
                )

            elif review.state == ReviewState.APPROVED:
                approvals[review.reviewer] = review

        if len(approvals) < policy.required_reviews:
            reasons.append(
                f"Requires {policy.required_reviews} valid approvals; "
                f"found {len(approvals)}"
            )

        if policy.require_resolved_conversations:
            if not pr.conversations_resolved:
                reasons.append("Unresolved review conversations.")

        check_map = {
            check.name: check for check in checks
            if check.commit_id == latest_head
        }

        for required in policy.required_checks:
            check = check_map.get(required)

            if check is None:
                reasons.append(f"Missing check: {required}")
            elif check.state != CheckState.SUCCESS:
                reasons.append(f"Check not successful: {required}")

        if not pr.commits:
            reasons.append("Pull Request has no changes.")

        return not reasons, reasons


# ============================================================
# PIPELINE ENGINE
# ============================================================

class PipelineEngine:
    def __init__(self, repository: Repository):
        self.repository = repository
        self.pipelines: dict[str, Pipeline] = {}
        self.status_checks: list[StatusCheck] = []

        self.stage_handlers = {
            "checkout": self.checkout,
            "build": self.build,
            "unit_tests": self.unit_tests,
            "integration_tests": self.integration_tests,
            "security_scan": self.security_scan,
            "package": self.package
        }

    def checkout(self, pipeline: Pipeline) -> str:
        commit = self.repository.commits[pipeline.commit_id]
        return f"Checked out commit {commit.commit_id}"

    def build(self, pipeline: Pipeline) -> str:
        if pipeline.commit_id not in self.repository.commits:
            raise PipelineError("Source commit unavailable.")

        return "Application build completed."

    def unit_tests(self, pipeline: Pipeline) -> str:
        commit = self.repository.commits[pipeline.commit_id]

        if not commit.files:
            raise PipelineError("No testable source files.")

        return "Unit tests passed: 42/42."

    def integration_tests(self, pipeline: Pipeline) -> str:
        return "Integration tests passed: 18/18."

    def security_scan(self, pipeline: Pipeline) -> str:
        commit = self.repository.commits[pipeline.commit_id]

        prohibited = {
            ".env",
            "private.key",
            "id_rsa",
            "credentials.json"
        }

        found = prohibited.intersection(
            {Path(filename).name for filename in commit.files}
        )

        if found:
            raise PipelineError(
                f"Potential sensitive files detected: {sorted(found)}"
            )

        return "Dependency and source security checks passed."

    def package(self, pipeline: Pipeline) -> str:
        digest = hashlib.sha256(
            pipeline.commit_id.encode("utf-8")
        ).hexdigest()

        pipeline.artifact_hash = digest
        return f"Artifact SHA-256: {digest}"

    def execute(self, commit_id: str) -> Pipeline:
        if commit_id not in self.repository.commits:
            raise ValidationError("Unknown commit.")

        pipeline = Pipeline(
            pipeline_id=generate_id("pipeline"),
            repository=self.repository.name,
            commit_id=commit_id,
            stages=[
                PipelineStage(name)
                for name in self.stage_handlers
            ]
        )

        self.pipelines[pipeline.pipeline_id] = pipeline
        pipeline.state = PipelineState.RUNNING
        pipeline.started_at = utc_now()

        logger.info("Starting pipeline %s", pipeline.pipeline_id)

        for stage in pipeline.stages:
            stage.state = StageState.RUNNING
            start = time.perf_counter()

            try:
                handler = self.stage_handlers[stage.name]
                stage.output = handler(pipeline)
                stage.state = StageState.SUCCESS

            except Exception as exc:
                stage.state = StageState.FAILURE
                stage.output = str(exc)
                pipeline.state = PipelineState.FAILURE

                logger.exception("Pipeline stage failed: %s", stage.name)

            finally:
                stage.duration_seconds = (
                    time.perf_counter() - start
                )

            self.status_checks.append(
                StatusCheck(
                    name=stage.name,
                    state=(
                        CheckState.SUCCESS
                        if stage.state == StageState.SUCCESS
                        else CheckState.FAILURE
                    ),
                    details=stage.output,
                    commit_id=commit_id
                )
            )

            if stage.state == StageState.FAILURE:
                for remaining in pipeline.stages:
                    if remaining.state == StageState.PENDING:
                        remaining.state = StageState.SKIPPED
                break

        if pipeline.state != PipelineState.FAILURE:
            pipeline.state = PipelineState.SUCCESS

        pipeline.completed_at = utc_now()

        logger.info(
            "Pipeline %s finished with %s",
            pipeline.pipeline_id,
            pipeline.state.value
        )

        return pipeline


# ============================================================
# DEPLOYMENT SERVICE
# ============================================================

class DeploymentService:
    def __init__(self):
        self.deployments: dict[str, Deployment] = {}
        self.current_versions: dict[Environment, str] = {
            Environment.DEVELOPMENT: "0.0.0",
            Environment.STAGING: "0.0.0",
            Environment.PRODUCTION: "0.0.0"
        }

    def request_deployment(
        self,
        pipeline: Pipeline,
        environment: Environment,
        version: str
    ) -> Deployment:
        if pipeline.state != PipelineState.SUCCESS:
            raise PolicyViolation(
                "Only successful pipelines can be deployed."
            )

        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            raise ValidationError("Version must use semantic version format.")

        deployment = Deployment(
            deployment_id=generate_id("deploy"),
            pipeline_id=pipeline.pipeline_id,
            environment=environment,
            version=version,
            state=DeploymentState.PENDING,
            previous_version=self.current_versions[environment]
        )

        self.deployments[deployment.deployment_id] = deployment
        return deployment

    def approve(
        self,
        deployment_id: str,
        approver: str,
        role: str
    ) -> Deployment:
        deployment = self.deployments.get(deployment_id)

        if deployment is None:
            raise ValidationError("Deployment not found.")

        if deployment.state != DeploymentState.PENDING:
            raise StateTransitionError("Deployment is not pending.")

        if not approver.strip():
            raise ValidationError("Approver identity is required.")

        if deployment.environment == Environment.PRODUCTION:
            if role not in {"release_manager", "platform_admin"}:
                raise PolicyViolation(
                    "Production deployment requires an authorized approver."
                )

        deployment.approved_by = approver
        deployment.state = DeploymentState.APPROVED

        return deployment

    def deploy(
        self,
        deployment_id: str,
        health_check_passed: bool = True
    ) -> Deployment:
        deployment = self.deployments.get(deployment_id)

        if deployment is None:
            raise ValidationError("Deployment not found.")

        if deployment.state != DeploymentState.APPROVED:
            raise PolicyViolation("Deployment requires approval.")

        deployment.state = DeploymentState.DEPLOYING

        try:
            if not health_check_passed:
                raise PipelineError("Post-deployment health check failed.")

            self.current_versions[deployment.environment] = (
                deployment.version
            )
            deployment.state = DeploymentState.SUCCESS

        except PipelineError:
            self.current_versions[deployment.environment] = (
                deployment.previous_version or "0.0.0"
            )
            deployment.state = DeploymentState.ROLLED_BACK
            logger.error("Deployment rolled back: %s", deployment_id)

        return deployment


# ============================================================
# REPORTING
# ============================================================

def print_pipeline_report(pipeline: Pipeline) -> None:
    print("\nPIPELINE REPORT")
    print("=" * 65)
    print("Pipeline:", pipeline.pipeline_id)
    print("Commit:", pipeline.commit_id)
    print("State:", pipeline.state.value)

    for stage in pipeline.stages:
        print(
            f"{stage.name:20} "
            f"{stage.state.value:10} "
            f"{stage.duration_seconds:.6f}s"
        )

    print("Artifact:", pipeline.artifact_hash or "Not generated")


def export_audit(repository: Repository, filename: str) -> None:
    safe_json_write(
        Path(filename),
        [asdict(event) for event in repository.audit_log]
    )


# ============================================================
# END-TO-END EXECUTION
# ============================================================

def run_demo() -> None:
    print("\nENTERPRISE MULTI-STAGE CI/CD PLATFORM")
    print("=" * 65)

    repository = Repository("enterprise-platform")

    # Repository development workflow.
    repository.create_branch("feature/payment-api")

    commit = Commit.create(
        message="Implement payment API validation",
        author="developer-01",
        files=[
            "src/payment.py",
            "tests/test_payment.py",
            "requirements.txt"
        ]
    )

    repository.add_commit(
        "feature/payment-api",
        commit,
        "developer-01"
    )

    pr = repository.create_pull_request(
        "feature/payment-api",
        "main",
        "developer-01"
    )

    print("\nPull Request:", pr.pr_id)

    # Code review is separate from merge enforcement.
    repository.add_review(
        pr.pr_id,
        "reviewer-01",
        ReviewState.APPROVED
    )

    repository.add_review(
        pr.pr_id,
        "reviewer-02",
        ReviewState.APPROVED
    )

    repository.resolve_conversations(pr.pr_id)

    # CI pipeline.
    engine = PipelineEngine(repository)
    pipeline = engine.execute(commit.commit_id)

    print_pipeline_report(pipeline)

    # Merge eligibility uses approvals, discussions and CI checks.
    eligible, reasons = MergeEligibilityService.evaluate(
        repository,
        pr.pr_id,
        engine.status_checks
    )

    print("\nMERGE ELIGIBILITY")
    print("Eligible:", eligible)

    for reason in reasons:
        print("Blocked:", reason)

    if eligible:
        target = repository.branches[pr.target_branch]
        source = repository.branches[pr.source_branch]

        # The target receives the proposed changes only after
        # all repository-level merge conditions have passed.
        target.commits.extend(
            cid for cid in pr.commits if cid not in target.commits
        )
        target.head = source.head
        pr.state = PullRequestState.MERGED

        repository.audit(
            "maintainer",
            "pull_request_merged",
            pr.pr_id,
            {"strategy": pr.merge_strategy.value}
        )

    # Deployment workflow.
    deployment_service = DeploymentService()

    staging = deployment_service.request_deployment(
        pipeline,
        Environment.STAGING,
        "1.0.0"
    )

    deployment_service.approve(
        staging.deployment_id,
        "release-operator",
        "release_manager"
    )

    deployment_service.deploy(staging.deployment_id)

    production = deployment_service.request_deployment(
        pipeline,
        Environment.PRODUCTION,
        "1.0.0"
    )

    deployment_service.approve(
        production.deployment_id,
        "production-release-manager",
        "release_manager"
    )

    # Demonstrate automatic rollback after a failed health check.
    deployment_service.deploy(
        production.deployment_id,
        health_check_passed=False
    )

    print("\nDEPLOYMENT REPORT")
    print("=" * 65)

    for deployment in deployment_service.deployments.values():
        print(
            deployment.environment.value,
            deployment.version,
            deployment.state.value
        )

    print("\nCURRENT ENVIRONMENT VERSIONS")

    for environment, version in deployment_service.current_versions.items():
        print(environment.value, ":", version)

    export_audit(repository, "cicd_audit.json")

    print("\nAudit log exported to cicd_audit.json")
    print("Pull Request final state:", pr.state.value)


if __name__ == "__main__":
    try:
        run_demo()
    except CICDError as error:
        logger.error("CI/CD execution error: %s", error)
        raise SystemExit(1)
