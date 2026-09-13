"""
Package Management on Linux
============================

A self-contained study script covering:

- Package management fundamentals
- Packages, package managers, repositories, metadata, dependencies
- Debian/Ubuntu: apt, apt-get, dpkg
- Red Hat/Fedora: yum, dnf, rpm
- Repository configuration and package sources
- Installation, removal, upgrade, search, inspection
- Dependency resolution
- Package caches and metadata
- Version selection and pinning concepts
- Repository trust and package signing
- Configuration files
- Package lifecycle and transactions
- Common errors and troubleshooting
- Security updates
- Automation and non-interactive installation
- Idempotency
- Production considerations
- Performance and operational trade-offs
- Safe Python automation through dry-run command construction
- Comparison of apt, yum/dnf, and low-level package tools

The examples are designed to teach Linux package management without
requiring package-management commands to be executed automatically.
"""

from __future__ import annotations

import platform
import re
import shlex
import shutil
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


# =============================================================================
# SECTION 1: FUNDAMENTALS
# =============================================================================

def section(title: str) -> None:
    """Print a readable study section heading."""
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def explain_term(term: str, definition: str) -> None:
    """Display a concise definition."""
    print(f"\n{term}")
    print(f"  {definition}")


def demonstrate_fundamentals() -> None:
    section("1. Package Management Fundamentals")

    terms = {
        "Package": (
            "A packaged unit of software containing files, metadata, version "
            "information, and dependency information."
        ),
        "Package manager": (
            "A system tool that installs, removes, upgrades, queries, and "
            "tracks software packages."
        ),
        "Repository": (
            "A trusted software source containing packages and metadata that "
            "a package manager can discover and download."
        ),
        "Dependency": (
            "Software required by another package for correct operation."
        ),
        "Package metadata": (
            "Information such as package name, version, architecture, "
            "dependencies, maintainer, description, and checksums."
        ),
        "Package database": (
            "Local system state recording installed packages and their "
            "metadata."
        ),
        "Transaction": (
            "A package-management operation that changes installed software, "
            "such as installing or upgrading packages."
        ),
    }

    for term, definition in terms.items():
        explain_term(term, definition)

    print("\nThe general package-management workflow is:")
    workflow = [
        "Identify the required software",
        "Refresh or obtain repository metadata",
        "Resolve dependencies",
        "Select package versions and architecture",
        "Download package files",
        "Verify package authenticity and integrity",
        "Install or upgrade packages",
        "Update the local package database",
        "Run package configuration scripts when applicable",
        "Verify the resulting installation",
    ]

    for number, step in enumerate(workflow, start=1):
        print(f"  {number}. {step}")


# =============================================================================
# SECTION 2: PACKAGE FORMATS
# =============================================================================

@dataclass
class Package:
    """A simplified representation of a Linux package."""

    name: str
    version: str
    architecture: str
    dependencies: List[str] = field(default_factory=list)
    repository: Optional[str] = None

    def identifier(self) -> str:
        """Return a human-readable package identifier."""
        return f"{self.name}={self.version} [{self.architecture}]"


def demonstrate_package_structure() -> None:
    section("2. What a Package Contains")

    nginx = Package(
        name="nginx",
        version="1.24.0",
        architecture="amd64",
        dependencies=["libc6", "libpcre2-8-0", "zlib1g"],
        repository="stable",
    )

    print("Example conceptual package:")
    print(f"  Name:         {nginx.name}")
    print(f"  Version:      {nginx.version}")
    print(f"  Architecture: {nginx.architecture}")
    print(f"  Repository:   {nginx.repository}")
    print(f"  Dependencies: {', '.join(nginx.dependencies)}")

    explain_term(
        "Debian package",
        "A package normally distributed as a .deb file and managed at a "
        "low level by dpkg. apt provides higher-level repository and "
        "dependency-management functionality."
    )

    explain_term(
        "RPM package",
        "A package normally distributed as an RPM file and managed at a "
        "low level by rpm. yum and dnf provide higher-level repository and "
        "dependency-management functionality."
    )


# =============================================================================
# SECTION 3: PACKAGE MANAGER LAYERS
# =============================================================================

def demonstrate_tool_layers() -> None:
    section("3. High-Level and Low-Level Package Tools")

    layers = [
        (
            "Debian/Ubuntu",
            "apt",
            "High-level package management, repositories, dependency resolution",
        ),
        (
            "Debian/Ubuntu",
            "dpkg",
            "Low-level installation and package database operations",
        ),
        (
            "RHEL/CentOS/Fedora family",
            "dnf",
            "High-level package management and repository operations",
        ),
        (
            "Older Red Hat family",
            "yum",
            "High-level package management, historically dominant before dnf",
        ),
        (
            "RHEL/Fedora family",
            "rpm",
            "Low-level RPM package installation and package database operations",
        ),
    ]

    print(f"{'Family':<24} {'Tool':<10} Purpose")
    print("-" * 78)

    for family, tool, purpose in layers:
        print(f"{family:<24} {tool:<10} {purpose}")

    print(
        "\nImportant distinction: apt, dnf, and yum normally understand "
        "repositories and dependency relationships. dpkg and rpm operate "
        "closer to individual package files and local package databases."
    )


# =============================================================================
# SECTION 4: COMMAND REFERENCE
# =============================================================================

APT_COMMANDS: Dict[str, str] = {
    "apt update": "Refresh available package metadata.",
    "apt install PACKAGE": "Install a package and required dependencies.",
    "apt remove PACKAGE": "Remove a package while generally retaining configuration files.",
    "apt purge PACKAGE": "Remove a package and associated configuration files where supported.",
    "apt upgrade": "Upgrade installed packages without removing packages for dependency changes.",
    "apt full-upgrade": "Perform a more complete upgrade when dependency changes require additions/removals.",
    "apt search TERM": "Search package metadata for a term.",
    "apt show PACKAGE": "Display package metadata.",
    "apt list --installed": "List installed packages.",
    "apt autoremove": "Remove automatically installed packages that are no longer required.",
    "apt policy PACKAGE": "Display available and installed versions and repository priorities.",
}

