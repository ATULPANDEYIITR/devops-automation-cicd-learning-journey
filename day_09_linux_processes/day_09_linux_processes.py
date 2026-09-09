#!/usr/bin/env python3
"""
Linux Processes: ps, top, htop, kill, signals, and foreground/background processes.

This is a self-contained Linux process laboratory and study script. It teaches
process fundamentals first and progressively demonstrates:

1. What a Linux process is
2. PIDs, PPIDs, process trees, sessions, process groups, and threads
3. Process states and scheduling concepts
4. ps and its important options
5. top and htop concepts
6. Signals and signal delivery
7. kill, pkill, and related process-control commands
8. Foreground/background execution and shell job control
9. Process creation with fork-like concepts and subprocesses in Python
10. SIGTERM, SIGINT, SIGSTOP, SIGCONT, SIGHUP, SIGKILL, SIGCHLD, SIGUSR1, SIGUSR2
11. Graceful shutdown and cleanup
12. Process monitoring and /proc
13. Zombie and orphan processes
14. Pipes and process relationships
15. CPU and memory measurements
16. Debugging and production considerations
17. Security, permissions, PID reuse, PID 1, and signal limitations
18. Practical laboratories and edge cases

Run on Linux with Python 3.8+.

Most demonstrations use only Python's standard library and standard Linux
commands. Destructive process operations are intentionally restricted to
processes created by this script.
"""

from __future__ import annotations

import argparse
import errno
import os
import platform
import random
import re
import shutil
import signal
import subprocess
import sys
import textwrap
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# ============================================================================
# SECTION 1: GENERAL PRESENTATION HELPERS
# ============================================================================

def print_banner(title: str) -> None:
    """Print a readable section banner."""
    line = "=" * 78
    print(f"\n{line}")
    print(title)
    print(line)


def print_subsection(title: str) -> None:
    """Print a smaller subsection heading."""
    print(f"\n--- {title} ---")


def explain(text: str) -> None:
    """Print wrapped educational text."""
    print(textwrap.fill(text.strip(), width=78))


def command_exists(command: str) -> bool:
    """Return True when a command is available in PATH."""
    return shutil.which(command) is not None


