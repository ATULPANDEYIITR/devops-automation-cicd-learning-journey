# File: src/linux_admin/models.py
"""Data models shared by the automation modules."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(slots=True)
class CommandResult:
    """Result of an operating-system command."""

    command: list[str]
    return_code: int
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0 and not self.timed_out

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TaskResult:
    """Normalized result returned by an automation task."""

    name: str
    status: str
    message: str
    started_at: str
    finished_at: str
    details: dict[str, Any] = field(default_factory=dict)

    @property
    def succeeded(self) -> bool:
        return self.status == "success"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class SystemSnapshot:
    """Point-in-time information about a Linux machine."""

    hostname: str
    kernel: str
    architecture: str
    uptime_seconds: float
    load_average: tuple[float, float, float]
    cpu_count: int
    memory_total_bytes: int
    memory_available_bytes: int
    disk_usage: dict[str, dict[str, int | float]]
    captured_at: str = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
