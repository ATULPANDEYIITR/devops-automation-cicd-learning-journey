#!/usr/bin/env python3
"""
Bash Functions: functions, arguments, return codes, and reusable scripts
==========================================================================

This Python study companion models and demonstrates the major ideas behind
Bash functions and reusable shell scripts.

The actual Bash syntax is shown as strings and comments because this file is
Python. The demonstrations are executable Python implementations of concepts
such as positional arguments, defaults, validation, return status, pipelines,
environment-style configuration, reusable modules, dispatch tables, retries,
logging, testing, and command-oriented script design.

The examples progress from beginner concepts to production-oriented design.
No external Python packages are required.
"""

from __future__ import annotations

import os
import shlex
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable


# ---------------------------------------------------------------------------
# 1. Fundamental idea: a function is a reusable unit of behavior
# ---------------------------------------------------------------------------
#
# Bash:
#
#   greet() {
#       echo "Hello, $1"
#   }
#
#   greet "Atul"
#
# The value $1 is the first positional argument received by the function.
#
# Python's closest conceptual equivalent is a normal function with parameters.

def greet(name: str) -> str:
    """Return a greeting for one argument."""
    return f"Hello, {name}"


def demonstrate_basic_function() -> None:
    print("\n=== 1. Basic function ===")
    print(greet("Atul"))
    print(greet("Developer"))


# ---------------------------------------------------------------------------
# 2. Bash positional arguments
# ---------------------------------------------------------------------------
#
# Important Bash function variables:
#
#   $1       first argument
#   $2       second argument
#   $3       third argument
#   $#       number of arguments
#   $@       all arguments as separate words
#   "$@"     all arguments preserved as separate arguments
#   $*       all arguments
#   "$*"     all arguments joined according to IFS
#
# "$@" is normally preferred when forwarding arguments because it preserves
# argument boundaries.

def inspect_arguments(*arguments: str) -> dict[str, object]:
    return {
        "count": len(arguments),
        "first": arguments[0] if arguments else None,
        "second": arguments[1] if len(arguments) > 1 else None,
        "all_as_list": list(arguments),
        "all_as_words": " ".join(arguments),
    }


def demonstrate_arguments() -> None:
    print("\n=== 2. Positional arguments ===")

    data = inspect_arguments("alpha", "two words", "gamma")

    for key, value in data.items():
        print(f"{key:14}: {value}")

    print("\nBash conceptual form:")
    print('inspect_arguments() {')
    print('    echo "count=$#"')
    print('    echo "first=$1"')
    print('    printf "<%s>\\n" "$@"')
    print('}')
    print('inspect_arguments "alpha" "two words" "gamma"')


# ---------------------------------------------------------------------------
# 3. The critical distinction between stdout and a return status
# ---------------------------------------------------------------------------
#
# Bash functions have two very different output mechanisms:
#
#   echo "value"
#
# writes to stdout.
#
#   return 0
#
# sets the function's exit status.
#
# A Bash function's status is an integer from 0 through 255. By convention:
#
#   0     success
#   non-0 failure or another condition
#
# Command substitution captures stdout, not the return status:
#
#   result=$(function_name)
#
# The function status can be captured separately:
#
#   function_name
#   status=$?
#
# Python functions can return objects directly, so this example deliberately
# models Bash's distinction.

@dataclass
class BashResult:
    stdout: str
    return_code: int


def validate_username(username: str) -> BashResult:
    """Model a Bash function that prints a value and returns a status."""
    if not username:
        return BashResult("", 2)

    if not username.replace("_", "").isalnum():
        return BashResult("", 3)

    return BashResult(username.lower(), 0)


def demonstrate_return_codes() -> None:
    print("\n=== 3. Return values versus return codes ===")

    for username in ["Atul", "user_01", "", "bad-name"]:
        result = validate_username(username)
        print(
            f"input={username!r:12} "
            f"stdout={result.stdout!r:12} "
            f"status={result.return_code}"
        )

    print("\nBash conceptual usage:")
    print('validate_username "$name"')
    print('status=$?')
    print('if (( status == 0 )); then')
    print('    echo "Valid"')
    print('fi')


# ---------------------------------------------------------------------------
# 4. Default arguments
# ---------------------------------------------------------------------------
#
# Bash does not provide function defaults in the same syntax as Python.
# A common Bash pattern is:
#
#   greet() {
#       local name="${1:-Guest}"
#       echo "Hello, $name"
#   }
#
# ${1:-Guest} means use Guest when $1 is unset or empty.
#
# Related parameter-expansion forms:
#
#   ${var:-default}   default if unset OR empty
#   ${var-default}    default if unset
#   ${var:=default}   assign default if unset OR empty
#   ${var:?message}   fail if unset OR empty
#   ${var:+value}     use value when set and non-empty