def run_command(
    command: Sequence[str],
    *,
    timeout: float = 10.0,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """
    Execute a command and capture text output.

    Commands are passed as an argument list rather than shell text. This avoids
    accidental shell expansion and makes demonstrations safer.
    """
    try:
        return subprocess.run(
            list(command),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=check,
        )
    except FileNotFoundError:
        return subprocess.CompletedProcess(
            command, 127, "", f"Command not found: {command[0]}"
        )
    except subprocess.TimeoutExpired as exc:
        return subprocess.CompletedProcess(
            command,
            124,
            exc.stdout or "",
            f"Command timed out: {' '.join(command)}",
        )


def print_command_output(
    command: Sequence[str],
    *,
    timeout: float = 10.0,
    max_lines: int = 40,
) -> None:
    """Run a command and print a bounded amount of its output."""
    print(f"$ {' '.join(command)}")
    result = run_command(command, timeout=timeout)
    output = (result.stdout or "").strip()
    error = (result.stderr or "").strip()

    if output:
        lines = output.splitlines()
        if len(lines) > max_lines:
            print("\n".join(lines[:max_lines]))
            print(f"... [{len(lines) - max_lines} more lines omitted]")
        else:
            print(output)

    if error:
        print(f"[stderr] {error}")

    if result.returncode not in (0, None):
        print(f"[exit status] {result.returncode}")


def require_linux() -> bool:
    """Warn when the script is being executed on a non-Linux system."""
    if platform.system() != "Linux":
        print("This educational script targets Linux.")
        print(f"Detected operating system: {platform.system()}")
        print("Some demonstrations may be unavailable.")
        return False
    return True


# ============================================================================
# SECTION 2: PROCESS FUNDAMENTALS
# ============================================================================

def show_process_fundamentals() -> None:
    print_banner("1. Linux Process Fundamentals")

    explain(
        """
        A process is a running instance of a program. A program is passive
        code stored on disk; a process is the operating system's managed
        execution context for that code.

        A Linux process normally has a unique process identifier, called a PID,
        while that PID remains allocated. A process also has a parent process,
        identified by PPID. The kernel tracks scheduling information, memory
        mappings, open file descriptors, credentials, signal state, resource
        limits, and other execution metadata.

        Linux process management is closely connected to the kernel scheduler,
        virtual memory subsystem, signals, file descriptors, sessions, process
        groups, and the shell.
        """
    )

    print_subsection("Current Python process")
    print(f"PID       : {os.getpid()}")
    print(f"PPID      : {os.getppid()}")
    print(f"UID       : {os.getuid() if hasattr(os, 'getuid') else 'N/A'}")
    print(f"GID       : {os.getgid() if hasattr(os, 'getgid') else 'N/A'}")

    if hasattr(os, "getpgid"):
        try:
            print(f"Process PGID: {os.getpgid(0)}")
        except OSError as exc:
            print(f"Process PGID: unavailable ({exc})")

    if hasattr(os, "getsid"):
        try:
            print(f"Session ID : {os.getsid(0)}")
        except OSError as exc:
            print(f"Session ID : unavailable ({exc})")

    print_subsection("Important terminology")
    terms = {
        "PID": "Process ID. Identifies a process in the kernel's process namespace.",
        "PPID": "Parent Process ID. Identifies the process that created/adopted it.",
        "PGID": "Process Group ID. Used to control related processes together.",
        "SID": "Session ID. Groups process groups, commonly around a terminal/session.",
        "TTY": "Controlling terminal associated with a process, when present.",
        "UID/GID": "User and group credentials used for permission decisions.",
        "Thread": "An execution unit within a process that shares process resources.",
        "Daemon": "A background service process, often detached from an interactive terminal.",
        "Zombie": "A terminated child whose exit status has not yet been collected by its parent.",
        "Orphan": "A process whose original parent has terminated; it is reparented.",
    }

    for name, definition in terms.items():
        print(f"{name:10} {definition}")


# ============================================================================
# SECTION 3: PROCESS STATES
# ============================================================================

def show_process_states() -> None:
    print_banner("2. Linux Process States")

    explain(
        """
        Linux exposes process state information through interfaces such as
        ps and /proc. The state is not simply a permanent category. A process
        can move between runnable, sleeping, stopped, and zombie-related states
        as it executes and waits for resources or receives signals.
        """
    )

    states = [
        ("R", "Running or runnable", "Executing on a CPU or waiting in the run queue."),
        ("S", "Interruptible sleep", "Waiting for an event and normally interruptible by signals."),
        ("D", "Uninterruptible sleep", "Usually waiting for kernel/I/O activity; ordinary signals may not take effect immediately."),
        ("T", "Stopped", "Stopped by job control or a stopping signal such as SIGSTOP."),
        ("t", "Tracing stop", "Stopped under tracing/debugging."),
        ("Z", "Zombie", "Exited but still represented until its parent collects its status."),
        ("X", "Dead", "Rarely visible terminal state."),
        ("I", "Idle kernel thread", "Used for certain kernel threads on Linux."),
    ]

    print(f"{'State':<8}{'Meaning':<25}Description")
    print("-" * 78)
    for state, meaning, description in states:
        print(f"{state:<8}{meaning:<25}{description}")


# ============================================================================
# SECTION 4: PS
# ============================================================================

def demonstrate_ps() -> None:
    print_banner("3. ps: Inspecting Processes")

    if not command_exists("ps"):
        print("ps is unavailable on this system.")
        return

    explain(
        """
        ps means process status. It provides a snapshot of process information.
        Unlike top or htop, ps does not normally provide a continuously
        refreshing interactive display. It is extremely useful in scripts,
        troubleshooting, pipelines, and precise process selection.

        ps has several option styles. BSD-style options commonly omit the
        leading dash, UNIX-style options use a dash, and GNU long options may
        use two dashes. These forms are related but are not interchangeable in
        every context.
        """
    )

    print_subsection("Current user's processes")
    print_command_output(["ps", "-u", os.environ.get("USER", "")], max_lines=25)

    print_subsection("All processes with a useful custom format")
    print_command_output(
        [
            "ps",
            "-eo",
            "pid,ppid,user,stat,%cpu,%mem,etime,comm",
            "--sort=-%cpu",
        ],
        max_lines=30,
    )

    print_subsection("Process hierarchy")
    print_command_output(["ps", "-ef", "--forest"], max_lines=35)

    print_subsection("Thread-oriented view")
    print_command_output(
        ["ps", "-eLf", "--sort", "-pid"],
        max_lines=25,
    )

    explain(
        """
        Common ps patterns include ps aux, ps -ef, ps -p PID, ps -o FORMAT,
        ps --forest, and ps -L. The exact output columns differ between
        implementations and operating systems, so scripts should not blindly
        parse human-oriented output when a machine-readable interface is
        available.

        Useful fields include PID, PPID, USER, STAT, %CPU, %MEM, VSZ, RSS, TTY,
        STAT, START, TIME, COMMAND, and elapsed time. RSS represents resident
        memory, while VSZ represents virtual memory size. RSS is generally more
        meaningful when examining actual resident physical memory consumption,
        but it still does not equal unique memory attributable to a process
        because shared pages can be counted in multiple processes.
        """
    )


# ============================================================================
# SECTION 5: TOP
# ============================================================================

def demonstrate_top() -> None:
    print_banner("4. top: Interactive Real-Time Monitoring")

    if not command_exists("top"):
        print("top is unavailable on this system.")
        return

    explain(
        """
        top provides a continuously refreshed process view. It is useful when
        the question is not simply "what processes exist?" but "what is
        happening right now?"

        Typical information includes system load, CPU usage, memory and swap
        information, process states, CPU consumption, resident memory,
        priorities, and elapsed CPU time.

        Important interactive keys commonly include P for CPU sorting, M for
        memory sorting, T for accumulated CPU time, k for sending a signal,
        r for changing priority, and q for quitting. Exact behavior depends
        on the implementation and configuration.
        """
    )

    print_subsection("Non-interactive top snapshot")
    print_command_output(
        ["top", "-b", "-n", "1", "-o", "%CPU"],
        timeout=10,
        max_lines=35,
    )

    explain(
        """
        The -b option requests batch mode and -n 1 requests one iteration.
        This makes top useful in scripts, although ps or /proc is often a
        better interface for structured monitoring.
        """
    )


# ============================================================================
# SECTION 6: HTOP
# ============================================================================

def demonstrate_htop() -> None:
    print_banner("5. htop: Interactive Process Explorer")

    if not command_exists("htop"):
        print("htop is not installed. The command is optional.")
        explain(
            """
            htop is an interactive process viewer that is generally easier to
            navigate than traditional top. It provides process trees,
            scrolling, searching, sorting, and convenient process-control
            actions. It is a separate program and is not part of Python.
            """
        )
        return

    explain(
        """
        htop presents similar core information to top but emphasizes interactive
        navigation. It can display a process tree, CPU meters, memory meters,
        process relationships, and selectable process actions.

        Common keyboard operations include F3 for search, F4 for filtering,
        F5 for tree view, F6 for sorting, F9 for sending a signal, and F10 for
        exit. Exact keys can vary with configuration and version.
        """
    )

    print_subsection("Check htop version without entering its interactive UI")
    print_command_output(["htop", "--version"], max_lines=5)


# ============================================================================
# SECTION 7: SIGNALS
# ============================================================================

SIGNAL_DESCRIPTIONS = {
    "SIGHUP": "Terminal/session hangup. Historically means hangup; commonly used to request configuration reloads by daemons.",
    "SIGINT": "Interrupt from terminal, commonly generated by Ctrl-C.",
    "SIGQUIT": "Quit from terminal, commonly generated by Ctrl-\\\\; may produce a core dump.",
    "SIGKILL": "Immediate termination requested by the kernel. Cannot be caught, blocked, or ignored.",
    "SIGTERM": "Termination request. Normally catchable and preferred for graceful shutdown.",
    "SIGSTOP": "Stop process execution. Cannot be caught, blocked, or ignored.",
    "SIGTSTP": "Terminal stop, commonly generated by Ctrl-Z; can be handled unlike SIGSTOP.",
    "SIGCONT": "Continue a stopped process.",
    "SIGCHLD": "Child process state change notification, commonly delivered when a child exits or stops.",
    "SIGUSR1": "Application-defined user signal.",
    "SIGUSR2": "Application-defined user signal.",
    "SIGALRM": "Alarm/timer signal.",
    "SIGPIPE": "Written to a pipe/socket with no reader; behavior matters in pipelines.",
}

def show_signals() -> None:
    print_banner("6. Linux Signals")

    explain(
        """
        A signal is an asynchronous notification delivered to a process or
        process group. Signals are one of Linux's fundamental process-control
        mechanisms.

        Signal delivery does not mean every signal instantly destroys a
        process. The default action depends on the signal. A process can
        install handlers for many signals, block signals temporarily, or
        ignore some signals. SIGKILL and SIGSTOP are important exceptions:
        they cannot be caught, blocked, or ignored.
        """
    )

    print_subsection("Important signals")
    for name, description in SIGNAL_DESCRIPTIONS.items():
        signum = getattr(signal, name, None)
        if signum is not None:
            print(f"{name:<10} {signum:>3}  {description}")
        else:
            print(f"{name:<10} N/A  {description}")

    print_subsection("Python signal-handler example")

    received: List[str] = []

    def demonstration_handler(signum: int, _frame) -> None:
        signal_name = signal.Signals(signum).name
        received.append(signal_name)
        print(f"\nSignal handler received {signal_name} ({signum}).")

    previous_handler = signal.getsignal(signal.SIGUSR1)
    try:
        signal.signal(signal.SIGUSR1, demonstration_handler)
        print(f"Current PID: {os.getpid()}")
        print("Sending SIGUSR1 to this process...")
        os.kill(os.getpid(), signal.SIGUSR1)
    finally:
        signal.signal(signal.SIGUSR1, previous_handler)

    print(f"Signals received during demonstration: {received}")


# ============================================================================
# SECTION 8: KILL AND RELATED COMMANDS
# ============================================================================

def demonstrate_kill_commands() -> None:
    print_banner("7. kill, pkill, killall, and Process Selection")

    explain(
        """
        The kill command is named historically for signal delivery, not merely
        process termination. kill PID normally sends SIGTERM. The actual
        behavior is determined by the signal supplied.

        Examples include kill PID, kill -TERM PID, kill -INT PID, kill -STOP PID,
        kill -CONT PID, and kill -KILL PID. A process can only signal another
        process when Linux's permission rules allow it, subject to privileged
        capabilities.

        pkill selects processes by attributes such as name or user and sends a
        signal to matching processes. killall also selects by process name, but
        its exact semantics depend on the implementation. Broad selection is
        dangerous in production because an unintended match can affect an
        unrelated process.
        """
    )

    print_subsection("List common signal names")
    if command_exists("kill"):
        print_command_output(["kill", "-l"], max_lines=10)

    print_subsection("Safe signal demonstration")
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import signal,time,sys\n"
                "def handler(sig, frame):\n"
                "    print('child: SIGTERM received; exiting gracefully', flush=True)\n"
                "    sys.exit(0)\n"
                "signal.signal(signal.SIGTERM, handler)\n"
                "print('child: ready', flush=True)\n"
                "while True:\n"
                "    time.sleep(1)\n"
            ),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        line = child.stdout.readline().strip() if child.stdout else ""
        print(f"Child PID: {child.pid}")
        if line:
            print(line)

        print(f"Sending SIGTERM with os.kill({child.pid}, SIGTERM).")
        os.kill(child.pid, signal.SIGTERM)
        return_code = child.wait(timeout=5)
        print(f"Child exit status: {return_code}")
    except Exception as exc:
        print(f"Demonstration error: {exc}")
        if child.poll() is None:
            child.kill()
            child.wait()
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


# ============================================================================
# SECTION 9: PROCESS GROUPS, SESSIONS, AND JOB CONTROL
# ============================================================================

