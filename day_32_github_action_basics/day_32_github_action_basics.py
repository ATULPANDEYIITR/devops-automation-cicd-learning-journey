#!/usr/bin/env python3
"""
GitHub Actions Basics: workflow files, events, jobs, and steps.

This executable learning model represents the core structure of a GitHub Actions
workflow without requiring GitHub credentials, network access, or third-party
packages.

The model focuses on four closely related concepts:

- Workflow files: YAML documents stored under .github/workflows/.
- Events: repository or scheduled activities that can trigger a workflow.
- Jobs: independent units of work executed by a runner.
- Steps: ordered commands or actions executed inside a job.

The simulator also demonstrates dependencies, conditions, matrix expansion,
environment variables, outputs, failures, cancellation, concurrency, and
workflow validation. These advanced mechanisms are included only where they
directly explain how workflows execute.

The examples intentionally use repository-development scenarios such as
testing, linting, building, and deployment.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Callable, Iterable


# ---------------------------------------------------------------------------
# Workflow fundamentals
# ---------------------------------------------------------------------------

class JobStatus(str, Enum):
    """Possible lifecycle states for a simulated job."""

    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Event:
    """
    A repository event that may trigger a workflow.

    GitHub Actions supports many event types. The simulator concentrates on
    common development events and keeps event payload data so filters can be
    evaluated against realistic information such as a branch name.
    """

    name: str
    branch: str = "main"
    actor: str = "developer"
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class Step:
    """
    A workflow step.

    A step can either run a shell command or invoke a Python callable. The
    callable makes the simulator deterministic and allows the learning example
    to demonstrate step behavior without external services.
    """

    name: str
    command: str | None = None
    action: Callable[["ExecutionContext"], None] | None = None
    condition: Callable[["ExecutionContext"], bool] | None = None
    continue_on_error: bool = False
    env: dict[str, str] = field(default_factory=dict)


@dataclass
class Job:
    """
    A unit of work executed on a runner.

    `needs` expresses a dependency on another job. A dependent job does not
    start until its required jobs have completed successfully unless its own
    condition explicitly permits execution after failure.
    """

    name: str
    runs_on: str
    steps: list[Step]
    needs: list[str] = field(default_factory=list)
    condition: Callable[["WorkflowContext"], bool] | None = None
    matrix: dict[str, list[Any]] = field(default_factory=dict)
    env: dict[str, str] = field(default_factory=dict)
    status: JobStatus = JobStatus.QUEUED
    outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class Workflow:
    """
    A workflow definition.

    A real GitHub Actions workflow is represented by YAML. This Python class
    mirrors the important semantic pieces so the execution rules can be
    demonstrated directly.
    """

    name: str
    events: set[str]
    jobs: dict[str, Job]
    branches: set[str] | None = None
    path: str = ".github/workflows/ci.yml"


@dataclass
class ExecutionContext:
    """State available while a job's steps execute."""

    workflow: Workflow
    event: Event
    job: Job
    workspace: Path
    environment: dict[str, str]
    outputs: dict[str, str] = field(default_factory=dict)
    step_results: dict[str, JobStatus] = field(default_factory=dict)

    def set_output(self, name: str, value: str) -> None:
        """Store a job output that can be consumed by later workflow logic."""
        self.outputs[name] = value
        self.job.outputs[name] = value

    def log(self, message: str) -> None:
        """Print a workflow-style log line."""
        print(f"      {message}")


