# Linux Permissions: Users, Groups, `chmod`, `chown`, `sudo`, and the Linux Permissions Model

## Introduction

Linux is a multi-user operating system in which files, directories, processes, and system services operate under user and group identities. The permissions model controls which identities are allowed to read, modify, execute, search, traverse, create, or remove filesystem objects.

The traditional Linux permissions system is based on three permission classes:

- Owner or user
- Group
- Others

Each class can receive combinations of:

- Read
- Write
- Execute

The Python script accompanying this document develops the Linux permissions model from its basic numeric representation to more advanced topics such as directory semantics, privilege elevation, special permission bits, umask behavior, access control lists, permission auditing, and production security design.

The script primarily simulates permission decisions so that the examples can be executed without changing the user's actual system configuration.

---

# Fundamental Permission Model

Every ordinary filesystem object has ownership information and permission bits.

Conceptually, an object can be represented as:

    owner
    group
    owner permissions
    group permissions
    others permissions

A common permission string is:

    rwxr-xr--

The nine characters are divided into three groups:

    rwx | r-x | r--

The first group applies to the owner, the second group applies to users belonging to the object's group, and the third group applies to everyone else.

The permissions are:

| Symbol | Numeric Value | Meaning for Files |
|---|---:|---|
| `r` | 4 | Read the file contents |
| `w` | 2 | Modify the file contents |
| `x` | 1 | Execute the file as a program |

Permissions are represented numerically by adding these values.

For example:

    rwx = 4 + 2 + 1 = 7
    rw- = 4 + 2     = 6
    r-x = 4     + 1 = 5
    r-- = 4         = 4
    -wx =     2 + 1 = 3
    --x =         1 = 1
    --- =             0

The script implements conversion between symbolic and numeric permission representations.

---

# Numeric and Octal Permissions

Linux permission modes are commonly written using three octal digits.

Examples include:

| Mode | Symbolic Form |
|---|---|
| `000` | `---------` |
| `400` | `r--------` |
| `600` | `rw-------` |
| `640` | `rw-r-----` |
| `644` | `rw-r--r--` |
| `700` | `rwx------` |
| `750` | `rwxr-x---` |
| `755` | `rwxr-xr-x` |
| `777` | `rwxrwxrwx` |

The three digits correspond to:

    owner | group | others

Therefore:

    755

means:

    owner  = 7 = rwx
    group  = 5 = r-x
    others = 5 = r-x

which produces:

    rwxr-xr-x

The script provides functions that convert:

    rwxr-xr-x -> 755

and:

    755 -> rwxr-xr-x

These conversions are useful for understanding how `chmod` interprets numeric modes.

---

# Users and Groups

Linux identities are represented by users and groups.

A user normally has:

- A username
- A numeric user identifier called a UID
- A primary group
- Zero or more supplementary groups

A group has a numeric group identifier called a GID and can contain multiple users.

Groups provide a scalable authorization mechanism. Instead of granting access individually to many users, an administrator can assign a file to a group and grant that group the required permissions.

For example:

    Owner: alice
    Group: developers
    Permissions: rw-r-----

The effective access is determined by the relationship between the accessing user and the object.

The permission selection process is:

1. If the user is the owner, Linux uses the owner permission bits.
2. Otherwise, if the user belongs to the object's group, Linux uses the group permission bits.
3. Otherwise, Linux uses the others permission bits.

A critical rule is that these permission classes are not merged.

Suppose:

    owner  = rw-
    group  = r--
    others = rwx

If the user is the owner, the owner permissions are selected. Linux does not combine the owner, group, and others permissions to give the user the broadest available access.

The script demonstrates this selection process using simulated `LinuxUser` and `LinuxObject` classes.

---

# Reading, Writing, and Executing

For regular files, the three standard permissions have the following meanings.

## Read

Read permission allows the file contents to be read.

Examples include:

- Viewing a text file
- Reading configuration data
- Loading data from a file

## Write

Write permission allows modification of file contents.

