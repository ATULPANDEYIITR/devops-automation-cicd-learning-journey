#!/usr/bin/env python3
"""
LINUX FUNDAMENTALS
==================

A comprehensive beginner-to-advanced study script covering:

- Linux and Unix concepts
- Filesystem hierarchy
- Directories and files
- Absolute and relative paths
- File types
- Navigation commands
- File and directory management
- Viewing and searching files
- Permissions and ownership
- Links
- Redirection and pipes
- Wildcards and shell expansion
- Environment variables
- Processes and basic system inspection
- Disk usage
- Archives and compression
- Shell scripting fundamentals
- Error handling and debugging
- Security and production best practices

This script is intentionally self-contained. It does not execute destructive
Linux commands. Linux command demonstrations are represented as strings and
explained using Python simulations where useful.

Run:
    python3 linux_fundamentals.py
"""

from __future__ import annotations

import os
import shutil
import stat
import tempfile
from pathlib import Path
from typing import Dict, List, Tuple


# ============================================================================
# SECTION 1: INTRODUCTION TO LINUX
# ============================================================================

def print_section(title: str) -> None:
    """Print a clearly formatted section heading."""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def introduction() -> None:
    print_section("1. LINUX FUNDAMENTALS")

    print(
        """
Linux is an operating system family based on the Linux kernel.

A typical Linux system consists of several layers:

1. Hardware
   Physical components such as CPU, memory, storage, and network devices.

2. Kernel
   The core of the operating system. It manages hardware resources, processes,
   memory, devices, and system calls.

3. Shell
   A command interpreter that allows users to interact with the operating
   system using commands.

4. Utilities and applications
   Programs used for administration, development, networking, text processing,
   and other tasks.

The command line is often accessed through a terminal application.

A terminal provides an interface to a shell.

Common shells include:
    bash
    zsh
    sh
    fish

This script focuses primarily on concepts commonly used with POSIX-like shells
and Bash.
"""
    )


# ============================================================================
# SECTION 2: FILESYSTEM FUNDAMENTALS
# ============================================================================

def filesystem_fundamentals() -> None:
    print_section("2. THE LINUX FILESYSTEM")

    print(
        """
Linux uses a hierarchical filesystem.

The highest directory is called the root directory:

    /

Every file and directory exists somewhere below this root.

A simplified hierarchy looks like:

    /
    ├── bin
    ├── boot
    ├── dev
    ├── etc
    ├── home
    │   ├── alice
    │   └── bob
    ├── lib
    ├── media
    ├── mnt
    ├── opt
    ├── proc
    ├── root
    ├── run
    ├── sbin
    ├── tmp
    ├── usr
    │   ├── bin
    │   ├── lib
    │   └── local
    └── var

Important directories:

/           Root of the filesystem.

/home       Usually contains ordinary users' home directories.

/root       Home directory of the root user.

/etc        System configuration files.

/bin        Essential executable commands on many traditional layouts.

/usr        User applications, libraries, documentation, and shared resources.

/var        Variable data such as logs, caches, and databases.

/tmp        Temporary files.

/dev        Device representations.

/proc       Virtual filesystem containing process and kernel information.

/opt        Optional or third-party software.

/mnt        Temporary mount locations.

/media      Mount points for removable media on many distributions.
"""
    )


# ============================================================================
# SECTION 3: FILES, DIRECTORIES, AND FILE TYPES
# ============================================================================

def file_types() -> None:
    print_section("3. FILES, DIRECTORIES, AND FILE TYPES")

    print(
        """
In Linux, many resources are represented as files.

Common file types include:

Regular file
    Contains ordinary data such as text, images, programs, or binary data.

Directory
    Stores references to files and other directories.

Symbolic link
    A reference to another path.

Character device
    Represents devices that transfer data character by character.

Block device
    Represents devices that transfer data in blocks.

Socket
    Used for inter-process or network communication.

Named pipe (FIFO)
    Allows processes to communicate through a special filesystem object.
"""
    )

    sample_modes = {
        "regular file": stat.S_IFREG,
        "directory": stat.S_IFDIR,
        "symbolic link": stat.S_IFLNK,
        "character device": stat.S_IFCHR,
        "block device": stat.S_IFBLK,
        "FIFO": stat.S_IFIFO,
        "socket": stat.S_IFSOCK,
    }

    print("Python representations of common Linux file type constants:")
    for name, mode in sample_modes.items():
        print(f"  {name:20} -> {mode}")


# ============================================================================
# SECTION 4: PATHS
# ============================================================================