DNF_COMMANDS: Dict[str, str] = {
    "dnf check-update": "Check whether updates are available.",
    "dnf install PACKAGE": "Install a package and dependencies.",
    "dnf remove PACKAGE": "Remove a package.",
    "dnf upgrade": "Upgrade installed packages.",
    "dnf search TERM": "Search repositories for packages.",
    "dnf info PACKAGE": "Display package information.",
    "dnf list installed": "List installed packages.",
    "dnf list available": "List packages available from enabled repositories.",
    "dnf repoquery PACKAGE": "Query package and repository information.",
    "dnf autoremove": "Remove packages installed as dependencies that are no longer needed.",
    "dnf clean all": "Clean cached package metadata and package files.",
}

YUM_COMMANDS: Dict[str, str] = {
    "yum install PACKAGE": "Install a package and dependencies.",
    "yum remove PACKAGE": "Remove a package.",
    "yum update": "Update installed packages.",
    "yum search TERM": "Search enabled repositories.",
    "yum info PACKAGE": "Display package information.",
    "yum list installed": "List installed packages.",
    "yum repolist": "Display configured repositories.",
}


def print_command_reference(title: str, commands: Dict[str, str]) -> None:
    print(f"\n{title}")
    for command, description in commands.items():
        print(f"  {command:<34} {description}")


def demonstrate_command_reference() -> None:
    section("4. Core Package-Management Commands")

    print_command_reference("APT", APT_COMMANDS)
    print_command_reference("DNF", DNF_COMMANDS)
    print_command_reference("YUM", YUM_COMMANDS)

    print("\nLow-level examples:")
    low_level = {
        "dpkg -i package.deb": "Install a local Debian package file.",
        "dpkg -l": "List packages known to the dpkg database.",
        "dpkg -L PACKAGE": "List files installed by a package.",
        "dpkg -S /path/to/file": "Find the package owning a file.",
        "rpm -i package.rpm": "Install a local RPM package.",
        "rpm -q PACKAGE": "Query whether an RPM package is installed.",
        "rpm -ql PACKAGE": "List files installed by an RPM package.",
        "rpm -qi PACKAGE": "Display installed RPM package metadata.",
        "rpm -qf /path/to/file": "Find the RPM package owning a file.",
    }

    for command, description in low_level.items():
        print(f"  {command:<30} {description}")


# =============================================================================
# SECTION 5: APT INSTALLATION WORKFLOW
# =============================================================================

def simulate_apt_install(package_name: str) -> List[str]:
    """
    Construct a safe educational representation of an apt installation.

    This function deliberately does not execute apt.
    """
    if not re.fullmatch(r"[A-Za-z0-9.+:_-]+", package_name):
        raise ValueError("Invalid package name for this demonstration.")

    return [
        "sudo apt update",
        f"sudo apt install {shlex.quote(package_name)}",
        f"apt show {shlex.quote(package_name)}",
    ]


def demonstrate_apt_installation() -> None:
    section("5. APT Installation Workflow")

    package_name = "curl"

    print(f"Requested package: {package_name}")
    print("\nConceptual commands:")
    for command in simulate_apt_install(package_name):
        print(f"  {command}")

    print(
        "\nThe first command refreshes repository metadata. The second "
        "asks apt to resolve and install the package. The third inspects "
        "metadata without installing anything."
    )

    print("\nImportant distinction:")
    print("  apt update   -> refresh package information")
    print("  apt upgrade  -> upgrade installed packages")
    print("  apt install  -> install a requested package")

    print(
        "\nConfusing 'update' with 'upgrade' is one of the most common "
        "beginner mistakes."
    )


# =============================================================================
# SECTION 6: DNF/YUM INSTALLATION
# =============================================================================

def simulate_dnf_install(package_name: str) -> List[str]:
    """Construct safe educational dnf commands without executing them."""
    if not re.fullmatch(r"[A-Za-z0-9.+:_-]+", package_name):
        raise ValueError("Invalid package name for this demonstration.")

    quoted = shlex.quote(package_name)
    return [
        f"sudo dnf install {quoted}",
        f"dnf info {quoted}",
        f"dnf repoquery {quoted}",
    ]


def demonstrate_dnf_installation() -> None:
    section("6. DNF and YUM Installation")

    package_name = "httpd"

    print("Modern Fedora and many modern Red Hat-family systems use dnf.")
    print(f"\nExample package: {package_name}")

    for command in simulate_dnf_install(package_name):
        print(f"  {command}")

    print("\nYUM compatibility:")
    print("  yum install httpd")
    print("  yum update")
    print("  yum search httpd")

    print(
        "\nThe exact command availability depends on the distribution and "
        "release. On systems where yum is provided as a compatibility "
        "interface, its behavior may be backed by dnf."
    )


# =============================================================================
# SECTION 7: REPOSITORIES
# =============================================================================

@dataclass
class Repository:
    """Simplified repository representation."""

    name: str
    base_url: str
    enabled: bool = True
    signed: bool = True
    priority: int = 500

    def status(self) -> str:
        return "enabled" if self.enabled else "disabled"


def demonstrate_repositories() -> None:
    section("7. Repositories")

    repositories = [
        Repository(
            name="distribution-main",
            base_url="https://mirror.example.invalid/main",
            enabled=True,
            signed=True,
            priority=500,
        ),
        Repository(
            name="distribution-updates",
            base_url="https://mirror.example.invalid/updates",
            enabled=True,
            signed=True,
            priority=400,
        ),
        Repository(
            name="third-party-example",
            base_url="https://packages.example.invalid",
            enabled=False,
            signed=True,
            priority=700,
        ),
    ]

    print(f"{'Repository':<26} {'Status':<10} {'Signed':<10} Priority")
    print("-" * 68)

    for repository in repositories:
        print(
            f"{repository.name:<26} "
            f"{repository.status():<10} "
            f"{str(repository.signed):<10} "
            f"{repository.priority}"
        )

    print("\nRepository configuration concepts:")
    print("  • Repository identity")
    print("  • Base URL or mirror")
    print("  • Enabled/disabled state")
    print("  • Distribution/release")
    print("  • Components or repository sections")
    print("  • Architecture")
    print("  • Signing keys")
    print("  • Repository priority or pinning")
    print("  • Metadata")
    print("  • Package availability")

    print("\nTypical Debian-family locations:")
    print("  /etc/apt/sources.list")
    print("  /etc/apt/sources.list.d/")

    print("\nTypical RPM-family locations:")
    print("  /etc/yum.repos.d/")
    print("  /etc/dnf/")
    print("  Repository definitions are commonly stored as .repo files.")


