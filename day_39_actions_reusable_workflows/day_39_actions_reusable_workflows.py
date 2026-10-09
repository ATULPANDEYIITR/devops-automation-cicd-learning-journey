#!/usr/bin/env python3
"""Executable model of GitHub Actions reusable workflows and composite actions.

The model distinguishes workflow-level reuse from step-level reuse, validates
workflow interfaces, resolves inputs, evaluates job dependencies, and simulates
a reusable deployment workflow invoking a composite deployment action.

This is a local educational simulator. It does not contact GitHub or execute
untrusted workflow YAML.
"""

from __future__ import annotations

import json
import re
import sys
import unittest
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence


class WorkflowError(Exception):
    """Base exception for workflow configuration and execution failures."""


class InputValidationError(WorkflowError):
    """Raised when a workflow or action input violates its declared contract."""


class DependencyError(WorkflowError):
    """Raised when a job dependency is absent or cannot be satisfied."""


class ExecutionError(WorkflowError):
    """Raised when a workflow step fails."""


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class InputSpec:
    name: str
    description: str
    required: bool = False
    default: str = ""
    allowed_values: tuple[str, ...] = ()

    def resolve(self, supplied: Mapping[str, Any]) -> str:
        value = supplied.get(self.name, self.default)

        if value is None:
            value = ""

        if not isinstance(value, (str, int, float, bool)):
            raise InputValidationError(
                f"Input {self.name!r} must be a scalar value."
            )

        resolved = str(value).lower() if isinstance(value, bool) else str(value)

        if self.required and not resolved.strip():
            raise InputValidationError(
                f"Required input {self.name!r} was not provided."
            )

        if self.allowed_values and resolved not in self.allowed_values:
            raise InputValidationError(
                f"Input {self.name!r} must be one of "
                f"{self.allowed_values}; received {resolved!r}."
            )

        return resolved


@dataclass(frozen=True)
class WorkflowContract:
    name: str
    inputs: tuple[InputSpec, ...]
    required_secrets: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()

    def validate(
        self,
        supplied_inputs: Mapping[str, Any],
        supplied_secrets: Mapping[str, str],
    ) -> dict[str, str]:
        known_inputs = {item.name for item in self.inputs}
        unknown_inputs = set(supplied_inputs) - known_inputs

        if unknown_inputs:
            raise InputValidationError(
                f"Unknown inputs for {self.name}: {sorted(unknown_inputs)}"
            )

        resolved = {
            spec.name: spec.resolve(supplied_inputs)
            for spec in self.inputs
        }

        missing_secrets = [
            name
            for name in self.required_secrets
            if not supplied_secrets.get(name)
        ]

        if missing_secrets:
            raise InputValidationError(
                f"Missing required secrets: {missing_secrets}"
            )

        return resolved


@dataclass
class Step:
    name: str
    run: Callable[[dict[str, Any]], None]
    continue_on_error: bool = False


@dataclass
class Job:
    name: str
    needs: tuple[str, ...] = ()
    steps: list[Step] = field(default_factory=list)
    status: JobStatus = JobStatus.PENDING
    error: str | None = None


@dataclass
class ExecutionContext:
    inputs: dict[str, str]
    secrets: dict[str, str]
    environment: dict[str, str]
    logs: list[str] = field(default_factory=list)
    outputs: dict[str, str] = field(default_factory=dict)

    def log(self, message: str) -> None:
        # Do not expose secret values in diagnostic output.
        safe_message = message
        for secret in self.secrets.values():
            if secret:
                safe_message = safe_message.replace(secret, "***")
        self.logs.append(safe_message)


class CompositeAction:
    """A reusable sequence of steps executed within one calling job."""

    def __init__(
        self,
        name: str,
        inputs: Sequence[InputSpec],
        steps: Sequence[Step],
        outputs: Sequence[str] = (),
    ) -> None:
        self.name = name
        self.inputs = tuple(inputs)
        self.steps = list(steps)
        self.output_names = tuple(outputs)

    def execute(
        self,
        supplied_inputs: Mapping[str, Any],
        context: ExecutionContext,
    ) -> dict[str, str]:
        known = {spec.name for spec in self.inputs}
        unknown = set(supplied_inputs) - known

        if unknown:
            raise InputValidationError(
                f"Unknown inputs for composite action {self.name}: "
                f"{sorted(unknown)}"
            )

        resolved = {
            spec.name: spec.resolve(supplied_inputs)
            for spec in self.inputs
        }

        action_context: dict[str, Any] = {
            "inputs": resolved,
            "environment": context.environment,
            "secrets": context.secrets,
            "outputs": {},
            "log": context.log,
        }

        for step in self.steps:
            try:
                context.log(f"Action {self.name}: {step.name}")
                step.run(action_context)
            except Exception as exc:
                if not step.continue_on_error:
                    raise ExecutionError(
                        f"Composite action {self.name}, step "
                        f"{step.name!r} failed: {exc}"
                    ) from exc
                context.log(f"Non-fatal action step failure: {exc}")

        result = action_context["outputs"]
        missing = set(self.output_names) - set(result)

        if missing:
            raise ExecutionError(
                f"Composite action did not produce outputs: {sorted(missing)}"
            )

        context.outputs.update(
            {f"{self.name}.{key}": str(value) for key, value in result.items()}
        )
        return {key: str(value) for key, value in result.items()}


