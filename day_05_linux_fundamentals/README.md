# Linux Fundamentals: Filesystem, Directories, Files, Paths, and Commands

## Introduction

Linux is a family of operating systems built around the Linux kernel. It is widely used in servers, cloud infrastructure, embedded systems, cybersecurity environments, scientific computing, software development, containers, and enterprise systems.

A Linux system is composed of several important layers:

- **Hardware** provides physical computing resources.
- **The kernel** manages processes, memory, devices, filesystems, and communication with hardware.
- **The shell** interprets commands entered by users.
- **Utilities and applications** perform tasks such as file management, networking, programming, administration, and text processing.
- **The filesystem** organizes persistent data into directories and files.

The Python study script accompanying this document demonstrates Linux concepts progressively. It explains command-line concepts while using Python to safely simulate filesystem operations and inspect the current operating environment.

---

# 1. The Linux Filesystem

Linux uses a hierarchical filesystem structure.

The top of the hierarchy is called the **root directory**, represented by:

    /

Every file and directory belongs somewhere below the root directory.

A simplified hierarchy is:

    /
    ├── bin
    ├── boot
    ├── dev
    ├── etc
    ├── home
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
    └── var

Linux differs from systems that organize storage using drive letters such as `C:` or `D:`. Storage devices and partitions are generally mounted into locations within one unified directory hierarchy.

## Important Directories

### `/`

The root of the entire filesystem hierarchy.

### `/home`

Contains home directories for ordinary users on many Linux systems.

Examples:

    /home/alice
    /home/bob

A user's home directory commonly stores personal files, shell configuration, and application settings.

### `/root`

The home directory of the root user.

It should not be confused with `/`, which is the root of the filesystem.

### `/etc`

Contains system configuration files.

Configuration files are often text-based, although the exact organization depends on the Linux distribution and application.

### `/usr`

Contains many user-space applications, libraries, shared resources, and documentation.

Common subdirectories include:

    /usr/bin
    /usr/lib
    /usr/local

### `/var`

Contains variable data that changes during normal system operation.

Examples include:

- Logs
- Caches
- Spools
- Databases
- Application state

### `/tmp`

Used for temporary files.

Applications should not assume that temporary files remain permanently available.

### `/dev`

Contains filesystem representations of devices.

Linux often represents hardware and certain virtual devices as filesystem objects.

### `/proc`

A virtual filesystem that provides information about processes and the kernel.

Files in `/proc` often represent system state rather than ordinary persistent files stored on disk.

### `/opt`

Commonly used for optional or separately installed software.

### `/mnt`

Traditionally used for temporary mount points.

### `/media`

Often used for removable media such as USB drives.

---

# 2. Files and Directories

A **file** is a filesystem object used to store data.

A **directory** is a filesystem object that organizes references to files and other directories.

Linux treats many resources using a unified file-oriented model.

## Common File Types

### Regular Files

Regular files store ordinary data.

Examples include:

- Text documents
- Source code
- Images
- Videos
- Databases
- Executable programs

### Directories

Directories organize filesystem objects.

A directory can contain files and subdirectories.

### Symbolic Links

A symbolic link stores a reference to another filesystem path.

A symbolic link can point to:

- A file
- A directory
- A path on another filesystem

A symbolic link can become broken if its target is removed or moved.

### Hard Links

A hard link is another directory entry referencing the same underlying file data.

Removing one hard link does not necessarily remove the underlying data while other hard links still exist.

### Character Devices

Character devices generally transfer data as streams of characters or bytes.

### Block Devices

Block devices generally provide block-oriented storage access.

### Named Pipes

Named pipes, also called FIFOs, provide a communication mechanism between processes.

### Sockets

Sockets are used for communication between processes or across networks.

---

# 3. Paths

A **path** identifies the location of a filesystem object.

Linux paths use forward slashes:

    /

## Absolute Paths

An absolute path begins at the filesystem root.

Example:

    /home/student/projects/application.py

