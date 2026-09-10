#!/usr/bin/env python3
"""
Linux Services: systemd, systemctl, and Service Management
===========================================================

A comprehensive, self-contained educational script covering:

- Linux services and daemons
- Processes versus services
- Init systems
- systemd architecture
- Units and unit types
- systemctl fundamentals
- Service lifecycle
- Starting, stopping, restarting, reloading, enabling and disabling services
- Boot targets and startup processes
- Service states and properties
- Unit files
- Dependencies and ordering
- Targets
- Timers
- Sockets
- Environment variables
- Logging with journald
- Service failures and debugging
- Resource limits
- Security hardening
- Restart policies
- User and system services
- Temporary and generated units
- Masking and unmasking
- Presets
- Drop-in configuration
- Service supervision
- Practical automation
- Safe Python interaction with systemd
- Edge cases, limitations, and production considerations

The examples are intentionally conservative. Commands that modify the system are
displayed for study rather than executed automatically. Read-only commands may
be executed when systemd is available.

This file is intended to be readable as source code and executable as a teaching
program on a Linux system.
"""

from __future__ import annotations

import json
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Sequence


# =============================================================================
# SECTION 1: GENERAL PRESENTATION HELPERS
# =============================================================================

def print_title(title: str) -> None:
    """Print a consistent section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def print_subtitle(title: str) -> None:
    """Print a smaller subsection heading."""
    print("\n" + "-" * 78)
    print(title)
    print("-" * 78)


def explain(text: str) -> None:
    """Print explanatory text with readable wrapping."""
    print(textwrap.fill(text.strip(), width=76))


def show_code(code: str) -> None:
    """Display shell commands without executing them."""
    print("$ " + code)


def show_output(output: str) -> None:
    """Display representative or actual command output."""
    if output.strip():
        print(output.rstrip())
    else:
        print("(no output)")


def pause_if_interactive() -> None:
    """
    Pause only when the script is attached to an interactive terminal.

    The pause is deliberately disabled for redirected or automated execution.
    """
    if sys.stdin.isatty() and os.environ.get("LINUX_SERVICES_NO_PAUSE") != "1":
        try:
            input("\nPress Enter to continue...")
        except EOFError:
            pass


# =============================================================================
# SECTION 2: PLATFORM DETECTION
# =============================================================================

def detect_platform() -> dict[str, str | bool]:
    """Collect basic platform information."""
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "systemctl": shutil.which("systemctl") or "",
        "journalctl": shutil.which("journalctl") or "",
        "ps": shutil.which("ps") or "",
        "is_linux": platform.system() == "Linux",
        "is_root": hasattr(os, "geteuid") and os.geteuid() == 0,
    }


def print_platform_information() -> None:
    """Explain the environment in which the script is running."""
    print_title("1. Environment and Linux service concepts")

    info = detect_platform()

    print(f"Operating system : {info['system']}")
    print(f"Kernel release   : {info['release']}")
    print(f"Architecture     : {info['machine']}")
    print(f"Python version   : {info['python']}")
    print(f"systemctl        : {info['systemctl'] or 'not found'}")
    print(f"journalctl       : {info['journalctl'] or 'not found'}")

    if info["is_root"]:
        print("Privilege         : root")
    elif info["is_linux"]:
        print("Privilege         : non-root user")
    else:
        print("Privilege         : platform is not Linux")

    explain(
        """
        A Linux service is a long-running program managed as part of the operating
        system. Examples include SSH servers, web servers, database servers,
        schedulers, network managers, and logging services.

        A process is an executing program instance. A service is an operational
        concept that normally involves a long-running process, a defined
        lifecycle, dependencies, configuration, logging, and supervision.

        Modern Linux distributions commonly use systemd as the init and service
        manager. The systemd process normally runs as PID 1, meaning it is the
        first userspace process started by the kernel and has special
        responsibilities for system initialization and service supervision.
        """
    )


# =============================================================================
# SECTION 3: PROCESSES, DAEMONS, SERVICES, AND INIT SYSTEMS
# =============================================================================

def explain_process_service_relationship() -> None:
    print_title("2. Processes, daemons, services, and init systems")

    concepts = {
        "Process": (
            "An executing instance of a program. It has a PID, memory, file "
            "descriptors, scheduling state, credentials, and other attributes."
        ),
        "Daemon": (
            "A background program designed to provide a persistent service. "
            "Many daemon names historically end with 'd', such as sshd."
        ),
        "Service": (
            "A managed system capability, commonly represented by a systemd "
            "service unit ending in .service."
        ),
        "Init system": (
            "The userspace system responsible for bringing the operating system "
            "into its intended operational state and managing early services."
        ),
        "systemd": (
            "A system and service manager that manages units, dependencies, "
            "startup ordering, supervision, logging integration, and more."
        ),
    }

    for name, description in concepts.items():
        print(f"\n{name}")
        explain(description)

    print_subtitle("Historical context")

    explain(
        """
        Older Linux systems commonly used SysV init scripts. Other systems and
        distributions have used alternatives such as OpenRC, runit, or Upstart.
        systemd introduced a declarative unit model and a dependency graph that
        allows many independent services to start concurrently when their
        prerequisites are satisfied.

        The existence of systemd should not be confused with the existence of
        the Linux kernel. Linux is the kernel. systemd is userspace software
        commonly used to initialize and manage the operating system.
        """
    )

    print_subtitle("Typical lifecycle")

    lifecycle = [
        "Kernel starts and initializes hardware and core kernel facilities.",
        "The kernel starts PID 1.",
        "systemd initializes its manager and reads unit configuration.",
        "systemd establishes targets and dependency relationships.",
        "Required and enabled services are started according to dependencies.",
        "Services remain supervised while the system is operating.",
        "Shutdown or reboot causes systemd to stop units in dependency-aware order.",
    ]

    for index, item in enumerate(lifecycle, start=1):
        print(f"{index}. {item}")


# =============================================================================
# SECTION 4: SYSTEMD ARCHITECTURE
# =============================================================================

def explain_systemd_architecture() -> None:
    print_title("3. systemd architecture")

    explain(
        """
        systemd is more than a command named systemctl. It is an ecosystem of
        components and concepts centered around units and a dependency graph.

        The system manager normally runs as PID 1. A separate per-user systemd
        manager can also exist for user services. systemd uses units to represent
        services, sockets, devices, mounts, automounts, swap areas, targets,
        paths, timers, scopes, slices, and other managed resources.
        """
    )

    print_subtitle("Important components")

    components = [
        ("systemd", "The central system and service manager."),
        ("systemctl", "The primary command-line interface for controlling systemd."),
        ("journald", "The systemd journal service responsible for centralized logging."),
        ("journalctl", "The command-line interface for reading journal entries."),
        ("logind", "Manages user logins, sessions, seats, and related policies."),
        ("udevd", "Handles dynamic device events, commonly integrated with systemd."),
        ("resolved", "Provides DNS resolution services where enabled."),
        ("networkd", "Provides network configuration services where enabled."),
        ("timedated", "Provides a service interface for time and timezone management."),
    ]

    for component, purpose in components:
        print(f"{component:<15} {purpose}")

    print_subtitle("The systemd dependency graph")

    explain(
        """
        systemd does not simply execute a flat list of startup commands. Unit
        relationships can express requirements and ordering.

        Requires= means another unit is required by the relationship.
        Wants= expresses a weaker dependency.
        After= establishes ordering without itself creating a requirement.
        Before= establishes the inverse ordering relationship.

        A critical distinction is that dependency and ordering are different.
        Requires= answers whether a unit relationship exists. After= answers which
        unit should be started first. A service can have After=network.target
        without necessarily requiring network.target.
        """
    )


# =============================================================================
# SECTION 5: UNIT TYPES
# =============================================================================

@dataclass(frozen=True)
class UnitType:
    suffix: str
    meaning: str
    common_use: str


UNIT_TYPES = [
    UnitType(".service", "A supervised service process", "Web server, SSH server, worker"),
    UnitType(".socket", "A listening socket activated by systemd", "On-demand network service"),
    UnitType(".target", "A logical synchronization or grouping point", "Boot states and service groups"),
    UnitType(".timer", "A time-based activation mechanism", "Scheduled maintenance"),
    UnitType(".path", "A filesystem path activation mechanism", "Reacting to file changes"),
    UnitType(".mount", "A filesystem mount", "Mounting storage"),
    UnitType(".automount", "An automount point", "On-demand filesystem mounting"),
    UnitType(".swap", "A swap device or file", "Swap activation"),
    UnitType(".device", "A kernel device exposed through udev", "Hardware dependencies"),
    UnitType(".slice", "A resource-management hierarchy", "CPU and memory grouping"),
    UnitType(".scope", "An externally created process group", "Session/application tracking"),
    UnitType(".busname", "A D-Bus bus name", "D-Bus activation"),
    UnitType(".path", "A filesystem path trigger", "File/directory monitoring"),
]


def explain_unit_types() -> None:
    print_title("4. systemd units and unit types")

    explain(
        """
        A unit is a configuration object understood by systemd. Unit names
        normally contain a name followed by a suffix. The suffix identifies the
        unit type.

        The most important type for traditional service administration is
        .service, but systemd can use many other unit types to model dependencies
        and activation mechanisms.
        """
    )

    for unit in UNIT_TYPES:
        print(f"{unit.suffix:<12} {unit.meaning:<42} {unit.common_use}")


# =============================================================================
# SECTION 6: SYSTEMCTL COMMAND REFERENCE
# =============================================================================

SYSTEMCTL_COMMANDS = [
    ("status", "Show runtime status and recent log information."),
    ("start", "Start a unit immediately."),
    ("stop", "Stop a running unit."),
    ("restart", "Stop and start a unit."),
    ("try-restart", "Restart only if the unit is already running."),
    ("reload", "Ask a service to reload its configuration if supported."),
    ("reload-or-restart", "Reload when supported, otherwise restart."),
    ("enable", "Configure a unit to start automatically according to its install rules."),
    ("disable", "Remove the automatic startup relationship."),
    ("enable --now", "Enable a unit and start it immediately."),
    ("disable --now", "Disable a unit and stop it immediately."),
    ("is-active", "Check whether a unit is currently active."),
    ("is-enabled", "Check whether a unit is configured to start automatically."),
    ("is-failed", "Check whether a unit is in a failed state."),
    ("mask", "Make a unit impossible to start through normal activation."),
    ("unmask", "Remove a systemd mask."),
    ("daemon-reload", "Ask systemd to reread unit files and drop-ins."),
    ("cat", "Display the unit file and applicable fragments."),
    ("show", "Display machine-readable unit properties."),
    ("list-units", "List units currently loaded into the manager."),
    ("list-unit-files", "List installed unit files and their enablement states."),
    ("list-dependencies", "Display a unit's dependency tree."),
    ("get-default", "Display the default boot target."),
    ("set-default", "Change the default boot target."),
    ("list-timers", "List timer units and their scheduling state."),
]


def explain_systemctl() -> None:
    print_title("5. systemctl fundamentals")

    explain(
        """
        systemctl is the primary administrative interface to systemd. Most
        commands take a unit name, such as ssh.service, nginx.service, or a
        target such as multi-user.target.

        A command that changes system state normally requires appropriate
        privileges. The examples below are intentionally displayed rather than
        executed automatically.
        """
    )

    for command, meaning in SYSTEMCTL_COMMANDS:
        print(f"systemctl {command:<22} {meaning}")

    print_subtitle("Safe read-only examples")

    examples = [
        "systemctl status ssh.service",
        "systemctl is-active ssh.service",
        "systemctl is-enabled ssh.service",
        "systemctl is-failed ssh.service",
        "systemctl show ssh.service",
        "systemctl cat ssh.service",
        "systemctl list-units --type=service",
        "systemctl list-unit-files --type=service",
        "systemctl list-dependencies ssh.service",
        "systemctl get-default",
        "systemctl list-timers --all",
    ]

    for command in examples:
        show_code(command)

    print_subtitle("State-changing examples")

    examples = [
        "sudo systemctl start example.service",
        "sudo systemctl stop example.service",
        "sudo systemctl restart example.service",
        "sudo systemctl reload example.service",
        "sudo systemctl enable example.service",
        "sudo systemctl disable example.service",
        "sudo systemctl enable --now example.service",
        "sudo systemctl disable --now example.service",
    ]

    for command in examples:
        show_code(command)


# =============================================================================
# SECTION 7: SERVICE STATES
# =============================================================================

def explain_service_states() -> None:
    print_title("6. Service states and status interpretation")

    states = {
        "active (running)": "The service is currently running.",
        "active (exited)": (
            "The unit completed successfully but remains considered active. "
            "Common with Type=oneshot and RemainAfterExit=yes."
        ),
        "inactive (dead)": "The service is not running and has no active state.",
        "failed": "The service attempted to start or operate and encountered failure.",
        "activating": "The service is currently starting.",
        "deactivating": "The service is currently stopping.",
        "reloading": "The service is currently processing a reload operation.",
    }

    for state, meaning in states.items():
        print(f"\n{state}")
        explain(meaning)

    print_subtitle("Important distinction: active versus enabled")

    explain(
        """
        active describes the current runtime state. enabled describes whether
        systemd has an installation relationship that causes the unit to be
        activated automatically in the appropriate context.

        A service can therefore be active but disabled, or inactive but enabled.
        For example, a manually started service may be active without being
        enabled for boot.
        """
    )

    print_subtitle("Example")

    print("systemctl is-active nginx.service")
    print("Possible result: active")

    print("\nsystemctl is-enabled nginx.service")
    print("Possible result: enabled")


# =============================================================================
# SECTION 8: UNIT FILE STRUCTURE
# =============================================================================

SAMPLE_UNIT_FILE = """[Unit]
Description=Example Python Worker
After=network.target
Wants=network.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 /opt/example-worker/worker.py
Restart=on-failure
RestartSec=5
User=example-worker
Group=example-worker
Environment=APP_ENV=production
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
"""


def explain_unit_file() -> None:
    print_title("7. Anatomy of a .service unit file")

    explain(
        """
        A service unit commonly contains [Unit], [Service], and [Install]
        sections. The sections have different responsibilities.

        [Unit] describes the unit itself and its relationships to other units.
        [Service] describes how the service process should be started and
        supervised. [Install] describes how enablement creates relationships
        with targets or other units.
        """
    )

    print_subtitle("Representative service unit")

    print(SAMPLE_UNIT_FILE)

    print_subtitle("Directive explanations")

    directives = {
        "Description=": "Human-readable description.",
        "After=": "Ordering relationship.",
        "Wants=": "Weak dependency relationship.",
        "Requires=": "Stronger dependency relationship.",
        "Type=": "Describes how systemd determines service startup behavior.",
        "ExecStart=": "Command used to start the service.",
        "ExecStop=": "Optional command used to stop the service.",
        "ExecReload=": "Optional command used to reload configuration.",
        "Restart=": "Policy for restarting after termination.",
        "RestartSec=": "Delay before an automatic restart.",
        "User=": "Account under which the service runs.",
        "Group=": "Primary group under which the service runs.",
        "Environment=": "Environment variables passed to the service.",
        "WorkingDirectory=": "Working directory for the service process.",
        "TimeoutStartSec=": "Maximum allowed startup time.",
        "TimeoutStopSec=": "Maximum allowed shutdown time.",
        "NoNewPrivileges=": "Prevents gaining additional privileges.",
        "WantedBy=": "Target relationship used by systemctl enable.",
    }

    for directive, explanation in directives.items():
        print(f"{directive:<22} {explanation}")


# =============================================================================
# SECTION 9: SERVICE TYPES
# =============================================================================

SERVICE_TYPES = {
    "simple": (
        "The process specified by ExecStart is considered the main process. "
        "This is the normal default for many modern services."
    ),
    "exec": (
        "Similar to simple, but systemd waits until the executable has actually "
        "been successfully invoked."
    ),
    "forking": (
        "Used by programs that start and then fork into the background. "
        "PIDFile= may be relevant for identifying the main process."
    ),
    "oneshot": (
        "Used for commands intended to perform an operation and exit."
    ),
    "notify": (
        "The service communicates readiness to systemd using systemd's notification "
        "protocol."
    ),
    "dbus": (
        "The service is considered started after acquiring a specified D-Bus name."
    ),
    "idle": (
        "Similar to simple but delayed until active jobs have been dispatched."
    ),
}


def explain_service_types() -> None:
    print_title("8. Service Type= options")

    for service_type, meaning in SERVICE_TYPES.items():
        print(f"\nType={service_type}")
        explain(meaning)

    print_subtitle("Important design choice")

    explain(
        """
        Choosing Type= is not cosmetic. It determines how systemd interprets
        service startup and readiness. A modern foreground application normally
        works well with Type=simple or Type=exec. A legacy daemon that forks into
        the background may require Type=forking. A short-lived administrative
        task is often better represented by Type=oneshot.

        Services should generally remain in the foreground when designed for
        systemd. Double-forking or implementing daemonization manually can make
        process supervision more complicated.
        """
    )


# =============================================================================
# SECTION 10: SERVICE LIFECYCLE
# =============================================================================

def explain_service_lifecycle() -> None:
    print_title("9. Service lifecycle management")

    explain(
        """
        Service management consists of several distinct operations. Starting a
        service changes its runtime state. Enabling a service changes its boot
        or activation configuration. Restarting terminates and starts the
        service again. Reloading asks the existing process to reread
        configuration without necessarily replacing the process.
        """
    )

    print_subtitle("Start")

    print("sudo systemctl start example.service")
    explain(
        "Starts the service now. It does not by itself mean that the service will "
        "start automatically after the next reboot."
    )

    print_subtitle("Stop")

    print("sudo systemctl stop example.service")
    explain(
        "Stops the service now. It does not necessarily disable future automatic "
        "activation."
    )

    print_subtitle("Restart")

    print("sudo systemctl restart example.service")
    explain(
        "Stops and starts the service. This is appropriate when configuration "
        "changes require a fresh process."
    )

    print_subtitle("Reload")

    print("sudo systemctl reload example.service")
    explain(
        "Requests configuration reload through the service's supported reload "
        "mechanism. It only works when the service defines or otherwise supports "
        "reload behavior."
    )

    print_subtitle("Reload-or-restart")

    print("sudo systemctl reload-or-restart example.service")
    explain(
        "Attempts a reload where supported and falls back to restart. The exact "
        "behavior depends on systemd and the unit's configuration."
    )

    print_subtitle("Enable")

    print("sudo systemctl enable example.service")
    explain(
        "Creates the relationships specified by the unit's [Install] section. "
        "It configures automatic activation but normally does not start the "
        "service immediately."
    )

    print_subtitle("Enable and start")

    print("sudo systemctl enable --now example.service")
    explain(
        "Combines enablement and immediate startup, which is convenient during "
        "service installation."
    )


# =============================================================================
# SECTION 11: STARTUP AND TARGETS
# =============================================================================

def explain_targets() -> None:
    print_title("10. Boot targets and startup processes")

    explain(
        """
        A target is a unit used primarily to group units and represent a system
        state. Targets are comparable to logical milestones rather than ordinary
        executable programs.

        multi-user.target commonly represents a fully operational,
        non-graphical multi-user environment. graphical.target generally extends
        that state with graphical-session-related requirements. The exact
        composition depends on the distribution.
        """
    )

    target_examples = [
        ("basic.target", "Basic system initialization."),
        ("sysinit.target", "Core system initialization."),
        ("sockets.target", "Socket units that should be available."),
        ("network.target", "Basic network availability synchronization point."),
        ("network-online.target", "A stronger network-online synchronization point when supported."),
        ("multi-user.target", "Common multi-user operational state."),
        ("graphical.target", "Common graphical operational state."),
        ("rescue.target", "Single-user rescue environment."),
        ("emergency.target", "Minimal emergency environment."),
        ("shutdown.target", "Shutdown dependency point."),
        ("reboot.target", "Reboot target."),
    ]

    for target, description in target_examples:
        print(f"{target:<24} {description}")

    print_subtitle("Useful commands")

    commands = [
        "systemctl get-default",
        "systemctl list-dependencies multi-user.target",
        "systemctl list-dependencies graphical.target",
        "systemctl isolate multi-user.target",
        "sudo systemctl set-default multi-user.target",
    ]

    for command in commands:
        show_code(command)

    explain(
        """
        Commands such as isolate and set-default can materially change system
        behavior. They should be used only when the operator understands the
        target relationships and has appropriate recovery access.
        """
    )


# =============================================================================
# SECTION 12: DEPENDENCIES AND ORDERING
# =============================================================================

def explain_dependencies() -> None:
    print_title("11. Dependencies and ordering")

    relationships = [
        ("Requires=A.service", "The unit requires A. Failure can affect the relationship."),
        ("Wants=A.service", "The unit wants A but the dependency is weaker."),
        ("Requisite=A.service", "A must already be active when the dependent starts."),
        ("After=A.service", "The current unit starts after A when both are involved."),
        ("Before=A.service", "The current unit starts before A when both are involved."),
        ("BindsTo=A.service", "Stronger lifecycle coupling than Requires in relevant cases."),
        ("PartOf=A.service", "Restart/stop relationships can propagate through the group."),
        ("Conflicts=A.service", "The units cannot be active together."),
    ]

    for relationship, explanation in relationships:
        print(f"\n{relationship}")
        explain(explanation)

    print_subtitle("Dependency is not ordering")

    print("Requires=database.service")
    print("After=database.service")

    explain(
        """
        These directives solve different problems. Requires expresses a
        relationship. After expresses sequencing. Using Requires without
        appropriate ordering can produce a dependency relationship without the
        desired startup sequence. Using After without a dependency can express
        ordering only when both units are activated.
        """
    )

    print_subtitle("Why this matters")

    explain(
        """
        Production services should declare the dependencies they genuinely need
        rather than relying on accidental startup order. Excessive dependencies
        can make boot slower and failure domains larger. Missing dependencies can
        create race conditions during startup.
        """
    )


# =============================================================================
# SECTION 13: COMMON STARTUP PATTERNS
# =============================================================================

def explain_startup_patterns() -> None:
    print_title("12. Common startup patterns")

    patterns = {
        "Network-dependent service": """
