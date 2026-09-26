"""
Git Tags & Releases: A Complete Study Program
==============================================

This standalone Python program teaches Git tags, semantic versioning, and
release concepts from beginner to advanced level.

Requirements:
    - Python 3.10+
    - Git installed and available on PATH

The program primarily uses the Python standard library. It can run in
"simulation mode" without modifying a repository, and it can optionally
inspect a real Git repository supplied through --repo.

Examples:
    python git_tags_releases.py
    python git_tags_releases.py --repo .
    python git_tags_releases.py --repo . --inspect
    python git_tags_releases.py --repo . --demo-tag v0.1.0 --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional


# ---------------------------------------------------------------------------
# 1. Fundamental terminology
# ---------------------------------------------------------------------------

TERMINOLOGY = {
    "repository": (
        "A Git repository stores project history, references, objects, and "
        "metadata."
    ),
    "commit": (
        "A commit records a snapshot of project content plus metadata and "
        "references to parent commits."
    ),
    "tag": (
        "A tag is a human-readable reference to a specific Git object, "
        "normally a commit, used to identify an important point in history."
    ),
    "annotated_tag": (
        "An annotated tag is a Git object containing a tag name, target, "
        "tagger information, timestamp, and message."
    ),
    "lightweight_tag": (
        "A lightweight tag is essentially a movable name pointing directly "
        "at an object, without an annotated tag object."
    ),
    "release": (
        "A release is a distribution-oriented project milestone, often "
        "associated with a Git tag, release notes, source archives, binaries, "
        "checksums, and other published artifacts."
    ),
    "semantic_versioning": (
        "Semantic Versioning, commonly written SemVer, represents a version "
        "as MAJOR.MINOR.PATCH with defined compatibility rules."
    ),
    "reference": (
        "A Git reference is a human-readable name that identifies an object, "
        "such as refs/heads/main or refs/tags/v1.2.3."
    ),
    "immutable_release": (
        "An operational policy under which a published release tag is treated "
        "as permanent and is never moved to another commit."
    ),
}


# ---------------------------------------------------------------------------
# 2. Semantic Versioning implementation
# ---------------------------------------------------------------------------

# SemVer 2.0.0 grammar is more precise than simply accepting three integers.
# This regular expression supports:
#   MAJOR.MINOR.PATCH
#   optional prerelease identifiers
#   optional build metadata
#
# Examples:
#   1.0.0
#   2.4.1
#   1.0.0-alpha
#   1.0.0-alpha.1
#   1.0.0+build.25
#   1.0.0-rc.1+linux.x86
SEMVER_PATTERN = re.compile(
    r"""
    ^
    (?P<major>0|[1-9][0-9]*)
    \.
    (?P<minor>0|[1-9][0-9]*)
    \.
    (?P<patch>0|[1-9][0-9]*)
    (?:
        -
        (?P<prerelease>
            (?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)
            (?:
                \.
                (?:0|[1-9][0-9]*|[0-9A-Za-z-]*[A-Za-z-][0-9A-Za-z-]*)
            )*
        )
    )?
    (?:
        \+
        (?P<build>
            [0-9A-Za-z-]+
            (?:
                \.
                [0-9A-Za-z-]+
            )*
        )
    )?
    $
    """,
    re.VERBOSE,
)


@dataclass(frozen=True, order=False)
class SemVer:
    """
    A small SemVer 2.0.0 implementation.

    Build metadata is deliberately excluded from precedence comparisons.
    Thus 1.0.0+linux and 1.0.0+windows have equal SemVer precedence.
    """

    major: int
    minor: int
    patch: int
    prerelease: tuple[str, ...] = field(default_factory=tuple)
    build: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def parse(cls, value: str) -> "SemVer":
        """Parse and validate a SemVer string."""
        match = SEMVER_PATTERN.fullmatch(value.strip())
        if not match:
            raise ValueError(f"Invalid Semantic Version: {value!r}")

        prerelease_text = match.group("prerelease")
        build_text = match.group("build")

        prerelease = (
            tuple(prerelease_text.split("."))
            if prerelease_text is not None
            else ()
        )
        build = tuple(build_text.split(".")) if build_text else ()

        return cls(
            major=int(match.group("major")),
            minor=int(match.group("minor")),
            patch=int(match.group("patch")),
            prerelease=prerelease,
            build=build,
        )

    @property
    def is_prerelease(self) -> bool:
        return bool(self.prerelease)

    def __str__(self) -> str:
        result = f"{self.major}.{self.minor}.{self.patch}"

        if self.prerelease:
            result += "-" + ".".join(self.prerelease)

        if self.build:
            result += "+" + ".".join(self.build)

        return result

    def _compare_prerelease(self, other: "SemVer") -> int:
        """
        Compare prerelease identifiers according to SemVer precedence.

        Rules:
          - A normal version has higher precedence than a prerelease version.
          - Numeric identifiers compare numerically.
          - Numeric identifiers have lower precedence than non-numeric ones.
          - Non-numeric identifiers compare lexically in ASCII sort order.
          - If all shared identifiers match, the shorter sequence is lower.
        """
        left = self.prerelease
        right = other.prerelease

        if not left and not right:
            return 0

        if not left:
            return 1

        if not right:
            return -1

        for left_id, right_id in zip(left, right):
            if left_id == right_id:
                continue

            left_numeric = left_id.isdigit()
            right_numeric = right_id.isdigit()

            if left_numeric and right_numeric:
                return -1 if int(left_id) < int(right_id) else 1

            if left_numeric != right_numeric:
                return -1 if left_numeric else 1

            return -1 if left_id < right_id else 1

        if len(left) == len(right):
            return 0

        return -1 if len(left) < len(right) else 1

    def compare(self, other: "SemVer") -> int:
        """Return -1, 0, or 1 according to SemVer precedence."""
        for left, right in (
            (self.major, other.major),
            (self.minor, other.minor),
            (self.patch, other.patch),
        ):
            if left != right:
                return -1 if left < right else 1

        # Build metadata does not affect precedence.
        return self._compare_prerelease(other)

    def __lt__(self, other: "SemVer") -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self.compare(other) < 0

    def __le__(self, other: "SemVer") -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self.compare(other) <= 0

    def __gt__(self, other: "SemVer") -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self.compare(other) > 0

    def __ge__(self, other: "SemVer") -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return self.compare(other) >= 0

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, SemVer):
            return NotImplemented
        return (
            self.major == other.major
            and self.minor == other.minor
            and self.patch == other.patch
            and self.prerelease == other.prerelease
        )

    def __hash__(self) -> int:
        return hash(
            (
                self.major,
                self.minor,
                self.patch,
                self.prerelease,
            )
        )

    def bump_major(self) -> "SemVer":
        return SemVer(self.major + 1, 0, 0)

    def bump_minor(self) -> "SemVer":
        return SemVer(self.major, self.minor + 1, 0)

    def bump_patch(self) -> "SemVer":
        return SemVer(self.major, self.minor, self.patch + 1)

    def without_build_metadata(self) -> "SemVer":
        return SemVer(
            self.major,
            self.minor,
            self.patch,
            self.prerelease,
        )


# ---------------------------------------------------------------------------
# 3. Version-range reasoning
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class VersionConstraint:
    """Represents one simple comparison constraint."""

    operator: str
    version: SemVer

    def matches(self, candidate: SemVer) -> bool:
        comparisons = {
            "=": candidate == self.version,
            "==": candidate == self.version,
            "!=": candidate != self.version,
            ">": candidate > self.version,
            ">=": candidate >= self.version,
            "<": candidate < self.version,
            "<=": candidate <= self.version,
        }

        if self.operator not in comparisons:
            raise ValueError(f"Unsupported operator: {self.operator}")

        return comparisons[self.operator]


def parse_constraint(expression: str) -> VersionConstraint:
    """
    Parse a simple expression such as >=1.2.0.

    This intentionally does not implement every package-manager range syntax.
    The goal is to demonstrate the distinction between SemVer itself and
    higher-level dependency range languages.
    """
    match = re.fullmatch(r"(==|!=|>=|<=|>|<|=)\s*(.+)", expression.strip())
    if not match:
        raise ValueError(
            f"Unsupported constraint {expression!r}; "
            "use forms such as >=1.2.0 or <2.0.0."
        )

    return VersionConstraint(match.group(1), SemVer.parse(match.group(2)))


# ---------------------------------------------------------------------------
# 4. Git command execution
# ---------------------------------------------------------------------------

class GitCommandError(RuntimeError):
    """Raised when a Git command cannot be completed successfully."""


def run_git(
    args: list[str],
    repo: Path,
    *,
    check: bool = True,
) -> str:
    """
    Execute a Git command safely.

    A list of arguments is used instead of shell=True, preventing shell
    interpretation of tag names, paths, or user-controlled input.
    """
    command = ["git", "-C", str(repo), *args]

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError as exc:
        raise GitCommandError(
            "Git was not found. Install Git and ensure it is on PATH."
        ) from exc

    if check and completed.returncode != 0:
        message = completed.stderr.strip() or completed.stdout.strip()
        raise GitCommandError(
            f"Git command failed ({completed.returncode}): "
            f"{' '.join(command)}\n{message}"
        )

    return completed.stdout.strip()


def is_git_repository(repo: Path) -> bool:
    try:
        result = run_git(
            ["rev-parse", "--is-inside-work-tree"],
            repo,
            check=False,
        )
        return result == "true"
    except GitCommandError:
        return False


# ---------------------------------------------------------------------------
# 5. Git tag models
# ---------------------------------------------------------------------------

@dataclass
class GitTagInfo:
    name: str
    object_type: str
    object_id: str
    creator: str = ""
    date: str = ""
    message: str = ""

    @property
    def is_annotated(self) -> bool:
        return self.object_type == "tag"

    @property
    def version(self) -> Optional[SemVer]:
        """
        Parse a SemVer from a tag.

        A leading 'v' is accepted as a common Git convention:
            v1.2.3 -> 1.2.3
        """
        candidate = self.name[1:] if self.name.startswith("v") else self.name

        try:
            return SemVer.parse(candidate)
        except ValueError:
            return None


def list_git_tags(repo: Path) -> list[GitTagInfo]:
    """
    Read tags from a repository.

    The %(...) placeholders are Git's formatting directives. They let us
    retrieve structured reference information without scraping human-oriented
    command output.
    """
    format_string = (
        "%(refname:short)%x09"
        "%(objecttype)%x09"
        "%(objectname)%x09"
        "%(creatordate:iso-strict)%x09"
        "%(creator)"
    )

    output = run_git(
        [
            "for-each-ref",
            f"--format={format_string}",
            "refs/tags",
        ],
        repo,
    )

    if not output:
        return []

    tags: list[GitTagInfo] = []

    for line in output.splitlines():
        fields = line.split("\t", maxsplit=4)

        if len(fields) != 5:
            continue

        name, object_type, object_id, date, creator = fields

        message = ""
        if object_type == "tag":
            message = run_git(
                ["tag", "-l", name, "--format=%(contents:subject)"],
                repo,
                check=False,
            )

        tags.append(
            GitTagInfo(
                name=name,
                object_type=object_type,
                object_id=object_id,
                creator=creator,
                date=date,
                message=message,
            )
        )

    return tags


# ---------------------------------------------------------------------------
# 6. Tag naming policy
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class TagPolicy:
    """
    A release-tag policy.

    Example:
        prefix = "v"
        require_semver = True
        require_annotated = True
        require_clean_worktree = True
        forbid_existing_tag = True
    """

    prefix: str = "v"
    require_semver: bool = True
    require_annotated: bool = True
    require_clean_worktree: bool = True
    forbid_existing_tag: bool = True

    def validate_name(self, tag_name: str) -> SemVer:
        if not tag_name:
            raise ValueError("Tag name cannot be empty.")

        if self.prefix and not tag_name.startswith(self.prefix):
            raise ValueError(
                f"Release tags must start with {self.prefix!r}."
            )

        candidate = (
            tag_name[len(self.prefix):]
            if self.prefix
            else tag_name
        )

        version = SemVer.parse(candidate)

        if self.require_semver and version is None:
            raise ValueError("Tag does not contain a valid SemVer version.")

        return version


# ---------------------------------------------------------------------------
# 7. Release planning
# ---------------------------------------------------------------------------

@dataclass
class ReleasePlan:
    version: SemVer
    tag_name: str
    title: str
    prerelease: bool
    notes: list[str]
    validation_errors: list[str]

    @property
    def is_valid(self) -> bool:
        return not self.validation_errors


def create_release_plan(
    version_text: str,
    *,
    prefix: str = "v",
    title: Optional[str] = None,
    notes: Optional[Iterable[str]] = None,
) -> ReleasePlan:
    version = SemVer.parse(version_text)

    tag_name = f"{prefix}{version}"
    release_title = title or f"Release {tag_name}"

    note_list = list(notes or [])

    errors: list[str] = []

    if version.major < 0 or version.minor < 0 or version.patch < 0:
        errors.append("SemVer numeric components cannot be negative.")

    return ReleasePlan(
        version=version,
        tag_name=tag_name,
        title=release_title,
        prerelease=version.is_prerelease,
        notes=note_list,
        validation_errors=errors,
    )


# ---------------------------------------------------------------------------
# 8. Changelog generation
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Commit:
    hash: str
    subject: str


def parse_git_log(repo: Path, revision_range: Optional[str]) -> list[Commit]:
    """
    Read commit subjects.

    If revision_range is supplied, it can be something such as:
        v1.2.0..HEAD

    Git receives it as one argument, rather than being interpreted by a shell.
    """
    args = [
        "log",
        "--no-merges",
        "--format=%H%x09%s",
    ]

    if revision_range:
        args.append(revision_range)

    output = run_git(args, repo)

    if not output:
        return []

    commits: list[Commit] = []

    for line in output.splitlines():
        commit_hash, _, subject = line.partition("\t")

        if commit_hash:
            commits.append(
                Commit(
                    hash=commit_hash,
                    subject=subject,
                )
            )

    return commits


def categorize_commit(subject: str) -> str:
    """
    A simple conventional-commit classifier.

    It is intentionally conservative. A production organization may define
    a stricter commit-message grammar and require CI validation.
    """
    lowered = subject.lower()

    if lowered.startswith("feat"):
        return "Features"

    if lowered.startswith("fix"):
        return "Bug Fixes"

    if lowered.startswith("docs"):
        return "Documentation"

    if lowered.startswith("perf"):
        return "Performance"

    if lowered.startswith("refactor"):
        return "Refactoring"

    if lowered.startswith("test"):
        return "Tests"

    if lowered.startswith("build") or lowered.startswith("ci"):
        return "Build and CI"

    return "Other Changes"


def generate_changelog(
    commits: Iterable[Commit],
    version: SemVer,
) -> str:
    groups: dict[str, list[Commit]] = {}

    for commit in commits:
        groups.setdefault(categorize_commit(commit.subject), []).append(
            commit
        )

    lines = [
        f"## {version}",
        "",
        f"Released: {datetime.now().date().isoformat()}",
        "",
    ]

    preferred_order = [
        "Breaking Changes",
        "Features",
        "Bug Fixes",
        "Performance",
        "Refactoring",
        "Documentation",
        "Tests",
        "Build and CI",
        "Other Changes",
    ]

    for category in preferred_order:
        category_commits = groups.get(category, [])

        if not category_commits:
            continue

        lines.extend([f"### {category}", ""])

        for commit in category_commits:
            short_hash = commit.hash[:8]
            lines.append(f"- {commit.subject} (`{short_hash}`)")

        lines.append("")

    if len(lines) <= 4:
        lines.append("- No categorized commits were found.")

    return "\n".join(lines).rstrip()


# ---------------------------------------------------------------------------
# 9. Git state inspection
# ---------------------------------------------------------------------------

@dataclass
class RepositoryState:
    branch: str
    head: str
    is_dirty: bool
    remote_names: list[str]
    tags: list[GitTagInfo]


def inspect_repository(repo: Path) -> RepositoryState:
    if not is_git_repository(repo):
        raise GitCommandError(f"{repo} is not a Git working tree.")

    branch = run_git(
        ["branch", "--show-current"],
        repo,
    )

    # Detached HEAD produces an empty branch name.
    if not branch:
        branch = "(detached HEAD)"

    head = run_git(
        ["rev-parse", "HEAD"],
        repo,
    )

    status_output = run_git(
        ["status", "--porcelain"],
        repo,
    )

    remotes_output = run_git(
        ["remote"],
        repo,
    )

    remotes = [
        line.strip()
        for line in remotes_output.splitlines()
        if line.strip()
    ]

    return RepositoryState(
        branch=branch,
        head=head,
        is_dirty=bool(status_output),
        remote_names=remotes,
        tags=list_git_tags(repo),
    )


# ---------------------------------------------------------------------------
# 10. Safe tag operations
# ---------------------------------------------------------------------------

def tag_exists(repo: Path, tag_name: str) -> bool:
    result = run_git(
        ["show-ref", "--tags", "--verify", f"refs/tags/{tag_name}"],
        repo,
        check=False,
    )
    return bool(result)


def create_annotated_tag(
    repo: Path,
    tag_name: str,
    message: str,
    *,
    force: bool = False,
    dry_run: bool = False,
) -> None:
    """
    Create an annotated tag.

    Important production behavior:
      - annotated tags preserve metadata
      - force-moving release tags is intentionally explicit
      - dry-run prevents mutation
    """
    if not tag_name:
        raise ValueError("Tag name cannot be empty.")

    if tag_exists(repo, tag_name) and not force:
        raise GitCommandError(
            f"Tag {tag_name!r} already exists. "
            "Refusing to move it without explicit force=True."
        )

    command = ["tag", "-a", tag_name, "-m", message]

    if force:
        command.insert(1, "--force")

    if dry_run:
        print("DRY RUN:", "git", "-C", str(repo), *command)
        return

    run_git(command, repo)


def push_tag(
    repo: Path,
    tag_name: str,
    *,
    remote: str = "origin",
    dry_run: bool = False,
) -> None:
    """
    Push one tag.

    Publishing a tag is a separate action from creating it locally.
    """
    if not tag_name:
        raise ValueError("Tag name cannot be empty.")

    command = ["push", remote, tag_name]

    if dry_run:
        print("DRY RUN:", "git", "-C", str(repo), *command)
        return

    run_git(command, repo)


# ---------------------------------------------------------------------------
# 11. Version-selection helpers
# ---------------------------------------------------------------------------

def version_tags(tags: Iterable[GitTagInfo]) -> list[tuple[SemVer, GitTagInfo]]:
    versions: list[tuple[SemVer, GitTagInfo]] = []

    for tag in tags:
        version = tag.version

        if version is not None:
            versions.append((version, tag))

    return versions


def latest_version(
    tags: Iterable[GitTagInfo],
    *,
    include_prerelease: bool = False,
) -> Optional[tuple[SemVer, GitTagInfo]]:
    candidates = version_tags(tags)

    if not include_prerelease:
        candidates = [
            item
            for item in candidates
            if not item[0].is_prerelease
        ]

    if not candidates:
        return None

    return max(candidates, key=lambda item: item[0])


def recommend_next_version(
    current: SemVer,
    change_type: str,
) -> SemVer:
    """
    Select the next version from an explicitly supplied change classification.

    This is a rule-based demonstration, not an automatic judgment of project
    compatibility. Humans and project policies must determine whether an API
    change is breaking.
    """
    normalized = change_type.lower().strip()

    if normalized == "major":
        return current.bump_major()

    if normalized == "minor":
        return current.bump_minor()

    if normalized == "patch":
        return current.bump_patch()

    raise ValueError(
        "change_type must be 'major', 'minor', or 'patch'."
    )


# ---------------------------------------------------------------------------
# 12. Educational demonstrations
# ---------------------------------------------------------------------------

def print_section(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def demonstrate_terminology() -> None:
    print_section("1. Git Tags and Release Terminology")

    for name, description in TERMINOLOGY.items():
        readable = name.replace("_", " ").title()
        print(f"{readable}: {description}")


def demonstrate_tag_types() -> None:
    print_section("2. Lightweight Tags vs Annotated Tags")

    print(
        """