def greet_with_default(name: str | None = None) -> str:
    effective_name = name if name else "Guest"
    return f"Hello, {effective_name}"


def demonstrate_defaults() -> None:
    print("\n=== 4. Default arguments ===")
    print(greet_with_default())
    print(greet_with_default(""))
    print(greet_with_default("Atul"))

    print("\nBash:")
    print('greet() {')
    print('    local name="${1:-Guest}"')
    print('    printf "Hello, %s\\n" "$name"')
    print('}')


# ---------------------------------------------------------------------------
# 5. Local variables
# ---------------------------------------------------------------------------
#
# Bash variables are global by default.
#
#   count=10
#
# inside a function can modify a global variable unless local is used.
#
#   local count=10
#
# creates function-local scope.
#
# Using local variables is an important defensive practice in reusable scripts.

GLOBAL_COUNTER = 100


def demonstrate_scope() -> None:
    global GLOBAL_COUNTER

    print("\n=== 5. Variable scope ===")

    def function_with_local_variable() -> int:
        local_counter = 5
        return local_counter

    print("Global before:", GLOBAL_COUNTER)
    print("Local value:", function_with_local_variable())
    print("Global after :", GLOBAL_COUNTER)

    # The Python example illustrates the desired design principle:
    # avoid modifying global state unless the API intentionally requires it.


# ---------------------------------------------------------------------------
# 6. Passing many arguments and preserving spaces
# ---------------------------------------------------------------------------
#
# Bash:
#
#   print_files() {
#       for file in "$@"; do
#           printf 'FILE: %s\n' "$file"
#       done
#   }
#
# Without "$@" a filename such as "annual report.txt" can be split into
# multiple words.
#
# This is one of the most important practical rules in shell scripting.

def print_items(items: Iterable[str]) -> None:
    for item in items:
        print(f"ITEM: {item}")


def demonstrate_argument_boundaries() -> None:
    print("\n=== 6. Argument boundaries ===")

    files = [
        "report.txt",
        "annual report.txt",
        "data/2026 results.csv",
    ]

    print_items(files)

    print("\nBash safe forwarding:")
    print('for file in "$@"; do')
    print('    printf "FILE: %s\\n" "$file"')
    print('done')


# ---------------------------------------------------------------------------
# 7. Shift and option-like positional processing
# ---------------------------------------------------------------------------
#
# Bash's shift command moves positional parameters:
#
#   while (( $# > 0 )); do
#       case "$1" in
#           --verbose)
#               verbose=true
#               shift
#               ;;
#           --name)
#               name="$2"
#               shift 2
#               ;;
#       esac
#   done
#
# The example below models the same parser.

@dataclass
class ParsedOptions:
    verbose: bool = False
    name: str = "Guest"
    files: list[str] | None = None


def parse_arguments(arguments: list[str]) -> tuple[ParsedOptions | None, int]:
    options = ParsedOptions(files=[])

    index = 0
    while index < len(arguments):
        current = arguments[index]

        if current == "--verbose":
            options.verbose = True
            index += 1
        elif current == "--name":
            if index + 1 >= len(arguments):
                print("Error: --name requires a value", file=sys.stderr)
                return None, 2

            options.name = arguments[index + 1]
            index += 2
        elif current == "--":
            options.files.extend(arguments[index + 1:])
            break
        elif current.startswith("-"):
            print(f"Error: unknown option: {current}", file=sys.stderr)
            return None, 2
        else:
            options.files.append(current)
            index += 1

    return options, 0


def demonstrate_argument_parser() -> None:
    print("\n=== 7. Option parsing ===")

    samples = [
        ["--verbose", "--name", "Atul", "one.txt", "two.txt"],
        ["--name", "Research", "--", "--literal-file"],
        ["--unknown"],
    ]

    for sample in samples:
        print("\nInput:", sample)
        options, status = parse_arguments(sample)
        print("Status:", status)
        print("Parsed:", options)


# ---------------------------------------------------------------------------
# 8. Environment variables and configuration
# ---------------------------------------------------------------------------
#
# Bash functions often consume environment variables:
#
#   API_URL="${API_URL:-http://localhost:8000}"
#
# Exported variables become available to child processes:
#
#   export API_URL
#
# Python can read environment variables through os.environ.