The meaning of an absolute path does not depend on the current working directory.

## Relative Paths

A relative path is interpreted from the current working directory.

Example:

    projects/application.py

The same relative path can identify different locations depending on where the process is currently running.

## Special Path Components

### `.`

Represents the current directory.

Example:

    ./script.sh

### `..`

Represents the parent directory.

Example:

    ../documents

### `~`

In many shells, `~` expands to the current user's home directory.

Example:

    ~/projects

Shell expansion behavior should not be confused with literal filesystem naming. The shell performs the expansion before passing the resulting path to many commands.

---

# 4. Current Working Directory

Every process has a **current working directory**.

Relative paths are interpreted relative to this location.

The command:

    pwd

prints the current working directory.

For example, if the current directory is:

    /home/student

then:

    documents/report.txt

may refer to:

    /home/student/documents/report.txt

Changing the current directory changes the interpretation of relative paths.

This is important in scripts and production applications because code that depends on an assumed working directory may fail when executed from another location.

The Python `pathlib` module demonstrates this distinction through objects such as:

    Path.cwd()

and:

    Path("documents") / "notes.txt"

---

# 5. Directory Navigation

## `pwd`

Prints the current working directory.

Example:

    pwd

## `ls`

Lists directory contents.

Example:

    ls

Common options include:

    ls -l

Long listing format.

    ls -a

Includes hidden files.

Hidden files commonly begin with a period:

    .bashrc
    .profile
    .config

## `cd`

Changes the current directory.

Example:

    cd documents

Move to the parent directory:

    cd ..

Move to the home directory:

    cd ~

Move to the filesystem root:

    cd /

---

# 6. Creating Files and Directories

## `touch`

A common command for creating an empty file:

    touch file.txt

If the file already exists, `touch` may update its timestamps.

## `mkdir`

Creates a directory.

Example:

    mkdir project

Nested directories can be created using:

    mkdir -p project/src/python

The `-p` option allows missing parent directories to be created.

---

# 7. Copying, Moving, and Removing Files

## `cp`

Copies files.

Example:

    cp source.txt destination.txt

Directories can be copied recursively:

    cp -r source_directory destination_directory

## `mv`

Moves or renames files.

Rename:

    mv old_name.txt new_name.txt

Move:

    mv report.txt documents/

## `rm`

Removes files.

Example:

    rm file.txt

Recursive removal:

    rm -r directory

This command requires significant care because deletion generally does not behave like moving a file to a graphical recycle bin.

## `rmdir`

Removes empty directories.

Example:

    rmdir empty_directory

A common mistake is using recursive removal without verifying the target path.

---

# 8. Viewing File Content

## `cat`

Displays file content.

Example:

    cat notes.txt

It is convenient for small files but may be unsuitable for very large files.

## `less`

Provides interactive viewing.

Example:

    less large_file.log

## `head`

Displays the beginning of a file.

Example:

    head file.txt

## `tail`

Displays the end of a file.

Example:

    tail file.txt

A common monitoring pattern is:

    tail -f application.log

This follows newly appended data.

## `wc`

Counts lines, words, and bytes.

Example:

    wc file.txt

---

# 9. Searching Files and Text

## `find`

Searches the filesystem.

Example:

    find . -name "*.py"

This searches below the current directory for names matching the pattern.

Example:

    find /var/log -type f

This searches for regular files.

Filesystem searches can be expensive when performed over large directory trees.

## `grep`

Searches text for patterns.

Example:

    grep "error" application.log

Case-insensitive search:

    grep -i "error" application.log

Recursive search:

    grep -r "TODO" .

Display line numbers:

    grep -n "pattern" file.txt

`grep` is frequently combined with pipes and other commands.

---

# 10. Wildcards and Shell Expansion

Wildcards are patterns interpreted by the shell.

## `*`

Matches zero or more characters.

Example:

    *.txt

## `?`

Matches exactly one character.

Example:

    file?.txt

This may match:

    file1.txt
    file2.txt