[Unit]
After=network-online.target
Wants=network-online.target
""",
        "Database-dependent service": """
[Unit]
Requires=database.service
After=database.service
""",
        "Service started at multi-user boot": """
[Install]
WantedBy=multi-user.target
""",
        "Simple foreground application": """
[Service]
Type=exec
ExecStart=/opt/example/app
Restart=on-failure
""",
        "Short task": """
[Service]
Type=oneshot
ExecStart=/opt/example/maintenance-task
""",
    }

    for name, configuration in patterns.items():
        print(f"\n{name}")
        print(configuration.strip())


# =============================================================================
# SECTION 14: RESTART POLICIES
# =============================================================================

def explain_restart_policies() -> None:
    print_title("13. Automatic restart and failure recovery")

    policies = {
        "no": "Do not automatically restart.",
        "on-success": "Restart when the service exits successfully.",
        "on-failure": "Restart after unsuccessful termination conditions.",
        "on-abnormal": "Restart after abnormal termination.",
        "on-abort": "Restart after abnormal termination caused by an uncaught signal.",
        "on-watchdog": "Restart when a watchdog failure is detected.",
        "always": "Restart regardless of how the service exits, subject to systemd rules.",
    }

    for policy, meaning in policies.items():
        print(f"Restart={policy:<14} {meaning}")

    print_subtitle("Example")

    print("""[Service]