class ReusableWorkflow:
    """A workflow callable through workflow_call-like inputs and secrets."""

    def __init__(
        self,
        contract: WorkflowContract,
        jobs: Sequence[Job],
        runner: Callable[[ExecutionContext, Job], None],
    ) -> None:
        self.contract = contract
        self.jobs = {job.name: job for job in jobs}
        self.runner = runner

        if len(self.jobs) != len(jobs):
            raise WorkflowError("Job names must be unique.")

        for job in jobs:
            missing = set(job.needs) - set(self.jobs)
            if missing:
                raise DependencyError(
                    f"Job {job.name} depends on missing jobs: {sorted(missing)}"
                )

        self._validate_acyclic()

    def _validate_acyclic(self) -> None:
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(name: str) -> None:
            if name in visiting:
                raise DependencyError(
                    f"Dependency cycle detected at job {name!r}."
                )
            if name in visited:
                return

            visiting.add(name)
            for dependency in self.jobs[name].needs:
                visit(dependency)
            visiting.remove(name)
            visited.add(name)

        for name in self.jobs:
            visit(name)

    def execute(
        self,
        supplied_inputs: Mapping[str, Any],
        supplied_secrets: Mapping[str, str],
        environment: Mapping[str, str] | None = None,
    ) -> ExecutionContext:
        resolved = self.contract.validate(supplied_inputs, supplied_secrets)
        context = ExecutionContext(
            inputs=resolved,
            secrets=dict(supplied_secrets),
            environment=dict(environment or {}),
        )

        # A workflow object can be reused for multiple invocations.
        for job in self.jobs.values():
            job.status = JobStatus.PENDING
            job.error = None

        remaining = set(self.jobs)

        while remaining:
            progressed = False

            for name in list(remaining):
                job = self.jobs[name]

                if any(
                    self.jobs[dependency].status
                    in (JobStatus.FAILURE, JobStatus.SKIPPED)
                    for dependency in job.needs
                ):
                    job.status = JobStatus.SKIPPED
                    context.log(f"Job {name} skipped: dependency did not succeed.")
                    remaining.remove(name)
                    progressed = True
                    continue

                if not all(
                    self.jobs[dependency].status == JobStatus.SUCCESS
                    for dependency in job.needs
                ):
                    continue

                job.status = JobStatus.RUNNING
                context.log(f"Starting job {name}.")

                try:
                    self.runner(context, job)
                    job.status = JobStatus.SUCCESS
                    context.log(f"Job {name} completed successfully.")
                except Exception as exc:
                    job.status = JobStatus.FAILURE
                    job.error = str(exc)
                    context.log(f"Job {name} failed: {exc}")

                remaining.remove(name)
                progressed = True

            if not progressed:
                raise DependencyError(
                    f"Jobs cannot progress: {sorted(remaining)}"
                )

        return context


def checkout_step(state: dict[str, Any]) -> None:
    environment = state["environment"]
    revision = environment.get("GITHUB_SHA", "")

    if not re.fullmatch(r"[0-9a-fA-F]{7,64}", revision):
        raise ExecutionError(
            "GITHUB_SHA must be a hexadecimal commit identifier."
        )

    state["log"](f"Validated checkout revision {revision[:12]}.")


def build_step(state: dict[str, Any]) -> None:
    environment = state["environment"]
    revision = environment["GITHUB_SHA"]
    version = state["inputs"]["release-version"]

    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise InputValidationError(
            "Release version must follow the numeric MAJOR.MINOR.PATCH format."
        )

    artifact = f"service-{version}-{revision[:12]}.tar"
    state["outputs"]["artifact-name"] = artifact
    state["log"](f"Prepared artifact metadata for {artifact}.")


