#!/usr/bin/env python3
"""
Actions Secrets: secrets, credentials, and secure configuration.

This self-contained program models a GitHub Actions-style secret-management
workflow without contacting GitHub. It demonstrates:

- Repository, environment, and organization secret scopes
- Secret-name validation
- Secret values kept out of normal output
- Masking sensitive values in logs
- Environment-specific configuration
- Credential rotation
- Secret usage auditing
- Permission-aware access
- Detection of unsafe configuration
- Merge/deployment policy checks involving secret configuration
- Secure handling of temporary credentials
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
import hashlib
import hmac
import re
import secrets as crypto_secrets
from typing import Dict, Iterable, List, Optional, Set, Tuple


class SecretScope(str, Enum):
    ORGANIZATION = "organization"
    REPOSITORY = "repository"
    ENVIRONMENT = "environment"


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class AccessLevel(str, Enum):
    READ = "read"
    WRITE = "write"
    ADMIN = "admin"


@dataclass(frozen=True)
class Actor:
    username: str
    access: AccessLevel
    repositories: Set[str] = field(default_factory=set)
    environments: Set[str] = field(default_factory=set)


@dataclass
class SecretRecord:
    name: str
    scope: SecretScope
    value: str
    repository: Optional[str] = None
    environment: Optional[str] = None
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rotated_at: Optional[datetime] = None
    expires_at: Optional[datetime] = None
    active: bool = True

    def metadata(self) -> dict:
        # The actual secret value is intentionally absent from metadata.
        return {
            "name": self.name,
            "scope": self.scope.value,
            "repository": self.repository,
            "environment": self.environment,
            "created_at": self.created_at.isoformat(),
            "rotated_at": self.rotated_at.isoformat() if self.rotated_at else None,
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "active": self.active,
        }


@dataclass
class AuditEvent:
    timestamp: datetime
    actor: str
    action: str
    secret_name: str
    scope: str
    repository: Optional[str]
    environment: Optional[str]
    result: str


class SecretValidationError(ValueError):
    """Raised when a secret violates the secret-management policy."""


class SecretAccessError(PermissionError):
    """Raised when an actor cannot access a requested secret."""


class SecretManager:
    """
    In-memory secret manager used to demonstrate secure configuration.

    A production system would normally delegate secret storage to a managed
    secret store. The important design property is that application logs and
    normal configuration metadata never need to contain plaintext secrets.
    """

    SECRET_NAME_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,99}$")

    def __init__(self) -> None:
        self._secrets: Dict[Tuple[str, str, Optional[str], Optional[str]], SecretRecord] = {}
        self._audit: List[AuditEvent] = []

    @staticmethod
    def _key(record: SecretRecord) -> Tuple[str, str, Optional[str], Optional[str]]:
        return (
            record.scope.value,
            record.name,
            record.repository,
            record.environment,
        )

    def _audit_event(
        self,
        actor: Actor,
        action: str,
        record: SecretRecord,
        result: str,
    ) -> None:
        self._audit.append(
            AuditEvent(
                timestamp=datetime.now(timezone.utc),
                actor=actor.username,
                action=action,
                secret_name=record.name,
                scope=record.scope.value,
                repository=record.repository,
                environment=record.environment,
                result=result,
            )
        )

    def validate_name(self, name: str) -> None:
        if not self.SECRET_NAME_PATTERN.fullmatch(name):
            raise SecretValidationError(
                "Secret names must start with an uppercase letter and contain "
                "only uppercase letters, digits, and underscores."
            )

        reserved = {"PASSWORD", "SECRET", "TOKEN", "KEY"}
        if name in reserved:
            raise SecretValidationError(
                f"{name} is too generic. Use a specific purpose-oriented name."
            )

    @staticmethod
    def validate_value(value: str) -> None:
        if not value:
            raise SecretValidationError("Secret value cannot be empty.")
        if len(value) < 12:
            raise SecretValidationError(
                "This demonstration requires secrets to contain at least 12 characters."
            )
        if "\n" in value or "\r" in value:
            raise SecretValidationError(
                "Multi-line credentials must be handled explicitly rather than "
                "accidentally copied into a single-line secret."
            )

    def _can_manage(self, actor: Actor, repository: Optional[str]) -> bool:
        if actor.access == AccessLevel.ADMIN:
            return True
        return (
            actor.access == AccessLevel.WRITE
            and repository is not None
            and repository in actor.repositories
        )

    def _can_read(
        self,
        actor: Actor,
        repository: Optional[str],
        environment: Optional[str],
    ) -> bool:
        if actor.access == AccessLevel.ADMIN:
            return True

        if repository is None or repository not in actor.repositories:
            return False

        if environment and actor.environments:
            return environment in actor.environments

        return actor.access in {AccessLevel.READ, AccessLevel.WRITE}

    def create_or_update(
        self,
        actor: Actor,
        name: str,
        value: str,
        scope: SecretScope,
        repository: Optional[str] = None,
        environment: Optional[str] = None,
        expires_in_days: Optional[int] = 90,
    ) -> SecretRecord:
        self.validate_name(name)
        self.validate_value(value)

        if scope == SecretScope.REPOSITORY and not repository:
            raise SecretValidationError(
                "Repository-scoped secrets require a repository."
            )

        if scope == SecretScope.ENVIRONMENT:
            if not repository or not environment:
                raise SecretValidationError(
                    "Environment-scoped secrets require both repository and environment."
                )

        if not self._can_manage(actor, repository):
            raise SecretAccessError(
                f"{actor.username} cannot manage secrets for {repository or 'this scope'}."
            )

        now = datetime.now(timezone.utc)
        key = (scope.value, name, repository, environment)
        existing = self._secrets.get(key)

        record = SecretRecord(
            name=name,
            scope=scope,
            value=value,
            repository=repository,
            environment=environment,
            created_at=existing.created_at if existing else now,
            rotated_at=now if existing else None,
            expires_at=(
                now + timedelta(days=expires_in_days)
                if expires_in_days is not None
                else None
            ),
            active=True,
        )

        self._secrets[key] = record
        self._audit_event(actor, "create" if not existing else "rotate", record, "allowed")
        return record

    def disable(
        self,
        actor: Actor,
        record: SecretRecord,
    ) -> None:
        if not self._can_manage(actor, record.repository):
            self._audit_event(actor, "disable", record, "denied")
            raise SecretAccessError("Actor cannot disable this secret.")

        record.active = False
        self._audit_event(actor, "disable", record, "allowed")

    def resolve(
        self,
        actor: Actor,
        name: str,
        repository: str,
        environment: Optional[str] = None,
    ) -> str:
        """
        Resolve a secret using scope precedence.

        Environment secrets override repository secrets for the same name.
        Organization secrets are the fallback. This mirrors a common layered
        configuration model, while making the precedence explicit.
        """
        candidates = [
            (SecretScope.ENVIRONMENT.value, name, repository, environment),
            (SecretScope.REPOSITORY.value, name, repository, None),
            (SecretScope.ORGANIZATION.value, name, None, None),
        ]

        for key in candidates:
            record = self._secrets.get(key)
            if not record or not record.active:
                continue

            if record.expires_at and record.expires_at <= datetime.now(timezone.utc):
                continue

            if not self._can_read(actor, repository, environment):
                self._audit_event(actor, "read", record, "denied")
                raise SecretAccessError(
                    f"{actor.username} is not authorized to read secret {name}."
                )

            self._audit_event(actor, "read", record, "allowed")
            return record.value

        raise KeyError(
            f"No active non-expired secret named {name} is available "
            f"for repository={repository}, environment={environment}."
        )

    def list_metadata(self) -> List[dict]:
        return [record.metadata() for record in self._secrets.values()]

    def audit_report(self) -> List[dict]:
        return [
            {
                "timestamp": event.timestamp.isoformat(),
                "actor": event.actor,
                "action": event.action,
                "secret_name": event.secret_name,
                "scope": event.scope,
                "repository": event.repository,
                "environment": event.environment,
                "result": event.result,
            }
            for event in self._audit
        ]


class SecretMasker:
    """
    Masks known secret values in log-like text.

    Masking is a defense-in-depth control. It is not a replacement for avoiding
    secret output in the first place.
    """

    def __init__(self, values: Iterable[str]) -> None:
        self._values = sorted(
            {value for value in values if len(value) >= 4},
            key=len,
            reverse=True,
        )

    def mask(self, text: str) -> str:
        result = text
        for value in self._values:
            result = result.replace(value, "***")
        return result


class SecureConfiguration:
    """Combines non-sensitive settings with references to secret names."""

    def __init__(self) -> None:
        self.settings = {
            "LOG_LEVEL": "INFO",
            "API_BASE_URL": "https://api.example.internal",
            "DATABASE_SSL_MODE": "require",
        }
        # Configuration contains names, not plaintext credentials.
        self.secret_references = {
            "DATABASE_PASSWORD": "DATABASE_PASSWORD",
            "DEPLOY_TOKEN": "DEPLOY_TOKEN",
        }

    def validate(self) -> List[str]:
        problems: List[str] = []

        for key, value in self.settings.items():
            if any(marker in key.upper() for marker in ("PASSWORD", "TOKEN", "SECRET", "PRIVATE_KEY")):
                problems.append(f"Potential secret-bearing setting: {key}")

            if any(marker in value.upper() for marker in ("PASSWORD=", "TOKEN=", "SECRET=")):
                problems.append(f"Potential credential embedded in setting {key}")

        return problems


def generate_demo_credential(prefix: str) -> str:
    """Generate a high-entropy credential suitable for this demonstration."""
    return f"{prefix}_{crypto_secrets.token_urlsafe(32)}"


def fingerprint(value: str) -> str:
    """
    Produce a non-reversible identifier for auditing.

    This is useful for detecting whether a value changed without displaying
    the credential itself. A fingerprint must not be confused with encryption.
    """
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:16]


def constant_time_equal(left: str, right: str) -> bool:
    """Use constant-time comparison when comparing sensitive values."""
    return hmac.compare_digest(left, right)


def evaluate_ci_configuration(
    repository: str,
    required_secrets: Set[str],
    manager: SecretManager,
    environment: str,
) -> List[str]:
    """
    Evaluate whether a CI job has the secret configuration it expects.

    The function checks metadata and attempts controlled resolution without
    printing secret values.
    """
    findings: List[str] = []
    actor = Actor(
        username="ci-runtime",
        access=AccessLevel.READ,
        repositories={repository},
        environments={environment},
    )

    for name in sorted(required_secrets):
        try:
            value = manager.resolve(actor, name, repository, environment)
            findings.append(
                f"{name}: available, fingerprint={fingerprint(value)}"
            )
        except (KeyError, SecretAccessError) as exc:
            findings.append(f"{name}: unavailable ({exc})")

    return findings


def simulate_github_actions_job(
    manager: SecretManager,
    repository: str,
    environment: str,
) -> None:
    """
    Simulate a deployment job.

    The important behavior is that the job receives secret values only at the
    point where they are needed and never includes them in diagnostic output.
    """
    runner = Actor(
        username="github-actions-runner",
        access=AccessLevel.READ,
        repositories={repository},
        environments={environment},
    )

    deployment_token = manager.resolve(
        runner,
        "DEPLOY_TOKEN",
        repository,
        environment,
    )

    print("Deployment job started")
    print(f"Repository: {repository}")
    print(f"Environment: {environment}")
    print(f"Credential available: {bool(deployment_token)}")
    print("Credential value: [not displayed]")

    simulated_command_output = (
        "curl authorization=Bearer " + deployment_token
        + " deployment=successful"
    )

    masker = SecretMasker([deployment_token])
    print("Masked runner log:")
    print(masker.mask(simulated_command_output))


def demonstrate_expiration(manager: SecretManager, administrator: Actor) -> None:
    record = manager.create_or_update(
        administrator,
        "SHORT_LIVED_TOKEN",
        generate_demo_credential("short"),
        SecretScope.REPOSITORY,
        repository="acme/payments",
        expires_in_days=1,
    )

    # Force expiration to demonstrate the failure path deterministically.
    record.expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)

    runner = Actor(
        username="github-actions-runner",
        access=AccessLevel.READ,
        repositories={"acme/payments"},
        environments={"production"},
    )

    try:
        manager.resolve(
            runner,
            "SHORT_LIVED_TOKEN",
            "acme/payments",
            "production",
        )
    except KeyError as exc:
        print(f"Expired secret rejected: {exc}")


def main() -> None:
    print("=== Actions Secrets and Secure Configuration ===")

    manager = SecretManager()

    administrator = Actor(
        username="platform-admin",
        access=AccessLevel.ADMIN,
        repositories={"acme/payments", "acme/web"},
        environments={"development", "staging", "production"},
    )

    developer = Actor(
        username="developer-a",
        access=AccessLevel.WRITE,
        repositories={"acme/payments"},
        environments={"development", "staging"},
    )

    production_runner = Actor(
        username="production-runner",
        access=AccessLevel.READ,
        repositories={"acme/payments"},
        environments={"production"},
    )

    print("\n=== Creating scoped secrets ===")

    manager.create_or_update(
        administrator,
        "NPM_PUBLISH_TOKEN",
        generate_demo_credential("npm"),
        SecretScope.ORGANIZATION,
        expires_in_days=90,
    )

    manager.create_or_update(
        administrator,
        "DATABASE_PASSWORD",
        generate_demo_credential("db"),
        SecretScope.REPOSITORY,
        repository="acme/payments",
        expires_in_days=60,
    )

    manager.create_or_update(
        administrator,
        "DATABASE_PASSWORD",
        generate_demo_credential("prod-db"),
        SecretScope.ENVIRONMENT,
        repository="acme/payments",
        environment="production",
        expires_in_days=30,
    )

    manager.create_or_update(
        administrator,
        "DEPLOY_TOKEN",
        generate_demo_credential("deploy-prod"),
        SecretScope.ENVIRONMENT,
        repository="acme/payments",
        environment="production",
        expires_in_days=14,
    )

    print("Secret metadata:")
    for metadata in manager.list_metadata():
        print(metadata)

    print("\n=== Environment-specific resolution ===")

    staging_database_password = manager.resolve(
        developer,
        "DATABASE_PASSWORD",
        "acme/payments",
        "staging",
    )

    production_database_password = manager.resolve(
        production_runner,
        "DATABASE_PASSWORD",
        "acme/payments",
        "production",
    )

    print("Staging password resolved:", fingerprint(staging_database_password))
    print("Production password resolved:", fingerprint(production_database_password))
    print(
        "Passwords differ:",
        not constant_time_equal(
            staging_database_password,
            production_database_password,
        ),
    )

    print("\n=== Secure CI configuration ===")

    required = {"DATABASE_PASSWORD", "DEPLOY_TOKEN", "NPM_PUBLISH_TOKEN"}
    for finding in evaluate_ci_configuration(
        "acme/payments",
        required,
        manager,
        "production",
    ):
        print(finding)

    print("\n=== Simulated deployment ===")
    simulate_github_actions_job(manager, "acme/payments", "production")

    print("\n=== Authorization failure ===")
    unauthorized_actor = Actor(
        username="external-contributor",
        access=AccessLevel.READ,
        repositories=set(),
        environments=set(),
    )

    try:
        manager.resolve(
            unauthorized_actor,
            "DATABASE_PASSWORD",
            "acme/payments",
            "production",
        )
    except SecretAccessError as exc:
        print(f"Access denied as expected: {exc}")

    print("\n=== Credential rotation ===")
    old_metadata = [
        item for item in manager.list_metadata()
        if item["name"] == "DEPLOY_TOKEN"
    ][0]
    print("Before rotation:", old_metadata)

    rotated = manager.create_or_update(
        administrator,
        "DEPLOY_TOKEN",
        generate_demo_credential("deploy-prod-rotated"),
        SecretScope.ENVIRONMENT,
        repository="acme/payments",
        environment="production",
        expires_in_days=14,
    )

    print("After rotation:")
    print(rotated.metadata())

    print("\n=== Configuration validation ===")
    configuration = SecureConfiguration()
    print("Configuration findings:", configuration.validate())
    print("Secrets remain references rather than embedded values.")

    print("\n=== Expiration handling ===")
    demonstrate_expiration(manager, administrator)

    print("\n=== Audit trail ===")
    for event in manager.audit_report():
        print(event)

    print("\n=== Production security observations ===")
    observations = [
        "Store credentials in a dedicated secret-management system rather than source control.",
        "Grant CI jobs only the repository and environment access they require.",
        "Use environment-specific credentials when production access needs stronger isolation.",
        "Rotate long-lived credentials and prefer short-lived or federated credentials where supported.",
        "Do not place secret values in source files, command arguments, artifacts, cache entries, or diagnostic logs.",
        "Treat masking as defense in depth because transformed or encoded values may evade simple masking.",
        "Keep secret names and ordinary configuration separate from secret values.",
        "Audit access and rotation events without recording plaintext credentials.",
    ]

    for observation in observations:
        print(f"- {observation}")


if __name__ == "__main__":
    main()