@dataclass
class WorkflowContext:
    """State shared across the complete workflow execution."""

    workflow: Workflow
    event: Event
    workspace: Path
    job_results: dict[str, JobStatus] = field(default_factory=dict)
    job_outputs: dict[str, dict[str, str]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

def heading(title: str) -> None:
    """Print a readable console heading without relying on external packages."""
    print("\n" + "=" * 76)
    print(title)
    print("=" * 76)


def normalize_environment(
    base: dict[str, str],
    additions: dict[str, str],
) -> dict[str, str]:
    """Create a job environment without mutating the workflow definition."""
    environment = dict(base)
    environment.update(additions)
    return environment


def safe_slug(value: str) -> str:
    """Convert a repository-style value into a safe identifier."""
    return re.sub(r"[^A-Za-z0-9_.-]+", "-", value).strip("-").lower()


def expand_matrix(matrix: dict[str, list[Any]]) -> list[dict[str, Any]]:
    """
    Expand a Cartesian-product matrix.

    For example, Python versions [3.11, 3.12] and operating systems [linux,
    windows] produce four job variants. Matrix expansion happens conceptually
    before runners execute the individual variants.
    """
    if not matrix:
        return [{}]

    dimensions = list(matrix.items())
    combinations: list[dict[str, Any]] = [{}]

    for dimension_name, values in dimensions:
        if not values:
            raise ValueError(f"Matrix dimension '{dimension_name}' is empty")

        next_combinations: list[dict[str, Any]] = []
        for existing in combinations:
            for value in values:
                combination = dict(existing)
                combination[dimension_name] = value
                next_combinations.append(combination)
        combinations = next_combinations

    return combinations


# ---------------------------------------------------------------------------
# Event handling
# ---------------------------------------------------------------------------

def event_matches(workflow: Workflow, event: Event) -> bool:
    """
    Determine whether an event triggers a workflow.

    Event matching is separate from job execution. A workflow can exist in a
    repository but remain dormant for events that do not match its trigger
    configuration.
    """
    if event.name not in workflow.events:
        return False

    if workflow.branches is not None and event.branch not in workflow.branches:
        return False

    return True


def demonstrate_events() -> None:
    """Show how the same workflow reacts differently to repository events."""
    heading("EVENTS: deciding when a workflow starts")

    workflow = Workflow(
        name="Continuous Integration",
        events={"push", "pull_request"},
        branches={"main", "develop"},
        jobs={},
    )

    events = [
        Event("push", "main", "atul"),
        Event("pull_request", "main", "reviewer"),
        Event("push", "feature/payment-refactor", "atul"),
        Event("schedule", "main", "github-actions"),
    ]

    for event in events:
        result = "TRIGGERED" if event_matches(workflow, event) else "IGNORED"
        print(
            f"{event.name:13} branch={event.branch:28} "
            f"actor={event.actor:18} -> {result}"
        )

    print(
        "\nThe event decides whether workflow execution begins. It does not "
        "itself perform the repository's tests or build."
    )


# ---------------------------------------------------------------------------
# Step implementations
# ---------------------------------------------------------------------------

def checkout_repository(context: ExecutionContext) -> None:
    """
    Simulate actions/checkout.

    The real checkout action retrieves repository content into the runner
    workspace. Here the workspace already contains a small repository fixture,
    so the step demonstrates the role rather than contacting GitHub.
    """
    context.log(f"Repository available at {context.workspace}")
    files = sorted(path.name for path in context.workspace.iterdir())
    context.log(f"Workspace files: {', '.join(files)}")


def install_dependencies(context: ExecutionContext) -> None:
    """Simulate dependency installation based on the selected environment."""
    version = context.environment.get("PYTHON_VERSION", "system")
    context.log(f"Preparing dependencies for Python {version}")
    context.log("Dependency installation completed")


def run_unit_tests(context: ExecutionContext) -> None:
    """
    Execute real Python assertions against a temporary project.

    This is intentionally executable rather than a textual claim about tests.
    """
    project = context.workspace / "calculator.py"
    project.write_text(
        "def add(a, b):\n"
        "    return a + b\n\n"
        "def divide(a, b):\n"
        "    if b == 0:\n"
        "        raise ValueError('division by zero')\n"
        "    return a / b\n",
        encoding="utf-8",
    )

    test_code = (
        "from calculator import add, divide\n"
        "assert add(2, 3) == 5\n"
        "assert divide(10, 2) == 5\n"
        "try:\n"
        "    divide(1, 0)\n"
        "except ValueError:\n"
        "    pass\n"
        "else:\n"
        "    raise AssertionError('division by zero was accepted')\n"
    )

    test_file = context.workspace / "test_calculator.py"
    test_file.write_text(test_code, encoding="utf-8")

    result = subprocess.run(
        [os.environ.get("PYTHON", shutil.which("python") or "python"), "-m", "pytest", "-q"],
        cwd=context.workspace,
        text=True,
        capture_output=True,
    )

    if result.returncode != 0:
        # Some minimal environments do not have pytest. Fall back to direct
        # execution so this educational simulator remains self-contained.
        context.log("pytest is unavailable or failed; running deterministic assertions")
        namespace: dict[str, Any] = {}
        exec(project.read_text(encoding="utf-8"), namespace)
        assert namespace["add"](2, 3) == 5
        assert namespace["divide"](10, 2) == 5
        try:
            namespace["divide"](1, 0)
        except ValueError:
            pass
        else:
            raise AssertionError("division by zero was accepted")
    else:
        context.log(result.stdout.strip())

    context.log("Unit tests passed")


def run_linter(context: ExecutionContext) -> None:
    """
    Perform a small source-quality check.

    A real workflow might invoke Ruff, ESLint, clang-tidy, or another tool.
    The example checks a concrete repository file without requiring a package.
    """
    source = context.workspace / "calculator.py"
    text = source.read_text(encoding="utf-8")

    if "\t" in text:
        raise RuntimeError("Lint failure: tab characters detected")

    if len(text) > 5000:
        raise RuntimeError("Lint failure: example source exceeds policy limit")

    context.log("Lint checks passed")


def build_artifact(context: ExecutionContext) -> None:
    """Create an artifact-like file after validation succeeds."""
    artifact = context.workspace / "build" / "release.txt"
    artifact.parent.mkdir(exist_ok=True)
    artifact.write_text(
        "Repository build artifact\n"
        f"event={context.event.name}\n"
        f"branch={context.event.branch}\n"
        f"runner={context.job.runs_on}\n",
        encoding="utf-8",
    )
    context.log(f"Built artifact: {artifact.relative_to(context.workspace)}")


def publish_test_result(context: ExecutionContext) -> None:
    """Demonstrate a job output consumed by another part of the workflow."""
    passed = context.environment.get("TESTS_PASSED", "true")
    context.set_output("quality_gate", "passed" if passed == "true" else "failed")
    context.log(f"Job output quality_gate={context.outputs['quality_gate']}")


def demonstrate_step_order() -> None:
    """Explain the essential ordered nature of steps inside one job."""
    heading("STEPS: ordered work inside a job")

    with tempfile.TemporaryDirectory(prefix="actions-basics-") as temporary:
        workspace = Path(temporary)
        (workspace / "README.txt").write_text(
            "Repository fixture for workflow execution\n",
            encoding="utf-8",
        )

        workflow = Workflow(
            name="CI",
            events={"push"},
            jobs={},
        )

        job = Job(
            name="test",
            runs_on="ubuntu-latest",
            steps=[
                Step("Checkout repository", action=checkout_repository),
                Step("Install dependencies", action=install_dependencies),
                Step("Run unit tests", action=run_unit_tests),
                Step("Run linter", action=run_linter),
                Step("Build artifact", action=build_artifact),
            ],
        )

        context = ExecutionContext(
            workflow=workflow,
            event=Event("push", "main", "atul"),
            job=job,
            workspace=workspace,
            environment={},
        )

        for step in job.steps:
            print(f"    -> {step.name}")
            if step.action is not None:
                step.action(context)

    print(
        "\nA step is not a separate job. Steps share the job's runner context, "
        "workspace, environment, and filesystem."
    )


# ---------------------------------------------------------------------------
# Job execution
# ---------------------------------------------------------------------------

def execute_job(
    workflow_context: WorkflowContext,
    job_template: Job,
    matrix_values: dict[str, Any] | None = None,
) -> JobStatus:
    """
    Execute one concrete job instance.

    Job dependencies are checked before this function is called. A failure in a
    normal step stops later steps in the same job. `continue_on_error` changes
    that behavior for the individual step.
    """
    matrix_values = matrix_values or {}

    if job_template.condition is not None and not job_template.condition(
        workflow_context
    ):
        job_template.status = JobStatus.SKIPPED
        print(f"  Job '{job_template.name}' -> SKIPPED")
        return JobStatus.SKIPPED

    job = Job(
        name=job_template.name,
        runs_on=job_template.runs_on,
        steps=job_template.steps,
        needs=list(job_template.needs),
        condition=job_template.condition,
        matrix=job_template.matrix,
        env=dict(job_template.env),
    )
    job.status = JobStatus.RUNNING

    matrix_suffix = ""
    if matrix_values:
        matrix_suffix = " [" + ", ".join(
            f"{key}={value}" for key, value in matrix_values.items()
        ) + "]"

    print(f"  Job '{job.name}'{matrix_suffix} on {job.runs_on}")

    environment = normalize_environment(
        {
            "CI": "true",
            "GITHUB_EVENT_NAME": workflow_context.event.name,
            "GITHUB_REF_NAME": workflow_context.event.branch,
            "GITHUB_ACTOR": workflow_context.event.actor,
            "RUNNER_OS": job.runs_on,
        },
        job.env | {key.upper(): str(value) for key, value in matrix_values.items()},
    )

    with tempfile.TemporaryDirectory(prefix="job-workspace-") as temporary:
        workspace = Path(temporary)
        (workspace / "README.md").write_text(
            "# Example repository\n",
            encoding="utf-8",
        )

        context = ExecutionContext(
            workflow=workflow_context.workflow,
            event=workflow_context.event,
            job=job,
            workspace=workspace,
            environment=environment,
        )

        for step in job.steps:
            if step.condition is not None and not step.condition(context):
                context.step_results[step.name] = JobStatus.SKIPPED
                print(f"    Step '{step.name}' -> SKIPPED")
                continue

            step_environment = normalize_environment(
                environment,
                step.env,
            )
            context.environment = step_environment

            print(f"    Step '{step.name}' -> RUNNING")

            try:
                if step.action is not None:
                    step.action(context)
                elif step.command is not None:
                    execute_shell_step(step.command, context)
                else:
                    raise ValueError(
                        f"Step '{step.name}' has neither action nor command"
                    )

                context.step_results[step.name] = JobStatus.SUCCESS
                print(f"    Step '{step.name}' -> SUCCESS")

            except Exception as exc:
                context.step_results[step.name] = JobStatus.FAILURE
                print(f"    Step '{step.name}' -> FAILURE: {exc}")

                if not step.continue_on_error:
                    job.status = JobStatus.FAILURE
                    print(f"  Job '{job.name}' -> FAILURE")
                    return JobStatus.FAILURE

        job.outputs = context.outputs

    job.status = JobStatus.SUCCESS
    print(f"  Job '{job.name}' -> SUCCESS")
    return JobStatus.SUCCESS


def execute_shell_step(command: str, context: ExecutionContext) -> None:
    """
    Execute a shell command safely enough for this local educational example.

    Shell commands in real workflows execute on a runner with the permissions
    granted to the workflow. Untrusted input should never be interpolated into
    shell commands without careful validation and escaping.
    """
    result = subprocess.run(
        command,
        cwd=context.workspace,
        shell=True,
        text=True,
        capture_output=True,
        env={**os.environ, **context.environment},
    )

    if result.stdout.strip():
        context.log(result.stdout.strip())

    if result.returncode != 0:
        raise RuntimeError(
            f"command exited with status {result.returncode}: "
            f"{result.stderr.strip()}"
        )


def topological_order(jobs: dict[str, Job]) -> list[str]:
    """
    Produce a dependency-safe job order.

    A cycle such as build -> test -> build is invalid because no job can become
    ready. Detecting it before execution prevents an ambiguous workflow state.
    """
    temporary: set[str] = set()
    permanent: set[str] = set()
    order: list[str] = []

    def visit(job_name: str) -> None:
        if job_name in permanent:
            return

        if job_name in temporary:
            raise ValueError(f"Cyclic job dependency detected at '{job_name}'")

        if job_name not in jobs:
            raise ValueError(f"Job dependency references unknown job '{job_name}'")

        temporary.add(job_name)

        for dependency in jobs[job_name].needs:
            visit(dependency)

        temporary.remove(job_name)
        permanent.add(job_name)
        order.append(job_name)

    for job_name in jobs:
        visit(job_name)

    return order


def execute_workflow(workflow: Workflow, event: Event) -> WorkflowContext:
    """
    Run the complete workflow model.

    This function separates workflow-level triggering from job-level execution.
    It also expands matrix jobs and respects dependency results.
    """
    heading(f"WORKFLOW EXECUTION: {workflow.name}")

    if not event_matches(workflow, event):
        print(
            f"Workflow ignored event '{event.name}' on branch '{event.branch}'."
        )
        return WorkflowContext(workflow, event, Path("."))

    with tempfile.TemporaryDirectory(prefix="workflow-") as temporary:
        workflow_context = WorkflowContext(
            workflow=workflow,
            event=event,
            workspace=Path(temporary),
        )

        order = topological_order(workflow.jobs)

        for job_name in order:
            job = workflow.jobs[job_name]

            dependency_statuses = [
                workflow_context.job_results[dependency]
                for dependency in job.needs
            ]

            if any(
                status in {JobStatus.FAILURE, JobStatus.CANCELLED}
                for status in dependency_statuses
            ):
                workflow_context.job_results[job_name] = JobStatus.SKIPPED
                print(
                    f"  Job '{job_name}' -> SKIPPED because a required "
                    "dependency failed"
                )
                continue

            variants = expand_matrix(job.matrix)
            variant_statuses: list[JobStatus] = []

            for variant in variants:
                status = execute_job(workflow_context, job, variant)
                variant_statuses.append(status)

            if any(status == JobStatus.FAILURE for status in variant_statuses):
                workflow_context.job_results[job_name] = JobStatus.FAILURE
            elif all(status == JobStatus.SKIPPED for status in variant_statuses):
                workflow_context.job_results[job_name] = JobStatus.SKIPPED
            else:
                workflow_context.job_results[job_name] = JobStatus.SUCCESS

            workflow_context.job_outputs[job_name] = dict(job.outputs)

        print("\nWorkflow result:")
        for name, status in workflow_context.job_results.items():
            print(f"  {name:20} {status.value}")

        return workflow_context


# ---------------------------------------------------------------------------
# Conditions, environment variables, and outputs
# ---------------------------------------------------------------------------

def demonstrate_conditions_and_environment() -> None:
    """Show why conditions and scoped environment variables matter."""
    heading("CONDITIONS, ENVIRONMENT VARIABLES, AND JOB OUTPUTS")

    workflow = Workflow(
        name="Release preparation",
        events={"push"},
        branches={"main"},
        jobs={
            "test": Job(
                name="test",
                runs_on="ubuntu-latest",
                env={"TESTS_PASSED": "true"},
                steps=[
                    Step(
                        "Record quality gate",
                        action=publish_test_result,
                    ),
                ],
            ),
            "deploy": Job(
                name="deploy",
                runs_on="ubuntu-latest",
                needs=["test"],
                condition=lambda context: context.event.branch == "main",
                steps=[
                    Step(
                        "Verify release branch",
                        action=lambda context: context.log(
                            f"Deploying commit context from {context.event.branch}"
                        ),
                    ),
                    Step(
                        "Print controlled environment",
                        command="python -c \"import os; print('CI=' + os.environ.get('CI', ''))\"",
                    ),
                ],
            ),
        },
    )

    execute_workflow(workflow, Event("push", "main", "release-bot"))


# ---------------------------------------------------------------------------
# Matrix jobs
# ---------------------------------------------------------------------------

def demonstrate_matrix() -> None:
    """Demonstrate how one job definition can produce several job variants."""
    heading("MATRIX JOBS")

    workflow = Workflow(
        name="Compatibility tests",
        events={"push"},
        jobs={
            "test": Job(
                name="test",
                runs_on="ubuntu-latest",
                matrix={
                    "python_version": ["3.11", "3.12", "3.13"],
                    "database": ["postgres", "sqlite"],
                },
                steps=[
                    Step(
                        "Run compatibility check",
                        action=lambda context: context.log(
                            "Compatibility environment: "
                            f"Python {context.environment['PYTHON_VERSION']}, "
                            f"database={context.environment['DATABASE']}"
                        ),
                    ),
                ],
            )
        },
    )

    execute_workflow(workflow, Event("push", "main", "atul"))

    combinations = expand_matrix(workflow.jobs["test"].matrix)
    print(f"\nMatrix expansion produced {len(combinations)} independent variants.")


# ---------------------------------------------------------------------------
# Failure handling
# ---------------------------------------------------------------------------

def demonstrate_failure_handling() -> None:
    """
    Show the difference between an ordinary failing step and
    continue-on-error.
    """
    heading("FAILURE HANDLING")

    workflow = Workflow(
        name="Failure example",
        events={"push"},
        jobs={
            "quality": Job(
                name="quality",
                runs_on="ubuntu-latest",
                steps=[
                    Step(
                        "Required validation",
                        action=lambda context: (_ for _ in ()).throw(
                            RuntimeError("simulated quality failure")
                        ),
                    ),
                    Step(
                        "Never reached after required failure",
                        action=lambda context: context.log("unexpected execution"),
                    ),
                ],
            ),
            "informational": Job(
                name="informational",
                runs_on="ubuntu-latest",
                steps=[
                    Step(
                        "Non-blocking diagnostic",
                        action=lambda context: (_ for _ in ()).throw(
                            RuntimeError("diagnostic command failed")
                        ),
                        continue_on_error=True,
                    ),
                    Step(
                        "Continue after diagnostic",
                        action=lambda context: context.log(
                            "Execution continues because continue_on_error is true"
                        ),
                    ),
                ],
            ),
        },
    )

    execute_workflow(workflow, Event("push", "main", "atul"))


# ---------------------------------------------------------------------------
# Workflow-file validation
# ---------------------------------------------------------------------------

def validate_workflow_structure(document: dict[str, Any]) -> list[str]:
    """
    Validate a simplified workflow representation.

    This is not a full GitHub Actions YAML parser. It checks structural rules
    that are useful for understanding the relationship among name, triggers,
    jobs, needs, runs-on, and steps.
    """
    errors: list[str] = []

    if not isinstance(document, dict):
        return ["Workflow must be an object"]

    if not document.get("name"):
        errors.append("Workflow name is required")

    if "on" not in document:
        errors.append("Workflow trigger configuration is required")

    jobs = document.get("jobs")
    if not isinstance(jobs, dict) or not jobs:
        errors.append("At least one job is required")
        return errors

    for job_id, job in jobs.items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_-]*", job_id):
            errors.append(f"Invalid job identifier: {job_id}")

        if not isinstance(job, dict):
            errors.append(f"Job '{job_id}' must be an object")
            continue

        if not job.get("runs-on"):
            errors.append(f"Job '{job_id}' is missing runs-on")

        steps = job.get("steps")
        if not isinstance(steps, list) or not steps:
            errors.append(f"Job '{job_id}' must contain at least one step")
            continue

        for index, step in enumerate(steps):
            if not isinstance(step, dict):
                errors.append(
                    f"Job '{job_id}' step {index} must be an object"
                )
                continue

            if not step.get("name"):
                errors.append(
                    f"Job '{job_id}' step {index} is missing a name"
                )

            if "run" not in step and "uses" not in step:
                errors.append(
                    f"Job '{job_id}' step {index} needs run or uses"
                )

        for dependency in job.get("needs", []):
            if dependency not in jobs:
                errors.append(
                    f"Job '{job_id}' needs unknown job '{dependency}'"
                )

    try:
        simplified_jobs = {
            job_id: Job(
                name=job_id,
                runs_on=str(job["runs-on"]),
                steps=[
                    Step(
                        name=str(step.get("name", "unnamed")),
                        command=step.get("run"),
                    )
                    for step in job["steps"]
                ],
                needs=list(job.get("needs", [])),
            )
            for job_id, job in jobs.items()
            if isinstance(job, dict) and "runs-on" in job
        }
        topological_order(simplified_jobs)
    except ValueError as exc:
        errors.append(str(exc))

    return errors


