#!/usr/bin/env python3
"""
Bash DevOps Scripts: Deployment, Health Checks, and Log Processing

This standalone Python study file teaches the design principles behind Bash
DevOps automation while providing executable Python implementations of the
same operational ideas.

The Bash-oriented concepts covered are:

- Shell scripting fundamentals
- Variables and quoting
- Exit codes
- Functions
- Arguments
- Environment variables
- Command substitution
- Pipes and redirection
- Standard input/output/error
- Conditional execution
- Loops
- Defensive shell scripting
- set -e, set -u, set -o pipefail
- Traps and cleanup
- Temporary files
- Deployment workflows
- Atomic deployment patterns
- Health checks
- HTTP-style health checks
- Process health checks
- Log filtering
- Log aggregation
- Error counting
- Time-window processing
- Rotation concepts
- Idempotency
- Retry logic
- Timeouts
- Locking concepts
- Configuration validation
- Observability
- Security considerations
- Performance considerations
- Production-oriented script design

The Python implementations deliberately use only the standard library.
They model several operations that Bash scripts commonly perform so that the
underlying DevOps concepts can be studied without requiring a particular
Linux distribution or production server.
"""

from __future__ import annotations

import argparse
import contextlib
import dataclasses
import datetime as dt
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import textwrap
import time
from pathlib import Path
from typing import Callable, Iterable, Iterator, Sequence


# ---------------------------------------------------------------------------
# Section 1: Core terminology
# ---------------------------------------------------------------------------

def explain_core_terms() -> None:
    terms = {
        "Shell": "A command interpreter. Bash is one widely used Unix shell.",
        "Script": "A text file containing commands and control logic executed by a shell.",
        "Exit status": "An integer returned by a command. Conventionally 0 means success.",
        "STDIN": "Standard input stream.",
        "STDOUT": "Standard output stream.",
        "STDERR": "Standard error stream.",
        "Pipe": "A mechanism that connects one command's output to another command's input.",
        "Redirection": "Sending command input or output to files or other streams.",
        "Environment variable": "A process environment value inherited by child processes.",
        "Health check": "An automated test that determines whether a service is functioning.",
        "Deployment": "The controlled process of releasing application artifacts to an environment.",
        "Idempotency": "Running an operation repeatedly produces the same intended final state.",
        "Rollback": "Returning a deployment to a known previous version.",
        "Log processing": "Filtering, parsing, aggregating, and analyzing operational logs.",
        "Trap": "A shell mechanism for executing cleanup or recovery logic when signals/events occur.",
        "Atomic operation": "An operation designed to expose either the old state or the new state, not a partial state.",
    }

    print("\n=== Core DevOps Shell Terminology ===")
    for term, definition in terms.items():
        print(f"{term:22} {definition}")


# ---------------------------------------------------------------------------
# Section 2: Exit codes and command results
# ---------------------------------------------------------------------------

def simulate_exit_status(success: bool) -> int:
    """Model the most important shell convention: zero means success."""
    return 0 if success else 1


def demonstrate_exit_codes() -> None:
    print("\n=== Exit Codes ===")

    successful_status = simulate_exit_status(True)
    failed_status = simulate_exit_status(False)

    print(f"Successful command status: {successful_status}")
    print(f"Failed command status:     {failed_status}")

    if successful_status == 0:
        print("A shell script can treat status 0 as success.")

    if failed_status != 0:
        print("A shell script can branch when a command returns non-zero.")


# ---------------------------------------------------------------------------
# Section 3: Environment variables and configuration
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class DeploymentConfig:
    application: str
    environment: str
    version: str
    release_root: Path
    health_url: str
    health_timeout_seconds: float
    retries: int


def load_configuration() -> DeploymentConfig:
    """
    Read configuration from environment variables.

    Bash equivalent concept:

        APP_NAME="${APP_NAME:-example-app}"
        ENVIRONMENT="${ENVIRONMENT:-staging}"

    The Python implementation uses os.environ and defaults.
    """
    application = os.environ.get("APP_NAME", "example-app")
    environment = os.environ.get("DEPLOY_ENV", "development")
    version = os.environ.get("APP_VERSION", "1.0.0")
    release_root = Path(os.environ.get("RELEASE_ROOT", "./releases"))
    health_url = os.environ.get("HEALTH_URL", "http://127.0.0.1:8080/health")

    try:
        timeout = float(os.environ.get("HEALTH_TIMEOUT", "3"))
    except ValueError:
        timeout = 3.0

    try:
        retries = int(os.environ.get("HEALTH_RETRIES", "3"))
    except ValueError:
        retries = 3

    return DeploymentConfig(
        application=application,
        environment=environment,
        version=version,
        release_root=release_root,
        health_url=health_url,
        health_timeout_seconds=max(0.1, timeout),
        retries=max(1, retries),
    )


