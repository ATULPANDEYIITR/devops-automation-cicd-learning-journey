#!/usr/bin/env python3
"""
Bash Automation Study Companion
================================

This self-contained Python program teaches the concepts behind Bash automation
through executable simulations and cross-platform-safe examples.

The focus is:
- File automation
- Backups
- Cleanup
- System tasks
- Shell commands and processes
- Scheduling concepts
- Logging
- Validation
- Error handling
- Idempotency
- Security
- Reliability
- Performance
- Production-oriented automation design

The program intentionally avoids destructive operations on the real machine.
Temporary directories are created and removed safely for demonstrations.

Run:
    python bash_automation.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path


# ---------------------------------------------------------------------------
# Fundamentals: representing a file operation
# ---------------------------------------------------------------------------

@dataclass
class FileRecord:
    path: Path
    size: int
    modified_time: float


def heading(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def explain_shell_concept() -> None:
    heading("1. What Bash automation is")

    print(
        """
Bash is a Unix shell and scripting language commonly used to automate
operating-system tasks.

A Bash automation script commonly performs this sequence:

    input -> validation -> operation -> verification -> logging

Typical tasks include:

    - creating directories
    - copying and moving files
    - finding files
    - compressing archives
    - rotating logs
    - removing expired temporary files
    - checking disk space
    - starting or stopping services
    - running scheduled maintenance
    - invoking other programs
    - handling failures
    - producing audit logs

A Bash script normally begins with a shebang such as:

    #!/usr/bin/env bash

The shebang tells the operating system which interpreter should execute
the script.
"""
    )


# ---------------------------------------------------------------------------
# Shell command concepts
# ---------------------------------------------------------------------------

def run_command(command: list[str], *, check: bool = False) -> subprocess.CompletedProcess:
    """
    Demonstrates the safe equivalent of Bash's command execution.

    Python's subprocess.run(list) avoids constructing a shell command string.
    This is useful for understanding the security difference between:

        command arguments
    and
        shell source code
    """
    return subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=check,
    )


def demonstrate_process_execution() -> None:
    heading("2. Executing system commands")

    if platform.system() == "Windows":
        command = ["cmd", "/c", "echo Bash automation concepts"]
    else:
        command = ["printf", "%s\\n", "Bash automation concepts"]

    result = run_command(command)

    print("Command:", command)
    print("Return code:", result.returncode)
    print("Standard output:", result.stdout.strip())
    print("Standard error:", result.stderr.strip() or "<empty>")

    print(
        """
In Bash, the equivalent conceptual operation is:

    command
    status=$?

The special variable `$?` contains the exit status of the previous command.

Conventionally:
    0     success
    non-0 failure

This convention is fundamental to reliable automation.
"""
    )


# ---------------------------------------------------------------------------
# File discovery
# ---------------------------------------------------------------------------

def create_demo_tree(root: Path) -> None:
    """Create a realistic but disposable directory tree."""
    directories = [
        root / "documents",
        root / "documents" / "reports",
        root / "logs",
        root / "cache",
        root / "backup",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    files = {
        root / "documents" / "notes.txt": "Important notes\n",
        root / "documents" / "reports" / "annual.txt": "Annual report\n",
        root / "logs" / "application.log": "INFO application started\n",
        root / "logs" / "old.log": "INFO old event\n",
        root / "cache" / "temporary.tmp": "temporary data\n",
    }

    for path, content in files.items():
        path.write_text(content, encoding="utf-8")


def discover_files(root: Path) -> list[FileRecord]:
    """Equivalent conceptually to recursive `find` operations."""
    records = []

    for path in root.rglob("*"):
        if path.is_file():
            stat = path.stat()
            records.append(
                FileRecord(
                    path=path,
                    size=stat.st_size,
                    modified_time=stat.st_mtime,
                )
            )

    return records


def demonstrate_file_discovery(root: Path) -> None:
    heading("3. File automation and discovery")

    records = discover_files(root)

    for record in sorted(records, key=lambda item: str(item.path)):
        print(f"{record.path.relative_to(root)} | {record.size} bytes")

    print(
        """
