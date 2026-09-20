# File: src/linux_admin/cli.py
"""Command-line interface for the Linux administration toolkit."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .command import CommandRunner
from .config import Settings
from .filesystem import directory_size, find_large_files, remove_old_files
from .health import run_health_check
from .logging_config import configure_logging
from .packages import PackageManagerService
from .reporting import write_task_report
from .security import SecurityError, require_linux
from .services import ServiceManager
from .system import collect_snapshot, human_bytes, human_duration
from .tasks import TaskRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="linux-admin",
        description="Linux system administration automation toolkit.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Do not execute commands or delete files.",
    )
    parser.add_argument(
        "--concurrent",
        action="store_true",
        help="Run independent tasks concurrently.",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("system-info", help="Display host information.")
    subparsers.add_parser("health", help="Run automated health checks.")

    service = subparsers.add_parser("service", help="Manage systemd services.")
    service.add_argument("action", choices=("status", "restart", "enable"))
    service.add_argument("name")

    packages = subparsers.add_parser("packages", help="Inspect package updates.")
    packages.add_argument(
        "action",
        choices=("update-metadata", "updates"),
    )

    files = subparsers.add_parser("files", help="Inspect filesystem usage.")
    file_sub = files.add_subparsers(dest="file_action", required=True)

    size = file_sub.add_parser("size")
    size.add_argument("path", type=Path)

    large = file_sub.add_parser("large")
    large.add_argument("path", type=Path)
    large.add_argument("--minimum-mb", type=float, default=100.0)

    cleanup = file_sub.add_parser("cleanup")
    cleanup.add_argument("path", type=Path)
    cleanup.add_argument("--older-than-days", type=float, default=30.0)
    cleanup.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete matching files. Without this flag cleanup is a dry run.",
    )

    return parser


def print_json(payload: object) -> None:
    print(json.dumps(payload, indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    settings = Settings.from_environment()

    if args.dry_run:
        settings = Settings(
            log_level=settings.log_level,
            log_file=settings.log_file,
            dry_run=True,
            command_timeout=settings.command_timeout,
            max_workers=settings.max_workers,
            state_file=settings.state_file,
            report_directory=settings.report_directory,
            allowed_paths=settings.allowed_paths,
        )

    settings.ensure_directories()
    configure_logging(settings.log_level, settings.log_file)

    try:
        require_linux()

        if args.command == "system-info":
            snapshot = collect_snapshot()
            print(f"Hostname: {snapshot.hostname}")
            print(f"Kernel: {snapshot.kernel}")
            print(f"Architecture: {snapshot.architecture}")
            print(f"CPU count: {snapshot.cpu_count}")
            print(f"Uptime: {human_duration(snapshot.uptime_seconds)}")
            print(
                "Memory available: "
                f"{human_bytes(snapshot.memory_available_bytes)} / "
                f"{human_bytes(snapshot.memory_total_bytes)}"
            )

            for mount, usage in snapshot.disk_usage.items():
                print(
                    f"Disk {mount}: {usage['used_percent']}% used "
                    f"({human_bytes(int(usage['free_bytes']))} free)"
                )

            return 0

        if args.command == "health":
            result = run_health_check()
            print_json(result)
            return 0 if result["status"] == "healthy" else 2

        runner = CommandRunner(
            timeout=settings.command_timeout,
            dry_run=settings.dry_run,
        )

        if args.command == "service":
            manager = ServiceManager(runner)
            result = {
                "status": manager.status(args.name).to_dict()
            } if args.action == "status" else {
                "status": getattr(manager, args.action)(args.name).to_dict()
            }
            print_json(result)
            return 0 if result["status"]["status"] == "success" else 2

        if args.command == "packages":
            manager = PackageManagerService(runner)
            result = (
                manager.update_metadata()
                if args.action == "update-metadata"
                else manager.list_upgradable()
            )
            print_json(result.to_dict())
            return 0 if result.succeeded else 2

        if args.command == "files":
            if args.file_action == "size":
                value = directory_size(args.path, settings.allowed_paths)
                print(
                    json.dumps(
                        {
                            "path": str(args.path.resolve()),
                            "size_bytes": value,
                            "size_human": human_bytes(value),
                        },
                        indent=2,
                    )
                )
                return 0

            if args.file_action == "large":
                minimum_bytes = int(args.minimum_mb * 1024 * 1024)
                results = find_large_files(
                    args.path,
                    minimum_bytes,
                    settings.allowed_paths,
                )
                print_json(results)
                return 0

            result = remove_old_files(
                args.path,
                args.older_than_days * 86400,
                settings.allowed_paths,
                dry_run=not args.execute or settings.dry_run,
            )
            print_json(result.to_dict())
            return 0 if result.status in {"success", "partial"} else 2

    except SecurityError as exc:
        print(f"Security validation failed: {exc}", file=sys.stderr)
        return 3
    except (OSError, ValueError) as exc:
        print(f"Operation failed: {exc}", file=sys.stderr)
        return 4

    parser.error("Unsupported command")
    return 5


if __name__ == "__main__":
    raise SystemExit(main())
