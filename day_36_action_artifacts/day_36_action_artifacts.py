#!/usr/bin/env python3
"""
Build artifact lifecycle demonstration.

This script models artifact creation, packaging, checksums, metadata, local storage,
upload/download behavior, retention, integrity verification, and cleanup. It uses
only Python's standard library so it can run without external dependencies.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tarfile
import tempfile
import time
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable


ARTIFACT_SCHEMA_VERSION = 1


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def sha256_file(path: Path, chunk_size: int = 1024 * 1024) -> str:
    """Hash a file incrementally so large artifacts do not need to fit in memory."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def directory_size(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def ensure_safe_relative_path(path: str) -> Path:
    """
    Reject absolute paths and traversal components before extracting an archive.

    Artifact archives are untrusted inputs in many build systems, so extraction
    must not be allowed to write outside the intended destination.
    """
    candidate = Path(path)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError(f"Unsafe archive member path: {path}")
    return candidate


@dataclass(frozen=True)
class ArtifactFile:
    relative_path: str
    size_bytes: int
    sha256: str


@dataclass
class ArtifactManifest:
    artifact_id: str
    repository: str
    commit_sha: str
    build_number: int
    created_at: str
    files: list[ArtifactFile]
    total_size_bytes: int
    archive_sha256: str = ""
    retention_days: int = 30
    labels: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "schema_version": ARTIFACT_SCHEMA_VERSION,
            **asdict(self),
            "files": [asdict(item) for item in self.files],
        }


@dataclass
class StoredArtifact:
    artifact_id: str
    archive_path: Path
    manifest_path: Path
    created_at: datetime
    retention_days: int

    @property
    def expires_at(self) -> datetime:
        return self.created_at + timedelta(days=self.retention_days)