Common Bash tools:

    find
    basename
    dirname
    stat
    du
    ls

For example, conceptually:

    find "$SOURCE_DIR" -type f -name "*.log"

Quoting variables such as "$SOURCE_DIR" is important because paths can
contain spaces and shell metacharacters.
"""
    )


# ---------------------------------------------------------------------------
# File filtering
# ---------------------------------------------------------------------------

def files_matching_suffix(root: Path, suffix: str) -> list[Path]:
    return [
        path
        for path in root.rglob("*")
        if path.is_file() and path.suffix.lower() == suffix.lower()
    ]


def demonstrate_filtering(root: Path) -> None:
    heading("4. Filtering files")

    print("Text files:")
    for path in files_matching_suffix(root, ".txt"):
        print(" ", path.relative_to(root))

    print("Log files:")
    for path in files_matching_suffix(root, ".log"):
        print(" ", path.relative_to(root))

    print(
        """
Bash globbing examples:

    *.log
    *.txt
    backup-*.tar.gz

A glob is not the same thing as a regular expression.

    *.log

means a shell filename pattern, while:

    ^.*\\.log$

is a regular expression describing matching text.
"""
    )


# ---------------------------------------------------------------------------
# Safe copying and backup
# ---------------------------------------------------------------------------

def sha256(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def backup_directory(source: Path, destination: Path) -> list[dict[str, str | int]]:
    """
    Create a file-level backup while retaining relative paths.

    This models what an automation script should verify:
    source existence, destination creation, copying, and integrity.
    """
    if not source.is_dir():
        raise ValueError(f"Source is not a directory: {source}")

    destination.mkdir(parents=True, exist_ok=True)
    manifest = []

    for source_file in source.rglob("*"):
        if not source_file.is_file():
            continue

        relative = source_file.relative_to(source)
        destination_file = destination / relative
        destination_file.parent.mkdir(parents=True, exist_ok=True)

        shutil.copy2(source_file, destination_file)

        source_hash = sha256(source_file)
        destination_hash = sha256(destination_file)

        if source_hash != destination_hash:
            raise IOError(f"Integrity verification failed: {source_file}")

        manifest.append(
            {
                "file": str(relative),
                "size": source_file.stat().st_size,
                "sha256": source_hash,
            }
        )

    return manifest


def demonstrate_backup(root: Path) -> None:
    heading("5. Backup automation")

    source = root / "documents"
    destination = root / "backup" / "documents"

    manifest = backup_directory(source, destination)

    print(json.dumps(manifest, indent=2))

    print(
        """
A basic Bash backup might use:

    cp -a "$SOURCE/" "$BACKUP/"

For large systems, tools such as `rsync` are often preferable because
they can transfer only changed data.

A robust backup process should consider:

    - source validation
    - destination validation
    - permissions
    - available disk space
    - partial failures
    - checksums
    - timestamps
    - retention
    - encryption
    - restoration testing
    - logging
    - off-machine copies

A backup that cannot be restored is not a reliable recovery mechanism.
"""
    )


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------

def cleanup_expired_files(root: Path, age_seconds: int, suffix: str | None = None) -> list[Path]:
    """
    Delete only files satisfying explicit conditions.

    The function returns the deleted paths so an automation system can log
    exactly what happened.
    """
    cutoff = time.time() - age_seconds
    deleted = []

    for path in root.rglob("*"):
        if not path.is_file():
            continue

        if suffix and path.suffix.lower() != suffix.lower():
            continue

        if path.stat().st_mtime < cutoff:
            path.unlink()
            deleted.append(path)

    return deleted


def demonstrate_cleanup(root: Path) -> None:
    heading("6. Cleanup automation")

    old_file = root / "logs" / "old.log"

    old_time = time.time() - (10 * 24 * 60 * 60)
    os.utime(old_file, (old_time, old_time))

    deleted = cleanup_expired_files(root / "logs", age_seconds=7 * 24 * 60 * 60)

    print("Deleted:")
    for path in deleted:
        print(" ", path.relative_to(root))

    print(
        """
