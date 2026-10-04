#!/usr/bin/env python3
"""
Actions Variables: Environment Variables, Contexts, and Expressions

A self-contained executable model of GitHub Actions-style variable handling.
The implementation focuses on the distinction between:
- environment variables available to processes,
- workflow/job/step environment scopes,
- Actions contexts such as github, vars, env, matrix, needs, and steps,
- expressions evaluated before a command executes,
- runtime process environment,
- precedence and scope,
- conditional expressions,
- matrix expansion,
- outputs flowing between steps and jobs,
- validation and security-sensitive handling of values.

This is a local educational simulation. It does not call GitHub APIs and does
not require external packages.
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Expression engine
# ---------------------------------------------------------------------------

class ExpressionError(ValueError):
    """Raised when an Actions-style expression cannot be evaluated."""


class MissingContextError(ExpressionError):
    """Raised when an expression references unavailable context data."""


def get_nested(data: dict[str, Any], path: str) -> Any:
    """Resolve dotted context paths such as github.ref or matrix.python."""
    current: Any = data

    for part in path.split("."):
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            raise MissingContextError(f"Context value '{path}' is unavailable.")

    return current


def split_arguments(text: str) -> list[str]:
    """Split function arguments while respecting nested parentheses and quotes."""
    arguments: list[str] = []
    start = 0
    depth = 0
    quote: str | None = None

    for index, character in enumerate(text):
        if quote:
            if character == quote and (index == 0 or text[index - 1] != "\\"):
                quote = None
            continue

        if character in {"'", '"'}:
            quote = character
        elif character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == "," and depth == 0:
            arguments.append(text[start:index].strip())
            start = index + 1

    arguments.append(text[start:].strip())
    return arguments


def evaluate_expression(expression: str, contexts: dict[str, Any]) -> Any:
    """
    Evaluate a deliberately small, safe subset of GitHub Actions expressions.

    Supported:
      context.path
      string / number / boolean / null literals
      !value
      value == value
      value != value
      value && value
      value || value
      startsWith(a, b)
      endsWith(a, b)
      contains(a, b)
      format("...", value)
      success()
      failure()
      cancelled()
      always()

    Python eval is intentionally not used because an Actions expression should
    not become arbitrary executable Python.
    """
    expression = expression.strip()

    if not expression:
        return ""

    # Remove one balanced outer pair of parentheses.
    if expression.startswith("(") and expression.endswith(")"):
        depth = 0
        balanced = True
        quote: str | None = None

        for index, character in enumerate(expression):
            if quote:
                if character == quote and (index == 0 or expression[index - 1] != "\\"):
                    quote = None
                continue

            if character in {"'", '"'}:
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
                if depth == 0 and index != len(expression) - 1:
                    balanced = False
                    break

        if balanced and depth == 0:
            return evaluate_expression(expression[1:-1], contexts)

    # Lowest-precedence logical operators.
    for operator in ("||", "&&"):
        depth = 0
        quote = None

        for index in range(len(expression) - 1, -1, -1):
            character = expression[index]

            if character in {"'", '"'}:
                if quote is None:
                    quote = character
                elif quote == character:
                    quote = None
                continue

            if quote:
                continue

            if character == ")":
                depth += 1
            elif character == "(":
                depth -= 1
            elif depth == 0 and expression[index:index + 2] == operator:
                left = expression[:index]
                right = expression[index + 2:]

                left_value = evaluate_expression(left, contexts)

                if operator == "&&":
                    return (
                        evaluate_expression(right, contexts)
                        if bool(left_value)
                        else left_value
                    )

                return left_value if bool(left_value) else evaluate_expression(right, contexts)

    # Comparisons.
    for operator in ("==", "!="):
        depth = 0
        quote = None

        for index, character in enumerate(expression):
            if quote:
                if character == quote and (index == 0 or expression[index - 1] != "\\"):
                    quote = None
                continue

            if character in {"'", '"'}:
                quote = character
            elif character == "(":
                depth += 1
            elif character == ")":
                depth -= 1
            elif depth == 0 and expression[index:index + 2] == operator:
                left = evaluate_expression(expression[:index], contexts)
                right = evaluate_expression(expression[index + 2:], contexts)
                return left == right if operator == "==" else left != right

    # Unary negation.
    if expression.startswith("!"):
        return not bool(evaluate_expression(expression[1:], contexts))

    # Function calls.
    function_match = re.fullmatch(r"([A-Za-z_][A-Za-z0-9_]*)\((.*)\)", expression, re.DOTALL)
    if function_match:
        function_name = function_match.group(1)
        argument_text = function_match.group(2)
        arguments = [
            evaluate_expression(argument, contexts)
            for argument in split_arguments(argument_text)
            if argument.strip()
        ]

        if function_name == "startsWith":
            if len(arguments) != 2:
                raise ExpressionError("startsWith requires two arguments.")
            return str(arguments[0]).startswith(str(arguments[1]))

        if function_name == "endsWith":
            if len(arguments) != 2:
                raise ExpressionError("endsWith requires two arguments.")
            return str(arguments[0]).endswith(str(arguments[1]))

        if function_name == "contains":
            if len(arguments) != 2:
                raise ExpressionError("contains requires two arguments.")
            return str(arguments[1]) in str(arguments[0])

        if function_name == "format":
            if not arguments:
                raise ExpressionError("format requires a format string.")
            template = str(arguments[0])
            return template.format(*arguments[1:])

        if function_name in {"success", "failure", "cancelled", "always"}:
            if arguments:
                raise ExpressionError(f"{function_name} takes no arguments.")
            return bool(contexts.get("_status", {}).get(function_name, False))

        raise ExpressionError(f"Unsupported expression function: {function_name}")

    # Literals.
    if (expression.startswith("'") and expression.endswith("'")) or (
        expression.startswith('"') and expression.endswith('"')
    ):
        return bytes(expression[1:-1], "utf-8").decode("unicode_escape")

    if expression == "true":
        return True

    if expression == "false":
        return False

    if expression == "null":
        return None

    if re.fullmatch(r"-?\d+", expression):
        return int(expression)

    if re.fullmatch(r"-?\d+\.\d+", expression):
        return float(expression)

    # Context lookup.
    context_match = re.fullmatch(
        r"(github|env|vars|matrix|needs|steps|runner|job|secrets)(?:\.([A-Za-z_][A-Za-z0-9_.-]*))?",
        expression,
    )

    if context_match:
        context_name = context_match.group(1)
        path = context_match.group(2)

        if context_name not in contexts:
            raise MissingContextError(f"Context '{context_name}' is unavailable.")

        if path:
            return get_nested(contexts[context_name], path)

        return contexts[context_name]

    raise ExpressionError(f"Cannot evaluate expression: {expression}")


EXPRESSION_PATTERN = re.compile(r"\$\{\{\s*(.*?)\s*\}\}")


def interpolate(value: Any, contexts: dict[str, Any]) -> Any:
    """
    Resolve ${{ ... }} expressions inside strings.

    A value consisting entirely of one expression preserves the expression's
    original type, which matters for booleans and numeric values.
    """
    if not isinstance(value, str):
        return value

    complete_match = re.fullmatch(r"\$\{\{\s*(.*?)\s*\}\}", value, re.DOTALL)
    if complete_match:
        return evaluate_expression(complete_match.group(1), contexts)

    def replace(match: re.Match[str]) -> str:
        result = evaluate_expression(match.group(1), contexts)
        return "" if result is None else str(result)

    return EXPRESSION_PATTERN.sub(replace, value)


# ---------------------------------------------------------------------------
# Variable scopes
# ---------------------------------------------------------------------------

@dataclass
class VariableScopes:
    """
    Represents the major variable layers involved in an Actions job.

    Workflow, job, and step env values are modeled separately so precedence
    remains explicit rather than being hidden inside one dictionary.
    """

    workflow_env: dict[str, str] = field(default_factory=dict)
    job_env: dict[str, str] = field(default_factory=dict)
    step_env: dict[str, str] = field(default_factory=dict)
    configuration_vars: dict[str, str] = field(default_factory=dict)
    runner_env: dict[str, str] = field(default_factory=dict)

    def effective_environment(self) -> dict[str, str]:
        """
        Construct the process environment.

        A step-level environment overrides a job-level environment, which
        overrides a workflow-level environment. Configuration variables are
        represented separately because ${{ vars.NAME }} is a context lookup,
        not an ordinary process environment lookup.
        """
        result = dict(self.runner_env)
        result.update(self.workflow_env)
        result.update(self.job_env)
        result.update(self.step_env)
        return result


# ---------------------------------------------------------------------------
# Workflow simulation
# ---------------------------------------------------------------------------

@dataclass
class StepResult:
    step_id: str
    name: str
    outcome: str
    conclusion: str
    outputs: dict[str, str] = field(default_factory=dict)


@dataclass
class JobResult:
    job_id: str
    outcome: str
    steps: dict[str, StepResult]


class ActionsSimulator:
    """
    Simulates important variable/context behavior without pretending to be
    the complete GitHub Actions runner implementation.
    """

    def __init__(
        self,
        workflow_env: dict[str, str],
        configuration_vars: dict[str, str],
        github_context: dict[str, Any],
        runner_context: dict[str, Any],
    ) -> None:
        self.scopes = VariableScopes(
            workflow_env=workflow_env,
            configuration_vars=configuration_vars,
            runner_env={
                "PATH": os.environ.get("PATH", ""),
                "LANG": os.environ.get("LANG", ""),
            },
        )
        self.github_context = github_context
        self.runner_context = runner_context
        self.step_results: dict[str, StepResult] = {}
        self.job_results: dict[str, JobResult] = {}

    def build_context(
        self,
        job_env: dict[str, str],
        step_env: dict[str, str],
        matrix: dict[str, Any] | None = None,
        needs: dict[str, Any] | None = None,
        job_status: str = "success",
    ) -> dict[str, Any]:
        """Build a context snapshot available to expression evaluation."""
        scopes = VariableScopes(
            workflow_env=self.scopes.workflow_env,
            job_env=job_env,
            step_env=step_env,
            configuration_vars=self.scopes.configuration_vars,
            runner_env=self.scopes.runner_env,
        )

        return {
            "github": self.github_context,
            "vars": self.scopes.configuration_vars,
            "env": scopes.effective_environment(),
            "matrix": matrix or {},
            "needs": needs or {},
            "steps": {
                step_id: {
                    "outcome": result.outcome,
                    "conclusion": result.conclusion,
                    "outputs": result.outputs,
                }
                for step_id, result in self.step_results.items()
            },
            "runner": self.runner_context,
            "job": {"status": job_status},
            "secrets": {},
            "_status": {
                "success": job_status == "success",
                "failure": job_status == "failure",
                "cancelled": job_status == "cancelled",
                "always": True,
            },
        }

    def execute_command(
        self,
        command: str,
        environment: dict[str, str],
        *,
        cwd: Path | None = None,
    ) -> subprocess.CompletedProcess[str]:
        """
        Execute a local shell command with the effective process environment.

        The command is intentionally kept simple and uses the host shell only
        for demonstration. Real workflow commands execute in a runner shell
        selected by the job configuration.
        """
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd) if cwd else None,
            env={**os.environ, **environment},
            text=True,
            capture_output=True,
            check=False,
        )
        return completed

    def run_step(
        self,
        *,
        step_id: str,
        name: str,
        run: str,
        job_env: dict[str, str],
        step_env: dict[str, str] | None = None,
        if_expression: str | None = None,
        matrix: dict[str, Any] | None = None,
    ) -> StepResult:
        """Resolve expressions, build environment, execute, and record outputs."""
        step_env = step_env or {}

        contexts = self.build_context(
            job_env=job_env,
            step_env=step_env,
            matrix=matrix,
            job_status="success",
        )

        if if_expression:
            condition = interpolate(f"${{{{ {if_expression} }}}}", contexts)
            if not bool(condition):
                result = StepResult(
                    step_id=step_id,
                    name=name,
                    outcome="skipped",
                    conclusion="skipped",
                )
                self.step_results[step_id] = result
                return result

        resolved_run = interpolate(run, contexts)

        resolved_step_env = {
            key: str(interpolate(value, contexts))
            for key, value in step_env.items()
        }

        scopes = VariableScopes(
            workflow_env=self.scopes.workflow_env,
            job_env=job_env,
            step_env=resolved_step_env,
            configuration_vars=self.scopes.configuration_vars,
            runner_env=self.scopes.runner_env,
        )

        environment = scopes.effective_environment()

        # Expressions in env values are resolved before the process starts.
        completed = self.execute_command(resolved_run, environment)

        outcome = "success" if completed.returncode == 0 else "failure"

        # A local file is used as a simplified model of step output transport.
        outputs: dict[str, str] = {}

        result = StepResult(
            step_id=step_id,
            name=name,
            outcome=outcome,
            conclusion=outcome,
            outputs=outputs,
        )
        self.step_results[step_id] = result

        print(f"\n[{name}]")
        print(f"command: {resolved_run}")
        print(f"exit code: {completed.returncode}")

        if completed.stdout.strip():
            print(f"stdout: {completed.stdout.strip()}")

        if completed.stderr.strip():
            print(f"stderr: {completed.stderr.strip()}")

        return result


# ---------------------------------------------------------------------------
# Beginner demonstration: process environment versus Actions contexts
# ---------------------------------------------------------------------------

def demonstrate_basic_variable_layers() -> None:
    print("\n=== Environment variables and contexts ===")

    simulator = ActionsSimulator(
        workflow_env={
            "DEPLOY_REGION": "ap-south-1",
            "LOG_LEVEL": "info",
        },
        configuration_vars={
            "APPLICATION_NAME": "payment-api",
            "DEPLOYMENT_TIER": "staging",
        },
        github_context={
            "repository": "ATULPANDEYIITR/actions-variable-lab",
            "ref": "refs/heads/main",
            "ref_name": "main",
            "event_name": "push",
            "actor": "developer",
            "sha": "abc123def456",
        },
        runner_context={
            "os": "local-simulation",
            "arch": "x64",
        },
    )

    contexts = simulator.build_context(
        job_env={"LOG_LEVEL": "debug", "SERVICE_PORT": "8080"},
        step_env={"LOG_LEVEL": "trace"},
    )

    print("vars.APPLICATION_NAME:", interpolate("${{ vars.APPLICATION_NAME }}", contexts))
    print("github.ref_name:", interpolate("${{ github.ref_name }}", contexts))
    print("env.LOG_LEVEL:", interpolate("${{ env.LOG_LEVEL }}", contexts))
    print("env.SERVICE_PORT:", interpolate("${{ env.SERVICE_PORT }}", contexts))

    print(
        "The process environment is separate from the vars context:",
        contexts["env"]["SERVICE_PORT"],
        "is available to a process, while",
        "vars.APPLICATION_NAME",
        "is configuration-context data.",
    )


# ---------------------------------------------------------------------------
# Pulling expressions from realistic workflow-like data
# ---------------------------------------------------------------------------

def demonstrate_expression_processing() -> None:
    print("\n=== Expressions and conditional execution ===")

    simulator = ActionsSimulator(
        workflow_env={"APP_ENV": "production"},
        configuration_vars={
            "DEPLOYMENT_TIER": "production",
            "MINIMUM_PYTHON": "3.12",
        },
        github_context={
            "ref": "refs/heads/main",
            "ref_name": "main",
            "event_name": "push",
            "repository": "example/platform",
        },
        runner_context={"os": "linux", "arch": "x64"},
    )

    contexts = simulator.build_context(
        job_env={"APP_ENV": "production"},
        step_env={"REGION": "ap-south-1"},
    )

    expressions = {
        "branch": "${{ github.ref_name }}",
        "deployment tier": "${{ vars.DEPLOYMENT_TIER }}",
        "is production": "${{ env.APP_ENV == 'production' }}",
        "main branch": "${{ github.ref_name == 'main' }}",
        "branch predicate": "${{ startsWith(github.ref, 'refs/heads/') }}",
        "formatted artifact": "${{ format('{0}-{1}', vars.DEPLOYMENT_TIER, github.ref_name) }}",
    }

    for label, expression in expressions.items():
        print(f"{label}: {interpolate(expression, contexts)}")


# ---------------------------------------------------------------------------
# Job and step environment precedence
# ---------------------------------------------------------------------------

def demonstrate_scope_precedence() -> None:
    print("\n=== Workflow, job, and step environment precedence ===")

    workflow_env = {"API_MODE": "workflow", "REGION": "global"}
    job_env = {"API_MODE": "job", "JOB_NAME": "release"}
    step_env = {"API_MODE": "step"}

    scopes = VariableScopes(
        workflow_env=workflow_env,
        job_env=job_env,
        step_env=step_env,
    )

    print("workflow API_MODE:", workflow_env["API_MODE"])
    print("job API_MODE:", job_env["API_MODE"])
    print("step API_MODE:", step_env["API_MODE"])
    print("effective API_MODE:", scopes.effective_environment())
    print(
        "The effective process value is the most specific value:",
        scopes.effective_environment()["API_MODE"],
    )


# ---------------------------------------------------------------------------
# Matrix contexts
# ---------------------------------------------------------------------------

def demonstrate_matrix_context() -> None:
    print("\n=== Matrix context ===")

    simulator = ActionsSimulator(
        workflow_env={"CI": "true"},
        configuration_vars={"SERVICE": "billing"},
        github_context={
            "ref_name": "main",
            "event_name": "push",
        },
        runner_context={"os": "local"},
    )

    matrix = [
        {"python": "3.11", "database": "postgres"},
        {"python": "3.12", "database": "postgres"},
        {"python": "3.13", "database": "sqlite"},
    ]

    for combination in matrix:
        contexts = simulator.build_context(
            job_env={"TEST_MODE": "integration"},
            step_env={},
            matrix=combination,
        )

        command = interpolate(
            "test-${{ matrix.python }}-${{ matrix.database }}",
            contexts,
        )

        print(command)


# ---------------------------------------------------------------------------
# Step outputs and downstream expressions
# ---------------------------------------------------------------------------

def demonstrate_step_outputs() -> None:
    print("\n=== Step outputs and downstream expressions ===")

    simulator = ActionsSimulator(
        workflow_env={"CI": "true"},
        configuration_vars={"ARTIFACT_PREFIX": "platform"},
        github_context={
            "ref_name": "main",
            "event_name": "push",
        },
        runner_context={"os": "local"},
    )

    first = StepResult(
        step_id="metadata",
        name="Create build metadata",
        outcome="success",
        conclusion="success",
        outputs={
            "version": "2026.10.04",
            "artifact": "platform-2026.10.04",
        },
    )

    simulator.step_results["metadata"] = first

    contexts = simulator.build_context(
        job_env={},
        step_env={},
    )

    print(
        "step output:",
        interpolate("${{ steps.metadata.outputs.version }}", contexts),
    )

    print(
        "artifact name:",
        interpolate("${{ steps.metadata.outputs.artifact }}", contexts),
    )


# ---------------------------------------------------------------------------
# Job outputs and needs context
# ---------------------------------------------------------------------------

def demonstrate_job_dependency_context() -> None:
    print("\n=== needs context between jobs ===")

    simulator = ActionsSimulator(
        workflow_env={"CI": "true"},
        configuration_vars={"ENVIRONMENT": "staging"},
        github_context={"ref_name": "main"},
        runner_context={"os": "local"},
    )

    needs = {
        "build": {
            "result": "success",
            "outputs": {
                "image": "registry.example.com/payment-api:2026.10.04",
                "version": "2026.10.04",
            },
        }
    }

    contexts = simulator.build_context(
        job_env={},
        step_env={},
        needs=needs,
    )

    image = interpolate("${{ needs.build.outputs.image }}", contexts)
    result = interpolate("${{ needs.build.result }}", contexts)

    print("build result:", result)
    print("image selected for deployment:", image)


# ---------------------------------------------------------------------------
# Secure handling of sensitive data
# ---------------------------------------------------------------------------

def mask_sensitive_values(text: str, secrets: dict[str, str]) -> str:
    """
    Replace known secret values before output reaches a log.

    Real GitHub Actions masking has runner-specific behavior and should not be
    reduced to this local function. The important rule is to avoid printing
    credentials in commands, logs, artifacts, or diagnostic output.
    """
    masked = text

    for secret in secrets.values():
        if secret:
            masked = masked.replace(secret, "***")

    return masked


def demonstrate_security() -> None:
    print("\n=== Sensitive values and logging boundaries ===")

    secrets = {
        "DEPLOY_TOKEN": "ghs_example_secret_9f82",
        "DATABASE_PASSWORD": "correct-horse-battery-staple",
    }

    simulated_command_output = (
        "deploying with token=ghs_example_secret_9f82 "
        "to production"
    )

    print(mask_sensitive_values(simulated_command_output, secrets))
    print(
        "Sensitive values should be consumed by the process rather than "
        "embedded directly into command strings."
    )


# ---------------------------------------------------------------------------
# Validation of workflow-style configuration
# ---------------------------------------------------------------------------

ALLOWED_ENVIRONMENT_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


def validate_environment_mapping(values: dict[str, str]) -> list[str]:
    """Detect variable names and values that are unsafe or ambiguous."""
    errors: list[str] = []

    for name, value in values.items():
        if not ALLOWED_ENVIRONMENT_NAME.fullmatch(name):
            errors.append(
                f"Invalid environment variable name '{name}'. "
                "Use uppercase letters, digits, and underscores."
            )

        if "\x00" in value:
            errors.append(f"Environment variable '{name}' contains a NUL byte.")

        if "\n" in value or "\r" in value:
            errors.append(
                f"Environment variable '{name}' contains a line break; "
                "validate multiline values before exporting them."
            )

    return errors


def demonstrate_validation() -> None:
    print("\n=== Environment validation ===")

    values = {
        "API_BASE_URL": "https://api.example.com",
        "RETRY_LIMIT": "3",
        "bad-name": "invalid",
        "SAFE_VALUE": "normal",
    }

    errors = validate_environment_mapping(values)

    if errors:
        for error in errors:
            print("validation error:", error)
    else:
        print("all environment variables are valid")


# ---------------------------------------------------------------------------
# Shell expansion versus Actions expression expansion
# ---------------------------------------------------------------------------

def demonstrate_two_evaluation_stages() -> None:
    print("\n=== Actions expression evaluation versus shell expansion ===")

    simulator = ActionsSimulator(
        workflow_env={"REGION": "ap-south-1"},
        configuration_vars={"SERVICE": "orders"},
        github_context={"ref_name": "main"},
        runner_context={"os": "local"},
    )

    contexts = simulator.build_context(
        job_env={"DEPLOY_ENV": "staging"},
        step_env={},
    )

    actions_stage = interpolate(
        "echo '${{ vars.SERVICE }} on ${{ github.ref_name }}'",
        contexts,
    )

    print("Actions stage result:", actions_stage)

    shell_environment = VariableScopes(
        workflow_env={"REGION": "ap-south-1"},
        job_env={"DEPLOY_ENV": "staging"},
    ).effective_environment()

    print(
        "Shell stage example:",
        "$DEPLOY_ENV resolves only when the shell process expands it.",
    )
    print("Actual environment:", shell_environment)


# ---------------------------------------------------------------------------
# Failure modes and debugging
# ---------------------------------------------------------------------------

def demonstrate_failure_modes() -> None:
    print("\n=== Failure modes ===")

    simulator = ActionsSimulator(
        workflow_env={},
        configuration_vars={"KNOWN": "value"},
        github_context={"ref_name": "main"},
        runner_context={"os": "local"},
    )

    contexts = simulator.build_context(job_env={}, step_env={})

    failures = [
        "${{ vars.MISSING }}",
        "${{ github.nonexistent }}",
        "${{ unsupported(value) }}",
        "${{ startsWith(github.ref_name) }}",
    ]

    for expression in failures:
        try:
            print(expression, "=>", interpolate(expression, contexts))
        except ExpressionError as exc:
            print(expression, "=> ERROR:", exc)


# ---------------------------------------------------------------------------
# A realistic end-to-end workflow simulation
# ---------------------------------------------------------------------------

def run_release_workflow() -> None:
    print("\n=== End-to-end release workflow simulation ===")

    simulator = ActionsSimulator(
        workflow_env={
            "CI": "true",
            "LOG_LEVEL": "info",
        },
        configuration_vars={
            "SERVICE_NAME": "payments-api",
            "DEPLOY_ENVIRONMENT": "production",
            "ARTIFACT_REGISTRY": "registry.example.com",
        },
        github_context={
            "repository": "ATULPANDEYIITR/payments-api",
            "ref": "refs/heads/main",
            "ref_name": "main",
            "event_name": "push",
            "sha": "5c91aef8",
            "actor": "release-bot",
        },
        runner_context={
            "os": "linux",
            "arch": "x64",
        },
    )

    build = simulator.run_step(
        step_id="build",
        name="Build application",
        run="printf 'building $SERVICE_NAME for $DEPLOY_ENVIRONMENT\\n'",
        job_env={
            "SERVICE_NAME": "${{ vars.SERVICE_NAME }}",
            "DEPLOY_ENVIRONMENT": "${{ vars.DEPLOY_ENVIRONMENT }}",
        },
    )

    build.outputs["version"] = "2026.10.04"
    build.outputs["artifact"] = "payments-api-2026.10.04"

    contexts = simulator.build_context(
        job_env={},
        step_env={},
    )

    artifact = interpolate(
        "${{ steps.build.outputs.artifact }}",
        contexts,
    )

    deployment_condition = interpolate(
        "${{ github.ref_name == 'main' && vars.DEPLOY_ENVIRONMENT == 'production' }}",
        contexts,
    )

    print("artifact passed to deployment:", artifact)
    print("deployment condition:", deployment_condition)

    if deployment_condition:
        simulator.run_step(
            step_id="deploy",
            name="Deploy application",
            run="printf 'deploying %s\\n' \"$ARTIFACT\"",
            job_env={},
            step_env={"ARTIFACT": artifact},
        )
    else:
        print("Deployment skipped by expression policy.")


# ---------------------------------------------------------------------------
# Small local inspection utility
# ---------------------------------------------------------------------------

def inspect_process_environment() -> None:
    print("\n=== Selected process environment ===")

    interesting = {
        key: os.environ.get(key)
        for key in ("PATH", "HOME", "USER", "USERNAME")
        if os.environ.get(key) is not None
    }

    print(json.dumps(interesting, indent=2))


def main() -> None:
    print("Actions Variables Laboratory")
    print("Environment variables | Contexts | Expressions")

    demonstrate_basic_variable_layers()
    demonstrate_expression_processing()
    demonstrate_scope_precedence()
    demonstrate_matrix_context()
    demonstrate_step_outputs()
    demonstrate_job_dependency_context()
    demonstrate_security()
    demonstrate_validation()
    demonstrate_two_evaluation_stages()
    demonstrate_failure_modes()
    run_release_workflow()
    inspect_process_environment()

    print("\n=== Completed ===")
    print("The simulation finished without requiring external packages.")


if __name__ == "__main__":
    main()
