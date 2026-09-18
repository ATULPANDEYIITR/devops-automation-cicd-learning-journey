#!/usr/bin/env python3
"""
Bash Error Handling: exit codes, set -e, set -u, traps, and defensive scripting.

This standalone study program teaches Bash error handling from beginner to advanced
levels. It uses Python to:
    1. Explain Bash concepts through executable demonstrations.
    2. Generate temporary Bash programs safely.
    3. Execute those programs and inspect their exit status and output.
    4. Compare common error-handling strategies.
    5. Demonstrate defensive scripting patterns and failure cases.

The examples intentionally use small, isolated shell programs so that a failure in
one demonstration does not terminate this Python program.

Requirements:
    - Python 3.9+
    - Bash available as "bash" on PATH

The script avoids third-party Python packages.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# Utility functions
# ---------------------------------------------------------------------------

@dataclass
class BashResult:
    """Stores the observable result of a Bash demonstration."""

    name: str
    return_code: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0

    def describe(self) -> None:
        print(f"\n--- {self.name} ---")
        print(f"exit code: {self.return_code}")
        if self.stdout:
            print("stdout:")
            print(self.stdout.rstrip())
        if self.stderr:
            print("stderr:")
            print(self.stderr.rstrip())


def require_bash() -> str:
    """Locate Bash before any demonstration is attempted."""
    bash_path = shutil.which("bash")
    if bash_path is None:
        raise RuntimeError(
            "Bash was not found on PATH. Run this study file in an environment "
            "where Bash is installed."
        )
    return bash_path


def run_bash(
    bash_path: str,
    name: str,
    script: str,
    *,
    timeout: float = 5.0,
    environment: Optional[dict[str, str]] = None,
) -> BashResult:
    """
    Execute a Bash program in a subprocess.

    Important defensive property:
    the Python process does not use shell=True. The script is supplied directly
    to Bash with stdin, avoiding an additional shell parsing layer.
    """
    completed = subprocess.run(
        [bash_path, "--noprofile", "--norc"],
        input=textwrap.dedent(script),
        text=True,
        capture_output=True,
        timeout=timeout,
        env=environment,
        check=False,
    )

    return BashResult(
        name=name,
        return_code=completed.returncode,
        stdout=completed.stdout,
        stderr=completed.stderr,
    )


def print_section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def print_concept(title: str, explanation: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))
    print(textwrap.dedent(explanation).strip())


def explain_result(result: BashResult) -> None:
    result.describe()
    if result.return_code == 0:
        print("Interpretation: the Bash process reported success.")
    else:
        print(
            "Interpretation: the Bash process reported failure. "
            "The exact meaning depends on the command and convention involved."
        )


# ---------------------------------------------------------------------------
# Bash fundamentals
# ---------------------------------------------------------------------------

def demonstrate_basic_exit_codes(bash: str) -> None:
    print_section("1. Exit codes: the foundation of Bash error handling")

    print_concept(
        "Exit status",
        """
        Every ordinary Unix process terminates with an integer status.

        Conventionally:
            0       means success.
            nonzero means some form of failure, condition, or exceptional result.

        Bash exposes the status of the most recently executed command through
        the special parameter $?.

        A status is not automatically an English error message. Its meaning is
        defined by the program that returned it.
        """,
    )

    result = run_bash(
        bash,
        "successful command",
        """
        true
        printf 'status after true = %s\\n' "$?"
        """,
    )
    explain_result(result)

    result = run_bash(
        bash,
        "failed command",
        """
        false
        printf 'status after false = %s\\n' "$?"
        """,
    )
    explain_result(result)

    print_concept(
        "Why $?",
        """
        The value of $? changes after commands execute. Therefore, capture it
        immediately when you need it.

        Good:
            command
            status=$?

        Risky:
            command
            printf 'debug message\\n'
            status=$?

        The printf command has replaced the status you intended to inspect.
        """,
    )

    result = run_bash(
        bash,
        "capture an exit code immediately",
        """
        false
        status=$?
        printf 'captured status = %s\\n' "$status"
        """,
    )
    explain_result(result)

    print_concept(
        "Explicit exit",
        """
        The exit builtin terminates the current shell or script with a chosen
        status. A script can therefore define a meaningful interface to its
        caller.

        Example:
            exit 0
            exit 1

        Avoid inventing complicated meanings without documenting them. For
        larger systems, stable exit-code conventions make automation easier.
        """,
    )

    result = run_bash(
        bash,
        "explicit exit status",
        """
        printf 'about to exit with status 7\\n'
        exit 7
        """,
    )
    explain_result(result)


# ---------------------------------------------------------------------------
# Conditional handling
# ---------------------------------------------------------------------------

def demonstrate_if_and_or(bash: str) -> None:
    print_section("2. Handling failures explicitly with conditionals")

    print_concept(
        "Commands as conditions",
        """
        Bash commands can be used directly as conditions. The shell evaluates
        their exit status rather than requiring a Boolean type.

        The following is idiomatic:

            if command; then
                ...
            else
                ...
            fi

        A nonzero result is expected in many legitimate situations, so not every
        nonzero status should automatically be treated as a fatal error.
        """,
    )

    result = run_bash(
        bash,
        "explicit if handling",
        """
        if test -f /definitely/not/a/real/file; then
            printf 'file exists\\n'
        else
            printf 'file does not exist; this was handled intentionally\\n'
        fi
        """,
    )
    explain_result(result)

    print_concept(
        "Short-circuit operators",
        """
        && runs the right-hand command only if the left-hand command succeeds.

        || runs the right-hand command only if the left-hand command fails.

        These operators are useful for compact logic, but excessive chaining can
        make failure behavior difficult to understand.
        """,
    )

    result = run_bash(
        bash,
        "&& and ||",
        """
        true && printf 'success path\\n'
        false || printf 'failure path\\n'
        """,
    )
    explain_result(result)

    print_concept(
        "A subtle anti-pattern",
        """
        The expression:

            command && success || failure

        is not always equivalent to:

            if command; then
                success
            else
                failure
            fi

        If the 'success' command itself fails, the || branch can run even though
        the original command succeeded. An explicit if statement is often clearer.
        """,
    )

    result = run_bash(
        bash,
        "why && ... || ... can surprise you",
        """
        true && {
            printf 'primary command succeeded\\n'
            false
        } || {
            printf 'fallback branch also ran\\n'
        }
        """,
    )
    explain_result(result)


# ---------------------------------------------------------------------------
# set -e
# ---------------------------------------------------------------------------

def demonstrate_set_e(bash: str) -> None:
    print_section("3. set -e: automatic termination after failures")

    print_concept(
        "What set -e does",
        """
        set -e, also written as set -o errexit, asks Bash to exit when a simple
        command fails in contexts where Bash considers that failure unhandled.

        It is useful for preventing a script from silently continuing after an
        important failure.

        The critical detail is that errexit has exceptions. It is not a universal
        'exit on every nonzero status' switch.
        """,
    )

    result = run_bash(
        bash,
        "set -e stops a simple command failure",
        """
        set -e
        printf 'before failure\\n'
        false
        printf 'this line is not reached\\n'
        """,
    )
    explain_result(result)

    print_concept(
        "set -e does not behave identically everywhere",
        """
        Bash suppresses errexit in several syntactic contexts, including common
        conditional constructs. This exists partly because nonzero statuses are
        often expected conditions rather than fatal failures.

        For example, a command used as the test in an if statement may return
        nonzero without terminating the script.
        """,
    )

    result = run_bash(
        bash,
        "set -e inside an if condition",
        """
        set -e
        if false; then
            printf 'unexpected success\\n'
        else
            printf 'false was used as a condition and was handled\\n'
        fi
        printf 'script continued\\n'
        """,
    )
    explain_result(result)

    result = run_bash(
        bash,
        "set -e with a non-final pipeline example",
        """
        set -e
        false | true
        printf 'without pipefail, the pipeline status is normally the final command status\\n'
        """,
    )
    explain_result(result)

    print_concept(
        "Why pipefail matters",
        """
        A pipeline such as:

            producer | transformer | consumer

        normally gets the exit status of the last command.

        Therefore an earlier failure can be hidden if the last command succeeds.

        set -o pipefail changes the pipeline status so that a pipeline reports
        failure when an element fails, with Bash using the rightmost failing
        command's status.
        """,
    )

    result = run_bash(
        bash,
        "set -e with pipefail",
        """
        set -e
        set -o pipefail

        false | true
        printf 'this line is not reached\\n'
        """,
    )
    explain_result(result)

    print_concept(
        "errexit design lesson",
        """
        set -e is useful as a defensive baseline, but it should not replace
        explicit error handling. Functions, conditionals, pipelines, command
        substitutions, subshells, and shell version details can affect behavior.

        A robust script normally combines:
            set -e
            set -u
            set -o pipefail
        with deliberate handling of expected failures.
        """,
    )


# ---------------------------------------------------------------------------
# set -u
# ---------------------------------------------------------------------------

def demonstrate_set_u(bash: str) -> None:
    print_section("4. set -u: undefined-variable protection")

    print_concept(
        "What set -u does",
        """
        set -u, also called set -o nounset, treats expansion of an unset variable
        as an error in normal parameter expansion contexts.

        This catches spelling mistakes and missing configuration earlier.

        Without nounset, an unset variable often expands to an empty string.
        That can silently produce incorrect paths, arguments, or configuration.
        """,
    )

    result = run_bash(
        bash,
        "unset variable without nounset",
        """
        unset USER_SELECTED_PATH
        printf 'value=[%s]\\n' "$USER_SELECTED_PATH"
        printf 'script continued\\n'
        """,
    )
    explain_result(result)

    result = run_bash(
        bash,
        "unset variable with nounset",
        """
        set -u
        unset USER_SELECTED_PATH
        printf 'value=[%s]\\n' "$USER_SELECTED_PATH"
        printf 'script continued\\n'
        """,
    )
    explain_result(result)

    print_concept(
        "Safe defaults",
        """
        Bash parameter expansion provides operators for optional variables.

        ${name:-default}
            Use default when name is unset or empty.

        ${name-default}
            Use default only when name is unset.

        ${name:?message}
            Fail with a diagnostic if name is unset or empty.

        ${name?message}
            Fail only if name is unset.

        These forms are particularly useful with set -u.
        """,
    )

    result = run_bash(
        bash,
        "nounset with a default",
        """
        set -u
        unset OPTIONAL_PORT
        port="${OPTIONAL_PORT:-8080}"
        printf 'port=%s\\n' "$port"
        """,
    )
    explain_result(result)

    result = run_bash(
        bash,
        "nounset with a required setting",
        """
        set -u
        unset DATABASE_URL
        : "${DATABASE_URL:?DATABASE_URL must be configured}"
        printf 'configuration is valid\\n'
        """,
    )
    explain_result(result)

    print_concept(
        "Arrays and nounset",
        """
        Arrays introduce additional edge cases. A script should not assume that
        every index exists simply because an array exists.

        Defensive scripts validate indexes or use appropriate parameter expansion
        before dereferencing optional values.
        """,
    )

    result = run_bash(
        bash,
        "safe optional array access",
        """
        set -u
        values=(alpha beta)
        index=5

        if (( index < ${#values[@]} )); then
            printf 'value=%s\\n' "${values[index]}"
        else
            printf 'index %s is outside the array\\n' "$index"
        fi
        """,
    )
    explain_result(result)


# ---------------------------------------------------------------------------
# traps
# ---------------------------------------------------------------------------

def demonstrate_traps(bash: str) -> None:
    print_section("5. trap: reacting to shell events")

    print_concept(
        "What trap does",
        """
        trap registers shell code to execute when a specified signal or shell
        event occurs.

        Common events include:
            EXIT   before a shell exits
            ERR    after a command failure in contexts where Bash generates ERR
            INT    interrupt such as Ctrl-C
            TERM   termination request

        trap is useful for cleanup, diagnostics, and controlled shutdown.
        """,
    )

    result = run_bash(
        bash,
        "EXIT trap",
        """
        cleanup() {
            printf 'cleanup executed before shell exit\\n'
        }

        trap cleanup EXIT

        printf 'main work\\n'
        """,
    )
    explain_result(result)

    print_concept(
        "ERR trap",
        """
        ERR traps are useful for diagnostics but have behavior closely related
        to errexit's conditional contexts. They should not be treated as a
        perfect universal exception mechanism.

        A diagnostic trap can inspect:
            $?          status associated with the failure
            BASH_COMMAND command being executed
            FUNCNAME    function call context
            BASH_LINENO source-line context
        """,
    )

    result = run_bash(
        bash,
        "ERR trap diagnostic",
        """
        set -E
        trap 'status=$?; printf "ERR: status=%s command=%s function=%s\\n" "$status" "$BASH_COMMAND" "${FUNCNAME[1]:-main}"' ERR

        failing_operation() {
            false
        }

        failing_operation
        """,
    )
    explain_result(result)

    print_concept(
        "ERR propagation",
        """
        set -E, or set -o errtrace, makes ERR traps inherited by shell functions,
        command substitutions, and subshell environments in relevant contexts.

        Without deliberate trap propagation, diagnostics may not appear where
        developers expect them.
        """,
    )

    print_concept(
        "Signals",
        """
        A production script may receive SIGINT or SIGTERM while waiting for work.
        Cleanup should be idempotent: running it twice should not corrupt state.

        A common pattern is:

            trap cleanup EXIT
            trap 'exit 130' INT

        The EXIT trap performs the actual cleanup while the INT trap establishes
        an appropriate termination status.
        """,
    )

    result = run_bash(
        bash,
        "controlled cleanup structure",
        """
        temporary_file=""

        cleanup() {
            if [[ -n "$temporary_file" && -e "$temporary_file" ]]; then
                rm -f -- "$temporary_file"
                printf 'temporary resource removed\\n'
            fi
        }

        trap cleanup EXIT

        temporary_file="$(mktemp)"
        printf 'temporary data\\n' > "$temporary_file"
        printf 'resource created: %s\\n' "$temporary_file"
        """,
    )
    explain_result(result)


# ---------------------------------------------------------------------------
# Defensive scripting
# ---------------------------------------------------------------------------

def demonstrate_defensive_scripting(bash: str) -> None:
    print_section("6. Defensive Bash scripting")

    print_concept(
        "A common defensive baseline",
        """
        A frequently used baseline is:

            set -Eeuo pipefail

        E       ERR traps are inherited in relevant contexts.
        e       exit on unhandled command failures.
        u       reject unintended unset-variable expansion.
        o pipefail
                propagate failures through pipelines.

        This is powerful, but it does not remove the need to understand Bash's
        control-flow exceptions.
        """,
    )

    result = run_bash(
        bash,
        "strict-mode baseline",
        r"""
        set -Eeuo pipefail

        cleanup() {
            printf 'cleanup handler executed\\n'
        }

        on_error() {
            local status=$?
            printf 'error status=%s command=%s line=%s\\n' \
                "$status" "$BASH_COMMAND" "${BASH_LINENO[0]}"
        }

        trap on_error ERR
        trap cleanup EXIT

        printf 'strict script started\\n'
        printf '%s\n' "alpha" "beta" | grep -q "beta"
        printf 'pipeline succeeded\\n'
        """,
    )
    explain_result(result)

    print_concept(
        "Quoting",
        """
        Quote variable expansions when treating them as a single value:

            "$file"

        instead of:

            $file

        Unquoted expansion can trigger word splitting and pathname expansion.
        This is one of the most important defensive habits in Bash.
        """,
    )

    result = run_bash(
        bash,
        "quoted versus unquoted arguments",
        r"""
        set -u

        filename="report final.txt"

        show_argument() {
            printf 'argument=[%s]\n' "$1"
        }

        show_argument "$filename"

        # The next form is intentionally avoided because the space would create
        # multiple arguments after word splitting.
        """,
    )
    explain_result(result)

    print_concept(
        "Paths beginning with -",
        """
        Commands that accept filenames can interpret a filename beginning with
        '-' as an option.

        When supported by the command, use '--' before filenames:

            rm -- "$file"
            cat -- "$file"

        This separates options from positional operands.
        """,
    )

    result = run_bash(
        bash,
        "defensive filename handling",
        """
        set -euo pipefail

        directory="$(mktemp -d)"
        trap 'rm -rf -- "$directory"' EXIT

        file="$directory/-example.txt"
        printf 'safe filename\\n' > "$file"

        cat -- "$file"
        """,
    )
    explain_result(result)

    print_concept(
        "Temporary resources",
        """
        Temporary files should be created with mktemp rather than predictable
        filenames. Predictable temporary filenames can create collisions and
        security problems.

        Cleanup belongs in an EXIT trap so normal and error exits can share the
        same cleanup path.
        """,
    )

    print_concept(
        "Input validation",
        """
        Validate assumptions at boundaries.

        Examples:
            [[ -f "$config_file" ]] || ...
            [[ "$port" =~ ^[0-9]+$ ]] || ...
            (( port >= 1 && port <= 65535 )) || ...

        Validation makes failures local and easier to diagnose.
        """,
    )

    result = run_bash(
        bash,
        "numeric validation",
        """
        validate_port() {
            local port=$1

            if [[ ! "$port" =~ ^[0-9]+$ ]]; then
                printf 'invalid port: %s\\n' "$port" >&2
                return 2
            fi

            if (( port < 1 || port > 65535 )); then
                printf 'port outside valid range: %s\\n' "$port" >&2
                return 2
            fi

            printf 'valid port: %s\\n' "$port"
        }

        validate_port 443
        validate_port 70000 || printf 'caller handled invalid input\\n'
        """,
    )
    explain_result(result)


# ---------------------------------------------------------------------------
# Functions and return statuses
# ---------------------------------------------------------------------------

def demonstrate_functions(bash: str) -> None:
    print_section("7. Functions and error propagation")

    print_concept(
        "Functions return statuses",
        """
        A Bash function's exit status is normally the status of its last command,
        unless it uses return explicitly.

        This makes return useful for communicating failure to the caller.
        """,
    )

    result = run_bash(
        bash,
        "function return status",
        """
        validate_name() {
            local name=$1

            if [[ -z "$name" ]]; then
                printf 'name cannot be empty\\n' >&2
                return 2
            fi

            printf 'valid name: %s\\n' "$name"
        }

        validate_name "Ada"
        validate_name "" || printf 'validation failed as expected\\n'
        """,
    )
    explain_result(result)

    print_concept(
        "Preserving errors",
        """
        A wrapper function should not accidentally replace a meaningful status.

        A useful pattern is:

            if ! operation; then
                ...
                return
            fi

        This makes the expected failure explicit and prevents set -e from
        terminating before custom handling occurs.
        """,
    )

    result = run_bash(
        bash,
        "explicit function error handling",
        """
        set -e

        perform_task() {
            printf 'task started\\n'

            if ! false; then
                printf 'task failure handled inside function\\n' >&2
                return 42
            fi
        }

        if ! perform_task; then
            printf 'caller received task failure\\n'
        fi

        printf 'script continues intentionally\\n'
        """,
    )
    explain_result(result)


# ---------------------------------------------------------------------------
# Pipelines and command substitutions
# ---------------------------------------------------------------------------

def demonstrate_pipelines_and_substitution(bash: str) -> None:
    print_section("8. Pipelines and command substitutions")

    print_concept(
        "Pipeline status",
        """
        Without pipefail:

            A | B | C

        normally gets the status of C.

        With pipefail, a failure in A or B can make the pipeline fail.

        This matters when data producers or transformations are critical.
        """,
    )

    examples = [
        (
            "pipeline without pipefail",
            """
            set +e
            printf 'pipeline status = '
            false | true
            printf '%s\\n' "$?"
            """,
        ),
        (
            "pipeline with pipefail",
            """
            set +e
            set -o pipefail
            false | true
            printf 'pipeline status = %s\\n' "$?"
            """,
        ),
    ]

    for name, script in examples:
        explain_result(run_bash(bash, name, script))

    print_concept(
        "PIPESTATUS",
        """
        Bash provides PIPESTATUS as an array containing the status of the
        commands in the most recent foreground pipeline.

        This is useful when a program needs to inspect individual pipeline stages
        rather than only the combined status.
        """,
    )

    result = run_bash(
        bash,
        "inspect individual pipeline statuses",
        """
        set +e
        false | true | false
        printf 'PIPESTATUS: %s %s %s\\n' \
            "${PIPESTATUS[0]}" "${PIPESTATUS[1]}" "${PIPESTATUS[2]}"
        """,
    )
    explain_result(result)

    print_concept(
        "Command substitution",
        """
        Command substitution:

            result="$(command)"

        captures standard output.

        If the command fails, the failure can be easy to overlook depending on
        context. With strict scripting, explicitly validate important commands
        rather than assuming captured output implies success.
        """,
    )

    result = run_bash(
        bash,
        "command substitution with explicit handling",
        """
        set -e

        if output="$(printf 'generated data\\n')"; then
            printf 'captured=[%s]\\n' "$output"
        else
            printf 'generation failed\\n' >&2
            exit 1
        fi
        """,
    )
    explain_result(result)


# ---------------------------------------------------------------------------
# Expected failures
# ---------------------------------------------------------------------------

def demonstrate_expected_failures(bash: str) -> None:
    print_section("9. Expected failures are not always errors")

    print_concept(
        "The distinction",
        """
        Defensive programming requires distinguishing:

            unexpected failure
                Something went wrong and execution should stop or recover.

            expected nonzero status
                The command communicates a normal condition through its status.

        Examples include grep finding no match, test checking a missing file,
        and conditional feature detection.
        """,
    )

    result = run_bash(
        bash,
        "grep no-match handled intentionally",
        """
        set -e

        if grep -q "missing-pattern" /dev/null; then
            printf 'match found\\n'
        else
            printf 'no match; expected condition\\n'
        fi

        printf 'script continues\\n'
        """,
    )
    explain_result(result)

    print_concept(
        "Temporarily disabling errexit",
        """
        A script can intentionally run a command whose failure will be examined:

            set +e
            command
            status=$?
            set -e

        This works, but explicit conditional syntax is often easier to audit:

            if command; then
                ...
            else
                ...
            fi
        """,
    )

    result = run_bash(
        bash,
        "capturing an expected failure",
        """
        set -e

        set +e
        false
        status=$?
        set -e

        printf 'expected status was %s\\n' "$status"
        """,
    )
    explain_result(result)


# ---------------------------------------------------------------------------
# Subshells and process boundaries
# ---------------------------------------------------------------------------

def demonstrate_subshells(bash: str) -> None:
    print_section("10. Subshells, grouping, and process boundaries")

    print_concept(
        "Subshell",
        """
        Parentheses create a subshell environment:

            ( commands )

        Variable changes inside it generally do not affect the parent shell.

        A subshell also has its own execution context and exit status.
        """,
    )

    result = run_bash(
        bash,
        "subshell variable scope",
        """
        value="parent"

        (
            value="child"
            printf 'inside subshell: %s\\n' "$value"
        )

        printf 'outside subshell: %s\\n' "$value"
        """,
    )
    explain_result(result)

    print_concept(
        "Grouping in the current shell",
        """
        Curly-brace grouping:

            { commands; }

        executes in the current shell, subject to normal syntax requirements.

        Parentheses and braces therefore differ in process and variable scope.
        """,
    )

    result = run_bash(
        bash,
        "current-shell grouping",
        """
        value="parent"

        {
            value="changed"
            printf 'inside group: %s\\n' "$value"
        }

        printf 'outside group: %s\\n' "$value"
        """,
    )
    explain_result(result)


# ---------------------------------------------------------------------------
# ERR trap and stack diagnostics
# ---------------------------------------------------------------------------

def demonstrate_advanced_diagnostics(bash: str) -> None:
    print_section("11. Advanced diagnostics")

    print_concept(
        "Useful Bash diagnostic variables",
        """
        BASH_COMMAND
            The command Bash is executing at the point of diagnostic handling.

        LINENO
            Current source line number in the shell script.

        BASH_LINENO
            Line-number information associated with the function call stack.

        FUNCNAME
            Function names associated with the current call stack.

        PS4
            Prefix used by xtrace output when set -x is enabled.

        These variables can be combined into structured diagnostic messages.
        """,
    )

    result = run_bash(
        bash,
        "function stack diagnostic",
        r"""
        set -E
        trap '
            status=$?
            printf "ERROR status=%s command=%s line=%s function=%s\n" \
                "$status" "$BASH_COMMAND" "${BASH_LINENO[0]:-unknown}" \
                "${FUNCNAME[1]:-main}" >&2
        ' ERR

        level_one() {
            level_two
        }

        level_two() {
            false
        }

        level_one
        """,
    )
    explain_result(result)

    print_concept(
        "xtrace",
        """
        set -x prints commands as Bash executes them. It is useful for debugging,
        but it can expose secrets if variables are expanded into trace output.

        Never assume xtrace is safe around passwords, tokens, private keys, or
        sensitive configuration.
        """,
    )

    result = run_bash(
        bash,
        "controlled xtrace",
        """
        printf 'normal output\\n'

        set -x
        value="visible-debug-value"
        printf 'value=%s\\n' "$value"
        set +x

        printf 'tracing disabled\\n'
        """,
    )
    explain_result(result)


# ---------------------------------------------------------------------------
# Cleanup and transactional thinking
# ---------------------------------------------------------------------------

def demonstrate_transactional_workflow(bash: str) -> None:
    print_section("12. Production-style cleanup workflow")

    print_concept(
        "Why cleanup matters",
        """
        A script may create temporary directories, lock files, generated files,
        sockets, or other resources.

        If the script exits early, resources must still be released where
        appropriate. EXIT traps provide a centralized cleanup mechanism.

        Cleanup should tolerate partially completed setup. For example, rm -f
        should be acceptable when the target does not exist.
        """,
    )

    result = run_bash(
        bash,
        "transaction-like workflow",
        """
        set -Eeuo pipefail

        work_dir=""
        committed="false"

        cleanup() {
            status=$?

            if [[ -n "$work_dir" && -d "$work_dir" ]]; then
                rm -rf -- "$work_dir"
                printf 'cleanup: removed work directory\\n' >&2
            fi

            printf 'cleanup: final status=%s committed=%s\\n' \
                "$status" "$committed" >&2
        }

        trap cleanup EXIT

        work_dir="$(mktemp -d)"
        printf 'stage-1\\n' > "$work_dir/data.txt"
        printf 'staged data at %s\\n' "$work_dir"

        # Simulate a successful commit.
        mv "$work_dir/data.txt" "$work_dir/final.txt"
        committed="true"

        printf 'workflow completed\\n'
        """,
    )
    explain_result(result)

    result = run_bash(
        bash,
        "transaction-like workflow with failure",
        """
        set -Eeuo pipefail

        work_dir=""

        cleanup() {
            status=$?

            if [[ -n "$work_dir" && -d "$work_dir" ]]; then
                rm -rf -- "$work_dir"
            fi

            printf 'cleanup completed; original status=%s\\n' "$status" >&2
        }

        trap cleanup EXIT

        work_dir="$(mktemp -d)"
        printf 'partial data\\n' > "$work_dir/data.txt"

        printf 'simulating failure before commit\\n' >&2
        false
        """,
    )
    explain_result(result)


# ---------------------------------------------------------------------------
# Security examples
# ---------------------------------------------------------------------------

def demonstrate_security(bash: str) -> None:
    print_section("13. Security considerations")

    print_concept(
        "Command injection",
        """
        Never construct shell commands from untrusted input merely by concatenating
        strings.

        Dangerous conceptual pattern:

            sh -c "process $user_input"

        An attacker may introduce shell metacharacters such as ;, &, |, $(), or
        backticks.

        Prefer direct command arguments when possible. In Bash itself, use arrays
        to preserve argument boundaries.
        """,
    )

    result = run_bash(
        bash,
        "safe argument array",
        """
        set -euo pipefail

        user_input="report; printf 'unexpected command\\n'"

        command=(printf 'received=[%s]\\n')
        "${command[@]}" "$user_input"
        """,
    )
    explain_result(result)

    print_concept(
        "Arrays as an argument boundary",
        """
        An array stores individual arguments rather than one shell command string.

        For example:

            args=(-v -- "$filename")
            some_command "${args[@]}"

        This avoids accidental word splitting and usually makes argument
        construction clearer.
        """,
    )

    print_concept(
        "Permissions and temporary files",
        """
        Error handling and security overlap.

        A script should consider:
            - file permissions
            - directory permissions
            - symlink races
            - predictable filenames
            - untrusted PATH values
            - untrusted environment variables
            - secret leakage through logs
            - unsafe use of eval
            - command injection
            - excessive privileges

        Running as root does not make unsafe shell construction safe.
        """,
    )


# ---------------------------------------------------------------------------
# Retry logic
# ---------------------------------------------------------------------------

def demonstrate_retry_logic(bash: str) -> None:
    print_section("14. Retry logic and bounded recovery")

    print_concept(
        "Retries",
        """
        Retrying a failed command is useful only when failure may be transient.

        Good retry design normally specifies:
            - maximum attempts
            - delay between attempts
            - which failures are retryable
            - when to stop
            - what status to return

        Infinite retries can turn a small failure into a permanent hang.
        """,
    )

    result = run_bash(
        bash,
        "bounded retry with deterministic failure",
        """
        set -u

        attempt=1
        max_attempts=3

        while (( attempt <= max_attempts )); do
            printf 'attempt %d/%d\\n' "$attempt" "$max_attempts"

            if (( attempt == max_attempts )); then
                printf 'operation succeeded on final attempt\\n'
                break
            fi

            printf 'transient failure\\n' >&2
            (( attempt++ ))
        done
        """,
    )
    explain_result(result)

    print_concept(
        "Backoff",
        """
        Real systems often use increasing delays such as:

            delay = base * 2^(attempt - 1)

        A production implementation should also consider an upper bound and
        jitter so that many clients do not retry simultaneously.
        """,
    )

    result = run_bash(
        bash,
        "bounded exponential-backoff calculation",
        """
        set -u

        base_delay=1
        maximum_delay=8

        for attempt in 1 2 3 4 5; do
            delay=$(( base_delay * 2 ** (attempt - 1) ))

            if (( delay > maximum_delay )); then
                delay=$maximum_delay
            fi

            printf 'attempt=%s delay=%ss\\n' "$attempt" "$delay"
        done
        """,
    )
    explain_result(result)


# ---------------------------------------------------------------------------
# Testing
# ---------------------------------------------------------------------------

def demonstrate_testing_patterns(bash: str) -> None:
    print_section("15. Testing error handling")

    print_concept(
        "Test failure paths deliberately",
        """
        Error handling is incomplete if only successful execution is tested.

        A shell test suite should exercise:
            - missing arguments
            - malformed input
            - missing files
            - permission errors
            - failed commands
            - pipeline failures
            - unset configuration
            - signal interruption
            - cleanup after failure
            - expected nonzero statuses
            - retry exhaustion
        """,
    )

    result = run_bash(
        bash,
        "small self-test",
        """
        set -euo pipefail

        validate_positive_integer() {
            [[ "$1" =~ ^[0-9]+$ ]] || return 2
            (( 10#$1 > 0 )) || return 2
        }

        validate_positive_integer 5
        validate_positive_integer 0 && exit 1 || true
        validate_positive_integer abc && exit 1 || true

        printf 'self-test passed\\n'
        """,
    )
    explain_result(result)

    print_concept(
        "Do not hide failures with true",
        """
        A construction such as:

            command || true

        intentionally converts failure into success.

        It is appropriate only when the failure is genuinely acceptable and
        documented. Otherwise it can mask defects.
        """,
    )


# ---------------------------------------------------------------------------
# Comparison matrix
# ---------------------------------------------------------------------------

def print_comparison() -> None:
    print_section("16. Practical comparison of Bash error-handling mechanisms")

    rows = [
        ("$?", "Inspect the immediately preceding status", "Simple diagnostics"),
        ("if command", "Handle expected success/failure explicitly", "Best for clear branching"),
        ("&& / ||", "Compact conditional execution", "Short simple conditions"),
        ("set -e", "Stop after many unhandled failures", "Defensive baseline"),
        ("set -u", "Reject unintended unset variables", "Configuration safety"),
        ("pipefail", "Expose failures inside pipelines", "Pipeline correctness"),
        ("trap EXIT", "Centralize cleanup", "Resource management"),
        ("trap ERR", "Diagnose many command failures", "Error reporting"),
        ("trap INT/TERM", "React to signals", "Graceful shutdown"),
        ("return", "Propagate function status", "Reusable functions"),
        ("exit", "Terminate with explicit status", "Script interface"),
    ]

    print(f"{'Mechanism':<18} {'Purpose':<44} {'Typical use':<28}")
    print("-" * 94)
    for mechanism, purpose, use in rows:
        print(f"{mechanism:<18} {purpose:<44} {use:<28}")


# ---------------------------------------------------------------------------
# Comprehensive case study
# ---------------------------------------------------------------------------

def run_case_study(bash: str) -> None:
    print_section("17. Integrated defensive deployment-style case study")

    print_concept(
        "Scenario",
        """
        The shell script below simulates a small deployment workflow.

        It:
            1. Validates required configuration.
            2. Creates an isolated staging directory.
            3. Installs staged application data.
            4. Validates the staged result.
            5. Atomically promotes the staged file.
            6. Cleans up temporary state on every exit.

        The example is intentionally local and safe. It does not contact a
        network or modify a real application installation.
        """,
    )

    result = run_bash(
        bash,
        "integrated deployment simulation",
        """
        set -Eeuo pipefail

        readonly APP_NAME="example-service"
        readonly REQUIRED_VERSION="1.0.0"

        staging_dir=""
        target_dir=""

        log() {
            printf '[INFO] %s\\n' "$*"
        }

        fail() {
            printf '[ERROR] %s\\n' "$*" >&2
            return 1
        }

        cleanup() {
            local status=$?

            if [[ -n "$staging_dir" && -d "$staging_dir" ]]; then
                rm -rf -- "$staging_dir"
            fi

            if [[ -n "$target_dir" && -d "$target_dir" ]]; then
                rm -rf -- "$target_dir"
            fi

            printf '[INFO] cleanup complete, status=%s\\n' "$status" >&2
        }

        on_error() {
            local status=$?
            printf '[ERROR] status=%s command=%s line=%s\\n' \
                "$status" "$BASH_COMMAND" "${BASH_LINENO[0]}" >&2
        }

        trap on_error ERR
        trap cleanup EXIT

        log "starting $APP_NAME deployment"

        : "${REQUIRED_VERSION:?required version is missing}"

        staging_dir="$(mktemp -d)"
        target_dir="$(mktemp -d)"

        log "staging directory created"

        printf 'name=%s\\nversion=%s\\n' \
            "$APP_NAME" "$REQUIRED_VERSION" > "$staging_dir/metadata.txt"

        if [[ ! -s "$staging_dir/metadata.txt" ]]; then
            fail "staged metadata is empty"
        fi

        grep -q "^version=$REQUIRED_VERSION$" "$staging_dir/metadata.txt"

        cp -- "$staging_dir/metadata.txt" "$target_dir/application.txt"

        if [[ ! -s "$target_dir/application.txt" ]]; then
            fail "promotion produced an empty target"
        fi

        log "deployment simulation succeeded"
        """,
    )
    explain_result(result)


# ---------------------------------------------------------------------------
# Study checklist
# ---------------------------------------------------------------------------

def print_study_checklist() -> None:
    print_section("18. Study checklist")

    checklist = [
        "Understand that zero normally means success and nonzero means failure.",
        "Capture $? immediately when its value is needed.",
        "Use if statements for expected failure conditions.",
        "Understand the limitations and exceptions of set -e.",
        "Use set -u to detect unintended unset variables.",
        "Use parameter expansion for intentional optional configuration.",
        "Use set -o pipefail when pipeline failures matter.",
        "Use trap EXIT for reliable cleanup.",
        "Use ERR traps as diagnostics, not as a replacement for explicit logic.",
        "Use set -E when ERR propagation is required in functions and subshell contexts.",
        "Quote variable expansions unless deliberate splitting is required.",
        "Use arrays for command arguments instead of constructing shell command strings.",
        "Use -- before filenames where supported.",
        "Use mktemp for temporary resources.",
        "Validate external input at boundaries.",
        "Bound retry loops and distinguish retryable from permanent failures.",
        "Test both success and failure paths.",
        "Avoid masking errors with || true unless the failure is intentionally acceptable.",
        "Avoid exposing secrets through set -x or logs.",
        "Treat exit statuses as part of a script's interface to callers.",
    ]

    for index, item in enumerate(checklist, start=1):
        print(f"{index:02d}. {item}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run every educational module in a stable order."""
    print("Bash Error Handling Study Program")
    print("Topic: exit codes, set -e, set -u, traps, defensive scripting")

    try:
        bash = require_bash()
    except RuntimeError as exc:
        print(f"ERROR: {exc}")
        raise SystemExit(2)

    print(f"Bash executable: {bash}")

    demonstrate_basic_exit_codes(bash)
    demonstrate_if_and_or(bash)
    demonstrate_set_e(bash)
    demonstrate_set_u(bash)
    demonstrate_traps(bash)
    demonstrate_defensive_scripting(bash)
    demonstrate_functions(bash)
    demonstrate_pipelines_and_substitution(bash)
    demonstrate_expected_failures(bash)
    demonstrate_subshells(bash)
    demonstrate_advanced_diagnostics(bash)
    demonstrate_transactional_workflow(bash)
    demonstrate_security(bash)
    demonstrate_retry_logic(bash)
    demonstrate_testing_patterns(bash)
    print_comparison()
    run_case_study(bash)
    print_study_checklist()

    print_section("19. Completion")
    print(
        "All demonstrations completed. Individual Bash failures were isolated "
        "inside subprocesses so the Python study program could continue."
    )


if __name__ == "__main__":
    main()
