#!/usr/bin/env python3
"""
GitHub Actions Runner Laboratory

A self-contained executable model of GitHub Actions runner architecture.

The program progresses from the basic idea of a runner, through hosted and
self-hosted execution, to labels, routing, queues, isolation, lifecycle
management, capacity, security boundaries, failure handling, and workflow
scheduling.

No external packages are required.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from collections import deque
from datetime import datetime, timezone
import json
import platform
import random
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Callable, Iterable, Optional


class RunnerKind(str, Enum):
    HOSTED = "github-hosted"
    SELF_HOSTED = "self-hosted"


class RunnerState(str, Enum):
    OFFLINE = "offline"
    IDLE = "idle"
    BUSY = "busy"
    DRAINING = "draining"


class JobState(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class RunnerImage:
    """Describes the operating-system image/environment used by a runner."""

    name: str
    operating_system: str
    architecture: str
    preinstalled_tools: frozenset[str]
    ephemeral: bool = True

    def supports(self, required_tools: set[str]) -> bool:
        return required_tools.issubset(self.preinstalled_tools)


@dataclass
class WorkflowJob:
    """A simplified representation of a GitHub Actions job."""

    name: str
    labels: set[str]
    duration_seconds: float = 0.1
    required_tools: set[str] = field(default_factory=set)
    secrets_required: bool = False
    state: JobState = JobState.QUEUED
    assigned_runner: Optional[str] = None
    failure_reason: Optional[str] = None

    def requires(self, label: str) -> bool:
        return label in self.labels


@dataclass
class Runner:
    """
    Models the scheduling properties of a runner.

    Labels are intentionally explicit. A runner can advertise capabilities
    such as "linux", "x64", "docker", or "gpu", allowing a job to target
    compatible execution infrastructure.
    """

    name: str
    kind: RunnerKind
    labels: set[str]
    image: RunnerImage
    state: RunnerState = RunnerState.IDLE
    group: str = "default"
    online: bool = True
    busy_job: Optional[str] = None
    persistent_workspace: bool = False
    trusted: bool = False

    def can_run(self, job: WorkflowJob) -> tuple[bool, str]:
        if not self.online or self.state in {
            RunnerState.OFFLINE,
            RunnerState.DRAINING,
        }:
            return False, "runner is unavailable"

        if self.state != RunnerState.IDLE:
            return False, "runner is not idle"

        if not job.labels.issubset(self.labels):
            missing = sorted(job.labels - self.labels)
            return False, f"missing labels: {', '.join(missing)}"

        if not self.image.supports(job.required_tools):
            missing = sorted(job.required_tools - self.image.preinstalled_tools)
            return False, f"missing tools: {', '.join(missing)}"

        return True, "compatible"


class RunnerRegistry:
    """Stores runners and performs deterministic label-based routing."""

    def __init__(self) -> None:
        self.runners: dict[str, Runner] = {}

    def register(self, runner: Runner) -> None:
        if runner.name in self.runners:
            raise ValueError(f"runner already registered: {runner.name}")
        self.runners[runner.name] = runner

    def route(self, job: WorkflowJob) -> tuple[Optional[Runner], list[str]]:
        diagnostics: list[str] = []

        # GitHub Actions routing is capability-oriented: the job's requested
        # labels constrain which runners can receive it.
        for runner in self.runners.values():
            compatible, reason = runner.can_run(job)
            diagnostics.append(f"{runner.name}: {reason}")
            if compatible:
                return runner, diagnostics

        return None, diagnostics

    def online_runners(self) -> list[Runner]:
        return [
            runner
            for runner in self.runners.values()
            if runner.online and runner.state != RunnerState.OFFLINE
        ]


class RunnerPool:
    """
    Models a runner fleet with queueing and execution.

    A real Actions service performs orchestration outside the runner process.
    This class focuses on the architectural relationship between jobs and
    available execution agents.
    """

    def __init__(self, registry: RunnerRegistry) -> None:
        self.registry = registry
        self.queue: deque[WorkflowJob] = deque()
        self.completed: list[WorkflowJob] = []

    def submit(self, job: WorkflowJob) -> None:
        if job.state != JobState.QUEUED:
            raise ValueError("only queued jobs can be submitted")
        self.queue.append(job)

    def dispatch(self) -> None:
        remaining: deque[WorkflowJob] = deque()

        while self.queue:
            job = self.queue.popleft()
            runner, diagnostics = self.registry.route(job)

            if runner is None:
                remaining.append(job)
                print(f"[QUEUE] {job.name}: no compatible runner")
                for diagnostic in diagnostics:
                    print(f"        {diagnostic}")
                continue

            self.execute(job, runner)

        self.queue = remaining

    def execute(self, job: WorkflowJob, runner: Runner) -> None:
        job.assigned_runner = runner.name
        job.state = JobState.RUNNING
        runner.state = RunnerState.BUSY
        runner.busy_job = job.name

        print(
            f"[RUN ] {job.name} -> {runner.name} "
            f"({runner.kind.value}, {runner.image.name})"
        )

        try:
            # The sleep represents workload execution rather than API
            # communication with GitHub. A production runner executes steps,
            # captures logs, handles commands, and reports results.
            time.sleep(job.duration_seconds)

            if job.required_tools and not runner.image.supports(job.required_tools):
                raise RuntimeError("runtime tool requirement was not satisfied")

            job.state = JobState.SUCCEEDED
            print(f"[DONE] {job.name}: succeeded")
        except Exception as exc:
            job.state = JobState.FAILED
            job.failure_reason = str(exc)
            print(f"[FAIL] {job.name}: {job.failure_reason}")
        finally:
            runner.state = RunnerState.IDLE
            runner.busy_job = None
            self.completed.append(job)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def demonstrate_runner_architecture() -> None:
    print("\n=== Runner architecture ===")

    print(
        """