Lightweight tag:
    git tag v1.0.0

Annotated tag:
    git tag -a v1.0.0 -m "Release v1.0.0"

Typical distinction:
    Lightweight tags are simple references.
    Annotated tags are first-class tag objects with metadata.

For formal releases, annotated tags are commonly preferred because they
provide a durable description, tagger identity, and timestamp.
""".strip()
    )


def demonstrate_semver() -> None:
    print_section("3. Semantic Versioning")

    examples = [
        "0.1.0",
        "1.0.0",
        "1.4.2",
        "2.0.0",
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-rc.1",
        "1.0.0+build.17",
        "1.0.0-rc.1+linux.x86",
    ]

    for value in examples:
        version = SemVer.parse(value)
        print(
            f"{value:28} -> "
            f"major={version.major}, "
            f"minor={version.minor}, "
            f"patch={version.patch}, "
            f"prerelease={version.prerelease or '-'}, "
            f"build={version.build or '-'}"
        )

    print("\nPrecedence examples:")
    precedence_pairs = [
        ("1.0.0-alpha", "1.0.0"),
        ("1.0.0-alpha", "1.0.0-beta"),
        ("1.0.0-beta", "1.0.0-rc.1"),
        ("1.0.0-rc.1", "1.0.0"),
        ("1.0.0+linux", "1.0.0+windows"),
    ]

    for left_text, right_text in precedence_pairs:
        left = SemVer.parse(left_text)
        right = SemVer.parse(right_text)

        if left < right:
            relation = "<"
        elif left > right:
            relation = ">"
        else:
            relation = "="

        print(f"  {left} {relation} {right}")


def demonstrate_semver_rules() -> None:
    print_section("4. Semantic Versioning Compatibility Rules")

    print(
        """
