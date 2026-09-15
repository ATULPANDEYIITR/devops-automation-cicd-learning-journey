"""
Bash Fundamentals Study Companion
Topic: Shell syntax, variables, conditions, loops

This file teaches Bash fundamentals from beginner to advanced level through
executable Python demonstrations and comparisons.

The Python program models important Bash concepts without requiring Bash itself.
It also executes a few safe Bash examples when Bash is available, so the learner
can compare shell behavior with Python behavior.

Run:
    python bash_fundamentals.py

The demonstrations are intentionally self-contained and use only the Python
standard library.
"""

from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Callable, Iterable


# ============================================================================
# 1. INTRODUCTION
# ============================================================================

def section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def explain(message: str) -> None:
    print(f"\n{message}")


def run_python_example(name: str, function: Callable[[], None]) -> None:
    print(f"\n--- {name} ---")
    try:
        function()
    except Exception as exc:
        print(f"Example failed: {type(exc).__name__}: {exc}")


def command_exists(command: str) -> bool:
    return shutil.which(command) is not None


section("BASH FUNDAMENTALS: SHELL SYNTAX, VARIABLES, CONDITIONS, LOOPS")

print(
    """
Bash is both a command interpreter and a scripting language commonly used
on Linux and Unix-like systems.

A shell accepts commands, expands syntax, starts programs, connects their
input/output, and reports an exit status.

Core concepts covered here:

  * shell commands and arguments
  * quoting and escaping
  * variables and environment variables
  * positional parameters
  * command substitution
  * arithmetic expansion
  * conditions and exit status
  * if/elif/else
  * case
  * for, while, and until loops
  * functions
  * arrays
  * parameter expansion
  * redirection and pipelines
  * globbing
  * process-related concepts
  * safe command execution
  * debugging and defensive scripting
  * performance and production considerations
"""
)


# ============================================================================
# 2. BASIC SHELL COMMAND MODEL
# ============================================================================

section("1. BASIC SHELL COMMAND MODEL")

print(
    """
A typical Bash command has this conceptual structure:

    command argument1 argument2 ...

Examples:

    pwd
    ls
    echo "hello"
    mkdir reports
    printf '%s\\n' "hello"

The shell first interprets shell syntax. It may perform expansions such as
variable expansion, command substitution, arithmetic expansion, and pathname
expansion before the resulting command is executed.

The distinction is important:

    echo "$name"

is not the same shell operation as:

    echo $name

because unquoted expansion can undergo word splitting and pathname expansion.
"""
)


def demonstrate_command_model() -> None:
    current_directory = os.getcwd()
    operating_system = platform.system()

    print("Current directory:", current_directory)
    print("Operating system:", operating_system)
    print("Equivalent Python concept: os.getcwd()")


run_python_example("Command model", demonstrate_command_model)


# ============================================================================
# 3. QUOTING AND ESCAPING
# ============================================================================

section("2. QUOTING AND ESCAPING")

print(
    """
Bash has three especially important forms of quoting:

Single quotes:
    'text $variable'

Everything inside is treated literally, except that a single quote cannot
appear directly inside a single-quoted string.

Double quotes:
    "text $variable"

Variable expansion and command substitution still work inside double quotes,
while most word splitting and pathname expansion are suppressed.

Backslash:
    \\$

A backslash can prevent the special interpretation of the following
character in appropriate contexts.

Example:

    name="Ada"
    echo '$name'
    echo "$name"
    echo \\$name

Conceptual results:

    $name
    Ada
    $name
"""
)


def demonstrate_python_quoting() -> None:
    name = "Ada"

    print("Single-quoted Python string:", '$name')
    print("Double-quoted Python string with formatting:", f"{name}")
    print("Escaped dollar sign:", "\\$name")
    print("Python and Bash have different parsing rules, so syntax should not be mixed.")


run_python_example("Quoting comparison", demonstrate_python_quoting)


# ============================================================================
# 4. VARIABLES
# ============================================================================

section("3. VARIABLES")

print(
    """
Bash variables are created by assignment:

    name="Atul"
    count=10

There must not be spaces around the assignment operator.

Correct:
    name="Atul"

Incorrect:
    name = "Atul"

Reading a variable normally uses $:

    echo "$name"

Braces make boundaries explicit:

    echo "${name}_report"

This is important when text immediately follows a variable name.

Bash variables are generally strings unless arithmetic context is requested.
"""
)


def demonstrate_variables() -> None:
    name = "Atul"
    count = 10

    print("name =", name)
    print("count =", count)
    print("combined =", f"{name}_report")
    print("Python also supports explicit numeric types:", count + 5)


run_python_example("Variables", demonstrate_variables)


# ============================================================================
# 5. ENVIRONMENT VARIABLES
# ============================================================================

section("4. ENVIRONMENT VARIABLES")

print(
    """
Environment variables are variables exported into the environment inherited
by child processes.

Typical examples:

    PATH
    HOME
    USER
    SHELL
    PWD

In Bash:

    export APP_MODE="production"

A child process can read APP_MODE.

A normal shell variable:

    APP_MODE="production"

is not automatically exported to child processes.

This distinction matters in scripts that launch programs.
"""
)


def demonstrate_environment_variables() -> None:
    print("PATH exists:", "PATH" in os.environ)
    print("HOME:", os.environ.get("HOME", "<not available>"))
    print("SHELL:", os.environ.get("SHELL", "<not available>"))

    child_environment = os.environ.copy()
    child_environment["DEMO_MODE"] = "production"

    result = subprocess.run(
        ["python", "-c", "import os; print(os.environ.get('DEMO_MODE'))"],
        env=child_environment,
        capture_output=True,
        text=True,
        check=True,
    )

    print("Child process received DEMO_MODE:", result.stdout.strip())


run_python_example("Environment variables", demonstrate_environment_variables)


# ============================================================================
# 6. SPECIAL PARAMETERS
# ============================================================================

section("5. SPECIAL PARAMETERS AND SCRIPT ARGUMENTS")

print(
    """
Bash provides special parameters:

    $0   script name
    $1   first positional argument
    $2   second positional argument
    $#   number of positional arguments
    $@   all positional arguments
    $?   previous command's exit status
    $$   current shell process ID
    $!   PID of the most recently started background process

A robust script should understand the difference between "$@" and "$*".

With:

    "$@"

each positional argument remains a separate argument.

With:

    "$*"

the positional arguments are generally combined into one word when quoted.

This distinction is important when arguments contain spaces.
"""
)


def demonstrate_arguments() -> None:
    simulated_arguments = ["backup.sh", "quarter one", "2026"]

    script_name = simulated_arguments[0]
    positional_arguments = simulated_arguments[1:]

    print("Equivalent $0:", script_name)
    print("Equivalent $#:", len(positional_arguments))
    print("Equivalent $1:", positional_arguments[0])
    print("Equivalent $2:", positional_arguments[1])

    print("\nArgument preservation:")
    for argument in positional_arguments:
        print(repr(argument))


run_python_example("Positional parameters", demonstrate_arguments)


