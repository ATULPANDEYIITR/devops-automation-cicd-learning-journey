#!/usr/bin/env python3
"""
Ansible Fundamentals: Inventory, Modules, and Playbooks

A self-contained Ansible-inspired configuration management simulator.
Demonstrates inventory management, host groups, module execution,
playbook orchestration, variable precedence, idempotency, handlers,
check mode, error handling, and execution reporting.

Python standard library only.
"""

from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger("ansible_fundamentals")


class ConfigurationError(Exception):
    """Raised when inventory or playbook configuration is invalid."""


class ExecutionError(Exception):
    """Raised when a configuration task cannot execute."""


class TaskStatus(Enum):
    CHANGED = "changed"
    OK = "ok"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class Host:
    name: str
    address: str
    username: str = "ansible"
    port: int = 22
    variables: dict[str, Any] = field(default_factory=dict)
    state: dict[str, Any] = field(default_factory=dict)
    reachable: bool = True

    def __post_init__(self):
        if not self.name or not self.address:
            raise ConfigurationError("Host name and address are required.")

        if not 1 <= self.port <= 65535:
            raise ConfigurationError("Invalid SSH port.")


class Inventory:
    """Maintains hosts, groups, and group-level variables."""

    def __init__(self):
        self.hosts: dict[str, Host] = {}
        self.groups: dict[str, set[str]] = {}
        self.group_variables: dict[str, dict[str, Any]] = {}

    def add_host(self, host: Host, groups: list[str] | None = None):
        if host.name in self.hosts:
            raise ConfigurationError(
                f"Duplicate inventory host: {host.name}"
            )

        self.hosts[host.name] = host

        for group in groups or ["ungrouped"]:
            if not re.fullmatch(r"[A-Za-z0-9_]+", group):
                raise ConfigurationError(f"Invalid group: {group}")

            self.groups.setdefault(group, set()).add(host.name)

    def set_group_variables(
        self,
        group: str,
        variables: dict[str, Any]
    ):
        if group not in self.groups:
            raise ConfigurationError(f"Unknown group: {group}")

        self.group_variables[group] = variables.copy()

    def resolve_hosts(self, pattern: str) -> list[Host]:
        if pattern == "all":
            names = set(self.hosts)
        elif pattern in self.groups:
            names = self.groups[pattern].copy()
        elif pattern in self.hosts:
            names = {pattern}
        else:
            raise ConfigurationError(
                f"Inventory pattern not found: {pattern}"
            )

        return [self.hosts[name] for name in sorted(names)]

    def effective_variables(self, host: Host) -> dict[str, Any]:
        result = {}

        # Host variables override group variables.
        for group, members in self.groups.items():
            if host.name in members:
                result.update(self.group_variables.get(group, {}))

        result.update(host.variables)
        return result

    @classmethod
    def from_ini(cls, content: str) -> Inventory:
        """
        Parse a basic INI inventory.

        Supports:
            [web]
            server1 ansible_host=192.168.1.10 ansible_user=admin
        """

        inventory = cls()
        current_group = "ungrouped"

        for line_number, raw_line in enumerate(content.splitlines(), 1):
            line = raw_line.split("#", 1)[0].strip()

            if not line:
                continue

            if line.startswith("[") and line.endswith("]"):
                current_group = line[1:-1].strip()

                if not re.fullmatch(
                    r"[A-Za-z0-9_]+",
                    current_group
                ):
                    raise ConfigurationError(
                        f"Invalid group at line {line_number}"
                    )

                inventory.groups.setdefault(current_group, set())
                continue

            parts = line.split()
            name = parts[0]
            variables = {}

            for item in parts[1:]:
                if "=" not in item:
                    raise ConfigurationError(
                        f"Invalid inventory variable at line {line_number}"
                    )

                key, value = item.split("=", 1)
                variables[key] = value

            address = variables.pop("ansible_host", name)
            username = variables.pop("ansible_user", "ansible")
            port = int(variables.pop("ansible_port", 22))

            host = Host(
                name=name,
                address=address,
                username=username,
                port=port,
                variables=variables
            )

            if name not in inventory.hosts:
                inventory.add_host(host, [current_group])
            else:
                inventory.groups.setdefault(
                    current_group, set()
                ).add(name)

        return inventory


