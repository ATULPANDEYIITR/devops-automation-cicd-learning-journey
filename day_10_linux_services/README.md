# Linux services: systemd, systemctl, and service management

## Introduction

Linux services are programs that provide persistent functionality to an operating system or its users. Common examples include SSH servers, web servers, databases, background workers, network services, monitoring agents, schedulers, and logging components.

Modern Linux distributions commonly use **systemd** as the system and service manager. systemd is responsible for much of the userspace initialization process and provides a framework for starting, stopping, supervising, grouping, scheduling, and inspecting system resources.

The primary command-line interface to systemd is **systemctl**.

This study script develops the subject from basic process and service concepts through systemd units, service lifecycle management, dependency relationships, boot targets, logging, timers, socket activation, security hardening, resource management, debugging, automation, and production design.

The script intentionally displays commands that modify system state rather than executing them automatically. Read-only systemd queries may be executed when the host provides systemctl.

## Linux processes, daemons, and services

A **process** is an executing instance of a program. Every normal Linux process has attributes such as a process identifier, memory space, credentials, file descriptors, scheduling information, and a parent process relationship.

A **daemon** is a background program designed to provide a persistent service. Historically, daemon names often ended with `d`, as in `sshd`, although the naming convention is not mandatory.

A **service** is a broader operational concept. It normally represents a capability that needs to be started, monitored, stopped, restarted, configured, and integrated with other components.

The distinctions are important:

- A process describes execution.
- A daemon describes a background-oriented program.
- A service describes an operational capability and its lifecycle.
- An init system manages system initialization and service activation.
- systemd is an init and service-management system commonly used on Linux.

## The Linux startup process

The Linux kernel initializes core kernel facilities and eventually starts the first userspace process.

On a system using systemd, that process is normally systemd with **PID 1**.

The simplified sequence is:

1. Firmware or a bootloader loads the kernel.
2. The kernel initializes hardware and core kernel subsystems.
3. The kernel starts the initial userspace process.
4. systemd initializes its service manager.
5. systemd loads unit definitions and establishes dependencies.
6. Appropriate targets and units are activated.
7. Services are started according to dependency and ordering relationships.
8. systemd continues supervising services while the system operates.
9. During shutdown or reboot, systemd stops units according to the applicable dependency relationships.

The real startup process is more complex and distribution-specific. The simplified sequence is useful for understanding where systemd fits into the operating system.

## systemd architecture

systemd is not simply another name for `systemctl`.

The major concepts include:

- **systemd**: the service manager and initialization system.
- **systemctl**: command-line administration interface.
- **systemd-journald**: system logging service.
- **journalctl**: command-line interface for journal data.
- **targets**: logical synchronization and grouping points.
- **units**: configuration objects managed by systemd.
- **cgroups**: Linux process groups used for resource management and tracking.
- **timers**: scheduling units.
- **sockets**: socket activation units.
- **paths**: filesystem-triggered activation units.
- **slices**: resource-management groups.
- **scopes**: externally created process groups.

systemd creates a dependency graph rather than relying exclusively on a long sequential startup script.

This graph allows independent components to start concurrently while dependencies and ordering constraints are respected.

## systemd units

A **unit** is an object understood by systemd.

The unit type is normally indicated by the filename suffix.

| Unit type | Purpose |
|---|---|
| `.service` | Managed service process |
| `.socket` | Socket activation |
| `.target` | Logical grouping or synchronization point |
| `.timer` | Time-based activation |
| `.path` | Filesystem path activation |
| `.mount` | Filesystem mount |
| `.automount` | Automatic filesystem mounting |
| `.swap` | Swap device or file |
| `.device` | Kernel device |
| `.slice` | Resource-management hierarchy |
| `.scope` | Externally created process group |
| `.busname` | D-Bus activation |

The most commonly administered unit is a `.service` unit.

For example:

`ssh.service`

represents the SSH service on systems that use that particular unit name.

Unit names are not completely universal across distributions. One distribution may use `ssh.service`, while another may use `sshd.service`.

## Service units

A service unit generally describes:

- what the service does
- how it starts
- how it stops
- how it reloads
- which user runs it
- what dependencies it has
- how it should be restarted
- how long startup and shutdown may take
- which environment variables it receives
- which security restrictions apply
- which target should activate it

