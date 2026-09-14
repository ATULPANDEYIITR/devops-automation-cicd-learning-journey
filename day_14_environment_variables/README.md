# Environment Variables

## Introduction

Environment variables are named values made available to a running process by the operating system or its parent process. They provide a way to supply configuration without embedding every runtime setting directly into application source code.

Common environment variables include `PATH`, `HOME`, `USER`, `TEMP`, `PYTHONPATH`, and application-specific settings such as `APP_ENV`, `APP_PORT`, `DATABASE_URL`, `LOG_LEVEL`, and `API_KEY`.

The accompanying Python script develops the subject from basic environment-variable access through configuration parsing, `PATH` handling, subprocess inheritance, testing, validation, security, and production-oriented configuration design.

A central idea is that environment variables are fundamentally string values. An application is responsible for interpreting those strings as integers, booleans, floating-point values, lists, URLs, enumerations, or other types.

## Environment variables and processes

An environment belongs to a process. When a program starts, it receives an environment from its parent process. Python exposes the environment through `os.environ`.

The following two operations have different behavior:

- `os.environ["NAME"]` requires the variable to exist and raises `KeyError` when it does not.
- `os.getenv("NAME")` returns `None` when the variable does not exist.
- `os.getenv("NAME", "default")` supplies a fallback value.

The environment visible to a Python program is not the same thing as the entire operating system's permanent configuration.

When Python changes `os.environ`, it changes the environment of the current process. That change normally does not modify the parent shell and does not become a permanent system-wide setting.

## Environment variables are strings

Environment variables do not inherently carry Python types.

For example, a variable containing `8000` is received by Python as the string `"8000"`. If the application requires an integer, it must explicitly perform the conversion.

Typical conversions include:

- `int(value)` for integers
- `float(value)` for floating-point values
- custom parsing for booleans
- `split(",")` for simple comma-separated lists
- `json.loads(value)` for structured JSON
- URL parsing for connection strings and service endpoints

Conversion and validation should normally happen at the configuration boundary rather than throughout application logic.

## Missing values and empty values

A missing environment variable and an empty environment variable are different states.

If `MISSING_SETTING` does not exist:

`os.getenv("MISSING_SETTING")` returns `None`.

If it exists but has an empty value:

`os.getenv("EMPTY_SETTING")` returns `""`.

Applications should define whether an empty string is acceptable. For required settings such as credentials or service identifiers, treating an empty string as invalid is usually appropriate.

## Setting and deleting variables

Python can create or change a variable with `os.environ`:

`os.environ["APP_ENV"] = "development"`

Because environment values are strings, numeric values should be converted to strings before assignment.

Variables can be deleted with `del os.environ["NAME"]` or removed safely with `os.environ.pop("NAME", None)`.

These modifications affect the current process. They should not be confused with permanently setting variables in a user's shell or operating-system account.

## Shell variables versus environment variables

Shells can maintain variables internally.

In Unix-like shells, a shell variable can be created with a form such as:

`NAME=value`

Exporting it makes it available to child processes:

`export NAME=value`

The distinction is important because a child program such as Python only receives variables that are part of its process environment.

Shell syntax differs across environments. Windows Command Prompt, PowerShell, Bash, Zsh, and other shells have different commands and conventions.

The Python program itself should generally depend on the environment it receives rather than on a particular shell's syntax.

## PATH

`PATH` is a special and widely used environment variable containing directories in which executable commands are searched.

For example, when a user types a command such as `python` or `git`, the command interpreter can search the directories listed in `PATH` to locate the corresponding executable.

The separator is platform-dependent:

- Unix-like systems commonly use `:`
- Windows commonly uses `;`

Python exposes the correct separator through `os.pathsep`.

The script demonstrates splitting `PATH`, inspecting entries, and resolving executable locations with `shutil.which()`.

## PATH order

The order of directories in `PATH` matters.

If several directories contain an executable with the same command name, the search process can select the first matching executable according to the platform's command-resolution rules.

This is important when a machine contains:

- multiple Python installations
- multiple Java versions
- several Node.js versions
- system and user-installed tools
- virtual environments
- development toolchains

Unexpected PATH order is a common reason that a command appears to use the wrong version.

## PATH modification

A program should not casually replace the complete `PATH` value.