class Module:
    """Base class for configuration management modules."""

    def execute(
        self,
        host: Host,
        arguments: dict[str, Any],
        check_mode: bool = False
    ) -> tuple[TaskStatus, str]:
        raise NotImplementedError


class FileModule(Module):
    """Manage file and directory state."""

    def execute(self, host, arguments, check_mode=False):
        path = arguments.get("path")
        state = arguments.get("state", "file")
        mode = arguments.get("mode", "0644")

        if not isinstance(path, str) or not path.startswith("/"):
            raise ExecutionError("An absolute file path is required.")

        if ".." in Path(path).parts:
            raise ExecutionError("Path traversal is not permitted.")

        if state not in {"file", "directory", "absent"}:
            raise ExecutionError("Unsupported file state.")

        if not re.fullmatch(r"[0-7]{3,4}", str(mode)):
            raise ExecutionError("Invalid file permission mode.")

        current = host.state.get(path)

        desired = {
            "type": state,
            "mode": str(mode)
        }

        if state == "absent":
            desired = None

        if current == desired:
            return TaskStatus.OK, f"{path} already matches desired state"

        if not check_mode:
            if desired is None:
                host.state.pop(path, None)
            else:
                host.state[path] = desired

        return TaskStatus.CHANGED, f"File state evaluated for {path}"


class PackageModule(Module):
    """Simulate package installation and removal."""

    def execute(self, host, arguments, check_mode=False):
        name = arguments.get("name")
        state = arguments.get("state", "present")

        if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z0-9_.+-]+", name
        ):
            raise ExecutionError("Invalid package name.")

        if state not in {"present", "absent"}:
            raise ExecutionError("Invalid package state.")

        installed = host.state.setdefault("packages", set())
        exists = name in installed

        if (state == "present" and exists) or (
            state == "absent" and not exists
        ):
            return TaskStatus.OK, f"Package {name} already compliant"

        if not check_mode:
            if state == "present":
                installed.add(name)
            else:
                installed.discard(name)

        return TaskStatus.CHANGED, f"Package {name}: {state}"


class ServiceModule(Module):
    """Manage service state."""

    def execute(self, host, arguments, check_mode=False):
        name = arguments.get("name")
        state = arguments.get("state", "started")
        enabled = arguments.get("enabled", True)

        if not isinstance(name, str) or not re.fullmatch(
            r"[A-Za-z0-9_.@-]+", name
        ):
            raise ExecutionError("Invalid service name.")

        if state not in {"started", "stopped"}:
            raise ExecutionError("Unsupported service state.")

        if not isinstance(enabled, bool):
            raise ExecutionError("enabled must be boolean.")

        services = host.state.setdefault("services", {})

        desired = {
            "state": state,
            "enabled": enabled
        }

        if services.get(name) == desired:
            return TaskStatus.OK, f"Service {name} already compliant"

        if not check_mode:
            services[name] = desired

        return TaskStatus.CHANGED, f"Service {name}: {state}"


class CommandModule(Module):
    """
    Restricted command simulator.

    Arbitrary shell execution is intentionally excluded.
    """

    ALLOWED_COMMANDS = {
        "check_http": "HTTP configuration checked",
        "check_disk": "Disk capacity checked",
        "check_service": "Service availability checked"
    }

    def execute(self, host, arguments, check_mode=False):
        command = arguments.get("command")

        if command not in self.ALLOWED_COMMANDS:
            raise ExecutionError("Command is not permitted.")

        return (
            TaskStatus.OK,
            self.ALLOWED_COMMANDS[command]
        )


class ModuleRegistry:
    def __init__(self):
        self.modules: dict[str, Module] = {
            "file": FileModule(),
            "package": PackageModule(),
            "service": ServiceModule(),
            "command": CommandModule()
        }

    def execute(self, name, host, arguments, check_mode=False):
        module = self.modules.get(name)

        if module is None:
            raise ExecutionError(f"Unknown module: {name}")

        return module.execute(host, arguments, check_mode)


