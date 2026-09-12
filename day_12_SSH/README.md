# SSH: architecture, keys, ssh-agent, scp, and rsync

## Topic introduction

SSH, or Secure Shell, is a network protocol used for secure communication with remote systems. It is commonly associated with remote terminal access, but its architecture supports much more than interactive shells. SSH can carry remote commands, file-transfer subsystems, port-forwarded network traffic, and multiple logical channels through one encrypted connection.

This study script develops SSH knowledge from basic terminology to advanced operational concepts. It covers SSH client and server architecture, the connection lifecycle, host keys, user authentication, public and private keys, `authorized_keys`, `known_hosts`, `ssh-agent`, client and server configuration, `scp`, `rsync`, SFTP, port forwarding, bastion hosts, `ProxyJump`, connection multiplexing, automation, security hardening, troubleshooting, performance, key lifecycle management, certificates, and production architecture.

The examples use standard Python functionality wherever executable demonstrations are useful. Remote SSH operations are represented as commands rather than automatically executed, preventing the study script from making unexpected connections to external systems.

## SSH architecture

The fundamental SSH architecture consists of a client and a server.

The SSH client runs on the machine initiating the connection. The `ssh` command is the standard OpenSSH client.

The SSH server runs on the destination machine. The OpenSSH server daemon is normally called `sshd`.

A simplified connection is:

    SSH client
        |
        | TCP connection
        v
    SSH server
        |
        +--> host-key verification
        |
        +--> user authentication
        |
        +--> encrypted session
        |
        +--> shell, command, forwarding, or subsystem

The default TCP port conventionally used by SSH is 22. Port 22 is not a fundamental requirement of the protocol. An SSH server can listen on another port.

The script demonstrates how SSH command arguments can be constructed programmatically without executing them.

## The two identities involved in SSH

One of the most important SSH concepts is the distinction between server identity and user identity.

### Server identity

The server uses a host key to identify itself.

The client stores information about previously recognized server host keys in `known_hosts`.

This answers:

    "Am I connecting to the server I intended to connect to?"

### User identity

A user can authenticate with a public/private key pair.

The server can store the user's public key in `authorized_keys`.

This answers:

    "Is this user authorized to log in?"

These are separate security mechanisms. A server can have a valid host identity while rejecting a particular user. Likewise, successful user authentication does not eliminate the need for host verification.

## The SSH connection lifecycle

A simplified SSH connection lifecycle is:

    TCP connection
        |
        v
    protocol negotiation
        |
        v
    algorithm negotiation
        |
        v
    cryptographic key exchange
        |
        v
    server host-key verification
        |
        v
    user authentication
        |
        v
    encrypted SSH session

The actual SSH protocol contains considerably more detail, but this sequence provides a useful mental model.

SSH uses cryptographic mechanisms to provide confidentiality and integrity. Authentication establishes identities and authorization.

Encryption by itself does not establish that the remote endpoint is the intended endpoint. Host-key verification is therefore a fundamental component of SSH security.

## Cryptographic keys

SSH uses asymmetric cryptography for public-key authentication and server identity.

A key pair contains:

- a private key
- a public key

The private key is secret and must be protected.

The public key is intended to be distributed to systems that need to verify authentication involving the corresponding private key.

For a normal public-key login, the private key does not need to be copied to the remote server. The client proves possession of the private key, while the server verifies the proof using the authorized public key.

## SSH key algorithms

The script introduces several important key algorithms.

### Ed25519

Ed25519 is a modern public-key signature algorithm and is commonly a strong default for new OpenSSH user keys.

A typical command is:

    ssh-keygen -t ed25519

### RSA

RSA is an older but still widely deployed public-key algorithm. Existing RSA keys can remain operational when appropriately configured, but new deployments should use modern configurations and adequate key sizes.

### ECDSA

ECDSA is an elliptic-curve public-key algorithm supported by OpenSSH.

### DSA

DSA is obsolete and should not be used for modern SSH authentication.

Algorithm availability depends on the installed OpenSSH version and security configuration.

## Generating an SSH key

A common command for generating an Ed25519 key is:

    ssh-keygen -t ed25519

The resulting files commonly resemble:

    ~/.ssh/id_ed25519
    ~/.ssh/id_ed25519.pub

The exact filename can be changed during key generation.

A private key should normally have a strong passphrase. The passphrase protects the private key if the key file itself is obtained by an attacker.

File-system permissions provide another layer of protection.

## SSH file permissions

On Unix-like systems, typical SSH permissions include:

    ~/.ssh/                  0700
    private key              0600
    public key               0644
    authorized_keys          0600

The exact requirements depend on the operating system, SSH implementation, configuration, ownership, and filesystem.

