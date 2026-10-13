#!/usr/bin/env python3
"""
Code Quality Engineering: Linters, Formatters, and Static Analysis

A self-contained demonstration of code quality checks for a Python
repository. It implements source validation, formatting checks, lightweight
static analysis, configurable quality policies, file scanning, JSON reports,
and regression tests using only the Python standard library.

Run:
    python code_quality.py
    python code_quality.py --path ./src
    python code_quality.py --path ./src --report quality-report.json
    python code_quality.py --self-test
"""

from __future__ import annotations

import argparse
import ast
import json
import re
import sys
import tempfile
import textwrap
import tokenize
import unittest

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


@dataclass(frozen=True)
class Finding:
    """A machine-readable code quality finding."""

    rule: str
    severity: str
    message: str
    path: str
    line: int = 1
    column: int = 1

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class QualityConfig:
    """Repository-specific quality policy."""

    max_line_length: int = 88
    max_function_lines: int = 50
    max_parameters: int = 5
    max_cyclomatic_complexity: int = 10
    require_final_newline: bool = True
    allow_wildcard_imports: bool = False
    fail_on_warnings: bool = False

    def __post_init__(self) -> None:
        if self.max_line_length < 20:
            raise ValueError("max_line_length must be at least 20")
        if self.max_function_lines < 1:
            raise ValueError("max_function_lines must be positive")
        if self.max_parameters < 0:
            raise ValueError("max_parameters cannot be negative")
        if self.max_cyclomatic_complexity < 1:
            raise ValueError("max_cyclomatic_complexity must be positive")


class QualityReport:
    """Collects findings and computes a reproducible quality summary."""

    def __init__(self) -> None:
        self.findings: list[Finding] = []
        self.files_scanned = 0
        self.parse_failures = 0

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def summary(self) -> dict[str, object]:
        severities = Counter(item.severity for item in self.findings)
        rules = Counter(item.rule for item in self.findings)
        return {
            "files_scanned": self.files_scanned,
            "parse_failures": self.parse_failures,
            "finding_count": len(self.findings),
            "by_severity": dict(sorted(severities.items())),
            "by_rule": dict(sorted(rules.items())),
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "summary": self.summary(),
            "findings": [
                finding.to_dict()
                for finding in sorted(
                    self.findings,
                    key=lambda item: (
                        item.path,
                        item.line,
                        item.column,
                        item.rule,
                    ),
                )
            ],
        }

    def print_console(self) -> None:
        for finding in sorted(
            self.findings,
            key=lambda item: (
                item.path,
                item.line,
                item.column,
                item.rule,
            ),
        ):
            print(
                f"{finding.path}:{finding.line}:{finding.column}: "
                f"{finding.severity} {finding.rule}: {finding.message}"
            )

        summary = self.summary()
        print("\nQuality report")
        print(f"Files scanned: {summary['files_scanned']}")
        print(f"Parse failures: {summary['parse_failures']}")
        print(f"Findings: {summary['finding_count']}")
        print(f"By severity: {summary['by_severity']}")


def complexity_of(node: ast.AST) -> int:
    """
    Approximate McCabe cyclomatic complexity.

    A function starts at complexity one. Branches and compound conditions
    increase the score. Nested function bodies are excluded from the
    enclosing function's score.
    """
    complexity = 1

    for child in ast.walk(node):
        if child is not node and isinstance(
            child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)
        ):
            continue

        if isinstance(child, (ast.If, ast.For, ast.AsyncFor, ast.While)):
            complexity += 1
        elif isinstance(child, (ast.IfExp, ast.ExceptHandler)):
            complexity += 1
        elif isinstance(child, ast.BoolOp):
            complexity += max(0, len(child.values) - 1)
        elif isinstance(child, ast.comprehension):
            complexity += len(child.ifs)

    return complexity


def function_end_line(node: ast.AST) -> int:
    """Find a function's last relevant source line, including its body."""
    end_line = getattr(node, "end_lineno", None)
    if end_line is not None:
        return end_line

    lines = [
        getattr(child, "lineno", 1)
        for child in ast.walk(node)
        if hasattr(child, "lineno")
    ]
    return max(lines, default=getattr(node, "lineno", 1))


