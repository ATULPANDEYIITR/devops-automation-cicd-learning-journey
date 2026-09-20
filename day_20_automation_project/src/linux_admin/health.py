# File: src/linux_admin/health.py
"""Automated host health checks."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .models import SystemSnapshot
from .system import collect_snapshot

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class HealthThresholds:
    """Configurable thresholds used by health checks."""

    memory_available_percent_min: float = 10.0
    disk_used_percent_max: float = 90.0
    load_per_cpu_max: float = 2.0


def run_health_check(
    thresholds: HealthThresholds | None = None,
) -> dict[str, object]:
    """Evaluate a system snapshot against operational thresholds."""
    thresholds = thresholds or HealthThresholds()
    snapshot: SystemSnapshot = collect_snapshot()

    checks: list[dict[str, object]] = []

    memory_percent = (
        snapshot.memory_available_bytes / snapshot.memory_total_bytes * 100
        if snapshot.memory_total_bytes
        else 0.0
    )

    checks.append(
        {
            "name": "memory_available",
            "value_percent": round(memory_percent, 2),
            "threshold_percent": thresholds.memory_available_percent_min,
            "status": (
                "pass"
                if memory_percent >= thresholds.memory_available_percent_min
                else "fail"
            ),
        }
    )

    for mount, usage in snapshot.disk_usage.items():
        used_percent = float(usage["used_percent"])
        checks.append(
            {
                "name": f"disk:{mount}",
                "value_percent": used_percent,
                "threshold_percent": thresholds.disk_used_percent_max,
                "status": (
                    "pass"
                    if used_percent <= thresholds.disk_used_percent_max
                    else "fail"
                ),
            }
        )

    cpu_count = max(snapshot.cpu_count, 1)
    normalized_load = snapshot.load_average[0] / cpu_count

    checks.append(
        {
            "name": "load_per_cpu",
            "value": round(normalized_load, 3),
            "threshold": thresholds.load_per_cpu_max,
            "status": (
                "pass"
                if normalized_load <= thresholds.load_per_cpu_max
                else "fail"
            ),
        }
    )

    passed = all(check["status"] == "pass" for check in checks)

    return {
        "status": "healthy" if passed else "attention_required",
        "checks": checks,
        "snapshot": snapshot.to_dict(),
    }
