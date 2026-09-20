# File: src/linux_admin/config.py
"""Configuration management for the administration toolkit."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_int(value: str | None, default: int) -> int:
    if value is None:
        return default
    try:
        parsed = int(value)
    except ValueError as exc:
        raise ValueError(f"Expected integer configuration value, got {value!r}") from exc
    if parsed <= 0:
        raise ValueError("Integer configuration values must be greater than zero.")
    return parsed


@dataclass(frozen=True, slots=True)
class Settings:
    """Immutable runtime configuration.

    Environment variables are used so secrets and host-specific settings do not
    need to be stored in source code.
    """

    log_level: str
    log_file: Path | None
    dry_run: bool
    command_timeout: int
    max_workers: int
    state_file: Path
    report_directory: Path
    allowed_paths: tuple[Path, ...]

    @classmethod
    def from_environment(cls) -> "Settings":
        raw_log_file = os.getenv("AUTOMATION_LOG_FILE", "").strip()

        allowed_paths = tuple(
            Path(item.strip()).resolve()
            for item in os.getenv(
                "AUTOMATION_ALLOWED_PATHS",
                "/etc,/var/log,/tmp",
            ).split(",")
            if item.strip()
        )

        return cls(
            log_level=os.getenv("AUTOMATION_LOG_LEVEL", "INFO").upper(),
            log_file=Path(raw_log_file) if raw_log_file else None,
            dry_run=_as_bool(os.getenv("AUTOMATION_DRY_RUN")),
            command_timeout=_as_int(
                os.getenv("AUTOMATION_COMMAND_TIMEOUT"),
                30,
            ),
            max_workers=_as_int(
                os.getenv("AUTOMATION_MAX_WORKERS"),
                4,
            ),
            state_file=Path(
                os.getenv("AUTOMATION_STATE_FILE", "runtime/state.json")
            ),
            report_directory=Path(
                os.getenv("AUTOMATION_REPORT_DIRECTORY", "reports")
            ),
            allowed_paths=allowed_paths,
        )

    def ensure_directories(self) -> None:
        """Create local runtime directories when necessary."""
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.report_directory.mkdir(parents=True, exist_ok=True)
        if self.log_file:
            self.log_file.parent.mkdir(parents=True, exist_ok=True)
