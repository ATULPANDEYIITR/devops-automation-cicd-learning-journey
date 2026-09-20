# File: src/linux_admin/filesystem.py
"""Filesystem inspection and cleanup operations."""

from __future__ import annotations

import logging
import os
import stat
from pathlib import Path
from typing import Iterator

from .models import TaskResult, utc_now
from .security import validate_path

LOGGER = logging.getLogger(__name__)


def iter_files(root: Path) -> Iterator[Path]:
    """Yield regular files recursively while skipping symlink traversal."""
    if root.is_file():
        yield root
        return

    if not root.is_dir():
        return

    for entry in os.scandir(root):
        path = Path(entry.path)

        if entry.is_symlink():
            continue

        if entry.is_file(follow_symlinks=False):
            yield path
        elif entry.is_dir(follow_symlinks=False):
            yield from iter_files(path)


def directory_size(root: Path, allowed_roots: tuple[Path, ...]) -> int:
    """Calculate total regular-file size within an allowed directory."""
    safe_root = validate_path(root, allowed_roots)
    total = 0

    for path in iter_files(safe_root):
        try:
            total += path.stat().st_size
        except OSError as exc:
            LOGGER.warning("Unable to stat %s: %s", path, exc)

    return total


def find_large_files(
    root: Path,
    minimum_bytes: int,
    allowed_roots: tuple[Path, ...],
) -> list[dict[str, int | str]]:
    """Find regular files at or above a size threshold."""
    if minimum_bytes < 0:
        raise ValueError("minimum_bytes cannot be negative")

    safe_root = validate_path(root, allowed_roots)
    results: list[dict[str, int | str]] = []

    for path in iter_files(safe_root):
        try:
            metadata = path.stat()
        except OSError as exc:
            LOGGER.warning("Unable to inspect %s: %s", path, exc)
            continue

        if metadata.st_size >= minimum_bytes:
            results.append(
                {
                    "path": str(path),
                    "size_bytes": metadata.st_size,
                }
            )

    return sorted(
        results,
        key=lambda item: int(item["size_bytes"]),
        reverse=True,
    )


def remove_old_files(
    root: Path,
    older_than_seconds: float,
    allowed_roots: tuple[Path, ...],
    dry_run: bool = True,
) -> TaskResult:
    """Delete old regular files when explicitly permitted.

    Dry-run defaults to True because deletion is a destructive operation.
    """
    if older_than_seconds < 0:
        raise ValueError("older_than_seconds cannot be negative")

    safe_root = validate_path(root, allowed_roots)
    started = utc_now()
    cutoff = __import__("time").time() - older_than_seconds

    candidates: list[str] = []
    removed: list[str] = []
    failures: list[dict[str, str]] = []

    for path in iter_files(safe_root):
        try:
            metadata = path.stat()
        except OSError as exc:
            failures.append({"path": str(path), "error": str(exc)})
            continue

        if metadata.st_mtime >= cutoff:
            continue

        mode = stat.S_IMODE(metadata.st_mode)
        if mode & stat.S_IWOTH:
            LOGGER.warning("Skipping world-writable file: %s", path)
            failures.append(
                {
                    "path": str(path),
                    "error": "world-writable file requires explicit review",
                }
            )
            continue

        candidates.append(str(path))

        if not dry_run:
            try:
                path.unlink()
                removed.append(str(path))
            except OSError as exc:
                failures.append({"path": str(path), "error": str(exc)})

    status = "success" if not failures else "partial"

    return TaskResult(
        name=f"cleanup:{safe_root}",
        status=status,
        message=(
            f"Identified {len(candidates)} old file(s); "
            f"removed {len(removed)} file(s)."
        ),
        started_at=started,
        finished_at=utc_now(),
        details={
            "dry_run": dry_run,
            "candidates": candidates,
            "removed": removed,
            "failures": failures,
        },
    )