def deployment_step(state: dict[str, Any]) -> None:
    environment = state["environment"]
    secrets = state["secrets"]
    target = state["inputs"]["target-environment"]

    if target == "production":
        if environment.get("PRODUCTION_APPROVED") != "true":
            raise ExecutionError(
                "Production deployment requires an explicit approval signal."
            )

    token = secrets.get("DEPLOY_TOKEN", "")
    if len(token) < 16:
        raise ExecutionError("Deployment credential does not meet minimum length.")

    # A real action would invoke a deployment API. This simulation deliberately
    # avoids network access and never prints the credential.
    state["outputs"]["deployment-target"] = target
    state["log"](f"Deployment request validated for {target}.")


def make_deployment_action() -> CompositeAction:
    return CompositeAction(
        name="deploy-service",
        inputs=(
            InputSpec(
                "target-environment",
                "Deployment destination",
                required=True,
                allowed_values=("staging", "production"),
            ),
            InputSpec(
                "release-version",
                "Semantic release version",
                required=True,
            ),
        ),
        steps=(
            Step("validate revision", checkout_step),
            Step("prepare artifact", build_step),
            Step("validate deployment request", deployment_step),
        ),
        outputs=("artifact-name", "deployment-target"),
    )


def make_release_workflow(action: CompositeAction) -> ReusableWorkflow:
    contract = WorkflowContract(
        name="reusable-release",
        inputs=(
            InputSpec(
                "release-version",
                "Release version",
                required=True,
            ),
            InputSpec(
                "target-environment",
                "Release destination",
                default="staging",
                allowed_values=("staging", "production"),
            ),
        ),
        required_secrets=("DEPLOY_TOKEN",),
        outputs=("artifact-name",),
    )

    def run_job(context: ExecutionContext, job: Job) -> None:
        if job.name == "test":
            context.log("Unit tests and release metadata checks passed.")
            return

        if job.name == "release":
            action.execute(
                {
                    "target-environment": context.inputs["target-environment"],
                    "release-version": context.inputs["release-version"],
                },
                context,
            )
            return

        if job.name == "audit":
            artifact = context.outputs.get("deploy-service.artifact-name")
            if not artifact:
                raise ExecutionError("Release artifact metadata is unavailable.")
            context.log(f"Recorded deployment audit entry for {artifact}.")
            return

        raise ExecutionError(f"Unknown job {job.name!r}")

    return ReusableWorkflow(
        contract=contract,
        jobs=(
            Job("test"),
            Job("release", needs=("test",)),
            Job("audit", needs=("release",)),
        ),
        runner=run_job,
    )


def validate_manifest(manifest: Mapping[str, Any]) -> list[str]:
    """Validate selected reusable-workflow and composite-action invariants."""

    errors: list[str] = []
    workflow_call = manifest.get("on", {}).get("workflow_call", {})
    if not isinstance(workflow_call, dict):
        errors.append("workflow_call must be a mapping.")
        return errors

    declared_inputs = workflow_call.get("inputs", {})
    for name, definition in declared_inputs.items():
        if not isinstance(definition, dict):
            errors.append(f"Input {name!r} must have a mapping definition.")
            continue

        if definition.get("required") and "default" in definition:
            errors.append(
                f"Required input {name!r} also declares a default; "
                "review the intended contract."
            )

        if definition.get("type") not in ("string", "boolean", "number"):
            errors.append(f"Input {name!r} has an unsupported declared type.")

    jobs = manifest.get("jobs", {})
    for name, definition in jobs.items():
        if not isinstance(definition, dict):
            errors.append(f"Job {name!r} must be a mapping.")
            continue

        if "uses" in definition and "steps" in definition:
            errors.append(
                f"Job {name!r} cannot combine a reusable workflow call "
                "with a normal steps list."
            )

        if "uses" in definition and "runs-on" in definition:
            errors.append(
                f"Reusable workflow call job {name!r} must not define runs-on."
            )

        if "uses" in definition and not re.search(
            r"@([0-9a-fA-F]{40}|v?\d+(?:\.\d+){0,2})$",
            definition["uses"],
        ):
            errors.append(
                f"Job {name!r} should pin its reusable workflow to a "
                "version tag or full commit SHA."
            )

    return errors