A dangerous cleanup command is one that deletes without validating its
target.

Safer Bash structure:

    TARGET_DIR="/var/tmp/application"

    [[ -d "$TARGET_DIR" ]] || exit 1

    find "$TARGET_DIR" -type f -mtime +7 -name "*.tmp" -delete

Important principles:

    - use an explicit directory
    - validate that the directory exists
    - use restrictive filename patterns
    - avoid accidental `/`
    - avoid unquoted variables
    - test with `-print` before `-delete`
"""
    )


# ---------------------------------------------------------------------------
# Archives
# ---------------------------------------------------------------------------

def create_archive(source: Path, archive: Path) -> None:
    archive.parent.mkdir(parents=True, exist_ok=True)
    shutil.make_archive(
        base_name=str(archive.with_suffix("")),
        format="gztar",
        root_dir=str(source),
    )


def demonstrate_archiving(root: Path) -> None:
    heading("7. Compression and archives")

    archive_base = root / "backup" / "documents-archive"
    create_archive(root / "documents", archive_base)

    archive_path = Path(str(archive_base) + ".tar.gz")

    print("Created:", archive_path.relative_to(root))
    print(
        """
Bash commonly uses:

    tar -czf backup.tar.gz directory/

Extraction:

    tar -xzf backup.tar.gz

Typical options:

    -c  create
    -x  extract
    -t  list
    -z  gzip
    -f  file

Archive formats have different characteristics. Compression saves storage
and bandwidth but costs CPU time.
"""
    )


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

class AutomationLogger:
    """Minimal structured logger for automation demonstrations."""

    def __init__(self, path: Path):
        self.path = path

    def log(self, level: str, message: str) -> None:
        timestamp = datetime.now().isoformat(timespec="seconds")
        line = f"{timestamp} [{level.upper()}] {message}\n"
        with self.path.open("a", encoding="utf-8") as file:
            file.write(line)
        print(line, end="")


def demonstrate_logging(root: Path) -> None:
    heading("8. Logging")

    logger = AutomationLogger(root / "automation.log")
    logger.log("info", "Automation started")
    logger.log("info", "Backup verification completed")
    logger.log("warning", "Example warning")
    logger.log("info", "Automation finished")

    print(
        """
Production scripts should record:

    - start time
    - operation
    - target
    - result
    - error
    - duration
    - exit status

A useful distinction is:

    stdout -> normal operational output
    stderr -> errors and diagnostic information

Bash redirection examples:

    command > output.log
    command 2> error.log
    command >> output.log 2>&1
"""
    )


# ---------------------------------------------------------------------------
# Validation and idempotency
# ---------------------------------------------------------------------------

def ensure_directory(path: Path) -> bool:
    """
    Idempotent directory creation.

    Calling this repeatedly produces the same desired state.
    """
    path.mkdir(parents=True, exist_ok=True)
    return path.is_dir()


def demonstrate_idempotency(root: Path) -> None:
    heading("9. Validation and idempotency")

    target = root / "idempotent-output"

    first = ensure_directory(target)
    second = ensure_directory(target)

    print("First call:", first)
    print("Second call:", second)

    print(
        """
Idempotency means that repeating an operation does not produce unintended
additional effects.

Examples:

    mkdir -p directory

is naturally idempotent.

A naive:

    mkdir directory

may fail if the directory already exists.

Automation should usually describe a desired state rather than merely
performing an uncontrolled sequence of actions.
"""
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class AutomationConfig:
    source: Path
    backup: Path
    retention_days: int
    dry_run: bool


def validate_config(config: AutomationConfig) -> None:
    if config.retention_days < 0:
        raise ValueError("Retention days cannot be negative.")

    if config.source == config.backup:
        raise ValueError("Source and backup directories must differ.")

    if config.source.is_file():
        raise ValueError("Source must be a directory.")


def demonstrate_configuration(root: Path) -> None:
    heading("10. Configuration-driven automation")

    config = AutomationConfig(
        source=root / "documents",
        backup=root / "backup" / "configured",
        retention_days=30,
        dry_run=True,
    )

    validate_config(config)

    print(config)

    print(
        """