# =============================================================================
# SECTION 8: DEPENDENCY RESOLUTION
# =============================================================================

@dataclass
class DependencyGraph:
    """Small dependency graph used to demonstrate resolution."""

    dependencies: Dict[str, List[str]]

    def resolve(self, package_name: str) -> List[str]:
        """
        Return dependencies in installation order.

        Raises ValueError when a dependency cycle is detected.
        """
        result: List[str] = []
        visiting = set()
        visited = set()

        def visit(name: str) -> None:
            if name in visiting:
                raise ValueError(f"Dependency cycle detected involving {name}")

            if name in visited:
                return

            visiting.add(name)

            for dependency in self.dependencies.get(name, []):
                visit(dependency)

            visiting.remove(name)
            visited.add(name)
            result.append(name)

        visit(package_name)
        return result


def demonstrate_dependency_resolution() -> None:
    section("8. Dependency Resolution")

    graph = DependencyGraph(
        {
            "web-app": ["web-server", "database-client"],
            "web-server": ["network-library", "crypto-library"],
            "database-client": ["network-library"],
            "network-library": ["libc"],
            "crypto-library": ["libc"],
            "libc": [],
        }
    )

    installation_order = graph.resolve("web-app")

    print("Conceptual dependency graph:")
    print("  web-app")
    print("    ├── web-server")
    print("    │   ├── network-library")
    print("    │   │   └── libc")
    print("    │   └── crypto-library")
    print("    │       └── libc")
    print("    └── database-client")
    print("        └── network-library")

    print("\nOne valid dependency-first installation order:")
    for package in installation_order:
        print(f"  {package}")

    print(
        "\nA package manager must avoid installing dependencies repeatedly. "
        "It also has to detect conflicts and cycles."
    )

    cyclic_graph = DependencyGraph(
        {
            "package-a": ["package-b"],
            "package-b": ["package-c"],
            "package-c": ["package-a"],
        }
    )

    try:
        cyclic_graph.resolve("package-a")
    except ValueError as error:
        print(f"\nEdge case handled: {error}")


# =============================================================================
# SECTION 9: VERSIONING
# =============================================================================

@dataclass(frozen=True)
class VersionedPackage:
    name: str
    version: str
    repository: str


def version_key(version: str) -> Tuple:
    """
    Produce a simple educational version key.

    Real Debian and RPM version comparison rules are substantially more
    sophisticated than this demonstration.
    """
    pieces = re.findall(r"\d+|[A-Za-z]+", version)

    converted = []
    for piece in pieces:
        if piece.isdigit():
            converted.append((0, int(piece)))
        else:
            converted.append((1, piece.lower()))

    return tuple(converted)


def select_highest_version(packages: Iterable[VersionedPackage]) -> VersionedPackage:
    """Select the highest version using the simplified comparator."""
    packages = list(packages)

    if not packages:
        raise ValueError("No packages supplied.")

    return max(packages, key=lambda package: version_key(package.version))


def demonstrate_versions() -> None:
    section("9. Package Versions")

    candidates = [
        VersionedPackage("example", "1.9.0", "stable"),
        VersionedPackage("example", "2.0.0", "updates"),
        VersionedPackage("example", "2.1.0", "testing"),
    ]

    print("Available versions:")
    for package in candidates:
        print(
            f"  {package.name} {package.version} "
            f"from {package.repository}"
        )

    selected = select_highest_version(candidates)
    print(
        f"\nSimplified highest-version selection: "
        f"{selected.name} {selected.version}"
    )

    print(
        "\nReal package managers implement distribution-specific version "
        "comparison rules. Debian versions may contain epochs, revisions, "
        "and special ordering rules. RPM versions use epoch, version, and "
        "release semantics."
    )

    print("\nVersion-related concepts:")
    print("  • Installed version")
    print("  • Candidate version")
    print("  • Available version")
    print("  • Epoch")
    print("  • Release/revision")
    print("  • Repository priority")
    print("  • Version constraints")
    print("  • Pinning")


# =============================================================================
# SECTION 10: INSTALL, REMOVE, PURGE, UPGRADE
# =============================================================================

def demonstrate_lifecycle_operations() -> None:
    section("10. Package Lifecycle Operations")

    operations = [
        ("Install", "Add a package and required dependencies."),
        ("Upgrade", "Replace an installed version with a newer compatible version."),
        ("Downgrade", "Replace an installed package with an older version."),
        ("Remove", "Uninstall package files while configuration may remain."),
        ("Purge", "Remove package files and configuration files where supported."),
        ("Reinstall", "Install the package again, useful when package files are damaged."),
        ("Autoremove", "Remove no-longer-required automatically installed dependencies."),
        ("Hold/version lock", "Prevent or restrict automatic version changes."),
    ]

    for operation, description in operations:
        print(f"  {operation:<18} {description}")

    print("\nAPT examples:")
    print("  sudo apt install nginx")
    print("  sudo apt remove nginx")
    print("  sudo apt purge nginx")
    print("  sudo apt reinstall nginx")
    print("  sudo apt upgrade")

    print("\nDNF examples:")
    print("  sudo dnf install nginx")
    print("  sudo dnf remove nginx")
    print("  sudo dnf reinstall nginx")
    print("  sudo dnf upgrade")

    print(
        "\nRemoval does not necessarily mean that every configuration file "
        "created by software will disappear. Package-manager behavior and "
        "application-generated files must be distinguished."
    )


# =============================================================================
# SECTION 11: SEARCH AND INSPECTION
# =============================================================================

