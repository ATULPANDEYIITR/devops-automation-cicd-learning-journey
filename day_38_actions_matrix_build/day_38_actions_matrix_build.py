"""
Actions Matrix Builds: Matrix Strategy and Multi-Version Testing

A self-contained simulation of a CI matrix engine inspired by GitHub Actions.
The program models:
- Matrix dimensions and Cartesian-product expansion
- Include and exclude rules
- Multiple runtime versions
- Operating-system dimensions
- Dependency/test compatibility
- Fail-fast behavior
- Continue-on-error behavior
- Per-combination execution results
- Aggregated workflow conclusions
- Matrix validation and coverage analysis
- Artifact naming
- Retry behavior
- Production-oriented matrix design

Run with:
    python matrix_builds.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import product
from typing import Any, Callable, Iterable
import hashlib
import json
import random
import time


SUPPORTED_PYTHON = ("3.10", "3.11", "3.12", "3.13")
SUPPORTED_OS = ("ubuntu", "windows", "macos")


@dataclass(frozen=True)
class MatrixJob:
    """One concrete matrix combination after expansion."""

    python: str
    os: str
    dependency_mode: str
    experimental: bool = False

    @property
    def key(self) -> str:
        return f"python={self.python},os={self.os},deps={self.dependency_mode}"

    @property
    def identifier(self) -> str:
        raw = f"{self.python}|{self.os}|{self.dependency_mode}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:8]
        return f"matrix-{digest}"

    def artifact_name(self) -> str:
        return (
            f"test-results-py{self.python.replace('.', '')}-"
            f"{self.os}-{self.dependency_mode}"
        )


@dataclass
class JobResult:
    job: MatrixJob
    passed: bool
    skipped: bool = False
    attempts: int = 1
    duration_seconds: float = 0.0
    message: str = ""

    @property
    def status(self) -> str:
        if self.skipped:
            return "skipped"
        return "passed" if self.passed else "failed"


@dataclass
class MatrixDefinition:
    python_versions: list[str]
    operating_systems: list[str]
    dependency_modes: list[str]
    exclude: list[dict[str, str]] = field(default_factory=list)
    include: list[dict[str, Any]] = field(default_factory=list)


class MatrixValidationError(ValueError):
    pass


class MatrixEngine:
    """
    Expands a declarative matrix into concrete jobs.

    The base matrix is a Cartesian product. Exclusions remove combinations
    after expansion. Include entries can enrich an existing combination or
    add a new combination.
    """

    def __init__(self, definition: MatrixDefinition):
        self.definition = definition
        self._validate_definition()

    def _validate_definition(self) -> None:
        if not self.definition.python_versions:
            raise MatrixValidationError("At least one Python version is required.")

        if not self.definition.operating_systems:
            raise MatrixValidationError("At least one operating system is required.")

        if not self.definition.dependency_modes:
            raise MatrixValidationError("At least one dependency mode is required.")

        unknown_python = set(self.definition.python_versions) - set(SUPPORTED_PYTHON)
        if unknown_python:
            raise MatrixValidationError(
                f"Unsupported Python versions: {sorted(unknown_python)}"
            )

        unknown_os = set(self.definition.operating_systems) - set(SUPPORTED_OS)
        if unknown_os:
            raise MatrixValidationError(
                f"Unsupported operating systems: {sorted(unknown_os)}"
            )

        valid_dependency_modes = {"minimum", "locked", "latest"}
        unknown_modes = set(self.definition.dependency_modes) - valid_dependency_modes
        if unknown_modes:
            raise MatrixValidationError(
                f"Unsupported dependency modes: {sorted(unknown_modes)}"
            )

    @staticmethod
    def _matches(job: MatrixJob, rule: dict[str, Any]) -> bool:
        values = {
            "python": job.python,
            "os": job.os,
            "dependency_mode": job.dependency_mode,
            "experimental": job.experimental,
        }
        return all(values.get(key) == value for key, value in rule.items())

    def expand(self) -> list[MatrixJob]:
        jobs: list[MatrixJob] = []

        for python_version, operating_system, dependency_mode in product(
            self.definition.python_versions,
            self.definition.operating_systems,
            self.definition.dependency_modes,
        ):
            job = MatrixJob(
                python=python_version,
                os=operating_system,
                dependency_mode=dependency_mode,
            )

            if any(self._matches(job, rule) for rule in self.definition.exclude):
                continue

            jobs.append(job)

        # Include entries can add metadata to an existing combination or
        # introduce a deliberately special combination outside the base product.
        for item in self.definition.include:
            matching_index = next(
                (
                    index
                    for index, job in enumerate(jobs)
                    if all(
                        getattr(job, key, object()) == value
                        for key, value in item.items()
                        if key in {"python", "os", "dependency_mode"}
                    )
                ),
                None,
            )

            if matching_index is not None:
                existing = jobs[matching_index]
                jobs[matching_index] = MatrixJob(
                    python=existing.python,
                    os=existing.os,
                    dependency_mode=existing.dependency_mode,
                    experimental=bool(
                        item.get("experimental", existing.experimental)
                    ),
                )
            else:
                required = {"python", "os", "dependency_mode"}
                if not required.issubset(item):
                    raise MatrixValidationError(
                        "An include entry that creates a new job must define "
                        "python, os, and dependency_mode."
                    )

                jobs.append(
                    MatrixJob(
                        python=str(item["python"]),
                        os=str(item["os"]),
                        dependency_mode=str(item["dependency_mode"]),
                        experimental=bool(item.get("experimental", False)),
                    )
                )

        return jobs


class TestSuite:
    """
    Represents tests whose compatibility differs across matrix combinations.

    The failures are deterministic rather than random so the demonstration
    remains reproducible.
    """

    def run(self, job: MatrixJob) -> tuple[bool, str]:
        if job.python == "3.10" and job.dependency_mode == "latest":
            return False, "latest dependency set dropped Python 3.10 support"

        if job.os == "macos" and job.python == "3.13":
            return False, "native extension test is incompatible with this build"

        if job.os == "windows" and job.python == "3.10":
            return False, "Windows legacy compatibility test failed"

        if job.dependency_mode == "minimum" and job.python == "3.13":
            return False, "minimum dependency set lacks a Python 3.13-compatible release"

        return True, "unit, integration, packaging, and compatibility tests passed"


class MatrixRunner:
    """
    Executes concrete matrix jobs.

    fail_fast controls whether non-experimental failures cancel jobs that have
    not yet started. Experimental jobs are allowed to fail without making the
    workflow fail.
    """

    def __init__(
        self,
        test_suite: TestSuite,
        fail_fast: bool = True,
        max_retries: int = 1,
    ):
        self.test_suite = test_suite
        self.fail_fast = fail_fast
        self.max_retries = max_retries

    def run(
        self,
        jobs: Iterable[MatrixJob],
        continue_on_error: Callable[[MatrixJob], bool] | None = None,
    ) -> list[JobResult]:
        results: list[JobResult] = []
        workflow_failure_seen = False

        for job in jobs:
            if self.fail_fast and workflow_failure_seen and not job.experimental:
                results.append(
                    JobResult(
                        job=job,
                        passed=False,
                        skipped=True,
                        message="cancelled because fail-fast stopped the matrix",
                    )
                )
                continue

            attempts = 0
            passed = False
            message = ""

            while attempts <= self.max_retries and not passed:
                attempts += 1
                start = time.perf_counter()
                passed, message = self.test_suite.run(job)
                duration = time.perf_counter() - start

            result = JobResult(
                job=job,
                passed=passed,
                attempts=attempts,
                duration_seconds=duration,
                message=message,
            )
            results.append(result)

            tolerated = (
                continue_on_error(job) if continue_on_error is not None else False
            )

            if not passed and not tolerated:
                workflow_failure_seen = True

        return results


def print_matrix(jobs: list[MatrixJob]) -> None:
    print("\nExpanded matrix")
    print("-" * 90)

    for index, job in enumerate(jobs, start=1):
        experimental = " experimental" if job.experimental else ""
        print(
            f"{index:02d}  {job.identifier:<18} "
            f"Python {job.python:<4} "
            f"{job.os:<8} "
            f"{job.dependency_mode:<8}"
            f"{experimental}"
        )


def print_results(results: list[JobResult]) -> None:
    print("\nMatrix execution")
    print("-" * 110)

    for result in results:
        print(
            f"{result.job.identifier:<18} "
            f"{result.status:<8} "
            f"attempts={result.attempts:<2} "
            f"{result.job.key:<42} "
            f"{result.message}"
        )


def workflow_conclusion(results: list[JobResult]) -> str:
    blocking_failures = [
        result
        for result in results
        if not result.passed
        and not result.skipped
        and not result.job.experimental
    ]

    if blocking_failures:
        return "failure"

    if all(result.skipped or result.passed for result in results):
        return "success"

    return "cancelled"


def analyze_coverage(jobs: list[MatrixJob]) -> dict[str, Any]:
    versions = sorted({job.python for job in jobs})
    systems = sorted({job.os for job in jobs})
    dependency_modes = sorted({job.dependency_mode for job in jobs})

    return {
        "job_count": len(jobs),
        "python_versions": versions,
        "operating_systems": systems,
        "dependency_modes": dependency_modes,
        "experimental_jobs": sum(job.experimental for job in jobs),
        "full_cartesian_size": (
            len(versions) * len(systems) * len(dependency_modes)
        ),
    }


def demonstrate_validation() -> None:
    print("\nValidation example")

    try:
        MatrixEngine(
            MatrixDefinition(
                python_versions=["3.13", "3.14"],
                operating_systems=["ubuntu"],
                dependency_modes=["locked"],
            )
        )
    except MatrixValidationError as exc:
        print(f"Rejected invalid matrix: {exc}")


def demonstrate_artifacts(jobs: list[MatrixJob]) -> None:
    print("\nArtifact isolation")
    print("-" * 70)

    for job in jobs[:5]:
        print(f"{job.key:<50} -> {job.artifact_name()}")


def demonstrate_json_export(results: list[JobResult]) -> None:
    payload = [
        {
            "matrix": {
                "python": result.job.python,
                "os": result.job.os,
                "dependency_mode": result.job.dependency_mode,
            },
            "status": result.status,
            "attempts": result.attempts,
            "experimental": result.job.experimental,
            "message": result.message,
        }
        for result in results
    ]

    print("\nMachine-readable result sample")
    print(json.dumps(payload[:3], indent=2))


def main() -> None:
    definition = MatrixDefinition(
        python_versions=["3.10", "3.11", "3.12", "3.13"],
        operating_systems=["ubuntu", "windows", "macos"],
        dependency_modes=["minimum", "locked", "latest"],
        exclude=[
            {
                "python": "3.10",
                "os": "macos",
                "dependency_mode": "minimum",
            },
            {
                "python": "3.13",
                "os": "windows",
                "dependency_mode": "minimum",
            },
        ],
        include=[
            {
                "python": "3.13",
                "os": "ubuntu",
                "dependency_mode": "latest",
                "experimental": True,
            }
        ],
    )

    engine = MatrixEngine(definition)
    jobs = engine.expand()

    print("ACTIONS MATRIX BUILD SIMULATION")
    print("=" * 90)
    print_matrix(jobs)

    coverage = analyze_coverage(jobs)
    print("\nCoverage")
    print("-" * 70)
    for key, value in coverage.items():
        print(f"{key}: {value}")

    runner = MatrixRunner(
        test_suite=TestSuite(),
        fail_fast=False,
        max_retries=1,
    )

    results = runner.run(
        jobs,
        continue_on_error=lambda job: job.experimental,
    )

    print_results(results)

    print("\nWorkflow conclusion")
    print("-" * 70)
    print(workflow_conclusion(results))

    demonstrate_artifacts(jobs)
    demonstrate_json_export(results)
    demonstrate_validation()

    passed = sum(result.passed for result in results)
    failed = sum(
        not result.passed and not result.skipped for result in results
    )
    skipped = sum(result.skipped for result in results)

    print("\nExecution statistics")
    print("-" * 70)
    print(f"Concrete jobs: {len(results)}")
    print(f"Passed:        {passed}")
    print(f"Failed:        {failed}")
    print(f"Skipped:       {skipped}")

    print(
        "\nMatrix design principle: expand combinations deliberately, "
        "exclude combinations that have no meaningful coverage value, "
        "and use experimental entries only when their failure semantics "
        "are explicitly different from release-blocking jobs."
    )


if __name__ == "__main__":
    random.seed(42)
    main()
