#!/usr/bin/env python3
"""
Jenkins Credentials Management
Demonstrates credential stores, secret handling, scopes, rotation,
pipeline binding, validation, auditing, and secure configuration.

Uses simulated secrets. Never stores real credentials in source code.
"""

from __future__ import annotations

import hashlib
import re
import secrets
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from enum import Enum
from typing import Optional


class CredentialType(Enum):
    SECRET_TEXT = "secret_text"
    USERNAME_PASSWORD = "username_password"
    SSH_PRIVATE_KEY = "ssh_private_key"
    SECRET_FILE = "secret_file"
    CERTIFICATE = "certificate"


class CredentialScope(Enum):
    GLOBAL = "global"
    SYSTEM = "system"


class CredentialStatus(Enum):
    ACTIVE = "active"
    EXPIRED = "expired"
    REVOKED = "revoked"


class SecurityError(Exception):
    pass


class CredentialNotFoundError(Exception):
    pass


class ValidationError(Exception):
    pass


@dataclass
class Credential:
    credential_id: str
    description: str
    credential_type: CredentialType
    scope: CredentialScope
    owner: str
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc)
    )
    expires_at: Optional[datetime] = None
    status: CredentialStatus = CredentialStatus.ACTIVE
    version: int = 1
    fingerprint: str = ""

    def is_valid(self) -> bool:
        if self.status != CredentialStatus.ACTIVE:
            return False

        if self.expires_at and datetime.now(timezone.utc) >= self.expires_at:
            return False

        return True


@dataclass
class AuditEvent:
    timestamp: datetime
    action: str
    credential_id: str
    actor: str
    outcome: str
    details: str = ""


class SecretVault:
    """
    Demonstration-only in-memory secret provider.

    Production systems should use Jenkins Credentials Providers,
    encrypted storage, restricted controller access, and external
    secret managers where appropriate.
    """

    def __init__(self):
        self._secrets: dict[str, object] = {}

    def store(self, credential_id: str, value: object) -> None:
        if not credential_id:
            raise ValidationError("Credential ID cannot be empty")

        if value is None:
            raise ValidationError("Secret value cannot be None")

        if isinstance(value, str) and not value:
            raise ValidationError("Secret value cannot be empty")

        if isinstance(value, dict):
            if not value.get("username") or not value.get("password"):
                raise ValidationError(
                    "Username/password credentials require both fields"
                )

        self._secrets[credential_id] = value

    def retrieve(self, credential_id: str) -> object:
        if credential_id not in self._secrets:
            raise CredentialNotFoundError(credential_id)

        return self._secrets[credential_id]

    def delete(self, credential_id: str) -> None:
        self._secrets.pop(credential_id, None)

    def fingerprint(self, credential_id: str) -> str:
        value = repr(self.retrieve(credential_id))
        return hashlib.sha256(value.encode()).hexdigest()[:16]