def path_fundamentals() -> None:
    print_section("4. PATHS: ABSOLUTE AND RELATIVE")

    print(
        """
A path identifies the location of a file or directory.

Absolute path:
    Starts from the root directory.

Example:

    /home/student/projects/app.py

Relative path:
    Starts from the current working directory.

Example:

    projects/app.py

Special path components:

.       Current directory
..      Parent directory
~       Home directory in shell expansion

Examples:

    .
    ../documents
    ../../file.txt
    ~/projects
"""
    )

    current_directory = Path.cwd()

    print("Current Python working directory:")
    print(f"  {current_directory}")

    print("\nPath examples using pathlib:")

    relative_path = Path("documents") / "notes.txt"
    print(f"Relative path: {relative_path}")

    absolute_path = current_directory / relative_path
    print(f"Absolute path: {absolute_path}")

    parent_directory = current_directory.parent
    print(f"Parent directory: {parent_directory}")

    home_directory = Path.home()
    print(f"Home directory: {home_directory}")


# ============================================================================
# SECTION 5: NAVIGATION COMMANDS
# ============================================================================

def navigation_commands() -> None:
    print_section("5. NAVIGATING DIRECTORIES")

    commands = [
        ("pwd", "Print the current working directory."),
        ("ls", "List directory contents."),
        ("ls -l", "List files using long format."),
        ("ls -a", "Include hidden files."),
        ("cd directory", "Change into a directory."),
        ("cd ..", "Move to the parent directory."),
        ("cd ~", "Move to the user's home directory."),
        ("cd /", "Move to the filesystem root."),
    ]

    for command, description in commands:
        print(f"{command:20} {description}")

    print(
        """
Hidden files usually begin with a period.

Examples:

    .bashrc
    .profile
    .config

The command:

    ls

normally does not show them.

The command:

    ls -a

shows entries beginning with a period.
"""
    )


# ============================================================================
# SECTION 6: FILE AND DIRECTORY MANAGEMENT
# ============================================================================

def file_management() -> None:
    print_section("6. CREATING, COPYING, MOVING, AND REMOVING FILES")

    print(
        """
Common commands:

touch file.txt
    Creates an empty file if it does not exist.

mkdir directory
    Creates a directory.

mkdir -p parent/child/grandchild
    Creates nested directories when necessary.

cp source.txt destination.txt
    Copies a file.

cp -r source_directory destination_directory
    Recursively copies a directory.

mv old_name.txt new_name.txt
    Renames or moves a file.

rm file.txt
    Removes a file.

rm -r directory
    Recursively removes a directory.

rmdir empty_directory
    Removes an empty directory.

Important:
    rm generally does not move files to a recycle bin.
    Incorrect recursive removal can permanently delete important data.
"""
    )

    # Demonstrate equivalent operations safely inside a temporary directory.
    with tempfile.TemporaryDirectory() as temporary_directory:
        workspace = Path(temporary_directory)

        print(f"\nSafe temporary workspace: {workspace}")

        original = workspace / "original.txt"
        original.write_text("Linux filesystem demonstration.\n", encoding="utf-8")

        copy = workspace / "copy.txt"
        shutil.copy2(original, copy)

        renamed = workspace / "renamed.txt"
        copy.rename(renamed)

        nested = workspace / "parent" / "child" / "grandchild"
        nested.mkdir(parents=True)

        print("Created:")
        for item in sorted(workspace.rglob("*")):
            print(f"  {item.relative_to(workspace)}")


# ============================================================================
# SECTION 7: VIEWING FILE CONTENT
# ============================================================================

def viewing_files() -> None:
    print_section("7. VIEWING FILE CONTENT")

    commands = [
        ("cat file.txt", "Display file contents."),
        ("less file.txt", "View content interactively."),
        ("head file.txt", "Display the first lines."),
        ("tail file.txt", "Display the final lines."),
        ("tail -f logfile.log", "Follow new content appended to a file."),
        ("wc file.txt", "Count lines, words, and bytes."),
    ]

    for command, description in commands:
        print(f"{command:25} {description}")

    sample_text = """line one
line two
line three
line four
line five"""

    lines = sample_text.splitlines()

    print("\nPython simulation of head:")
    for line in lines[:3]:
        print(line)

    print("\nPython simulation of tail:")
    for line in lines[-3:]:
        print(line)

    print("\nLine count:")
    print(len(lines))


# ============================================================================
# SECTION 8: SEARCHING FOR FILES AND TEXT
# ============================================================================