A workflow job is the workload.
A runner is the execution agent.
The orchestration service selects an eligible runner.
The runner obtains job instructions, executes steps, streams results,
and reports completion.

The important boundary is that a runner executes code; it is not merely
a label attached to a workflow.
""".strip()
    )

    print(f"Python process: {sys.executable}")
    print(f"Operating system: {platform.system()} {platform.release()}")
    print(f"Machine architecture: {platform.machine()}")


def demonstrate_hosted_and_self_hosted() -> None:
    print("\n=== Hosted versus self-hosted runners ===")

    hosted_image = RunnerImage(
        name="ubuntu-latest",
        operating_system="Linux",
        architecture="x64",
        preinstalled_tools=frozenset({"git", "python", "node", "docker"}),
        ephemeral=True,
    )

    self_hosted_image = RunnerImage(
        name="company-linux-builder",
        operating_system="Linux",
        architecture="x64",
        preinstalled_tools=frozenset(
            {"git", "python", "node", "docker", "internal-sdk"}
        ),
        ephemeral=False,
    )

    hosted = Runner(
        name="hosted-ubuntu-01",
        kind=RunnerKind.HOSTED,
        labels={"self-hosted:false", "linux", "x64", "docker"},
        image=hosted_image,
        group="github-hosted",
        trusted=False,
    )

    self_hosted = Runner(
        name="internal-builder-01",
        kind=RunnerKind.SELF_HOSTED,
        labels={"self-hosted", "linux", "x64", "docker", "internal"},
        image=self_hosted_image,
        group="production-builders",
        persistent_workspace=True,
        trusted=True,
    )

    for runner in (hosted, self_hosted):
        print(
            f"{runner.name}: kind={runner.kind.value}, "
            f"image={runner.image.name}, "
            f"ephemeral={runner.image.ephemeral}, "
            f"persistent_workspace={runner.persistent_workspace}"
        )

    print(
        "\nHosted runners provide managed execution environments. "
        "Self-hosted runners place operating-system, software, network, "
        "patching, and lifecycle responsibility on the organization."
    )


def demonstrate_label_routing() -> None:
    print("\n=== Label-based routing ===")

    registry = RunnerRegistry()

    registry.register(
        Runner(
            name="linux-general",
            kind=RunnerKind.SELF_HOSTED,
            labels={"self-hosted", "linux", "x64"},
            image=RunnerImage(
                "linux-general",
                "Linux",
                "x64",
                frozenset({"git", "python"}),
                ephemeral=False,
            ),
        )
    )

    registry.register(
        Runner(
            name="linux-docker",
            kind=RunnerKind.SELF_HOSTED,
            labels={"self-hosted", "linux", "x64", "docker"},
            image=RunnerImage(
                "linux-docker",
                "Linux",
                "x64",
                frozenset({"git", "python", "docker"}),
                ephemeral=False,
            ),
        )
    )

    registry.register(
        Runner(
            name="linux-gpu",
            kind=RunnerKind.SELF_HOSTED,
            labels={"self-hosted", "linux", "x64", "docker", "gpu"},
            image=RunnerImage(
                "linux-gpu",
                "Linux",
                "x64",
                frozenset({"git", "python", "docker", "cuda"}),
                ephemeral=False,
            ),
        )
    )

    jobs = [
        WorkflowJob(
            name="unit-tests",
            labels={"self-hosted", "linux", "x64"},
            required_tools={"python"},
        ),
        WorkflowJob(
            name="container-build",
            labels={"self-hosted", "linux", "x64", "docker"},
            required_tools={"docker"},
        ),
        WorkflowJob(
            name="gpu-integration",
            labels={"self-hosted", "linux", "x64", "docker", "gpu"},
            required_tools={"cuda", "docker"},
        ),
    ]

    for job in jobs:
        runner, diagnostics = registry.route(job)
        print(
            f"{job.name}: selected={runner.name if runner else 'none'}"
        )
        if runner is None:
            print("  " + " | ".join(diagnostics))

    print(
        "\nLabel design is part of fleet architecture. Labels should describe "
        "capabilities and trust boundaries rather than arbitrary personal "
        "names, because workflows depend on those labels for routing."
    )


def demonstrate_queue_and_failure() -> None:
    print("\n=== Queueing and failure handling ===")

    registry = RunnerRegistry()
    registry.register(
        Runner(
            name="ephemeral-linux",
            kind=RunnerKind.HOSTED,
            labels={"linux", "x64", "docker"},
            image=RunnerImage(
                "ubuntu-latest",
                "Linux",
                "x64",
                frozenset({"git", "python", "node", "docker"}),
            ),
        )
    )

    registry.register(
        Runner(
            name="windows-builder",
            kind=RunnerKind.SELF_HOSTED,
            labels={"self-hosted", "windows", "x64"},
            image=RunnerImage(
                "windows-builder",
                "Windows",
                "x64",
                frozenset({"git", "python"}),
                ephemeral=False,
            ),
        )
    )

    pool = RunnerPool(registry)

    jobs = [
        WorkflowJob(
            name="linux-tests",
            labels={"linux", "x64"},
            required_tools={"python"},
        ),
        WorkflowJob(
            name="windows-tests",
            labels={"self-hosted", "windows", "x64"},
            required_tools={"python"},
        ),
        WorkflowJob(
            name="unavailable-arm-job",
            labels={"linux", "arm64"},
            required_tools={"python"},
        ),
    ]

    for job in jobs:
        pool.submit(job)

    pool.dispatch()

    print(f"\nRemaining queued jobs: {[job.name for job in pool.queue]}")
    print(
        "A queued job with no eligible runner remains queued rather than "
        "being sent to an incompatible machine."
    )


def demonstrate_drain_mode() -> None:
    print("\n=== Runner lifecycle and draining ===")

    runner = Runner(
        name="maintenance-builder",
        kind=RunnerKind.SELF_HOSTED,
        labels={"self-hosted", "linux", "x64"},
        image=RunnerImage(
            "maintenance-image",
            "Linux",
            "x64",
            frozenset({"git", "python"}),
            ephemeral=False,
        ),
    )

    print(f"Initial state: {runner.state.value}")
    runner.state = RunnerState.DRAINING
    print(
        "Draining state: the runner remains registered but should not "
        "receive new work while an operator prepares maintenance."
    )

    job = WorkflowJob(
        name="maintenance-check",
        labels={"self-hosted", "linux", "x64"},
        required_tools={"python"},
    )

    compatible, reason = runner.can_run(job)
    print(f"Can accept new job? {compatible}; reason={reason}")

    runner.state = RunnerState.OFFLINE
    runner.online = False
    print(f"Offline state: {runner.state.value}, online={runner.online}")


def demonstrate_ephemeral_workspace_security() -> None:
    print("\n=== Workspace isolation and security ===")

    with tempfile.TemporaryDirectory(prefix="actions-runner-") as workspace:
        workspace_path = Path(workspace)
        build_output = workspace_path / "build.txt"
        build_output.write_text(
            "artifact produced by one job\n",
            encoding="utf-8",
        )

        print(f"Temporary workspace: {workspace_path}")
        print(f"Workspace contents: {build_output.read_text(encoding='utf-8').strip()}")

    print(
        "After the context exits, the temporary workspace is removed. "
        "Ephemeral execution reduces persistence between unrelated jobs."
    )

    print(
        "\nSecurity boundary: self-hosted runners execute workflow code on "
        "infrastructure controlled by the organization. A malicious or "
        "compromised workflow can potentially access anything the runner "
        "account can access. Persistent self-hosted machines therefore "
        "require stronger isolation, least privilege, network controls, "
        "credential protection, patching, and workspace cleanup."
    )


def demonstrate_subprocess_execution() -> None:
    print("\n=== Real local command execution ===")

    # This is intentionally a harmless local command. A runner ultimately
    # executes operating-system processes, so subprocess execution illustrates
    # the boundary between orchestration logic and the machine environment.
    executable = shutil.which("python") or sys.executable

    result = subprocess.run(
        [executable, "-c", "print('runner executed a real process')"],
        capture_output=True,
        text=True,
        check=False,
        timeout=10,
    )

    print(f"Exit code: {result.returncode}")
    print(result.stdout.strip())

    if result.stderr.strip():
        print(f"stderr: {result.stderr.strip()}")


def demonstrate_capacity_model() -> None:
    print("\n=== Capacity planning ===")

    jobs = 24
    average_minutes = 6
    concurrent_runners = 4

    total_runner_minutes = jobs * average_minutes
    approximate_wall_clock_minutes = total_runner_minutes / concurrent_runners

    print(f"Queued jobs: {jobs}")
    print(f"Average job duration: {average_minutes} minutes")
    print(f"Concurrent runners: {concurrent_runners}")
    print(f"Total runner-minutes: {total_runner_minutes}")
    print(
        f"Approximate execution time at full utilization: "
        f"{approximate_wall_clock_minutes:.1f} minutes"
    )

    print(
        "\nRunner count affects queue latency only when the jobs can execute "
        "concurrently and enough compatible capacity exists. Adding five "
        "Linux runners does not solve a queue of jobs requiring a single "
        "GPU-labeled runner."
    )


def demonstrate_matrix_style_fleet() -> None:
    print("\n=== Multi-platform runner fleet ===")

    fleet = [
        ("ubuntu-x64", {"linux", "x64"}),
        ("ubuntu-arm64", {"linux", "arm64"}),
        ("windows-x64", {"windows", "x64"}),
        ("macos-arm64", {"macos", "arm64"}),
    ]

    required_jobs = [
        ("Linux x64", {"linux", "x64"}),
        ("Linux ARM", {"linux", "arm64"}),
        ("Windows", {"windows", "x64"}),
        ("macOS ARM", {"macos", "arm64"}),
    ]

    for job_name, requirements in required_jobs:
        matches = [
            name for name, labels in fleet if requirements.issubset(labels)
        ]
        print(f"{job_name}: {matches}")


def demonstrate_configuration_validation() -> None:
    print("\n=== Runner configuration validation ===")

    def validate_runner(runner: Runner) -> list[str]:
        problems: list[str] = []

        if runner.kind == RunnerKind.SELF_HOSTED and "self-hosted" not in runner.labels:
            problems.append("self-hosted runner should advertise the self-hosted label")

        if "linux" in runner.labels and runner.image.operating_system != "Linux":
            problems.append("linux label conflicts with the runner image")

        if "windows" in runner.labels and runner.image.operating_system != "Windows":
            problems.append("windows label conflicts with the runner image")

        if "arm64" in runner.labels and runner.image.architecture != "arm64":
            problems.append("arm64 label conflicts with runner architecture")

        if "x64" in runner.labels and runner.image.architecture != "x64":
            problems.append("x64 label conflicts with runner architecture")

        if runner.persistent_workspace and runner.image.ephemeral:
            problems.append(
                "persistent workspace contradicts an explicitly ephemeral image"
            )

        return problems

    candidates = [
        Runner(
            name="valid-builder",
            kind=RunnerKind.SELF_HOSTED,
            labels={"self-hosted", "linux", "x64"},
            image=RunnerImage(
                "linux",
                "Linux",
                "x64",
                frozenset({"git"}),
                ephemeral=False,
            ),
        ),
        Runner(
            name="misconfigured-builder",
            kind=RunnerKind.SELF_HOSTED,
            labels={"self-hosted", "linux", "arm64"},
            image=RunnerImage(
                "incorrect-image",
                "Linux",
                "x64",
                frozenset({"git"}),
                ephemeral=False,
            ),
        ),
    ]

    for runner in candidates:
        problems = validate_runner(runner)
        print(
            f"{runner.name}: "
            + ("valid" if not problems else "; ".join(problems))
        )


def demonstrate_serialization() -> None:
    print("\n=== Fleet inventory serialization ===")

    runner = Runner(
        name="inventory-linux",
        kind=RunnerKind.SELF_HOSTED,
        labels={"self-hosted", "linux", "x64"},
        image=RunnerImage(
            "linux-builder",
            "Linux",
            "x64",
            frozenset({"git", "python", "docker"}),
            ephemeral=False,
        ),
        group="engineering",
        trusted=True,
    )

    inventory = {
        "timestamp": utc_now(),
        "runner": {
            "name": runner.name,
            "kind": runner.kind.value,
            "state": runner.state.value,
            "online": runner.online,
            "group": runner.group,
            "labels": sorted(runner.labels),
            "image": runner.image.name,
            "architecture": runner.image.architecture,
            "tools": sorted(runner.image.preinstalled_tools),
            "trusted": runner.trusted,
        },
    }

    print(json.dumps(inventory, indent=2))


def run_topic_laboratory() -> None:
    random.seed(7)

    print("GitHub Actions Runner Laboratory")
    print("=" * 34)

    demonstrate_runner_architecture()
    demonstrate_hosted_and_self_hosted()
    demonstrate_label_routing()
    demonstrate_queue_and_failure()
    demonstrate_drain_mode()
    demonstrate_ephemeral_workspace_security()
    demonstrate_subprocess_execution()
    demonstrate_capacity_model()
    demonstrate_matrix_style_fleet()
    demonstrate_configuration_validation()
    demonstrate_serialization()

    print("\n=== Key architectural relationships ===")
    print(
        "Workflow -> job -> routing constraints -> eligible runner -> "
        "execution environment -> logs/results -> job completion"
    )
    print(
        "Hosted runners shift machine lifecycle responsibility toward the "
        "platform; self-hosted runners shift infrastructure responsibility "
        "toward the repository or organization."
    )
    print(
        "Runner labels express routing capabilities. Runner groups and "
        "organizational policy can establish which workflows are allowed "
        "to consume particular infrastructure."
    )
    print(
        "Security depends on the runner trust boundary, not merely on the "
        "workflow YAML. A runner that can reach production systems or read "
        "sensitive credentials becomes part of that security boundary."
    )


if __name__ == "__main__":
    run_topic_laboratory()
