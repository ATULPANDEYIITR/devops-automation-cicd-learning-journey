#!/usr/bin/env python3
"""
Jenkins Agents: Static Agents, Dynamic Agents, and Distributed Builds

Simulates a Jenkins controller coordinating static and dynamically
provisioned agents, assigning builds according to labels and capacity,
tracking execution states, and handling failures.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from collections import defaultdict
import time


class AgentType(Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"


class AgentStatus(Enum):
    OFFLINE = "offline"
    ONLINE = "online"
    BUSY = "busy"
    TERMINATED = "terminated"


class BuildStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Build:
    build_id: int
    job_name: str
    required_labels: set[str]
    estimated_seconds: int = 10
    status: BuildStatus = BuildStatus.QUEUED
    assigned_agent: Optional[str] = None
    actual_seconds: float = 0.0
    error: Optional[str] = None

    def __post_init__(self):
        if self.build_id <= 0:
            raise ValueError("Build ID must be positive.")
        if not self.job_name.strip():
            raise ValueError("Job name cannot be empty.")
        if self.estimated_seconds <= 0:
            raise ValueError("Estimated execution time must be positive.")
        if not self.required_labels:
            raise ValueError("At least one execution label is required.")


@dataclass
class Agent:
    name: str
    agent_type: AgentType
    labels: set[str]
    executors: int = 1
    status: AgentStatus = AgentStatus.ONLINE
    active_builds: set[int] = field(default_factory=set)
    max_builds: int = 0
    idle_since: float = field(default_factory=time.monotonic)

    def __post_init__(self):
        if not self.name.strip():
            raise ValueError("Agent name cannot be empty.")
        if self.executors < 1:
            raise ValueError("An agent needs at least one executor.")
        if self.agent_type == AgentType.STATIC:
            self.max_builds = 0

    @property
    def available_executors(self) -> int:
        return self.executors - len(self.active_builds)

    @property
    def is_available(self) -> bool:
        return (
            self.status == AgentStatus.ONLINE
            and self.available_executors > 0
        )

    def supports(self, required_labels: set[str]) -> bool:
        return required_labels.issubset(self.labels)


class JenkinsController:
    """
    Controller responsible for queue management and agent scheduling.

    Static agents remain registered.
    Dynamic agents are provisioned on demand and terminated after
    becoming idle for the configured timeout.
    """

    def __init__(
        self,
        dynamic_agent_limit: int = 3,
        idle_timeout: int = 60
    ):
        if dynamic_agent_limit < 0:
            raise ValueError("Dynamic agent limit cannot be negative.")
        if idle_timeout < 0:
            raise ValueError("Idle timeout cannot be negative.")

        self.agents: dict[str, Agent] = {}
        self.builds: dict[int, Build] = {}
        self.queue: list[int] = []
        self.dynamic_agent_limit = dynamic_agent_limit
        self.idle_timeout = idle_timeout
        self.next_dynamic_id = 1
        self.metrics = defaultdict(int)

    def register_agent(self, agent: Agent) -> None:
        if agent.name in self.agents:
            raise ValueError(f"Agent already registered: {agent.name}")
        self.agents[agent.name] = agent
        print(f"Registered {agent.agent_type.value} agent: {agent.name}")

    def submit_build(self, build: Build) -> None:
        if build.build_id in self.builds:
            raise ValueError("Duplicate build ID.")

        self.builds[build.build_id] = build
        self.queue.append(build.build_id)
        self.metrics["submitted"] += 1

        print(
            f"Queued build #{build.build_id}: {build.job_name}, "
            f"labels={sorted(build.required_labels)}"
        )

    def _find_agent(self, build: Build) -> Optional[Agent]:
        candidates = [
            agent
            for agent in self.agents.values()
            if agent.is_available
            and agent.supports(build.required_labels)
        ]

        # Prefer static agents to reduce provisioning overhead.
        # Among candidates, prefer the least-loaded agent.
        candidates.sort(
            key=lambda agent: (
                agent.agent_type != AgentType.STATIC,
                len(agent.active_builds),
                agent.name
            )
        )

        return candidates[0] if candidates else None

    def _provision_dynamic_agent(self, build: Build) -> Optional[Agent]:
        active_dynamic = sum(
            1 for agent in self.agents.values()
            if agent.agent_type == AgentType.DYNAMIC
            and agent.status != AgentStatus.TERMINATED
        )

        if active_dynamic >= self.dynamic_agent_limit:
            return None

        name = f"dynamic-agent-{self.next_dynamic_id}"
        self.next_dynamic_id += 1

        agent = Agent(
            name=name,
            agent_type=AgentType.DYNAMIC,
            labels=set(build.required_labels) | {"dynamic"},
            executors=1,
            max_builds=1
        )

        self.register_agent(agent)
        self.metrics["provisioned"] += 1

        return agent

    def schedule(self) -> int:
        """
        Assign queued builds to compatible agents.

        Returns the number of builds assigned during this scheduling pass.
        """
        assigned = 0

        for build_id in list(self.queue):
            build = self.builds[build_id]

            if build.status != BuildStatus.QUEUED:
                self.queue.remove(build_id)
                continue

            agent = self._find_agent(build)

            if agent is None:
                agent = self._provision_dynamic_agent(build)

            if agent is None:
                continue

            agent.active_builds.add(build.build_id)
            agent.status = AgentStatus.BUSY
            build.assigned_agent = agent.name
            build.status = BuildStatus.RUNNING

            self.queue.remove(build_id)
            self.metrics["assigned"] += 1
            assigned += 1

            print(
                f"Build #{build_id} assigned to {agent.name}"
            )

        return assigned

    def complete_build(
        self,
        build_id: int,
        success: bool = True,
        execution_seconds: Optional[float] = None,
        error: Optional[str] = None
    ) -> None:
        build = self.builds.get(build_id)

        if build is None:
            raise KeyError(f"Unknown build: {build_id}")

        if build.status != BuildStatus.RUNNING:
            raise ValueError("Only running builds can be completed.")

        agent = self.agents[build.assigned_agent]

        agent.active_builds.remove(build_id)
        agent.idle_since = time.monotonic()

        if agent.status != AgentStatus.OFFLINE:
            agent.status = AgentStatus.ONLINE

        build.status = (
            BuildStatus.SUCCESS if success else BuildStatus.FAILED
        )
        build.actual_seconds = (
            execution_seconds
            if execution_seconds is not None
            else float(build.estimated_seconds)
        )

        if build.actual_seconds < 0:
            raise ValueError("Execution time cannot be negative.")

        build.error = None if success else (
            error or "Build execution failed."
        )

        self.metrics[build.status.value] += 1

        print(
            f"Build #{build_id}: {build.status.value} "
            f"on {agent.name}"
        )

    def set_agent_online(self, name: str, online: bool) -> None:
        agent = self.agents.get(name)

        if agent is None:
            raise KeyError(f"Unknown agent: {name}")

        if agent.status == AgentStatus.TERMINATED:
            raise ValueError("A terminated agent cannot be reactivated.")

        if not online and agent.active_builds:
            raise ValueError(
                "Cannot take an agent offline while it has active builds."
            )

        agent.status = (
            AgentStatus.ONLINE if online else AgentStatus.OFFLINE
        )

    def cleanup_idle_dynamic_agents(
        self,
        current_time: Optional[float] = None
    ) -> list[str]:
        now = current_time or time.monotonic()
        terminated = []

        for agent in self.agents.values():
            if agent.agent_type != AgentType.DYNAMIC:
                continue

            if agent.status != AgentStatus.ONLINE:
                continue

            if agent.active_builds:
                continue

            if now - agent.idle_since >= self.idle_timeout:
                agent.status = AgentStatus.TERMINATED
                terminated.append(agent.name)
                self.metrics["terminated"] += 1

                print(f"Terminated idle agent: {agent.name}")

        return terminated

    def cancel_build(self, build_id: int) -> None:
        build = self.builds.get(build_id)

        if build is None:
            raise KeyError(f"Unknown build: {build_id}")

        if build.status == BuildStatus.QUEUED:
            self.queue.remove(build_id)
            build.status = BuildStatus.CANCELLED
        elif build.status == BuildStatus.RUNNING:
            agent = self.agents[build.assigned_agent]
            agent.active_builds.remove(build_id)

            if not agent.active_builds:
                agent.status = AgentStatus.ONLINE
                agent.idle_since = time.monotonic()

            build.status = BuildStatus.CANCELLED
        else:
            raise ValueError("Build is already in a final state.")

        self.metrics["cancelled"] += 1

    def report(self) -> None:
        print("\n========== JENKINS REPORT ==========")

        for agent in self.agents.values():
            print(
                f"{agent.name:20} "
                f"type={agent.agent_type.value:7} "
                f"status={agent.status.value:10} "
                f"executors={agent.executors} "
                f"active={len(agent.active_builds)}"
            )

        print("\nBuild statistics:")

        for status in BuildStatus:
            count = sum(
                build.status == status
                for build in self.builds.values()
            )
            print(f"{status.value:12}: {count}")

        print(f"Queue length: {len(self.queue)}")


def demonstrate():
    controller = JenkinsController(
        dynamic_agent_limit=2,
        idle_timeout=30
    )

    # Static agents are permanently registered infrastructure.
    controller.register_agent(
        Agent(
            name="linux-builder-01",
            agent_type=AgentType.STATIC,
            labels={"linux", "python", "docker"},
            executors=2
        )
    )

    controller.register_agent(
        Agent(
            name="windows-builder-01",
            agent_type=AgentType.STATIC,
            labels={"windows", "dotnet"},
            executors=1
        )
    )

    builds = [
        Build(1, "Python Unit Tests", {"linux", "python"}, 15),
        Build(2, "Docker Image Build", {"linux", "docker"}, 25),
        Build(3, "Windows Integration", {"windows", "dotnet"}, 30),
        Build(4, "Linux Security Scan", {"linux", "security"}, 20),
        Build(5, "Python Deployment", {"linux", "python"}, 12),
    ]

    for build in builds:
        controller.submit_build(build)

    print("\n--- Scheduling distributed builds ---")
    controller.schedule()

    # Complete currently running jobs.
    for build in builds:
        if build.status == BuildStatus.RUNNING:
            controller.complete_build(
                build.build_id,
                success=build.build_id != 3,
                execution_seconds=build.estimated_seconds,
                error="Integration test failure"
            )

    print("\n--- Scheduling remaining work ---")
    controller.schedule()

    for build in builds:
        if build.status == BuildStatus.RUNNING:
            controller.complete_build(build.build_id)

    controller.report()

    # Simulate a dynamic agent remaining idle beyond its timeout.
    old_time = time.monotonic() + 60
    controller.cleanup_idle_dynamic_agents(old_time)

    print("\n--- Final infrastructure state ---")
    controller.report()


if __name__ == "__main__":
    demonstrate()
