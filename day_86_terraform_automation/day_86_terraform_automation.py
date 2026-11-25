#!/usr/bin/env python3
"""
Terraform Automation Integrated with CI/CD

Models an infrastructure delivery pipeline with:
- Terraform configuration validation
- Formatting and initialization stages
- Plan generation and artifact tracking
- Security and policy checks
- Approval gates
- State locking
- Controlled infrastructure deployment
- Drift detection
- Failure handling and audit logging

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import uuid

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("terraform-cicd")


class PipelineError(Exception):
    pass


class ValidationError(PipelineError):
    pass


class ApprovalError(PipelineError):
    pass


class LockError(PipelineError):
    pass


class Stage(Enum):
    CREATED = "created"
    VALIDATING = "validating"
    INITIALIZING = "initializing"
    PLANNING = "planning"
    SECURITY_SCANNING = "security_scanning"
    WAITING_APPROVAL = "waiting_approval"
    APPLYING = "applying"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Environment(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class ApprovalStatus(Enum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class PipelineConfig:
    project: str
    environment: Environment
    terraform_version: str
    working_directory: Path
    required_approvals: int = 1
    require_security_scan: bool = True
    require_plan_review: bool = True
    allow_destroy: bool = False
    auto_approve_nonproduction: bool = False
    timeout_seconds: int = 300

    def __post_init__(self):
        if not re.fullmatch(r"[a-zA-Z0-9_-]{2,64}", self.project):
            raise ValidationError("Invalid project identifier")

        if self.required_approvals < 0:
            raise ValidationError("Approval count cannot be negative")

        if self.timeout_seconds <= 0:
            raise ValidationError("Timeout must be positive")


@dataclass
class Approval:
    reviewer: str
    status: ApprovalStatus
    timestamp: str
    comment: str = ""


@dataclass
class Plan:
    plan_id: str
    project: str
    environment: str
    additions: int
    changes: int
    destructions: int
    configuration_hash: str
    generated_at: str
    approved: bool = False

    @property
    def has_changes(self) -> bool:
        return any(
            (self.additions, self.changes, self.destructions)
        )


@dataclass
class PipelineRun:
    run_id: str
    config: PipelineConfig
    stage: Stage = Stage.CREATED
    approvals: list[Approval] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)
    plan: Plan | None = None
    errors: list[str] = field(default_factory=list)
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    completed_at: str | None = None

    def record(self, event: str, details: str = "") -> None:
        self.events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "stage": self.stage.value,
            "event": event,
            "details": details
        })


class StateLock:
    """
    In-process lock representing a remote Terraform state lock.

    Production deployments should use a backend that supports
    atomic state locking, such as an appropriately configured
    remote state backend.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._owner: str | None = None

    def acquire(self, owner: str, timeout: float = 5.0) -> None:
        if not self._lock.acquire(timeout=timeout):
            raise LockError("Terraform state is locked")

        self._owner = owner

    def release(self, owner: str) -> None:
        if self._owner != owner:
            raise LockError("Only the lock owner can release the lock")

        self._owner = None
        self._lock.release()


