#!/usr/bin/env python3
"""
Ansible Roles: Reusable Configuration-Management Architecture

A self-contained configuration-management simulator demonstrating:
- Role structure and metadata
- Role dependencies and execution order
- Variables, defaults, and precedence
- Tasks, handlers, tags, and notifications
- Idempotent execution
- Check mode
- Dependency validation and circular dependency detection
- Host inventory and role assignment
- Execution reporting and failure handling

Requires Python 3.10 or later.
Uses only the Python standard library.
"""

from __future__ import annotations

import copy
import json
import logging
import re
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger("ansible_roles")


class RoleError(Exception):
    """Base exception for role execution errors."""


class RoleValidationError(RoleError):
    """Invalid role configuration."""


class DependencyError(RoleError):
    """Invalid or cyclic role dependency."""


class TaskExecutionError(RoleError):
    """Task execution failure."""


class TaskStatus(Enum):
    CHANGED = "changed"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Host:
    name: str
    variables: dict[str, Any] = field(default_factory=dict)
    facts: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    failed: bool = False


@dataclass
class TaskResult:
    host: str
    role: str
    task: str
    status: TaskStatus
    message: str

    def to_dict(self) -> dict[str, str]:
        return {
            "host": self.host,
            "role": self.role,
            "task": self.task,
            "status": self.status.value,
            "message": self.message,
        }


@dataclass
class Task:
    name: str
    action: Callable[[Host, dict[str, Any]], tuple[bool, str]]
    tags: set[str] = field(default_factory=set)
    notify: list[str] = field(default_factory=list)
    when: Callable[[Host, dict[str, Any]], bool] | None = None
    become: bool = False

    def validate(self) -> None:
        if not self.name.strip():
            raise RoleValidationError("Task name cannot be empty.")

        if not callable(self.action):
            raise RoleValidationError(
                f"Task '{self.name}' requires a callable action."
            )


@dataclass
class Handler:
    name: str
    action: Callable[[Host, dict[str, Any]], tuple[bool, str]]


@dataclass
class Role:
    name: str
    tasks: list[Task]
    defaults: dict[str, Any] = field(default_factory=dict)
    variables: dict[str, Any] = field(default_factory=dict)
    dependencies: list[str] = field(default_factory=list)
    handlers: dict[str, Handler] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9_-]+", self.name):
            raise RoleValidationError(
                f"Invalid role name: {self.name}"
            )

        for task in self.tasks:
            task.validate()

        for dependency in self.dependencies:
            if dependency == self.name:
                raise DependencyError(
                    f"Role '{self.name}' cannot depend on itself."
                )

        for key, handler in self.handlers.items():
            if key != handler.name:
                raise RoleValidationError(
                    f"Handler key '{key}' does not match its name."
                )


class RoleRegistry:
    """Stores roles and resolves their dependency graph."""

    def __init__(self) -> None:
        self.roles: dict[str, Role] = {}

    def register(self, role: Role) -> None:
        role.validate()

        if role.name in self.roles:
            raise RoleValidationError(
                f"Role '{role.name}' is already registered."
            )

        self.roles[role.name] = role

    def resolve(self, requested: list[str]) -> list[Role]:
        ordered: list[Role] = []
        visited: set[str] = set()
        active: set[str] = set()

        def visit(name: str) -> None:
            if name not in self.roles:
                raise DependencyError(
                    f"Unknown role dependency: '{name}'"
                )

            if name in active:
                raise DependencyError(
                    f"Circular dependency detected at '{name}'."
                )

            if name in visited:
                return

            active.add(name)

            role = self.roles[name]

            for dependency in role.dependencies:
                visit(dependency)

            active.remove(name)
            visited.add(name)
            ordered.append(role)

        for name in requested:
            visit(name)

        return ordered


class VariableResolver:
    """
    Simplified variable precedence:

    role defaults < inventory variables < role variables
    < play variables < extra variables

    This is an educational model, not the complete Ansible
    variable precedence specification.
    """

    @staticmethod
    def resolve(
        role: Role,
        host: Host,
        play_variables: dict[str, Any],
        extra_variables: dict[str, Any],
    ) -> dict[str, Any]:

        result = copy.deepcopy(role.defaults)

        for source in (
            host.variables,
            role.variables,
            play_variables,
            extra_variables,
        ):
            result.update(copy.deepcopy(source))

        return result