Depending on the operation and filesystem behavior, this may involve:

- Changing file contents
- Truncating a file
- Updating application data

The ability to delete a file is primarily controlled by permissions on the containing directory rather than by write permission on the file itself.

This distinction is important in Linux permission debugging.

## Execute

Execute permission allows a file to be executed as a program.

For shell scripts and native binaries, execution also depends on other factors, including the file format, interpreter availability, mount options, and system security policy.

---

# Directory Permissions

Directory permissions use the same symbols but have different semantics.

| Permission | Meaning for Directories |
|---|---|
| `r` | Read directory entries or list names |
| `w` | Modify directory entries |
| `x` | Traverse or search the directory |

The execute permission on directories is particularly important.

A user may need execute permission on every relevant parent directory in order to reach a file.

For example, a file may itself be readable, but access can still fail if a parent directory cannot be traversed.

A directory with:

    r-x

allows listing and traversal but generally does not permit creating or removing entries.

A directory with:

    --x

may permit traversal when the user already knows the name of an entry, while preventing the user from listing all directory entries.

A common permission debugging mistake is inspecting only the target file and ignoring the permissions of its parent directories.

---

# `chmod`

The `chmod` command changes permission bits.

The name originates from "change mode."

There are two major styles of usage.

## Numeric Mode

A numeric mode directly specifies owner, group, and others permissions.

Example:

    chmod 640 filename

The resulting permissions are:

    rw-r-----

This means:

- Owner can read and write
- Group can read
- Others have no access

## Symbolic Mode

Symbolic mode modifies selected permission classes.

The main permission classes are:

- `u` for owner
- `g` for group
- `o` for others
- `a` for all classes

The main operators are:

- `+` to add permissions
- `-` to remove permissions
- `=` to assign permissions exactly

Examples:

    chmod u+x filename

Adds execute permission to the owner.

    chmod g-w filename

Removes write permission from the group.

    chmod o=r filename

Sets others permissions exactly to read.

    chmod a-w filename

Removes write permission from owner, group, and others.

The script implements a simulation of numeric and symbolic `chmod` behavior.

---

# `chown` and Group Ownership

The `chown` command changes ownership.

Conceptually:

    chown alice filename

changes the owner to `alice`.

Ownership and group can also be changed together.

Conceptually:

    chown alice:developers filename

changes:

- Owner to `alice`
- Group to `developers`

A group-only ownership change is conceptually represented by:

    chown :developers filename

The `chgrp` command changes group ownership.

Ordinary users are restricted in how they may change ownership. Administrative authorization is usually required to arbitrarily assign ownership to another user.

The script simulates ownership changes without modifying actual system ownership.

---

# Permission Decision Logic

The script implements the central Linux permission selection model.

Given a user and object:

1. Compare the username with the object's owner.
2. If the usernames match, use owner permissions.
3. Otherwise, inspect the user's primary and supplementary groups.
4. If the object group matches one of the user's groups, use group permissions.
5. Otherwise, use others permissions.

The selected permission triplet is then evaluated for the requested operation.

For example:

    Object permissions: rw-r-----
    Owner: alice
    Group: developers

If Alice accesses the file, the owner permissions apply:

    rw-

If Bob belongs to `developers`, the group permissions apply:

    r--

If Charlie belongs to neither the owner identity nor the group:

    ---

applies.

The script implements simulated read, write, and execute checks and raises an access-denied exception when an operation is not permitted.

---

# `sudo` and Privilege Elevation

Linux systems often separate ordinary user activity from administrative operations.

The root account traditionally has UID 0 and broad system privileges.

The `sudo` mechanism allows controlled privilege elevation.

A typical conceptual use is:

    sudo command

This does not necessarily mean that the user receives unrestricted administrative control.

A `sudo` policy can control:

- Which users may use `sudo`
- Which groups may use it
- Which commands are authorized
- Which target identities can be used
- Whether authentication is required
- Which environment values are preserved or restricted