def searching() -> None:
    print_section("8. SEARCHING FILES AND TEXT")

    print(
        """
Common Linux tools:

find
    Searches for filesystem objects.

grep
    Searches text using patterns.

Examples:

    find . -name "*.py"

Find Python files below the current directory.

    find /var/log -type f

Find regular files below /var/log.

    grep "error" application.log

Search for the text "error".

    grep -i "error" application.log

Search without case sensitivity.

    grep -r "TODO" .

Recursively search files below the current directory.

    grep -n "pattern" file.txt

Display matching line numbers.
"""
    )

    sample_files: Dict[str, str] = {
        "application.log": "INFO server started\nERROR database unavailable\n",
        "notes.txt": "TODO review filesystem permissions\n",
        "readme.md": "Linux commands and directories\n",
    }

    search_term = "error"

    print(f"\nCase-insensitive search for '{search_term}':")

    for filename, content in sample_files.items():
        for line_number, line in enumerate(content.splitlines(), start=1):
            if search_term.lower() in line.lower():
                print(f"{filename}:{line_number}:{line}")


# ============================================================================
# SECTION 9: WILDCARDS AND SHELL EXPANSION
# ============================================================================

def shell_wildcards() -> None:
    print_section("9. WILDCARDS AND SHELL EXPANSION")

    print(
        """
Shell wildcards are patterns expanded by the shell.

*       Matches zero or more characters.

?       Matches exactly one character.

[abc]   Matches one character from a set.

[0-9]   Matches one digit.

Examples:

    *.txt
    file?.txt
    image[0-9].png

Important distinction:

A wildcard is usually expanded by the shell before the command receives it.

For example:

    rm *.tmp

The shell may expand *.tmp into:

    rm a.tmp b.tmp c.tmp

The rm command may never see the literal string "*.tmp".
"""
    )

    filenames = [
        "report.txt",
        "notes.txt",
        "image.png",
        "file1.txt",
        "file2.txt",
        "file10.txt",
    ]

    import fnmatch

    print("\nPattern: *.txt")
    print([name for name in filenames if fnmatch.fnmatch(name, "*.txt")])

    print("\nPattern: file?.txt")
    print([name for name in filenames if fnmatch.fnmatch(name, "file?.txt")])


# ============================================================================
# SECTION 10: FILE PERMISSIONS
# ============================================================================

def permission_fundamentals() -> None:
    print_section("10. FILE PERMISSIONS")

    print(
        """
Linux permissions are commonly represented by:

r = read
w = write
x = execute

Permissions are evaluated for:

u = user (owner)
g = group
o = others

Example:

    rwxr-xr--

This can be interpreted as:

Owner:
    rwx

Group:
    r-x

Others:
    r--

Numeric representation:

r = 4
w = 2
x = 1

Examples:

7 = rwx = 4 + 2 + 1
6 = rw- = 4 + 2
5 = r-x = 4 + 1
4 = r-- = 4
0 = --- = no permissions

Therefore:

755 = rwxr-xr-x
644 = rw-r--r--
700 = rwx------
"""
    )

    examples = [0o644, 0o755, 0o700, 0o600]

    for mode in examples:
        permission_text = stat.filemode(mode)
        print(f"{oct(mode)} -> {permission_text}")

    print(
        """
Important command examples:

    chmod 644 file.txt
    chmod 755 script.sh
    chmod u+x script.sh

Ownership commands:

    chown user file.txt
    chown user:group file.txt

Changing ownership generally requires appropriate privileges.

Directory permissions have special implications:

Read:
    Allows listing directory entries in many situations.

Write:
    Allows creating, deleting, or renaming entries when combined with suitable
    directory access.

Execute:
    Allows traversal through the directory.

A common mistake is treating directory permissions exactly like file permissions.
Directory access semantics are different.
"""
    )


# ============================================================================
# SECTION 11: OWNERSHIP AND GROUPS
# ============================================================================

def ownership() -> None:
    print_section("11. OWNERSHIP AND GROUPS")

    print(
        """
Every filesystem object usually has:

- A user owner
- A group owner

Common inspection command:

    ls -l

Example output:

    -rw-r--r-- 1 alice developers 1200 Sep 5 10:00 report.txt

Conceptually:

    permissions  links  owner  group  size  date  name

Ownership supports collaborative access control.

Groups allow multiple users to share permissions without assigning permissions
individually to every user.

Commands:

    id

Displays user identity and group information.

    groups

Displays group membership.

    chown

Changes ownership.

    chgrp

Changes group ownership.
"""
    )

    if hasattr(os, "getuid"):
        print(f"Current UID: {os.getuid()}")

    if hasattr(os, "getgid"):
        print(f"Current GID: {os.getgid()}")


# ============================================================================
# SECTION 12: LINKS
# ============================================================================