# ============================================================================
# 7. COMMAND SUBSTITUTION
# ============================================================================

section("6. COMMAND SUBSTITUTION")

print(
    """
Command substitution allows command output to become part of another command:

    current_date=$(date)
    files=$(ls)

The modern form is $(...).

The older backtick form:

    current_date=`date`

exists but is harder to nest and is generally less readable.

Command substitution captures standard output. It does not automatically
capture standard error.

Python's subprocess.run() provides a comparable mechanism.
"""
)


def demonstrate_command_substitution() -> None:
    result = subprocess.run(
        ["python", "-c", "print('generated-value')"],
        capture_output=True,
        text=True,
        check=True,
    )

    generated_value = result.stdout.strip()
    print("Captured output:", generated_value)


run_python_example("Command substitution", demonstrate_command_substitution)


# ============================================================================
# 8. ARITHMETIC EXPANSION
# ============================================================================

section("7. ARITHMETIC EXPANSION")

print(
    """
Bash supports arithmetic expressions using:

    $(( expression ))

Examples:

    total=$((10 + 20))
    doubled=$((count * 2))
    remainder=$((17 % 5))

For integer arithmetic, Bash provides common operators such as:

    +  -  *  /  %  **
    <  <=  >  >=
    == !=
    && ||

Division of integers produces an integer result.

For example:

    $((7 / 2))

produces 3 rather than 3.5.
"""
)


def demonstrate_arithmetic() -> None:
    total = 10 + 20
    doubled = 7 * 2
    remainder = 17 % 5
    integer_division = 7 // 2

    print("total =", total)
    print("doubled =", doubled)
    print("remainder =", remainder)
    print("integer division =", integer_division)


run_python_example("Arithmetic", demonstrate_arithmetic)


# ============================================================================
# 9. EXIT STATUS
# ============================================================================

section("8. EXIT STATUS")

print(
    """
Every normally completed Unix process returns an exit status.

Convention:

    0      success
    nonzero failure or special condition

Bash stores the most recently completed command's status in:

    $?

Example:

    mkdir reports
    if [ $? -eq 0 ]; then
        echo "Directory created"
    fi

A more idiomatic approach is to place the command directly in the condition:

    if mkdir reports; then
        echo "Directory created"
    fi

This avoids unnecessary dependence on a separately inspected status.
"""
)


def demonstrate_exit_status() -> None:
    successful = subprocess.run(["python", "-c", "pass"])
    failed = subprocess.run(["python", "-c", "raise SystemExit(3)"])

    print("Successful process return code:", successful.returncode)
    print("Failed process return code:", failed.returncode)
    print("Zero means success:", successful.returncode == 0)
    print("Nonzero means failure:", failed.returncode != 0)


run_python_example("Exit status", demonstrate_exit_status)


# ============================================================================
# 10. CONDITIONS
# ============================================================================

section("9. CONDITIONS AND TESTING")

print(
    """
Bash commonly evaluates conditions with the test command:

    [ condition ]

The spaces around [ and ] are significant because [ is a command-like
construct in shell syntax.

Examples:

    [ "$name" = "Atul" ]
    [ "$count" -gt 10 ]
    [ -f "$file" ]
    [ -d "$directory" ]

String operators include:

    =   equality
    !=  inequality
    -z  empty string
    -n  non-empty string

Integer comparisons commonly use:

    -eq  equal
    -ne  not equal
    -lt  less than
    -le  less than or equal
    -gt  greater than
    -ge  greater than or equal

File tests include:

    -e path exists
    -f regular file
    -d directory
    -r readable
    -w writable
    -x executable
"""
)


def demonstrate_conditions() -> None:
    name = "Atul"
    count = 25

    print("String equality:", name == "Atul")
    print("Integer greater-than:", count > 10)

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "example.txt"
        path.write_text("hello", encoding="utf-8")

        print("Exists:", path.exists())
        print("Regular file:", path.is_file())
        print("Directory:", path.parent.is_dir())


run_python_example("Conditions", demonstrate_conditions)


# ============================================================================
# 11. IF / ELIF / ELSE
# ============================================================================

section("10. IF / ELIF / ELSE")

print(
    """
Bash conditional structure:

    if condition; then
        commands
    elif another_condition; then
        commands
    else
        commands
    fi

The condition is based on command exit status.

This means commands themselves can serve as conditions.

For example:

    if grep -q "ERROR" application.log; then
        echo "Errors found"
    fi
"""
)


def classify_score(score: int) -> str:
    if score >= 90:
        return "excellent"
    elif score >= 60:
        return "passing"
    else:
        return "needs improvement"


def demonstrate_if() -> None:
    for score in (95, 72, 40):
        print(score, "->", classify_score(score))


run_python_example("if/elif/else", demonstrate_if)


# ============================================================================
# 12. [[ ]] AND TEST
# ============================================================================

section("11. [ ] VERSUS [[ ]]")

print(
    """
Bash provides both [ ... ] and [[ ... ]].

[ ... ] is traditionally portable and behaves like the test command.

[[ ... ]] is a Bash conditional expression with additional capabilities.
It reduces several quoting and parsing hazards and supports features such
as pattern matching and regular-expression matching.

Examples:

    [[ "$name" == "A*" ]]
    [[ "$value" =~ ^[0-9]+$ ]]

For Bash-specific scripts, [[ ... ]] is often preferable for complex tests.

Do not confuse these constructs with Python's syntax. Shell parsing happens
before the command itself runs.
"""
)


def demonstrate_pattern_matching() -> None:
    names = ["Alice", "Atul", "Bob"]

    for name in names:
        # Equivalent conceptual behavior to a Bash [[ "$name" == A* ]] test.
        starts_with_a = name.startswith("A")
        print(f"{name:>5} -> starts with A: {starts_with_a}")


run_python_example("Pattern matching", demonstrate_pattern_matching)


# ============================================================================
# 13. CASE
# ============================================================================

section("12. CASE STATEMENTS")

print(
    """
Bash case syntax:

    case "$value" in
        start)
            ...
            ;;
        stop)
            ...
            ;;
        *)
            ...
            ;;
    esac

case is useful when one value needs to be compared against multiple
patterns.

It is often clearer than a long chain of if/elif statements.

The ;; terminates a case branch.
"""
)


def interpret_action(action: str) -> str:
    match action:
        case "start":
            return "starting service"
        case "stop":
            return "stopping service"
        case "status":
            return "checking service"
        case _:
            return "unknown command"


def demonstrate_case() -> None:
    for action in ("start", "status", "restart"):
        print(action, "->", interpret_action(action))


run_python_example("case-style dispatch", demonstrate_case)


# ============================================================================
# 14. FOR LOOPS
# ============================================================================

section("13. FOR LOOPS")

print(
    """
The basic Bash form is:

    for item in one two three; do
        echo "$item"
    done

A safer and more general pattern for filenames is:

    for file in "$directory"/*; do
        ...
    done

When iterating over arbitrary command-line arguments, use:

    for argument in "$@"; do
        ...
    done

Bash also supports C-style loops:

    for ((i=0; i<10; i++)); do
        ...
    done
"""
)