def demonstrate_workflow_validation() -> None:
    """Validate a correct workflow model and a deliberately broken one."""
    heading("WORKFLOW FILE STRUCTURE VALIDATION")

    valid = {
        "name": "CI",
        "on": {"push": {"branches": ["main"]}},
        "jobs": {
            "test": {
                "runs-on": "ubuntu-latest",
                "steps": [
                    {"name": "Run tests", "run": "python -m pytest"},
                ],
            },
            "build": {
                "needs": ["test"],
                "runs-on": "ubuntu-latest",
                "steps": [
                    {"name": "Build", "run": "python build.py"},
                ],
            },
        },
    }

    invalid = {
        "name": "Broken CI",
        "on": {"push": {}},
        "jobs": {
            "test": {
                "runs-on": "ubuntu-latest",
                "needs": ["missing-job"],
                "steps": [
                    {"name": "Missing implementation"},
                ],
            }
        },
    }

    for label, document in [("valid workflow", valid), ("invalid workflow", invalid)]:
        errors = validate_workflow_structure(document)
        print(f"\n{label}:")
        if errors:
            for error in errors:
                print(f"  ERROR: {error}")
        else:
            print("  VALID")


# ---------------------------------------------------------------------------
# Practical GitHub Actions concepts
# ---------------------------------------------------------------------------

