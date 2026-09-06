#!/usr/bin/env python3
"""
Linux Commands Study Script
============================

Topic:
    ls, cd, pwd, cp, mv, rm, mkdir, cat, less, head, tail

Purpose:
    A self-contained practical study guide for learning essential Linux
    filesystem commands from absolute beginner through advanced usage.

Important:
    This Python program teaches Linux commands by explaining them and by
    optionally executing safe demonstrations inside a temporary directory.

Requirements:
    Python 3.8+
    Linux, macOS, WSL, or another Unix-like environment.

Safety:
    Demonstrations run inside a temporary directory created by Python.
    Destructive commands such as rm are demonstrated through Python's
    subprocess interface only inside that controlled directory.
"""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from textwrap import dedent


# ============================================================================
# 1. BASIC OUTPUT HELPERS
# ============================================================================

def section(title: str) -> None:
    """Print a visually distinct section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def subsection(title: str) -> None:
    """Print a subsection heading."""
    print("\n" + "-" * 78)
    print(title)
    print("-" * 78)


def explain(text: str) -> None:
    """Print educational text with consistent indentation."""
    print(dedent(text).strip())


def run_command(
    command: list[str],
    cwd: Path | None = None,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    """
    Execute a command and display its command line, stdout, and stderr.

    list[str] is intentionally used instead of shell=True. This avoids shell
    parsing surprises and is safer when paths contain spaces or shell
    metacharacters.
    """
    print(f"\n$ {' '.join(command)}")

    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        text=True,
        capture_output=True,
        check=check,
    )

    if result.stdout:
        print(result.stdout.rstrip())

    if result.stderr:
        print(f"[stderr] {result.stderr.rstrip()}")

    print(f"[exit status] {result.returncode}")
    return result


def show_python_environment() -> None:
    """Display information about the environment running the tutorial."""
    section("ENVIRONMENT INFORMATION")

    print(f"Operating system : {platform.system()}")
    print(f"Platform         : {platform.platform()}")
    print(f"Python version   : {platform.python_version()}")
    print(f"Current user     : {os.environ.get('USER') or os.environ.get('USERNAME', 'unknown')}")
    print(f"Home directory   : {Path.home()}")
    print(f"Current directory: {Path.cwd()}")

    if platform.system() == "Windows":
        explain(
            """
            This tutorial is designed for Linux and Unix-like systems.
            On Windows, use WSL or another Linux environment for the command
            demonstrations. The Python explanations remain useful regardless
            of the host operating system.
            """
        )


# ============================================================================
# 2. LINUX FILESYSTEM FUNDAMENTALS
# ============================================================================

def teach_filesystem_fundamentals() -> None:
    section("1. LINUX FILESYSTEM FUNDAMENTALS")

    explain(
        """
        Linux treats almost everything as a file or as something exposed
        through a file-like interface.

        A filesystem organizes files and directories into a hierarchy.

        The root directory is written as:

            /

        Examples of common locations include:

            /home
            /etc
            /var
            /tmp
            /usr
            /bin

        A user's home directory is commonly:

            /home/username

        The tilde character is a shell abbreviation for the current user's
        home directory:

            ~

        A path can be absolute or relative.

        Absolute path:
            /home/alex/documents/report.txt

        Relative path:
            documents/report.txt

        The special path components are:

            .       current directory
            ..      parent directory
            ~       current user's home directory
            /       root directory or path separator

        Examples:

            ./notes.txt
            ../images
            ~/Documents
            /var/log

        Linux filenames are case-sensitive. These are different names:

            report.txt
            Report.txt
            REPORT.TXT

        Spaces are valid in filenames, but they require quoting or escaping
        when typed directly in a shell:

            cat "my report.txt"
            cat my\\ report.txt
        """
    )


# ============================================================================
# 3. COMMAND STRUCTURE
# ============================================================================

def teach_command_structure() -> None:
    section("2. COMMAND STRUCTURE AND SHELL BASICS")

    explain(
        """
        A Linux command is normally entered into a shell such as Bash.

        A useful conceptual structure is:

            command [options] [arguments]

        Example:

            ls -lah /var/log

        Here:

            ls          command
            -lah        options
            /var/log    argument

        Options can often be combined:

            ls -l -a -h

        is commonly equivalent to:

            ls -lah

        Long options frequently use two hyphens:

            ls --all
            ls --human-readable

        The shell also expands special syntax before a program receives its
        arguments. Important examples include:

            *       wildcard matching
            ?       one-character wildcard
            ~       home directory expansion
            $VAR    environment-variable expansion

        Quoting matters.

            rm *.log

        may expand to many filenames before rm is executed.

            rm "*.log"

        normally refers to a literal filename containing the characters
        *.log, if such a filename exists.

        The command:

            command --help

        commonly provides command-specific usage information.

        The command:

            man command

        opens the manual page when the system has manual pages installed.
        """
    )

    if shutil.which("bash"):
        subsection("Bash Availability")
        print(f"Bash executable: {shutil.which('bash')}")
    else:
        print("Bash was not detected in PATH.")


# ============================================================================
# 4. PWD
# ============================================================================

def teach_pwd() -> None:
    section("3. pwd")

    explain(
        """
        pwd means "print working directory."

        It tells you which directory the current shell process considers its
        working directory.

        Basic syntax:

            pwd

        Common form:

            pwd -P

        The -P option asks for the physical path, resolving symbolic links
        where applicable.

        The logical and physical paths can differ when symbolic links are
        involved.

        Example:

            $ pwd
            /home/user/projects

        Why pwd matters:

        - It prevents confusion about your current location.
        - Relative paths are interpreted from the current directory.
        - It is useful before destructive commands.
        - Scripts often need an explicit understanding of their working
          directory.

        Important distinction:

            pwd

        reports the shell's current working directory. It does not list the
        contents of that directory.
        """
    )

    run_command(["pwd"])


# ============================================================================
# 5. LS
# ============================================================================

def teach_ls() -> None:
    section("4. ls")

    explain(
        """
        ls means "list."

        It displays directory contents.

        Basic syntax:

            ls [options] [path]

        Basic example:

            ls

        List another directory:

            ls /etc

        Long format:

            ls -l

        Hidden files:

            ls -a

        Human-readable sizes:

            ls -h

        These are frequently combined:

            ls -lah

        A typical long-format entry resembles:

            -rw-r--r-- 1 user group 2048 Sep  6 10:30 report.txt

        The first character identifies the file type. Common values include:

            -       regular file
            d       directory
            l       symbolic link

        The remaining permission characters describe read, write, and execute
        permissions for the owner, group, and others.

        Useful forms:

            ls -l        detailed listing
            ls -a        include hidden entries
            ls -A        include hidden entries except . and ..
            ls -h        human-readable sizes
            ls -R        recursive listing
            ls -t        sort by modification time
            ls -S        sort by size
            ls -r        reverse sorting
            ls -d        list directory entries themselves rather than contents

        A common practical command is:

            ls -lah

        which combines detailed output, hidden entries, and readable sizes.

        Important:
        ls does not recursively inspect all subdirectories unless -R is used.
        """
    )

    subsection("Executable Examples")

    run_command(["ls"])
    run_command(["ls", "-l"])
    run_command(["ls", "-la"])
    run_command(["ls", "-lah"])


# ============================================================================
# 6. CD
# ============================================================================

def teach_cd() -> None:
    section("5. cd")

    explain(
        """
        cd means "change directory."

        Basic syntax:

            cd DIRECTORY

        Examples:

            cd /tmp
            cd ..
            cd .
            cd ~
            cd /var/log

        Return to the previous directory:

            cd -

        Go to the home directory:

            cd

        or:

            cd ~

        The cd command is normally a shell builtin rather than an independent
        executable.

        This is important because changing the working directory must modify
        the state of the current shell. An external child process cannot
        permanently change its parent's working directory.

        Relative navigation:

            cd project
            cd ../images
            cd ./src

        Absolute navigation:

            cd /home/user/project/src

        A common beginner workflow is:

            pwd
            ls
            cd directory
            pwd

        This makes your location explicit before continuing.
        """
    )

    print(f"Current Python process directory: {Path.cwd()}")


# ============================================================================
# 7. MKDIR
# ============================================================================

def teach_mkdir() -> None:
    section("6. mkdir")

    explain(
        """
        mkdir means "make directory."

        Basic syntax:

            mkdir DIRECTORY

        Example:

            mkdir projects

        Multiple directories can be created:

            mkdir src tests docs

        Parent directories can be created automatically with -p:

            mkdir -p project/src/python

        Without -p, creating a directory whose parent does not exist fails.

        Useful option:

            mkdir -p path/to/deep/directory

        The -p option also avoids failure when the requested directory already
        exists in the usual case.

        Permissions can be requested at creation time:

            mkdir -m 755 public

        The final permission bits can still be affected by the process umask.
        """
    )


# ============================================================================
# 8. CP
# ============================================================================

def teach_cp() -> None:
    section("7. cp")

    explain(
        """
        cp means "copy."

        Basic syntax:

            cp SOURCE DESTINATION

        Copy a file:

            cp report.txt backup.txt

        Copy a file into a directory:

            cp report.txt backups/

        Copy multiple files into a directory:

            cp a.txt b.txt backups/

        Recursive directory copying:

            cp -r source_directory destination_directory

        Archive-style copying:

            cp -a source destination

        The -a option is commonly used when preserving as much metadata as
        possible and recursively copying directories.

        Interactive mode:

            cp -i source destination

        This can ask before overwriting.

        No-clobber mode:

            cp -n source destination

        Behavior and option availability can vary between implementations,
        so consult the local manual page when portability matters.

        Common mistake:

            cp directory destination

        may fail because directories generally require recursive copying:

            cp -r directory destination

        Another important issue is whether the destination already exists.
        If the destination is an existing directory, cp usually places the
        source inside it.
        """
    )


# ============================================================================
# 9. MV
# ============================================================================

def teach_mv() -> None:
    section("8. mv")

    explain(
        """
        mv means "move."

        It is also commonly used to rename files and directories.

        Rename a file:

            mv old.txt new.txt

        Move a file:

            mv report.txt documents/

        Move and rename simultaneously:

            mv report.txt documents/final-report.txt

        Move a directory:

            mv project archive/

        Unlike cp, mv normally does not create a second copy.

        Within the same filesystem, moving a file is generally implemented
        using a filesystem rename operation and can therefore be very fast
        even for large files.

        Moving across filesystems can require a copy followed by deletion,
        depending on the implementation and circumstances.

        Interactive mode:

            mv -i source destination

        No-clobber behavior:

            mv -n source destination

        Force option:

            mv -f source destination

        Be careful with -f because it can remove an existing destination
        before replacing it when permitted.
        """
    )


# ============================================================================
# 10. RM
# ============================================================================

def teach_rm() -> None:
    section("9. rm")

    explain(
        """
        rm means "remove."

        Basic syntax:

            rm FILE

        Example:

            rm old.txt

        Remove several files:

            rm a.txt b.txt c.txt

        Interactive mode:

            rm -i file.txt

        Recursive removal:

            rm -r directory

        Force removal:

            rm -f file.txt

        A common destructive command is:

            rm -rf directory

        This recursively removes a directory and suppresses many prompts and
        errors.

        It is extremely dangerous when used with an incorrect path.

        Recommended safety habits:

        1. Use pwd before destructive operations.
        2. Use ls to inspect the target.
        3. Quote paths containing spaces.
        4. Prefer rm -i when learning.
        5. Avoid blindly using rm -rf.
        6. Do not run destructive commands with elevated privileges unless
           genuinely necessary.
        7. Check shell expansions such as * before pressing Enter.

        Linux normally does not provide a universal undelete mechanism for
        rm. Removing a directory entry can make data difficult or impossible
        to recover.

        rm removes directory entries. It is not the same as securely erasing
        every physical trace of data from storage.
        """
    )


# ============================================================================
# 11. CAT
# ============================================================================

def teach_cat() -> None:
    section("10. cat")

    explain(
        """
        cat means "concatenate."

        It reads files and writes their contents to standard output.

        Display a file:

            cat file.txt

        Display multiple files:

            cat first.txt second.txt

        Concatenate files into another file:

            cat first.txt second.txt > combined.txt

        Number lines:

            cat -n file.txt

        Show non-printing characters:

            cat -A file.txt

        cat is excellent for short files.

        It is usually a poor choice for enormous files because it can send the
        entire file to the terminal at once.

        A subtle distinction:

            cat file.txt

        displays the contents.

            cat > file.txt

        reads from standard input and writes the resulting data to the file,
        replacing its previous contents in typical shell usage.

        Redirection operators such as > and >> belong to the shell, not to
        cat itself.

            >       overwrite/create output file
            >>      append to output file
            <       redirect input from a file
        """
    )


# ============================================================================
# 12. LESS
# ============================================================================

def teach_less() -> None:
    section("11. less")

    explain(
        """
        less is a terminal pager.

        It allows large text output to be viewed interactively instead of
        printing everything at once.

        Examples:

            less large.log
            ls -lah /var/log | less
            cat large.log | less

        Useful navigation keys inside less commonly include:

            Space       next page
            b           previous page
            Enter       next line
            q           quit
            /pattern    search forward
            ?pattern    search backward
            n           next search result
            N           previous search result
            g           beginning
            G           end

        less is especially useful for:

            man ls
            large log files
            long configuration files
            large command output

        A major conceptual distinction:

            cat      sends the content directly to stdout
            less     provides interactive paging
        """
    )

    if shutil.which("less"):
        print(f"less executable: {shutil.which('less')}")
    else:
        print("less was not detected in PATH. The command may not be installed.")


# ============================================================================
# 13. HEAD
# ============================================================================

def teach_head() -> None:
    section("12. head")

    explain(
        """
        head displays the beginning of a file or input stream.

        Basic usage:

            head file.txt

        By default, many common implementations display the first 10 lines.

        Select a number of lines:

            head -n 5 file.txt

        Some implementations support:

            head -5 file.txt

        but -n is clearer and more portable.

        Display the first N bytes:

            head -c 100 file.txt

        head is useful for quickly inspecting:

            CSV headers
            log-file beginnings
            configuration files
            generated text
            large datasets

        It avoids reading the entire visible output into the terminal.
        """
    )


# ============================================================================
# 14. TAIL
# ============================================================================

def teach_tail() -> None:
    section("13. tail")

    explain(
        """
        tail displays the end of a file or input stream.

        Basic usage:

            tail file.txt

        Select the number of lines:

            tail -n 20 file.txt

        Select bytes:

            tail -c 100 file.txt

        Follow a growing file:

            tail -f application.log

        tail -f is particularly useful for monitoring logs.

        A common production workflow is:

            tail -f /var/log/some-service.log

        The process continues waiting for new data until interrupted, usually
        with Ctrl+C.

        Some implementations provide additional follow behavior such as:

            tail -F file.log

        which is designed to continue following a file across certain log
        rotation scenarios. Exact behavior depends on the implementation.
        """
    )


# ============================================================================
# 15. CONTROLLED PRACTICAL LAB
# ============================================================================

def create_demo_environment(base: Path) -> None:
    """
    Create a safe filesystem tree for demonstrations.

    The structure intentionally resembles a small project.
    """
    directories = [
        base / "project",
        base / "project" / "docs",
        base / "project" / "src",
        base / "project" / "logs",
        base / "backup",
        base / "empty-directory",
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    files = {
        base / "project" / "README.txt": (
            "Linux command practice project\n"
            "This file is used by the tutorial.\n"
            "It contains several lines.\n"
            "The commands ls, cp, mv, rm, cat, head, and tail can inspect it.\n"
        ),
        base / "project" / "docs" / "notes.txt": (
            "Line 1: Filesystem basics\n"
            "Line 2: Absolute and relative paths\n"
            "Line 3: Directory navigation\n"
            "Line 4: File copying\n"
            "Line 5: File moving\n"
            "Line 6: File deletion\n"
            "Line 7: Text inspection\n"
            "Line 8: Logs\n"
            "Line 9: Permissions\n"
            "Line 10: Production safety\n"
            "Line 11: Edge cases\n"
            "Line 12: Automation\n"
        ),
        base / "project" / "logs" / "application.log": (
            "2026-09-06 INFO Application started\n"
            "2026-09-06 INFO Configuration loaded\n"
            "2026-09-06 INFO Database connection established\n"
            "2026-09-06 WARNING Cache miss\n"
            "2026-09-06 INFO Request processed\n"
            "2026-09-06 INFO Worker started\n"
            "2026-09-06 ERROR Example controlled error\n"
            "2026-09-06 INFO Recovery completed\n"
        ),
        base / "project" / "src" / "main.py": (
            "def main():\n"
            "    print('Hello from the demonstration project')\n"
            "\n"
            "if __name__ == '__main__':\n"
            "    main()\n"
        ),
        base / "project" / ".hidden-config": "Hidden configuration example\n",
    }

    for path, content in files.items():
        path.write_text(content, encoding="utf-8")


def demonstrate_ls(base: Path) -> None:
    subsection("LAB: ls")

    run_command(["ls"], cwd=base)
    run_command(["ls", "-la"], cwd=base)
    run_command(["ls", "-lah", "project"], cwd=base)
    run_command(["ls", "-l", "project/docs"], cwd=base)


def demonstrate_pwd_and_cd(base: Path) -> None:
    subsection("LAB: pwd and cd")

    run_command(["pwd"], cwd=base)
    run_command(["pwd"], cwd=base / "project")
    run_command(["pwd"], cwd=base / "project" / "docs")

    explain(
        """
        Python's subprocess cwd parameter lets this demonstration execute each
        command in a selected directory without changing the parent Python
        process's own working directory.

        In an interactive Bash shell, the equivalent operations are:

            pwd
            cd project
            pwd
            cd docs
            pwd
            cd ..
            pwd
        """
    )


def demonstrate_mkdir(base: Path) -> None:
    subsection("LAB: mkdir")

    run_command(["mkdir", "new-directory"], cwd=base)
    run_command(["mkdir", "-p", "nested/one/two"], cwd=base)
    run_command(["ls", "-la"], cwd=base)


def demonstrate_cp(base: Path) -> None:
    subsection("LAB: cp")

    source = base / "project" / "README.txt"
    destination = base / "backup" / "README-copy.txt"

    run_command(["cp", str(source), str(destination)])
    run_command(["ls", "-lah", "backup"], cwd=base)

    run_command(
        ["cp", "-r", str(base / "project" / "docs"), str(base / "backup" / "docs-copy")],
        cwd=base,
    )

    run_command(["find", "backup", "-maxdepth", "3", "-type", "f"], cwd=base)


def demonstrate_mv(base: Path) -> None:
    subsection("LAB: mv")

    source = base / "backup" / "README-copy.txt"
    renamed = base / "backup" / "README-renamed.txt"

    run_command(["mv", str(source), str(renamed)])
    run_command(["ls", "-lah", "backup"], cwd=base)

    move_source = base / "backup" / "README-renamed.txt"
    move_destination = base / "project" / "docs" / "README-moved.txt"

    run_command(["mv", str(move_source), str(move_destination)])
    run_command(["ls", "-lah", "project/docs"], cwd=base)


def demonstrate_cat_less_head_tail(base: Path) -> None:
    subsection("LAB: cat")

    run_command(["cat", "project/README.txt"], cwd=base)
    run_command(["cat", "-n", "project/docs/notes.txt"], cwd=base)

    subsection("LAB: head")

    run_command(["head", "-n", "4", "project/docs/notes.txt"], cwd=base)
    run_command(["head", "-c", "40", "project/docs/notes.txt"], cwd=base)

    subsection("LAB: tail")

    run_command(["tail", "-n", "4", "project/docs/notes.txt"], cwd=base)
    run_command(["tail", "-c", "50", "project/docs/notes.txt"], cwd=base)

    subsection("LAB: less")

    if shutil.which("less"):
        explain(
            """
            An interactive pager is deliberately not launched automatically
            because this program should not block waiting for keyboard input.

            The equivalent command is:

                less project/docs/notes.txt
            """
        )
    else:
        print("less is unavailable in this environment.")


def demonstrate_rm(base: Path) -> None:
    subsection("LAB: rm")

    removable_file = base / "project" / "temporary.txt"
    removable_file.write_text("Temporary demonstration file\n", encoding="utf-8")

    run_command(["ls", "-l", "project"], cwd=base)
    run_command(["rm", str(removable_file)], cwd=base)
    run_command(["ls", "-l", "project"], cwd=base)

    removable_directory = base / "remove-me"
    removable_directory.mkdir()
    (removable_directory / "file.txt").write_text(
        "This directory is intentionally disposable.\n",
        encoding="utf-8",
    )

    run_command(["rm", "-r", str(removable_directory)], cwd=base)
    run_command(["ls", "-la"], cwd=base)


def run_controlled_lab() -> None:
    section("14. CONTROLLED PRACTICAL LAB")

    explain(
        """
        The following exercises use Python's TemporaryDirectory.

        Nothing is intentionally created in your normal home directory.
        The temporary directory is automatically removed when this function
        finishes.

        The examples demonstrate real Linux commands rather than merely
        printing command names.
        """
    )

    with tempfile.TemporaryDirectory(prefix="linux_commands_lab_") as temporary_directory:
        base = Path(temporary_directory)

        print(f"Temporary lab directory: {base}")

        create_demo_environment(base)

        demonstrate_ls(base)
        demonstrate_pwd_and_cd(base)
        demonstrate_mkdir(base)
        demonstrate_cp(base)
        demonstrate_mv(base)
        demonstrate_cat_less_head_tail(base)
        demonstrate_rm(base)

        subsection("Final lab state")
        run_command(["find", ".", "-maxdepth", "4", "-print"], cwd=base)


# ============================================================================
# 16. COMMAND COMPARISONS
# ============================================================================

def teach_command_comparisons() -> None:
    section("15. IMPORTANT COMMAND DISTINCTIONS")

    comparisons = [
        ("pwd", "Reports the current working directory.", "pwd"),
        ("ls", "Lists directory entries.", "ls -lah"),
        ("cd", "Changes the shell's working directory.", "cd /var/log"),
        ("mkdir", "Creates directories.", "mkdir -p project/src"),
        ("cp", "Copies files or directories.", "cp -r source backup"),
        ("mv", "Moves or renames files/directories.", "mv old.txt new.txt"),
        ("rm", "Removes directory entries.", "rm file.txt"),
        ("cat", "Writes file contents to standard output.", "cat file.txt"),
        ("less", "Provides interactive paging.", "less large.log"),
        ("head", "Shows the beginning of input.", "head -n 10 file.txt"),
        ("tail", "Shows the end of input.", "tail -n 10 file.txt"),
    ]

    print(f"{'Command':<10} {'Primary purpose':<48} Example")
    print("-" * 100)

    for command, purpose, example in comparisons:
        print(f"{command:<10} {purpose:<48} {example}")


# ============================================================================
# 17. PATH EDGE CASES
# ============================================================================

def teach_path_edge_cases() -> None:
    section("16. PATHS, SPACES, HIDDEN FILES, AND EDGE CASES")

    explain(
        """
        Paths are one of the most important sources of command-line mistakes.

        1. Spaces

        A path such as:

            My Documents/report.txt

        contains a space. Quote it:

            cat "My Documents/report.txt"

        or escape the space:

            cat My\\ Documents/report.txt

        2. Hidden files

        In Linux, filenames beginning with . are normally hidden from ordinary
        ls output.

            ls

        may not show:

            .config
            .env
            .gitignore

        Use:

            ls -la

        to include them.

        3. Relative paths

            ./file.txt

        explicitly means a file in the current directory.

            ../file.txt

        refers to a file in the parent directory.

        4. Absolute paths

            /tmp/example.txt

        do not depend on the current working directory.

        5. Root versus home

            /

        is the root of the filesystem hierarchy.

            ~

        refers to the current user's home directory.

        They are not interchangeable.

        6. Trailing slash

        A path such as:

            project/

        explicitly presents the path as a directory in many command contexts.

        7. Symbolic links

        A symbolic link points to another filesystem object. Commands such as
        ls can display link information, and pwd can show logical or physical
        paths depending on options and shell behavior.
        """
    )


# ============================================================================
# 18. WILDCARDS AND EXPANSION
# ============================================================================

def teach_wildcards() -> None:
    section("17. WILDCARDS AND SHELL EXPANSION")

    explain(
        """
        Wildcards are usually expanded by the shell before the command runs.

        Common patterns:

            *       matches zero or more characters
            ?       matches one character
            [abc]   matches one character from a set
            [0-9]   matches one character in a range

        Examples:

            ls *.txt
            ls report?.txt
            ls [abc].txt

        Suppose a directory contains:

            a.txt
            b.txt
            notes.txt
            image.png

        Then:

            ls *.txt

        can become conceptually:

            ls a.txt b.txt notes.txt

        This has an important safety consequence.

        A command such as:

            rm *.log

        can remove multiple files.

        If no files match, behavior depends on the shell configuration. Bash
        commonly leaves an unmatched pattern unchanged unless options such as
        nullglob are enabled.

        Quoting prevents ordinary wildcard expansion:

            ls "*.txt"

        This usually searches for a literal filename named *.txt.

        Always inspect expansions before using destructive commands.
        """
    )


# ============================================================================
# 19. STANDARD INPUT AND OUTPUT
# ============================================================================

def teach_streams_and_redirection() -> None:
    section("18. STANDARD INPUT, OUTPUT, AND REDIRECTION")

    explain(
        """
        Unix command-line programs commonly use three standard streams:

            stdin    file descriptor 0
            stdout   file descriptor 1
            stderr   file descriptor 2

        stdout is normal output.

        stderr is commonly used for diagnostic and error messages.

        Shell redirection can connect these streams to files.

        Examples:

            command > output.txt

        Overwrites or creates output.txt.

            command >> output.txt

        Appends to output.txt.

            command 2> errors.txt

        Redirects standard error.

            command > output.txt 2> errors.txt

        Separates normal output and errors.

            command > all.txt 2>&1

        Sends stderr to the same destination as stdout in common POSIX shells.

        A pipe:

            command1 | command2

        connects stdout from command1 to stdin of command2.

        Examples relevant to this topic:

            ls -lah | less
            cat application.log | head -n 5
            cat application.log | tail -n 5

        cat is not required in many pipelines because commands can often read
        files directly:

            head -n 5 application.log

        is simpler than:

            cat application.log | head -n 5

        This is commonly described as avoiding a useless use of cat.
        """
    )


# ============================================================================
# 20. FILE OPERATIONS AND METADATA
# ============================================================================

def teach_metadata() -> None:
    section("19. FILE METADATA AND ls -l")

    explain(
        """
        A long ls listing can expose important filesystem metadata.

        Example conceptual output:

            -rw-r--r-- 1 alice developers 2048 Sep  6 10:30 report.txt

        Components include:

            file type and permissions
            link count
            owner
            group
            size
            modification timestamp
            filename

        Permission notation uses three primary groups:

            owner
            group
            others

        Each group has:

            r       read
            w       write
            x       execute

        Example:

            rwxr-xr--

        can be interpreted as:

            owner:  rwx
            group:  r-x
            others: r--

        For directories, execute permission has a special meaning: it allows
        traversal/search through the directory when combined with appropriate
        permissions.

        Therefore, directory permissions should not be interpreted exactly
        like regular-file permissions.
        """
    )

    with tempfile.TemporaryDirectory(prefix="metadata_lab_") as temporary_directory:
        base = Path(temporary_directory)
        sample = base / "sample.txt"
        sample.write_text("metadata demonstration\n", encoding="utf-8")

        run_command(["ls", "-l", str(sample)])
        run_command(["ls", "-ld", str(base)])


# ============================================================================
# 21. COMMAND FAILURE AND EXIT STATUS
# ============================================================================

def teach_exit_status_and_errors() -> None:
    section("20. EXIT STATUS, ERRORS, AND DEBUGGING")

    explain(
        """
        Unix commands communicate success or failure through an exit status.

        Conventionally:

            0       success
            nonzero failure or special condition

        Example:

            ls existing-file

        can return 0.

        Attempting to access a nonexistent file commonly returns a nonzero
        status.

        In a shell, the previous command's exit status can be inspected using:

            echo $?

        Python's subprocess.run returns the status as:

            result.returncode

        Typical debugging workflow:

            1. Check pwd.
            2. Run ls.
            3. Verify the path.
            4. Check spelling and case.
            5. Check whether the target exists.
            6. Check permissions.
            7. Read stderr.
            8. Inspect the command's exit status.

        Do not interpret every error as a command-syntax problem. A command
        can be syntactically valid but fail because a file does not exist,
        permission is denied, a filesystem is read-only, or a destination
        conflicts with an existing object.
        """
    )

    with tempfile.TemporaryDirectory(prefix="error_lab_") as temporary_directory:
        base = Path(temporary_directory)

        result = run_command(["ls", "does-not-exist.txt"], cwd=base)
        print(f"Python observed return code: {result.returncode}")

        if result.returncode != 0:
            print("The controlled example failed as expected.")


# ============================================================================
# 22. SECURITY
# ============================================================================

def teach_security() -> None:
    section("21. SECURITY CONSIDERATIONS")

    explain(
        """
        Filesystem commands are powerful because they directly manipulate
        persistent data.

        1. Least privilege

        Run commands with the lowest privileges necessary.

        Avoid unnecessarily using:

            sudo rm -rf ...

        Elevated privileges can turn a small path mistake into a system-wide
        incident.

        2. Validate paths

        Automated scripts should not blindly trust paths supplied by users.

        A path such as:

            ../../sensitive-file

        can escape an intended directory if input is not constrained.

        3. Quote shell arguments

        Shell metacharacters can change command meaning.

        Dangerous construction:

            shell command built from untrusted text

        Safer programmatic construction:

            subprocess.run(["ls", user_supplied_path], ...)

        rather than constructing a shell command string with shell=True.

        4. Be careful with wildcards

            rm *.tmp

        can affect many files.

        5. Symbolic links

        Symbolic links can redirect operations to unexpected targets.

        Security-sensitive programs should not assume that a path's apparent
        location guarantees the location of the final object.

        6. Sensitive files

        Commands such as:

            cat .env
            cat private-key

        can expose credentials or secrets on screen, terminal history,
        recordings, logs, or monitoring systems.

        7. Deletion is not secure erasure

        rm primarily removes filesystem references. Data-recovery behavior
        depends on the filesystem, storage technology, snapshots, backups,
        encryption, and other factors.
        """
    )


# ============================================================================
# 23. PERFORMANCE AND IMPLEMENTATION
# ============================================================================

def teach_performance() -> None:
    section("22. PERFORMANCE AND IMPLEMENTATION CONSIDERATIONS")

    explain(
        """
        The commands are simple from a user perspective, but their behavior
        involves filesystem operations, system calls, directory metadata, and
        storage characteristics.

        ls:

        Listing a directory generally requires reading directory entries and
        may require metadata lookups. Detailed listings can therefore involve
        more filesystem work than a minimal listing.

        cp:

        Copying a large file requires transferring its data. Performance is
        influenced by storage speed, cache state, filesystem behavior, network
        storage, and whether metadata must be preserved.

        mv:

        A rename within the same filesystem can be very cheap because the
        operation can often update directory metadata rather than copying the
        file contents.

        Moving between filesystems may require copying data and removing the
        source.

        rm:

        Removing a large directory tree can require processing many directory
        entries. It is not equivalent to instantly wiping every data block.

        cat:

        cat streams data to stdout. For a huge file, the terminal itself can
        become the bottleneck.

        less:

        less avoids flooding the terminal with the entire file and provides
        interactive navigation.

        head and tail:

        These commands are efficient tools for inspecting only a portion of a
        large text stream.

        tail -f:

        Following a file can remain active for a long time and therefore has
        different operational behavior from a one-shot tail command.
        """
    )


# ============================================================================
# 24. PRODUCTION PRACTICES
# ============================================================================

def teach_production_practices() -> None:
    section("23. PRODUCTION AND OPERATIONS PRACTICES")

    explain(
        """
        A reliable operational workflow usually makes assumptions explicit.

        Before a destructive filesystem operation:

            pwd
            ls -lah TARGET

        For important data:

            verify backups
            verify the target path
            verify ownership and permissions
            consider a dry run when the tool supports it
            use interactive confirmation when appropriate

        For scripts:

        - Quote paths.
        - Check exit statuses.
        - Handle missing files deliberately.
        - Avoid unnecessary shell interpretation.
        - Log important operations.
        - Avoid hard-coded assumptions about usernames or home directories.
        - Consider filenames containing spaces.
        - Consider symbolic links where security matters.
        - Test on non-production data first.
        - Use absolute paths when ambiguity would be dangerous.
        - Prefer predictable behavior over clever one-liners.

        For log investigation:

            head -n 50 application.log
            tail -n 50 application.log
            less application.log
            tail -f application.log

        For directory inspection:

            pwd
            ls -lah
            ls -lah subdirectory

        For controlled organization:

            mkdir -p project/src project/tests project/docs
            cp -a project backup
            mv old-name new-name
        """
    )


# ============================================================================
# 25. COMMON MISTAKES
# ============================================================================

def teach_common_mistakes() -> None:
    section("24. COMMON MISTAKES")

    mistakes = [
        (
            "Using the wrong current directory",
            "Run pwd before using relative paths."
        ),
        (
            "Confusing / with ~",
            "/ is filesystem root; ~ is the current user's home directory."
        ),
        (
            "Forgetting hidden files",
            "Use ls -la when hidden entries matter."
        ),
        (
            "Using cp without -r for directories",
            "Use cp -r or cp -a when recursive copying is required."
        ),
        (
            "Assuming mv always copies data",
            "Within one filesystem, mv can be implemented as a rename."
        ),
        (
            "Using rm casually",
            "Deletion can be irreversible. Verify the target first."
        ),
        (
            "Using cat for enormous files",
            "Use less, head, or tail when only part of the content is needed."
        ),
        (
            "Forgetting spaces in filenames",
            "Quote or escape paths containing spaces."
        ),
        (
            "Ignoring case sensitivity",
            "File.txt and file.txt are different names on normal Linux filesystems."
        ),
        (
            "Ignoring stderr",
            "An error message may explain exactly why an operation failed."
        ),
        (
            "Assuming wildcard expansion is harmless",
            "Patterns such as * can expand to many filesystem entries."
        ),
        (
            "Using sudo unnecessarily",
            "Elevated privileges increase the impact of mistakes."
        ),
    ]

    print(f"{'Mistake':<42} Correct practice")
    print("-" * 100)

    for mistake, practice in mistakes:
        print(f"{mistake:<42} {practice}")


# ============================================================================
# 26. PROGRESSIVE WORKFLOWS
# ============================================================================

def teach_progressive_workflows() -> None:
    section("25. PROGRESSIVE COMMAND-LINE WORKFLOWS")

    subsection("Beginner workflow")

    explain(
        """
        Inspect location:

            pwd

        List files:

            ls

        Create a directory:

            mkdir practice

        Enter it:

            cd practice

        Create a file using another tool or shell redirection:

            printf "hello\\n" > hello.txt

        Inspect it:

            cat hello.txt

        Return:

            cd ..
        """
    )

    subsection("Intermediate workflow")

    explain(
        """
        Create a project structure:

            mkdir -p project/src project/docs project/logs

        Inspect it:

            ls -lah project

        Copy a file:

            cp project/src/main.py project/src/main-backup.py

        Rename it:

            mv project/src/main-backup.py project/src/main-old.py

        Inspect a document:

            less project/docs/notes.txt

        Inspect the first and last lines:

            head -n 10 project/docs/notes.txt
            tail -n 10 project/docs/notes.txt
        """
    )

    subsection("Advanced operational workflow")

    explain(
        """
        Inspect the current context:

            pwd
            ls -lah

        Inspect a potentially large log:

            head -n 30 application.log
            tail -n 30 application.log
            less application.log

        Monitor new log entries:

            tail -f application.log

        Preserve a project tree:

            cp -a project project-backup

        Rename an atomic filesystem-level object where appropriate:

            mv configuration.new configuration.active

        Remove temporary artifacts only after verification:

            ls -lah temporary/
            rm -i temporary/file.txt

        The important skill is not memorizing isolated commands. It is
        combining them while maintaining awareness of path, state, ownership,
        permissions, and consequences.
        """
    )


# ============================================================================
# 27. COMMAND REFERENCE
# ============================================================================

def print_command_reference() -> None:
    section("26. QUICK COMMAND REFERENCE")

    reference = [
        ("pwd", "Show current working directory", "pwd"),
        ("ls", "List directory contents", "ls -lah"),
        ("cd", "Change directory", "cd /var/log"),
        ("mkdir", "Create directory", "mkdir -p a/b/c"),
        ("cp", "Copy file", "cp source.txt backup.txt"),
        ("cp -r", "Copy directory recursively", "cp -r source backup"),
        ("cp -a", "Archive-style recursive copy", "cp -a source backup"),
        ("mv", "Move or rename", "mv old.txt new.txt"),
        ("rm", "Remove file", "rm file.txt"),
        ("rm -r", "Remove directory recursively", "rm -r directory"),
        ("rm -i", "Prompt before removal", "rm -i file.txt"),
        ("cat", "Display/concatenate files", "cat file.txt"),
        ("cat -n", "Display numbered lines", "cat -n file.txt"),
        ("less", "Interactively page through text", "less large.log"),
        ("head", "Show beginning of file", "head -n 10 file.txt"),
        ("tail", "Show end of file", "tail -n 10 file.txt"),
        ("tail -f", "Follow new data in a file", "tail -f application.log"),
    ]

    print(f"{'Command':<12} {'Purpose':<38} Example")
    print("-" * 100)

    for command, purpose, example in reference:
        print(f"{command:<12} {purpose:<38} {example}")


# ============================================================================
# 28. KNOWLEDGE CHECK
# ============================================================================

def knowledge_check() -> None:
    section("27. KNOWLEDGE CHECK")

    questions = [
        (
            "Which command tells you where you are?",
            "pwd"
        ),
        (
            "Which command lists directory contents?",
            "ls"
        ),
        (
            "Which command changes your current directory?",
            "cd"
        ),
        (
            "Which option makes ls show hidden entries?",
            "-a or -A"
        ),
        (
            "Which command creates a directory?",
            "mkdir"
        ),
        (
            "Which mkdir option creates missing parent directories?",
            "-p"
        ),
        (
            "Which command copies files?",
            "cp"
        ),
        (
            "Which cp option is commonly used for recursive directory copying?",
            "-r"
        ),
        (
            "Which command moves or renames files?",
            "mv"
        ),
        (
            "Which command removes files?",
            "rm"
        ),
        (
            "Which rm option recursively removes directories?",
            "-r"
        ),
        (
            "Which command displays file contents?",
            "cat"
        ),
        (
            "Which command provides interactive paging?",
            "less"
        ),
        (
            "Which command displays the beginning of a file?",
            "head"
        ),
        (
            "Which command displays the end of a file?",
            "tail"
        ),
        (
            "Which tail option follows a growing file?",
            "-f"
        ),
        (
            "Which special path means the parent directory?",
            ".."
        ),
        (
            "Which special path means the current directory?",
            "."
        ),
        (
            "Which symbol commonly represents the user's home directory?",
            "~"
        ),
        (
            "What exit status conventionally represents success?",
            "0"
        ),
    ]

    print("Answers are intentionally shown after each question for self-checking.\n")

    for number, (question, answer) in enumerate(questions, start=1):
        print(f"{number:02d}. {question}")
        print(f"    Answer: {answer}\n")


# ============================================================================
# 29. AUTOMATION EXAMPLE
# ============================================================================

def demonstrate_python_automation() -> None:
    section("28. AUTOMATING LINUX COMMANDS FROM PYTHON")

    explain(
        """
        Python can invoke Linux commands using subprocess.

        Prefer argument lists:

            subprocess.run(["ls", "-lah", path])

        over shell command strings:

            subprocess.run(f"ls -lah {path}", shell=True)

        when shell interpretation is unnecessary.

        Argument lists reduce shell parsing issues and make boundaries between
        arguments explicit.

        subprocess.run can provide:

            stdout
            stderr
            returncode

        Setting check=True causes Python to raise CalledProcessError for a
        nonzero exit status.

        This section uses only the controlled temporary directory.
        """
    )

    with tempfile.TemporaryDirectory(prefix="python_linux_automation_") as temporary_directory:
        base = Path(temporary_directory)
        create_demo_environment(base)

        result = subprocess.run(
            ["ls", "-lah", "project"],
            cwd=str(base),
            text=True,
            capture_output=True,
            check=True,
        )

        print("Captured stdout:")
        print(result.stdout)

        print(f"Captured stderr: {result.stderr!r}")
        print(f"Return code: {result.returncode}")

        subsection("Python-native equivalent")

        explain(
            """
            Python's pathlib can often perform filesystem operations directly.

            For example:

                Path("new").mkdir()
                shutil.copy2(source, destination)
                Path.rename(new_name)
                Path.unlink()

            Direct Python APIs can be preferable when building applications
            because they avoid depending on command availability and shell
            behavior.

            Linux commands remain essential when working interactively in a
            shell, administering systems, troubleshooting, and composing
            Unix pipelines.
            """
        )


# ============================================================================
# 30. COMMANDS VERSUS PYTHON FILE APIs
# ============================================================================

def compare_shell_and_python() -> None:
    section("29. LINUX COMMANDS VERSUS PYTHON FILE APIs")

    rows = [
        ("pwd", "Path.cwd()", "Discover current process directory"),
        ("ls", "Path.iterdir()", "Enumerate directory entries"),
        ("cd", "Path.chdir-like process behavior via os.chdir()", "Change process directory"),
        ("mkdir", "Path.mkdir()", "Create directories"),
        ("cp", "shutil.copy2()", "Copy files with metadata"),
        ("mv", "shutil.move()", "Move files/directories"),
        ("rm", "Path.unlink()", "Remove one file"),
        ("rm -r", "shutil.rmtree()", "Remove directory trees"),
        ("cat", "Path.read_text()", "Read text"),
        ("head", "Read selected initial data", "Inspect beginning"),
        ("tail", "Read selected final data", "Inspect ending"),
    ]

    print(f"{'Linux command':<14} {'Python approach':<48} Purpose")
    print("-" * 110)

    for command, python_api, purpose in rows:
        print(f"{command:<14} {python_api:<48} {purpose}")


# ============================================================================
# 31. INTEGRATED EXERCISE
# ============================================================================

def integrated_exercise() -> None:
    section("30. INTEGRATED FILESYSTEM EXERCISE")

    explain(
        """
        This exercise models a small administrative workflow.

        Tasks:

        1. Create an application directory.
        2. Create docs, logs, and backups directories.
        3. Create a sample log.
        4. Inspect the directory.
        5. Inspect the beginning and end of the log.
        6. Copy the log into backups.
        7. Rename the backup.
        8. Remove a temporary file.
        9. Verify the final structure.

        The entire exercise is isolated inside a temporary directory.
        """
    )

    with tempfile.TemporaryDirectory(prefix="integrated_linux_lab_") as temporary_directory:
        base = Path(temporary_directory)

        run_command(["mkdir", "-p", "application/docs", "application/logs", "application/backups"], cwd=base)

        log_file = base / "application" / "logs" / "service.log"
        log_file.write_text(
            "\n".join(
                [
                    "INFO service starting",
                    "INFO loading configuration",
                    "INFO opening database connection",
                    "INFO database connection ready",
                    "WARNING request latency increased",
                    "INFO cache refreshed",
                    "ERROR controlled demonstration error",
                    "INFO retry started",
                    "INFO retry succeeded",
                    "INFO service healthy",
                ]
            )
            + "\n",
            encoding="utf-8",
        )

        temporary_file = base / "application" / "docs" / "temporary.txt"
        temporary_file.write_text("Temporary documentation\n", encoding="utf-8")

        run_command(["ls", "-lah", "application"], cwd=base)
        run_command(["ls", "-lah", "application/logs"], cwd=base)
        run_command(["head", "-n", "3", "application/logs/service.log"], cwd=base)
        run_command(["tail", "-n", "3", "application/logs/service.log"], cwd=base)

        run_command(
            [
                "cp",
                "application/logs/service.log",
                "application/backups/service.log.backup",
            ],
            cwd=base,
        )

        run_command(
            [
                "mv",
                "application/docs/temporary.txt",
                "application/docs/temporary-old.txt",
            ],
            cwd=base,
        )

        run_command(
            ["rm", "application/docs/temporary-old.txt"],
            cwd=base,
        )

        run_command(
            ["find", "application", "-maxdepth", "3", "-print"],
            cwd=base,
        )


# ============================================================================
# 32. FINAL STUDY NOTES
# ============================================================================

def final_study_notes() -> None:
    section("31. FINAL STUDY NOTES")

    explain(
        """
        The essential mental model is:

            pwd     Where am I?
            ls      What is here?
            cd      Where should I go?
            mkdir   What directory should I create?
            cp      What should I duplicate?
            mv      What should I move or rename?
            rm      What should I remove?
            cat     What short text should I display?
            less    What large text should I inspect interactively?
            head    What is at the beginning?
            tail    What is at the end?

        These commands become powerful when combined with:

            absolute paths
            relative paths
            wildcards
            standard input/output
            redirection
            pipes
            permissions
            exit statuses
            symbolic links
            careful quoting
            controlled automation

        The most important operational principle is to maintain awareness of
        your current location and the exact target of every filesystem
        operation.

        Before destructive work, establish:

            pwd
            ls -lah TARGET

        Before automating filesystem operations, establish:

            expected input
            expected output
            failure behavior
            permissions
            path validation
            recovery or backup strategy
        """
    )


# ============================================================================
# 33. MAIN PROGRAM
# ============================================================================

def main() -> None:
    """Run the complete Linux command tutorial."""
    show_python_environment()

    teach_filesystem_fundamentals()
    teach_command_structure()

    teach_pwd()
    teach_ls()
    teach_cd()
    teach_mkdir()
    teach_cp()
    teach_mv()
    teach_rm()
    teach_cat()
    teach_less()
    teach_head()
    teach_tail()

    run_controlled_lab()

    teach_command_comparisons()
    teach_path_edge_cases()
    teach_wildcards()
    teach_streams_and_redirection()
    teach_metadata()
    teach_exit_status_and_errors()
    teach_security()
    teach_performance()
    teach_production_practices()
    teach_common_mistakes()
    teach_progressive_workflows()

    print_command_reference()
    knowledge_check()
    demonstrate_python_automation()
    compare_shell_and_python()
    integrated_exercise()
    final_study_notes()

    section("TUTORIAL COMPLETE")
    print("The Linux command study program has completed successfully.")


if __name__ == "__main__":
    main()
