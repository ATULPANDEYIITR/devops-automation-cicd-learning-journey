#!/usr/bin/env python3
"""
Jenkins Pipeline workflow simulator.

Models two Jenkins Pipeline styles:
- Declarative: stages are defined as structured configuration.
- Scripted: stages and parallel branches are controlled imperatively.

This is a local educational simulator. It does not connect to a Jenkins
controller or execute shell commands on real agents.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from threading import Lock
from time import monotonic
from typing import Callable, Iterable, Mapping


class StageStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"
    UNSTABLE = "UNSTABLE"


class BuildStatus(str, Enum):
    SUCCESS = "SUCCESS"
    FAILURE = "FAILURE"
    UNSTABLE = "UNSTABLE"


StageAction = Callable[["PipelineContext"], None]
StageCondition = Callable[["PipelineContext"], bool]
PostAction = Callable[["PipelineContext"], None]


@dataclass(frozen=True)
class StageSpec:
    name: str
    action: StageAction
    agent: str = "any"
    retries: int = 0
    when: StageCondition | None = None
    continue_on_failure: bool = False

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Stage name cannot be empty")
        if not self.agent.strip():
            raise ValueError(f"Stage {self.name}: agent cannot be empty")
        if self.retries < 0:
            raise ValueError(f"Stage {self.name}: retries cannot be negative")


@dataclass(frozen=True)
class StageResult:
    name: str
    status: StageStatus
    attempts: int
    duration_seconds: float
    message: str = ""


@dataclass
class PipelineContext:
    parameters: dict[str, object] = field(default_factory=dict)
    environment: dict[str, str] = field(default_factory=dict)
    credentials: dict[str, str] = field(default_factory=dict)
    artifacts: set[str] = field(default_factory=set)
    logs: list[str] = field(default_factory=list)
    _lock: Lock = field(default_factory=Lock, repr=False)

    def log(self, message: str) -> None:
        """Redact known credential values before recording a message."""
        safe_message = str(message)
        for secret in sorted(self.credentials.values(), key=len, reverse=True):
            if secret:
                safe_message = safe_message.replace(secret, "****")
        with self._lock:
            self.logs.append(safe_message)
            print(safe_message)

    def add_artifact(self, artifact_name: str) -> None:
        if not artifact_name.strip():
            raise ValueError("Artifact name cannot be empty")
        with self._lock:
            self.artifacts.add(artifact_name)

    @contextmanager
    def bind_credential(self, credential_id: str):
        """
        Simulate a scoped Jenkins credentials binding.

        The secret is returned only inside the context manager. Logging
        remains redacted even when an action accidentally logs the value.
        """
        if credential_id not in self.credentials:
            raise KeyError(f"Credential '{credential_id}' is unavailable")

        yield self.credentials[credential_id]


def execute_stage(
    spec: StageSpec,
    context: PipelineContext,
) -> StageResult:
    started = monotonic()

    if spec.when is not None:
        try:
            if not spec.when(context):
                context.log(f"[{spec.name}] skipped by its condition")
                return StageResult(
                    spec.name,
                    StageStatus.SKIPPED,
                    0,
                    monotonic() - started,
                    "Condition evaluated to false",
                )
        except Exception as exc:
            message = f"Condition failed: {type(exc).__name__}: {exc}"
            context.log(f"[{spec.name}] {message}")
            return StageResult(
                spec.name,
                StageStatus.FAILED,
                0,
                monotonic() - started,
                message,
            )

    context.log(f"[{spec.name}] agent={spec.agent}")

    last_error = ""
    for attempt in range(1, spec.retries + 2):
        try:
            context.log(
                f"[{spec.name}] attempt {attempt}/{spec.retries + 1}"
            )
            spec.action(context)
            context.log(f"[{spec.name}] completed successfully")
            return StageResult(
                spec.name,
                StageStatus.SUCCESS,
                attempt,
                monotonic() - started,
            )
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {exc}"
            context.log(f"[{spec.name}] attempt failed: {last_error}")

            if attempt <= spec.retries:
                context.log(f"[{spec.name}] retrying")
                continue

    final_status = (
        StageStatus.UNSTABLE
        if spec.continue_on_failure
        else StageStatus.FAILED
    )
    context.log(f"[{spec.name}] final status: {final_status.value}")

    return StageResult(
        spec.name,
        final_status,
        spec.retries + 1,
        monotonic() - started,
        last_error,
    )


@dataclass(frozen=True)
class PipelineResult:
    name: str
    status: BuildStatus
    stages: tuple[StageResult, ...]
    artifacts: tuple[str, ...]


def determine_build_status(
    stage_results: Iterable[StageResult],
    script_failed: bool = False,
) -> BuildStatus:
    results = tuple(stage_results)

    if script_failed or any(
        result.status == StageStatus.FAILED for result in results
    ):
        return BuildStatus.FAILURE

    if any(
        result.status == StageStatus.UNSTABLE for result in results
    ):
        return BuildStatus.UNSTABLE

    return BuildStatus.SUCCESS


def validate_post_actions(post: Mapping[str, PostAction]) -> None:
    allowed = {"always", "success", "failure", "unstable"}
    unknown = set(post) - allowed
    if unknown:
        raise ValueError(
            f"Unsupported post condition(s): {sorted(unknown)}"
        )


class DeclarativePipeline:
    """
    Structured pipeline definition.

    The stage list represents the declarative stages block. The post map
    represents post-build actions associated with build outcomes.
    """

    def __init__(
        self,
        name: str,
        stages: Iterable[StageSpec],
        context: PipelineContext,
        default_agent: str = "any",
        post: Mapping[str, PostAction] | None = None,
    ) -> None:
        self.name = name
        self.stages = tuple(stages)
        self.context = context
        self.default_agent = default_agent
        self.post = dict(post or {})

        if not name.strip():
            raise ValueError("Pipeline name cannot be empty")
        if not default_agent.strip():
            raise ValueError("Default agent cannot be empty")

        validate_post_actions(self.post)
        self._validate_stages()

    def _validate_stages(self) -> None:
        names: set[str] = set()

        for stage in self.stages:
            if stage.name in names:
                raise ValueError(
                    f"Duplicate stage name: {stage.name}"
                )
            names.add(stage.name)

    def run(self) -> PipelineResult:
        results: list[StageResult] = []
        failed = False

        for index, stage in enumerate(self.stages):
            selected_agent = (
                stage.agent
                if stage.agent != "any"
                else self.default_agent
            )
            selected_stage = StageSpec(
                name=stage.name,
                action=stage.action,
                agent=selected_agent,
                retries=stage.retries,
                when=stage.when,
                continue_on_failure=stage.continue_on_failure,
            )

            result = execute_stage(selected_stage, self.context)
            results.append(result)

            if result.status == StageStatus.FAILED:
                failed = True
                for remaining in self.stages[index + 1:]:
                    skipped = StageResult(
                        remaining.name,
                        StageStatus.SKIPPED,
                        0,
                        0.0,
                        "Pipeline stopped after a required stage failed",
                    )
                    results.append(skipped)
                    self.context.log(
                        f"[{remaining.name}] skipped because the pipeline failed"
                    )
                break

        status = determine_build_status(results)
        self._run_post_actions(status)

        return PipelineResult(
            self.name,
            status,
            tuple(results),
            tuple(sorted(self.context.artifacts)),
        )

    def _run_post_actions(self, status: BuildStatus) -> None:
        conditions = ["always", status.value.lower()]

        for condition in conditions:
            action = self.post.get(condition)
            if action is None:
                continue
            try:
                action(self.context)
            except Exception as exc:
                # Post-action errors are recorded separately. They do not
                # erase the original stage failure or success information.
                self.context.log(
                    f"[post:{condition}] failed: "
                    f"{type(exc).__name__}: {exc}"
                )


class ScriptedRuntime:
    """
    Imperative API for a scripted-style pipeline.

    Stages are invoked from ordinary program flow. Parallel branches use
    independent worker threads and share a thread-safe pipeline context.
    """

    def __init__(
        self,
        context: PipelineContext,
        max_parallel: int = 4,
    ) -> None:
        if max_parallel < 1:
            raise ValueError("max_parallel must be at least 1")
        self.context = context
        self.max_parallel = max_parallel
        self.results: list[StageResult] = []
        self._lock = Lock()

    def node(self, agent: str):
        if not agent.strip():
            raise ValueError("Agent label cannot be empty")
        return _NodeScope(self.context, agent)

    def stage(
        self,
        name: str,
        action: StageAction,
        retries: int = 0,
        continue_on_failure: bool = False,
    ) -> StageResult:
        spec = StageSpec(
            name=name,
            action=action,
            agent="scripted-node",
            retries=retries,
            continue_on_failure=continue_on_failure,
        )
        result = execute_stage(spec, self.context)

        with self._lock:
            self.results.append(result)

        if result.status == StageStatus.FAILED:
            raise RuntimeError(
                f"Scripted stage '{name}' failed: {result.message}"
            )
        return result

    def parallel(
        self,
        branches: Mapping[str, Callable[[], None]],
    ) -> None:
        if not branches:
            raise ValueError("Parallel block must contain a branch")

        branch_names = list(branches)
        if len(branch_names) != len(set(branch_names)):
            raise ValueError("Parallel branch names must be unique")

        self.context.log(
            f"[parallel] starting {len(branches)} branches"
        )

        errors: list[BaseException] = []
        with ThreadPoolExecutor(
            max_workers=min(self.max_parallel, len(branches))
        ) as executor:
            futures = {
                executor.submit(branch): name
                for name, branch in branches.items()
            }
            for future in as_completed(futures):
                branch_name = futures[future]
                try:
                    future.result()
                    self.context.log(
                        f"[parallel:{branch_name}] completed"
                    )
                except BaseException as exc:
                    errors.append(exc)
                    self.context.log(
                        f"[parallel:{branch_name}] failed: {exc}"
                    )

        if errors:
            raise RuntimeError(
                f"{len(errors)} parallel branch(es) failed"
            ) from errors[0]


class _NodeScope:
    def __init__(self, context: PipelineContext, agent: str) -> None:
        self.context = context
        self.agent = agent

    def __enter__(self):
        self.context.log(f"[node] allocated agent label: {self.agent}")
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.context.log(f"[node] released agent label: {self.agent}")
        return False


class ScriptedPipeline:
    def __init__(
        self,
        name: str,
        context: PipelineContext,
        script: Callable[[ScriptedRuntime], None],
        post: Mapping[str, PostAction] | None = None,
    ) -> None:
        self.name = name
        self.context = context
        self.script = script
        self.post = dict(post or {})

        if not name.strip():
            raise ValueError("Pipeline name cannot be empty")
        validate_post_actions(self.post)

    def run(self) -> PipelineResult:
        runtime = ScriptedRuntime(self.context)
        script_failed = False

        try:
            self.script(runtime)
        except Exception as exc:
            script_failed = True
            self.context.log(
                f"[script] pipeline execution failed: "
                f"{type(exc).__name__}: {exc}"
            )

        status = determine_build_status(
            runtime.results,
            script_failed=script_failed,
        )

        for condition in ("always", status.value.lower()):
            action = self.post.get(condition)
            if action is None:
                continue
            try:
                action(self.context)
            except Exception as exc:
                self.context.log(
                    f"[post:{condition}] failed: "
                    f"{type(exc).__name__}: {exc}"
                )

        return PipelineResult(
            self.name,
            status,
            tuple(runtime.results),
            tuple(sorted(self.context.artifacts)),
        )


# Pipeline actions -----------------------------------------------------------

def checkout(context: PipelineContext) -> None:
    repository = str(
        context.parameters.get("repository", "payments-service")
    )
    context.log(f"Checking out repository {repository}")


def compile_application(context: PipelineContext) -> None:
    context.log("Compiling application")
    context.add_artifact("application.jar")


def run_unit_tests(context: PipelineContext) -> None:
    context.log("Running unit tests")
    assert context.parameters.get("unit_tests_enabled", True)


def run_integration_tests(context: PipelineContext) -> None:
    context.log("Running integration tests")
    assert context.parameters.get("integration_tests_enabled", True)


def package_application(context: PipelineContext) -> None:
    if "application.jar" not in context.artifacts:
        raise RuntimeError("Compiled artifact is missing")
    context.log("Packaging application")
    context.add_artifact("payments-release.tar.gz")


def deploy_application(context: PipelineContext) -> None:
    if not context.parameters.get("deployment_approved", False):
        raise PermissionError("Production deployment was not approved")

    with context.bind_credential("production-deploy-token") as token:
        # The token is intentionally not printed or stored as an artifact.
        context.log(
            f"Using deployment credential of length {len(token)}"
        )
        context.log("Deploying release to production")


def print_result(result: PipelineResult) -> None:
    print(f"\nPipeline: {result.name}")
    print(f"Build status: {result.status.value}")
    print("Stage results:")

    for stage in result.stages:
        print(
            f"  {stage.name}: {stage.status.value}, "
            f"attempts={stage.attempts}, "
            f"duration={stage.duration_seconds:.4f}s"
        )

    print(f"Artifacts: {list(result.artifacts)}")


def main() -> None:
    declarative_context = PipelineContext(
        parameters={
            "repository": "payments-service",
            "branch": "main",
            "deployment_approved": True,
            "unit_tests_enabled": True,
            "integration_tests_enabled": True,
        },
        credentials={
            "production-deploy-token": "prod-secret-7f9c2a",
        },
    )

    declarative = DeclarativePipeline(
        name="payments-declarative",
        default_agent="linux-docker",
        context=declarative_context,
        stages=[
            StageSpec("Checkout", checkout),
            StageSpec("Build", compile_application),
            StageSpec("Unit Tests", run_unit_tests),
            StageSpec("Integration Tests", run_integration_tests),
            StageSpec("Package", package_application),
            StageSpec(
                "Deploy to Production",
                deploy_application,
                agent="linux-deploy",
                when=lambda ctx: (
                    ctx.parameters.get("branch") == "main"
                    and bool(
                        ctx.parameters.get("deployment_approved")
                    )
                ),
            ),
        ],
        post={
            "always": lambda ctx: ctx.log(
                "Declarative pipeline cleanup completed"
            ),
            "success": lambda ctx: ctx.log(
                "Declarative pipeline completed successfully"
            ),
            "failure": lambda ctx: ctx.log(
                "Declarative pipeline requires investigation"
            ),
        },
    )

    print("\n=== Declarative pipeline ===")
    declarative_result = declarative.run()
    print_result(declarative_result)

    scripted_context = PipelineContext(
        parameters={
            "repository": "payments-service",
            "branch": "feature/reporting",
        },
    )

    def scripted_flow(runtime: ScriptedRuntime) -> None:
        with runtime.node("linux-docker"):
            runtime.stage("Checkout", checkout)
            runtime.stage("Build", compile_application)

            runtime.parallel(
                {
                    "unit-tests": lambda: runtime.stage(
                        "Unit Tests", run_unit_tests
                    ),
                    "integration-tests": lambda: runtime.stage(
                        "Integration Tests",
                        run_integration_tests,
                    ),
                }
            )

            runtime.stage("Package", package_application)

            # Scripted flow uses ordinary control flow to decide whether
            # this stage should be invoked.
            if scripted_context.parameters.get("branch") == "main":
                runtime.stage("Deploy", deploy_application)
            else:
                scripted_context.log(
                    "Deploy omitted for a feature branch"
                )

    scripted = ScriptedPipeline(
        name="payments-scripted",
        context=scripted_context,
        script=scripted_flow,
        post={
            "always": lambda ctx: ctx.log(
                "Scripted pipeline cleanup completed"
            ),
        },
    )

    print("\n=== Scripted pipeline ===")
    scripted_result = scripted.run()
    print_result(scripted_result)


if __name__ == "__main__":
    main()