class JenkinsCredentialManager:
    ID_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{2,63}$")

    def __init__(self):
        self.vault = SecretVault()
        self.credentials: dict[str, Credential] = {}
        self.audit_log: list[AuditEvent] = []

    def _audit(
        self,
        action: str,
        credential_id: str,
        actor: str,
        outcome: str,
        details: str = ""
    ) -> None:
        self.audit_log.append(
            AuditEvent(
                timestamp=datetime.now(timezone.utc),
                action=action,
                credential_id=credential_id,
                actor=actor,
                outcome=outcome,
                details=details
            )
        )

    def add_credential(
        self,
        credential_id: str,
        description: str,
        credential_type: CredentialType,
        scope: CredentialScope,
        owner: str,
        secret: object,
        expires_at: Optional[datetime] = None
    ) -> Credential:

        if not self.ID_PATTERN.fullmatch(credential_id):
            raise ValidationError("Invalid credential ID")

        if credential_id in self.credentials:
            raise ValidationError("Credential ID already exists")

        if not description.strip() or not owner.strip():
            raise ValidationError("Description and owner are required")

        if expires_at and expires_at <= datetime.now(timezone.utc):
            raise ValidationError("Expiration must be in the future")

        if credential_type == CredentialType.USERNAME_PASSWORD:
            if not isinstance(secret, dict):
                raise ValidationError("Expected username/password dictionary")

        elif credential_type in (
            CredentialType.SECRET_TEXT,
            CredentialType.SSH_PRIVATE_KEY,
            CredentialType.SECRET_FILE,
            CredentialType.CERTIFICATE
        ):
            if not isinstance(secret, str) or not secret:
                raise ValidationError("Expected a non-empty secret string")

        self.vault.store(credential_id, secret)

        credential = Credential(
            credential_id=credential_id,
            description=description,
            credential_type=credential_type,
            scope=scope,
            owner=owner,
            expires_at=expires_at,
            fingerprint=self.vault.fingerprint(credential_id)
        )

        self.credentials[credential_id] = credential

        self._audit(
            "CREATE",
            credential_id,
            owner,
            "SUCCESS"
        )

        return credential

    def get_metadata(self, credential_id: str) -> Credential:
        credential = self.credentials.get(credential_id)

        if not credential:
            raise CredentialNotFoundError(credential_id)

        return credential

    def resolve(
        self,
        credential_id: str,
        pipeline: str,
        actor: str,
        required_type: Optional[CredentialType] = None,
        allow_system_scope: bool = False
    ) -> object:

        credential = self.get_metadata(credential_id)

        if not credential.is_valid():
            self._audit(
                "RESOLVE",
                credential_id,
                actor,
                "DENIED",
                "Inactive or expired credential"
            )
            raise SecurityError("Credential is not active")

        if credential.scope == CredentialScope.SYSTEM and not allow_system_scope:
            self._audit(
                "RESOLVE",
                credential_id,
                actor,
                "DENIED",
                "System credential access denied"
            )
            raise SecurityError("System credential is restricted")

        if required_type and credential.credential_type != required_type:
            raise SecurityError("Credential type mismatch")

        if not pipeline.strip() or not actor.strip():
            raise ValidationError("Pipeline and actor are required")

        self._audit(
            "RESOLVE",
            credential_id,
            actor,
            "SUCCESS",
            f"Pipeline: {pipeline}"
        )

        return self.vault.retrieve(credential_id)

    def rotate(
        self,
        credential_id: str,
        new_secret: object,
        actor: str
    ) -> None:

        credential = self.get_metadata(credential_id)

        if credential.status == CredentialStatus.REVOKED:
            raise SecurityError("Revoked credentials cannot be rotated")

        if credential.credential_type == CredentialType.USERNAME_PASSWORD:
            if not isinstance(new_secret, dict):
                raise ValidationError("Expected username/password dictionary")
        elif not isinstance(new_secret, str) or not new_secret:
            raise ValidationError("Invalid replacement secret")

        self.vault.store(credential_id, new_secret)

        credential.version += 1
        credential.status = CredentialStatus.ACTIVE
        credential.fingerprint = self.vault.fingerprint(credential_id)
        credential.expires_at = None

        self._audit(
            "ROTATE",
            credential_id,
            actor,
            "SUCCESS",
            f"Version {credential.version}"
        )

    def revoke(self, credential_id: str, actor: str) -> None:
        credential = self.get_metadata(credential_id)

        credential.status = CredentialStatus.REVOKED
        self.vault.delete(credential_id)

        self._audit(
            "REVOKE",
            credential_id,
            actor,
            "SUCCESS"
        )

    def list_credentials(self) -> list[dict]:
        return [
            {
                "id": item.credential_id,
                "type": item.credential_type.value,
                "scope": item.scope.value,
                "owner": item.owner,
                "status": item.status.value,
                "version": item.version
            }
            for item in self.credentials.values()
        ]

    def audit_report(self) -> list[dict]:
        return [
            {
                "timestamp": event.timestamp.isoformat(),
                "action": event.action,
                "credential_id": event.credential_id,
                "actor": event.actor,
                "outcome": event.outcome,
                "details": event.details
            }
            for event in self.audit_log
        ]


class PipelineSecurityValidator:
    """
    Validates declarative pipeline configuration before execution.
    """

    SECRET_PATTERNS = [
        re.compile(r"(?i)(password|token|secret|api_key)\s*=\s*['\"][^'\"]+"),
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
        re.compile(r"(?i)authorization\s*:\s*bearer\s+\S+")
    ]

    def __init__(self, manager: JenkinsCredentialManager):
        self.manager = manager

    def validate_pipeline(
        self,
        pipeline_name: str,
        credential_ids: list[str]
    ) -> bool:

        if not pipeline_name.strip():
            raise ValidationError("Pipeline name is required")

        if len(credential_ids) != len(set(credential_ids)):
            raise ValidationError("Duplicate credential bindings")

        for credential_id in credential_ids:
            credential = self.manager.get_metadata(credential_id)

            if not credential.is_valid():
                raise SecurityError(
                    f"Inactive credential: {credential_id}"
                )

        return True

    def scan_configuration(self, configuration: str) -> list[str]:
        findings = []

        for pattern in self.SECRET_PATTERNS:
            if pattern.search(configuration):
                findings.append("Potential hardcoded secret detected")

        return sorted(set(findings))