but not necessarily:

    file10.txt

## Character Classes

Example:

    image[0-9].png

This can match filenames containing one digit in that position.

A critical detail is that shell wildcard expansion often occurs before the command executes.

For example:

    rm *.tmp

may be expanded by the shell into:

    rm one.tmp two.tmp three.tmp

The command receives the expanded filenames rather than necessarily receiving the literal wildcard pattern.

---

# 11. File Permissions

Linux commonly uses three basic permission types:

- `r` for read
- `w` for write
- `x` for execute

Permissions are evaluated for three categories:

- User or owner
- Group
- Others

Example:

    rwxr-xr--

This means:

| Category | Permissions |
|---|---|
| Owner | `rwx` |
| Group | `r-x` |
| Others | `r--` |

## Numeric Permissions

Permission values are:

| Permission | Value |
|---|---:|
| Read | 4 |
| Write | 2 |
| Execute | 1 |

Combinations are represented by addition.

Examples:

    7 = 4 + 2 + 1 = rwx
    6 = 4 + 2     = rw-
    5 = 4 + 1     = r-x
    4 = 4         = r--
    0             = ---

Common modes include:

### `644`

    rw-r--r--

### `755`

    rwxr-xr-x

### `700`

    rwx------

### `600`

    rw-------

Permissions can be modified using:

    chmod

Examples:

    chmod 644 file.txt

    chmod 755 script.sh

    chmod u+x script.sh

---

# 12. Directory Permissions

Directory permissions have different practical implications from file permissions.

## Read Permission

Allows listing directory entries in many situations.

## Write Permission

Allows modification of directory entries when combined with appropriate directory access.

This can affect:

- Creating files
- Removing files
- Renaming files

## Execute Permission

Allows traversal through a directory.

A common mistake is assuming that directory permissions behave identically to file permissions.

---

# 13. Ownership and Groups

Filesystem objects commonly have:

- A user owner
- A group owner

The command:

    ls -l

often displays information such as:

    -rw-r--r-- 1 alice developers 1200 Sep 5 10:00 report.txt

The output conceptually contains:

- File type and permissions
- Link count
- Owner
- Group
- Size
- Timestamp
- Name

Useful commands include:

    id

Displays user identity and group information.

    groups

Displays group membership.

    chown

Changes ownership.

    chgrp

Changes group ownership.

Ownership changes often require appropriate privileges.

---

# 14. Hard Links and Symbolic Links

## Hard Links

A hard link is another filesystem name for the same underlying file data.

Create one with:

    ln original.txt hard_link.txt

Important characteristics:

- Multiple names can reference the same underlying data.
- Removing one name does not necessarily remove the data.
- Hard links usually cannot cross filesystem boundaries.
- Directory hard links are normally restricted.

## Symbolic Links

Create a symbolic link with:

    ln -s original.txt symbolic_link.txt

A symbolic link stores a path reference.

Characteristics include:

- Can cross filesystem boundaries.
- Can point to directories.
- Can become broken.
- Has its own filesystem entry.

The distinction between hard and symbolic links is important when managing deployments, shared files, configuration paths, and storage.

---

# 15. Standard Streams

Processes commonly interact using three streams.

## Standard Input

Also called:

    stdin

Common file descriptor:

    0

## Standard Output

Also called:

    stdout

Common file descriptor:

    1

## Standard Error

Also called:

    stderr

Common file descriptor:

    2

Separating standard output from standard error allows programs and scripts to process normal results separately from diagnostics.

---

# 16. Redirection

## Output Redirection

Overwrite a file:

    command > output.txt

Append to a file:

    command >> output.txt

## Error Redirection

Redirect standard error:

    command 2> errors.txt

Redirect output and errors together:

    command > output.txt 2>&1

Redirection is useful for:

- Logging
- Automation
- Data processing
- Batch jobs
- Debugging

Care is required because `>` can overwrite an existing file.

---

# 17. Pipes

A pipe connects the output of one process to the input of another.