A private key should never be intentionally exposed through source code, logs, screenshots, configuration repositories, or public storage.

The Python script creates temporary simulated key files and demonstrates the distinction between restrictive private-key permissions and more permissive public-key permissions.

## `authorized_keys`

A server can authorize public-key authentication using:

    ~/.ssh/authorized_keys

A simplified authentication relationship is:

    Client private key
          |
          | cryptographic proof
          v
    Server authorized_keys
          |
          | matching public key
          v
      authentication

The server does not need the client's private key.

An `authorized_keys` entry can also contain restrictions. Depending on the SSH configuration and OpenSSH version, restrictions can limit commands, source addresses, agent forwarding, TCP forwarding, pseudo-terminal allocation, and other capabilities.

This is particularly useful for automation accounts.

A deployment key, for example, does not necessarily need the same privileges as a human administrator.

## Host keys and `known_hosts`

The SSH server has its own host keys.

Common server-side files include:

    /etc/ssh/ssh_host_*_key
    /etc/ssh/ssh_host_*_key.pub

The client normally maintains a database of recognized server host keys in:

    ~/.ssh/known_hosts

When connecting to a server for the first time, SSH may display a host-key fingerprint and ask whether the server should be trusted.

The secure approach is to verify the fingerprint using a trusted channel before accepting it.

A changed host key can have legitimate causes, such as:

- server reinstallation
- host migration
- replacement of host keys
- infrastructure changes

It can also indicate a security problem.

Possible explanations include:

- DNS or routing problems
- connecting to the wrong system
- server replacement without proper key management
- a man-in-the-middle attempt
- a compromised environment

A host-key warning should therefore be investigated rather than bypassed.

## Fingerprints

A cryptographic fingerprint is a compact representation of key material.

Instead of manually comparing a large cryptographic key, an administrator can compare a short fingerprint.

OpenSSH commonly displays SHA-256 fingerprints.

The important security principle is that the fingerprint must come from a trusted source. Obtaining a fingerprint from the same potentially compromised connection does not independently prove the server's identity.

The Python script demonstrates fingerprint generation using SHA-256 for educational purposes.

## `ssh-keygen`

`ssh-keygen` is one of the most important SSH utilities.

Common operations include:

    ssh-keygen -t ed25519
    ssh-keygen -lf ~/.ssh/id_ed25519.pub
    ssh-keygen -F hostname
    ssh-keygen -R hostname

The first generates a key.

The second displays key fingerprint information.

The third searches known host information.

The fourth removes a selected host entry.

Removing a host entry is not itself a security solution. If a host key changes unexpectedly, the new key should first be independently verified.

## SSH client configuration

The standard user-level client configuration file is commonly:

    ~/.ssh/config

It allows connection parameters to be represented through a short host alias.

A configuration can conceptually look like:

    Host production
        HostName server.example.com
        User deploy
        Port 22
        IdentityFile ~/.ssh/id_ed25519
        IdentitiesOnly yes

The user can then connect with:

    ssh production

Important SSH client directives include:

- `Host`
- `HostName`
- `User`
- `Port`
- `IdentityFile`
- `IdentitiesOnly`
- `ForwardAgent`
- `LocalForward`
- `RemoteForward`
- `DynamicForward`
- `ProxyJump`
- `ProxyCommand`
- `ServerAliveInterval`
- `ServerAliveCountMax`
- `StrictHostKeyChecking`
- `UserKnownHostsFile`

Configuration improves repeatability and reduces long command lines, but it should still be reviewed as security-sensitive configuration.

## `IdentitiesOnly`

An SSH agent may contain multiple identities.

When connecting to a server, the SSH client can potentially try several available identities. A server may reject a connection after too many unsuccessful authentication attempts.

`IdentitiesOnly yes` can be useful when the connection should use only explicitly configured identity files.

For sensitive systems, explicit identity selection makes the authentication behavior easier to understand and audit.

## `ssh-agent`

`ssh-agent` is a local process that holds private-key identities for SSH authentication.

The basic problem is straightforward.

A private key may be protected by a passphrase. Re-entering the passphrase every time the key is used can be inconvenient.

An agent allows the user to unlock the key once and then use the agent for subsequent cryptographic authentication operations.

The conceptual architecture is:

    Private key
        |
        | user unlocks key
        v
    ssh-agent
        |
        | signing/authentication operations
        v
    ssh client
        |
        v
    SSH server

Typical commands include:

    eval "$(ssh-agent -s)"
    ssh-add ~/.ssh/id_ed25519
    ssh-add -l
    ssh-add -D

`ssh-add -l` lists loaded identities.

`ssh-add -D` removes all identities from the agent.