class PythonQualityAnalyzer:
    """Performs deterministic lint-style checks on Python source."""

    def __init__(self, config: QualityConfig | None = None) -> None:
        self.config = config or QualityConfig()

    def analyze_text(
        self,
        source: str,
        path: str = "<memory>",
    ) -> list[Finding]:
        findings: list[Finding] = []
        lines = source.splitlines()

        if (
            self.config.require_final_newline
            and source
            and not source.endswith("\n")
        ):
            findings.append(
                Finding(
                    "CQ001",
                    "warning",
                    "File must end with a newline.",
                    path,
                    max(1, len(lines)),
                    1,
                )
            )

        # These checks are deliberately lexical. They are fast, but string
        # matching can produce false positives inside comments or literals.
        for line_number, line in enumerate(lines, start=1):
            if len(line) > self.config.max_line_length:
                findings.append(
                    Finding(
                        "CQ002",
                        "warning",
                        f"Line has {len(line)} characters; limit is "
                        f"{self.config.max_line_length}.",
                        path,
                        line_number,
                        self.config.max_line_length + 1,
                    )
                )

            if line.rstrip(" \t") != line:
                findings.append(
                    Finding(
                        "CQ003",
                        "warning",
                        "Trailing whitespace detected.",
                        path,
                        line_number,
                        len(line.rstrip(" \t")) + 1,
                    )
                )

            if "\t" in line[: len(line) - len(line.lstrip())]:
                findings.append(
                    Finding(
                        "CQ004",
                        "error",
                        "Use spaces rather than tabs for indentation.",
                        path,
                        line_number,
                        1,
                    )
                )

            if re.search(r"\bprint\s*\(", line):
                findings.append(
                    Finding(
                        "CQ005",
                        "info",
                        "Review print() usage in production code; "
                        "structured logging may be more appropriate.",
                        path,
                        line_number,
                        line.find("print") + 1,
                    )
                )

            if re.search(r"\bexcept\s*:", line):
                findings.append(
                    Finding(
                        "CQ006",
                        "warning",
                        "Bare except catches exceptions such as "
                        "KeyboardInterrupt and SystemExit.",
                        path,
                        line_number,
                        line.find("except") + 1,
                    )
                )

            if re.search(r"\bassert\b", line):
                findings.append(
                    Finding(
                        "CQ007",
                        "info",
                        "Do not rely on assert for production input "
                        "validation; optimized Python can remove assertions.",
                        path,
                        line_number,
                        line.find("assert") + 1,
                    )
                )

        try:
            tree = ast.parse(source, filename=path)
        except SyntaxError as exc:
            findings.append(
                Finding(
                    "CQ008",
                    "error",
                    f"Syntax error: {exc.msg}.",
                    path,
                    exc.lineno or 1,
                    exc.offset or 1,
                )
            )
            return findings

        findings.extend(self._analyze_ast(tree, path))
        return findings

    def _analyze_ast(self, tree: ast.AST, path: str) -> list[Finding]:
        findings: list[Finding] = []

        imported_names: set[str] = set()
        used_names: set[str] = set()
        wildcard_imports: list[ast.ImportFrom] = []
        function_nodes: list[ast.FunctionDef | ast.AsyncFunctionDef] = []

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used_names.add(node.id)

            if isinstance(node, ast.Import):
                for alias in node.names:
                    bound_name = alias.asname or alias.name.split(".")[0]
                    imported_names.add(bound_name)

            elif isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if alias.name == "*":
                        wildcard_imports.append(node)
                    else:
                        imported_names.add(alias.asname or alias.name)

            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                function_nodes.append(node)

        # This simple unused-import detector avoids reporting names that
        # appear as imported symbols in any loaded Name node. It does not
        # attempt sophisticated scope or re-export analysis.
        for imported_name in sorted(imported_names - used_names):
            line_number = 1
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        bound = alias.asname or alias.name.split(".")[0]
                        if bound == imported_name:
                            line_number = node.lineno
                            break
                elif isinstance(node, ast.ImportFrom):
                    for alias in node.names:
                        bound = alias.asname or alias.name
                        if bound == imported_name:
                            line_number = node.lineno
                            break

            findings.append(
                Finding(
                    "CQ009",
                    "warning",
                    f"Imported name '{imported_name}' appears unused.",
                    path,
                    line_number,
                    1,
                )
            )

        if not self.config.allow_wildcard_imports:
            for node in wildcard_imports:
                findings.append(
                    Finding(
                        "CQ010",
                        "warning",
                        "Wildcard imports obscure the names introduced "
                        "into the module namespace.",
                        path,
                        node.lineno,
                        node.col_offset + 1,
                    )
                )

        for node in function_nodes:
            parameters = (
                node.args.posonlyargs
                + node.args.args
                + node.args.kwonlyargs
            )
            if node.args.vararg is not None:
                parameters.append(node.args.vararg)
            if node.args.kwarg is not None:
                parameters.append(node.args.kwarg)

            if len(parameters) > self.config.max_parameters:
                findings.append(
                    Finding(
                        "CQ011",
                        "warning",
                        f"Function '{node.name}' has {len(parameters)} "
                        f"parameters; limit is {self.config.max_parameters}.",
                        path,
                        node.lineno,
                        node.col_offset + 1,
                    )
                )

            line_count = function_end_line(node) - node.lineno + 1
            if line_count > self.config.max_function_lines:
                findings.append(
                    Finding(
                        "CQ012",
                        "warning",
                        f"Function '{node.name}' spans {line_count} lines; "
                        f"limit is {self.config.max_function_lines}.",
                        path,
                        node.lineno,
                        node.col_offset + 1,
                    )
                )

            complexity = complexity_of(node)
            if complexity > self.config.max_cyclomatic_complexity:
                findings.append(
                    Finding(
                        "CQ013",
                        "warning",
                        f"Function '{node.name}' has approximate "
                        f"cyclomatic complexity {complexity}; limit is "
                        f"{self.config.max_cyclomatic_complexity}.",
                        path,
                        node.lineno,
                        node.col_offset + 1,
                    )
                )

        # Mutable list and dictionary defaults persist across calls. Flag
        # direct mutable literals while allowing deliberate immutable defaults.
        for node in function_nodes:
            defaults = list(node.args.defaults) + [
                value
                for value in node.args.kw_defaults
                if value is not None
            ]
            for default in defaults:
                if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                    findings.append(
                        Finding(
                            "CQ014",
                            "error",
                            f"Function '{node.name}' uses a mutable "
                            "literal as a default argument.",
                            path,
                            default.lineno,
                            default.col_offset + 1,
                        )
                    )

        return findings


