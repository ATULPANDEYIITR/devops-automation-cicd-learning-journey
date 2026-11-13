#!/usr/bin/env python3
"""
Canary Deployment Simulator
Demonstrates progressive traffic splitting, automated health evaluation,
promotion, rollback, deployment history, and release governance.
Python 3.10+
"""

from __future__ import annotations

import json
import random
import statistics
import sys
import time

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class DeploymentState(str, Enum):
    CREATED = "created"
    CANARY = "canary"
    PROMOTED = "promoted"
    ROLLED_BACK = "rolled_back"
    FAILED = "failed"


class CheckStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ReleasePolicy:
    stages: tuple[int, ...] = (5, 10, 25, 50, 100)
    max_error_rate: float = 0.02
    max_latency_ms: float = 500.0
    min_success_rate: float = 0.98
    min_requests: int = 100
    max_error_rate_increase: float = 0.015
    required_consecutive_passes: int = 1

    def __post_init__(self):
        if not self.stages or self.stages[-1] != 100:
            raise ValueError("Traffic stages must end at 100%.")
        if any(not isinstance(x, int) or x < 1 or x > 100
               for x in self.stages):
            raise ValueError("Traffic percentages must be integers in [1, 100].")
        if tuple(sorted(set(self.stages))) != self.stages:
            raise ValueError("Traffic stages must be strictly increasing.")
        if not 0 < self.max_error_rate < 1:
            raise ValueError("Invalid maximum error rate.")
        if not 0 < self.min_success_rate <= 1:
            raise ValueError("Invalid minimum success rate.")
        if self.min_requests < 1:
            raise ValueError("Minimum request count must be positive.")
        if self.max_latency_ms <= 0:
            raise ValueError("Latency threshold must be positive.")
        if self.required_consecutive_passes < 1:
            raise ValueError("Consecutive passes must be positive.")


@dataclass
class Metrics:
    requests: int
    errors: int
    p95_latency_ms: float
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def error_rate(self) -> float:
        return self.errors / self.requests if self.requests else 1.0

    @property
    def success_rate(self) -> float:
        return 1.0 - self.error_rate

    def validate(self):
        if self.requests < 0 or self.errors < 0:
            raise ValueError("Request and error counts cannot be negative.")
        if self.errors > self.requests:
            raise ValueError("Errors cannot exceed requests.")
        if self.p95_latency_ms < 0:
            raise ValueError("Latency cannot be negative.")


@dataclass
class Deployment:
    release_id: str
    version: str
    state: DeploymentState = DeploymentState.CREATED
    traffic_percent: int = 0
    stage_index: int = -1
    consecutive_passes: int = 0
    history: list[dict] = field(default_factory=list)

    def record(self, event: str, details: dict):
        self.history.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "details": details
        })


class CanaryDeploymentError(Exception):
    pass


class CanaryController:
    def __init__(self, policy: ReleasePolicy):
        self.policy = policy
        self.deployments: dict[str, Deployment] = {}
        self.active_version = "v1.0.0"
        self.baseline: Optional[Metrics] = None

    def register(self, release_id: str, version: str) -> Deployment:
        if not release_id or release_id in self.deployments:
            raise CanaryDeploymentError("Release ID is empty or duplicated.")
        if not version.strip():
            raise CanaryDeploymentError("Version cannot be empty.")

        deployment = Deployment(release_id, version)
        deployment.record("registered", {"version": version})
        self.deployments[release_id] = deployment
        return deployment

    def start(self, release_id: str, baseline: Metrics):
        deployment = self._get(release_id)
        baseline.validate()

        if deployment.state != DeploymentState.CREATED:
            raise CanaryDeploymentError("Release has already started.")

        if baseline.requests < self.policy.min_requests:
            raise CanaryDeploymentError("Insufficient baseline observations.")

        self.baseline = baseline
        deployment.state = DeploymentState.CANARY
        deployment.stage_index = 0
        deployment.traffic_percent = self.policy.stages[0]
        deployment.record("canary_started", {
            "traffic_percent": deployment.traffic_percent,
            "baseline_error_rate": baseline.error_rate
        })

    def evaluate(self, release_id: str, metrics: Metrics) -> bool:
        deployment = self._get(release_id)

        if deployment.state != DeploymentState.CANARY:
            raise CanaryDeploymentError("Deployment is not in canary state.")

        metrics.validate()

        failures = []

        if metrics.requests < self.policy.min_requests:
            failures.append("insufficient_requests")

        if metrics.error_rate > self.policy.max_error_rate:
            failures.append("error_rate_threshold")

        if metrics.p95_latency_ms > self.policy.max_latency_ms:
            failures.append("latency_threshold")

        if metrics.success_rate < self.policy.min_success_rate:
            failures.append("success_rate_threshold")

        if self.baseline is not None:
            increase = metrics.error_rate - self.baseline.error_rate
            if increase > self.policy.max_error_rate_increase:
                failures.append("baseline_regression")

        deployment.record("health_evaluation", {
            "metrics": asdict(metrics),
            "failures": failures
        })

        if failures:
            self.rollback(release_id, ",".join(failures))
            return False

        deployment.consecutive_passes += 1

        if deployment.consecutive_passes < self.policy.required_consecutive_passes:
            return True

        deployment.stage_index += 1

        if deployment.stage_index >= len(self.policy.stages):
            deployment.state = DeploymentState.PROMOTED
            deployment.traffic_percent = 100
            self.active_version = deployment.version
            deployment.record("promoted", {
                "active_version": self.active_version
            })
            return True

        deployment.traffic_percent = self.policy.stages[
            deployment.stage_index
        ]

        deployment.record("traffic_increased", {
            "traffic_percent": deployment.traffic_percent
        })

        return True

    def rollback(self, release_id: str, reason: str):
        deployment = self._get(release_id)

        if deployment.state != DeploymentState.CANARY:
            raise CanaryDeploymentError("Only active canaries can roll back.")

        deployment.state = DeploymentState.ROLLED_BACK
        deployment.traffic_percent = 0
        deployment.consecutive_passes = 0

        deployment.record("rollback", {
            "reason": reason,
            "restored_version": self.active_version
        })

    def close(self, release_id: str):
        deployment = self._get(release_id)

        if deployment.state == DeploymentState.CANARY:
            self.rollback(release_id, "manual_closure")
        elif deployment.state not in (
            DeploymentState.PROMOTED,
            DeploymentState.ROLLED_BACK,
            DeploymentState.FAILED
        ):
            deployment.state = DeploymentState.FAILED
            deployment.record("closed_before_start", {})

    def _get(self, release_id: str) -> Deployment:
        if release_id not in self.deployments:
            raise CanaryDeploymentError("Unknown release.")
        return self.deployments[release_id]

    def report(self) -> dict:
        return {
            "active_version": self.active_version,
            "deployments": [
                {
                    "release_id": d.release_id,
                    "version": d.version,
                    "state": d.state.value,
                    "traffic_percent": d.traffic_percent,
                    "history": d.history
                }
                for d in self.deployments.values()
            ]
        }


