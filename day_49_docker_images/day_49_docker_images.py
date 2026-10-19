#!/usr/bin/env python3
"""
Docker image laboratory: layers, caching, tags, and lifecycle.

This script models Docker image behavior locally without requiring a Docker
daemon. It also inspects real Docker metadata when the Docker CLI is
available, making the distinction between an educational model and an actual
Docker engine observable.

The model represents:
- immutable content-addressed image layers
- parent/child layer relationships
- cache reuse based on instruction and input fingerprints
- mutable tags pointing at image identities
- image creation, tagging, promotion, retirement, and garbage collection
- multi-stage builds
- image-size accounting
- common cache invalidation causes
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def short_digest(digest: str) -> str:
    return digest[:12]


@dataclass(frozen=True)
class Layer:
    digest: str
    instruction: str
    size_bytes: int
    created_at: str
    parent: str | None = None


@dataclass
class Image:
    image_id: str
    layers: tuple[str, ...]
    created_at: str
    architecture: str = "linux/amd64"
    metadata: dict[str, str] = field(default_factory=dict)

    @property
    def compressed_size(self) -> int:
        return 0


@dataclass
class CacheEntry:
    key: str
    layer_digest: str
    instruction: str


@dataclass
class BuildResult:
    image: Image
    cache_hits: int
    cache_misses: int
    new_layers: list[Layer]


class DockerImageModel:
    """
    A compact model of the parts of Docker image construction that matter for
    learning layer reuse and tag/lifecycle behavior.

    A layer digest is derived from its parent, instruction, and relevant build
    input. That mirrors the important idea behind content-addressed storage:
    changing an earlier dependency can invalidate later filesystem changes.
    """

    def __init__(self) -> None:
        self.layers: dict[str, Layer] = {}
        self.images: dict[str, Image] = {}
        self.tags: dict[str, str] = {}
        self.cache: dict[str, CacheEntry] = {}
        self.registry: dict[str, str] = {}
        self.retired_images: set[str] = set()

    def _layer(
        self,
        parent: str | None,
        instruction: str,
        input_fingerprint: str,
        size_bytes: int,
    ) -> Layer:
        payload = "|".join(
            [
                parent or "<base>",
                instruction,
                input_fingerprint,
            ]
        )
        digest = "sha256:" + sha256_text(payload)
        existing = self.layers.get(digest)
        if existing:
            return existing

        layer = Layer(
            digest=digest,
            instruction=instruction,
            size_bytes=size_bytes,
            created_at=datetime.now(timezone.utc).isoformat(),
            parent=parent,
        )
        self.layers[digest] = layer
        return layer

    def _cache_key(
        self,
        parent: str | None,
        instruction: str,
        input_fingerprint: str,
    ) -> str:
        return sha256_text(
            json.dumps(
                {
                    "parent": parent,
                    "instruction": instruction,
                    "input": input_fingerprint,
                },
                sort_keys=True,
            )
        )

    def build(
        self,
        name: str,
        instructions: Iterable[tuple[str, str, int]],
        build_inputs: dict[str, str] | None = None,
    ) -> BuildResult:
        build_inputs = build_inputs or {}
        parent: str | None = None
        selected_layers: list[str] = []
        new_layers: list[Layer] = []
        hits = 0
        misses = 0

        for instruction, input_name, size_bytes in instructions:
            input_fingerprint = build_inputs.get(input_name, "")
            key = self._cache_key(parent, instruction, input_fingerprint)
            cached = self.cache.get(key)

            if cached and cached.layer_digest in self.layers:
                layer = self.layers[cached.layer_digest]
                hits += 1
            else:
                layer = self._layer(
                    parent,
                    instruction,
                    input_fingerprint,
                    size_bytes,
                )
                self.cache[key] = CacheEntry(
                    key=key,
                    layer_digest=layer.digest,
                    instruction=instruction,
                )
                misses += 1
                new_layers.append(layer)

            selected_layers.append(layer.digest)
            parent = layer.digest

        image_id = "sha256:" + sha256_text(
            "|".join(selected_layers)
        )
        image = Image(
            image_id=image_id,
            layers=tuple(selected_layers),
            created_at=datetime.now(timezone.utc).isoformat(),
            metadata={"name": name},
        )
        self.images[image_id] = image
        self.tags[name] = image_id

        return BuildResult(
            image=image,
            cache_hits=hits,
            cache_misses=misses,
            new_layers=new_layers,
        )

    def tag(self, image_ref: str, tag: str) -> None:
        image_id = self.resolve(image_ref)
        self.tags[tag] = image_id

    def resolve(self, image_or_tag: str) -> str:
        if image_or_tag in self.images:
            return image_or_tag
        if image_or_tag in self.tags:
            return self.tags[image_or_tag]
        raise KeyError(f"Unknown image reference: {image_or_tag}")

    def push(self, image_or_tag: str, repository: str) -> None:
        image_id = self.resolve(image_or_tag)
        self.registry[repository] = image_id

    def remove_tag(self, tag: str) -> None:
        self.tags.pop(tag, None)

    def remove_image(self, image_ref: str) -> None:
        image_id = self.resolve(image_ref)
        if image_id in self.tags.values():
            raise RuntimeError(
                "Image still has a tag. Remove or retarget the tag first."
            )
        self.retired_images.add(image_id)

    def referenced_layer_digests(self) -> set[str]:
        referenced_images = set(self.tags.values()) | set(self.registry.values())
        referenced_images |= set(self.images) - self.retired_images

        result: set[str] = set()
        for image_id in referenced_images:
            image = self.images.get(image_id)
            if image:
                result.update(image.layers)
        return result

    def garbage_collect(self) -> list[str]:
        referenced = self.referenced_layer_digests()
        removed: list[str] = []

        for digest in list(self.layers):
            if digest not in referenced:
                removed.append(digest)
                del self.layers[digest]

        for image_id in list(self.retired_images):
            if image_id not in self.tags.values():
                self.images.pop(image_id, None)
                self.retired_images.remove(image_id)

        return removed

    def layer_sizes(self, image_ref: str) -> list[tuple[str, int, str]]:
        image_id = self.resolve(image_ref)
        image = self.images[image_id]
        return [
            (
                short_digest(digest),
                self.layers[digest].size_bytes,
                self.layers[digest].instruction,
            )
            for digest in image.layers
        ]

    def image_size(self, image_ref: str) -> int:
        return sum(size for _, size, _ in self.layer_sizes(image_ref))


def print_bytes(value: int) -> str:
    units = ["B", "KiB", "MiB", "GiB"]
    amount = float(value)
    for unit in units:
        if amount < 1024 or unit == units[-1]:
            return f"{amount:.1f} {unit}"
        amount /= 1024
    return f"{value} B"


def demonstrate_layered_builds() -> None:
    model = DockerImageModel()

    common_inputs = {
        "base": "python:3.13-slim@sha256:base-image",
        "requirements": (
            "fastapi==0.116.1\n"
            "uvicorn==0.35.0\n"
        ),
        "application": (
            "app/main.py:v1\n"
            "app/routes.py:v1\n"
        ),
    }

    instructions = [
        (
            "FROM python:3.13-slim",
            "base",
            28 * 1024 * 1024,
        ),
        (
            "RUN python -m pip install --no-cache-dir -r requirements.txt",
            "requirements",
            7 * 1024 * 1024,
        ),
        (
            "COPY app/ /app/",
            "application",
            80 * 1024,
        ),
        (
            "CMD [\"python\", \"-m\", \"app.main\"]",
            "application",
            1024,
        ),
    ]

    first = model.build("inventory-api:1.0", instructions, common_inputs)

    print("=== Initial build ===")
    print(f"image: {short_digest(first.image.image_id)}")
    print(f"cache hits: {first.cache_hits}")
    print(f"cache misses: {first.cache_misses}")
    print(f"image size: {print_bytes(model.image_size('inventory-api:1.0'))}")

    second = model.build("inventory-api:1.0-rebuild", instructions, common_inputs)

    print("\n=== Identical rebuild ===")
    print(f"cache hits: {second.cache_hits}")
    print(f"cache misses: {second.cache_misses}")

    changed_application = dict(common_inputs)
    changed_application["application"] = (
        "app/main.py:v2\n"
        "app/routes.py:v1\n"
    )

    third = model.build(
        "inventory-api:1.1",
        instructions,
        changed_application,
    )

    print("\n=== Application-only change ===")
    print(f"cache hits: {third.cache_hits}")
    print(f"cache misses: {third.cache_misses}")
    print("Changed source invalidates the COPY layer and later layers.")

    changed_requirements = dict(changed_application)
    changed_requirements["requirements"] += "httpx==0.28.1\n"

    fourth = model.build(
        "inventory-api:1.2",
        instructions,
        changed_requirements,
    )

    print("\n=== Dependency change ===")
    print(f"cache hits: {fourth.cache_hits}")
    print(f"cache misses: {fourth.cache_misses}")
    print(
        "A changed dependency input invalidates the dependency-install layer "
        "and every layer constructed after it."
    )

    print("\n=== Layers in inventory-api:1.2 ===")
    for digest, size, instruction in model.layer_sizes("inventory-api:1.2"):
        print(
            f"{digest:14} {print_bytes(size):>10}  {instruction}"
        )

    model.tag("inventory-api:1.2", "inventory-api:stable")
    model.tag("inventory-api:1.2", "inventory-api:production")
    model.push("inventory-api:production", "registry.example.com/inventory-api")

    print("\n=== Tag and registry state ===")
    print(
        "stable ->",
        short_digest(model.resolve("inventory-api:stable")),
    )
    print(
        "production ->",
        short_digest(model.resolve("inventory-api:production")),
    )
    print(
        "registry ->",
        short_digest(
            model.registry["registry.example.com/inventory-api"]
        ),
    )

    model.tag("inventory-api:1.1", "inventory-api:stable")
    print(
        "stable moved to ->",
        short_digest(model.resolve("inventory-api:stable")),
    )

    model.remove_tag("inventory-api:1.0")
    model.remove_tag("inventory-api:1.0-rebuild")

    print("\n=== Lifecycle ===")
    print(
        "An image ID identifies content; a tag is a movable human-readable "
        "reference."
    )

    for image_id in list(model.images):
        if image_id not in model.tags.values():
            model.retired_images.add(image_id)

    removed_layers = model.garbage_collect()
    print(f"garbage-collected unreferenced layers: {len(removed_layers)}")


def demonstrate_multi_stage_build() -> None:
    model = DockerImageModel()

    build_inputs = {
        "builder": "go.mod:v1|go.sum:v1|cmd/api:v1",
        "runtime": "dist/api:v1",
    }

    builder = model.build(
        "orders-builder:temporary",
        [
            (
                "FROM golang:1.25-alpine AS builder",
                "builder",
                320 * 1024 * 1024,
            ),
            (
                "RUN go build -o /out/orders ./cmd/api",
                "builder",
                14 * 1024 * 1024,
            ),
        ],
        build_inputs,
    )

    runtime = model.build(
        "orders-api:1.0",
        [
            (
                "FROM gcr.io/distroless/static-debian12",
                "runtime",
                12 * 1024 * 1024,
            ),
            (
                "COPY --from=builder /out/orders /orders",
                "runtime",
                8 * 1024 * 1024,
            ),
        ],
        build_inputs,
    )

    print("\n=== Multi-stage build model ===")
    print(
        f"builder image represented layers: "
        f"{len(builder.image.layers)}"
    )
    print(
        f"runtime image represented layers: "
        f"{len(runtime.image.layers)}"
    )
    print(
        "The final runtime image does not need to contain the complete "
        "builder filesystem."
    )


def demonstrate_cache_ordering() -> None:
    model = DockerImageModel()

    inputs = {
        "requirements": "requirements:v1",
        "application": "application:v1",
    }

    dependency_first = [
        ("FROM python:3.13-slim", "base", 28 * 1024 * 1024),
        (
            "COPY requirements.txt /app/requirements.txt",
            "requirements",
            4096,
        ),
        (
            "RUN pip install --no-cache-dir -r /app/requirements.txt",
            "requirements",
            7 * 1024 * 1024,
        ),
        ("COPY app/ /app/", "application", 80 * 1024),
    ]

    dependency_late = [
        ("FROM python:3.13-slim", "base", 28 * 1024 * 1024),
        ("COPY app/ /app/", "application", 80 * 1024),
        (
            "COPY requirements.txt /app/requirements.txt",
            "requirements",
            4096,
        ),
        (
            "RUN pip install --no-cache-dir -r /app/requirements.txt",
            "requirements",
            7 * 1024 * 1024,
        ),
    ]

    first = model.build("good-cache:v1", dependency_first, inputs)

    changed = dict(inputs)
    changed["application"] = "application:v2"
    second = model.build("good-cache:v2", dependency_first, changed)

    print("\n=== Cache-friendly instruction ordering ===")
    print(
        "Dependency-first build after application change:",
        f"{second.cache_hits} cache hits, {second.cache_misses} misses",
    )

    model2 = DockerImageModel()
    model2.build("poor-cache:v1", dependency_late, inputs)
    second_poor = model2.build("poor-cache:v2", dependency_late, changed)

    print(
        "Application-first build after application change:",
        f"{second_poor.cache_hits} cache hits, "
        f"{second_poor.cache_misses} misses",
    )
    print(
        "The difference illustrates why stable, expensive dependency "
        "steps are normally placed before frequently changing source files."
    )


def inspect_real_docker() -> None:
    docker = shutil.which("docker")
    print("\n=== Docker CLI inspection ===")

    if not docker:
        print("Docker CLI is not installed or is not available on PATH.")
        return

    try:
        version = subprocess.run(
            [docker, "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        if version.returncode != 0:
            print("Docker CLI exists, but the Docker daemon is unavailable.")
            print(version.stderr.strip())
            return

        print(f"Docker Engine: {version.stdout.strip()}")

        result = subprocess.run(
            [
                docker,
                "image",
                "inspect",
                "python:3.13-slim",
                "--format",
                "{{.Id}}|{{.Size}}|{{json .RootFS.Layers}}",
            ],
            capture_output=True,
            text=True,
            timeout=20,
            check=False,
        )

        if result.returncode != 0:
            print(
                "python:3.13-slim is not available locally. "
                "Pull it before using this inspection example."
            )
            return

        parts = result.stdout.strip().split("|", maxsplit=2)
        if len(parts) == 3:
            image_id, size, layers = parts
            print(f"image id: {image_id}")
            print(f"reported size: {print_bytes(int(size))}")
            print(f"layer metadata: {layers}")

    except subprocess.TimeoutExpired:
        print("Docker inspection timed out.")
    except ValueError:
        print("Docker returned unexpected image-size metadata.")
    except OSError as exc:
        print(f"Could not execute Docker: {exc}")


def demonstrate_validation() -> None:
    model = DockerImageModel()

    print("\n=== Lifecycle validation ===")

    try:
        model.resolve("missing-image:latest")
    except KeyError as exc:
        print(f"Invalid reference rejected: {exc}")

    result = model.build(
        "audit-service:1.0",
        [
            ("FROM debian:13-slim", "base", 25 * 1024 * 1024),
            ("COPY service/ /service/", "service", 200 * 1024),
        ],
        {"base": "debian-13-slim-digest", "service": "service-v1"},
    )

    model.tag(result.image.image_id, "audit-service:stable")

    try:
        model.remove_image(result.image.image_id)
    except RuntimeError as exc:
        print(f"Tagged image cannot be retired directly: {exc}")

    model.remove_tag("audit-service:stable")
    model.remove_image(result.image.image_id)
    print("Image retired after its tag was removed.")


def main() -> None:
    print("Docker Image Technical Laboratory")
    print("=" * 36)
    demonstrate_layered_builds()
    demonstrate_multi_stage_build()
    demonstrate_cache_ordering()
    demonstrate_validation()
    inspect_real_docker()


if __name__ == "__main__":
    main()