Bash scripts frequently accept configuration through:

    positional arguments
    command-line options
    environment variables
    configuration files

Examples:

    ./backup.sh /data /backup

    BACKUP_ROOT=/backup ./backup.sh

A production script should validate every external value before using it.
"""
    )


# ---------------------------------------------------------------------------
# Dry-run design
# ---------------------------------------------------------------------------

def planned_cleanup(root: Path, suffix: str) -> list[Path]:
    """Return candidates without deleting them."""
    return [
        path
        for path in root.rglob(f"*{suffix}")
        if path.is_file()
    ]


def demonstrate_dry_run(root: Path) -> None:
    heading("11. Dry-run mode")

    candidates = planned_cleanup(root / "logs", ".log")

    print("Dry-run candidates:")
    for path in candidates:
        print(" WOULD DELETE:", path.relative_to(root))

    print(
        """
Dry-run mode is especially valuable for destructive automation.

A common Bash design is:

    DRY_RUN="${DRY_RUN:-true}"

    if [[ "$DRY_RUN" == "true" ]]; then
        echo "Would delete: $file"
    else
        rm -- "$file"
    fi

The exact implementation should be designed so a failed or malformed
configuration cannot silently switch into destructive behavior.
"""
    )


# ---------------------------------------------------------------------------
# Disk-space concepts
# ---------------------------------------------------------------------------

def demonstrate_disk_usage(root: Path) -> None:
    heading("12. Disk-space monitoring")

    usage = shutil.disk_usage(root)

    print(f"Total:     {usage.total / (1024**3):.2f} GiB")
    print(f"Used:      {usage.used / (1024**3):.2f} GiB")
    print(f"Free:      {usage.free / (1024**3):.2f} GiB")

    print(
        """
A Bash monitoring script may use:

    df -h

and parse the result.

Production automation should avoid fragile parsing where possible.
When a command provides machine-readable output, prefer that form.

For example, many Unix utilities provide options designed for scripting.
"""
    )


# ---------------------------------------------------------------------------
# Checksums and integrity
# ---------------------------------------------------------------------------

def demonstrate_integrity(root: Path) -> None:
    heading("13. File integrity")

    target = root / "documents" / "notes.txt"
    digest = sha256(target)

    print("File:", target.relative_to(root))
    print("SHA-256:", digest)

    print(
        """
Checksums can verify that a copied file has the same content as the source.

Common Unix tools:

    sha256sum file
    md5sum file

SHA-256 is generally preferable to MD5 for integrity checks where modern
cryptographic hashing is required.

A checksum does not automatically prove that a backup is trustworthy:
the integrity of the checksum itself and the backup storage must also be
considered.
"""
    )


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

def retry(operation, attempts: int = 3, delay: float = 0.1):
    """
    Generic retry pattern.

    Retry only failures that are expected to be transient.
    Retrying permanent failures can make an incident worse.
    """
    last_error = None

    for attempt in range(1, attempts + 1):
        try:
            return operation()
        except Exception as error:
            last_error = error
            if attempt < attempts:
                time.sleep(delay * attempt)

    raise RuntimeError(f"Operation failed after {attempts} attempts") from last_error


def demonstrate_retry() -> None:
    heading("14. Retry and transient failures")

    state = {"attempts": 0}

    def unstable_operation() -> str:
        state["attempts"] += 1

        if state["attempts"] < 3:
            raise ConnectionError("Temporary failure")

        return "Operation succeeded"

    print(retry(unstable_operation))
    print("Attempts:", state["attempts"])

    print(
        """
Retries are useful for:

    - temporary network failures
    - transient service unavailability
    - temporary resource contention

Retries should normally use:

    - a maximum attempt count
    - a delay
    - exponential backoff
    - optional jitter
    - clear logging

Do not blindly retry destructive operations unless their semantics are
safe and idempotent.
"""
    )


# ---------------------------------------------------------------------------
# Scheduling concepts
# ---------------------------------------------------------------------------

def demonstrate_scheduling() -> None:
    heading("15. Scheduling")

    print(
        """