Syntax:

    command1 | command2

Example:

    ls -l | grep ".txt"

The conceptual flow is:

    Producer -> Filter -> Transformer -> Consumer

Pipelines are a major design principle of Unix-like systems because small utilities can be combined into larger workflows.

---

# 18. Environment Variables

Environment variables store configuration associated with processes.

Common variables include:

- `HOME`
- `PATH`
- `USER`
- `SHELL`
- `PWD`

Examples:

    echo $HOME

    echo $PATH

Temporary assignment:

    MODE=production command

Exporting:

    export MODE=production

Environment variables are inherited by child processes.

They should not automatically be considered secure secret storage.

Potential exposure mechanisms include:

- Logs
- Process inspection
- Debugging output
- Monitoring systems
- Crash reports

---

# 19. The PATH Variable

`PATH` is a list of directories searched when a command name is entered without an explicit path.

For example:

    python3

may cause the shell to search directories listed in `PATH`.

An explicit executable path bypasses the normal command lookup process:

    /usr/bin/python3

A security risk occurs when untrusted directories appear early in `PATH`. A malicious or unintended executable could be executed before the expected system program.

---

# 20. Archives and Compression

Archiving and compression are different operations.

## Archive

Combines multiple files into one archive.

## Compression

Reduces data size.

The `tar` utility is commonly used for archives.

Create an archive:

    tar -cf archive.tar directory

List contents:

    tar -tf archive.tar

Extract:

    tar -xf archive.tar

Create a gzip-compressed archive:

    tar -czf archive.tar.gz directory

Extract:

    tar -xzf archive.tar.gz

Common archive formats include:

- `.tar`
- `.tar.gz`
- `.tgz`
- `.tar.bz2`
- `.tar.xz`
- `.zip`

Untrusted archives should be handled carefully because extraction can create security and operational risks such as path traversal or excessive disk consumption.

---

# 21. Disk Usage

Two important commands are:

    df -h

and:

    du -sh directory

They answer different questions.

## `df`

Reports usage of mounted filesystems.

## `du`

Reports storage usage associated with files and directories.

Large recursive directory scans can be expensive.

Disk monitoring should account for:

- Free space
- Filesystem capacity
- Temporary files
- Log growth
- Deleted but still-open files
- Application caches

---

# 22. Processes

A process is an executing program.

Important terms include:

## PID

Process identifier.

## PPID

Parent process identifier.

## Foreground Process

Associated with the active terminal.

## Background Process

Runs independently of immediate interactive shell use.

Common commands include:

    ps

    ps aux

    top

---

# 23. Process Signals

Signals are operating system mechanisms used to notify processes.

Examples:

    kill PID

Often sends a default termination signal.

Graceful termination:

    kill -TERM PID

Forced termination:

    kill -KILL PID

`SIGTERM` allows a process to perform cleanup.

`SIGKILL` cannot be handled or ignored by the target process and should generally be used only when graceful termination is unsuccessful or inappropriate.

---

# 24. File Descriptors

Unix-like systems commonly represent open resources using file descriptors.

Examples of resources include:

- Files
- Pipes
- Sockets
- Devices

The three standard streams are commonly associated with:

    0 -> stdin
    1 -> stdout
    2 -> stderr

Programs should release resources when they are no longer required.

Python context managers provide a reliable pattern:

    with open("file.txt") as file:
        data = file.read()

The file is closed automatically when the block exits.

---

# 25. Users and Privileges

Linux systems distinguish between ordinary users and privileged accounts.

The root account generally has extensive administrative access.

Administrative operations may be performed using:

    sudo command

The principle of least privilege should be followed.

A process should receive only the permissions required for its intended task.

Important practices include:

- Avoid unnecessary root access.
- Review privileged commands before execution.
- Restrict administrative permissions.
- Protect sensitive files.
- Avoid running ordinary development tools as root.

---

# 26. Shell Scripting

A shell script is a text file containing commands interpreted by a shell.