A typical service has three major sections.

### `[Unit]`

This section describes metadata and relationships.

Common directives include:

- `Description=`
- `After=`
- `Before=`
- `Requires=`
- `Wants=`
- `Requisite=`
- `BindsTo=`
- `PartOf=`
- `Conflicts=`

### `[Service]`

This section describes process execution and supervision.

Common directives include:

- `Type=`
- `ExecStart=`
- `ExecStop=`
- `ExecReload=`
- `Restart=`
- `RestartSec=`
- `User=`
- `Group=`
- `Environment=`
- `EnvironmentFile=`
- `WorkingDirectory=`
- `TimeoutStartSec=`
- `TimeoutStopSec=`
- `NoNewPrivileges=`

### `[Install]`

This section defines relationships used when a unit is enabled.

A common directive is:

`WantedBy=multi-user.target`

This allows `systemctl enable` to create the appropriate activation relationship.

## `systemctl`

`systemctl` is the primary command-line tool for systemd administration.

The script demonstrates the most important commands.

### Checking status

`systemctl status UNIT`

This displays a human-oriented view of the unit's current state, including recent service messages and process information.

### Starting a service

`sudo systemctl start UNIT`

Starting a service changes its current runtime state.

Starting does not normally configure the service to start automatically after reboot.

### Stopping a service

`sudo systemctl stop UNIT`

Stopping a service changes its current runtime state.

Stopping does not necessarily disable automatic startup.

### Restarting a service

`sudo systemctl restart UNIT`

Restarting generally stops and starts the service.

This is useful when a complete process restart is required.

### Reloading a service

`sudo systemctl reload UNIT`

Reloading asks the service to reread its configuration without necessarily replacing the running process.

Reloading only works when the service supports an appropriate reload mechanism.

### Reload or restart

`sudo systemctl reload-or-restart UNIT`

This is useful when an application supports reload but the administrator wants a fallback restart when reload is unavailable.

## Active versus enabled

One of the most important distinctions in systemd administration is:

**active** describes the current runtime state.

**enabled** describes whether a unit has been configured for automatic activation through its installation relationships.

A service can therefore be:

- active and enabled
- active and disabled
- inactive and enabled
- inactive and disabled

For example, an administrator can manually start a disabled service.

The two commands are:

`systemctl is-active UNIT`

and

`systemctl is-enabled UNIT`

They answer different questions.

## Service states

Common service states include:

### `active (running)`

The service is currently running.

### `active (exited)`

The service completed its execution but remains considered active according to its unit configuration.

This is commonly encountered with `Type=oneshot` and appropriate use of `RemainAfterExit=`.

### `inactive (dead)`

The service is not currently active.

### `failed`

The service encountered a failure condition.

The failure may result from:

- unsuccessful process termination
- startup failure
- timeout
- dependency failure
- watchdog failure
- configuration error
- permission error
- missing executable
- application-level failure

### `activating`

The service is currently being started.

### `deactivating`

The service is currently being stopped.

### `reloading`

The service is currently processing a reload operation.

## `Type=` and service startup behavior

The `Type=` directive tells systemd how to interpret service startup.

Important types include:

### `simple`

The command from `ExecStart=` is treated as the main process.

This is suitable for many foreground applications.

### `exec`

This is similar to `simple` but provides stronger startup semantics around successful execution of the specified executable.

### `forking`

This is intended for programs that start and then fork into the background.

Older daemon-style applications may require this model.

### `oneshot`

This represents a task that performs an operation and exits.

It is useful for maintenance tasks, initialization actions, and administrative jobs.

### `notify`

The application communicates readiness to systemd using systemd's notification mechanism.

This allows an application to distinguish process creation from actual service readiness.

### `dbus`

The service is considered started after acquiring an appropriate D-Bus name.

### `idle`

This resembles `simple` but delays execution until active jobs have been dispatched.

The correct service type depends on the application's process model.

Modern services are often best designed as foreground processes rather than programs that implement their own daemonization.

## Service lifecycle

The fundamental lifecycle operations are:

`start`

`stop`

`restart`

`reload`

`enable`

`disable`

These operations should not be treated as interchangeable.

A common operational mistake is to use `restart` when a non-disruptive `reload` is available, or to use `start` and assume the service is configured for automatic boot activation.

## Enablement

