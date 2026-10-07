#!/usr/bin/env python3
"""
GitHub Actions dependency and conditional-execution simulator.

The program models workflow jobs, `needs` dependencies, job conditions,
dependency result propagation, matrix-like fan-out, failure handling,
optional jobs, and a merge-gate workflow.

It is intentionally self-contained and uses only the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Dict, Iterable, List, Optional, Set
import json
import time


class JobStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    SKIPPED = "skipped"
    CANCELLED = "cancelled"


class DependencyError(Exception):
    """Raised when the dependency graph is invalid."""


class WorkflowExecutionError(Exception):
    """Raised for invalid workflow execution operations."""


Condition = Callable[[Dict[str, "JobResult"], Dict[str, str]], bool]
JobAction = Callable[["JobContext"], "JobResult"]


@dataclass(frozen=True)
class JobResult:
    name: str
    status: JobStatus
    conclusion: str
    outputs: Dict[str, str] = field(default_factory=dict)
    message: str = ""

    @property
    def successful(self) -> bool:
        return self.status == JobStatus.SUCCESS

    @property
    def failed(self) -> bool:
        return self.status == JobStatus.FAILURE


@dataclass
class JobContext:
    name: str
    environment: Dict[str, str]
    dependencies: Dict[str, JobResult]

    def dependency(self, name: str) -> JobResult:
        if name not in self.dependencies:
            raise WorkflowExecutionError(
                f"Job '{self.name}' cannot access dependency '{name}'."
            )
        return self.dependencies[name]


@dataclass
class Job:
    name: str
    needs: List[str] = field(default_factory=list)
    condition: Optional[Condition] = None
    action: Optional[JobAction] = None
    allow_failure: bool = False


class Workflow:
    """
    A small execution engine resembling the dependency semantics of CI jobs.

    The important distinction is between:
      * dependency ordering: controlled by `needs`
      * eligibility: controlled by the job condition
      * result propagation: controlled by dependency conclusions
      * execution: performed only after dependencies have reached terminal states
    """

    def __init__(self, name: str, environment: Optional[Dict[str, str]] = None):
        self.name = name
        self.environment = environment or {}
        self.jobs: Dict[str, Job] = {}
        self.results: Dict[str, JobResult] = {}

    def add_job(self, job: Job) -> None:
        if job.name in self.jobs:
            raise DependencyError(f"Duplicate job name: {job.name}")

        for dependency in job.needs:
            if dependency == job.name:
                raise DependencyError(
                    f"Job '{job.name}' cannot depend on itself."
                )

        self.jobs[job.name] = job

    def validate(self) -> None:
        for job in self.jobs.values():
            for dependency in job.needs:
                if dependency not in self.jobs:
                    raise DependencyError(
                        f"Job '{job.name}' depends on unknown job '{dependency}'."
                    )

        state: Dict[str, int] = {name: 0 for name in self.jobs}

        def visit(name: str) -> None:
            if state[name] == 1:
                raise DependencyError(
                    f"Dependency cycle detected involving '{name}'."
                )
            if state[name] == 2:
                return

            state[name] = 1
            for dependency in self.jobs[name].needs:
                visit(dependency)
            state[name] = 2

        for name in self.jobs:
            visit(name)

    def _default_condition(
        self,
        job: Job,
        dependency_results: Dict[str, JobResult],
    ) -> bool:
        """
        Without an explicit condition, a job behaves like a normal dependent
        job: all required dependencies must succeed.

        This models the important practical distinction between merely waiting
        for `needs` and actually being eligible to run after those jobs finish.
        """
        return all(result.successful for result in dependency_results.values())

    def _run_job(self, job: Job) -> JobResult:
        dependency_results = {
            dependency: self.results[dependency]
            for dependency in job.needs
        }

        if job.condition is None:
            eligible = self._default_condition(job, dependency_results)
        else:
            eligible = job.condition(self.results, self.environment)

        if not eligible:
            return JobResult(
                name=job.name,
                status=JobStatus.SKIPPED,
                conclusion="skipped",
                message="Job condition evaluated to false.",
            )

        context = JobContext(
            name=job.name,
            environment=self.environment,
            dependencies=dependency_results,
        )

        if job.action is None:
            return JobResult(
                name=job.name,
                status=JobStatus.SUCCESS,
                conclusion="success",
                message="No action supplied; dependency evaluation succeeded.",
            )

        try:
            result = job.action(context)
            if result.name != job.name:
                return JobResult(
                    name=job.name,
                    status=result.status,
                    conclusion=result.conclusion,
                    outputs=result.outputs,
                    message=result.message,
                )
            return result
        except Exception as exc:
            if job.allow_failure:
                return JobResult(
                    name=job.name,
                    status=JobStatus.FAILURE,
                    conclusion="failure-allowed",
                    message=str(exc),
                )

            return JobResult(
                name=job.name,
                status=JobStatus.FAILURE,
                conclusion="failure",
                message=str(exc),
            )

    def run(self) -> Dict[str, JobResult]:
        self.validate()

        while len(self.results) < len(self.jobs):
            progress = False

            for name, job in self.jobs.items():
                if name in self.results:
                    continue

                if all(dependency in self.results for dependency in job.needs):
                    self.results[name] = self._run_job(job)
                    progress = True

            if not progress:
                unresolved = [
                    name for name in self.jobs if name not in self.results
                ]
                raise WorkflowExecutionError(
                    f"Unable to resolve jobs: {unresolved}"
                )

        return self.results

    def print_report(self) -> None:
        print(f"\n=== Workflow: {self.name} ===")
        for name, result in self.results.items():
            print(
                f"{name:18} {result.status.value:10} "
                f"{result.conclusion:16} {result.message}"
            )

    def dependency_graph(self) -> Dict[str, List[str]]:
        return {
            job.name: list(job.needs)
            for job in self.jobs.values()
        }


def successful_job(name: str, message: str = "") -> JobAction:
    def action(_: JobContext) -> JobResult:
        return JobResult(
            name=name,
            status=JobStatus.SUCCESS,
            conclusion="success",
            message=message or "Completed successfully.",
        )

    return action


def failing_job(name: str, message: str) -> JobAction:
    def action(_: JobContext) -> JobResult:
        return JobResult(
            name=name,
            status=JobStatus.FAILURE,
            conclusion="failure",
            message=message,
        )

    return action


def compile_action(context: JobContext) -> JobResult:
    print("Compiling application...")
    return JobResult(
        name=context.name,
        status=JobStatus.SUCCESS,
        conclusion="success",
        outputs={"artifact": "build/app.tar.gz"},
        message="Build artifact produced.",
    )


def unit_test_action(context: JobContext) -> JobResult:
    build = context.dependency("build")
    if "artifact" not in build.outputs:
        raise WorkflowExecutionError("Test job received no build artifact.")

    print(f"Testing {build.outputs['artifact']}...")
    return JobResult(
        name=context.name,
        status=JobStatus.SUCCESS,
        conclusion="success",
        outputs={"coverage": "92.4"},
        message="Unit tests passed.",
    )


def integration_test_action(context: JobContext) -> JobResult:
    unit_tests = context.dependency("unit-tests")

    if unit_tests.outputs.get("coverage") is None:
        raise WorkflowExecutionError("Coverage output is unavailable.")

    return JobResult(
        name=context.name,
        status=JobStatus.SUCCESS,
        conclusion="success",
        message="Integration tests passed.",
    )


def deploy_action(context: JobContext) -> JobResult:
    print("Deploying validated artifact...")
    return JobResult(
        name=context.name,
        status=JobStatus.SUCCESS,
        conclusion="success",
        message="Deployment completed.",
    )


def notify_action(context: JobContext) -> JobResult:
    failed = [
        name
        for name, result in context.dependencies.items()
        if result.failed
    ]
    return JobResult(
        name=context.name,
        status=JobStatus.SUCCESS,
        conclusion="success",
        message=f"Notification sent; failed dependencies: {failed or 'none'}.",
    )


def demonstrate_basic_dependencies() -> None:
    """
    Shows a linear dependency chain:

        build -> unit-tests -> integration-tests -> deploy

    `needs` controls ordering and also creates a data dependency between jobs.
    """
    workflow = Workflow("basic-ci")

    workflow.add_job(
        Job(
            name="build",
            action=compile_action,
        )
    )

    workflow.add_job(
        Job(
            name="unit-tests",
            needs=["build"],
            action=unit_test_action,
        )
    )

    workflow.add_job(
        Job(
            name="integration-tests",
            needs=["unit-tests"],
            action=integration_test_action,
        )
    )

    workflow.add_job(
        Job(
            name="deploy",
            needs=["integration-tests"],
            action=deploy_action,
        )
    )

    workflow.run()
    workflow.print_report()

    print("\nDependency graph:")
    print(json.dumps(workflow.dependency_graph(), indent=2))


def demonstrate_parallel_branches() -> None:
    """
    Jobs with the same dependency can become eligible independently.

             build
             /   \
        lint       unit-tests
             \   /
            package
    """
    workflow = Workflow("parallel-validation")

    workflow.add_job(
        Job(name="build", action=compile_action)
    )

    workflow.add_job(
        Job(
            name="lint",
            needs=["build"],
            action=successful_job("lint", "Static analysis passed."),
        )
    )

    workflow.add_job(
        Job(
            name="unit-tests",
            needs=["build"],
            action=unit_test_action,
        )
    )

    workflow.add_job(
        Job(
            name="package",
            needs=["lint", "unit-tests"],
            action=successful_job(
                "package",
                "Packaging waits for both validation branches.",
            ),
        )
    )

    workflow.run()
    workflow.print_report()


def always_run_condition(
    results: Dict[str, JobResult],
    _: Dict[str, str],
) -> bool:
    """
    An explicit condition can intentionally allow execution even when a
    dependency failed. This is appropriate for cleanup, diagnostics, or
    notification jobs, but usually inappropriate for deployment.
    """
    return True


def all_dependencies_finished(
    results: Dict[str, JobResult],
    _: Dict[str, str],
) -> bool:
    return all(
        result.status
        in {
            JobStatus.SUCCESS,
            JobStatus.FAILURE,
            JobStatus.SKIPPED,
            JobStatus.CANCELLED,
        }
        for result in results.values()
    )


def demonstrate_conditional_execution() -> None:
    workflow = Workflow("conditional-workflow")

    workflow.add_job(
        Job(
            name="build",
            action=failing_job("build", "Compiler rejected the source."),
        )
    )

    workflow.add_job(
        Job(
            name="deploy",
            needs=["build"],
            action=deploy_action,
        )
    )

    workflow.add_job(
        Job(
            name="diagnostics",
            needs=["build"],
            condition=always_run_condition,
            action=successful_job(
                "diagnostics",
                "Diagnostics collected despite build failure.",
            ),
        )
    )

    workflow.add_job(
        Job(
            name="notification",
            needs=["build", "deploy", "diagnostics"],
            condition=all_dependencies_finished,
            action=notify_action,
        )
    )

    workflow.run()
    workflow.print_report()


def demonstrate_failure_propagation() -> None:
    """
    A job depending on a failed job is skipped by default. A sibling job does
    not automatically fail merely because another sibling failed.
    """
    workflow = Workflow("failure-propagation")

    workflow.add_job(
        Job(
            name="security-scan",
            action=failing_job(
                "security-scan",
                "Critical dependency vulnerability detected.",
            ),
        )
    )

    workflow.add_job(
        Job(
            name="documentation",
            action=successful_job(
                "documentation",
                "Documentation generated independently.",
            ),
        )
    )

    workflow.add_job(
        Job(
            name="release",
            needs=["security-scan", "documentation"],
            action=deploy_action,
        )
    )

    workflow.run()
    workflow.print_report()


def demonstrate_optional_failure() -> None:
    """
    Some jobs are informational rather than release-blocking. The model keeps
    their failure visible while allowing the workflow to continue.
    """
    workflow = Workflow("optional-quality-check")

    workflow.add_job(
        Job(
            name="build",
            action=compile_action,
        )
    )

    workflow.add_job(
        Job(
            name="experimental-analysis",
            needs=["build"],
            action=failing_job(
                "experimental-analysis",
                "Experimental analyzer found a non-blocking issue.",
            ),
            allow_failure=True,
        )
    )

    workflow.add_job(
        Job(
            name="release",
            needs=["build"],
            action=deploy_action,
        )
    )

    workflow.run()
    workflow.print_report()


def demonstrate_environment_condition() -> None:
    """
    Conditions can depend on workflow context, such as a deployment
    environment. In a real GitHub Actions workflow this pattern corresponds
    to expressions involving event data, variables, or other workflow state.
    """
    workflow = Workflow(
        "environment-aware-deployment",
        environment={
            "environment": "staging",
            "release_enabled": "true",
        },
    )

    workflow.add_job(Job(name="build", action=compile_action))

    workflow.add_job(
        Job(
            name="staging-deploy",
            needs=["build"],
            condition=lambda _, env: env.get("environment") == "staging",
            action=deploy_action,
        )
    )

    workflow.add_job(
        Job(
            name="production-deploy",
            needs=["build"],
            condition=lambda _, env: (
                env.get("environment") == "production"
                and env.get("release_enabled") == "true"
            ),
            action=deploy_action,
        )
    )

    workflow.run()
    workflow.print_report()


@dataclass(frozen=True)
class MatrixJob:
    name: str
    value: str
    passed: bool
    message: str


def simulate_matrix_dependencies(
    versions: Iterable[str],
) -> List[MatrixJob]:
    """
    Matrix-like execution creates several independent validation jobs.
    The aggregation stage evaluates the complete set before release.
    """
    jobs: List[MatrixJob] = []

    for version in versions:
        passed = version != "3.8"
        jobs.append(
            MatrixJob(
                name=f"test-python-{version}",
                value=version,
                passed=passed,
                message=(
                    "Tests passed."
                    if passed
                    else "Unsupported dependency behavior detected."
                ),
            )
        )

    return jobs


def demonstrate_matrix_aggregation() -> None:
    matrix_results = simulate_matrix_dependencies(
        ["3.11", "3.12", "3.13", "3.8"]
    )

    print("\n=== Matrix aggregation ===")
    for result in matrix_results:
        print(
            f"{result.name:20} "
            f"{'PASS' if result.passed else 'FAIL':5} "
            f"{result.message}"
        )

    release_allowed = all(result.passed for result in matrix_results)

    print(
        "Release eligibility:",
        "allowed" if release_allowed else "blocked",
    )


def topological_order(graph: Dict[str, List[str]]) -> List[str]:
    """
    Kahn's algorithm produces a valid dependency order.

    Time complexity is O(V + E), where V is the number of jobs and E is the
    number of dependency edges.
    """
    indegree = {node: 0 for node in graph}
    dependents: Dict[str, List[str]] = {node: [] for node in graph}

    for node, dependencies in graph.items():
        for dependency in dependencies:
            if dependency not in graph:
                raise DependencyError(
                    f"Unknown dependency '{dependency}' in graph."
                )
            indegree[node] += 1
            dependents[dependency].append(node)

    ready = [node for node, degree in indegree.items() if degree == 0]
    order: List[str] = []

    while ready:
        node = ready.pop(0)
        order.append(node)

        for dependent in dependents[node]:
            indegree[dependent] -= 1
            if indegree[dependent] == 0:
                ready.append(dependent)

    if len(order) != len(graph):
        raise DependencyError("Graph contains a dependency cycle.")

    return order


def demonstrate_graph_algorithm() -> None:
    graph = {
        "checkout": [],
        "build": ["checkout"],
        "lint": ["build"],
        "unit-tests": ["build"],
        "integration-tests": ["unit-tests"],
        "package": ["lint", "integration-tests"],
        "deploy": ["package"],
    }

    print("\n=== Topological dependency order ===")
    print(" -> ".join(topological_order(graph)))


def demonstrate_invalid_graphs() -> None:
    print("\n=== Dependency validation ===")

    missing_dependency = Workflow("missing-dependency")
    missing_dependency.add_job(
        Job(name="deploy", needs=["nonexistent"])
    )

    try:
        missing_dependency.validate()
    except DependencyError as exc:
        print("Missing dependency rejected:", exc)

    cycle = Workflow("cycle")
    cycle.add_job(Job(name="build", needs=["test"]))
    cycle.add_job(Job(name="test", needs=["build"]))

    try:
        cycle.validate()
    except DependencyError as exc:
        print("Cycle rejected:", exc)


def demonstrate_production_design() -> None:
    """
    Models a common CI/CD release structure where deployment is intentionally
    separated from notification and diagnostic paths.

    The release job has a narrow dependency set. This reduces accidental
    coupling: an informational job does not block deployment unless it is
    explicitly placed in `needs`.
    """
    workflow = Workflow(
        "production-release",
        environment={
            "branch": "main",
            "release_enabled": "true",
        },
    )

    workflow.add_job(
        Job(
            name="build",
            action=compile_action,
        )
    )

    workflow.add_job(
        Job(
            name="security",
            needs=["build"],
            action=successful_job(
                "security",
                "Dependency and static security checks passed.",
            ),
        )
    )

    workflow.add_job(
        Job(
            name="unit-tests",
            needs=["build"],
            action=unit_test_action,
        )
    )

    workflow.add_job(
        Job(
            name="release-candidate",
            needs=["security", "unit-tests"],
            condition=lambda results, env: (
                env.get("branch") == "main"
                and env.get("release_enabled") == "true"
                and results["security"].successful
                and results["unit-tests"].successful
            ),
            action=successful_job(
                "release-candidate",
                "Release candidate is eligible.",
            ),
        )
    )

    workflow.add_job(
        Job(
            name="deploy",
            needs=["release-candidate"],
            action=deploy_action,
        )
    )

    workflow.add_job(
        Job(
            name="notify",
            needs=["deploy"],
            condition=always_run_condition,
            action=notify_action,
        )
    )

    workflow.run()
    workflow.print_report()


def main() -> None:
    print("GitHub Actions Job Dependencies and Conditional Execution")
    print("=" * 62)

    demonstrate_basic_dependencies()
    demonstrate_parallel_branches()
    demonstrate_conditional_execution()
    demonstrate_failure_propagation()
    demonstrate_optional_failure()
    demonstrate_environment_condition()
    demonstrate_matrix_aggregation()
    demonstrate_graph_algorithm()
    demonstrate_invalid_graphs()
    demonstrate_production_design()

    print("\n=== Key execution invariant ===")
    print(
        "A dependency edge determines when a job may be evaluated; "
        "the job condition determines whether it is eligible to run."
    )


if __name__ == "__main__":
    main()