def links() -> None:
    print_section("12. HARD LINKS AND SYMBOLIC LINKS")

    print(
        """
A hard link is another directory entry pointing to the same underlying inode.

A symbolic link stores a path reference to another filesystem object.

Hard link characteristics:

- Shares underlying file data with the original.
- Usually cannot cross filesystem boundaries.
- Usually cannot link directories for ordinary users.
- Removing one name does not remove the data while another hard link exists.

Symbolic link characteristics:

- Stores a path to another object.
- Can point across filesystems.
- Can point to directories.
- Can become broken if the target is removed.

Commands:

    ln original.txt hard_link.txt

Creates a hard link.

    ln -s original.txt symbolic_link.txt

Creates a symbolic link.
"""
    )

    with tempfile.TemporaryDirectory() as temporary_directory:
        directory = Path(temporary_directory)

        original = directory / "original.txt"
        original.write_text("Shared file data", encoding="utf-8")

        symbolic = directory / "symbolic.txt"
        symbolic.symlink_to(original)

        print("Original exists:", original.exists())
        print("Symbolic link exists:", symbolic.exists())
        print("Symbolic link points to:", os.readlink(symbolic))


# ============================================================================
# SECTION 13: INPUT, OUTPUT, AND ERROR STREAMS
# ============================================================================

def streams_and_redirection() -> None:
    print_section("13. STANDARD INPUT, OUTPUT, ERROR, AND REDIRECTION")

    print(
        """
Processes commonly use three standard streams:

stdin
    Standard input.

stdout
    Standard output.

stderr
    Standard error.

File descriptors commonly associated with them:

0 -> stdin
1 -> stdout
2 -> stderr

Examples:

    command > output.txt

Redirect standard output to a file.

    command >> output.txt

Append standard output.

    command 2> errors.txt

Redirect standard error.

    command > output.txt 2>&1

Redirect standard output and standard error together.

Pipes connect the output of one command to the input of another:

    command1 | command2

Example:

    ls -l | grep ".txt"

Conceptually:

    ls produces text
        |
        v
    grep receives that text through standard input
"""
    )


# ============================================================================
# SECTION 14: PIPES WITH PYTHON SIMULATION
# ============================================================================

def pipeline_simulation() -> None:
    print_section("14. PIPELINE CONCEPTS")

    numbers = list(range(1, 21))

    # First pipeline stage: produce data.
    produced = numbers

    # Second pipeline stage: filter data.
    filtered = [number for number in produced if number % 2 == 0]

    # Third pipeline stage: transform data.
    transformed = [number * number for number in filtered]

    print("Produced:", produced)
    print("Filtered even numbers:", filtered)
    print("Squared values:", transformed)

    print(
        """
A shell pipeline follows the same broad concept:

producer | filter | transformer | consumer

Pipelines are powerful because programs can be combined into larger workflows.
"""
    )


# ============================================================================
# SECTION 15: ENVIRONMENT VARIABLES
# ============================================================================

def environment_variables() -> None:
    print_section("15. ENVIRONMENT VARIABLES")

    print(
        """
Environment variables store configuration values associated with a process.

Common variables:

HOME
    User's home directory.

PATH
    Directories searched for executable commands.

USER
    Current user name on many systems.

SHELL
    User's shell.

PWD
    Current working directory.

Examples:

    echo $HOME

    echo $PATH

Temporary assignment for one command:

    MODE=production command

Exporting a variable:

    export MODE=production
"""
    )

    for variable_name in ("HOME", "PATH", "USER", "SHELL"):
        print(f"{variable_name} = {os.environ.get(variable_name)}")

    print(
        """
Security consideration:

Environment variables are convenient but are not automatically secure storage.

Secrets placed in environment variables can sometimes be exposed through:

- Process inspection
- Logs
- Debug output
- Crash reports
- Misconfigured monitoring systems

Sensitive values should be handled carefully.
"""
    )


# ============================================================================
# SECTION 16: THE PATH VARIABLE
# ============================================================================

def path_environment() -> None:
    print_section("16. HOW THE PATH VARIABLE WORKS")

    path_value = os.environ.get("PATH", "")
    directories = path_value.split(os.pathsep)

    print("Executable search directories:")

    for index, directory in enumerate(directories, start=1):
        print(f"{index:2}. {directory}")

    print(
        """
When a command such as:

    python

is entered, the shell searches directories listed in PATH.

A command can also be executed using an explicit path:

    /usr/bin/python3

Security consideration:

Avoid adding untrusted directories to PATH, particularly before trusted system
directories.

A dangerous configuration can cause an unintended executable with the same name
to run before the intended system command.
"""
    )


# ============================================================================
# SECTION 17: ARCHIVES AND COMPRESSION
# ============================================================================

def archives_and_compression() -> None:
    print_section("17. ARCHIVES AND COMPRESSION")

    print(
        """
Archiving and compression are related but different concepts.

Archive:
    Combines multiple files and directories into one file.

Compression:
    Reduces data size.

The tar utility commonly creates archives.

Examples:

    tar -cf archive.tar directory

Create an archive.

    tar -tf archive.tar

List archive contents.

    tar -xf archive.tar

Extract an archive.

Compressed archive examples:

    tar -czf archive.tar.gz directory

Creates a gzip-compressed tar archive.

    tar -xzf archive.tar.gz

Extracts it.

Common extensions:

.tar
.tar.gz
.tgz
.tar.bz2
.tar.xz
.zip

Security consideration:

Do not blindly extract untrusted archives into sensitive directories.

Potential issues include:

- Path traversal entries
- Extremely large extracted data
- Symbolic link manipulation
- Overwriting important files
"""
    )


