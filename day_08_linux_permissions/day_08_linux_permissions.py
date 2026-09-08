#!/usr/bin/env python3
"""
Linux Permissions: Users, Groups, chmod, chown, sudo, and the Permissions Model
===============================================================================

This self-contained Python study script teaches the Linux permissions model from
beginner through advanced concepts.

It demonstrates:

1. Linux users and groups
2. Ownership and permission classes
3. Reading symbolic permissions
4. Numeric/octal permissions
5. chmod concepts and simulations
6. chown and chgrp concepts
7. Directory permissions
8. sudo and privilege elevation
9. Special permissions: setuid, setgid, sticky bit
10. Access control decision logic
11. umask
12. Symbolic links
13. Practical permission validation
14. Security mistakes and safer alternatives
15. Production-oriented permission design
16. Permission auditing simulations
17. Unit tests for permission logic

IMPORTANT:
This script simulates many Linux permission operations instead of changing the
permissions of your own system. The demonstrations are therefore safe to run.

Some examples also display real Unix permission metadata when the script is run
on a Unix-like operating system.
"""

from __future__ import annotations

import os
import stat
import pwd
import grp
import tempfile
import shutil
import subprocess
import getpass
import platform
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, Optional, Set, Tuple
import unittest


# =============================================================================
# SECTION 1: FUNDAMENTAL TERMINOLOGY
# =============================================================================

"""
Linux is a multi-user operating system.

Every process normally runs with an effective user identity and one or more
group identities. Files and directories have:

    1. An owner user
    2. An owner group
    3. Permission bits

Traditional Linux permissions divide users into three permission classes:

    u = user / owner
    g = group
    o = others

Each class can receive three basic permissions:

    r = read
    w = write
    x = execute

The common textual representation is:

    rwxr-xr--

This is divided into three groups:

    rwx | r-x | r--

    owner | group | others

The owner has read, write, execute.
The group has read and execute.
Others have read only.
"""


READ = 4
WRITE = 2
EXECUTE = 1


# =============================================================================
# SECTION 2: NUMERIC PERMISSION MODEL
# =============================================================================

def permission_triplet_to_number(triplet: str) -> int:
    """
    Convert a symbolic triplet such as 'rwx' or 'r-x' into a numeric value.

    Examples:

        rwx -> 7
        rw- -> 6
        r-x -> 5
        r-- -> 4
        -wx -> 3
        --x -> 1

    The numeric value is the sum of:

        read    = 4
        write   = 2
        execute = 1
    """
    if len(triplet) != 3:
        raise ValueError("Permission triplet must contain exactly 3 characters.")

    value = 0

    if triplet[0] == "r":
        value += READ
    elif triplet[0] != "-":
        raise ValueError(f"Invalid read permission character: {triplet[0]!r}")

    if triplet[1] == "w":
        value += WRITE
    elif triplet[1] != "-":
        raise ValueError(f"Invalid write permission character: {triplet[1]!r}")

    if triplet[2] == "x":
        value += EXECUTE
    elif triplet[2] != "-":
        raise ValueError(f"Invalid execute permission character: {triplet[2]!r}")

    return value


def number_to_permission_triplet(value: int) -> str:
    """
    Convert a numeric permission value from 0 through 7 into symbolic form.
    """
    if not isinstance(value, int) or not 0 <= value <= 7:
        raise ValueError("Permission value must be an integer from 0 through 7.")

    return (
        ("r" if value & READ else "-")
        + ("w" if value & WRITE else "-")
        + ("x" if value & EXECUTE else "-")
    )


def parse_octal_permission(mode: str | int) -> Tuple[int, int, int]:
    """
    Parse permissions such as:

        755
        "755"
        "0755"

    Return:

        (owner, group, others)

    The special-permission digit is intentionally not handled by this basic
    function. Examples such as 4755 are handled later.
    """
    text = str(mode)

    if text.startswith("0") and len(text) > 3:
        text = text[1:]

    if len(text) != 3 or not text.isdigit():
        raise ValueError("Permission mode must contain exactly three octal digits.")

    digits = tuple(int(character) for character in text)

    if any(digit > 7 for digit in digits):
        raise ValueError("Permission digits must be between 0 and 7.")

    return digits


def octal_to_symbolic(mode: str | int) -> str:
    """
    Convert 755 into rwxr-xr-x.
    """
    owner, group, others = parse_octal_permission(mode)

    return (
        number_to_permission_triplet(owner)
        + number_to_permission_triplet(group)
        + number_to_permission_triplet(others)
    )


def symbolic_to_octal(symbolic: str) -> str:
    """
    Convert rwxr-xr-x into 755.
    """
    if len(symbolic) != 9:
        raise ValueError("Symbolic permissions must contain exactly 9 characters.")

    return "".join(
        str(permission_triplet_to_number(symbolic[index:index + 3]))
        for index in range(0, 9, 3)
    )


# =============================================================================
# SECTION 3: BASIC PERMISSION DEMONSTRATIONS
# =============================================================================

def demonstrate_permission_basics() -> None:
    print("\n" + "=" * 78)
    print("SECTION 1: BASIC LINUX PERMISSIONS")
    print("=" * 78)

    examples = [
        "rwx",
        "rw-",
        "r-x",
        "r--",
        "---",
    ]

    for symbolic in examples:
        numeric = permission_triplet_to_number(symbolic)
        restored = number_to_permission_triplet(numeric)
        print(f"{symbolic} -> {numeric} -> {restored}")

    print("\nCommon file modes:")

    common_modes = {
        "644": "Typical regular file",
        "600": "Private file readable/writable only by owner",
        "755": "Typical executable program or directory",
        "700": "Private executable or private directory",
        "777": "Readable, writable, executable by everyone",
    }

    for mode, meaning in common_modes.items():
        print(f"{mode} -> {octal_to_symbolic(mode)} -> {meaning}")


# =============================================================================
# SECTION 4: USERS AND GROUPS
# =============================================================================

@dataclass(frozen=True)
class LinuxUser:
    """
    A simplified representation of a Linux user.

    Real Linux users have additional attributes such as:

        UID
        primary GID
        supplementary groups
        home directory
        login shell
    """

    username: str
    uid: int
    primary_group: str
    supplementary_groups: frozenset[str] = field(default_factory=frozenset)

    def all_groups(self) -> Set[str]:
        return {self.primary_group, *self.supplementary_groups}