MAJOR.MINOR.PATCH

MAJOR:
    Increment when incompatible API changes are introduced.

MINOR:
    Increment when backward-compatible functionality is added.

PATCH:
    Increment for backward-compatible bug fixes.

Prerelease:
    2.0.0-alpha, 2.0.0-beta.1, 2.0.0-rc.1

Build metadata:
    2.0.0+build.123

Important:
    Semantic Versioning describes a contract. It does not automatically know
    whether a source-code change is breaking. The project must define and
    apply its compatibility policy.
""".strip()
    )


def demonstrate_invalid_versions() -> None:
    print_section("5. Invalid Semantic Versions")

    invalid_values = [
        "1",
        "1.2",
        "01.2.3",
        "1.02.3",
        "1.2.03",
        "v1.2.3",
        "1.2.3-",
        "1.2.3+",
        "1.2.3..build",
    ]

    for value in invalid_values:
        try:
            SemVer.parse(value)
        except ValueError as exc:
            print(f"Rejected: {value!r} -> {exc}")
        else:
            print(f"Unexpectedly accepted: {value!r}")


def demonstrate_version_bumping() -> None:
    print_section("6. Version Bumping")

    current = SemVer.parse("3.7.4")

    for change_type in ("patch", "minor", "major"):
        next_version = recommend_next_version(current, change_type)
        print(f"{change_type:6} : {current} -> {next_version}")


def demonstrate_constraints() -> None:
    print_section("7. Version Constraints")

    constraints = [
        parse_constraint(">=1.5.0"),
        parse_constraint("<2.0.0"),
        parse_constraint("!=1.7.0"),
    ]

    candidates = [
        SemVer.parse("1.4.9"),
        SemVer.parse("1.5.0"),
        SemVer.parse("1.7.0"),
        SemVer.parse("1.8.2"),
        SemVer.parse("2.0.0"),
    ]

    for candidate in candidates:
        results = [
            constraint.matches(candidate)
            for constraint in constraints
        ]
        print(f"{candidate:10} -> {results}")


def demonstrate_release_plan() -> None:
    print_section("8. Release Planning")

    plan = create_release_plan(
        "2.3.0-rc.1",
        notes=[
            "Added repository release metadata.",
            "Improved version validation.",
            "Updated documentation.",
        ],
    )

    print(f"Version:     {plan.version}")
    print(f"Tag:         {plan.tag_name}")
    print(f"Title:       {plan.title}")
    print(f"Prerelease:  {plan.prerelease}")
    print(f"Valid:       {plan.is_valid}")

    if plan.notes:
        print("Notes:")
        for note in plan.notes:
            print(f"  - {note}")


def demonstrate_changelog() -> None:
    print_section("9. Changelog Generation")

    commits = [
        Commit("a1b2c3d4", "feat: add release dashboard"),
        Commit("b2c3d4e5", "fix: reject invalid SemVer identifiers"),
        Commit("c3d4e5f6", "docs: document release policy"),
        Commit("d4e5f6a7", "perf: optimize tag inspection"),
        Commit("e5f6a7b8", "refactor: separate version parser"),
        Commit("f6a7b8c9", "test: add prerelease precedence tests"),
        Commit("12345678", "update dependencies"),
    ]

    print(generate_changelog(commits, SemVer.parse("1.4.0")))


def demonstrate_tag_policy() -> None:
    print_section("10. Release Tag Policy")

    policy = TagPolicy()

    candidates = [
        "v1.0.0",
        "v2.4.1",
        "1.2.3",
        "v1.2",
        "v01.2.3",
    ]

    for candidate in candidates:
        try:
            version = policy.validate_name(candidate)
            print(f"Accepted: {candidate} -> {version}")
        except ValueError as exc:
            print(f"Rejected: {candidate} -> {exc}")


def demonstrate_release_lifecycle() -> None:
    print_section("11. Typical Release Lifecycle")

    lifecycle = [
        "1. Decide the release scope.",
        "2. Determine the next SemVer according to documented compatibility rules.",
        "3. Ensure tests and required checks pass.",
        "4. Confirm the working tree is clean.",
        "5. Update changelog and release metadata.",
        "6. Create an annotated tag at the intended commit.",
        "7. Verify the tag points to the intended commit.",
        "8. Push the tag to the remote.",
        "9. Publish the release and its artifacts.",
        "10. Verify the published artifacts and checksums.",
        "11. Preserve the release tag according to the project's immutability policy.",
    ]

    for index, step in enumerate(lifecycle, start=1):
        print(f"{index:2}. {step}")


# ---------------------------------------------------------------------------
# 13. Repository inspection output
# ---------------------------------------------------------------------------

def print_repository_state(state: RepositoryState) -> None:
    print_section("Repository Inspection")

    print(f"Branch:       {state.branch}")
    print(f"HEAD:         {state.head}")
    print(f"Working tree: {'DIRTY' if state.is_dirty else 'CLEAN'}")
    print(
        "Remotes:      "
        + (", ".join(state.remote_names) if state.remote_names else "(none)")
    )
    print(f"Tag count:    {len(state.tags)}")

    if not state.tags:
        print("No tags found.")
        return

    print("\nTags:")

    for tag in sorted(
        state.tags,
        key=lambda item: (
            item.version is None,
            item.version or SemVer(0, 0, 0),
        ),
    ):
        version_text = str(tag.version) if tag.version else "not SemVer"
        kind = "annotated" if tag.is_annotated else "lightweight"

        print(
            f"  {tag.name:24} "
            f"{kind:12} "
            f"{tag.object_id[:12]:12} "
            f"{version_text}"
        )

    latest = latest_version(state.tags)

    if latest:
        version, tag = latest
        print(
            f"\nLatest stable SemVer tag: {tag.name} "
            f"({version})"
        )
    else:
        print("\nNo stable SemVer tags were found.")


# ---------------------------------------------------------------------------
# 14. Release-tag validation against a real repository
# ---------------------------------------------------------------------------

def validate_release_tag(
    repo: Path,
    tag_name: str,
    policy: TagPolicy,
) -> list[str]:
    errors: list[str] = []

    try:
        policy.validate_name(tag_name)
    except ValueError as exc:
        errors.append(str(exc))

    if policy.require_clean_worktree:
        status = run_git(
            ["status", "--porcelain"],
            repo,
        )

        if status:
            errors.append(
                "Working tree is not clean; release creation policy "
                "requires a clean tree."
            )

    if policy.forbid_existing_tag and tag_exists(repo, tag_name):
        errors.append(
            f"Tag {tag_name!r} already exists; immutable release policy "
            "requires choosing a new version."
        )

    return errors


def demonstrate_dry_run_release(repo: Path, version_text: str) -> None:
    print_section("12. Real Git Release Dry Run")

    policy = TagPolicy()

    try:
        version = policy.validate_name(
            f"{policy.prefix}{SemVer.parse(version_text)}"
        )
    except ValueError as exc:
        print(f"Invalid release version: {exc}")
        return

    tag_name = f"{policy.prefix}{version}"

    errors = validate_release_tag(
        repo,
        tag_name,
        policy,
    )

    print(f"Proposed version: {version}")
    print(f"Proposed tag:     {tag_name}")

    if errors:
        print("Release validation failed:")

        for error in errors:
            print(f"  - {error}")

        return

    print("Validation passed.")
    create_annotated_tag(
        repo,
        tag_name,
        f"Release {tag_name}",
        dry_run=True,
    )


# ---------------------------------------------------------------------------
# 15. Unit tests
# ---------------------------------------------------------------------------

def run_tests() -> None:
    print_section("13. Automated Self-Tests")

    # Valid versions.
    assert str(SemVer.parse("1.2.3")) == "1.2.3"
    assert str(SemVer.parse("1.2.3-alpha.1")) == "1.2.3-alpha.1"
    assert str(SemVer.parse("1.2.3+build.7")) == "1.2.3+build.7"
    assert str(
        SemVer.parse("1.2.3-alpha.1+build.7")
    ) == "1.2.3-alpha.1+build.7"

    # Build metadata does not affect precedence.
    assert (
        SemVer.parse("1.0.0+one")
        == SemVer.parse("1.0.0+two")
    )

    # Standard SemVer precedence sequence.
    ordered = [
        "1.0.0-alpha",
        "1.0.0-alpha.1",
        "1.0.0-alpha.beta",
        "1.0.0-beta",
        "1.0.0-beta.2",
        "1.0.0-beta.11",
        "1.0.0-rc.1",
        "1.0.0",
    ]

    parsed = [SemVer.parse(value) for value in ordered]

    for left, right in zip(parsed, parsed[1:]):
        assert left < right, f"{left} should be lower than {right}"

    # Invalid leading zeroes.
    for invalid in ("01.0.0", "1.01.0", "1.0.01"):
        try:
            SemVer.parse(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError(f"{invalid} should be invalid")

    # Bumps.
    version = SemVer.parse("2.4.9")
    assert version.bump_patch() == SemVer.parse("2.4.10")
    assert version.bump_minor() == SemVer.parse("2.5.0")
    assert version.bump_major() == SemVer.parse("3.0.0")

    # Constraints.
    assert parse_constraint(">=1.0.0").matches(
        SemVer.parse("1.5.0")
    )
    assert not parse_constraint("<1.0.0").matches(
        SemVer.parse("1.5.0")
    )

    # Tag naming.
    policy = TagPolicy()
    assert policy.validate_name("v1.2.3") == SemVer.parse("1.2.3")

    try:
        policy.validate_name("1.2.3")
    except ValueError:
        pass
    else:
        raise AssertionError("Tag without v prefix should be rejected")

    # Changelog categorization.
    assert categorize_commit("feat: new API") == "Features"
    assert categorize_commit("fix: crash") == "Bug Fixes"
    assert categorize_commit("docs: clarify") == "Documentation"
    assert categorize_commit("perf: improve parser") == "Performance"

    print("All tests passed.")


# ---------------------------------------------------------------------------
# 16. JSON representation
# ---------------------------------------------------------------------------

def semver_to_dict(version: SemVer) -> dict[str, object]:
    return {
        "major": version.major,
        "minor": version.minor,
        "patch": version.patch,
        "prerelease": list(version.prerelease),
        "build": list(version.build),
        "is_prerelease": version.is_prerelease,
        "string": str(version),
    }


def demonstrate_json() -> None:
    print_section("14. Machine-Readable Release Metadata")

    version = SemVer.parse("4.2.0-rc.1+build.20260926")

    release_metadata = {
        "version": semver_to_dict(version),
        "tag": f"v{version}",
        "release_type": "prerelease",
        "published": False,
        "artifacts": [
            "project-4.2.0-rc.1.tar.gz",
            "project-4.2.0-rc.1.zip",
        ],
    }

    print(
        json.dumps(
            release_metadata,
            indent=2,
        )
    )


# ---------------------------------------------------------------------------
# 17. Main command-line interface
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Study Git tags, Semantic Versioning, and release workflows."
        )
    )

    parser.add_argument(
        "--repo",
        type=Path,
        default=Path("."),
        help="Git repository to inspect. Defaults to the current directory.",
    )

    parser.add_argument(
        "--inspect",
        action="store_true",
        help="Inspect tags and state of the specified repository.",
    )

    parser.add_argument(
        "--demo-tag",
        metavar="VERSION",
        help=(
            "Validate a proposed version and perform a real-repository "
            "release dry run, for example 1.4.0."
        ),
    )

    parser.add_argument(
        "--run-tests",
        action="store_true",
        help="Run built-in assertions.",
    )

    parser.add_argument(
        "--json-version",
        metavar="VERSION",
        help="Print machine-readable information about a SemVer version.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    demonstrate_terminology()
    demonstrate_tag_types()
    demonstrate_semver()
    demonstrate_semver_rules()
    demonstrate_invalid_versions()
    demonstrate_version_bumping()
    demonstrate_constraints()
    demonstrate_release_plan()
    demonstrate_changelog()
    demonstrate_tag_policy()
    demonstrate_release_lifecycle()
    demonstrate_json()

    if args.run_tests:
        run_tests()

    if args.json_version:
        print_section("Requested Version")
        try:
            version = SemVer.parse(args.json_version)
        except ValueError as exc:
            print(exc)
            return 2

        print(json.dumps(semver_to_dict(version), indent=2))

    if args.inspect or args.demo_tag:
        repo = args.repo.resolve()

        if not is_git_repository(repo):
            print(
                f"\nRepository inspection skipped: {repo} "
                "is not a Git working tree."
            )
        else:
            try:
                state = inspect_repository(repo)

                if args.inspect:
                    print_repository_state(state)

                if args.demo_tag:
                    demonstrate_dry_run_release(
                        repo,
                        args.demo_tag,
                    )

            except GitCommandError as exc:
                print(f"Git error: {exc}", file=sys.stderr)
                return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
