# File: src/linux_admin/reporting.py
"""JSON and human-readable reporting."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import TaskResult


def write_json_report(
    path: Path,
    payload: dict[str, Any],
) -> Path:
    """Write an atomically replaced JSON report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")

    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    temporary.replace(path)

    return path


def write_task_report(
    directory: Path,
    tasks: list[TaskResult],
) -> Path:
    """Persist task results as a timestamped JSON report."""
    from datetime import datetime, timezone

    directory.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = directory / f"automation-{timestamp}.json"

    payload = {
        "task_count": len(tasks),
        "successful_tasks": sum(task.succeeded for task in tasks),
        "failed_tasks": sum(not task.succeeded for task in tasks),
        "tasks": [task.to_dict() for task in tasks],
    }

    return write_json_report(path, payload)
