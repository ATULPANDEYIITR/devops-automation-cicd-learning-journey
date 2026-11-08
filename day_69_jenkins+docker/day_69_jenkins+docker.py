#!/usr/bin/env python3
"""
Jenkins + Docker: Automated Build and Deployment Pipeline

Features:
- Pipeline stage management
- Docker image validation and tagging
- Build, test, push, and deployment workflows
- Environment-based configuration
- Failure handling and retry logic
- Pipeline execution history
- JSON reporting
- Dry-run and real Docker execution modes

Usage:
    python jenkins_docker_pipeline.py
    python jenkins_docker_pipeline.py --execute
    python jenkins_docker_pipeline.py --execute --push
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------
# Logging
# ---------------------------------------------------------

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger("jenkins-docker")


# ---------------------------------------------------------
# Pipeline states
# ---------------------------------------------------------

class StageStatus(Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class PipelineStatus(Enum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"


@dataclass
class StageResult:
    name: str
    status: StageStatus = StageStatus.PENDING
    duration_seconds: float = 0.0
    message: str = ""
    attempts: int = 0


@dataclass
class PipelineConfig:
    application: str
    dockerfile: str
    context: str
    image_repository: str
    image_tag: str
    docker_registry: str
    compose_file: str
    retries: int = 2
    timeout: int = 120
    execute: bool = False
    push: bool = False

    @property
    def image(self) -> str:
        return f"{self.image_repository}:{self.image_tag}"

    def validate(self) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]{0,62}", self.application):
            raise ValueError("Invalid application name.")

        if not re.fullmatch(
            r"[a-z0-9]+(?:[._/-][a-z0-9]+)*",
            self.image_repository,
        ):
            raise ValueError("Invalid Docker image repository.")

        if not re.fullmatch(
            r"[a-zA-Z0-9_][a-zA-Z0-9_.-]{0,127}",
            self.image_tag,
        ):
            raise ValueError("Invalid Docker image tag.")

        if self.retries < 0 or self.timeout <= 0:
            raise ValueError("Invalid retry or timeout configuration.")

        if not Path(self.dockerfile).is_file():
            raise FileNotFoundError(self.dockerfile)

        if not Path(self.context).is_dir():
            raise NotADirectoryError(self.context)

        if not Path(self.compose_file).is_file():
            raise FileNotFoundError(self.compose_file)


# ---------------------------------------------------------
# Pipeline execution engine
# ---------------------------------------------------------

class DockerPipeline:

    def __init__(self, config: PipelineConfig):
        config.validate()

        self.config = config
        self.status = PipelineStatus.CREATED
        self.results: list[StageResult] = []
        self.started_at: Optional[str] = None

    def run_command(
        self,
        command: list[str],
        description: str,
        retry: bool = False,
    ) -> bool:

        if not self.config.execute:
            logger.info("[DRY RUN] %s: %s", description, command)
            return True

        if shutil.which(command[0]) is None:
            logger.error("Executable not found: %s", command[0])
            return False

        attempts = self.config.retries + 1 if retry else 1

        for attempt in range(1, attempts + 1):
            logger.info("%s (attempt %s/%s)", description, attempt, attempts)

            try:
                completed = subprocess.run(
                    command,
                    capture_output=True,
                    text=True,
                    timeout=self.config.timeout,
                    check=False,
                )

                if completed.returncode == 0:
                    if completed.stdout:
                        logger.info(completed.stdout.strip())
                    return True

                logger.error(
                    "%s failed: %s",
                    description,
                    completed.stderr.strip(),
                )

            except subprocess.TimeoutExpired:
                logger.error("%s timed out.", description)

            except OSError as exc:
                logger.error("Command execution error: %s", exc)
                return False

            if attempt < attempts:
                time.sleep(min(2 ** (attempt - 1), 8))

        return False

    def execute_stage(
        self,
        name: str,
        action,
        retry: bool = False,
    ) -> bool:

        result = StageResult(name=name)
        result.status = StageStatus.RUNNING

        start = time.monotonic()

        try:
            attempts = self.config.retries + 1 if retry else 1

            for attempt in range(1, attempts + 1):
                result.attempts = attempt

                if action():
                    result.status = StageStatus.SUCCESS
                    result.message = "Stage completed."
                    break

                if attempt < attempts:
                    time.sleep(min(2 ** (attempt - 1), 8))

            if result.status != StageStatus.SUCCESS:
                result.status = StageStatus.FAILED
                result.message = "Stage failed after configured attempts."

        except Exception as exc:
            result.status = StageStatus.FAILED
            result.message = str(exc)
            logger.exception("Stage %s encountered an exception.", name)

        finally:
            result.duration_seconds = round(
                time.monotonic() - start,
                3,
            )
            self.results.append(result)

        logger.info(
            "%s: %s",
            name,
            result.status.value,
        )

        return result.status == StageStatus.SUCCESS

    # -----------------------------------------------------
    # Individual pipeline stages
    # -----------------------------------------------------

    def checkout(self) -> bool:
        return self.execute_stage(
            "CHECKOUT",
            lambda: (
                Path(self.config.context).is_dir()
                and Path(self.config.dockerfile).is_file()
            ),
        )

    def build(self) -> bool:
        command = [
            "docker",
            "build",
            "--pull",
            "-f",
            self.config.dockerfile,
            "-t",
            self.config.image,
            self.config.context,
        ]

        return self.execute_stage(
            "DOCKER_BUILD",
            lambda: self.run_command(
                command,
                "Building Docker image",
            ),
            retry=True,
        )

    def test(self) -> bool:
        command = [
            "docker",
            "image",
            "inspect",
            self.config.image,
        ]

        return self.execute_stage(
            "IMAGE_VALIDATION",
            lambda: self.run_command(
                command,
                "Validating Docker image",
            ),
        )

    def push(self) -> bool:
        if not self.config.push:
            result = StageResult(
                name="DOCKER_PUSH",
                status=StageStatus.SKIPPED,
                message="Image publishing disabled.",
            )
            self.results.append(result)
            return True

        if not self.config.docker_registry:
            raise ValueError("Docker registry is required for publishing.")

        command = [
            "docker",
            "push",
            self.config.image,
        ]

        return self.execute_stage(
            "DOCKER_PUSH",
            lambda: self.run_command(
                command,
                "Publishing Docker image",
                retry=True,
            ),
        )

    def deploy(self) -> bool:
        command = [
            "docker",
            "compose",
            "-f",
            self.config.compose_file,
            "up",
            "-d",
            "--no-build",
        ]

        return self.execute_stage(
            "DEPLOYMENT",
            lambda: self.run_command(
                command,
                "Deploying application",
                retry=True,
            ),
        )

    # -----------------------------------------------------
    # Pipeline orchestration
    # -----------------------------------------------------

    def run(self) -> PipelineStatus:
        self.status = PipelineStatus.RUNNING
        self.started_at = datetime.now(timezone.utc).isoformat()

        logger.info("Starting pipeline for %s", self.config.application)
        logger.info("Docker image: %s", self.config.image)

        stages = [
            self.checkout,
            self.build,
            self.test,
            self.push,
            self.deploy,
        ]

        try:
            for stage in stages:
                if not stage():
                    self.status = PipelineStatus.FAILED
                    break
            else:
                self.status = PipelineStatus.SUCCESS

        except Exception:
            self.status = PipelineStatus.FAILED
            logger.exception("Pipeline execution failed.")

        logger.info("Pipeline result: %s", self.status.value)

        return self.status

    def report(self) -> dict:
        return {
            "application": self.config.application,
            "image": self.config.image,
            "status": self.status.value,
            "started_at": self.started_at,
            "stages": [
                {
                    **asdict(result),
                    "status": result.status.value,
                }
                for result in self.results
            ],
        }

    def save_report(self, filename: str = "pipeline-report.json") -> None:
        destination = Path(filename)

        destination.write_text(
            json.dumps(self.report(), indent=4),
            encoding="utf-8",
        )

        logger.info("Report saved to %s", destination)


# ---------------------------------------------------------
# Application entry point
# ---------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Jenkins and Docker pipeline automation."
    )

    parser.add_argument(
        "--execute",
        action="store_true",
        help="Execute actual Docker commands.",
    )

    parser.add_argument(
        "--push",
        action="store_true",
        help="Publish the image to the configured registry.",
    )

    parser.add_argument(
        "--tag",
        default="1.0.0",
        help="Docker image tag.",
    )

    args = parser.parse_args()

    config = PipelineConfig(
        application="inventory-api",
        dockerfile="Dockerfile",
        context=".",
        image_repository=os.getenv(
            "IMAGE_REPOSITORY",
            "inventory-api",
        ),
        image_tag=args.tag,
        docker_registry=os.getenv(
            "DOCKER_REGISTRY",
            "docker.io",
        ),
        compose_file="compose.yaml",
        execute=args.execute,
        push=args.push,
    )

    try:
        pipeline = DockerPipeline(config)
        status = pipeline.run()
        pipeline.save_report()

        print(json.dumps(pipeline.report(), indent=4))

        return 0 if status == PipelineStatus.SUCCESS else 1

    except (ValueError, OSError) as exc:
        logger.error("Configuration error: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