@dataclass
class LinuxObject:
    """
    Simulated filesystem object.

    object_type may be:

        file
        directory
        executable

    Linux internally stores permissions as mode bits rather than this string
    representation, but symbolic permissions are convenient for teaching.
    """

    path: str
    owner: str
    group: str
    permissions: str
    object_type: str = "file"

    def __post_init__(self) -> None:
        if len(self.permissions) != 9:
            raise ValueError("Permissions must contain exactly 9 characters.")

        if self.object_type not in {"file", "directory", "executable"}:
            raise ValueError("Unsupported object type.")

    @property
    def owner_permissions(self) -> str:
        return self.permissions[0:3]

    @property
    def group_permissions(self) -> str:
        return self.permissions[3:6]

    @property
    def others_permissions(self) -> str:
        return self.permissions[6:9]


def determine_permission_class(user: LinuxUser, obj: LinuxObject) -> str:
    """
    Determine which permission class Linux checks.

    This order is extremely important:

        1. If the user owns the object, use owner permissions.
        2. Otherwise, if the user belongs to the object's group, use group
           permissions.
        3. Otherwise, use others permissions.

    Linux does not combine these classes.

    Example:

        Owner permissions: rw-
        Group permissions: ---
        Others permissions: r--

    If the user is the owner, Linux uses rw- even if that user is also a member
    of another relevant group. Permissions are not merged into the most
    permissive combination.
    """
    if user.username == obj.owner:
        return "owner"

    if obj.group in user.all_groups():
        return "group"

    return "others"


def permissions_for_user(user: LinuxUser, obj: LinuxObject) -> str:
    permission_class = determine_permission_class(user, obj)

    if permission_class == "owner":
        return obj.owner_permissions

    if permission_class == "group":
        return obj.group_permissions

    return obj.others_permissions


# =============================================================================
# SECTION 5: SIMULATING ACCESS CONTROL
# =============================================================================

def can_read(user: LinuxUser, obj: LinuxObject) -> bool:
    return "r" in permissions_for_user(user, obj)


def can_write(user: LinuxUser, obj: LinuxObject) -> bool:
    return "w" in permissions_for_user(user, obj)


def can_execute(user: LinuxUser, obj: LinuxObject) -> bool:
    return "x" in permissions_for_user(user, obj)


def demonstrate_user_group_access() -> None:
    print("\n" + "=" * 78)
    print("SECTION 2: USERS, GROUPS, AND ACCESS DECISIONS")
    print("=" * 78)

    alice = LinuxUser(
        username="alice",
        uid=1001,
        primary_group="developers",
        supplementary_groups=frozenset({"docker", "analytics"}),
    )

    bob = LinuxUser(
        username="bob",
        uid=1002,
        primary_group="developers",
    )

    charlie = LinuxUser(
        username="charlie",
        uid=1003,
        primary_group="sales",
    )

    project_file = LinuxObject(
        path="/srv/project/config.py",
        owner="alice",
        group="developers",
        permissions="rw-r-----",
        object_type="file",
    )

    print(f"\nObject: {project_file.path}")
    print(f"Owner: {project_file.owner}")
    print(f"Group: {project_file.group}")
    print(f"Permissions: {project_file.permissions}")
    print()

    for user in [alice, bob, charlie]:
        selected_class = determine_permission_class(user, project_file)
        selected_permissions = permissions_for_user(user, project_file)

        print(
            f"{user.username:7} -> class={selected_class:6} "
            f"permissions={selected_permissions} "
            f"read={can_read(user, project_file)} "
            f"write={can_write(user, project_file)} "
            f"execute={can_execute(user, project_file)}"
        )


# =============================================================================
# SECTION 6: DIRECTORY PERMISSIONS
# =============================================================================

"""
Directory permissions are often misunderstood because their meaning differs
from file permissions.

For a regular file:

    r = read file contents
    w = modify file contents
    x = execute the file as a program

For a directory:

    r = list directory entries
    w = create, remove, or rename entries, subject to directory semantics
    x = traverse/search the directory

The execute permission on a directory is particularly important.

A user may have:

    r-- on a directory

This can permit listing names while preventing traversal into entries.

A user may have:

    --x on a directory

This can permit traversal if the user already knows a file name, but not listing
all names in the directory.
"""


def explain_directory_permissions() -> None:
    print("\n" + "=" * 78)
    print("SECTION 3: DIRECTORY PERMISSIONS")
    print("=" * 78)

    directory_modes = {
        "rwx": "List entries, modify entries, and traverse/search.",
        "r-x": "List and traverse entries, but cannot normally create/remove entries.",
        "--x": "Traverse/search if entry names are known, but cannot list names.",
        "rw-": "Read and modify directory entries is incomplete without traversal.",
        "---": "No ordinary access.",
    }

    for permissions, explanation in directory_modes.items():
        print(f"{permissions}: {explanation}")


# =============================================================================
# SECTION 7: CHMOD CONCEPTS
# =============================================================================

def chmod_numeric(obj: LinuxObject, mode: str | int) -> None:
    """
    Simulate chmod using numeric notation.

    Example:

        chmod_numeric(file, 640)

    Equivalent conceptual Linux command:

        chmod 640 filename
    """
    obj.permissions = octal_to_symbolic(mode)


def chmod_symbolic(
    obj: LinuxObject,
    classes: str,
    operator: str,
    permissions: str,
) -> None:
    """
    Simulate a useful subset of symbolic chmod.

    Examples:

        chmod u+x file
        chmod g-w file
        chmod o=r file
        chmod ug+rw file
        chmod a+r file

    classes:
        u, g, o, a

    operator:
        + add permissions
        - remove permissions
        = assign permissions exactly

    permissions:
        combination of r, w, x

    This implementation intentionally focuses on the standard conceptual model
    rather than reproducing every GNU chmod extension.
    """
    valid_classes = {"u", "g", "o", "a"}
    valid_permissions = {"r", "w", "x"}

    if not classes:
        raise ValueError("At least one permission class is required.")

    if any(character not in valid_classes for character in classes):
        raise ValueError("Invalid permission class.")

    if operator not in {"+", "-", "="}:
        raise ValueError("Operator must be '+', '-', or '='.")

    if any(character not in valid_permissions for character in permissions):
        raise ValueError("Invalid permission symbol.")

    selected_classes = set(classes)

    if "a" in selected_classes:
        selected_classes = {"u", "g", "o"}

    positions = {
        "u": 0,
        "g": 3,
        "o": 6,
    }

    permission_characters = list(obj.permissions)

    for permission_class in selected_classes:
        start = positions[permission_class]
        current = set(
            permission_characters[start + offset]
            for offset in range(3)
            if permission_characters[start + offset] != "-"
        )

        requested = set(permissions)

        if operator == "+":
            updated = current | requested
        elif operator == "-":
            updated = current - requested
        else:
            updated = requested

        permission_characters[start:start + 3] = [
            symbol if symbol in updated else "-"
            for symbol in "rwx"
        ]

    obj.permissions = "".join(permission_characters)


