#!/usr/bin/env python3
"""Practical Docker CLI laboratory: images, containers, execution, logs, and lifecycle."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import json
import shutil
import subprocess


@dataclass
class ContainerRecord:
    container_id: str
    name: str
    image: str
    status: str = "created"
    exit_code: Optional[int] = None
    logs: list[str] = field(default_factory=list)


class DockerCLI:
    """Run Docker CLI commands safely and inspect their results."""

    def __init__(self, executable: str = "docker"):
        self.executable = executable
        self.available = shutil.which(executable) is not None

    def run(self, *arguments: str, timeout: int = 30) -> subprocess.CompletedProcess:
        if not self.available:
            raise RuntimeError("Docker CLI is not installed or is missing from PATH.")

        if not arguments:
            raise ValueError("At least one Docker argument is required.")

        # Pass an argument list rather than a shell string to prevent shell injection.
        return subprocess.run(
            [self.executable, *arguments],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def require_success(self, *arguments: str, timeout: int = 30) -> str:
        result = self.run(*arguments, timeout=timeout)
        if result.returncode != 0:
            raise RuntimeError(
                f"docker {' '.join(arguments)} failed "
                f"(exit {result.returncode}): {result.stderr.strip()}"
            )
        return result.stdout.strip()

    def version(self) -> str:
        return self.require_success("version", "--format", "{{json .Client}}")

    def info(self) -> str:
        return self.require_success(
            "info", "--format", "Containers={{.Containers}}, Images={{.Images}}"
        )

    def pull(self, image: str) -> str:
        if not image.strip():
            raise ValueError("Image name cannot be empty.")
        return self.require_success("pull", image, timeout=600)

    def run_container(
        self,
        image: str,
        name: str,
        command: Optional[list[str]] = None,
        detached: bool = False,
    ) -> str:
        if not image or not name:
            raise ValueError("Image and container name are required.")

        arguments = ["run", "--name", name]
        if detached:
            arguments.append("-d")
        else:
            arguments.append("--rm")

        arguments.append(image)
        if command:
            arguments.extend(command)

        return self.require_success(*arguments, timeout=120)

    def list_containers(self, all_containers: bool = False) -> list[dict]:
        arguments = ["ps", "--format", "{{json .}}"]
        if all_containers:
            arguments.insert(1, "-a")

        output = self.require_success(*arguments)
        if not output:
            return []

        return [json.loads(line) for line in output.splitlines()]

    def execute(self, container: str, command: list[str]) -> str:
        if not container or not command:
            raise ValueError("Container name and command are required.")
        return self.require_success("exec", container, *command, timeout=60)

    def logs(self, container: str, tail: int = 50) -> str:
        if tail < 1:
            raise ValueError("Log tail must be positive.")
        return self.require_success("logs", "--tail", str(tail), container)

    def stop(self, container: str, timeout: int = 10) -> str:
        return self.require_success("stop", "--time", str(timeout), container)

    def start(self, container: str) -> str:
        return self.require_success("start", container)

    def inspect(self, container: str) -> dict:
        output = self.require_success("inspect", container)
        records = json.loads(output)
        if not records:
            raise RuntimeError("Docker returned no inspection record.")
        return records[0]


def demonstrate_docker_cli() -> None:
    print("Docker CLI practical laboratory")
    docker = DockerCLI()

    if not docker.available:
        print("Docker CLI is unavailable. Install Docker Desktop or Docker Engine.")
        return

    try:
        print("\nClient version:")
        print(docker.version())

        print("\nEngine information:")
        print(docker.info())

        # This workload is isolated and exits automatically after printing.
        print("\nRunning a temporary container:")
        output = docker.run_container(
            image="alpine:3.22",
            name="docker-cli-lab-once",
            command=["sh", "-c", "echo 'Container started'; date -u"],
        )
        print(output or "(Container completed without output.)")

        print("\nPulling an image:")
        print(docker.pull("alpine:3.22"))

        # Detached containers are useful for inspecting lifecycle operations.
        print("\nStarting a detached service container:")
        container_id = docker.require_success(
            "run",
            "-d",
            "--name",
            "docker-cli-lab-service",
            "--label",
            "purpose=cli-learning",
            "alpine:3.22",
            "sh",
            "-c",
            "while true; do echo heartbeat; sleep 5; done",
        )
        print(f"Container ID: {container_id[:12]}")

        try:
            print("\nRunning ps:")
            for container in docker.list_containers():
                print(
                    container.get("ID"),
                    container.get("Names"),
                    container.get("Status"),
                )

            print("\nExecuting a command inside the running container:")
            print(docker.execute("docker-cli-lab-service", ["sh", "-c", "echo ready"]))

            print("\nReading container logs:")
            print(docker.logs("docker-cli-lab-service", tail=5))

            print("\nInspecting container state:")
            inspection = docker.inspect("docker-cli-lab-service")
            state = inspection.get("State", {})
            print(
                json.dumps(
                    {
                        "name": inspection.get("Name"),
                        "status": state.get("Status"),
                        "running": state.get("Running"),
                        "started_at": state.get("StartedAt"),
                    },
                    indent=2,
                )
            )

            print("\nStopping the container:")
            print(docker.stop("docker-cli-lab-service"))

            print("\nRestarting the stopped container:")
            print(docker.start("docker-cli-lab-service"))

        finally:
            # Clean up only the explicitly named laboratory container.
            result = docker.run("rm", "-f", "docker-cli-lab-service")
            if result.returncode == 0:
                print("\nLaboratory container removed.")

    except (RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"Docker operation failed: {exc}")


if __name__ == "__main__":
    demonstrate_docker_cli()