# ============================================================================
# SECTION 18: DISK USAGE
# ============================================================================

def disk_usage() -> None:
    print_section("18. DISK USAGE")

    print(
        """
Common commands:

    df -h

Shows filesystem-level disk usage.

    du -sh directory

Shows approximate total usage of a directory.

The concepts differ:

df
    Reports usage of mounted filesystems.

du
    Calculates usage associated with files and directories.

Large file systems can make recursive directory analysis expensive.
"""
    )

    usage = shutil.disk_usage(Path.cwd())

    print(f"Current filesystem total: {usage.total}")
    print(f"Current filesystem used:  {usage.used}")
    print(f"Current filesystem free:  {usage.free}")

    if usage.total > 0:
        used_percentage = usage.used / usage.total * 100
        print(f"Used percentage: {used_percentage:.2f}%")


# ============================================================================
# SECTION 19: PROCESSES
# ============================================================================

def processes() -> None:
    print_section("19. PROCESSES")

    print(
        """
A process is an executing program.

Important process concepts:

PID
    Process identifier.

PPID
    Parent process identifier.

Foreground process
    Associated with the current terminal.

Background process
    Runs without occupying the shell interactively.

Common commands:

    ps

Displays processes.

    ps aux

Displays a detailed process list on many systems.

    top

Interactive process monitor.

    kill PID

Sends a signal to a process.

    kill -TERM PID

Requests graceful termination.

    kill -KILL PID

Forces termination when the operating system allows it.

Important distinction:

SIGTERM allows a process to perform cleanup.

SIGKILL cannot be handled or ignored by the target process and should generally
not be the first termination choice.
"""
    )

    print("Current process ID:", os.getpid())

    if hasattr(os, "getppid"):
        print("Parent process ID:", os.getppid())


# ============================================================================
# SECTION 20: FILE DESCRIPTORS AND RESOURCE MANAGEMENT
# ============================================================================

def file_descriptors() -> None:
    print_section("20. FILE DESCRIPTORS AND RESOURCE MANAGEMENT")

    print(
        """
Operating systems represent open files and other resources using handles.

On Unix-like systems these are commonly called file descriptors.

Programs should close resources when they are no longer required.

Python's context manager is a safe pattern:

    with open("file.txt") as file:
        data = file.read()

The file is closed automatically when leaving the block, even when an exception
occurs during processing.
"""
    )

    with tempfile.TemporaryDirectory() as temporary_directory:
        filename = Path(temporary_directory) / "example.txt"

        with filename.open("w", encoding="utf-8") as file:
            file.write("Resource management demonstration.\n")

        with filename.open("r", encoding="utf-8") as file:
            print(file.read().strip())


# ============================================================================
# SECTION 21: USERS AND PRIVILEGES
# ============================================================================

def users_and_privileges() -> None:
    print_section("21. USERS, ROOT, AND PRIVILEGES")

    print(
        """
Linux systems distinguish between ordinary users and privileged users.

The root account typically has extensive administrative privileges.

Administrative operations should follow the principle of least privilege:

Grant only the permissions required for a task.

Commands may be executed with elevated privileges using tools such as:

    sudo command

Security principles:

- Avoid using root unnecessarily.
- Avoid running development applications with elevated privileges.
- Review commands before executing them with sudo.
- Restrict administrative access.
- Use appropriate file permissions.
- Do not store credentials in world-readable files.
"""
    )


# ============================================================================
# SECTION 22: BASIC SHELL SCRIPTING
# ============================================================================

def shell_scripting_concepts() -> None:
    print_section("22. BASIC SHELL SCRIPTING")

    print(
        """
A shell script is a text file containing shell commands.

Example structure:

    #!/usr/bin/env bash

    name="student"
    echo "Hello, $name"

The first line is called a shebang.

It identifies the interpreter used to execute the script.

Variables:

    name="Linux"

Variable reference:

    echo "$name"

Command substitution:

    current_date=$(date)

Conditional execution:

    if [ -f "file.txt" ]; then
        echo "File exists"
    fi

Loop:

    for item in *.txt; do
        echo "$item"
    done

Important shell rule:

Quoting variables is often necessary.

Safer:

    rm -- "$filename"

Potentially unsafe:

    rm $filename

Unquoted expansion can cause word splitting and wildcard expansion.
"""
    )


