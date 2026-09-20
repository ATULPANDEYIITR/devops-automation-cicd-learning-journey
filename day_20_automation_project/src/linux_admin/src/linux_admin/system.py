# File: src/linux_admin/system.py
"""Linux system inspection functionality using standard library interfaces."""

from __future__ import annotations

import logging
import os
import platform
import shutil
import time
from pathlib import Path

from .models import SystemSnapshot
from .security import require_linux

LOGGER = logging.getLogger(__name__)


def _read_meminfo() -> tuple[int, int]:
    total = 0
    available = 0

    with Path("/proc/meminfo").open(encoding="utf-8") as file:
        for line in file:
            key, _, value = line.partition(":")
            number = value.strip().split()[0]
            if key == "MemTotal":
                total = int(number) * 1024
            elif key == "MemAvailable":
                available = int(number) * 1024

    return total, available


def _read_uptime() -> float:
    return float(Path("/proc/uptime").read_text(encoding="utf-8").split()[0])


def collect_snapshot(paths: tuple[str, ...] = ("/", "/tmp")) -> SystemSnapshot:
    """Collect CPU, memory, uptime, load and disk information."""
    require_linux()

    memory_total, memory_available = _read_meminfo()
    disk_usage: dict[str, dict[str, int | float]] = {}

    for path in paths:
        usage = shutil.disk_usage(path)
        percent = (
            (usage.used / usage.total) * 100
            if usage.total
            else 0.0
        )
        disk_usage[path] = {
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "used_percent": round(percent, 2),
        }

    return SystemSnapshot(
        hostname=platform.node(),
        kernel=platform.release(),
        architecture=platform.machine(),
        uptime_seconds=_read_uptime(),
        load_average=os.getloadavg(),
        cpu_count=os.cpu_count() or 1,
        memory_total_bytes=memory_total,
        memory_available_bytes=memory_available,
        disk_usage=disk_usage,
    )


def human_bytes(value: int) -> str:
    """Convert bytes into a readable IEC unit."""
    size = float(value)
    units = ("B", "KiB", "MiB", "GiB", "TiB")

    for unit in units:
        if size < 1024 or unit == units[-1]:
            return f"{size:.2f} {unit}"
        size /= 1024

    return f"{value} B"


def human_duration(seconds: float) -> str:
    """Convert seconds into a readable duration."""
    total = int(seconds)
    days, remainder = divmod(total, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)

    return (
        f"{days}d {hours:02d}h {minutes:02d}m {secs:02d}s"
        if days
        else f"{hours:02d}h {minutes:02d}m {secs:02d}s"
    )


def wait_for_load(
    maximum_load: float,
    check_interval: float = 5.0,
    checks: int = 3,
) -> bool:
    """Wait until the one-minute load average is below a threshold."""
    if maximum_load <= 0:
        raise ValueError("maximum_load must be greater than zero")
    if check_interval < 0:
        raise ValueError("check_interval cannot be negative")
    if checks <= 0:
        raise ValueError("checks must be greater than zero")

    for _ in range(checks):
        current = os.getloadavg()[0]
        LOGGER.info("Current one-minute load average: %.2f", current)

        if current <= maximum_load:
            return True

        time.sleep(check_interval)

    return False
