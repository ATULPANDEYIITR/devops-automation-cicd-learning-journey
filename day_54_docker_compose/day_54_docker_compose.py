#!/usr/bin/env python3
"""Docker Compose multi-container application workflow simulator.

Uses only the Python standard library. The model represents service
dependencies, health checks, networks, configuration validation, startup
ordering, failure handling, and reverse-order shutdown.
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Callable

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(message)s",
)
LOGGER = logging.getLogger("compose-lab")


class ServiceState(str, Enum):
    CREATED = "created"
    STARTING = "starting"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STOPPED = "stopped"
    FAILED = "failed"


class ComposeError(Exception):
    """Base exception for simulated Compose failures."""


class ConfigurationError(ComposeError):
    """Invalid service, network, or dependency configuration."""


class StartupError(ComposeError):
    """A service cannot start or become ready."""


@dataclass(frozen=True)
class Network:
    name: str
    internal: bool = False
    driver: str = "bridge"

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", self.name):
            raise ConfigurationError(f"Invalid network name: {self.name}")
        if self.driver not in {"bridge", "overlay"}:
            raise ConfigurationError(f"Unsupported network driver: {self.driver}")


@dataclass(frozen=True)
class Dependency:
    service: str
    condition: str = "service_healthy"

    def __post_init__(self) -> None:
        if self.condition not in {"service_started", "service_healthy"}:
            raise ConfigurationError(
                f"Unsupported dependency condition: {self.condition}"
            )


@dataclass
class Service:
    name: str
    image: str
    networks: set[str]
    dependencies: list[Dependency] = field(default_factory=list)
    healthcheck_required: bool = False
    restart_policy: str = "no"
    environment: dict[str, str] = field(default_factory=dict)
    state: ServiceState = ServiceState.CREATED

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_.-]*", self.name):
            raise ConfigurationError(f"Invalid service name: {self.name}")
        if not self.image.strip():
            raise ConfigurationError(f"Service {self.name} has no image")
        if self.restart_policy not in {"no", "on-failure", "always", "unless-stopped"}:
            raise ConfigurationError(
                f"Invalid restart policy for {self.name}"
            )


@dataclass
class ComposeProject:
    name: str
    networks: dict[str, Network]
    services: dict[str, Service]
    events: list[dict[str, str]] = field(default_factory=list)

    def validate(self) -> None:
        if not self.name.strip():
            raise ConfigurationError("Project name cannot be empty")
        if not self.services:
            raise ConfigurationError("Project must define at least one service")

        for service in self.services.values():
            if not service.networks:
                raise ConfigurationError(
                    f"Service {service.name} must join a network"
                )

            unknown_networks = service.networks - self.networks.keys()
            if unknown_networks:
                raise ConfigurationError(
                    f"{service.name} references unknown networks: "
                    f"{sorted(unknown_networks)}"
                )

            for dependency in service.dependencies:
                if dependency.service not in self.services:
                    raise ConfigurationError(
                        f"{service.name} depends on missing service "
                        f"{dependency.service}"
                    )

                if dependency.service == service.name:
                    raise ConfigurationError(
                        f"{service.name} cannot depend on itself"
                    )

                if (
                    dependency.condition == "service_healthy"
                    and not self.services[dependency.service].healthcheck_required
                ):
                    raise ConfigurationError(
                        f"{dependency.service} needs a health check for "
                        f"service_healthy dependency"
                    )

        self.startup_order()

        # Environment values must not be empty where credentials are required.
        for service in self.services.values():
            for key, value in service.environment.items():
                if key.endswith(("_PASSWORD", "_TOKEN", "_SECRET")) and not value:
                    raise ConfigurationError(
                        f"Required secret variable {key} is empty in "
                        f"{service.name}"
                    )

    def startup_order(self) -> list[str]:
        """Topological sort detects circular service dependencies."""
        indegree = {name: 0 for name in self.services}
        dependents = {name: [] for name in self.services}

        for name, service in self.services.items():
            for dependency in service.dependencies:
                if dependency.service not in self.services:
                    continue
                indegree[name] += 1
                dependents[dependency.service].append(name)

        ready = sorted(name for name, degree in indegree.items() if degree == 0)
        result: list[str] = []

        while ready:
            current = ready.pop(0)
            result.append(current)

            for dependent in sorted(dependents[current]):
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    ready.append(dependent)
                    ready.sort()

        if len(result) != len(self.services):
            raise ConfigurationError("Circular service dependency detected")

        return result

    def connected(self, first: str, second: str) -> bool:
        """Two services can communicate only through a shared network."""
        if first not in self.services or second not in self.services:
            return False

        shared = (
            self.services[first].networks
            & self.services[second].networks
        )
        return bool(shared)

    def record(self, service: str, event: str) -> None:
        self.events.append({"service": service, "event": event})
        LOGGER.info("%s: %s", service, event)

    def start(
        self,
        health_probe: Callable[[Service], bool] | None = None,
    ) -> None:
        self.validate()
        probe = health_probe or (lambda service: True)
        started: list[str] = []

        try:
            for name in self.startup_order():
                service = self.services[name]

                for dependency in service.dependencies:
                    parent = self.services[dependency.service]

                    if dependency.condition == "service_started":
                        if parent.state not in {
                            ServiceState.HEALTHY,
                            ServiceState.UNHEALTHY,
                        }:
                            raise StartupError(
                                f"{name} requires {parent.name} to be started"
                            )
                    elif parent.state != ServiceState.HEALTHY:
                        raise StartupError(
                            f"{name} requires healthy dependency {parent.name}"
                        )

                service.state = ServiceState.STARTING
                self.record(name, "starting")

                started.append(name)

                if probe(service):
                    service.state = ServiceState.HEALTHY
                    self.record(name, "healthy")
                else:
                    service.state = ServiceState.UNHEALTHY
                    self.record(name, "unhealthy")
                    raise StartupError(f"Health check failed for {name}")

        except Exception:
            for name in reversed(started):
                self.services[name].state = ServiceState.STOPPED
                self.record(name, "stopped after startup failure")
            raise

    def stop(self) -> None:
        for name in reversed(self.startup_order()):
            service = self.services[name]
            if service.state != ServiceState.STOPPED:
                service.state = ServiceState.STOPPED
                self.record(name, "stopped")

    def status(self) -> list[dict[str, str]]:
        return [
            {"service": name, "state": service.state.value}
            for name, service in sorted(self.services.items())
        ]


def build_project() -> ComposeProject:
    """A private database, internal API, and public-facing web service."""
    networks = {
        "frontend": Network("frontend"),
        "backend": Network("backend", internal=True),
    }

    services = {
        "db": Service(
            name="db",
            image="postgres:18",
            networks={"backend"},
            healthcheck_required=True,
            restart_policy="unless-stopped",
            environment={
                "POSTGRES_DB": "orders",
                "POSTGRES_USER": "app",
                "POSTGRES_PASSWORD": os.environ.get(
                    "DB_PASSWORD", "local-development-only"
                ),
            },
        ),
        "api": Service(
            name="api",
            image="python:3.13-slim",
            networks={"frontend", "backend"},
            dependencies=[Dependency("db", "service_healthy")],
            healthcheck_required=True,
            restart_policy="on-failure",
            environment={"DATABASE_HOST": "db", "DATABASE_NAME": "orders"},
        ),
        "web": Service(
            name="web",
            image="nginx:alpine",
            networks={"frontend"},
            dependencies=[Dependency("api", "service_healthy")],
            healthcheck_required=True,
            restart_policy="unless-stopped",
        ),
    }

    return ComposeProject("orders-stack", networks, services)


def demonstrate_failure_handling() -> None:
    project = build_project()

    try:
        project.start(
            lambda service: service.name != "db"
        )
    except StartupError as error:
        print(f"Expected startup failure: {error}")

    print("States after failure:")
    print(json.dumps(project.status(), indent=2))


def main() -> None:
    project = build_project()
    project.validate()

    print("Startup order:", " -> ".join(project.startup_order()))
    print("API can reach database:", project.connected("api", "db"))
    print("Web can reach database directly:", project.connected("web", "db"))

    project.start()
    print("Healthy project:")
    print(json.dumps(project.status(), indent=2))

    project.stop()
    print("Stopped project:")
    print(json.dumps(project.status(), indent=2))

    demonstrate_failure_handling()

    # Verify a configuration error is caught before startup.
    invalid = build_project()
    invalid.services["db"].dependencies = [
        Dependency("web", "service_healthy")
    ]
    invalid.services["web"].dependencies = [
        Dependency("db", "service_healthy")
    ]

    try:
        invalid.validate()
    except ConfigurationError as error:
        print(f"Expected configuration failure: {error}")


if __name__ == "__main__":
    main()