A typical Bash script begins with:

    #!/usr/bin/env bash

This is called a **shebang**.

Variables can be assigned:

    name="student"

Referenced:

    echo "$name"

Command substitution:

    current_date=$(date)

Conditional execution:

    if [ -f "file.txt" ]; then
        echo "File exists"
    fi

Loops can process multiple files:

    for item in *.txt; do
        echo "$item"
    done

---

# 27. Quoting and Shell Safety

Quoting is important because shell expansion can change the meaning of data.

Suppose a variable contains:

    my file.txt

Using:

    rm $filename

may cause word splitting.

Using:

    rm -- "$filename"

is safer for many ordinary filename operations.

The `--` convention often indicates the end of command options.

This is particularly important for filenames beginning with:

    -

Without protection, such a filename may be interpreted as an option.

---

# 28. Command Exit Status

Commands usually return an exit status.

Conventionally:

    0

means success.

Non-zero values generally indicate failure or another special condition.

The shell can display the most recent status:

    echo $?

Reliable automation should check command results instead of assuming that every command succeeds.

Failure can occur because of:

- Missing files
- Permission errors
- Invalid input
- Full disks
- Network failures
- Resource exhaustion
- Interrupted processes

---

# 29. Filesystem Edge Cases

## Filenames with Spaces

Example:

    my file.txt

Commands should quote such names:

    cat "my file.txt"

## Filenames Beginning with a Dash

Example:

    -file.txt

Use:

    rm -- -file.txt

## Broken Symbolic Links

A symbolic link may remain after its target is removed.

The link exists, but its target cannot be accessed.

## Case Sensitivity

Linux filesystems are commonly case-sensitive.

These may be different files:

    File.txt
    file.txt

## Relative Path Dependence

A relative path can refer to different locations depending on the current working directory.

## Deleted Open Files

On Unix-like systems, removing a directory entry does not always immediately eliminate data when a process still holds the file open.

This behavior can affect disk usage investigations.

---

# 30. Path Traversal

Path traversal is a security problem caused by unsafe handling of filesystem paths.

Suppose an application stores uploads inside:

    /safe/uploads

If untrusted input contains:

    ../../sensitive_file

a naive path construction approach may allow access outside the intended directory.

A safer approach is:

1. Resolve the trusted base directory.
2. Resolve the candidate path.
3. Verify that the candidate remains inside the trusted base.

The Python script demonstrates this using `Path.resolve()` and `relative_to()`.

Path validation is important in:

- File upload systems
- Web applications
- Backup systems
- Package extractors
- Document management systems

---

# 31. Performance Considerations

Filesystem performance depends on:

- Storage hardware
- Filesystem type
- File sizes
- Number of files
- Metadata operations
- Caching
- Network latency
- Concurrent access

One large file and millions of small files can have very different performance characteristics.

Potentially expensive operations include:

- Recursive directory scans
- Repeated metadata lookups
- Loading large files entirely into memory
- Searching very broad filesystem trees

Efficient programs should:

- Limit search scope.
- Stream large data.
- Avoid unnecessary repeated scans.
- Use appropriate buffering.
- Handle concurrent filesystem changes.

---

# 32. Debugging Filesystem Problems

Useful diagnostic questions include:

## Where am I?

    pwd

## Does the file exist?

    ls

or:

    find

## What are the permissions?

    ls -l

## Which user is running the command?

    whoami

or:

    id

## Which executable is being used?

    which command

or:

    command -v command

## What was the command exit status?

    echo $?

## Is the filesystem full?

    df -h

## Is the process running?

    ps

or:

    top

Systematic debugging begins by verifying assumptions rather than modifying commands repeatedly without understanding the failure.

---

# 33. Production File Operations

Production applications should assume filesystem operations can fail.

Important considerations include:

- Permission changes
- Disk exhaustion
- Concurrent access
- Interrupted writes
- Invalid paths
- Filesystem corruption
- Unexpected symbolic links
- Temporary storage failures

