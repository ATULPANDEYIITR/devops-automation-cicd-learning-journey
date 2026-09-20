<!-- File: README.md -->
# Linux system administration automation toolkit

## Project introduction

This repository is a Python-only toolkit for automating common Linux system administration activities.

The project demonstrates how administrative automation can be designed as a collection of small, testable operations instead of a collection of large shell commands. It covers system inspection, health checks, systemd service management, package-manager inspection, filesystem analysis, controlled cleanup, command execution, configuration, logging, testing, concurrency, containerization, and continuous integration.

The implementation intentionally uses Python's standard library for the core functionality. This keeps the execution model visible to a learner and reduces unnecessary dependency complexity.

Administrative operations that can change the machine are treated more carefully than read-only inspection. File cleanup defaults to a dry run, and command execution does not use a shell.

## Project purpose

Manual administration becomes difficult when the same procedure must be performed repeatedly across machines. Automation provides a repeatable process that can be tested, logged, reviewed, and executed consistently.

This project demonstrates an architecture with the following layers:

- command execution
- security validation
- system inspection
- service management
- package management
- filesystem operations
- health evaluation
- task orchestration
- reporting
- command-line interface

The layers are intentionally separated so that a change to one operation does not require rewriting the entire application.

## Repository structure

The repository uses the following structure:

`src/linux_admin/` contains the application package.

`src/linux_admin/command.py` contains controlled subprocess execution.

`src/linux_admin/config.py` loads environment-based configuration.

`src/linux_admin/security.py` validates Linux execution, service names, and filesystem boundaries.

`src/linux_admin/system.py` reads Linux system information.

`src/linux_admin/services.py` manages systemd services.

`src/linux_admin/packages.py` detects common package managers and queries package state.

`src/linux_admin/filesystem.py` provides filesystem inspection and controlled cleanup.

`src/linux_admin/health.py` evaluates operational thresholds.

`src/linux_admin/tasks.py` executes independent automation tasks sequentially or concurrently.

`src/linux_admin/reporting.py` creates JSON reports.

`src/linux_admin/cli.py` provides the command-line interface.

`tests/` contains automated tests.

`config/health-thresholds.yml` contains example operational thresholds.

`data/example-task-plan.json` demonstrates how a higher-level automation plan can be represented as data.

`.github/workflows/ci.yml` performs automated validation.

`Dockerfile` defines a reproducible container image.

`compose.yaml` provides a safe read-only container example.

## Prerequisites

A Linux system with Python 3.11 or newer is required for the complete toolkit.

The health and system-inspection functionality expects the Linux `/proc` filesystem.

For service-management operations, `systemctl` and systemd must be available.

For package operations, the host should have `apt-get`, `dnf`, or `yum`.

Some administrative operations require elevated operating-system privileges. The toolkit does not attempt to obtain or store a password.

## Installation

Create a virtual environment:

`python3 -m venv .venv`

Activate it:

`source .venv/bin/activate`

Upgrade pip:

`python -m pip install --upgrade pip`

Install the project:

`pip install -e .`

Install development dependencies:

`pip install -e ".[dev]"`

The executable is then available as:

`linux-admin`

The package can also be invoked from the source tree with:

`python -m linux_admin.cli --help`

## Configuration

Copy `.env.example` to `.env` when environment-based local configuration is useful.

The application reads these variables:

`AUTOMATION_LOG_LEVEL` controls logging verbosity.

`AUTOMATION_LOG_FILE` optionally selects a log file.

`AUTOMATION_DRY_RUN` prevents external command execution.

`AUTOMATION_COMMAND_TIMEOUT` limits subprocess execution time.

`AUTOMATION_MAX_WORKERS` controls concurrent task workers.

`AUTOMATION_STATE_FILE` identifies the runtime state location.

`AUTOMATION_REPORT_DIRECTORY` identifies the report directory.

`AUTOMATION_ALLOWED_PATHS` defines filesystem trees that file operations may access.

The repository's `.gitignore` excludes `.env`, virtual environments, generated reports, caches, and compiled files.

## Running locally

Display system information:

`linux-admin system-info`

Run health checks:

`linux-admin health`

The health command reports memory availability, filesystem usage, load normalized by CPU count, and a complete system snapshot.

Check a systemd service:

`linux-admin service status ssh`

On distributions using another service name, provide that service name instead.

Restart a service:

`linux-admin service restart ssh`

Enable a service:

`linux-admin service enable ssh`