def demonstrate_chmod() -> None:
    print("\n" + "=" * 78)
    print("SECTION 4: CHMOD")
    print("=" * 78)

    script = LinuxObject(
        path="/opt/application/run.sh",
        owner="alice",
        group="developers",
        permissions="rw-r-----",
        object_type="file",
    )

    print(f"Initial permissions: {script.permissions}")

    chmod_numeric(script, 750)
    print(f"chmod 750:          {script.permissions}")

    chmod_symbolic(script, "g", "-", "x")
    print(f"chmod g-x:          {script.permissions}")

    chmod_symbolic(script, "u", "+", "x")
    print(f"chmod u+x:          {script.permissions}")

    chmod_symbolic(script, "o", "=", "r")
    print(f"chmod o=r:          {script.permissions}")

    chmod_symbolic(script, "a", "-", "w")
    print(f"chmod a-w:          {script.permissions}")


# =============================================================================
# SECTION 8: CHOWN AND CHGRP
# =============================================================================

def chown(
    obj: LinuxObject,
    new_owner: Optional[str] = None,
    new_group: Optional[str] = None,
) -> None:
    """
    Simulate ownership changes.

    Conceptually:

        chown alice file
        chown alice:developers file
        chown :developers file

    Real systems impose authorization rules. Ordinary users generally cannot
    arbitrarily change file ownership to another user.
    """
    if new_owner is not None:
        if not new_owner:
            raise ValueError("Owner name cannot be empty.")
        obj.owner = new_owner

    if new_group is not None:
        if not new_group:
            raise ValueError("Group name cannot be empty.")
        obj.group = new_group


def demonstrate_chown() -> None:
    print("\n" + "=" * 78)
    print("SECTION 5: CHOWN AND GROUP OWNERSHIP")
    print("=" * 78)

    report = LinuxObject(
        path="/srv/reports/quarterly.txt",
        owner="alice",
        group="finance",
        permissions="rw-r-----",
    )

    print(
        f"Initial: owner={report.owner}, group={report.group}, "
        f"permissions={report.permissions}"
    )

    chown(report, new_group="auditors")
    print(
        f"Group change: owner={report.owner}, group={report.group}, "
        f"permissions={report.permissions}"
    )

    chown(report, new_owner="bob", new_group="finance")
    print(
        f"Owner/group change: owner={report.owner}, group={report.group}, "
        f"permissions={report.permissions}"
    )


# =============================================================================
# SECTION 9: ROOT AND SUDO
# =============================================================================

"""
The root account has UID 0 and is traditionally the superuser.

sudo does not simply mean "run everything as root forever."

sudo commonly performs controlled privilege elevation for a particular command.
Its policy can specify:

    - Which users may use sudo
    - Which groups may use sudo
    - Which commands may be executed
    - Which target users may be selected
    - Whether authentication is required
    - Whether environment variables are restricted

The configuration is commonly managed through sudoers policy.

A secure operational principle is:

    Use the least privilege required.

Avoid running an entire shell or application with elevated privileges when only
one operation requires elevation.
"""


@dataclass
class SudoPolicy:
    """
    Simplified sudo authorization model.

    This is educational and is not a replacement for the real sudo policy
    language.
    """

    allowed_commands: Dict[str, Set[str]]

    def can_run(self, username: str, command: str) -> bool:
        return command in self.allowed_commands.get(username, set())


def demonstrate_sudo() -> None:
    print("\n" + "=" * 78)
    print("SECTION 6: SUDO AND PRIVILEGE ELEVATION")
    print("=" * 78)

    policy = SudoPolicy(
        allowed_commands={
            "alice": {
                "/usr/bin/systemctl restart example.service",
                "/usr/bin/journalctl",
            },
            "bob": {
                "/usr/bin/systemctl status example.service",
            },
        }
    )

    checks = [
        ("alice", "/usr/bin/systemctl restart example.service"),
        ("alice", "/bin/bash"),
        ("bob", "/usr/bin/systemctl restart example.service"),
        ("bob", "/usr/bin/systemctl status example.service"),
    ]

    for username, command in checks:
        allowed = policy.can_run(username, command)
        print(
            f"User={username:5} Command={command:45} Allowed={allowed}"
        )

    print(
        "\nSecurity principle: narrowly authorize required commands instead "
        "of granting unrestricted administrative shells."
    )


# =============================================================================
# SECTION 10: SPECIAL PERMISSION BITS
# =============================================================================

"""
Linux supports three historically important special permission bits:

    setuid = 4 in the leading octal position
    setgid = 2 in the leading octal position
    sticky = 1 in the leading octal position

Examples:

    4755
    2755
    1777

setuid:
    Executable processes may run with the effective identity associated with the
    executable's owner.

setgid on executable:
    Processes may run with the executable's group identity.

setgid on directory:
    Newly created objects commonly inherit the directory's group.

sticky bit on directory:
    Restricts deletion or renaming of entries so that users generally cannot
    remove arbitrary files belonging to other users, even when the directory is
    otherwise writable by multiple users.

A classic shared temporary directory mode is conceptually:

    1777

Special permissions increase the security importance of executable ownership and
file integrity.
"""


SETUID = 0o4000
SETGID = 0o2000
STICKY = 0o1000


def describe_special_mode(mode: int) -> Dict[str, bool]:
    """
    Return which special bits are enabled.
    """
    return {
        "setuid": bool(mode & SETUID),
        "setgid": bool(mode & SETGID),
        "sticky": bool(mode & STICKY),
    }


