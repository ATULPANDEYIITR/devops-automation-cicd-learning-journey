# File: src/linux_admin/services.py
"""systemd service administration."""

from __future__ import annotations

import logging

from .command import CommandRunner
from .models import TaskResult, utc_now
from .security import require_linux, validate_service_name

LOGGER = logging.getLogger(__name__)


class ServiceManager:
    """Manage systemd services through systemctl."""

    def __init__(self, runner: CommandRunner) -> None:
        self.runner = runner

    def status(self, service: str) -> TaskResult:
        require_linux()
        service = validate_service_name(service)
        started = utc_now()

        result = self.runner.run(
            ["systemctl", "is-active", service]
        )

        status = "success" if result.succeeded else "failed"
        message = result.stdout.strip() or result.stderr.strip() or "unknown"

        return TaskResult(
            name=f"service-status:{service}",
            status=status,
            message=message,
            started_at=started,
            finished_at=utc_now(),
            details={
                "service": service,
                "return_code": result.return_code,
            },
        )

    def restart(self, service: str) -> TaskResult:
        require_linux()
        service = validate_service_name(service)
        started = utc_now()

        result = self.runner.run(
            ["systemctl", "restart", service]
        )

        return TaskResult(
            name=f"service-restart:{service}",
            status="success" if result.succeeded else "failed",
            message=(
                f"Service {service} restarted."
                if result.succeeded
                else result.stderr.strip() or "Service restart failed."
            ),
            started_at=started,
            finished_at=utc_now(),
            details={
                "service": service,
                "return_code": result.return_code,
            },
        )

    def enable(self, service: str) -> TaskResult:
        require_linux()
        service = validate_service_name(service)
        started = utc_now()

        result = self.runner.run(
            ["systemctl", "enable", service]
        )

        return TaskResult(
            name=f"service-enable:{service}",
            status="success" if result.succeeded else "failed",
            message=(
                f"Service {service} enabled."
                if result.succeeded
                else result.stderr.strip() or "Service enable failed."
            ),
            started_at=started,
            finished_at=utc_now(),
            details={
                "service": service,
                "return_code": result.return_code,
            },
        )