ExecStart=/opt/example/worker
Restart=on-failure
RestartSec=5
""")

    explain(
        """
        Automatic restarts improve availability but can also hide application
        defects or create restart loops. Restart policies should be paired with
        appropriate logging, rate limits, health monitoring, and application
        correctness.
        """
    )


# =============================================================================
# SECTION 15: RESTART RATE LIMITING
# =============================================================================

def explain_restart_limits() -> None:
    print_title("14. Restart storms and rate limiting")

    explain(
        """
        A broken service can exit immediately every time it is started. Automatic
        restart policies can therefore create a restart storm. systemd includes
        controls for limiting repeated starts.

        The exact available directives and defaults depend on the systemd version.
        A service operator should inspect the local systemd documentation and
        generated unit properties before relying on a particular default.
        """
    )

    print("""[Unit]
StartLimitIntervalSec=60
StartLimitBurst=5

[Service]
Restart=on-failure
RestartSec=5
""")

    explain(
        """
        This conceptual configuration limits repeated starts during a time
        window. It is important to distinguish a service being configured to
        restart from the service actually being healthy.
        """
    )


# =============================================================================
# SECTION 16: ENVIRONMENT AND CONFIGURATION
# =============================================================================

def explain_environment_configuration() -> None:
    print_title("15. Environment variables and service configuration")

    explain(
        """
        Services often need configuration such as application environment,
        paths, endpoints, feature flags, and credentials. systemd supports
        several ways of supplying environment information.

        Environment= can define variables directly in the unit. EnvironmentFile=
        can read variables from a separate file. Drop-in configuration is often
        preferable to editing distribution-provided unit files directly.
        """
    )

    print("""[Service]
Environment="APP_ENV=production"
Environment="APP_PORT=8080"
EnvironmentFile=-/etc/example/app.env
""")

    explain(
        """
        The leading hyphen on EnvironmentFile= makes the file optional. Secrets
        require additional care. Environment variables can be exposed through
        process inspection or diagnostic interfaces, so they should not
        automatically be treated as a secure secret store.
        """
    )


# =============================================================================
# SECTION 17: DROP-IN CONFIGURATION
# =============================================================================

def explain_drop_ins() -> None:
    print_title("16. Drop-in configuration")

    explain(
        """
        Package-managed unit files should generally not be edited directly.
        Updates can overwrite such modifications.

        systemd supports drop-in directories. A common location is:

        /etc/systemd/system/example.service.d/

        A file such as override.conf in that directory can override or extend
        selected settings.
        """
    )

    print("""sudo systemctl edit example.service""")

    print("\nExample drop-in content:")
    print("""[Service]
