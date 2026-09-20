# File: src/linux_admin/command.py
"""Safe subprocess execution primitives."""

from __future__ import annotations

import logging
import subprocess
import time
from collections.abc import Sequence

from .models import CommandResult

LOGGER = logging.getLogger(__name__)


class CommandExecutionError(RuntimeError):
    """Raised when a command cannot be started."""


class CommandRunner:
    """Execute commands without invoking a shell.

    Avoiding shell=True prevents shell metacharacters from being interpreted.
    Commands are therefore represented as argument lists rather than strings.
    """

    def __init__(self, timeout: int = 30, dry_run: bool = False) -> None:
        if timeout <= 0:
            raise ValueError("timeout must be greater than zero")
        self.timeout = timeout
        self.dry_run = dry_run

    def run(self, command: Sequence[str]) -> CommandResult:
        if not command:
            raise ValueError("command cannot be empty")

        normalized = [str(part) for part in command]
        LOGGER.info(
            "%s command: %s",
            "DRY-RUN" if self.dry_run else "Executing",
            " ".join(normalized),
        )

        if self.dry_run:
            return CommandResult(
                command=normalized,
                return_code=0,
                stdout="",
                stderr="",
                duration_seconds=0.0,
            )

        started = time.monotonic()

        try:
            completed = subprocess.run(
                normalized,
                capture_output=True,
                text=True,
                timeout=self.timeout,
                check=False,
            )
        except subprocess.TimeoutExpired as exc:
            duration = time.monotonic() - started
            stdout = exc.stdout or ""
            stderr = exc.stderr or ""
            return CommandResult(
                command=normalized,
                return_code=124,
                stdout=stdout,
                stderr=stderr,
                duration_seconds=duration,
                timed_out=True,
            )
        except OSError as exc:
            raise CommandExecutionError(
                f"Unable to execute {normalized[0]!r}: {exc}"
            ) from exc

        duration = time.monotonic() - started

        return CommandResult(
            command=normalized,
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=duration,
        )