Replacing `PATH` can make standard commands unavailable and can create difficult-to-debug failures.

When a directory needs to be added, it can be placed before or after the existing entries using `os.pathsep`.

Prepending a directory gives it higher priority during command lookup. Appending it generally gives existing directories priority.

PATH manipulation should be deliberate because command resolution can have security implications.

## Executable discovery with shutil.which

Python's `shutil.which()` searches for an executable using PATH-related rules.

This is preferable to manually guessing executable locations when portable command discovery is required.

`sys.executable` provides another important piece of information: it identifies the Python interpreter that is currently running the program.

The distinction is useful because `shutil.which("python")` identifies a command found through executable search, while `sys.executable` identifies the interpreter actually executing the current process.

## Process inheritance

Child processes normally inherit a copy of their parent's environment.

The Python script demonstrates this with `subprocess.run()`.

If the parent process contains:

`PARENT_DEMO_VARIABLE=visible-to-child`

a child process can normally read that value.

The reverse does not occur. If a child modifies its own environment, the modification does not propagate back into the already-running parent.

This follows from process isolation. Each process has its own environment state.

## Custom environments for subprocesses

`subprocess.run()` accepts an `env` argument.

A common pattern is:

`child_environment = os.environ.copy()`

followed by specific changes:

`child_environment["WORKER_ROLE"] = "background-worker"`

The modified mapping is then supplied to the child process.

Copying the existing environment is often safer than constructing a completely empty environment because programs may rely on variables such as PATH.

A custom environment is useful when different subprocesses require different configuration.

## Temporary environment changes

Environment variables are process-wide mutable state. Tests and demonstrations that modify them can accidentally affect later code.

The script defines a `temporary_environment()` context manager. It records original values, applies temporary values, and restores the previous state after the context exits.

This pattern is particularly useful for testing configuration-dependent functions.

It also makes configuration experiments safer because changes do not remain active after the controlled block.

## Configuration through environment variables

One of the most important uses of environment variables is runtime configuration.

An application can use the same source code while receiving different settings in different environments.

For example:

Development may use a local database and debugging enabled.

Testing may use an isolated database and deterministic settings.

Staging may use infrastructure similar to production.

Production may use strict security settings, production services, and controlled logging.

The application code does not need to contain separate copies of the application for each environment.

## Defaults

Optional settings often have defaults.

For example:

`LOG_LEVEL` can default to `INFO`.

`APP_HOST` can default to `127.0.0.1`.

`APP_PORT` can default to `8000`.

Defaults should be chosen carefully. A default is part of the application's behavior and should not accidentally create an insecure production configuration.

Security-sensitive settings should not receive weak or surprising defaults merely for convenience.

## Required variables

Some settings should be mandatory.

Examples include:

- production database credentials
- required API credentials
- encryption keys
- mandatory service endpoints
- identifiers needed for external integrations

The script implements a required-variable function that rejects both missing and empty values.

Failing early during application startup is preferable to allowing a missing credential to cause a much less understandable error later during a request.

## Boolean configuration

Boolean environment variables require special attention.

Environment variables are strings, so this is incorrect:

`bool("false")`

It evaluates to `True` because the string is non-empty.

A configuration system should explicitly define accepted representations. The script accepts values such as:

- `true`
- `false`
- `1`
- `0`
- `yes`
- `no`
- `on`
- `off`

Unrecognized values are rejected instead of silently producing an unexpected result.

## Numeric configuration

Integer and floating-point settings should be converted and validated.

A port is not merely an integer. It also has a valid range, normally from 1 through 65535 for a TCP or UDP port.

A worker count may require a minimum of one and a reasonable maximum.

A timeout may require a non-negative value, although whether zero is meaningful depends on the application's semantics.

The script separates parsing from validation so that the application can produce explicit configuration errors.

## Enumerated configuration

Some settings should only accept values from a known set.

An application environment may be restricted to:

- `development`
- `testing`
- `staging`
- `production`

A logging level may be restricted to:

- `DEBUG`
- `INFO`
- `WARNING`
- `ERROR`
- `CRITICAL`

Normalizing case before validation allows values such as `Production` to be interpreted consistently as `production`.

Restricting values prevents silent acceptance of misspelled configuration.

## List configuration

A simple environment-variable convention for lists is comma-separated text.