def show_process_groups_and_sessions() -> None:
    print_banner("8. Process Groups, Sessions, and Job Control")

    explain(
        """
        A PID identifies one process, but terminal job control often operates
        on process groups. A shell creates or manages process groups for jobs.
        A pipeline such as "producer | consumer" can consist of multiple
        processes in one job/process group.

        A session contains one or more process groups. Interactive shells
        commonly manage a session associated with a controlling terminal.

        Foreground and background are therefore not simply properties stored
        as a universal boolean on a process. They depend on terminal
        ownership, process groups, shell job-control state, and how the shell
        launched the command.
        """
    )

    print_subsection("Current process identifiers")
    print(f"PID:  {os.getpid()}")

    if hasattr(os, "getpgid"):
        print(f"PGID: {os.getpgid(0)}")

    if hasattr(os, "getsid"):
        print(f"SID:  {os.getsid(0)}")

    tty_name = "not attached to a terminal"
    try:
        tty_name = os.ttyname(sys.stdin.fileno())
    except OSError:
        pass
    print(f"TTY:  {tty_name}")

    explain(
        """
        Shell built-ins such as jobs, fg, bg, disown, and wait are central to
        interactive job control. The exact syntax and behavior belongs to the
        shell, so bash, zsh, fish, and other shells may differ.

        Ctrl-C normally causes SIGINT to the foreground job. Ctrl-Z normally
        causes SIGTSTP and stops the foreground job. bg resumes a stopped job
        in the background, while fg makes a job foreground again.
        """
    )


def show_shell_job_control_examples() -> None:
    print_banner("9. Foreground and Background Processes")

    explain(
        """
        A foreground process normally occupies the terminal's foreground
        process group. Terminal-generated signals such as Ctrl-C are directed
        toward that foreground process group.

        A background job can continue while the shell accepts more commands.
        The shell assigns a job identifier such as %1 while the kernel still
        identifies individual processes by PID.

        The following examples are intended for a shell such as bash. They are
        printed rather than automatically executed because automatically
        manipulating the user's interactive shell would be unsafe and cannot
        change the parent shell's job table from a child Python process.
        """
    )

    examples = [
        ("Foreground", "sleep 30"),
        ("Background", "sleep 30 &"),
        ("List jobs", "jobs"),
        ("Bring job to foreground", "fg %1"),
        ("Resume stopped job in background", "bg %1"),
        ("Stop foreground job", "Ctrl-Z"),
        ("Interrupt foreground job", "Ctrl-C"),
        ("Wait for a background job", "wait %1"),
        ("Run a pipeline in background", "producer | consumer &"),
    ]

    for concept, command in examples:
        print(f"{concept:<32} {command}")

    explain(
        """
        A subtle point is that ampersand is shell syntax. It is not a Linux
        signal and is not a property of the executable itself. The shell
        decides to start the command without waiting for its completion and
        records the job.
        """
    )


# ============================================================================
# SECTION 10: /PROC
# ============================================================================

@dataclass
class ProcStatus:
    pid: int
    name: str
    state: str
    ppid: Optional[int]
    vm_size_kb: Optional[int]
    vm_rss_kb: Optional[int]
    threads: Optional[int]


def parse_proc_status(pid: int) -> Optional[ProcStatus]:
    """Read selected fields from /proc/PID/status."""
    path = Path("/proc") / str(pid) / "status"
    try:
        content = path.read_text(errors="replace")
    except (FileNotFoundError, PermissionError, OSError):
        return None

    values: Dict[str, str] = {}
    for line in content.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()

    state_value = values.get("State", "")
    state = state_value[:1] if state_value else "?"

    def numeric_kb(key: str) -> Optional[int]:
        value = values.get(key)
        if not value:
            return None
        match = re.match(r"(\d+)", value)
        return int(match.group(1)) if match else None

    def numeric_value(key: str) -> Optional[int]:
        value = values.get(key)
        if not value:
            return None
        match = re.match(r"(\d+)", value)
        return int(match.group(1)) if match else None

    return ProcStatus(
        pid=pid,
        name=values.get("Name", "?"),
        state=state,
        ppid=numeric_value("PPid"),
        vm_size_kb=numeric_kb("VmSize"),
        vm_rss_kb=numeric_kb("VmRSS"),
        threads=numeric_value("Threads"),
    )


def show_proc_filesystem() -> None:
    print_banner("10. The /proc Process Interface")

    if not Path("/proc").is_dir():
        print("/proc is unavailable.")
        return

    explain(
        """
        Linux exposes extensive process and kernel information through the
        proc pseudo-filesystem, normally mounted at /proc. Entries such as
        /proc/PID/status, /proc/PID/stat, /proc/PID/cmdline, /proc/PID/fd,
        /proc/PID/maps, and /proc/PID/task provide different views of a
        process.

        /proc is not an ordinary disk-backed directory. Many files are
        generated dynamically by the kernel and can disappear immediately
        when a process exits.
        """
    )

    status = parse_proc_status(os.getpid())
    if status:
        print_subsection("Selected fields from /proc/self/status")
        print(f"Name       : {status.name}")
        print(f"State      : {status.state}")
        print(f"PPID       : {status.ppid}")
        print(f"VmSize     : {status.vm_size_kb} kB")
        print(f"VmRSS      : {status.vm_rss_kb} kB")
        print(f"Threads    : {status.threads}")

    print_subsection("Selected /proc/self paths")
    for relative in [
        "status",
        "stat",
        "cmdline",
        "fd",
        "maps",
        "task",
    ]:
        path = Path("/proc/self") / relative
        print(f"{path}: {'available' if path.exists() else 'unavailable'}")


# ============================================================================
# SECTION 11: PROCESS TREE
# ============================================================================

def get_process_table() -> Dict[int, Tuple[int, str]]:
    """
    Return PID -> (PPID, command/name) using ps.

    This function intentionally uses ps rather than parsing /proc/stat so the
    educational output corresponds to the command students learn.
    """
    if not command_exists("ps"):
        return {}

    result = run_command(["ps", "-e", "-o", "pid=,ppid=,comm="], max(1, 1))
    if result.returncode != 0:
        return {}

    table: Dict[int, Tuple[int, str]] = {}
    for line in result.stdout.splitlines():
        fields = line.strip().split(None, 2)
        if len(fields) == 3:
            try:
                pid = int(fields[0])
                ppid = int(fields[1])
            except ValueError:
                continue
            table[pid] = (ppid, fields[2])
    return table


def build_process_tree(
    table: Dict[int, Tuple[int, str]],
    root_pid: int,
    prefix: str = "",
    visited: Optional[set[int]] = None,
) -> List[str]:
    """Build a small process tree from a PID/PPID table."""
    if visited is None:
        visited = set()

    if root_pid in visited:
        return [prefix + "[cycle/reference already shown]"]

    visited.add(root_pid)

    if root_pid not in table:
        return [prefix + f"{root_pid} [process disappeared]"]

    ppid, command = table[root_pid]
    lines = [prefix + f"{root_pid} {command} (PPID={ppid})"]

    children = sorted(
        pid for pid, (parent, _) in table.items() if parent == root_pid
    )

    for index, child in enumerate(children):
        connector = "└─ " if index == len(children) - 1 else "├─ "
        child_prefix = prefix + ("   " if index == len(children) - 1 else "│  ")
        child_lines = build_process_tree(
            table,
            child,
            prefix=child_prefix,
            visited=visited,
        )
        if child_lines:
            first = child_lines[0]
            lines.append(prefix + connector + first[len(child_prefix):])
            lines.extend(child_lines[1:])
    return lines


def show_current_process_tree() -> None:
    print_banner("11. Process Hierarchy")

    table = get_process_table()
    if not table:
        print("Could not build a process table.")
        return

    current_pid = os.getpid()
    print("Process ancestry can be viewed with ps --forest or pstree.")
    if command_exists("pstree"):
        print_command_output(["pstree", "-p", str(current_pid)], max_lines=20)
    else:
        print("pstree is not installed; constructing a small tree from ps.")
        for line in build_process_tree(table, current_pid):
            print(line)


# ============================================================================
# SECTION 12: CPU AND MEMORY
# ============================================================================

