#!/usr/bin/env python3
"""
Terraform Workspaces: Environment Separation and Workspace Strategies

Models Terraform repositories, workspaces, state isolation, environment
configuration, deployment policies, state locking, and workspace lifecycle.

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import json
import re
import hashlib
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


class Environment(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class WorkspaceStatus(Enum):
    ACTIVE = "active"
    LOCKED = "locked"
    DELETED = "deleted"


class DeploymentStatus(Enum):
    PLANNED = "planned"
    APPLIED = "applied"
    FAILED = "failed"


class WorkspaceError(Exception):
    """Base exception for workspace operations."""


class WorkspaceNotFoundError(WorkspaceError):
    pass


class WorkspaceExistsError(WorkspaceError):
    pass


class StateLockedError(WorkspaceError):
    pass


class PolicyViolationError(WorkspaceError):
    pass


class ConfigurationError(WorkspaceError):
    pass


@dataclass(frozen=True)
class EnvironmentConfig:
    name: Environment
    region: str
    instance_type: str
    instance_count: int
    database_enabled: bool
    approval_required: bool
    allowed_instance_types: tuple[str, ...]
    monthly_budget: float

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z]{2}-[a-z]+-\d+", self.region):
            raise ConfigurationError("Invalid cloud region.")

        if self.instance_count < 0:
            raise ConfigurationError("Instance count cannot be negative.")

        if self.instance_type not in self.allowed_instance_types:
            raise ConfigurationError(
                f"Instance type {self.instance_type} is not permitted."
            )

        if self.monthly_budget <= 0:
            raise ConfigurationError("Monthly budget must be positive.")

        if self.name == Environment.PRODUCTION:
            if not self.approval_required:
                raise ConfigurationError(
                    "Production deployments require approval."
                )


@dataclass
class TerraformState:
    workspace_name: str
    serial: int = 0
    resources: dict[str, dict] = field(default_factory=dict)
    lineage: str = field(default_factory=lambda: hashlib.sha256(
        str(datetime.now(timezone.utc).timestamp()).encode()
    ).hexdigest()[:16])
    updated_at: Optional[str] = None

    def fingerprint(self) -> str:
        payload = json.dumps(
            self.resources, sort_keys=True, default=str
        )
        return hashlib.sha256(payload.encode()).hexdigest()


@dataclass
class Workspace:
    name: str
    environment: Environment
    config: EnvironmentConfig
    state: TerraformState
    status: WorkspaceStatus = WorkspaceStatus.ACTIVE
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    deployments: list[dict] = field(default_factory=list)


@dataclass
class Deployment:
    workspace: str
    changes: dict[str, dict]
    status: DeploymentStatus
    timestamp: str
    state_serial: int


class StateLock:
    """Thread-safe in-process state lock for simulation."""

    def __init__(self):
        self._lock = threading.Lock()
        self.owner: Optional[str] = None

    def acquire(self, owner: str) -> None:
        if not self._lock.acquire(blocking=False):
            raise StateLockedError(
                f"State is already locked by {self.owner}."
            )
        self.owner = owner

    def release(self, owner: str) -> None:
        if self.owner != owner:
            raise StateLockedError("Only the lock owner can release it.")
        self.owner = None
        self._lock.release()


class TerraformWorkspaceManager:
    def __init__(
        self,
        configs: dict[Environment, EnvironmentConfig],
        state_directory: str = "terraform_states",
    ):
        self.configs = configs
        self.state_directory = Path(state_directory)
        self.workspaces: dict[str, Workspace] = {}
        self.current_workspace = "default"
        self.locks: dict[str, StateLock] = {}
        self._manager_lock = threading.RLock()

        self.workspaces["default"] = Workspace(
            name="default",
            environment=Environment.DEVELOPMENT,
            config=configs[Environment.DEVELOPMENT],
            state=TerraformState("default"),
        )
        self.locks["default"] = StateLock()

    @staticmethod
    def validate_name(name: str) -> None:
        if not isinstance(name, str):
            raise ConfigurationError("Workspace name must be a string.")

        if not re.fullmatch(r"[a-z][a-z0-9_-]{0,62}", name):
            raise ConfigurationError(
                "Workspace names must start with a lowercase letter "
                "and contain only lowercase letters, digits, _ or -."
            )

    def create_workspace(
        self,
        name: str,
        environment: Environment,
    ) -> Workspace:
        self.validate_name(name)

        with self._manager_lock:
            if name in self.workspaces:
                raise WorkspaceExistsError(
                    f"Workspace '{name}' already exists."
                )

            if environment not in self.configs:
                raise ConfigurationError("Unknown environment.")

            config = self.configs[environment]
            config.validate()

            workspace = Workspace(
                name=name,
                environment=environment,
                config=config,
                state=TerraformState(name),
            )

            self.workspaces[name] = workspace
            self.locks[name] = StateLock()
            return workspace

    def select_workspace(self, name: str) -> Workspace:
        with self._manager_lock:
            workspace = self.workspaces.get(name)

            if workspace is None:
                raise WorkspaceNotFoundError(name)

            if workspace.status != WorkspaceStatus.ACTIVE:
                raise WorkspaceError("Workspace is not active.")

            self.current_workspace = name
            return workspace

    def get_current_workspace(self) -> Workspace:
        return self.workspaces[self.current_workspace]

    def plan(
        self,
        changes: dict[str, Optional[dict]],
    ) -> dict:
        workspace = self.get_current_workspace()
        workspace.config.validate()

        if workspace.status != WorkspaceStatus.ACTIVE:
            raise WorkspaceError("Cannot plan in an inactive workspace.")

        if not isinstance(changes, dict) or not changes:
            raise ConfigurationError("A non-empty changeset is required.")

        current = workspace.state.resources
        operations = []

        for resource_name, desired in changes.items():
            if not re.fullmatch(
                r"[a-zA-Z][a-zA-Z0-9_.-]{0,127}", resource_name
            ):
                raise ConfigurationError("Invalid resource address.")

            if desired is None:
                if resource_name in current:
                    operations.append({
                        "action": "destroy",
                        "resource": resource_name,
                    })
                continue

            if not isinstance(desired, dict):
                raise ConfigurationError(
                    "Resource configuration must be a dictionary."
                )

            existing = current.get(resource_name)

            if existing is None:
                action = "create"
            elif existing != desired:
                action = "update"
            else:
                action = "no_change"

            operations.append({
                "action": action,
                "resource": resource_name,
                "desired": desired,
            })

        return {
            "workspace": workspace.name,
            "environment": workspace.environment.value,
            "state_serial": workspace.state.serial,
            "operations": operations,
            "requires_approval": workspace.config.approval_required,
        }

    def apply(
        self,
        plan: dict,
        approved: bool = False,
    ) -> Deployment:
        workspace = self.get_current_workspace()

        if plan["workspace"] != workspace.name:
            raise PolicyViolationError(
                "Plan belongs to another workspace."
            )

        if plan["state_serial"] != workspace.state.serial:
            raise PolicyViolationError(
                "State changed after planning. Generate a new plan."
            )

        if plan["requires_approval"] and not approved:
            raise PolicyViolationError(
                "Production deployment requires explicit approval."
            )

        lock = self.locks[workspace.name]
        lock.acquire("deployment")

        try:
            updated_resources = dict(workspace.state.resources)

            for operation in plan["operations"]:
                address = operation["resource"]
                action = operation["action"]

                if action in ("create", "update"):
                    updated_resources[address] = operation["desired"]
                elif action == "destroy":
                    updated_resources.pop(address, None)

            workspace.state.resources = updated_resources
            workspace.state.serial += 1
            workspace.state.updated_at = (
                datetime.now(timezone.utc).isoformat()
            )

            deployment = Deployment(
                workspace=workspace.name,
                changes=updated_resources.copy(),
                status=DeploymentStatus.APPLIED,
                timestamp=workspace.state.updated_at,
                state_serial=workspace.state.serial,
            )

            workspace.deployments.append(asdict(deployment))
            return deployment

        finally:
            lock.release("deployment")

    def delete_workspace(self, name: str) -> None:
        with self._manager_lock:
            if name == "default":
                raise PolicyViolationError(
                    "The default workspace cannot be deleted."
                )

            if name == self.current_workspace:
                raise PolicyViolationError(
                    "Select another workspace before deletion."
                )

            workspace = self.workspaces.get(name)

            if workspace is None:
                raise WorkspaceNotFoundError(name)

            if workspace.state.resources:
                raise PolicyViolationError(
                    "Workspace contains resources. Destroy them first."
                )

            workspace.status = WorkspaceStatus.DELETED
            del self.workspaces[name]
            del self.locks[name]

    def export_state(self, name: str, output: str) -> None:
        workspace = self.workspaces.get(name)

        if workspace is None:
            raise WorkspaceNotFoundError(name)

        # State files may contain secrets. Restrict permissions in production.
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(workspace.state), indent=2),
            encoding="utf-8",
        )

        try:
            path.chmod(0o600)
        except OSError:
            pass

    def report(self) -> list[dict]:
        return [
            {
                "workspace": workspace.name,
                "environment": workspace.environment.value,
                "resources": len(workspace.state.resources),
                "serial": workspace.state.serial,
                "state_fingerprint": workspace.state.fingerprint(),
            }
            for workspace in self.workspaces.values()
        ]


def build_manager() -> TerraformWorkspaceManager:
    configs = {
        Environment.DEVELOPMENT: EnvironmentConfig(
            Environment.DEVELOPMENT,
            "ap-south-1",
            "t3.micro",
            1,
            False,
            False,
            ("t3.micro", "t3.small"),
            100,
        ),
        Environment.STAGING: EnvironmentConfig(
            Environment.STAGING,
            "ap-south-1",
            "t3.small",
            2,
            True,
            False,
            ("t3.small", "t3.medium"),
            500,
        ),
        Environment.PRODUCTION: EnvironmentConfig(
            Environment.PRODUCTION,
            "ap-south-1",
            "t3.medium",
            3,
            True,
            True,
            ("t3.medium", "t3.large"),
            2000,
        ),
    }

    return TerraformWorkspaceManager(configs)


def demonstrate() -> None:
    manager = build_manager()

    manager.create_workspace(
        "development",
        Environment.DEVELOPMENT,
    )
    manager.create_workspace(
        "staging",
        Environment.STAGING,
    )
    manager.create_workspace(
        "production",
        Environment.PRODUCTION,
    )

    deployments = [
        ("development", {
            "aws_instance.application": {
                "instance_type": "t3.micro",
                "count": 1,
            }
        }),
        ("staging", {
            "aws_instance.application": {
                "instance_type": "t3.small",
                "count": 2,
            },
            "aws_db_instance.main": {
                "engine": "postgres",
                "storage_gb": 30,
            },
        }),
        ("production", {
            "aws_instance.application": {
                "instance_type": "t3.medium",
                "count": 3,
            },
        }),
    ]

    for workspace_name, changes in deployments:
        manager.select_workspace(workspace_name)
        plan = manager.plan(changes)

        try:
            result = manager.apply(
                plan,
                approved=(workspace_name == "production"),
            )
            print(
                f"{result.workspace}: "
                f"{result.status.value}, serial={result.state_serial}"
            )
        except WorkspaceError as error:
            print(f"Deployment rejected: {error}")

    print("\nWorkspace report:")
    print(json.dumps(manager.report(), indent=2))

    # A stale plan must not be applied after another deployment.
    manager.select_workspace("development")
    stale_plan = manager.plan({
        "aws_instance.application": {
            "instance_type": "t3.small",
            "count": 2,
        }
    })

    manager.apply(manager.plan({
        "aws_instance.application": {
            "instance_type": "t3.micro",
            "count": 2,
        }
    }))

    try:
        manager.apply(stale_plan)
    except PolicyViolationError as error:
        print(f"\nStale plan rejected: {error}")

    # Workspace isolation demonstration.
    manager.select_workspace("development")
    development_resources = manager.get_current_workspace().state.resources

    manager.select_workspace("staging")
    staging_resources = manager.get_current_workspace().state.resources

    assert development_resources is not staging_resources
    assert "aws_db_instance.main" not in development_resources

    print("\nIndependent workspace states verified.")


if __name__ == "__main__":
    demonstrate()