Restart=on-failure
RestartSec=10
""")

    explain(
        """
        After changing unit configuration, systemd may need to reread the
        configuration:

        sudo systemctl daemon-reload

        If the changed property affects an already-running service, the service
        may also need to be restarted.
        """
    )


# =============================================================================
# SECTION 18: DAEMON-RELOAD VERSUS RESTART
# =============================================================================

def explain_daemon_reload() -> None:
    print_title("17. daemon-reload versus restart")

    print("sudo systemctl daemon-reload")
    explain(
        """
        daemon-reload tells systemd to reread unit files. It does not restart
        every service and it does not itself apply every changed service
        property to an already-running process.
        """
    )

    print("\nsudo systemctl restart example.service")
    explain(
        """
        restart actually replaces the running service process according to the
        service's lifecycle rules.
        """
    )

    print("\nTypical configuration workflow:")
    print("1. Edit or create the unit configuration.")
    print("2. Run: sudo systemctl daemon-reload")
    print("3. Run: sudo systemctl restart example.service")
    print("4. Run: systemctl status example.service")
    print("5. Inspect logs with journalctl if necessary.")


# =============================================================================
# SECTION 19: JOURNALD AND JOURNALCTL
# =============================================================================

def explain_journald() -> None:
    print_title("18. Logging with journald and journalctl")

    explain(
        """
        systemd commonly integrates service output with journald. journalctl
        provides access to journal entries.

        Logs can be filtered by unit, boot, priority, time, PID, executable, or
        other metadata depending on what is available on the system.
        """
    )

    commands = [
        "journalctl -u example.service",
        "journalctl -u example.service -n 100",
        "journalctl -u example.service -f",
        "journalctl -u example.service --since today",
        "journalctl -u example.service --since '1 hour ago'",
        "journalctl -b",
        "journalctl -b -1",
        "journalctl -p err",
        "journalctl -xeu example.service",
    ]

    for command in commands:
        show_code(command)

    explain(
        """
        The -f option follows new messages similarly to tailing a live log.
        -b restricts output to a boot. -1 refers to the previous boot. -p filters
        by priority. -u selects a systemd unit.

        Log retention depends on distribution and journald configuration.
        Therefore, journald should not automatically be assumed to provide
        unlimited historical storage.
        """
    )


# =============================================================================
# SECTION 20: SERVICE FAILURE DEBUGGING
# =============================================================================

def explain_debugging() -> None:
    print_title("19. Debugging a failed service")

    explain(
        """
        When a service fails, do not immediately restart it repeatedly. First
        identify whether the failure occurred during configuration parsing,
        executable lookup, permissions, dependency activation, startup timeout,
        runtime execution, resource exhaustion, or application logic.
        """
    )

    print_subtitle("Structured diagnostic workflow")

    commands = [
        "systemctl status example.service",
        "systemctl is-failed example.service",
        "journalctl -u example.service -b --no-pager",
        "systemctl cat example.service",
        "systemctl show example.service",
        "systemctl list-dependencies example.service",
    ]

    for step, command in enumerate(commands, start=1):
        print(f"{step}. {command}")

    print_subtitle("Typical causes")

    causes = [
        "Executable path does not exist.",
        "The executable is not executable.",
        "The configured User= does not exist.",
        "The service lacks permission to access a file or directory.",
        "The working directory does not exist.",
        "A required network or dependency relationship is missing.",
        "The application exits immediately because configuration is invalid.",
        "The application binds to an unavailable port.",
        "A mandatory environment variable is absent.",
        "The startup timeout is too short.",
        "The service enters a restart loop.",
        "SELinux or another mandatory access-control system denies an operation.",
        "Resource limits prevent the process from operating correctly.",
    ]

    for cause in causes:
        print(f"- {cause}")


# =============================================================================
# SECTION 21: MACHINE-READABLE SYSTEMCTL OUTPUT
# =============================================================================

def explain_machine_readable_properties() -> None:
    print_title("20. Inspecting unit properties")

    explain(
        """
        systemctl show is useful for automation because it exposes structured
        properties rather than human-oriented status text. Individual
        properties can be requested with -p.
        """
    )

    commands = [
        "systemctl show example.service",
        "systemctl show -p ActiveState example.service",
        "systemctl show -p SubState example.service",
        "systemctl show -p MainPID example.service",
        "systemctl show -p FragmentPath example.service",
        "systemctl show -p UnitFileState example.service",
    ]

    for command in commands:
        show_code(command)

    explain(
        """
        Automation should prefer machine-readable output where possible.
        Parsing human-readable status messages is fragile because formatting can
        change between versions and environments.
        """
    )


# =============================================================================
# SECTION 22: PYTHON SYSTEMCTL WRAPPER
# =============================================================================

@dataclass
class CommandResult:
    command: list[str]
    return_code: int
    stdout: str
    stderr: str

    @property
    def succeeded(self) -> bool:
        return self.return_code == 0


class SystemdManager:
    """
    Safe Python interface for querying systemd.

    Mutating operations are intentionally not included in this class. This keeps
    the educational program from accidentally starting, stopping, enabling,
    disabling, masking, or otherwise changing services.
    """

    def __init__(self, systemctl_path: str | None = None):
        self.systemctl_path = systemctl_path or shutil.which("systemctl")

    @property
    def available(self) -> bool:
        return bool(self.systemctl_path)

    def run_read_only(self, *arguments: str) -> CommandResult:
        """Run a systemctl command that is intended to be read-only."""
        if not self.available:
            return CommandResult(
                command=["systemctl", *arguments],
                return_code=127,
                stdout="",
                stderr="systemctl was not found on this system.",
            )

        command = [self.systemctl_path, *arguments]

        try:
            completed = subprocess.run(
                command,
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return CommandResult(
                command=command,
                return_code=124,
                stdout="",
                stderr="Command timed out.",
            )
        except OSError as exc:
            return CommandResult(
                command=command,
                return_code=1,
                stdout="",
                stderr=str(exc),
            )

        return CommandResult(
            command=command,
            return_code=completed.returncode,
            stdout=completed.stdout,
            stderr=completed.stderr,
        )

    def is_active(self, unit: str) -> bool:
        result = self.run_read_only("is-active", unit)
        return result.succeeded and result.stdout.strip() == "active"

    def is_enabled(self, unit: str) -> bool:
        result = self.run_read_only("is-enabled", unit)
        return result.succeeded and result.stdout.strip() == "enabled"

    def show_property(self, unit: str, property_name: str) -> str | None:
        result = self.run_read_only("show", "-p", property_name, "--value", unit)
        if not result.succeeded:
            return None
        return result.stdout.strip()

    def status(self, unit: str) -> CommandResult:
        return self.run_read_only("status", unit, "--no-pager")

    def unit_file(self, unit: str) -> CommandResult:
        return self.run_read_only("cat", unit)

    def dependencies(self, unit: str) -> CommandResult:
        return self.run_read_only("list-dependencies", unit)


def demonstrate_python_systemd_queries() -> None:
    print_title("21. Querying systemd safely from Python")

    manager = SystemdManager()

    if not manager.available:
        explain(
            """
            systemctl is not available in this environment. The Python
            integration examples remain valid for a Linux system using systemd,
            but no live query will be executed here.
            """
        )
        return

    candidate_units = [
        "systemd-journald.service",
        "cron.service",
        "crond.service",
        "sshd.service",
        "ssh.service",
    ]

    selected_unit = None

    for unit in candidate_units:
        result = manager.run_read_only("show", "-p", "LoadState", "--value", unit)
        if result.succeeded and result.stdout.strip() == "loaded":
            selected_unit = unit
            break

    if selected_unit is None:
        explain(
            """
            No common demonstration service was detected by name. Use the
            systemctl list-unit-files command to identify services on the local
            distribution.
            """
        )
        return

    print(f"Detected demonstration unit: {selected_unit}")

    active = manager.is_active(selected_unit)
    enabled = manager.is_enabled(selected_unit)

    print(f"Active : {active}")
    print(f"Enabled: {enabled}")

    properties = [
        "LoadState",
        "ActiveState",
        "SubState",
        "MainPID",
        "FragmentPath",
        "UnitFileState",
    ]

    print_subtitle("Selected properties")

    for property_name in properties:
        value = manager.show_property(selected_unit, property_name)
        print(f"{property_name:<18}: {value if value else '(unavailable)'}")


# =============================================================================
# SECTION 23: UNIT FILE LOCATIONS
# =============================================================================

def explain_unit_locations() -> None:
    print_title("22. Unit file locations and precedence")

    locations = [
        (
            "/etc/systemd/system/",
            "Administrator-created or administrator-customized system units."
        ),
        (
            "/run/systemd/system/",
            "Runtime-generated or runtime-created units; generally temporary."
        ),
        (
            "/usr/lib/systemd/system/",
            "Common vendor/package-provided unit location on many distributions."
        ),
        (
            "/lib/systemd/system/",
            "Package-provided unit location used by some distributions."
        ),
        (
            "~/.config/systemd/user/",
            "Per-user unit files."
        ),
        (
            "/etc/systemd/user/",
            "Administrator-level user-manager unit configuration."
        ),
    ]

    for path, description in locations:
        print(f"{path:<34} {description}")

    explain(
        """
        Exact paths vary between distributions and package layouts. The most
        reliable way to discover the unit actually in use is systemctl cat or
        systemctl show -p FragmentPath.

        Configuration precedence is important. Administrator configuration in
        /etc generally takes precedence over vendor-provided configuration.
        Drop-ins provide a controlled mechanism for overrides.
        """
    )


# =============================================================================
# SECTION 24: MASKING
# =============================================================================

def explain_masking() -> None:
    print_title("23. Masking and unmasking")

    explain(
        """
        Masking is stronger than disabling. A masked unit is linked to
        /dev/null, preventing normal activation of the unit.

        Disabling removes an enablement relationship. Masking prevents the unit
        from being started through ordinary activation paths.
        """
    )

    print("sudo systemctl mask example.service")
    print("sudo systemctl unmask example.service")

    explain(
        """
        Masking is useful when an administrator needs to guarantee that a
        service cannot be started accidentally or through an indirect
        dependency. It should be used carefully because another unit may rely
        on the masked unit.
        """
    )


# =============================================================================
# SECTION 25: USER SERVICES
# =============================================================================

def explain_user_services() -> None:
    print_title("24. System services versus user services")

    explain(
        """
        systemd supports both system-wide and per-user service managers.

        System services normally run under the system manager and are controlled
        through commands such as systemctl status example.service.

        User services belong to an individual user's systemd manager and are
        commonly controlled with systemctl --user.
        """
    )

    print_subtitle("Examples")

    commands = [
        "systemctl --user status example.service",
        "systemctl --user start example.service",
        "systemctl --user enable example.service",
        "systemctl --user list-units --type=service",
    ]

    for command in commands:
        show_code(command)

    explain(
        """
        User services can be appropriate for applications that do not need
        system-wide privileges. They can reduce the need to run application
        processes as root.
        """
    )


# =============================================================================
# SECTION 26: SECURITY PRINCIPLES
# =============================================================================

def explain_security() -> None:
    print_title("25. Service security and privilege reduction")

    explain(
        """
        A service is an important security boundary. A compromised network
        service running as root can potentially compromise the entire system.
        Running services with the minimum required privileges significantly
        reduces the impact of compromise.
        """
    )

    security_directives = {
        "User=": "Run under a dedicated non-root account when possible.",
        "Group=": "Use an appropriately restricted group.",
        "NoNewPrivileges=": "Prevent gaining additional privileges.",
        "PrivateTmp=": "Provide a private temporary directory view where appropriate.",
        "ProtectSystem=": "Restrict write access to system paths.",
        "ProtectHome=": "Restrict access to user home directories.",
        "ReadWritePaths=": "Explicitly allow writes where required.",
        "ReadOnlyPaths=": "Make selected paths read-only.",
        "InaccessiblePaths=": "Hide selected paths from the service.",
        "PrivateDevices=": "Restrict device access when appropriate.",
        "RestrictAddressFamilies=": "Limit usable network address families.",
        "RestrictNamespaces=": "Restrict namespace creation where appropriate.",
        "CapabilityBoundingSet=": "Reduce Linux capabilities available to the service.",
    }

    for directive, purpose in security_directives.items():
        print(f"{directive:<28} {purpose}")

    print_subtitle("Example hardening profile")

    print("""[Service]