def validate_configuration(config: DeploymentConfig) -> list[str]:
    """Validate deployment configuration before making changes."""
    errors: list[str] = []

    if not config.application.strip():
        errors.append("Application name cannot be empty.")

    if not re.fullmatch(r"[A-Za-z0-9._-]+", config.application):
        errors.append("Application name contains unsafe characters.")

    if not config.environment.strip():
        errors.append("Deployment environment cannot be empty.")

    if not re.fullmatch(r"[A-Za-z0-9._-]+", config.environment):
        errors.append("Deployment environment contains unsafe characters.")

    if not re.fullmatch(r"[A-Za-z0-9._+-]+", config.version):
        errors.append("Version contains unsupported characters.")

    if config.health_timeout_seconds <= 0:
        errors.append("Health timeout must be positive.")

    if config.retries < 1:
        errors.append("Retry count must be at least one.")

    return errors


# ---------------------------------------------------------------------------
# Section 4: Safe subprocess execution
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class CommandResult:
    command: list[str]
    return_code: int
    stdout: str
    stderr: str
    duration_seconds: float


def run_command(
    command: Sequence[str],
    *,
    timeout: float | None = None,
    cwd: Path | None = None,
    environment: dict[str, str] | None = None,
) -> CommandResult:
    """
    Execute a command without invoking a shell.

    This is an important security pattern.

    Unsafe conceptual pattern:
        shell=True with user-controlled text

    Safer pattern:
        provide an argument list and execute the program directly.

    Bash scripts should also quote variables carefully instead of constructing
    arbitrary command strings from untrusted input.
    """
    start = time.monotonic()

    try:
        completed = subprocess.run(
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
            env=environment,
            check=False,
        )
        return CommandResult(
            command=list(command),
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
            duration_seconds=time.monotonic() - start,
        )
    except subprocess.TimeoutExpired as exc:
        return CommandResult(
            command=list(command),
            return_code=124,
            stdout=exc.stdout or "",
            stderr=(
                (exc.stderr or "")
                + "\nCommand timed out."
            ),
            duration_seconds=time.monotonic() - start,
        )
    except OSError as exc:
        return CommandResult(
            command=list(command),
            return_code=127,
            stdout="",
            stderr=str(exc),
            duration_seconds=time.monotonic() - start,
        )


def demonstrate_command_execution() -> None:
    print("\n=== Command Execution ===")

    if os.name == "nt":
        command = ["cmd", "/c", "echo", "Hello from a subprocess"]
    else:
        command = ["printf", "%s\n", "Hello from a subprocess"]

    result = run_command(command)

    print("Command:", " ".join(result.command))
    print("Return code:", result.return_code)
    print("STDOUT:", result.stdout.strip())
    if result.stderr.strip():
        print("STDERR:", result.stderr.strip())
    print(f"Duration: {result.duration_seconds:.6f}s")


# ---------------------------------------------------------------------------
# Section 5: Pipes and data processing
# ---------------------------------------------------------------------------

SAMPLE_LOGS = [
    "2026-09-19T10:00:01Z INFO api request completed status=200 latency_ms=31",
    "2026-09-19T10:00:02Z INFO api request completed status=200 latency_ms=22",
    "2026-09-19T10:00:03Z WARN api request slow status=200 latency_ms=820",
    "2026-09-19T10:00:04Z ERROR database connection failed status=503 latency_ms=0",
    "2026-09-19T10:00:05Z INFO api request completed status=201 latency_ms=45",
    "2026-09-19T10:00:06Z ERROR database connection failed status=503 latency_ms=0",
    "2026-09-19T10:00:07Z INFO api request completed status=200 latency_ms=27",
    "2026-09-19T10:00:08Z WARN api request slow status=200 latency_ms=700",
    "2026-09-19T10:00:09Z INFO api request completed status=200 latency_ms=19",
]