For example:

`ALLOWED_HOSTS=localhost,127.0.0.1,example.com`

The application can split the string and remove surrounding whitespace.

The script uses a `parse_csv()` function that also ignores empty items.

For complex structured configuration, a formal representation such as JSON may be more appropriate.

## JSON configuration

Environment variables are strings, but the string can contain JSON.

For example, feature flags can be represented as a JSON object.

This is useful for small structured settings but should not be used indiscriminately. Very large JSON configuration stored in an environment variable becomes difficult to inspect, validate, maintain, and transport safely.

The script uses `json.loads()` and verifies that the result is a dictionary.

## URL configuration

Service endpoints and connection strings are often supplied through environment variables.

Examples include:

- `DATABASE_URL`
- `API_BASE_URL`
- `CACHE_URL`
- `MESSAGE_QUEUE_URL`

The script demonstrates basic URL parsing with `urllib.parse.urlparse()`.

URL validation should reflect the application's requirements. Checking that a URL has an HTTP or HTTPS scheme and a host is useful, but it is not a complete security validation for every possible application.

## Database URLs

A database connection URL can contain sensitive information such as usernames and passwords.

For example, a database URL may contain:

`postgresql://user:password@host:5432/database`

The application may need the complete value internally, but diagnostic output should not expose it.

The script demonstrates extracting non-sensitive components and redacting the password before displaying a URL.

## Configuration objects

A strong configuration architecture converts raw environment strings into a typed configuration object.

The script uses Python `dataclass` definitions such as `ApplicationConfig`, `ServiceConfig`, and `ProductionReadyConfig`.

This approach creates a boundary:

Environment variables → parsing → validation → typed configuration → application logic

Business logic can then receive an explicit configuration object rather than repeatedly calling `os.getenv()`.

## Immutable configuration

The configuration dataclasses use `frozen=True`.

This makes configuration objects immutable after construction.

Immutable configuration reduces accidental runtime changes and makes dependencies easier to reason about.

Instead of modifying global environment state during normal application execution, an application can load configuration once and pass the resulting object to components that require it.

## Configuration precedence

Applications may have several configuration sources:

- built-in defaults
- configuration files
- environment variables
- command-line arguments

There is no universal precedence rule. The application must define one.

The script demonstrates:

Command line > environment variable > configuration file > default

The important principle is not that this exact ordering is mandatory. The important principle is that precedence should be explicit and predictable.

Environment variables are commonly used as a deployment-level override because they allow the same application artifact to run with different runtime settings.

## .env files

A `.env` file is a file containing environment-like configuration.

It is important to distinguish the file from the actual process environment.

Python does not automatically treat every `.env` file as `os.environ`. Development tools and third-party libraries can load such files and populate the process environment.

The script includes a small educational parser supporting simple assignments, comments, blank lines, and basic quoting.

It intentionally does not attempt to reproduce all shell syntax or every `.env` implementation.

## .env and source control

A common development arrangement is to keep local secrets in a `.env` file while providing a non-secret template such as `.env.example`.

The template can document:

- required variable names
- expected formats
- safe example values
- defaults

Real credentials should not be committed to source control merely because they are stored in a file named `.env`.

## Secrets

Environment variables are frequently used to provide secrets such as:

- API keys
- database passwords
- access tokens
- service credentials
- private configuration values

Using an environment variable can be safer than hard-coding a secret in source code because the credential is separated from the application source.

It does not mean that environment variables are automatically a secure secret-management system.

Depending on the operating system and infrastructure, environment values can potentially be exposed through process inspection, debugging mechanisms, crash reports, logs, deployment configuration, or child processes.

For higher-security requirements, dedicated secret-management systems and appropriate access controls may be necessary.

## Secret redaction

A major operational mistake is logging the entire environment.

The environment may contain passwords, access tokens, private keys, and other credentials.

The script implements a redaction approach that identifies names containing fragments such as:

- `PASSWORD`
- `SECRET`
- `TOKEN`
- `API_KEY`
- `PRIVATE_KEY`
- `CREDENTIAL`

The actual secret is replaced with `<REDACTED>` in diagnostics.

Name-based redaction is useful but should not be treated as a complete security mechanism. Sensitive values should be explicitly controlled and should never be logged simply because they happen to be available.