User=example-worker
Group=example-worker
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/var/lib/example-worker
""")

    explain(
        """
        Hardening directives must be tested against the application's actual
        behavior. Overly restrictive settings can prevent legitimate access to
        files, devices, namespaces, sockets, or system interfaces.

        Security hardening should complement application-level authentication,
        authorization, input validation, patching, secret management, network
        controls, and least-privilege design.
        """
    )


# =============================================================================
# SECTION 27: RESOURCE MANAGEMENT
# =============================================================================

def explain_resource_management() -> None:
    print_title("26. Resource management with systemd")

    explain(
        """
        systemd integrates with Linux control groups, commonly called cgroups.
        Cgroups allow processes to be grouped and resource-controlled.

        This enables administrators to constrain or account for resources such
        as CPU time and memory.
        """
    )

    directives = {
        "MemoryMax=": "Hard memory limit for the unit.",
        "MemoryHigh=": "Memory pressure boundary used for throttling/reclaim behavior.",
        "CPUQuota=": "CPU time quota.",
        "CPUWeight=": "Relative CPU scheduling weight.",
        "IOWeight=": "Relative I/O weight.",
        "TasksMax=": "Maximum number of tasks/processes/threads allowed.",
        "LimitNOFILE=": "Maximum number of open file descriptors.",
        "LimitNPROC=": "Process limit where supported by the service manager's limits.",
    }

    for directive, explanation in directives.items():
        print(f"{directive:<18} {explanation}")

    print_subtitle("Example")

    print("""[Service]
MemoryMax=512M
CPUQuota=50%
TasksMax=100
LimitNOFILE=4096
""")

    explain(
        """
        Resource limits should be selected from observed workload requirements.
        Arbitrary low limits can cause failures that are difficult to diagnose.
        Resource controls are particularly useful for protecting a host from a
        runaway service.
        """
    )


# =============================================================================
# SECTION 28: TIMERS
# =============================================================================

def explain_timers() -> None:
    print_title("27. systemd timers")

    explain(
        """
        A .timer unit schedules activation of another unit, commonly a
        corresponding .service unit. Timers can replace many traditional cron
        use cases while integrating with systemd dependencies and journald.
        """
    )

    print("Example timer:")
    print("""[Unit]
Description=Run cleanup service every day

[Timer]
OnCalendar=daily
Persistent=true

[Install]
WantedBy=timers.target
""")

    print("\nCorresponding service:")
    print("""[Unit]
Description=Cleanup task

[Service]
Type=oneshot
ExecStart=/usr/local/bin/cleanup
""")

    print_subtitle("Useful commands")

    for command in [
        "systemctl list-timers --all",
        "systemctl status example.timer",
        "sudo systemctl enable --now example.timer",
        "journalctl -u example.service",
    ]:
        show_code(command)

    explain(
        """
        Persistent=true is useful when a scheduled event should be triggered
        after the machine has been powered off during the intended schedule.
        The exact scheduling behavior depends on the timer expression and
        systemd version.
        """
    )


# =============================================================================
# SECTION 29: SOCKET ACTIVATION
# =============================================================================

def explain_socket_activation() -> None:
    print_title("28. Socket activation")

    explain(
        """
        Socket activation allows systemd to listen on a socket before the
        service process itself is running. When traffic arrives, systemd can
        activate the associated service.

        This can reduce idle resource consumption and can improve startup
        coordination for suitable applications.
        """
    )

    print("Example socket:")
    print("""[Socket]
ListenStream=8080
Accept=no
""")

    print("\nExample service relationship:")
    print("""[Unit]
Requires=example.socket
After=example.socket

[Service]
ExecStart=/opt/example/server
""")

    explain(
        """
        Socket activation requires application support for the socket model.
        A service must correctly receive and use the file descriptors supplied
        by the service manager.
        """
    )


# =============================================================================
# SECTION 30: PATH ACTIVATION
# =============================================================================

def explain_path_units() -> None:
    print_title("29. Path activation")

    explain(
        """
        A .path unit can activate another unit when a filesystem path changes or
        meets a specified condition. This is useful for lightweight event-driven
        workflows.
        """
    )

    print("""[Path]
PathModified=/var/lib/example/input.txt

[Install]
WantedBy=multi-user.target
""")

    explain(
        """
        The path unit normally activates a corresponding service. It should not
        be treated as a replacement for every filesystem event-processing
        architecture. High-volume or complex event streams may require a
        dedicated event-processing system.
        """
    )


# =============================================================================
# SECTION 31: SERVICE PROCESS TYPES
# =============================================================================

def explain_process_relationships() -> None:
    print_title("30. Main PID, child processes, and process supervision")

    explain(
        """
        systemd tracks the processes belonging to a unit through cgroups and
        related service-manager state. The MainPID property identifies the main
        process when systemd can determine one.

        Modern service design generally favors a clear foreground main process.
        This makes supervision, signal handling, exit status, resource tracking,
        and logging easier to reason about.
        """
    )

    print_subtitle("Inspecting process information")

    commands = [
        "systemctl show -p MainPID example.service",
        "systemctl status example.service",
        "systemctl show -p ControlGroup example.service",
        "ps -ef",
        "ps -p <PID> -o pid,ppid,user,stat,etime,cmd",
    ]

    for command in commands:
        show_code(command)


# =============================================================================
# SECTION 32: SIGNALS AND STOPPING
# =============================================================================

def explain_signals() -> None:
    print_title("31. Signals, graceful shutdown, and termination")

    explain(
        """
        When stopping a service, systemd can send termination signals to the
        processes belonging to the unit. Well-designed applications should
        handle termination gracefully, close resources, flush important state,
        and exit within a reasonable time.

        Poor signal handling can result in forced termination after the service's
        stop timeout.
        """
    )

    print("""[Service]
TimeoutStopSec=30
KillSignal=SIGTERM
""")

    explain(
        """
        SIGTERM is commonly used for graceful termination. SIGKILL cannot be
        caught or handled by the process and is therefore a last-resort
        mechanism when graceful shutdown does not complete.
        """
    )


# =============================================================================
# SECTION 33: EXIT STATUS AND FAILURE
# =============================================================================

def explain_exit_status() -> None:
    print_title("32. Exit status and service failure")

    explain(
        """
        A service process communicates part of its result through an exit
        status. Zero conventionally represents success. Non-zero values usually
        represent failure.

        systemd uses exit status, signals, timeout conditions, watchdog
        conditions, and other state information when determining service state.
        """
    )

    print("Example shell application result:")
    print("exit 0   -> successful completion")
    print("exit 1   -> generic failure")

    print("\nService configuration can explicitly recognize selected status values:")
    print("""[Service]