class ArtifactBuilder:
    """Creates a reproducible artifact archive and its manifest."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.workspace.mkdir(parents=True, exist_ok=True)

    def collect_files(self, source: Path) -> list[ArtifactFile]:
        if not source.exists() or not source.is_dir():
            raise FileNotFoundError(f"Build output directory does not exist: {source}")

        records: list[ArtifactFile] = []
        for path in sorted(source.rglob("*")):
            if path.is_file():
                relative = path.relative_to(source).as_posix()
                records.append(
                    ArtifactFile(
                        relative_path=relative,
                        size_bytes=path.stat().st_size,
                        sha256=sha256_file(path),
                    )
                )

        if not records:
            raise ValueError("Cannot publish an empty artifact.")

        return records

    def package(
        self,
        source: Path,
        repository: str,
        commit_sha: str,
        build_number: int,
        retention_days: int = 30,
        labels: dict[str, str] | None = None,
    ) -> tuple[Path, ArtifactManifest]:
        files = self.collect_files(source)
        artifact_id = (
            f"{repository.replace('/', '-')}-"
            f"{build_number}-{uuid.uuid4().hex[:12]}"
        )
        archive_path = self.workspace / f"{artifact_id}.tar.gz"

        with tarfile.open(archive_path, "w:gz") as archive:
            for record in files:
                archive.add(source / record.relative_path, arcname=record.relative_path)

        manifest = ArtifactManifest(
            artifact_id=artifact_id,
            repository=repository,
            commit_sha=commit_sha,
            build_number=build_number,
            created_at=utc_now().isoformat(),
            files=files,
            total_size_bytes=sum(item.size_bytes for item in files),
            archive_sha256=sha256_file(archive_path),
            retention_days=retention_days,
            labels=labels or {},
        )

        manifest_path = self.workspace / f"{artifact_id}.manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.to_dict(), indent=2),
            encoding="utf-8",
        )
        return archive_path, manifest


class ArtifactRepository:
    """
    A filesystem-backed artifact repository.

    The same interface concepts map to object storage systems: an artifact has
    immutable content, metadata, a key, retention information, and integrity data.
    """

    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def upload(self, archive: Path, manifest: ArtifactManifest) -> StoredArtifact:
        if not archive.is_file():
            raise FileNotFoundError(archive)

        if sha256_file(archive) != manifest.archive_sha256:
            raise ValueError("Artifact checksum does not match its manifest.")

        destination = self.root / f"{manifest.artifact_id}.tar.gz"
        manifest_destination = self.root / f"{manifest.artifact_id}.manifest.json"

        # copy2 retains useful filesystem metadata while the content remains immutable
        shutil.copy2(archive, destination)
        manifest_destination.write_text(
            json.dumps(manifest.to_dict(), indent=2),
            encoding="utf-8",
        )

        return StoredArtifact(
            artifact_id=manifest.artifact_id,
            archive_path=destination,
            manifest_path=manifest_destination,
            created_at=datetime.fromisoformat(manifest.created_at),
            retention_days=manifest.retention_days,
        )

    def download(
        self,
        artifact_id: str,
        destination: Path,
        expected_sha256: str | None = None,
    ) -> Path:
        source = self.root / f"{artifact_id}.tar.gz"
        if not source.is_file():
            raise FileNotFoundError(f"Artifact not found: {artifact_id}")

        destination.mkdir(parents=True, exist_ok=True)
        downloaded = destination / source.name
        shutil.copy2(source, downloaded)

        actual_hash = sha256_file(downloaded)
        if expected_sha256 and actual_hash != expected_sha256:
            downloaded.unlink(missing_ok=True)
            raise ValueError(
                f"Integrity verification failed: expected {expected_sha256}, "
                f"received {actual_hash}"
            )

        return downloaded

    def read_manifest(self, artifact_id: str) -> ArtifactManifest:
        path = self.root / f"{artifact_id}.manifest.json"
        if not path.is_file():
            raise FileNotFoundError(f"Manifest not found: {artifact_id}")

        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("schema_version") != ARTIFACT_SCHEMA_VERSION:
            raise ValueError("Unsupported artifact manifest schema.")

        return ArtifactManifest(
            artifact_id=data["artifact_id"],
            repository=data["repository"],
            commit_sha=data["commit_sha"],
            build_number=data["build_number"],
            created_at=data["created_at"],
            files=[ArtifactFile(**item) for item in data["files"]],
            total_size_bytes=data["total_size_bytes"],
            archive_sha256=data["archive_sha256"],
            retention_days=data["retention_days"],
            labels=data.get("labels", {}),
        )

    def list_artifacts(self) -> list[StoredArtifact]:
        results = []
        for manifest_path in sorted(self.root.glob("*.manifest.json")):
            artifact_id = manifest_path.name.removesuffix(".manifest.json")
            try:
                manifest = self.read_manifest(artifact_id)
                archive_path = self.root / f"{artifact_id}.tar.gz"
                if archive_path.exists():
                    results.append(
                        StoredArtifact(
                            artifact_id=artifact_id,
                            archive_path=archive_path,
                            manifest_path=manifest_path,
                            created_at=datetime.fromisoformat(manifest.created_at),
                            retention_days=manifest.retention_days,
                        )
                    )
            except (OSError, ValueError, KeyError):
                # A production repository would send this to structured logging
                # rather than silently ignoring corrupt metadata.
                continue
        return results

    def delete(self, artifact_id: str) -> None:
        self.read_manifest(artifact_id)
        (self.root / f"{artifact_id}.tar.gz").unlink(missing_ok=True)
        (self.root / f"{artifact_id}.manifest.json").unlink(missing_ok=True)

    def purge_expired(self, now: datetime | None = None) -> list[str]:
        current_time = now or utc_now()
        deleted: list[str] = []

        for artifact in self.list_artifacts():
            if current_time >= artifact.expires_at:
                self.delete(artifact.artifact_id)
                deleted.append(artifact.artifact_id)

        return deleted


def safe_extract(archive_path: Path, destination: Path) -> list[Path]:
    """
    Extract an artifact while preventing path traversal.

    A checksum proves that the downloaded archive is the expected artifact,
    but archive-member validation is still needed before writing its contents.
    """
    destination.mkdir(parents=True, exist_ok=True)
    extracted: list[Path] = []

    with tarfile.open(archive_path, "r:gz") as archive:
        for member in archive.getmembers():
            relative = ensure_safe_relative_path(member.name)
            target = destination / relative

            if member.issym() or member.islnk():
                raise ValueError(f"Links are not allowed in build artifacts: {member.name}")

            resolved_target = target.resolve()
            resolved_root = destination.resolve()
            if resolved_target != resolved_root and resolved_root not in resolved_target.parents:
                raise ValueError(f"Archive member escapes destination: {member.name}")

            archive.extract(member, destination)
            extracted.append(target)

    return extracted


def verify_extracted_files(
    destination: Path,
    manifest: ArtifactManifest,
) -> None:
    """Verify each extracted file against the manifest created during packaging."""
    for record in manifest.files:
        target = destination / record.relative_path
        if not target.is_file():
            raise ValueError(f"Missing artifact file: {record.relative_path}")

        actual_size = target.stat().st_size
        actual_hash = sha256_file(target)

        if actual_size != record.size_bytes:
            raise ValueError(
                f"Size mismatch for {record.relative_path}: "
                f"expected {record.size_bytes}, got {actual_size}"
            )

        if actual_hash != record.sha256:
            raise ValueError(
                f"Checksum mismatch for {record.relative_path}: "
                f"expected {record.sha256}, got {actual_hash}"
            )


def create_demo_build_output(path: Path) -> None:
    """Create realistic build output for the executable demonstration."""
    (path / "bin").mkdir(parents=True, exist_ok=True)
    (path / "config").mkdir(parents=True, exist_ok=True)
    (path / "docs").mkdir(parents=True, exist_ok=True)

    (path / "bin" / "release-info.txt").write_text(
        "application=artifact-demo\nversion=2026.10.06\nprofile=release\n",
        encoding="utf-8",
    )
    (path / "config" / "runtime.json").write_text(
        json.dumps(
            {
                "environment": "production",
                "logging": "structured",
                "artifact_format": "tar.gz",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (path / "docs" / "build.txt").write_text(
        "Build output is packaged as an immutable artifact.\n",
        encoding="utf-8",
    )


def run_demo() -> None:
    print("=== Build Artifact Lifecycle ===")

    with tempfile.TemporaryDirectory(prefix="artifact-demo-") as temporary:
        root = Path(temporary)
        build_output = root / "build-output"
        staging = root / "staging"
        repository_root = root / "artifact-repository"
        download_root = root / "downloads"

        create_demo_build_output(build_output)

        builder = ArtifactBuilder(staging)
        archive, manifest = builder.package(
            source=build_output,
            repository="platform/release-service",
            commit_sha="7f3d8a2b91c4",
            build_number=184,
            retention_days=30,
            labels={
                "environment": "production",
                "format": "tar.gz",
                "pipeline": "release",
            },
        )

        print(f"Created artifact: {manifest.artifact_id}")
        print(f"Files: {len(manifest.files)}")
        print(f"Logical content size: {manifest.total_size_bytes} bytes")
        print(f"Archive size: {archive.stat().st_size} bytes")
        print(f"SHA-256: {manifest.archive_sha256}")

        repository = ArtifactRepository(repository_root)
        stored = repository.upload(archive, manifest)
        print(f"Stored at: {stored.archive_path}")

        downloaded = repository.download(
            manifest.artifact_id,
            download_root,
            expected_sha256=manifest.archive_sha256,
        )
        print(f"Downloaded: {downloaded.name}")

        extracted = download_root / "release"
        safe_extract(downloaded, extracted)
        verify_extracted_files(extracted, manifest)

        print("Artifact integrity verification: PASSED")
        print(f"Extracted size: {directory_size(extracted)} bytes")

        loaded_manifest = repository.read_manifest(manifest.artifact_id)
        print(
            "Metadata verification:",
            loaded_manifest.commit_sha == "7f3d8a2b91c4",
        )

        print("\nStored artifacts:")
        for artifact in repository.list_artifacts():
            print(
                f"  {artifact.artifact_id} | "
                f"expires {artifact.expires_at.isoformat()}"
            )

        # Simulate retention expiry without waiting 30 days.
        expired = repository.purge_expired(
            now=utc_now() + timedelta(days=31)
        )
        print(f"Retention cleanup removed: {expired}")


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build artifact packaging, storage, download, and verification demo."
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the complete local artifact lifecycle demonstration.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    if args.self_test:
        run_demo()
    else:
        print("Run with --self-test to execute the artifact lifecycle demonstration.")