class TrafficRouter:
    """Deterministic percentage-based traffic assignment."""

    def __init__(self, controller: CanaryController):
        self.controller = controller

    def route(self, request_id: str, release_id: str) -> str:
        deployment = self.controller._get(release_id)

        if deployment.state != DeploymentState.CANARY:
            return self.controller.active_version

        # Stable hashing keeps a client consistently assigned.
        bucket = hash(request_id) % 100

        if bucket < deployment.traffic_percent:
            return deployment.version

        return self.controller.active_version


def simulate_metrics(
    requests: int,
    error_rate: float,
    latency_ms: float,
    seed: int
) -> Metrics:
    if requests < 0 or not 0 <= error_rate <= 1:
        raise ValueError("Invalid simulation parameters.")

    rng = random.Random(seed)
    errors = sum(rng.random() < error_rate for _ in range(requests))

    return Metrics(
        requests=requests,
        errors=errors,
        p95_latency_ms=latency_ms
    )


def run_tests():
    policy = ReleasePolicy(min_requests=100)
    controller = CanaryController(policy)

    baseline = Metrics(1000, 10, 180)
    baseline.validate()

    deployment = controller.register("release-001", "v2.0.0")
    controller.start("release-001", baseline)

    assert deployment.traffic_percent == 5

    for index, stage in enumerate(policy.stages):
        result = controller.evaluate(
            "release-001",
            Metrics(1000, 12, 200)
        )
        assert result

        if stage == 100:
            assert deployment.state == DeploymentState.PROMOTED

    assert controller.active_version == "v2.0.0"

    failed = controller.register("release-002", "v3.0.0")
    controller.start("release-002", baseline)

    result = controller.evaluate(
        "release-002",
        Metrics(1000, 150, 900)
    )

    assert not result
    assert failed.state == DeploymentState.ROLLED_BACK
    assert failed.traffic_percent == 0
    assert controller.active_version == "v2.0.0"

    try:
        controller.evaluate("release-002", Metrics(1000, 0, 100))
        raise AssertionError("Expected invalid transition.")
    except CanaryDeploymentError:
        pass

    try:
        Metrics(10, 11, 100).validate()
        raise AssertionError("Expected metric validation error.")
    except ValueError:
        pass

    print("All canary deployment tests passed.")


def main():
    run_tests()

    policy = ReleasePolicy(
        stages=(5, 10, 25, 50, 100),
        max_error_rate=0.02,
        max_latency_ms=500,
        min_requests=100
    )

    controller = CanaryController(policy)
    router = TrafficRouter(controller)

    baseline = Metrics(5000, 50, 190)
    deployment = controller.register("production-2026-11", "v2.1.0")
    controller.start(deployment.release_id, baseline)

    print("\nCanary deployment execution")

    observations = [
        Metrics(1000, 12, 210),
        Metrics(1000, 13, 220),
        Metrics(1000, 15, 225),
        Metrics(1000, 11, 230),
        Metrics(1000, 14, 240)
    ]

    for metrics in observations:
        if deployment.state != DeploymentState.CANARY:
            break

        controller.evaluate(deployment.release_id, metrics)

        print(
            f"Version={deployment.version}, "
            f"traffic={deployment.traffic_percent}%, "
            f"state={deployment.state.value}"
        )

    print("\nTraffic routing examples")

    for request_id in ("client-001", "client-002", "client-003"):
        print(request_id, "->", router.route(
            request_id, deployment.release_id
        ))

    output = Path("canary_deployment_report.json")
    output.write_text(
        json.dumps(controller.report(), indent=2),
        encoding="utf-8"
    )

    print(f"\nReport saved to {output.resolve()}")


if __name__ == "__main__":
    try:
        main()
    except (CanaryDeploymentError, ValueError, OSError) as exc:
        print(f"Deployment simulation failed: {exc}", file=sys.stderr)
        sys.exit(1)