An agent is not a replacement for endpoint security. Malware running with appropriate local access may attempt to interact with the agent.

## Agent forwarding

Agent forwarding allows an SSH connection to make the local agent available to a remote host.

A common command is:

    ssh -A user@host

This can be convenient when using a trusted intermediate system to reach another system.

The security problem is that forwarding extends the trust boundary.

The remote system can potentially request authentication operations from the forwarded agent.

Therefore, agent forwarding should be used selectively and should generally be avoided when the intermediate host is not fully trusted.

## Password authentication versus public-key authentication

Password authentication and public-key authentication use different security models.

Password authentication generally involves a password credential known to the user and a server-side authentication mechanism.

Public-key authentication involves a private key on the client and a public key authorized on the server.

Public-key authentication is particularly useful for automation because an automation process can authenticate without storing a reusable plaintext password.

That does not mean public-key authentication is automatically secure.

Security still depends on:

- private-key protection
- authorization
- key lifecycle management
- endpoint security
- host verification
- server configuration
- least privilege
- revocation

## SSH server configuration

The OpenSSH server configuration is commonly found at:

    /etc/ssh/sshd_config

Some systems also use configuration fragments under:

    /etc/ssh/sshd_config.d/

Important directives include:

### `Port`

Controls the TCP listening port.

### `PermitRootLogin`

Controls direct root login policy.

Direct root login should generally be restricted unless there is a justified operational reason.

### `PasswordAuthentication`

Controls password-based authentication.

### `PubkeyAuthentication`

Controls public-key authentication.

### `AllowUsers`

Restricts which users may authenticate.

### `AllowGroups`

Restricts authentication to selected groups.

### `MaxAuthTries`

Controls the number of authentication attempts allowed during a connection.

### `AllowTcpForwarding`

Controls TCP forwarding.

### `X11Forwarding`

Controls X11 forwarding.

### `ClientAliveInterval` and `ClientAliveCountMax`

Provide server-side connection liveness mechanisms.

## Validating SSH server configuration

A configuration error can prevent administrators from connecting.

A commonly used OpenSSH validation command is:

    sshd -t

Production configuration changes should be validated before restarting or reloading the SSH service.

A useful operational practice is to keep an existing administrative session open while changing SSH configuration. A second connection should be tested before closing the existing session.

This reduces the risk of locking administrators out because of a configuration error.

## `scp`

`scp` provides a straightforward command-line method for copying files using SSH.

Upload:

    scp report.csv user@host:/home/user/reports/

Download:

    scp user@host:/home/user/reports/report.csv ./report.csv

Recursive copy:

    scp -r directory/ user@host:/remote/path/

A non-standard SSH port is specified using uppercase `-P`:

    scp -P 2222 file user@host:/path/

`scp` is useful for simple copy operations.

Its conceptual model is:

    local source
        |
        | SSH transport
        v
    remote destination

For repeated synchronization of directory trees, `rsync` often provides better semantics and efficiency.

Modern OpenSSH versions have changed aspects of the implementation underlying `scp`, so behavior should be checked against the installed version rather than assuming behavior from older OpenSSH releases.

## `rsync`

`rsync` is designed for efficient file synchronization.

A common SSH-backed command is:

    rsync -av project/ user@host:/srv/project/

The tool compares source and destination state and can avoid transferring data that does not need to be retransmitted.

Important options include:

### `-a`

Archive mode. It enables a collection of preservation and recursive behaviors.

### `-v`

Verbose output.

### `-n`

Dry run. It shows intended changes without applying them.

### `-z`

Compresses transfer data.

### `--delete`

Removes destination-side files that are not present in the source.

### `--exclude`

Excludes selected files or directories.

### `--progress`

Shows transfer progress.

### `-e`

Selects the remote shell or transport command.

For example:

    rsync -avz -e "ssh -p 2222" ./site/ user@host:/var/www/site/

## The importance of the trailing slash in rsync

These commands are not equivalent:

    rsync -av source/ destination/

and:

    rsync -av source destination/

The trailing slash changes what rsync treats as the source content.

With:

    source/

the contents of the directory are synchronized.

Without the trailing slash, directory structure semantics can produce a different destination layout.

This is one of the most common rsync mistakes.

Testing with:

    rsync -avn ...

before changing production data makes the intended behavior easier to verify.

## `rsync --delete`

`--delete` is powerful because it makes the destination more closely mirror the source.

It is also dangerous.

Suppose the destination contains:

    report.pdf

and the source no longer contains that file.

With `--delete`, the destination copy can be removed.

A safer operational process is:

    dry run
        |
        v
    inspect changes
        |
        v
    confirm source and destination
        |
        v
    execute synchronization
        |
        v
    validate result

