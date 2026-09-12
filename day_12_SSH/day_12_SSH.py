"""
SSH: Architecture, Keys, ssh-agent, scp, and rsync
===================================================

A self-contained study script covering SSH from absolute beginner concepts
through practical and advanced administration, automation, security, and
performance topics.

The examples are designed to be safe to study locally. Commands that would
contact another machine are represented as strings or executed only when the
user explicitly enables the relevant demonstration.

Requirements:
    Python 3.9+
    Standard library only.

Suggested study order:
    1. SSH fundamentals and architecture
    2. Authentication and host verification
    3. SSH keys
    4. ssh-agent
    5. Configuration
    6. scp
    7. rsync
    8. Security
    9. Automation
    10. Advanced architecture and troubleshooting
"""

from __future__ import annotations

import base64
import getpass
import hashlib
import os
import platform
import secrets
import shlex
import socket
import stat
import subprocess
import tempfile
import textwrap
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


# =============================================================================
# SECTION 1: SSH FUNDAMENTALS
# =============================================================================

def print_section(title: str) -> None:
    """Print a consistent study-section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def explain_ssh_architecture() -> None:
    print_section("1. SSH architecture")

    print(
        """
SSH means Secure Shell. It is a network protocol used to securely communicate
with another computer over an untrusted network.

The most common SSH workflow is:

    SSH client
        |
        | TCP connection, normally destination port 22
        v
    SSH server
        |
        +--> host-key verification
        |
        +--> user authentication
        |
        +--> encrypted session
        |
        +--> command execution / shell / subsystem / forwarding

Important terminology:

    Client
        The machine initiating the SSH connection.

    Server
        The machine running an SSH daemon and accepting connections.

    ssh
        The OpenSSH client program.

    sshd
        The OpenSSH server daemon.

    Host key
        A cryptographic identity belonging to the SSH server.

    User key
        A client-side authentication key pair used to authenticate a user.

    Public key
        The shareable half of an asymmetric key pair.

    Private key
        The secret half. It must remain protected.

    ssh-agent
        A local process that securely keeps private keys available for
        authentication without repeatedly entering their passphrases.

    scp
        A command-line file-copy mechanism using SSH transport.

    rsync
        A synchronization tool that efficiently transfers changed data.
        It commonly uses SSH as its transport.

The security model has two separate identity questions:

    1. "Am I really talking to the intended server?"
       -> server host-key verification.

    2. "Is this user allowed to log in?"
       -> user authentication.

These are related but not the same thing.
"""
    )


# =============================================================================
# SECTION 2: BASIC SSH COMMAND CONSTRUCTION
# =============================================================================

def build_ssh_command(
    username: str,
    hostname: str,
    port: int = 22,
    identity_file: Optional[str] = None,
    command: Optional[str] = None,
) -> list[str]:
    """
    Build an SSH command without executing it.

    Keeping command construction separate from execution is useful for:
    - testing
    - logging
    - reviewing commands
    - automation
    """
    args = ["ssh"]

    if port != 22:
        args.extend(["-p", str(port)])

    if identity_file:
        args.extend(["-i", identity_file])

    destination = f"{username}@{hostname}"
    args.append(destination)

    if command:
        args.append(command)

    return args


def demonstrate_basic_ssh_commands() -> None:
    print_section("2. Basic SSH commands")

    examples = [
        build_ssh_command("alice", "server.example.com"),
        build_ssh_command("alice", "server.example.com", port=2222),
        build_ssh_command(
            "alice",
            "server.example.com",
            identity_file="~/.ssh/id_ed25519",
        ),
        build_ssh_command(
            "alice",
            "server.example.com",
            command="uname -a",
        ),
    ]

    for command in examples:
        print("$", shlex.join(command))

    print(
        """
Common patterns:

    ssh user@host
        Open an interactive remote shell.

    ssh -p 2222 user@host
        Connect to a non-default SSH port.

    ssh -i ~/.ssh/id_ed25519 user@host
        Select a particular private key.

    ssh user@host "command"
        Execute one remote command.

The command syntax can be thought of as:

    ssh [options] [user@]hostname [remote-command]

Do not confuse the SSH server port with the remote user's shell port.
SSH itself is a protocol transported over TCP. Port 22 is merely the default
TCP listening port conventionally used by SSH servers.
"""
    )


# =============================================================================
# SECTION 3: CONNECTION LAYERS AND HANDSHAKE
# =============================================================================

def explain_connection_handshake() -> None:
    print_section("3. SSH connection establishment")

    print(
        """
A simplified SSH connection lifecycle is:

    TCP connection
        |
        v
    SSH protocol version exchange
        |
        v
    Algorithm negotiation
        |
        v
    Key exchange
        |
        v
    Server host-key verification
        |
        v
    User authentication
        |
        v
    Encrypted session
        |
        +--> interactive shell
        +--> remote command
        +--> file transfer subsystem
        +--> port forwarding
        +--> other channels

The actual protocol is more sophisticated than this simplified diagram.

SSH provides confidentiality, integrity, and authentication mechanisms.

Confidentiality:
    Data is encrypted so network observers cannot normally read the session.

Integrity:
    Cryptographic mechanisms detect unauthorized modification.

Authentication:
    The server can authenticate itself using a host key, and the user can
    authenticate using passwords, public keys, certificates, or other methods.

A critical security distinction:

    Encryption != authentication

A connection can be encrypted while authentication is still improperly
configured. Host-key verification exists specifically to prevent a client
from silently trusting an unintended server.
"""
    )


# =============================================================================
# SECTION 4: CRYPTOGRAPHIC KEY TYPES
# =============================================================================

@dataclass
class KeyAlgorithm:
    name: str
    purpose: str
    recommendation: str


def explain_key_algorithms() -> None:
    print_section("4. SSH cryptographic algorithms")

    algorithms = [
        KeyAlgorithm(
            "Ed25519",
            "Modern public-key signature algorithm",
            "Excellent default for most new OpenSSH user keys",
        ),
        KeyAlgorithm(
            "ECDSA",
            "Elliptic-curve public-key algorithm",
            "Supported widely, though Ed25519 is often preferred for new keys",
        ),
        KeyAlgorithm(
            "RSA",
            "Traditional public-key algorithm",
            "Still widely deployed; use an adequate key size and modern SSH",
        ),
        KeyAlgorithm(
            "DSA",
            "Older public-key algorithm",
            "Obsolete and should not be used",
        ),
    ]

    for algorithm in algorithms:
        print(f"\n{algorithm.name}")
        print(f"  Purpose:       {algorithm.purpose}")
        print(f"  Guidance:      {algorithm.recommendation}")

    print(
        """
A key pair consists of:

    private key
        Secret material.

    public key
        Material intended to be distributed to systems that need to verify
        signatures produced by the corresponding private key.

The private key does not need to be copied to the server for normal
public-key authentication.

Typical flow:

    Client:
        private key + authentication operation

    Server:
        authorized public key

    Result:
        server verifies proof that the client possesses the private key.

This is fundamentally different from sending the private key to the server.
"""
    )


# =============================================================================
# SECTION 5: SSH KEY GENERATION
# =============================================================================

def explain_key_generation() -> None:
    print_section("5. SSH key generation")

    commands = [
        "ssh-keygen -t ed25519 -C 'user@example.com'",
        "ssh-keygen -t rsa -b 4096 -C 'user@example.com'",
        "ssh-keygen -lf ~/.ssh/id_ed25519.pub",
        "ssh-keygen -y -f ~/.ssh/id_ed25519",
    ]

    print("Typical commands:")
    for command in commands:
        print("  ", command)

    print(
        """
The most important conceptual command is:

    ssh-keygen -t ed25519

The generated pair commonly resembles:

    ~/.ssh/id_ed25519
    ~/.ssh/id_ed25519.pub

The exact filenames depend on the options selected.

The private key should normally be protected by:

    1. operating-system file permissions
    2. a strong passphrase
    3. careful handling and backup procedures

The public key is the one normally installed into:

    ~/.ssh/authorized_keys

on the remote account.

Never treat the .pub file as equivalent to the private key.
"""
    )


def inspect_key_permissions(path: Path) -> None:
    """Display Unix-style permission information where available."""
    try:
        mode = path.stat().st_mode
    except OSError as exc:
        print(f"Unable to inspect {path}: {exc}")
        return

    print(f"{path}: {stat.filemode(mode)}")


def demonstrate_secure_file_permissions() -> None:
    print_section("6. SSH file permissions")

    with tempfile.TemporaryDirectory() as directory:
        private_key = Path(directory) / "id_ed25519"
        public_key = Path(directory) / "id_ed25519.pub"

        private_key.write_text("SIMULATED PRIVATE KEY MATERIAL\n", encoding="utf-8")
        public_key.write_text("SIMULATED PUBLIC KEY MATERIAL\n", encoding="utf-8")

        # 0600 means owner read/write only.
        private_key.chmod(0o600)

        # 0644 is commonly acceptable for public information.
        public_key.chmod(0o644)

        inspect_key_permissions(private_key)
        inspect_key_permissions(public_key)

    print(
        """
Typical Unix permissions:

    ~/.ssh/
        often 0700

    private key
        commonly 0600

    public key
        commonly 0644

    authorized_keys
        commonly 0600

