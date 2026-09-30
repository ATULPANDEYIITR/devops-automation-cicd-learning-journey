#!/usr/bin/env python3
"""
Git Automation: hooks, commit validation, and automated checks.

This self-contained example models a practical Git automation pipeline:
- repository hook configuration
- commit-message validation
- staged-file validation
- secret detection
- automated test and quality checks
- pre-commit and commit-msg hook simulation
- CI-style validation
- JSON audit reporting
- safe subprocess execution

The program does not modify the current repository by default. It creates a
temporary demonstration repository so that the workflow can be executed
without damaging an existing project.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Callable, Iterable


PROJECT_NAME = "git-automation-demo"

# Conventional commit subjects are validated before a commit is accepted.
COMMIT_PATTERN = re.compile(
    r"^(feat|fix|docs|refactor|test|build|ci|chore|perf|style|revert)"
    r"(\([a-z0-9._/-]+\))?!?: .{1,100}$"
)

# These patterns catch common accidental credential formats. A real
# organization should maintain a repository-specific secret-detection policy.
SECRET_PATTERNS = [
    re.compile(r"(?i)\baws(.{0,20})?(access[_-]?key|secret)[^\n]{0,80}"),
    re.compile(r"(?i)\bgithub_pat_[A-Za-z0-9_]{20,}"),
    re.compile(r"(?i)\bghp_[A-Za-z0-9]{20,}"),
    re.compile(r"(?i)\b(api[_-]?key|secret[_-]?key)\s*[:=]\s*['\"][^'\"]{8,}"),
]

ALLOWED_TEXT_SUFFIXES = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".cpp",
    ".h",
    ".hpp",
    ".md",
    ".txt",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
}

FORBIDDEN_PATH_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    "__pycache__",
}

MAX_TEXT_FILE_BYTES = 512_000


@dataclass
class CheckResult:
    name: str
    passed: bool
    message: str
    details: list[str] = field(default_factory=list)

    def display(self) -> str:
        status = "PASS" if self.passed else "FAIL"
        suffix = f" | {'; '.join(self.details)}" if self.details else ""
        return f"[{status}] {self.name}: {self.message}{suffix}"


@dataclass
class AutomationReport:
    results: list[CheckResult]

    @property
    def passed(self) -> bool:
        return all(result.passed for result in self.results)

    def print_report(self, title: str) -> None:
        print(f"\n=== {title} ===")
        for result in self.results:
            print(result.display())
        print(f"Result: {'PASS' if self.passed else 'FAIL'}")


@dataclass
class HookConfig:
    hook_name: str
    enabled: bool
    description: str


@dataclass
class RepositoryPolicy:
    protected_branch: str = "main"
    require_commit_message: bool = True
    require_tests: bool = True
    require_secret_scan: bool = True
    require_clean_whitespace: bool = True
    require_supported_files: bool = True


def run_command(
    command: list[str],
    cwd: Path,
    *,
    timeout: int = 30,
) -> tuple[int, str, str]:
    """
    Execute a subprocess without shell interpolation.

    Passing an argument list instead of shell=True prevents command strings
    from being interpreted as shell syntax when file names or input values
    originate outside the program.
    """
    try:
        completed = subprocess.run(
            command,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return completed.returncode, completed.stdout.strip(), completed.stderr.strip()
    except subprocess.TimeoutExpired:
        return 124, "", f"Command timed out after {timeout} seconds"
    except OSError as exc:
        return 127, "", str(exc)


def git(repo: Path, *arguments: str) -> tuple[int, str, str]:
    return run_command(["git", *arguments], repo)


def initialize_demo_repository(repo: Path) -> None:
    code, stdout, stderr = git(repo, "init", "-b", "main")
    if code != 0:
        raise RuntimeError(f"git init failed: {stderr or stdout}")

    commands = [
        ("config", "user.name", "Automation Demo"),
        ("config", "user.email", "automation@example.invalid"),
    ]

    for command in commands:
        code, stdout, stderr = git(repo, *command)
        if code != 0:
            raise RuntimeError(f"Git configuration failed: {stderr or stdout}")

    (repo / "src").mkdir()
    (repo / "tests").mkdir()
    (repo / "src" / "calculator.py").write_text(
        "def add(left: int, right: int) -> int:\n"
        "    return left + right\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_calculator.py").write_text(
        "from src.calculator import add\n\n"
        "def test_add():\n"
        "    assert add(2, 3) == 5\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text(
        "# Git Automation Demo\n\n"
        "Repository used to demonstrate local validation and automated checks.\n",
        encoding="utf-8",
    )

    code, stdout, stderr = git(repo, "add", ".")
    if code != 0:
        raise RuntimeError(stderr or stdout)

    code, stdout, stderr = git(
        repo,
        "commit",
        "-m",
        "chore: initialize automation demonstration",
    )
    if code != 0:
        raise RuntimeError(stderr or stdout)


def list_staged_files(repo: Path) -> list[Path]:
    """
    Ask Git which paths are staged for the next commit.

    Using Git's index rather than scanning the entire working tree is critical:
    pre-commit checks should normally validate what is actually being
    committed, not unrelated local modifications.
    """
    code, stdout, stderr = git(
        repo,
        "diff",
        "--cached",
        "--name-only",
        "--diff-filter=ACMR",
    )
    if code != 0:
        raise RuntimeError(f"Unable to inspect index: {stderr or stdout}")

    return [Path(line) for line in stdout.splitlines() if line.strip()]


def validate_commit_message(message: str) -> CheckResult:
    subject = message.strip().splitlines()[0] if message.strip() else ""

    if not subject:
        return CheckResult(
            "commit-message",
            False,
            "Commit message is empty.",
        )

    if len(subject) > 100:
        return CheckResult(
            "commit-message",
            False,
            "Commit subject exceeds 100 characters.",
        )

    if not COMMIT_PATTERN.fullmatch(subject):
        return CheckResult(
            "commit-message",
            False,
            "Subject does not follow the configured conventional format.",
            ["Example: feat(auth): validate session tokens"],
        )

    return CheckResult(
        "commit-message",
        True,
        "Commit subject matches the configured policy.",
    )


def validate_file_paths(paths: Iterable[Path]) -> CheckResult:
    invalid = []

    for path in paths:
        normalized = path.as_posix()

        if any(part in FORBIDDEN_PATH_PARTS for part in path.parts):
            invalid.append(f"{normalized}: generated/dependency path")

        if path.is_absolute():
            invalid.append(f"{normalized}: absolute path")

    if invalid:
        return CheckResult(
            "file-path-policy",
            False,
            "One or more staged paths violate repository policy.",
            invalid,
        )

    return CheckResult(
        "file-path-policy",
        True,
        "Staged paths are acceptable.",
    )


def validate_file_sizes(repo: Path, paths: Iterable[Path]) -> CheckResult:
    oversized = []

    for relative_path in paths:
        absolute_path = repo / relative_path

        if not absolute_path.exists():
            continue

        if absolute_path.is_file() and absolute_path.stat().st_size > MAX_TEXT_FILE_BYTES:
            oversized.append(
                f"{relative_path.as_posix()} exceeds {MAX_TEXT_FILE_BYTES} bytes"
            )

    if oversized:
        return CheckResult(
            "file-size-policy",
            False,
            "A staged file exceeds the configured size limit.",
            oversized,
        )

    return CheckResult(
        "file-size-policy",
        True,
        "Staged files are within the configured size limit.",
    )


def scan_for_secrets(repo: Path, paths: Iterable[Path]) -> CheckResult:
    findings = []

    for relative_path in paths:
        absolute_path = repo / relative_path

        if not absolute_path.exists() or not absolute_path.is_file():
            continue

        if absolute_path.suffix.lower() not in ALLOWED_TEXT_SUFFIXES:
            continue

        try:
            content = absolute_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue

        for pattern in SECRET_PATTERNS:
            if pattern.search(content):
                findings.append(
                    f"Potential credential pattern in {relative_path.as_posix()}"
                )

    if findings:
        return CheckResult(
            "secret-scan",
            False,
            "Potential secret material was detected.",
            findings,
        )

    return CheckResult(
        "secret-scan",
        True,
        "No configured credential patterns were detected.",
    )


def validate_trailing_whitespace(repo: Path, paths: Iterable[Path]) -> CheckResult:
    findings = []

    for relative_path in paths:
        absolute_path = repo / relative_path

        if (
            not absolute_path.exists()
            or not absolute_path.is_file()
            or absolute_path.suffix.lower() not in ALLOWED_TEXT_SUFFIXES
        ):
            continue

        try:
            lines = absolute_path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue

        for line_number, line in enumerate(lines, start=1):
            if line.endswith((" ", "\t")):
                findings.append(
                    f"{relative_path.as_posix()}:{line_number}"
                )

    if findings:
        return CheckResult(
            "whitespace",
            False,
            "Trailing whitespace was found.",
            findings,
        )

    return CheckResult(
        "whitespace",
        True,
        "No trailing whitespace found in staged text files.",
    )


def run_python_tests(repo: Path) -> CheckResult:
    """
    Run tests as an automated gate.

    The demo uses unittest from the standard library so the script remains
    dependency-free. The same design can invoke pytest in a real repository.
    """
    test_code = """