# ============================================================================
# SECTION 23: COMMAND EXIT STATUS
# ============================================================================

def exit_status() -> None:
    print_section("23. COMMAND EXIT STATUS")

    print(
        """
Unix commands generally return an exit status.

Conventionally:

0
    Success.

Non-zero
    Failure or another condition.

The exact meaning of non-zero values depends on the command.

In a shell:

    command
    echo $?

In Python:

    import subprocess

    result = subprocess.run(
        ["command"],
        capture_output=True,
        text=True
    )

    print(result.returncode)

Checking exit status is essential for reliable automation.
"""
    )


# ============================================================================
# SECTION 24: ERROR HANDLING
# ============================================================================

def error_handling() -> None:
    print_section("24. ERROR HANDLING")

    print(
        """
Common Linux-related failure categories include:

- File does not exist.
- Permission denied.
- Disk full.
- Command not found.
- Invalid path.
- Resource busy.
- Network unavailable.
- Process terminated.
"""
    )

    try:
        Path("/path/that/does/not/exist/example.txt").read_text()
    except FileNotFoundError as error:
        print("Handled FileNotFoundError:")
        print(" ", error)

    try:
        value = int("not-a-number")
    except ValueError as error:
        print("\nHandled ValueError:")
        print(" ", error)


# ============================================================================
# SECTION 25: COMMON FILESYSTEM EDGE CASES
# ============================================================================

def filesystem_edge_cases() -> None:
    print_section("25. FILESYSTEM EDGE CASES")

    print(
        """
Important edge cases:

1. Filenames can contain spaces.

    "my file.txt"

Use quoting:

    cat "my file.txt"

2. Filenames can begin with a dash.

A filename such as:

    -file.txt

may be interpreted as a command option.

Use:

    rm -- -file.txt

The -- convention often indicates the end of command options.

3. Symbolic links can be broken.

4. Relative paths depend on the current working directory.

5. Case sensitivity is usually significant.

    File.txt

and:

    file.txt

are normally different names.

6. Deleting an open file behaves differently from simply deleting a filename.

On Unix-like systems, a process may continue using an already-open file even after
its directory entry is removed, depending on the filesystem and operating system.

7. File permissions alone are not the complete security model.

Access control lists, mandatory access control systems, mount options, capabilities,
and application-level permissions may also matter.
"""
    )


# ============================================================================
# SECTION 26: FILE NAME VALIDATION
# ============================================================================

def filename_validation() -> None:
    print_section("26. FILE NAME VALIDATION")

    invalid_characters = {"/", "\x00"}

    filenames = [
        "report.txt",
        "my document.txt",
        "../outside.txt",
        "normal-file",
        "data.csv",
    ]

    def is_simple_filename(name: str) -> bool:
        """
        Validate a filename for a restricted application scenario.

        This is intentionally stricter than Linux itself.

        Linux permits many names that applications should reject when accepting
        untrusted input.
        """
        if not name:
            return False

        if any(character in name for character in invalid_characters):
            return False

        if name in {".", ".."}:
            return False

        if Path(name).name != name:
            # Reject path components rather than accepting arbitrary paths.
            return False

        return True

    for filename in filenames:
        print(f"{filename!r:20} -> {is_simple_filename(filename)}")


# ============================================================================
# SECTION 27: PATH TRAVERSAL SECURITY
# ============================================================================

def path_traversal_security() -> None:
    print_section("27. PATH TRAVERSAL SECURITY")

    print(
        """
Path traversal occurs when untrusted input influences a filesystem path.

Unsafe conceptual example:

    requested_name = user_input
    path = Path("/safe/uploads") / requested_name

If requested_name contains:

    ../../sensitive_file

the resulting path may escape the intended directory.

A safer strategy is:

1. Resolve the intended base directory.
2. Resolve the candidate path.
3. Verify that the candidate remains inside the allowed directory.
"""
    )

    with tempfile.TemporaryDirectory() as temporary_directory:
        base_directory = Path(temporary_directory).resolve()

        def safe_path(base: Path, user_input: str) -> Path:
            candidate = (base / user_input).resolve()

            try:
                candidate.relative_to(base)
            except ValueError as error:
                raise ValueError("Path escapes the allowed directory.") from error

            return candidate

        safe_candidate = safe_path(base_directory, "documents/report.txt")
        print("Safe candidate:", safe_candidate)

        try:
            unsafe_candidate = safe_path(base_directory, "../../outside.txt")
            print(unsafe_candidate)
        except ValueError as error:
            print("Blocked unsafe path:", error)


# ============================================================================
# SECTION 28: WORKING DIRECTORY DEPENDENCE
# ============================================================================