Actual requirements can vary with operating system and SSH configuration.

Permissions that are too open can cause OpenSSH to reject a key or create a
security exposure.
"""
    )


# =============================================================================
# SECTION 7: AUTHORIZED_KEYS
# =============================================================================

def explain_authorized_keys() -> None:
    print_section("7. authorized_keys")

    print(
        """
A server can permit public-key authentication using:

    ~/.ssh/authorized_keys

Each authorized public key is normally represented on one logical line.

Conceptually:

    client private key
            |
            | proves possession
            v
    server's authorized_keys
            |
            v
    matching public key
            |
            v
        authentication accepted

The server does not need the client's private key.

A key can also carry restrictions. Depending on configuration, authorized_keys
entries can use options that restrict behavior such as:

    command=
    from=
    no-agent-forwarding
    no-port-forwarding
    no-pty
    no-user-rc
    restrict

These controls are especially useful for automation accounts.

Example conceptual restricted key:

    restrict,command="/usr/local/bin/deploy" ssh-ed25519 AAAA...

The exact authorization design should be tested carefully before production
deployment.
"""
    )


# =============================================================================
# SECTION 8: HOST KEY VERIFICATION
# =============================================================================

def explain_host_keys() -> None:
    print_section("8. Server host keys and known_hosts")

    print(
        """
Host keys answer:

    "Is this the server I intended to connect to?"

The SSH client commonly stores previously accepted host identities in:

    ~/.ssh/known_hosts

On the first connection, SSH may display a fingerprint and ask whether the
host should be trusted.

The secure practice is to verify the fingerprint through a trusted channel
before accepting it.

Why this matters:

    Without host verification, an attacker could potentially place a malicious
    SSH endpoint between the client and intended server.

Important files:

    /etc/ssh/ssh_host_*_key
        Server host private keys.

    /etc/ssh/ssh_host_*_key.pub
        Corresponding host public keys.

    ~/.ssh/known_hosts
        Client-side records of trusted server host keys.

Do not casually delete or bypass host-key verification just because a warning
appeared.

A changed host key may be legitimate, for example after:
    - server reinstallation
    - host migration
    - replacement of host keys

It may also indicate:
    - DNS/IP misdirection
    - a compromised system
    - a man-in-the-middle attempt

The correct response is verification, not blind acceptance.
"""
    )


# =============================================================================
# SECTION 9: SSH CONFIGURATION
# =============================================================================

@dataclass
class SSHHostConfig:
    alias: str
    hostname: str
    user: str
    port: int
    identity_file: str


def render_ssh_config(config: SSHHostConfig) -> str:
    """Render a safe ~/.ssh/config-style configuration snippet."""
    return textwrap.dedent(
        f"""
        Host {config.alias}
            HostName {config.hostname}
            User {config.user}
            Port {config.port}
            IdentityFile {config.identity_file}
            IdentitiesOnly yes
        """
    ).strip()


def explain_ssh_config() -> None:
    print_section("9. SSH client configuration")

    config = SSHHostConfig(
        alias="production",
        hostname="server.example.com",
        user="deploy",
        port=22,
        identity_file="~/.ssh/id_ed25519",
    )

    print(render_ssh_config(config))

    print(
        """
The usual client configuration file is:

    ~/.ssh/config

It lets a short alias represent a longer connection definition.

For example, after defining an alias called "production", the client can use:

    ssh production

Useful directives include:

    Host
    HostName
    User
    Port
    IdentityFile
    IdentitiesOnly
    ForwardAgent
    LocalForward
    RemoteForward
    DynamicForward
    ProxyJump
    ProxyCommand
    ServerAliveInterval
    ServerAliveCountMax
    StrictHostKeyChecking
    UserKnownHostsFile

Security principle:

    Make defaults conservative and override them only where necessary.

"IdentitiesOnly yes" can be useful when an agent contains many keys and the
server would otherwise receive multiple authentication attempts.
"""
    )


# =============================================================================
# SECTION 10: SSH AGENT
# =============================================================================

def explain_ssh_agent() -> None:
    print_section("10. ssh-agent")

    print(
        """
Problem:

    A private key may have a passphrase.

Without an agent:
    The user may need to unlock the key repeatedly.

With ssh-agent:
    The private key can remain protected while the agent performs signing
    operations on behalf of the SSH client.

Typical Unix workflow:

    eval "$(ssh-agent -s)"
    ssh-add ~/.ssh/id_ed25519
    ssh-add -l

Conceptually:

    encrypted/private key
            |
            | unlocked by user
            v
        ssh-agent
            |
            | authentication signing operations
            v
        ssh client
            |
            v
        SSH server

The private key is not normally copied to the remote server.

Useful commands:

    ssh-agent -s
        Start an agent and print environment settings.

    ssh-add keyfile
        Load a key into the agent.

    ssh-add -l
        List loaded identities.

    ssh-add -D
        Remove all identities from the agent.

    ssh-add -d keyfile
        Remove a selected identity.

Security concern:

    Agent forwarding

Using:

    ssh -A user@host

can allow a remote environment to request authentication operations from the
forwarded local agent.

This is convenient for multi-hop workflows but expands the trust boundary.
Use it only when required and with trusted intermediate hosts.
"""
    )


def inspect_ssh_agent_environment() -> None:
    print_section("11. Inspecting the current ssh-agent")

    agent_socket = os.environ.get("SSH_AUTH_SOCK")
    agent_pid = os.environ.get("SSH_AGENT_PID")

    print("SSH_AUTH_SOCK:", agent_socket or "<not set>")
    print("SSH_AGENT_PID:", agent_pid or "<not set>")

    if agent_socket:
        print(
            "An SSH agent socket is exposed to this process through "
            "SSH_AUTH_SOCK."
        )
    else:
        print("No SSH agent socket is visible in this environment.")

    print(
        """
Environment variables do not themselves prove that an agent is trustworthy.
The agent socket should be treated as a security-sensitive capability.
"""
    )


# =============================================================================
# SECTION 11: PASSWORD VS PUBLIC-KEY AUTHENTICATION
# =============================================================================

def compare_authentication_methods() -> None:
    print_section("12. Password authentication vs public-key authentication")

    comparison = [
        ("Secret stored", "Server-side password database", "Client private key"),
        ("Phishing exposure", "Generally higher", "Different threat model"),
        ("Automation", "Awkward and risky", "Well suited with careful key management"),
        ("Rotation", "Password changes", "Replace/revoke authorized keys"),
        ("Passphrase", "Password itself", "Optional private-key passphrase"),
        ("Recommended use", "Depends on policy", "Common preferred method"),
    ]

    print(f"{'Property':<20} {'Password':<35} {'Public key'}")
    print("-" * 90)
    for row in comparison:
        print(f"{row[0]:<20} {row[1]:<35} {row[2]}")

    print(
        """
Public-key authentication is not automatically secure merely because keys
are involved. Security still depends on:

    - private-key protection
    - access control
    - key rotation
    - revocation
    - host verification
    - endpoint security
    - SSH server configuration
    - account permissions

A passphrase protects a private key at rest. It does not replace server-side
authorization.
"""
    )


# =============================================================================
# SECTION 12: SSH SERVER CONFIGURATION
# =============================================================================

def explain_sshd_config() -> None:
    print_section("13. SSH server configuration")

    directives = {
        "Port": "TCP port on which sshd listens",
        "PermitRootLogin": "Controls direct root login policy",
        "PasswordAuthentication": "Controls password-based authentication",
        "PubkeyAuthentication": "Controls public-key authentication",
        "AllowUsers": "Restricts which users may authenticate",
        "AllowGroups": "Restricts authentication to selected groups",
        "MaxAuthTries": "Limits authentication attempts per connection",
        "X11Forwarding": "Controls X11 forwarding",
        "AllowTcpForwarding": "Controls TCP forwarding",
        "PermitTunnel": "Controls tunnel interfaces",
        "ClientAliveInterval": "Server-side keepalive interval",
        "ClientAliveCountMax": "Number of unanswered keepalive checks",
    }

    for directive, description in directives.items():
        print(f"{directive:<24} {description}")

    print(
        """
The server configuration is commonly:

    /etc/ssh/sshd_config

On many systems, configuration fragments can also be loaded from:

    /etc/ssh/sshd_config.d/

After configuration changes, validate the configuration before restarting
the daemon when the operating system provides a validation command.

A common OpenSSH validation pattern is:

    sshd -t

A configuration error can otherwise lock administrators out of the server.

Production principle:

    Keep an already-open administrative session available while changing
    SSH configuration and test a new connection before closing the old one.
"""
    )


# =============================================================================
# SECTION 13: SCP
# =============================================================================

def build_scp_upload_command(
    local_path: str,
    username: str,
    hostname: str,
    remote_path: str,
    port: int = 22,
) -> list[str]:
    command = ["scp"]

    if port != 22:
        command.extend(["-P", str(port)])

    command.extend(
        [
            local_path,
            f"{username}@{hostname}:{remote_path}",
        ]
    )

    return command


def build_scp_download_command(
    username: str,
    hostname: str,
    remote_path: str,
    local_path: str,
    port: int = 22,
) -> list[str]:
    command = ["scp"]

    if port != 22:
        command.extend(["-P", str(port)])

    command.extend(
        [
            f"{username}@{hostname}:{remote_path}",
            local_path,
        ]
    )

    return command


def explain_scp() -> None:
    print_section("14. scp")

    upload = build_scp_upload_command(
        "report.csv",
        "alice",
        "server.example.com",
        "/home/alice/reports/",
    )

    download = build_scp_download_command(
        "alice",
        "server.example.com",
        "/home/alice/reports/report.csv",
        "./report.csv",
    )

    print("$", shlex.join(upload))
    print("$", shlex.join(download))

    print(
        """
