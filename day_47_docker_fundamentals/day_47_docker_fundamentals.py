#!/usr/bin/env python3
"""Docker fundamentals: containers, images, registries, and architecture.

Runs without Docker or third-party Python packages. The program models image
layers, container lifecycle, registry operations, port publishing, resource
limits, and a small multi-container application. It can also inspect a real
Docker installation when the Docker CLI is available.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class DockerModelError(Exception):
    """Base exception for invalid operations in the Docker simulation."""


class ImageNotFound(DockerModelError):
    pass


class ContainerStateError(DockerModelError):
    pass


class RegistryError(DockerModelError):
    pass


@dataclass(frozen=True)
class ImageLayer:
    digest: str
    instruction: str
    size_mb: float

    def __post_init__(self) -> None:
        if not self.digest or not self.instruction:
            raise ValueError("Layer digest and instruction are required.")
        if self.size_mb < 0:
            raise ValueError("Layer size cannot be negative.")


@dataclass(frozen=True)
class Image:
    repository: str
    tag: str
    layers: tuple[ImageLayer, ...]
    entrypoint: tuple[str, ...]
    environment: tuple[tuple[str, str], ...] = ()
    created_at: str = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        if not self.repository or not self.tag:
            raise ValueError("Image repository and tag are required.")
        if not self.layers:
            raise ValueError("An image must contain at least one layer.")
        if not self.entrypoint:
            raise ValueError("An image must define an entrypoint.")

    @property
    def reference(self) -> str:
        return f"{self.repository}:{self.tag}"

    @property
    def total_size_mb(self) -> float:
        return sum(layer.size_mb for layer in self.layers)

    @property
    def unique_layer_count(self) -> int:
        return len({layer.digest for layer in self.layers})

    def to_dict(self) -> dict[str, Any]:
        return {
            "reference": self.reference,
            "layers": [asdict(layer) for layer in self.layers],
            "size_mb": self.total_size_mb,
            "entrypoint": list(self.entrypoint),
            "created_at": self.created_at,
        }


@dataclass
class Container:
    container_id: str
    name: str
    image_reference: str
    command: tuple[str, ...]
    environment: dict[str, str]
    published_ports: dict[int, int]
    memory_limit_mb: int
    status: str = "created"
    exit_code: int | None = None
    started_at: str | None = None
    logs: list[str] = field(default_factory=list)

    def record(self, message: str) -> None:
        self.logs.append(f"{utc_now()} {message}")


class ImageStore:
    """Models the daemon's local image and shared-layer storage."""

    def __init__(self) -> None:
        self.images: dict[str, Image] = {}
        self.layers: dict[str, ImageLayer] = {}

    def add(self, image: Image) -> None:
        self.images[image.reference] = image
        for layer in image.layers:
            self.layers.setdefault(layer.digest, layer)

    def get(self, reference: str) -> Image:
        try:
            return self.images[reference]
        except KeyError as exc:
            raise ImageNotFound(
                f"Image {reference!r} is not available locally."
            ) from exc

    def storage_mb(self) -> float:
        # Shared layers are counted once, not once per image tag.
        return sum(layer.size_mb for layer in self.layers.values())

    def inspect(self) -> dict[str, Any]:
        return {
            "image_count": len(self.images),
            "unique_layer_count": len(self.layers),
            "unique_layer_storage_mb": round(self.storage_mb(), 2),
            "images": [
                {
                    "reference": image.reference,
                    "size_mb": round(image.total_size_mb, 2),
                }
                for image in self.images.values()
            ],
        }


class Registry:
    """Models explicit image publication and retrieval."""

    def __init__(self, hostname: str) -> None:
        if not hostname or "/" in hostname:
            raise ValueError("Provide a registry hostname.")
        self.hostname = hostname
        self.images: dict[str, Image] = {}
        self.authenticated = False

    def login(self, credential_token: str) -> None:
        # A real client should obtain credentials from a secure credential
        # store and never print or log the token.
        if not credential_token.strip():
            raise RegistryError("Registry credentials cannot be empty.")
        self.authenticated = True

    def push(self, local_image: Image, remote_repository: str,
             tag: str) -> str:
        if not self.authenticated:
            raise RegistryError("Authenticate before pushing an image.")
        if not remote_repository or not tag:
            raise RegistryError("Remote repository and tag are required.")
        remote_ref = f"{self.hostname}/{remote_repository}:{tag}"
        self.images[remote_ref] = Image(
            repository=f"{self.hostname}/{remote_repository}",
            tag=tag,
            layers=local_image.layers,
            entrypoint=local_image.entrypoint,
            environment=local_image.environment,
        )
        return remote_ref

    def pull(self, remote_reference: str, local_store: ImageStore) -> Image:
        try:
            remote_image = self.images[remote_reference]
        except KeyError as exc:
            raise RegistryError(
                f"Remote image {remote_reference!r} does not exist."
            ) from exc

        local_image = Image(
            repository=remote_image.repository,
            tag=remote_image.tag,
            layers=remote_image.layers,
            entrypoint=remote_image.entrypoint,
            environment=remote_image.environment,
        )
        local_store.add(local_image)
        return local_image