def get_configuration(environment: dict[str, str] | None = None) -> dict[str, str]:
    source = environment if environment is not None else os.environ

    return {
        "environment": source.get("APP_ENV", "development"),
        "log_level": source.get("LOG_LEVEL", "INFO"),
        "timeout": source.get("TIMEOUT", "30"),
    }


def demonstrate_environment_configuration() -> None:
    print("\n=== 8. Environment configuration ===")

    configuration = get_configuration(
        {
            "APP_ENV": "production",
            "LOG_LEVEL": "WARNING",
        }
    )

    print(configuration)

    print("\nBash:")
    print('APP_ENV="${APP_ENV:-development}"')
    print('LOG_LEVEL="${LOG_LEVEL:-INFO}"')
    print('TIMEOUT="${TIMEOUT:-30}"')
    print('export APP_ENV LOG_LEVEL TIMEOUT')


# ---------------------------------------------------------------------------
# 9. Boolean tests and conditionals
# ---------------------------------------------------------------------------
#
# Bash does not use Python-style True/False return objects for ordinary
# shell conditions. Commands communicate success through exit status.
#
# Examples:
#
#   [[ -f "$file" ]]
#   [[ -d "$directory" ]]
#   [[ -n "$value" ]]
#   [[ "$a" == "$b" ]]
#
# An if statement tests the command status:
#
#   if [[ -f "$file" ]]; then
#       ...
#   fi

def file_exists(path: Path) -> bool:
    return path.is_file()


def demonstrate_tests() -> None:
    print("\n=== 9. Tests and conditions ===")

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "example.txt"
        path.write_text("hello\n", encoding="utf-8")

        print("Regular file:", file_exists(path))
        print("Directory   :", path.parent.is_dir())

    print("\nBash:")
    print('if [[ -f "$file" ]]; then')
    print('    echo "regular file"')
    print('fi')


# ---------------------------------------------------------------------------
# 10. Error handling
# ---------------------------------------------------------------------------
#
# A robust Bash function should:
#
#   - validate input
#   - write diagnostics to stderr
#   - return meaningful non-zero status
#   - avoid hiding failures
#
# stderr:
#
#   printf 'Error: invalid input\\n' >&2
#
# status:
#
#   return 2
#
# A useful convention is:
#
#   0 = success
#   1 = general failure
#   2 = invalid command usage
#
# Actual conventions vary by application.

def require_positive_integer(value: str) -> BashResult:
    try:
        number = int(value)
    except ValueError:
        return BashResult("Error: expected an integer", 2)

    if number <= 0:
        return BashResult("Error: value must be positive", 3)

    return BashResult(str(number), 0)


def demonstrate_error_handling() -> None:
    print("\n=== 10. Validation and error handling ===")

    for value in ["42", "0", "-3", "abc"]:
        result = require_positive_integer(value)
        stream = "stdout" if result.return_code == 0 else "stderr"
        print(
            f"{value!r:6} -> {stream}: {result.stdout!r}, "
            f"status={result.return_code}"
        )


# ---------------------------------------------------------------------------
# 11. Bash function composition
# ---------------------------------------------------------------------------
#
# Functions become powerful when small functions are composed.
#
#   validate_input
#   load_configuration
#   process_data
#   save_result
#
# Each function should have a narrow responsibility.

def normalize_email(email: str) -> str:
    return email.strip().lower()


def validate_email(email: str) -> bool:
    normalized = normalize_email(email)
    return "@" in normalized and "." in normalized.rsplit("@", 1)[-1]


def prepare_email(email: str) -> BashResult:
    normalized = normalize_email(email)

    if not validate_email(normalized):
        return BashResult("Invalid email address", 2)

    return BashResult(normalized, 0)


def demonstrate_composition() -> None:
    print("\n=== 11. Function composition ===")

    for email in [" ATUL@example.com ", "invalid", "person@example.org"]:
        result = prepare_email(email)
        print(email, "=>", result)


# ---------------------------------------------------------------------------
# 12. Command execution and exit status
# ---------------------------------------------------------------------------
#
# Bash is a command interpreter, so functions frequently call external
# commands:
#
#   function backup() {
#       tar -czf "$1.tar.gz" "$1"
#   }
#
# The called command has an exit status. A function can return it:
#
#   command
#   return $?
#
# Or simply:
#
#   command
#
# because the function's final command determines its status.
#
# Python subprocess.run provides a comparable interface.