These service commands call `systemctl` directly rather than constructing a shell command.

Update package metadata:

`linux-admin packages update-metadata`

Inspect available package updates:

`linux-admin packages updates`

Inspect the size of an allowed directory:

`linux-admin files size /tmp`

Find files larger than the default 100 MiB threshold:

`linux-admin files large /tmp`

Specify another threshold:

`linux-admin files large /tmp --minimum-mb 10`

Run a cleanup audit without deleting files:

`linux-admin files cleanup /tmp --older-than-days 30`

The cleanup command is intentionally non-destructive unless `--execute` is provided.

To explicitly perform deletion:

`linux-admin files cleanup /tmp --older-than-days 30 --execute`

A global `--dry-run` option can also prevent command execution:

`linux-admin --dry-run service restart ssh`

The global dry-run setting takes precedence over the cleanup execution flag.

## Fundamental concepts

### Automation

Automation means expressing an operational procedure as software that can execute the same decision process repeatedly.

A useful automation task has:

- defined inputs
- validation
- predictable actions
- explicit success and failure states
- logging
- observable output
- tests

The project represents task results using the `TaskResult` data class in `models.py`.

### Idempotency

An idempotent operation can be applied repeatedly without producing unintended cumulative changes.

Read-only operations such as system inspection are naturally idempotent.

A service enable operation is generally designed by systemd to tolerate repeated requests.

File deletion is not naturally idempotent because the first execution removes a file. The cleanup implementation therefore separates discovery from deletion and defaults to a dry run.

### Desired state

Administration automation is easier to reason about when the desired state is explicit.

For example, a desired service state might be:

`nginx.service -> enabled and running`

An automation system can inspect the current state and then determine whether an action is required.

This repository keeps individual service operations explicit rather than silently modifying every discovered service.

### Declarative versus imperative automation

Imperative automation describes actions:

`restart nginx`

Declarative automation describes desired state:

`nginx must be running`

Imperative operations are easier to demonstrate in a small toolkit. Larger infrastructure systems often combine declarative configuration with reconciliation logic.

### Dry-run behavior

A dry run is a safety mechanism that allows an administrator to inspect what an operation would do without performing the change.

`CommandRunner` returns a successful simulated result in dry-run mode.

Filesystem cleanup has an independent dry-run default because deletion is destructive.

### Privilege boundaries

Linux administration frequently crosses privilege boundaries.

The application does not embed passwords, use hard-coded credentials, or attempt to bypass operating-system authorization.

An administrator can invoke the application with the appropriate system permissions when an operation requires them.

## Command execution architecture

The `CommandRunner` class centralizes subprocess execution.

It uses `subprocess.run` with:

- argument lists
- captured output
- explicit timeouts
- no shell
- explicit return-code handling

The absence of `shell=True` is important. A command such as `systemctl restart nginx` is represented as:

`["systemctl", "restart", "nginx"]`

This prevents shell syntax from being interpreted.

A timeout is converted into a `CommandResult` with return code 124 and `timed_out=True`.

An operating-system failure to start the process raises `CommandExecutionError`.

## Security model

Security is part of the automation design rather than an independent afterthought.

### Shell injection prevention

User-controlled values must never be interpolated into a shell command.

Service operations validate the service name and then pass arguments directly to `subprocess.run`.

### Filesystem boundaries

File operations use `AUTOMATION_ALLOWED_PATHS`.

For example:

`AUTOMATION_ALLOWED_PATHS=/etc,/var/log,/tmp`

A requested path is resolved and compared against these configured roots.

A path outside the roots raises `SecurityError`.

This protects against accidental access to unrelated filesystem locations.

### Symlink handling

Recursive filesystem traversal skips symbolic links.

This avoids following a link from an allowed directory into an unrelated part of the filesystem.

### Destructive operations

Cleanup requires explicit `--execute`.

Without it, the program only identifies candidates.

World-writable files are skipped by the cleanup routine and reported for review.

### Secrets

No passwords, tokens, API keys, private keys, or real credentials are stored in this repository.

Environment variables are used for host-specific settings.

## System inspection

`system.py` uses Linux interfaces directly.

Memory information is read from `/proc/meminfo`.

Uptime is read from `/proc/uptime`.

CPU information comes from `os.cpu_count()`.

Load averages come from `os.getloadavg()`.

Disk capacity is obtained with `shutil.disk_usage()`.

This approach demonstrates an important Linux administration principle: many system properties can be obtained through operating-system interfaces without executing external commands.

