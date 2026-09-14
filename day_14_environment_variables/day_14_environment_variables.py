"""
Environment Variables: PATH, Shell Variables, and Configuration Through Environment Variables

A comprehensive, self-contained tutorial from beginner to advanced level.

This script demonstrates:
- What environment variables are
- Process environments
- Reading variables with os.environ and os.getenv()
- Setting variables for the current process
- PATH and executable discovery
- Shell variables versus exported environment variables
- Inheritance between parent and child processes
- Temporary environment changes
- Configuration through environment variables
- Type conversion and validation
- Boolean, list, numeric, URL, and JSON configuration
- Required and optional settings
- Default values
- Precedence between configuration sources
- Secret handling
- Environment-specific configuration
- Subprocess behavior
- Cross-platform considerations
- PATH manipulation
- Security risks
- Debugging techniques
- Testing configuration
- Production design considerations
- Advanced configuration patterns
- Practical examples and edge cases

The examples intentionally use only Python's standard library.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


# ============================================================================
# 1. BASIC CONCEPT: WHAT IS AN ENVIRONMENT VARIABLE?
# ============================================================================

print("=" * 80)
print("1. ENVIRONMENT VARIABLES")
print("=" * 80)

# An environment variable is a named value supplied to a running process
# through its operating-system environment.
#
# Typical examples:
#   PATH
#   HOME
#   USER
#   TEMP
#   LANG
#   PYTHONPATH
#
# Applications also commonly define their own variables:
#   APP_ENV
#   APP_PORT
#   DATABASE_URL
#   LOG_LEVEL
#
# Environment variable values are fundamentally strings.

print("Operating system:", platform.system())
print("Python version:", platform.python_version())
print("Current working directory:", os.getcwd())
print("Number of environment variables visible to this process:", len(os.environ))


# ============================================================================
# 2. READING ENVIRONMENT VARIABLES
# ============================================================================

print("\n" + "=" * 80)
print("2. READING ENVIRONMENT VARIABLES")
print("=" * 80)

# os.environ behaves similarly to a mutable dictionary.
#
# Important:
#   os.environ["NAME"]
# raises KeyError if NAME does not exist.
#
# os.getenv("NAME")
# returns None if NAME does not exist.
#
# os.getenv("NAME", "default")
# returns the supplied default when NAME does not exist.

python_path = os.environ.get("PATH")

print("PATH exists:", python_path is not None)

if python_path:
    print("PATH length:", len(python_path))

home_directory = os.getenv("HOME")
windows_user_profile = os.getenv("USERPROFILE")

print("HOME:", home_directory)
print("USERPROFILE:", windows_user_profile)

# A portable home-directory lookup is preferable when the goal is simply to
# locate the current user's home directory.
print("Path.home():", Path.home())

missing_value = os.getenv("VARIABLE_THAT_PROBABLY_DOES_NOT_EXIST")
print("Missing variable with getenv():", missing_value)

try:
    missing_value = os.environ["VARIABLE_THAT_PROBABLY_DOES_NOT_EXIST"]
except KeyError:
    print("Dictionary-style access raises KeyError for missing variables.")


# ============================================================================
# 3. ENVIRONMENT VARIABLES ARE STRINGS
# ============================================================================

print("\n" + "=" * 80)
print("3. ENVIRONMENT VARIABLES ARE STRINGS")
print("=" * 80)

# Even if an environment variable looks like a number, the operating system
# exposes it as text.

os.environ["DEMO_PORT"] = "8000"
os.environ["DEMO_DEBUG"] = "true"
os.environ["DEMO_TIMEOUT"] = "2.5"

raw_port = os.environ["DEMO_PORT"]
raw_debug = os.environ["DEMO_DEBUG"]
raw_timeout = os.environ["DEMO_TIMEOUT"]

print(raw_port, type(raw_port))
print(raw_debug, type(raw_debug))
print(raw_timeout, type(raw_timeout))

# Applications must explicitly convert values into the required types.
port = int(raw_port)
timeout = float(raw_timeout)

print("Converted port:", port, type(port))
print("Converted timeout:", timeout, type(timeout))


# ============================================================================
# 4. SETTING VARIABLES FROM PYTHON
# ============================================================================

print("\n" + "=" * 80)
print("4. SETTING ENVIRONMENT VARIABLES")
print("=" * 80)

# os.environ changes the environment mapping of the current process.
#
# It does NOT permanently modify the operating system's global environment.
# It also does not normally modify the parent shell from which Python was
# launched.

os.environ["PYTHON_ENVIRONMENT_TUTORIAL"] = "active"

print(
    "PYTHON_ENVIRONMENT_TUTORIAL =",
    os.environ["PYTHON_ENVIRONMENT_TUTORIAL"],
)

# Values assigned to os.environ must be strings.
try:
    os.environ["INVALID_INTEGER_VALUE"] = 123  # type: ignore[assignment]
except (TypeError, ValueError):
    print("Environment variable values must be strings.")

# Correct form:
os.environ["VALID_INTEGER_VALUE"] = str(123)
print("VALID_INTEGER_VALUE:", os.environ["VALID_INTEGER_VALUE"])


# ============================================================================
# 5. DELETING ENVIRONMENT VARIABLES
# ============================================================================

print("\n" + "=" * 80)
print("5. DELETING ENVIRONMENT VARIABLES")
print("=" * 80)

os.environ["TEMPORARY_VARIABLE"] = "temporary"
print("Before deletion:", os.getenv("TEMPORARY_VARIABLE"))

del os.environ["TEMPORARY_VARIABLE"]

print("After deletion:", os.getenv("TEMPORARY_VARIABLE"))

# pop() is useful when deletion should tolerate a missing key.
os.environ["ANOTHER_TEMPORARY_VARIABLE"] = "value"
removed_value = os.environ.pop("ANOTHER_TEMPORARY_VARIABLE", None)

print("Removed value:", removed_value)


# ============================================================================
# 6. ENVIRONMENT VARIABLE NAMES
# ============================================================================

print("\n" + "=" * 80)
print("6. ENVIRONMENT VARIABLE NAMING")
print("=" * 80)

# A common convention is uppercase names with underscores:
#
# DATABASE_URL
# API_HOST
# API_PORT
# LOG_LEVEL
# APP_ENV
#
# Names are strings. Naming conventions are application-level conventions,
# although shells and operating systems can impose their own restrictions.

os.environ["APP_ENV"] = "development"
os.environ["APP_NAME"] = "EnvironmentTutorial"

print("APP_ENV:", os.getenv("APP_ENV"))
print("APP_NAME:", os.getenv("APP_NAME"))


# ============================================================================
# 7. THE PATH VARIABLE
# ============================================================================

print("\n" + "=" * 80)
print("7. PATH")
print("=" * 80)

# PATH is one of the most important environment variables.
#
# It tells command interpreters and programs where to search for executable
# commands.
#
# PATH is a sequence of directory paths separated by an operating-system
# specific separator:
#
# Unix/Linux/macOS: ":"
# Windows:          ";"
#
# Python exposes the correct separator through os.pathsep.

path_value = os.getenv("PATH", "")
path_entries = path_value.split(os.pathsep)

print("PATH separator:", repr(os.pathsep))
print("Number of PATH entries:", len(path_entries))

for index, entry in enumerate(path_entries[:10], start=1):
    print(f"{index:2}: {entry}")

if len(path_entries) > 10:
    print(f"... and {len(path_entries) - 10} more entries")


# ============================================================================
# 8. PATH AND EXECUTABLE DISCOVERY
# ============================================================================

print("\n" + "=" * 80)
print("8. FINDING EXECUTABLES")
print("=" * 80)

# shutil.which() searches PATH for an executable.
#
# This is usually safer and more portable than manually constructing paths.

python_executable = shutil.which("python")
git_executable = shutil.which("git")
pip_executable = shutil.which("pip")

print("python:", python_executable)
print("git:", git_executable)
print("pip:", pip_executable)

# sys.executable identifies the Python interpreter running this script.
print("Current Python interpreter:", sys.executable)

# The result can be None when the executable cannot be found.
print("Nonexistent command:", shutil.which("command_that_does_not_exist"))


# ============================================================================
# 9. PATH ORDER MATTERS
# ============================================================================

print("\n" + "=" * 80)
print("9. PATH ORDER")
print("=" * 80)

# If multiple directories contain executables with the same name, the search
# order can determine which executable is selected.
#
# This has practical consequences:
# - Python virtual environments
# - Different Node.js installations
# - Multiple versions of Java
# - System versus user-installed programs
# - Build tools
#
# shutil.which() follows the effective PATH.

print("Executable selected for Python:", shutil.which("python"))


# ============================================================================
# 10. SAFE PATH MANIPULATION
# ============================================================================

print("\n" + "=" * 80)
print("10. PATH MANIPULATION")
print("=" * 80)

# Avoid blindly replacing PATH. A replacement can make normal commands
# unavailable.
#
# To prepend a directory:
#     new_path = directory + os.pathsep + old_path
#
# To append a directory:
#     new_path = old_path + os.pathsep + directory

example_directory = str(Path.home() / "example-bin")
current_path = os.getenv("PATH", "")

prepended_path = example_directory + os.pathsep + current_path
appended_path = current_path + os.pathsep + example_directory

print("Example prepended PATH starts with:", prepended_path[:120])
print("Example appended PATH ends with:", appended_path[-120:])

# Do not change the real PATH merely for demonstration.


# ============================================================================
# 11. SHELL VARIABLES VERSUS ENVIRONMENT VARIABLES
# ============================================================================

print("\n" + "=" * 80)
print("11. SHELL VARIABLES AND ENVIRONMENT VARIABLES")
print("=" * 80)

# In Unix-like shells, a shell variable can exist only inside the shell:
#
#     NAME=value
#
# Exporting it makes it part of the environment inherited by child processes:
#
#     export NAME=value
#
# Windows command shells and PowerShell use different syntax.
#
# Python does not directly see a shell's private variables. It sees variables
# that the operating system placed into the process environment.

print(
    "Python sees APP_ENV because it was explicitly placed into this process "
    "environment."
)


# ============================================================================
# 12. PROCESS INHERITANCE
# ============================================================================

print("\n" + "=" * 80)
print("12. PROCESS ENVIRONMENT INHERITANCE")
print("=" * 80)

# When a process creates a child process, the child normally receives a copy
# of the parent's environment.
#
# Changes made by the child do not propagate backward into the parent.

os.environ["PARENT_DEMO_VARIABLE"] = "visible-to-child"

child_code = (
    "import os; "
    "print(os.getenv('PARENT_DEMO_VARIABLE', '<missing>'))"
)

completed = subprocess.run(
    [sys.executable, "-c", child_code],
    capture_output=True,
    text=True,
    check=True,
)

print("Child process received:", completed.stdout.strip())


# ============================================================================
# 13. CUSTOM ENVIRONMENT FOR A SUBPROCESS
# ============================================================================

print("\n" + "=" * 80)
print("13. CUSTOM SUBPROCESS ENVIRONMENT")
print("=" * 80)

# subprocess.run(..., env=custom_environment) allows a child to receive a
# deliberately constructed environment.
#
# A copy is generally preferable to constructing a completely empty
# environment because programs may depend on variables such as PATH.

child_environment = os.environ.copy()
child_environment["CHILD_ONLY_VARIABLE"] = "custom-value"

child_code = (
    "import os; "
    "print(os.getenv('CHILD_ONLY_VARIABLE', '<missing>'))"
)

completed = subprocess.run(
    [sys.executable, "-c", child_code],
    env=child_environment,
    capture_output=True,
    text=True,
    check=True,
)

print("Child-specific variable:", completed.stdout.strip())
print("Parent still has child variable:", os.getenv("CHILD_ONLY_VARIABLE"))


# ============================================================================
# 14. ENVIRONMENT VARIABLES DO NOT FLOW BACK TO THE PARENT
# ============================================================================

print("\n" + "=" * 80)
print("14. CHILD-TO-PARENT ENVIRONMENT CHANGES")
print("=" * 80)

child_code = (
    "import os; "
    "os.environ['CHILD_CHANGED_VARIABLE'] = 'child-value'; "
    "print(os.getenv('CHILD_CHANGED_VARIABLE'))"
)

completed = subprocess.run(
    [sys.executable, "-c", child_code],
    capture_output=True,
    text=True,
    check=True,
)

print("Child saw:", completed.stdout.strip())
print(
    "Parent sees:",
    os.getenv("CHILD_CHANGED_VARIABLE", "<not present>"),
)


# ============================================================================
# 15. TEMPORARY ENVIRONMENT CHANGES
# ============================================================================

print("\n" + "=" * 80)
print("15. TEMPORARY ENVIRONMENT CHANGES")
print("=" * 80)


@contextmanager
def temporary_environment(
    updates: dict[str, str],
) -> Iterator[None]:
    """
    Temporarily modify environment variables.

    Existing values are restored when the context exits.
    Variables that did not exist before are removed.
    """
    original_values: dict[str, str | None] = {
        key: os.environ.get(key)
        for key in updates
    }

    try:
        for key, value in updates.items():
            os.environ[key] = value
        yield
    finally:
        for key, original_value in original_values.items():
            if original_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = original_value


os.environ.pop("TEMP_CONTEXT_VARIABLE", None)

print("Before context:", os.getenv("TEMP_CONTEXT_VARIABLE"))

with temporary_environment(
    {"TEMP_CONTEXT_VARIABLE": "inside-context"}
):
    print("Inside context:", os.getenv("TEMP_CONTEXT_VARIABLE"))

print("After context:", os.getenv("TEMP_CONTEXT_VARIABLE"))


# ============================================================================
# 16. CONFIGURATION THROUGH ENVIRONMENT VARIABLES
# ============================================================================

print("\n" + "=" * 80)
print("16. APPLICATION CONFIGURATION")
print("=" * 80)

# Environment variables are particularly useful for configuration that should
# vary between environments without changing source code.
#
# Example:
#
# Development:
#   APP_ENV=development
#   APP_PORT=8000
#
# Production:
#   APP_ENV=production
#   APP_PORT=443
#
# The application code can remain unchanged.

os.environ["APPLICATION_NAME"] = "InventoryService"
os.environ["APPLICATION_ENV"] = "development"
os.environ["APPLICATION_PORT"] = "8080"
os.environ["APPLICATION_DEBUG"] = "false"

print("Application:", os.getenv("APPLICATION_NAME"))
print("Environment:", os.getenv("APPLICATION_ENV"))
print("Port:", os.getenv("APPLICATION_PORT"))
print("Debug:", os.getenv("APPLICATION_DEBUG"))


# ============================================================================
# 17. DEFAULT VALUES
# ============================================================================

print("\n" + "=" * 80)
print("17. DEFAULT VALUES")
print("=" * 80)

# Defaults are useful for optional configuration.
#
# Do not use an unsafe or surprising default for security-sensitive settings.

log_level = os.getenv("LOG_LEVEL", "INFO")
host = os.getenv("APP_HOST", "127.0.0.1")

print("Log level:", log_level)
print("Host:", host)


# ============================================================================
# 18. REQUIRED VARIABLES
# ============================================================================

print("\n" + "=" * 80)
print("18. REQUIRED VARIABLES")
print("=" * 80)


def get_required_environment_variable(name: str) -> str:
    """
    Return a required environment variable.

    Raises:
        RuntimeError: when the variable is missing or empty.
    """
    value = os.getenv(name)

    if value is None or not value.strip():
        raise RuntimeError(
            f"Required environment variable {name!r} is missing or empty."
        )

    return value


os.environ["REQUIRED_DEMO"] = "configured"

print(
    "Required value:",
    get_required_environment_variable("REQUIRED_DEMO"),
)

try:
    get_required_environment_variable("MISSING_REQUIRED_DEMO")
except RuntimeError as error:
    print("Validation error:", error)


# ============================================================================
# 19. EMPTY VALUES ARE DIFFERENT FROM MISSING VALUES
# ============================================================================

print("\n" + "=" * 80)
print("19. MISSING VERSUS EMPTY")
print("=" * 80)

os.environ["EMPTY_VARIABLE"] = ""

print("Missing:", os.getenv("VARIABLE_DOES_NOT_EXIST"))
print("Empty:", repr(os.getenv("EMPTY_VARIABLE")))

# getenv() returns None for missing variables, but an empty variable returns
# an empty string. Configuration validation may need to distinguish them.


# ============================================================================
# 20. BOOLEAN CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("20. BOOLEAN ENVIRONMENT VARIABLES")
print("=" * 80)


def parse_boolean(value: str) -> bool:
    """
    Convert common textual representations into a boolean.

    Accepted true values:
        true, 1, yes, y, on

    Accepted false values:
        false, 0, no, n, off
    """
    normalized = value.strip().lower()

    if normalized in {"true", "1", "yes", "y", "on"}:
        return True

    if normalized in {"false", "0", "no", "n", "off"}:
        return False

    raise ValueError(
        f"Invalid boolean value: {value!r}. "
        "Use true/false, 1/0, yes/no, or on/off."
    )


for value in ("true", "FALSE", "1", "0", "yes", "off"):
    print(value, "->", parse_boolean(value))

try:
    parse_boolean("sometimes")
except ValueError as error:
    print("Boolean validation:", error)


# ============================================================================
# 21. INTEGER CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("21. INTEGER CONFIGURATION")
print("=" * 80)


def parse_positive_integer(
    value: str,
    *,
    name: str,
    minimum: int = 1,
    maximum: int | None = None,
) -> int:
    """Parse and validate a bounded positive integer."""
    try:
        parsed = int(value.strip())
    except ValueError as error:
        raise ValueError(
            f"{name} must be an integer."
        ) from error

    if parsed < minimum:
        raise ValueError(
            f"{name} must be at least {minimum}."
        )

    if maximum is not None and parsed > maximum:
        raise ValueError(
            f"{name} must be at most {maximum}."
        )

    return parsed


print(
    parse_positive_integer(
        "8080",
        name="APP_PORT",
        minimum=1,
        maximum=65535,
    )
)

try:
    parse_positive_integer(
        "70000",
        name="APP_PORT",
        minimum=1,
        maximum=65535,
    )
except ValueError as error:
    print("Port validation:", error)


# ============================================================================
# 22. FLOAT CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("22. FLOAT CONFIGURATION")
print("=" * 80)


def parse_float(
    value: str,
    *,
    name: str,
    minimum: float | None = None,
) -> float:
    """Parse a floating-point configuration value."""
    try:
        parsed = float(value.strip())
    except ValueError as error:
        raise ValueError(f"{name} must be numeric.") from error

    if minimum is not None and parsed < minimum:
        raise ValueError(
            f"{name} must be at least {minimum}."
        )

    return parsed


print(
    parse_float(
        "2.75",
        name="REQUEST_TIMEOUT",
        minimum=0,
    )
)


# ============================================================================
# 23. LIST CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("23. LIST CONFIGURATION")
print("=" * 80)

# A simple convention is comma-separated values.

os.environ["ALLOWED_HOSTS"] = "localhost,127.0.0.1,example.com"


def parse_csv(value: str) -> list[str]:
    """Parse comma-separated configuration into cleaned values."""
    return [
        item.strip()
        for item in value.split(",")
        if item.strip()
    ]


allowed_hosts = parse_csv(os.environ["ALLOWED_HOSTS"])

print("Allowed hosts:", allowed_hosts)


# ============================================================================
# 24. JSON CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("24. JSON CONFIGURATION")
print("=" * 80)

# Environment variables are strings, but a string can contain structured data.
# JSON can represent nested configuration, although very large JSON blobs in
# environment variables can become difficult to manage.

os.environ["FEATURE_FLAGS"] = (
    '{"search": true, "reports": false, "experimental": true}'
)


def parse_json_object(value: str) -> dict[str, Any]:
    """Parse a JSON object stored in an environment variable."""
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError as error:
        raise ValueError(
            "Configuration contains invalid JSON."
        ) from error

    if not isinstance(parsed, dict):
        raise ValueError("Expected a JSON object.")

    return parsed


feature_flags = parse_json_object(os.environ["FEATURE_FLAGS"])

print("Feature flags:", feature_flags)


# ============================================================================
# 25. URL CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("25. URL-LIKE CONFIGURATION")
print("=" * 80)

from urllib.parse import urlparse


def validate_http_url(value: str, name: str) -> str:
    """
    Validate a basic HTTP/HTTPS URL.

    This is intentionally not a full URL security validator.
    """
    parsed = urlparse(value)

    if parsed.scheme not in {"http", "https"}:
        raise ValueError(
            f"{name} must use http or https."
        )

    if not parsed.netloc:
        raise ValueError(
            f"{name} must contain a host."
        )

    return value


database_admin_url = "https://database.example.com"

print(
    "Validated URL:",
    validate_http_url(
        database_admin_url,
        "DATABASE_ADMIN_URL",
    ),
)


# ============================================================================
# 26. A TYPED APPLICATION CONFIGURATION OBJECT
# ============================================================================

print("\n" + "=" * 80)
print("26. TYPED CONFIGURATION")
print("=" * 80)

from dataclasses import dataclass


@dataclass(frozen=True)
class ApplicationConfig:
    """
    Typed application configuration.

    Environment variables are the input mechanism; this object is the
    validated representation used by application code.
    """

    environment: str
    host: str
    port: int
    debug: bool
    log_level: str
    request_timeout: float


def load_application_config() -> ApplicationConfig:
    """Load, convert, and validate application configuration."""
    environment = os.getenv("APPLICATION_ENV", "development").strip().lower()

    allowed_environments = {
        "development",
        "testing",
        "staging",
        "production",
    }

    if environment not in allowed_environments:
        raise ValueError(
            "APPLICATION_ENV must be one of: "
            + ", ".join(sorted(allowed_environments))
        )

    host = os.getenv("APP_HOST", "127.0.0.1").strip()

    port = parse_positive_integer(
        os.getenv("APPLICATION_PORT", "8000"),
        name="APPLICATION_PORT",
        minimum=1,
        maximum=65535,
    )

    debug = parse_boolean(
        os.getenv("APPLICATION_DEBUG", "false")
    )

    log_level = os.getenv("LOG_LEVEL", "INFO").strip().upper()

    allowed_log_levels = {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }

    if log_level not in allowed_log_levels:
        raise ValueError(
            "LOG_LEVEL must be one of: "
            + ", ".join(sorted(allowed_log_levels))
        )

    request_timeout = parse_float(
        os.getenv("REQUEST_TIMEOUT", "5.0"),
        name="REQUEST_TIMEOUT",
        minimum=0,
    )

    return ApplicationConfig(
        environment=environment,
        host=host,
        port=port,
        debug=debug,
        log_level=log_level,
        request_timeout=request_timeout,
    )


os.environ["REQUEST_TIMEOUT"] = "3.5"
config = load_application_config()

print(config)
print("Config port:", config.port)
print("Config debug:", config.debug)


# ============================================================================
# 27. CONFIGURATION PRECEDENCE
# ============================================================================

print("\n" + "=" * 80)
print("27. CONFIGURATION PRECEDENCE")
print("=" * 80)

# Real applications often combine several configuration sources:
#
# 1. Built-in defaults
# 2. Configuration files
# 3. Environment variables
# 4. Command-line arguments
#
# The exact precedence is an application design decision.
#
# Environment variables are often preferred over static defaults because
# deployment systems can change them without modifying source code.

def choose_config_value(
    *,
    environment_name: str,
    command_line_value: str | None,
    environment_value: str | None,
    file_value: str | None,
    default_value: str,
) -> str:
    """
    Demonstrate an explicit configuration precedence policy.

    Command-line > environment > file > default.
    """
    if command_line_value is not None:
        return command_line_value

    if environment_value is not None:
        return environment_value

    if file_value is not None:
        return file_value

    return default_value


os.environ["SERVICE_MODE"] = "production"

selected_mode = choose_config_value(
    environment_name="SERVICE_MODE",
    command_line_value=None,
    environment_value=os.getenv("SERVICE_MODE"),
    file_value="staging",
    default_value="development",
)

print("Selected configuration value:", selected_mode)


# ============================================================================
# 28. ENVIRONMENT-SPECIFIC CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("28. DEVELOPMENT, TESTING, STAGING, PRODUCTION")
print("=" * 80)

# The same application can receive different environment values in different
# deployment environments.
#
# Development:
#   verbose logging
#   local services
#   debugging enabled
#
# Testing:
#   isolated databases
#   deterministic settings
#
# Staging:
#   production-like infrastructure
#
# Production:
#   strict security
#   production databases
#   controlled logging

for environment in (
    "development",
    "testing",
    "staging",
    "production",
):
    with temporary_environment(
        {"APPLICATION_ENV": environment}
    ):
        print(
            "APPLICATION_ENV =",
            os.getenv("APPLICATION_ENV"),
        )


# ============================================================================
# 29. SECRETS AND ENVIRONMENT VARIABLES
# ============================================================================

print("\n" + "=" * 80)
print("29. SECRETS")
print("=" * 80)

# Environment variables are commonly used to provide secrets to applications:
#
#   DATABASE_PASSWORD
#   API_KEY
#   ACCESS_TOKEN
#
# This avoids hard-coding secrets directly into source code.
#
# But environment variables are NOT automatically a perfect secret store.
# Depending on the operating system, process management tools, debugging
# tools, crash reports, logs, child processes, or deployment systems may
# expose environment values.
#
# Never print secrets casually.

os.environ["DEMO_API_KEY"] = "example-secret-value"

print(
    "Secret exists:",
    bool(os.getenv("DEMO_API_KEY")),
)

# A safe diagnostic should reveal presence rather than the secret itself.


def secret_present(name: str) -> bool:
    """Return whether a secret-like variable is present and non-empty."""
    return bool(os.getenv(name))


print("DEMO_API_KEY present:", secret_present("DEMO_API_KEY"))


# ============================================================================
# 30. REDACTING CONFIGURATION FOR LOGGING
# ============================================================================

print("\n" + "=" * 80)
print("30. SAFE CONFIGURATION DIAGNOSTICS")
print("=" * 80)


SENSITIVE_NAME_FRAGMENTS = {
    "PASSWORD",
    "SECRET",
    "TOKEN",
    "API_KEY",
    "PRIVATE_KEY",
    "CREDENTIAL",
}


def redact_environment_value(name: str, value: str | None) -> str:
    """
    Redact values whose names indicate sensitive information.
    """
    uppercase_name = name.upper()

    if any(
        fragment in uppercase_name
        for fragment in SENSITIVE_NAME_FRAGMENTS
    ):
        return "<REDACTED>"

    if value is None:
        return "<MISSING>"

    return value


for name in (
    "APPLICATION_ENV",
    "APPLICATION_PORT",
    "DEMO_API_KEY",
    "MISSING_SETTING",
):
    print(
        name,
        "=",
        redact_environment_value(
            name,
            os.getenv(name),
        ),
    )


# ============================================================================
# 31. ENVIRONMENT VARIABLES AND CHILD PROCESSES
# ============================================================================

print("\n" + "=" * 80)
print("31. SUBPROCESS CONFIGURATION")
print("=" * 80)

# A useful production pattern is to give a child process only the environment
# it needs.
#
# A complete "empty environment" can break commands because PATH and other
# expected variables may be absent.
#
# A safer pattern is often:
#     env = os.environ.copy()
#     env["SPECIFIC_SETTING"] = "value"

child_environment = os.environ.copy()
child_environment["WORKER_ROLE"] = "background-worker"

worker_code = (
    "import os; "
    "print('worker role:', os.getenv('WORKER_ROLE')); "
    "print('application environment:', os.getenv('APPLICATION_ENV'))"
)

completed = subprocess.run(
    [sys.executable, "-c", worker_code],
    env=child_environment,
    capture_output=True,
    text=True,
    check=True,
)

print(completed.stdout.strip())


# ============================================================================
# 32. ENVIRONMENT VARIABLES AND os.system / SHELL COMMANDS
# ============================================================================

print("\n" + "=" * 80)
print("32. SHELL COMMANDS AND ENVIRONMENT")
print("=" * 80)

# subprocess.run() is generally preferred over os.system() because it provides
# structured control over arguments, environment, output, and errors.
#
# When a shell is involved, untrusted input can create command-injection risks.
#
# This example does not execute user-controlled shell syntax.

safe_environment = os.environ.copy()
safe_environment["COMMAND_DEMO"] = "safe-value"

completed = subprocess.run(
    [
        sys.executable,
        "-c",
        "import os; print(os.getenv('COMMAND_DEMO'))",
    ],
    env=safe_environment,
    capture_output=True,
    text=True,
    check=True,
)

print("Child command output:", completed.stdout.strip())


# ============================================================================
# 33. PATH SECURITY
# ============================================================================

print("\n" + "=" * 80)
print("33. PATH SECURITY")
print("=" * 80)

# PATH can be a security boundary.
#
# If an attacker can insert a malicious directory early in PATH, a program
# that launches a command by name may execute the wrong program.
#
# Security-sensitive software should consider:
# - Using absolute executable paths when appropriate
# - Validating PATH
# - Avoiding writable directories in privileged PATHs
# - Avoiding unnecessary shell execution
# - Using subprocess argument lists instead of shell strings

print("Current Python executable:", sys.executable)
print("Resolved Python through PATH:", shutil.which("python"))


# ============================================================================
# 34. PATH INJECTION AND COMMAND EXECUTION
# ============================================================================

print("\n" + "=" * 80)
print("34. COMMAND RESOLUTION")
print("=" * 80)

# Compare:
#
#     subprocess.run(["python", "-c", "..."])
#
# with:
#
#     subprocess.run("python -c '...'", shell=True)
#
# The first form avoids shell parsing and is generally easier to reason about.
#
# If command names come from untrusted input, additional validation is needed.

command = shutil.which("python")

if command:
    result = subprocess.run(
        [
            command,
            "-c",
            "print('Command resolved safely')",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    print(result.stdout.strip())


# ============================================================================
# 35. CASE SENSITIVITY
# ============================================================================

print("\n" + "=" * 80)
print("35. CASE SENSITIVITY")
print("=" * 80)

# Environment-variable name case behavior depends partly on the operating
# system. Windows environment variable names are generally case-insensitive,
# while Unix-like systems generally treat names as case-sensitive.
#
# Applications should therefore choose a consistent naming convention.

os.environ["CaseDemoVariable"] = "value"

print(
    "CaseDemoVariable:",
    os.getenv("CaseDemoVariable"),
)

print(
    "CASEDEMOVARIABLE:",
    os.getenv("CASEDEMOVARIABLE"),
)


# ============================================================================
# 36. ENVIRONMENT VARIABLE LENGTH AND SIZE LIMITS
# ============================================================================

print("\n" + "=" * 80)
print("36. ENVIRONMENT SIZE LIMITATIONS")
print("=" * 80)

# Operating systems impose limits on environment size and process creation.
# Exact limits vary by operating system and execution environment.
#
# Therefore, environment variables are best suited to relatively small
# configuration values, credentials, feature flags, and connection strings.
#
# Very large configuration documents can become difficult to manage.

large_demo_value = "x" * 1000
os.environ["SMALL_CONFIGURATION_DOCUMENT"] = large_demo_value

print(
    "Example environment value length:",
    len(os.environ["SMALL_CONFIGURATION_DOCUMENT"]),
)


# ============================================================================
# 37. UNICODE ENVIRONMENT VALUES
# ============================================================================

print("\n" + "=" * 80)
print("37. UNICODE VALUES")
print("=" * 80)

# Modern operating systems and Python generally support Unicode environment
# values, but interoperability with external tools can vary.

os.environ["DISPLAY_NAME"] = "Atul Pandey"
print("DISPLAY_NAME:", os.getenv("DISPLAY_NAME"))


# ============================================================================
# 38. WHITESPACE HANDLING
# ============================================================================

print("\n" + "=" * 80)
print("38. WHITESPACE")
print("=" * 80)

os.environ["WHITESPACE_DEMO"] = "   production   "

raw_value = os.getenv("WHITESPACE_DEMO", "")
clean_value = raw_value.strip()

print("Raw value:", repr(raw_value))
print("Clean value:", repr(clean_value))


# ============================================================================
# 39. CASE NORMALIZATION FOR ENUM-LIKE VALUES
# ============================================================================

print("\n" + "=" * 80)
print("39. NORMALIZING ENUM-LIKE VALUES")
print("=" * 80)


def parse_environment_name(value: str) -> str:
    """Normalize and validate an application environment name."""
    normalized = value.strip().lower()

    allowed = {
        "development",
        "testing",
        "staging",
        "production",
    }

    if normalized not in allowed:
        raise ValueError(
            f"Unsupported environment: {value!r}"
        )

    return normalized


for environment_name in (
    "DEVELOPMENT",
    " testing ",
    "Production",
):
    print(
        repr(environment_name),
        "->",
        parse_environment_name(environment_name),
    )


# ============================================================================
# 40. CONFIGURATION VALIDATION AS A SEPARATE STAGE
# ============================================================================

print("\n" + "=" * 80)
print("40. LOAD, PARSE, VALIDATE")
print("=" * 80)

# A robust configuration architecture separates:
#
# 1. Loading raw values
# 2. Parsing types
# 3. Validating constraints
# 4. Producing a typed configuration object
#
# This makes errors occur early rather than deep inside application logic.

def validate_application_config(config: ApplicationConfig) -> None:
    """Validate relationships between configuration fields."""
    if config.environment == "production" and config.debug:
        raise ValueError(
            "Debug mode must not be enabled in production."
        )

    if config.request_timeout <= 0:
        raise ValueError(
            "Request timeout must be greater than zero."
        )


with temporary_environment(
    {
        "APPLICATION_ENV": "development",
        "APPLICATION_PORT": "8000",
        "APPLICATION_DEBUG": "true",
        "LOG_LEVEL": "DEBUG",
        "REQUEST_TIMEOUT": "5",
    }
):
    development_config = load_application_config()
    validate_application_config(development_config)
    print("Development configuration validated.")


# ============================================================================
# 41. PRODUCTION CONFIGURATION VALIDATION
# ============================================================================

print("\n" + "=" * 80)
print("41. PRODUCTION SAFETY VALIDATION")
print("=" * 80)

with temporary_environment(
    {
        "APPLICATION_ENV": "production",
        "APPLICATION_PORT": "443",
        "APPLICATION_DEBUG": "true",
        "LOG_LEVEL": "INFO",
        "REQUEST_TIMEOUT": "5",
    }
):
    try:
        production_config = load_application_config()
        validate_application_config(production_config)
    except ValueError as error:
        print("Production validation rejected configuration:", error)


# ============================================================================
# 42. OPTIONAL VARIABLES
# ============================================================================

print("\n" + "=" * 80)
print("42. OPTIONAL CONFIGURATION")
print("=" * 80)


def get_optional_environment_variable(
    name: str,
    default: str | None = None,
) -> str | None:
    """
    Read an optional environment variable.

    Empty strings are treated as missing in this application policy.
    """
    value = os.getenv(name)

    if value is None:
        return default

    cleaned = value.strip()

    return cleaned if cleaned else default


print(
    "Optional value:",
    get_optional_environment_variable(
        "OPTIONAL_SETTING",
        default="fallback",
    ),
)


# ============================================================================
# 43. DATABASE CONNECTION STRING EXAMPLE
# ============================================================================

print("\n" + "=" * 80)
print("43. DATABASE CONNECTION CONFIGURATION")
print("=" * 80)

# A database connection URL is commonly injected through an environment
# variable. The actual credentials should never be committed to source code.

os.environ["DATABASE_URL"] = (
    "postgresql://app_user:example-password@localhost:5432/appdb"
)

database_url = os.getenv("DATABASE_URL")

if database_url:
    parsed_database_url = urlparse(database_url)

    print("Database scheme:", parsed_database_url.scheme)
    print("Database host:", parsed_database_url.hostname)
    print("Database port:", parsed_database_url.port)
    print("Database name:", parsed_database_url.path.lstrip("/"))

    # Do not print the full URL because it may contain credentials.


# ============================================================================
# 44. REDACTING A DATABASE URL
# ============================================================================

print("\n" + "=" * 80)
print("44. DATABASE URL REDACTION")
print("=" * 80)

from urllib.parse import urlunparse


def redact_url_password(value: str) -> str:
    """Return a URL with its password removed from displayed output."""
    parsed = urlparse(value)

    if parsed.username is None:
        return value

    hostname = parsed.hostname or ""

    if parsed.port:
        hostname = f"{hostname}:{parsed.port}"

    userinfo = parsed.username

    redacted_netloc = f"{userinfo}:<REDACTED>@{hostname}"

    redacted = parsed._replace(netloc=redacted_netloc)

    return urlunparse(redacted)


if database_url:
    print(redact_url_password(database_url))


# ============================================================================
# 45. ENVIRONMENT VARIABLES AND .env FILES
# ============================================================================

print("\n" + "=" * 80)
print("45. .env FILES")
print("=" * 80)

# A .env file is a convention used by many development tools and libraries
# for defining environment-like configuration.
#
# Important distinction:
#   A .env file is a file.
#   An environment variable is part of a process environment.
#
# Python's standard library does not automatically load .env files.
#
# In development, tools or libraries may load a .env file into the process
# environment. Production systems often inject environment variables directly
# through the operating system, container platform, CI/CD system, or secret
# management infrastructure.

print(
    ".env files are configuration files; they are not inherently the same "
    "thing as process environment variables."
)


# ============================================================================
# 46. SAFE MINI .env PARSER FOR EDUCATIONAL PURPOSES
# ============================================================================

print("\n" + "=" * 80)
print("46. SIMPLE .env PARSING")
print("=" * 80)


def parse_simple_env_file(content: str) -> dict[str, str]:
    """
    Parse a deliberately simple .env-like format.

    Supported:
        KEY=value
        KEY="value"
        KEY='value'
        # comments
        blank lines

    This is educational and intentionally does not attempt to reproduce
    every shell or .env syntax feature.
    """
    result: dict[str, str] = {}

    for line_number, raw_line in enumerate(
        content.splitlines(),
        start=1,
    ):
        line = raw_line.strip()

        if not line or line.startswith("#"):
            continue

        if "=" not in line:
            raise ValueError(
                f"Invalid configuration line {line_number}: {raw_line!r}"
            )

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()

        if not key:
            raise ValueError(
                f"Missing key on line {line_number}."
            )

        if (
            len(value) >= 2
            and value[0] == value[-1]
            and value[0] in {"'", '"'}
        ):
            value = value[1:-1]

        result[key] = value

    return result


sample_env_content = """
# Development configuration
APP_ENV=development
APP_PORT=8000
APP_DEBUG="true"
APP_NAME='Example Application'
"""

parsed_env_file = parse_simple_env_file(sample_env_content)

for key, value in parsed_env_file.items():
    print(key, "=", value)


# ============================================================================
# 47. APPLYING PARSED VALUES
# ============================================================================

print("\n" + "=" * 80)
print("47. APPLYING CONFIGURATION VALUES")
print("=" * 80)

# A parsed .env-style file can be applied to the current process if desired.
# Production applications should use a deliberate policy regarding whether
# environment-file values may override already-defined variables.

for key, value in parsed_env_file.items():
    os.environ[key] = value

print("APP_ENV:", os.getenv("APP_ENV"))
print("APP_PORT:", os.getenv("APP_PORT"))
print("APP_DEBUG:", os.getenv("APP_DEBUG"))


# ============================================================================
# 48. DO NOT COMMIT SECRETS
# ============================================================================

print("\n" + "=" * 80)
print("48. SOURCE CONTROL AND SECRETS")
print("=" * 80)

# A configuration file containing credentials should not be committed merely
# because it has a familiar name such as .env.
#
# A common development pattern is:
#
#   .env
#   .env.example
#
# .env contains local secrets and is excluded from source control.
# .env.example documents required variable names without real credentials.

print(
    "Configuration templates should document variable names without exposing "
    "real secrets."
)


# ============================================================================
# 49. ENVIRONMENT VARIABLES AND CI/CD
# ============================================================================

print("\n" + "=" * 80)
print("49. CI/CD CONFIGURATION")
print("=" * 80)

# Continuous integration and deployment systems commonly inject variables such
# as:
#
#   CI=true
#   BUILD_NUMBER=...
#   DEPLOYMENT_ENV=...
#   API_TOKEN=...
#
# The application should treat CI/CD-provided values as untrusted input unless
# the deployment system guarantees their origin and access control.

os.environ["CI"] = "true"

print("CI mode:", parse_boolean(os.getenv("CI", "false")))


# ============================================================================
# 50. CONTAINER CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("50. CONTAINERIZED APPLICATIONS")
print("=" * 80)

# Containers commonly receive configuration through environment variables.
#
# Example conceptual configuration:
#
#   APP_ENV=production
#   APP_PORT=8080
#   DATABASE_URL=...
#
# The container image can remain identical while different deployments supply
# different environment values.
#
# Environment variables are configuration inputs, not a replacement for
# proper secret management and access control.

os.environ["CONTAINER_NAME"] = "application-container"

print("Container name:", os.getenv("CONTAINER_NAME"))


# ============================================================================
# 51. ENVIRONMENT VARIABLE SNAPSHOTS
# ============================================================================

print("\n" + "=" * 80)
print("51. ENVIRONMENT SNAPSHOTS")
print("=" * 80)

# os.environ represents the environment currently visible to this process.
# A snapshot can be useful for testing or diagnostics.

environment_snapshot = dict(os.environ)

print(
    "Snapshot contains variables:",
    len(environment_snapshot),
)

print(
    "Snapshot APP_ENV:",
    environment_snapshot.get("APP_ENV"),
)


# ============================================================================
# 52. TESTING CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("52. TESTING ENVIRONMENT-BASED CONFIGURATION")
print("=" * 80")


def get_app_port() -> int:
    """Read and validate the application port."""
    return parse_positive_integer(
        os.getenv("APP_PORT", "8000"),
        name="APP_PORT",
        minimum=1,
        maximum=65535,
    )


def test_get_app_port_valid() -> None:
    """Verify a valid port is converted correctly."""
    with temporary_environment({"APP_PORT": "9000"}):
        assert get_app_port() == 9000


def test_get_app_port_invalid() -> None:
    """Verify invalid port values raise an error."""
    with temporary_environment({"APP_PORT": "99999"}):
        try:
            get_app_port()
        except ValueError:
            return

        raise AssertionError(
            "Invalid port should raise ValueError."
        )


test_get_app_port_valid()
test_get_app_port_invalid()

print("Environment configuration tests passed.")


# ============================================================================
# 53. TEST ISOLATION
# ============================================================================

print("\n" + "=" * 80)
print("53. TEST ISOLATION")
print("=" * 80)

# Tests that modify os.environ can accidentally influence later tests.
# temporary_environment() prevents this by restoring values.

with temporary_environment({"TEST_MODE": "unit-test"}):
    assert os.getenv("TEST_MODE") == "unit-test"

assert os.getenv("TEST_MODE") is None

print("Environment changes were isolated.")


# ============================================================================
# 54. DEBUGGING MISSING VARIABLES
# ============================================================================

print("\n" + "=" * 80)
print("54. DEBUGGING MISSING VARIABLES")
print("=" * 80)


def diagnose_environment_variable(
    name: str,
) -> dict[str, Any]:
    """Provide non-secret diagnostic information."""
    value = os.getenv(name)

    return {
        "name": name,
        "present": value is not None,
        "empty": value == "",
        "length": len(value) if value is not None else None,
    }


print(
    diagnose_environment_variable("APPLICATION_ENV")
)

print(
    diagnose_environment_variable("VARIABLE_THAT_IS_MISSING")
)


# ============================================================================
# 55. DEBUGGING PATH PROBLEMS
# ============================================================================

print("\n" + "=" * 80)
print("55. DEBUGGING PATH")
print("=" * 80)


def explain_executable_lookup(executable_name: str) -> None:
    """
    Display safe diagnostics for executable discovery.
    """
    resolved = shutil.which(executable_name)

    print("Command:", executable_name)
    print("Resolved path:", resolved)

    if resolved is None:
        print("The command was not found through the current PATH.")


explain_executable_lookup("python")
explain_executable_lookup("git")


# ============================================================================
# 56. ENVIRONMENT VARIABLES AND PYTHON MODULE DISCOVERY
# ============================================================================

print("\n" + "=" * 80)
print("56. PYTHONPATH")
print("=" * 80)

# PYTHONPATH is an environment variable that can add directories to Python's
# module search path.
#
# It can be useful in specific development environments but can also make
# imports harder to reproduce because behavior depends on external state.
#
# sys.path shows the effective Python module search path for this process.

pythonpath = os.getenv("PYTHONPATH")

print("PYTHONPATH:", pythonpath)
print("First Python import path entry:", sys.path[0] if sys.path else None)


# ============================================================================
# 57. ENVIRONMENT VARIABLES AND HOME/TEMP DIRECTORIES
# ============================================================================

print("\n" + "=" * 80)
print("57. COMMON OPERATING SYSTEM VARIABLES")
print("=" * 80)

# Common variables differ between operating systems.
#
# HOME is common on Unix-like systems.
# USERPROFILE is commonly used on Windows.
# TEMP and TMP may identify temporary directories.
#
# For portable Python code, standard-library APIs such as Path.home() and
# tempfile.gettempdir() are usually preferable when available.

print("HOME:", os.getenv("HOME"))
print("USERPROFILE:", os.getenv("USERPROFILE"))
print("TEMP:", os.getenv("TEMP"))
print("TMP:", os.getenv("TMP"))
print("Python temp directory:", tempfile.gettempdir())


# ============================================================================
# 58. CONFIGURATION WITH PREFIXES
# ============================================================================

print("\n" + "=" * 80)
print("58. VARIABLE PREFIXES")
print("=" * 80)

# Prefixes reduce collisions between applications.
#
# Instead of:
#   PORT
#   TIMEOUT
#
# an application may use:
#   MYAPP_PORT
#   MYAPP_TIMEOUT
#
# This is particularly useful on shared machines and deployment platforms.

os.environ["MYAPP_PORT"] = "8080"
os.environ["MYAPP_TIMEOUT"] = "10"

myapp_configuration = {
    key: value
    for key, value in os.environ.items()
    if key.startswith("MYAPP_")
}

print("MYAPP_* configuration:", myapp_configuration)


# ============================================================================
# 59. CONFIGURATION AS A MAPPING
# ============================================================================

print("\n" + "=" * 80)
print("59. EXTRACTING APPLICATION CONFIGURATION")
print("=" * 80)


def get_prefixed_environment(
    prefix: str,
) -> dict[str, str]:
    """
    Return all environment variables beginning with a prefix.

    The prefix is removed from the resulting keys.
    """
    configuration: dict[str, str] = {}

    for key, value in os.environ.items():
        if key.startswith(prefix):
            configuration[key[len(prefix):]] = value

    return configuration


print(
    get_prefixed_environment("MYAPP_")
)


# ============================================================================
# 60. A SMALL CONFIGURATION SYSTEM
# ============================================================================

print("\n" + "=" * 80)
print("60. SMALL CONFIGURATION SYSTEM")
print("=" * 80)


@dataclass(frozen=True)
class ServiceConfig:
    """Validated configuration for a small service."""

    name: str
    environment: str
    host: str
    port: int
    debug: bool
    workers: int
    allowed_origins: tuple[str, ...]


def load_service_config() -> ServiceConfig:
    """Load service configuration from environment variables."""
    name = os.getenv("SERVICE_NAME", "ExampleService").strip()

    if not name:
        raise ValueError("SERVICE_NAME cannot be empty.")

    environment = parse_environment_name(
        os.getenv("SERVICE_ENV", "development")
    )

    host = os.getenv("SERVICE_HOST", "127.0.0.1").strip()

    if not host:
        raise ValueError("SERVICE_HOST cannot be empty.")

    port = parse_positive_integer(
        os.getenv("SERVICE_PORT", "8000"),
        name="SERVICE_PORT",
        minimum=1,
        maximum=65535,
    )

    debug = parse_boolean(
        os.getenv("SERVICE_DEBUG", "false")
    )

    workers = parse_positive_integer(
        os.getenv("SERVICE_WORKERS", "1"),
        name="SERVICE_WORKERS",
        minimum=1,
        maximum=256,
    )

    allowed_origins = tuple(
        parse_csv(
            os.getenv(
                "SERVICE_ALLOWED_ORIGINS",
                "http://localhost",
            )
        )
    )

    if environment == "production" and debug:
        raise ValueError(
            "SERVICE_DEBUG cannot be enabled in production."
        )

    return ServiceConfig(
        name=name,
        environment=environment,
        host=host,
        port=port,
        debug=debug,
        workers=workers,
        allowed_origins=allowed_origins,
    )


with temporary_environment(
    {
        "SERVICE_NAME": "InventoryAPI",
        "SERVICE_ENV": "development",
        "SERVICE_HOST": "0.0.0.0",
        "SERVICE_PORT": "8080",
        "SERVICE_DEBUG": "true",
        "SERVICE_WORKERS": "2",
        "SERVICE_ALLOWED_ORIGINS": (
            "http://localhost:3000,http://localhost:5173"
        ),
    }
):
    service_config = load_service_config()
    print(service_config)


# ============================================================================
# 61. IMMUTABLE CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("61. IMMUTABLE CONFIGURATION")
print("=" * 80)

# @dataclass(frozen=True) creates a configuration object that cannot be
# accidentally modified after loading.
#
# This helps prevent one component from changing global application settings
# while another component is using them.

try:
    service_config.port = 9000  # type: ignore[misc]
except Exception as error:
    print("Immutable configuration:", type(error).__name__)


# ============================================================================
# 62. CONFIGURATION VALIDATION ERRORS SHOULD BE EARLY
# ============================================================================

print("\n" + "=" * 80)
print("62. FAILING EARLY")
print("=" * 80)

with temporary_environment(
    {
        "SERVICE_PORT": "not-a-number",
        "SERVICE_WORKERS": "2",
    }
):
    try:
        load_service_config()
    except ValueError as error:
        print("Startup configuration error:", error)


# ============================================================================
# 63. ENVIRONMENT VARIABLES ARE INPUT
# ============================================================================

print("\n" + "=" * 80)
print("63. TREAT ENVIRONMENT VALUES AS INPUT")
print("=" * 80)

# Environment variables should not automatically be trusted.
#
# They can be malformed, missing, unexpectedly large, or incorrectly supplied
# by deployment systems.
#
# Validate:
# - Type
# - Range
# - Allowed values
# - Required/optional status
# - Relationships between fields
# - Security-sensitive combinations

with temporary_environment(
    {"SERVICE_WORKERS": "-5"}
):
    try:
        parse_positive_integer(
            os.getenv("SERVICE_WORKERS", ""),
            name="SERVICE_WORKERS",
            minimum=1,
            maximum=256,
        )
    except ValueError as error:
        print("Input validation:", error)


# ============================================================================
# 64. PATH NORMALIZATION
# ============================================================================

print("\n" + "=" * 80)
print("64. PATH ENTRY NORMALIZATION")
print("=" * 80)

# PATH entries may contain relative paths, empty entries, duplicates, or paths
# that no longer exist. The exact interpretation of an empty PATH component
# is platform/shell dependent and can have security implications.

def normalized_path_entries(path_value: str) -> list[str]:
    """Return cleaned non-empty PATH entries."""
    return [
        entry.strip()
        for entry in path_value.split(os.pathsep)
        if entry.strip()
    ]


cleaned_path_entries = normalized_path_entries(
    os.getenv("PATH", "")
)

print("Cleaned PATH entries:", len(cleaned_path_entries))


# ============================================================================
# 65. DUPLICATE PATH ENTRIES
# ============================================================================

print("\n" + "=" * 80)
print("65. DUPLICATE PATH ENTRIES")
print("=" * 80)


def find_duplicate_values(values: list[str]) -> list[str]:
    """Return values that occur more than once, preserving first occurrence."""
    seen: set[str] = set()
    duplicates: list[str] = set()

    for value in values:
        if value in seen:
            duplicates.add(value)
        else:
            seen.add(value)

    return sorted(duplicates)


duplicates = find_duplicate_values(
    cleaned_path_entries
)

print("Duplicate PATH entries:", duplicates[:10])


# ============================================================================
# 66. ENVIRONMENT VARIABLE OVERRIDES
# ============================================================================

print("\n" + "=" * 80)
print("66. EXPLICIT OVERRIDE POLICY")
print("=" * 80)


def environment_override(
    name: str,
    default: str,
) -> str:
    """
    Environment variable overrides the default only when non-empty.
    """
    value = os.getenv(name)

    if value is None or not value.strip():
        return default

    return value.strip()


with temporary_environment({"OVERRIDE_DEMO": "from-environment"}):
    print(
        environment_override(
            "OVERRIDE_DEMO",
            "from-default",
        )
    )

print(
    environment_override(
        "OVERRIDE_DEMO_MISSING",
        "from-default",
    )
)


# ============================================================================
# 67. CONFIGURATION DEPENDENCIES
# ============================================================================

print("\n" + "=" * 80)
print("67. CROSS-FIELD VALIDATION")
print("=" * 80)


def validate_service_relationships(config: ServiceConfig) -> None:
    """
    Validate rules involving multiple configuration values.
    """
    if config.environment == "production":
        if config.host in {"127.0.0.1", "localhost"}:
            raise ValueError(
                "Production service should not bind only to localhost "
                "when external traffic is required."
            )

        if config.debug:
            raise ValueError(
                "Production debug mode is forbidden."
            )

    if config.workers > 1 and config.debug:
        raise ValueError(
            "This example application forbids multiple workers in debug mode."
        )


with temporary_environment(
    {
        "SERVICE_NAME": "Demo",
        "SERVICE_ENV": "production",
        "SERVICE_HOST": "0.0.0.0",
        "SERVICE_PORT": "8080",
        "SERVICE_DEBUG": "false",
        "SERVICE_WORKERS": "4",
        "SERVICE_ALLOWED_ORIGINS": "https://example.com",
    }
):
    production_service_config = load_service_config()
    validate_service_relationships(production_service_config)
    print("Cross-field production validation passed.")


# ============================================================================
# 68. CONFIGURATION DOCUMENTATION
# ============================================================================

print("\n" + "=" * 80)
print("68. CONFIGURATION DOCUMENTATION")
print("=" * 80)

# A production application should document:
#
# Variable name
# Required/optional status
# Data type
# Default value
# Allowed values
# Security sensitivity
# Example format
# Which environments use it
#
# The following structure can serve as machine-readable metadata.

configuration_schema = {
    "SERVICE_PORT": {
        "type": "integer",
        "required": False,
        "default": 8000,
        "minimum": 1,
        "maximum": 65535,
        "secret": False,
    },
    "SERVICE_DEBUG": {
        "type": "boolean",
        "required": False,
        "default": False,
        "secret": False,
    },
    "DATABASE_URL": {
        "type": "url",
        "required": True,
        "default": None,
        "secret": True,
    },
}

print(json.dumps(configuration_schema, indent=2))


# ============================================================================
# 69. CONFIGURATION CHECKER
# ============================================================================

print("\n" + "=" * 80)
print("69. CONFIGURATION CHECKER")
print("=" * 80)


def check_required_variables(
    names: list[str],
) -> list[str]:
    """
    Return missing or empty required environment variable names.
    """
    missing: list[str] = []

    for name in names:
        value = os.getenv(name)

        if value is None or not value.strip():
            missing.append(name)

    return missing


with temporary_environment(
    {
        "REQUIRED_A": "value-a",
        "REQUIRED_B": "",
    }
):
    missing = check_required_variables(
        ["REQUIRED_A", "REQUIRED_B", "REQUIRED_C"]
    )

print("Missing required variables:", missing)


# ============================================================================
# 70. ENVIRONMENT VARIABLE DEPENDENCY ON EXTERNAL SERVICES
# ============================================================================

print("\n" + "=" * 80)
print("70. EXTERNAL SERVICE CONFIGURATION")
print("=" * 80)

# Environment variables can configure external dependencies without changing
# application source:
#
# CACHE_HOST
# CACHE_PORT
# DATABASE_URL
# MESSAGE_QUEUE_URL
# API_BASE_URL

with temporary_environment(
    {
        "CACHE_HOST": "localhost",
        "CACHE_PORT": "6379",
    }
):
    cache_host = os.getenv("CACHE_HOST", "localhost")
    cache_port = parse_positive_integer(
        os.getenv("CACHE_PORT", "6379"),
        name="CACHE_PORT",
        minimum=1,
        maximum=65535,
    )

    print("Cache host:", cache_host)
    print("Cache port:", cache_port)


# ============================================================================
# 71. ENVIRONMENT VARIABLES AND LOGGING
# ============================================================================

print("\n" + "=" * 80)
print("71. LOGGING CONFIGURATION")
print("=" * 80)


def parse_log_level(value: str) -> str:
    """Validate a logging level."""
    normalized = value.strip().upper()

    allowed = {
        "DEBUG",
        "INFO",
        "WARNING",
        "ERROR",
        "CRITICAL",
    }

    if normalized not in allowed:
        raise ValueError(
            f"Invalid log level: {value!r}"
        )

    return normalized


for level in ("debug", "INFO", "warning"):
    print(level, "->", parse_log_level(level))


# ============================================================================
# 72. ENVIRONMENT VARIABLES AND FEATURE FLAGS
# ============================================================================

print("\n" + "=" * 80)
print("72. FEATURE FLAGS")
print("=" * 80)

with temporary_environment(
    {
        "FEATURE_NEW_SEARCH": "true",
        "FEATURE_NEW_REPORTS": "false",
    }
):
    new_search_enabled = parse_boolean(
        os.getenv("FEATURE_NEW_SEARCH", "false")
    )

    new_reports_enabled = parse_boolean(
        os.getenv("FEATURE_NEW_REPORTS", "false")
    )

    print("New search:", new_search_enabled)
    print("New reports:", new_reports_enabled)


# ============================================================================
# 73. FEATURE FLAG DEFAULTS
# ============================================================================

print("\n" + "=" * 80)
print("73. SAFE FEATURE FLAG DEFAULTS")
print("=" * 80)

# A security-sensitive or unfinished feature often should default to disabled.
# The correct default depends on the application and risk profile.

def feature_enabled(
    name: str,
    *,
    default: bool = False,
) -> bool:
    """Read a boolean feature flag with a controlled default."""
    raw_value = os.getenv(name)

    if raw_value is None:
        return default

    return parse_boolean(raw_value)


print(
    "Unknown feature:",
    feature_enabled("FEATURE_UNKNOWN"),
)


# ============================================================================
# 74. ENVIRONMENT VARIABLES AND TIMEOUTS
# ============================================================================

print("\n" + "=" * 80)
print("74. TIMEOUT CONFIGURATION")
print("=" * 80)


def get_timeout(
    name: str,
    default: float,
) -> float:
    """Read a non-negative timeout."""
    value = os.getenv(name)

    if value is None:
        return default

    timeout = parse_float(
        value,
        name=name,
        minimum=0,
    )

    return timeout


with temporary_environment(
    {"HTTP_TIMEOUT": "10.5"}
):
    print(
        "HTTP timeout:",
        get_timeout("HTTP_TIMEOUT", 5.0),
    )


# ============================================================================
# 75. EDGE CASE: ZERO TIMEOUT
# ============================================================================

print("\n" + "=" * 80)
print("75. EDGE CASE: ZERO")
print("=" * 80)

# Whether zero is meaningful depends on the setting.
# For some APIs, zero can mean "disable", "immediate", or "no wait".
# For others, it is invalid.
#
# Validation must therefore reflect application semantics rather than merely
# using generic numeric conversion.

with temporary_environment(
    {"TIMEOUT_EDGE_CASE": "0"}
):
    print(
        "Zero timeout parsed as:",
        get_timeout("TIMEOUT_EDGE_CASE", 5.0),
    )


# ============================================================================
# 76. EDGE CASE: NEGATIVE VALUES
# ============================================================================

print("\n" + "=" * 80)
print("76. EDGE CASE: NEGATIVE VALUES")
print("=" * 80)

with temporary_environment(
    {"POSITIVE_SETTING": "-1"}
):
    try:
        parse_positive_integer(
            os.getenv("POSITIVE_SETTING", ""),
            name="POSITIVE_SETTING",
            minimum=1,
        )
    except ValueError as error:
        print("Negative value rejected:", error)


# ============================================================================
# 77. EDGE CASE: INVALID UNICODE OR ENCODING
# ============================================================================

print("\n" + "=" * 80)
print("77. ENCODING CONSIDERATIONS")
print("=" * 80)

# Python exposes environment values as strings. Underlying operating-system
# encoding and process-launch behavior still matter for portability.
#
# Applications exchanging configuration with external systems should use
# consistent encoding assumptions.

os.environ["UNICODE_SETTING"] = "café-日本-भारत"

print("Unicode setting:", os.getenv("UNICODE_SETTING"))


# ============================================================================
# 78. EDGE CASE: VARIABLE NAME COLLISIONS
# ============================================================================

print("\n" + "=" * 80)
print("78. VARIABLE NAME COLLISIONS")
print("=" * 80)

# Generic names such as PORT or DEBUG can conflict conceptually with other
# tools. Application prefixes reduce ambiguity.

os.environ["INVENTORY_APP_PORT"] = "9000"
os.environ["PAYMENTS_APP_PORT"] = "9001"

print("Inventory port:", os.getenv("INVENTORY_APP_PORT"))
print("Payments port:", os.getenv("PAYMENTS_APP_PORT"))


# ============================================================================
# 79. ENVIRONMENT VARIABLES ARE NOT A DATABASE
# ============================================================================

print("\n" + "=" * 80)
print("79. CONFIGURATION VERSUS APPLICATION STATE")
print("=" * 80)

# Environment variables are appropriate for startup configuration.
#
# They are usually not appropriate for:
# - frequently changing application state
# - large datasets
# - user records
# - transactional data
# - durable counters
#
# Changing os.environ in a running process does not automatically reconfigure
# every component that previously read and cached a value.

os.environ["RUNTIME_MODE"] = "initial"

cached_runtime_mode = os.getenv("RUNTIME_MODE")

os.environ["RUNTIME_MODE"] = "changed"

print("Cached value:", cached_runtime_mode)
print("Current environment value:", os.getenv("RUNTIME_MODE"))


# ============================================================================
# 80. STARTUP-TIME CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("80. STARTUP CONFIGURATION")
print("=" * 80)

# A common pattern is:
#
#   process starts
#       |
#       v
#   read environment
#       |
#       v
#   parse values
#       |
#       v
#   validate configuration
#       |
#       v
#   create application
#       |
#       v
#   run
#
# This makes configuration errors visible before the application starts
# handling real requests.

print("Configuration should normally be loaded and validated during startup.")


# ============================================================================
# 81. CACHING CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("81. CACHING CONFIGURATION")
print("=" * 80)

# Loading configuration once can avoid repeated parsing.
#
# The trade-off is that changes to the process environment after startup will
# not automatically appear in the cached object.

with temporary_environment(
    {
        "SERVICE_PORT": "8100",
        "SERVICE_ENV": "development",
        "SERVICE_HOST": "127.0.0.1",
        "SERVICE_DEBUG": "false",
        "SERVICE_WORKERS": "1",
        "SERVICE_ALLOWED_ORIGINS": "http://localhost",
    }
):
    startup_config = load_service_config()

print("Cached startup port:", startup_config.port)


# ============================================================================
# 82. THREADING AND ENVIRONMENT MUTATION
# ============================================================================

print("\n" + "=" * 80)
print("82. GLOBAL PROCESS STATE")
print("=" * 80)

# os.environ is process-wide mutable state.
#
# Frequent mutation from different parts of a multithreaded application can
# make behavior difficult to reason about.
#
# Prefer loading configuration once and passing an immutable configuration
# object to components.

print(
    "Application configuration is easier to reason about when treated as "
    "immutable after startup."
)


# ============================================================================
# 83. CONFIGURATION OBJECT DEPENDENCY INJECTION
# ============================================================================

print("\n" + "=" * 80)
print("83. PASSING CONFIGURATION EXPLICITLY")
print("=" * 80)


def build_service_address(config: ServiceConfig) -> str:
    """Build an address from explicit configuration."""
    return f"{config.host}:{config.port}"


with temporary_environment(
    {
        "SERVICE_NAME": "ExplicitConfigDemo",
        "SERVICE_ENV": "development",
        "SERVICE_HOST": "127.0.0.1",
        "SERVICE_PORT": "8200",
        "SERVICE_DEBUG": "false",
        "SERVICE_WORKERS": "1",
        "SERVICE_ALLOWED_ORIGINS": "http://localhost",
    }
):
    explicit_config = load_service_config()

print(
    "Service address:",
    build_service_address(explicit_config),
)


# ============================================================================
# 84. AVOIDING HIDDEN GLOBAL CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("84. EXPLICIT DEPENDENCIES")
print("=" * 80)

# This is easier to test:
#
#     function(config)
#
# than code that repeatedly calls:
#
#     os.getenv(...)
#
# throughout business logic.
#
# Environment access should usually be concentrated near application startup.

print(
    "A useful design is to read environment variables at the configuration "
    "boundary and pass typed values inward."
)


# ============================================================================
# 85. ENVIRONMENT VARIABLE SECURITY CHECKLIST
# ============================================================================

print("\n" + "=" * 80)
print("85. SECURITY CHECKS")
print("=" * 80)

security_principles = [
    "Do not hard-code production credentials in source code.",
    "Do not print secrets in logs.",
    "Do not expose complete environment dumps in diagnostic endpoints.",
    "Validate all environment values.",
    "Use least privilege for credentials.",
    "Protect deployment systems that can inject environment variables.",
    "Avoid insecure PATH entries in privileged processes.",
    "Prefer argument lists over shell command strings.",
    "Use dedicated secret-management facilities when stronger protection is required.",
]

for principle in security_principles:
    print("-", principle)


# ============================================================================
# 86. CONFIGURATION ANTI-PATTERNS
# ============================================================================

print("\n" + "=" * 80)
print("86. COMMON ANTI-PATTERNS")
print("=" * 80)

anti_patterns = {
    "Hard-coded secret": "Credential embedded directly in source code.",
    "Unvalidated integer": "Calling int() without checking range or meaning.",
    "Boolean truthiness": "Treating any non-empty string as True.",
    "Environment dump": "Logging all environment variables indiscriminately.",
    "PATH replacement": "Overwriting PATH and losing required executables.",
    "Scattered getenv calls": "Reading configuration unpredictably throughout business logic.",
    "Mutable global config": "Changing configuration during normal application execution.",
    "Huge environment blobs": "Using environment variables for large datasets.",
}

for name, explanation in anti_patterns.items():
    print(f"{name}: {explanation}")


# ============================================================================
# 87. CORRECT BOOLEAN VERSUS INCORRECT BOOLEAN PARSING
# ============================================================================

print("\n" + "=" * 80)
print("87. BOOLEAN PARSING COMPARISON")
print("=" * 80)

# Incorrect:
#
#     bool("false")
#
# This produces True because every non-empty string is truthy.
#
# Correct:
# explicitly interpret the textual representation.

print('bool("false"):', bool("false"))
print('parse_boolean("false"):', parse_boolean("false"))


# ============================================================================
# 88. PATH COMPARISON WITH SHUTIL.WHICH
# ============================================================================

print("\n" + "=" * 80)
print("88. PATH LOOKUP COMPARISON")
print("=" * 80)

# Manual PATH processing can tell you which directories exist in PATH, but
# shutil.which() performs command resolution according to Python's platform
# behavior.

first_path_entry = (
    cleaned_path_entries[0]
    if cleaned_path_entries
    else "<PATH is empty>"
)

print("First PATH entry:", first_path_entry)
print("Python command:", shutil.which("python"))
print("Python executable:", sys.executable)


# ============================================================================
# 89. TEMPORARY ENVIRONMENT IN TESTS
# ============================================================================

print("\n" + "=" * 80)
print("89. TESTING MULTIPLE CONFIGURATIONS")
print("=" * 80)


def service_workers_from_environment() -> int:
    """Return validated worker count."""
    return parse_positive_integer(
        os.getenv("SERVICE_WORKERS", "1"),
        name="SERVICE_WORKERS",
        minimum=1,
        maximum=256,
    )


test_cases = [
    ("1", 1),
    ("4", 4),
    ("16", 16),
]

for raw_value, expected in test_cases:
    with temporary_environment(
        {"SERVICE_WORKERS": raw_value}
    ):
        actual = service_workers_from_environment()
        assert actual == expected
        print(
            f"SERVICE_WORKERS={raw_value!r} -> {actual}"
        )


# ============================================================================
# 90. TESTING INVALID CONFIGURATION
# ============================================================================

print("\n" + "=" * 80)
print("90. INVALID CONFIGURATION TEST CASES")
print("=" * 80)

invalid_values = [
    "zero",
    "-1",
    "1.5",
    "",
]

for invalid_value in invalid_values:
    with temporary_environment(
        {"INVALID_WORKER_SETTING": invalid_value}
    ):
        try:
            parse_positive_integer(
                os.getenv("INVALID_WORKER_SETTING", ""),
                name="INVALID_WORKER_SETTING",
                minimum=1,
            )
        except ValueError:
            print(
                repr(invalid_value),
                "correctly rejected",
            )


# ============================================================================
# 91. ENVIRONMENT VARIABLE PRIORITY DEMONSTRATION
# ============================================================================

print("\n" + "=" * 80)
print("91. PRECEDENCE EXAMPLE")
print("=" * 80)


def resolve_setting(
    *,
    command_line: str | None,
    environment: str | None,
    config_file: str | None,
    default: str,
) -> tuple[str, str]:
    """
    Return the selected value and its source.

    Precedence:
        command line > environment > configuration file > default
    """
    if command_line is not None:
        return command_line, "command line"

    if environment is not None:
        return environment, "environment"

    if config_file is not None:
        return config_file, "configuration file"

    return default, "default"


value, source = resolve_setting(
    command_line=None,
    environment="production",
    config_file="staging",
    default="development",
)

print("Resolved value:", value)
print("Source:", source)


# ============================================================================
# 92. PORTABLE PATH HANDLING
# ============================================================================

print("\n" + "=" * 80)
print("92. PORTABLE PATH HANDLING")
print("=" * 80)

# Never assume ":" is the PATH separator on every operating system.
#
# Use os.pathsep:
#   ":" on Unix-like systems
#   ";" on Windows

print("Platform PATH separator:", os.pathsep)


# ============================================================================
# 93. EXECUTABLE FILE EXTENSIONS
# ============================================================================

print("\n" + "=" * 80)
print("93. EXECUTABLE RESOLUTION")
print("=" * 80)

# Windows executable resolution may consider extensions listed by PATHEXT.
# shutil.which() abstracts much of this platform-specific behavior.

print("PATHEXT:", os.getenv("PATHEXT"))
print("Resolved Python:", shutil.which("python"))


# ============================================================================
# 94. ENVIRONMENT VARIABLES AND CURRENT DIRECTORY
# ============================================================================

print("\n" + "=" * 80)
print("94. CURRENT DIRECTORY")
print("=" * 80)

# The current working directory is process state related to, but distinct from,
# environment variables.
#
# Some programs use PWD on Unix-like systems, but os.getcwd() is the reliable
# Python API for the actual current working directory.

print("os.getcwd():", os.getcwd())
print("PWD:", os.getenv("PWD"))


# ============================================================================
# 95. CONFIGURATION SNAPSHOT FOR SAFE OBSERVABILITY
# ============================================================================

print("\n" + "=" * 80)
print("95. SAFE CONFIGURATION SNAPSHOT")
print("=" * 80)


def safe_configuration_snapshot(
    names: list[str],
) -> dict[str, str]:
    """
    Produce a diagnostic snapshot with sensitive values redacted.
    """
    return {
        name: redact_environment_value(
            name,
            os.getenv(name),
        )
        for name in names
    }


snapshot = safe_configuration_snapshot(
    [
        "APPLICATION_ENV",
        "APPLICATION_PORT",
        "LOG_LEVEL",
        "DATABASE_URL",
        "DEMO_API_KEY",
    ]
)

for key, value in snapshot.items():
    print(f"{key}: {value}")


# ============================================================================
# 96. ENVIRONMENT VARIABLES AND REPRODUCIBILITY
# ============================================================================

print("\n" + "=" * 80)
print("96. REPRODUCIBILITY")
print("=" * 80)

# Environment-dependent applications can behave differently on two machines
# even when their source code is identical.
#
# Reproducibility improves when:
# - configuration is documented
# - required variables are validated
# - defaults are explicit
# - configuration versions are controlled
# - deployment environments are consistent
# - diagnostics show non-sensitive configuration

print(
    "Source code alone may not fully describe an application's runtime "
    "behavior when environment variables affect configuration."
)


# ============================================================================
# 97. ENVIRONMENT VARIABLE CONTRACT
# ============================================================================

print("\n" + "=" * 80)
print("97. CONFIGURATION CONTRACT")
print("=" * 80)

# A configuration contract specifies exactly what the application expects.

configuration_contract = [
    {
        "name": "SERVICE_ENV",
        "type": "enum",
        "required": False,
        "default": "development",
        "allowed": [
            "development",
            "testing",
            "staging",
            "production",
        ],
    },
    {
        "name": "SERVICE_PORT",
        "type": "integer",
        "required": False,
        "default": 8000,
        "range": "1..65535",
    },
    {
        "name": "SERVICE_DEBUG",
        "type": "boolean",
        "required": False,
        "default": False,
    },
]

for item in configuration_contract:
    print(json.dumps(item))


# ============================================================================
# 98. STARTUP VALIDATION FUNCTION
# ============================================================================

print("\n" + "=" * 80)
print("98. STARTUP VALIDATION")
print("=" * 80")


def validate_startup_environment() -> None:
    """
    Validate a minimal production-style environment contract.
    """
    required_names = [
        "SERVICE_NAME",
    ]

    missing = check_required_variables(required_names)

    if missing:
        raise RuntimeError(
            "Missing required environment variables: "
            + ", ".join(missing)
        )

    config = load_service_config()
    validate_service_relationships(config)


with temporary_environment(
    {
        "SERVICE_NAME": "StartupValidationDemo",
        "SERVICE_ENV": "development",
        "SERVICE_HOST": "127.0.0.1",
        "SERVICE_PORT": "8000",
        "SERVICE_DEBUG": "false",
        "SERVICE_WORKERS": "1",
        "SERVICE_ALLOWED_ORIGINS": "http://localhost",
    }
):
    validate_startup_environment()

print("Startup validation succeeded.")


# ============================================================================
# 99. PRODUCTION DESIGN PRINCIPLES
# ============================================================================

print("\n" + "=" * 80)
print("99. PRODUCTION DESIGN PRINCIPLES")
print("=" * 80)

production_principles = [
    "Centralize environment-variable loading.",
    "Convert strings into explicit application types.",
    "Validate values before starting the service.",
    "Use safe defaults for non-sensitive optional settings.",
    "Require critical settings explicitly.",
    "Do not expose secrets through logs or diagnostics.",
    "Keep configuration immutable after startup where practical.",
    "Document every supported environment variable.",
    "Use prefixes to avoid naming collisions.",
    "Treat environment values as untrusted input.",
    "Avoid using environment variables for large or mutable application state.",
    "Protect PATH and executable resolution in privileged contexts.",
]

for principle in production_principles:
    print("-", principle)


# ============================================================================
# 100. FINAL INTEGRATED EXAMPLE
# ============================================================================

print("\n" + "=" * 80)
print("100. INTEGRATED APPLICATION CONFIGURATION EXAMPLE")
print("=" * 80)


@dataclass(frozen=True)
class ProductionReadyConfig:
    """
    Example of a complete, immutable application configuration.
    """

    app_name: str
    environment: str
    host: str
    port: int
    debug: bool
    log_level: str
    workers: int
    timeout_seconds: float
    database_url: str
    allowed_origins: tuple[str, ...]


def load_production_ready_config() -> ProductionReadyConfig:
    """
    Read all configuration from environment variables and validate it.

    The function deliberately avoids printing secrets.
    """
    app_name = get_required_environment_variable(
        "APP_NAME"
    )

    environment = parse_environment_name(
        os.getenv("APP_ENV", "development")
    )

    host = os.getenv(
        "APP_HOST",
        "127.0.0.1",
    ).strip()

    if not host:
        raise ValueError("APP_HOST cannot be empty.")

    port = parse_positive_integer(
        os.getenv("APP_PORT", "8000"),
        name="APP_PORT",
        minimum=1,
        maximum=65535,
    )

    debug = parse_boolean(
        os.getenv("APP_DEBUG", "false")
    )

    log_level = parse_log_level(
        os.getenv("LOG_LEVEL", "INFO")
    )

    workers = parse_positive_integer(
        os.getenv("APP_WORKERS", "1"),
        name="APP_WORKERS",
        minimum=1,
        maximum=256,
    )

    timeout_seconds = get_timeout(
        "APP_TIMEOUT",
        default=10.0,
    )

    database_url = get_required_environment_variable(
        "DATABASE_URL"
    )

    allowed_origins = tuple(
        parse_csv(
            os.getenv(
                "ALLOWED_ORIGINS",
                "http://localhost",
            )
        )
    )

    if environment == "production" and debug:
        raise ValueError(
            "APP_DEBUG must be false in production."
        )

    if environment == "production" and (
        not database_url.startswith("postgresql://")
        and not database_url.startswith("postgres://")
    ):
        raise ValueError(
            "Production database URL must use PostgreSQL "
            "in this example."
        )

    if timeout_seconds <= 0:
        raise ValueError(
            "APP_TIMEOUT must be greater than zero."
        )

    return ProductionReadyConfig(
        app_name=app_name,
        environment=environment,
        host=host,
        port=port,
        debug=debug,
        log_level=log_level,
        workers=workers,
        timeout_seconds=timeout_seconds,
        database_url=database_url,
        allowed_origins=allowed_origins,
    )


with temporary_environment(
    {
        "APP_NAME": "ProductionReadyDemo",
        "APP_ENV": "production",
        "APP_HOST": "0.0.0.0",
        "APP_PORT": "8443",
        "APP_DEBUG": "false",
        "LOG_LEVEL": "INFO",
        "APP_WORKERS": "4",
        "APP_TIMEOUT": "15",
        "DATABASE_URL": (
            "postgresql://service_user:secret@db.example.com:5432/app"
        ),
        "ALLOWED_ORIGINS": "https://example.com,https://admin.example.com",
    }
):
    production_ready_config = load_production_ready_config()

    # Print only non-sensitive configuration.
    print("Application name:", production_ready_config.app_name)
    print("Environment:", production_ready_config.environment)
    print("Host:", production_ready_config.host)
    print("Port:", production_ready_config.port)
    print("Debug:", production_ready_config.debug)
    print("Log level:", production_ready_config.log_level)
    print("Workers:", production_ready_config.workers)
    print(
        "Timeout:",
        production_ready_config.timeout_seconds,
    )
    print(
        "Database configured:",
        bool(production_ready_config.database_url),
    )
    print(
        "Allowed origins:",
        production_ready_config.allowed_origins,
    )


# ============================================================================
# 101. KEY RELATIONSHIPS
# ============================================================================

print("\n" + "=" * 80)
print("101. KEY RELATIONSHIPS")
print("=" * 80)

relationships = [
    "Environment variable -> string supplied to a process.",
    "os.environ -> mutable mapping of the current process environment.",
    "os.getenv() -> convenient read operation with optional default.",
    "PATH -> environment variable used for executable discovery.",
    "shutil.which() -> Python API for locating an executable through PATH.",
    "Parent process -> normally supplies an environment to child processes.",
    "Child process -> receives a copy and cannot modify the parent's environment.",
    "Configuration loader -> converts raw strings into typed application settings.",
    "Validation -> prevents malformed configuration from reaching application logic.",
    "Immutable config -> reduces accidental runtime configuration mutation.",
]

for relationship in relationships:
    print("-", relationship)


# ============================================================================
# 102. FINAL PRACTICAL DEMONSTRATION
# ============================================================================

print("\n" + "=" * 80)
print("102. PRACTICAL DEMONSTRATION")
print("=" * 80)

with temporary_environment(
    {
        "DEMO_APP_NAME": "EnvironmentConfiguredApp",
        "DEMO_APP_PORT": "5000",
        "DEMO_APP_DEBUG": "false",
        "DEMO_APP_ENV": "development",
    }
):
    demo_name = os.getenv(
        "DEMO_APP_NAME",
        "UnnamedApplication",
    )

    demo_port = parse_positive_integer(
        os.getenv("DEMO_APP_PORT", "8000"),
        name="DEMO_APP_PORT",
        minimum=1,
        maximum=65535,
    )

    demo_debug = parse_boolean(
        os.getenv("DEMO_APP_DEBUG", "false")
    )

    demo_environment = parse_environment_name(
        os.getenv("DEMO_APP_ENV", "development")
    )

    print("Name:", demo_name)
    print("Port:", demo_port)
    print("Debug:", demo_debug)
    print("Environment:", demo_environment)

print("\nEnvironment variable tutorial completed successfully.")