def demonstrate_search_and_inspection() -> None:
    section("11. Searching and Inspecting Packages")

    print("APT:")
    print("  apt search nginx")
    print("  apt show nginx")
    print("  apt policy nginx")
    print("  dpkg -L nginx")
    print("  dpkg -S /usr/sbin/nginx")

    print("\nDNF:")
    print("  dnf search nginx")
    print("  dnf info nginx")
    print("  dnf repoquery nginx")
    print("  rpm -ql nginx")
    print("  rpm -qf /usr/sbin/nginx")

    print("\nUseful questions during troubleshooting:")
    questions = [
        "Is the package installed?",
        "Which version is installed?",
        "Which repository provides the package?",
        "Which files does the package own?",
        "Which package owns a suspicious or missing file?",
        "Which dependencies are required?",
        "Are updates available?",
        "Is the repository enabled?",
        "Is the installed package architecture correct?",
    ]

    for question in questions:
        print(f"  • {question}")


# =============================================================================
# SECTION 12: PACKAGE FILES
# =============================================================================

def demonstrate_local_package_files() -> None:
    section("12. Installing Local .deb and .rpm Files")

    print("Debian-family package file:")
    print("  package.deb")

    print("Low-level installation:")
    print("  sudo dpkg -i package.deb")

    print("Higher-level dependency-aware approach:")
    print("  sudo apt install ./package.deb")

    print("\nRPM-family package file:")
    print("  package.rpm")

    print("Low-level installation:")
    print("  sudo rpm -i package.rpm")

    print("Higher-level dependency-aware approach:")
    print("  sudo dnf install ./package.rpm")

    print(
        "\nA local package file can be useful when software is distributed "
        "outside the normal repository. Repository installation is generally "
        "easier to maintain because metadata, updates, dependencies, and "
        "security mechanisms are integrated."
    )


# =============================================================================
# SECTION 13: REPOSITORY METADATA
# =============================================================================

@dataclass
class RepositoryMetadata:
    repository: str
    package_count: int
    architectures: List[str]
    signed: bool
    last_refresh: str

    def is_acceptable(self) -> bool:
        return self.signed and self.package_count > 0


def demonstrate_repository_metadata() -> None:
    section("13. Repository Metadata")

    metadata = RepositoryMetadata(
        repository="distribution-updates",
        package_count=12000,
        architectures=["amd64", "arm64"],
        signed=True,
        last_refresh="2026-09-13",
    )

    print(f"Repository:      {metadata.repository}")
    print(f"Package count:   {metadata.package_count}")
    print(f"Architectures:   {', '.join(metadata.architectures)}")
    print(f"Signed metadata: {metadata.signed}")
    print(f"Last refresh:    {metadata.last_refresh}")
    print(f"Acceptable:      {metadata.is_acceptable()}")

    print(
        "\nRepository metadata lets a package manager discover packages "
        "without downloading every package file. Refreshing metadata is "
        "therefore distinct from installing software."
    )


# =============================================================================
# SECTION 14: SECURITY AND TRUST
# =============================================================================

@dataclass
class PackageTrustResult:
    package_name: str
    signature_valid: bool
    checksum_valid: bool
    trusted_repository: bool

    @property
    def acceptable(self) -> bool:
        return (
            self.signature_valid
            and self.checksum_valid
            and self.trusted_repository
        )


def demonstrate_package_security() -> None:
    section("14. Package Security")

    result = PackageTrustResult(
        package_name="example-package",
        signature_valid=True,
        checksum_valid=True,
        trusted_repository=True,
    )

    print(f"Package:             {result.package_name}")
    print(f"Signature valid:     {result.signature_valid}")
    print(f"Checksum valid:      {result.checksum_valid}")
    print(f"Trusted repository:  {result.trusted_repository}")
    print(f"Accept package:      {result.acceptable}")

    print("\nSecurity concepts:")
    print("  • Repository trust")
    print("  • Package signatures")
    print("  • Cryptographic checksums")
    print("  • Signing keys")
    print("  • Key expiration and rotation")
    print("  • Secure transport")
    print("  • Repository configuration integrity")
    print("  • Supply-chain security")
    print("  • Timely security updates")

    print(
        "\nA checksum primarily verifies integrity of known content. A "
        "signature additionally establishes that the package or metadata "
        "was signed by a key trusted by the package-management system."
    )

    print(
        "\nSecurity warning: blindly installing packages from random websites "
        "or disabling signature verification undermines the package trust "
        "model."
    )


# =============================================================================
# SECTION 15: NON-INTERACTIVE INSTALLATION
# =============================================================================

def build_noninteractive_command(
    manager: str,
    package_name: str,
) -> List[str]:
    """
    Build a non-interactive package command without executing it.

    This function demonstrates command construction and validates the
    package name to reduce shell-injection risk.
    """
    if not re.fullmatch(r"[A-Za-z0-9.+:_-]+", package_name):
        raise ValueError("Unsafe package name.")

    if manager == "apt":
        return ["sudo", "apt", "install", "-y", package_name]

    if manager == "dnf":
        return ["sudo", "dnf", "install", "-y", package_name]

    if manager == "yum":
        return ["sudo", "yum", "install", "-y", package_name]

    raise ValueError(f"Unsupported package manager: {manager}")


def demonstrate_automation() -> None:
    section("15. Automation and Non-Interactive Installation")

    for manager in ("apt", "dnf", "yum"):
        command = build_noninteractive_command(manager, "curl")
        print(f"{manager:<5}: {shlex.join(command)}")

    print(
        "\nThe -y option generally answers confirmation prompts automatically. "
        "It should be used carefully in automation because package changes "
        "can be destructive."
    )

    print("\nSafer automation principles:")
    print("  • Validate inputs")
    print("  • Prefer explicit package names")
    print("  • Review planned changes")
    print("  • Use controlled repositories")
    print("  • Log transactions")
    print("  • Test changes before production")
    print("  • Avoid shell=True when subprocess execution is required")
    print("  • Make automation idempotent")


# =============================================================================
# SECTION 16: DRY RUN CONCEPT
# =============================================================================