Type=oneshot
ExecStart=/usr/local/bin/check
SuccessExitStatus=0 2
""")

    explain(
        """
        SuccessExitStatus should be used only when the application's exit
        semantics are well understood. Treating an actual failure code as
        success can conceal operational problems.
        """
    )


# =============================================================================
# SECTION 34: WATCHDOGS
# =============================================================================

def explain_watchdogs() -> None:
    print_title("33. Service watchdogs")

    explain(
        """
        systemd can supervise applications using watchdog notifications when
        watchdog support is configured. The application must periodically
        communicate that it is healthy.

        A watchdog detects certain classes of application failure that ordinary
        process-existence checks cannot detect. A process may still exist while
        being deadlocked or otherwise unable to perform useful work.
        """
    )

    print("""[Service]
Type=notify
WatchdogSec=30
Restart=on-failure
""")

    explain(
        """
        Watchdogs should measure a meaningful health signal. Setting an
        aggressive timeout without considering application startup and workload
        behavior can cause false restarts.
        """
    )


# =============================================================================
# SECTION 35: SECURITY AND SECRETS
# =============================================================================

def explain_secret_handling() -> None:
    print_title("34. Secrets and credentials")

    explain(
        """
        Service configuration often requires passwords, API keys, certificates,
        or other sensitive material. Storing secrets directly in a world-readable
        unit file is unsafe.

        Environment variables also require care because process environments can
        sometimes be inspected by privileged users or diagnostic mechanisms.

        Production systems should use appropriate operating-system permissions,
        dedicated secret-management mechanisms where available, restricted
        credential files, and least-privilege service accounts.
        """
    )

    print_subtitle("Avoid")

    print("Environment=DATABASE_PASSWORD=plain-text-secret")

    print_subtitle("Prefer the narrowest practical access")

    print("""[Service]
User=example-app
Group=example-app
EnvironmentFile=/etc/example-app/app.env
""")

    explain(
        """
        The configuration file itself must then be protected with suitable
        ownership and permissions. A secure storage mechanism is not useful if
        the service account or unrelated users can read the secret anyway.
        """
    )


# =============================================================================
# SECTION 36: COMMON MISTAKES
# =============================================================================

def explain_common_mistakes() -> None:
    print_title("35. Common mistakes")

    mistakes = [
        (
            "Starting a service and assuming it is enabled",
            "start changes runtime state; enable changes automatic activation."
        ),
        (
            "Editing a vendor unit directly",
            "updates can overwrite the modification; use drop-ins where appropriate."
        ),
        (
            "Forgetting daemon-reload",
            "systemd may still use its previously loaded unit configuration."
        ),
        (
            "Using After= as if it were a dependency",
            "ordering and dependency are separate concepts."
        ),
        (
            "Running everything as root",
            "unnecessary privileges increase the potential impact of compromise."
        ),
        (
            "Using restart for every configuration change",
            "some services support reload and can avoid unnecessary downtime."
        ),
        (
            "Ignoring logs",
            "service status and journal entries often reveal the actual failure reason."
        ),
        (
            "Creating an infinite restart loop",
            "restart policies need appropriate rate limiting and diagnosis."
        ),
        (
            "Assuming service names are universal",
            "different distributions may use different names, such as ssh versus sshd."
        ),
        (
            "Parsing human-readable systemctl output in automation",
            "machine-readable properties are more stable for scripts."
        ),
        (
            "Assuming network.target means the network is fully usable",
            "network-online.target and distribution-specific networking behavior may matter."
        ),
        (
            "Putting secrets in unit files",
            "unit files may be readable by users who should not access secrets."
        ),
    ]

    for mistake, correction in mistakes:
        print(f"\nMistake: {mistake}")
        print(f"Better approach: {correction}")


# =============================================================================
# SECTION 37: PRODUCTION DESIGN
# =============================================================================

def explain_production_design() -> None:
    print_title("36. Production service design")

    principles = [
        "Use a dedicated service account when root is unnecessary.",
        "Keep the main process in the foreground when practical.",
        "Declare genuine dependencies explicitly.",
        "Use ordering directives for sequencing.",
        "Use Restart= deliberately rather than blindly.",
        "Configure appropriate startup and shutdown timeouts.",
        "Send meaningful logs to standard output/error or journald.",
        "Use structured application logging where operationally useful.",
        "Define health and readiness behavior clearly.",
        "Apply resource limits based on measured requirements.",
        "Apply security hardening incrementally and test each restriction.",
        "Use drop-ins for local overrides of vendor units.",
        "Use version-controlled configuration for custom services.",
        "Avoid embedding unnecessary credentials in unit files.",
        "Test boot behavior, restart behavior, and failure recovery.",
        "Verify behavior after package upgrades and operating-system updates.",
        "Monitor service state and application health separately.",
    ]

    for principle in principles:
        print(f"- {principle}")

    print_subtitle("Operational checklist")

    checklist = [
        "Can the service start from a clean boot?",
        "Does it fail safely when a dependency is unavailable?",
        "Does it recover after an unexpected process termination?",
        "Does it stop gracefully?",
        "Are logs sufficient to diagnose startup failure?",
        "Are permissions restricted?",
        "Are resource limits appropriate?",
        "Are secrets protected?",
        "Is the unit configuration reproducible?",
        "Is monitoring based on actual service health rather than process existence alone?",
    ]

    for item in checklist:
        print(f"[ ] {item}")


# =============================================================================
# SECTION 38: PERFORMANCE CONSIDERATIONS
# =============================================================================

def explain_performance() -> None:
    print_title("37. Performance and boot-time considerations")

    explain(
        """
        systemd can start independent units concurrently. Good dependency design
        therefore affects boot performance.

        Artificially adding dependencies can serialize startup and increase boot
        time. Missing dependencies can create races. A well-designed unit graph
        expresses only real relationships and uses ordering directives precisely.
        """

    commands = [
        "systemd-analyze",
        "systemd-analyze blame",
        "systemd-analyze critical-chain",
        "systemd-analyze plot > boot.svg",
        "systemd-analyze security example.service",
    ]

    for command in commands:
        show_code(command)

    explain(
        """
        systemd-analyze blame can help identify units associated with startup
        delays, but it should not be interpreted as a complete causal analysis
        by itself. critical-chain is useful for understanding dependency chains.
        """
    )


# =============================================================================
# SECTION 39: SECURITY ANALYSIS
# =============================================================================

def explain_systemd_security_analysis() -> None:
    print_title("38. systemd-analyze security")

    explain(
        """
        systemd-analyze security can provide an exposure-oriented assessment of
        service sandboxing settings. It is a useful diagnostic aid, not a
        replacement for a complete security review.

        A lower exposure score does not automatically mean that an application
        is secure. Application vulnerabilities, credentials, network exposure,
        dependencies, kernel vulnerabilities, and configuration mistakes remain
        relevant.
        """
    )

    print("systemd-analyze security example.service")


# =============================================================================
# SECTION 40: PRESETS
# =============================================================================

def explain_presets() -> None:
    print_title("39. Presets")

    explain(
        """
        systemd presets provide policy-driven defaults for enabling or disabling
        units. Distribution packages can ship preset policies that describe
        expected administrative defaults.

        Presets are different from directly issuing enable or disable for a
        single unit.
        """
    )

    commands = [
        "systemctl preset example.service",
        "systemctl preset-all",
        "systemctl list-unit-files",
    ]

    for command in commands:
        show_code(command)


# =============================================================================
# SECTION 41: GENERATED AND TRANSIENT UNITS
# =============================================================================

def explain_transient_units() -> None:
    print_title("40. Transient and generated units")

    explain(
        """
        Not every unit visible to systemd must originate from a static file in
        /etc or a package directory.

        Transient units can be created dynamically, often through tools such as
        systemd-run. Generators can create units or dependency relationships
        dynamically during system initialization.

        This is one reason that looking only at static files can give an
        incomplete picture of runtime systemd state.
        """
    )

    print("Example transient command:")
    print("systemd-run --unit=example-transient.service /usr/bin/sleep 30")

    explain(
        """
        systemd-run can be powerful for temporary jobs and experiments. It
        should not be confused with a persistent service installation.
        """
    )


# =============================================================================
# SECTION 42: SERVICE MANAGEMENT WITH PYTHON
# =============================================================================

def explain_python_automation() -> None:
    print_title("41. Automating service inspection with Python")

    explain(
        """
        Python can interact with systemd through subprocess calls, D-Bus
        libraries, or other operating-system interfaces. For portable teaching
        code, subprocess is sufficient for basic read-only queries.

        When automation changes service state, privilege handling becomes a
        critical concern. A Python script should not casually invoke commands
        through a shell with user-controlled strings.
        """
    )

    print_subtitle("Safe argument construction")

    print("""command = [
    "systemctl",
    "show",
    "-p",
    "ActiveState",
    "--value",
    "example.service",
]

subprocess.run(command, check=False, capture_output=True, text=True)
""")

    print_subtitle("Avoid shell interpolation")

    print("""# Risky when user input is inserted into a shell command:
subprocess.run(
    f"systemctl status {user_input}",
    shell=True,
)
""")

    explain(
        """
        A list of arguments avoids shell parsing and reduces command-injection
        risk. User-controlled unit names should still be validated according to
        the application's requirements.
        """
    )


# =============================================================================
# SECTION 43: UNIT NAME VALIDATION
# =============================================================================

UNIT_NAME_PATTERN = re.compile(
    r"^[A-Za-z0-9_.:@%+\-\\]+(?:\.(?:service|socket|target|timer|path|mount|automount|swap|device|slice|scope|busname))?$"
)


def validate_unit_name(unit_name: str) -> bool:
    """
    Perform a conservative educational validation of a unit name.

    This is not intended to be a complete implementation of systemd's unit-name
    escaping rules. It demonstrates the principle of validating external input
    before passing it into administrative tooling.
    """
    return bool(UNIT_NAME_PATTERN.fullmatch(unit_name))


def demonstrate_validation() -> None:
    print_title("42. Input validation for service automation")

    examples = [
        "nginx.service",
        "ssh.service",
        "example-worker.service",
        "../danger.service",
        "example.service;rm -rf /",
        "normal-name.service",
    ]

    for unit_name in examples:
        print(f"{unit_name!r:<35} valid={validate_unit_name(unit_name)}")

    explain(
        """
        The validator is intentionally conservative and educational. Production
        software should use a validation strategy appropriate to the exact
        interface and systemd unit-name grammar rather than assuming that a
        regular expression fully represents every valid escaped unit name.
        """
    )


# =============================================================================
# SECTION 44: SERVICE INSTALLATION EXAMPLE
# =============================================================================

def explain_installation_workflow() -> None:
    print_title("43. Installing a custom service")

    explain(
        """
        A typical administrator workflow for a custom system service is:

        1. Create a dedicated application directory.
        2. Create an appropriate service account.
        3. Install the application with controlled ownership and permissions.
        4. Create the service unit under an administrator-controlled directory.
        5. Validate the unit.
        6. Reload systemd's configuration.
        7. Start the service.
        8. Inspect status and logs.
        9. Enable the service if automatic startup is required.
        10. Test reboot and failure recovery.
        """
    )

    print_subtitle("Example commands")

    commands = [
        "sudo systemctl daemon-reload",
        "systemctl status example-worker.service",
        "sudo systemctl start example-worker.service",
        "systemctl is-active example-worker.service",
        "journalctl -u example-worker.service -n 100",
        "sudo systemctl enable example-worker.service",
    ]

    for command in commands:
        show_code(command)


# =============================================================================
# SECTION 45: UNIT VALIDATION
# =============================================================================

def explain_unit_validation() -> None:
    print_title("44. Validating unit configuration")

    explain(
        """
        systemd provides commands that can help identify syntax and dependency
        problems before or after activation. A unit should be validated as part
        of deployment rather than discovering syntax problems during an outage.
        """
    )

    commands = [
        "systemd-analyze verify /etc/systemd/system/example.service",
        "systemctl cat example.service",
        "systemctl show example.service",
    ]

    for command in commands:
        show_code(command)

    explain(
        """
        systemd-analyze verify can inspect unit files and report a range of
        configuration problems. Availability and exact diagnostics depend on
        the installed systemd version.
        """
    )


# =============================================================================
# SECTION 46: COMMAND COMPARISONS
# =============================================================================

def explain_command_comparisons() -> None:
    print_title("45. Important command distinctions")

    comparisons = [
        (
            "start",
            "Run now",
            "Does not normally configure boot activation."
        ),
        (
            "enable",
            "Configure automatic activation",
            "Does not normally start immediately."
        ),
        (
            "restart",
            "Replace running process",
            "May cause downtime."
        ),
        (
            "reload",
            "Ask process to reread configuration",
            "Requires reload support."
        ),
        (
            "disable",
            "Remove automatic activation",
            "Does not necessarily stop the current process."
        ),
        (
            "mask",
            "Block normal activation",
            "Stronger than disable."
        ),
        (
            "daemon-reload",
            "Reread unit definitions",
            "Does not restart services."
        ),
    ]

    print(f"{'Command':<18}{'Purpose':<34}{'Important distinction'}")
    print("-" * 78)

    for command, purpose, distinction in comparisons:
        print(f"{command:<18}{purpose:<34}{distinction}")


# =============================================================================
# SECTION 47: SERVICE DEPENDENCY GRAPH EXAMPLE
# =============================================================================

def explain_dependency_graph_example() -> None:
    print_title("46. Example dependency graph")

    graph = {
        "multi-user.target": ["network.target", "logging.service", "application.service"],
        "application.service": ["database.service", "network-online.target"],
        "database.service": ["local-fs.target"],
        "logging.service": ["local-fs.target"],
        "network.target": ["sysinit.target"],
        "network-online.target": ["network.target"],
    }

    for unit, dependencies in graph.items():
        print(f"{unit}")
        for dependency in dependencies:
            print(f"  └── {dependency}")

    explain(
        """
        This diagram is conceptual. Actual systemd dependency graphs can be much
        larger and contain different relationship types. The key idea is that
        services can be represented as nodes in a graph rather than as a simple
        sequential startup script.
        """
    )


# =============================================================================
# SECTION 48: EDGE CASES
# =============================================================================

def explain_edge_cases() -> None:
    print_title("47. Edge cases and subtle behavior")

    cases = [
        (
            "A service is enabled but inactive",
            "Enablement affects future activation; it does not guarantee current execution."
        ),
        (
            "A service is active but disabled",
            "It may have been manually started or activated by another mechanism."
        ),
        (
            "A service says active (exited)",
            "This can be normal for a successful oneshot service."
        ),
        (
            "Restart immediately fails",
            "Inspect logs and the unit definition instead of repeatedly restarting."
        ),
        (
            "daemon-reload succeeds but behavior does not change",
            "The running service may need restart or reload after configuration changes."
        ),
        (
            "After=network.target does not guarantee internet connectivity",
            "Ordering is not equivalent to application-level network readiness."
        ),
        (
            "A unit cannot be started because it is masked",
            "Unmasking is required before normal activation can occur."
        ),
        (
            "systemctl status looks healthy but application is broken",
            "A running process does not prove that the application's business function is healthy."
        ),
        (
            "A service works manually but fails under systemd",
            "Environment, user identity, working directory, permissions, PATH, and sandboxing may differ."
        ),
        (
            "The service starts manually but not after boot",
            "The enablement relationship, target, dependencies, or boot-time environment may differ."
        ),
    ]

    for situation, explanation in cases:
        print(f"\nSituation: {situation}")
        print(f"Interpretation: {explanation}")


# =============================================================================
# SECTION 49: REAL-WORLD APPLICATIONS
# =============================================================================

def explain_real_world_applications() -> None:
    print_title("48. Real-world applications")

    applications = [
        "Web servers such as Nginx or Apache.",
        "SSH server management.",
        "Database servers such as PostgreSQL or MariaDB.",
        "Application servers and API backends.",
        "Background job workers.",
        "Message queue consumers.",
        "Monitoring agents.",
        "Security and endpoint agents.",
        "Scheduled backups through timer units.",
        "Log processing pipelines.",
        "Network services.",
        "Container-related services.",
        "Storage and mount management.",
        "Hardware and device activation.",
        "Per-user desktop and development services.",
    ]

    for application in applications:
        print(f"- {application}")

    explain(
        """
        In each case, the same service-management principles apply: define how
        the program starts, identify dependencies, establish ownership and
        permissions, decide what happens on failure, expose useful logs, and
        ensure the service behaves predictably during startup and shutdown.
        """
    )


# =============================================================================
# SECTION 50: INTERACTIVE SAFE INSPECTION
# =============================================================================

def run_live_read_only_demo() -> None:
    print_title("49. Live read-only systemd inspection")

    manager = SystemdManager()

    if not manager.available:
        print("systemctl is unavailable. Live systemd inspection skipped.")
        return

    print_subtitle("systemd manager status")

    result = manager.run_read_only("is-system-running")
    print("Command:", " ".join(shlex.quote(part) for part in result.command))
    print("Return code:", result.return_code)
    print("State:", result.stdout.strip() or result.stderr.strip() or "unknown")

    print_subtitle("Default target")

    result = manager.run_read_only("get-default")
    show_output(result.stdout or result.stderr)

    print_subtitle("Loaded service units")

    result = manager.run_read_only(
        "list-units",
        "--type=service",
        "--no-legend",
        "--no-pager",
    )

    if result.succeeded:
        lines = result.stdout.splitlines()
        for line in lines[:15]:
            print(line)
        if len(lines) > 15:
            print(f"... {len(lines) - 15} additional service entries not displayed")
    else:
        print(result.stderr.strip() or "Unable to list services.")

    print_subtitle("Timers")

    result = manager.run_read_only(
        "list-timers",
        "--all",
        "--no-legend",
        "--no-pager",
    )

    if result.succeeded:
        lines = result.stdout.splitlines()
        for line in lines[:10]:
            print(line)
        if len(lines) > 10:
            print(f"... {len(lines) - 10} additional timer entries not displayed")
    else:
        print(result.stderr.strip() or "Unable to list timers.")


# =============================================================================
# SECTION 51: SAFE SERVICE AUDIT REPORT
# =============================================================================

def collect_service_audit(manager: SystemdManager, unit: str) -> dict[str, str | bool | None]:
    """Collect selected read-only properties for an audit report."""
    properties = [
        "LoadState",
        "ActiveState",
        "SubState",
        "UnitFileState",
        "MainPID",
        "FragmentPath",
        "ControlGroup",
    ]

    report: dict[str, str | bool | None] = {
        "unit": unit,
        "active": manager.is_active(unit),
        "enabled": manager.is_enabled(unit),
    }

    for property_name in properties:
        report[property_name] = manager.show_property(unit, property_name)

    return report


def demonstrate_service_audit() -> None:
    print_title("50. Example service audit")

    manager = SystemdManager()

    if not manager.available:
        print("systemctl is unavailable. Audit skipped.")
        return

    candidates = [
        "systemd-journald.service",
        "systemd-logind.service",
        "ssh.service",
        "sshd.service",
    ]

    selected = None

    for unit in candidates:
        load_state = manager.show_property(unit, "LoadState")
        if load_state == "loaded":
            selected = unit
            break

    if selected is None:
        print("No demonstration service found.")
        return

    report = collect_service_audit(manager, selected)

    print(json.dumps(report, indent=2))


# =============================================================================
# SECTION 52: TESTING SERVICE CONFIGURATION
# =============================================================================

def explain_testing() -> None:
    print_title("51. Testing service configuration")

    explain(
        """
        Service testing should cover both positive and negative behavior.
        Testing only successful startup is insufficient.

        A robust service test checks startup, readiness, normal operation,
        graceful shutdown, unexpected termination, automatic restart, logging,
        dependency failure, permission behavior, and reboot persistence when
        relevant.
        """
    )

    test_cases = [
        "Unit syntax is valid.",
        "Executable path exists.",
        "Service account can access required resources.",
        "Service starts successfully.",
        "Service reaches its intended ready state.",
        "Service logs useful diagnostics.",
        "Service reload works if supported.",
        "Service stops gracefully.",
        "Service recovers after an unexpected exit.",
        "Restart limits behave as intended.",
        "Required dependencies are present.",
        "Service does not start when intentionally masked.",
        "Enablement produces expected boot behavior.",
        "Resource limits do not break normal operation.",
        "Security restrictions do not break required functionality.",
    ]

    for test in test_cases:
        print(f"[ ] {test}")


# =============================================================================
# SECTION 53: SERVICE DESIGN COMPARISON
# =============================================================================

def explain_cron_vs_timer() -> None:
    print_title("52. systemd timers versus traditional cron jobs")

    print(f"{'Capability':<30}{'systemd timer':<25}{'cron'}")
    print("-" * 78)

    rows = [
        ("Service supervision", "Integrated", "Separate process model"),
        ("Journal integration", "Native", "Usually external logging"),
        ("Dependencies", "Native unit graph", "Limited"),
        ("Resource controls", "cgroups/systemd", "Not equivalent by default"),
        ("Boot persistence", "Persistent timers", "Cron-specific behavior"),
        ("On-demand activation", "Possible", "Not the primary model"),
        ("Calendar scheduling", "Yes", "Yes"),
    ]

    for capability, timer, cron in rows:
        print(f"{capability:<30}{timer:<25}{cron}")

    explain(
        """
        cron remains useful and widely deployed. systemd timers are particularly
        attractive when scheduled work should integrate with systemd services,
        dependencies, logging, resource controls, and service lifecycle
        management.
        """
    )


# =============================================================================
# SECTION 54: SERVICE MANAGER COMMAND CHEAT SHEET
# =============================================================================

def print_cheat_sheet() -> None:
    print_title("53. systemctl practical reference")

    cheat_sheet = [
        ("status", "systemctl status UNIT", "Inspect runtime state."),
        ("start", "sudo systemctl start UNIT", "Start now."),
        ("stop", "sudo systemctl stop UNIT", "Stop now."),
        ("restart", "sudo systemctl restart UNIT", "Restart now."),
        ("reload", "sudo systemctl reload UNIT", "Reload configuration if supported."),
        ("enable", "sudo systemctl enable UNIT", "Enable future automatic activation."),
        ("disable", "sudo systemctl disable UNIT", "Disable automatic activation."),
        ("enable --now", "sudo systemctl enable --now UNIT", "Enable and start."),
        ("disable --now", "sudo systemctl disable --now UNIT", "Disable and stop."),
        ("is-active", "systemctl is-active UNIT", "Check current active state."),
        ("is-enabled", "systemctl is-enabled UNIT", "Check enablement."),
        ("is-failed", "systemctl is-failed UNIT", "Check failure state."),
        ("cat", "systemctl cat UNIT", "Display unit source."),
        ("show", "systemctl show UNIT", "Display structured properties."),
        ("daemon-reload", "sudo systemctl daemon-reload", "Reread unit configuration."),
        ("list-units", "systemctl list-units", "List loaded units."),
        ("list-unit-files", "systemctl list-unit-files", "List installed unit files."),
        ("list-dependencies", "systemctl list-dependencies UNIT", "Inspect dependencies."),
        ("mask", "sudo systemctl mask UNIT", "Block activation."),
        ("unmask", "sudo systemctl unmask UNIT", "Remove activation block."),
    ]

    print(f"{'Operation':<20}{'Command':<48}Purpose")
    print("-" * 110)

    for operation, command, purpose in cheat_sheet:
        print(f"{operation:<20}{command:<48}{purpose}")


# =============================================================================
# SECTION 55: MAIN EDUCATIONAL PROGRAM
# =============================================================================

def main() -> None:
    """
    Run the complete educational walkthrough.

    The order moves from basic concepts toward systemd internals,
    administration, automation, security, debugging, and production design.
    """

    print_title("Linux Services: systemd and systemctl")

    print(
        """
