# File: src/linux_admin/packages.py
"""Package-manager inspection for common Debian and Red Hat systems."""

from __future__ import annotations

import logging
import shutil
from dataclasses import dataclass

from .command import CommandRunner
from .models import TaskResult, utc_now
from .security import require_linux

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PackageManager:
    """Description of a supported package manager."""

    executable: str
    name: str


def detect_package_manager() -> PackageManager | None:
    """Detect apt, dnf, or yum without executing package changes."""
    require_linux()

    for executable, name in (
        ("apt-get", "apt"),
        ("dnf", "dnf"),
        ("yum", "yum"),
    ):
        if shutil.which(executable):
            return PackageManager(executable, name)

    return None


class PackageManagerService:
    """Inspect and update packages using the detected package manager."""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def update_metadata(self) -> TaskResult:
        manager = detect_package_manager()
        started = utc_now()

        if manager is None:
            return TaskResult(
                name="package-metadata-update",
                status="failed",
                message="No supported package manager was detected.",
                started_at=started,
                finished_at=utc_now(),
            )

        command = (
            [manager.executable, "update"]
            if manager.name == "apt"
            else [manager.executable, "makecache"]
        )

        result = self.runner.run(command)

        return TaskResult(
            name="package-metadata-update",
            status="success" if result.succeeded else "failed",
            message=(
                f"{manager.name} metadata updated."
                if result.succeeded
                else result.stderr.strip() or "Package metadata update failed."
            ),
            started_at=started,
            finished_at=utc_now(),
            details={
                "manager": manager.name,
                "return_code": result.return_code,
            },
        )

    def list_upgradable(self) -> TaskResult:
        manager = detect_package_manager()
        started = utc_now()

        if manager is None:
            return TaskResult(
                name="package-updates",
                status="failed",
                message="No supported package manager was detected.",
                started_at=started,
                finished_at=utc_now(),
            )

        if manager.name == "apt":
            command = [manager.executable, "-s", "upgrade"]
        else:
            command = [manager.executable, "check-update"]

        result = self.runner.run(command)

        # dnf/yum commonly use return code 100 to mean updates are available.
        valid_nonzero = manager.name in {"dnf", "yum"} and result.return_code == 100
        success = result.succeeded or valid_nonzero

        return TaskResult(
            name="package-updates",
            status="success" if success else "failed",
            message=(
                "Package update information collected."
                if success
                else result.stderr.strip() or "Package update query failed."
            ),
            started_at=started,
            finished_at=utc_now(),
            details={
                "manager": manager.name,
                "return_code": result.return_code,
                "output": result.stdout,
            },
        )