A secure policy follows the principle of least privilege.

For example, allowing a user to restart one specific service is substantially more restrictive than granting unrestricted access to an administrative shell.

The script contains a simplified `SudoPolicy` class demonstrating command-specific authorization.

Real `sudo` configuration has a richer policy language and should be managed carefully because configuration errors can create privilege-escalation paths.

---

# Special Permission Bits

Linux provides three important special permission bits.

| Special Bit | Leading Octal Value |
|---|---:|
| setuid | `4` |
| setgid | `2` |
| sticky bit | `1` |

These values occupy a fourth octal position.

## setuid

An executable with setuid may run with an effective user identity associated with the executable owner.

A typical symbolic representation may contain:

    s

in the owner's execute position.

Example:

    4755

which may appear symbolically as:

    rwsr-xr-x

Setuid programs require careful security review. A vulnerability in a privileged executable can become a privilege-escalation vulnerability.

## setgid

Setgid can apply differently to executables and directories.

For executables, it can affect the effective group identity of a process.

For directories, it is commonly used for collaborative directories so that newly created objects inherit the directory's group.

Example:

    2755

The script demonstrates how special bits are represented symbolically.

## Sticky Bit

The sticky bit is commonly used on shared writable directories.

A classic example is conceptually:

    1777

which may appear as:

    rwxrwxrwt

The sticky bit helps prevent users from deleting or renaming arbitrary entries owned by other users in a shared writable directory.

---

# Umask

The umask controls which permissions are removed from the permissions requested during object creation.

A conceptual formula is:

    final_mode = requested_mode AND NOT umask

Typical requested modes are:

    Regular files: 666
    Directories:    777

Regular files normally do not request execute permission during ordinary creation.

With:

    umask 022

a regular file requested with `666` becomes:

    644

A directory requested with `777` becomes:

    755

With:

    umask 077

a regular file becomes:

    600

and a directory becomes:

    700

The script implements an `apply_umask` function and demonstrates several common scenarios.

---

# Symbolic Links

A symbolic link contains a reference to another filesystem path.

A symbolic link is not equivalent to an ordinary file containing a copy of the target's contents.

When a symbolic link is accessed, the system commonly resolves the link and performs access checks against the target.

Permission behavior involving symbolic links requires care during recursive administrative operations.

Administrators must understand whether a command follows symbolic links or operates on the link itself.

Recursive ownership and permission operations can be dangerous when their traversal behavior is misunderstood.

---

# Access Control Lists

Traditional Linux permissions provide only three broad classes:

- Owner
- Group
- Others

This is simple and efficient but sometimes insufficient.

Access Control Lists, commonly called ACLs, provide more granular authorization.

An ACL may grant additional permissions to:

- Named users
- Named groups

ACLs can also include a mask that limits effective permissions for certain entries.

The script includes a simplified ACL model.

For example, a named user may be granted:

    rw-

but an ACL mask of:

    r--

can reduce the effective permission to:

    r--

ACL behavior is more complex than traditional permission bits, so permission auditing must consider both the standard mode and ACL entries.

---

# Permission Denied Errors

A permission error should not automatically be solved by making the object world-writable.

A systematic debugging process is safer.

The script identifies a structured sequence:

1. Identify the effective user running the process.
2. Inspect the target object's owner and group.
3. Inspect owner, group, and others permissions.
4. Determine which permission class applies.
5. Inspect execute permission on parent directories.
6. Check supplementary group membership.
7. Inspect ACLs.
8. Inspect mandatory access-control systems.
9. Inspect mount options.
10. Confirm the application is using the expected path.
11. Avoid using `chmod 777` as a default troubleshooting response.

Permission problems can also result from service configuration.

For example, an application may be expected to run as one user but may actually run as a dedicated service account with different group memberships.

---

# Common Security Mistakes

## Using `chmod 777` Without Analysis

Mode `777` grants read, write, and execute permissions to all users.

For a directory, broad write permission can allow unrelated users to create, remove, or rename entries.