A synchronization mirror is not automatically a complete backup system.

## `scp` versus `rsync`

The tools serve different purposes.

| Requirement | scp | rsync |
|---|---|---|
| Simple one-time copy | Strong | Strong |
| Repeated synchronization | Limited | Strong |
| Incremental synchronization | Not its primary purpose | Core capability |
| Dry-run workflow | Limited | Strong |
| Destination deletion | Not its primary purpose | Supported |
| Directory synchronization | Basic | Strong |
| Learning simplicity | Very high | Moderate |
| Deployment synchronization | Possible | Commonly suitable |
| Large repeated transfers | Less suitable | Often preferable |

A simple practical rule is:

    simple copy -> scp

    repeated synchronization -> rsync

The correct choice still depends on the exact workflow.

## SFTP

SFTP means SSH File Transfer Protocol.

It is a distinct file-transfer protocol/subsystem that commonly runs through SSH.

A typical command is:

    sftp user@host

SFTP provides interactive operations such as:

    ls
    cd
    get
    put
    mkdir
    rm

The distinction is useful:

    scp
        Copy-oriented tool.

    sftp
        Interactive file-transfer protocol.

    rsync
        Synchronization tool optimized for efficiently transferring changes.

## SSH target syntax

SSH commonly uses:

    user@hostname

For file-transfer tools, a remote path is often expressed as:

    user@hostname:/remote/path

For example:

    alice@server.example.com:/srv/application/

The Python script contains a parser for common `user@host:path` syntax. The parser intentionally handles common scp/rsync-style targets rather than attempting to implement every possible URI grammar.

## Remote command execution

SSH can execute commands without opening a long-lived interactive shell.

For example:

    ssh user@host "uname -a"

This is especially useful for automation.

The command architecture becomes:

    local automation
        |
        v
    SSH authentication
        |
        v
    remote command
        |
        v
    exit code + stdout + stderr

Automation should capture and interpret:

- exit code
- standard output
- standard error
- timeout
- authentication failure
- connection failure

A successful SSH connection does not guarantee that the remote command succeeded.

## SSH exit codes

A return code of zero conventionally indicates success.

A return code such as 255 is commonly associated with SSH-level failures, although the precise behavior depends on the command and environment.

A different non-zero return code can represent failure of the remote command itself.

Therefore, diagnostics should distinguish:

    SSH connection failure

from:

    successful SSH connection + failed remote command

This distinction is important for deployment and monitoring systems.

## Python automation with OpenSSH

Python can automate SSH using the system's OpenSSH tools through `subprocess`.

The script deliberately uses argument lists rather than constructing shell command strings.

Preferred pattern:

    subprocess.run(["ssh", "user@host", "command"])

Riskier pattern:

    subprocess.run(f"ssh {user}@{host} {command}", shell=True)

The second pattern can introduce shell injection when values contain attacker-controlled shell syntax.

Good automation design includes:

- argument validation
- explicit timeouts
- controlled retries
- exit-code handling
- stderr capture
- host-key policy
- least-privilege accounts
- careful logging

## Command injection

Command injection occurs when untrusted data becomes executable shell syntax.

Consider a command constructed by concatenating arbitrary input into a shell command.

If the input contains shell metacharacters, the resulting command can perform actions beyond the intended operation.

Using an argument list prevents Python itself from invoking a shell for that subprocess.

Remote command construction can still involve another shell, so the remote-side command must also be designed carefully.

The strongest design is to use fixed commands where possible and validate all dynamic values.

## DNS and SSH identity

DNS answers a location question:

    "Which IP address should the hostname resolve to?"

SSH host-key verification answers an identity question:

    "Which cryptographic server identity did I reach?"

These are different concepts.

A trusted DNS system does not make host-key verification unnecessary.

This is why an unexpected host-key change should be investigated even when the hostname itself appears correct.

## IPv4 and IPv6

SSH can operate over both IPv4 and IPv6.

A hostname can have:

    A
        IPv4 records

    AAAA
        IPv6 records

Connectivity can differ between address families.

OpenSSH provides:

    ssh -4 user@host

and:

    ssh -6 user@host

These can help diagnose situations where one address family works and the other does not.

## Verbose SSH debugging

OpenSSH provides diagnostic modes:

    ssh -v user@host
    ssh -vv user@host
    ssh -vvv user@host

Verbose output can reveal:

- configuration processing
- identity selection
- host-key verification
- authentication attempts
- algorithm negotiation
- connection progress

When sharing verbose output, review it for sensitive information such as usernames, hostnames, paths, internal addresses, and configuration details.

## Network troubleshooting

SSH failures should be diagnosed layer by layer.