Common forms:

    scp local.txt user@host:/remote/path/

    scp user@host:/remote/path/file.txt ./local/path/

    scp -r directory/ user@host:/remote/path/

    scp -P 2222 file user@host:/path/

The uppercase -P is used by scp for the SSH port.

Important limitation:

    scp is primarily a copy operation.

If the goal is repeated synchronization of large directory trees, rsync is
often more efficient because it can avoid retransmitting unchanged data.

Modern OpenSSH implementations have changed scp's transfer implementation
over time, so operational behavior should be verified against the installed
version rather than relying on assumptions from very old scp documentation.
"""
    )


# =============================================================================
# SECTION 14: RSYNC
# =============================================================================

def build_rsync_command(
    source: str,
    destination: str,
    archive: bool = True,
    verbose: bool = True,
    dry_run: bool = True,
    delete: bool = False,
    compress: bool = False,
) -> list[str]:
    command = ["rsync"]

    options = ""

    if archive:
        options += "a"

    if verbose:
        options += "v"

    if compress:
        options += "z"

    if dry_run:
        options += "n"

    if options:
        command.append("-" + options)

    if delete:
        command.append("--delete")

    command.extend([source, destination])

    return command


def explain_rsync() -> None:
    print_section("15. rsync")

    command = build_rsync_command(
        "project/",
        "alice@server.example.com:/srv/project/",
        dry_run=True,
        delete=False,
    )

    print("$", shlex.join(command))

    print(
        """
rsync is designed for efficient synchronization.

Typical SSH-backed form:

    rsync -av project/ user@host:/srv/project/

Important options:

    -a
        Archive mode. Preserves many file attributes and recursively copies
        directory contents.

    -v
        Verbose output.

    -n
        Dry run. Shows intended changes without applying them.

    -z
        Compress data during transfer.

    --delete
        Remove destination files that no longer exist in the source.

    --exclude
        Exclude selected files or directories.

    --progress
        Show transfer progress.

    -e
        Select the remote shell/transport command.

Example:

    rsync -avz -e "ssh -p 2222" ./site/ user@host:/var/www/site/

Trailing slash semantics matter.

    source/
        Means synchronize the contents of source.

    source
        Means synchronize the directory itself.

Always use a dry run before using --delete in an unfamiliar environment.

The rsync algorithm can transfer only changed portions of files in suitable
situations. This makes it particularly useful for repeated synchronization.
"""
    )


# =============================================================================
# SECTION 15: SCP VS RSYNC
# =============================================================================

def compare_scp_and_rsync() -> None:
    print_section("16. scp vs rsync")

    rows = [
        ("Simple one-time copy", "Excellent", "Good"),
        ("Repeated synchronization", "Limited", "Excellent"),
        ("Incremental transfer", "Not its main strength", "Core strength"),
        ("Delete destination extras", "Not a primary feature", "Supported"),
        ("Dry run", "Limited", "Excellent"),
        ("Preserve directory attributes", "Basic recursive options", "Archive mode"),
        ("Large repeated directory trees", "Less suitable", "Usually preferable"),
        ("Ease of learning", "Very easy", "Moderate"),
    ]

    print(f"{'Use case':<36} {'scp':<24} {'rsync'}")
    print("-" * 90)
    for use_case, scp_value, rsync_value in rows:
        print(f"{use_case:<36} {scp_value:<24} {rsync_value}")

    print(
        """
Rule of thumb:

    One simple copy:
        scp can be sufficient.

    Continuous or repeated synchronization:
        rsync is often the better tool.

    Deployment:
        rsync can be useful when its attribute and deletion semantics are
        carefully controlled.

    Backups:
        rsync can be useful as one component, but a complete backup strategy
        also needs retention, verification, recovery testing, and protection
        against deletion or compromise.
"""
    )


# =============================================================================
# SECTION 16: SSH URL / TARGET PARSING
# =============================================================================

@dataclass
class SSHTarget:
    user: Optional[str]
    host: str
    path: Optional[str]


def parse_ssh_target(target: str) -> SSHTarget:
    """
    Parse common user@host:path syntax.

    This intentionally handles the common scp/rsync target form rather than
    attempting to implement every possible URI grammar.
    """
    if ":" not in target:
        return SSHTarget(None, target, None)

    login, path = target.split(":", 1)

    if "@" in login:
        user, host = login.split("@", 1)
    else:
        user, host = None, login

    return SSHTarget(user, host, path)


def demonstrate_target_parsing() -> None:
    print_section("17. SSH target syntax")

    targets = [
        "server.example.com",
        "alice@server.example.com",
        "alice@server.example.com:/srv/data",
        "server.example.com:/tmp/file.txt",
    ]

    for target in targets:
        parsed = parse_ssh_target(target)
        print(f"{target!r} -> {parsed}")


# =============================================================================
# SECTION 17: REMOTE COMMAND EXECUTION FROM PYTHON
# =============================================================================

def safe_display_command(command: Iterable[str]) -> str:
    """Return a shell-safe representation suitable for display."""
    return shlex.join(list(command))


def run_local_command(
    command: list[str],
    timeout: int = 10,
) -> subprocess.CompletedProcess[str]:
    """
    Execute a local command without invoking a shell.

    This is safer than constructing a shell string and using shell=True.
    """
    return subprocess.run(
        command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def demonstrate_python_ssh_automation() -> None:
    print_section("18. SSH automation from Python")

    command = build_ssh_command(
        username="alice",
        hostname="server.example.com",
        command="uname -a",
    )

    print("Command that could be executed:")
    print(" ", safe_display_command(command))

    print(
        """
Python can automate SSH through:

    1. subprocess + installed OpenSSH
    2. a dedicated SSH library
    3. configuration-management or orchestration systems

Using subprocess with OpenSSH has an important advantage:

    The same SSH configuration, host-key database, keys, and agent can often
    be reused by automation.

For user-controlled values, prefer argument lists:

    subprocess.run(["ssh", "user@host", "command"])

rather than:

    subprocess.run(f"ssh {user}@{host} {command}", shell=True)

The second form can introduce shell injection if values are not carefully
controlled.

For serious automation, define:
    - timeouts
    - exit-code handling
    - stderr handling
    - retry policy
    - host-key policy
    - authentication strategy
    - logging
    - least-privilege accounts
"""
    )


# =============================================================================
# SECTION 18: SSH EXIT CODES AND ERROR HANDLING
# =============================================================================

@dataclass
class CommandResult:
    return_code: int
    stdout: str
    stderr: str


def classify_ssh_result(result: CommandResult) -> str:
    if result.return_code == 0:
        return "success"

    if result.return_code == 255:
        return (
            "SSH-level failure is likely: connection, authentication, "
            "configuration, or protocol problem."
        )

    return "Remote command or transport returned a non-zero status."


def demonstrate_error_handling() -> None:
    print_section("19. SSH error handling")

    examples = [
        CommandResult(0, "Linux server 6.x\n", ""),
        CommandResult(255, "", "Permission denied (publickey)."),
        CommandResult(1, "", "remote command failed"),
    ]

    for result in examples:
        print(
            f"return_code={result.return_code} -> "
            f"{classify_ssh_result(result)}"
        )

    print(
        """
A non-zero exit code does not always mean the same thing.

Typical diagnostic categories:

    DNS resolution failure
        Hostname cannot be resolved.

    Connection refused
        Something rejected the TCP connection, or no SSH daemon is listening.

    Connection timed out
        Firewall, routing, service availability, or network problem.

    Permission denied (publickey)
        Authentication failed or the key was not accepted.

    Host key verification failure
        The server identity does not match the client's known information.

    Remote command failure
        SSH succeeded, but the command executed remotely returned an error.

    Connection closed/reset
        The network or server ended the session.

Always inspect both:
    - return code
    - stderr
"""
    )


# =============================================================================
# SECTION 19: HOSTNAME AND PORT TESTING
# =============================================================================

def resolve_hostname(hostname: str) -> list[str]:
    try:
        results = socket.getaddrinfo(hostname, None)
    except socket.gaierror:
        return []

    addresses = sorted(
        {
            result[4][0]
            for result in results
            if result[4]
        }
    )

    return addresses


def test_tcp_port(hostname: str, port: int, timeout: float = 2.0) -> bool:
    """Test TCP connectivity without performing an SSH login."""
    try:
        with socket.create_connection((hostname, port), timeout=timeout):
            return True
    except OSError:
        return False


def demonstrate_network_diagnostics() -> None:
    print_section("20. Basic network diagnostics")

    hostname = "localhost"
    print("Hostname:", hostname)
    print("Resolved addresses:", resolve_hostname(hostname))
    print("TCP port 22 reachable:", test_tcp_port(hostname, 22))

    print(
        """