def run_command(command: list[str]) -> BashResult:
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        return BashResult(str(error), 127)

    output = completed.stdout.strip()
    error_output = completed.stderr.strip()

    if completed.returncode != 0 and error_output:
        output = error_output

    return BashResult(output, completed.returncode)


def demonstrate_external_command() -> None:
    print("\n=== 12. External commands and status ===")

    result = run_command([sys.executable, "-c", "print('child process ran')"])
    print("Success output:", result.stdout)
    print("Status:", result.return_code)

    result = run_command(
        [sys.executable, "-c", "import sys; sys.exit(7)"]
    )
    print("Failure status:", result.return_code)


# ---------------------------------------------------------------------------
# 13. Pipelines
# ---------------------------------------------------------------------------
#
# Bash:
#
#   generate_data | filter_data | summarize_data
#
# Pipelines connect stdout of one command to stdin of another.
#
# A subtle Bash issue is that pipeline status behavior depends on shell
# settings. Without pipefail, a pipeline may report the status of its final
# command even if an earlier command failed.
#
# Bash:
#
#   set -o pipefail
#
# makes the pipeline fail when a command in the pipeline fails.

def demonstrate_pipeline_concept() -> None:
    print("\n=== 13. Pipeline concept ===")

    data = ["apple", "banana", "apricot", "pear", "avocado"]

    generated = data
    filtered = [item for item in generated if item.startswith("a")]
    summarized = len(filtered)

    print("Generated:", generated)
    print("Filtered :", filtered)
    print("Count    :", summarized)

    print("\nBash conceptual pipeline:")
    print("generate_data | filter_data | summarize_data")
    print("set -o pipefail")


# ---------------------------------------------------------------------------
# 14. Functions that return data
# ---------------------------------------------------------------------------
#
# Shell functions generally communicate data through stdout:
#
#   get_version() {
#       printf '%s\\n' "1.2.3"
#   }
#
#   version="$(get_version)"
#
# Diagnostics should go to stderr so command substitution does not capture
# them accidentally.

def get_version() -> str:
    return "1.2.3"


def demonstrate_stdout_as_data() -> None:
    print("\n=== 14. stdout as function data ===")
    version = get_version()
    print("Captured value:", version)

    print("\nBash:")
    print('version="$(get_version)"')
    print('printf "Version: %s\\n" "$version"')


# ---------------------------------------------------------------------------
# 15. Reusable script structure
# ---------------------------------------------------------------------------
#
# A reusable Bash script often separates:
#
#   constants
#   functions
#   argument parsing
#   main function
#   entry-point guard
#
# Bash has no Python-style __name__ == "__main__" mechanism. A common pattern:
#
#   main() {
#       ...
#   }
#
#   if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
#       main "$@"
#   fi
#
# This allows the file to be sourced without automatically executing main.

def application_main(arguments: list[str]) -> int:
    options, status = parse_arguments(arguments)

    if status != 0 or options is None:
        return status

    print(f"Hello, {options.name}")

    if options.verbose:
        print(f"Files received: {len(options.files or [])}")

    for filename in options.files or []:
        print(f"Processing: {filename}")

    return 0


def demonstrate_script_structure() -> None:
    print("\n=== 15. Main function and reusable script structure ===")
    status = application_main(
        ["--verbose", "--name", "Atul", "report.txt", "data.csv"]
    )
    print("Application status:", status)


# ---------------------------------------------------------------------------
# 16. Library-style versus executable-style shell scripts
# ---------------------------------------------------------------------------
#
# Reusable Bash libraries can contain functions:
#
#   #!/usr/bin/env bash
#   log_info() { ...; }
#   log_error() { ...; }
#
# Another script can load them:
#
#   source ./lib.sh
#
# or:
#
#   . ./lib.sh
#
# Important security point:
# never blindly source a file whose contents or location you do not trust.
#
# "${BASH_SOURCE[0]}" can be used to locate the current script rather than
# relying on the caller's working directory.

def demonstrate_reusable_library() -> None:
    print("\n=== 16. Reusable library design ===")

    def log_info(message: str) -> None:
        print(f"INFO: {message}")

    def log_error(message: str) -> None:
        print(f"ERROR: {message}", file=sys.stderr)

    log_info("library function called")
    log_error("example diagnostic")

    print("\nBash:")
    print("source ./lib.sh")
    print('log_info "library function called"')