def mode_to_symbolic_with_special_bits(mode: int, is_directory: bool = False) -> str:
    """
    Convert a full Unix mode into symbolic permissions including special bits.

    Examples:

        0o4755 -> rwsr-xr-x
        0o2755 -> rwxr-sr-x
        0o1777 -> rwxrwxrwt

    Lowercase s/t means execute permission is also present.
    Uppercase S/T means the special bit is present without execute permission.
    """
    if mode < 0 or mode > 0o7777:
        raise ValueError("Mode must be between 0 and 0o7777.")

    owner = number_to_permission_triplet((mode >> 6) & 0b111)
    group = number_to_permission_triplet((mode >> 3) & 0b111)
    others = number_to_permission_triplet(mode & 0b111)

    characters = list(owner + group + others)

    if mode & SETUID:
        characters[2] = "s" if characters[2] == "x" else "S"

    if mode & SETGID:
        characters[5] = "s" if characters[5] == "x" else "S"

    if mode & STICKY:
        characters[8] = "t" if characters[8] == "x" else "T"

    return "".join(characters)


def demonstrate_special_permissions() -> None:
    print("\n" + "=" * 78)
    print("SECTION 7: SPECIAL PERMISSIONS")
    print("=" * 78)

    modes = [
        (0o4755, "setuid executable"),
        (0o2755, "setgid directory or executable"),
        (0o1777, "sticky shared directory"),
        (0o6755, "setuid + setgid"),
    ]

    for mode, meaning in modes:
        flags = describe_special_mode(mode)
        symbolic = mode_to_symbolic_with_special_bits(mode)

        print(
            f"{mode:04o} -> {symbolic} -> {meaning}; "
            f"flags={flags}"
        )


# =============================================================================
# SECTION 11: UMASK
# =============================================================================

"""
umask controls which permissions are removed from the permissions requested by
newly created files and directories.

A conceptual formula is:

    final_mode = requested_mode & ~umask

Typical requested modes are:

    files:       666
    directories: 777

Regular files generally do not request execute permission by default.

Examples:

    umask 022

    file:
        666 & ~022 = 644

    directory:
        777 & ~022 = 755
"""


def apply_umask(requested_mode: int, umask: int) -> int:
    """
    Apply a Unix-style umask to an octal mode.
    """
    if not 0 <= requested_mode <= 0o777:
        raise ValueError("Requested mode must be between 0 and 0o777.")

    if not 0 <= umask <= 0o777:
        raise ValueError("Umask must be between 0 and 0o777.")

    return requested_mode & (~umask & 0o777)


def demonstrate_umask() -> None:
    print("\n" + "=" * 78)
    print("SECTION 8: UMASK")
    print("=" * 78)

    examples = [
        (0o666, 0o022, "regular file"),
        (0o777, 0o022, "directory"),
        (0o666, 0o077, "private file"),
        (0o777, 0o077, "private directory"),
        (0o666, 0o002, "group-collaboration file"),
    ]

    for requested, mask, description in examples:
        final_mode = apply_umask(requested, mask)

        print(
            f"{description:28} requested={requested:03o} "
            f"umask={mask:03o} final={final_mode:03o} "
            f"({octal_to_symbolic(f'{final_mode:03o}')})"
        )


# =============================================================================
# SECTION 12: SYMBOLIC LINKS
# =============================================================================

"""
A symbolic link is a filesystem object containing a reference to another path.

Important conceptual distinction:

    Permissions displayed for a symbolic link itself are generally not used to
    control access in the same way as ordinary file permissions.

Access checks usually apply to the target object.

Ownership of symbolic links can still matter for some administrative operations.

When changing permissions recursively, administrators should be careful with
symbolic links and filesystem traversal behavior.
"""


def demonstrate_symbolic_links() -> None:
    print("\n" + "=" * 78)
    print("SECTION 9: SYMBOLIC LINKS")
    print("=" * 78)

    print(
        "A symbolic link points to another path. Access checks generally "
        "resolve to the target object's permissions."
    )
    print(
        "Administrative operations involving recursive ownership or permission "
        "changes must consider symlink traversal behavior carefully."
    )


# =============================================================================
# SECTION 13: ACCESS CONTROL ENGINE
# =============================================================================

class AccessDeniedError(PermissionError):
    """Raised when the simulated Linux permission model denies an operation."""


def require_access(
    user: LinuxUser,
    obj: LinuxObject,
    operation: str,
) -> None:
    """
    Raise AccessDeniedError when the selected permission class does not allow
    the requested operation.
    """
    allowed_operations = {
        "read": can_read,
        "write": can_write,
        "execute": can_execute,
    }

    if operation not in allowed_operations:
        raise ValueError(
            f"Unsupported operation {operation!r}. "
            f"Use read, write, or execute."
        )

    allowed = allowed_operations[operation](user, obj)

    if not allowed:
        permission_class = determine_permission_class(user, obj)
        effective_permissions = permissions_for_user(user, obj)

        raise AccessDeniedError(
            f"Access denied: user={user.username}, object={obj.path}, "
            f"operation={operation}, class={permission_class}, "
            f"permissions={effective_permissions}"
        )


def demonstrate_permission_errors() -> None:
    print("\n" + "=" * 78)
    print("SECTION 10: PERMISSION DENIALS AND DEBUGGING")
    print("=" * 78)

    alice = LinuxUser("alice", 1001, "developers")
    bob = LinuxUser("bob", 1002, "sales")

    secret = LinuxObject(
        path="/srv/secrets/database.env",
        owner="alice",
        group="developers",
        permissions="rw-------",
    )

    try:
        require_access(bob, secret, "read")
    except AccessDeniedError as error:
        print(error)

    try:
        require_access(alice, secret, "write")
        print(f"Write allowed for {alice.username}.")
    except AccessDeniedError as error:
        print(error)


# =============================================================================
# SECTION 14: DIRECTORY TRAVERSAL SIMULATION
# =============================================================================

@dataclass
class DirectoryAccessResult:
    can_list: bool
    can_create_or_remove_entries: bool
    can_traverse: bool


def evaluate_directory_access(
    user: LinuxUser,
    directory: LinuxObject,
) -> DirectoryAccessResult:
    """
    Evaluate permissions specifically according to directory semantics.

    This is simplified and does not model ACLs, immutable attributes, mount
    options, mandatory access control systems, or filesystem-specific rules.
    """
    if directory.object_type != "directory":
        raise ValueError("Object must be a directory.")

    permissions = permissions_for_user(user, directory)

    return DirectoryAccessResult(
        can_list="r" in permissions,
        can_create_or_remove_entries="w" in permissions,
        can_traverse="x" in permissions,
    )


