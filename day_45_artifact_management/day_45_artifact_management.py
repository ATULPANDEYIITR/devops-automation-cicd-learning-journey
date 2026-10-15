#!/usr/bin/env python3
"""Artifact management, versioning, immutability, and repository governance.

Standard-library-only implementation of a content-addressed artifact repository.
Run with: python artifact_management.py
"""

from __future__ import annotations

import hashlib
import json
import re
import tempfile
import unittest
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ARTIFACT_NAME_PATTERN = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}$")
VERSION_PATTERN = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)"
    r"(?:-([0-9A-Za-z.-]+))?(?:\+([0-9A-Za-z.-]+))?$"
)
SHA256_PATTERN = re.compile(r"^[a-f0-9]{64}$")


class ArtifactError(Exception):
    """Base exception for artifact repository operations."""


class ValidationError(ArtifactError):
    """Raised when artifact metadata or input violates repository rules."""


class ArtifactNotFoundError(ArtifactError):
    """Raised when an artifact or version does not exist."""


class ImmutableArtifactError(ArtifactError):
    """Raised when an operation attempts to mutate immutable content."""


class IntegrityError(ArtifactError):
    """Raised when stored content does not match its recorded digest."""


@dataclass(frozen=True, order=True)
class SemanticVersion:
    """Semantic version value with explicit prerelease handling."""

    major: int
    minor: int
    patch: int
    prerelease: str = field(default="", compare=False)
    build: str = field(default="", compare=False)

    @classmethod
    def parse(cls, value: str) -> "SemanticVersion":
        match = VERSION_PATTERN.fullmatch(value)
        if not match:
            raise ValidationError(f"Invalid semantic version: {value!r}")

        major, minor, patch, prerelease, build = match.groups()

        if prerelease:
            for identifier in prerelease.split("."):
                if not identifier:
                    raise ValidationError("Prerelease identifiers cannot be empty.")
                if identifier.isdigit() and len(identifier) > 1 and identifier[0] == "0":
                    raise ValidationError(
                        "Numeric prerelease identifiers cannot contain leading zeroes."
                    )

        return cls(
            major=int(major),
            minor=int(minor),
            patch=int(patch),
            prerelease=prerelease or "",
            build=build or "",
        )

    def __str__(self) -> str:
        value = f"{self.major}.{self.minor}.{self.patch}"
        if self.prerelease:
            value += f"-{self.prerelease}"
        if self.build:
            value += f"+{self.build}"
        return value

    def precedence_key(self) -> tuple[Any, ...]:
        """Return SemVer precedence components; build metadata is ignored."""
        if not self.prerelease:
            return self.major, self.minor, self.patch, 1, ()

        identifiers = []
        for item in self.prerelease.split("."):
            if item.isdigit():
                identifiers.append((0, int(item)))
            else:
                identifiers.append((1, item))

        return self.major, self.minor, self.patch, 0, tuple(identifiers)


@dataclass(frozen=True)
class ArtifactManifest:
    """Immutable metadata associated with one published artifact version."""

    name: str
    version: str
    digest: str
    size_bytes: int
    media_type: str
    created_at: str
    publisher: str
    source_revision: str
    metadata: tuple[tuple[str, str], ...] = ()

    def validate(self) -> None:
        if not ARTIFACT_NAME_PATTERN.fullmatch(self.name):
            raise ValidationError("Artifact name contains unsupported characters.")

        SemanticVersion.parse(self.version)

        if not SHA256_PATTERN.fullmatch(self.digest):
            raise ValidationError("A lowercase SHA-256 digest is required.")

        if self.size_bytes < 0:
            raise ValidationError("Artifact size cannot be negative.")

        if not self.media_type or "/" not in self.media_type:
            raise ValidationError("Media type must have a type/subtype format.")

        if not self.publisher.strip():
            raise ValidationError("Publisher cannot be empty.")

        if not self.source_revision.strip():
            raise ValidationError("Source revision cannot be empty.")

        try:
            parsed = datetime.fromisoformat(self.created_at)
        except ValueError as exc:
            raise ValidationError("Invalid creation timestamp.") from exc

        if parsed.tzinfo is None:
            raise ValidationError("Creation timestamp must include a timezone.")

        if len({key for key, _ in self.metadata}) != len(self.metadata):
            raise ValidationError("Manifest metadata keys must be unique.")