class TerraformExecutor:
    """
    Executes Terraform through subprocess.

    Execution is disabled by default. Enable it explicitly with
    --execute after configuring credentials and a remote backend.
    """

    def __init__(
        self,
        directory: Path,
        executable: str = "terraform",
        execute: bool = False,
        timeout: int = 300
    ):
        self.directory = directory.resolve()
        self.executable = executable
        self.execute = execute
        self.timeout = timeout

    def _run(self, arguments: list[str]) -> str:
        if not self.execute:
            logger.info("SIMULATED: terraform %s", " ".join(arguments))
            return "simulation successful"

        if not self.directory.is_dir():
            raise PipelineError("Terraform directory does not exist")

        command = [self.executable, *arguments]

        try:
            result = subprocess.run(
                command,
                cwd=self.directory,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
                shell=False
            )
        except FileNotFoundError as exc:
            raise PipelineError(
                "Terraform executable was not found"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise PipelineError(
                "Terraform command timed out"
            ) from exc

        if result.returncode != 0:
            # Avoid logging environment variables or credentials.
            raise PipelineError(
                f"Terraform command failed: {result.stderr[-2000:]}"
            )

        return result.stdout

    def version(self) -> str:
        return self._run(["version"])

    def format_check(self) -> str:
        return self._run(["fmt", "-check", "-recursive"])

    def validate(self) -> str:
        return self._run(["validate", "-no-color"])

    def initialize(self) -> str:
        return self._run([
            "init",
            "-input=false",
            "-lockfile=readonly"
        ])

    def create_plan(self, plan_path: Path) -> str:
        return self._run([
            "plan",
            "-input=false",
            "-lock-timeout=60s",
            "-out",
            str(plan_path)
        ])

    def apply(self, plan_path: Path) -> str:
        return self._run([
            "apply",
            "-input=false",
            "-lock-timeout=60s",
            str(plan_path)
        ])


class ConfigurationInspector:

    RESOURCE_PATTERN = re.compile(
        r'^\s*resource\s+"([^"]+)"\s+"([^"]+)"',
        re.MULTILINE
    )

    def inspect(self, directory: Path) -> dict[str, Any]:
        if not directory.is_dir():
            raise ValidationError("Configuration directory not found")

        files = sorted(directory.rglob("*.tf"))

        if not files:
            raise ValidationError("No Terraform configuration files found")

        digest = hashlib.sha256()
        resources: list[tuple[str, str]] = []
        errors: list[str] = []

        for file in files:
            # Avoid scanning generated or hidden directories.
            if any(part.startswith(".") for part in file.parts):
                continue

            content = file.read_text(encoding="utf-8")
            digest.update(file.name.encode())
            digest.update(content.encode())

            resources.extend(
                self.RESOURCE_PATTERN.findall(content)
            )

            if "\x00" in content:
                errors.append(f"Invalid null byte in {file.name}")

        if errors:
            raise ValidationError("; ".join(errors))

        return {
            "files": len(files),
            "resources": resources,
            "resource_count": len(resources),
            "configuration_hash": digest.hexdigest()
        }


class SecurityScanner:
    """
    Basic demonstration scanner.

    A production pipeline should additionally run dedicated
    IaC security scanners and policy-as-code evaluations.
    """

    DANGEROUS_PATTERNS = {
        "Hardcoded cloud secret": re.compile(
            r'(?i)(access_key|secret_key|client_secret)\s*=\s*"[^"]+"'
        ),
        "Public access configuration": re.compile(
            r'(?i)(0\.0\.0\.0/0)'
        ),
        "Disabled encryption": re.compile(
            r'(?i)encrypted\s*=\s*false'
        )
    }

    def scan(self, directory: Path) -> list[str]:
        findings = []

        for file in directory.rglob("*.tf"):
            if any(part.startswith(".") for part in file.parts):
                continue

            content = file.read_text(
                encoding="utf-8"
            )

            for description, pattern in self.DANGEROUS_PATTERNS.items():
                if pattern.search(content):
                    findings.append(
                        f"{file.name}: {description}"
                    )

        return findings


class ApprovalService:

    def approve(
        self,
        run: PipelineRun,
        reviewer: str,
        comment: str = ""
    ) -> None:
        if not reviewer.strip():
            raise ApprovalError("Reviewer identity is required")

        if any(
            approval.reviewer == reviewer
            and approval.status == ApprovalStatus.APPROVED
            for approval in run.approvals
        ):
            raise ApprovalError("Reviewer has already approved")

        run.approvals.append(
            Approval(
                reviewer=reviewer,
                status=ApprovalStatus.APPROVED,
                timestamp=datetime.now(timezone.utc).isoformat(),
                comment=comment
            )
        )

        run.record("approval_received", reviewer)

    def reject(
        self,
        run: PipelineRun,
        reviewer: str,
        comment: str
    ) -> None:
        if not reviewer.strip():
            raise ApprovalError("Reviewer identity is required")

        run.approvals.append(
            Approval(
                reviewer=reviewer,
                status=ApprovalStatus.REJECTED,
                timestamp=datetime.now(timezone.utc).isoformat(),
                comment=comment
            )
        )

        run.record("approval_rejected", reviewer)

    def validate(
        self,
        run: PipelineRun,
        required: int
    ) -> None:
        if any(
            approval.status == ApprovalStatus.REJECTED
            for approval in run.approvals
        ):
            raise ApprovalError("Deployment rejected by reviewer")

        unique_reviewers = {
            approval.reviewer
            for approval in run.approvals
            if approval.status == ApprovalStatus.APPROVED
        }

        if len(unique_reviewers) < required:
            raise ApprovalError(
                f"Required {required} approvals, "
                f"received {len(unique_reviewers)}"
            )


class TerraformPipeline:

    def __init__(
        self,
        config: PipelineConfig,
        executor: TerraformExecutor,
        inspector: ConfigurationInspector | None = None,
        scanner: SecurityScanner | None = None
    ):
        self.config = config
        self.executor = executor
        self.inspector = inspector or ConfigurationInspector()
        self.scanner = scanner or SecurityScanner()
        self.approvals = ApprovalService()
        self.state_lock = StateLock()
        self.run = PipelineRun(
            run_id=str(uuid.uuid4()),
            config=config
        )

    def transition(self, stage: Stage) -> None:
        self.run.stage = stage
        self.run.record("stage_transition", stage.value)
        logger.info(
            "Pipeline %s: %s",
            self.run.run_id[:8],
            stage.value
        )

    def validate_configuration(self) -> dict[str, Any]:
        self.transition(Stage.VALIDATING)

        inspection = self.inspector.inspect(
            self.config.working_directory
        )

        self.executor.format_check()
        self.executor.validate()

        self.run.record(
            "configuration_validated",
            f"{inspection['resource_count']} resources"
        )

        return inspection

    def initialize(self) -> None:
        self.transition(Stage.INITIALIZING)
        self.executor.initialize()

    def generate_plan(
        self,
        inspection: dict[str, Any],
        plan_path: Path
    ) -> Plan:
        self.transition(Stage.PLANNING)

        self.executor.create_plan(plan_path)

        # Simulated plan metrics. Real metrics must be extracted
        # from terraform show -json using a trusted parser.
        plan = Plan(
            plan_id=str(uuid.uuid4()),
            project=self.config.project,
            environment=self.config.environment.value,
            additions=2,
            changes=1,
            destructions=0,
            configuration_hash=inspection["configuration_hash"],
            generated_at=datetime.now(timezone.utc).isoformat()
        )

        if plan.destructions and not self.config.allow_destroy:
            raise PipelineError(
                "Destructive changes are prohibited"
            )

        self.run.plan = plan
        self.run.record(
            "plan_generated",
            json.dumps(asdict(plan))
        )

        return plan

    def security_scan(self) -> None:
        self.transition(Stage.SECURITY_SCANNING)

        findings = self.scanner.scan(
            self.config.working_directory
        )

        if findings:
            raise ValidationError(
                "Security findings: " + "; ".join(findings)
            )

        self.run.record("security_scan_passed")

    def request_approval(self) -> None:
        required = self.config.required_approvals

        if (
            self.config.environment != Environment.PRODUCTION
            and self.config.auto_approve_nonproduction
        ):
            required = 0

        if required == 0:
            self.run.plan.approved = True
            self.run.record("approval_not_required")
            return

        self.transition(Stage.WAITING_APPROVAL)

        self.approvals.validate(
            self.run,
            required
        )

        self.run.plan.approved = True

    def deploy(self, plan_path: Path) -> None:
        if not self.run.plan or not self.run.plan.approved:
            raise ApprovalError("An approved plan is required")

        self.transition(Stage.APPLYING)

        owner = self.run.run_id

        self.state_lock.acquire(owner)

        try:
            # The plan is applied rather than recalculated.
            self.executor.apply(plan_path)
        finally:
            self.state_lock.release(owner)

        self.transition(Stage.SUCCEEDED)
        self.run.completed_at = datetime.now(
            timezone.utc
        ).isoformat()

    def execute_pipeline(
        self,
        plan_path: Path
    ) -> PipelineRun:
        try:
            inspection = self.validate_configuration()
            self.initialize()
            self.generate_plan(inspection, plan_path)

            if self.config.require_security_scan:
                self.security_scan()

            self.request_approval()
            self.deploy(plan_path)

        except Exception as exc:
            self.run.errors.append(str(exc))
            self.transition(Stage.FAILED)
            self.run.completed_at = datetime.now(
                timezone.utc
            ).isoformat()

            logger.exception("Pipeline failed")

        return self.run


class DriftDetector:
    """
    Compares a stored resource snapshot with a current snapshot.
    """

    @staticmethod
    def detect(
        expected: dict[str, Any],
        actual: dict[str, Any]
    ) -> dict[str, Any]:
        missing = set(expected) - set(actual)
        unexpected = set(actual) - set(expected)

        changed = {
            key: {
                "expected": expected[key],
                "actual": actual[key]
            }
            for key in expected.keys() & actual.keys()
            if expected[key] != actual[key]
        }

        return {
            "drift_detected": bool(
                missing or unexpected or changed
            ),
            "missing_resources": sorted(missing),
            "unexpected_resources": sorted(unexpected),
            "changed_resources": changed
        }


def save_audit_report(
    run: PipelineRun,
    output: Path
) -> None:
    report = {
        "run_id": run.run_id,
        "project": run.config.project,
        "environment": run.config.environment.value,
        "stage": run.stage.value,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "plan": asdict(run.plan) if run.plan else None,
        "approvals": [
            {
                **asdict(approval),
                "status": approval.status.value
            }
            for approval in run.approvals
        ],
        "events": run.events,
        "errors": run.errors
    }

    output.parent.mkdir(parents=True, exist_ok=True)

    temporary = output.with_suffix(output.suffix + ".tmp")

    temporary.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8"
    )

    os.replace(temporary, output)