def plan_installation(
    manager: str,
    packages: Sequence[str],
) -> List[str]:
    """
    Produce a dry-run-style plan.

    No command is executed.
    """
    if not packages:
        raise ValueError("At least one package is required.")

    plan = []

    for package in packages:
        if not re.fullmatch(r"[A-Za-z0-9.+:_-]+", package):
            raise ValueError(f"Unsafe package name: {package}")

    if manager == "apt":
        plan.append("sudo apt update")
        plan.append(
            "sudo apt install --dry-run "
            + " ".join(shlex.quote(package) for package in packages)
        )
    elif manager == "dnf":
        plan.append(
            "sudo dnf install --assumeno "
            + " ".join(shlex.quote(package) for package in packages)
        )
    elif manager == "yum":
        plan.append(
            "sudo yum install --assumeno "
            + " ".join(shlex.quote(package) for package in packages)
        )
    else:
        raise ValueError(f"Unsupported manager: {manager}")

    return plan


def demonstrate_dry_run() -> None:
    section("16. Dry Runs and Transaction Planning")

    print("Planned installation:")
    for command in plan_installation("apt", ["curl", "git", "vim"]):
        print(f"  {command}")

    print(
        "\nA dry run allows an operator to inspect package changes before "
        "committing them. Exact flags differ between package managers and "
        "distribution versions."
    )


# =============================================================================
# SECTION 17: ERROR HANDLING
# =============================================================================

def diagnose_package_error(error_message: str) -> List[str]:
    """
    Return educational troubleshooting actions based on common messages.
    """
    message = error_message.lower()

    diagnoses = []

    if "unable to locate package" in message:
        diagnoses.extend(
            [
                "Check the package name.",
                "Refresh repository metadata.",
                "Verify that the appropriate repository is enabled.",
                "Check whether the package exists for this distribution release.",
            ]
        )

    if "dependency" in message:
        diagnoses.extend(
            [
                "Inspect dependency information.",
                "Check repository consistency.",
                "Avoid mixing incompatible repositories.",
                "Complete interrupted package configuration if appropriate.",
            ]
        )

    if "permission" in message or "are you root" in message:
        diagnoses.extend(
            [
                "Use appropriate administrative privileges.",
                "Verify that the current account is authorized.",
            ]
        )

    if "404" in message or "failed to fetch" in message:
        diagnoses.extend(
            [
                "Check repository URLs.",
                "Refresh metadata.",
                "Check mirror availability.",
                "Check network connectivity and DNS.",
            ]
        )

    if "lock" in message:
        diagnoses.extend(
            [
                "Check whether another package-management process is running.",
                "Do not delete lock files blindly.",
                "Allow the active transaction to complete when appropriate.",
            ]
        )

    if not diagnoses:
        diagnoses.append(
            "Inspect the complete package-manager output and identify the "
            "first meaningful error rather than only the final message."
        )

    return diagnoses


def demonstrate_error_handling() -> None:
    section("17. Common Errors and Troubleshooting")

    examples = [
        "E: Unable to locate package example",
        "Error: Failed to download metadata for repository",
        "E: Could not get lock /var/lib/dpkg/lock",
        "Error: package has unmet dependencies",
        "Permission denied",
    ]

    for error in examples:
        print(f"\nError: {error}")
        for diagnosis in diagnose_package_error(error):
            print(f"  • {diagnosis}")

    print(
        "\nA strong troubleshooting method starts with classification: "
        "package name, repository, metadata, network, permissions, "
        "dependency, package database, or configuration problem."
    )


# =============================================================================
# SECTION 18: APT PACKAGE STATES
# =============================================================================

def demonstrate_debian_package_states() -> None:
    section("18. Debian Package States")

    states = {
        "installed": "Package is installed and configured.",
        "unpacked": "Package files are unpacked but configuration may be incomplete.",
        "half-configured": "Configuration process started but did not complete.",
        "not-installed": "Package is not currently installed.",
        "config-files": "Package was removed while configuration files remain.",
        "rc": "Common dpkg notation for removed package with residual configuration.",
    }

    for state, meaning in states.items():
        print(f"  {state:<18} {meaning}")

    print(
        "\nPackage-management failures can leave a system in an intermediate "
        "state. Repair operations should be performed carefully because "
        "package databases represent actual system state."
    )


# =============================================================================
# SECTION 19: RPM QUERY CONCEPTS
# =============================================================================

def demonstrate_rpm_queries() -> None:
    section("19. RPM Query Concepts")

    queries = [
        ("rpm -q bash", "Is bash installed?"),
        ("rpm -qi bash", "What metadata does the installed bash package contain?"),
        ("rpm -ql bash", "Which files belong to the installed bash package?"),
        ("rpm -qf /bin/bash", "Which installed RPM owns this file?"),
        ("rpm -qa", "Which RPM packages are installed?"),
        ("rpm -q --whatrequires PACKAGE", "Which installed packages require a package?"),
        ("rpm -q --requires PACKAGE", "Which dependencies does a package declare?"),
    ]

    for command, meaning in queries:
        print(f"  {command:<42} {meaning}")


# =============================================================================
# SECTION 20: REPOSITORY PRIORITIES AND PINNING
# =============================================================================

@dataclass
class Candidate:
    package: str
    version: str
    priority: int
    repository: str


def choose_by_priority_then_version(
    candidates: Sequence[Candidate],
) -> Candidate:
    """
    Educational candidate-selection model.

    Higher priority value is treated as preferred here. Real apt pin
    priorities have their own documented semantics, so this is not a
    replacement for the actual package manager.
    """
    if not candidates:
        raise ValueError("No candidates available.")

    highest_priority = max(candidate.priority for candidate in candidates)
    preferred = [
        candidate
        for candidate in candidates
        if candidate.priority == highest_priority
    ]

    return max(
        preferred,
        key=lambda candidate: version_key(candidate.version),
    )


def demonstrate_pinning() -> None:
    section("20. Repository Priorities, Pinning, and Version Locks")

    candidates = [
        Candidate("example", "1.0.0", 500, "stable"),
        Candidate("example", "1.1.0", 700, "internal"),
        Candidate("example", "2.0.0", 300, "testing"),
    ]

    selected = choose_by_priority_then_version(candidates)

    print("Candidate packages:")
    for candidate in candidates:
        print(
            f"  {candidate.package} {candidate.version:<7} "
            f"priority={candidate.priority:<3} "
            f"repo={candidate.repository}"
        )

    print(
        f"\nEducational selection result: "
        f"{selected.version} from {selected.repository}"
    )

    print("\nWhy pinning is useful:")
    print("  • Prevent unexpected upgrades")
    print("  • Prefer an internal package repository")
    print("  • Control compatibility-sensitive software")
    print("  • Support reproducible environments")

    print(
        "\nWhy pinning can be dangerous:"
        "\n  • Security fixes may be blocked."
        "\n  • Dependency resolution may become harder."
        "\n  • Old versions may eventually become unsupported."
    )