A useful troubleshooting sequence is:

    1. Check the hostname.
    2. Check DNS resolution.
    3. Check network routing.
    4. Check TCP connectivity.
    5. Check that sshd is listening.
    6. Check host-key verification.
    7. Check authentication.
    8. Check remote authorization.
    9. Check the remote command itself.

Do not jump immediately to changing passwords or deleting known_hosts.
Diagnose the layer that is actually failing.
"""
    )


# =============================================================================
# SECTION 20: SSH VERBOSE MODE
# =============================================================================

def explain_verbose_debugging() -> None:
    print_section("21. SSH verbose debugging")

    commands = [
        "ssh -v user@host",
        "ssh -vv user@host",
        "ssh -vvv user@host",
    ]

    for command in commands:
        print("$", command)

    print(
        """
OpenSSH provides increasing levels of client-side diagnostic information:

    -v
    -vv
    -vvv

Verbose output can reveal:

    - configuration files being read
    - selected algorithms
    - offered identities
    - host-key processing
    - authentication methods
    - connection state

Use verbose output carefully when sharing logs because command lines,
hostnames, usernames, file paths, and configuration information can be
sensitive.
"""
    )


# =============================================================================
# SECTION 21: PORT FORWARDING
# =============================================================================

@dataclass
class ForwardingExample:
    kind: str
    syntax: str
    purpose: str


def explain_port_forwarding() -> None:
    print_section("22. SSH port forwarding")

    examples = [
        ForwardingExample(
            "Local forwarding",
            "ssh -L 8080:internal-db:5432 user@bastion",
            "Expose a remote/internal service through a local port",
        ),
        ForwardingExample(
            "Remote forwarding",
            "ssh -R 9000:localhost:3000 user@server",
            "Expose a local-side service through a remote listening port",
        ),
        ForwardingExample(
            "Dynamic forwarding",
            "ssh -D 1080 user@server",
            "Create a SOCKS proxy through the SSH connection",
        ),
    ]

    for example in examples:
        print(f"\n{example.kind}")
        print("  Syntax:", example.syntax)
        print("  Purpose:", example.purpose)

    print(
        """
Forwarding changes SSH from "remote shell" into a general-purpose secure
transport mechanism.

Local forwarding:

    local application
        |
        v
    localhost:8080
        |
      SSH
        |
        v
    internal-db:5432

This is useful for reaching services that are not directly exposed to the
client.

Security considerations:

    - forwarding can bypass intended network segmentation
    - forwarded ports can expose services unexpectedly
    - bastion hosts become security-sensitive
    - access should be restricted by policy
    - audit forwarding where necessary

Relevant server controls include:

    AllowTcpForwarding
    PermitOpen
    GatewayPorts
"""
    )


# =============================================================================
# SECTION 22: PROXYJUMP / BASTION ARCHITECTURE
# =============================================================================

def explain_bastion_and_proxyjump() -> None:
    print_section("23. Bastion hosts and ProxyJump")

    print(
        """
A bastion host, jump host, or jump server is an intermediate machine used to
reach systems that are not directly reachable from the client.

Architecture:

    Developer
       |
       | SSH
       v
    Bastion
       |
       | SSH
       v
    Private server

Modern OpenSSH commonly supports:

    ssh -J bastion user@private-server

The equivalent configuration can be placed in ~/.ssh/config:

    Host private-server
        HostName 10.0.0.10
        User deploy
        ProxyJump bastion

Advantages:

    - private servers do not need public exposure
    - centralized access control
    - easier auditing
    - reduced attack surface

Trade-off:

    The bastion becomes critical infrastructure. It needs strong hardening,
    monitoring, patching, access control, and reliable availability.
"""
    )


# =============================================================================
# SECTION 23: SSH MULTIPLEXING
# =============================================================================

def explain_connection_multiplexing() -> None:
    print_section("24. SSH connection multiplexing")

    print(
        """
OpenSSH can reuse an existing connection for multiple sessions.

Relevant client options include:

    ControlMaster
    ControlPath
    ControlPersist

Conceptually:

    First SSH connection
        |
        v
    persistent master connection
        |
        +--> session 1
        +--> session 2
        +--> session 3

This can reduce repeated TCP and cryptographic handshake overhead.

A typical configuration pattern is conceptually:

    Host server.example.com
        ControlMaster auto
        ControlPersist 5m
        ControlPath ~/.ssh/control-%C

Security and operational considerations:

    - control sockets are sensitive
    - filesystem permissions matter
    - stale sockets can cause confusing failures
    - multiplexing changes connection lifecycle assumptions
"""
    )


# =============================================================================
# SECTION 24: SCP AND RSYNC USING NON-STANDARD PORTS
# =============================================================================

def demonstrate_nonstandard_ports() -> None:
    print_section("25. Non-standard SSH ports")

    scp_command = build_scp_upload_command(
        "backup.tar",
        "backup",
        "server.example.com",
        "/srv/backups/",
        port=2222,
    )

    rsync_command = [
        "rsync",
        "-av",
        "-e",
        "ssh -p 2222",
        "./backup/",
        "backup@server.example.com:/srv/backups/",
    ]

    print("scp:")
    print("$", shlex.join(scp_command))

    print("\nrsync:")
    print("$", shlex.join(rsync_command))

    print(
        """
Port changes can reduce unsolicited scanning noise, but changing the SSH
port is not a substitute for authentication hardening, patching, firewall
policy, and least privilege.

For scp:

    -P 2222

For rsync:

    -e "ssh -p 2222"

Note the different capitalization and option syntax.
"""
    )


# =============================================================================
# SECTION 25: RSYNC SEMANTICS
# =============================================================================

def explain_rsync_semantics() -> None:
    print_section("26. rsync semantics and edge cases")

    print(
        """
Consider:

    rsync -av source/ destination/

This synchronizes the contents of source into destination.

Compare:

    rsync -av source destination/

This can create a destination/source directory structure depending on the
destination path.

Always test directory semantics with:

    rsync -av --dry-run ...

before changing production data.

Deletion:

    --delete

means files that exist at the destination but not the source may be removed.

This is powerful and dangerous.

Safer deployment workflow:

    1. inspect source
    2. run dry run
    3. inspect proposed deletions
    4. verify source and destination
    5. perform transfer
    6. validate application
    7. retain rollback/recovery capability

Exclude example:

    rsync -av \
        --exclude '.git/' \
        --exclude '__pycache__/' \
        --exclude '*.log' \
        project/ user@host:/srv/project/

Preservation details depend on operating system, filesystem, user privileges,
and rsync options.
"""
    )


# =============================================================================
# SECTION 26: RSYNC PERFORMANCE
# =============================================================================

def explain_rsync_performance() -> None:
    print_section("27. rsync performance")

    print(
        """
Performance depends on:

    - network bandwidth
    - network latency
    - CPU cost of compression
    - disk throughput
    - number of files
    - file sizes
    - filesystem metadata operations
    - amount of changed data
    - encryption overhead
    - rsync algorithm behavior

Compression is not automatically faster.

If the network is fast and the CPU is the bottleneck:

    -z

may reduce performance.

If the network is slow and data is compressible, compression may help.

Many small files can be expensive because metadata operations and file
creation dominate transfer time.

Large files with small changes can benefit from rsync's delta-transfer design.

Performance should be measured in the actual environment rather than assumed
from a generic benchmark.
"""
    )


# =============================================================================
# SECTION 27: SSH SECURITY HARDENING
# =============================================================================

def explain_security_hardening() -> None:
    print_section("28. SSH security hardening")

    recommendations = [
        "Use modern supported OpenSSH releases.",
        "Keep the operating system patched.",
        "Prefer strong public-key authentication.",
        "Protect private keys with strong passphrases.",
        "Restrict who can log in.",
        "Avoid unnecessary direct root login.",
        "Use least privilege.",
        "Use host-key verification.",
        "Restrict forwarding where it is not required.",
        "Use firewall rules and network segmentation.",
        "Monitor authentication activity.",
        "Rotate and revoke credentials when necessary.",
        "Use separate keys for different trust domains.",
        "Protect automation keys carefully.",
    ]

    for recommendation in recommendations:
        print(" -", recommendation)

    print(
        """
A useful security model is:

    Identity
        Who is connecting?

    Authentication
        Can they prove that identity?

    Authorization
        What are they allowed to do?

    Transport security
        Is the connection protected?

    Host verification
        Is the endpoint the intended endpoint?

    Auditing
        Can suspicious activity be detected?

SSH security is therefore a system-design problem rather than a single
configuration switch.
"""
    )


# =============================================================================
# SECTION 28: KEY MANAGEMENT
# =============================================================================

@dataclass
class KeyLifecycle:
    generation: str
    storage: str
    distribution: str
    rotation: str
    revocation: str


def explain_key_lifecycle() -> None:
    print_section("29. SSH key lifecycle")

    lifecycle = KeyLifecycle(
        generation="Generate keys using a trusted cryptographic implementation.",
        storage="Protect private keys with permissions and passphrases.",
        distribution="Install only the public key on authorized systems.",
        rotation="Replace keys according to organizational policy and risk.",
        revocation="Remove or disable keys when access should end.",
    )

    for field_name in lifecycle.__dataclass_fields__:
        print(f"{field_name.title():<14}: {getattr(lifecycle, field_name)}")

    print(
        """