def demonstrate_job_dependencies() -> None:
    """Show a realistic test -> build -> deploy dependency graph."""
    heading("JOB DEPENDENCIES: TEST -> BUILD -> DEPLOY")

    workflow = Workflow(
        name="Application delivery",
        events={"push"},
        branches={"main"},
        jobs={
            "test": Job(
                name="test",
                runs_on="ubuntu-latest",
                steps=[
                    Step(
                        "Run tests",
                        action=lambda context: context.log(
                            "Application test suite passed"
                        ),
                    )
                ],
            ),
            "build": Job(
                name="build",
                runs_on="ubuntu-latest",
                needs=["test"],
                steps=[
                    Step(
                        "Compile application",
                        action=lambda context: context.log(
                            "Build output generated"
                        ),
                    )
                ],
            ),
            "deploy": Job(
                name="deploy",
                runs_on="ubuntu-latest",
                needs=["build"],
                condition=lambda context: context.event.branch == "main",
                steps=[
                    Step(
                        "Deploy release",
                        action=lambda context: context.log(
                            "Release deployment permitted for main"
                        ),
                    )
                ],
            ),
        },
    )

    execute_workflow(workflow, Event("push", "main", "release-bot"))


# ---------------------------------------------------------------------------
# Advanced practical model: pull-request-oriented CI
# ---------------------------------------------------------------------------

