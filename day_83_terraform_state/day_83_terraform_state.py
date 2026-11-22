#!/usr/bin/env python3
"""
Terraform State Management
--------------------------
Demonstrates:
- Terraform state files and their internal structure
- Resource-to-real-world infrastructure mapping
- Local and remote state backends
- State serial numbers and lineage
- State snapshots and version history
- State locking and concurrent execution prevention
- Optimistic concurrency control
- State refresh and drift detection
- State backup and recovery
- Sensitive output protection
- Workspace isolation
- State migration and resource addressing
- Atomic state persistence

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import threading
import time
import uuid

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional


# ============================================================
# ENUMERATIONS
# ============================================================

class BackendType(Enum):
    LOCAL = "local"
    REMOTE = "remote"


class OperationType(Enum):
    PLAN = "plan"
    APPLY = "apply"
    REFRESH = "refresh"
    IMPORT = "import"
    MIGRATION = "migration"


class ResourceAction(Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NO_CHANGE = "no_change"


class LockStatus(Enum):
    ACQUIRED = "acquired"
    REJECTED = "rejected"
    RELEASED = "released"


# ============================================================
# CUSTOM EXCEPTIONS
# ============================================================

class TerraformStateError(Exception):
    pass


class StateValidationError(TerraformStateError):
    pass


class StateLockError(TerraformStateError):
    pass


class StateConflictError(TerraformStateError):
    pass


class BackendError(TerraformStateError):
    pass


class StateRecoveryError(TerraformStateError):
    pass


# ============================================================
# UTILITY FUNCTIONS
# ============================================================

def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def calculate_checksum(data: dict[str, Any]) -> str:
    serialized = json.dumps(
        data,
        sort_keys=True,
        separators=(",", ":")
    )
    return hashlib.sha256(serialized.encode()).hexdigest()


def deep_copy(data: Any) -> Any:
    return copy.deepcopy(data)


# ============================================================
# RESOURCE MODEL
# ============================================================

@dataclass
class TerraformResource:
    address: str
    resource_type: str
    provider: str
    resource_id: str
    attributes: dict[str, Any] = field(default_factory=dict)
    sensitive_attributes: set[str] = field(default_factory=set)

    def validate(self) -> None:
        if not self.address or "." not in self.address:
            raise StateValidationError(
                f"Invalid resource address: {self.address}"
            )

        if not self.resource_type:
            raise StateValidationError("Resource type is required.")

        if not self.resource_id:
            raise StateValidationError("Resource ID is required.")

        if not isinstance(self.attributes, dict):
            raise StateValidationError(
                "Resource attributes must be a dictionary."
            )

        if not self.sensitive_attributes.issubset(
            self.attributes.keys()
        ):
            raise StateValidationError(
                "Sensitive attributes must exist in resource attributes."
            )

    def to_dict(self) -> dict[str, Any]:
        return {
            "address": self.address,
            "type": self.resource_type,
            "provider": self.provider,
            "id": self.resource_id,
            "attributes": deep_copy(self.attributes),
            "sensitive_attributes": sorted(
                self.sensitive_attributes
            )
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TerraformResource":
        resource = cls(
            address=data["address"],
            resource_type=data["type"],
            provider=data["provider"],
            resource_id=data["id"],
            attributes=deep_copy(data["attributes"]),
            sensitive_attributes=set(
                data.get("sensitive_attributes", [])
            )
        )
        resource.validate()
        return resource

    def display(self) -> dict[str, Any]:
        result = deep_copy(self.to_dict())

        for key in self.sensitive_attributes:
            result["attributes"][key] = "[REDACTED]"

        return result


# ============================================================
# TERRAFORM STATE MODEL
# ============================================================

@dataclass
class TerraformState:
    version: int = 4
    terraform_version: str = "1.10.0"
    lineage: str = field(
        default_factory=lambda: str(uuid.uuid4())
    )
    serial: int = 0
    workspace: str = "default"
    resources: dict[str, TerraformResource] = field(
        default_factory=dict
    )
    outputs: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    updated_at: str = field(default_factory=utc_now)

    def validate(self) -> None:
        if self.version != 4:
            raise StateValidationError(
                "This implementation supports state format version 4."
            )

        if self.serial < 0:
            raise StateValidationError(
                "State serial cannot be negative."
            )

        if not self.lineage:
            raise StateValidationError(
                "State lineage is required."
            )

        for address, resource in self.resources.items():
            resource.validate()

            if address != resource.address:
                raise StateValidationError(
                    "Resource dictionary key and address differ."
                )

        for name, output in self.outputs.items():
            if not name or "value" not in output:
                raise StateValidationError(
                    f"Invalid output: {name}"
                )

    def to_dict(self) -> dict[str, Any]:
        self.validate()

        return {
            "version": self.version,
            "terraform_version": self.terraform_version,
            "lineage": self.lineage,
            "serial": self.serial,
            "workspace": self.workspace,
            "resources": {
                address: resource.to_dict()
                for address, resource in sorted(
                    self.resources.items()
                )
            },
            "outputs": deep_copy(self.outputs),
            "updated_at": self.updated_at
        }

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any]
    ) -> "TerraformState":

        state = cls(
            version=data["version"],
            terraform_version=data["terraform_version"],
            lineage=data["lineage"],
            serial=data["serial"],
            workspace=data["workspace"],
            resources={
                address: TerraformResource.from_dict(resource)
                for address, resource in data.get(
                    "resources", {}
                ).items()
            },
            outputs=deep_copy(data.get("outputs", {})),
            updated_at=data.get("updated_at", utc_now())
        )

        state.validate()
        return state


# ============================================================
# STATE LOCK
# ============================================================

@dataclass
class StateLock:
    lock_id: str
    operation: str
    owner: str
    created_at: str
    hostname: str

    @classmethod
    def create(
        cls,
        operation: str,
        owner: str
    ) -> "StateLock":

        import socket

        return cls(
            lock_id=str(uuid.uuid4()),
            operation=operation,
            owner=owner,
            created_at=utc_now(),
            hostname=socket.gethostname()
        )


# ============================================================
# STATE BACKEND INTERFACE
# ============================================================

class StateBackend:

    def read(self, workspace: str) -> TerraformState:
        raise NotImplementedError

    def write(
        self,
        workspace: str,
        state: TerraformState,
        expected_serial: int
    ) -> None:
        raise NotImplementedError

    def acquire_lock(
        self,
        workspace: str,
        operation: str,
        owner: str
    ) -> StateLock:
        raise NotImplementedError

    def release_lock(
        self,
        workspace: str,
        lock_id: str
    ) -> None:
        raise NotImplementedError


# ============================================================
# LOCAL STATE BACKEND
# ============================================================

class LocalStateBackend(StateBackend):

    def __init__(self, directory: str):
        self.directory = Path(directory)
        self.directory.mkdir(
            parents=True,
            exist_ok=True
        )

        self._mutex = threading.RLock()
        self._locks: dict[str, StateLock] = {}

    def _path(self, workspace: str) -> Path:
        if not workspace or any(
            character not in
            "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-"
            for character in workspace
        ):
            raise BackendError("Invalid workspace name.")

        filename = (
            "terraform.tfstate"
            if workspace == "default"
            else f"terraform.{workspace}.tfstate"
        )

        return self.directory / filename

    def read(self, workspace: str) -> TerraformState:
        with self._mutex:
            path = self._path(workspace)

            if not path.exists():
                return TerraformState(workspace=workspace)

            try:
                with path.open("r", encoding="utf-8") as file:
                    state = TerraformState.from_dict(
                        json.load(file)
                    )

                if state.workspace != workspace:
                    raise StateValidationError(
                        "Workspace mismatch in state file."
                    )

                return state

            except (OSError, json.JSONDecodeError, KeyError) as exc:
                raise BackendError(
                    f"Unable to read state: {exc}"
                ) from exc

    def write(
        self,
        workspace: str,
        state: TerraformState,
        expected_serial: int
    ) -> None:

        with self._mutex:
            current = self.read(workspace)

            if current.serial != expected_serial:
                raise StateConflictError(
                    "State changed after it was read."
                )

            if current.lineage != state.lineage:
                raise StateConflictError(
                    "State lineage mismatch."
                )

            if state.serial != expected_serial + 1:
                raise StateValidationError(
                    "New state serial must increase by one."
                )

            state.workspace = workspace
            state.updated_at = utc_now()
            state.validate()

            path = self._path(workspace)

            # Write to a temporary file before replacing the state.
            fd, temporary_path = tempfile.mkstemp(
                dir=self.directory,
                prefix=".state-",
                suffix=".tmp"
            )

            try:
                with os.fdopen(fd, "w", encoding="utf-8") as file:
                    json.dump(
                        state.to_dict(),
                        file,
                        indent=2,
                        sort_keys=True
                    )
                    file.flush()
                    os.fsync(file.fileno())

                os.replace(temporary_path, path)

            except Exception:
                if os.path.exists(temporary_path):
                    os.remove(temporary_path)
                raise

    def acquire_lock(
        self,
        workspace: str,
        operation: str,
        owner: str
    ) -> StateLock:

        with self._mutex:
            if workspace in self._locks:
                raise StateLockError(
                    f"Workspace {workspace} is already locked."
                )

            lock = StateLock.create(operation, owner)
            self._locks[workspace] = lock
            return lock

    def release_lock(
        self,
        workspace: str,
        lock_id: str
    ) -> None:

        with self._mutex:
            existing = self._locks.get(workspace)

            if existing is None:
                raise StateLockError("No active lock exists.")

            if existing.lock_id != lock_id:
                raise StateLockError("Lock ownership mismatch.")

            del self._locks[workspace]


# ============================================================
# REMOTE STATE BACKEND
# ============================================================

class RemoteStateBackend(StateBackend):
    """
    In-memory remote backend simulation.

    A production implementation should use a durable remote
    object store and a distributed locking mechanism.
    """

    def __init__(self):
        self._states: dict[str, TerraformState] = {}
        self._locks: dict[str, StateLock] = {}
        self._history: dict[
            str, list[dict[str, Any]]
        ] = {}

        self._mutex = threading.RLock()

    def read(self, workspace: str) -> TerraformState:
        with self._mutex:
            if workspace not in self._states:
                return TerraformState(workspace=workspace)

            return TerraformState.from_dict(
                self._states[workspace].to_dict()
            )

    def write(
        self,
        workspace: str,
        state: TerraformState,
        expected_serial: int
    ) -> None:

        with self._mutex:
            current = self.read(workspace)

            if current.serial != expected_serial:
                raise StateConflictError(
                    "Remote state serial conflict."
                )

            if current.lineage != state.lineage:
                raise StateConflictError(
                    "Remote state lineage conflict."
                )

            if state.serial != expected_serial + 1:
                raise StateValidationError(
                    "Invalid serial transition."
                )

            state.workspace = workspace
            state.updated_at = utc_now()
            state.validate()

            snapshot = deep_copy(state.to_dict())

            self._history.setdefault(
                workspace, []
            ).append(snapshot)

            self._states[workspace] = state

    def acquire_lock(
        self,
        workspace: str,
        operation: str,
        owner: str
    ) -> StateLock:

        with self._mutex:
            if workspace in self._locks:
                existing = self._locks[workspace]

                raise StateLockError(
                    f"Remote state locked by {existing.owner}."
                )

            lock = StateLock.create(operation, owner)
            self._locks[workspace] = lock

            return lock

    def release_lock(
        self,
        workspace: str,
        lock_id: str
    ) -> None:

        with self._mutex:
            existing = self._locks.get(workspace)

            if existing is None:
                raise StateLockError("Remote state is not locked.")

            if existing.lock_id != lock_id:
                raise StateLockError("Invalid lock identifier.")

            del self._locks[workspace]

    def history(self, workspace: str) -> list[dict[str, Any]]:
        with self._mutex:
            return deep_copy(
                self._history.get(workspace, [])
            )


# ============================================================
# INFRASTRUCTURE SIMULATOR
# ============================================================

class Infrastructure:

    def __init__(self):
        self.resources: dict[
            str, dict[str, Any]
        ] = {}

    def create(
        self,
        address: str,
        resource_id: str,
        attributes: dict[str, Any]
    ) -> None:

        if address in self.resources:
            raise TerraformStateError(
                f"Infrastructure resource already exists: {address}"
            )

        self.resources[address] = {
            "id": resource_id,
            "attributes": deep_copy(attributes)
        }

    def update(
        self,
        address: str,
        attributes: dict[str, Any]
    ) -> None:

        if address not in self.resources:
            raise TerraformStateError(
                f"Resource does not exist: {address}"
            )

        self.resources[address]["attributes"].update(
            deep_copy(attributes)
        )

    def delete(self, address: str) -> None:
        if address not in self.resources:
            raise TerraformStateError(
                f"Cannot delete missing resource: {address}"
            )

        del self.resources[address]

    def describe(self) -> dict[str, Any]:
        return deep_copy(self.resources)


# ============================================================
# PLAN MODEL
# ============================================================

@dataclass
class PlannedChange:
    address: str
    action: ResourceAction
    before: Optional[dict[str, Any]]
    after: Optional[dict[str, Any]]


@dataclass
class TerraformPlan:
    workspace: str
    lineage: str
    base_serial: int
    changes: list[PlannedChange]

    @property
    def has_changes(self) -> bool:
        return bool(self.changes)


# ============================================================
# TERRAFORM STATE MANAGER
# ============================================================

class TerraformStateManager:

    def __init__(
        self,
        backend: StateBackend,
        infrastructure: Infrastructure
    ):
        self.backend = backend
        self.infrastructure = infrastructure

    def plan(
        self,
        desired: dict[str, dict[str, Any]],
        workspace: str = "default"
    ) -> TerraformPlan:

        current = self.backend.read(workspace)

        changes: list[PlannedChange] = []

        current_addresses = set(current.resources)
        desired_addresses = set(desired)

        for address in sorted(
            desired_addresses - current_addresses
        ):
            changes.append(
                PlannedChange(
                    address,
                    ResourceAction.CREATE,
                    None,
                    deep_copy(desired[address])
                )
            )

        for address in sorted(
            current_addresses - desired_addresses
        ):
            changes.append(
                PlannedChange(
                    address,
                    ResourceAction.DELETE,
                    current.resources[address].to_dict(),
                    None
                )
            )

        for address in sorted(
            current_addresses & desired_addresses
        ):
            existing = current.resources[address].to_dict()
            target = desired[address]

            if (
                existing["attributes"] != target["attributes"]
                or existing["resource_id"] if False else False
            ):
                pass

            if existing["attributes"] != target["attributes"]:
                changes.append(
                    PlannedChange(
                        address,
                        ResourceAction.UPDATE,
                        existing,
                        deep_copy(target)
                    )
                )

        return TerraformPlan(
            workspace=workspace,
            lineage=current.lineage,
            base_serial=current.serial,
            changes=changes
        )

    def apply(
        self,
        plan: TerraformPlan,
        owner: str = "terraform-runner"
    ) -> TerraformState:

        lock = self.backend.acquire_lock(
            plan.workspace,
            OperationType.APPLY.value,
            owner
        )

        try:
            current = self.backend.read(plan.workspace)

            # A plan created against an older state cannot be applied.
            if (
                current.serial != plan.base_serial
                or current.lineage != plan.lineage
            ):
                raise StateConflictError(
                    "Plan is stale. Generate a new plan."
                )

            updated = TerraformState.from_dict(
                current.to_dict()
            )

            for change in plan.changes:

                if change.action == ResourceAction.CREATE:
                    desired = change.after

                    self.infrastructure.create(
                        change.address,
                        desired["id"],
                        desired["attributes"]
                    )

                    resource = TerraformResource(
                        address=change.address,
                        resource_type=desired["type"],
                        provider=desired["provider"],
                        resource_id=desired["id"],
                        attributes=deep_copy(
                            desired["attributes"]
                        ),
                        sensitive_attributes=set(
                            desired.get(
                                "sensitive_attributes", []
                            )
                        )
                    )

                    updated.resources[change.address] = resource

                elif change.action == ResourceAction.UPDATE:
                    desired = change.after

                    self.infrastructure.update(
                        change.address,
                        desired["attributes"]
                    )

                    updated.resources[
                        change.address
                    ].attributes = deep_copy(
                        desired["attributes"]
                    )

                elif change.action == ResourceAction.DELETE:
                    self.infrastructure.delete(
                        change.address
                    )

                    del updated.resources[change.address]

            if plan.changes:
                updated.serial = current.serial + 1
                self.backend.write(
                    plan.workspace,
                    updated,
                    expected_serial=current.serial
                )

            return updated

        finally:
            self.backend.release_lock(
                plan.workspace,
                lock.lock_id
            )

    def refresh(
        self,
        workspace: str = "default"
    ) -> TerraformState:

        current = self.backend.read(workspace)

        refreshed = TerraformState.from_dict(
            current.to_dict()
        )

        for address, resource in refreshed.resources.items():

            actual = self.infrastructure.resources.get(
                address
            )

            if actual is None:
                raise StateConflictError(
                    f"Infrastructure resource missing: {address}"
                )

            resource.resource_id = actual["id"]
            resource.attributes = deep_copy(
                actual["attributes"]
            )

        refreshed.serial = current.serial + 1

        lock = self.backend.acquire_lock(
            workspace,
            OperationType.REFRESH.value,
            "refresh-runner"
        )

        try:
            self.backend.write(
                workspace,
                refreshed,
                expected_serial=current.serial
            )
        finally:
            self.backend.release_lock(
                workspace,
                lock.lock_id
            )

        return refreshed

    def import_resource(
        self,
        workspace: str,
        address: str,
        resource_type: str,
        provider: str,
        resource_id: str,
        attributes: dict[str, Any]
    ) -> TerraformState:

        current = self.backend.read(workspace)

        if address in current.resources:
            raise StateConflictError(
                "Resource already exists in state."
            )

        actual = self.infrastructure.resources.get(address)

        if actual is None or actual["id"] != resource_id:
            raise StateValidationError(
                "Resource is not present in infrastructure."
            )

        lock = self.backend.acquire_lock(
            workspace,
            OperationType.IMPORT.value,
            "import-runner"
        )

        try:
            latest = self.backend.read(workspace)

            if latest.serial != current.serial:
                raise StateConflictError(
                    "State changed during import."
                )

            latest.resources[address] = TerraformResource(
                address=address,
                resource_type=resource_type,
                provider=provider,
                resource_id=resource_id,
                attributes=deep_copy(attributes)
            )

            latest.serial += 1

            self.backend.write(
                workspace,
                latest,
                expected_serial=current.serial
            )

            return latest

        finally:
            self.backend.release_lock(
                workspace,
                lock.lock_id
            )


# ============================================================
# STATE FILE BACKUP AND RECOVERY
# ============================================================

class StateBackupManager:

    @staticmethod
    def backup(
        state: TerraformState,
        backup_directory: str
    ) -> Path:

        directory = Path(backup_directory)
        directory.mkdir(
            parents=True,
            exist_ok=True
        )

        filename = (
            f"{state.workspace}-"
            f"{state.serial}-"
            f"{int(time.time())}.backup.json"
        )

        path = directory / filename

        data = state.to_dict()
        data["_integrity_checksum"] = calculate_checksum(
            data
        )

        with path.open("w", encoding="utf-8") as file:
            json.dump(data, file, indent=2)

        return path

    @staticmethod
    def recover(path: str) -> TerraformState:

        try:
            with open(path, "r", encoding="utf-8") as file:
                data = json.load(file)

            expected_checksum = data.pop(
                "_integrity_checksum"
            )

            actual_checksum = calculate_checksum(data)

            if actual_checksum != expected_checksum:
                raise StateRecoveryError(
                    "Backup checksum verification failed."
                )

            return TerraformState.from_dict(data)

        except (OSError, json.JSONDecodeError, KeyError) as exc:
            raise StateRecoveryError(
                f"Backup recovery failed: {exc}"
            ) from exc


# ============================================================
# STATE DRIFT DETECTION
# ============================================================

def detect_drift(
    state: TerraformState,
    infrastructure: Infrastructure
) -> dict[str, Any]:

    drift = {
        "missing_resources": [],
        "modified_resources": [],
        "untracked_resources": []
    }

    for address, resource in state.resources.items():

        actual = infrastructure.resources.get(address)

        if actual is None:
            drift["missing_resources"].append(address)
            continue

        if (
            resource.resource_id != actual["id"]
            or resource.attributes != actual["attributes"]
        ):
            drift["modified_resources"].append(address)

    for address in infrastructure.resources:
        if address not in state.resources:
            drift["untracked_resources"].append(address)

    return drift


# ============================================================
# WORKSPACE MANAGEMENT
# ============================================================

class WorkspaceManager:

    def __init__(self, backend: StateBackend):
        self.backend = backend
        self.workspaces = {"default"}

    def create(self, name: str) -> None:

        if not name or name == "default":
            raise StateValidationError(
                "Invalid workspace name."
            )

        if name in self.workspaces:
            raise StateValidationError(
                "Workspace already exists."
            )

        self.backend.read(name)
        self.workspaces.add(name)

    def list(self) -> list[str]:
        return sorted(self.workspaces)


# ============================================================
# OUTPUT MANAGEMENT
# ============================================================

def display_outputs(
    outputs: dict[str, dict[str, Any]]
) -> dict[str, Any]:

    visible = {}

    for name, output in outputs.items():

        value = output.get("value")
        sensitive = output.get("sensitive", False)

        visible[name] = (
            "[SENSITIVE]"
            if sensitive
            else value
        )

    return visible


# ============================================================
# DEMONSTRATION
# ============================================================

def run_demo() -> None:

    print("\nTERRAFORM STATE MANAGEMENT")
    print("=" * 65)

    with tempfile.TemporaryDirectory() as directory:

        backend = LocalStateBackend(
            os.path.join(directory, "state")
        )

        infrastructure = Infrastructure()

        manager = TerraformStateManager(
            backend,
            infrastructure
        )

        workspace_manager = WorkspaceManager(backend)

        # 1. Define infrastructure configuration.
        desired = {
            "aws_instance.application": {
                "type": "aws_instance",
                "provider": "registry.terraform.io/hashicorp/aws",
                "id": "i-application-001",
                "attributes": {
                    "instance_type": "t3.medium",
                    "region": "ap-south-1",
                    "environment": "production"
                }
            },
            "aws_s3_bucket.storage": {
                "type": "aws_s3_bucket",
                "provider": "registry.terraform.io/hashicorp/aws",
                "id": "application-storage-001",
                "attributes": {
                    "bucket": "application-storage-001",
                    "versioning": True
                }
            }
        }

        # 2. Generate initial plan.
        plan = manager.plan(desired)

        print("\nINITIAL PLAN")

        for change in plan.changes:
            print(
                change.action.value.upper(),
                change.address
            )

        # 3. Apply infrastructure changes.
        state = manager.apply(plan)

        print("\nSTATE AFTER APPLY")
        print("Lineage:", state.lineage)
        print("Serial:", state.serial)
        print("Resources:", len(state.resources))

        # 4. Add outputs.
        state.outputs = {
            "application_instance_id": {
                "value": "i-application-001",
                "sensitive": False
            },
            "database_password": {
                "value": "example-secret",
                "sensitive": True
            }
        }

        # Persist outputs as another state transition.
        lock = backend.acquire_lock(
            "default",
            "output-update",
            "demo"
        )

        try:
            previous_serial = state.serial
            state.serial += 1

            backend.write(
                "default",
                state,
                previous_serial
            )
        finally:
            backend.release_lock(
                "default",
                lock.lock_id
            )

        print("\nOUTPUTS")
        print(display_outputs(state.outputs))

        # 5. Generate backup.
        backup_path = StateBackupManager.backup(
            state,
            os.path.join(directory, "backups")
        )

        print("\nBACKUP CREATED")
        print(backup_path.name)

        # 6. Simulate infrastructure drift.
        infrastructure.update(
            "aws_instance.application",
            {"instance_type": "t3.large"}
        )

        drift = detect_drift(
            backend.read("default"),
            infrastructure
        )

        print("\nDRIFT DETECTION")
        print(json.dumps(drift, indent=2))

        # 7. Refresh state from actual infrastructure.
        refreshed = manager.refresh()

        print("\nSTATE AFTER REFRESH")
        print("Serial:", refreshed.serial)
        print(
            "Instance type:",
            refreshed.resources[
                "aws_instance.application"
            ].attributes["instance_type"]
        )

        # 8. Demonstrate workspace isolation.
        workspace_manager.create("staging")

        staging_state = backend.read("staging")

        print("\nWORKSPACES")
        print(workspace_manager.list())
        print(
            "Staging resources:",
            len(staging_state.resources)
        )

        # 9. Demonstrate lock rejection.
        lock = backend.acquire_lock(
            "default",
            "apply",
            "operator-A"
        )

        try:
            try:
                backend.acquire_lock(
                    "default",
                    "apply",
                    "operator-B"
                )
            except StateLockError as exc:
                print("\nCONCURRENT LOCK REJECTED")
                print(exc)
        finally:
            backend.release_lock(
                "default",
                lock.lock_id
            )

        # 10. Demonstrate recovery.
        recovered = StateBackupManager.recover(
            str(backup_path)
        )

        print("\nBACKUP RECOVERY")
        print("Recovered serial:", recovered.serial)
        print("Recovered lineage:", recovered.lineage)

        # 11. Demonstrate stale plan rejection.
        stale_plan = manager.plan({
            **desired,
            "aws_instance.application": {
                **desired["aws_instance.application"],
                "attributes": {
                    "instance_type": "t3.small",
                    "region": "ap-south-1",
                    "environment": "production"
                }
            }
        })

        manager.refresh()

        try:
            manager.apply(stale_plan)
        except StateConflictError as exc:
            print("\nSTALE PLAN REJECTED")
            print(exc)

        print("\nDEMONSTRATION COMPLETED")


# ============================================================
# UNIT-STYLE ASSERTIONS
# ============================================================

def run_tests() -> None:

    resource = TerraformResource(
        address="aws_instance.test",
        resource_type="aws_instance",
        provider="hashicorp/aws",
        resource_id="i-test",
        attributes={"instance_type": "t3.micro"}
    )

    resource.validate()

    state = TerraformState(
        resources={resource.address: resource}
    )

    restored = TerraformState.from_dict(
        state.to_dict()
    )

    assert restored.serial == 0
    assert restored.lineage == state.lineage
    assert len(restored.resources) == 1

    backend = RemoteStateBackend()

    lock = backend.acquire_lock(
        "default",
        "apply",
        "test-runner"
    )

    try:
        try:
            backend.acquire_lock(
                "default",
                "apply",
                "second-runner"
            )
            raise AssertionError(
                "Concurrent lock should have failed."
            )
        except StateLockError:
            pass
    finally:
        backend.release_lock(
            "default",
            lock.lock_id
        )

    print("All assertions passed.")


if __name__ == "__main__":
    run_tests()
    run_demo()