Avoid using one highly privileged private key everywhere.

Separate keys can reduce blast radius:

    personal development key
    production administration key
    deployment automation key
    backup automation key

If one key is compromised, separation can limit the affected systems.

For larger organizations, centralized SSH certificates or identity systems
may be preferable to manually maintaining large authorized_keys files.
"""
    )


# =============================================================================
# SECTION 29: SSH CERTIFICATES
# =============================================================================

def explain_ssh_certificates() -> None:
    print_section("30. SSH certificates")

    print(
        """
SSH certificates are different from ordinary public keys.

A simplified model:

    Certificate Authority (CA)
             |
             | signs
             v
    user/host public key + metadata
             |
             v
    SSH server trusts CA
             |
             v
    certificate accepted

A certificate can carry identity and validity information without requiring
every server to know every individual public key directly.

Benefits:

    - centralized trust
    - easier large-scale identity management
    - short-lived credentials
    - reduced manual key distribution

Important distinction:

    Public key:
        The key itself is trusted.

    Certificate:
        A trusted authority attests to a key and associated identity.

SSH certificates should be designed with appropriate CA protection, validity
periods, principals, and issuance controls.
"""
    )


# =============================================================================
# SECTION 30: AUTOMATION KEYS
# =============================================================================

def explain_automation_accounts() -> None:
    print_section("31. SSH automation and deployment accounts")

    print(
        """
A production deployment account should generally not have unrestricted
administrator privileges unless there is a justified requirement.

A stronger design can be:

    CI/CD system
        |
        | dedicated SSH key
        v
    deployment account
        |
        | restricted command
        v
    deployment mechanism

Potential controls:

    - dedicated Unix user
    - dedicated key
    - restricted authorized_keys entry
    - no interactive shell where unnecessary
    - no agent forwarding
    - no port forwarding
    - limited filesystem permissions
    - centralized logging

The goal is to reduce the consequences of a compromised automation credential.
"""
    )


# =============================================================================
# SECTION 31: HOST KEY FINGERPRINTS
# =============================================================================

def fingerprint_text(value: str) -> str:
    """Create a SHA-256 fingerprint-like representation for demonstration."""
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    encoded = base64.b64encode(digest).decode("ascii").rstrip("=")
    return "SHA256:" + encoded


def demonstrate_fingerprints() -> None:
    print_section("32. Fingerprints")

    simulated_host_key = "SIMULATED SERVER HOST KEY"
    print("Demonstration fingerprint:")
    print(" ", fingerprint_text(simulated_host_key))

    print(
        """
OpenSSH commonly displays SHA-256 fingerprints for keys.

A fingerprint is a compact representation of key material.

It is useful because comparing:

    huge cryptographic key
        vs
    short fingerprint

is easier for humans.

The fingerprint must be obtained from a trusted source when performing
first-time host verification.
"""
    )


# =============================================================================
# SECTION 32: KNOWN_HOSTS MANAGEMENT
# =============================================================================

def explain_known_hosts_management() -> None:
    print_section("33. known_hosts management")

    print(
        """
Useful OpenSSH tools include:

    ssh-keygen -F hostname
        Search known_hosts for a host.

    ssh-keygen -R hostname
        Remove a host entry.

    ssh-keyscan hostname
        Retrieve host keys from a server.

Important security warning:

    ssh-keyscan obtains a server's presented key. It does not independently
    prove that the server is trustworthy.

Therefore:

    keyscan + trusted verification
        is meaningful.

    blindly accepting keyscan output
        is not a complete identity-verification process.

When a host key changes, investigate first.
"""
    )


# =============================================================================
# SECTION 33: SSH TUNNELING DESIGN
# =============================================================================

def explain_tunneling_security() -> None:
    print_section("34. Tunneling security")

    print(
        """
SSH tunneling can intentionally bypass network boundaries.

Example:

    User laptop
       |
       | SSH
       v
    Bastion
       |
       v
    Internal database

The database may remain inaccessible from the public internet.

This is useful when designed deliberately.

It can become dangerous when:

    - users can freely forward arbitrary ports
    - the bastion is poorly secured
    - forwarding bypasses monitoring
    - internal services assume network location equals authorization

Network location should not be treated as the only authorization boundary.

Use explicit access controls at the application/service layer where possible.
"""
    )


# =============================================================================
# SECTION 34: SSH PERFORMANCE
# =============================================================================

def explain_ssh_performance() -> None:
    print_section("35. SSH performance")

    print(
        """
SSH performance is affected by:

    Network latency
        High latency increases the cost of round trips.

    Bandwidth
        Determines how quickly encrypted data can be transferred.

    Cipher and cryptographic processing
        Modern CPUs often make this relatively inexpensive, but workloads vary.

    Compression
        Can reduce bytes transmitted while increasing CPU work.

    Connection setup
        Repeated handshakes can be expensive in high-latency environments.

    Multiplexing
        Can reuse an existing connection and reduce setup overhead.

    File-transfer algorithm
        rsync can reduce data transferred during repeated synchronization.

Optimization should begin with measurement.

For example:

    repeated short SSH commands
        -> connection multiplexing may help.

    compressible data over a slow link
        -> compression may help.

    already-compressed media
        -> compression often adds CPU cost without useful reduction.

    many small files
        -> filesystem and metadata behavior may dominate.
"""
    )


# =============================================================================
# SECTION 35: SSH ENVIRONMENT VARIABLES
# =============================================================================

def explain_ssh_environment() -> None:
    print_section("36. SSH environment variables")

    interesting_variables = [
        "SSH_AUTH_SOCK",
        "SSH_AGENT_PID",
        "SSH_CONNECTION",
        "SSH_CLIENT",
        "SSH_TTY",
    ]

    for variable in interesting_variables:
        value = os.environ.get(variable)
        print(f"{variable:<20} {value if value else '<not set>'}")

    print(
        """
Some SSH-related environment variables expose information about the current
SSH context.

SSH_AUTH_SOCK:
    Path to the agent's Unix-domain socket when an agent is available.

SSH_CONNECTION:
    Commonly contains remote and local connection address/port information
    for an SSH server-side session.

SSH_TTY:
    Indicates an allocated pseudo-terminal in environments where one exists.

Environment variables should not automatically be considered trusted input.
Applications should validate security-sensitive values independently.
"""
    )


# =============================================================================
# SECTION 36: PSEUDO-TERMINALS
# =============================================================================

def explain_tty() -> None:
    print_section("37. Interactive shell and pseudo-terminal")

    print(
        """
An interactive SSH login commonly allocates a pseudo-terminal (PTY).

For example:

    ssh user@host

A command that does not require an interactive terminal can be run without
allocating one:

    ssh user@host "command"

The -t option requests a pseudo-terminal.

TTY allocation matters for:

    - interactive shells
    - terminal-based programs
    - sudo configurations
    - terminal formatting
    - programs that expect a controlling terminal

Automation should generally avoid unnecessary interactive terminal behavior.
"""
    )


# =============================================================================
# SECTION 37: SSH SESSION CHANNELS
# =============================================================================

def explain_channels() -> None:
    print_section("38. SSH channels")

    print(
        """
One SSH connection can carry multiple logical channels.

Examples include:

    session channels
        Shells and remote commands.

    forwarding channels
        Port-forwarded traffic.

    subsystem channels
        Services such as SFTP.

This architecture is one reason SSH is more than a remote terminal program.

Conceptually:

                SSH connection
                       |
          +------------+------------+
          |            |            |
        shell       command      forwarding
          |
        subsystem

Encryption and integrity protection operate over the SSH transport while
logical channels carry different kinds of activity.
"""
    )


# =============================================================================
# SECTION 38: SFTP DISTINCTION
# =============================================================================

def explain_sftp() -> None:
    print_section("39. SFTP vs scp")

    print(
        """
SFTP means SSH File Transfer Protocol.

It is a distinct SSH subsystem/protocol from scp, even though both commonly
operate over SSH.

Typical command:

    sftp user@host

SFTP provides interactive file-management operations such as:

    ls
    cd
    get
    put
    mkdir
    rm

Comparison:

    scp
        Simple copy-oriented command.

    sftp
        Interactive/file-transfer protocol with richer file operations.

    rsync
        Synchronization algorithm/tool optimized for repeated comparison and
        transfer of changed data.

Choose based on the actual requirement rather than treating all three as
identical tools.
"""
    )


# =============================================================================
# SECTION 39: SSH SECURITY MISTAKES
# =============================================================================

def demonstrate_common_mistakes() -> None:
    print_section("40. Common SSH mistakes")

    mistakes = {
        "Sharing private keys": "Private keys should remain secret.",
        "Ignoring host-key warnings": "May hide endpoint impersonation.",
        "Using root everywhere": "Violates least privilege.",
        "Using one key everywhere": "Increases blast radius.",
        "Blindly using --delete": "Can destroy destination-only files.",
        "Using shell=True with user input": "Can create command injection.",
        "Forwarding agents everywhere": "Expands trust to remote hosts.",
        "Disabling verification to fix errors": "Weakens endpoint authentication.",
        "No recovery plan": "Configuration errors can cause lockout.",
        "No key inventory": "Orphaned credentials remain difficult to revoke.",
    }

    for mistake, explanation in mistakes.items():
        print(f"\n{mistake}")
        print("  ", explanation)


# =============================================================================
# SECTION 40: COMMAND INJECTION
# =============================================================================

def demonstrate_command_injection_prevention() -> None:
    print_section("41. Command injection and Python automation")

    unsafe_example = (
        "ssh " +
        "user@host " +
        "echo " +
        "USER_VALUE"
    )

    safe_example = [
        "ssh",
        "user@host",
        "echo",
        "USER_VALUE",
    ]

    print("Unsafe shell-string pattern:")
    print(" ", unsafe_example)

    print("\nPreferred argument-list pattern:")
    print(" ", shlex.join(safe_example))

    print(
        """