def read_meminfo() -> Dict[str, int]:
    """Read /proc/meminfo values in kB."""
    result: Dict[str, int] = {}
    path = Path("/proc/meminfo")

    try:
        content = path.read_text(errors="replace")
    except OSError:
        return result

    for line in content.splitlines():
        match = re.match(r"^([^:]+):\s+(\d+)", line)
        if match:
            result[match.group(1)] = int(match.group(2))
    return result


def show_memory_information() -> None:
    print_banner("12. Process Memory and System Memory")

    meminfo = read_meminfo()
    if not meminfo:
        print("/proc/meminfo unavailable.")
        return

    total = meminfo.get("MemTotal")
    available = meminfo.get("MemAvailable")

    if total is not None:
        print(f"Total memory     : {total / 1024:.1f} MiB")
    if available is not None:
        print(f"Available memory : {available / 1024:.1f} MiB")

    status = parse_proc_status(os.getpid())
    if status:
        print(f"This process VmSize: {status.vm_size_kb} kB")
        print(f"This process VmRSS : {status.vm_rss_kb} kB")

    explain(
        """
        VmSize is virtual address space and can be substantially larger than
        physical RAM actually resident for the process. VmRSS is resident set
        size. Neither number alone tells the complete memory story because
        shared libraries and shared pages complicate attribution.

        Linux also uses page cache extensively. A machine with apparently low
        free memory is not necessarily experiencing memory pressure. The
        MemAvailable concept is generally more informative than MemFree for
        estimating memory that can be allocated without swapping.
        """
    )


def demonstrate_resource_measurement() -> None:
    print_banner("13. Measuring a Process with /usr/bin/time")

    time_path = shutil.which("time")

    if not time_path:
        print("time command unavailable.")
        return

    explain(
        """
        The time utility measures resource usage of a command. Depending on
        the implementation, useful measurements include elapsed wall time,
        user CPU time, system CPU time, maximum resident set size, and other
        resource counters.

        Wall time and CPU time answer different questions. A process that
        spends most of its life waiting for disk or network activity can have
        high elapsed time but relatively little CPU time.
        """
    )

    command = [
        time_path,
        "-p",
        sys.executable,
        "-c",
        "sum(i * i for i in range(1_000_000))",
    ]

    result = run_command(command, timeout=15)
    print("$", " ".join(command))
    print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())


# ============================================================================
# SECTION 13: SUBPROCESSES AND PROCESS CREATION
# ============================================================================

def demonstrate_subprocess_creation() -> None:
    print_banner("14. Creating Processes from Python")

    explain(
        """
        Python's subprocess module starts external programs and gives the
        parent process a controlled interface to their standard input, output,
        error streams, and exit status.

        On POSIX systems, process creation involves operating-system mechanisms
        such as fork/exec or platform-specific equivalents. Modern Python
        implementations can choose efficient creation mechanisms internally.
        The high-level subprocess API is generally preferred over manually
        reproducing fork/exec behavior unless low-level process control is
        specifically required.
        """
    )

    print_subsection("A child process returning a value")
    child = subprocess.run(
        [
            sys.executable,
            "-c",
            "print('hello from a child process')",
        ],
        text=True,
        capture_output=True,
        check=True,
    )

    print(f"Parent PID: {os.getpid()}")
    print(f"Captured child output: {child.stdout.strip()}")
    print(f"Child exit status: {child.returncode}")

    print_subsection("Popen: parent and child execute concurrently")
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import os,time\n"
                "print(f'child PID={os.getpid()}', flush=True)\n"
                "time.sleep(1)\n"
                "print('child complete', flush=True)\n"
            ),
        ],
        stdout=subprocess.PIPE,
        text=True,
    )

    first_line = process.stdout.readline().strip() if process.stdout else ""
    print(first_line)
    print(f"Parent sees child PID: {process.pid}")
    print(f"Child still running? {process.poll() is None}")

    stdout, _ = process.communicate(timeout=5)
    print(stdout.strip())
    print(f"Final child return code: {process.returncode}")


# ============================================================================
# SECTION 14: SIGNAL-DRIVEN CHILD PROCESS LAB
# ============================================================================

CHILD_SIGNAL_PROGRAM = r"""
import os
import signal
import sys
import time

running = True
paused_messages = 0

def handle_term(signum, frame):
    global running
    print(f"child {os.getpid()}: received {signal.Signals(signum).name}", flush=True)
    running = False

def handle_usr1(signum, frame):
    global paused_messages
    paused_messages += 1
    print(
        f"child {os.getpid()}: SIGUSR1 count={paused_messages}",
        flush=True,
    )

def handle_hup(signum, frame):
    print(
        f"child {os.getpid()}: SIGHUP received; reload would happen here",
        flush=True,
    )

signal.signal(signal.SIGTERM, handle_term)
signal.signal(signal.SIGINT, handle_term)
signal.signal(signal.SIGUSR1, handle_usr1)
signal.signal(signal.SIGHUP, handle_hup)

print(f"child_ready pid={os.getpid()}", flush=True)

counter = 0
while running:
    counter += 1
    print(f"child heartbeat={counter}", flush=True)
    time.sleep(0.5)

print("child graceful_shutdown_complete", flush=True)
"""


def run_signal_lab() -> None:
    print_banner("15. Safe Signal Laboratory")

    explain(
        """
        This laboratory creates one temporary child process and sends it
        application-level signals. It demonstrates the distinction between
        requesting an action and forcing termination.

        SIGUSR1 and SIGHUP are handled by the child. SIGTERM is handled as a
        graceful shutdown request. The script never sends signals to arbitrary
        system processes.
        """
    )

    child = subprocess.Popen(
        [sys.executable, "-c", CHILD_SIGNAL_PROGRAM],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    try:
        if child.stdout is None:
            raise RuntimeError("Child stdout was not created.")

        ready_line = child.stdout.readline().strip()
        print(ready_line)

        print_subsection("Send SIGUSR1")
        os.kill(child.pid, signal.SIGUSR1)
        time.sleep(0.2)
        print(child.stdout.readline().strip())

        print_subsection("Send SIGHUP")
        os.kill(child.pid, signal.SIGHUP)
        time.sleep(0.2)
        print(child.stdout.readline().strip())

        print_subsection("Send SIGTERM")
        os.kill(child.pid, signal.SIGTERM)

        deadline = time.monotonic() + 5
        while child.poll() is None and time.monotonic() < deadline:
            line = child.stdout.readline().strip()
            if line:
                print(line)

        if child.poll() is None:
            print("Child did not exit after SIGTERM; using SIGKILL as cleanup.")
            child.kill()

        child.wait(timeout=5)
        print(f"Child final exit status: {child.returncode}")

    except Exception as exc:
        print(f"Signal lab error: {exc}")
        if child.poll() is None:
            child.kill()
        child.wait()


# ============================================================================
# SECTION 15: STOP/CONTINUE LAB
# ============================================================================

def run_stop_continue_lab() -> None:
    print_banner("16. SIGSTOP and SIGCONT Laboratory")

    explain(
        """
        SIGSTOP forcibly stops execution and cannot be caught or ignored.
        SIGCONT resumes a stopped process. These signals are useful for
        demonstrating process state transitions.

        The child process below is created solely for this experiment.
        """
    )

    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import os,time\n"
                "print(f'ready {os.getpid()}', flush=True)\n"
                "while True:\n"
                "    print('working', flush=True)\n"
                "    time.sleep(0.5)\n"
            ),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        ready = child.stdout.readline().strip() if child.stdout else ""
        print(ready)

        time.sleep(0.5)
        print("Sending SIGSTOP...")
        os.kill(child.pid, signal.SIGSTOP)
        time.sleep(0.5)

        if command_exists("ps"):
            print_command_output(
                ["ps", "-o", "pid,ppid,stat,comm", "-p", str(child.pid)],
                max_lines=5,
            )

        print("Sending SIGCONT...")
        os.kill(child.pid, signal.SIGCONT)

        time.sleep(0.5)
        if command_exists("ps"):
            print_command_output(
                ["ps", "-o", "pid,ppid,stat,comm", "-p", str(child.pid)],
                max_lines=5,
            )

    finally:
        if child.poll() is None:
            os.kill(child.pid, signal.SIGTERM)

        try:
            child.wait(timeout=3)
        except subprocess.TimeoutExpired:
            child.kill()
            child.wait()