def demonstrate_directory_access() -> None:
    print("\n" + "=" * 78)
    print("SECTION 11: DIRECTORY ACCESS EDGE CASES")
    print("=" * 78)

    alice = LinuxUser("alice", 1001, "engineering")
    visitor = LinuxUser("visitor", 1002, "guests")

    private_directory = LinuxObject(
        path="/home/alice/private",
        owner="alice",
        group="engineering",
        permissions="rwx--x---",
        object_type="directory",
    )

    for user in [alice, visitor]:
        result = evaluate_directory_access(user, private_directory)
        print(
            f"{user.username:8} list={result.can_list} "
            f"modify_entries={result.can_create_or_remove_entries} "
            f"traverse={result.can_traverse}"
        )


# =============================================================================
# SECTION 15: COMMON SECURITY MISTAKES
# =============================================================================

def demonstrate_security_mistakes() -> None:
    print("\n" + "=" * 78)
    print("SECTION 12: COMMON SECURITY MISTAKES")
    print("=" * 78)

    examples = [
        (
            "chmod 777",
            "Grants write access to every user. This can permit unintended "
            "modification or deletion in shared locations.",
        ),
        (
            "World-readable secrets",
            "Credentials, private keys, tokens, and configuration secrets "
            "should not be readable by unrelated accounts.",
        ),
        (
            "Unrestricted sudo",
            "Administrative authorization should be restricted to required "
            "users and commands.",
        ),
        (
            "Incorrect group ownership",
            "Collaborative services often fail because the process user and "
            "filesystem group are not designed consistently.",
        ),
        (
            "Ignoring directory execute permission",
            "Directory access failures can occur even when a file itself "
            "appears readable because a parent directory cannot be traversed.",
        ),
        (
            "Unsafe setuid programs",
            "A vulnerable privileged executable can create a serious "
            "privilege-escalation path.",
        ),
    ]

    for title, explanation in examples:
        print(f"\n{title}")
        print(f"  {explanation}")


# =============================================================================
# SECTION 16: LEAST PRIVILEGE DESIGN
# =============================================================================

@dataclass
class ApplicationPermissionRequirement:
    """
    Describe a practical permission requirement.
    """

    resource: str
    readers: Set[str]
    writers: Set[str]
    executors: Set[str]


def design_permission_model(
    requirement: ApplicationPermissionRequirement,
) -> Dict[str, Set[str]]:
    """
    Produce a conceptual role-based access representation.

    Linux groups are often useful for implementing shared authorization where
    multiple users need similar access.
    """
    return {
        "read": set(requirement.readers),
        "write": set(requirement.writers),
        "execute": set(requirement.executors),
    }


def demonstrate_permission_design() -> None:
    print("\n" + "=" * 78)
    print("SECTION 13: LEAST PRIVILEGE PERMISSION DESIGN")
    print("=" * 78)

    requirement = ApplicationPermissionRequirement(
        resource="/srv/application/config",
        readers={"app-service", "deploy-user"},
        writers={"deploy-user"},
        executors=set(),
    )

    design = design_permission_model(requirement)

    print(f"Resource: {requirement.resource}")

    for operation, identities in design.items():
        print(f"{operation:8}: {sorted(identities)}")

    print(
        "\nProduction design principle: identify exactly which identities need "
        "which operations and avoid granting broader permissions merely for "
        "convenience."
    )


# =============================================================================
# SECTION 17: REAL UNIX FILESYSTEM DEMONSTRATION
# =============================================================================

def format_real_mode(path: Path) -> str:
    """
    Return Unix-style mode information for a real path.
    """
    metadata = path.stat()
    return stat.filemode(metadata.st_mode)


def demonstrate_real_filesystem_metadata() -> None:
    print("\n" + "=" * 78)
    print("SECTION 14: REAL FILESYSTEM METADATA")
    print("=" * 78)

    print(f"Operating system: {platform.system()}")
    print(f"Current user name: {getpass.getuser()}")

    if os.name != "posix":
        print(
            "This demonstration is most meaningful on Unix-like systems. "
            "The simulated permission examples remain portable."
        )
        return

    temporary_directory = Path(tempfile.mkdtemp(prefix="linux_permissions_demo_"))

    try:
        demo_file = temporary_directory / "example.txt"
        demo_file.write_text("Linux permissions demonstration\n", encoding="utf-8")

        os.chmod(demo_file, 0o640)

        metadata = demo_file.stat()

        print(f"Temporary file: {demo_file}")
        print(f"Symbolic mode: {format_real_mode(demo_file)}")
        print(f"Octal mode: {stat.S_IMODE(metadata.st_mode):03o}")
        print(f"UID: {metadata.st_uid}")
        print(f"GID: {metadata.st_gid}")

        try:
            username = pwd.getpwuid(metadata.st_uid).pw_name
            group_name = grp.getgrgid(metadata.st_gid).gr_name

            print(f"Owner: {username}")
            print(f"Group: {group_name}")
        except KeyError:
            print("Owner or group name could not be resolved.")

    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)


# =============================================================================
# SECTION 18: ACL CONCEPTS
# =============================================================================

"""
Traditional owner/group/others permissions are not always sufficiently granular.

POSIX Access Control Lists can provide additional permissions for named users
and groups.

Conceptually:

    owner: rw-
    group: r--
    others: ---

An ACL may grant a particular additional user read access.

ACLs introduce additional concepts such as an ACL mask that can limit effective
permissions for named users and groups.

Traditional chmod bits remain important even when ACLs are present.
"""


@dataclass
class SimpleACL:
    """
    Simplified educational ACL representation.

    This is not a complete POSIX ACL implementation.
    """

    named_user_permissions: Dict[str, str] = field(default_factory=dict)
    named_group_permissions: Dict[str, str] = field(default_factory=dict)
    mask: str = "rwx"

    def effective_user_permissions(
        self,
        user: LinuxUser,
        obj: LinuxObject,
    ) -> str:
        """
        Return named ACL permissions when present.

        Owner permission remains conceptually distinct.
        ACL mask is applied to named user permissions.
        """
        if user.username == obj.owner:
            return obj.owner_permissions

        if user.username in self.named_user_permissions:
            requested = self.named_user_permissions[user.username]
            return intersect_permission_triplets(requested, self.mask)

        matching_permissions = [
            permissions
            for group_name, permissions in self.named_group_permissions.items()
            if group_name in user.all_groups()
        ]

        if matching_permissions:
            merged = union_permission_triplets(*matching_permissions)
            return intersect_permission_triplets(merged, self.mask)

        if obj.group in user.all_groups():
            return intersect_permission_triplets(
                obj.group_permissions,
                self.mask,
            )

        return obj.others_permissions