A useful sequence is:

    hostname resolution
        |
        v
    network reachability
        |
        v
    TCP port reachability
        |
        v
    sshd availability
        |
        v
    host-key verification
        |
        v
    user authentication
        |
        v
    authorization
        |
        v
    remote command

Common failure categories include:

### DNS failure

The hostname cannot be resolved.

### Connection refused

The host is reachable, but the target TCP port is not accepting the connection.

### Connection timeout

A firewall, routing problem, unavailable service, or network issue may be responsible.

### Permission denied

Authentication failed or the authenticated identity was not authorized.

### Host-key failure

The server identity does not match the expected identity.

### Remote command failure

SSH succeeded, but the command returned a non-zero status.

The Python script demonstrates basic hostname resolution and TCP port testing without performing an SSH login.

## Port forwarding

SSH can carry network traffic beyond ordinary shell sessions.

### Local forwarding

A simplified example is:

    ssh -L 8080:internal-db:5432 user@bastion

The conceptual path is:

    local application
        |
        v
    localhost:8080
        |
        v
    SSH connection
        |
        v
    internal-db:5432

This can allow a local application to access an internal service through an SSH host.

### Remote forwarding

A remote forwarding example is:

    ssh -R 9000:localhost:3000 user@server

This can make a local service accessible through a remote listening port, depending on SSH server configuration.

### Dynamic forwarding

A SOCKS proxy can be created using:

    ssh -D 1080 user@server

Port forwarding is powerful but changes network boundaries. It can unintentionally expose internal services or bypass intended segmentation.

Relevant controls include:

- `AllowTcpForwarding`
- `PermitOpen`
- `GatewayPorts`

## Bastion hosts

A bastion host is an intermediate server through which administrative connections pass.

A typical architecture is:

    Developer
        |
        v
    Bastion
        |
        v
    Private server

Private servers do not need direct public exposure.

A bastion can centralize:

- access control
- logging
- network entry
- patching
- monitoring

The trade-off is that the bastion becomes critical infrastructure. Its security and availability must be managed carefully.

## `ProxyJump`

OpenSSH provides `ProxyJump` for connections through an intermediate host.

Command-line example:

    ssh -J bastion user@private-server

Configuration can use:

    Host private-server
        HostName 10.0.0.10
        User deploy
        ProxyJump bastion

This provides a cleaner architecture than exposing every internal server directly to the public network.

## SSH connection multiplexing

OpenSSH can reuse an existing SSH connection for additional sessions.

Relevant options include:

- `ControlMaster`
- `ControlPath`
- `ControlPersist`

The conceptual architecture is:

    first connection
        |
        v
    persistent master connection
        |
        +--> session
        +--> session
        +--> session

Connection reuse can reduce repeated handshake overhead, which can matter in high-latency environments or automation systems that issue many short SSH commands.

Control sockets are security-sensitive files and must be protected appropriately.

## Keepalives

Long-running SSH connections can be interrupted by NAT devices, firewalls, or idle connection policies.

Client-side options include:

    ServerAliveInterval
    ServerAliveCountMax

Server-side options include:

    ClientAliveInterval
    ClientAliveCountMax

Keepalives can help detect dead connections and maintain desired connection behavior.

They should not be configured unnecessarily aggressively because frequent keepalive traffic creates additional network activity.

## SSH performance

SSH performance depends on multiple factors.

### Network bandwidth

Determines how much data can be transmitted per unit time.

### Network latency

High latency increases the cost of operations requiring round trips.

### CPU

Encryption and compression consume CPU resources.

### Compression

Compression can reduce network traffic for compressible data but increases CPU work.

Compression may help for:

- text
- source code
- structured logs
- highly compressible data

Compression often provides little benefit for:

- JPEG images
- MP4 video
- ZIP archives
- already-compressed backups

### Connection setup

Repeated connections can create unnecessary handshake overhead.

Connection multiplexing can reduce this cost.

### File count

A directory containing millions of small files can be limited by metadata operations rather than raw network bandwidth.

## rsync performance

`rsync` performance depends on:

- network bandwidth
- network latency
- CPU
- filesystem performance
- number of files
- changed data
- compression
- metadata operations
- encryption overhead

The correct optimization depends on the workload.

For example:

    slow network + compressible data
        -> compression may help

    fast network + CPU-limited host
        -> compression may hurt

    repeated large files with small changes
        -> rsync's synchronization design may reduce transferred data

    millions of small files
        -> metadata and filesystem operations may dominate

Benchmarking the actual environment is more reliable than assuming a universal optimization.

## rsync metadata preservation

Archive mode preserves a collection of filesystem properties, but it is not a universal guarantee that every filesystem feature will be reproduced.

Specialized options can address:

- ACLs
- extended attributes
- hard links
- sparse files
- ownership
- symbolic links
- timestamps
- permissions

Examples include:

    -A
    -X
    -H
    -S

These should be selected according to the actual requirements.

Additional preservation can increase complexity, privilege requirements, compatibility constraints, and transfer cost.

## SSH security hardening

A secure SSH deployment should be based on layered controls.

Important principles include:

- use supported OpenSSH versions
- patch the operating system
- protect private keys
- use strong authentication
- restrict allowed users
- avoid unnecessary root access
- apply least privilege
- verify host keys
- restrict forwarding
- use network segmentation
- monitor authentication
- maintain key inventories
- rotate credentials
- revoke unused credentials
- protect automation accounts

Changing the SSH port can reduce unsolicited scanning noise, but it is not a replacement for authentication security or system hardening.

## Least privilege

Least privilege means granting an identity only the permissions required for its role.

A human administrator may need shell access.

A deployment process may only need permission to update a particular directory.

A monitoring account may only need permission to run a fixed health-check command.

These identities should not automatically share the same credentials or privileges.

Least privilege reduces blast radius when credentials are compromised.

## SSH key lifecycle

SSH keys should be managed through a complete lifecycle:

    generation
        |
        v
    secure storage
        |
        v
    authorization
        |
        v
    operational use
        |
        v
    rotation
        |
        v
    revocation

Key management is not finished when the key is generated.

An organization should know:

- who owns a key
- what systems trust it
- what environment it belongs to
- when it should be rotated
- how it can be revoked
- what happens if it is lost or compromised

Using separate keys for different environments can reduce the blast radius of compromise.

## SSH certificates

SSH certificates introduce a trust model based on a Certificate Authority.

Conceptually:

    Certificate Authority
            |
            | signs
            v
    user or host public key
            |
            v
    SSH server trusts CA

A certificate can carry identity and validity information.

The main advantage is centralized trust.

Instead of placing every user's public key on every server, servers can trust an SSH Certificate Authority.

This can simplify large-scale identity management and support shorter-lived credentials.

The CA itself becomes extremely sensitive infrastructure and must be strongly protected.

## Automation accounts

Automation should normally use dedicated identities.

A production deployment architecture can be:

    CI/CD system
        |
        | dedicated SSH key
        v
    deployment account
        |
        v
    restricted deployment operation

Useful controls include:

- dedicated Unix account
- dedicated SSH key
- restricted `authorized_keys` entry
- no unnecessary interactive shell
- no agent forwarding
- no unnecessary TCP forwarding
- limited filesystem permissions
- monitoring and audit logs

A deployment account should not automatically have unrestricted administrator privileges.

## Hardware-backed authentication

SSH can integrate with hardware-backed key mechanisms where supported.

The security model places sensitive cryptographic operations inside a security boundary rather than exposing the private-key operation entirely through ordinary filesystem storage.

Potential benefits include:

- stronger resistance to key theft
- hardware-backed protection
- user-presence controls
- stronger credential protection

Operational planning must account for:

- device loss
- replacement
- enrollment
- recovery
- compatibility
- administrative procedures

## Agent security

`ssh-agent` improves convenience, but it does not eliminate credential risk.

Potential threats include:

- local malware interacting with the agent
- unsafe agent forwarding
- too many identities loaded simultaneously
- accidental authentication against the wrong host

Good practices include:

- load only required keys
- remove unused identities
- use separate keys for sensitive environments
- avoid forwarding into untrusted systems
- use lifetime controls where appropriate

The agent should be treated as a security-sensitive local capability.

## SSH channels

An SSH connection can contain multiple logical channels.

These channels can support:

- interactive shells
- remote commands
- port forwarding
- subsystems such as SFTP

This explains why SSH is more than a remote terminal protocol.

A single authenticated and encrypted SSH connection can carry multiple logically distinct activities.

## Pseudo-terminals

Interactive SSH sessions commonly use a pseudo-terminal, or PTY.

An ordinary interactive login:

    ssh user@host

can allocate a terminal.

A non-interactive remote command:

    ssh user@host "uname -a"

may not require one.

PTY allocation matters for programs that expect terminal behavior, such as interactive shells and some terminal-oriented applications.

Automation should generally avoid unnecessary interactive terminal behavior.

## Logging and auditing

SSH logging can provide valuable information for security monitoring.

Useful audit information can include:

- username
- source address
- timestamp
- authentication method
- success or failure
- target host
- privileged actions

Sensitive secrets should never be logged.

Do not log:

- private-key contents
- passwords
- passphrases
- unnecessary authentication secrets

Verbose SSH output is useful for troubleshooting but should be reviewed before being shared externally.