## CI/CD systems

Continuous integration and deployment systems commonly inject environment variables into build and deployment processes.

Examples can include:

- build identifiers
- deployment environments
- feature settings
- credentials
- API tokens

These values should still be validated by the application.

A deployment platform can provide the value, but the application should not assume that every value has the correct format or semantics.

Access to systems capable of injecting production environment variables should itself be tightly controlled.

## Containers

Containerized applications frequently receive configuration through environment variables.

The same container image can be deployed to different environments with different settings.

For example, one image can receive different:

- database URLs
- service ports
- logging levels
- feature flags
- API endpoints

This supports separation between application artifacts and deployment configuration.

Environment variables should not be treated as a replacement for secure secret-management systems when the deployment has stronger secret-protection requirements.

## Configuration validation

A robust configuration system performs four major tasks:

1. Load raw values.
2. Convert them into appropriate types.
3. Validate individual values.
4. Validate relationships between values.

For example:

`APP_PORT` can be checked as an integer in the valid port range.

`APP_ENV` can be checked against a fixed set of environments.

`APP_DEBUG` can be converted using explicit boolean rules.

A cross-field rule can reject debug mode when the environment is production.

This design prevents invalid combinations from reaching application logic.

## Cross-field validation

Some configuration rules involve multiple variables.

For example:

- Debugging may be forbidden in production.
- A production database may need a production-compatible scheme.
- Multiple workers may be incompatible with a particular debug mode.
- A service binding only to localhost may be unsuitable when external access is required.
- A timeout may need to be positive when a network client requires an actual waiting period.

These constraints cannot be validated by looking at one variable in isolation.

## Startup validation

Configuration errors should usually be detected during application startup.

A useful sequence is:

Load environment values.

Parse their types.

Validate individual values.

Validate cross-field relationships.

Construct an immutable configuration object.

Start the application.

This prevents an application from starting in an invalid state and discovering the problem only after receiving real traffic.

## Environment variables and application state

Environment variables are primarily appropriate for configuration, not general application state.

They are suitable for settings that are read when a process starts or when a controlled component requires them.

They are generally unsuitable for:

- user records
- transaction data
- large datasets
- frequently changing counters
- durable application state

Changing an environment variable in a running process also does not automatically update components that already read and cached the old value.

## Configuration caching

Loading configuration once can improve consistency and avoid repeatedly parsing environment variables.

The trade-off is that subsequent changes to `os.environ` will not automatically appear in the cached configuration object.

For most applications, immutable startup configuration is easier to reason about than dynamically changing global configuration.

If runtime reconfiguration is required, it should be designed explicitly rather than relying on incidental mutation of `os.environ`.

## Environment variables as global process state

`os.environ` is process-wide state.

Multiple components that modify it during normal execution can make an application difficult to understand and test.

A cleaner architecture is to access environment variables near the application boundary, validate them, and pass explicit configuration objects to components.

This reduces hidden dependencies.

A function that accepts `config` has a visible dependency. A function that silently calls `os.getenv()` can depend on global process state without making that dependency apparent.

## Testing environment-based configuration

Environment-dependent code requires isolated tests.

If one test sets:

`APP_PORT=9000`

and fails to restore the previous value, a later test may unexpectedly run with port 9000.

The `temporary_environment()` context manager in the script prevents this class of test contamination.

Good configuration tests should cover:

- missing variables
- empty values
- valid values
- invalid values
- boundary values
- invalid ranges
- case normalization
- defaults
- production-specific restrictions
- cross-field relationships

## Debugging environment variables

When a configuration problem occurs, useful diagnostics include:

- whether a variable exists
- whether it is empty
- the length of the value
- the selected configuration source
- the normalized non-sensitive value
- the resolved executable path

The actual secret should not be displayed merely to verify that it exists.

For PATH problems, `shutil.which()` is particularly useful because it shows which executable Python resolves through the current environment.

## PYTHONPATH

`PYTHONPATH` is an environment variable that can affect Python's module search path.

It can be useful in some development setups, but it can also make imports dependent on external process configuration.

The effective Python import search path can be inspected through `sys.path`.

For reproducible applications, unexpected dependencies on `PYTHONPATH` should be avoided or deliberately documented.

## Operating-system variables