`systemctl enable UNIT`

configures the relationships specified by the unit's `[Install]` section.

It normally does not start the service immediately.

The combined command:

`sudo systemctl enable --now UNIT`

both enables and starts the unit.

Likewise:

`sudo systemctl disable --now UNIT`

disables the unit and stops it.

## Disablement

`systemctl disable UNIT`

removes the activation relationship created by enablement.

It does not necessarily stop a currently running service.

This distinction is important when performing maintenance.

## Targets

A target is a systemd unit used mainly for grouping and synchronization.

Important targets include:

- `basic.target`
- `sysinit.target`
- `sockets.target`
- `network.target`
- `network-online.target`
- `multi-user.target`
- `graphical.target`
- `rescue.target`
- `emergency.target`
- `shutdown.target`
- `reboot.target`

### `multi-user.target`

This commonly represents a fully operational multi-user environment without requiring a graphical environment.

### `graphical.target`

This generally represents a graphical operating environment and normally builds on the multi-user state.

The exact relationships depend on the distribution.

## Default boot target

The default target can be inspected with:

`systemctl get-default`

A system administrator can change it with a command such as:

`sudo systemctl set-default multi-user.target`

Changing the default target affects future boot behavior and should be performed with an understanding of the target dependency graph.

## Dependencies

systemd uses several dependency relationships.

### `Requires=`

Expresses a strong dependency relationship.

If the required unit cannot be activated successfully, the relationship can affect the dependent unit.

### `Wants=`

Expresses a weaker dependency.

It asks systemd to activate another unit but does not impose the same level of coupling as `Requires=`.

### `Requisite=`

Requires another unit to already be active when the dependent unit starts.

### `BindsTo=`

Provides stronger lifecycle coupling than a normal `Requires=` relationship in relevant situations.

### `PartOf=`

Allows certain lifecycle operations to propagate between related units.

### `Conflicts=`

Expresses that two units should not be active simultaneously.

## Dependency versus ordering

This distinction is fundamental.

`Requires=database.service`

expresses a dependency.

`After=database.service`

expresses ordering.

They solve different problems.

A service may need both:

`Requires=database.service`

and:

`After=database.service`

The first expresses that the database service is required. The second expresses that the application should be started after the database service when both units are being activated.

`After=` alone does not mean that the other unit will automatically be started.

## Ordering directives

### `After=`

The current unit should be started after the specified unit when both are involved in the transaction.

### `Before=`

The current unit should be started before the specified unit when both are involved.

Ordering does not automatically create dependency relationships.

This separation allows systemd to construct flexible dependency graphs.

## Network dependencies

A common mistake is assuming that:

`After=network.target`

means that an application has fully usable network connectivity.

It does not necessarily mean that the network is ready for application-level communication.

Where appropriate, services may use:

`After=network-online.target`

and:

`Wants=network-online.target`

The exact semantics depend on the distribution and its network-management implementation.

Applications should also handle temporary network failure themselves instead of assuming that boot-time network availability guarantees permanent connectivity.

## Unit file locations

Common unit locations include:

`/etc/systemd/system/`

`/run/systemd/system/`

`/usr/lib/systemd/system/`

`/lib/systemd/system/`

For user services, common locations include:

`~/.config/systemd/user/`

Exact locations vary across distributions.

Administrator-managed configuration generally belongs under `/etc`.

Package-provided units commonly live under `/usr/lib` or `/lib`, depending on the distribution.

The actual source used for a unit can be inspected with:

`systemctl cat UNIT`

and:

`systemctl show -p FragmentPath UNIT`

## Drop-in configuration

Directly editing package-provided unit files is usually undesirable because package updates can replace those files.

systemd supports drop-in configuration.

A common administrative command is:

`sudo systemctl edit example.service`

This can create a configuration such as:

`[Service]`

`Restart=on-failure`

`RestartSec=10`

Drop-ins allow local configuration to override or extend vendor configuration without modifying the original package file.

## `daemon-reload`

When a unit file or drop-in changes, systemd may need to reread its configuration.

The command is:

`sudo systemctl daemon-reload`

This does not restart all services.

A changed unit may still require:

`sudo systemctl restart UNIT`

or:

`sudo systemctl reload UNIT`

depending on the change and application behavior.

A useful distinction is:

- `daemon-reload`: reread unit definitions
- `reload`: ask a service process to reload its configuration
- `restart`: replace the running service process

## Restart policies

systemd supports automatic service restart policies through `Restart=`.

Important values include:

- `no`
- `on-success`
- `on-failure`
- `on-abnormal`
- `on-abort`
- `on-watchdog`
- `always`

A common production configuration is:

`Restart=on-failure`

combined with:

`RestartSec=5`

Automatic restart improves availability for certain classes of failure, but it does not fix an application defect.

A broken service can repeatedly crash and restart.

This can consume resources, flood logs, and hide the original failure.

## Restart rate limiting

systemd can limit repeated activation attempts.

Example concepts include:

`StartLimitIntervalSec=`

and:

`StartLimitBurst=`

These mechanisms help prevent uncontrolled restart loops.

Restart policy and restart rate limiting should be designed together.

A service should not simply restart indefinitely without giving operators enough information to diagnose the underlying problem.

## Environment variables

Services frequently require environment variables.

systemd supports:

`Environment=`

and:

`EnvironmentFile=`

For example:

`Environment="APP_ENV=production"`

and:

`EnvironmentFile=/etc/example/app.env`

Environment variables are useful but should not automatically be treated as a secure secret store.

Process environments can potentially be inspected through operating-system interfaces by sufficiently privileged users.

Sensitive credentials require controlled permissions and appropriate secret-management practices.

## Working directories and execution context

A service started by systemd may run in a different environment from an interactive shell.

Differences can include:

- current working directory
- `PATH`
- user identity
- group membership
- environment variables
- filesystem permissions
- network availability
- security restrictions
- resource limits

This explains a common debugging problem:

> The command works manually but fails under systemd.

The command may depend on environment assumptions that do not exist when systemd launches it.

Production services should use explicit paths and deliberate configuration rather than depending on interactive shell state.

## Logging with journald

systemd commonly integrates service output with **journald**.

The command-line interface is:

`journalctl`

Useful examples include:

`journalctl -u example.service`

`journalctl -u example.service -n 100`

`journalctl -u example.service -f`

`journalctl -u example.service --since today`

`journalctl -b`

`journalctl -b -1`

`journalctl -p err`

`journalctl -xeu example.service`

### Unit-specific logging

`journalctl -u UNIT`

filters messages associated with a specific unit.

### Following live logs

`journalctl -f`

follows newly generated messages.

When combined with a unit filter, it is useful for observing an application while reproducing a problem.

### Boot-specific logs

`journalctl -b`

shows logs from the current boot.

`journalctl -b -1`

can show the previous boot when journal history is available.

## Debugging failed services

A disciplined debugging process is more effective than repeated restarts.

A useful sequence is:

1. Inspect `systemctl status UNIT`.
2. Check `systemctl is-failed UNIT`.
3. Read unit-specific journal messages.
4. Inspect the actual unit with `systemctl cat UNIT`.
5. Inspect structured properties with `systemctl show UNIT`.
6. Inspect dependency relationships.
7. Check executable paths.
8. Check users, groups, ownership, and permissions.
9. Check environment configuration.
10. Check ports and other required resources.
11. Check resource limits and security restrictions.
12. Reproduce the underlying application failure directly where appropriate.

Common causes include:

- missing executable
- incorrect executable path
- invalid configuration
- incorrect user
- missing working directory
- permission errors
- unavailable ports
- missing environment variables
- failed dependencies
- startup timeout
- shutdown timeout
- security-policy denial
- resource exhaustion
- application crashes
- restart loops

## `systemctl status` versus `systemctl show`

`systemctl status` is designed for human inspection.

`systemctl show` exposes structured properties that are more suitable for automation.

Examples include:

`systemctl show -p ActiveState UNIT`

`systemctl show -p SubState UNIT`

`systemctl show -p MainPID UNIT`

`systemctl show -p FragmentPath UNIT`

`systemctl show -p UnitFileState UNIT`

Automation should generally prefer machine-readable properties rather than parsing human-oriented status output.

## Main PID and process supervision

`MainPID` can identify the primary process associated with a service.

Modern service design benefits from a clear foreground process because systemd can supervise it more predictably.

A service that unnecessarily forks, daemonizes, or creates complicated process trees can make supervision and debugging harder.