The `SystemSnapshot` class provides a structured representation of the collected data.

## Health checks

`health.py` evaluates a snapshot against explicit thresholds.

The default thresholds are:

- minimum available memory: 10 percent
- maximum disk utilization: 90 percent
- maximum normalized one-minute load: 2.0 per CPU

These values are operational defaults rather than universal definitions of a healthy server.

The health result contains both the individual checks and the underlying system snapshot.

A host can therefore be inspected without losing the measurements that produced the health decision.

## Service management

`services.py` provides three operations:

`status`

`restart`

`enable`

The service name is validated before it is passed to `systemctl`.

The service manager does not automatically restart failed services. Automatic remediation can be dangerous when the root cause is unknown, so this toolkit keeps remediation explicit.

A production system may add policy such as:

- restart only specific services
- limit restart frequency
- require health verification after restart
- record change history
- require authorization
- notify an operator after repeated failure

## Package management

`packages.py` detects:

- apt
- dnf
- yum

Package metadata operations differ between package managers.

For Debian-family systems the implementation uses `apt-get update`.

For dnf and yum it uses `makecache`.

The update query uses `apt-get -s upgrade` on Debian-family systems.

dnf and yum may return code 100 when updates are available. The implementation treats that specific condition as a successful information query rather than a command failure.

The toolkit deliberately does not perform unattended package installation or upgrade.

Package upgrades can affect kernels, shared libraries, running services, configuration files, and application compatibility. Those changes normally require explicit change-management decisions.

## Filesystem automation

The filesystem module demonstrates three major operations.

### Directory size

`directory_size()` recursively measures regular files.

It ignores symbolic links.

It logs files that cannot be inspected instead of terminating the entire scan.

### Large-file discovery

`find_large_files()` returns records containing:

- path
- size in bytes

The output is sorted from largest to smallest.

### Old-file cleanup

`remove_old_files()` calculates an age cutoff and identifies old files.

The operation has two modes.

Dry-run mode reports candidates without deleting them.

Execution mode removes eligible regular files.

The function returns a structured `TaskResult`, which makes the operation testable and suitable for later reporting.

## Task orchestration

`tasks.py` demonstrates two execution models.

Sequential execution runs one task after another.

Concurrent execution uses `ThreadPoolExecutor`.

Concurrency is appropriate when independent tasks spend significant time waiting for I/O.

The implementation does not assume that concurrency automatically improves every workload. CPU-intensive Python operations can be limited by the interpreter's execution model, while external command execution and filesystem operations often involve I/O waits.

The caller can explicitly request concurrent execution with the `concurrent=True` argument.

## Error handling

The project uses different error categories for different problems.

`ValueError` represents invalid application arguments.

`SecurityError` represents violations of security boundaries.

`CommandExecutionError` represents inability to start an operating-system command.

`CommandResult` represents commands that successfully started but returned a non-zero result.

This distinction is important because a failed service restart is different from the inability to execute `systemctl`.

The CLI converts failures into non-zero exit codes so that shell scripts and CI systems can detect failure.

## Testing

Run the complete test suite:

`pytest`

Run tests with coverage:

`pytest --cov=linux_admin --cov-report=term-missing`

Run lint checks:

`ruff check src tests`

The tests cover:

- subprocess execution
- dry-run execution
- empty commands
- service-name validation
- filesystem security boundaries
- valid service names
- directory-size calculation
- large-file discovery
- task orchestration
- configuration defaults

Tests that require real systemd services are intentionally not included in the default suite because service availability varies between Linux environments.

## Edge cases

The implementation handles several operational edge cases.

A missing package manager produces a structured failure instead of selecting a nonexistent executable.

A command timeout produces an explicit timeout result.

An empty command is rejected.

Invalid service names are rejected before execution.

Filesystem traversal skips symbolic links.

Unreadable filesystem entries are recorded rather than terminating the entire scan.

A zero-byte filesystem is handled without division by zero.

A missing CPU count falls back to one CPU for normalization.

No configured filesystem roots means file operations are rejected.

## Common mistakes

Running administrative commands through a shell with untrusted input can create command-injection vulnerabilities.

Deleting files without a dry-run phase can cause irreversible data loss.

Using fixed filesystem paths without validating their scope can cause automation to affect unintended files.

Assuming every Linux distribution uses the same package manager makes automation less portable.

Assuming a service name is identical on every distribution can cause incorrect service operations.

Ignoring command return codes can make a failed administration action appear successful.