def intersect_permission_triplets(first: str, second: str) -> str:
    if len(first) != 3 or len(second) != 3:
        raise ValueError("Both permission triplets must have length 3.")

    return "".join(
        character if character == other else "-"
        for character, other in zip(first, second)
    )


def union_permission_triplets(*triplets: str) -> str:
    if not triplets:
        return "---"

    for triplet in triplets:
        if len(triplet) != 3:
            raise ValueError("Permission triplets must have length 3.")

    result = []

    for index, permission in enumerate("rwx"):
        result.append(
            permission
            if any(triplet[index] == permission for triplet in triplets)
            else "-"
        )

    return "".join(result)


def demonstrate_acl_concepts() -> None:
    print("\n" + "=" * 78)
    print("SECTION 15: ACCESS CONTROL LIST CONCEPTS")
    print("=" * 78)

    owner = LinuxUser("alice", 1001, "engineering")
    analyst = LinuxUser("diana", 1004, "analytics")

    file_object = LinuxObject(
        path="/srv/data/restricted.csv",
        owner="alice",
        group="engineering",
        permissions="rw-r-----",
    )

    acl = SimpleACL(
        named_user_permissions={
            "diana": "rw-",
        },
        mask="r--",
    )

    print(
        f"Named ACL for diana requests rw-, but ACL mask is r--."
    )
    print(
        f"Effective permissions: "
        f"{acl.effective_user_permissions(analyst, file_object)}"
    )

    print(
        "Important distinction: requested ACL permissions can be reduced by "
        "the ACL mask."
    )


# =============================================================================
# SECTION 19: PERMISSION AUDITING
# =============================================================================

@dataclass
class PermissionFinding:
    severity: str
    path: str
    message: str


def audit_permissions(objects: Iterable[LinuxObject]) -> list[PermissionFinding]:
    """
    Perform simple security-oriented checks.

    These checks are illustrative. Real permission auditing should account for:

        ACLs
        capabilities
        mount options
        service accounts
        containers
        namespaces
        mandatory access control
        application requirements
        filesystem type
    """
    findings: list[PermissionFinding] = []

    for obj in objects:
        owner, group, others = parse_octal_permission(
            symbolic_to_octal(obj.permissions)
        )

        if obj.object_type == "file" and others & WRITE:
            findings.append(
                PermissionFinding(
                    severity="HIGH",
                    path=obj.path,
                    message="Regular file is writable by others.",
                )
            )

        if obj.object_type == "directory" and others & WRITE:
            findings.append(
                PermissionFinding(
                    severity="MEDIUM",
                    path=obj.path,
                    message=(
                        "Directory is writable by others. Verify whether "
                        "sticky-bit protections and application requirements "
                        "are appropriate."
                    ),
                )
            )

        if obj.object_type == "executable" and others & WRITE:
            findings.append(
                PermissionFinding(
                    severity="CRITICAL",
                    path=obj.path,
                    message=(
                        "Executable is writable by others. Another user may "
                        "be able to modify code executed by more privileged "
                        "users or services."
                    ),
                )
            )

        if owner == 7 and group == 7 and others == 7:
            findings.append(
                PermissionFinding(
                    severity="HIGH",
                    path=obj.path,
                    message="Object uses mode 777. Verify that this is required.",
                )
            )

    return findings


def demonstrate_permission_audit() -> None:
    print("\n" + "=" * 78)
    print("SECTION 16: PERMISSION AUDITING")
    print("=" * 78)

    objects = [
        LinuxObject(
            "/srv/app/config.env",
            "app",
            "app",
            "rw-r-----",
            "file",
        ),
        LinuxObject(
            "/srv/app/run.sh",
            "app",
            "app",
            "rwxr-xr-x",
            "executable",
        ),
        LinuxObject(
            "/srv/shared",
            "root",
            "shared",
            "rwxrwxrwx",
            "directory",
        ),
        LinuxObject(
            "/srv/tools/admin-tool",
            "root",
            "admins",
            "rwxrwxrwx",
            "executable",
        ),
    ]

    findings = audit_permissions(objects)

    for finding in findings:
        print(
            f"[{finding.severity:8}] {finding.path}: {finding.message}"
        )


# =============================================================================
# SECTION 20: ADVANCED LIMITATIONS OF TRADITIONAL MODE BITS
# =============================================================================

def demonstrate_permission_model_limitations() -> None:
    print("\n" + "=" * 78)
    print("SECTION 17: LIMITATIONS AND ADVANCED SECURITY LAYERS")
    print("=" * 78)

    limitations = [
        (
            "ACLs",
            "Traditional owner/group/others permissions cannot always express "
            "fine-grained authorization requirements.",
        ),
        (
            "Linux capabilities",
            "Some privileged operations can be granted without giving a "
            "process unrestricted root privileges.",
        ),
        (
            "SELinux or AppArmor",
            "Mandatory access control can deny an operation even when Unix "
            "permission bits appear to allow it.",
        ),
        (
            "Mount options",
            "Filesystem mount options such as noexec, nosuid, and nodev can "
            "change security behavior.",
        ),
        (
            "Containers and namespaces",
            "Identity and filesystem views may differ from the host's "
            "perspective.",
        ),
        (
            "Network filesystems",
            "Authorization behavior can depend on server-side configuration "
            "and identity mapping.",
        ),
    ]

    for concept, explanation in limitations:
        print(f"\n{concept}")
        print(f"  {explanation}")


# =============================================================================
# SECTION 21: REAL-WORLD PERMISSION DESIGN EXAMPLE
# =============================================================================