@dataclass
class Task:
    name: str
    module: str
    arguments: dict[str, Any]
    notify: list[str] = field(default_factory=list)
    when: bool = True
    ignore_errors: bool = False


@dataclass
class Play:
    name: str
    hosts: str
    tasks: list[Task]
    variables: dict[str, Any] = field(default_factory=dict)
    handlers: dict[str, Task] = field(default_factory=dict)
    become: bool = False


@dataclass
class TaskResult:
    host: str
    task: str
    status: TaskStatus
    message: str


class PlaybookEngine:
    def __init__(self, inventory: Inventory):
        self.inventory = inventory
        self.registry = ModuleRegistry()
        self.results: list[TaskResult] = []

    def execute_play(
        self,
        play: Play,
        check_mode: bool = False
    ) -> list[TaskResult]:

        if not play.name or not play.tasks:
            raise ConfigurationError(
                "A play requires a name and at least one task."
            )

        hosts = self.inventory.resolve_hosts(play.hosts)
        play_results = []

        for host in hosts:
            if not host.reachable:
                result = TaskResult(
                    host.name,
                    "connection",
                    TaskStatus.FAILED,
                    "Host is unreachable"
                )
                self._record(result)
                play_results.append(result)
                continue

            variables = self.inventory.effective_variables(host)
            variables.update(play.variables)

            notified_handlers = set()
            failed = False

            for task in play.tasks:
                if failed:
                    break

                if not task.when:
                    result = TaskResult(
                        host.name,
                        task.name,
                        TaskStatus.SKIPPED,
                        "Condition evaluated to false"
                    )
                    self._record(result)
                    play_results.append(result)
                    continue

                try:
                    arguments = self._resolve_arguments(
                        task.arguments,
                        variables
                    )

                    status, message = self.registry.execute(
                        task.module,
                        host,
                        arguments,
                        check_mode
                    )

                    result = TaskResult(
                        host.name,
                        task.name,
                        status,
                        message
                    )

                    if status == TaskStatus.CHANGED:
                        notified_handlers.update(task.notify)

                except (ExecutionError, ValueError, TypeError) as exc:
                    result = TaskResult(
                        host.name,
                        task.name,
                        TaskStatus.FAILED,
                        str(exc)
                    )

                    if not task.ignore_errors:
                        failed = True

                self._record(result)
                play_results.append(result)

            if not failed:
                for handler_name in sorted(notified_handlers):
                    handler = play.handlers.get(handler_name)

                    if handler is None:
                        logger.error(
                            "Unknown handler: %s",
                            handler_name
                        )
                        continue

                    try:
                        status, message = self.registry.execute(
                            handler.module,
                            host,
                            self._resolve_arguments(
                                handler.arguments,
                                variables
                            ),
                            check_mode
                        )

                        result = TaskResult(
                            host.name,
                            f"handler:{handler_name}",
                            status,
                            message
                        )

                    except (ExecutionError, ValueError, TypeError) as exc:
                        result = TaskResult(
                            host.name,
                            f"handler:{handler_name}",
                            TaskStatus.FAILED,
                            str(exc)
                        )

                    self._record(result)
                    play_results.append(result)

        return play_results

    @staticmethod
    def _resolve_arguments(
        arguments: dict[str, Any],
        variables: dict[str, Any]
    ) -> dict[str, Any]:
        """
        Resolve complete variable expressions.

        Example: "{{ package_name }}" becomes the actual variable value.
        """

        pattern = re.compile(r"^\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}$")

        def resolve(value):
            if isinstance(value, str):
                match = pattern.fullmatch(value)

                if match:
                    key = match.group(1)

                    if key not in variables:
                        raise ExecutionError(
                            f"Undefined variable: {key}"
                        )

                    return variables[key]

            if isinstance(value, dict):
                return {
                    key: resolve(item)
                    for key, item in value.items()
                }

            if isinstance(value, list):
                return [resolve(item) for item in value]

            return value

        return resolve(arguments)

    def _record(self, result: TaskResult):
        self.results.append(result)

        logger.info(
            "%-12s %-24s %-8s %s",
            result.host,
            result.task,
            result.status.value,
            result.message
        )

    def report(self) -> dict[str, Any]:
        report = {}

        for result in self.results:
            host_report = report.setdefault(
                result.host,
                {
                    "ok": 0,
                    "changed": 0,
                    "failed": 0,
                    "skipped": 0
                }
            )

            host_report[result.status.value] += 1

        return report