def demonstrate_pull_request_ci() -> None:
    """
    Demonstrate a common GitHub Actions workflow shape for pull requests.

    The event is pull_request rather than push, and the jobs represent separate
    concerns. The example does not implement GitHub's API; it models the
    workflow execution that follows a matching event.
    """
    heading("REALISTIC CI: PULL REQUEST VALIDATION")

    workflow = Workflow(
        name="Pull Request CI",
        events={"pull_request"},
        jobs={
            "lint": Job(
                name="lint",
                runs_on="ubuntu-latest",
                steps=[
                    Step(
                        "Check source style",
                        action=lambda context: context.log(
                            "Lint rules evaluated against changed repository code"
                        ),
                    )
                ],
            ),
            "test": Job(
                name="test",
                runs_on="ubuntu-latest",
                steps=[
                    Step(
                        "Execute unit tests",
                        action=lambda context: context.log(
                            "Unit and integration tests completed"
                        ),
                    )
                ],
            ),
            "build": Job(
                name="build",
                runs_on="ubuntu-latest",
                needs=["lint", "test"],
                steps=[
                    Step(
                        "Build application",
                        action=lambda context: context.log(
                            "Application build completed only after lint and test jobs passed"
                        ),
                    )
                ],
            ),
        },
    )

    event = Event(
        name="pull_request",
        branch="main",
        actor="contributor",
        payload={
            "action": "opened",
            "pull_request": {
                "number": 42,
                "draft": False,
            },
        },
    )

    execute_workflow(workflow, event)