# ---------------------------------------------------------------------------
# 17. Namespaces and avoiding accidental global collisions
# ---------------------------------------------------------------------------
#
# Bash functions share a global namespace within a shell.
#
# Naming conventions can reduce collisions:
#
#   app_log_info
#   app_validate_config
#   app_process_file
#
# This is especially useful when sourcing multiple libraries.

class ApplicationFunctions:
    """Python namespace used to model a Bash function naming convention."""

    @staticmethod
    def log_info(message: str) -> None:
        print(f"APP_INFO: {message}")

    @staticmethod
    def validate_config(config: dict[str, str]) -> bool:
        return bool(config.get("environment"))


def demonstrate_namespacing() -> None:
    print("\n=== 17. Namespacing ===")
    ApplicationFunctions.log_info("namespaced operation")
    print(
        "Configuration valid:",
        ApplicationFunctions.validate_config({"environment": "prod"}),
    )


# ---------------------------------------------------------------------------
# 18. Higher-order function: conceptual comparison
# ---------------------------------------------------------------------------
#
# Bash functions can be invoked dynamically:
#
#   command="$1"
#   "$command" ...
#
# Function names can also be stored and dispatched through controlled logic.
#
# Dynamic execution must be handled carefully. Never concatenate untrusted
# input into eval.
#
# Python can model a safer dispatch table directly.

Handler = Callable[[list[str]], int]


def command_status(arguments: list[str]) -> int:
    print("status: system is operational")
    return 0


def command_version(arguments: list[str]) -> int:
    print("version: 1.0.0")
    return 0


def command_echo(arguments: list[str]) -> int:
    print(" ".join(arguments))
    return 0


COMMANDS: dict[str, Handler] = {
    "status": command_status,
    "version": command_version,
    "echo": command_echo,
}


def dispatch_command(command: str, arguments: list[str]) -> int:
    handler = COMMANDS.get(command)

    if handler is None:
        print(f"Unknown command: {command}", file=sys.stderr)
        return 127

    return handler(arguments)


def demonstrate_dispatch() -> None:
    print("\n=== 18. Function dispatch ===")

    for command, arguments in [
        ("status", []),
        ("version", []),
        ("echo", ["hello", "shell", "functions"]),
        ("missing", []),
    ]:
        status = dispatch_command(command, arguments)
        print("Return status:", status)


# ---------------------------------------------------------------------------
# 19. Retry logic
# ---------------------------------------------------------------------------
#
# Shell scripts often wrap unreliable operations:
#
#   retry() {
#       local attempts="$1"
#       shift
#
#       for ((i=1; i<=attempts; i++)); do
#           "$@" && return 0
#           sleep 1
#       done
#
#       return 1
#   }
#
# Retry design must consider:
#   - whether failure is transient
#   - maximum attempts
#   - delay
#   - exponential backoff
#   - idempotency
#   - timeout
#   - logging
#
# The example uses an injectable operation for deterministic testing.

def retry_operation(
    operation: Callable[[], BashResult],
    attempts: int,
    delay_seconds: float = 0.0,
) -> BashResult:
    if attempts <= 0:
        return BashResult("attempt count must be positive", 2)

    last_result = BashResult("operation did not execute", 1)

    for attempt in range(1, attempts + 1):
        last_result = operation()

        if last_result.return_code == 0:
            return last_result

        if attempt < attempts and delay_seconds > 0:
            time.sleep(delay_seconds)

    return last_result


def demonstrate_retry() -> None:
    print("\n=== 19. Retry logic ===")

    state = {"attempts": 0}

    def unstable_operation() -> BashResult:
        state["attempts"] += 1

        if state["attempts"] < 3:
            return BashResult("temporary failure", 1)

        return BashResult("success", 0)

    result = retry_operation(unstable_operation, attempts=4)
    print("Attempts:", state["attempts"])
    print("Result:", result)


# ---------------------------------------------------------------------------
# 20. Idempotency
# ---------------------------------------------------------------------------
#
# An idempotent operation can be safely repeated without producing an
# unintended cumulative effect.
#
# Good shell automation often prefers:
#
#   mkdir -p directory
#
# over:
#
#   mkdir directory
#
# when repeated execution is expected.
#
# Another example:
#
#   touch file
#
# creates the file if necessary and leaves an existing file in place.
#
# Configuration management heavily depends on idempotent operations.

def ensure_directory(path: Path) -> BashResult:
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        return BashResult(str(error), 1)

    return BashResult(str(path), 0)


def demonstrate_idempotency() -> None:
    print("\n=== 20. Idempotency ===")

    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "nested" / "output"

        first = ensure_directory(target)
        second = ensure_directory(target)

        print("First :", first)
        print("Second:", second)
        print("Exists:", target.is_dir())


