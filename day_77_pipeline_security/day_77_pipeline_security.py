#!/usr/bin/env python3
"""
Pipeline Security: Secrets, Permissions, and Supply-Chain Security

A self-contained pipeline security simulation covering:
- Secret storage, retrieval, masking, and rotation
- Least-privilege pipeline permissions
- Job-level permission isolation
- Dependency integrity and vulnerability evaluation
- Artifact provenance and verification
- Pipeline execution policy enforcement
- Security event auditing
- Failure handling and automated security tests

Requires Python 3.10 or later.
Uses only the Python standard library.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import re
import secrets
import unittest

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)

logger = logging.getLogger("pipeline-security")


# ============================================================
# 1. Domain Types
# ============================================================

class SecurityError(Exception):
    """Base exception for pipeline security failures."""


class SecretAccessError(SecurityError):
    pass


class PermissionDenied(SecurityError):
    pass


class SupplyChainError(SecurityError):
    pass


class PolicyViolation(SecurityError):
    pass


class PipelineState(Enum):
    CREATED = "created"
    VALIDATING = "validating"
    RUNNING = "running"
    BLOCKED = "blocked"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class Permission(Enum):
    CONTENT_READ = "contents:read"
    CONTENT_WRITE = "contents:write"
    ACTIONS_READ = "actions:read"
    ACTIONS_WRITE = "actions:write"
    DEPLOYMENTS_READ = "deployments:read"
    DEPLOYMENTS_WRITE = "deployments:write"
    PACKAGES_READ = "packages:read"
    PACKAGES_WRITE = "packages:write"
    IDENTITY_WRITE = "id-token:write"


class DependencyStatus(Enum):
    VERIFIED = "verified"
    UNVERIFIED = "unverified"
    VULNERABLE = "vulnerable"
    BLOCKED = "blocked"


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


# ============================================================
# 2. Security Audit
# ============================================================

@dataclass(frozen=True)
class AuditEvent:
    timestamp: datetime
    event_type: str
    actor: str
    resource: str
    outcome: str
    details: dict[str, Any] = field(default_factory=dict)


class AuditLogger:

    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(
        self,
        event_type: str,
        actor: str,
        resource: str,
        outcome: str,
        details: Optional[dict[str, Any]] = None
    ) -> None:

        event = AuditEvent(
            timestamp=datetime.now(timezone.utc),
            event_type=event_type,
            actor=actor,
            resource=resource,
            outcome=outcome,
            details=details or {}
        )

        self._events.append(event)

        logger.info(
            "AUDIT event=%s actor=%s resource=%s outcome=%s",
            event_type,
            actor,
            resource,
            outcome
        )

    def events(self) -> tuple[AuditEvent, ...]:
        return tuple(self._events)

    def filter_events(
        self,
        event_type: Optional[str] = None,
        outcome: Optional[str] = None
    ) -> list[AuditEvent]:

        return [
            event for event in self._events
            if (event_type is None or event.event_type == event_type)
            and (outcome is None or event.outcome == outcome)
        ]


# ============================================================
# 3. Secret Management
# ============================================================

@dataclass
class SecretRecord:
    name: str
    value: str
    version: int
    created_at: datetime
    expires_at: Optional[datetime] = None
    enabled: bool = True


class SecretManager:
    """
    Demonstration secret manager.

    Production systems should use a dedicated secret manager,
    encrypted storage, access identities, and managed rotation.

    Values are never returned through list_metadata().
    """

    def __init__(self, audit: AuditLogger) -> None:
        self._secrets: dict[str, SecretRecord] = {}
        self.audit = audit

    @staticmethod
    def _validate_name(name: str) -> None:
        if not re.fullmatch(r"[A-Z][A-Z0-9_]{1,63}", name):
            raise ValueError("Invalid secret name")

    def store(
        self,
        name: str,
        value: str,
        actor: str,
        expires_at: Optional[datetime] = None
    ) -> None:

        self._validate_name(name)

        if not value or len(value) > 16384:
            raise ValueError("Secret must contain 1 to 16384 characters")

        if expires_at is not None:
            if expires_at.tzinfo is None:
                raise ValueError("Expiration must be timezone-aware")
            if expires_at <= datetime.now(timezone.utc):
                raise ValueError("Expiration must be in the future")

        old = self._secrets.get(name)
        version = old.version + 1 if old else 1

        self._secrets[name] = SecretRecord(
            name=name,
            value=value,
            version=version,
            created_at=datetime.now(timezone.utc),
            expires_at=expires_at
        )

        self.audit.record(
            "SECRET_STORED",
            actor,
            name,
            "SUCCESS",
            {"version": version}
        )

    def retrieve(
        self,
        name: str,
        actor: str,
        allowed_secrets: set[str]
    ) -> str:

        if name not in allowed_secrets:
            self.audit.record(
                "SECRET_ACCESS",
                actor,
                name,
                "DENIED"
            )
            raise SecretAccessError(
                f"Actor {actor} cannot access {name}"
            )

        record = self._secrets.get(name)

        if record is None or not record.enabled:
            raise SecretAccessError("Secret unavailable")

        now = datetime.now(timezone.utc)

        if record.expires_at and now >= record.expires_at:
            self.audit.record(
                "SECRET_ACCESS",
                actor,
                name,
                "EXPIRED"
            )
            raise SecretAccessError("Secret has expired")

        self.audit.record(
            "SECRET_ACCESS",
            actor,
            name,
            "SUCCESS",
            {"version": record.version}
        )

        return record.value

    def rotate(
        self,
        name: str,
        new_value: str,
        actor: str
    ) -> None:

        if name not in self._secrets:
            raise SecretAccessError("Unknown secret")

        self.store(name, new_value, actor)

        self.audit.record(
            "SECRET_ROTATED",
            actor,
            name,
            "SUCCESS"
        )

    def revoke(self, name: str, actor: str) -> None:

        record = self._secrets.get(name)

        if record is None:
            raise SecretAccessError("Unknown secret")

        record.enabled = False

        self.audit.record(
            "SECRET_REVOKED",
            actor,
            name,
            "SUCCESS"
        )

    def list_metadata(self) -> list[dict[str, Any]]:

        return [
            {
                "name": record.name,
                "version": record.version,
                "enabled": record.enabled,
                "created_at": record.created_at.isoformat(),
                "expires_at": (
                    record.expires_at.isoformat()
                    if record.expires_at else None
                )
            }
            for record in self._secrets.values()
        ]

    @staticmethod
    def mask(text: str, values: list[str]) -> str:

        for value in sorted(
            set(values),
            key=len,
            reverse=True
        ):
            if value:
                text = text.replace(value, "***REDACTED***")

        return text


# ============================================================
# 4. Permission Management
# ============================================================

@dataclass(frozen=True)
class JobIdentity:
    job_name: str
    permissions: frozenset[Permission]
    allowed_secrets: frozenset[str]


class PermissionManager:

    def __init__(self, audit: AuditLogger) -> None:
        self.audit = audit

    def authorize(
        self,
        identity: JobIdentity,
        permission: Permission,
        resource: str
    ) -> bool:

        allowed = permission in identity.permissions

        self.audit.record(
            "PERMISSION_CHECK",
            identity.job_name,
            resource,
            "ALLOWED" if allowed else "DENIED",
            {"permission": permission.value}
        )

        if not allowed:
            raise PermissionDenied(
                f"{identity.job_name} lacks {permission.value}"
            )

        return True

    @staticmethod
    def validate_identity(identity: JobIdentity) -> None:

        if not identity.job_name.strip():
            raise ValueError("Job identity cannot be empty")

        if Permission.CONTENT_WRITE in identity.permissions:
            if Permission.CONTENT_READ not in identity.permissions:
                raise ValueError(
                    "Content write requires content read in this policy"
                )

        if len(identity.allowed_secrets) > 20:
            raise ValueError("Excessive secret access configuration")


# ============================================================
# 5. Dependency and Supply-Chain Security
# ============================================================

@dataclass(frozen=True)
class Dependency:
    name: str
    version: str
    expected_hash: str
    actual_hash: str
    severity: Severity = Severity.LOW
    source: str = "approved-registry"


@dataclass(frozen=True)
class DependencyAssessment:
    name: str
    version: str
    status: DependencyStatus
    reason: str


class SupplyChainScanner:

    def __init__(
        self,
        blocked_sources: Optional[set[str]] = None
    ) -> None:

        self.blocked_sources = blocked_sources or set()

    @staticmethod
    def valid_package_name(name: str) -> bool:
        return bool(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", name)
        )

    @staticmethod
    def valid_version(version: str) -> bool:
        return bool(
            re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+_-]{0,63}", version)
        )

    def assess(
        self,
        dependency: Dependency
    ) -> DependencyAssessment:

        if not self.valid_package_name(dependency.name):
            raise SupplyChainError("Invalid package name")

        if not self.valid_version(dependency.version):
            raise SupplyChainError("Invalid package version")

        if dependency.source in self.blocked_sources:
            return DependencyAssessment(
                dependency.name,
                dependency.version,
                DependencyStatus.BLOCKED,
                "Dependency source is not approved"
            )

        if not re.fullmatch(r"[a-fA-F0-9]{64}", dependency.expected_hash):
            raise SupplyChainError("Invalid expected SHA-256 hash")

        if not re.fullmatch(r"[a-fA-F0-9]{64}", dependency.actual_hash):
            raise SupplyChainError("Invalid actual SHA-256 hash")

        if not hmac.compare_digest(
            dependency.expected_hash.lower(),
            dependency.actual_hash.lower()
        ):
            return DependencyAssessment(
                dependency.name,
                dependency.version,
                DependencyStatus.UNVERIFIED,
                "Downloaded dependency does not match expected hash"
            )

        if dependency.severity in (
            Severity.HIGH,
            Severity.CRITICAL
        ):
            return DependencyAssessment(
                dependency.name,
                dependency.version,
                DependencyStatus.VULNERABLE,
                f"Known {dependency.severity.value} severity vulnerability"
            )

        return DependencyAssessment(
            dependency.name,
            dependency.version,
            DependencyStatus.VERIFIED,
            "Integrity and vulnerability policy passed"
        )

    def scan(
        self,
        dependencies: list[Dependency]
    ) -> list[DependencyAssessment]:

        names = set()
        results = []

        for dependency in dependencies:

            normalized_name = dependency.name.lower()

            if normalized_name in names:
                raise SupplyChainError(
                    f"Duplicate dependency: {dependency.name}"
                )

            names.add(normalized_name)
            results.append(self.assess(dependency))

        return results


# ============================================================
# 6. Artifact Provenance
# ============================================================

@dataclass(frozen=True)
class Artifact:
    name: str
    digest: str
    source_commit: str
    builder_identity: str
    dependencies: tuple[str, ...]
    created_at: datetime


class ProvenanceManager:
    """
    Creates and verifies demonstration artifact attestations.

    HMAC provides an integrity check when the verifier possesses
    the same trusted key. It is not a replacement for signed
    attestations and asymmetric key management in production.
    """

    def __init__(self, signing_key: bytes) -> None:

        if len(signing_key) < 32:
            raise ValueError("Signing key must contain at least 32 bytes")

        self._key = signing_key

    @staticmethod
    def canonical_payload(artifact: Artifact) -> bytes:

        data = {
            "name": artifact.name,
            "digest": artifact.digest,
            "source_commit": artifact.source_commit,
            "builder_identity": artifact.builder_identity,
            "dependencies": sorted(artifact.dependencies),
            "created_at": artifact.created_at.isoformat()
        }

        return json.dumps(
            data,
            sort_keys=True,
            separators=(",", ":")
        ).encode("utf-8")

    def create_attestation(self, artifact: Artifact) -> str:

        payload = self.canonical_payload(artifact)

        return hmac.new(
            self._key,
            payload,
            hashlib.sha256
        ).hexdigest()

    def verify(
        self,
        artifact: Artifact,
        attestation: str
    ) -> bool:

        if not re.fullmatch(r"[a-fA-F0-9]{64}", attestation):
            return False

        expected = self.create_attestation(artifact)

        return hmac.compare_digest(
            expected,
            attestation.lower()
        )


# ============================================================
# 7. Pipeline Security Policy
# ============================================================

@dataclass(frozen=True)
class PipelinePolicy:
    minimum_reviews: int = 1
    require_verified_dependencies: bool = True
    require_provenance: bool = True
    allow_untrusted_pull_requests_secrets: bool = False
    require_pinned_actions: bool = True
    maximum_permission_count: int = 5


@dataclass
class PipelineRun:
    run_id: str
    source_branch: str
    target_branch: str
    identity: JobIdentity
    is_untrusted_pull_request: bool
    reviewer_count: int
    dependencies: list[Dependency]
    artifact: Optional[Artifact] = None
    attestation: Optional[str] = None
    state: PipelineState = PipelineState.CREATED
    failure_reasons: list[str] = field(default_factory=list)


class PipelineSecurityEngine:

    def __init__(
        self,
        policy: PipelinePolicy,
        audit: AuditLogger,
        secret_manager: SecretManager,
        permission_manager: PermissionManager,
        scanner: SupplyChainScanner,
        provenance_manager: ProvenanceManager
    ) -> None:

        self.policy = policy
        self.audit = audit
        self.secret_manager = secret_manager
        self.permission_manager = permission_manager
        self.scanner = scanner
        self.provenance_manager = provenance_manager

    def validate(self, run: PipelineRun) -> list[str]:

        errors = []

        try:
            PermissionManager.validate_identity(run.identity)
        except ValueError as exc:
            errors.append(str(exc))

        if len(run.identity.permissions) > self.policy.maximum_permission_count:
            errors.append("Pipeline exceeds permission limit")

        if (
            run.is_untrusted_pull_request
            and not self.policy.allow_untrusted_pull_requests_secrets
            and run.identity.allowed_secrets
        ):
            errors.append(
                "Untrusted pull request must not receive secrets"
            )

        if run.reviewer_count < self.policy.minimum_reviews:
            errors.append("Required reviewer count not satisfied")

        if self.policy.require_verified_dependencies:

            try:
                assessments = self.scanner.scan(run.dependencies)

                for result in assessments:

                    if result.status != DependencyStatus.VERIFIED:
                        errors.append(
                            f"{result.name}: {result.reason}"
                        )

            except SupplyChainError as exc:
                errors.append(str(exc))

        if self.policy.require_provenance:

            if run.artifact is None:
                errors.append("Artifact is missing")

            elif run.attestation is None:
                errors.append("Artifact provenance is missing")

            elif not self.provenance_manager.verify(
                run.artifact,
                run.attestation
            ):
                errors.append("Artifact provenance verification failed")

        return errors

    def execute(self, run: PipelineRun) -> PipelineRun:

        if run.state != PipelineState.CREATED:
            raise PolicyViolation("Pipeline run already processed")

        run.state = PipelineState.VALIDATING

        self.audit.record(
            "PIPELINE_VALIDATION",
            run.identity.job_name,
            run.run_id,
            "STARTED"
        )

        errors = self.validate(run)

        if errors:

            run.state = PipelineState.BLOCKED
            run.failure_reasons.extend(errors)

            self.audit.record(
                "PIPELINE_VALIDATION",
                run.identity.job_name,
                run.run_id,
                "BLOCKED",
                {"reasons": errors}
            )

            return run

        run.state = PipelineState.RUNNING

        self.audit.record(
            "PIPELINE_EXECUTION",
            run.identity.job_name,
            run.run_id,
            "STARTED"
        )

        try:

            # Example of a narrowly authorized deployment action.
            self.permission_manager.authorize(
                run.identity,
                Permission.DEPLOYMENTS_WRITE,
                run.target_branch
            )

            run.state = PipelineState.SUCCEEDED

            self.audit.record(
                "PIPELINE_EXECUTION",
                run.identity.job_name,
                run.run_id,
                "SUCCESS"
            )

        except PermissionDenied as exc:

            run.state = PipelineState.FAILED
            run.failure_reasons.append(str(exc))

            self.audit.record(
                "PIPELINE_EXECUTION",
                run.identity.job_name,
                run.run_id,
                "FAILED",
                {"reason": str(exc)}
            )

        return run


# ============================================================
# 8. Pipeline Configuration Security
# ============================================================

@dataclass(frozen=True)
class ActionReference:
    name: str
    reference: str


class ConfigurationValidator:

    SHA_PATTERN = re.compile(r"^[a-fA-F0-9]{40}$")

    @classmethod
    def validate_action(
        cls,
        action: ActionReference,
        require_pinned: bool = True
    ) -> bool:

        if not action.name.strip():
            raise ValueError("Action name is required")

        if require_pinned and not cls.SHA_PATTERN.fullmatch(
            action.reference
        ):
            raise PolicyViolation(
                f"Action {action.name} must use a full commit SHA"
            )

        return True

    @staticmethod
    def reject_dangerous_interpolation(value: str) -> bool:

        dangerous_patterns = [
            r"\$\{\{\s*github\.event\.issue\.title",
            r"\$\{\{\s*github\.event\.pull_request\.title",
            r"\$\{\{\s*github\.event\.comment\.body"
        ]

        for pattern in dangerous_patterns:

            if re.search(pattern, value, flags=re.IGNORECASE):
                raise PolicyViolation(
                    "Untrusted event data must not be interpolated "
                    "directly into shell commands"
                )

        return True


# ============================================================
# 9. Demonstration and Testing
# ============================================================

def build_demo() -> tuple[PipelineSecurityEngine, AuditLogger]:

    audit = AuditLogger()

    secret_manager = SecretManager(audit)
    permission_manager = PermissionManager(audit)

    secret_manager.store(
        "PRODUCTION_TOKEN",
        secrets.token_urlsafe(32),
        "security-admin"
    )

    identity = JobIdentity(
        job_name="production-deployment",
        permissions=frozenset({
            Permission.CONTENT_READ,
            Permission.DEPLOYMENTS_WRITE
        }),
        allowed_secrets=frozenset({
            "PRODUCTION_TOKEN"
        })
    )

    scanner = SupplyChainScanner(
        blocked_sources={"untrusted-mirror"}
    )

    provenance = ProvenanceManager(
        signing_key=secrets.token_bytes(32)
    )

    artifact = Artifact(
        name="application-release",
        digest=hashlib.sha256(
            b"application-release-v1"
        ).hexdigest(),
        source_commit="a" * 40,
        builder_identity="trusted-ci-builder",
        dependencies=("framework@1.2.0",),
        created_at=datetime.now(timezone.utc)
    )

    attestation = provenance.create_attestation(artifact)

    engine = PipelineSecurityEngine(
        policy=PipelinePolicy(),
        audit=audit,
        secret_manager=secret_manager,
        permission_manager=permission_manager,
        scanner=scanner,
        provenance_manager=provenance
    )

    return engine, audit


def demonstration() -> None:

    engine, audit = build_demo()

    dependency = Dependency(
        name="framework",
        version="1.2.0",
        expected_hash=hashlib.sha256(b"framework").hexdigest(),
        actual_hash=hashlib.sha256(b"framework").hexdigest()
    )

    artifact = Artifact(
        name="application-release",
        digest=hashlib.sha256(b"release").hexdigest(),
        source_commit="a" * 40,
        builder_identity="trusted-ci-builder",
        dependencies=("framework@1.2.0",),
        created_at=datetime.now(timezone.utc)
    )

    attestation = engine.provenance_manager.create_attestation(
        artifact
    )

    identity = JobIdentity(
        job_name="production-deployment",
        permissions=frozenset({
            Permission.CONTENT_READ,
            Permission.DEPLOYMENTS_WRITE
        }),
        allowed_secrets=frozenset()
    )

    run = PipelineRun(
        run_id="RUN-1001",
        source_branch="release/1.0",
        target_branch="production",
        identity=identity,
        is_untrusted_pull_request=False,
        reviewer_count=2,
        dependencies=[dependency],
        artifact=artifact,
        attestation=attestation
    )

    result = engine.execute(run)

    print("\nPIPELINE SECURITY REPORT")
    print("=" * 50)
    print("Run ID:", result.run_id)
    print("State:", result.state.value)
    print("Source:", result.source_branch)
    print("Target:", result.target_branch)
    print("Failure reasons:", result.failure_reasons)
    print("Audit events:", len(audit.events()))

    print("\nSECURITY TEST SCENARIOS")

    # Scenario 1: Untrusted pull request cannot receive secrets.
    untrusted = PipelineRun(
        run_id="RUN-1002",
        source_branch="external/contribution",
        target_branch="main",
        identity=identity,
        is_untrusted_pull_request=True,
        reviewer_count=2,
        dependencies=[dependency],
        artifact=artifact,
        attestation=attestation
    )

    assert engine.execute(untrusted).state == PipelineState.BLOCKED

    # Scenario 2: Modified dependency fails integrity verification.
    modified = Dependency(
        name="framework",
        version="1.2.0",
        expected_hash=hashlib.sha256(b"original").hexdigest(),
        actual_hash=hashlib.sha256(b"modified").hexdigest()
    )

    assessments = engine.scanner.scan([modified])

    assert assessments[0].status == DependencyStatus.UNVERIFIED

    # Scenario 3: An expired or missing secret is rejected.
    try:
        engine.secret_manager.retrieve(
            "UNKNOWN_SECRET",
            "production-deployment",
            {"UNKNOWN_SECRET"}
        )
        raise AssertionError("Unknown secret should fail")
    except SecretAccessError:
        print("Unknown secret access: BLOCKED")

    # Scenario 4: Missing deployment permission is rejected.
    read_only = JobIdentity(
        job_name="test-job",
        permissions=frozenset({
            Permission.CONTENT_READ
        }),
        allowed_secrets=frozenset()
    )

    try:
        engine.permission_manager.authorize(
            read_only,
            Permission.DEPLOYMENTS_WRITE,
            "production"
        )
        raise AssertionError("Unauthorized deployment should fail")
    except PermissionDenied:
        print("Unauthorized deployment: BLOCKED")

    # Scenario 5: Mutable action references are rejected.
    try:
        ConfigurationValidator.validate_action(
            ActionReference("third-party-action", "v2")
        )
        raise AssertionError("Mutable action reference should fail")
    except PolicyViolation:
        print("Mutable action reference: BLOCKED")

    # Scenario 6: Direct shell interpolation of untrusted input.
    try:
        ConfigurationValidator.reject_dangerous_interpolation(
            "${{ github.event.issue.title }}"
        )
        raise AssertionError("Untrusted interpolation should fail")
    except PolicyViolation:
        print("Untrusted shell interpolation: BLOCKED")

    print("\nAll security assertions passed.")


if __name__ == "__main__":
    demonstration()
