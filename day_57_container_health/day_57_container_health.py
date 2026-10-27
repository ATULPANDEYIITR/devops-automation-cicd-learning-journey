#!/usr/bin/env python3
"""
Container health automation simulator.

Models:
- HEALTHCHECK state transitions
- Restart policies
- CPU and memory limits
- Health-aware automation
- Restart backoff
- Resource validation
- Failure handling
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, List, Optional


class HealthStatus(str, Enum):
    STARTING = "starting"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


class RestartPolicy(str, Enum):
    NO = "no"
    ON_FAILURE = "on-failure"
    ALWAYS = "always"
    UNLESS_STOPPED = "unless-stopped"


class ContainerState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    RESTARTING = "restarting"


class HealthCheckError(Exception):
    """Raised when a health-check configuration is invalid."""


@dataclass(frozen=True)
class ResourceLimits:
    cpu_millicores: int
    memory_mb: int

    def validate(self) -> None:
        if self.cpu_millicores <= 0:
            raise ValueError("CPU limit must be greater than zero")
        if self.memory_mb <= 0:
            raise ValueError("Memory limit must be greater than zero")


@dataclass(frozen=True)
class HealthCheckConfig:
    interval_seconds: float = 5.0
    timeout_seconds: float = 2.0
    retries: int = 3
    start_period_seconds: float = 0.0

    def validate(self) -> None:
        if self.interval_seconds <= 0:
            raise HealthCheckError("Health-check interval must be positive")
        if self.timeout_seconds <= 0:
            raise HealthCheckError("Health-check timeout must be positive")
        if self.timeout_seconds > self.interval_seconds:
            raise HealthCheckError("Timeout cannot exceed the check interval")
        if self.retries < 1:
            raise HealthCheckError("Retries must be at least one")
        if self.start_period_seconds < 0:
            raise HealthCheckError("Start period cannot be negative")


@dataclass
class HealthResult:
    timestamp: float
    success: bool
    latency_ms: float
    message: str


@dataclass
class Container:
    name: str
    image: str
    resources: ResourceLimits
    healthcheck: HealthCheckConfig
    restart_policy: RestartPolicy = RestartPolicy.NO
    max_restarts: int = 5

    state: ContainerState = ContainerState.CREATED
    health: HealthStatus = HealthStatus.STARTING
    consecutive_failures: int = 0
    restart_count: int = 0
    manually_stopped: bool = False
    health_history: List[HealthResult] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.resources.validate()
        self.healthcheck.validate()

        if not self.name.strip():
            raise ValueError("Container name cannot be empty")
        if not self.image.strip():
            raise ValueError("Container image cannot be empty")
        if self.max_restarts < 0:
            raise ValueError("max_restarts cannot be negative")

    def start(self) -> None:
        if self.state == ContainerState.RUNNING:
            return

        self.manually_stopped = False
        self.state = ContainerState.RUNNING
        self.health = HealthStatus.STARTING
        self.consecutive_failures = 0

    def stop(self, manual: bool = True) -> None:
        self.state = ContainerState.STOPPED
        self.manually_stopped = manual

    def should_restart(self, exit_code: int) -> bool:
        if self.manually_stopped:
            return False

        if self.restart_count >= self.max_restarts:
            return False

        if self.restart_policy == RestartPolicy.NO:
            return False

        if self.restart_policy == RestartPolicy.ALWAYS:
            return True

        if self.restart_policy == RestartPolicy.UNLESS_STOPPED:
            return True

        return (
            self.restart_policy == RestartPolicy.ON_FAILURE
            and exit_code != 0
        )

    def record_health(self, result: HealthResult, elapsed_since_start: float) -> None:
        self.health_history.append(result)

        if elapsed_since_start < self.healthcheck.start_period_seconds:
            self.health = HealthStatus.STARTING
            self.consecutive_failures = 0
            return

        if result.success and result.latency_ms <= self.healthcheck.timeout_seconds * 1000:
            self.consecutive_failures = 0
            self.health = HealthStatus.HEALTHY
            return

        self.consecutive_failures += 1

        if self.consecutive_failures >= self.healthcheck.retries:
            self.health = HealthStatus.UNHEALTHY

    def restart(self) -> None:
        if self.restart_count >= self.max_restarts:
            raise RuntimeError(f"Restart limit reached for {self.name}")

        self.state = ContainerState.RESTARTING
        self.restart_count += 1
        self.start()


@dataclass
class ContainerRuntime:
    containers: Dict[str, Container] = field(default_factory=dict)

    def register(self, container: Container) -> None:
        if container.name in self.containers:
            raise ValueError(f"Container already exists: {container.name}")
        self.containers[container.name] = container

    def start_all(self) -> None:
        for container in self.containers.values():
            container.start()

    def check_health(
        self,
        name: str,
        probe: Callable[[Container], HealthResult],
        elapsed_since_start: float,
    ) -> HealthStatus:
        container = self.containers[name]

        if container.state != ContainerState.RUNNING:
            raise RuntimeError(
                f"Cannot health-check non-running container: {name}"
            )

        result = probe(container)
        container.record_health(result, elapsed_since_start)

        if container.health == HealthStatus.UNHEALTHY:
            self._recover(container, exit_code=1)

        return container.health

    @staticmethod
    def _recover(container: Container, exit_code: int) -> None:
        if not container.should_restart(exit_code):
            return

        # A real runtime would use exponential backoff and jitter.
        # The simulator keeps the operation deterministic.
        container.restart()


def simulated_http_probe(container: Container) -> HealthResult:
    """Example probe for a web service."""
    now = time.time()

    if container.name == "api":
        return HealthResult(
            timestamp=now,
            success=True,
            latency_ms=45.0,
            message="HTTP 200 /health",
        )

    return HealthResult(
        timestamp=now,
        success=False,
        latency_ms=3000.0,
        message="Health endpoint timeout",
    )


def failing_probe(container: Container) -> HealthResult:
    return HealthResult(
        timestamp=time.time(),
        success=False,
        latency_ms=2500.0,
        message="dependency unavailable",
    )


def print_status(runtime: ContainerRuntime) -> None:
    print("\nContainer status")
    print("-" * 78)

    for container in runtime.containers.values():
        print(
            f"{container.name:12} "
            f"state={container.state.value:10} "
            f"health={container.health.value:9} "
            f"restarts={container.restart_count} "
            f"cpu={container.resources.cpu_millicores}m "
            f"memory={container.resources.memory_mb}MB"
        )


def main() -> None:
    runtime = ContainerRuntime()

    api = Container(
        name="api",
        image="example/api:2.4",
        resources=ResourceLimits(
            cpu_millicores=500,
            memory_mb=512,
        ),
        healthcheck=HealthCheckConfig(
            interval_seconds=5,
            timeout_seconds=2,
            retries=3,
            start_period_seconds=5,
        ),
        restart_policy=RestartPolicy.UNLESS_STOPPED,
    )

    worker = Container(
        name="worker",
        image="example/worker:4.1",
        resources=ResourceLimits(
            cpu_millicores=750,
            memory_mb=1024,
        ),
        healthcheck=HealthCheckConfig(
            interval_seconds=10,
            timeout_seconds=3,
            retries=2,
        ),
        restart_policy=RestartPolicy.ON_FAILURE,
        max_restarts=2,
    )

    runtime.register(api)
    runtime.register(worker)
    runtime.start_all()

    # During the start period, failed probes do not immediately mark
    # a container unhealthy.
    runtime.check_health("api", simulated_http_probe, elapsed_since_start=2)
    runtime.check_health("api", simulated_http_probe, elapsed_since_start=8)

    # Worker repeatedly fails and eventually reaches the configured
    # restart boundary.
    for attempt in range(4):
        try:
            status = runtime.check_health(
                "worker",
                failing_probe,
                elapsed_since_start=20,
            )
            print(f"worker health attempt {attempt + 1}: {status.value}")
        except RuntimeError as exc:
            print(f"worker recovery stopped: {exc}")
            break

    print_status(runtime)

    # Manual stops must prevent policies such as ALWAYS and
    # UNLESS-STOPPED from automatically bringing the service back.
    api.stop(manual=True)

    if not api.should_restart(exit_code=1):
        print("\nManual stop correctly suppresses automatic restart.")

    # Security and validation checks.
    try:
        ResourceLimits(cpu_millicores=0, memory_mb=512).validate()
    except ValueError as exc:
        print(f"Validation rejected invalid resource limit: {exc}")

    try:
        HealthCheckConfig(
            interval_seconds=2,
            timeout_seconds=4,
        ).validate()
    except HealthCheckError as exc:
        print(f"Validation rejected invalid health check: {exc}")

    assert api.health == HealthStatus.HEALTHY
    assert api.restart_count == 0
    assert worker.restart_count <= worker.max_restarts

    print("\nAssertions passed.")
    print(
        "Production note: resource limits must be enforced by the container "
        "runtime, while HEALTHCHECK only reports application health."
    )


if __name__ == "__main__":
    main()