def demo_manifest_validation() -> None:
    good_manifest = {
        "on": {
            "workflow_call": {
                "inputs": {
                    "release-version": {
                        "type": "string",
                        "required": True,
                    }
                }
            }
        },
        "jobs": {
            "release": {
                "uses": "acme/automation/.github/workflows/release.yml@v2.1.0",
                "with": {"release-version": "2.4.1"},
            }
        },
    }

    bad_manifest = {
        "on": {"workflow_call": {"inputs": {}}},
        "jobs": {
            "release": {
                "uses": "acme/automation/.github/workflows/release.yml@main",
                "runs-on": "ubuntu-latest",
                "steps": [],
            }
        },
    }

    assert validate_manifest(good_manifest) == []
    errors = validate_manifest(bad_manifest)
    assert len(errors) >= 2

    print("Manifest validation:")
    print(f"  Valid manifest errors: {validate_manifest(good_manifest)}")
    for error in errors:
        print(f"  Invalid manifest: {error}")


class WorkflowModelTests(unittest.TestCase):
    def setUp(self) -> None:
        self.workflow = make_release_workflow(make_deployment_action())
        self.secrets = {"DEPLOY_TOKEN": "secure-demo-token-12345"}
        self.environment = {
            "GITHUB_SHA": "a4c31e98d01234567890abcdef1234567890abcd",
            "PRODUCTION_APPROVED": "false",
        }

    def test_staging_release(self) -> None:
        context = self.workflow.execute(
            {"release-version": "2.4.1"},
            self.secrets,
            self.environment,
        )
        self.assertEqual(self.workflow.jobs["release"].status, JobStatus.SUCCESS)
        self.assertEqual(
            context.outputs["deploy-service.deployment-target"],
            "staging",
        )

    def test_production_requires_approval(self) -> None:
        self.workflow.execute(
            {
                "release-version": "2.4.1",
                "target-environment": "production",
            },
            self.secrets,
            self.environment,
        )
        self.assertEqual(self.workflow.jobs["release"].status, JobStatus.FAILURE)
        self.assertEqual(self.workflow.jobs["audit"].status, JobStatus.SKIPPED)

    def test_invalid_version_rejected(self) -> None:
        with self.assertRaises(InputValidationError):
            self.workflow.contract.validate(
                {
                    "release-version": "",
                    "target-environment": "staging",
                },
                self.secrets,
            )

    def test_unknown_input_rejected(self) -> None:
        with self.assertRaises(InputValidationError):
            self.workflow.contract.validate(
                {
                    "release-version": "2.4.1",
                    "unrecognized": "value",
                },
                self.secrets,
            )

    def test_missing_secret_rejected(self) -> None:
        with self.assertRaises(InputValidationError):
            self.workflow.contract.validate(
                {"release-version": "2.4.1"},
                {},
            )

    def test_invalid_revision_fails_release(self) -> None:
        environment = dict(self.environment)
        environment["GITHUB_SHA"] = "not-a-commit"
        self.workflow.execute(
            {"release-version": "2.4.1"},
            self.secrets,
            environment,
        )
        self.assertEqual(self.workflow.jobs["release"].status, JobStatus.FAILURE)

    def test_dependency_cycle_rejected(self) -> None:
        with self.assertRaises(DependencyError):
            ReusableWorkflow(
                WorkflowContract("cycle", (), ()),
                (Job("a", needs=("b",)), Job("b", needs=("a",))),
                lambda context, job: None,
            )

    def test_secret_not_written_to_logs(self) -> None:
        context = self.workflow.execute(
            {"release-version": "2.4.1"},
            self.secrets,
            self.environment,
        )
        self.assertTrue(
            all(self.secrets["DEPLOY_TOKEN"] not in line for line in context.logs)
        )


def run_demo() -> None:
    workflow = make_release_workflow(make_deployment_action())
    environment = {
        "GITHUB_SHA": "a4c31e98d01234567890abcdef1234567890abcd",
        "PRODUCTION_APPROVED": "false",
    }
    secrets = {"DEPLOY_TOKEN": "secure-demo-token-12345"}

    print("Reusable workflow and composite action simulation")
    context = workflow.execute(
        {"release-version": "2.4.1", "target-environment": "staging"},
        secrets,
        environment,
    )

    for entry in context.logs:
        print(f"  {entry}")

    print("Job states:")
    print(
        json.dumps(
            {name: job.status.value for name, job in workflow.jobs.items()},
            indent=2,
        )
    )
    print("Outputs:")
    print(json.dumps(context.outputs, indent=2))

    print("\nProduction policy failure demonstration")
    production_context = workflow.execute(
        {
            "release-version": "2.4.1",
            "target-environment": "production",
        },
        secrets,
        environment,
    )
    for entry in production_context.logs:
        print(f"  {entry}")

    print("\nWorkflow manifest checks")
    demo_manifest_validation()


if __name__ == "__main__":
    if "--test" in sys.argv:
        unittest.main(argv=[sys.argv[0]], verbosity=2)
    else:
        run_demo()