def format_python(source: str) -> str:
    """
    Apply a small deterministic formatting transformation.

    This is intentionally not a replacement for Black or Ruff formatting.
    It normalizes line endings, removes trailing whitespace, and guarantees
    a final newline. It does not rewrite Python syntax.
    """
    normalized = source.replace("\r\n", "\n").replace("\r", "\n")
    normalized = "\n".join(line.rstrip(" \t") for line in normalized.split("\n"))
    normalized = normalized.rstrip("\n")
    return normalized + "\n" if normalized else ""


def validate_python_syntax(source: str, path: str) -> list[Finding]:
    """Use the interpreter tokenizer and AST parser to validate syntax."""
    findings: list[Finding] = []

    try:
        list(tokenize.generate_tokens(iter(source.splitlines(keepends=True)).__next__))
        ast.parse(source, filename=path)
    except (SyntaxError, tokenize.TokenError, IndentationError) as exc:
        line = getattr(exc, "lineno", None) or 1
        column = getattr(exc, "offset", None) or 1
        message = getattr(exc, "msg", None) or str(exc)
        findings.append(
            Finding("CQ008", "error", f"Syntax validation failed: {message}",
                    path, line, column)
        )

    return findings


def scan_repository(
    root: Path,
    config: QualityConfig | None = None,
    exclude_dirs: Iterable[str] = (
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        "node_modules",
        "build",
        "dist",
    ),
) -> QualityReport:
    """Scan Python files under a repository directory."""
    root = root.resolve()
    if not root.exists():
        raise FileNotFoundError(f"Path does not exist: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Expected a directory: {root}")

    analyzer = PythonQualityAnalyzer(config)
    report = QualityReport()
    excluded = set(exclude_dirs)

    for file_path in sorted(root.rglob("*.py")):
        if any(part in excluded for part in file_path.parts):
            continue

        try:
            source = file_path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            report.add(
                Finding(
                    "CQ015",
                    "error",
                    f"Unable to read source file: {exc}",
                    str(file_path.relative_to(root)),
                )
            )
            continue

        relative_path = str(file_path.relative_to(root))
        report.files_scanned += 1

        syntax_findings = validate_python_syntax(source, relative_path)
        report.findings.extend(syntax_findings)

        if syntax_findings:
            report.parse_failures += 1
            continue

        report.findings.extend(analyzer.analyze_text(source, relative_path))

    return report


def demonstrate_formatting() -> None:
    """Show formatting as a source transformation rather than a lint rule."""
    original = "def total(items):  \r\n    return sum(items)  "
    formatted = format_python(original)

    print("Formatting demonstration")
    print(f"Original:  {original!r}")
    print(f"Formatted: {formatted!r}")
    print(f"Changed:   {original != formatted}")