Cron is a common Unix scheduler.

A conceptual entry:

    0 2 * * * /opt/scripts/backup.sh

means approximately:

    minute   = 0
    hour     = 2
    day      = every day
    month    = every month
    weekday  = every weekday

Common cron patterns:

    */5 * * * *       every five minutes
    0 * * * *         every hour
    0 0 * * *         every day at midnight
    0 0 * * 0         weekly

Scheduled jobs should use absolute paths where appropriate, because cron's
environment can differ significantly from an interactive shell.

The script should also explicitly define environment assumptions.
"""
    )


# ---------------------------------------------------------------------------
# Signals and process safety
# ---------------------------------------------------------------------------

def demonstrate_process_safety() -> None:
    heading("16. Process and signal safety")

    print(
        """
Unix processes can receive signals.

Important examples:

    SIGTERM  request graceful termination
    SIGINT   interrupt, often from Ctrl+C
    SIGKILL  force termination; cannot be caught
    SIGHUP   historically associated with terminal/session closure

Bash can install cleanup handlers:

    trap cleanup EXIT
    trap 'handle_interrupt' INT TERM

This is useful when automation creates temporary files, locks, mounts,
or other resources that must be released.

A cleanup handler should itself be simple and safe.
"""
    )


# ---------------------------------------------------------------------------
# Locking concepts
# ---------------------------------------------------------------------------

def demonstrate_locking() -> None:
    heading("17. Preventing concurrent runs")

    print(
        """
Scheduled automation can accidentally overlap.

For example:

    02:00 backup starts
    02:01 backup starts again because the previous run is still active

Unix systems commonly use lock files or utilities such as `flock`.

Conceptually:

    flock -n /var/run/my-job.lock ./job.sh

A non-blocking lock can cause the second execution to exit rather than
perform duplicate work.

Locks should account for stale processes and abnormal termination.
"""
    )


# ---------------------------------------------------------------------------
# Security
# ---------------------------------------------------------------------------

def demonstrate_security() -> None:
    heading("18. Security principles")

    print(
        """
Shell automation is powerful because it can directly control the operating
system. That also makes mistakes potentially destructive.

Important practices:

1. Quote variables:

       "$FILE"

   instead of:

       $FILE

2. Avoid evaluating untrusted strings as shell code.

   Dangerous pattern:

       eval "$USER_INPUT"

3. Prefer arrays for commands:

       command=(tar -czf "$archive" "$directory")
       "${command[@]}"

4. Validate paths.

5. Use least privilege.

6. Never place secrets directly in source code.

7. Restrict permissions on credential files.

8. Avoid logging passwords, access tokens, private keys, and sensitive data.

9. Use absolute paths when PATH manipulation could be unsafe.

10. Validate destructive operations.

11. Avoid running the entire script as root when only one operation needs
    elevated privileges.

12. Treat filenames as data, not shell syntax.

Command injection is one of the most important shell-specific risks.
"""
    )


# ---------------------------------------------------------------------------
# Performance
# ---------------------------------------------------------------------------

def demonstrate_performance() -> None:
    heading("19. Performance considerations")

    print(
        """
Automation performance depends on workload.

Potential bottlenecks include:

    - repeatedly spawning processes
    - scanning millions of files
    - unnecessary copying
    - compression
    - network transfers
    - slow storage
    - inefficient pipelines

For large trees, prefer tools designed for bulk operations.

Examples:

    find
    rsync
    tar
    xargs
    awk
    sed

A Bash loop such as:

    for file in $(find ...)

can be problematic because command substitution performs word splitting
and pathname expansion.

A safer pattern is often:

    while IFS= read -r file; do
        ...
    done < <(find ... -print0)

with appropriate null-delimited handling.

For very large datasets, choose tools based on measured workload rather
than assuming that shell loops are always efficient.
"""
    )


# ---------------------------------------------------------------------------
# Bash strict mode
# ---------------------------------------------------------------------------

def demonstrate_strict_mode() -> None:
    heading("20. Bash strict mode")

    print(
        """