def demonstrate_application_deployment_design() -> None:
    print("\n" + "=" * 78)
    print("SECTION 18: APPLICATION DEPLOYMENT PERMISSION DESIGN")
    print("=" * 78)

    deployment_objects = [
        LinuxObject(
            path="/srv/myapp",
            owner="deploy",
            group="myapp",
            permissions="rwxr-x---",
            object_type="directory",
        ),
        LinuxObject(
            path="/srv/myapp/application.py",
            owner="deploy",
            group="myapp",
            permissions="rw-r-----",
            object_type="file",
        ),
        LinuxObject(
            path="/srv/myapp/venv/bin/python",
            owner="deploy",
            group="myapp",
            permissions="rwxr-x---",
            object_type="executable",
        ),
        LinuxObject(
            path="/srv/myapp/secrets.env",
            owner="deploy",
            group="myapp",
            permissions="rw-------",
            object_type="file",
        ),
    ]

    for obj in deployment_objects:
        print(
            f"{obj.permissions}  owner={obj.owner:8} "
            f"group={obj.group:8} {obj.path}"
        )

    print(
        "\nDesign considerations:"
    )
    print(
        "- Service identities should receive only the permissions required "
        "to run the application."
    )
    print(
        "- Deployment identities may need controlled write access."
    )
    print(
        "- Secrets should have stricter access than ordinary application code."
    )
    print(
        "- Shared groups can simplify controlled collaboration."
    )
    print(
        "- Production permission changes should be auditable and reviewed."
    )


# =============================================================================
# SECTION 22: TROUBLESHOOTING PERMISSION DENIED
# =============================================================================

def permission_troubleshooting_steps() -> list[str]:
    """
    Return a structured troubleshooting sequence.

    Permission errors frequently result from checking only the final file while
    ignoring ownership, parent directories, groups, ACLs, or security modules.
    """
    return [
        "Identify the effective user running the process.",
        "Inspect the object's owner and group.",
        "Inspect owner, group, and others permission bits.",
        "Determine which permission class applies to the effective user.",
        "Check execute/search permission on every parent directory.",
        "Inspect supplementary group membership.",
        "Check ACLs when traditional permissions appear inconsistent.",
        "Check SELinux, AppArmor, or another mandatory access-control layer.",
        "Check mount options and filesystem behavior.",
        "Confirm the application is using the expected path.",
        "Avoid immediately applying chmod 777 as a troubleshooting shortcut.",
    ]


def demonstrate_troubleshooting() -> None:
    print("\n" + "=" * 78)
    print("SECTION 19: DEBUGGING 'PERMISSION DENIED'")
    print("=" * 78)

    for number, step in enumerate(permission_troubleshooting_steps(), start=1):
        print(f"{number}. {step}")


# =============================================================================
# SECTION 23: PYTHON FILE PERMISSIONS
# =============================================================================

def demonstrate_python_permission_operations() -> None:
    """
    Demonstrate Python interfaces to common Unix permission operations.

    The demonstration operates only on a temporary directory created by this
    script.
    """
    print("\n" + "=" * 78)
    print("SECTION 20: PYTHON AND UNIX PERMISSIONS")
    print("=" * 78)

    if os.name != "posix":
        print(
            "Permission APIs are platform-dependent. The simulation examples "
            "remain applicable."
        )
        return

    temporary_directory = Path(tempfile.mkdtemp(prefix="python_permissions_"))

    try:
        file_path = temporary_directory / "data.txt"
        file_path.write_text("permission example\n", encoding="utf-8")

        os.chmod(file_path, 0o600)

        initial_mode = stat.S_IMODE(file_path.stat().st_mode)

        print(f"Created: {file_path.name}")
        print(f"Mode after os.chmod(..., 0o600): {initial_mode:03o}")

        file_path.chmod(0o640)

        updated_mode = stat.S_IMODE(file_path.stat().st_mode)

        print(f"Mode after Path.chmod(0o640): {updated_mode:03o}")

    finally:
        shutil.rmtree(temporary_directory, ignore_errors=True)


# =============================================================================
# SECTION 24: PRODUCTION CHANGE SAFETY
# =============================================================================

def safe_permission_change_plan(
    path: str,
    current_mode: str,
    proposed_mode: str,
    reason: str,
) -> Dict[str, str]:
    """
    Build a conceptual permission-change record.

    Production systems benefit from recording:

        - target
        - current state
        - proposed state
        - business/technical reason

    A real change workflow may also include:

        - backup
        - approval
        - staging validation
        - deployment automation
        - rollback plan
        - post-change verification
    """
    current_symbolic = octal_to_symbolic(current_mode)
    proposed_symbolic = octal_to_symbolic(proposed_mode)

    return {
        "path": path,
        "current_mode": str(current_mode),
        "current_symbolic": current_symbolic,
        "proposed_mode": str(proposed_mode),
        "proposed_symbolic": proposed_symbolic,
        "reason": reason,
    }


def demonstrate_production_change_design() -> None:
    print("\n" + "=" * 78)
    print("SECTION 21: PRODUCTION PERMISSION CHANGES")
    print("=" * 78)

    plan = safe_permission_change_plan(
        path="/srv/myapp/secrets.env",
        current_mode="644",
        proposed_mode="600",
        reason="Restrict sensitive configuration to the owning account.",
    )

    for key, value in plan.items():
        print(f"{key:18}: {value}")


# =============================================================================
# SECTION 25: COMPARING PERMISSION STRATEGIES
# =============================================================================

def demonstrate_permission_strategy_comparison() -> None:
    print("\n" + "=" * 78)
    print("SECTION 22: PERMISSION STRATEGY COMPARISON")
    print("=" * 78)

    comparison = [
        (
            "Owner-only access",
            "Simple and restrictive.",
            "Private keys, secrets, personal configuration.",
        ),
        (
            "Shared group access",
            "Efficient for controlled collaboration.",
            "Application teams and shared service directories.",
        ),
        (
            "Others permissions",
            "Broad and simple but less restrictive.",
            "Public read-only data and globally executable programs.",
        ),
        (
            "ACLs",
            "Fine-grained but more complex to audit.",
            "Exceptions requiring named users or additional groups.",
        ),
        (
            "sudo policy",
            "Controls privileged command execution.",
            "Administrative operations requiring elevated rights.",
        ),
    ]

    for strategy, tradeoff, use_case in comparison:
        print(f"\nStrategy: {strategy}")
        print(f"Trade-off: {tradeoff}")
        print(f"Typical use: {use_case}")


# =============================================================================
# SECTION 26: UNIT TESTS
# =============================================================================