import unittest

class CalculatorTests(unittest.TestCase):
    def test_add(self):
        from src.calculator import add
        self.assertEqual(add(2, 3), 5)

    def test_negative_value(self):
        from src.calculator import add
        self.assertEqual(add(-2, 5), 3)

if __name__ == "__main__":
    unittest.main()
""".strip()

    test_file = repo / ".automation_test.py"
    test_file.write_text(test_code + "\n", encoding="utf-8")

    try:
        code, stdout, stderr = run_command(
            ["python", str(test_file.name)],
            repo,
            timeout=20,
        )
    finally:
        test_file.unlink(missing_ok=True)

    if code != 0:
        return CheckResult(
            "automated-tests",
            False,
            "Automated tests failed.",
            [stderr or stdout or "No test output"],
        )

    return CheckResult(
        "automated-tests",
        True,
        "Automated tests completed successfully.",
        [stdout.replace("\n", " ")],
    )


def check_git_integrity(repo: Path) -> CheckResult:
    code, stdout, stderr = git(repo, "fsck", "--no-progress")

    if code != 0:
        return CheckResult(
            "git-integrity",
            False,
            "Git object integrity check failed.",
            [stderr or stdout],
        )

    return CheckResult(
        "git-integrity",
        True,
        "Git object database passed fsck.",
    )


def run_pre_commit_checks(repo: Path, policy: RepositoryPolicy) -> AutomationReport:
    staged = list_staged_files(repo)
    results = [
        validate_file_paths(staged),
        validate_file_sizes(repo, staged),
    ]

    if policy.require_secret_scan:
        results.append(scan_for_secrets(repo, staged))

    if policy.require_clean_whitespace:
        results.append(validate_trailing_whitespace(repo, staged))

    if policy.require_tests:
        results.append(run_python_tests(repo))

    return AutomationReport(results)


def install_demo_hooks(repo: Path) -> list[HookConfig]:
    """
    Create real Git hook scripts inside the temporary repository.

    Git hooks are executable files in .git/hooks. This example creates hooks
    that point to a repository-local Python validator. The hook files are
    deliberately installed only in the temporary demonstration repository.
    """
    hooks_directory = repo / ".git" / "hooks"
    hooks_directory.mkdir(parents=True, exist_ok=True)

    validator = repo / "automation_validator.py"
    validator.write_text(
        """
