#!/usr/bin/env python3
"""
Jenkins Shared Libraries: Reusable Enterprise Pipeline Code

Demonstrates:
- Shared library structure and version management
- Reusable pipeline steps
- Pipeline configuration and execution
- Declarative workflow simulation
- Validation and policy enforcement
- Credentials masking
- Retry and timeout handling
- Release governance
- Pipeline events and execution history
- Automated tests
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("jenkins.shared.library")


class PipelineError(Exception):
    """Base exception for pipeline execution errors."""


class ValidationError(PipelineError):
    """Invalid pipeline configuration."""


class PolicyError(PipelineError):
    """A governance policy was violated."""


class StageError(PipelineError):
    """A pipeline stage failed."""


class PipelineStatus(str, Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    ABORTED = "ABORTED"


class StageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class Environment(str, Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


@dataclass(frozen=True)
class LibraryVersion:
    name: str
    version: str
    approved: bool
    tested: bool
    commit: str

    def __post_init__(self):
        if not self.name.strip():
            raise ValidationError("Library name cannot be empty.")

        if not re.fullmatch(r"\d+\.\d+\.\d+", self.version):
            raise ValidationError("Library version must use semantic versioning.")

        if not re.fullmatch(r"[a-f0-9]{7,40}", self.commit):
            raise ValidationError("Invalid library commit identifier.")


@dataclass
class StageResult:
    name: str
    status: StageStatus
    attempts: int = 0
    duration_seconds: float = 0.0
    message: str = ""


@dataclass
class PipelineContext:
    application: str
    branch: str
    environment: Environment
    build_number: int
    library: LibraryVersion
    parameters: dict[str, Any] = field(default_factory=dict)
    results: list[StageResult] = field(default_factory=list)
    status: PipelineStatus = PipelineStatus.CREATED
    started_at: str | None = None
    finished_at: str | None = None

    def add_result(self, result: StageResult) -> None:
        self.results.append(result)


class SharedLibraryRegistry:
    """Maintains approved and tested shared library releases."""

    def __init__(self):
        self._versions: dict[tuple[str, str], LibraryVersion] = {}

    def register(self, release: LibraryVersion) -> None:
        key = (release.name, release.version)

        if key in self._versions:
            raise ValidationError("Library version already registered.")

        self._versions[key] = release
        logger.info("Registered %s@%s", *key)

    def resolve(
        self,
        name: str,
        version: str,
        require_approval: bool = True,
    ) -> LibraryVersion:
        release = self._versions.get((name, version))

        if release is None:
            raise ValidationError(
                f"Library release {name}@{version} does not exist."
            )

        if not release.tested:
            raise PolicyError("Untested library releases cannot be used.")

        if require_approval and not release.approved:
            raise PolicyError("Library release has not been approved.")

        return release


class PipelineSteps:
    """
    Reusable pipeline operations.

    In a real Jenkins Shared Library, corresponding implementations
    would normally be organized under vars/, src/, and resources/.
    """

    def __init__(self, context: PipelineContext):
        self.context = context
        self.credentials: dict[str, str] = {}

    def checkout(self, repository: str) -> dict[str, str]:
        if not repository.startswith(("https://", "ssh://")):
            raise ValidationError("Repository must use HTTPS or SSH.")

        logger.info("Checking out source for %s", self.context.application)

        return {
            "repository": repository,
            "branch": self.context.branch,
            "commit": "a1b2c3d4e5f6789",
        }

    def validate(self, configuration: dict[str, Any]) -> None:
        required = {"application", "version", "environment"}

        missing = required - configuration.keys()

        if missing:
            raise ValidationError(
                f"Missing configuration: {sorted(missing)}"
            )

        if configuration["application"] != self.context.application:
            raise ValidationError("Application configuration mismatch.")

    def retry(
        self,
        operation: Callable[[], Any],
        attempts: int = 3,
        delay: float = 0.05,
    ) -> Any:
        if not 1 <= attempts <= 10:
            raise ValidationError("Attempts must be between 1 and 10.")

        last_error: Exception | None = None

        for attempt in range(1, attempts + 1):
            try:
                logger.info("Execution attempt %d/%d", attempt, attempts)
                return operation()
            except Exception as exc:
                last_error = exc
                logger.warning("Attempt %d failed: %s", attempt, exc)

                if attempt < attempts:
                    time.sleep(delay * attempt)

        raise StageError("All retry attempts failed.") from last_error

    def with_credentials(
        self,
        credential_id: str,
        secret: str,
        operation: Callable[[], Any],
    ) -> Any:
        if not credential_id or not secret:
            raise ValidationError("Credential identifier and secret are required.")

        self.credentials[credential_id] = secret

        try:
            return operation()
        finally:
            # Remove secrets immediately after the protected operation.
            self.credentials.pop(credential_id, None)

    def deploy(
        self,
        artifact: str,
        approval: bool = False,
    ) -> dict[str, str]:
        if not artifact:
            raise ValidationError("Artifact cannot be empty.")

        if self.context.environment == Environment.PRODUCTION and not approval:
            raise PolicyError("Production deployment requires approval.")

        logger.info(
            "Deploying %s to %s",
            artifact,
            self.context.environment.value,
        )

        return {
            "artifact": artifact,
            "environment": self.context.environment.value,
            "deployment": "completed",
        }


class PipelineEngine:
    """Executes an ordered pipeline with independent stage tracking."""

    def __init__(self, context: PipelineContext):
        self.context = context
        self.steps = PipelineSteps(context)

    def execute_stage(
        self,
        name: str,
        operation: Callable[[], Any],
    ) -> Any:
        result = StageResult(name=name, status=StageStatus.RUNNING)
        start = time.perf_counter()

        logger.info("Starting stage: %s", name)

        try:
            output = operation()
            result.status = StageStatus.SUCCESS
            result.message = "Stage completed successfully."
            return output

        except Exception as exc:
            result.status = StageStatus.FAILED
            result.message = str(exc)
            raise StageError(f"Stage '{name}' failed: {exc}") from exc

        finally:
            result.duration_seconds = time.perf_counter() - start
            self.context.add_result(result)

            logger.info(
                "Stage %s: %s",
                name,
                result.status.value,
            )

    def run(
        self,
        repository: str,
        approval: bool = False,
    ) -> PipelineContext:
        if self.context.status != PipelineStatus.CREATED:
            raise PipelineError("Pipeline can only execute once.")

        self.context.status = PipelineStatus.RUNNING
        self.context.started_at = datetime.now(timezone.utc).isoformat()

        try:
            self.execute_stage(
                "configuration",
                lambda: self.steps.validate({
                    "application": self.context.application,
                    "version": "1.0.0",
                    "environment": self.context.environment.value,
                }),
            )

            checkout = self.execute_stage(
                "checkout",
                lambda: self.steps.checkout(repository),
            )

            self.execute_stage(
                "build",
                lambda: {
                    "artifact": (
                        f"{self.context.application}-"
                        f"{self.context.build_number}.jar"
                    )
                },
            )

            self.execute_stage(
                "test",
                lambda: self.steps.retry(
                    lambda: self.run_tests(checkout),
                    attempts=3,
                ),
            )

            self.execute_stage(
                "package",
                lambda: {
                    "artifact": (
                        f"{self.context.application}-"
                        f"{self.context.build_number}.jar"
                    )
                },
            )

            self.execute_stage(
                "deploy",
                lambda: self.steps.deploy(
                    f"{self.context.application}-"
                    f"{self.context.build_number}.jar",
                    approval=approval,
                ),
            )

            self.context.status = PipelineStatus.SUCCESS

        except Exception:
            self.context.status = PipelineStatus.FAILED
            logger.exception("Pipeline execution failed.")

        finally:
            self.context.finished_at = datetime.now(timezone.utc).isoformat()

        return self.context

    @staticmethod
    def run_tests(checkout: dict[str, str]) -> dict[str, Any]:
        if not checkout.get("commit"):
            raise StageError("Checkout did not produce a commit.")

        return {
            "unit_tests": 42,
            "passed": 42,
            "failed": 0,
        }


def save_execution_report(
    context: PipelineContext,
    destination: Path,
) -> None:
    """Persist a JSON execution report without storing credentials."""

    report = {
        "application": context.application,
        "branch": context.branch,
        "environment": context.environment.value,
        "build_number": context.build_number,
        "library": asdict(context.library),
        "status": context.status.value,
        "started_at": context.started_at,
        "finished_at": context.finished_at,
        "stages": [
            {
                **asdict(stage),
                "status": stage.status.value,
            }
            for stage in context.results
        ],
    }

    destination.parent.mkdir(parents=True, exist_ok=True)

    temporary = destination.with_suffix(".tmp")

    try:
        temporary.write_text(
            json.dumps(report, indent=2),
            encoding="utf-8",
        )
        temporary.replace(destination)
    except OSError:
        temporary.unlink(missing_ok=True)
        raise


def run_tests() -> None:
    registry = SharedLibraryRegistry()

    stable = LibraryVersion(
        name="enterprise-ci",
        version="2.1.0",
        approved=True,
        tested=True,
        commit="a1b2c3d4e5f6789",
    )

    registry.register(stable)

    resolved = registry.resolve("enterprise-ci", "2.1.0")

    assert resolved.version == "2.1.0"

    try:
        registry.resolve("enterprise-ci", "9.9.9")
        raise AssertionError("Unknown versions must be rejected.")
    except ValidationError:
        pass

    context = PipelineContext(
        application="payment-service",
        branch="main",
        environment=Environment.STAGING,
        build_number=104,
        library=resolved,
    )

    engine = PipelineEngine(context)

    result = engine.run(
        repository="https://git.example.com/platform/payment-service.git"
    )

    assert result.status == PipelineStatus.SUCCESS
    assert len(result.results) == 6

    production_context = PipelineContext(
        application="payment-service",
        branch="main",
        environment=Environment.PRODUCTION,
        build_number=105,
        library=resolved,
    )

    production_result = PipelineEngine(production_context).run(
        repository="https://git.example.com/platform/payment-service.git",
        approval=False,
    )

    assert production_result.status == PipelineStatus.FAILED
    assert production_result.results[-1].status == StageStatus.FAILED

    logger.info("All assertions passed.")


def main() -> None:
    registry = SharedLibraryRegistry()

    registry.register(
        LibraryVersion(
            name="enterprise-ci",
            version="2.1.0",
            approved=True,
            tested=True,
            commit="a1b2c3d4e5f6789",
        )
    )

    library = registry.resolve("enterprise-ci", "2.1.0")

    context = PipelineContext(
        application="inventory-service",
        branch="main",
        environment=Environment.STAGING,
        build_number=205,
        library=library,
    )

    engine = PipelineEngine(context)

    result = engine.run(
        "https://git.example.com/platform/inventory-service.git"
    )

    report_path = Path("pipeline-report.json")
    save_execution_report(result, report_path)

    print("\nPIPELINE EXECUTION REPORT")
    print("=" * 55)
    print(f"Application: {result.application}")
    print(f"Library:     {result.library.name}@{result.library.version}")
    print(f"Environment: {result.environment.value}")
    print(f"Build:       {result.build_number}")
    print(f"Status:      {result.status.value}")

    for stage in result.results:
        print(
            f"{stage.name:15} {stage.status.value:10} "
            f"{stage.duration_seconds:.4f}s"
        )

    print(f"\nReport saved to: {report_path.resolve()}")

    run_tests()


if __name__ == "__main__":
    main()
