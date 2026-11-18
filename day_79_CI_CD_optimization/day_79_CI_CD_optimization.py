#!/usr/bin/env python3
"""
CI/CD Optimization Engine
Demonstrates parallel execution, content-addressed caching,
dependency-aware scheduling, artifact reuse, and failure handling.

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("cicd")


class StageState(Enum):
    PENDING = "pending"
    RUNNING = "running"
    CACHED = "cached"
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class Artifact:
    name: str
    content: str
    digest: str

    @classmethod
    def create(cls, name: str, content: str) -> Artifact:
        digest = hashlib.sha256(content.encode()).hexdigest()
        return cls(name, content, digest)


@dataclass
class Stage:
    name: str
    command: str
    dependencies: list[str] = field(default_factory=list)
    inputs: dict[str, str] = field(default_factory=dict)
    action: Callable[[], str] | None = None


@dataclass
class StageResult:
    name: str
    state: StageState
    artifact: Artifact | None = None
    duration: float = 0.0
    error: str | None = None


class PipelineError(Exception):
    pass


class ArtifactCache:
    """Thread-safe content-addressed artifact storage."""

    def __init__(self):
        self._artifacts: dict[str, Artifact] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> Artifact | None:
        with self._lock:
            return self._artifacts.get(key)

    def put(self, key: str, artifact: Artifact) -> None:
        with self._lock:
            self._artifacts[key] = artifact

    def statistics(self) -> dict:
        with self._lock:
            return {
                "entries": len(self._artifacts),
                "digests": sorted(
                    artifact.digest
                    for artifact in self._artifacts.values()
                ),
            }


class Pipeline:
    def __init__(
        self,
        stages: list[Stage],
        max_workers: int = 4,
        cache: ArtifactCache | None = None,
    ):
        if max_workers < 1:
            raise ValueError("max_workers must be positive")

        self.stages = {stage.name: stage for stage in stages}
        self.max_workers = max_workers
        self.cache = cache or ArtifactCache()
        self.results: dict[str, StageResult] = {}

        if len(self.stages) != len(stages):
            raise PipelineError("Duplicate stage names")

        self._validate_graph()

    def _validate_graph(self) -> None:
        for stage in self.stages.values():
            if not stage.name.strip():
                raise PipelineError("Stage name cannot be empty")

            if not stage.command.strip():
                raise PipelineError(
                    f"Command cannot be empty: {stage.name}"
                )

            for dependency in stage.dependencies:
                if dependency not in self.stages:
                    raise PipelineError(
                        f"Unknown dependency: {dependency}"
                    )

                if dependency == stage.name:
                    raise PipelineError("Self-dependency detected")

        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                raise PipelineError("Circular dependency detected")

            if name in visited:
                return

            visiting.add(name)

            for dependency in self.stages[name].dependencies:
                visit(dependency)

            visiting.remove(name)
            visited.add(name)

        for name in self.stages:
            visit(name)

    def _cache_key(self, stage: Stage) -> str:
        dependency_digests = {}

        for dependency in sorted(stage.dependencies):
            result = self.results[dependency]

            if result.artifact is None:
                raise PipelineError(
                    f"Missing dependency artifact: {dependency}"
                )

            dependency_digests[dependency] = result.artifact.digest

        # Include all inputs that can affect the output.
        payload = {
            "stage": stage.name,
            "command": stage.command,
            "inputs": stage.inputs,
            "dependencies": dependency_digests,
            "cache_schema": 1,
        }

        encoded = json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()

        return hashlib.sha256(encoded).hexdigest()

    def _execute(self, stage: Stage) -> StageResult:
        start = time.perf_counter()
        key = self._cache_key(stage)

        cached = self.cache.get(key)

        if cached is not None:
            return StageResult(
                stage.name,
                StageState.CACHED,
                cached,
                time.perf_counter() - start,
            )

        try:
            if stage.action is None:
                raise PipelineError(
                    f"No executable action for {stage.name}"
                )

            content = stage.action()

            if not isinstance(content, str):
                raise PipelineError("Stage output must be text")

            artifact = Artifact.create(stage.name, content)
            self.cache.put(key, artifact)

            return StageResult(
                stage.name,
                StageState.SUCCESS,
                artifact,
                time.perf_counter() - start,
            )

        except Exception as exc:
            logger.exception("Stage failed: %s", stage.name)

            return StageResult(
                stage.name,
                StageState.FAILED,
                duration=time.perf_counter() - start,
                error=str(exc),
            )

    def run(self) -> dict[str, StageResult]:
        self.results = {
            name: StageResult(name, StageState.PENDING)
            for name in self.stages
        }

        running = {}

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=self.max_workers
        ) as executor:

            while True:
                progress = False

                # Submit every stage whose dependencies have completed.
                for name, stage in self.stages.items():
                    result = self.results[name]

                    if result.state != StageState.PENDING:
                        continue

                    dependencies = [
                        self.results[dep]
                        for dep in stage.dependencies
                    ]

                    if any(
                        dep.state in (
                            StageState.FAILED,
                            StageState.BLOCKED,
                        )
                        for dep in dependencies
                    ):
                        result.state = StageState.BLOCKED
                        result.error = "Dependency failed"
                        progress = True
                        continue

                    if not all(
                        dep.state in (
                            StageState.SUCCESS,
                            StageState.CACHED,
                        )
                        for dep in dependencies
                    ):
                        continue

                    if len(running) >= self.max_workers:
                        continue

                    future = executor.submit(self._execute, stage)
                    running[future] = name
                    result.state = StageState.RUNNING
                    progress = True

                if running:
                    completed, _ = concurrent.futures.wait(
                        running,
                        return_when=concurrent.futures.FIRST_COMPLETED,
                    )

                    for future in completed:
                        name = running.pop(future)

                        try:
                            self.results[name] = future.result()
                        except Exception as exc:
                            self.results[name] = StageResult(
                                name,
                                StageState.FAILED,
                                error=str(exc),
                            )

                        progress = True

                unfinished = any(
                    result.state in (
                        StageState.PENDING,
                        StageState.RUNNING,
                    )
                    for result in self.results.values()
                )

                if not unfinished:
                    break

                if not progress:
                    raise PipelineError(
                        "Pipeline scheduler made no progress"
                    )

        return self.results

    def report(self) -> None:
        print("\nCI/CD EXECUTION REPORT")
        print("-" * 75)

        for name, result in self.results.items():
            print(
                f"{name:15} "
                f"{result.state.value:10} "
                f"{result.duration:.4f}s"
            )

            if result.error:
                print(f"  Error: {result.error}")

            if result.artifact:
                print(f"  SHA256: {result.artifact.digest[:16]}")

        successful = sum(
            r.state in (StageState.SUCCESS, StageState.CACHED)
            for r in self.results.values()
        )

        print("-" * 75)
        print(f"Completed: {successful}/{len(self.results)}")
        print(f"Cache: {self.cache.statistics()['entries']} entries")

    @property
    def successful(self) -> bool:
        return all(
            result.state in (
                StageState.SUCCESS,
                StageState.CACHED,
            )
            for result in self.results.values()
        )


def make_stages(source_version: str) -> list[Stage]:
    """Build a realistic dependency graph."""

    def action(name: str, output: str):
        def execute() -> str:
            logger.info("Executing %s", name)
            time.sleep(0.15)
            return output
        return execute

    return [
        Stage(
            "checkout",
            "git checkout",
            inputs={"source": source_version},
            action=action("checkout", f"source:{source_version}"),
        ),
        Stage(
            "compile",
            "compiler build",
            ["checkout"],
            {"compiler": "gcc-14", "mode": "release"},
            action("compile", "compiled-binary-v1"),
        ),
        Stage(
            "lint",
            "static analysis",
            ["checkout"],
            {"rules": "strict-v2"},
            action("lint", "lint-passed"),
        ),
        Stage(
            "unit_tests",
            "pytest unit",
            ["compile"],
            {"suite": "unit-v3"},
            action("unit_tests", "unit-tests-passed"),
        ),
        Stage(
            "integration_tests",
            "pytest integration",
            ["compile"],
            {"suite": "integration-v2"},
            action("integration_tests", "integration-tests-passed"),
        ),
        Stage(
            "security_scan",
            "dependency and source scan",
            ["checkout"],
            {"scanner": "security-v1"},
            action("security_scan", "security-passed"),
        ),
        Stage(
            "package",
            "build immutable package",
            [
                "unit_tests",
                "integration_tests",
                "lint",
                "security_scan",
            ],
            {"format": "tar.gz", "package_version": "1"},
            action("package", "application-package-v1"),
        ),
        Stage(
            "deploy_staging",
            "deploy verified artifact",
            ["package"],
            {"environment": "staging"},
            action("deploy_staging", "staging-deployment-success"),
        ),
    ]


def demonstrate_failure() -> None:
    """Verify that downstream stages are blocked after failure."""

    stages = [
        Stage(
            "build",
            "build application",
            action=lambda: "binary",
        ),
        Stage(
            "test",
            "execute tests",
            ["build"],
            action=lambda: (_ for _ in ()).throw(
                RuntimeError("Test assertion failed")
            ),
        ),
        Stage(
            "deploy",
            "deploy application",
            ["test"],
            action=lambda: "deployed",
        ),
    ]

    pipeline = Pipeline(stages, max_workers=2)
    results = pipeline.run()

    assert results["test"].state == StageState.FAILED
    assert results["deploy"].state == StageState.BLOCKED


def main() -> None:
    shared_cache = ArtifactCache()

    print("FIRST PIPELINE EXECUTION")
    first = Pipeline(
        make_stages("commit-a100"),
        max_workers=4,
        cache=shared_cache,
    )
    first.run()
    first.report()

    assert first.successful

    print("\nSECOND PIPELINE EXECUTION")
    second = Pipeline(
        make_stages("commit-a100"),
        max_workers=4,
        cache=shared_cache,
    )
    second.run()
    second.report()

    assert second.successful
    assert all(
        result.state == StageState.CACHED
        for result in second.results.values()
    )

    print("\nCHANGED SOURCE EXECUTION")
    changed = Pipeline(
        make_stages("commit-b200"),
        max_workers=4,
        cache=shared_cache,
    )
    changed.run()
    changed.report()

    assert changed.successful

    print("\nFAILURE PROPAGATION TEST")
    demonstrate_failure()

    print("\nAll CI/CD validation assertions passed.")


if __name__ == "__main__":
    main()
