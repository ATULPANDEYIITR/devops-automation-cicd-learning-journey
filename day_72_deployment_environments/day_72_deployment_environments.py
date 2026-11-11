#!/usr/bin/env python3
"""
Deployment Environment Lifecycle Simulator

Models development, QA, staging, and production environments.
Implements artifact promotion, environment-specific configuration,
approval gates, deployment history, rollback, and validation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("deployment")


class Environment(str, Enum):
    DEVELOPMENT = "development"
    QA = "qa"
    STAGING = "staging"
    PRODUCTION = "production"


class DeploymentStatus(str, Enum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class DeploymentError(Exception):
    """Base deployment exception."""


class ValidationError(DeploymentError):
    pass


class ApprovalError(DeploymentError):
    pass


class ConfigurationError(DeploymentError):
    pass


@dataclass(frozen=True)
class Artifact:
    name: str
    version: str
    commit_sha: str
    checksum: str
    build_timestamp: str

    def __post_init__(self):
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}", self.name):
            raise ValidationError("Invalid artifact name.")

        if not re.fullmatch(r"\d+\.\d+\.\d+(?:-[a-zA-Z0-9.-]+)?", self.version):
            raise ValidationError("Invalid semantic version.")

        if not re.fullmatch(r"[0-9a-f]{7,40}", self.commit_sha):
            raise ValidationError("Invalid commit SHA.")

        if not re.fullmatch(r"[0-9a-f]{64}", self.checksum):
            raise ValidationError("Invalid SHA-256 checksum.")

    @staticmethod
    def create(name: str, version: str, commit_sha: str, content: bytes):
        checksum = hashlib.sha256(content).hexdigest()
        return Artifact(
            name=name,
            version=version,
            commit_sha=commit_sha,
            checksum=checksum,
            build_timestamp=datetime.now(timezone.utc).isoformat(),
        )

    @property
    def identity(self) -> str:
        return f"{self.name}:{self.version}:{self.checksum}"


@dataclass
class EnvironmentConfig:
    name: Environment
    endpoint: str
    replicas: int
    approval_required: bool
    required_checks: set[str] = field(default_factory=set)
    variables: dict[str, str] = field(default_factory=dict)

    def validate(self):
        if not self.endpoint.startswith("https://"):
            raise ConfigurationError(
                f"{self.name.value}: endpoint must use HTTPS."
            )

        if not 1 <= self.replicas <= 100:
            raise ConfigurationError("Replica count must be between 1 and 100.")

        forbidden = {"password", "secret", "private_key", "access_token"}

        for key in self.variables:
            if key.lower() in forbidden:
                raise ConfigurationError(
                    f"Sensitive variable '{key}' must use a secret manager."
                )


@dataclass
class DeploymentRecord:
    deployment_id: int
    environment: Environment
    artifact: Artifact
    status: DeploymentStatus
    deployed_at: str
    deployed_by: str
    approved_by: str | None = None
    failure_reason: str | None = None
    previous_artifact: Artifact | None = None


class DeploymentManager:
    """
    Manages immutable artifact promotion and environment state.

    A promotion deploys the same artifact identity across environments.
    Environment-specific settings are applied separately.
    """

    ORDER = [
        Environment.DEVELOPMENT,
        Environment.QA,
        Environment.STAGING,
        Environment.PRODUCTION,
    ]

    def __init__(self, configs: dict[Environment, EnvironmentConfig]):
        if set(configs) != set(self.ORDER):
            raise ConfigurationError("All four environments are required.")

        self.configs = configs
        self.current: dict[Environment, Artifact] = {}
        self.history: list[DeploymentRecord] = []
        self._next_id = 1
        self._checks: dict[str, set[str]] = {}

        for config in configs.values():
            config.validate()

    def register_checks(self, artifact: Artifact, checks: set[str]):
        self._checks[artifact.identity] = set(checks)

    def _validate_promotion(
        self,
        environment: Environment,
        artifact: Artifact,
        approved_by: str | None,
    ):
        position = self.ORDER.index(environment)

        if position > 0:
            previous_environment = self.ORDER[position - 1]
            previous_artifact = self.current.get(previous_environment)

            if previous_artifact is None:
                raise ValidationError(
                    f"{previous_environment.value} must be deployed first."
                )

            if previous_artifact.identity != artifact.identity:
                raise ValidationError(
                    "Artifact does not match the previous environment."
                )

        config = self.configs[environment]
        config.validate()

        passed = self._checks.get(artifact.identity, set())
        missing = config.required_checks - passed

        if missing:
            raise ValidationError(
                f"Missing required checks: {sorted(missing)}"
            )

        if config.approval_required and not approved_by:
            raise ApprovalError(
                f"Approval required for {environment.value}."
            )

        if approved_by and not approved_by.strip():
            raise ApprovalError("Approver identity cannot be empty.")

    def deploy(
        self,
        environment: Environment,
        artifact: Artifact,
        deployed_by: str,
        approved_by: str | None = None,
        simulate_failure: bool = False,
    ) -> DeploymentRecord:

        if not deployed_by.strip():
            raise ValidationError("Deployment actor is required.")

        self._validate_promotion(environment, artifact, approved_by)

        previous = self.current.get(environment)

        record = DeploymentRecord(
            deployment_id=self._next_id,
            environment=environment,
            artifact=artifact,
            status=DeploymentStatus.PENDING,
            deployed_at=datetime.now(timezone.utc).isoformat(),
            deployed_by=deployed_by,
            approved_by=approved_by,
            previous_artifact=previous,
        )

        self._next_id += 1
        self.history.append(record)

        try:
            if simulate_failure:
                raise DeploymentError("Simulated health-check failure.")

            # In production, execute deployment through an authenticated
            # deployment agent and verify readiness before updating state.
            self.current[environment] = artifact
            record.status = DeploymentStatus.SUCCEEDED

            logger.info(
                "Deployment %s succeeded: %s -> %s",
                record.deployment_id,
                environment.value,
                artifact.identity,
            )

        except DeploymentError as exc:
            record.status = DeploymentStatus.FAILED
            record.failure_reason = str(exc)

            logger.error(
                "Deployment %s failed: %s",
                record.deployment_id,
                exc,
            )

        return record

    def rollback(self, environment: Environment, deployed_by: str):
        current = self.current.get(environment)

        if current is None:
            raise DeploymentError("No deployment exists to roll back.")

        previous_record = next(
            (
                record
                for record in reversed(self.history)
                if record.environment == environment
                and record.status == DeploymentStatus.SUCCEEDED
                and record.artifact.identity != current.identity
            ),
            None,
        )

        if previous_record is None:
            raise DeploymentError("No previous successful version exists.")

        previous = previous_record.artifact

        rollback_record = DeploymentRecord(
            deployment_id=self._next_id,
            environment=environment,
            artifact=previous,
            status=DeploymentStatus.PENDING,
            deployed_at=datetime.now(timezone.utc).isoformat(),
            deployed_by=deployed_by,
            previous_artifact=current,
        )

        self._next_id += 1
        self.history.append(rollback_record)

        self.current[environment] = previous
        rollback_record.status = DeploymentStatus.SUCCEEDED

        # Mark the original deployment as rolled back for audit reporting.
        for record in reversed(self.history[:-1]):
            if (
                record.environment == environment
                and record.artifact.identity == current.identity
                and record.status == DeploymentStatus.SUCCEEDED
            ):
                record.status = DeploymentStatus.ROLLED_BACK
                break

        logger.warning(
            "Rolled back %s to %s",
            environment.value,
            previous.identity,
        )

        return rollback_record

    def report(self):
        return {
            "environments": {
                env.value: (
                    self.current[env].identity
                    if env in self.current
                    else None
                )
                for env in self.ORDER
            },
            "deployment_count": len(self.history),
            "history": [
                {
                    "id": record.deployment_id,
                    "environment": record.environment.value,
                    "artifact": record.artifact.identity,
                    "status": record.status.value,
                    "deployed_by": record.deployed_by,
                    "approved_by": record.approved_by,
                    "failure_reason": record.failure_reason,
                }
                for record in self.history
            ],
        }

    def save_report(self, destination: Path):
        report = self.report()

        destination.parent.mkdir(parents=True, exist_ok=True)

        # Write atomically so an interrupted write cannot corrupt the report.
        temporary = destination.with_suffix(destination.suffix + ".tmp")

        try:
            temporary.write_text(
                json.dumps(report, indent=2),
                encoding="utf-8",
            )
            temporary.replace(destination)
        finally:
            if temporary.exists():
                temporary.unlink()


def build_manager() -> DeploymentManager:
    configs = {
        Environment.DEVELOPMENT: EnvironmentConfig(
            Environment.DEVELOPMENT,
            "https://dev.example.internal",
            1,
            False,
            {"unit_tests", "build"},
            {"DEBUG": "true"},
        ),
        Environment.QA: EnvironmentConfig(
            Environment.QA,
            "https://qa.example.internal",
            2,
            False,
            {"unit_tests", "integration_tests", "security_scan"},
            {"DEBUG": "false"},
        ),
        Environment.STAGING: EnvironmentConfig(
            Environment.STAGING,
            "https://staging.example.internal",
            3,
            True,
            {"unit_tests", "integration_tests", "security_scan", "load_tests"},
            {"DEBUG": "false"},
        ),
        Environment.PRODUCTION: EnvironmentConfig(
            Environment.PRODUCTION,
            "https://production.example.com",
            5,
            True,
            {
                "unit_tests",
                "integration_tests",
                "security_scan",
                "load_tests",
                "acceptance_tests",
            },
            {"DEBUG": "false"},
        ),
    }

    return DeploymentManager(configs)


def run_demo():
    manager = build_manager()

    content = b"application release 1.0.0"
    artifact = Artifact.create(
        name="inventory-api",
        version="1.0.0",
        commit_sha="a" * 40,
        content=content,
    )

    checks = {
        "unit_tests",
        "integration_tests",
        "security_scan",
        "load_tests",
        "acceptance_tests",
        "build",
    }

    manager.register_checks(artifact, checks)

    # Promote one immutable artifact through all environments.
    for environment in manager.ORDER:
        approval = (
            "release-manager"
            if manager.configs[environment].approval_required
            else None
        )

        record = manager.deploy(
            environment,
            artifact,
            deployed_by="deployment-bot",
            approved_by=approval,
        )

        assert record.status == DeploymentStatus.SUCCEEDED

    # Demonstrate rejection of an unapproved production deployment.
    try:
        manager.deploy(
            Environment.PRODUCTION,
            artifact,
            deployed_by="deployment-bot",
        )
    except ApprovalError as exc:
        logger.info("Expected approval rejection: %s", exc)

    # Demonstrate failed deployment handling in an isolated development
    # deployment of a newer artifact.
    next_artifact = Artifact.create(
        "inventory-api",
        "1.1.0",
        "b" * 40,
        b"application release 1.1.0",
    )

    manager.register_checks(next_artifact, checks)

    failed = manager.deploy(
        Environment.DEVELOPMENT,
        next_artifact,
        deployed_by="developer",
        simulate_failure=True,
    )

    assert failed.status == DeploymentStatus.FAILED

    # Roll back a previously promoted environment using its deployment history.
    rollback = manager.rollback(
        Environment.DEVELOPMENT,
        deployed_by="operator",
    )

    assert rollback.artifact.identity == artifact.identity

    report_path = Path("deployment_report.json")
    manager.save_report(report_path)

    print(json.dumps(manager.report(), indent=2))
    print(f"\nReport saved to: {report_path.resolve()}")


def run_tests():
    manager = build_manager()

    artifact = Artifact.create(
        "test-api",
        "1.0.0",
        "c" * 40,
        b"test content",
    )

    manager.register_checks(
        artifact,
        {
            "unit_tests",
            "integration_tests",
            "security_scan",
            "load_tests",
            "acceptance_tests",
            "build",
        },
    )

    # Invalid configuration is rejected.
    try:
        Artifact.create("bad name!", "1.0.0", "d" * 40, b"x")
        raise AssertionError("Invalid artifact name was accepted.")
    except ValidationError:
        pass

    # QA cannot be deployed before development.
    try:
        manager.deploy(
            Environment.QA,
            artifact,
            "developer",
        )
        raise AssertionError("Invalid promotion was accepted.")
    except ValidationError:
        pass

    dev = manager.deploy(
        Environment.DEVELOPMENT,
        artifact,
        "developer",
    )
    assert dev.status == DeploymentStatus.SUCCEEDED

    qa = manager.deploy(
        Environment.QA,
        artifact,
        "qa-engineer",
    )
    assert qa.status == DeploymentStatus.SUCCEEDED

    # Missing approval blocks staging.
    try:
        manager.deploy(
            Environment.STAGING,
            artifact,
            "release-bot",
        )
        raise AssertionError("Missing approval was accepted.")
    except ApprovalError:
        pass

    print("All deployment tests passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Deployment environment lifecycle simulator"
    )
    parser.add_argument(
        "--test",
        action="store_true",
        help="Run built-in tests.",
    )

    args = parser.parse_args()

    try:
        run_tests() if args.test else run_demo()
    except (DeploymentError, OSError) as exc:
        logger.exception("Execution failed: %s", exc)
        raise SystemExit(1)