systemd also tracks service processes through Linux cgroups, which allows resource management and lifecycle tracking across the processes belonging to a unit.

## Signals and graceful shutdown

Service processes should handle termination gracefully.

A good application should:

- receive the termination signal
- stop accepting new work
- finish or cancel appropriate operations
- close resources
- flush necessary state
- release locks
- exit within a reasonable time

`TimeoutStopSec=` can define how long systemd waits for graceful shutdown behavior.

`SIGTERM` is commonly associated with graceful termination.

`SIGKILL` cannot be caught or handled by the application and therefore represents a forced termination mechanism.

Applications that ignore termination signals can delay shutdown and complicate deployment.

## Exit statuses

Processes normally communicate successful completion through exit status `0`.

Non-zero exit statuses generally indicate failure.

systemd uses exit status along with signals, timeouts, watchdog behavior, and other conditions to determine service state.

For short-lived services, `SuccessExitStatus=` can identify additional statuses that should be interpreted as successful.

This must be used carefully. Marking an actual failure code as successful can hide real operational problems.

## `oneshot` services

`Type=oneshot` is useful for operations that perform a task and exit.

Typical examples include:

- database migrations
- maintenance tasks
- initialization
- cleanup
- one-time configuration operations

A oneshot service should not be used merely because an application happens to terminate quickly. Its semantics should reflect the intended lifecycle.

## Timers

A systemd `.timer` unit schedules activation of another unit.

Timers can replace many traditional cron jobs while integrating scheduled tasks into the systemd service model.

A typical relationship is:

`example.timer`

activating:

`example.service`

A timer can use calendar expressions such as:

`OnCalendar=daily`

The `Persistent=` option can be useful when scheduled work should be triggered after the machine has been offline during the intended schedule.

Useful commands include:

`systemctl list-timers --all`

and:

`systemctl status example.timer`

## systemd timers versus cron

Both systemd timers and cron can schedule recurring tasks.

| Capability | systemd timer | cron |
|---|---|---|
| Calendar scheduling | Yes | Yes |
| Service integration | Native | Separate mechanism |
| Dependency graph | Native | Limited |
| journald integration | Native | Usually indirect |
| Resource controls | systemd/cgroups | Not equivalent by default |
| Service supervision | Native when paired with a service | Separate process model |
| Persistent scheduling | Supported | Different implementation semantics |

Cron remains widely useful. systemd timers are particularly useful when scheduled operations need to behave as managed systemd services.

## Socket activation

A `.socket` unit can listen for connections before the associated service process starts.

When a connection arrives, systemd can activate the service.

This can be useful for services that:

- receive network connections
- do not need to remain resident when idle
- support systemd socket activation
- benefit from centralized socket management

Socket activation is not universal. The application must support the expected socket-passing model.

## Path activation

A `.path` unit can trigger another unit when a filesystem condition occurs.

Examples include:

- a file being modified
- a directory changing
- a path appearing

Path activation is appropriate for simple filesystem-triggered workflows.

It is not a universal replacement for high-volume filesystem event-processing systems.

## User services

systemd can manage both system-wide services and per-user services.

System services are managed through the system manager.

User services can be controlled with:

`systemctl --user`

For example:

`systemctl --user status example.service`

User services are appropriate when an application belongs to an individual user and does not need system-wide privileges.

Running an application as a non-root user can substantially reduce the impact of an application compromise.

## Service security

Service configuration is an important security boundary.

The primary principle is **least privilege**.

A service should not run as root unless root privileges are genuinely required.

Useful security-related directives include:

- `User=`
- `Group=`
- `NoNewPrivileges=`
- `PrivateTmp=`
- `ProtectSystem=`
- `ProtectHome=`
- `ReadWritePaths=`
- `ReadOnlyPaths=`
- `InaccessiblePaths=`
- `PrivateDevices=`
- `RestrictAddressFamilies=`
- `RestrictNamespaces=`
- `CapabilityBoundingSet=`

These directives can restrict what a service can access even if the application is compromised.

## `NoNewPrivileges=`

`NoNewPrivileges=true` prevents a process and its descendants from gaining additional privileges through mechanisms such as certain privilege-changing operations.

It is an important defense-in-depth control.

It does not by itself make an application secure.

## Filesystem protection

Directives such as:

`ProtectSystem=`