def working_directory_dependence() -> None:
    print_section("28. CURRENT WORKING DIRECTORY DEPENDENCE")

    print(
        """
Relative paths depend on the process's current working directory.

Example:

    Path("config/settings.json")

does not identify a single universal location.

Its actual location depends on where the process is running.

Production applications should carefully consider whether resources should be
located relative to:

- Current working directory
- Script location
- User home directory
- System configuration directory
- Environment configuration
"""
    )

    current = Path.cwd()
    relative = Path("data") / "input.txt"

    print("Current directory:", current)
    print("Relative path:", relative)
    print("Interpreted absolute path:", (current / relative).resolve())


# ============================================================================
# SECTION 29: FILESYSTEM PERFORMANCE
# ============================================================================

def performance_considerations() -> None:
    print_section("29. FILESYSTEM PERFORMANCE CONSIDERATIONS")

    print(
        """
Filesystem performance depends on many factors:

- Storage hardware
- Filesystem type
- File size
- Number of files
- Directory structure
- Caching
- Network storage
- Concurrent access
- Metadata operations

Important distinctions:

Reading one large file can behave very differently from reading millions of
small files.

Repeatedly scanning an entire directory tree can be expensive.

Repeated calls such as:

    find /
    grep -r /

can consume significant CPU, storage bandwidth, and memory.

Efficient applications should:

- Limit search scope.
- Stream large files instead of loading everything into memory.
- Avoid unnecessary filesystem scans.
- Use buffering appropriately.
- Handle concurrent modifications.
"""
    )

    sample_data = "record\n" * 100_000

    # Streaming-like processing avoids creating another large list unnecessarily.
    line_count = 0

    for _line in sample_data.splitlines():
        line_count += 1

    print("Processed lines:", line_count)


# ============================================================================
# SECTION 30: DEBUGGING FILESYSTEM PROBLEMS
# ============================================================================

def debugging() -> None:
    print_section("30. DEBUGGING FILESYSTEM AND COMMAND PROBLEMS")

    print(
        """
Useful debugging questions:

1. Am I in the expected directory?

    pwd

2. Does the file actually exist?

    ls
    find

3. What permissions does it have?

    ls -l

4. Which user is running the command?

    whoami
    id

5. Which executable is being executed?

    which command
    command -v command

6. What is the exact command exit status?

    echo $?

7. Is PATH configured correctly?

    echo $PATH

8. Is the filesystem full?

    df -h

9. Is the process still running?

    ps
    top
"""
    )


# ============================================================================
# SECTION 31: PRODUCTION FILE OPERATIONS
# ============================================================================

def production_file_operations() -> None:
    print_section("31. PRODUCTION FILE OPERATION PRINCIPLES")

    print(
        """
Production systems should treat filesystem operations carefully.

Important practices:

Atomic replacement:
    Write new data to a temporary file and replace the target when complete.

Validation:
    Validate paths and file types.

Permissions:
    Create files with restrictive permissions when they contain sensitive data.

Durability:
    Understand when data is buffered and when it is actually written to storage.

Concurrency:
    Multiple processes may attempt to modify the same resource.

Logging:
    Record meaningful failures without exposing secrets.

Cleanup:
    Remove temporary resources.

Error handling:
    Assume operations can fail due to environmental conditions.
"""
    )

    with tempfile.TemporaryDirectory() as temporary_directory:
        directory = Path(temporary_directory)

        target = directory / "configuration.txt"
        temporary = directory / "configuration.txt.tmp"

        temporary.write_text("version=2\n", encoding="utf-8")

        # os.replace provides replacement semantics appropriate for many local
        # filesystem use cases. Atomicity depends on filesystem conditions.
        os.replace(temporary, target)

        print("Atomic-style replacement result:")
        print(target.read_text(encoding="utf-8").strip())


# ============================================================================
# SECTION 32: COMMON COMMANDS REFERENCE
# ============================================================================

def command_reference() -> None:
    print_section("32. COMMON LINUX COMMAND REFERENCE")

    command_groups: List[Tuple[str, List[Tuple[str, str]]]] = [
        (
            "Navigation",
            [
                ("pwd", "Show current directory."),
                ("ls", "List directory contents."),
                ("cd", "Change directory."),
            ],
        ),
        (
            "Files and Directories",
            [
                ("touch", "Create or update a file."),
                ("mkdir", "Create a directory."),
                ("cp", "Copy files."),
                ("mv", "Move or rename files."),
                ("rm", "Remove files."),
                ("rmdir", "Remove empty directories."),
            ],
        ),
        (
            "Viewing",
            [
                ("cat", "Display file content."),
                ("less", "View files interactively."),
                ("head", "Display initial lines."),
                ("tail", "Display final lines."),
                ("wc", "Count lines, words, and bytes."),
            ],
        ),
        (
            "Searching",
            [
                ("find", "Search filesystem objects."),
                ("grep", "Search text."),
            ],
        ),
        (
            "Permissions",
            [
                ("chmod", "Change permissions."),
                ("chown", "Change ownership."),
                ("chgrp", "Change group ownership."),
            ],
        ),
        (
            "System",
            [
                ("ps", "Display processes."),
                ("top", "Monitor processes."),
                ("df", "Show filesystem usage."),
                ("du", "Show directory usage."),
                ("uname", "Show system information."),
            ],
        ),
    ]

    for category, commands in command_groups:
        print(f"\n{category}:")
        for command, description in commands:
            print(f"  {command:10} {description}")