Running several destructive operations concurrently can increase the impact of an error.

Logging command output without considering sensitive information can expose credentials or confidential data.

Running an automation process with unnecessary root privileges increases the potential impact of application defects.

## Performance considerations

Recursive filesystem operations are proportional to the number of filesystem entries inspected.

A directory containing many millions of files can therefore take substantially longer to scan than a small directory.

Large-file discovery stores matching results in memory. A very large result set could require a streaming design.

The task runner supports bounded concurrency through `max_workers`.

Subprocess operations have explicit timeouts so an unresponsive external command does not block indefinitely.

Filesystem metadata is requested only as needed.

The project does not introduce caching because the system state being inspected can change quickly and stale administrative information can be misleading.

## Reliability considerations

Reliable administration automation should make failures visible.

The toolkit returns explicit exit codes.

Task results contain status and message information.

JSON reports provide machine-readable output.

Logging records the command lifecycle.

Timeouts protect against indefinitely blocked subprocesses.

Configuration is externalized so host-specific behavior does not require source-code modifications.

Production deployments should also consider:

- centralized log collection
- alerting
- audit records
- configuration versioning
- rollback procedures
- controlled privileges
- change approval
- backup verification
- host-level monitoring

## Reporting

The reporting module writes JSON documents containing task counts and individual task results.

Reports are written to the configured report directory.

The JSON writer first writes a temporary file and then replaces the target file. This reduces the chance of leaving a partially written final report after an interruption.

The repository's `.gitignore` excludes generated reports because operational reports are runtime artifacts rather than source code.

## Docker

The Docker image uses Python 3.12 on a slim Linux base image.

The image installs the package without development dependencies.

The container runs as a non-root user.

The default mode is dry-run.

The Compose example is configured with a read-only root filesystem and only exposes `/tmp` as a writable temporary filesystem.

Containerized system administration has an important limitation: a normal container does not automatically have access to the host's systemd, kernel state, devices, or filesystem.

Therefore the Docker configuration is intended to demonstrate packaging and safe execution, not unrestricted host administration.

Host administration should normally run with an appropriate host-level service account or controlled management mechanism.

## CI/CD

GitHub Actions runs on Ubuntu and performs:

- repository checkout
- Python setup
- package installation
- Ruff linting
- pytest execution
- coverage reporting
- CLI installation verification

No deployment credentials are included.

The workflow uses read-only repository permissions.

## Production considerations

A production automation service should not simply run arbitrary administrative commands received from users.

A stronger architecture would use:

- an explicit operation allowlist
- role-based authorization
- audit logging
- signed configuration
- rate limiting
- command timeouts
- process isolation
- least-privilege service accounts
- centralized monitoring
- configuration validation
- approval workflows for destructive actions
- backup and rollback procedures
- host identity verification

The current project demonstrates these principles at a smaller scale through command allowlisting by construction, service-name validation, filesystem boundaries, dry-run behavior, explicit destructive flags, and non-root container execution.

## Real-world applications

The same design can support larger administrative workflows such as:

- scheduled disk-capacity audits
- service health checks
- package inventory collection
- temporary-file cleanup
- server compliance checks
- configuration validation
- operational report generation
- fleet-wide diagnostics
- pre-deployment validation
- post-deployment verification

Fleet-wide execution should introduce authentication, authorization, host inventory, retry policies, concurrency limits, audit logging, and failure isolation rather than simply executing the same local script on every server.

## Operational exit codes

The CLI uses exit codes so it can participate in automation pipelines.

`0` means the requested operation completed successfully.

`2` indicates an operational result that requires attention, such as a failed health check or failed administrative operation.

`3` indicates a security validation failure.

`4` indicates an operating-system or argument-related operation failure.

`5` indicates an unsupported CLI state.

These codes allow external schedulers and monitoring systems to distinguish ordinary success from different classes of failure.

## Example read-only workflow

A simple operational sequence is:

`linux-admin system-info`

`linux-admin health`

`linux-admin files size /tmp`

`linux-admin files large /tmp --minimum-mb 100`

`linux-admin service status ssh`

This workflow gathers information without modifying services or deleting files.

A cleanup operation should first be inspected:

`linux-admin files cleanup /tmp --older-than-days 30`

Only after reviewing the candidates should an administrator explicitly execute the deletion:

`linux-admin files cleanup /tmp --older-than-days 30 --execute`

The allowed filesystem roots should also be configured appropriately before performing such an operation.