# ============================================================================
# SECTION 16: ZOMBIE PROCESSES
# ============================================================================

ZOMBIE_CHILD_PROGRAM = r"""
import os
import time

print(f"zombie_candidate_child={os.getpid()}", flush=True)
os._exit(0)
"""


def run_zombie_lab() -> None:
    print_banner("17. Zombie Process Laboratory")

    explain(
        """
        A zombie is a process that has terminated but whose parent has not
        collected its termination status. The kernel retains a small amount
        of information so the parent can call wait or a related operation.

        A zombie is not consuming CPU like a running process. It does consume
        a process-table entry. A large accumulation of zombies can exhaust
        process identifiers or related process-table resources.

        The following demonstration intentionally creates a short-lived child
        and delays wait so its state can be observed. It is cleaned up before
        returning.
        """
    )

    child = subprocess.Popen(
        [sys.executable, "-c", ZOMBIE_CHILD_PROGRAM],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    try:
        child_line = child.stdout.readline().strip() if child.stdout else ""
        print(child_line)

        # Give the child enough time to terminate before the parent waits.
        time.sleep(0.5)

        if command_exists("ps"):
            print("Parent has not called wait() yet:")
            print_command_output(
                ["ps", "-o", "pid,ppid,stat,comm", "-p", str(child.pid)],
                max_lines=5,
            )

        return_code = child.wait(timeout=3)
        print(f"Parent collected child exit status: {return_code}")

    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


# ============================================================================
# SECTION 17: ORPHAN PROCESSES
# ============================================================================

def explain_orphans() -> None:
    print_banner("18. Orphan Processes")

    explain(
        """
        An orphan is a running process whose original parent has terminated.
        Linux must maintain a parent relationship for process lifecycle
        management, so the orphan is reparented to another process according
        to the kernel's rules.

        On modern Linux systems, the system's PID 1 or a designated subreaper
        can adopt descendants. PID 1 is special because it is responsible for
        important system initialization and child-reaping duties in a normal
        booted system.

        Containers can have a different PID namespace, making the first
        process inside a container PID 1 in that namespace. PID 1 behavior,
        signal handling, and child reaping are therefore important in
        containerized applications.
        """
    )

    if command_exists("ps"):
        print_subsection("PID 1")
        print_command_output(
            ["ps", "-p", "1", "-o", "pid,ppid,stat,comm,args"],
            max_lines=5,
        )


# ============================================================================
# SECTION 18: WAITING AND EXIT STATUS
# ============================================================================

def demonstrate_wait_and_exit_status() -> None:
    print_banner("19. wait(), Exit Status, and SIGCHLD")

    explain(
        """
        A parent normally retrieves a child's termination status using wait,
        waitpid, waitid, or a high-level API such as subprocess.wait().
        Waiting both synchronizes the parent with the child and allows the
        kernel to release the child's zombie bookkeeping.

        A conventional process exit status is an integer value. Shells expose
        it through $?. When a process is terminated by a signal, shells and
        APIs may represent that fact differently. Python's subprocess return
        code on POSIX systems is commonly negative when the child was
        terminated by a signal.
        """
    )

    child = subprocess.run(
        [sys.executable, "-c", "raise SystemExit(7)"],
        check=False,
    )
    print(f"Child normal exit code: {child.returncode}")

    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"]
    )
    print(f"Child PID: {child.pid}")

    try:
        os.kill(child.pid, signal.SIGTERM)
        child.wait(timeout=3)
        print(f"Child terminated by SIGTERM; Python return code: {child.returncode}")
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()


# ============================================================================
# SECTION 19: PIPES AND PROCESSES
# ============================================================================

def demonstrate_pipeline() -> None:
    print_banner("20. Pipelines: Processes Connected by File Descriptors")

    explain(
        """
        A shell pipeline connects standard output from one process to standard
        input of another. The pipe is implemented using kernel-managed file
        descriptors and a pipe buffer.

        This creates a process relationship that is important to job control:
        multiple commands in one pipeline may form one shell job and commonly
        share a process group.
        """
    )

    producer = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "print('alpha'); print('beta'); print('gamma')",
        ],
        stdout=subprocess.PIPE,
        text=True,
    )

    consumer = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import sys\n"
                "for line in sys.stdin:\n"
                "    print(line.strip().upper())\n"
            ),
        ],
        stdin=producer.stdout,
        stdout=subprocess.PIPE,
        text=True,
    )

    if producer.stdout is not None:
        producer.stdout.close()

    output, _ = consumer.communicate(timeout=5)
    producer.wait(timeout=5)

    print("Pipeline output:")
    print(output.strip())
    print(f"Producer status: {producer.returncode}")
    print(f"Consumer status: {consumer.returncode}")


# ============================================================================
# SECTION 20: CPU LOAD AND PROCESS SCHEDULING
# ============================================================================

def show_scheduler_concepts() -> None:
    print_banner("21. Scheduling, Priority, Nice Values, and Load")

    explain(
        """
        Linux scheduling decides which runnable execution entities receive CPU
        time. A process can be runnable without currently executing because
        another task may be using the CPU.

        The nice value influences scheduling priority for ordinary processes.
        A higher nice value generally means lower scheduling priority. Changing
        nice values is subject to permission rules, and real-time scheduling
        policies have substantially different behavior and risks.

        Load average is not simply CPU utilization. It reflects the number of
        tasks in relevant runnable or uninterruptible states averaged over
        time. A high load can therefore be caused by CPU contention or certain
        forms of blocked work.
        """
    )

    if command_exists("uptime"):
        print_subsection("Load average")
        print_command_output(["uptime"], max_lines=5)

    if command_exists("nice"):
        print_subsection("Nice demonstration")
        print_command_output(["nice", "-n", "10", "true"], max_lines=5)

    print_subsection("Current scheduling-related process fields")
    if command_exists("ps"):
        print_command_output(
            ["ps", "-p", str(os.getpid()), "-o", "pid,ni,pri,stat,cls,comm"],
            max_lines=5,
        )


# ============================================================================
# SECTION 21: THREADS
# ============================================================================

def demonstrate_threads_vs_processes() -> None:
    print_banner("22. Processes Versus Threads")

    explain(
        """
        A process provides an isolated virtual address space and owns resources
        such as file descriptors and credentials. Threads within one process
        share much of that process state but have independent execution
        contexts such as stacks and scheduling identity.

        Threads are lighter than independent processes in many respects, but
        shared memory introduces synchronization problems. A signal can be
        directed to a process or, depending on the mechanism, to a particular
        thread. Python's signal handling has additional language-level
        restrictions: ordinary Python signal handlers execute in the main
        thread of the main interpreter.
        """
    )

    counter = {"value": 0}
    lock = threading.Lock()

    def worker(iterations: int) -> None:
        for _ in range(iterations):
            with lock:
                counter["value"] += 1

    threads = [
        threading.Thread(target=worker, args=(10_000,))
        for _ in range(4)
    ]

    for thread in threads:
        thread.start()

    for thread in threads:
        thread.join()

    print(f"Threads created: {len(threads)}")
    print(f"Protected shared counter: {counter['value']}")

    status = parse_proc_status(os.getpid())
    if status:
        print(f"Current process thread count: {status.threads}")

    if command_exists("ps"):
        print_subsection("OS view of this process's threads")
        print_command_output(
            ["ps", "-L", "-p", str(os.getpid()), "-o", "pid,tid,psr,stat,comm"],
            max_lines=15,
        )


# ============================================================================
# SECTION 22: PROCESS LIMITS
# ============================================================================