# ============================================================================
# SECTION 33: PRACTICAL MINI FILESYSTEM EXERCISE
# ============================================================================

def practical_filesystem_exercise() -> None:
    print_section("33. PRACTICAL FILESYSTEM EXERCISE")

    print(
        """
This demonstration creates a small project structure safely inside a temporary
directory and performs several common filesystem operations.
"""
    )

    with tempfile.TemporaryDirectory() as temporary_directory:
        project_root = Path(temporary_directory) / "linux_demo_project"

        source_directory = project_root / "src"
        data_directory = project_root / "data"
        logs_directory = project_root / "logs"

        source_directory.mkdir(parents=True)
        data_directory.mkdir()
        logs_directory.mkdir()

        main_file = source_directory / "main.py"
        main_file.write_text(
            'print("Linux filesystem demonstration")\n',
            encoding="utf-8",
        )

        data_file = data_directory / "records.txt"
        data_file.write_text(
            "alpha\nbeta\ngamma\n",
            encoding="utf-8",
        )

        copied_file = data_directory / "records_backup.txt"
        shutil.copy2(data_file, copied_file)

        renamed_file = logs_directory / "application.log"
        renamed_file.write_text(
            "INFO project created\n",
            encoding="utf-8",
        )

        print("Project structure:")

        for item in sorted(project_root.rglob("*")):
            relative_name = item.relative_to(project_root)

            if item.is_dir():
                print(f"  [DIR]  {relative_name}")
            else:
                print(f"  [FILE] {relative_name}")

        print("\nSearching text files for 'beta':")

        for text_file in project_root.rglob("*.txt"):
            for line_number, line in enumerate(
                text_file.read_text(encoding="utf-8").splitlines(),
                start=1,
            ):
                if "beta" in line:
                    print(
                        f"  {text_file.relative_to(project_root)}:"
                        f"{line_number}:{line}"
                    )


# ============================================================================
# SECTION 34: IMPORTANT COMPARISONS
# ============================================================================

def important_comparisons() -> None:
    print_section("34. IMPORTANT COMPARISONS")

    comparisons = [
        (
            "Absolute path",
            "Relative path",
            "Starts from root",
            "Depends on current working directory",
        ),
        (
            "File",
            "Directory",
            "Stores ordinary data",
            "Stores filesystem entries",
        ),
        (
            "Hard link",
            "Symbolic link",
            "References underlying inode",
            "References another path",
        ),
        (
            "cp",
            "mv",
            "Creates a copy",
            "Moves or renames",
        ),
        (
            ">",
            ">>",
            "Overwrites redirected output",
            "Appends redirected output",
        ),
        (
            "stdout",
            "stderr",
            "Normal command output",
            "Diagnostic or error output",
        ),
        (
            "SIGTERM",
            "SIGKILL",
            "Graceful termination request",
            "Forced termination signal",
        ),
    ]

    for left_name, right_name, left_description, right_description in comparisons:
        print(f"\n{left_name} vs {right_name}")
        print(f"  {left_name}:  {left_description}")
        print(f"  {right_name}: {right_description}")


# ============================================================================
# SECTION 35: MAIN EXECUTION
# ============================================================================

def main() -> None:
    """
    Execute all Linux fundamentals demonstrations in progressive order.
    """

    introduction()
    filesystem_fundamentals()
    file_types()
    path_fundamentals()
    navigation_commands()
    file_management()
    viewing_files()
    searching()
    shell_wildcards()
    permission_fundamentals()
    ownership()
    links()
    streams_and_redirection()
    pipeline_simulation()
    environment_variables()
    path_environment()
    archives_and_compression()
    disk_usage()
    processes()
    file_descriptors()
    users_and_privileges()
    shell_scripting_concepts()
    exit_status()
    error_handling()
    filesystem_edge_cases()
    filename_validation()
    path_traversal_security()
    working_directory_dependence()
    performance_considerations()
    debugging()
    production_file_operations()
    command_reference()
    practical_filesystem_exercise()
    important_comparisons()

    print_section("END OF LINUX FUNDAMENTALS STUDY SCRIPT")


if __name__ == "__main__":
    main()