def build_example() -> tuple[Inventory, list[Play]]:
    inventory = Inventory()

    inventory.add_host(
        Host(
            "web01",
            "192.168.10.11",
            variables={"environment": "production"}
        ),
        ["web"]
    )

    inventory.add_host(
        Host(
            "web02",
            "192.168.10.12",
            variables={"environment": "production"}
        ),
        ["web"]
    )

    inventory.add_host(
        Host(
            "db01",
            "192.168.10.21",
            variables={"environment": "production"}
        ),
        ["database"]
    )

    inventory.set_group_variables(
        "web",
        {"package_name": "nginx"}
    )

    inventory.set_group_variables(
        "database",
        {"package_name": "postgresql"}
    )

    web_play = Play(
        name="Configure web infrastructure",
        hosts="web",
        variables={"service_enabled": True},
        tasks=[
            Task(
                name="Install web package",
                module="package",
                arguments={
                    "name": "{{ package_name }}",
                    "state": "present"
                }
            ),
            Task(
                name="Create application directory",
                module="file",
                arguments={
                    "path": "/srv/application",
                    "state": "directory",
                    "mode": "0755"
                }
            ),
            Task(
                name="Start web service",
                module="service",
                arguments={
                    "name": "nginx",
                    "state": "started",
                    "enabled": "{{ service_enabled }}"
                },
                notify=["reload_web"]
            ),
            Task(
                name="Check HTTP configuration",
                module="command",
                arguments={"command": "check_http"}
            )
        ],
        handlers={
            "reload_web": Task(
                name="Reload web service",
                module="service",
                arguments={
                    "name": "nginx",
                    "state": "started",
                    "enabled": True
                }
            )
        }
    )

    database_play = Play(
        name="Configure database infrastructure",
        hosts="database",
        tasks=[
            Task(
                name="Install database package",
                module="package",
                arguments={
                    "name": "{{ package_name }}",
                    "state": "present"
                }
            ),
            Task(
                name="Start database service",
                module="service",
                arguments={
                    "name": "postgresql",
                    "state": "started",
                    "enabled": True
                }
            )
        ]
    )

    return inventory, [web_play, database_play]


def main():
    parser = argparse.ArgumentParser(
        description="Ansible fundamentals simulator"
    )

    parser.add_argument(
        "--check",
        action="store_true",
        help="Simulate changes without modifying host state"
    )

    parser.add_argument(
        "--inventory",
        type=Path,
        help="Optional INI inventory file"
    )

    parser.add_argument(
        "--output",
        type=Path,
        help="Optional JSON report destination"
    )

    args = parser.parse_args()

    inventory, plays = build_example()

    if args.inventory:
        try:
            inventory = Inventory.from_ini(
                args.inventory.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, ConfigurationError) as exc:
            logger.error("Inventory loading failed: %s", exc)
            return 1

    engine = PlaybookEngine(inventory)

    for play in plays:
        try:
            engine.execute_play(play, check_mode=args.check)
        except ConfigurationError as exc:
            logger.error("Play failed: %s", exc)
            return 1

    report = engine.report()

    print("\nExecution report:")
    print(json.dumps(report, indent=4))

    if args.output:
        try:
            args.output.write_text(
                json.dumps(report, indent=4),
                encoding="utf-8"
            )
        except OSError as exc:
            logger.error("Could not save report: %s", exc)
            return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