class DockerDaemon:
    """Models container creation, state transitions, and host resources."""

    VALID_STATES = {"created", "running", "stopped", "removed"}

    def __init__(self, memory_capacity_mb: int = 4096) -> None:
        if memory_capacity_mb <= 0:
            raise ValueError("Memory capacity must be positive.")
        self.memory_capacity_mb = memory_capacity_mb
        self.image_store = ImageStore()
        self.containers: dict[str, Container] = {}
        self.used_host_ports: dict[int, str] = {}
        self.next_id = 1

    def create_container(
        self,
        image_reference: str,
        name: str,
        command: tuple[str, ...] | None = None,
        environment: dict[str, str] | None = None,
        published_ports: dict[int, int] | None = None,
        memory_limit_mb: int = 256,
    ) -> Container:
        image = self.image_store.get(image_reference)

        if not name or any(c.name == name for c in self.containers.values()
                           if c.status != "removed"):
            raise DockerModelError(f"Invalid or duplicate container name: {name}")
        if memory_limit_mb <= 0:
            raise DockerModelError("Memory limit must be positive.")
        if memory_limit_mb > self.memory_capacity_mb:
            raise DockerModelError("Container limit exceeds host capacity.")

        ports = dict(published_ports or {})
        for container_port, host_port in ports.items():
            if not (1 <= container_port <= 65535 and
                    1 <= host_port <= 65535):
                raise DockerModelError("Ports must be between 1 and 65535.")
            if host_port in self.used_host_ports:
                raise DockerModelError(
                    f"Host port {host_port} is already allocated."
                )

        env = dict(image.environment)
        env.update(environment or {})

        container = Container(
            container_id=f"{self.next_id:012x}",
            name=name,
            image_reference=image_reference,
            command=command if command is not None else image.entrypoint,
            environment=env,
            published_ports=ports,
            memory_limit_mb=memory_limit_mb,
        )
        self.next_id += 1
        container.record("Container created.")
        self.containers[container.container_id] = container

        for host_port in ports.values():
            self.used_host_ports[host_port] = container.container_id

        return container

    def _get(self, container_id: str) -> Container:
        try:
            return self.containers[container_id]
        except KeyError as exc:
            raise ContainerStateError("Unknown container ID.") from exc

    def start(self, container_id: str) -> Container:
        container = self._get(container_id)
        if container.status not in {"created", "stopped"}:
            raise ContainerStateError(
                f"Cannot start a container in state {container.status}."
            )
        container.status = "running"
        container.exit_code = None
        container.started_at = utc_now()
        container.record(f"Started with command {container.command!r}.")
        return container

    def stop(self, container_id: str, exit_code: int = 0) -> None:
        container = self._get(container_id)
        if container.status != "running":
            raise ContainerStateError("Only running containers can be stopped.")
        container.status = "stopped"
        container.exit_code = exit_code
        container.record(f"Stopped with exit code {exit_code}.")

    def remove(self, container_id: str) -> None:
        container = self._get(container_id)
        if container.status == "running":
            raise ContainerStateError(
                "Stop the container before removing it."
            )
        if container.status == "removed":
            raise ContainerStateError("Container is already removed.")

        for host_port in container.published_ports.values():
            self.used_host_ports.pop(host_port, None)

        container.status = "removed"
        container.record("Container removed; image remains available.")

    def logs(self, container_id: str) -> list[str]:
        return list(self._get(container_id).logs)

    def list_containers(self) -> list[dict[str, Any]]:
        return [
            {
                "id": c.container_id,
                "name": c.name,
                "image": c.image_reference,
                "status": c.status,
                "ports": c.published_ports,
                "memory_limit_mb": c.memory_limit_mb,
                "exit_code": c.exit_code,
            }
            for c in self.containers.values()
            if c.status != "removed"
        ]

    def used_memory_limit_mb(self) -> int:
        # This is configured capacity, not a measurement of actual memory use.
        return sum(
            c.memory_limit_mb
            for c in self.containers.values()
            if c.status == "running"
        )


