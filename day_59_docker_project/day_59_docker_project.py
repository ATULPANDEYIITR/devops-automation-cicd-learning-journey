#!/usr/bin/env python3
"""
Multi-service Docker application simulator and deployment validator.

The model represents a small production-style application composed of:
- frontend
- API
- worker
- PostgreSQL
- Redis

It validates service dependencies, environment configuration, health states,
startup ordering, resource constraints, network reachability, and shutdown
behavior. The implementation intentionally models Docker Compose concepts
without requiring Docker to be installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Iterable, List, Optional, Set


class ServiceState(Enum):
    CREATED = "created"
    STARTING = "starting"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"
    STOPPED = "stopped"


class DependencyCondition(Enum):
    STARTED = "service_started"
    HEALTHY = "service_healthy"


@dataclass(frozen=True)
class Dependency:
    service: str
    condition: DependencyCondition = DependencyCondition.STARTED


@dataclass
class Service:
    name: str
    image: str
    port: Optional[int]
    environment: Dict[str, str] = field(default_factory=dict)
    dependencies: List[Dependency] = field(default_factory=list)
    memory_mb: int = 256
    state: ServiceState = ServiceState.CREATED
    restart_count: int = 0

    def validate(self) -> None:
        if not self.name or not self.name.replace("-", "").isalnum():
            raise ValueError(f"Invalid service name: {self.name!r}")

        if not self.image or ":" not in self.image:
            raise ValueError(
                f"{self.name}: image must use an explicit tag, for example "
                "'postgres:18'"
            )

        if self.port is not None and not 1 <= self.port <= 65535:
            raise ValueError(f"{self.name}: invalid port {self.port}")

        if self.memory_mb < 64:
            raise ValueError(f"{self.name}: memory allocation is too small")

        for key, value in self.environment.items():
            if not key or not key.replace("_", "").isalnum():
                raise ValueError(f"{self.name}: invalid environment variable {key!r}")
            if "\x00" in value:
                raise ValueError(f"{self.name}: NUL byte in environment value")


@dataclass
class Network:
    name: str
    services: Set[str] = field(default_factory=set)

    def connect(self, service_name: str) -> None:
        self.services.add(service_name)

    def can_reach(self, source: str, destination: str) -> bool:
        return source in self.services and destination in self.services


class ComposeValidator:
    """Validates a Compose-like service graph before startup."""

    def __init__(self, services: Iterable[Service]):
        self.services: Dict[str, Service] = {service.name: service for service in services}

    def validate(self) -> None:
        if not self.services:
            raise ValueError("Application must contain at least one service")

        for service in self.services.values():
            service.validate()

            for dependency in service.dependencies:
                if dependency.service not in self.services:
                    raise ValueError(
                        f"{service.name}: dependency {dependency.service!r} "
                        "does not exist"
                    )

                if dependency.service == service.name:
                    raise ValueError(
                        f"{service.name}: service cannot depend on itself"
                    )

        self._validate_cycles()
        self._validate_host_ports()

    def _validate_cycles(self) -> None:
        graph = {
            name: [dependency.service for dependency in service.dependencies]
            for name, service in self.services.items()
        }

        visiting: Set[str] = set()
        visited: Set[str] = set()

        def visit(node: str) -> None:
            if node in visiting:
                raise ValueError("Dependency cycle detected")
            if node in visited:
                return

            visiting.add(node)
            for dependency in graph[node]:
                visit(dependency)
            visiting.remove(node)
            visited.add(node)

        for service_name in graph:
            visit(service_name)

    def _validate_host_ports(self) -> None:
        used: Dict[int, str] = {}
        for service in self.services.values():
            if service.port is None:
                continue
            if service.port in used:
                raise ValueError(
                    f"Host port {service.port} is already assigned to "
                    f"{used[service.port]}"
                )
            used[service.port] = service.name

    def startup_order(self) -> List[str]:
        """
        Topological ordering.

        This orders dependency relationships, while health conditions are
        handled separately by the runtime.
        """
        indegree = {name: 0 for name in self.services}
        graph = {name: [] for name in self.services}

        for service in self.services.values():
            for dependency in service.dependencies:
                graph[dependency.service].append(service.name)
                indegree[service.name] += 1

        queue = [name for name, degree in indegree.items() if degree == 0]
        order: List[str] = []

        while queue:
            current = queue.pop(0)
            order.append(current)

            for dependent in graph[current]:
                indegree[dependent] -= 1
                if indegree[dependent] == 0:
                    queue.append(dependent)

        if len(order) != len(self.services):
            raise ValueError("Unable to produce a valid startup order")

        return order


class ComposeRuntime:
    def __init__(self, services: Iterable[Service]):
        self.services: Dict[str, Service] = {
            service.name: service for service in services
        }
        self.network = Network("application-network")
        self.validator = ComposeValidator(self.services)

    def validate(self) -> None:
        self.validator.validate()

    def _dependencies_ready(self, service: Service) -> bool:
        for dependency in service.dependencies:
            dependency_service = self.services[dependency.service]

            if dependency.condition == DependencyCondition.STARTED:
                if dependency_service.state not in {
                    ServiceState.STARTING,
                    ServiceState.HEALTHY,
                }:
                    return False

            elif dependency.condition == DependencyCondition.HEALTHY:
                if dependency_service.state != ServiceState.HEALTHY:
                    return False

        return True

    def start(self, service_name: str) -> None:
        if service_name not in self.services:
            raise KeyError(service_name)

        service = self.services[service_name]

        if service.state == ServiceState.HEALTHY:
            return

        if not self._dependencies_ready(service):
            raise RuntimeError(
                f"{service_name} cannot start because dependencies are not ready"
            )

        service.state = ServiceState.STARTING
        self.network.connect(service.name)

        # In this deterministic model startup completes immediately.
        service.state = ServiceState.HEALTHY

    def start_all(self) -> List[str]:
        self.validate()
        order = self.validator.startup_order()

        for name in order:
            self.start(name)

        return order

    def stop(self, service_name: str) -> None:
        service = self.services[service_name]
        service.state = ServiceState.STOPPED
        self.network.services.discard(service_name)

    def restart(self, service_name: str) -> None:
        service = self.services[service_name]
        self.stop(service_name)
        service.restart_count += 1
        self.start(service_name)

    def mark_unhealthy(self, service_name: str) -> None:
        self.services[service_name].state = ServiceState.UNHEALTHY

    def health_report(self) -> Dict[str, str]:
        return {
            name: service.state.value
            for name, service in sorted(self.services.items())
        }

    def print_status(self) -> None:
        print("\nSERVICE STATUS")
        print("-" * 68)

        for service in sorted(self.services.values(), key=lambda item: item.name):
            print(
                f"{service.name:12} "
                f"{service.state.value:10} "
                f"image={service.image:18} "
                f"memory={service.memory_mb:4}MB "
                f"restarts={service.restart_count}"
            )

        print(f"network: {self.network.name}")
        print(f"connected: {', '.join(sorted(self.network.services))}")


def build_application() -> List[Service]:
    return [
        Service(
            name="db",
            image="postgres:18",
            port=5432,
            environment={
                "POSTGRES_DB": "orders",
                "POSTGRES_USER": "app",
                "POSTGRES_PASSWORD": "change-this-in-production",
            },
            memory_mb=512,
        ),
        Service(
            name="redis",
            image="redis:8",
            port=6379,
            memory_mb=256,
        ),
        Service(
            name="api",
            image="orders-api:1.0",
            port=8080,
            environment={
                "DATABASE_HOST": "db",
                "DATABASE_NAME": "orders",
                "REDIS_HOST": "redis",
            },
            dependencies=[
                Dependency("db", DependencyCondition.HEALTHY),
                Dependency("redis", DependencyCondition.HEALTHY),
            ],
            memory_mb=512,
        ),
        Service(
            name="worker",
            image="orders-worker:1.0",
            port=None,
            environment={
                "DATABASE_HOST": "db",
                "REDIS_HOST": "redis",
            },
            dependencies=[
                Dependency("db", DependencyCondition.HEALTHY),
                Dependency("redis", DependencyCondition.HEALTHY),
            ],
            memory_mb=384,
        ),
        Service(
            name="frontend",
            image="orders-frontend:1.0",
            port=3000,
            environment={"API_BASE_URL": "http://api:8080"},
            dependencies=[Dependency("api", DependencyCondition.HEALTHY)],
            memory_mb=256,
        ),
    ]


def run_edge_case_tests() -> None:
    """Assertions cover configuration and dependency failures."""

    bad_service = Service(
        name="broken",
        image="broken-image",
        port=9000,
    )

    try:
        ComposeValidator([bad_service]).validate()
    except ValueError as exc:
        assert "explicit tag" in str(exc)
    else:
        raise AssertionError("Missing image tag should fail validation")

    missing_dependency = Service(
        name="api",
        image="api:1.0",
        port=8081,
        dependencies=[Dependency("missing")],
    )

    try:
        ComposeValidator([missing_dependency]).validate()
    except ValueError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("Missing dependency should fail validation")

    a = Service("a", "a:1.0", None, dependencies=[Dependency("b")])
    b = Service("b", "b:1.0", None, dependencies=[Dependency("a")])

    try:
        ComposeValidator([a, b]).validate()
    except ValueError as exc:
        assert "cycle" in str(exc).lower()
    else:
        raise AssertionError("Dependency cycle should fail validation")


def main() -> None:
    run_edge_case_tests()

    services = build_application()
    runtime = ComposeRuntime(services)

    print("VALIDATING MULTI-SERVICE APPLICATION")
    runtime.validate()

    order = runtime.start_all()

    print("STARTUP ORDER")
    print(" -> ".join(order))

    runtime.print_status()

    assert runtime.network.can_reach("frontend", "api")
    assert runtime.network.can_reach("api", "db")
    assert runtime.network.can_reach("worker", "redis")
    assert not runtime.network.can_reach("frontend", "db")

    print("\nSIMULATING DATABASE FAILURE")
    runtime.mark_unhealthy("db")
    runtime.print_status()

    print("\nRECOVERING DATABASE")
    runtime.restart("db")
    runtime.print_status()

    print("\nAPPLICATION HEALTH")
    for name, state in runtime.health_report().items():
        print(f"{name}: {state}")

    print("\nVALIDATION COMPLETE")
    print("The model covers dependency ordering, health conditions,")
    print("network membership, restart state, validation, and failure recovery.")


if __name__ == "__main__":
    main()