import sys
from pathlib import Path

repo = Path(__file__).resolve().parent
print("Repository-local Git automation validator invoked.")

if len(sys.argv) > 1 and sys.argv[1] == "commit-msg":
    message_file = Path(sys.argv[2])
    message = message_file.read_text(encoding="utf-8")
    subject = message.strip().splitlines()[0] if message.strip() else ""
    if not subject.startswith(("feat:", "fix:", "docs:", "test:", "chore:", "ci:")):
        print("Commit rejected: unsupported commit subject.", file=sys.stderr)
        raise SystemExit(1)

raise SystemExit(0)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    pre_commit = hooks_directory / "pre-commit"
    pre_commit.write_text(
        "#!/bin/sh\n"
        'python3 automation_validator.py pre-commit\n',
        encoding="utf-8",
    )

    commit_msg = hooks_directory / "commit-msg"
    commit_msg.write_text(
        "#!/bin/sh\n"
        'python3 automation_validator.py commit-msg "$1"\n',
        encoding="utf-8",
    )

    # Git executes hooks as programs on Unix-like systems. Windows Git Bash
    # handles shell hooks; chmod is attempted only where supported.
    try:
        pre_commit.chmod(pre_commit.stat().st_mode | 0o111)
        commit_msg.chmod(commit_msg.stat().st_mode | 0o111)
    except OSError:
        pass

    return [
        HookConfig(
            "pre-commit",
            True,
            "Validates staged content before Git creates a commit.",
        ),
        HookConfig(
            "commit-msg",
            True,
            "Validates the commit message after the editor completes.",
        ),
    ]


def demonstrate_commit_rejection(repo: Path) -> None:
    """
    Demonstrate a failing validation without relying on a globally installed
    hook manager. The same validator concept can be connected to Git hooks,
    CI, or both.
    """
    invalid_message = "updated things"
    result = validate_commit_message(invalid_message)

    print("\n=== Invalid Commit Demonstration ===")
    print(result.display())

    valid_message = "fix(validation): reject invalid commit subjects"
    result = validate_commit_message(valid_message)
    print(result.display())


