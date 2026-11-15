#!/usr/bin/env python3
"""
Automated Rollback Strategies and Release Recovery

Simulates production release deployment, health monitoring, automated
rollback, canary analysis, deployment history, and recovery validation.

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import json
import logging
import random
import time
import uuid

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger("release-recovery")


class ReleaseState(str, Enum):
    CREATED = "created"
    DEPLOYING = "deploying"
    ACTIVE = "active"
    FAILED = "failed"
    ROLLING_BACK = "rolling_back"
    ROLLED_BACK = "rolled_back"
    RECOVERED = "recovered"


class RollbackStrategy(str, Enum):
    IMMEDIATE = "immediate"
    BLUE_GREEN = "blue_green"
    CANARY = "canary"
    PROGRESSIVE = "progressive"


@dataclass(frozen=True)
class Release:
    release_id: str
    version: str
    artifact_digest: str
    created_at: str

    @staticmethod
    def create(version: str, digest: str) -> "Release":
        if not version.strip():
            raise ValueError("Version cannot be empty")
        if not digest.startswith("sha256:"):
            raise ValueError("Artifact digest must use SHA-256 notation")

        return Release(
            release_id=str(uuid.uuid4()),
            version=version,
            artifact_digest=digest,
            created_at=datetime.now(timezone.utc).isoformat(),
        )


@dataclass
class HealthMetrics:
    error_rate: float
    latency_ms: float
    availability: float
    failed_checks: int = 0

    def validate(self) -> None:
        if not 0 <= self.error_rate <= 1:
            raise ValueError("Error rate must be between 0 and 1")
        if self.latency_ms < 0:
            raise ValueError("Latency cannot be negative")
        if not 0 <= self.availability <= 1:
            raise ValueError("Availability must be between 0 and 1")
        if self.failed_checks < 0:
            raise ValueError("Failed checks cannot be negative")


@dataclass(frozen=True)
class RollbackPolicy:
    max_error_rate: float = 0.05
    max_latency_ms: float = 500
    min_availability: float = 0.99
    max_failed_checks: int = 2
    evaluation_windows: int = 2

    def __post_init__(self):
        if not 0 <= self.max_error_rate <= 1:
            raise ValueError("Invalid error threshold")
        if self.max_latency_ms <= 0:
            raise ValueError("Latency threshold must be positive")
        if not 0 < self.min_availability <= 1:
            raise ValueError("Invalid availability threshold")
        if self.max_failed_checks < 0 or self.evaluation_windows < 1:
            raise ValueError("Invalid check configuration")


@dataclass
class Deployment:
    release: Release
    state: ReleaseState = ReleaseState.CREATED
    traffic_percentage: int = 0
    metrics_history: list[HealthMetrics] = field(default_factory=list)
    rollback_reason: Optional[str] = None


class DeploymentError(Exception):
    pass


class RecoveryError(Exception):
    pass


class ReleaseManager:
    def __init__(
        self,
        policy: RollbackPolicy,
        history_file: str = "release_history.json",
    ):
        self.policy = policy
        self.history_file = Path(history_file)
        self.deployments: dict[str, Deployment] = {}
        self.active_release: Optional[str] = None
        self.previous_release: Optional[str] = None
        self.audit_log: list[dict] = []

    def record_event(self, event: str, details: dict) -> None:
        self.audit_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "details": details,
        })

    def register(self, release: Release) -> Deployment:
        if release.release_id in self.deployments:
            raise DeploymentError("Release already registered")

        deployment = Deployment(release=release)
        self.deployments[release.release_id] = deployment

        self.record_event("release_registered", {
            "release_id": release.release_id,
            "version": release.version,
        })
        return deployment

    def evaluate_health(self, metrics: HealthMetrics) -> tuple[bool, list[str]]:
        metrics.validate()
        failures = []

        if metrics.error_rate > self.policy.max_error_rate:
            failures.append("error_rate_exceeded")

        if metrics.latency_ms > self.policy.max_latency_ms:
            failures.append("latency_exceeded")

        if metrics.availability < self.policy.min_availability:
            failures.append("availability_below_threshold")

        if metrics.failed_checks > self.policy.max_failed_checks:
            failures.append("failed_checks_exceeded")

        return not failures, failures

    def deploy(
        self,
        release_id: str,
        strategy: RollbackStrategy,
        health_windows: list[HealthMetrics],
    ) -> Deployment:
        deployment = self.deployments[release_id]

        if deployment.state not in (
            ReleaseState.CREATED,
            ReleaseState.ROLLED_BACK,
        ):
            raise DeploymentError("Release cannot be deployed from current state")

        if not health_windows:
            raise DeploymentError("At least one health window is required")

        deployment.state = ReleaseState.DEPLOYING
        self.record_event("deployment_started", {
            "release_id": release_id,
            "strategy": strategy.value,
        })

        # A release is not considered active until validation succeeds.
        try:
            if strategy == RollbackStrategy.IMMEDIATE:
                self._set_traffic(deployment, 100)
                self._validate_windows(deployment, health_windows)

            elif strategy == RollbackStrategy.BLUE_GREEN:
                # New environment receives traffic only after pre-switch checks.
                self._validate_windows(deployment, health_windows)
                self._set_traffic(deployment, 100)

            elif strategy == RollbackStrategy.CANARY:
                self._progressive_deploy(
                    deployment, health_windows, [5, 25, 50, 100]
                )

            elif strategy == RollbackStrategy.PROGRESSIVE:
                self._progressive_deploy(
                    deployment, health_windows, [10, 30, 60, 100]
                )

            else:
                raise DeploymentError("Unsupported deployment strategy")

            old_release = self.active_release

            if old_release and old_release != release_id:
                self.previous_release = old_release

            self.active_release = release_id
            deployment.state = ReleaseState.ACTIVE

            self.record_event("deployment_activated", {
                "release_id": release_id,
                "version": deployment.release.version,
            })

            return deployment

        except (DeploymentError, ValueError) as exc:
            deployment.state = ReleaseState.FAILED
            deployment.rollback_reason = str(exc)

            self.record_event("deployment_failed", {
                "release_id": release_id,
                "reason": str(exc),
            })

            if self.previous_release:
                self.rollback(release_id, self.previous_release)

            raise

    def _set_traffic(self, deployment: Deployment, percentage: int) -> None:
        if not 0 <= percentage <= 100:
            raise DeploymentError("Traffic percentage out of range")

        deployment.traffic_percentage = percentage

        self.record_event("traffic_changed", {
            "release_id": deployment.release.release_id,
            "percentage": percentage,
        })

    def _validate_windows(
        self,
        deployment: Deployment,
        windows: list[HealthMetrics],
    ) -> None:
        if len(windows) < self.policy.evaluation_windows:
            raise DeploymentError("Insufficient health evaluation windows")

        for metrics in windows:
            metrics.validate()
            deployment.metrics_history.append(metrics)

            healthy, failures = self.evaluate_health(metrics)

            if not healthy:
                raise DeploymentError(
                    "Health validation failed: " + ", ".join(failures)
                )

    def _progressive_deploy(
        self,
        deployment: Deployment,
        windows: list[HealthMetrics],
        stages: list[int],
    ) -> None:
        if len(windows) < len(stages):
            raise DeploymentError("Insufficient metrics for traffic stages")

        for percentage, metrics in zip(stages, windows):
            self._set_traffic(deployment, percentage)
            deployment.metrics_history.append(metrics)

            healthy, failures = self.evaluate_health(metrics)

            if not healthy:
                raise DeploymentError(
                    f"Failure at {percentage}% traffic: {failures}"
                )

    def rollback(self, failed_id: str, target_id: str) -> None:
        failed = self.deployments[failed_id]
        target = self.deployments.get(target_id)

        if target is None:
            raise RecoveryError("Rollback target does not exist")

        if target.state not in (
            ReleaseState.ACTIVE,
            ReleaseState.RECOVERED,
            ReleaseState.ROLLED_BACK,
        ):
            raise RecoveryError("Rollback target is not available")

        failed.state = ReleaseState.ROLLING_BACK

        self.record_event("rollback_started", {
            "failed_release": failed_id,
            "target_release": target_id,
        })

        # Switch traffic only to a previously validated release.
        failed.traffic_percentage = 0
        target.traffic_percentage = 100

        self.active_release = target_id
        failed.state = ReleaseState.ROLLED_BACK

        self.record_event("rollback_completed", {
            "failed_release": failed_id,
            "restored_release": target_id,
        })

    def recover_forward(
        self,
        failed_id: str,
        replacement: Release,
        metrics: list[HealthMetrics],
    ) -> Deployment:
        """Deploy a corrected release instead of restoring old code."""
        failed = self.deployments[failed_id]

        if failed.state not in (
            ReleaseState.FAILED,
            ReleaseState.ROLLED_BACK,
        ):
            raise RecoveryError("Release is not eligible for forward recovery")

        new_deployment = self.register(replacement)

        try:
            self.deploy(
                replacement.release_id,
                RollbackStrategy.CANARY,
                metrics,
            )
            new_deployment.state = ReleaseState.RECOVERED

            self.record_event("forward_recovery_completed", {
                "failed_release": failed_id,
                "replacement_release": replacement.release_id,
            })

            return new_deployment

        except (DeploymentError, RecoveryError):
            raise

    def save_history(self) -> None:
        """Write an audit snapshot using atomic replacement."""
        payload = {
            "active_release": self.active_release,
            "previous_release": self.previous_release,
            "deployments": [
                {
                    "release": asdict(d.release),
                    "state": d.state.value,
                    "traffic_percentage": d.traffic_percentage,
                    "rollback_reason": d.rollback_reason,
                    "metrics_history": [
                        asdict(m) for m in d.metrics_history
                    ],
                }
                for d in self.deployments.values()
            ],
            "audit_log": self.audit_log,
        }

        temporary = self.history_file.with_suffix(".tmp")

        try:
            temporary.write_text(
                json.dumps(payload, indent=2),
                encoding="utf-8",
            )
            temporary.replace(self.history_file)
        except OSError as exc:
            raise RecoveryError(f"Unable to persist history: {exc}") from exc


def run_demo() -> None:
    policy = RollbackPolicy(
        max_error_rate=0.05,
        max_latency_ms=500,
        min_availability=0.99,
        evaluation_windows=2,
    )

    manager = ReleaseManager(policy)

    release_v1 = Release.create("1.0.0", "sha256:" + "a" * 64)
    manager.register(release_v1)

    manager.deploy(
        release_v1.release_id,
        RollbackStrategy.IMMEDIATE,
        [
            HealthMetrics(0.01, 120, 0.999),
            HealthMetrics(0.02, 150, 0.998),
        ],
    )

    release_v2 = Release.create("2.0.0", "sha256:" + "b" * 64)
    manager.register(release_v2)

    try:
        manager.deploy(
            release_v2.release_id,
            RollbackStrategy.CANARY,
            [
                HealthMetrics(0.01, 140, 0.999),
                HealthMetrics(0.02, 160, 0.998),
                HealthMetrics(0.18, 950, 0.92),
                HealthMetrics(0.01, 150, 0.999),
            ],
        )
    except DeploymentError as exc:
        logger.warning("Automatic recovery triggered: %s", exc)

    assert manager.active_release == release_v1.release_id
    assert manager.deployments[release_v2.release_id].state == ReleaseState.ROLLED_BACK

    release_v3 = Release.create("2.0.1", "sha256:" + "c" * 64)

    recovered = manager.recover_forward(
        release_v2.release_id,
        release_v3,
        [
            HealthMetrics(0.01, 130, 0.999),
            HealthMetrics(0.015, 140, 0.998),
            HealthMetrics(0.02, 160, 0.997),
            HealthMetrics(0.01, 125, 0.999),
        ],
    )

    assert recovered.state == ReleaseState.RECOVERED
    assert manager.active_release == release_v3.release_id

    manager.save_history()

    print("\nRELEASE RECOVERY REPORT")
    print("-" * 65)

    for deployment in manager.deployments.values():
        print(
            f"{deployment.release.version:10} "
            f"{deployment.state.value:15} "
            f"traffic={deployment.traffic_percentage}%"
        )

    print(f"\nActive release: {manager.active_release}")
    print(f"Audit events: {len(manager.audit_log)}")
    print(f"History file: {manager.history_file.resolve()}")


if __name__ == "__main__":
    run_demo()