# =============================================================================
# SECTION 21: REPOSITORY MIXING
# =============================================================================

def demonstrate_repository_mixing() -> None:
    section("21. Repository Mixing and Compatibility")

    print("Example of a risky configuration:")
    print("  Distribution stable repository")
    print("  Distribution testing repository")
    print("  Unrelated third-party repository")
    print("  Random manually downloaded packages")

    print("\nPotential consequences:")
    consequences = [
        "Conflicting package versions",
        "Dependency resolution failures",
        "Unexpected upgrades",
        "ABI incompatibilities",
        "Unsupported combinations",
        "Difficult rollback",
        "Security uncertainty",
    ]

    for consequence in consequences:
        print(f"  • {consequence}")

    print(
        "\nRepositories should be selected deliberately. A package manager "
        "can resolve declared dependencies, but it cannot guarantee that an "
        "arbitrary mixture of repositories represents a supported operating "
        "system configuration."
    )


# =============================================================================
# SECTION 22: CACHE AND PERFORMANCE
# =============================================================================

@dataclass
class Cache:
    metadata_entries: int = 0
    package_files: Dict[str, int] = field(default_factory=dict)

    def size(self) -> int:
        return sum(self.package_files.values())

    def add_package(self, name: str, megabytes: int) -> None:
        if megabytes < 0:
            raise ValueError("Package size cannot be negative.")
        self.package_files[name] = megabytes

    def remove_package(self, name: str) -> None:
        self.package_files.pop(name, None)


def demonstrate_cache_and_performance() -> None:
    section("22. Package Caches and Performance")

    cache = Cache(metadata_entries=15000)
    cache.add_package("linux-image", 120)
    cache.add_package("browser", 250)
    cache.add_package("compiler", 180)

    print(f"Metadata entries: {cache.metadata_entries}")
    print(f"Cached package size: {cache.size()} MB")

    print("\nPerformance considerations:")
    print("  • Repository mirrors closer to the host reduce network latency.")
    print("  • Cached package files can avoid repeated downloads.")
    print("  • Large repository metadata can increase refresh time.")
    print("  • Parallel downloads can improve installation speed.")
    print("  • Unnecessary repositories increase metadata and dependency complexity.")
    print("  • Container image layers can make package caches costly.")

    print(
        "\nCache cleanup is a storage-management decision. Removing caches "
        "may save disk space but can require future downloads."
    )


# =============================================================================
# SECTION 23: IDEMPOTENCY
# =============================================================================

@dataclass
class SystemState:
    installed: Dict[str, str] = field(default_factory=dict)

    def install(self, package: str, version: str) -> str:
        current = self.installed.get(package)

        if current == version:
            return f"{package} {version} is already installed."

        self.installed[package] = version

        if current is None:
            return f"Installed {package} {version}."

        return f"Changed {package} from {current} to {version}."


def demonstrate_idempotency() -> None:
    section("23. Idempotency in Automation")

    state = SystemState()

    print(state.install("nginx", "1.24.0"))
    print(state.install("nginx", "1.24.0"))
    print(state.install("nginx", "1.25.0"))

    print(
        "\nIdempotent automation can be run repeatedly without causing "
        "unnecessary changes when the desired state has already been reached."
    )

    print(
        "\nPackage managers naturally support many idempotent operations, "
        "but a complete automation system must also consider configuration "
        "files, services, repository definitions, and application state."
    )


# =============================================================================
# SECTION 24: SERVICES AFTER INSTALLATION
# =============================================================================

def demonstrate_post_installation() -> None:
    section("24. Package Installation Does Not End With File Installation")

    print("After installing a server package, verify:")
    checks = [
        "Package version",
        "Installed files",
        "Configuration syntax",
        "Service state",
        "Listening ports",
        "Logs",
        "Permissions",
        "Firewall rules",
        "Application health",
        "Security update status",
    ]

    for check in checks:
        print(f"  • {check}")

    print("\nTypical service-management commands may include:")
    print("  systemctl status SERVICE")
    print("  systemctl enable SERVICE")
    print("  systemctl start SERVICE")
    print("  journalctl -u SERVICE")

    print(
        "\nPackage management and service management are related but distinct. "
        "Installing a package does not mean that the resulting service is "
        "correctly configured or healthy."
    )


# =============================================================================
# SECTION 25: PACKAGE OWNERSHIP
# =============================================================================

def parse_package_ownership(output: str) -> List[str]:
    """Parse simplified package ownership output."""
    packages = []

    for line in output.splitlines():
        line = line.strip()

        if not line:
            continue

        packages.append(line)

    return packages


def demonstrate_file_ownership() -> None:
    section("25. Finding Which Package Owns a File")

    examples = {
        "Debian": "dpkg -S /usr/bin/curl",
        "RPM": "rpm -qf /usr/bin/curl",
    }

    for family, command in examples.items():
        print(f"  {family:<10} {command}")

    sample_output = """
curl: /usr/bin/curl
"""

    print("\nExample conceptual output:")
    for package in parse_package_ownership(sample_output):
        print(f"  {package}")

    print(
        "\nFile ownership is valuable when diagnosing missing executables, "
        "unexpected files, or determining which package should be reinstalled."
    )


# =============================================================================
# SECTION 26: ARCHITECTURES
# =============================================================================

def demonstrate_architectures() -> None:
    section("26. Package Architectures")

    architectures = {
        "amd64/x86_64": "64-bit x86 systems",
        "arm64/aarch64": "64-bit ARM systems",
        "armhf": "ARM systems using a hard-float ABI in Debian naming",
        "i386": "32-bit x86 systems",
        "noarch/all": "Architecture-independent packages",
    }

    for architecture, description in architectures.items():
        print(f"  {architecture:<16} {description}")

    print("\nArchitecture mistakes can cause:")
    print("  • Package installation failures")
    print("  • Incompatible binaries")
    print("  • Missing dependencies")
    print("  • Unexpected multi-architecture behavior")

    print(
        "\nSome distributions support multiple architectures on one system. "
        "Multi-architecture configuration should be deliberate because it "
        "changes dependency resolution and available package candidates."
    )


