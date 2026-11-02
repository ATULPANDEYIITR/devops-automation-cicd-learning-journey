from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable
import json
import tempfile
import time


class JobStatus(str, Enum):
    ENABLED = "enabled"
    DISABLED = "disabled"


class BuildStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    ABORTED = "ABORTED"


class TriggerType(str, Enum):
    MANUAL = "manual"
    TIMER = "timer"
    SCM = "scm"
    UPSTREAM = "upstream"


class JobError(Exception):
    pass


@dataclass(frozen=True)
class ParameterDefinition:
    name: str
    default: str
    required: bool = True
    choices: tuple[str, ...] = ()

    def validate(self, value: str) -> str:
        value = str(value).strip()
        if self.required and not value:
            raise JobError(f"Parameter {self.name} cannot be empty")
        if self.choices and value not in self.choices:
            raise JobError(
                f"Parameter {self.name} must be one of {self.choices}"
            )
        return value


@dataclass
class Build:
    number: int
    parameters: dict[str, str]
    status: BuildStatus
    workspace: Path
    log: list[str] = field(default_factory=list)
    started_at: float = field(default_factory=time.time)
    finished_at: float | None = None

    def finish(self) -> None:
        self.finished_at = time.time()


@dataclass
class FreestyleJob:
    name: str
    description: str
    workspace_root: Path
    status: JobStatus = JobStatus.ENABLED
    parameters: dict[str, ParameterDefinition] = field(default_factory=dict)
    triggers: set[TriggerType] = field(default_factory=set)
    builders: list[Callable[[dict[str, str], Path, list[str]], None]] = field(
        default_factory=list
    )
    builds: list[Build] = field(default_factory=list)

    def add_parameter(self, definition: ParameterDefinition) -> None:
        if definition.name in self.parameters:
            raise JobError(f"Duplicate parameter: {definition.name}")
        self.parameters[definition.name] = definition

    def add_trigger(self, trigger: TriggerType) -> None:
        self.triggers.add(trigger)

    def add_builder(
        self,
        builder: Callable[[dict[str, str], Path, list[str]], None],
    ) -> None:
        self.builders.append(builder)

    def resolve_parameters(
        self, supplied: dict[str, str] | None
    ) -> dict[str, str]:
        supplied = supplied or {}
        unknown = set(supplied) - set(self.parameters)
        if unknown:
            raise JobError(f"Unknown parameters: {sorted(unknown)}")

        resolved: dict[str, str] = {}
        for name, definition in self.parameters.items():
            raw = supplied.get(name, definition.default)
            resolved[name] = definition.validate(raw)
        return resolved

    def run(
        self,
        supplied_parameters: dict[str, str] | None = None,
        trigger: TriggerType = TriggerType.MANUAL,
    ) -> Build:
        if self.status != JobStatus.ENABLED:
            raise JobError(f"Job {self.name} is disabled")

        if trigger not in self.triggers and trigger != TriggerType.MANUAL:
            raise JobError(
                f"Trigger {trigger.value!r} is not configured for {self.name}"
            )

        parameters = self.resolve_parameters(supplied_parameters)
        build_number = len(self.builds) + 1
        workspace = self.workspace_root / self.name / f"build-{build_number}"
        workspace.mkdir(parents=True, exist_ok=True)

        build = Build(
            number=build_number,
            parameters=parameters,
            status=BuildStatus.SUCCESS,
            workspace=workspace,
        )
        build.log.append(
            f"BUILD #{build_number} started by {trigger.value} trigger"
        )
        build.log.append(f"Workspace: {workspace}")
        build.log.append(f"Parameters: {parameters}")

        try:
            for builder in self.builders:
                builder(parameters, workspace, build.log)
            build.log.append("Build completed successfully")
        except Exception as exc:
            build.status = BuildStatus.FAILURE
            build.log.append(f"Build failed: {exc}")
        finally:
            build.finish()
            self.builds.append(build)

        return build

    def latest_build(self) -> Build | None:
        return self.builds[-1] if self.builds else None