def iter_lines(lines: Iterable[str]) -> Iterator[str]:
    """Model a Unix pipeline by lazily passing one line at a time."""
    for line in lines:
        yield line.rstrip("\n")


def filter_log_level(lines: Iterable[str], level: str) -> Iterator[str]:
    level = level.upper()
    for line in lines:
        parts = line.split()
        if len(parts) >= 2 and parts[1].upper() == level:
            yield line


def extract_status_codes(lines: Iterable[str]) -> Iterator[int]:
    pattern = re.compile(r"\bstatus=(\d{3})\b")

    for line in lines:
        match = pattern.search(line)
        if match:
            yield int(match.group(1))


def demonstrate_pipeline() -> None:
    print("\n=== Log Pipeline ===")

    # A conceptual Bash pipeline might look like:
    #
    #   cat application.log | grep "ERROR" | grep -o "status=[0-9]*"
    #
    # A production script can often omit cat and use:
    #
    #   grep "ERROR" application.log | grep -o "status=[0-9]*"
    #
    # Python generators provide similar lazy processing semantics.

    error_lines = filter_log_level(iter_lines(SAMPLE_LOGS), "ERROR")
    status_codes = list(extract_status_codes(error_lines))

    print("Error status codes:", status_codes)


# ---------------------------------------------------------------------------
# Section 6: Log parsing and aggregation
# ---------------------------------------------------------------------------

@dataclasses.dataclass
class LogStatistics:
    total: int = 0
    info: int = 0
    warnings: int = 0
    errors: int = 0
    status_counts: dict[int, int] = dataclasses.field(default_factory=dict)
    latency_values: list[float] = dataclasses.field(default_factory=list)

    @property
    def error_rate(self) -> float:
        return self.errors / self.total if self.total else 0.0

    @property
    def average_latency(self) -> float:
        if not self.latency_values:
            return 0.0
        return sum(self.latency_values) / len(self.latency_values)


def parse_logs(lines: Iterable[str]) -> LogStatistics:
    statistics = LogStatistics()

    level_pattern = re.compile(r"\s(INFO|WARN|ERROR)\s")
    status_pattern = re.compile(r"\bstatus=(\d{3})\b")
    latency_pattern = re.compile(r"\blatency_ms=(\d+(?:\.\d+)?)\b")

    for line in lines:
        statistics.total += 1

        level_match = level_pattern.search(line)
        if level_match:
            level = level_match.group(1)
            if level == "INFO":
                statistics.info += 1
            elif level == "WARN":
                statistics.warnings += 1
            elif level == "ERROR":
                statistics.errors += 1

        status_match = status_pattern.search(line)
        if status_match:
            status = int(status_match.group(1))
            statistics.status_counts[status] = (
                statistics.status_counts.get(status, 0) + 1
            )

        latency_match = latency_pattern.search(line)
        if latency_match:
            statistics.latency_values.append(float(latency_match.group(1)))

    return statistics


def print_log_statistics(statistics: LogStatistics) -> None:
    print(f"Total records:    {statistics.total}")
    print(f"INFO records:     {statistics.info}")
    print(f"WARN records:     {statistics.warnings}")
    print(f"ERROR records:    {statistics.errors}")
    print(f"Error rate:       {statistics.error_rate:.2%}")
    print(f"Average latency:  {statistics.average_latency:.2f} ms")
    print("Status counts:    ", statistics.status_counts)


# ---------------------------------------------------------------------------
# Section 7: Deployment artifact management
# ---------------------------------------------------------------------------

@dataclasses.dataclass(frozen=True)
class Release:
    version: str
    path: Path