# =============================================================================
# SECTION 27: SECURITY UPDATES
# =============================================================================

@dataclass
class SecurityUpdate:
    package: str
    installed: str
    available: str
    severity: str

    def required(self) -> bool:
        return self.installed != self.available


def demonstrate_security_updates() -> None:
    section("27. Security Updates")

    updates = [
        SecurityUpdate("openssl", "3.0.1", "3.0.2", "high"),
        SecurityUpdate("curl", "8.0.0", "8.0.1", "medium"),
        SecurityUpdate("example-app", "1.0.0", "1.0.0", "none"),
    ]

    for update in updates:
        print(
            f"{update.package:<18} "
            f"{update.installed:<8} -> "
            f"{update.available:<8} "
            f"severity={update.severity:<6} "
            f"required={update.required()}"
        )

    print(
        "\nSecurity patching should be treated as an operational process. "
        "Organizations commonly combine update policies with testing, "
        "maintenance windows, monitoring, rollback plans, and vulnerability "
        "management."
    )


# =============================================================================
# SECTION 28: PRODUCTION PRACTICES
# =============================================================================

def demonstrate_production_practices() -> None:
    section("28. Production Package-Management Practices")

    practices = [
        "Use supported operating-system releases.",
        "Prefer official or organization-approved repositories.",
        "Verify repository signing configuration.",
        "Keep package metadata current.",
        "Apply security updates according to policy.",
        "Test important upgrades before production rollout.",
        "Record package versions for reproducibility.",
        "Avoid unnecessary third-party repositories.",
        "Avoid downloading arbitrary packages from untrusted sources.",
        "Use configuration management for repeatable server provisioning.",
        "Monitor package-manager logs.",
        "Maintain backups and rollback procedures.",
        "Control administrative privileges.",
        "Use staging environments for significant changes.",
        "Document exceptions such as pinned packages.",
    ]

    for practice in practices:
        print(f"  • {practice}")


# =============================================================================
# SECTION 29: COMPARISON
# =============================================================================

def demonstrate_manager_comparison() -> None:
    section("29. apt vs yum vs dnf vs dpkg vs rpm")

    rows = [
        (
            "apt",
            "Debian/Ubuntu family",
            "High-level",
            "Repositories + dependencies",
        ),
        (
            "dpkg",
            "Debian/Ubuntu family",
            "Low-level",
            "Local .deb package database",
        ),
        (
            "dnf",
            "Fedora/RHEL family",
            "High-level",
            "Repositories + dependency resolution",
        ),
        (
            "yum",
            "Older/compatible RHEL family",
            "High-level",
            "Repository-based package management",
        ),
        (
            "rpm",
            "Fedora/RHEL family",
            "Low-level",
            "Local RPM package database",
        ),
    ]

    print(f"{'Tool':<8} {'Family':<24} {'Layer':<14} Main role")
    print("-" * 78)

    for tool, family, layer, role in rows:
        print(f"{tool:<8} {family:<24} {layer:<14} {role}")

    print("\nGeneral rule:")
    print("  Use high-level tools for normal repository-based administration.")
    print("  Use low-level tools when inspecting or manipulating package files/database state.")


# =============================================================================
# SECTION 30: PACKAGE DATABASE VS FILESYSTEM
# =============================================================================

def demonstrate_database_vs_filesystem() -> None:
    section("30. Package Database and Filesystem State")

    print("Package manager state:")
    print("  • Package name")
    print("  • Version")
    print("  • Architecture")
    print("  • Installation status")
    print("  • Dependencies")
    print("  • Configuration status")
    print("  • Ownership information")

    print("\nFilesystem state:")
    print("  • Executables")
    print("  • Libraries")
    print("  • Configuration files")
    print("  • Documentation")
    print("  • Service files")

    print(
        "\nThese states can diverge. Manual deletion or modification of files "
        "can leave the package database believing that files still exist."
    )


# =============================================================================
# SECTION 31: TRANSACTION THINKING
# =============================================================================

@dataclass
class Transaction:
    install: List[str] = field(default_factory=list)
    upgrade: List[str] = field(default_factory=list)
    remove: List[str] = field(default_factory=list)

    def describe(self) -> None:
        print("Transaction plan:")

        if self.install:
            print(f"  Install: {', '.join(self.install)}")

        if self.upgrade:
            print(f"  Upgrade: {', '.join(self.upgrade)}")

        if self.remove:
            print(f"  Remove:  {', '.join(self.remove)}")

        if not any((self.install, self.upgrade, self.remove)):
            print("  No changes.")


def demonstrate_transactions() -> None:
    section("31. Package Transactions")

    transaction = Transaction(
        install=["curl"],
        upgrade=["openssl", "libc"],
        remove=["old-library"],
    )

    transaction.describe()

    print(
        "\nTransaction planning is important because installing one package "
        "may require additional packages, upgrades, or removals."
    )


# =============================================================================
# SECTION 32: VALIDATION
# =============================================================================

def validate_package_name(package_name: str) -> bool:
    """
    Validate a conservative package-name pattern for this educational script.

    This is not a universal package-name specification.
    """
    return bool(re.fullmatch(r"[A-Za-z0-9.+:_-]+", package_name))


def demonstrate_validation() -> None:
    section("32. Input Validation and Shell Safety")

    examples = [
        "nginx",
        "python3",
        "libssl3",
        "package-with-dash",
        "package; rm -rf /",
        "package && shutdown",
        "",
    ]

    for package in examples:
        print(f"{package!r:<28} valid={validate_package_name(package)}")

    print(
        "\nWhen automating package management from Python, do not blindly "
        "concatenate untrusted input into shell commands."
    )

    print(
        "\nPreferred subprocess design:"
        "\n  subprocess.run([\"sudo\", \"apt\", \"install\", \"-y\", package], check=True)"
        "\n"
        "\nPassing an argument list avoids unnecessary shell parsing."
    )