The important principle is not that shlex.quote() magically makes all SSH
automation safe. The stronger approach is:

    - avoid shell=True where possible
    - pass arguments as a list
    - validate values
    - separate trusted command structure from untrusted data
    - use fixed commands for privileged automation

If a remote command itself invokes a shell, remote-side shell parsing becomes
another security boundary that must be considered.
"""
    )


# =============================================================================
# SECTION 41: FILE HASHING FOR TRANSFER VALIDATION
# =============================================================================

def sha256_file(path: Path) -> str:
    """Calculate a SHA-256 hash using streaming reads."""
    digest = hashlib.sha256()

    with path.open("rb") as file:
        while True:
            chunk = file.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)

    return digest.hexdigest()


def demonstrate_transfer_verification() -> None:
    print_section("42. File integrity verification")

    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "example.txt"
        path.write_text(
            "SSH file-transfer verification example\n",
            encoding="utf-8",
        )

        print("File:", path)
        print("SHA-256:", sha256_file(path))

    print(
        """
A cryptographic hash can be used to verify that two files have identical
content.

For example:

    source hash
        =
    destination hash

provides strong evidence that the contents match, assuming a secure hash
algorithm and trustworthy comparison.

SSH already provides transport integrity, but end-to-end application-level
verification can still be valuable for critical workflows.
"""
    )


# =============================================================================
# SECTION 42: SAFE DRY-RUN DEPLOYMENT SIMULATION
# =============================================================================

@dataclass
class DeploymentPlan:
    source: str
    destination: str
    excludes: list[str]
    delete: bool


def create_rsync_deployment_plan(plan: DeploymentPlan) -> list[str]:
    command = [
        "rsync",
        "-av",
        "--dry-run",
    ]

    if plan.delete:
        command.append("--delete")

    for pattern in plan.excludes:
        command.extend(["--exclude", pattern])

    command.extend([plan.source, plan.destination])
    return command


def demonstrate_deployment_simulation() -> None:
    print_section("43. Safe rsync deployment planning")

    plan = DeploymentPlan(
        source="./application/",
        destination="deploy@server.example.com:/srv/application/",
        excludes=[".git/", "__pycache__/", "*.log"],
        delete=False,
    )

    command = create_rsync_deployment_plan(plan)

    print("$", shlex.join(command))

    print(
        """
A deployment system should make destructive behavior explicit.

A safer pattern is:

    dry run
        ->
    review
        ->
    transfer
        ->
    application validation
        ->
    monitoring

A deployment script should not automatically add --delete merely because
the goal is "synchronization". Deletion changes the risk profile.
"""
    )


# =============================================================================
# SECTION 43: BACKUP DESIGN
# =============================================================================

def explain_backup_design() -> None:
    print_section("44. rsync and backup design")

    print(
        """
rsync is useful for copying data, but a backup system requires more than
synchronization.

A robust backup architecture considers:

    source
      |
      v
    transfer
      |
      v
    backup storage
      |
      +--> retention
      +--> integrity verification
      +--> access control
      +--> encryption
      +--> monitoring
      +--> recovery testing
      +--> protection from accidental deletion

A plain mirror using:

    rsync --delete

can reproduce accidental deletion at the destination.

A backup strategy therefore needs historical versions, retention, or another
mechanism appropriate to the recovery objective.
"""
    )


# =============================================================================
# SECTION 44: SSH AND ZERO TRUST
# =============================================================================

def explain_zero_trust_context() -> None:
    print_section("45. SSH in modern access architecture")

    print(
        """
Traditional network security often assumed:

    inside network = trusted
    outside network = untrusted

Modern security architecture increasingly treats every connection as requiring
explicit authentication and authorization.

SSH fits naturally into this model because it provides:

    - strong identity
    - encrypted transport
    - host verification
    - granular access controls
    - forwarding controls
    - auditability

But SSH alone does not establish a complete zero-trust architecture.

Application authorization, device security, identity lifecycle, network policy,
logging, and monitoring remain important.
"""
    )


# =============================================================================
# SECTION 45: DNS AND SSH
# =============================================================================

def explain_dns_risks() -> None:
    print_section("46. DNS, IP addresses, and SSH identity")

    print(
        """
SSH connects to a hostname that may resolve to one or more IP addresses.

DNS answers:

    "Where should I attempt the network connection?"

The SSH host key answers:

    "Which cryptographic server identity did I encounter?"

These are different questions.

A DNS record can change while a legitimate server identity remains the same.
Conversely, a DNS name could resolve to an unintended server whose host key
does not match the expected identity.

This is why host-key verification remains important even when DNS is trusted.
"""
    )


# =============================================================================
# SECTION 46: IPV4 / IPV6
# =============================================================================

def explain_ip_versions() -> None:
    print_section("47. IPv4 and IPv6")

    print(
        """
SSH itself can operate over IPv4 and IPv6.

Useful diagnostic concepts:

    A record
        IPv4 address.

    AAAA record
        IPv6 address.

Potential troubleshooting issue:

    hostname resolves correctly
        but
    selected address family is unreachable.

OpenSSH provides options such as:

    -4
        Prefer/force IPv4.

    -6
        Prefer/force IPv6.

Example:

    ssh -4 user@host
    ssh -6 user@host
"""
    )


# =============================================================================
# SECTION 47: KEEPALIVES
# =============================================================================

def explain_keepalives() -> None:
    print_section("48. SSH keepalives")

    print(
        """
Long-lived SSH connections can be closed by NAT devices, firewalls, or idle
network infrastructure.

OpenSSH supports keepalive-related settings.

Client-side examples include:

    ServerAliveInterval
    ServerAliveCountMax

Server-side examples include:

    ClientAliveInterval
    ClientAliveCountMax

Keepalives can help detect dead connections, but they are not a replacement
for robust network design.

Too aggressive keepalives can create unnecessary traffic and load.
"""
    )


# =============================================================================
# SECTION 48: TIMEOUT DESIGN
# =============================================================================

@dataclass
class RetryPolicy:
    attempts: int
    initial_delay: float
    multiplier: float
    maximum_delay: float


def calculate_backoff(policy: RetryPolicy) -> list[float]:
    delays = []
    delay = policy.initial_delay

    for _ in range(policy.attempts):
        delays.append(min(delay, policy.maximum_delay))
        delay *= policy.multiplier

    return delays


def demonstrate_retry_policy() -> None:
    print_section("49. SSH automation retry strategy")

    policy = RetryPolicy(
        attempts=5,
        initial_delay=1,
        multiplier=2,
        maximum_delay=10,
    )

    print("Backoff delays:", calculate_backoff(policy))

    print(
        """
Retries should distinguish transient failures from permanent failures.

Potentially transient:

    - temporary network failure
    - service restart
    - temporary overload

Usually not solved by repeated retries:

    - invalid private key
    - unauthorized user
    - wrong host key
    - invalid remote command
    - broken SSH configuration

Use bounded exponential backoff rather than an unlimited tight retry loop.
"""
    )


# =============================================================================
# SECTION 49: CONFIGURATION VALIDATION
# =============================================================================

def validate_local_ssh_directory(directory: Path) -> dict[str, bool]:
    """Perform basic local checks without modifying anything."""
    return {
        "directory_exists": directory.exists(),
        "directory_is_directory": directory.is_dir(),
        "config_exists": (directory / "config").exists(),
        "known_hosts_exists": (directory / "known_hosts").exists(),
        "authorized_keys_exists": (directory / "authorized_keys").exists(),
    }


def demonstrate_local_ssh_inventory() -> None:
    print_section("50. Local SSH inventory")

    ssh_directory = Path.home() / ".ssh"
    inventory = validate_local_ssh_directory(ssh_directory)

    print("SSH directory:", ssh_directory)

    for item, present in inventory.items():
        print(f"{item:<28}: {present}")

    print(
        """
A local inventory is useful for understanding configuration, but file names
alone do not establish whether a key is active, trusted, valid, or secure.

Never print private-key contents into logs.
"""
    )


# =============================================================================
# SECTION 50: SECURITY-SAFE KEY INVENTORY
# =============================================================================

def list_public_key_files(directory: Path) -> list[Path]:
    """Find public-key files without reading private-key contents."""
    if not directory.exists():
        return []

    return sorted(
        path
        for path in directory.glob("*.pub")
        if path.is_file()
    )


def demonstrate_key_inventory() -> None:
    print_section("51. Public-key inventory")

    ssh_directory = Path.home() / ".ssh"
    public_keys = list_public_key_files(ssh_directory)

    if public_keys:
        for key in public_keys:
            print("Public key:", key)
    else:
        print("No .pub files found in the local ~/.ssh directory.")

    print(
        """