def demonstrate_for_loops() -> None:
    languages = ["Bash", "Python", "JavaScript", "C++"]

    for index, language in enumerate(languages):
        print(index, language)

    print("\nC-style loop equivalent:")
    for index in range(5):
        print("i =", index)


run_python_example("for loops", demonstrate_for_loops)


# ============================================================================
# 15. WHILE LOOPS
# ============================================================================

section("14. WHILE LOOPS")

print(
    """
Bash:

    counter=0

    while (( counter < 5 )); do
        echo "$counter"
        ((counter++))
    done

while is appropriate when repetition depends on a condition.

A very important shell pattern is reading a file line by line:

    while IFS= read -r line; do
        printf '%s\\n' "$line"
    done < "$file"

IFS= prevents leading/trailing whitespace from being discarded by the
read operation, while -r prevents backslash interpretation.
"""
)


def demonstrate_while_loop() -> None:
    counter = 0

    while counter < 5:
        print("counter =", counter)
        counter += 1


run_python_example("while loop", demonstrate_while_loop)


# ============================================================================
# 16. UNTIL LOOPS
# ============================================================================

section("15. UNTIL LOOPS")

print(
    """
until repeats commands while its condition is false.

Bash:

    until ping -c 1 server.example.com; do
        sleep 1
    done

Conceptually:

    while NOT condition:
        repeat

This can be useful for retry logic and waiting for a condition.
"""
)


def demonstrate_until_concept() -> None:
    attempt = 0

    # Simulate an external condition that becomes true after three attempts.
    while not (attempt >= 3):
        attempt += 1
        print("attempt:", attempt)

    print("Condition is now true.")


run_python_example("until concept", demonstrate_until_concept)


# ============================================================================
# 17. BREAK AND CONTINUE
# ============================================================================

section("16. BREAK AND CONTINUE")

print(
    """
break exits the nearest loop.

continue skips the remaining commands in the current iteration and starts
the next iteration.

Example:

    for number in {1..10}; do
        if (( number == 5 )); then
            continue
        fi

        if (( number == 8 )); then
            break
        fi

        echo "$number"
    done
"""
)


def demonstrate_loop_control() -> None:
    for number in range(1, 11):
        if number == 5:
            continue

        if number == 8:
            break

        print(number)


run_python_example("break and continue", demonstrate_loop_control)


# ============================================================================
# 18. FUNCTIONS
# ============================================================================

section("17. FUNCTIONS")

print(
    """
Bash functions:

    greet() {
        local name="$1"
        printf 'Hello, %s\\n' "$name"
    }

    greet "Atul"

Functions receive positional parameters just like scripts.

Use local variables whenever a variable should not modify the caller's
shell variable.

A Bash function's return status is numeric. It is not the same concept as
returning an arbitrary string.

    return 0

returns success.

Output intended as data can be written to stdout and captured with:

    result=$(function_name)
"""
)


def greet(name: str) -> None:
    print(f"Hello, {name}")


def demonstrate_functions() -> None:
    greet("Atul")

    def validate_positive(value: int) -> bool:
        return value > 0

    for value in (10, 0, -3):
        print(value, "valid:", validate_positive(value))


run_python_example("Functions", demonstrate_functions)


# ============================================================================
# 19. ARRAYS
# ============================================================================

section("18. ARRAYS")

print(
    """
Indexed Bash array:

    languages=("Bash" "Python" "JavaScript")

Access:

    echo "${languages[0]}"

Number of elements:

    echo "${#languages[@]}"

All elements:

    printf '%s\\n' "${languages[@]}"

Associative array:

    declare -A ports
    ports[http]=80
    ports[https]=443

Associative arrays require Bash rather than a minimal POSIX shell.
"""
)


def demonstrate_arrays() -> None:
    languages = ["Bash", "Python", "JavaScript"]
    print("First element:", languages[0])
    print("Number of elements:", len(languages))

    ports = {"http": 80, "https": 443}
    print("HTTPS port:", ports["https"])

    for language in languages:
        print("language:", language)


run_python_example("Arrays", demonstrate_arrays)


# ============================================================================
# 20. PARAMETER EXPANSION
# ============================================================================

section("19. PARAMETER EXPANSION")

print(
    """
Parameter expansion is one of Bash's most powerful features.

Examples:

    ${name:-default}
        use default if name is unset or empty

    ${name:=default}
        assign default if unset or empty

    ${name:?message}
        produce an error if unset or empty

    ${name:+alternate}
        use alternate if name is set and non-empty

String operations include:

    ${#name}
    ${name:0:5}
    ${name#pattern}
    ${name##pattern}
    ${name%pattern}
    ${name%%pattern}

These operations often avoid starting external commands, which can improve
performance and make scripts more self-contained.
"""
)


def demonstrate_parameter_expansion() -> None:
    name = ""

    default_name = name or "Guest"
    print("Default value:", default_name)

    path = "/var/log/application.log"
    basename = path.rsplit("/", 1)[-1]
    suffix_removed = basename.rsplit(".", 1)[0]

    print("Path:", path)
    print("Filename:", basename)
    print("Filename without extension:", suffix_removed)


run_python_example("Parameter expansion concepts", demonstrate_parameter_expansion)


# ============================================================================
# 21. GLOBBING
# ============================================================================

section("20. PATHNAME EXPANSION / GLOBBING")

print(
    """
Bash globbing expands patterns against filenames.

Common patterns:

    *       zero or more characters
    ?       exactly one character
    [abc]   one character from the set
    [0-9]   one character from the range

Example:

    for file in *.txt; do
        ...
    done

Important distinction:

Globbing is not the same as regular expressions.

The shell pattern *.txt is a pathname pattern. It is not a complete
regular expression.

If no pathname matches a glob, Bash's default behavior can leave the
pattern unchanged. Options such as nullglob change that behavior.
"""
)


def demonstrate_globbing_concept() -> None:
    names = ["report.txt", "notes.txt", "image.png", "data.csv"]

    txt_files = [name for name in names if name.endswith(".txt")]
    print("Matching *.txt:", txt_files)

    one_character_pattern = re.compile(r"^file.$")
    candidates = ["file1", "fileA", "file12"]
    print(
        "Conceptual ? pattern:",
        [name for name in candidates if one_character_pattern.match(name)],
    )


run_python_example("Globbing", demonstrate_globbing_concept)


# ============================================================================
# 22. REDIRECTION
# ============================================================================

section("21. INPUT AND OUTPUT REDIRECTION")

print(
    """
Shell file descriptors traditionally include:

    0   standard input
    1   standard output
    2   standard error

Common redirections:

    command > file
        replace stdout

    command >> file
        append stdout

    command 2> file
        replace stderr

    command 2>&1
        redirect stderr to the same destination as stdout

    command < file
        read stdin from a file

Modern Bash also supports:

    command &> file

for stdout and stderr together.

Redirection order matters. For example:

    command >file 2>&1

sends both streams to file.

Pipelines connect stdout of one command to stdin of another:

    command1 | command2
"""
)