class RoleExecutor:
    def __init__(
        self,
        registry: RoleRegistry,
        check_mode: bool = False,
        selected_tags: set[str] | None = None,
        extra_variables: dict[str, Any] | None = None,
        play_variables: dict[str, Any] | None = None,
    ) -> None:

        self.registry = registry
        self.check_mode = check_mode
        self.selected_tags = selected_tags or set()
        self.extra_variables = extra_variables or {}
        self.play_variables = play_variables or {}

        self.results: list[TaskResult] = []
        self.pending_handlers: dict[str, list[tuple[Host, Role]]] = {}

    def record(
        self,
        host: Host,
        role: Role,
        task: str,
        status: TaskStatus,
        message: str,
    ) -> None:

        result = TaskResult(
            host=host.name,
            role=role.name,
            task=task,
            status=status,
            message=message,
        )

        self.results.append(result)

        logger.info(
            "%s | %s | %s | %s",
            host.name,
            role.name,
            task,
            status.value,
        )

    def execute_task(
        self,
        host: Host,
        role: Role,
        task: Task,
        variables: dict[str, Any],
    ) -> None:

        if host.failed:
            return

        if self.selected_tags and not (
            task.tags.intersection(self.selected_tags)
            or "always" in task.tags
        ):
            self.record(
                host, role, task.name,
                TaskStatus.SKIPPED,
                "Task does not match selected tags."
            )
            return

        if task.when is not None:
            if not task.when(host, variables):
                self.record(
                    host, role, task.name,
                    TaskStatus.SKIPPED,
                    "Condition evaluated to false."
                )
                return

        try:
            if self.check_mode:
                self.record(
                    host,
                    role,
                    task.name,
                    TaskStatus.OK,
                    "Check mode: task inspected without changing state."
                )
                return

            changed, message = task.action(host, variables)

            status = (
                TaskStatus.CHANGED if changed else TaskStatus.OK
            )

            self.record(
                host, role, task.name, status, message
            )

            if changed:
                for handler_name in task.notify:
                    if handler_name not in role.handlers:
                        raise RoleValidationError(
                            f"Unknown handler '{handler_name}' "
                            f"in role '{role.name}'."
                        )

                    self.pending_handlers.setdefault(
                        handler_name, []
                    ).append((host, role))

        except Exception as exc:
            host.failed = True

            self.record(
                host,
                role,
                task.name,
                TaskStatus.FAILED,
                str(exc),
            )

    def flush_handlers(self) -> None:
        for handler_name, notifications in list(
            self.pending_handlers.items()
        ):

            unique_hosts: dict[tuple[str, str], tuple[Host, Role]] = {}

            for host, role in notifications:
                unique_hosts[(host.name, role.name)] = (host, role)

            for host, role in unique_hosts.values():
                if host.failed:
                    continue

                handler = role.handlers[handler_name]

                try:
                    changed, message = handler.action(
                        host,
                        VariableResolver.resolve(
                            role,
                            host,
                            self.play_variables,
                            self.extra_variables,
                        ),
                    )

                    self.record(
                        host,
                        role,
                        f"handler:{handler_name}",
                        TaskStatus.CHANGED if changed else TaskStatus.OK,
                        message,
                    )

                except Exception as exc:
                    host.failed = True

                    self.record(
                        host,
                        role,
                        f"handler:{handler_name}",
                        TaskStatus.FAILED,
                        str(exc),
                    )

        self.pending_handlers.clear()

    def run(
        self,
        hosts: list[Host],
        requested_roles: list[str],
    ) -> list[TaskResult]:

        if not hosts:
            raise RoleValidationError(
                "At least one inventory host is required."
            )

        roles = self.registry.resolve(requested_roles)

        for role in roles:
            for host in hosts:
                if host.failed:
                    continue

                variables = VariableResolver.resolve(
                    role,
                    host,
                    self.play_variables,
                    self.extra_variables,
                )

                for task in role.tasks:
                    self.execute_task(
                        host, role, task, variables
                    )

            self.flush_handlers()

        return self.results

    def report(self) -> dict[str, int]:
        counts = {
            status.value: 0 for status in TaskStatus
        }

        for result in self.results:
            counts[result.status.value] += 1

        return counts


# Configuration-management actions.

def ensure_package(
    package_name: str,
) -> Callable[[Host, dict[str, Any]], tuple[bool, str]]:

    def action(
        host: Host,
        variables: dict[str, Any],
    ) -> tuple[bool, str]:

        if not package_name:
            raise TaskExecutionError("Package name is required.")

        installed = host.state.setdefault(
            "packages", set()
        )

        if package_name in installed:
            return False, f"{package_name} is already installed."

        installed.add(package_name)

        return True, f"Installed package {package_name}."

    return action


def ensure_service(
    service_name: str,
) -> Callable[[Host, dict[str, Any]], tuple[bool, str]]:

    def action(
        host: Host,
        variables: dict[str, Any],
    ) -> tuple[bool, str]:

        services = host.state.setdefault("services", {})

        if services.get(service_name) == "running":
            return False, f"{service_name} is already running."

        services[service_name] = "running"

        return True, f"Started {service_name}."

    return action


def ensure_configuration(
    path: str,
    content_variable: str,
) -> Callable[[Host, dict[str, Any]], tuple[bool, str]]:

    def action(
        host: Host,
        variables: dict[str, Any],
    ) -> tuple[bool, str]:

        if not path.startswith("/etc/"):
            raise TaskExecutionError(
                "Configuration path must be under /etc/."
            )

        content = variables.get(content_variable)

        if not isinstance(content, str):
            raise TaskExecutionError(
                f"Variable '{content_variable}' must be a string."
            )

        files = host.state.setdefault("files", {})

        if files.get(path) == content:
            return False, f"{path} is already current."

        files[path] = content

        return True, f"Updated configuration {path}."

    return action