An inventory should avoid exposing private-key material.

Useful metadata can include:

    filename
    fingerprint
    algorithm
    creation date where known
    intended owner
    intended environment
    expiration/rotation policy

Private key contents should not be included in normal inventory reports.
"""
    )


# =============================================================================
# SECTION 51: REMOTE EXECUTION SAFETY
# =============================================================================

def build_fixed_remote_health_check(
    username: str,
    hostname: str,
) -> list[str]:
    """Build a fixed, non-user-controlled health-check command."""
    return build_ssh_command(
        username=username,
        hostname=hostname,
        command="uname -a",
    )


def demonstrate_fixed_remote_commands() -> None:
    print_section("52. Safe remote command design")

    command = build_fixed_remote_health_check(
        "monitor",
        "server.example.com",
    )

    print("$", shlex.join(command))

    print(
        """
For monitoring, deployment, and maintenance automation, fixed commands are
easier to secure than arbitrary command execution.

If arbitrary commands are genuinely required:

    - authenticate strongly
    - authorize explicitly
    - validate input
    - avoid shell interpretation
    - log carefully
    - restrict the automation account
    - limit network access
"""
    )


# =============================================================================
# SECTION 52: ADVANCED SSH AUTHENTICATION CONCEPTS
# =============================================================================

def explain_advanced_authentication() -> None:
    print_section("53. Advanced SSH authentication concepts")

    print(
        """
OpenSSH can support several authentication approaches depending on version
and configuration.

Examples include:

    Public-key authentication
        Cryptographic proof using a private key.

    Password authentication
        Password-based user authentication.

    Keyboard-interactive authentication
        Server-driven interactive authentication prompts.

    Host-based authentication
        Authentication based on trusted host identity and user information.

    Certificates
        CA-signed user or host identities.

    Hardware-backed keys
        Private-key operations can be performed by security hardware, reducing
        exposure of private key material.

Organizations may combine SSH with broader identity-management systems.

The correct choice depends on:

    - threat model
    - scale
    - administrative requirements
    - hardware availability
    - automation needs
    - compliance requirements
"""
    )


# =============================================================================
# SECTION 53: HARDWARE-BACKED AUTHENTICATION
# =============================================================================

def explain_hardware_backed_keys() -> None:
    print_section("54. Hardware-backed SSH keys")

    print(
        """
OpenSSH supports hardware-backed or security-token-backed key mechanisms on
systems and devices that provide appropriate support.

The security idea is:

    private-key operation
            |
            v
    hardware security boundary

rather than:

    private key permanently exposed as ordinary filesystem material

Potential advantages:

    - stronger protection against key theft
    - user-presence requirements
    - phishing-resistant authentication in suitable designs
    - reduced exposure of private key material

Operational considerations include:

    - hardware availability
    - recovery procedures
    - replacement tokens
    - enrollment
    - compatibility
    - user experience
"""
    )


# =============================================================================
# SECTION 54: SSH AGENT SECURITY MODEL
# =============================================================================

def explain_agent_security() -> None:
    print_section("55. ssh-agent security model")

    print(
        """
An agent does not magically make keys safe.

Threat model:

    Local malware
        may attempt to interact with the agent socket.

    Agent forwarding
        may extend access to remote systems.

    Excessive loaded keys
        can cause unexpected authentication attempts.

Better practices include:

    - load only keys that are needed
    - remove keys when no longer required
    - use agent lifetime controls where supported
    - avoid forwarding into untrusted systems
    - use separate keys for sensitive environments

The agent protects private-key handling, but it does not eliminate endpoint
security requirements.
"""
    )


# =============================================================================
# SECTION 55: SSH FILE STRUCTURE
# =============================================================================

def explain_ssh_directory() -> None:
    print_section("56. Common ~/.ssh structure")

    files = {
        "config": "Client configuration",
        "known_hosts": "Known server host keys",
        "authorized_keys": "Server-side authorized public keys",
        "id_ed25519": "Example private user key",
        "id_ed25519.pub": "Corresponding public key",
        "known_hosts.old": "Possible previous known_hosts file",
    }

    for name, purpose in files.items():
        print(f"{name:<24} {purpose}")

    print(
        """
Not every file will exist on every machine.

The meaning of a file also depends on whether the machine is acting as:

    SSH client
    SSH server
    both
"""
    )


# =============================================================================
# SECTION 56: FILESYSTEM SYMLINKS AND RSYNC
# =============================================================================

def explain_rsync_special_files() -> None:
    print_section("57. rsync special file behavior")

    print(
        """
rsync can preserve or handle metadata such as:

    - permissions
    - timestamps
    - symbolic links
    - ownership
    - groups
    - devices

The exact behavior depends on options and privileges.

Archive mode is approximately a convenient collection of preservation options,
not a universal guarantee that every filesystem property will be reproduced.

Important production considerations:

    - root vs non-root execution
    - filesystem support
    - ACLs
    - extended attributes
    - symbolic links
    - hard links
    - sparse files
    - device files
    - SELinux or other security labels

For sensitive migrations, explicitly verify which metadata must be preserved.
"""
    )


# =============================================================================
# SECTION 57: RSYNC ACL / XATTR CONCEPTS
# =============================================================================

def explain_rsync_metadata() -> None:
    print_section("58. rsync metadata preservation")

    print(
        """
For specialized environments, rsync provides additional preservation options
for metadata.

Examples include concepts represented by options such as:

    -A
        ACLs

    -X
        Extended attributes

    -H
        Hard links

    -S
        Sparse files

These should not be added blindly.

Each option can affect:

    performance
    compatibility
    privileges
    storage behavior
    correctness

The correct rsync command is determined by the properties the destination
must preserve.
"""
    )


# =============================================================================
# SECTION 58: SSH AND RSYNC LOGGING
# =============================================================================

def explain_logging() -> None:
    print_section("59. Logging and auditing")

    print(
        """
Useful audit information can include:

    - source address
    - username
    - authentication method
    - timestamp
    - success/failure
    - target system
    - privileged operations

Do not log:

    - private-key contents
    - passphrases
    - passwords
    - unnecessary authentication secrets

For rsync, verbose output can be useful operationally, but logs should be
designed so that sensitive paths or data are not unnecessarily exposed.

Centralized logging can improve incident detection and investigation.
"""
    )


# =============================================================================
# SECTION 59: SSH INCIDENT RESPONSE
# =============================================================================

def explain_incident_response() -> None:
    print_section("60. SSH credential compromise response")

    print(
        """
If an SSH private key is suspected to be compromised, treat the credential as
potentially exposed.

A conceptual response is:

    1. Identify affected key.
    2. Identify systems where its public key is authorized.
    3. Revoke/remove authorization.
    4. Replace the credential.
    5. Investigate authentication logs.
    6. Check for persistence or unauthorized changes.
    7. Rotate related credentials where necessary.
    8. Review why the key became exposed.

Do not rely on simply deleting the private-key file if the public key remains
authorized on production systems.

Revocation must happen at the authorization boundary.
"""
    )


# =============================================================================
# SECTION 60: SSH ARCHITECTURE CASE STUDY
# =============================================================================

def explain_case_study() -> None:
    print_section("61. Production architecture case study")

    print(
        """
Scenario:

    Developers need access to private application servers.

Architecture:

    Developer workstation
            |
            | SSH public key
            v
        Bastion host
            |
            | ProxyJump
            v
      Private application server
            |
            +--> application
            +--> database network

Controls:

    Developer:
        - protected private key
        - ssh-agent
        - host-key verification

    Bastion:
        - minimal exposed services
        - restricted accounts
        - monitoring
        - patching
        - limited forwarding

    Application server:
        - private network
        - least-privilege user
        - public-key authentication
        - no unnecessary forwarding

Deployment:

    CI/CD
       |
       | dedicated deployment key
       v
    deployment account
       |
       v
    rsync dry run
       |
       v
    rsync deployment
       |
       v
    health check

This design separates:

    human access
    deployment access
    network routing
    authorization
    application privileges

That separation reduces the blast radius of individual credential failures.
"""
    )


# =============================================================================
# SECTION 61: PRACTICAL COMMAND REFERENCE
# =============================================================================

def print_command_reference() -> None:
    print_section("62. Practical command reference")

    commands = [
        ("Connect", "ssh user@host"),
        ("Custom port", "ssh -p 2222 user@host"),
        ("Specific key", "ssh -i ~/.ssh/id_ed25519 user@host"),
        ("Remote command", "ssh user@host 'uname -a'"),
        ("Verbose", "ssh -vvv user@host"),
        ("Jump host", "ssh -J bastion user@private-host"),
        ("Generate Ed25519 key", "ssh-keygen -t ed25519"),
        ("List agent keys", "ssh-add -l"),
        ("Add key", "ssh-add ~/.ssh/id_ed25519"),
        ("Remove all agent keys", "ssh-add -D"),
        ("Inspect host key", "ssh-keygen -F host"),
        ("Remove known host", "ssh-keygen -R host"),
        ("SCP upload", "scp file user@host:/path/"),
        ("SCP download", "scp user@host:/path/file ."),
        ("Recursive SCP", "scp -r directory user@host:/path/"),
        ("Rsync", "rsync -av source/ user@host:/path/"),
        ("Rsync dry run", "rsync -avn source/ user@host:/path/"),
        ("Rsync compression", "rsync -avz source/ user@host:/path/"),
        ("Rsync delete", "rsync -av --delete source/ user@host:/path/"),
        ("SFTP", "sftp user@host"),
    ]

    for description, command in commands:
        print(f"{description:<28} {command}")


# =============================================================================
# SECTION 62: PRACTICAL DECISION TREE
# =============================================================================

def ssh_decision_tree() -> None:
    print_section("63. SSH tool selection decision tree")

    print(
        """