class PermissionModelTests(unittest.TestCase):
    def test_triplet_to_number(self) -> None:
        self.assertEqual(permission_triplet_to_number("rwx"), 7)
        self.assertEqual(permission_triplet_to_number("rw-"), 6)
        self.assertEqual(permission_triplet_to_number("r-x"), 5)
        self.assertEqual(permission_triplet_to_number("---"), 0)

    def test_number_to_triplet(self) -> None:
        self.assertEqual(number_to_permission_triplet(7), "rwx")
        self.assertEqual(number_to_permission_triplet(6), "rw-")
        self.assertEqual(number_to_permission_triplet(5), "r-x")
        self.assertEqual(number_to_permission_triplet(0), "---")

    def test_octal_conversion(self) -> None:
        self.assertEqual(octal_to_symbolic("755"), "rwxr-xr-x")
        self.assertEqual(octal_to_symbolic("640"), "rw-r-----")
        self.assertEqual(symbolic_to_octal("rw-r-----"), "640")

    def test_owner_permissions_take_precedence(self) -> None:
        user = LinuxUser(
            "alice",
            1001,
            "engineering",
            frozenset({"developers"}),
        )

        obj = LinuxObject(
            "/data/example",
            "alice",
            "developers",
            "rw-rw-r--",
        )

        self.assertEqual(determine_permission_class(user, obj), "owner")
        self.assertEqual(permissions_for_user(user, obj), "rw-")

    def test_group_permissions(self) -> None:
        user = LinuxUser(
            "bob",
            1002,
            "engineering",
            frozenset({"developers"}),
        )

        obj = LinuxObject(
            "/data/example",
            "alice",
            "developers",
            "rw-r-----",
        )

        self.assertEqual(determine_permission_class(user, obj), "group")
        self.assertTrue(can_read(user, obj))
        self.assertFalse(can_write(user, obj))

    def test_others_permissions(self) -> None:
        user = LinuxUser("charlie", 1003, "sales")

        obj = LinuxObject(
            "/data/example",
            "alice",
            "developers",
            "rw-r-----",
        )

        self.assertEqual(determine_permission_class(user, obj), "others")
        self.assertFalse(can_read(user, obj))

    def test_numeric_chmod(self) -> None:
        obj = LinuxObject(
            "/tmp/example",
            "alice",
            "developers",
            "rw-------",
        )

        chmod_numeric(obj, 755)

        self.assertEqual(obj.permissions, "rwxr-xr-x")

    def test_symbolic_chmod(self) -> None:
        obj = LinuxObject(
            "/tmp/example",
            "alice",
            "developers",
            "rw-r-----",
        )

        chmod_symbolic(obj, "g", "+", "w")
        self.assertEqual(obj.permissions, "rw-rw----")

        chmod_symbolic(obj, "o", "=", "r")
        self.assertEqual(obj.permissions, "rw-rw-r--")

    def test_umask(self) -> None:
        self.assertEqual(apply_umask(0o666, 0o022), 0o644)
        self.assertEqual(apply_umask(0o777, 0o022), 0o755)
        self.assertEqual(apply_umask(0o666, 0o077), 0o600)

    def test_special_permissions(self) -> None:
        self.assertEqual(
            mode_to_symbolic_with_special_bits(0o4755),
            "rwsr-xr-x",
        )

        self.assertEqual(
            mode_to_symbolic_with_special_bits(0o1777),
            "rwxrwxrwt",
        )

    def test_acl_mask(self) -> None:
        user = LinuxUser("diana", 1004, "analytics")

        obj = LinuxObject(
            "/srv/restricted",
            "alice",
            "engineering",
            "rw-r-----",
        )

        acl = SimpleACL(
            named_user_permissions={"diana": "rw-"},
            mask="r--",
        )

        self.assertEqual(
            acl.effective_user_permissions(user, obj),
            "r--",
        )


# =============================================================================
# SECTION 27: OPTIONAL REAL SYSTEM COMMAND DISPLAY
# =============================================================================

def demonstrate_common_commands() -> None:
    """
    Display common commands without executing privileged modifications.
    """
    print("\n" + "=" * 78)
    print("SECTION 23: COMMON LINUX COMMAND STRUCTURES")
    print("=" * 78)

    commands = [
        (
            "View permissions",
            "ls -l filename",
        ),
        (
            "View numeric permissions",
            "stat -c '%a %U %G %n' filename",
        ),
        (
            "Numeric chmod",
            "chmod 640 filename",
        ),
        (
            "Add owner execute",
            "chmod u+x filename",
        ),
        (
            "Remove others write",
            "chmod o-w filename",
        ),
        (
            "Change owner",
            "chown username filename",
        ),
        (
            "Change owner and group",
            "chown username:groupname filename",
        ),
        (
            "Change group",
            "chgrp groupname filename",
        ),
        (
            "Run permitted command with elevation",
            "sudo command",
        ),
    ]

    for purpose, command in commands:
        print(f"{purpose:30} {command}")


# =============================================================================
# SECTION 28: RUNNING THE COMPLETE STUDY DEMONSTRATION
# =============================================================================

def run_study_guide() -> None:
    print("=" * 78)
    print("LINUX PERMISSIONS STUDY SCRIPT")
    print("=" * 78)

    demonstrate_permission_basics()
    demonstrate_user_group_access()
    explain_directory_permissions()
    demonstrate_chmod()
    demonstrate_chown()
    demonstrate_sudo()
    demonstrate_special_permissions()
    demonstrate_umask()
    demonstrate_symbolic_links()
    demonstrate_permission_errors()
    demonstrate_directory_access()
    demonstrate_security_mistakes()
    demonstrate_permission_design()
    demonstrate_real_filesystem_metadata()
    demonstrate_acl_concepts()
    demonstrate_permission_audit()
    demonstrate_permission_model_limitations()
    demonstrate_application_deployment_design()
    demonstrate_troubleshooting()
    demonstrate_python_permission_operations()
    demonstrate_production_change_design()
    demonstrate_permission_strategy_comparison()
    demonstrate_common_commands()

    print("\n" + "=" * 78)
    print("TESTING PERMISSION MODEL IMPLEMENTATIONS")
    print("=" * 78)

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(
        PermissionModelTests
    )

    result = unittest.TextTestRunner(verbosity=2).run(suite)

    if result.wasSuccessful():
        print("\nAll permission-model tests passed.")
    else:
        print("\nOne or more permission-model tests failed.")


if __name__ == "__main__":
    run_study_guide()