can restrict write access to system areas.

`ProtectHome=`

can restrict access to users' home directories.

`ReadWritePaths=`

can identify locations that the application legitimately needs to modify.

A secure service should expose the smallest practical filesystem surface.

Overly aggressive restrictions can break legitimate applications, so security hardening should be introduced through testing.

## Linux capabilities

Traditional root privileges are broad.

Linux capabilities divide certain privileged operations into smaller units.

`CapabilityBoundingSet=` can reduce the capabilities available to a service.

This supports least-privilege service design.

Capability configuration requires knowledge of the application's actual requirements.

## Resource management

systemd integrates with Linux cgroups.

This enables grouping and control of processes belonging to a service.

Relevant directives include:

- `MemoryMax=`
- `MemoryHigh=`
- `CPUQuota=`
- `CPUWeight=`
- `IOWeight=`
- `TasksMax=`
- `LimitNOFILE=`
- `LimitNPROC=`

### Memory limits

`MemoryMax=` can establish a hard memory boundary.

This can protect a host against runaway memory consumption.

### CPU limits

`CPUQuota=` can restrict the amount of CPU time available to a service.

### Task limits

`TasksMax=` can limit the number of processes or threads associated with a unit.

### File descriptor limits

`LimitNOFILE=` controls the maximum number of open file descriptors subject to the applicable operating-system limits.

Resource limits should be derived from measured application requirements rather than arbitrary values.

## Watchdogs

A watchdog provides a mechanism for detecting certain classes of service failure.

A process can exist while being internally unhealthy, blocked, or deadlocked.

A watchdog can detect failures that simple process-existence monitoring cannot.

A typical configuration may use:

`Type=notify`

and:

`WatchdogSec=`

The application must cooperate with the notification protocol.

Watchdog intervals should be selected carefully to avoid false failures during legitimate periods of heavy workload or startup.

## Secret handling

Credentials require special treatment.

Sensitive values should not casually be placed directly in unit files.

Environment variables also do not automatically provide strong secret isolation.

A safer design may involve:

- dedicated secret files
- restrictive file ownership
- dedicated service accounts
- appropriate operating-system permissions
- external secret-management systems where justified
- avoiding unnecessary credential exposure

A secret is not protected merely because its filename is obscure.

The process receiving the secret must also be appropriately restricted.

## Masking

Masking is stronger than disabling.

`systemctl disable UNIT`

removes automatic activation relationships.

`systemctl mask UNIT`

prevents normal activation by creating a mask, commonly represented through `/dev/null`.

Unmasking is performed with:

`systemctl unmask UNIT`

Masking can be useful when a service must not start accidentally or indirectly.

It should be used carefully because another service may genuinely depend on the masked unit.

## Transient units

Not all systemd units originate from persistent unit files.

Transient units can be created dynamically.

For example, `systemd-run` can create temporary managed execution contexts.

A transient unit is useful for temporary jobs, experiments, or controlled administrative execution.

Transient units should not be confused with persistent service installation.

## Generated units

systemd can use generator programs during startup to create or modify unit relationships dynamically.

This means the runtime systemd state cannot always be understood solely by examining static unit files.

`systemctl cat` and `systemctl show` are therefore valuable for understanding the runtime configuration.

## Python automation

Python can interact with systemd through:

- `subprocess`
- D-Bus interfaces
- operating-system APIs
- specialized systemd libraries

The script uses `subprocess` for basic read-only demonstrations because it is available in the Python standard library.

A safe subprocess pattern passes arguments as a list rather than constructing shell commands through string interpolation.

Conceptually:

`["systemctl", "show", "-p", "ActiveState", "--value", "example.service"]`

is preferable to building an untrusted shell command as a single string.

## Command injection considerations

Administrative automation is security-sensitive.

Avoid patterns in which user-controlled input is interpolated into a shell command and executed through a shell.

A safer approach is:

- validate the input
- construct an argument list
- avoid `shell=True` unless there is a specific and controlled reason
- use least privilege
- restrict which operations automation is allowed to perform

The Python script includes a conservative educational unit-name validator to demonstrate this principle.

The validator is not a complete implementation of systemd's full unit-name escaping grammar.

## Read-only versus state-changing operations

Read-only operations include:

- `status`
- `is-active`
- `is-enabled`
- `is-failed`
- `show`
- `cat`
- `list-units`
- `list-unit-files`
- `list-dependencies`
- `list-timers`
- `get-default`

State-changing operations include:

- `start`
- `stop`
- `restart`
- `reload`
- `enable`
- `disable`
- `mask`
- `unmask`
- `set-default`
- `isolate`

Administrative automation should distinguish these categories explicitly.

## Performance and boot analysis

systemd can start independent units concurrently.

Good dependency design therefore affects boot performance.

Artificial dependencies can unnecessarily serialize startup.

Missing dependencies can create race conditions.

Useful diagnostic commands include:

`systemd-analyze`

`systemd-analyze blame`

`systemd-analyze critical-chain`

`systemd-analyze plot > boot.svg`

`systemd-analyze security UNIT`

### `systemd-analyze blame`

This identifies units associated with startup time.

It is useful for finding candidates for investigation but should not be treated as a complete causal performance analysis.

### `systemd-analyze critical-chain`

This helps reveal dependency chains that affect startup sequencing.

## Service validation

A service should be validated before deployment.

A useful command is:

`systemd-analyze verify /etc/systemd/system/example.service`

Other useful inspection commands include:

`systemctl cat example.service`

and:

`systemctl show example.service`

Validation can identify syntax and configuration problems before they become production failures.

## Production service design

A production-quality service should have deliberate decisions for:

- process ownership
- startup
- shutdown
- dependencies
- ordering
- restart behavior
- logging
- resource limits
- security restrictions
- configuration
- credentials
- health monitoring
- failure recovery
- deployment
- upgrade behavior

A useful design principle is to make the service's lifecycle explicit.

The service should not rely on accidental properties of a developer's interactive shell or a particular boot sequence.

## Service accounts

A dedicated service account is usually preferable to using root for applications that do not need administrative privileges.

A dedicated account limits access to:

- files
- directories
- devices
- credentials
- other user resources

This is one of the most important service-security practices.

## Graceful shutdown

Applications should respond appropriately to termination signals.

A service that takes too long to shut down can delay:

- reboot
- deployment
- failover
- scaling
- maintenance

`TimeoutStopSec=` should reflect realistic shutdown requirements.

The application should also avoid unnecessary cleanup operations that can become indefinitely blocked.

## Restart strategy

A restart policy should be based on the type of failure.

For example, `Restart=on-failure` can be suitable for long-running workers that should recover from unexpected crashes.

It is less useful to blindly restart an application that exits because a mandatory configuration value is invalid.

A repeated restart is not a substitute for diagnosing the underlying failure.

## Health monitoring

A running process is not necessarily a healthy service.

For example, an API process may remain alive while:

- all database connections are broken
- worker threads are deadlocked
- requests are permanently failing
- external dependencies are unavailable
- internal queues are saturated

Production monitoring should distinguish process state from application health.

systemd supervision and application-level health monitoring solve related but different problems.

## Common mistakes

### Assuming `start` means boot persistence

`start` changes the current state.

`enable` configures automatic activation.

### Assuming `enable` starts the service

Traditional `enable` does not normally start the service immediately.

`enable --now` combines the two operations.

### Editing vendor files directly

Package updates may overwrite changes.

Drop-ins are generally safer for administrator customizations.

### Forgetting `daemon-reload`

Changed unit definitions may not be reread until `daemon-reload`.

### Confusing dependencies and ordering

`Requires=` and `After=` solve different problems.

### Running every service as root

This unnecessarily expands the potential impact of a compromise.

### Ignoring journald

The service logs often contain the direct explanation for startup failure.

### Creating restart loops

Automatic restarts should be combined with sensible retry delays and rate limits.

### Assuming service names are universal

Distribution-specific naming differences are common.

### Parsing human-readable output

Automation should prefer `systemctl show` and explicit properties.

### Assuming process existence equals health

Application-level health should be monitored separately.

## systemd and cron

systemd timers and cron overlap in scheduling functionality.

systemd timers provide closer integration with:

- service units
- dependencies
- logging
- resource controls
- service lifecycle
- failure handling

cron remains a valid scheduling mechanism and is widely deployed.

The appropriate choice depends on the operating environment and operational requirements.

## Real-world service applications

Service management is relevant to:

