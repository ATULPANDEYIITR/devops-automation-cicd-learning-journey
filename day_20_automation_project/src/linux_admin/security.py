# File: src/linux_admin/security.py
"""Security-oriented validation helpers."""

from __future__ import annotations

import os
from pathlib import Path


class SecurityError(ValueError):
    """Raised when an operation violates a configured security boundary."""


def require_linux() -> None:
    """Reject execution on non-Linux systems."""
    if os.name != "posix":
        raise SecurityError("This toolkit requires a POSIX-compatible Linux environment.")

    if not Path("/proc").exists():
        raise SecurityError("The /proc filesystem is required for system inspection.")


def validate_path(path: Path, allowed_roots: tuple[Path, ...]) -> Path:
    """Resolve a path and ensure it belongs to an explicitly allowed tree."""
    resolved = path.expanduser().resolve()

    if not allowed_roots:
        raise SecurityError("No filesystem paths are configured as allowed.")

    for root in allowed_roots:
        try:
            resolved.relative_to(root)
        except ValueError:
            continue
        return resolved

    raise SecurityError(
        f"Path {resolved} is outside the configured filesystem safety boundaries."
    )


def validate_service_name(name: str) -> str:
    """Validate a systemd unit name without invoking a shell."""
    normalized = name.strip()

    if not normalized:
        raise SecurityError("Service name cannot be empty.")

    allowed = set(
        "abcdefghijklmnopqrstuvwxyz"
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
        "0123456789"
        "-_.@:"
    )

    if any(character not in allowed for character in normalized):
        raise SecurityError(f"Invalid service name: {name!r}")

    return normalized
