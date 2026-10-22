#!/usr/bin/env python3
"""
Docker volume storage model.

This executable models the three common Docker storage approaches:
- named volumes
- bind mounts
- ephemeral container storage

It demonstrates lifecycle, persistence, isolation, mount validation,
backup/restore, and cleanup behavior without requiring Docker itself.
The model is intentionally explicit so storage semantics can be tested
without modifying the host filesystem.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath
from typing import Dict, Iterable
import copy
import json
import re


class StorageType(str, Enum):
    NAMED_VOLUME = "named_volume"
    BIND_MOUNT = "bind_mount"
    EPHEMERAL = "ephemeral"


class StorageError(Exception):
    """Base exception for storage-model failures."""


class ValidationError(StorageError):
    """Raised when a storage configuration is invalid."""


class MountConflictError(StorageError):
    """Raised when a container receives conflicting mounts."""


class NotFoundError(StorageError):
    """Raised when a requested storage object does not exist."""


@dataclass
class NamedVolume:
    name: str
    data: Dict[str, str] = field(default_factory=dict)
    attached_containers: set[str] = field(default_factory=set)


@dataclass
class BindMount:
    host_path: str
    data: Dict[str, str] = field(default_factory=dict)
    read_only: bool = False


@dataclass
class Mount:
    source: str
    destination: str
    storage_type: StorageType
    read_only: bool = False


@dataclass
class Container:
    container_id: str
    mounts: list[Mount] = field(default_factory=list)
    ephemeral_data: Dict[str, str] = field(default_factory=dict)
    running: bool = False


class DockerStorageModel:
    """
    A small in-memory storage engine that mirrors important Docker
    persistence semantics.

    Named volume:
        Data is owned independently of a container and survives removal.

    Bind mount:
        Data belongs to the host path and therefore survives container
        removal, but its lifecycle is tied to the host filesystem.

    Ephemeral storage:
        Data belongs to the container writable layer and disappears when
        the container is removed.
    """

    _NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,62}$")

    def __init__(self) -> None:
        self.volumes: dict[str, NamedVolume] = {}
        self.bind_mounts: dict[str, BindMount] = {}
        self.containers: dict[str, Container] = {}

    def create_named_volume(self, name: str) -> None:
        self._validate_name(name)
        if name in self.volumes:
            raise ValidationError(f"Named volume already exists: {name}")
        self.volumes[name] = NamedVolume(name=name)

    def create_bind_mount(
        self,
        host_path: str,
        initial_data: Dict[str, str] | None = None,
        read_only: bool = False,
    ) -> None:
        path = self._normalize_host_path(host_path)
        if path in self.bind_mounts:
            raise ValidationError(f"Bind mount already exists: {path}")
        self.bind_mounts[path] = BindMount(
            host_path=path,
            data=dict(initial_data or {}),
            read_only=read_only,
        )

    def create_container(self, container_id: str) -> None:
        self._validate_name(container_id)
        if container_id in self.containers:
            raise ValidationError(f"Container already exists: {container_id}")
        self.containers[container_id] = Container(container_id=container_id)

    def start_container(self, container_id: str) -> None:
        container = self._container(container_id)
        if not container.mounts and container.running:
            return
        container.running = True

    def stop_container(self, container_id: str) -> None:
        self._container(container_id).running = False

    def remove_container(self, container_id: str) -> None:
        container = self._container(container_id)

        for mount in container.mounts:
            if mount.storage_type == StorageType.NAMED_VOLUME:
                volume = self._volume(mount.source)
                volume.attached_containers.discard(container_id)

        del self.containers[container_id]

    def attach_named_volume(
        self,
        container_id: str,
        volume_name: str,
        destination: str,
        read_only: bool = False,
    ) -> None:
        volume = self._volume(volume_name)
        container = self._container(container_id)
        self._add_mount(
            container,
            Mount(
                source=volume_name,
                destination=self._normalize_destination(destination),
                storage_type=StorageType.NAMED_VOLUME,
                read_only=read_only,
            ),
        )
        volume.attached_containers.add(container_id)

    def attach_bind_mount(
        self,
        container_id: str,
        host_path: str,
        destination: str,
        read_only: bool = False,
    ) -> None:
        path = self._normalize_host_path(host_path)
        if path not in self.bind_mounts:
            raise NotFoundError(f"Host path is not registered: {path}")

        container = self._container(container_id)
        self._add_mount(
            container,
            Mount(
                source=path,
                destination=self._normalize_destination(destination),
                storage_type=StorageType.BIND_MOUNT,
                read_only=read_only,
            ),
        )

    def write(self, container_id: str, path: str, value: str) -> None:
        container = self._container(container_id)
        mount = self._resolve_mount(container, path)

        if mount is None:
            container.ephemeral_data[self._relative_path(path)] = value
            return

        if mount.read_only:
            raise StorageError(
                f"Cannot write through read-only mount at {mount.destination}"
            )

        target = self._storage_for_mount(mount)
        target[self._relative_path(path, mount.destination)] = value

    def read(self, container_id: str, path: str) -> str:
        container = self._container(container_id)
        mount = self._resolve_mount(container, path)

        if mount is None:
            key = self._relative_path(path)
            if key not in container.ephemeral_data:
                raise NotFoundError(f"Ephemeral file not found: {path}")
            return container.ephemeral_data[key]

        target = self._storage_for_mount(mount)
        key = self._relative_path(path, mount.destination)
        if key not in target:
            raise NotFoundError(f"Stored file not found: {path}")
        return target[key]

    def backup_volume(self, volume_name: str) -> dict[str, str]:
        volume = self._volume(volume_name)
        return copy.deepcopy(volume.data)

    def restore_volume(self, volume_name: str, backup: dict[str, str]) -> None:
        volume = self._volume(volume_name)
        if not isinstance(backup, dict):
            raise ValidationError("Backup must be a dictionary")
        volume.data = {str(k): str(v) for k, v in backup.items()}

    def remove_named_volume(self, volume_name: str, force: bool = False) -> None:
        volume = self._volume(volume_name)
        if volume.attached_containers and not force:
            attached = ", ".join(sorted(volume.attached_containers))
            raise StorageError(
                f"Volume {volume_name!r} is still attached to: {attached}"
            )

        if force:
            for container_id in list(volume.attached_containers):
                container = self._container(container_id)
                container.mounts = [
                    m
                    for m in container.mounts
                    if not (
                        m.storage_type == StorageType.NAMED_VOLUME
                        and m.source == volume_name
                    )
                ]
            volume.attached_containers.clear()

        del self.volumes[volume_name]

    def inspect(self) -> dict:
        return {
            "volumes": {
                name: {
                    "data": dict(volume.data),
                    "attached_containers": sorted(
                        volume.attached_containers
                    ),
                }
                for name, volume in self.volumes.items()
            },
            "bind_mounts": {
                path: {
                    "data": dict(bind.data),
                    "read_only": bind.read_only,
                }
                for path, bind in self.bind_mounts.items()
            },
            "containers": {
                cid: {
                    "running": container.running,
                    "ephemeral_data": dict(container.ephemeral_data),
                    "mounts": [
                        {
                            "source": mount.source,
                            "destination": mount.destination,
                            "type": mount.storage_type.value,
                            "read_only": mount.read_only,
                        }
                        for mount in container.mounts
                    ],
                }
                for cid, container in self.containers.items()
            },
        }

    def _add_mount(self, container: Container, mount: Mount) -> None:
        for existing in container.mounts:
            if existing.destination == mount.destination:
                raise MountConflictError(
                    f"Destination already mounted: {mount.destination}"
                )
        container.mounts.append(mount)

    def _resolve_mount(
        self,
        container: Container,
        path: str,
    ) -> Mount | None:
        normalized = self._normalize_destination(path)
        candidates = [
            mount
            for mount in container.mounts
            if normalized == mount.destination
            or normalized.startswith(mount.destination.rstrip("/") + "/")
        ]

        if not candidates:
            return None

        return max(candidates, key=lambda mount: len(mount.destination))

    def _storage_for_mount(self, mount: Mount) -> Dict[str, str]:
        if mount.storage_type == StorageType.NAMED_VOLUME:
            return self._volume(mount.source).data
        if mount.storage_type == StorageType.BIND_MOUNT:
            return self.bind_mounts[mount.source].data
        raise StorageError("Ephemeral storage has no external mount target")

    def _relative_path(
        self,
        path: str,
        base: str = "/",
    ) -> str:
        normalized_path = self._normalize_destination(path)
        normalized_base = self._normalize_destination(base)

        if normalized_base == "/":
            relative = normalized_path.lstrip("/")
        else:
            relative = normalized_path[len(normalized_base):].lstrip("/")

        return relative or "."

    @classmethod
    def _normalize_destination(cls, path: str) -> str:
        if not isinstance(path, str) or not path.startswith("/"):
            raise ValidationError(
                f"Container path must be absolute: {path!r}"
            )

        normalized = str(PurePosixPath(path))
        if ".." in PurePosixPath(normalized).parts:
            raise ValidationError("Parent traversal is not permitted")

        return normalized

    @staticmethod
    def _normalize_host_path(path: str) -> str:
        if not isinstance(path, str) or not path.strip():
            raise ValidationError("Host path cannot be empty")
        return path.rstrip("/") or "/"

    @classmethod
    def _validate_name(cls, name: str) -> None:
        if not isinstance(name, str) or not cls._NAME_PATTERN.fullmatch(name):
            raise ValidationError(
                f"Invalid storage/container name: {name!r}"
            )

    def _container(self, container_id: str) -> Container:
        if container_id not in self.containers:
            raise NotFoundError(f"Container not found: {container_id}")
        return self.containers[container_id]

    def _volume(self, name: str) -> NamedVolume:
        if name not in self.volumes:
            raise NotFoundError(f"Named volume not found: {name}")
        return self.volumes[name]


def demonstrate_named_volume_persistence(storage: DockerStorageModel) -> None:
    storage.create_named_volume("orders-db")
    storage.create_container("orders-v1")
    storage.attach_named_volume("orders-v1", "orders-db", "/var/lib/orders")
    storage.start_container("orders-v1")
    storage.write("orders-v1", "/var/lib/orders/orders.json", '{"count": 42}')
    storage.stop_container("orders-v1")
    storage.remove_container("orders-v1")

    storage.create_container("orders-v2")
    storage.attach_named_volume("orders-v2", "orders-db", "/var/lib/orders")
    recovered = storage.read("orders-v2", "/var/lib/orders/orders.json")

    assert recovered == '{"count": 42}'
    print("Named volume persisted:", recovered)


def demonstrate_bind_mount(storage: DockerStorageModel) -> None:
    storage.create_bind_mount(
        "/srv/application/config",
        {"application.conf": "log_level=INFO"},
    )
    storage.create_container("config-reader")
    storage.attach_bind_mount(
        "config-reader",
        "/srv/application/config",
        "/etc/application",
        read_only=True,
    )

    value = storage.read(
        "config-reader",
        "/etc/application/application.conf",
    )
    assert value == "log_level=INFO"

    try:
        storage.write(
            "config-reader",
            "/etc/application/application.conf",
            "log_level=DEBUG",
        )
    except StorageError as exc:
        print("Read-only bind mount rejected write:", exc)


def demonstrate_ephemeral_storage(storage: DockerStorageModel) -> None:
    storage.create_container("temporary-worker")
    storage.write("temporary-worker", "/tmp/result.txt", "temporary result")
    assert storage.read("temporary-worker", "/tmp/result.txt") == "temporary result"
    storage.remove_container("temporary-worker")

    storage.create_container("replacement-worker")
    try:
        storage.read("replacement-worker", "/tmp/result.txt")
    except NotFoundError as exc:
        print("Ephemeral data disappeared with container:", exc)


def demonstrate_backup_restore(storage: DockerStorageModel) -> None:
    backup = storage.backup_volume("orders-db")
    backup["orders.json"] = '{"count": 100}'
    storage.restore_volume("orders-db", backup)

    storage.create_container("backup-verifier")
    storage.attach_named_volume(
        "backup-verifier",
        "orders-db",
        "/data",
    )
    assert storage.read("backup-verifier", "/data/orders.json") == (
        '{"count": 100}'
    )
    print("Volume restore succeeded.")


def main() -> None:
    storage = DockerStorageModel()

    demonstrate_named_volume_persistence(storage)
    demonstrate_bind_mount(storage)
    demonstrate_ephemeral_storage(storage)
    demonstrate_backup_restore(storage)

    print("\nStorage inventory:")
    print(json.dumps(storage.inspect(), indent=2))

    try:
        storage.create_container("unsafe")
        storage.attach_bind_mount(
            "unsafe",
            "/srv/application/config",
            "/etc/config",
        )
        storage.attach_named_volume(
            "unsafe",
            "orders-db",
            "/etc/config",
        )
    except MountConflictError as exc:
        print("\nMount conflict correctly rejected:", exc)

    print("\nProduction considerations:")
    print("- Named volumes should be backed up independently of containers.")
    print("- Bind mounts expose host paths and require strict path permissions.")
    print("- Read-only mounts reduce accidental mutation.")
    print("- Container writable layers are unsuitable for durable application data.")
    print("- Volume removal should be blocked while containers still depend on it.")


if __name__ == "__main__":
    main()