This executable study file demonstrates Linux service-management concepts
from beginner to advanced level.

System-changing commands are shown but are not automatically executed.
Read-only systemd inspection is performed only when systemctl is available.
""".strip()
    )

    print_platform_information()
    pause_if_interactive()

    explain_process_service_relationship()
    pause_if_interactive()

    explain_systemd_architecture()
    pause_if_interactive()

    explain_unit_types()
    pause_if_interactive()

    explain_systemctl()
    pause_if_interactive()

    explain_service_states()
    pause_if_interactive()

    explain_unit_file()
    pause_if_interactive()

    explain_service_types()
    pause_if_interactive()

    explain_service_lifecycle()
    pause_if_interactive()

    explain_targets()
    pause_if_interactive()

    explain_dependencies()
    pause_if_interactive()

    explain_startup_patterns()
    pause_if_interactive()

    explain_restart_policies()
    pause_if_interactive()

    explain_restart_limits()
    pause_if_interactive()

    explain_environment_configuration()
    pause_if_interactive()

    explain_drop_ins()
    pause_if_interactive()

    explain_daemon_reload()
    pause_if_interactive()

    explain_journald()
    pause_if_interactive()

    explain_debugging()
    pause_if_interactive()

    explain_machine_readable_properties()
    pause_if_interactive()

    demonstrate_python_systemd_queries()
    pause_if_interactive()

    explain_unit_locations()
    pause_if_interactive()

    explain_masking()
    pause_if_interactive()

    explain_user_services()
    pause_if_interactive()

    explain_security()
    pause_if_interactive()

    explain_resource_management()
    pause_if_interactive()

    explain_timers()
    pause_if_interactive()

    explain_socket_activation()
    pause_if_interactive()

    explain_path_units()
    pause_if_interactive()

    explain_process_relationships()
    pause_if_interactive()

    explain_signals()
    pause_if_interactive()

    explain_exit_status()
    pause_if_interactive()

    explain_watchdogs()
    pause_if_interactive()

    explain_secret_handling()
    pause_if_interactive()

    explain_common_mistakes()
    pause_if_interactive()

    explain_production_design()
    pause_if_interactive()

    explain_performance()
    pause_if_interactive()

    explain_systemd_security_analysis()
    pause_if_interactive()

    explain_presets()
    pause_if_interactive()

    explain_transient_units()
    pause_if_interactive()

    explain_python_automation()
    pause_if_interactive()

    demonstrate_validation()
    pause_if_interactive()

    explain_installation_workflow()
    pause_if_interactive()

    explain_unit_validation()
    pause_if_interactive()

    explain_command_comparisons()
    pause_if_interactive()

    explain_dependency_graph_example()
    pause_if_interactive()

    explain_edge_cases()
    pause_if_interactive()

    explain_real_world_applications()
    pause_if_interactive()

    run_live_read_only_demo()
    pause_if_interactive()

    demonstrate_service_audit()
    pause_if_interactive()

    explain_testing()
    pause_if_interactive()

    explain_cron_vs_timer()
    pause_if_interactive()

    print_cheat_sheet()

    print_title("54. End of Linux services study script")
    print(
        "The script completed. No state-changing systemctl commands were "
        "executed automatically."
    )


if __name__ == "__main__":
    main()