@dataclass(frozen=True)
class StoredArtifact:
    """Manifest and immutable payload location."""

    manifest: ArtifactManifest
    blob_path: Path


class ArtifactRepository:
    """Local demonstration repository using SHA-256 content addressing."""

    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.blob_directory = self.root / "blobs" / "sha256"
        self.manifest_directory = self.root / "manifests"
        self.index_path = self.root / "index.json"

        self.blob_directory.mkdir(parents=True, exist_ok=True)
        self.manifest_directory.mkdir(parents=True, exist_ok=True)

        if not self.index_path.exists():
            self._write_json_atomically(self.index_path, {"artifacts": {}})

        self._index = self._read_index()

    @staticmethod
    def digest_bytes(content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def _read_index(self) -> dict[str, Any]:
        try:
            with self.index_path.open("r", encoding="utf-8") as handle:
                value = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            raise IntegrityError("Repository index is unreadable.") from exc

        if not isinstance(value, dict) or not isinstance(value.get("artifacts"), dict):
            raise IntegrityError("Repository index has an invalid structure.")

        return value

    @staticmethod
    def _write_json_atomically(path: Path, value: Any) -> None:
        """Write a complete temporary file before replacing the destination."""
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{next(tempfile._get_candidate_names())}.tmp")

        try:
            with temporary.open("x", encoding="utf-8") as handle:
                json.dump(value, handle, indent=2, sort_keys=True)
                handle.write("\n")
                handle.flush()
                import os
                os.fsync(handle.fileno())
            temporary.replace(path)
        finally:
            temporary.unlink(missing_ok=True)

    def _blob_path(self, digest: str) -> Path:
        return self.blob_directory / digest[:2] / digest[2:]

    def _manifest_path(self, name: str, version: str) -> Path:
        key = hashlib.sha256(f"{name}@{version}".encode()).hexdigest()
        return self.manifest_directory / f"{key}.json"

    def publish(
        self,
        name: str,
        version: str,
        content: bytes,
        publisher: str,
        source_revision: str,
        media_type: str = "application/octet-stream",
        metadata: dict[str, str] | None = None,
    ) -> ArtifactManifest:
        if not isinstance(content, bytes):
            raise ValidationError("Artifact content must be bytes.")

        SemanticVersion.parse(version)
        digest = self.digest_bytes(content)
        artifact_key = f"{name}@{version}"

        existing = self._index["artifacts"].get(artifact_key)
        if existing:
            existing_manifest = self.get_manifest(name, version)

            # Repeating an identical publication is idempotent. Reusing a
            # version for different bytes or provenance is rejected.
            candidate_metadata = tuple(sorted((metadata or {}).items()))
            if (
                existing_manifest.digest == digest
                and existing_manifest.publisher == publisher
                and existing_manifest.source_revision == source_revision
                and existing_manifest.media_type == media_type
                and existing_manifest.metadata == candidate_metadata
            ):
                self.verify(name, version)
                return existing_manifest

            raise ImmutableArtifactError(
                f"{artifact_key} already exists; publish a new version."
            )

        blob_path = self._blob_path(digest)
        blob_path.parent.mkdir(parents=True, exist_ok=True)

        if blob_path.exists():
            if self.digest_bytes(blob_path.read_bytes()) != digest:
                raise IntegrityError("An existing content-addressed blob is corrupted.")
        else:
            # Exclusive creation prevents silently overwriting an existing blob.
            with blob_path.open("xb") as handle:
                handle.write(content)
                handle.flush()
                import os
                os.fsync(handle.fileno())

        manifest = ArtifactManifest(
            name=name,
            version=version,
            digest=digest,
            size_bytes=len(content),
            media_type=media_type,
            created_at=datetime.now(timezone.utc).isoformat(),
            publisher=publisher,
            source_revision=source_revision,
            metadata=tuple(sorted((metadata or {}).items())),
        )
        manifest.validate()

        manifest_path = self._manifest_path(name, version)
        if manifest_path.exists():
            raise IntegrityError("Manifest file exists without an index entry.")

        self._write_json_atomically(manifest_path, asdict(manifest))

        updated_index = json.loads(json.dumps(self._index))
        updated_index["artifacts"][artifact_key] = {
            "manifest": str(manifest_path.relative_to(self.root)),
            "digest": digest,
        }

        try:
            self._write_json_atomically(self.index_path, updated_index)
        except OSError:
            manifest_path.unlink(missing_ok=True)
            raise

        self._index = updated_index
        return manifest

    def get_manifest(self, name: str, version: str) -> ArtifactManifest:
        key = f"{name}@{version}"
        entry = self._index["artifacts"].get(key)
        if entry is None:
            raise ArtifactNotFoundError(f"Artifact version not found: {key}")

        path = self.root / entry["manifest"]
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            raw["metadata"] = tuple(tuple(item) for item in raw.get("metadata", []))
            manifest = ArtifactManifest(**raw)
            manifest.validate()
        except (OSError, ValueError, TypeError, KeyError) as exc:
            raise IntegrityError(f"Manifest is invalid: {key}") from exc

        if manifest.digest != entry["digest"]:
            raise IntegrityError("Index digest does not match manifest digest.")

        return manifest

    def download(self, name: str, version: str) -> bytes:
        manifest = self.get_manifest(name, version)
        blob_path = self._blob_path(manifest.digest)

        try:
            content = blob_path.read_bytes()
        except OSError as exc:
            raise IntegrityError("Artifact blob is missing or unreadable.") from exc

        if len(content) != manifest.size_bytes:
            raise IntegrityError("Artifact size differs from manifest.")

        if self.digest_bytes(content) != manifest.digest:
            raise IntegrityError("Artifact content digest verification failed.")

        return content

    def verify(self, name: str, version: str) -> bool:
        self.download(name, version)
        return True

    def list_versions(self, name: str) -> list[ArtifactManifest]:
        manifests = []
        for key in self._index["artifacts"]:
            artifact_name, separator, version = key.partition("@")
            if separator and artifact_name == name:
                manifests.append(self.get_manifest(artifact_name, version))

        return sorted(
            manifests,
            key=lambda item: SemanticVersion.parse(item.version).precedence_key(),
        )

    def latest_stable(self, name: str) -> ArtifactManifest:
        stable = [
            item
            for item in self.list_versions(name)
            if not SemanticVersion.parse(item.version).prerelease
        ]
        if not stable:
            raise ArtifactNotFoundError(f"No stable version published for {name}.")

        return stable[-1]

    def search_by_digest(self, digest: str) -> list[ArtifactManifest]:
        if not SHA256_PATTERN.fullmatch(digest):
            raise ValidationError("Invalid SHA-256 digest.")

        return [
            self.get_manifest(key.partition("@")[0], key.partition("@")[2])
            for key, entry in self._index["artifacts"].items()
            if entry["digest"] == digest
        ]

    def export_inventory(self, destination: str | Path) -> None:
        inventory = []
        for key in sorted(self._index["artifacts"]):
            name, _, version = key.partition("@")
            manifest = self.get_manifest(name, version)
            inventory.append(asdict(manifest))

        self._write_json_atomically(Path(destination), inventory)


def demonstrate_repository() -> None:
    with tempfile.TemporaryDirectory(prefix="artifact-repository-") as temporary:
        repository = ArtifactRepository(temporary)

        package_v1 = (
            b"package: telemetry-agent\n"
            b"runtime: python\n"
            b"configuration: production\n"
        )
        package_v2 = (
            b"package: telemetry-agent\n"
            b"runtime: python\n"
            b"configuration: production\n"
            b"feature: signed-manifest-verification\n"
        )

        first = repository.publish(
            name="telemetry-agent",
            version="1.0.0",
            content=package_v1,
            publisher="release-bot",
            source_revision="a82c1d4",
            media_type="text/plain",
            metadata={"pipeline": "release-linux", "environment": "production"},
        )

        repository.publish(
            name="telemetry-agent",
            version="1.1.0",
            content=package_v2,
            publisher="release-bot",
            source_revision="b73f9e2",
            media_type="text/plain",
            metadata={"pipeline": "release-linux", "environment": "production"},
        )

        # The same version and same bytes/provenance can be safely retried.
        repository.publish(
            name="telemetry-agent",
            version="1.0.0",
            content=package_v1,
            publisher="release-bot",
            source_revision="a82c1d4",
            media_type="text/plain",
            metadata={"pipeline": "release-linux", "environment": "production"},
        )

        print("Artifact repository demonstration")
        print(f"Published digest: {first.digest}")
        print(f"Latest stable version: {repository.latest_stable('telemetry-agent').version}")

        downloaded = repository.download("telemetry-agent", "1.1.0")
        print(f"Downloaded bytes: {len(downloaded)}")
        print(f"Integrity verified: {repository.verify('telemetry-agent', '1.1.0')}")

        try:
            repository.publish(
                name="telemetry-agent",
                version="1.0.0",
                content=b"modified bytes",
                publisher="release-bot",
                source_revision="c44d0ab",
            )
        except ImmutableArtifactError as exc:
            print(f"Immutable-version protection: {exc}")

        repository.export_inventory(Path(temporary) / "inventory.json")
        print(f"Inventory entries: {len(repository.list_versions('telemetry-agent'))}")


class ArtifactRepositoryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.repository = ArtifactRepository(self.temporary.name)

    def tearDown(self) -> None:
        self.temporary.cleanup()

    def publish(self, version: str, content: bytes = b"release") -> ArtifactManifest:
        return self.repository.publish(
            "inspection-service",
            version,
            content,
            "ci-release",
            "commit-4e1c",
        )

    def test_content_addressed_publication(self) -> None:
        manifest = self.publish("1.0.0")
        self.assertEqual(manifest.digest, hashlib.sha256(b"release").hexdigest())
        self.assertEqual(self.repository.download("inspection-service", "1.0.0"), b"release")

    def test_immutable_version(self) -> None:
        self.publish("1.0.0")
        with self.assertRaises(ImmutableArtifactError):
            self.publish("1.0.0", b"different release")

    def test_idempotent_publication(self) -> None:
        first = self.publish("1.0.0")
        second = self.publish("1.0.0")
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(first.created_at, second.created_at)

    def test_semantic_version_validation(self) -> None:
        with self.assertRaises(ValidationError):
            SemanticVersion.parse("01.2.3")

    def test_missing_artifact(self) -> None:
        with self.assertRaises(ArtifactNotFoundError):
            self.repository.download("inspection-service", "9.9.9")

    def test_blob_tampering_is_detected(self) -> None:
        manifest = self.publish("1.0.0")
        blob = self.repository._blob_path(manifest.digest)
        blob.write_bytes(b"tampered")
        with self.assertRaises(IntegrityError):
            self.repository.verify("inspection-service", "1.0.0")

    def test_stable_release_excludes_prerelease(self) -> None:
        self.publish("2.0.0-rc.1", b"candidate")
        self.publish("1.9.0", b"stable")
        self.assertEqual(self.repository.latest_stable("inspection-service").version, "1.9.0")

    def test_content_deduplication(self) -> None:
        first = self.publish("1.0.0", b"shared")
        second = self.publish("1.1.0", b"shared")
        self.assertEqual(first.digest, second.digest)
        self.assertEqual(self.repository.download("inspection-service", "1.1.0"), b"shared")


if __name__ == "__main__":
    demonstrate_repository()
    print("\nArtifact repository tests")
    unittest.main(argv=["artifact_management.py"], exit=False, verbosity=2)