A frequently used Bash baseline is:

    set -euo pipefail

Meaning:

    -e    exit on many unhandled command failures
    -u    treat unset variables as errors
    pipefail
          make a pipeline fail when an earlier command fails

Example:

    set -euo pipefail

    SOURCE="/data"
    BACKUP="/backup"

    [[ -d "$SOURCE" ]] || {
        echo "Source does not exist" >&2
        exit 1
    }

Strict mode improves failure visibility, but it does not make every script
automatically correct. Bash has contextual rules around `set -e`, pipelines,
conditionals, command substitutions, and traps.

Critical scripts should test failure paths explicitly.
"""
    )


# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

def demonstrate_testing(root: Path) -> None:
    heading("21. Testing automation")

    source = root / "documents"
    backup = root / "backup" / "test"

    manifest = backup_directory(source, backup)

    assert manifest, "Expected at least one backed-up file"

    for item in manifest:
        backed_up = backup / item["file"]
        assert backed_up.exists()
        assert sha256(backed_up) == item["sha256"]

    print("Backup integrity tests passed.")

    print(
        """
Automation should test:

    - successful execution
    - missing source
    - inaccessible destination
    - empty directories
    - spaces in filenames
    - unusual characters
    - permission failures
    - partial copies
    - interrupted execution
    - concurrent execution
    - insufficient disk space
    - corrupted archives
    - expired retention rules

Bash testing can use frameworks, shell assertions, temporary directories,
or simple command-level tests depending on project size.
"""
    )


# ---------------------------------------------------------------------------
# Production architecture
# ---------------------------------------------------------------------------

def demonstrate_production_architecture() -> None:
    heading("22. Production automation architecture")

    print(
        """
A mature automation script can be structured as:

    configuration
        |
        v
    validation
        |
        v
    logging
        |
        v
    acquire lock
        |
        v
    pre-flight checks
        |
        v
    execute operation
        |
        +---- failure ---> rollback / cleanup / alert
        |
        v
    verification
        |
        v
    release resources
        |
        v
    exit status

Useful production properties include:

    - deterministic behavior
    - idempotency
    - observability
    - bounded retries
    - clear exit codes
    - safe cleanup
    - least privilege
    - configuration validation
    - testability
    - restoration procedures
"""
    )


# ---------------------------------------------------------------------------
# Demonstration runner
# ---------------------------------------------------------------------------

def run_course() -> None:
    heading("BASH AUTOMATION: COMPLETE PRACTICAL STUDY")

    explain_shell_concept()

    with tempfile.TemporaryDirectory(prefix="bash_automation_") as temporary:
        root = Path(temporary)

        create_demo_tree(root)

        demonstrate_process_execution()
        demonstrate_file_discovery(root)
        demonstrate_filtering(root)
        demonstrate_backup(root)
        demonstrate_cleanup(root)
        demonstrate_archiving(root)
        demonstrate_logging(root)
        demonstrate_idempotency(root)
        demonstrate_configuration(root)
        demonstrate_dry_run(root)
        demonstrate_disk_usage(root)
        demonstrate_integrity(root)
        demonstrate_retry()
        demonstrate_scheduling()
        demonstrate_process_safety()
        demonstrate_locking()
        demonstrate_security()
        demonstrate_performance()
        demonstrate_strict_mode()
        demonstrate_testing(root)
        demonstrate_production_architecture()

    heading("Executable study completed")
    print(
        """
The temporary demonstration environment has been removed automatically.

The central Bash automation model is:

    validate -> execute -> verify -> log -> recover

For destructive operations, safety and verification are part of the
implementation rather than optional documentation.
"""
    )


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Interactive executable study companion for Bash automation."
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Reserved for compatibility; the educational demonstrations remain visible.",
    )
    return parser.parse_args()


def main() -> int:
    parse_arguments()

    try:
        run_course()
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted by user.", file=sys.stderr)
        return 130
    except Exception as error:
        print(f"Automation study failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