Environment-variable names and availability vary by platform.

Examples include:

- `HOME` on Unix-like systems
- `USERPROFILE` on Windows
- `TEMP`
- `TMP`
- `PATH`
- `PATHEXT` on Windows

When Python provides a standard-library API for an operating-system concept, that API is often preferable to manually reading an environment variable.

For example, `Path.home()` is more portable than assuming that `HOME` exists.

Similarly, `tempfile.gettempdir()` is useful for obtaining a temporary directory without manually interpreting platform-specific variables.

## Case sensitivity

Environment-variable name case behavior differs between operating systems.

Unix-like systems generally treat names such as `APP_ENV` and `app_env` as different variables.

Windows environment-variable handling is generally case-insensitive.

For cross-platform applications, a consistent uppercase naming convention reduces ambiguity.

## Environment-variable size

Operating systems impose limits on environment size and process-launch parameters.

Exact limits differ by operating system and execution environment.

Environment variables are therefore best suited to reasonably small configuration values.

Large documents, datasets, certificates, or complicated configuration structures can become unwieldy when placed into environment variables.

## Unicode

Modern systems and Python generally support Unicode environment values.

Applications that exchange environment configuration across multiple operating systems or deployment tools should still account for encoding and process-launch behavior.

The script demonstrates a Unicode value containing Latin, Japanese, and Devanagari characters.

## Variable prefixes

Application-specific prefixes reduce naming collisions.

Instead of generic names such as:

`PORT`

an application can use:

`MYAPP_PORT`

A larger system may use:

`INVENTORY_APP_PORT`

and:

`PAYMENTS_APP_PORT`

Prefixes are especially useful on shared systems and in environments where many services expose their configuration together.

## Configuration contracts

A production application should have a clear configuration contract.

For every environment variable, documentation should specify:

- variable name
- data type
- required or optional status
- default value
- allowed values
- valid range
- whether it contains sensitive information
- expected format
- relevant deployment environments

The script represents this information as Python data structures.

This makes configuration behavior explicit rather than leaving requirements scattered across application code.

## Security considerations

Environment variables create several important security concerns.

### Secret exposure

Never print credentials, tokens, passwords, or private keys in logs.

Avoid diagnostic endpoints that return the complete process environment.

Do not include secrets in exception messages unnecessarily.

### PATH manipulation

PATH controls executable discovery. If an attacker can insert a malicious directory before trusted directories, command execution may resolve to an unintended executable.

This is especially important for privileged processes.

Security-sensitive programs should consider:

- absolute executable paths
- controlled PATH values
- avoiding writable directories in privileged PATH configurations
- careful subprocess invocation

### Shell injection

Passing untrusted text into a shell command can create command-injection vulnerabilities.

Python's `subprocess` API generally allows commands to be passed as argument lists, which avoids unnecessary shell parsing.

The script demonstrates argument-list invocation rather than constructing shell command strings from untrusted values.

### Deployment security

Systems capable of setting production environment variables can effectively influence application behavior.

Access to deployment configurations and secret injection mechanisms should therefore be protected.

### Least privilege

Credentials supplied through environment variables should have only the permissions required by the application.

Moving a password from source code to an environment variable does not make an over-privileged credential safe.

## Common mistakes

### Treating all strings as booleans

Using `bool("false")` produces `True`.

Boolean strings must be explicitly interpreted.

### Assuming every variable exists

Direct dictionary access can raise `KeyError`.

Required and optional variables should be handled deliberately.

### Ignoring empty strings

An existing but empty variable can be just as invalid as a missing variable for required settings.

### Skipping validation

`int()` confirms that a value is numeric but does not confirm that it is meaningful.

A port of `99999` is numeric but outside the valid TCP/UDP port range.

### Replacing PATH

Overwriting PATH can prevent required commands from being found.

### Printing the entire environment

This can expose credentials and other sensitive values.

### Scattering environment access

Calling `os.getenv()` throughout business logic creates hidden global dependencies.

### Mutating configuration during runtime

Frequent changes to process-wide environment state make behavior difficult to reason about, especially in multithreaded applications.

### Storing large application state in environment variables

Environment variables are not a general-purpose database or storage system.

### Depending on shell-specific behavior

Shell syntax varies across operating systems. Portable applications should not assume that a particular shell's syntax is universally available.