class ReleaseManager:
    """
    Model a filesystem-based deployment layout:

        releases/
            1.0.0/
            1.1.0/
            current -> 1.1.0

    The real Bash equivalent would typically use mkdir, cp, ln, mv and rm.

    The implementation keeps the release structure explicit so the same
    design can be understood independently of a particular deployment tool.
    """

    def __init__(self, root: Path):
        self.root = root

    @property
    def current_link(self) -> Path:
        return self.root / "current"

    def initialize(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def release_path(self, version: str) -> Path:
        return self.root / version

    def create_release(self, version: str, files: dict[str, str]) -> Release:
        target = self.release_path(version)

        if target.exists():
            raise FileExistsError(
                f"Release {version!r} already exists. "
                "This protects against accidental overwrite."
            )

        target.mkdir(parents=True)

        for relative_name, content in files.items():
            relative_path = Path(relative_name)

            # Reject absolute paths and traversal outside the release directory.
            if relative_path.is_absolute() or ".." in relative_path.parts:
                raise ValueError(
                    f"Unsafe release path: {relative_name!r}"
                )

            destination = target / relative_path
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(content, encoding="utf-8")

        return Release(version=version, path=target)

    def activate(self, version: str) -> None:
        """
        Switch the active release.

        A production Unix deployment often uses a symbolic link and an atomic
        rename to make the switch very small and predictable.
        """
        target = self.release_path(version)

        if not target.is_dir():
            raise FileNotFoundError(f"Release does not exist: {target}")

        temporary_link = self.root / ".current.tmp"

        if temporary_link.exists() or temporary_link.is_symlink():
            temporary_link.unlink()

        temporary_link.symlink_to(target, target_is_directory=True)

        os.replace(temporary_link, self.current_link)

    def current_version(self) -> str | None:
        if not self.current_link.exists():
            return None

        resolved = self.current_link.resolve()
        return resolved.name


def demonstrate_release_manager() -> None:
    print("\n=== Deployment Release Manager ===")

    with tempfile.TemporaryDirectory(prefix="bash-devops-") as temporary_directory:
        manager = ReleaseManager(Path(temporary_directory) / "releases")
        manager.initialize()

        manager.create_release(
            "1.0.0",
            {
                "VERSION": "1.0.0\n",
                "app/config.txt": "environment=staging\n",
            },
        )

        manager.create_release(
            "1.1.0",
            {
                "VERSION": "1.1.0\n",
                "app/config.txt": "environment=staging\n",
            },
        )

        manager.activate("1.0.0")
        print("Current version:", manager.current_version())

        manager.activate("1.1.0")
        print("Current version:", manager.current_version())

        # The old release remains available, which enables rollback.
        manager.activate("1.0.0")
        print("Rolled back to:", manager.current_version())


# ---------------------------------------------------------------------------
# Section 8: Health checks
# ---------------------------------------------------------------------------

def tcp_health_check(host: str, port: int, timeout: float = 2.0) -> bool:
    """
    Check whether a TCP endpoint accepts a connection.

    This is intentionally implemented using the standard library.

    Bash often delegates this responsibility to tools such as curl, nc,
    timeout, systemctl, or application-specific commands.
    """
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def command_health_check(
    command: Sequence[str],
    timeout: float = 3.0,
) -> bool:
    result = run_command(command, timeout=timeout)
    return result.return_code == 0


def retry(
    operation: Callable[[], bool],
    attempts: int,
    delay_seconds: float,
) -> bool:
    """
    Generic retry implementation.

    Retrying can be appropriate for transient failures but should not hide
    deterministic configuration errors.
    """
    attempts = max(1, attempts)

    for attempt in range(1, attempts + 1):
        if operation():
            return True

        if attempt < attempts:
            time.sleep(max(0.0, delay_seconds))

    return False


def demonstrate_health_checks() -> None:
    print("\n=== Health Checks ===")

    command = (
        ["cmd", "/c", "exit", "0"]
        if os.name == "nt"
        else ["sh", "-c", "exit 0"]
    )

    healthy = retry(
        lambda: command_health_check(command),
        attempts=3,
        delay_seconds=0.1,
    )

    print("Command health:", "healthy" if healthy else "unhealthy")

    # A TCP check against a deliberately unlikely local port demonstrates
    # failure handling without contacting an external service.
    tcp_result = tcp_health_check("127.0.0.1", 65534, timeout=0.1)
    print("TCP test endpoint:", "reachable" if tcp_result else "unreachable")


# ---------------------------------------------------------------------------
# Section 9: Deployment state machine
# ---------------------------------------------------------------------------

class DeploymentState:
    CREATED = "created"
    VALIDATED = "validated"
    STAGED = "staged"
    ACTIVATED = "activated"
    HEALTHY = "healthy"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


@dataclasses.dataclass
class DeploymentRecord:
    application: str
    version: str
    environment: str
    state: str = DeploymentState.CREATED
    started_at: str = dataclasses.field(
        default_factory=lambda: dt.datetime.now(dt.timezone.utc).isoformat()
    )
    error: str | None = None


class DeploymentEngine:
    """
    A small deployment state machine.

    The important idea is that deployment is a sequence of observable states,
    not one enormous shell command.
    """

    def __init__(self, manager: ReleaseManager):
        self.manager = manager

    def deploy(
        self,
        config: DeploymentConfig,
        *,
        files: dict[str, str],
        health_check: Callable[[], bool],
    ) -> DeploymentRecord:
        record = DeploymentRecord(
            application=config.application,
            version=config.version,
            environment=config.environment,
        )

        errors = validate_configuration(config)
        if errors:
            record.state = DeploymentState.FAILED
            record.error = "; ".join(errors)
            return record

        record.state = DeploymentState.VALIDATED

        previous_version = self.manager.current_version()

        try:
            self.manager.create_release(config.version, files)
            record.state = DeploymentState.STAGED

            self.manager.activate(config.version)
            record.state = DeploymentState.ACTIVATED

            if health_check():
                record.state = DeploymentState.HEALTHY
                return record

            raise RuntimeError("Post-deployment health check failed.")

        except Exception as exc:
            record.state = DeploymentState.FAILED
            record.error = str(exc)

            if previous_version is not None:
                try:
                    self.manager.activate(previous_version)
                    record.state = DeploymentState.ROLLED_BACK
                except Exception as rollback_error:
                    record.error += (
                        f" Rollback also failed: {rollback_error}"
                    )

            return record


def demonstrate_deployment_engine() -> None:
    print("\n=== Deployment State Machine ===")

    with tempfile.TemporaryDirectory(prefix="deployment-engine-") as temporary:
        manager = ReleaseManager(Path(temporary) / "releases")
        manager.initialize()

        manager.create_release(
            "2.0.0",
            {"VERSION": "2.0.0\n"},
        )
        manager.activate("2.0.0")

        engine = DeploymentEngine(manager)

        successful = engine.deploy(
            DeploymentConfig(
                application="inventory-api",
                environment="staging",
                version="2.1.0",
                release_root=manager.root,
                health_url="internal://health",
                health_timeout_seconds=1,
                retries=2,
            ),
            files={"VERSION": "2.1.0\n"},
            health_check=lambda: True,
        )

        print(
            json.dumps(
                dataclasses.asdict(successful),
                indent=2,
            )
        )

        failed = engine.deploy(
            DeploymentConfig(
                application="inventory-api",
                environment="staging",
                version="2.2.0",
                release_root=manager.root,
                health_url="internal://health",
                health_timeout_seconds=1,
                retries=2,
            ),
            files={"VERSION": "2.2.0\n"},
            health_check=lambda: False,
        )

        print(
            json.dumps(
                dataclasses.asdict(failed),
                indent=2,
            )
        )
        print("Active version after failure:", manager.current_version())


# ---------------------------------------------------------------------------
# Section 10: Idempotency
# ---------------------------------------------------------------------------

def ensure_directory(path: Path) -> None:
    """
    Idempotent filesystem operation.

    Calling mkdir(..., exist_ok=True) repeatedly reaches the same desired
    state: the directory exists.
    """
    path.mkdir(parents=True, exist_ok=True)


def demonstrate_idempotency() -> None:
    print("\n=== Idempotency ===")

    with tempfile.TemporaryDirectory(prefix="idempotency-") as temporary:
        directory = Path(temporary) / "application" / "logs"

        ensure_directory(directory)
        ensure_directory(directory)
        ensure_directory(directory)

        print("Directory exists after repeated operations:", directory.is_dir())


# ---------------------------------------------------------------------------
# Section 11: Cleanup and signal handling
# ---------------------------------------------------------------------------

class TemporaryWorkspace:
    """
    Context-manager equivalent of a Bash trap-based cleanup pattern.

    Bash often uses:

        temp_dir="$(mktemp -d)"
        trap 'rm -rf "$temp_dir"' EXIT

    The important property is cleanup even when the main operation exits.
    """

    def __init__(self) -> None:
        self.path: Path | None = None

    def __enter__(self) -> Path:
        self.path = Path(tempfile.mkdtemp(prefix="devops-work-"))
        return self.path

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        if self.path is not None:
            shutil.rmtree(self.path, ignore_errors=True)


def demonstrate_cleanup() -> None:
    print("\n=== Temporary Workspace Cleanup ===")

    with TemporaryWorkspace() as workspace:
        marker = workspace / "deployment.marker"
        marker.write_text("temporary state\n", encoding="utf-8")
        print("Temporary workspace created:", workspace)
        print("Marker exists:", marker.exists())

    print("Workspace exists after cleanup:", workspace.exists())


# ---------------------------------------------------------------------------
# Section 12: Structured logs
# ---------------------------------------------------------------------------

def parse_json_logs(lines: Iterable[str]) -> list[dict]:
    records: list[dict] = []

    for line_number, line in enumerate(lines, start=1):
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue

        if isinstance(value, dict):
            value["_line_number"] = line_number
            records.append(value)

    return records


def demonstrate_json_log_processing() -> None:
    print("\n=== Structured JSON Log Processing ===")

    lines = [
        '{"level":"INFO","service":"api","status":200,"latency_ms":31}',
        '{"level":"ERROR","service":"db","status":503,"latency_ms":0}',
        '{"level":"WARN","service":"api","status":200,"latency_ms":810}',
        "this is not valid JSON",
        '{"level":"ERROR","service":"api","status":500,"latency_ms":120}',
    ]

    records = parse_json_logs(lines)
    error_records = [
        record for record in records
        if record.get("level") == "ERROR"
    ]

    print("Valid JSON records:", len(records))
    print("Error records:", len(error_records))

    for record in error_records:
        print(
            f"line={record['_line_number']} "
            f"service={record.get('service')} "
            f"status={record.get('status')}"
        )


# ---------------------------------------------------------------------------
# Section 13: Log rotation concepts
# ---------------------------------------------------------------------------

def rotate_log_files(
    log_path: Path,
    *,
    generations: int = 3,
) -> None:
    """
    Simple rotation model.

    Real production rotation should account for open file descriptors,
    compression, retention policies, concurrent writers, and system tooling.
    """
    if generations < 1:
        raise ValueError("generations must be at least one")

    if not log_path.exists():
        return

    for generation in range(generations, 0, -1):
        source = (
            log_path
            if generation == 1
            else Path(f"{log_path}.{generation - 1}")
        )
        destination = Path(f"{log_path}.{generation}")

        if source.exists():
            if destination.exists():
                destination.unlink()
            source.rename(destination)

    log_path.touch()


def demonstrate_log_rotation() -> None:
    print("\n=== Log Rotation ===")

    with tempfile.TemporaryDirectory(prefix="rotation-") as temporary:
        log_path = Path(temporary) / "application.log"

        log_path.write_text(
            "first generation\n",
            encoding="utf-8",
        )
        rotate_log_files(log_path, generations=3)

        log_path.write_text(
            "second generation\n",
            encoding="utf-8",
        )
        rotate_log_files(log_path, generations=3)

        for path in sorted(Path(temporary).glob("application.log*")):
            print(path.name, "=>", path.read_text(encoding="utf-8").strip())


# ---------------------------------------------------------------------------
# Section 14: Performance considerations
# ---------------------------------------------------------------------------

def count_lines_streaming(path: Path) -> int:
    """
    Stream a file instead of reading it completely into memory.

    This corresponds to the Unix philosophy of processing streams with tools
    such as grep, awk, sed, cut and sort.
    """
    count = 0

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for _ in handle:
            count += 1

    return count


def demonstrate_streaming() -> None:
    print("\n=== Streaming Log Processing ===")

    with tempfile.TemporaryDirectory(prefix="streaming-") as temporary:
        path = Path(temporary) / "large.log"

        with path.open("w", encoding="utf-8") as handle:
            for number in range(10_000):
                handle.write(
                    f"2026-09-19T10:00:00Z INFO record={number}\n"
                )

        print("Line count:", count_lines_streaming(path))


# ---------------------------------------------------------------------------
# Section 15: Security validation
# ---------------------------------------------------------------------------

def safe_filename(filename: str) -> bool:
    """
    Validate a filename before using it in a filesystem operation.

    Security principle:
    never assume input is safe merely because it came from an environment
    variable, command-line argument, CI variable, or configuration file.
    """
    if not filename:
        return False

    path = Path(filename)

    if path.is_absolute():
        return False

    if ".." in path.parts:
        return False

    return bool(re.fullmatch(r"[A-Za-z0-9._-]+", filename))


def demonstrate_security_validation() -> None:
    print("\n=== Security Validation ===")

    candidates = [
        "application.log",
        "release-1.2.0.tar.gz",
        "../secret.txt",
        "/etc/passwd",
        "hello;rm -rf /",
        "",
    ]

    for candidate in candidates:
        print(
            f"{candidate!r:24} -> "
            f"{'accepted' if safe_filename(candidate) else 'rejected'}"
        )


# ---------------------------------------------------------------------------
# Section 16: Bash script templates as data
# ---------------------------------------------------------------------------

BASH_DEPLOYMENT_TEMPLATE = r'''#!/usr/bin/env bash
set -Eeuo pipefail

APP_NAME="${APP_NAME:-example-app}"
VERSION="${VERSION:?VERSION is required}"
RELEASE_ROOT="${RELEASE_ROOT:-/opt/example-app/releases}"
HEALTH_URL="${HEALTH_URL:-http://127.0.0.1:8080/health}"

log() {
    printf '%s %s\n' "$(date -Is)" "$*"
}

die() {
    log "ERROR: $*"
    exit 1
}

cleanup() {
    local status=$?
    if (( status != 0 )); then
        log "Deployment failed with status ${status}"
    fi
}
trap cleanup EXIT

[[ "$VERSION" =~ ^[A-Za-z0-9._+-]+$ ]] || die "Invalid version"

release_dir="${RELEASE_ROOT}/${VERSION}"
mkdir -p "$release_dir"

printf '%s\n' "$VERSION" > "${release_dir}/VERSION"

ln -sfn "$release_dir" "${RELEASE_ROOT}/current"

curl --fail --silent --show-error \
    --max-time 5 \
    "$HEALTH_URL" >/dev/null \
    || die "Health check failed"

log "Deployment completed: ${APP_NAME} ${VERSION}"
'''


BASH_HEALTH_CHECK_TEMPLATE = r'''#!/usr/bin/env bash
set -Eeuo pipefail

URL="${1:?Usage: health-check.sh URL}"
TIMEOUT="${TIMEOUT:-5}"
ATTEMPTS="${ATTEMPTS:-3}"

for ((attempt=1; attempt<=ATTEMPTS; attempt++)); do
    if curl --fail --silent --show-error \
        --max-time "$TIMEOUT" \
        "$URL" >/dev/null; then
        printf 'healthy\n'
        exit 0
    fi

    printf 'health check attempt %d failed\n' "$attempt" >&2
    sleep 1
done

printf 'unhealthy\n' >&2
exit 1
'''


BASH_LOG_PROCESSING_TEMPLATE = r'''#!/usr/bin/env bash
set -Eeuo pipefail

LOG_FILE="${1:?Usage: log-report.sh LOG_FILE}"

[[ -r "$LOG_FILE" ]] || {
    printf 'Log file is not readable: %s\n' "$LOG_FILE" >&2
    exit 1
}

printf 'Total lines: '
wc -l < "$LOG_FILE"

printf 'ERROR lines: '
grep -c ' ERROR ' "$LOG_FILE" || true

printf '5xx responses: '
grep -oE 'status=5[0-9]{2}' "$LOG_FILE" \
    | sort \
    | uniq -c \
    | awk '{total += $1} END {print total + 0}'

printf '\nError summary:\n'
grep ' ERROR ' "$LOG_FILE" || true
'''


def demonstrate_bash_patterns() -> None:
    print("\n=== Bash Script Patterns ===")

    print("\n--- Deployment pattern ---")
    print(BASH_DEPLOYMENT_TEMPLATE)

    print("\n--- Health-check pattern ---")
    print(BASH_HEALTH_CHECK_TEMPLATE)

    print("\n--- Log-processing pattern ---")
    print(BASH_LOG_PROCESSING_TEMPLATE)


# ---------------------------------------------------------------------------
# Section 17: Common mistakes
# ---------------------------------------------------------------------------

def explain_common_mistakes() -> None:
    mistakes = [
        (
            "Unquoted variables",
            'rm -rf $TARGET',
            'rm -rf -- "$TARGET"',
            "Word splitting and wildcard expansion can change the intended arguments.",
        ),
        (
            "Ignoring exit codes",
            "deploy_command",
            "deploy_command || die 'deployment failed'",
            "A failed command can otherwise be followed by apparently successful work.",
        ),
        (
            "Unsafe shell construction",
            'sh -c "tool $USER_INPUT"',
            "Use direct arguments and strict validation.",
            "Untrusted input can become shell syntax.",
        ),
        (
            "Parsing ls output",
            "ls | while read file; do ...",
            "Use find, globbing, or null-delimited records where appropriate.",
            "Filenames can contain whitespace and unusual characters.",
        ),
        (
            "No timeout",
            "curl URL",
            "curl --fail --max-time 5 URL",
            "A deployment can hang indefinitely when a dependency is unavailable.",
        ),
        (
            "No cleanup",
            "mkdir temporary-directory",
            "Create a temporary directory and clean it with trap.",
            "Interrupted scripts can leave stale state.",
        ),
        (
            "Non-idempotent deployment",
            "Always overwrite the active deployment directly.",
            "Stage, validate, activate, health-check, and retain rollback state.",
            "Partial deployments are harder to recover safely.",
        ),
    ]

    print("\n=== Common Bash DevOps Mistakes ===")
    for name, bad, better, consequence in mistakes:
        print(f"\n{name}")
        print(f"  Risky:   {bad}")
        print(f"  Better:  {better}")
        print(f"  Reason:  {consequence}")


# ---------------------------------------------------------------------------
# Section 18: Testing operational code
# ---------------------------------------------------------------------------

def assert_equal(expected, actual, message: str = "") -> None:
    if expected != actual:
        raise AssertionError(
            message or f"Expected {expected!r}, got {actual!r}"
        )


def run_self_tests() -> None:
    print("\n=== Self Tests ===")

    assert_equal(0, simulate_exit_status(True))
    assert_equal(1, simulate_exit_status(False))

    stats = parse_logs(SAMPLE_LOGS)
    assert_equal(9, stats.total)
    assert_equal(2, stats.errors)
    assert_equal(2, stats.warnings)
    assert_equal(200, stats.status_counts[200])

    assert safe_filename("app.log")
    assert not safe_filename("../app.log")
    assert not safe_filename("/etc/passwd")

    with tempfile.TemporaryDirectory(prefix="test-release-") as temporary:
        manager = ReleaseManager(Path(temporary) / "releases")
        manager.initialize()
        manager.create_release("1.0.0", {"VERSION": "1.0.0"})
        manager.activate("1.0.0")
        assert_equal("1.0.0", manager.current_version())

    print("All self tests passed.")


# ---------------------------------------------------------------------------
# Section 19: CLI
# ---------------------------------------------------------------------------

def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Bash DevOps scripting study lab covering deployment, "
            "health checks, and log processing."
        )
    )

    parser.add_argument(
        "--topic",
        choices=[
            "terms",
            "exit-codes",
            "commands",
            "pipeline",
            "logs",
            "deployment",
            "health",
            "idempotency",
            "cleanup",
            "json-logs",
            "rotation",
            "streaming",
            "security",
            "bash-patterns",
            "mistakes",
            "tests",
            "all",
        ],
        default="all",
        help="Select a demonstration.",
    )

    return parser


def run_topic(topic: str) -> None:
    demonstrations: dict[str, Callable[[], None]] = {
        "terms": explain_core_terms,
        "exit-codes": demonstrate_exit_codes,
        "commands": demonstrate_command_execution,
        "pipeline": demonstrate_pipeline,
        "logs": lambda: print_log_statistics(parse_logs(SAMPLE_LOGS)),
        "deployment": demonstrate_deployment_engine,
        "health": demonstrate_health_checks,
        "idempotency": demonstrate_idempotency,
        "cleanup": demonstrate_cleanup,
        "json-logs": demonstrate_json_log_processing,
        "rotation": demonstrate_log_rotation,
        "streaming": demonstrate_streaming,
        "security": demonstrate_security_validation,
        "bash-patterns": demonstrate_bash_patterns,
        "mistakes": explain_common_mistakes,
        "tests": run_self_tests,
    }

    if topic == "all":
        for demonstration in demonstrations.values():
            demonstration()
        return

    demonstrations[topic]()


def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    try:
        run_topic(args.topic)
        return 0
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    main()