# ---------------------------------------------------------------------------
# 21. Security: command injection
# ---------------------------------------------------------------------------
#
# Dangerous Bash:
#
#   eval "grep $pattern $file"
#
# or:
#
#   sh -c "some command $untrusted_input"
#
# If user-controlled input is inserted into shell syntax, shell metacharacters
# can change what executes.
#
# Prefer:
#
#   command -- "$variable"
#
# and pass arguments as separate words.
#
# In Python, subprocess.run([...], shell=False) is safer than constructing a
# shell command string.

def safe_echo(user_input: str) -> BashResult:
    return run_command([sys.executable, "-c", "import sys; print(sys.argv[1])", user_input])


def demonstrate_command_injection_defense() -> None:
    print("\n=== 21. Command injection defense ===")

    malicious_text = 'hello; pretend-this-is-a-command'

    result = safe_echo(malicious_text)

    print("Input :", malicious_text)
    print("Output:", result.stdout)
    print("Status:", result.return_code)

    print("\nBash safe form:")
    print('printf "%s\\n" "$user_input"')
    print("\nAvoid:")
    print('eval "printf \\"%s\\\\n\\" $user_input"')


# ---------------------------------------------------------------------------
# 22. set -e, set -u, pipefail
# ---------------------------------------------------------------------------
#
# Production Bash scripts frequently use:
#
#   set -euo pipefail
#
# Meaning:
#
#   -e       exit when a simple command fails in contexts where failure is
#            considered unhandled
#   -u       treat unset variables as errors
#   pipefail make pipeline status reflect failures of pipeline components
#
# This is useful but not magic. set -e has important exceptions involving
# conditionals, lists, command substitutions, and other shell grammar.
#
# Defensive shell programming still requires explicit error handling.

def demonstrate_strict_mode() -> None:
    print("\n=== 22. Bash strict mode ===")
    print("Typical Bash header:")
    print("#!/usr/bin/env bash")
    print("set -euo pipefail")
    print()
    print("Important: strict mode does not eliminate the need to understand")
    print("Bash conditional and pipeline semantics.")


# ---------------------------------------------------------------------------
# 23. Traps and cleanup
# ---------------------------------------------------------------------------
#
# Bash:
#
#   cleanup() {
#       rm -f "$temporary_file"
#   }
#
#   trap cleanup EXIT
#
# A trap allows cleanup when the shell exits.
#
# Python's context manager is a comparable resource-management pattern.

def demonstrate_cleanup() -> None:
    print("\n=== 23. Cleanup and resource management ===")

    with tempfile.TemporaryDirectory() as directory:
        temporary_file = Path(directory) / "temporary.txt"
        temporary_file.write_text("temporary data", encoding="utf-8")
        print("Created:", temporary_file)
        print("Exists inside context:", temporary_file.exists())

    print("Exists after cleanup:", temporary_file.exists())

    print("\nBash pattern:")
    print('cleanup() { rm -f -- "$temporary_file"; }')
    print('trap cleanup EXIT')


# ---------------------------------------------------------------------------
# 24. Logging
# ---------------------------------------------------------------------------
#
# Reusable shell libraries often centralize logging:
#
#   log_info()  { printf '[INFO] %s\\n' "$*" >&2; }
#   log_warn()  { printf '[WARN] %s\\n' "$*" >&2; }
#   log_error() { printf '[ERROR] %s\\n' "$*" >&2; }
#
# Diagnostics commonly belong on stderr so stdout remains suitable for
# machine-readable data.

def log_info(message: str) -> None:
    print(f"[INFO] {message}", file=sys.stderr)


def log_warning(message: str) -> None:
    print(f"[WARN] {message}", file=sys.stderr)


def log_error(message: str) -> None:
    print(f"[ERROR] {message}", file=sys.stderr)


def demonstrate_logging() -> None:
    print("\n=== 24. Logging ===")
    log_info("operation started")
    log_warning("configuration is using a default")
    log_error("example error message")


# ---------------------------------------------------------------------------
# 25. Unit testing function behavior
# ---------------------------------------------------------------------------
#
# Shell functions can be tested by invoking the script/function and checking:
#
#   - exit status
#   - stdout
#   - stderr
#   - files created or changed
#
# A function that has a narrow responsibility is much easier to test.