## Credential compromise response

If a private SSH key is suspected to be compromised, deleting the local private-key file alone is insufficient.

The public key may remain authorized on production systems.

A conceptual response is:

    identify affected key
        |
        v
    identify systems trusting it
        |
        v
    revoke authorization
        |
        v
    generate replacement credential
        |
        v
    update systems
        |
        v
    review authentication logs
        |
        v
    investigate unauthorized activity

The important security boundary is authorization.

Removing the public key from `authorized_keys`, disabling the associated identity, or applying the relevant centralized revocation mechanism is necessary.

## SSH and zero-trust architecture

Traditional network security often relied heavily on network location.

A modern security architecture is more likely to require explicit authentication and authorization for every sensitive connection.

SSH contributes:

- encrypted transport
- host identity
- user identity
- public-key authentication
- forwarding controls
- access restrictions
- auditing

SSH does not constitute a complete zero-trust architecture by itself.

Application authorization, device security, network controls, identity lifecycle management, monitoring, and policy enforcement remain important.

## Backup architecture and rsync

`rsync` can be useful for backup transfer, but synchronization and backup are not identical.

A simple mirror can look like:

    source
       |
       v
    rsync
       |
       v
    backup destination

A robust backup system also needs:

- retention
- historical versions
- integrity verification
- access control
- encryption where appropriate
- monitoring
- recovery procedures
- recovery testing
- protection against accidental deletion

A mirror using `rsync --delete` can reproduce accidental deletions.

Therefore, a synchronization command should not automatically be treated as a complete backup strategy.

## File integrity verification

The Python script demonstrates SHA-256 file hashing.

A hash provides a compact representation of file contents.

For a transfer:

    source hash
        =
    destination hash

provides strong evidence that the two files contain identical data, assuming the comparison itself is trustworthy and SHA-256 is appropriate for the integrity requirement.

SSH already protects transport integrity, but application-level verification can be useful for critical workflows.

## Deployment with rsync

A deployment process can use rsync as follows:

    source application
        |
        v
    rsync dry run
        |
        v
    review proposed changes
        |
        v
    actual transfer
        |
        v
    application health check

A dry run is particularly important before enabling destructive behavior such as `--delete`.

A deployment system should also consider:

- rollback
- application compatibility
- atomicity
- permissions
- service restart requirements
- database migrations
- health checks
- monitoring

The correct deployment design depends on the application architecture.

## Retry strategy

Network failures can be transient.

A robust automation system should use bounded retries with exponential backoff where appropriate.

For example:

    attempt 1 -> 1 second
    attempt 2 -> 2 seconds
    attempt 3 -> 4 seconds
    attempt 4 -> 8 seconds

Not every failure should be retried.

Invalid authentication, invalid authorization, incorrect host keys, and broken commands are generally not fixed by repeated retries.

Retries should therefore distinguish transient infrastructure failures from permanent configuration or security failures.

## Common SSH mistakes

### Sharing private keys

Private keys should remain secret.

### Ignoring host-key warnings

This can conceal endpoint impersonation or infrastructure problems.

### Using root everywhere

This violates least privilege and increases the impact of credential compromise.

### Using one key everywhere

One compromised key can then affect many systems.

### Blindly using `rsync --delete`

This can remove destination data.

### Using shell strings with untrusted input

This can introduce command injection.

### Forwarding the agent everywhere

This expands the trust boundary.

### Disabling host-key verification to fix errors

This weakens server authentication.

### Changing SSH configuration without testing

A syntax or policy error can lock administrators out.

### Failing to maintain credential inventory

Unknown and obsolete keys are difficult to revoke.

## Production architecture example

A production architecture can separate human access from deployment access.

Human access:

    Developer
        |
        | protected user key
        v
    Bastion
        |
        | ProxyJump
        v
    Private application server

Deployment:

    CI/CD system
        |
        | dedicated deployment key
        v
    deployment account
        |
        v
    rsync dry run
        |
        v
    deployment
        |
        v
    health check

The design separates:

- human credentials
- automation credentials
- network entry
- server authorization
- application privileges

This reduces the blast radius of individual credential failures.

## SSH tool selection

A practical decision tree is:

    Need a remote shell?
        -> ssh

    Need a simple file copy?
        -> scp

    Need interactive file management?
        -> sftp

    Need repeated synchronization?
        -> rsync over SSH

    Need access through an intermediate host?
        -> ProxyJump

    Need access to an internal TCP service?
        -> SSH port forwarding

    Need many short SSH sessions?
        -> connection multiplexing

    Need large-scale centralized identity?
        -> SSH certificates and centralized key management

The tools are related but solve different problems.

## Practical command reference