For executable files, broad write permission is particularly dangerous because another user may be able to modify code executed by a privileged service.

## World-Readable Secrets

Sensitive files should not be readable by unrelated users.

Examples include:

- Private keys
- API credentials
- Authentication tokens
- Password files
- Secret configuration files

Private configuration commonly requires restrictive modes such as:

    600

or a carefully designed owner and group model.

## Excessive `sudo` Access

A user who needs to run one administrative command should not automatically receive unrestricted administrative shell access.

Narrow command authorization is easier to audit and reduces the attack surface.

## Incorrect Group Design

Shared applications often fail because group ownership and service identities are not designed consistently.

A deployment account may create files that the runtime service account cannot read, or a service may create files that administrators cannot safely manage.

A consistent ownership model is important.

## Ignoring Directory Traversal

A readable file may remain inaccessible if a parent directory lacks execute permission for the relevant identity.

## Unsafe Special-Permission Executables

Setuid and setgid executables require strict control over:

- Ownership
- Write permissions
- Input validation
- Executed paths
- Environment handling
- Temporary files
- Library loading behavior

---

# Permission Auditing

The script implements a simplified permission audit.

It identifies examples such as:

- Regular files writable by others
- Directories writable by others
- Executables writable by others
- Objects using mode `777`

A real audit must consider context.

A world-writable temporary directory may be intentional when combined with sticky-bit protection.

A simple numeric rule is therefore not always sufficient to determine whether a configuration is secure.

Real permission audits may also need to inspect:

- ACLs
- Linux capabilities
- SELinux
- AppArmor
- Mount options
- Containers
- Namespaces
- Service accounts
- Network filesystem behavior

The purpose of auditing is to identify conditions requiring investigation rather than blindly changing every broad permission.

---

# Traditional Permissions and Advanced Security Layers

Traditional Unix mode bits are only one layer of Linux access control.

## ACLs

ACLs provide named user and group permissions beyond the owner/group/others model.

## Linux Capabilities

Capabilities allow some privileged operations to be separated from unrestricted root privileges.

This can support more precise privilege design.

## SELinux and AppArmor

Mandatory access-control systems can restrict operations even when traditional Unix permissions appear to allow them.

A process may therefore receive a permission denial despite apparently correct `chmod` and `chown` settings.

## Mount Options

Filesystem mount options can affect behavior.

Examples include:

- `noexec`
- `nosuid`
- `nodev`

These options can provide additional restrictions.

## Containers and Namespaces

Container environments can change how identities and filesystem resources are viewed.

A UID inside a container may not have the same meaning or privilege relationship as a UID on the host.

## Network Filesystems

Network filesystems can introduce server-side authorization and identity mapping.

Permission troubleshooting may therefore require investigation beyond local mode bits.

---

# Least Privilege Design

The principle of least privilege means granting only the permissions necessary for a user, process, or service to perform its required tasks.

A practical permission design begins by identifying:

- Which identities require access
- Which resources they require
- Whether they need read access
- Whether they need write access
- Whether they need execute access
- Whether access is temporary or persistent

For an application:

- A deployment identity may need write access to application files.
- A runtime service may need read and execute access.
- A logging process may need write access only to a logging directory.
- Secrets may need stricter access than application source files.

Linux groups can often express these requirements more cleanly than granting broad permissions to all users.

---

# Production Permission Design

Production systems should treat permission changes as controlled configuration changes.

A permission change record can include:

- Target path
- Current mode
- Current symbolic representation
- Proposed mode
- Proposed symbolic representation
- Reason for the change

The script demonstrates a structured permission change plan.

Production workflows may also require:

- Configuration review
- Approval
- Staging validation
- Backup
- Automated deployment
- Rollback planning
- Post-change verification
- Audit logging

Recursive permission changes require particular care because a single broad command can unintentionally alter large portions of a filesystem tree.

---

# Python and Unix Permissions

Python provides several interfaces for working with Unix filesystem permissions.