def demonstrate_static_analysis() -> None:
    """Run the analyzer against code with realistic quality defects."""
    source = textwrap.dedent(
        """\
        import math
        import json

        def evaluate_release(branch, checks, approvals, reviewers=[]):
            try:
                if branch == "main" and checks:
                    if approvals > 0 and reviewers:
                        return True
                    else:
                        return False
                else:
                    return False
            except:
                return False
        """
    )

    findings = PythonQualityAnalyzer().analyze_text(
        source,
        "sample_release_policy.py",
    )

    print("\nStatic analysis demonstration")
    for finding in findings:
        print(
            f"{finding.severity.upper():7} {finding.rule} "
            f"line {finding.line}: {finding.message}"
        )


class QualityAnalyzerTests(unittest.TestCase):
    """Regression tests for core analyzer behavior."""

    def setUp(self) -> None:
        self.analyzer = PythonQualityAnalyzer()

    def test_detects_missing_final_newline(self) -> None:
        findings = self.analyzer.analyze_text("value = 3", "example.py")
        self.assertIn("CQ001", {item.rule for item in findings})

    def test_detects_syntax_error(self) -> None:
        findings = self.analyzer.analyze_text(
            "def broken(:\n    pass\n",
            "broken.py",
        )
        self.assertIn("CQ008", {item.rule for item in findings})

    def test_detects_mutable_default(self) -> None:
        findings = self.analyzer.analyze_text(
            "def add_item(item, values=[]):\n"
            "    values.append(item)\n"
            "    return values\n",
            "mutable_default.py",
        )
        self.assertIn("CQ014", {item.rule for item in findings})

    def test_formatter_is_idempotent(self) -> None:
        source = "value = 3  \r\n"
        formatted = format_python(source)
        self.assertEqual(format_python(formatted), formatted)

    def test_config_rejects_invalid_line_length(self) -> None:
        with self.assertRaises(ValueError):
            QualityConfig(max_line_length=10)

    def test_valid_source_has_no_syntax_finding(self) -> None:
        findings = validate_python_syntax(
            "def merge_allowed(checks_passed: bool) -> bool:\n"
            "    return checks_passed\n",
            "valid.py",
        )
        self.assertEqual(findings, [])

    def test_complexity_counts_branches(self) -> None:
        tree = ast.parse(
            "def policy(a, b):\n"
            "    if a and b:\n"
            "        return True\n"
            "    return False\n"
        )
        function = tree.body[0]
        self.assertEqual(complexity_of(function), 3)

    def test_scanner_ignores_virtual_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "good.py").write_text("value = 1\n", encoding="utf-8")
            (root / ".venv").mkdir()
            (root / ".venv" / "ignored.py").write_text(
                "value = 2\n",
                encoding="utf-8",
            )

            report = scan_repository(root)
            self.assertEqual(report.files_scanned, 1)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Inspect Python code using lightweight quality rules."
    )
    parser.add_argument(
        "--path",
        type=Path,
        default=Path("."),
        help="Directory to scan recursively.",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="Optional JSON report output path.",
    )
    parser.add_argument(
        "--max-line-length",
        type=int,
        default=88,
        help="Maximum allowed source line length.",
    )
    parser.add_argument(
        "--fail-on-warnings",
        action="store_true",
        help="Return a failure exit code when warnings exist.",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="Run the built-in regression tests.",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run formatting and static-analysis demonstrations.",
    )
    args = parser.parse_args(argv)

    if args.self_test:
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(
            QualityAnalyzerTests
        )
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1

    if args.demo:
        demonstrate_formatting()
        demonstrate_static_analysis()

    try:
        config = QualityConfig(
            max_line_length=args.max_line_length,
            fail_on_warnings=args.fail_on_warnings,
        )
        report = scan_repository(args.path, config)
    except (OSError, ValueError) as exc:
        print(f"Quality scan failed: {exc}", file=sys.stderr)
        return 2

    report.print_console()

    if args.report:
        try:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(
                json.dumps(report.to_dict(), indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            print(f"Unable to write report: {exc}", file=sys.stderr)
            return 2
        print(f"JSON report written to {args.report}")

    errors = sum(item.severity == "error" for item in report.findings)
    warnings = sum(item.severity == "warning" for item in report.findings)

    if errors or (config.fail_on_warnings and warnings):
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
