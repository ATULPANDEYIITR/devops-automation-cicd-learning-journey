#!/usr/bin/env python3
"""
Jenkinsfile Pipeline Execution Simulator

Demonstrates:
- Declarative pipeline structure
- Pipeline stages and steps
- Environment variables
- Stage-level environment overrides
- Stage conditions
- Success, failure, and unstable states
- Post-build actions
- Execution history and reporting
- Validation and error handling

Requires Python 3.10 or later.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Callable


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger("jenkins-pipeline")


class BuildStatus(str, Enum):
    NOT_BUILT = "NOT_BUILT"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    UNSTABLE = "UNSTABLE"
    ABORTED = "ABORTED"


class StageStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    SKIPPED = "SKIPPED"


class PipelineError(Exception):
    """Base exception for pipeline execution."""


class ConfigurationError(PipelineError):
    """Raised when pipeline configuration is invalid."""


class StepError(PipelineError):
    """Raised when a pipeline step fails."""


@dataclass
class Step:
    name: str
    action: Callable[[dict[str, str]], Any]
    timeout_seconds: float = 30.0
    continue_on_error: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ConfigurationError("Step name cannot be empty.")
        if self.timeout_seconds <= 0:
            raise ConfigurationError("Step timeout must be positive.")


@dataclass
class Stage:
    name: str
    steps: list[Step]
    environment: dict[str, str] = field(default_factory=dict)
    condition: Callable[[dict[str, str]], bool] | None = None
    status: StageStatus = StageStatus.PENDING
    duration_seconds: float = 0.0
    error: str | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ConfigurationError("Stage name cannot be empty.")
        if not self.steps:
            raise ConfigurationError(
                f"Stage '{self.name}' must contain at least one step."
            )


@dataclass
class PostActions:
    always: list[Callable[[dict[str, str]], None]] = field(
        default_factory=list
    )
    success: list[Callable[[dict[str, str]], None]] = field(
        default_factory=list
    )
    failure: list[Callable[[dict[str, str]], None]] = field(
        default_factory=list
    )
    unstable: list[Callable[[dict[str, str]], None]] = field(
        default_factory=list
    )
    cleanup: list[Callable[[dict[str, str]], None]] = field(
        default_factory=list
    )


@dataclass
class PipelineReport:
    name: str
    status: BuildStatus
    started_at: str
    completed_at: str
    duration_seconds: float
    stages: list[dict[str, Any]]
    environment_keys: list[str]


class JenkinsPipeline:
    """
    A small declarative pipeline execution engine.

    Environment values are copied into stage-specific dictionaries.
    Secret values should be injected by a secret manager rather than
    stored directly in source-controlled pipeline configuration.
    """

    RESERVED_ENVIRONMENT = {
        "PATH",
        "HOME",
        "USER",
        "SHELL",
    }

    def __init__(
        self,
        name: str,
        stages: list[Stage],
        environment: dict[str, str] | None = None,
        post: PostActions | None = None,
    ) -> None:
        self.name = name
        self.stages = stages
        self.environment = dict(environment or {})
        self.post = post or PostActions()
        self.status = BuildStatus.NOT_BUILT
        self.started_at: datetime | None = None
        self.completed_at: datetime | None = None
        self.history: list[dict[str, Any]] = []

        self._validate()

    def _validate(self) -> None:
        if not self.name.strip():
            raise ConfigurationError("Pipeline name cannot be empty.")

        if not self.stages:
            raise ConfigurationError("Pipeline requires at least one stage.")

        stage_names = [stage.name for stage in self.stages]

        if len(stage_names) != len(set(stage_names)):
            raise ConfigurationError("Stage names must be unique.")

        for key, value in self.environment.items():
            if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
                raise ConfigurationError(
                    f"Invalid environment variable name: {key}"
                )

            if not isinstance(value, str):
                raise ConfigurationError(
                    f"Environment value for {key} must be a string."
                )

    def _record(
        self,
        stage: str,
        event: str,
        details: str = "",
    ) -> None:
        self.history.append(
            {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "stage": stage,
                "event": event,
                "details": details,
            }
        )

    def _execute_step(
        self,
        stage: Stage,
        step: Step,
        environment: dict[str, str],
    ) -> None:
        logger.info("Executing step: %s", step.name)
        start = time.perf_counter()

        try:
            result = step.action(environment)

            elapsed = time.perf_counter() - start

            if elapsed > step.timeout_seconds:
                raise StepError(
                    f"Step '{step.name}' exceeded its timeout."
                )

            self._record(
                stage.name,
                "STEP_SUCCESS",
                f"{step.name}; duration={elapsed:.4f}s; result={result}",
            )

        except Exception as exc:
            self._record(
                stage.name,
                "STEP_FAILURE",
                f"{step.name}: {exc}",
            )

            logger.exception("Step failed: %s", step.name)

            if not step.continue_on_error:
                raise StepError(
                    f"Step '{step.name}' failed: {exc}"
                ) from exc

    def _execute_stage(self, stage: Stage) -> None:
        if stage.condition is not None:
            if not stage.condition(dict(self.environment)):
                stage.status = StageStatus.SKIPPED
                self._record(stage.name, "STAGE_SKIPPED")
                logger.info("Skipping stage: %s", stage.name)
                return

        stage.status = StageStatus.RUNNING
        start = time.perf_counter()

        self._record(stage.name, "STAGE_STARTED")

        stage_environment = {
            **self.environment,
            **stage.environment,
        }

        try:
            for step in stage.steps:
                self._execute_step(
                    stage,
                    step,
                    stage_environment,
                )

            stage.status = StageStatus.SUCCESS
            self._record(stage.name, "STAGE_SUCCESS")

        except StepError as exc:
            stage.status = StageStatus.FAILURE
            stage.error = str(exc)
            self._record(
                stage.name,
                "STAGE_FAILURE",
                str(exc),
            )
            raise

        finally:
            stage.duration_seconds = time.perf_counter() - start

    def _run_post_actions(self) -> None:
        actions = list(self.post.always)

        if self.status == BuildStatus.SUCCESS:
            actions.extend(self.post.success)

        elif self.status == BuildStatus.FAILURE:
            actions.extend(self.post.failure)

        elif self.status == BuildStatus.UNSTABLE:
            actions.extend(self.post.unstable)

        # Cleanup executes regardless of the build result.
        actions.extend(self.post.cleanup)

        for action in actions:
            try:
                action(dict(self.environment))
                self._record("POST", "POST_ACTION_SUCCESS")
            except Exception as exc:
                self._record(
                    "POST",
                    "POST_ACTION_FAILURE",
                    str(exc),
                )
                logger.exception("Post action failed.")

                if self.status == BuildStatus.SUCCESS:
                    self.status = BuildStatus.FAILURE

    def run(self) -> PipelineReport:
        if self.status == BuildStatus.RUNNING:
            raise PipelineError("Pipeline is already running.")

        if self.status != BuildStatus.NOT_BUILT:
            raise PipelineError(
                "A pipeline instance can only be executed once."
            )

        self.started_at = datetime.now(timezone.utc)
        start = time.perf_counter()
        self.status = BuildStatus.RUNNING

        logger.info("Pipeline started: %s", self.name)

        try:
            for stage in self.stages:
                self._execute_stage(stage)

            self.status = BuildStatus.SUCCESS

        except StepError:
            self.status = BuildStatus.FAILURE

            # Remaining stages are not executed after a failure.
            for stage in self.stages:
                if stage.status == StageStatus.PENDING:
                    stage.status = StageStatus.SKIPPED

        except Exception:
            self.status = BuildStatus.FAILURE
            logger.exception("Unexpected pipeline error.")

        finally:
            self._run_post_actions()
            self.completed_at = datetime.now(timezone.utc)

        elapsed = time.perf_counter() - start

        report = PipelineReport(
            name=self.name,
            status=self.status,
            started_at=self.started_at.isoformat(),
            completed_at=self.completed_at.isoformat(),
            duration_seconds=round(elapsed, 4),
            stages=[
                {
                    "name": stage.name,
                    "status": stage.status.value,
                    "duration_seconds": round(
                        stage.duration_seconds, 4
                    ),
                    "error": stage.error,
                }
                for stage in self.stages
            ],
            environment_keys=sorted(self.environment.keys()),
        )

        logger.info(
            "Pipeline completed: %s",
            self.status.value,
        )

        return report


# ---------------------------------------------------------
# Pipeline steps
# ---------------------------------------------------------

def checkout(environment: dict[str, str]) -> str:
    branch = environment.get("GIT_BRANCH", "main")

    if not re.fullmatch(r"[A-Za-z0-9._/-]+", branch):
        raise ValueError("Invalid Git branch name.")

    return f"Checked out branch {branch}"


def install_dependencies(environment: dict[str, str]) -> str:
    package_manager = environment.get(
        "PACKAGE_MANAGER",
        "pip",
    )

    if package_manager not in {"pip", "npm", "maven"}:
        raise ValueError("Unsupported package manager.")

    return f"Dependencies installed using {package_manager}"


def run_tests(environment: dict[str, str]) -> str:
    test_result = environment.get("TEST_RESULT", "PASS")

    if test_result == "FAIL":
        raise RuntimeError("Unit tests failed.")

    if test_result == "UNSTABLE":
        return "Tests completed with warnings."

    return "All unit tests passed."


def build_application(environment: dict[str, str]) -> str:
    application = environment.get(
        "APPLICATION_NAME",
        "sample-service",
    )

    return f"Built artifact for {application}"


def deploy_application(environment: dict[str, str]) -> str:
    target = environment.get("DEPLOY_TARGET", "staging")

    if target not in {"staging", "production"}:
        raise ValueError("Invalid deployment target.")

    return f"Deployment completed for {target}"


def notify(environment: dict[str, str]) -> None:
    logger.info(
        "Notification: build %s finished with status %s",
        environment.get("BUILD_NUMBER", "unknown"),
        environment.get("BUILD_STATUS", "available"),
    )


def archive_artifacts(environment: dict[str, str]) -> None:
    logger.info(
        "Archiving artifacts for %s",
        environment.get("APPLICATION_NAME", "application"),
    )


def cleanup(environment: dict[str, str]) -> None:
    logger.info("Cleaning temporary build resources.")


def main() -> int:
    pipeline_environment = {
        "GIT_BRANCH": "main",
        "PACKAGE_MANAGER": "pip",
        "APPLICATION_NAME": "inventory-service",
        "BUILD_NUMBER": "104",
        "DEPLOY_TARGET": "staging",
        "TEST_RESULT": "PASS",
        "CI": "true",
    }

    pipeline = JenkinsPipeline(
        name="Inventory Application CI/CD",
        environment=pipeline_environment,
        stages=[
            Stage(
                name="Checkout",
                steps=[
                    Step("Git checkout", checkout),
                ],
            ),
            Stage(
                name="Dependencies",
                steps=[
                    Step(
                        "Install dependencies",
                        install_dependencies,
                    ),
                ],
            ),
            Stage(
                name="Build",
                steps=[
                    Step(
                        "Compile application",
                        build_application,
                    ),
                ],
            ),
            Stage(
                name="Test",
                steps=[
                    Step("Run unit tests", run_tests),
                ],
            ),
            Stage(
                name="Deploy",
                environment={
                    "DEPLOY_TARGET": "staging",
                },
                condition=lambda env: env.get("CI") == "true",
                steps=[
                    Step(
                        "Deploy application",
                        deploy_application,
                    ),
                ],
            ),
        ],
        post=PostActions(
            always=[notify],
            success=[archive_artifacts],
            failure=[
                lambda env: logger.error(
                    "Build failed. Investigate pipeline logs."
                )
            ],
            cleanup=[cleanup],
        ),
    )

    report = pipeline.run()

    print("\nPIPELINE REPORT")
    print(json.dumps(asdict(report), indent=2, default=str))

    print("\nEXECUTION HISTORY")
    print(json.dumps(pipeline.history, indent=2))

    assert report.status == BuildStatus.SUCCESS
    assert all(
        stage["status"] in {
            "SUCCESS",
            "SKIPPED",
        }
        for stage in report.stages
    )

    # Verify that a failed test prevents deployment.
    failing_pipeline = JenkinsPipeline(
        name="Failure Demonstration",
        environment={
            "TEST_RESULT": "FAIL",
            "DEPLOY_TARGET": "production",
        },
        stages=[
            Stage(
                name="Test",
                steps=[
                    Step("Run failing tests", run_tests),
                ],
            ),
            Stage(
                name="Deploy",
                steps=[
                    Step("Deploy", deploy_application),
                ],
            ),
        ],
    )

    failed_report = failing_pipeline.run()

    assert failed_report.status == BuildStatus.FAILURE
    assert (
        failing_pipeline.stages[1].status
        == StageStatus.SKIPPED
    )

    print("\nAll pipeline validation assertions passed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
