# File: src/linux_admin/logging_config.py
"""Application logging configuration."""

from __future__ import annotations

import logging
from pathlib import Path


def configure_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    """Configure console logging and optionally a persistent log file."""
    handlers: list[logging.Handler] = [logging.StreamHandler()]

    if log_file:
        handlers.append(
            logging.FileHandler(
                log_file,
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        handlers=handlers,
        force=True,
    )