## Limitations

Environment variables have several limitations.

They are strings, so applications must implement type conversion.

They are process-level configuration rather than a durable storage mechanism.

They can be exposed through operating-system and deployment mechanisms.

Their size is constrained by operating-system and process-launch limits.

They are not inherently versioned.

They do not provide a universal configuration schema.

They do not automatically provide encryption or access control.

They are also not a substitute for proper secret-management infrastructure when sensitive credentials require stronger protection.

## Performance considerations

Reading an environment variable is generally inexpensive, but repeated parsing and validation can become unnecessary overhead if performed throughout a large application.

A practical design is to:

- read configuration during startup
- convert values once
- validate them once
- construct a typed configuration object
- pass that object to components

This also improves consistency because all components can operate on the same validated configuration.

The larger performance concern is usually not the environment lookup itself but inefficient configuration architecture and repeated parsing.

## Implementation considerations

A maintainable environment-based configuration system should have a clear boundary.

A useful architecture is:

Raw environment → parser → validator → immutable configuration → application components

Parsing should be responsible for converting representations.

Validation should be responsible for determining whether values are acceptable.

The configuration object should represent the final state that application code is allowed to use.

Business logic should not need to know whether a value came from an environment variable, configuration file, command-line argument, or default.

## Real-world applications

Environment variables are widely useful for:

- web-server ports
- application environments
- logging levels
- feature flags
- database connection information
- API endpoints
- cache configuration
- worker counts
- network timeouts
- cloud deployment settings
- CI/CD configuration
- container configuration
- development and testing overrides
- service discovery information

They are particularly useful when the same application artifact needs to run with different deployment configurations.

## Important distinction: configuration versus code

Environment variables allow runtime behavior to vary without changing application source code.

For example, a Python application can read:

`APP_PORT`

and use the supplied value.

The source code remains identical while development might provide `8000` and production might provide `443` or another deployment-specific port.

This separation improves deployment flexibility, but it also means that source code alone may not fully describe runtime behavior.

Configuration must therefore be documented and controlled as an important part of the application's operational environment.

## Important distinction: process environment versus permanent system configuration

A Python assignment such as:

`os.environ["APP_ENV"] = "production"`

changes the current process environment.

It does not mean that the operating system permanently changed the user's login environment.

Similarly, changing an environment variable inside a child process does not change the environment of its parent.

Persistent environment configuration is normally managed by the operating system, shell configuration, service manager, container platform, CI/CD system, or deployment infrastructure.

## Important distinction: environment variable versus .env file

An environment variable is part of the process environment.

A `.env` file is a file that contains configuration text.

A tool or library may read the file and place its values into the process environment, but the two concepts are not identical.

This distinction matters when debugging because a value existing in a `.env` file does not necessarily mean that a running process has received that value.

## Important distinction: PATH versus Python import path

`PATH` is primarily related to executable command discovery.

Python's module search path is represented by `sys.path` and can be influenced by mechanisms including `PYTHONPATH`.

They solve different problems.

`PATH` answers questions such as:

Which executable should run when a command name is supplied?

Python's import path answers questions such as:

Where should Python search for an importable module?

Confusing these two concepts can lead to incorrect debugging of Python installation and module-resolution problems.

## Advanced configuration design

A mature configuration system can support multiple sources while maintaining a predictable precedence policy.

For example:

Built-in defaults → configuration file → environment variables → command-line overrides

The exact ordering should be documented.

A configuration system can also include:

- schema validation
- immutable configuration objects
- startup checks
- secret redaction
- structured diagnostics
- environment-specific policies
- cross-field validation
- typed parsing
- test isolation
- configuration documentation

The important design principle is to treat configuration as a formal interface rather than as arbitrary strings read throughout the application.

## Production relevance

Production systems benefit from explicit configuration management because deployment environments differ while application artifacts should remain stable.

A production-ready environment configuration approach should:

- define required variables
- document optional variables
- validate all inputs
- use sensible defaults
- prevent insecure combinations
- protect credentials
- redact sensitive diagnostic output
- control executable lookup
- keep configuration immutable where practical
- test configuration independently
- make precedence rules explicit
- separate configuration from application state

The Python script demonstrates these principles through complete implementations rather than isolated syntax examples.