# ---------------------------------------------------------------------------
# Security and production considerations
# ---------------------------------------------------------------------------

def demonstrate_security_checks() -> None:
    """
    Show workflow-specific security rules as executable validation.

    The checks focus on dangerous patterns that can appear in workflow
    configuration, particularly shell interpolation and excessive permissions.
    """
    heading("SECURITY: WORKFLOW CONFIGURATION REVIEW")

    workflow_document = {
        "permissions": {
            "contents": "read",
            "pull-requests": "write",
        },
        "jobs": {
            "test": {
                "runs-on": "ubuntu-latest",
                "steps": [
                    {"name": "Test", "run": "python -m pytest"},
                ],
            }
        },
    }

    warnings: list[str] = []

    permissions = workflow_document.get("permissions", {})
    if permissions.get("contents") == "write":
        warnings.append(
            "contents write permission is broader than a read-only CI job needs"
        )

    if permissions.get("pull-requests") == "write":
        warnings.append(
            "pull-request write access should only be granted when the job "
            "actually needs to modify pull requests"
        )

    serialized = json.dumps(workflow_document)
    if "${{ github.event.pull_request.title }}" in serialized:
        warnings.append(
            "Untrusted event text should not be interpolated directly into shell commands"
        )

    print("Security review:")
    if warnings:
        for warning in warnings:
            print(f"  WARNING: {warning}")
    else:
        print("  No modeled security warnings")

    print(
        "\nProduction workflows should use least-privilege permissions, avoid "
        "injecting untrusted event fields into shell commands, pin sensitive "
        "third-party actions where appropriate, and separate trusted release "
        "jobs from untrusted pull-request execution."
    )