def write_workspace_manifest(
    parameters: dict[str, str], workspace: Path, log: list[str]
) -> None:
    manifest = {
        "job_parameters": parameters,
        "workspace": str(workspace),
        "files": [],
    }
    (workspace / "manifest.json").write_text(
        json.dumps(manifest, indent=2),
        encoding="utf-8",
    )
    log.append("Created manifest.json")


def validate_environment(
    parameters: dict[str, str], workspace: Path, log: list[str]
) -> None:
    environment = parameters["ENVIRONMENT"]
    version = parameters["VERSION"]

    if environment == "production" and version.startswith("dev-"):
        raise JobError(
            "Production builds cannot use development versions"
        )

    log.append(
        f"Environment validation passed for {environment}, version {version}"
    )


def package_application(
    parameters: dict[str, str], workspace: Path, log: list[str]
) -> None:
    package_name = (
        f"application-{parameters['VERSION']}-{parameters['ENVIRONMENT']}.txt"
    )
    package = workspace / package_name
    package.write_text(
        "Freestyle build artifact\n"
        f"version={parameters['VERSION']}\n"
        f"environment={parameters['ENVIRONMENT']}\n",
        encoding="utf-8",
    )
    log.append(f"Created artifact: {package.name}")


def archive_build_metadata(job: FreestyleJob, build: Build) -> Path:
    archive = job.workspace_root / job.name / "build-history.json"
    history = [
        {
            "number": item.number,
            "status": item.status.value,
            "parameters": item.parameters,
            "workspace": str(item.workspace),
        }
        for item in job.builds
    ]
    archive.write_text(json.dumps(history, indent=2), encoding="utf-8")
    return archive


def demonstrate() -> None:
    with tempfile.TemporaryDirectory(prefix="jenkins-freestyle-") as root:
        workspace_root = Path(root)

        job = FreestyleJob(
            name="release-application",
            description="Parameterized release-style Freestyle job",
            workspace_root=workspace_root,
        )

        job.add_parameter(
            ParameterDefinition(
                name="ENVIRONMENT",
                default="staging",
                choices=("development", "staging", "production"),
            )
        )
        job.add_parameter(
            ParameterDefinition(
                name="VERSION",
                default="1.0.0",
            )
        )

        job.add_trigger(TriggerType.TIMER)
        job.add_trigger(TriggerType.SCM)
        job.add_trigger(TriggerType.UPSTREAM)

        job.add_builder(write_workspace_manifest)
        job.add_builder(validate_environment)
        job.add_builder(package_application)

        build_one = job.run(
            {"ENVIRONMENT": "staging", "VERSION": "1.4.0"},
            trigger=TriggerType.SCM,
        )

        assert build_one.status == BuildStatus.SUCCESS
        assert (build_one.workspace / "manifest.json").exists()

        build_two = job.run(
            {"ENVIRONMENT": "production", "VERSION": "dev-2.0.0"},
            trigger=TriggerType.UPSTREAM,
        )

        assert build_two.status == BuildStatus.FAILURE
        assert any("development versions" in line for line in build_two.log)

        build_three = job.run(
            {"ENVIRONMENT": "production", "VERSION": "2.0.0"},
            trigger=TriggerType.MANUAL,
        )

        assert build_three.status == BuildStatus.SUCCESS
        assert len(job.builds) == 3

        archive = archive_build_metadata(job, build_three)

        print("Jenkins Freestyle Job Simulation")
        print("=" * 32)
        print(f"Job: {job.name}")
        print(f"Configured triggers: {sorted(t.value for t in job.triggers)}")
        print(f"Build history: {len(job.builds)} builds")
        print(f"History file: {archive}")

        for build in job.builds:
            print(
                f"\nBuild #{build.number}: {build.status.value}"
                f" | {build.parameters}"
            )
            for line in build.log:
                print(f"  {line}")


if __name__ == "__main__":
    demonstrate()