def restart_service(
    service_name: str,
) -> Callable[[Host, dict[str, Any]], tuple[bool, str]]:

    def action(
        host: Host,
        variables: dict[str, Any],
    ) -> tuple[bool, str]:

        services = host.state.setdefault("services", {})

        if services.get(service_name) != "running":
            raise TaskExecutionError(
                f"Cannot restart stopped service '{service_name}'."
            )

        host.state.setdefault("restart_count", {})
        counts = host.state["restart_count"]

        counts[service_name] = counts.get(service_name, 0) + 1

        return True, f"Restarted {service_name}."

    return action


def build_example_registry() -> RoleRegistry:
    registry = RoleRegistry()

    common = Role(
        name="common",
        defaults={
            "timezone": "UTC",
        },
        tasks=[
            Task(
                name="Install system utilities",
                action=ensure_package("curl"),
                tags={"packages", "common"},
            ),
        ],
    )

    webserver = Role(
        name="webserver",
        defaults={
            "http_port": 8080,
            "server_name": "example.internal",
            "web_config": (
                "server { listen 8080; "
                "server_name example.internal; }"
            ),
        },
        dependencies=["common"],
        tasks=[
            Task(
                name="Install nginx",
                action=ensure_package("nginx"),
                tags={"packages", "web"},
            ),
            Task(
                name="Deploy nginx configuration",
                action=ensure_configuration(
                    "/etc/nginx/nginx.conf",
                    "web_config",
                ),
                tags={"configuration", "web"},
                notify=["restart nginx"],
            ),
            Task(
                name="Ensure nginx service is running",
                action=ensure_service("nginx"),
                tags={"services", "web"},
            ),
        ],
        handlers={
            "restart nginx": Handler(
                name="restart nginx",
                action=restart_service("nginx"),
            )
        },
        metadata={
            "author": "Infrastructure Engineering",
            "description": "Reusable nginx configuration role",
            "minimum_ansible_version": "2.14",
        },
    )

    monitoring = Role(
        name="monitoring",
        defaults={
            "monitoring_enabled": True,
        },
        tasks=[
            Task(
                name="Install monitoring agent",
                action=ensure_package("node-exporter"),
                tags={"monitoring"},
                when=lambda host, variables: (
                    variables.get("monitoring_enabled", False)
                ),
            ),
        ],
    )

    registry.register(common)
    registry.register(webserver)
    registry.register(monitoring)

    return registry


def main() -> None:
    registry = build_example_registry()

    inventory = [
        Host(
            name="web-01",
            variables={
                "environment": "production",
            },
        ),
        Host(
            name="web-02",
            variables={
                "environment": "staging",
                "monitoring_enabled": False,
            },
        ),
    ]

    executor = RoleExecutor(
        registry=registry,
        check_mode=False,
        play_variables={
            "web_config": (
                "server { listen 8080; "
                "server_name production.internal; }"
            ),
        },
    )

    results = executor.run(
        hosts=inventory,
        requested_roles=[
            "webserver",
            "monitoring",
        ],
    )

    print("\nExecution report:")
    print(json.dumps(executor.report(), indent=2))

    print("\nDetailed results:")
    print(json.dumps(
        [result.to_dict() for result in results],
        indent=2,
    ))

    print("\nFinal host states:")

    for host in inventory:
        print(
            host.name,
            json.dumps(
                {
                    "packages": sorted(
                        host.state.get("packages", set())
                    ),
                    "services": host.state.get("services", {}),
                    "files": host.state.get("files", {}),
                    "restart_count": host.state.get(
                        "restart_count", {}
                    ),
                    "failed": host.failed,
                },
                indent=2,
            ),
        )

    # Verify idempotence: running the same configuration again
    # must not reinstall packages or rewrite unchanged files.
    print("\nIdempotence verification:")

    second_executor = RoleExecutor(registry)

    second_executor.run(
        inventory,
        ["webserver", "monitoring"],
    )

    assert all(
        result.status != TaskStatus.FAILED
        for result in second_executor.results
    )

    assert all(
        result.status != TaskStatus.CHANGED
        for result in second_executor.results
    )

    print("Idempotence verification passed.")

    # Dependency cycle validation.
    cyclic_registry = RoleRegistry()

    cyclic_registry.register(
        Role("alpha", [], dependencies=["beta"])
    )

    cyclic_registry.register(
        Role("beta", [], dependencies=["alpha"])
    )

    try:
        cyclic_registry.resolve(["alpha"])
    except DependencyError as exc:
        print(f"Dependency validation passed: {exc}")


if __name__ == "__main__":
    main()