def show_process_limits() -> None:
    print_banner("23. Process Limits and Resource Exhaustion")

    explain(
        """
        Processes consume kernel resources. Linux therefore provides resource
        limits and namespace-level controls. The per-user process limit
        represented by RLIMIT_NPROC is one relevant control, while containers
        and service managers can impose additional limits such as TasksMax.

        Process exhaustion can prevent legitimate programs from starting.
        Production systems should use appropriate resource controls instead of
        allowing an untrusted workload to create unlimited children.
        """
    )

    limits_path = Path("/proc/self/limits")
    if limits_path.exists():
        try:
            content = limits_path.read_text(errors="replace")
            relevant = [
                line
                for line in content.splitlines()
                if "processes" in line.lower() or "open files" in line.lower()
            ]
            print("\n".join(relevant))
        except OSError as exc:
            print(f"Could not read process limits: {exc}")

    if command_exists("ulimit"):
        print("ulimit is normally a shell builtin; this Python process does not")
        print("execute it as a shell builtin automatically.")


# ============================================================================
# SECTION 23: SAFE PROCESS INSPECTION BY PID
# ============================================================================

def inspect_pid(pid: int) -> None:
    print_banner(f"24. Inspecting PID {pid}")

    if pid <= 0:
        print("PID must be a positive integer.")
        return

    status = parse_proc_status(pid)
    if status:
        print_subsection("/proc status")
        print(f"Name       : {status.name}")
        print(f"State      : {status.state}")
        print(f"PPID       : {status.ppid}")
        print(f"VmSize     : {status.vm_size_kb} kB")
        print(f"VmRSS      : {status.vm_rss_kb} kB")
        print(f"Threads    : {status.threads}")
    else:
        print("The process does not exist or cannot be inspected.")

    if command_exists("ps"):
        print_subsection("ps")
        print_command_output(
            [
                "ps",
                "-p",
                str(pid),
                "-o",
                "pid,ppid,pgid,sid,user,stat,%cpu,%mem,etime,tty,comm,args",
            ],
            max_lines=10,
        )

    fd_dir = Path("/proc") / str(pid) / "fd"
    if fd_dir.exists():
        try:
            fd_count = len(list(fd_dir.iterdir()))
            print(f"Open file descriptor entries visible: {fd_count}")
        except OSError as exc:
            print(f"Could not enumerate file descriptors: {exc}")


# ============================================================================
# SECTION 24: SAFE SIGNAL TEST WITH USER-PROVIDED PID
# ============================================================================

def safe_signal_test_for_lab_process() -> None:
    print_banner("25. Signal Permission and Safety Rules")

    explain(
        """
        A process cannot arbitrarily signal every process on a Linux machine.
        Permission checks are applied. Root or appropriate capabilities can
        bypass some restrictions.

        A particularly important operational rule is to verify both the PID
        and the identity of the target before sending a destructive signal.
        PIDs can be reused after a process exits. A stale PID stored in a file
        can therefore refer to an entirely different process later.
        """
    )

    print(
        "This script does not accept an arbitrary PID for termination."
    )
    print(
        "Use ps, top, htop, /proc, service-manager state, and application-specific"
    )
    print(
        "identifiers to confirm the intended process before sending signals."
    )


# ============================================================================
# SECTION 25: SIGNAL ESCALATION
# ============================================================================

def explain_signal_escalation() -> None:
    print_banner("26. Graceful Shutdown and Signal Escalation")

    explain(
        """
        A sound operational shutdown strategy normally starts with a graceful
        request and escalates only when necessary.

        A common pattern is SIGTERM first. The application should stop
        accepting new work, finish or cancel active work according to its
        policy, close files and sockets, flush important state, and exit.

        If the process does not exit within an appropriate deadline, an
        operator or supervisor may escalate. SIGKILL is a last resort because
        the process cannot catch it and therefore cannot execute cleanup
        handlers.

        Sending SIGKILL too early can leave external state inconsistent,
        interrupt transactions, prevent application-level cleanup, and make
        diagnosis harder.
        """
    )

    print("Typical escalation:")
    print("1. Confirm the target.")
    print("2. Send SIGTERM.")
    print("3. Wait for a defined graceful-shutdown deadline.")
    print("4. Inspect state and logs.")
    print("5. Escalate only if policy permits.")
    print("6. Use SIGKILL only when necessary.")


# ============================================================================
# SECTION 26: SIGHUP AND DAEMONS
# ============================================================================

def explain_sighup_and_daemons() -> None:
    print_banner("27. SIGHUP, Terminals, and Daemons")

    explain(
        """
        SIGHUP historically represented a terminal hangup. Its meaning in
        modern applications depends on context. Many daemons use SIGHUP as a
        request to reload configuration rather than terminate.

        The exact behavior is application-defined. Never assume that SIGHUP
        always means reload or always means exit. Consult the service's
        documented signal behavior and supervisor configuration.
        """
    )

    if command_exists("systemctl"):
        print_subsection("systemd-related process concepts")
        print("systemctl can inspect service state on systemd systems.")
        print("Example inspection command:")
        print("  systemctl status <service-name>")


# ============================================================================
# SECTION 27: SYSTEMD AND SUPERVISORS
# ============================================================================

def explain_supervision() -> None:
    print_banner("28. Process Supervision in Production")

    explain(
        """
        Production processes are frequently supervised by systemd, containers,
        Kubernetes, supervisord, init systems, or another process manager.

        A supervisor can restart failed processes, enforce resource limits,
        capture logs, manage dependencies, apply stop timeouts, and define
        restart policies.

        This changes how process management should be approached. Manually
        killing a service process can be less appropriate than asking its
        supervisor to stop or restart the service because the supervisor owns
        the desired lifecycle.
        """
    )

    if command_exists("systemctl"):
        print("systemd detected.")
        print("Prefer service-level operations such as:")
        print("  systemctl status SERVICE")
        print("  systemctl stop SERVICE")
        print("  systemctl restart SERVICE")
        print("The exact operation depends on the operational requirement.")


# ============================================================================
# SECTION 28: DEBUGGING WORKFLOW
# ============================================================================

def show_debugging_workflow() -> None:
    print_banner("29. Process Troubleshooting Workflow")

    explain(
        """
        Process debugging should proceed from observation to hypothesis to
        controlled intervention. Avoid immediately killing a process simply
        because it consumes resources.

        A useful sequence is:
        identify the PID, confirm the executable and user, inspect the parent
        and process group, inspect CPU and memory behavior, inspect process
        state, inspect open files and relevant logs, determine whether the
        process is blocked or actively computing, and only then intervene.

        The most useful tool depends on the question. ps is strong for precise
        snapshots, top and htop are strong for interactive observation, /proc
        exposes kernel-maintained details, strace can expose system calls,
        lsof can show open files, and a debugger can inspect application state.
        """
    )

    commands = [
        ["ps", "-p", str(os.getpid()), "-o", "pid,ppid,stat,%cpu,%mem,etime,comm,args"],
        ["ps", "-L", "-p", str(os.getpid())],
    ]

    if command_exists("ls"):
        commands.append(["ls", "-l", f"/proc/{os.getpid()}/fd"])

    for command in commands:
        if command[0] == "ls" and not command_exists("ls"):
            continue
        print_command_output(command, max_lines=20)


# ============================================================================
# SECTION 29: SECURITY
# ============================================================================

def show_security_considerations() -> None:
    print_banner("30. Security Considerations")

    explain(
        """
        Process management is also a security boundary. Linux associates
        processes with credentials and capabilities. Signal permission checks
        prevent ordinary users from freely controlling unrelated processes.

        Be careful with commands such as pkill, killall, and broad ps pipelines.
        Matching by a short process name can target multiple processes.

        Do not trust a PID as a permanent identity. PID reuse means that a
        process may exit and a new process may later receive the same PID.

        Files containing PIDs should be protected against unauthorized
        modification. A malicious user who can replace a PID file can cause
        an administrator or supervisor to signal an unintended process.

        Never run arbitrary strings through a shell merely because a process
        command line came from an external source. Prefer argument arrays in
        subprocess APIs and validate all externally supplied identifiers.

        Containers add PID namespaces. A process can have one PID inside a
        namespace and another PID in the host namespace. This distinction is
        important when debugging containerized workloads.
        """
    )

    print_subsection("Current credentials")
    if hasattr(os, "getuid"):
        print(f"Real/effective UID: {os.getuid()}/{os.geteuid()}")
    if hasattr(os, "getgid"):
        print(f"Real/effective GID: {os.getgid()}/{os.getegid()}")


# ============================================================================
# SECTION 30: COMMON MISTAKES
# ============================================================================

