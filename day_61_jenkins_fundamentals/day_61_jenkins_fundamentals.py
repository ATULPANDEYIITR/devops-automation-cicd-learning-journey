#!/usr/bin/env python3
"""
Jenkins Fundamentals: controller, agents, jobs, queues, executors,
workspace allocation, build execution, failures, and basic governance.

This is a self-contained simulation of a Jenkins-style execution system.
It uses only the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set
import json
import tempfile
import time


class JobType(Enum):
    FREESTYLE = "freestyle"
    PIPELINE = "pipeline"


class BuildStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    ABORTED = "aborted"


class AgentStatus(Enum):
    ONLINE = "online"
    OFFLINE = "offline"


@dataclass(frozen=True)
class Commit:
    sha: str
    message: str


@dataclass
class Build:
    number: int
    job_name: str
    commit: Commit
    status: BuildStatus = BuildStatus.QUEUED
    agent_name: Optional[str] = None
    workspace: Optional[str] = None
    logs: List[str] = field(default_factory=list)
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def log(self, message: str) -> None:
        self.logs.append(message)

    @property
    def duration_seconds(self) -> Optional[float]:
        if self.started_at is None or self.finished_at is None:
            return None
        return self.finished_at - self.started_at


@dataclass
class Job:
    name: str
    job_type: JobType
    required_labels: Set[str] = field(default_factory=set)
    enabled: bool = True
    build_numbers: int = 0
    builds: List[Build] = field(default_factory=list)

    def next_build_number(self) -> int:
        self.build_numbers += 1
        return self.build_numbers


@dataclass
class Agent:
    name: str
    labels: Set[str]
    executors: int = 1
    status: AgentStatus = AgentStatus.ONLINE
    workspaces: Set[str] = field(default_factory=set)

    def __post_init__(self) -> None:
        if self.executors < 1:
            raise ValueError("An agent must have at least one executor.")

    def can_run(self, required_labels: Set[str]) -> bool:
        return (
            self.status == AgentStatus.ONLINE
            and required_labels.issubset(self.labels)
        )


class JenkinsController:
    """
    Models the controller's responsibilities:
    - job configuration
    - build numbering
    - queue management
    - agent selection
    - build records
    - execution coordination

    Actual Jenkins controllers do not execute arbitrary build commands
    on agents merely by storing these objects. This simulator separates
    orchestration from the worker execution model.
    """

    def __init__(self, workspace_root: Optional[Path] = None) -> None:
        self.jobs: Dict[str, Job] = {}
        self.agents: Dict[str, Agent] = {}
        self.queue: List[Build] = []
        self.workspace_root = workspace_root or Path(tempfile.mkdtemp(prefix="jenkins-"))
        self.audit_log: List[str] = []

    def register_agent(self, agent: Agent) -> None:
        if agent.name in self.agents:
            raise ValueError(f"Agent already exists: {agent.name}")
        self.agents[agent.name] = agent
        self.audit_log.append(f"agent_registered:{agent.name}")

    def create_job(
        self,
        name: str,
        job_type: JobType,
        required_labels: Optional[Set[str]] = None,
    ) -> Job:
        if not name.strip():
            raise ValueError("Job name cannot be empty.")
        if name in self.jobs:
            raise ValueError(f"Job already exists: {name}")

        job = Job(
            name=name,
            job_type=job_type,
            required_labels=required_labels or set(),
        )
        self.jobs[name] = job
        self.audit_log.append(f"job_created:{name}")
        return job

    def schedule_build(self, job_name: str, commit: Commit) -> Build:
        job = self.jobs.get(job_name)

        if job is None:
            raise KeyError(f"Unknown job: {job_name}")
        if not job.enabled:
            raise RuntimeError(f"Job is disabled: {job_name}")
        if len(commit.sha) < 7:
            raise ValueError("Commit SHA must contain at least seven characters.")

        build = Build(
            number=job.next_build_number(),
            job_name=job_name,
            commit=commit,
        )
        self.queue.append(build)
        self.audit_log.append(f"build_queued:{job_name}#{build.number}")
        return build

    def find_agent(self, job: Job) -> Optional[Agent]:
        candidates = [
            agent
            for agent in self.agents.values()
            if agent.can_run(job.required_labels)
        ]

        if not candidates:
            return None

        # Prefer the least-used compatible agent to spread work.
        return min(candidates, key=lambda a: len(a.workspaces))

    def allocate_workspace(self, agent: Agent, build: Build) -> Path:
        workspace = (
            self.workspace_root
            / agent.name
            / f"{build.job_name.replace('/', '_')}-{build.number}"
        )
        workspace.mkdir(parents=True, exist_ok=False)
        agent.workspaces.add(str(workspace))
        return workspace

    def execute_build(self, build: Build) -> Build:
        job = self.jobs[build.job_name]
        agent = self.find_agent(job)

        if agent is None:
            return build

        self.queue.remove(build)
        build.status = BuildStatus.RUNNING
        build.agent_name = agent.name
        build.started_at = time.perf_counter()

        try:
            workspace = self.allocate_workspace(agent, build)
            build.workspace = str(workspace)

            build.log(f"Controller assigned build to agent {agent.name}.")
            build.log(f"Checked out commit {build.commit.sha}.")
            (workspace / "commit.txt").write_text(
                f"{build.commit.sha}\n{build.commit.message}\n",
                encoding="utf-8",
            )

            # The pipeline intentionally has a deterministic validation step.
            if "FAIL" in build.commit.message.upper():
                raise RuntimeError("Build validation failed because the commit message requested failure.")

            self._run_validation(workspace, build)
            build.status = BuildStatus.SUCCESS
            build.log("Build completed successfully.")

        except (OSError, RuntimeError, ValueError) as exc:
            build.status = BuildStatus.FAILURE
            build.log(f"Build failed: {exc}")

        finally:
            build.finished_at = time.perf_counter()
            agent.workspaces.discard(build.workspace or "")
            job.builds.append(build)
            self.audit_log.append(
                f"build_finished:{build.job_name}#{build.number}:{build.status.value}"
            )

        return build

    @staticmethod
    def _run_validation(workspace: Path, build: Build) -> None:
        commit_file = workspace / "commit.txt"

        if not commit_file.exists():
            raise RuntimeError("Checkout artifact is missing.")

        contents = commit_file.read_text(encoding="utf-8").splitlines()
        if not contents or contents[0] != build.commit.sha:
            raise RuntimeError("Checkout validation failed.")

        build.log("Validation passed.")

    def run_next_available(self) -> Optional[Build]:
        for build in list(self.queue):
            job = self.jobs[build.job_name]
            if self.find_agent(job) is not None:
                return self.execute_build(build)
        return None

    def run_all_possible(self) -> List[Build]:
        completed: List[Build] = []

        while self.queue:
            result = self.run_next_available()
            if result is None:
                break
            completed.append(result)

        return completed

    def summary(self) -> dict:
        return {
            "jobs": {
                name: {
                    "type": job.job_type.value,
                    "enabled": job.enabled,
                    "build_count": len(job.builds),
                    "results": [build.status.value for build in job.builds],
                }
                for name, job in self.jobs.items()
            },
            "agents": {
                name: {
                    "labels": sorted(agent.labels),
                    "status": agent.status.value,
                    "active_workspaces": len(agent.workspaces),
                }
                for name, agent in self.agents.items()
            },
            "queued_builds": len(self.queue),
            "audit_events": len(self.audit_log),
        }


def run_examples() -> None:
    with tempfile.TemporaryDirectory(prefix="jenkins-demo-") as temp_dir:
        controller = JenkinsController(Path(temp_dir))

        controller.register_agent(
            Agent("linux-builder-1", {"linux", "python", "docker"}, executors=2)
        )
        controller.register_agent(
            Agent("linux-builder-2", {"linux", "java"}, executors=1)
        )
        controller.register_agent(
            Agent("offline-builder", {"linux", "python"}, status=AgentStatus.OFFLINE)
        )

        controller.create_job(
            "python-validation",
            JobType.PIPELINE,
            {"linux", "python"},
        )
        controller.create_job(
            "java-validation",
            JobType.FREESTYLE,
            {"linux", "java"},
        )

        first = controller.schedule_build(
            "python-validation",
            Commit("a1b2c3d4", "Add input validation"),
        )
        second = controller.schedule_build(
            "python-validation",
            Commit("e5f6g7h8", "FAIL: intentionally exercise failure handling"),
        )
        third = controller.schedule_build(
            "java-validation",
            Commit("11223344", "Improve service validation"),
        )

        results = controller.run_all_possible()

        assert first.status == BuildStatus.SUCCESS
        assert second.status == BuildStatus.FAILURE
        assert third.status == BuildStatus.SUCCESS
        assert not controller.queue

        print("Jenkins controller simulation")
        print("=" * 32)

        for build in results:
            print(
                f"{build.job_name} #{build.number}: "
                f"{build.status.value}, agent={build.agent_name}, "
                f"duration={build.duration_seconds:.6f}s"
            )
            for line in build.logs:
                print(f"  {line}")

        print("\nController state:")
        print(json.dumps(controller.summary(), indent=2))

        print("\nDesign checks:")
        print("- Controller owns job and queue state.")
        print("- Agents provide labeled execution capacity.")
        print("- Jobs select agents through label requirements.")
        print("- Builds retain immutable commit identity and execution history.")
        print("- Disabled or offline execution paths are rejected.")
        print("- Workspace paths are isolated per agent and build.")


if __name__ == "__main__":
    run_examples()
