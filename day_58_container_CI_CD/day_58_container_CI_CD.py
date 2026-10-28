#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable, Iterable


class PipelineState(str, Enum):
    CREATED = "created"
    BUILT = "built"
    TESTED = "tested"
    SCANNED = "scanned"
    PUBLISHED = "published"
    FAILED = "failed"


class PipelineError(RuntimeError):
    pass


@dataclass(frozen=True)
class ImageConfig:
    repository: str
    tag: str
    context: Path
    dockerfile: Path
    registry: str

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z0-9][a-z0-9._/-]*", self.repository):
            raise ValueError("Invalid image repository name")
        if not re.fullmatch(r"[A-Za-z0-9_.-]+", self.tag):
            raise ValueError("Invalid image tag")
        if not self.context.is_dir():
            raise ValueError(f"Build context does not exist: {self.context}")
        if not self.dockerfile.is_file():
            raise ValueError(f"Dockerfile does not exist: {self.dockerfile}")

    @property
    def image_ref(self) -> str:
        return f"{self.registry.rstrip('/')}/{self.repository}:{self.tag}"


@dataclass
class PipelineResult:
    state: PipelineState
    image_ref: str
    digest: str | None = None
    findings: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)


class CommandRunner:
    """Runs external commands while keeping output available for diagnostics."""

    def run(self, command: list[str], *, check: bool = True) -> str:
        if not command:
            raise ValueError("Command cannot be empty")

        print("$", " ".join(command))
        completed = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )

        if completed.stdout:
            print(completed.stdout, end="")

        if check and completed.returncode != 0:
            raise PipelineError(
                f"Command failed with exit code {completed.returncode}: "
                f"{' '.join(command)}"
            )

        return completed.stdout


class DockerPipeline:
    def __init__(
        self,
        config: ImageConfig,
        runner: CommandRunner | None = None,
    ) -> None:
        self.config = config
        self.runner = runner or CommandRunner()
        self.state = PipelineState.CREATED
        self.result = PipelineResult(
            state=self.state,
            image_ref=config.image_ref,
        )

    def _transition(self, state: PipelineState) -> None:
        self.state = state
        self.result.state = state

    def check_docker(self) -> None:
        self.runner.run(["docker", "version", "--format", "{{.Server.Version}}"])

    def build(self) -> None:
        self.config.validate()
        self.check_docker()

        self.runner.run(
            [
                "docker",
                "build",
                "--pull",
                "--tag",
                self.config.image_ref,
                "--file",
                str(self.config.dockerfile),
                str(self.config.context),
            ]
        )

        self._transition(PipelineState.BUILT)

    def test(self) -> None:
        if self.state != PipelineState.BUILT:
            raise PipelineError("Image must be built before testing")

        # The test container is intentionally removed after execution.
        # Tests are expected to return a non-zero exit status on failure.
        self.runner.run(
            [
                "docker",
                "run",
                "--rm",
                self.config.image_ref,
                "python",
                "-m",
                "unittest",
                "discover",
                "-s",
                "/app/tests",
            ]
        )

        self._transition(PipelineState.TESTED)

    def scan(self) -> None:
        if self.state != PipelineState.TESTED:
            raise PipelineError("Image must pass tests before scanning")

        scanner = os.environ.get("CONTAINER_SCANNER", "trivy")

        # A scanner is deliberately required rather than silently skipped.
        # This prevents an accidental publish of an unscanned image.
        self.runner.run(
            [
                scanner,
                "image",
                "--exit-code",
                "1",
                "--severity",
                "HIGH,CRITICAL",
                self.config.image_ref,
            ]
        )

        self._transition(PipelineState.SCANNED)

    def inspect_digest(self) -> str:
        output = self.runner.run(
            [
                "docker",
                "image",
                "inspect",
                self.config.image_ref,
                "--format",
                "{{json .RepoDigests}}",
            ]
        ).strip()

        if not output:
            raise PipelineError("Docker returned no image digest information")

        # Local images may not have a registry digest yet. Calculate a
        # deterministic content fingerprint for pipeline traceability.
        digest = hashlib.sha256(output.encode("utf-8")).hexdigest()
        self.result.digest = f"sha256:{digest}"
        return self.result.digest

    def publish(self) -> None:
        if self.state != PipelineState.SCANNED:
            raise PipelineError("Image must pass scanning before publishing")

        self.runner.run(["docker", "push", self.config.image_ref])
        self.inspect_digest()
        self._transition(PipelineState.PUBLISHED)

    def run(self, publish: bool = False) -> PipelineResult:
        try:
            self.build()
            self.test()
            self.scan()

            if publish:
                self.publish()
            else:
                self.inspect_digest()

            return self.result
        except Exception as exc:
            self.result.findings.append(str(exc))
            self._transition(PipelineState.FAILED)
            raise


def create_demo_project(root: Path) -> ImageConfig:
    """
    Creates a tiny executable project so the script can be demonstrated
    without requiring a pre-existing application directory.
    """
    app = root / "app"
    tests = app / "tests"
    tests.mkdir(parents=True)

    (app / "app.py").write_text(
        "def add(a, b):\n"
        "    return a + b\n",
        encoding="utf-8",
    )

    (tests / "test_app.py").write_text(
        "import unittest\n"
        "from app import add\n\n"
        "class TestApp(unittest.TestCase):\n"
        "    def test_add(self):\n"
        "        self.assertEqual(add(2, 3), 5)\n\n"
        "if __name__ == '__main__':\n"
        "    unittest.main()\n",
        encoding="utf-8",
    )

    dockerfile = app / "Dockerfile"
    dockerfile.write_text(
        "FROM python:3.13-slim\n"
        "WORKDIR /app\n"
        "COPY . /app\n"
        "CMD [\"python\", \"-m\", \"unittest\", \"discover\", \"-s\", \"/app/tests\"]\n",
        encoding="utf-8",
    )

    return ImageConfig(
        repository="ci-demo/container-app",
        tag="pipeline-test",
        context=app,
        dockerfile=dockerfile,
        registry=os.environ.get("CONTAINER_REGISTRY", "registry.example.com"),
    )


def print_report(result: PipelineResult) -> None:
    report = {
        "state": result.state.value,
        "image": result.image_ref,
        "digest": result.digest,
        "findings": result.findings,
    }
    print(json.dumps(report, indent=2))


def main() -> int:
    """
    Usage:
      python container_pipeline.py
      python container_pipeline.py --publish /path/to/project

    The publish path requires Docker credentials for the configured registry
    and a locally installed Trivy-compatible scanner.
    """
    publish = "--publish" in sys.argv
    supplied_context = next(
        (Path(arg) for arg in sys.argv[1:] if not arg.startswith("--")),
        None,
    )

    if supplied_context:
        dockerfile = supplied_context / "Dockerfile"
        config = ImageConfig(
            repository=os.environ.get("IMAGE_REPOSITORY", "ci-demo/app"),
            tag=os.environ.get("IMAGE_TAG", "ci"),
            context=supplied_context,
            dockerfile=dockerfile,
            registry=os.environ.get(
                "CONTAINER_REGISTRY",
                "registry.example.com",
            ),
        )
    else:
        with tempfile.TemporaryDirectory(prefix="container-ci-") as temp:
            config = create_demo_project(Path(temp))
            pipeline = DockerPipeline(config)
            try:
                result = pipeline.run(publish=False)
            except Exception:
                print_report(pipeline.result)
                return 1
            print_report(result)
            return 0

    pipeline = DockerPipeline(config)

    try:
        result = pipeline.run(publish=publish)
        print_report(result)
        return 0
    except Exception:
        print_report(pipeline.result)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