def show_common_mistakes() -> None:
    print_banner("31. Common Mistakes")

    mistakes = [
        (
            "Confusing program and process",
            "A program is code; a process is an executing instance with kernel-managed state.",
        ),
        (
            "Assuming kill always means terminate",
            "kill primarily means send a signal; the signal determines the action.",
        ),
        (
            "Using SIGKILL first",
            "SIGTERM normally gives an application an opportunity to shut down cleanly.",
        ),
        (
            "Assuming Ctrl-C kills everything",
            "Ctrl-C normally sends SIGINT to the terminal's foreground process group.",
        ),
        (
            "Treating & as a Linux process property",
            "& is shell syntax for asynchronous job execution.",
        ),
        (
            "Ignoring process groups",
            "Pipelines and terminal job control commonly involve process groups.",
        ),
        (
            "Reading %MEM as exact physical ownership",
            "Shared memory means simple RSS percentages do not equal unique memory usage.",
        ),
        (
            "Parsing ps output carelessly",
            "Human-oriented columns can vary; structured interfaces are preferable for automation.",
        ),
        (
            "Killing a zombie",
            "A zombie has already exited; its parent must collect its status.",
        ),
        (
            "Trusting a stale PID",
            "PIDs can be reused after a process exits.",
        ),
        (
            "Forgetting the supervisor",
            "A service manager may restart a manually killed process or consider it a failure.",
        ),
        (
            "Assuming D state means a signal was ignored",
            "Uninterruptible sleep usually means the task is waiting in the kernel; behavior depends on the operation.",
        ),
    ]

    for mistake, correction in mistakes:
        print(f"\n{mistake}")
        print(f"  {correction}")


# ============================================================================
# SECTION 31: COMPARISON
# ============================================================================

def show_tool_comparison() -> None:
    print_banner("32. Tool Comparison")

    rows = [
        ("ps", "Snapshot", "Precise process listing and scripting"),
        ("top", "Interactive", "Live CPU/memory/process monitoring"),
        ("htop", "Interactive", "Navigation, sorting, trees, process control"),
        ("kill", "Action", "Send a signal to a PID"),
        ("pkill", "Action", "Send a signal to processes selected by criteria"),
        ("killall", "Action", "Send signals to processes selected by name"),
        ("/proc", "Kernel interface", "Detailed process and system information"),
        ("jobs", "Shell builtin", "Current shell's job table"),
        ("fg", "Shell builtin", "Bring a job into the foreground"),
        ("bg", "Shell builtin", "Resume a stopped job in the background"),
        ("wait", "Shell builtin", "Wait for shell-managed child jobs"),
    ]

    print(f"{'Tool':<14}{'Type':<18}Primary purpose")
    print("-" * 78)
    for tool, kind, purpose in rows:
        print(f"{tool:<14}{kind:<18}{purpose}")


# ============================================================================
# SECTION 32: PRACTICAL COMMAND REFERENCE
# ============================================================================

def show_command_reference() -> None:
    print_banner("33. Practical Command Reference")

    commands = [
        ("ps aux", "Snapshot of many processes in BSD-style format."),
        ("ps -ef", "Full-format process listing."),
        ("ps -eo pid,ppid,stat,comm", "Custom process columns."),
        ("ps --forest", "Display process hierarchy."),
        ("ps -L -p PID", "Display threads for a process."),
        ("top", "Interactive live process monitor."),
        ("top -b -n 1", "One batch-mode top snapshot."),
        ("htop", "Interactive process monitor with navigation."),
        ("kill -TERM PID", "Request graceful termination."),
        ("kill -INT PID", "Send interrupt signal."),
        ("kill -STOP PID", "Stop a process."),
        ("kill -CONT PID", "Continue a stopped process."),
        ("kill -KILL PID", "Force termination; last resort."),
        ("kill -l", "List signal names/numbers."),
        ("jobs", "List shell jobs."),
        ("fg %1", "Bring job 1 to foreground."),
        ("bg %1", "Resume job 1 in background."),
        ("wait %1", "Wait for a shell job."),
        ("pstree -p PID", "Display a process tree."),
        ("cat /proc/PID/status", "Read kernel-maintained process status."),
        ("ls -l /proc/PID/fd", "Inspect visible file descriptors."),
    ]

    for command, purpose in commands:
        print(f"{command:<34} {purpose}")


# ============================================================================
# SECTION 33: EDGE CASES
# ============================================================================

def show_edge_cases() -> None:
    print_banner("34. Important Edge Cases and Exceptions")

    explain(
        """
        Process control has several behaviors that surprise beginners.

        A process in uninterruptible sleep may not respond immediately to
        signals because it is inside a kernel wait associated with an operation
        that cannot safely be interrupted at that moment.

        SIGSTOP and SIGKILL cannot be handled. A program cannot use a Python
        signal handler to clean up after SIGKILL.

        A process can change its state between the moment you inspect it and
        the moment you send a signal. This is a race condition. PID-based
        process management therefore requires careful identity verification.

        A process may spawn children after you inspect its process tree.
        Killing one PID does not necessarily terminate its descendants.

        A shell job can contain multiple processes. Signaling one PID is not
        automatically equivalent to signaling the whole job.

        A service may restart immediately after being killed because its
        supervisor is configured for automatic restart.

        Permissions can prevent inspection of some /proc information or
        signaling another user's process.
        """
    )


# ============================================================================
# SECTION 34: PERFORMANCE CONSIDERATIONS
# ============================================================================

def show_performance_considerations() -> None:
    print_banner("35. Performance Considerations")

    explain(
        """
        Monitoring itself consumes resources. Running expensive monitoring
        commands at extremely high frequency can create unnecessary CPU,
        process-creation, terminal, and I/O overhead.

        For one-off diagnosis, ps is usually cheap and straightforward.
        Interactive monitors should be configured with a sensible refresh
        interval. Production monitoring systems generally collect metrics
        continuously using specialized agents rather than repeatedly invoking
        large shell pipelines.

        Process creation also has a cost. Threads and processes have different
        memory and scheduling characteristics. High process churn can increase
        kernel overhead and complicate observability.
        """
    )


# ============================================================================
# SECTION 35: PRODUCTION CHECKLIST
# ============================================================================

def show_production_checklist() -> None:
    print_banner("36. Production Process-Management Checklist")

    checklist = [
        "Identify the process using PID, executable, user, and parent relationship.",
        "Confirm whether the target belongs to a service manager or container.",
        "Inspect CPU, memory, state, threads, open files, and relevant logs.",
        "Prefer graceful application-specific shutdown behavior.",
        "Use SIGTERM before SIGKILL unless an emergency policy requires otherwise.",
        "Use an explicit timeout for graceful shutdown.",
        "Understand whether a supervisor will restart the process.",
        "Avoid broad pkill/killall patterns unless the selection is verified.",
        "Protect PID files and other process-identity mechanisms.",
        "Account for PID namespaces in containers.",
        "Monitor zombie accumulation and process-count limits.",
        "Document signal semantics for production services.",
        "Use structured metrics rather than repeatedly parsing human output when possible.",
    ]

    for index, item in enumerate(checklist, start=1):
        print(f"{index:2}. {item}")


# ============================================================================
# SECTION 36: MINI QUIZ
# ============================================================================

def run_self_check() -> None:
    print_banner("37. Self-Check Questions")

    questions = [
        (
            "1. What is the difference between a program and a process?",
            "A program is passive code; a process is an executing instance with kernel-managed state.",
        ),
        (
            "2. What does kill -TERM PID normally request?",
            "A catchable termination request, normally allowing graceful cleanup.",
        ),
        (
            "3. Why is SIGKILL different from SIGTERM?",
            "SIGKILL cannot be caught, blocked, or ignored, so application cleanup cannot run because of the signal.",
        ),
        (
            "4. What does Ctrl-Z normally generate?",
            "SIGTSTP for the terminal foreground job.",
        ),
        (
            "5. What does Ctrl-C normally generate?",
            "SIGINT for the terminal foreground process group.",
        ),
        (
            "6. Why can a zombie not be fixed by simply sending SIGTERM?",
            "The process has already exited; its parent must collect its termination status.",
        ),
        (
            "7. What is PPID?",
            "The parent process ID.",
        ),
        (
            "8. Why is RSS not equivalent to unique memory ownership?",
            "Memory pages can be shared by multiple processes.",
        ),
        (
            "9. What is the primary difference between ps and top?",
            "ps provides a snapshot; top provides continuously refreshed interactive monitoring.",
        ),
        (
            "10. Why should a stale PID not be trusted?",
            "The PID may have been reused by a different process.",
        ),
    ]

    for question, answer in questions:
        print(f"\n{question}")
        print(f"Answer: {answer}")