def run_self_tests() -> None:
    print("\n=== 25. Self-tests ===")

    assert greet("Atul") == "Hello, Atul"

    result = validate_username("Atul_123")
    assert result.return_code == 0
    assert result.stdout == "atul_123"

    invalid = validate_username("bad-name")
    assert invalid.return_code != 0

    assert greet_with_default() == "Hello, Guest"

    parsed, status = parse_arguments(["--verbose", "--name", "Atul", "a.txt"])
    assert status == 0
    assert parsed is not None
    assert parsed.verbose is True
    assert parsed.name == "Atul"
    assert parsed.files == ["a.txt"]

    assert dispatch_command("status", []) == 0
    assert dispatch_command("does-not-exist", []) == 127

    with tempfile.TemporaryDirectory() as directory:
        target = Path(directory) / "a" / "b"
        assert ensure_directory(target).return_code == 0
        assert target.is_dir()

    print("All self-tests passed.")


# ---------------------------------------------------------------------------
# 26. Performance considerations
# ---------------------------------------------------------------------------
#
# Shell functions are lightweight organizational units, but repeatedly
# starting external processes can be expensive.
#
# For example, this is often inefficient for large datasets:
#
#   while read -r line; do
#       external_command "$line"
#   done
#
# when one invocation can process all input.
#
# Functions do not create an independent operating-system process by
# themselves. External commands do.
#
# Prefer shell built-ins where appropriate and avoid unnecessary subprocess
# creation in performance-sensitive loops.

def demonstrate_performance_principles() -> None:
    print("\n=== 26. Performance ===")

    numbers = list(range(100_000))

    start = time.perf_counter()
    total = sum(numbers)
    elapsed = time.perf_counter() - start

    print("Built-in aggregation result:", total)
    print(f"Elapsed time: {elapsed:.6f} seconds")

    print("\nShell design principle:")
    print("Prefer one operation over thousands of unnecessary subprocesses.")


# ---------------------------------------------------------------------------
# 27. A realistic reusable task runner
# ---------------------------------------------------------------------------
#
# This example models a small production-style command dispatcher.
#
# The design uses:
#   - explicit commands
#   - validation
#   - status codes
#   - centralized logging
#   - dependency injection for testability
#   - deterministic behavior
#
# A Bash implementation would use functions in a similar architecture.

@dataclass
class Task:
    name: str
    handler: Handler
    description: str


class TaskRunner:
    def __init__(self, tasks: list[Task]) -> None:
        self.tasks = {task.name: task for task in tasks}

    def run(self, name: str, arguments: list[str]) -> int:
        task = self.tasks.get(name)

        if task is None:
            log_error(f"unknown task: {name}")
            return 127

        log_info(f"starting task: {name}")
        status = task.handler(arguments)

        if status == 0:
            log_info(f"task completed: {name}")
        else:
            log_error(f"task failed: {name}, status={status}")

        return status

    def list_tasks(self) -> None:
        for task in sorted(self.tasks.values(), key=lambda item: item.name):
            print(f"{task.name:12} {task.description}")


def build_task_runner() -> TaskRunner:
    return TaskRunner(
        [
            Task("status", command_status, "display service status"),
            Task("version", command_version, "display application version"),
            Task("echo", command_echo, "print supplied arguments"),
        ]
    )


def demonstrate_task_runner() -> None:
    print("\n=== 27. Realistic reusable task runner ===")

    runner = build_task_runner()

    print("Available tasks:")
    runner.list_tasks()

    print("\nRunning status:")
    status = runner.run("status", [])
    print("Exit status:", status)

    print("\nRunning echo:")
    status = runner.run("echo", ["reusable", "shell", "functions"])
    print("Exit status:", status)

    print("\nRunning invalid command:")
    status = runner.run("missing", [])
    print("Exit status:", status)


# ---------------------------------------------------------------------------
# 28. Bash-specific syntax reference
# ---------------------------------------------------------------------------
#
# The following strings make the most important syntax easy to inspect while
# keeping this Python file executable.