## Atomic-Style Replacement

A common pattern is:

1. Write data to a temporary file.
2. Verify the write.
3. Replace the original file.

Python can use:

    os.replace()

for replacement behavior appropriate to many local filesystem situations.

The precise guarantees depend on filesystem and operating system conditions.

---

# 34. Common Mistakes

## Using Relative Paths Without Understanding the Working Directory

A script may work interactively but fail when executed by another process.

## Running Recursive Deletion Without Verification

Commands such as recursive `rm` can cause permanent data loss.

## Forgetting to Quote Variables

Unquoted shell variables may undergo word splitting and wildcard expansion.

## Assuming All Filesystems Behave Identically

Different filesystems can differ in behavior, features, performance, case sensitivity, and metadata support.

## Using Root Unnecessarily

Running programs with excessive privileges increases security risk.

## Treating `SIGKILL` as the Normal Termination Method

Graceful termination is usually preferable.

## Assuming Permissions Are the Only Access Control Mechanism

Other controls may include:

- Access control lists
- Mandatory access control
- Mount options
- Application-level authorization
- Capabilities

## Trusting User-Supplied Paths

Untrusted path input can create path traversal vulnerabilities.

---

# 35. Important Comparisons

## Absolute Path vs Relative Path

| Absolute Path | Relative Path |
|---|---|
| Begins from `/` | Begins from the current directory |
| Independent of working directory | Depends on working directory |
| Explicit location | Context-dependent location |

## File vs Directory

| File | Directory |
|---|---|
| Stores ordinary data | Organizes filesystem entries |
| Can contain text or binary data | Contains references to files and directories |

## Hard Link vs Symbolic Link

| Hard Link | Symbolic Link |
|---|---|
| References underlying file data | References a path |
| Usually cannot cross filesystems | Can cross filesystems |
| Removing one name may leave data available | Can become broken when target disappears |

## `cp` vs `mv`

| `cp` | `mv` |
|---|---|
| Creates a copy | Moves or renames |
| Original generally remains | Original path may disappear after movement |

## `>` vs `>>`

| `>` | `>>` |
|---|---|
| Overwrites output destination | Appends output |
| Can replace existing content | Preserves existing content and adds new data |

## Standard Output vs Standard Error

| stdout | stderr |
|---|---|
| Normal program output | Diagnostics and errors |
| File descriptor 1 | File descriptor 2 |

---

# 36. Practical Applications

Linux filesystem knowledge is directly relevant to:

- Software development
- Server administration
- Cloud computing
- DevOps
- Containers
- Cybersecurity
- Data engineering
- System automation
- Backend development
- Scientific computing

Typical tasks include:

- Creating project directories
- Managing configuration files
- Inspecting logs
- Searching source code
- Managing permissions
- Automating shell commands
- Monitoring disk usage
- Managing processes
- Creating archives
- Debugging deployments

---

# 37. Core Principles

The most important principles demonstrated by the script are:

1. Linux organizes storage into a single hierarchical filesystem.
2. Every process has a current working directory.
3. Absolute and relative paths have different behavior.
4. Directories and files are distinct filesystem object types.
5. Permissions are evaluated according to user, group, and others.
6. Directory permissions have different implications from file permissions.
7. Ownership and groups are important access-control mechanisms.
8. Shell expansion can change command arguments before a command executes.
9. Quoting protects data from unintended shell interpretation.
10. Standard input, output, and error enable composition between programs.
11. Pipes connect command output to another command's input.
12. Environment variables influence process behavior.
13. `PATH` determines where command names are searched.
14. Filesystem operations can fail and should be validated.
15. User-controlled paths require security validation.
16. Production filesystem operations require attention to concurrency, durability, permissions, and error handling.
17. Recursive commands should be scoped carefully.
18. Linux command-line work depends heavily on understanding the current execution context.

The accompanying Python script demonstrates these principles using safe temporary directories, standard library modules, path validation, file operations, permission inspection, process information, and progressively structured examples.
