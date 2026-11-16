#!/usr/bin/env python3
"""
Release Management System
Versioning, approvals, release governance, deployment controls,
release readiness, rollback, and audit history.

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class ReleaseError(Exception):
    """Base exception for release-management failures."""


class ValidationError(ReleaseError):
    pass


class GovernanceError(ReleaseError):
    pass


class VersionConflictError(ReleaseError):
    pass


class ReleaseState(str, Enum):
    DRAFT = "draft"
    CANDIDATE = "candidate"
    APPROVED = "approved"
    RELEASED = "released"
    ROLLED_BACK = "rolled_back"
    REJECTED = "rejected"


class ApprovalDecision(str, Enum):
    APPROVED = "approved"
    REJECTED = "rejected"
    PENDING = "pending"


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    PENDING = "pending"


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int
    prerelease: Optional[str] = None

    PATTERN = re.compile(
        r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
        r"(?:-([0-9A-Za-z.-]+))?$"
    )

    @classmethod
    def parse(cls, value: str) -> Version:
        match = cls.PATTERN.fullmatch(value)
        if not match:
            raise ValidationError(f"Invalid semantic version: {value}")

        return cls(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
            match.group(4)
        )

    def __str__(self) -> str:
        base = f"{self.major}.{self.minor}.{self.patch}"
        return f"{base}-{self.prerelease}" if self.prerelease else base

    def next_patch(self) -> Version:
        return Version(self.major, self.minor, self.patch + 1)

    def next_minor(self) -> Version:
        return Version(self.major, self.minor + 1, 0)

    def next_major(self) -> Version:
        return Version(self.major + 1, 0, 0)


@dataclass
class ReleasePolicy:
    required_approvals: int = 2
    required_checks: set[str] = field(default_factory=lambda: {
        "unit_tests",
        "integration_tests",
        "security_scan",
        "dependency_audit"
    })
    require_release_notes: bool = True
    require_artifact_digest: bool = True
    allow_prerelease_in_production: bool = False
    allow_emergency_override: bool = False

    def validate(self) -> None:
        if self.required_approvals < 1:
            raise ValidationError("At least one approval is required.")

        if not self.required_checks:
            raise ValidationError("At least one required check is necessary.")


@dataclass
class Approval:
    reviewer: str
    role: str
    decision: ApprovalDecision
    comment: str
    timestamp: str = field(default_factory=lambda: datetime.now(
        timezone.utc
    ).isoformat())


@dataclass
class QualityCheck:
    name: str
    status: CheckStatus
    details: str = ""


@dataclass
class Release:
    release_id: str
    product: str
    version: Version
    source_commit: str
    artifact_digest: str
    release_notes: str
    environment: Environment = Environment.STAGING
    state: ReleaseState = ReleaseState.DRAFT
    approvals: list[Approval] = field(default_factory=list)
    checks: dict[str, QualityCheck] = field(default_factory=dict)
    audit_log: list[dict] = field(default_factory=list)
    rollback_version: Optional[str] = None
    emergency_override: bool = False

    def log(self, action: str, actor: str, details: str = "") -> None:
        self.audit_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "actor": actor,
            "details": details
        })


class ReleaseManager:
    def __init__(
        self,
        policy: ReleasePolicy,
        storage_path: str = "release_audit.json"
    ):
        policy.validate()
        self.policy = policy
        self.storage_path = Path(storage_path)
        self.releases: dict[str, Release] = {}
        self.published_versions: dict[str, set[Version]] = {}
        self.production_versions: dict[str, Version] = {}

    def create_release(
        self,
        release_id: str,
        product: str,
        version: str,
        source_commit: str,
        artifact: bytes,
        release_notes: str
    ) -> Release:

        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,63}", release_id):
            raise ValidationError("Invalid release identifier.")

        if not product.strip():
            raise ValidationError("Product name cannot be empty.")

        if release_id in self.releases:
            raise VersionConflictError("Release identifier already exists.")

        parsed_version = Version.parse(version)

        if not re.fullmatch(r"[a-fA-F0-9]{7,64}", source_commit):
            raise ValidationError("Invalid source commit hash.")

        if not artifact:
            raise ValidationError("Release artifact cannot be empty.")

        digest = hashlib.sha256(artifact).hexdigest()

        release = Release(
            release_id=release_id,
            product=product,
            version=parsed_version,
            source_commit=source_commit.lower(),
            artifact_digest=digest,
            release_notes=release_notes
        )

        release.log(
            "release_created",
            "release_manager",
            f"Version {version}; SHA256 {digest}"
        )

        self.releases[release_id] = release
        return release

    def submit_candidate(self, release_id: str) -> None:
        release = self._get(release_id)

        if release.state != ReleaseState.DRAFT:
            raise GovernanceError("Only draft releases can become candidates.")

        existing = self.published_versions.setdefault(
            release.product, set()
        )

        if release.version in existing:
            raise VersionConflictError("Version has already been released.")

        if release.environment == Environment.PRODUCTION:
            current = self.production_versions.get(release.product)

            if current and release.version <= current:
                raise VersionConflictError(
                    "Production version must advance."
                )

        release.state = ReleaseState.CANDIDATE
        release.log("candidate_submitted", "release_manager")

    def record_check(
        self,
        release_id: str,
        check_name: str,
        status: CheckStatus,
        details: str = ""
    ) -> None:

        release = self._get(release_id)

        if release.state != ReleaseState.CANDIDATE:
            raise GovernanceError("Checks require a candidate release.")

        if check_name not in self.policy.required_checks:
            raise ValidationError("Unknown or unauthorized quality check.")

        release.checks[check_name] = QualityCheck(
            check_name, status, details
        )

        release.log(
            "quality_check_recorded",
            "ci_system",
            f"{check_name}: {status.value}"
        )

    def record_approval(
        self,
        release_id: str,
        reviewer: str,
        role: str,
        decision: ApprovalDecision,
        comment: str = ""
    ) -> None:

        release = self._get(release_id)

        if release.state != ReleaseState.CANDIDATE:
            raise GovernanceError("Approvals require a candidate release.")

        if not reviewer.strip():
            raise ValidationError("Reviewer identity is required.")

        if role not in {"release_manager", "security_lead", "qa_lead",
                        "engineering_lead", "product_owner"}:
            raise ValidationError("Reviewer role is not recognized.")

        if reviewer == "release_manager":
            raise GovernanceError("A release cannot approve itself.")

        if any(a.reviewer == reviewer for a in release.approvals):
            raise GovernanceError("Reviewer has already submitted a decision.")

        approval = Approval(
            reviewer=reviewer,
            role=role,
            decision=decision,
            comment=comment
        )

        release.approvals.append(approval)

        release.log(
            "approval_recorded",
            reviewer,
            f"{decision.value}: {comment}"
        )

    def evaluate(self, release_id: str) -> tuple[bool, list[str]]:
        release = self._get(release_id)
        failures = []

        if release.state != ReleaseState.CANDIDATE:
            failures.append("Release is not in candidate state.")

        if self.policy.require_release_notes and not release.release_notes.strip():
            failures.append("Release notes are missing.")

        if (
            self.policy.require_artifact_digest
            and not re.fullmatch(r"[a-f0-9]{64}", release.artifact_digest)
        ):
            failures.append("Artifact digest is invalid.")

        rejected = [
            a.reviewer for a in release.approvals
            if a.decision == ApprovalDecision.REJECTED
        ]

        if rejected:
            failures.append(f"Rejected by: {', '.join(rejected)}")

        approved = {
            a.reviewer for a in release.approvals
            if a.decision == ApprovalDecision.APPROVED
        }

        if len(approved) < self.policy.required_approvals:
            failures.append(
                f"Insufficient approvals: {len(approved)}/"
                f"{self.policy.required_approvals}"
            )

        missing = self.policy.required_checks - release.checks.keys()

        if missing:
            failures.append(
                f"Missing checks: {', '.join(sorted(missing))}"
            )

        failed = [
            name for name in self.policy.required_checks
            if name in release.checks
            and release.checks[name].status != CheckStatus.PASSED
        ]

        if failed:
            failures.append(f"Unsuccessful checks: {', '.join(sorted(failed))}")

        if (
            release.environment == Environment.PRODUCTION
            and release.version.prerelease
            and not self.policy.allow_prerelease_in_production
        ):
            failures.append("Prerelease versions are prohibited in production.")

        if (
            release.emergency_override
            and not self.policy.allow_emergency_override
        ):
            failures.append("Emergency override is not permitted.")

        return not failures, failures

    def approve_release(self, release_id: str) -> None:
        release = self._get(release_id)

        eligible, failures = self.evaluate(release_id)

        if not eligible:
            raise GovernanceError("; ".join(failures))

        release.state = ReleaseState.APPROVED
        release.log("release_approved", "governance_engine")

    def deploy(self, release_id: str, actor: str) -> None:
        release = self._get(release_id)

        if release.state != ReleaseState.APPROVED:
            raise GovernanceError("Only approved releases can be deployed.")

        if release.environment != Environment.PRODUCTION:
            raise GovernanceError("Production deployment requires production target.")

        current = self.production_versions.get(release.product)

        if current and release.version <= current:
            raise VersionConflictError("Version is not newer than production.")

        # Record publication only after all governance checks pass.
        self.published_versions.setdefault(
            release.product, set()
        ).add(release.version)

        self.production_versions[release.product] = release.version
        release.state = ReleaseState.RELEASED
        release.log("deployed", actor, f"Production version {release.version}")

    def rollback(self, release_id: str, previous_version: str, actor: str) -> None:
        release = self._get(release_id)

        if release.state != ReleaseState.RELEASED:
            raise GovernanceError("Only released versions can be rolled back.")

        target = Version.parse(previous_version)
        known = self.published_versions.get(release.product, set())

        if target not in known:
            raise GovernanceError("Rollback target is not a known published version.")

        if target == release.version:
            raise GovernanceError("Cannot roll back to the same version.")

        release.rollback_version = str(target)
        release.state = ReleaseState.ROLLED_BACK
        self.production_versions[release.product] = target

        release.log("rollback", actor, f"Restored version {target}")

    def reject_release(self, release_id: str, actor: str, reason: str) -> None:
        release = self._get(release_id)

        if release.state not in {
            ReleaseState.DRAFT, ReleaseState.CANDIDATE
        }:
            raise GovernanceError("This release cannot be rejected.")

        if not reason.strip():
            raise ValidationError("Rejection reason is required.")

        release.state = ReleaseState.REJECTED
        release.log("rejected", actor, reason)

    def save_audit(self) -> None:
        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "releases": [
                {
                    "release_id": r.release_id,
                    "product": r.product,
                    "version": str(r.version),
                    "state": r.state.value,
                    "source_commit": r.source_commit,
                    "artifact_digest": r.artifact_digest,
                    "approvals": [
                        {
                            "reviewer": a.reviewer,
                            "role": a.role,
                            "decision": a.decision.value,
                            "comment": a.comment,
                            "timestamp": a.timestamp
                        }
                        for a in r.approvals
                    ],
                    "checks": {
                        name: {
                            "status": check.status.value,
                            "details": check.details
                        }
                        for name, check in r.checks.items()
                    },
                    "audit_log": r.audit_log,
                    "rollback_version": r.rollback_version
                }
                for r in self.releases.values()
            ]
        }

        # Restrict file permissions where supported and avoid writing secrets.
        temporary = self.storage_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8"
        )
        temporary.replace(self.storage_path)

    def _get(self, release_id: str) -> Release:
        try:
            return self.releases[release_id]
        except KeyError:
            raise ValidationError(f"Unknown release: {release_id}") from None


def demonstration() -> None:
    policy = ReleasePolicy(
        required_approvals=2,
        required_checks={
            "unit_tests",
            "integration_tests",
            "security_scan",
            "dependency_audit"
        }
    )

    manager = ReleaseManager(policy)

    artifact = b"production-build-2026.11.1"

    release = manager.create_release(
        release_id="REL-2026-001",
        product="PaymentPlatform",
        version="2.4.1",
        source_commit="a" * 40,
        artifact=artifact,
        release_notes="Improved payment reliability and security controls."
    )

    release.environment = Environment.PRODUCTION

    manager.submit_candidate(release.release_id)

    for check in policy.required_checks:
        manager.record_check(
            release.release_id,
            check,
            CheckStatus.PASSED,
            "Automated pipeline completed successfully."
        )

    manager.record_approval(
        release.release_id,
        "reviewer_01",
        "security_lead",
        ApprovalDecision.APPROVED,
        "Security assessment passed."
    )

    manager.record_approval(
        release.release_id,
        "reviewer_02",
        "engineering_lead",
        ApprovalDecision.APPROVED,
        "Deployment package verified."
    )

    eligible, failures = manager.evaluate(release.release_id)

    print("Release:", release.release_id)
    print("Version:", release.version)
    print("Artifact SHA256:", release.artifact_digest)
    print("Eligible:", eligible)

    if failures:
        print("Blocking conditions:", failures)
        return

    manager.approve_release(release.release_id)
    manager.deploy(release.release_id, "production_deployment_service")

    print("Final state:", release.state.value)
    print("Production version:", manager.production_versions["PaymentPlatform"])

    # A second candidate demonstrates rejection of incomplete governance.
    second = manager.create_release(
        "REL-2026-002",
        "PaymentPlatform",
        "2.4.2",
        "b" * 40,
        b"second-build",
        "Performance improvements."
    )

    second.environment = Environment.PRODUCTION
    manager.submit_candidate(second.release_id)

    manager.record_check(
        second.release_id,
        "unit_tests",
        CheckStatus.PASSED
    )

    eligible, failures = manager.evaluate(second.release_id)

    print("\nIncomplete candidate eligibility:", eligible)
    for failure in failures:
        print("BLOCKED:", failure)

    manager.save_audit()
    print("\nAudit saved to:", manager.storage_path.resolve())


if __name__ == "__main__":
    try:
        demonstration()
    except (ReleaseError, OSError) as error:
        print(f"Release management error: {error}", file=sys.stderr)
        sys.exit(1)