def demonstrate_redirection() -> None:
    completed = subprocess.run(
        [
            "python",
            "-c",
            "print('standard output'); print('standard error', file=__import__('sys').stderr)",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    print("Captured stdout:", completed.stdout.strip())
    print("Captured stderr:", completed.stderr.strip())


run_python_example("Redirection", demonstrate_redirection)


# ============================================================================
# 23. PIPELINES
# ============================================================================

section("22. PIPELINES")

print(
    """
A pipeline:

    producer | consumer

connects the producer's stdout to the consumer's stdin.

Example:

    printf '%s\\n' *.log | grep ERROR

Pipelines are central to shell scripting because Unix programs often follow
the principle of doing one focused task and composing tools together.

Bash's PIPESTATUS array can inspect the exit status of individual commands
in the most recent pipeline:

    command1 | command2
    echo "${PIPESTATUS[@]}"

Without special handling, a pipeline's overall status can hide an earlier
failure depending on shell options and pipeline structure.
"""
)


def demonstrate_pipeline_with_python() -> None:
    producer = subprocess.Popen(
        ["python", "-c", "print('alpha'); print('beta'); print('gamma')"],
        stdout=subprocess.PIPE,
        text=True,
    )

    assert producer.stdout is not None

    consumer = subprocess.run(
        ["python", "-c", "import sys; print(sum(1 for _ in sys.stdin))"],
        stdin=producer.stdout,
        capture_output=True,
        text=True,
        check=True,
    )

    producer.stdout.close()
    producer.wait()

    print("Lines consumed:", consumer.stdout.strip())
    print("Producer return code:", producer.returncode)
    print("Consumer return code:", consumer.returncode)


run_python_example("Pipeline", demonstrate_pipeline_with_python)


# ============================================================================
# 24. COMMAND SEARCH AND PATH
# ============================================================================

section("23. PATH AND COMMAND SEARCH")

print(
    """
When Bash receives a command such as:

    python

it searches directories listed in PATH to locate an executable.

Inspect PATH:

    echo "$PATH"

Find a command:

    command -v python

The order of PATH entries matters. The first matching executable is normally
selected.

Security implication:

Putting the current directory or an untrusted directory early in PATH can
cause an unintended executable to run.
"""
)


def demonstrate_path() -> None:
    path_entries = os.environ.get("PATH", "").split(os.pathsep)

    print("Number of PATH entries:", len(path_entries))
    print("First five PATH entries:")
    for entry in path_entries[:5]:
        print(" ", entry)

    print("Python executable:", shutil.which("python"))


run_python_example("PATH", demonstrate_path)


# ============================================================================
# 25. SET -E, -U, PIPEFAIL
# ============================================================================

section("24. DEFENSIVE BASH OPTIONS")

print(
    """
Three frequently discussed Bash options are:

    set -e
        exit in many circumstances when a command returns nonzero

    set -u
        treat unset variables as errors

    set -o pipefail
        make a pipeline fail when an appropriate component fails

A common script header is:

    set -euo pipefail

This is useful but not magic.

-e has nuanced exceptions, including commands used in conditional contexts,
some compound commands, and pipelines. Scripts still require careful error
handling.

-u can require deliberate handling of optional variables.

pipefail changes pipeline status semantics and can expose failures that would
otherwise be hidden.

Use these options because their semantics are understood, not simply because
they are a standard-looking line.
"""
)


def demonstrate_defensive_python() -> None:
    values = {"required": "present"}

    required = values.get("required")
    if required is None:
        raise RuntimeError("Required value is missing")

    optional = values.get("optional", "safe-default")

    print("Required:", required)
    print("Optional:", optional)


run_python_example("Defensive programming analogue", demonstrate_defensive_python)


# ============================================================================
# 26. ERROR HANDLING
# ============================================================================

section("25. ERROR HANDLING")

print(
    """
A robust Bash script should decide which failures are expected and which
must terminate execution.

Useful patterns include:

    if ! command; then
        printf 'operation failed\\n' >&2
        exit 1
    fi

Functions can return meaningful status codes:

    return 0
    return 1
    return 2

Error messages should normally go to stderr:

    printf 'Invalid input\\n' >&2

A script should avoid silently ignoring commands that can corrupt data,
delete files, modify infrastructure, or produce invalid output.
"""
)


def demonstrate_error_handling() -> None:
    result = subprocess.run(
        ["python", "-c", "raise SystemExit(7)"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("Handled failure with status:", result.returncode)
    else:
        print("Command succeeded.")


run_python_example("Error handling", demonstrate_error_handling)


# ============================================================================
# 27. FILE PROCESSING
# ============================================================================

section("26. FILE PROCESSING")

print(
    """
A classic Bash file-processing loop is:

    while IFS= read -r line; do
        printf '%s\\n' "$line"
    done < input.txt

Important details:

    IFS=
        prevents read from trimming whitespace in the normal way

    -r
        prevents backslash escaping

    < input.txt
        supplies the file through stdin

This is preferable to:

    for line in $(cat input.txt)

because command substitution and word splitting can destroy whitespace and
line boundaries.
"""
)


def demonstrate_file_processing() -> None:
    content = "first line\nline with spaces\nbackslash: \\n"

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        delete=False,
    ) as temporary_file:
        temporary_file.write(content)
        file_name = temporary_file.name

    try:
        with open(file_name, encoding="utf-8") as handle:
            for line in handle:
                print(repr(line.rstrip("\n")))
    finally:
        Path(file_name).unlink(missing_ok=True)


run_python_example("Safe line-oriented file processing", demonstrate_file_processing)


# ============================================================================
# 28. READ
# ============================================================================

section("27. READ AND INPUT VALIDATION")

print(
    """
Bash's read builtin obtains input.

Example:

    read -r username

With a prompt:

    read -r -p "Username: " username

For sensitive input:

    read -r -s password

Input should be validated before being used in commands.

Never assume user input is safe merely because it came from a trusted-looking
terminal.
"""
)


def validate_username(username: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z0-9_]{3,32}", username))


def demonstrate_input_validation() -> None:
    candidates = ["atul_123", "bad name", "a", "admin!", "valid_user"]

    for username in candidates:
        print(username, "->", validate_username(username))


run_python_example("Input validation", demonstrate_input_validation)


# ============================================================================
# 29. COMMAND INJECTION
# ============================================================================

section("28. SECURITY: COMMAND INJECTION")

print(
    """
One of the most important shell security risks is command injection.

Dangerous pattern:

    user_input="..."
    bash -c "grep '$user_input' file.txt"

The input can alter shell syntax if it is inserted into a command string.

A safer principle is:

    * avoid invoking a shell when it is unnecessary
    * pass arguments as separate arguments
    * quote shell variables correctly
    * validate inputs according to the application's requirements
    * never assume shell escaping alone solves every security problem

In Python, subprocess.run([...], shell=False) passes arguments separately.

This is safer than constructing a command string and asking a shell to parse it.
"""
)


def demonstrate_safe_subprocess() -> None:
    user_value = "value with spaces; echo SHOULD_NOT_RUN"

    safe = subprocess.run(
        ["python", "-c", "import sys; print(sys.argv[1])", user_value],
        capture_output=True,
        text=True,
        check=True,
    )

    print("User value passed as one argument:")
    print(safe.stdout.strip())


run_python_example("Safe argument passing", demonstrate_safe_subprocess)


# ============================================================================
# 30. COMMAND INJECTION CONCEPTUAL TEST
# ============================================================================

section("29. WHY ARGUMENT ARRAYS MATTER")

print(
    """
Suppose an application wants to run:

    grep PATTERN FILE

If PATTERN is treated as shell source, characters such as:

    ;
    &
    |
    >
    <

may acquire shell meaning.

If the program instead invokes an executable with a structured argument list,
the input remains an argument rather than becoming shell syntax.

This distinction applies across Python, JavaScript, C++, web applications,
CI/CD systems, deployment scripts, and automation platforms.
"""
)


def demonstrate_argument_boundary() -> None:
    values = [
        "normal",
        "hello world",
        "semi;colon",
        "$(echo unexpected)",
    ]

    for value in values:
        result = subprocess.run(
            ["python", "-c", "import sys; print(sys.argv[1])", value],
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"Input preserved: {result.stdout.strip()!r}")


run_python_example("Argument boundaries", demonstrate_argument_boundary)


# ============================================================================
# 31. FUNCTIONS WITH VALIDATION
# ============================================================================

section("30. ADVANCED FUNCTIONS AND VALIDATION")

print(
    """
A production-oriented Bash function often validates arguments explicitly.

Conceptual pattern:

    require_file() {
        local file="$1"

        if [[ ! -f "$file" ]]; then
            printf 'File does not exist: %s\\n' "$file" >&2
            return 1
        fi
    }

Callers can then write:

    require_file "$config" || exit 1

This creates a clean separation between validation and the main workflow.
"""
)


def require_file(path: Path) -> None:
    if not path.is_file():
        raise FileNotFoundError(f"File does not exist: {path}")


def demonstrate_validation_function() -> None:
    with tempfile.TemporaryDirectory() as directory:
        existing = Path(directory) / "config.txt"
        existing.write_text("configuration", encoding="utf-8")

        require_file(existing)
        print("Existing file accepted.")

        try:
            require_file(Path(directory) / "missing.txt")
        except FileNotFoundError as exc:
            print("Expected validation error:", exc)


run_python_example("Validation function", demonstrate_validation_function)


# ============================================================================
# 32. SCRIPT ARGUMENT PARSING
# ============================================================================

section("31. ARGUMENT PARSING")

print(
    """
Simple Bash scripts often inspect "$1", "$2", and "$@".

For more complex interfaces, Bash provides getopts for short options.

Example concept:

    while getopts ":f:v" option; do
        case "$option" in
            f) file="$OPTARG" ;;
            v) verbose=true ;;
            *) exit 2 ;;
        esac
    done

For a production script with a large CLI interface, careful validation,
usage output, predictable exit codes, and explicit defaults become important.
"""
)


def demonstrate_argument_parsing() -> None:
    import argparse

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("-f", "--file")
    parser.add_argument("-v", "--verbose", action="store_true")

    arguments = parser.parse_args(["-f", "data.csv", "-v"])

    print("Parsed file:", arguments.file)
    print("Verbose:", arguments.verbose)


run_python_example("Argument parsing analogue", demonstrate_argument_parsing)


# ============================================================================
# 33. TEMPORARY FILES
# ============================================================================

section("32. TEMPORARY FILES AND SECURITY")

print(
    """
Temporary files should not be created using predictable filenames such as:

    /tmp/my-script-output

An attacker may create a symbolic link with that name before the script runs.

Use secure temporary-file mechanisms.

In Bash, mktemp is commonly used:

    temporary_file=$(mktemp)

and the file should be cleaned up appropriately.

Python's tempfile module provides secure temporary-file primitives.
"""
)


def demonstrate_secure_temporary_file() -> None:
    with tempfile.NamedTemporaryFile(
        mode="w+",
        encoding="utf-8",
        delete=True,
    ) as temporary_file:
        temporary_file.write("temporary data")
        temporary_file.flush()
        print("Secure temporary path:", temporary_file.name)
        print("Contents:", Path(temporary_file.name).read_text(encoding="utf-8"))


run_python_example("Secure temporary file", demonstrate_secure_temporary_file)


# ============================================================================
# 34. TRAPS AND CLEANUP
# ============================================================================

section("33. TRAP AND CLEANUP")

print(
    """
Bash's trap mechanism can execute commands when signals or shell events occur.

A common cleanup pattern is conceptually:

    temporary_file=$(mktemp)

    cleanup() {
        rm -f -- "$temporary_file"
    }

    trap cleanup EXIT

This allows cleanup even when the script exits through many paths.

Signals such as INT and TERM can also be handled deliberately.

Cleanup should be idempotent: running it more than once should not cause
additional damage.
"""
)


def demonstrate_cleanup_pattern() -> None:
    temporary_directory = Path(tempfile.mkdtemp())
    temporary_file = temporary_directory / "state.txt"
    temporary_file.write_text("temporary state", encoding="utf-8")

    try:
        print("Created:", temporary_file.exists())
    finally:
        temporary_file.unlink(missing_ok=True)
        temporary_directory.rmdir()

    print("Cleaned up:", not temporary_directory.exists())


run_python_example("Cleanup concept", demonstrate_cleanup_pattern)


# ============================================================================
# 35. DEBUGGING
# ============================================================================

section("34. DEBUGGING BASH")

print(
    """
Useful Bash debugging techniques include:

    bash -n script.sh
        syntax checking without execution

    bash -x script.sh
        trace commands as they execute

    set -x
        enable tracing during a script

    set +x
        disable tracing

    printf '%s\\n' "$variable"
        controlled diagnostic output

The PS4 variable controls the prefix used by xtrace.

Be careful with tracing secrets. A command containing a password, token, or
private key may become visible in logs when xtrace is enabled.
"""
)


def demonstrate_python_debugging() -> None:
    values = [2, 4, 6]
    total = sum(values)

    print("values =", values)
    print("total =", total)
    print("average =", total / len(values))


run_python_example("Debugging with explicit diagnostics", demonstrate_python_debugging)


# ============================================================================
# 36. SHELLCHECK CONCEPT
# ============================================================================

section("35. STATIC ANALYSIS CONCEPT")

print(
    """
Shell scripts have many subtle parsing rules, so static analysis is valuable.

ShellCheck is a widely used Bash/sh static-analysis tool.

Typical findings can include:

    * unsafe quoting
    * incorrect test syntax
    * unused variables
    * suspicious word splitting
    * portability problems
    * accidental glob expansion
    * common shell programming mistakes

Static analysis does not prove a script is correct. It is one layer of
quality control alongside tests and runtime validation.
"""
)


# ============================================================================
# 37. PERFORMANCE
# ============================================================================

section("36. PERFORMANCE CONSIDERATIONS")

print(
    """
Shell is excellent at orchestration and composition but is not universally
efficient for CPU-heavy data processing.

A loop that starts an external process once per item can be expensive:

    for file in *; do
        grep ...
    done

Repeated process creation can dominate runtime.

Prefer:

    * Bash builtins where appropriate
    * parameter expansion
    * one pipeline instead of thousands of processes
    * awk/sed/grep for suitable text-processing tasks
    * Python/C++ for complex computation or large data processing

Do not optimize blindly. Measure first.

The shell is often the orchestration layer while specialized languages handle
algorithmically expensive work.
"""
)


def demonstrate_process_overhead() -> None:
    import time

    iterations = 100

    start = time.perf_counter()
    total = sum(range(iterations))
    in_process_time = time.perf_counter() - start

    start = time.perf_counter()
    for _ in range(iterations):
        subprocess.run(
            ["python", "-c", "pass"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    process_creation_time = time.perf_counter() - start

    print("In-process computation result:", total)
    print(f"In-process time: {in_process_time:.6f}s")
    print(f"Launching {iterations} child processes: {process_creation_time:.6f}s")
    print("Exact timings depend on the machine.")


run_python_example("Process overhead", demonstrate_process_overhead)


# ============================================================================
# 38. PORTABILITY
# ============================================================================

section("37. BASH VERSUS POSIX SH")

print(
    """
Bash is not identical to sh.

Bash-specific features include:

    [[ ... ]]
    arrays
    associative arrays
    process substitution
    brace expansion
    Bash-specific parameter expansion
    many shell options and builtins

If a script starts with:

    #!/usr/bin/env bash

it explicitly requests Bash through env.

A script intended for POSIX sh should avoid Bash-only syntax.

Portability should be an explicit engineering requirement rather than an
accidental property.
"""
)


# ============================================================================
# 39. SHEBANG
# ============================================================================

section("38. SHEBANG")

print(
    """
The first line of an executable shell script commonly specifies its interpreter:

    #!/usr/bin/env bash

or:

    #!/bin/bash

After making a script executable:

    chmod +x script.sh

it can be run as:

    ./script.sh

The shebang matters because a script may behave differently under different
shell interpreters.
"""
)


# ============================================================================
# 40. BRACE EXPANSION
# ============================================================================

section("39. BRACE EXPANSION")

print(
    """
Bash brace expansion generates text before command execution.

Examples:

    echo file{1,2,3}.txt

produces:

    file1.txt file2.txt file3.txt

Ranges are also supported:

    echo {1..5}

and with increments:

    echo {0..10..2}

Brace expansion is shell syntax and should not be confused with pathname
globbing.
"""
)


def demonstrate_brace_expansion_concept() -> None:
    generated = [f"file{number}.txt" for number in range(1, 4)]
    print(generated)

    even_numbers = list(range(0, 11, 2))
    print(even_numbers)


run_python_example("Brace expansion", demonstrate_brace_expansion_concept)


# ============================================================================
# 41. HERE DOCUMENTS
# ============================================================================

section("40. HERE DOCUMENTS")

print(
    """
A here document supplies multiple lines of input:

    cat <<EOF
    first line
    second line
    EOF

If the delimiter is quoted:

    cat <<'EOF'
    $HOME
    EOF

variable expansion is suppressed inside the document.

Here documents are useful for configuration generation, SQL input, messages,
and multi-line commands.
"""
)


def demonstrate_here_document_concept() -> None:
    multiline_text = """first line
second line
third line"""
    print(multiline_text)


run_python_example("Here-document concept", demonstrate_here_document_concept)


# ============================================================================
# 42. COMMAND GROUPING
# ============================================================================

section("41. COMMAND GROUPING")

print(
    """
Bash has grouping constructs.

Parentheses:

    ( command1; command2 )

run commands in a subshell environment.

Braces:

    { command1; command2; }

group commands in the current shell context, with syntax requirements such
as the terminating semicolon.

This distinction matters when modifying variables:

    (count=10)
    echo "$count"

does not normally preserve the assignment in the parent shell.

By contrast, a brace group operates in the current shell.
"""
)


# ============================================================================
# 43. SUBSHELLS
# ============================================================================

section("42. SUBSHELL BEHAVIOR")

print(
    """
A subshell is a child shell environment.

Common causes include:

    ( ... )
    command substitution $(...)
    pipelines, depending on shell execution behavior

Changes to shell variables inside a subshell normally do not modify the
parent shell's variables.

This can surprise beginners when a loop is placed on the right side of
a pipeline.

An input-redirection form can avoid some such problems:

    while read -r line; do
        ...
    done < file
"""
)


def demonstrate_process_isolation() -> None:
    parent_value = "parent"
    child_value = parent_value

    child_value = "child"
    print("Parent conceptual value:", parent_value)
    print("Child conceptual value:", child_value)


run_python_example("Subshell isolation concept", demonstrate_process_isolation)


# ============================================================================
# 44. REAL-WORLD CASE STUDY
# ============================================================================

section("43. REAL-WORLD CASE STUDY: LOG AUDIT")

print(
    """
Consider a deployment server containing application logs.

A Bash script may need to:

    1. verify that the log directory exists
    2. inspect log files
    3. count error records
    4. detect warnings
    5. generate a report
    6. return a meaningful status code

Shell is well suited because it can combine filesystem operations and
specialized text-processing commands.

The script should still validate paths, handle missing files, avoid unsafe
command construction, and produce deterministic output.
"""
)


def log_audit(log_contents: dict[str, str]) -> dict[str, int]:
    statistics = {
        "files": len(log_contents),
        "errors": 0,
        "warnings": 0,
        "lines": 0,
    }

    for content in log_contents.values():
        lines = content.splitlines()
        statistics["lines"] += len(lines)
        statistics["errors"] += sum(
            1 for line in lines if "ERROR" in line
        )
        statistics["warnings"] += sum(
            1 for line in lines if "WARNING" in line
        )

    return statistics


def demonstrate_log_audit() -> None:
    logs = {
        "application.log": (
            "INFO startup\n"
            "WARNING slow response\n"
            "ERROR database unavailable\n"
            "INFO retry\n"
        ),
        "worker.log": (
            "INFO worker started\n"
            "ERROR timeout\n"
        ),
    }

    statistics = log_audit(logs)

    for key, value in statistics.items():
        print(f"{key}: {value}")


run_python_example("Log audit", demonstrate_log_audit)


# ============================================================================
# 45. RETRY LOGIC
# ============================================================================

section("44. RETRY LOGIC")

print(
    """
Retry loops are common in shell automation.

Conceptual Bash:

    attempts=0

    until command; do
        ((attempts++))

        if (( attempts >= 5 )); then
            printf 'operation failed\\n' >&2
            exit 1
        fi

        sleep 2
    done

Production retry logic should consider:

    * maximum attempts
    * timeout
    * exponential backoff
    * jitter
    * whether the operation is idempotent
    * which failures are retryable
"""
)


def retry_operation(max_attempts: int) -> bool:
    for attempt in range(1, max_attempts + 1):
        print("Attempt", attempt)

        # Simulated operation succeeds on attempt three.
        if attempt >= 3:
            return True

    return False


def demonstrate_retry() -> None:
    success = retry_operation(5)
    print("Final result:", success)


run_python_example("Retry logic", demonstrate_retry)


# ============================================================================
# 46. IDEMPOTENCY
# ============================================================================

section("45. IDEMPOTENCY")

print(
    """
An operation is idempotent if performing it repeatedly produces the same
intended final state.

Example:

    mkdir -p /some/directory

is designed to succeed even when the directory already exists.

A deployment script should prefer state-oriented operations where practical.

Non-idempotent actions can create duplicates, overwrite data, or produce
unexpected results when a script is retried.
"""
)


def demonstrate_idempotent_operation() -> None:
    state = set()

    def ensure_item(item: str) -> None:
        state.add(item)

    ensure_item("deployment")
    ensure_item("deployment")

    print("State after two identical operations:", state)


run_python_example("Idempotency", demonstrate_idempotent_operation)


# ============================================================================
# 47. SAFE PATH HANDLING
# ============================================================================

section("46. SAFE PATH HANDLING")

print(
    """
When passing a pathname to a command, quote it:

    rm -- "$file"

The -- signals that following arguments should not be interpreted as options
by programs that support it.

Without quoting, spaces and shell metacharacters can alter argument parsing.

Without --, a filename beginning with a hyphen may be interpreted as an option.

Example:

    rm -- "$directory/$filename"

is safer than constructing unquoted shell syntax.
"""
)


def demonstrate_safe_path_handling() -> None:
    unsafe_name = "-important file.txt"
    safe_argument = "--"
    print("Filename:", unsafe_name)
    print("Option terminator:", safe_argument)
    print("Concept: pass path as a separate argument and terminate options.")


run_python_example("Safe path handling", demonstrate_safe_path_handling)


# ============================================================================
# 48. ENVIRONMENT AND SECRETS
# ============================================================================

section("47. ENVIRONMENT VARIABLES AND SECRETS")

print(
    """
Environment variables are often used to supply configuration:

    export DATABASE_HOST="db.internal"
    export DATABASE_PORT="5432"

They are not automatically secure secret storage.

Environment variables can become visible through process inspection, crash
reports, debugging, child processes, logs, or accidental printing.

Never do:

    echo "$DATABASE_PASSWORD"

in normal diagnostic output.

Use appropriate secret-management systems in production environments and
limit credentials to the smallest necessary scope.
"""
)


def demonstrate_configuration() -> None:
    configuration = {
        "DATABASE_HOST": os.environ.get("DATABASE_HOST", "localhost"),
        "DATABASE_PORT": os.environ.get("DATABASE_PORT", "5432"),
    }

    for key, value in configuration.items():
        print(f"{key}={value}")


run_python_example("Configuration", demonstrate_configuration)


# ============================================================================
# 49. PROCESS CONTROL
# ============================================================================

section("48. PROCESSES AND BACKGROUND COMMANDS")

print(
    """
Bash can run commands in the background:

    long_task &

The shell can wait for it:

    wait

The PID can be stored:

    long_task &
    pid=$!

    wait "$pid"

Background jobs are useful for concurrency but create additional concerns:

    * output interleaving
    * exit-status collection
    * resource usage
    * race conditions
    * cleanup
    * signal handling
"""
)


def demonstrate_background_process() -> None:
    process = subprocess.Popen(
        ["python", "-c", "print('background task complete')"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    stdout, stderr = process.communicate()

    print("Process ID:", process.pid)
    print("Return code:", process.returncode)
    print("Output:", stdout.strip())
    print("Error:", stderr.strip())


run_python_example("Background process concept", demonstrate_background_process)


# ============================================================================
# 50. CONCURRENCY TRADE-OFF
# ============================================================================

section("49. CONCURRENCY TRADE-OFFS")

print(
    """
Running independent tasks concurrently can reduce wall-clock time when tasks
wait on I/O.

It can also increase:

    * CPU consumption
    * memory usage
    * output complexity
    * failure-handling complexity
    * contention

Bash is capable of lightweight background concurrency, but large-scale
parallel workloads often benefit from specialized systems or languages.
"""
)


# ============================================================================
# 51. COMPLETE MINI SHELL SCRIPT MODEL
# ============================================================================

section("50. COMPLETE MINI SHELL SCRIPT MODEL")

print(
    """
A practical Bash script often follows this architecture:

    1. interpreter declaration
    2. strict/defensive shell options where appropriate
    3. constants and configuration
    4. helper functions
    5. argument parsing
    6. validation
    7. main workflow
    8. cleanup
    9. explicit exit status

Conceptual structure:

    #!/usr/bin/env bash
    set -euo pipefail

    usage() {
        ...
    }

    validate() {
        ...
    }

    main() {
        ...
    }

    main "$@"

The exact structure should match the complexity of the script.
"""
)


# ============================================================================
# 52. MINI APPLICATION IMPLEMENTATION
# ============================================================================

section("51. MINI APPLICATION: DEPLOYMENT VALIDATOR")

print(
    """
The following Python implementation models a Bash-style deployment validator.

It demonstrates:

    * configuration
    * validation
    * conditions
    * loops
    * functions
    * structured status reporting
    * deterministic output
"""
)


class DeploymentValidator:
    """Validate a simplified deployment configuration."""

    REQUIRED_KEYS = ("application", "version", "environment")

    def __init__(self, configuration: dict[str, str]):
        self.configuration = configuration
        self.errors: list[str] = []

    def validate_required_fields(self) -> None:
        for key in self.REQUIRED_KEYS:
            if not self.configuration.get(key):
                self.errors.append(f"Missing required field: {key}")

    def validate_environment(self) -> None:
        allowed = {"development", "staging", "production"}
        environment = self.configuration.get("environment")

        if environment not in allowed:
            self.errors.append(
                f"Invalid environment: {environment!r}"
            )

    def validate_version(self) -> None:
        version = self.configuration.get("version", "")

        if not re.fullmatch(r"\d+\.\d+\.\d+", version):
            self.errors.append(
                f"Version must use semantic numeric form: {version!r}"
            )

    def validate(self) -> bool:
        self.errors.clear()

        self.validate_required_fields()
        self.validate_environment()
        self.validate_version()

        return not self.errors

    def report(self) -> None:
        if self.validate():
            print("Deployment configuration is valid.")
        else:
            print("Deployment configuration is invalid.")
            for error in self.errors:
                print("ERROR:", error)


def demonstrate_deployment_validator() -> None:
    valid_configuration = {
        "application": "market-api",
        "version": "2.4.1",
        "environment": "production",
    }

    invalid_configuration = {
        "application": "",
        "version": "2",
        "environment": "unknown",
    }

    print("Valid configuration:")
    DeploymentValidator(valid_configuration).report()

    print("\nInvalid configuration:")
    DeploymentValidator(invalid_configuration).report()


run_python_example("Deployment validator", demonstrate_deployment_validator)


# ============================================================================
# 53. BASH EXECUTION IF AVAILABLE
# ============================================================================

section("52. OPTIONAL REAL BASH EXECUTION")

print(
    """
If Bash is installed, the following safe demonstration executes a small
script through Bash itself.

The example intentionally avoids destructive commands and external input.
"""
)


def demonstrate_real_bash() -> None:
    bash = shutil.which("bash")

    if bash is None:
        print("Bash executable was not found. Skipping direct Bash execution.")
        return

    script = r'''
name="Bash learner"
count=3

if (( count > 0 )); then
    printf 'Hello, %s\n' "$name"
fi

for ((i=1; i<=count; i++)); do
    printf 'iteration=%d\n' "$i"
done
'''

    result = subprocess.run(
        [bash, "-c", script],
        capture_output=True,
        text=True,
        check=True,
    )

    print(result.stdout.rstrip())
    if result.stderr:
        print("stderr:", result.stderr.rstrip())


run_python_example("Direct Bash demonstration", demonstrate_real_bash)


# ============================================================================
# 54. COMMON MISTAKES
# ============================================================================

section("53. COMMON BASH MISTAKES")

mistakes = [
    (
        "Spaces around assignments",
        'name = "Atul"',
        'name="Atul"',
    ),
    (
        "Unquoted variables",
        "rm $file",
        'rm -- "$file"',
    ),
    (
        "Using command substitution for file iteration",
        "for line in $(cat file)",
        'while IFS= read -r line; do ...; done < file',
    ),
    (
        "Confusing strings and numbers",
        '[ "$a" > "$b" ]',
        '(( a > b ))',
    ),
    (
        "Assuming nonzero always means one specific error",
        "if ! command; then ...",
        "inspect and handle status according to the command's contract",
    ),
    (
        "Building shell commands from untrusted strings",
        'bash -c "tool $input"',
        "pass arguments separately whenever possible",
    ),
]

for mistake, bad, better in mistakes:
    print(f"\n{mistake}")
    print("  Risky/incorrect:", bad)
    print("  Better:", better)


# ============================================================================
# 55. COMPARISON WITH PYTHON
# ============================================================================

section("54. BASH AND PYTHON: WHEN EACH FITS")

comparison = [
    ("Starting programs", "Excellent", "Excellent"),
    ("Pipelines", "Native and concise", "Explicit subprocess plumbing"),
    ("Filesystem orchestration", "Excellent", "Excellent"),
    ("Complex data structures", "Limited", "Strong"),
    ("Large algorithms", "Usually unsuitable", "Strong"),
    ("Text command composition", "Excellent", "Strong"),
    ("Static typing", "No", "Optional through type hints"),
    ("Error handling", "Exit statuses", "Exceptions and return values"),
    ("Portability", "Shell/version dependent", "Interpreter dependent"),
]

for category, bash_strength, python_strength in comparison:
    print(f"{category:28} Bash: {bash_strength:30} Python: {python_strength}")


# ============================================================================
# 56. ADVANCED DESIGN PRINCIPLES
# ============================================================================

section("55. ADVANCED DESIGN PRINCIPLES")

print(
    """
Production Bash scripts benefit from these principles:

1. Define the supported shell explicitly.
2. Quote expansions unless intentional splitting/globbing is required.
3. Validate external input.
4. Keep functions focused.
5. Use local variables inside functions.
6. Send diagnostics to stderr.
7. Return meaningful exit statuses.
8. Handle expected failures explicitly.
9. Avoid unnecessary subshells and external processes.
10. Make destructive operations obvious and carefully validated.
11. Use -- before user-controlled paths where supported.
12. Avoid parsing human-oriented command output when structured output exists.
13. Treat filenames as arbitrary strings.
14. Test scripts against unusual whitespace and special characters.
15. Keep secrets out of command traces and logs.
16. Use shell static analysis.
17. Make cleanup reliable.
18. Consider idempotency for automation.
19. Document Bash version requirements.
20. Prefer another language when shell complexity becomes difficult to reason about.
"""
)


# ============================================================================
# 57. EDGE CASES
# ============================================================================

section("56. EDGE CASES")

edge_cases = [
    "An empty variable",
    "An unset variable",
    "A filename containing spaces",
    "A filename beginning with '-'",
    "A filename containing wildcard characters",
    "A path containing newline characters",
    "A command returning a nonzero status",
    "A pipeline where an earlier command fails",
    "A missing executable",
    "A command interrupted by a signal",
    "A script receiving zero arguments",
    "A script receiving more arguments than expected",
    "A variable containing a literal newline",
    "A value containing shell metacharacters",
]

for index, case in enumerate(edge_cases, start=1):
    print(f"{index:2}. {case}")


# ============================================================================
# 58. PRODUCTION CHECKLIST
# ============================================================================

section("57. PRODUCTION CHECKLIST")

checklist = [
    "Correct shebang",
    "Explicit Bash version assumptions",
    "Appropriate shell options",
    "Quoted expansions",
    "Input validation",
    "Meaningful exit statuses",
    "stderr for diagnostics",
    "Safe temporary files",
    "Reliable cleanup",
    "No accidental secret logging",
    "No unsafe command-string construction",
    "Safe handling of filenames",
    "Reasonable process count",
    "Test coverage for failure paths",
    "Static analysis",
    "Idempotent behavior where appropriate",
    "Clear usage/help output",
    "Deterministic output",
    "Documented operational assumptions",
]

for item in checklist:
    print("[ ]", item)


# ============================================================================
# 59. FINAL EXECUTABLE KNOWLEDGE TEST
# ============================================================================

section("58. KNOWLEDGE TEST")

questions = [
    (
        "What does a zero exit status normally indicate?",
        "Success",
    ),
    (
        "Which variable contains the previous command's exit status?",
        "$?",
    ),
    (
        "Which parameter represents the first positional argument?",
        "$1",
    ),
    (
        "Which construct is commonly preferred for complex Bash conditions?",
        "[[ ... ]]",
    ),
    (
        "Which loop continues while a condition is true?",
        "while",
    ),
    (
        "Which loop continues until a condition becomes true?",
        "until",
    ),
    (
        "What does $@ represent conceptually?",
        "The positional arguments",
    ),
    (
        "What does $(( ... )) perform?",
        "Arithmetic expansion",
    ),
    (
        "What does $( ... ) perform?",
        "Command substitution",
    ),
    (
        "Why quote "$file"?",
        "To preserve argument boundaries and suppress unintended splitting/globbing",
    ),
]

for number, (question, answer) in enumerate(questions, start=1):
    print(f"\n{number}. {question}")
    print("   Answer:", answer)


# ============================================================================
# 60. COMPLETION
# ============================================================================

section("59. STUDY FILE COMPLETED")

print(
    """
The demonstrations above cover Bash syntax, variables, conditions, loops,
functions, arrays, parameter expansion, command execution, pipelines,
redirection, file handling, debugging, security, performance, concurrency,
and production-oriented design.

The most important mental model is:

    shell syntax
        -> expansion
        -> command construction
        -> process execution
        -> exit status

A Bash script becomes much easier to reason about once these stages are
understood separately.
"""
)