# ============================================================================
# SECTION 37: INTERACTIVE MENU
# ============================================================================

MENU_ITEMS = {
    "1": ("Process fundamentals", show_process_fundamentals),
    "2": ("Process states", show_process_states),
    "3": ("ps demonstration", demonstrate_ps),
    "4": ("top demonstration", demonstrate_top),
    "5": ("htop concepts", demonstrate_htop),
    "6": ("Signals", show_signals),
    "7": ("kill and related commands", demonstrate_kill_commands),
    "8": ("Process groups and sessions", show_process_groups_and_sessions),
    "9": ("Foreground/background job control", show_shell_job_control_examples),
    "10": ("/proc", show_proc_filesystem),
    "11": ("Process hierarchy", show_current_process_tree),
    "12": ("Memory information", show_memory_information),
    "13": ("Resource measurement", demonstrate_resource_measurement),
    "14": ("Python subprocesses", demonstrate_subprocess_creation),
    "15": ("Signal laboratory", run_signal_lab),
    "16": ("SIGSTOP/SIGCONT laboratory", run_stop_continue_lab),
    "17": ("Zombie laboratory", run_zombie_lab),
    "18": ("Orphan processes", explain_orphans),
    "19": ("wait and exit status", demonstrate_wait_and_exit_status),
    "20": ("Pipelines", demonstrate_pipeline),
    "21": ("Scheduling and load", show_scheduler_concepts),
    "22": ("Threads versus processes", demonstrate_threads_vs_processes),
    "23": ("Process limits", show_process_limits),
    "24": ("Inspect current PID", lambda: inspect_pid(os.getpid())),
    "25": ("Signal safety", safe_signal_test_for_lab_process),
    "26": ("Graceful shutdown", explain_signal_escalation),
    "27": ("SIGHUP and daemons", explain_sighup_and_daemons),
    "28": ("Production supervision", explain_supervision),
    "29": ("Debugging workflow", show_debugging_workflow),
    "30": ("Security considerations", show_security_considerations),
    "31": ("Common mistakes", show_common_mistakes),
    "32": ("Tool comparison", show_tool_comparison),
    "33": ("Command reference", show_command_reference),
    "34": ("Edge cases", show_edge_cases),
    "35": ("Performance considerations", show_performance_considerations),
    "36": ("Production checklist", show_production_checklist),
    "37": ("Self-check questions", run_self_check),
}


def interactive_menu() -> None:
    """Run an interactive study menu."""
    while True:
        print_banner("Linux Processes Study Menu")
        for key, (title, _) in MENU_ITEMS.items():
            print(f"{key:>2}. {title}")
        print(" Q. Quit")

        choice = input("\nSelect a section: ").strip().lower()

        if choice == "q":
            print("Exiting.")
            return

        item = MENU_ITEMS.get(choice)
        if item is None:
            print("Invalid selection.")
            continue

        try:
            item[1]()
        except KeyboardInterrupt:
            print("\nSection interrupted.")
        except Exception as exc:
            print(f"\nSection failed safely: {type(exc).__name__}: {exc}")

        input("\nPress Enter to return to the menu...")


# ============================================================================
# SECTION 38: RUN ALL
# ============================================================================

def run_all() -> None:
    """
    Execute the educational sequence.

    Potentially interactive system tools such as top and htop are represented
    through safe non-interactive demonstrations, while shell job-control
    commands are explained rather than executed in the current shell.
    """
    sections = [
        show_process_fundamentals,
        show_process_states,
        demonstrate_ps,
        demonstrate_top,
        demonstrate_htop,
        show_signals,
        demonstrate_kill_commands,
        show_process_groups_and_sessions,
        show_shell_job_control_examples,
        show_proc_filesystem,
        show_current_process_tree,
        show_memory_information,
        demonstrate_resource_measurement,
        demonstrate_subprocess_creation,
        run_signal_lab,
        run_stop_continue_lab,
        run_zombie_lab,
        explain_orphans,
        demonstrate_wait_and_exit_status,
        demonstrate_pipeline,
        show_scheduler_concepts,
        demonstrate_threads_vs_processes,
        show_process_limits,
        lambda: inspect_pid(os.getpid()),
        safe_signal_test_for_lab_process,
        explain_signal_escalation,
        explain_sighup_and_daemons,
        explain_supervision,
        show_debugging_workflow,
        show_security_considerations,
        show_common_mistakes,
        show_tool_comparison,
        show_command_reference,
        show_edge_cases,
        show_performance_considerations,
        show_production_checklist,
        run_self_check,
    ]

    for section in sections:
        try:
            section()
        except KeyboardInterrupt:
            print("\nCurrent section interrupted. Continuing.")
        except Exception as exc:
            print(
                f"\nSection {section.__name__} failed safely: "
                f"{type(exc).__name__}: {exc}"
            )


# ============================================================================
# SECTION 39: COMMAND-LINE ARGUMENTS
# ============================================================================

def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Comprehensive Linux process study and safe process-control "
            "demonstration."
        )
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help="Run the complete educational sequence.",
    )

    parser.add_argument(
        "--menu",
        action="store_true",
        help="Open the interactive study menu.",
    )

    parser.add_argument(
        "--pid",
        type=int,
        help="Inspect an existing PID without sending it a signal.",
    )

    parser.add_argument(
        "--ps",
        action="store_true",
        help="Run the ps demonstration.",
    )

    parser.add_argument(
        "--top",
        action="store_true",
        help="Run the non-interactive top demonstration.",
    )

    parser.add_argument(
        "--signals",
        action="store_true",
        help="Show signal concepts and run a safe SIGUSR1 demonstration.",
    )

    parser.add_argument(
        "--signal-lab",
        action="store_true",
        help="Run the safe child-process signal laboratory.",
    )

    parser.add_argument(
        "--stop-cont",
        action="store_true",
        help="Run the safe SIGSTOP/SIGCONT laboratory.",
    )

    parser.add_argument(
        "--zombie-lab",
        action="store_true",
        help="Run the temporary zombie-process laboratory.",
    )

    parser.add_argument(
        "--reference",
        action="store_true",
        help="Print the command reference and tool comparison.",
    )

    return parser


# ============================================================================
# SECTION 40: MAIN
# ============================================================================

def main() -> int:
    parser = build_argument_parser()
    args = parser.parse_args()

    linux_available = require_linux()

    print_banner("Linux Processes: ps, top, htop, kill, Signals, and Job Control")
    print(f"Python version : {platform.python_version()}")
    print(f"Platform       : {platform.platform()}")
    print(f"Current PID    : {os.getpid()}")
    print(f"Current PPID   : {os.getppid()}")

    if not linux_available:
        print(
            "\nLinux-specific demonstrations are disabled on non-Linux systems."
        )
        return 1

    # Explicit command-line modes are useful for focused study.
    if args.pid is not None:
        inspect_pid(args.pid)
        return 0

    if args.ps:
        demonstrate_ps()
        return 0

    if args.top:
        demonstrate_top()
        return 0

    if args.signals:
        show_signals()
        return 0

    if args.signal_lab:
        run_signal_lab()
        return 0

    if args.stop_cont:
        run_stop_continue_lab()
        return 0

    if args.zombie_lab:
        run_zombie_lab()
        return 0

    if args.reference:
        show_tool_comparison()
        show_command_reference()
        return 0

    if args.all:
        run_all()
        return 0

    # The default behavior is interactive because several sections are
    # intentionally detailed and potentially lengthy.
    interactive_menu()
    return 0


if __name__ == "__main__":
    sys.exit(main())