def demonstration() -> None:
    directory = Path("terraform-demo")
    directory.mkdir(exist_ok=True)

    config_file = directory / "main.tf"

    if not config_file.exists():
        config_file.write_text(
            """
terraform {
  required_version = ">= 1.5.0"
}

resource "aws_s3_bucket" "application_data" {
  bucket = "example-application-data-2026"
}
""".strip() + "\n",
            encoding="utf-8"
        )

    config = PipelineConfig(
        project="cloud-platform",
        environment=Environment.PRODUCTION,
        terraform_version="1.9",
        working_directory=directory,
        required_approvals=2,
        require_security_scan=True
    )

    executor = TerraformExecutor(
        directory=directory,
        execute=False
    )

    pipeline = TerraformPipeline(config, executor)

    # Simulated review decisions.
    pipeline.approvals.approve(
        pipeline.run,
        "platform-lead",
        "Infrastructure changes reviewed"
    )

    pipeline.approvals.approve(
        pipeline.run,
        "security-lead",
        "Security review completed"
    )

    run = pipeline.execute_pipeline(
        Path("terraform-demo.plan")
    )

    save_audit_report(
        run,
        Path("reports/terraform-pipeline.json")
    )

    expected = {
        "application-bucket": "encrypted",
        "application-network": "private"
    }

    actual = {
        "application-bucket": "encrypted",
        "application-network": "public"
    }

    print("\nPIPELINE RESULT")
    print(json.dumps({
        "run_id": run.run_id,
        "status": run.stage.value,
        "errors": run.errors,
        "drift": DriftDetector.detect(expected, actual)
    }, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Terraform CI/CD automation simulator"
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute actual Terraform commands"
    )

    args = parser.parse_args()

    if args.execute:
        logger.warning(
            "Real Terraform execution requested. "
            "Production credentials and backend must be configured."
        )

    demonstration()


if __name__ == "__main__":
    main()