def demonstrate_staged_validation(repo: Path) -> None:
    staged_file = repo / "src" / "calculator.py"
    original = staged_file.read_text(encoding="utf-8")

    # Introduce a realistic quality failure: trailing whitespace.
    staged_file.write_text(
        original.rstrip("\n") + " \n",
        encoding="utf-8",
    )

    code, stdout, stderr = git(repo, "add", str(staged_file.relative_to(repo)))
    if code != 0:
        raise RuntimeError(stderr or stdout)

    report = run_pre_commit_checks(repo, RepositoryPolicy())
    report.print_report("Pre-Commit Validation With Failure")

    # Repair the staged content so the repository can continue to the
    # successful validation demonstration.
    staged_file.write_text(original, encoding="utf-8")
    code, stdout, stderr = git(repo, "add", str(staged_file.relative_to(repo)))
    if code != 0:
        raise RuntimeError(stderr or stdout)


def demonstrate_successful_validation(repo: Path) -> None:
    report = run_pre_commit_checks(repo, RepositoryPolicy())
    report.print_report("Successful Pre-Commit Validation")

    if not report.passed:
        raise RuntimeError("Expected the repaired repository to pass validation.")


def demonstrate_automated_commit(repo: Path) -> None:
    file_path = repo / "README.md"
    content = file_path.read_text(encoding="utf-8")
    content += "\nAutomation checks run before this commit.\n"
    file_path.write_text(content, encoding="utf-8")

    code, stdout, stderr = git(repo, "add", "README.md")
    if code != 0:
        raise RuntimeError(stderr or stdout)

    message = "docs(automation): document validation workflow"
    validation = validate_commit_message(message)

    print("\n=== Commit Gate ===")
    print(validation.display())

    if not validation.passed:
        raise RuntimeError("Commit should not proceed after message validation failure.")

    code, stdout, stderr = git(repo, "commit", "-m", message)
    if code != 0:
        raise RuntimeError(f"Commit failed: {stderr or stdout}")

    print("Commit created successfully.")
    print(stdout)


def generate_audit_report(
    repo: Path,
    policy: RepositoryPolicy,
    hook_configs: list[HookConfig],
    report: AutomationReport,
) -> Path:
    audit = {
        "repository": PROJECT_NAME,
        "repository_path": str(repo),
        "policy": asdict(policy),
        "hooks": [asdict(hook) for hook in hook_configs],
        "checks": [asdict(result) for result in report.results],
        "passed": report.passed,
    }

    output = repo / "automation-audit.json"
    output.write_text(
        json.dumps(audit, indent=2),
        encoding="utf-8",
    )
    return output


def demonstrate_ci_pipeline(repo: Path) -> None:
    """
    CI should repeat important local checks because client-side hooks are not
    a security boundary. Developers can bypass local hooks, while CI evaluates
    the pushed repository state in an independent environment.
    """
    policy = RepositoryPolicy(
        require_commit_message=True,
        require_tests=True,
        require_secret_scan=True,
        require_clean_whitespace=True,
    )

    staged = list_staged_files(repo)
    results = [
        validate_file_paths(staged),
        validate_file_sizes(repo, staged),
        scan_for_secrets(repo, staged),
        validate_trailing_whitespace(repo, staged),
        run_python_tests(repo),
        check_git_integrity(repo),
    ]

    report = AutomationReport(results)
    report.print_report("CI-Style Automated Checks")

    audit_path = generate_audit_report(
        repo,
        policy,
        install_demo_hooks(repo),
        report,
    )
    print(f"Audit report: {audit_path.name}")


def explain_hook_boundaries() -> None:
    print(
        """
=== Hook Boundaries ===
pre-commit  -> validates staged files before a commit object is created.
commit-msg  -> validates the commit message supplied to Git.
pre-push   -> can run broader checks before local refs are pushed.
post-commit -> can perform local notification or bookkeeping after success.
CI         -> independently validates pushed repository state.

Local hooks improve developer feedback speed, but they are not authoritative
because users control their own local Git configuration. Server-side CI and
repository policy are required when a check must be enforced for everyone.
""".strip()
    )


def main() -> int:
    print("Git Automation Demonstration")
    print("============================")

    with tempfile.TemporaryDirectory(prefix="git-automation-") as temporary:
        repo = Path(temporary)
        initialize_demo_repository(repo)

        hooks = install_demo_hooks(repo)

        print("\n=== Configured Hooks ===")
        for hook in hooks:
            state = "enabled" if hook.enabled else "disabled"
            print(f"{hook.hook_name}: {state} - {hook.description}")

        explain_hook_boundaries()
        demonstrate_commit_rejection(repo)
        demonstrate_staged_validation(repo)
        demonstrate_successful_validation(repo)
        demonstrate_automated_commit(repo)
        demonstrate_ci_pipeline(repo)

        code, stdout, stderr = git(
            repo,
            "log",
            "--oneline",
            "--decorate",
            "-5",
        )
        if code == 0:
            print("\n=== Recent Repository History ===")
            print(stdout)

    print("\nTemporary repository removed safely.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