def build_sample_images() -> tuple[Image, Image]:
    # Image layers are content-addressed. Images can reuse an identical layer.
    runtime = ImageLayer("sha256:runtime-a", "Python runtime", 80)
    dependencies = ImageLayer(
        "sha256:dependencies-a", "Install locked dependencies", 35
    )
    application = ImageLayer(
        "sha256:application-a", "Copy application source", 8
    )
    frontend_runtime = ImageLayer(
        "sha256:frontend-a", "Static web server runtime", 24
    )
    frontend_assets = ImageLayer(
        "sha256:frontend-assets-a", "Copy built web assets", 12
    )

    api_image = Image(
        repository="inventory-api",
        tag="1.0.0",
        layers=(runtime, dependencies, application),
        entrypoint=("python", "-m", "http.server", "8000"),
        environment=(("APP_MODE", "production"),),
    )
    web_image = Image(
        repository="inventory-web",
        tag="1.0.0",
        layers=(frontend_runtime, frontend_assets),
        entrypoint=("web-server", "--port", "8080"),
    )
    return api_image, web_image


def demonstrate_workflow() -> None:
    print("\n=== Image layers and local storage ===")
    daemon = DockerDaemon(memory_capacity_mb=2048)
    api_image, web_image = build_sample_images()
    daemon.image_store.add(api_image)
    daemon.image_store.add(web_image)

    print(json.dumps(daemon.image_store.inspect(), indent=2))
    print(
        "API image size:",
        f"{api_image.total_size_mb:.1f} MB",
        "| unique layers:",
        api_image.unique_layer_count,
    )

    print("\n=== Registry publication and retrieval ===")
    registry = Registry("registry.example.com")
    try:
        registry.push(api_image, "platform/inventory-api", "1.0.0")
    except RegistryError as exc:
        print("Expected unauthenticated push failure:", exc)

    registry.login("simulation-token")
    remote_ref = registry.push(
        api_image, "platform/inventory-api", "1.0.0"
    )
    print("Published:", remote_ref)

    deployment_store = ImageStore()
    pulled = registry.pull(remote_ref, deployment_store)
    print("Pulled:", pulled.reference)

    print("\n=== Container lifecycle and port publishing ===")
    api = daemon.create_container(
        api_image.reference,
        "inventory-api",
        published_ports={8000: 18000},
        environment={"LOG_LEVEL": "INFO"},
        memory_limit_mb=512,
    )
    daemon.start(api.container_id)
    print("Running API:", api.name, api.published_ports)

    try:
        daemon.create_container(
            web_image.reference,
            "conflicting-web",
            published_ports={8080: 18000},
            memory_limit_mb=256,
        )
    except DockerModelError as exc:
        print("Expected port conflict:", exc)

    web = daemon.create_container(
        web_image.reference,
        "inventory-web",
        published_ports={8080: 18080},
        memory_limit_mb=256,
    )
    daemon.start(web.container_id)

    print("Containers:")
    print(json.dumps(daemon.list_containers(), indent=2))
    print("Configured running memory limits:",
          daemon.used_memory_limit_mb(), "MB")

    try:
        daemon.remove(api.container_id)
    except ContainerStateError as exc:
        print("Expected removal failure:", exc)

    daemon.stop(api.container_id)
    daemon.remove(api.container_id)
    print("API container removed; image still exists:",
          daemon.image_store.get(api_image.reference).reference)

    print("\n=== State and resource edge cases ===")
    try:
        daemon.start(api.container_id)
        print("Stopped container can be restarted before removal.")
        daemon.stop(api.container_id)
    except ContainerStateError as exc:
        print("Expected state failure:", exc)

    try:
        daemon.create_container(
            web_image.reference,
            "oversized-service",
            memory_limit_mb=4096,
        )
    except DockerModelError as exc:
        print("Expected resource validation failure:", exc)

    print("\n=== Container logs ===")
    print("\n".join(daemon.logs(web.container_id)))


def inspect_real_docker() -> None:
    """Use the real Docker CLI when installed; never require it for the demo."""
    docker = shutil.which("docker")
    print("\n=== Real Docker environment ===")
    if docker is None:
        print("Docker CLI is unavailable; the simulation ran independently.")
        return

    try:
        result = subprocess.run(
            [docker, "version", "--format", "{{json .Server}}"],
            capture_output=True,
            text=True,
            timeout=8,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print("Could not query the Docker daemon:", exc)
        return

    if result.returncode != 0:
        print("Docker CLI exists, but the daemon may not be running.")
        print(result.stderr.strip())
        return

    print("Docker server information:")
    try:
        print(json.dumps(json.loads(result.stdout), indent=2))
    except json.JSONDecodeError:
        print(result.stdout.strip())

    # Listing containers is read-only. The program does not pull images,
    # start workloads, delete resources, or modify the Docker host.
    listing = subprocess.run(
        [docker, "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"],
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )
    if listing.returncode == 0:
        print("Running containers:")
        print(listing.stdout.strip() or "(none)")
    else:
        print("Container listing failed:", listing.stderr.strip())


def main() -> None:
    demonstrate_workflow()
    inspect_real_docker()


if __name__ == "__main__":
    main()