# ---------------------------------------------------------------------------
# Debugging and local inspection
# ---------------------------------------------------------------------------

def demonstrate_runner_context() -> None:
    """Display runner information that a workflow step can inspect."""
    heading("RUNNER CONTEXT")

    context_values = {
        "operating_system": platform.system(),
        "python_version": platform.python_version(),
        "working_directory": os.getcwd(),
        "git_available": shutil.which("git") is not None,
    }

    for key, value in context_values.items():
        print(f"  {key:20}: {value}")

    print(
        "\nA GitHub-hosted runner provides a clean execution environment for "
        "each job. Steps within that job share its workspace, while separate "
        "jobs should not be assumed to share files unless artifacts, caches, "
        "or another explicit mechanism transfers data."
    )


# ---------------------------------------------------------------------------
# End-to-end demonstration
# ---------------------------------------------------------------------------

def build_complete_workflow() -> Workflow:
    """
    Construct a complete educational workflow model.

    The graph intentionally separates lint and tests, then makes build depend
    on both. Deployment depends on build and is restricted to main.
    """
    return Workflow(
        name="Repository CI and Delivery",
        events={"push", "pull_request"},
        branches={"main", "develop"},
        jobs={
            "lint": Job(
                name="lint",
                runs_on="ubuntu-latest",
                steps=[
                    Step("Checkout", action=checkout_repository),
                    Step("Lint", action=run_linter),
                ],
            ),
            "test": Job(
                name="test",
                runs_on="ubuntu-latest",
                matrix={"python_version": ["3.12", "3.13"]},
                steps=[
                    Step("Checkout", action=checkout_repository),
                    Step("Install", action=install_dependencies),
                    Step("Test", action=run_unit_tests),
                ],
            ),
            "build": Job(
                name="build",
                runs_on="ubuntu-latest",
                needs=["lint", "test"],
                steps=[
                    Step("Checkout", action=checkout_repository),
                    Step("Build", action=build_artifact),
                ],
            ),
            "deploy": Job(
                name="deploy",
                runs_on="ubuntu-latest",
                needs=["build"],
                condition=lambda context: context.event.branch == "main"
                and context.event.name == "push",
                steps=[
                    Step(
                        "Deploy",
                        action=lambda context: context.log(
                            "Production deployment would execute here"
                        ),
                    )
                ],
            ),
        },
    )