| Task | Command |
|---|---|
| Connect | `ssh user@host` |
| Custom port | `ssh -p 2222 user@host` |
| Specific key | `ssh -i ~/.ssh/id_ed25519 user@host` |
| Remote command | `ssh user@host "uname -a"` |
| Verbose debugging | `ssh -vvv user@host` |
| Jump host | `ssh -J bastion user@private-host` |
| Generate Ed25519 key | `ssh-keygen -t ed25519` |
| List agent identities | `ssh-add -l` |
| Add key to agent | `ssh-add ~/.ssh/id_ed25519` |
| Remove all agent identities | `ssh-add -D` |
| Find known host | `ssh-keygen -F host` |
| Remove known host | `ssh-keygen -R host` |
| SCP upload | `scp file user@host:/path/` |
| SCP download | `scp user@host:/path/file .` |
| Recursive SCP | `scp -r directory user@host:/path/` |
| Basic rsync | `rsync -av source/ user@host:/path/` |
| rsync dry run | `rsync -avn source/ user@host:/path/` |
| rsync with compression | `rsync -avz source/ user@host:/path/` |
| rsync with deletion | `rsync -av --delete source/ user@host:/path/` |
| SFTP | `sftp user@host` |

## Edge cases covered by the script

The Python script demonstrates or discusses several situations that frequently cause problems:

- unusual hostname or target syntax
- IPv6
- paths containing spaces
- multiple SSH identities
- changed host keys
- rsync trailing-slash semantics
- destructive `--delete`
- compression overhead
- high-latency connections
- many small files
- automation credentials
- agent forwarding
- remote command injection
- metadata preservation
- connection retries

These cases matter because SSH commands that appear simple can behave differently when applied to production infrastructure.

## Implementation considerations

The Python examples deliberately separate command construction from execution.

This has several benefits:

- commands can be reviewed before execution
- unit tests can verify generated arguments
- shell interpretation can be avoided
- automation logic becomes easier to reason about
- accidental external connections are reduced

The script also uses standard-library components such as:

- `subprocess`
- `socket`
- `hashlib`
- `pathlib`
- `dataclasses`
- `tempfile`
- `shlex`

No third-party Python package is required for the educational demonstrations.

The actual `ssh`, `scp`, `rsync`, and `ssh-agent` programs are external operating-system tools and therefore depend on the local system.

## Testing

The script includes built-in tests for:

- SSH command construction
- SSH target parsing
- exponential backoff calculation
- SHA-256 file hashing

These tests demonstrate an important automation principle: security-sensitive command generation should be testable independently from actual network execution.

Testing command construction is safer than requiring a real production SSH server merely to verify argument formatting.

## Security considerations

SSH security depends on multiple layers working together.

The most important concepts covered by the script are:

- protect private keys
- use strong authentication
- verify host keys
- restrict authorized identities
- apply least privilege
- avoid unnecessary root access
- control forwarding
- limit agent forwarding
- separate human and automation credentials
- maintain key inventories
- rotate and revoke keys
- monitor authentication activity
- protect bastion hosts
- validate SSH configuration
- avoid command injection
- test destructive rsync operations
- maintain recovery procedures

A secure SSH deployment is therefore not defined by one command or one configuration directive. It is the result of cryptographic identity, authorization, network design, endpoint protection, credential management, and operational discipline working together.

## Real-world applications

SSH is widely applicable to:

- Linux server administration
- cloud infrastructure administration
- software deployment
- CI/CD systems
- remote troubleshooting
- infrastructure automation
- secure file transfer
- server backups
- bastion-based access
- private-network administration
- database access through tunnels
- development environments
- configuration management
- monitoring
- incident response
- enterprise identity management

The combination of SSH, public-key authentication, `ssh-agent`, `ProxyJump`, `scp`, and `rsync` forms a practical foundation for secure remote administration and automation.

## Relationship between the major components

The core concepts can be connected as follows:

    SSH
     |
     +--> Host identity
     |      |
     |      +--> host keys
     |      +--> known_hosts
     |
     +--> User identity
     |      |
     |      +--> private key
     |      +--> public key
     |      +--> authorized_keys
     |
     +--> Credential handling
     |      |
     |      +--> ssh-agent
     |
     +--> Remote access
     |      |
     |      +--> shell
     |      +--> commands
     |
     +--> File transfer
     |      |
     |      +--> scp
     |      +--> sftp
     |      +--> rsync
     |
     +--> Network transport
            |
            +--> local forwarding
            +--> remote forwarding
            +--> dynamic forwarding
            +--> ProxyJump
            +--> connection multiplexing

Understanding these relationships is more valuable than memorizing individual commands because it explains why each SSH component exists and when it should be used.