class JenkinsPipeline:
    """
    Simulates temporary credential binding in a pipeline.

    Values are not printed or persisted in the pipeline configuration.
    """

    def __init__(
        self,
        manager: JenkinsCredentialManager,
        pipeline_name: str,
        actor: str
    ):
        self.manager = manager
        self.pipeline_name = pipeline_name
        self.actor = actor

    def execute_with_credentials(
        self,
        credential_id: str,
        operation,
        required_type: Optional[CredentialType] = None
    ):

        secret = self.manager.resolve(
            credential_id=credential_id,
            pipeline=self.pipeline_name,
            actor=self.actor,
            required_type=required_type
        )

        try:
            return operation(secret)
        finally:
            # Release the local reference after the operation.
            # Python cannot guarantee memory zeroization.
            secret = None


def demonstrate():
    print("=" * 65)
    print("JENKINS CREDENTIALS MANAGEMENT")
    print("=" * 65)

    manager = JenkinsCredentialManager()

    manager.add_credential(
        credential_id="github-deploy-token",
        description="GitHub deployment token",
        credential_type=CredentialType.SECRET_TEXT,
        scope=CredentialScope.GLOBAL,
        owner="devops-team",
        secret="SIMULATED_GITHUB_TOKEN_123"
    )

    manager.add_credential(
        credential_id="docker-registry",
        description="Docker registry account",
        credential_type=CredentialType.USERNAME_PASSWORD,
        scope=CredentialScope.GLOBAL,
        owner="platform-team",
        secret={
            "username": "build-user",
            "password": "SIMULATED_REGISTRY_PASSWORD"
        }
    )

    manager.add_credential(
        credential_id="production-ssh",
        description="Production deployment SSH key",
        credential_type=CredentialType.SSH_PRIVATE_KEY,
        scope=CredentialScope.SYSTEM,
        owner="infrastructure-team",
        secret="SIMULATED_PRIVATE_KEY"
    )

    print("\n1. Credential metadata")

    for item in manager.list_credentials():
        print(item)

    validator = PipelineSecurityValidator(manager)

    print("\n2. Pipeline configuration validation")

    validator.validate_pipeline(
        "release-pipeline",
        ["github-deploy-token", "docker-registry"]
    )

    print("Pipeline configuration is valid")

    print("\n3. Hardcoded secret detection")

    findings = validator.scan_configuration(
        "pipeline { stages { stage('Build') { steps { echo 'Build' } } } }"
    )

    print("Findings:", findings or "No obvious hardcoded secrets")

    print("\n4. Temporary credential binding")

    pipeline = JenkinsPipeline(
        manager,
        "release-pipeline",
        "build-agent"
    )

    result = pipeline.execute_with_credentials(
        "docker-registry",
        lambda credential: (
            f"Authenticated as {credential['username']}"
        ),
        CredentialType.USERNAME_PASSWORD
    )

    print(result)

    print("\n5. Credential rotation")

    manager.rotate(
        "github-deploy-token",
        "SIMULATED_ROTATED_TOKEN_456",
        "security-admin"
    )

    print(
        "New credential version:",
        manager.get_metadata("github-deploy-token").version
    )

    print("\n6. Restricted system credential")

    try:
        manager.resolve(
            "production-ssh",
            "release-pipeline",
            "build-agent"
        )
    except SecurityError as error:
        print("Access denied:", error)

    print("\n7. Credential revocation")

    manager.revoke(
        "github-deploy-token",
        "security-admin"
    )

    try:
        manager.resolve(
            "github-deploy-token",
            "release-pipeline",
            "build-agent"
        )
    except SecurityError as error:
        print("Access denied:", error)

    print("\n8. Audit log")

    for event in manager.audit_report():
        print(event)

    print("\n9. Automated validation tests")

    assert len(manager.credentials) == 3
    assert manager.get_metadata("github-deploy-token").version == 2
    assert (
        manager.get_metadata("github-deploy-token").status
        == CredentialStatus.REVOKED
    )

    try:
        manager.add_credential(
            "invalid id",
            "Invalid credential",
            CredentialType.SECRET_TEXT,
            CredentialScope.GLOBAL,
            "admin",
            "secret"
        )
        raise AssertionError("Invalid ID was accepted")
    except ValidationError:
        print("Invalid credential ID correctly rejected")

    try:
        manager.resolve(
            "github-deploy-token",
            "release-pipeline",
            "build-agent"
        )
        raise AssertionError("Revoked credential was accepted")
    except SecurityError:
        print("Revoked credential correctly rejected")

    print("\nAll demonstration checks passed.")


if __name__ == "__main__":
    demonstrate()