The script demonstrates safe use of temporary files with:

- `os.chmod`
- `Path.chmod`
- `stat`
- `os.stat`

The `stat` module provides useful utilities for:

- Extracting permission bits
- Displaying symbolic modes
- Identifying special permission bits

The script uses:

    stat.S_IMODE(...)

to isolate the ordinary permission mode from filesystem metadata.

It uses:

    stat.filemode(...)

to produce a human-readable symbolic representation.

The real filesystem demonstrations operate only on temporary directories created by the script and remove those directories after execution.

---

# Permission Strategy Comparison

Different permission mechanisms solve different authorization problems.

| Strategy | Strength | Trade-Off |
|---|---|---|
| Owner-only access | Simple and restrictive | Limited collaboration |
| Shared group access | Efficient for teams and services | Requires group management |
| Others permissions | Simple public access | Broad authorization |
| ACLs | Fine-grained access | Greater complexity |
| `sudo` policy | Controlled administrative execution | Requires careful policy design |

The best choice depends on the resource, the identities involved, and the security requirements.

---

# Practical Application Design

A typical application deployment may contain several categories of objects.

## Application Directory

The directory may need controlled traversal and access for deployment and runtime identities.

## Application Code

The runtime process usually needs read access and, where appropriate, execute access.

The runtime identity should not necessarily have permission to modify production code.

## Secrets

Secret files should usually be more restrictive than ordinary application files.

A common pattern is owner-only access when no shared service identity requires the secret.

## Shared Runtime Directories

Directories used for sockets, temporary files, uploads, or logs may require carefully designed group ownership.

The permissions should allow required service operations without making the directory broadly writable.

---

# Performance Considerations

Traditional Unix permission checks are relatively lightweight and integrated into filesystem access operations.

Performance concerns usually arise more from permission architecture than from the basic mode-bit check itself.

Examples include:

- Large ACL configurations
- Network filesystem authorization
- Distributed identity lookups
- Mandatory access-control policy evaluation
- Large recursive permission operations

Recursive permission changes can be expensive on large directory trees because every object must be visited and modified.

They can also create operational problems when symbolic links, mounted filesystems, generated files, or service-owned files are included unintentionally.

---

# Security Considerations

Permission configuration is part of the system's security boundary.

Important practices include:

- Restrict secrets to required identities.
- Avoid unnecessary world-writable files.
- Prevent untrusted users from modifying privileged executables.
- Use groups for controlled collaboration.
- Use narrow `sudo` authorization.
- Review setuid and setgid executables carefully.
- Inspect parent directories when diagnosing access failures.
- Consider ACLs and mandatory access-control systems.
- Verify mount options for sensitive workloads.
- Record and review production permission changes.

Permissions should be designed according to actual access requirements rather than convenience.

---

# Testing the Permission Model

The Python script includes unit tests for its simulated permission logic.

The tests verify:

- Symbolic-to-numeric conversion
- Numeric-to-symbolic conversion
- Octal mode conversion
- Owner permission precedence
- Group access
- Others access
- Numeric `chmod`
- Symbolic `chmod`
- Umask calculations
- Special permission formatting
- ACL mask behavior

Testing permission logic is useful because authorization code can fail in subtle ways.

An incorrect rule that combines owner and group permissions, for example, may grant access that the actual Linux model would deny.

---

# Running the Script

Save the Python content as a file with a `.py` extension and execute it with a Python 3 interpreter.

The script is self-contained and uses only the Python standard library.

The execution includes:

- Permission conversion demonstrations
- User and group access simulations
- Directory permission behavior
- Numeric and symbolic `chmod` examples
- Ownership simulations
- Simplified `sudo` policy checks
- Special permission bit demonstrations
- Umask calculations
- ACL concepts
- Permission auditing
- Real temporary-file metadata demonstrations where supported
- Troubleshooting logic
- Unit tests

The real filesystem examples create temporary files and directories and remove them after the demonstrations complete.