Need a remote shell?
    |
    +--> ssh

Need a simple file copy?
    |
    +--> scp

Need interactive file management?
    |
    +--> sftp

Need repeated directory synchronization?
    |
    +--> rsync over SSH

Need to reach a private host through another SSH host?
    |
    +--> ProxyJump / -J

Need to access an internal TCP service?
    |
    +--> SSH port forwarding

Need many short SSH sessions?
    |
    +--> Consider connection multiplexing

Need many users/hosts at enterprise scale?
    |
    +--> Consider centralized identity and SSH certificates
"""
    )


# =============================================================================
# SECTION 63: EDGE CASES
# =============================================================================

def demonstrate_edge_cases() -> None:
    print_section("64. Important edge cases")

    edge_cases = [
        (
            "Hostname contains unusual characters",
            "Do not construct shell strings blindly; use structured arguments.",
        ),
        (
            "IPv6 literal",
            "SSH syntax can require bracket-style handling in some contexts.",
        ),
        (
            "Remote path contains spaces",
            "Quoting rules differ between local and remote command contexts.",
        ),
        (
            "Many agent keys",
            "Use IdentitiesOnly and explicit IdentityFile when appropriate.",
        ),
        (
            "Changed host key",
            "Verify the new identity before changing known_hosts.",
        ),
        (
            "rsync --delete",
            "Use a dry run first and confirm source/destination direction.",
        ),
        (
            "Large compressed files",
            "Compression may waste CPU without reducing transfer size.",
        ),
        (
            "High-latency network",
            "Connection reuse can reduce repeated setup overhead.",
        ),
        (
            "Automation account",
            "Restrict authorization and avoid unnecessary interactive access.",
        ),
    ]

    for title, behavior in edge_cases:
        print(f"\n{title}")
        print(" ", behavior)


# =============================================================================
# SECTION 64: MINI TESTS
# =============================================================================

def test_build_ssh_command() -> None:
    command = build_ssh_command(
        "alice",
        "example.com",
        port=2222,
        identity_file="/tmp/key",
        command="whoami",
    )

    assert command == [
        "ssh",
        "-p",
        "2222",
        "-i",
        "/tmp/key",
        "alice@example.com",
        "whoami",
    ]


def test_parse_ssh_target() -> None:
    target = parse_ssh_target("alice@example.com:/srv/data")
    assert target.user == "alice"
    assert target.host == "example.com"
    assert target.path == "/srv/data"


def test_backoff() -> None:
    policy = RetryPolicy(4, 1, 2, 10)
    assert calculate_backoff(policy) == [1, 2, 4, 8]


def test_file_hash() -> None:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "data.txt"
        path.write_text("hello", encoding="utf-8")

        expected = hashlib.sha256(b"hello").hexdigest()
        assert sha256_file(path) == expected


def run_tests() -> None:
    print_section("65. Built-in study tests")

    tests = [
        test_build_ssh_command,
        test_parse_ssh_target,
        test_backoff,
        test_file_hash,
    ]

    passed = 0

    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except AssertionError:
            print(f"FAIL  {test.__name__}")

    print(f"\nPassed: {passed}/{len(tests)}")


# =============================================================================
# SECTION 65: SYSTEM INFORMATION
# =============================================================================

def print_system_context() -> None:
    print_section("66. Local system context")

    print("Operating system:", platform.system())
    print("Platform:", platform.platform())
    print("Python:", platform.python_version())
    print("Current user:", getpass.getuser())

    print(
        """
SSH behavior depends on the installed OpenSSH implementation and operating
system. Commands shown in this study file should therefore be checked against
the local system's version and documentation before production use.
"""
    )


# =============================================================================
# SECTION 66: SAFE LOCAL DEMONSTRATION
# =============================================================================

def demonstrate_local_subprocess() -> None:
    print_section("67. Safe local subprocess demonstration")

    command = ["python", "--version"]

    try:
        result = run_local_command(command)

        print("Command:", shlex.join(command))
        print("Return code:", result.returncode)
        print("stdout:", result.stdout.strip())
        print("stderr:", result.stderr.strip())

    except (OSError, subprocess.SubprocessError) as exc:
        print("Could not execute local command:", exc)

    print(
        """
The demonstration executes only a local Python version command.

Remote SSH commands are intentionally not executed automatically by this
study script. That avoids unexpected access to external systems.
"""
    )


# =============================================================================
# SECTION 67: INTEGRATED WORKFLOW
# =============================================================================

def integrated_ssh_workflow() -> None:
    print_section("68. Integrated SSH workflow")

    print(
        """
A disciplined SSH workflow can be:

    Prepare
        |
        +--> install/update OpenSSH
        +--> create protected key
        +--> verify server host identity
        |
        v
    Authenticate
        |
        +--> load key into ssh-agent if appropriate
        +--> use dedicated identity
        |
        v
    Connect
        |
        +--> ssh / ProxyJump
        |
        v
    Transfer
        |
        +--> scp for simple copying
        +--> rsync for synchronization
        |
        v
    Validate
        |
        +--> exit code
        +--> application health check
        +--> file/hash validation where required
        |
        v
    Monitor
        |
        +--> logs
        +--> authentication events
        +--> system health
        |
        v
    Maintain
        |
        +--> rotate keys
        +--> revoke old credentials
        +--> patch OpenSSH
        +--> review access
"""
    )


# =============================================================================
# SECTION 68: MAIN PROGRAM
# =============================================================================

def main() -> None:
    """
    Run the complete SSH learning sequence.

    The script intentionally avoids making arbitrary remote connections.
    """
    print_section("SSH complete study program")
    print(
        """
Topic:
    SSH architecture, keys, ssh-agent, scp, rsync

This program is educational and self-contained.
Remote SSH commands are displayed rather than automatically executed.
"""
    )

    print_system_context()

    explain_ssh_architecture()
    demonstrate_basic_ssh_commands()
    explain_connection_handshake()
    explain_key_algorithms()
    explain_key_generation()
    demonstrate_secure_file_permissions()
    explain_authorized_keys()
    explain_host_keys()
    explain_ssh_config()
    explain_ssh_agent()
    inspect_ssh_agent_environment()
    compare_authentication_methods()
    explain_sshd_config()
    explain_scp()
    explain_rsync()
    compare_scp_and_rsync()
    demonstrate_target_parsing()
    demonstrate_python_ssh_automation()
    demonstrate_error_handling()
    demonstrate_network_diagnostics()
    explain_verbose_debugging()
    explain_port_forwarding()
    explain_bastion_and_proxyjump()
    explain_connection_multiplexing()
    demonstrate_nonstandard_ports()
    explain_rsync_semantics()
    explain_rsync_performance()
    explain_security_hardening()
    explain_key_lifecycle()
    explain_ssh_certificates()
    explain_automation_accounts()
    demonstrate_fingerprints()
    explain_known_hosts_management()
    explain_tunneling_security()
    explain_ssh_performance()
    explain_ssh_environment()
    explain_tty()
    explain_channels()
    explain_sftp()
    demonstrate_common_mistakes()
    demonstrate_command_injection_prevention()
    demonstrate_transfer_verification()
    demonstrate_deployment_simulation()
    explain_backup_design()
    explain_zero_trust_context()
    explain_dns_risks()
    explain_ip_versions()
    explain_keepalives()
    demonstrate_retry_policy()
    demonstrate_local_ssh_inventory()
    demonstrate_key_inventory()
    demonstrate_fixed_remote_commands()
    explain_advanced_authentication()
    explain_hardware_backed_keys()
    explain_agent_security()
    explain_ssh_directory()
    explain_rsync_special_files()
    explain_rsync_metadata()
    explain_logging()
    explain_incident_response()
    explain_case_study()
    print_command_reference()
    ssh_decision_tree()
    demonstrate_edge_cases()
    run_tests()
    demonstrate_local_subprocess()
    integrated_ssh_workflow()

    print_section("End of SSH study program")
    print(
        """
Core distinctions to retain:

    SSH
        Secure remote communication protocol.

    SSH host key
        Identifies the server.

    SSH user key
        Authenticates a user.

    ssh-agent
        Holds authentication keys for local use.

    scp
        Copy-oriented file transfer.

    rsync
        Efficient synchronization.

    ProxyJump
        Routes SSH through an intermediate host.

    Port forwarding
        Carries other network traffic through SSH.

    known_hosts
        Stores trusted server host-key information.

    authorized_keys
        Stores public keys authorized for a user on the server.

A secure SSH design combines these mechanisms with least privilege, careful
key lifecycle management, host verification, network controls, logging, and
recovery procedures.
"""
    )


if __name__ == "__main__":
    main()