- Nginx and Apache web servers
- SSH services
- PostgreSQL and MariaDB
- application backends
- Python workers
- Node.js services
- message consumers
- monitoring agents
- backup processes
- scheduled maintenance
- network services
- container infrastructure
- storage services
- hardware-related processes
- desktop services
- development environments

The underlying operational principles remain consistent even when the applications differ.

## Production troubleshooting checklist

When a service fails, inspect:

- unit status
- active state
- failed state
- service logs
- unit source
- drop-ins
- dependencies
- executable path
- service user
- group permissions
- environment variables
- working directory
- listening ports
- filesystem permissions
- resource limits
- security restrictions
- startup timeout
- restart behavior
- application configuration

A structured investigation is more reliable than repeatedly restarting the service.

## Important command reference

| Operation | Command | Purpose |
|---|---|---|
| Status | `systemctl status UNIT` | Inspect runtime state |
| Start | `sudo systemctl start UNIT` | Start now |
| Stop | `sudo systemctl stop UNIT` | Stop now |
| Restart | `sudo systemctl restart UNIT` | Restart now |
| Reload | `sudo systemctl reload UNIT` | Reload configuration if supported |
| Enable | `sudo systemctl enable UNIT` | Enable automatic activation |
| Disable | `sudo systemctl disable UNIT` | Disable automatic activation |
| Enable and start | `sudo systemctl enable --now UNIT` | Enable and start |
| Disable and stop | `sudo systemctl disable --now UNIT` | Disable and stop |
| Active state | `systemctl is-active UNIT` | Check runtime activity |
| Enabled state | `systemctl is-enabled UNIT` | Check automatic activation |
| Failed state | `systemctl is-failed UNIT` | Check failure status |
| Unit source | `systemctl cat UNIT` | Inspect unit configuration |
| Properties | `systemctl show UNIT` | Inspect structured properties |
| Reload manager | `sudo systemctl daemon-reload` | Reread unit definitions |
| List units | `systemctl list-units` | List loaded units |
| List unit files | `systemctl list-unit-files` | List installed unit files |
| Dependencies | `systemctl list-dependencies UNIT` | Inspect dependency relationships |
| Mask | `sudo systemctl mask UNIT` | Prevent normal activation |
| Unmask | `sudo systemctl unmask UNIT` | Remove a mask |
| Default target | `systemctl get-default` | Inspect default boot target |
| Timers | `systemctl list-timers --all` | Inspect scheduled timers |
| Logs | `journalctl -u UNIT` | Read service logs |
| Current boot | `journalctl -b` | Read current boot logs |
| Previous boot | `journalctl -b -1` | Read previous boot logs |
| Boot analysis | `systemd-analyze` | Analyze systemd startup |
| Critical chain | `systemd-analyze critical-chain` | Analyze startup dependency chain |
| Unit verification | `systemd-analyze verify FILE` | Validate unit configuration |
| Security analysis | `systemd-analyze security UNIT` | Inspect service sandboxing exposure |

## Systemd service architecture in practice

A well-designed production service can be viewed as several connected layers:

1. **Application layer**  
   The program performs its actual business or system function.

2. **Process layer**  
   The application runs as one or more Linux processes.

3. **Service layer**  
   systemd defines how those processes start, stop, restart, and communicate readiness.

4. **Dependency layer**  
   systemd describes relationships with filesystems, networking, databases, sockets, devices, and other services.

5. **Resource layer**  
   cgroups and systemd resource directives constrain CPU, memory, tasks, and I/O.

6. **Security layer**  
   users, groups, capabilities, namespaces, filesystem protections, and other sandboxing controls restrict the service.

7. **Observability layer**  
   journald and monitoring systems provide evidence about service behavior.

8. **Operational layer**  
   administrators manage deployment, upgrades, startup, failure recovery, and shutdown.

Understanding these layers makes systemd easier to reason about than memorizing isolated commands.

## Scope and limitations

systemd behavior depends on:

- Linux distribution
- systemd version
- installed packages
- enabled components
- kernel features
- security framework
- networking implementation
- filesystem layout
- user configuration

Not every directive is available or behaves identically on every systemd version.

Some Linux systems do not use systemd at all.

The concepts in this study file therefore apply most directly to Linux environments where systemd is the active service manager.

The Python examples use only the standard library and intentionally avoid automatically executing commands that modify system state.