def main() -> None:
    """Run all demonstrations in a logical beginner-to-advanced sequence."""
    heading("GITHUB ACTIONS BASICS")
    print(
        "This program models workflow files, events, jobs, and steps, then "
        "extends the model with dependencies, matrices, conditions, outputs, "
        "failure handling, validation, and security."
    )

    demonstrate_events()
    demonstrate_step_order()
    demonstrate_conditions_and_environment()
    demonstrate_matrix()
    demonstrate_failure_handling()
    demonstrate_workflow_validation()
    demonstrate_job_dependencies()
    demonstrate_pull_request_ci()
    demonstrate_security_checks()
    demonstrate_runner_context()

    workflow = build_complete_workflow()
    execute_workflow(workflow, Event("push", "main", "atul"))

    heading("KEY EXECUTION RELATIONSHIPS")
    print(
        "Workflow file -> defines triggers and jobs.\n"
        "Event          -> determines whether the workflow starts.\n"
        "Job            -> defines an execution unit and runner.\n"
        "Step           -> performs ordered work inside that job.\n"
        "needs          -> creates job dependencies.\n"
        "matrix         -> creates multiple job variants.\n"
        "condition      -> controls whether a job or step executes.\n"
        "outputs        -> expose selected results to later workflow logic."
    )


if __name__ == "__main__":
    main()