# =============================================================================
# SECTION 33: DETECTING THE OPERATING SYSTEM
# =============================================================================

def detect_package_family() -> str:
    """
    Detect a likely package family from executable availability.

    This is only an educational heuristic. A production application should
    inspect distribution metadata such as /etc/os-release and handle
    distribution-specific policies explicitly.
    """
    if shutil.which("apt"):
        return "apt/deb family"

    if shutil.which("dnf"):
        return "dnf/rpm family"

    if shutil.which("yum"):
        return "yum/rpm family"

    if shutil.which("dpkg"):
        return "dpkg/deb family"

    if shutil.which("rpm"):
        return "rpm family"

    return "unknown"


def demonstrate_environment_detection() -> None:
    section("33. Detecting the Package-Management Environment")

    print(f"Operating system: {platform.system()}")
    print(f"Release:          {platform.release()}")
    print(f"Machine:          {platform.machine()}")
    print(f"Detected family:  {detect_package_family()}")

    print(
        "\nExecutable detection is only a heuristic. Production software "
        "should not assume that the presence of one command fully identifies "
        "the distribution or its repository policy."
    )


# =============================================================================
# SECTION 34: TESTING
# =============================================================================

def test_dependency_resolution() -> None:
    graph = DependencyGraph(
        {
            "application": ["library"],
            "library": ["runtime"],
            "runtime": [],
        }
    )

    assert graph.resolve("application") == [
        "runtime",
        "library",
        "application",
    ]


def test_dependency_cycle_detection() -> None:
    graph = DependencyGraph(
        {
            "a": ["b"],
            "b": ["a"],
        }
    )

    try:
        graph.resolve("a")
    except ValueError as error:
        assert "cycle" in str(error).lower()
    else:
        raise AssertionError("Expected a dependency cycle error.")


def test_package_validation() -> None:
    assert validate_package_name("nginx")
    assert validate_package_name("python3")
    assert not validate_package_name("rm -rf /")
    assert not validate_package_name("")


def test_command_builder() -> None:
    command = build_noninteractive_command("apt", "curl")
    assert command == ["sudo", "apt", "install", "-y", "curl"]


def run_tests() -> None:
    section("35. Built-In Tests")

    tests = [
        test_dependency_resolution,
        test_dependency_cycle_detection,
        test_package_validation,
        test_command_builder,
    ]

    passed = 0

    for test in tests:
        try:
            test()
            print(f"PASS  {test.__name__}")
            passed += 1
        except Exception as error:
            print(f"FAIL  {test.__name__}: {error}")

    print(f"\nTests passed: {passed}/{len(tests)}")

    if passed != len(tests):
        raise SystemExit("One or more educational tests failed.")


# =============================================================================
# SECTION 36: COMPLETE STUDY CHECKLIST
# =============================================================================

def print_study_checklist() -> None:
    section("36. Package-Management Study Checklist")

    checklist = [
        "Understand packages and package managers.",
        "Distinguish repositories from local package files.",
        "Understand package metadata.",
        "Understand dependencies.",
        "Know apt update versus apt upgrade.",
        "Know apt install/remove/purge/search/show.",
        "Know dnf install/remove/upgrade/search/info.",
        "Understand yum's historical and compatibility role.",
        "Understand dpkg and rpm as lower-level tools.",
        "Understand repository configuration.",
        "Understand signing and package trust.",
        "Understand package versions and candidate selection.",
        "Understand package ownership queries.",
        "Understand architecture.",
        "Understand cache and metadata refresh.",
        "Understand package transactions.",
        "Understand dry-run planning.",
        "Understand package locks.",
        "Understand interrupted package configuration.",
        "Understand repository mixing risks.",
        "Understand version pinning.",
        "Understand automation and idempotency.",
        "Understand production update practices.",
        "Understand troubleshooting methodology.",
    ]

    for item in checklist:
        print(f"  [ ] {item}")


# =============================================================================
# SECTION 37: MAIN PROGRAM
# =============================================================================

def main() -> None:
    """
    Run the complete package-management study program.

    No package installation, removal, upgrade, repository modification,
    or privileged system command is executed by this script.
    """
    section("Linux Package Management: Complete Study Program")

    print(
        "This program teaches package management using explanations, "
        "simulations, command references, data structures, validation, "
        "dependency algorithms, and tests."
    )

    print(
        "\nSafety boundary: commands shown by this program are educational "
        "examples. The program does not automatically modify the host system."
    )

    demonstrate_fundamentals()
    demonstrate_package_structure()
    demonstrate_tool_layers()
    demonstrate_command_reference()
    demonstrate_apt_installation()
    demonstrate_dnf_installation()
    demonstrate_repositories()
    demonstrate_dependency_resolution()
    demonstrate_versions()
    demonstrate_lifecycle_operations()
    demonstrate_search_and_inspection()
    demonstrate_local_package_files()
    demonstrate_repository_metadata()
    demonstrate_package_security()
    demonstrate_automation()
    demonstrate_dry_run()
    demonstrate_error_handling()
    demonstrate_debian_package_states()
    demonstrate_rpm_queries()
    demonstrate_pinning()
    demonstrate_repository_mixing()
    demonstrate_cache_and_performance()
    demonstrate_idempotency()
    demonstrate_post_installation()
    demonstrate_file_ownership()
    demonstrate_architectures()
    demonstrate_security_updates()
    demonstrate_production_practices()
    demonstrate_manager_comparison()
    demonstrate_database_vs_filesystem()
    demonstrate_transactions()
    demonstrate_validation()
    demonstrate_environment_detection()
    run_tests()
    print_study_checklist()

    section("Reference: Safe Mental Model")

    print(
        "Repository metadata -> candidate packages -> dependency resolution "
        "-> transaction plan -> package download -> trust verification -> "
        "installation/configuration -> verification -> ongoing updates"
    )

    print(
        "\nThe package manager is responsible for software lifecycle state; "
        "the administrator remains responsible for repository trust, "
        "compatibility, change control, configuration, testing, monitoring, "
        "and operational recovery."
    )


if __name__ == "__main__":
    main()