def print_bash_reference() -> None:
    print("\n=== 28. Bash function syntax reference ===")

    reference = r'''
# Basic function
greet() {
    printf 'Hello, %s\n' "$1"
}

# Equivalent older style
function greet {
    printf 'Hello, %s\n' "$1"
}

# Multiple arguments
show_arguments() {
    printf 'count=%s\n' "$#"
    printf 'argument=<%s>\n' "$@"
}

# Local variables
calculate_total() {
    local first="$1"
    local second="$2"
    local total=$((first + second))
    printf '%s\n' "$total"
}

# Return status
is_valid() {
    [[ -n "$1" ]]
}

# Explicit return
validate() {
    if [[ -z "$1" ]]; then
        printf 'missing argument\n' >&2
        return 2
    fi
    return 0
}

# Capture stdout
value="$(get_value)"

# Capture exit status
validate "$value"
status=$?

# Conditional status check
if validate "$value"; then
    printf 'valid\n'
else
    printf 'invalid\n' >&2
fi

# Forward all arguments safely
wrapper() {
    some_command "$@"
}

# Shift positional arguments
parse() {
    while (( $# > 0 )); do
        case "$1" in
            --verbose)
                verbose=true
                shift
                ;;
            --name)
                name="$2"
                shift 2
                ;;
            *)
                printf 'unknown argument: %s\n' "$1" >&2
                return 2
                ;;
        esac
    done
}

# Main entry point
main() {
    ...
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    main "$@"
fi
'''
    print(reference)


# ---------------------------------------------------------------------------
# 29. Important Bash edge cases
# ---------------------------------------------------------------------------

def demonstrate_edge_cases() -> None:
    print("\n=== 29. Edge cases ===")

    examples = [
        [],
        [""],
        ["two words"],
        ["--"],
        ["--verbose", "--name"],
        ["--unknown"],
    ]

    for example in examples:
        options, status = parse_arguments(example)
        print(f"{example!r:35} status={status}, options={options}")

    print("\nImportant shell edge cases:")
    print("1. Empty string is different from an unset variable.")
    print("2. Quoting preserves argument boundaries.")
    print("3. A command's stdout is different from its exit status.")
    print("4. return does not normally return arbitrary string data.")
    print("5. $@ and \"$@\" have different behavior.")
    print("6. set -u makes accidental unset-variable access significant.")
    print("7. Pipelines have special exit-status semantics.")
    print("8. Functions can modify global shell state unless variables are local.")
    print("9. eval can turn data into executable shell syntax.")
    print("10. Sourcing executes the sourced file in the current shell.")


# ---------------------------------------------------------------------------
# 30. Production checklist
# ---------------------------------------------------------------------------

def production_checklist() -> None:
    print("\n=== 30. Production checklist ===")

    checklist = [
        "Use a clear function name that describes one responsibility.",
        "Validate required arguments before using them.",
        'Quote variable expansions, especially "$@" and "$variable".',
        "Use local variables inside functions where appropriate.",
        "Return meaningful non-zero statuses for failures.",
        "Keep stdout available for intended machine-readable output.",
        "Send diagnostics to stderr.",
        "Avoid eval with untrusted input.",
        "Use explicit command paths or controlled PATH where security matters.",
        "Use set -euo pipefail deliberately and understand its semantics.",
        "Use traps for temporary-file cleanup where appropriate.",
        "Prefer idempotent operations in automation.",
        "Avoid unnecessary external processes in large loops.",
        "Test success, failure, empty input, missing input, and unusual characters.",
        "Separate reusable functions from the executable main entry point.",
        "Document arguments, output, status codes, side effects, and assumptions.",
    ]

    for item in checklist:
        print(f"- {item}")


# ---------------------------------------------------------------------------
# 31. Main educational execution
# ---------------------------------------------------------------------------

def main() -> int:
    print("=" * 78)
    print("BASH FUNCTIONS: COMPLETE STUDY COMPANION")
    print("=" * 78)
    print(
        "Focus: functions, arguments, return codes, reusable scripts, "
        "error handling, security, and production design."
    )

    demonstrate_basic_function()
    demonstrate_arguments()
    demonstrate_return_codes()
    demonstrate_defaults()
    demonstrate_scope()
    demonstrate_argument_boundaries()
    demonstrate_argument_parser()
    demonstrate_environment_configuration()
    demonstrate_tests()
    demonstrate_error_handling()
    demonstrate_composition()
    demonstrate_external_command()
    demonstrate_pipeline_concept()
    demonstrate_stdout_as_data()
    demonstrate_script_structure()
    demonstrate_reusable_library()
    demonstrate_namespacing()
    demonstrate_dispatch()
    demonstrate_retry()
    demonstrate_idempotency()
    demonstrate_command_injection_defense()
    demonstrate_strict_mode()
    demonstrate_cleanup()
    demonstrate_logging()
    run_self_tests()
    demonstrate_performance_principles()
    demonstrate_task_runner()
    print_bash_reference()
    demonstrate_edge_cases()
    production_checklist()

    print("\n" + "=" * 78)
    print("Study file execution completed successfully.")
    print("=" * 78)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
