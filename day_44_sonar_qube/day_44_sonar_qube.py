#!/usr/bin/env python3
"""
SonarQube Quality Engineering Lab

A self-contained simulation of static code analysis, quality gates,
technical debt, quality metrics, issue lifecycles, and CI merge decisions.

Run:
    python sonarqube_quality_lab.py
    python sonarqube_quality_lab.py --json
    python sonarqube_quality_lab.py --strict

The implementation uses illustrative analysis findings and configurable
policies. It does not connect to a SonarQube server or reproduce its
proprietary analysis algorithms.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Iterable


class Severity(str, Enum):
    BLOCKER = "BLOCKER"
    CRITICAL = "CRITICAL"
    MAJOR = "MAJOR"
    MINOR = "MINOR"
    INFO = "INFO"


class IssueType(str, Enum):
    BUG = "BUG"
    VULNERABILITY = "VULNERABILITY"
    CODE_SMELL = "CODE_SMELL"
    SECURITY_HOTSPOT = "SECURITY_HOTSPOT"


class GateStatus(str, Enum):
    OK = "OK"
    ERROR = "ERROR"
    NO_ANALYSIS = "NO_ANALYSIS"


@dataclass(frozen=True)
class Issue:
    key: str
    component: str
    rule: str
    issue_type: IssueType
    severity: Severity
    message: str
    effort_minutes: int
    line: int
    introduced_in_current_change: bool = True
    resolved: bool = False
    reviewed_hotspot: bool = True

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.component.strip():
            raise ValueError("Issue key and component must not be empty.")
        if self.effort_minutes < 0 or self.line < 1:
            raise ValueError("Effort cannot be negative and line must be positive.")
        if self.issue_type == IssueType.SECURITY_HOTSPOT and self.severity == Severity.BLOCKER:
            raise ValueError("Security hotspots require an explicit security review, not a blocker severity shortcut.")


@dataclass(frozen=True)
class QualityProfile:
    name: str
    rules: dict[str, bool]
    description: str

    def is_enabled(self, rule: str) -> bool:
        return self.rules.get(rule, True)


@dataclass(frozen=True)
class GateCondition:
    metric: str
    operator: str
    threshold: float
    scope: str = "new_code"
    description: str = ""

    def __post_init__(self) -> None:
        allowed_metrics = {
            "coverage_percent",
            "duplicated_lines_percent",
            "reliability_rating",
            "security_rating",
            "maintainability_rating",
            "new_bugs",
            "new_vulnerabilities",
            "new_blocker_issues",
            "new_critical_issues",
            "new_code_smells",
            "new_technical_debt_minutes",
            "technical_debt_minutes",
            "security_hotspots_reviewed_percent",
        }
        if self.metric not in allowed_metrics:
            raise ValueError(f"Unsupported gate metric: {self.metric}")
        if self.operator not in {">", ">=", "<", "<=", "=", "!="}:
            raise ValueError(f"Unsupported operator: {self.operator}")
        if not math.isfinite(self.threshold):
            raise ValueError("Threshold must be finite.")
        if self.scope not in {"new_code", "overall"}:
            raise ValueError("Scope must be new_code or overall.")


@dataclass
class Analysis:
    project_key: str
    branch: str
    commit_sha: str
    analyzed_at: str
    lines_of_code: int
    covered_lines: int
    duplicated_lines: int
    new_lines: int
    new_covered_lines: int
    new_duplicated_lines: int
    issues: list[Issue]
    analyzed: bool = True
    analysis_error: str | None = None

    def __post_init__(self) -> None:
        if not self.project_key.strip() or not self.branch.strip():
            raise ValueError("Project key and branch are required.")
        if not self.commit_sha.strip():
            raise ValueError("Commit SHA is required.")
        for name in (
            "lines_of_code", "covered_lines", "duplicated_lines", "new_lines",
            "new_covered_lines", "new_duplicated_lines",
        ):
            value = getattr(self, name)
            if value < 0:
                raise ValueError(f"{name} cannot be negative.")
        if self.covered_lines > self.lines_of_code:
            raise ValueError("Covered lines cannot exceed lines of code.")
        if self.duplicated_lines > self.lines_of_code:
            raise ValueError("Duplicated lines cannot exceed lines of code.")
        if self.new_covered_lines > self.new_lines:
            raise ValueError("New covered lines cannot exceed new lines.")
        if self.new_duplicated_lines > self.new_lines:
            raise ValueError("New duplicated lines cannot exceed new lines.")

    @staticmethod
    def percentage(numerator: int, denominator: int) -> float:
        # Zero executable lines do not imply 100% coverage.
        return round(100.0 * numerator / denominator, 2) if denominator else 0.0

    def active_issues(self, scope: str = "overall") -> list[Issue]:
        issues = [issue for issue in self.issues if not issue.resolved]
        if scope == "new_code":
            return [issue for issue in issues if issue.introduced_in_current_change]
        return issues

    def metrics(self) -> dict[str, float | int]:
        overall = self.active_issues("overall")
        new = self.active_issues("new_code")

        def count(items: Iterable[Issue], issue_type: IssueType | None = None,
                  severity: Severity | None = None) -> int:
            return sum(
                1 for issue in items
                if (issue_type is None or issue.issue_type == issue_type)
                and (severity is None or issue.severity == severity)
            )

        new_debt = sum(issue.effort_minutes for issue in new)
        total_debt = sum(issue.effort_minutes for issue in overall)

        # A small educational rating approximation, not SonarQube's official rating algorithm.
        def rating(bad_count: int) -> int:
            if bad_count == 0:
                return 1
            if bad_count <= 2:
                return 2
            if bad_count <= 5:
                return 3
            if bad_count <= 10:
                return 4
            return 5

        new_hotspots = [
            issue for issue in new
            if issue.issue_type == IssueType.SECURITY_HOTSPOT
        ]
        all_hotspots = [
            issue for issue in overall
            if issue.issue_type == IssueType.SECURITY_HOTSPOT
        ]

        return {
            "coverage_percent": self.percentage(self.covered_lines, self.lines_of_code),
            "new_coverage_percent": self.percentage(self.new_covered_lines, self.new_lines),
            "duplicated_lines_percent": self.percentage(self.duplicated_lines, self.lines_of_code),
            "new_duplicated_lines_percent": self.percentage(
                self.new_duplicated_lines, self.new_lines
            ),
            "new_bugs": count(new, IssueType.BUG),
            "new_vulnerabilities": count(new, IssueType.VULNERABILITY),
            "new_blocker_issues": count(new, severity=Severity.BLOCKER),
            "new_critical_issues": count(new, severity=Severity.CRITICAL),
            "new_code_smells": count(new, IssueType.CODE_SMELL),
            "new_technical_debt_minutes": new_debt,
            "technical_debt_minutes": total_debt,
            "reliability_rating": rating(
                count(overall, IssueType.BUG)
            ),
            "security_rating": rating(
                count(overall, IssueType.VULNERABILITY)
            ),
            "maintainability_rating": rating(
                count(overall, IssueType.CODE_SMELL)
            ),
            "security_hotspots_reviewed_percent": self.percentage(
                sum(1 for issue in all_hotspots if issue.reviewed_hotspot),
                len(all_hotspots),
            ),
            "new_security_hotspots": len(new_hotspots),
            "total_active_issues": len(overall),
            "new_active_issues": len(new),
        }


@dataclass
class GateResult:
    status: GateStatus
    metrics: dict[str, float | int]
    failed_conditions: list[dict[str, Any]]
    evaluated_conditions: list[dict[str, Any]]
    explanation: str


@dataclass
class QualityGate:
    name: str
    conditions: list[GateCondition]
    require_analysis: bool = True

    @staticmethod
    def compare(actual: float | int, operator: str, expected: float) -> bool:
        return {
            ">": lambda: actual > expected,
            ">=": lambda: actual >= expected,
            "<": lambda: actual < expected,
            "<=": lambda: actual <= expected,
            "=": lambda: actual == expected,
            "!=": lambda: actual != expected,
        }[operator]()

    def evaluate(self, analysis: Analysis | None) -> GateResult:
        if analysis is None or not analysis.analyzed:
            return GateResult(
                GateStatus.NO_ANALYSIS,
                {},
                [],
                [],
                "No successful analysis is available; a missing result is not a pass.",
            )

        metrics = analysis.metrics()
        failed: list[dict[str, Any]] = []
        evaluated: list[dict[str, Any]] = []

        for condition in self.conditions:
            metric_value = metrics.get(condition.metric)
            if metric_value is None:
                failed.append({
                    "metric": condition.metric,
                    "reason": "Metric is unavailable.",
                })
                continue

            passed = self.compare(
                metric_value, condition.operator, condition.threshold
            )
            detail = {
                "metric": condition.metric,
                "actual": metric_value,
                "operator": condition.operator,
                "threshold": condition.threshold,
                "scope": condition.scope,
                "passed": passed,
                "description": condition.description,
            }
            evaluated.append(detail)
            if not passed:
                failed.append(detail)

        return GateResult(
            GateStatus.ERROR if failed else GateStatus.OK,
            metrics,
            failed,
            evaluated,
            "Quality gate failed." if failed else "All configured quality conditions passed.",
        )


class RepositoryWorkflow:
    """Models the relationship between analysis, gate status, and merge eligibility."""

    def __init__(self, gate: QualityGate) -> None:
        self.gate = gate
        self.analyses: dict[str, Analysis] = {}
        self.gate_results: dict[str, GateResult] = {}
        self.merged_commits: list[str] = []

    def publish_analysis(self, analysis: Analysis) -> GateResult:
        self.analyses[analysis.branch] = analysis
        result = self.gate.evaluate(analysis)
        self.gate_results[analysis.branch] = result
        return result

    def can_merge(self, branch: str, protected: bool = True) -> tuple[bool, str]:
        if branch not in self.analyses:
            return False, "No analysis has been published for this branch."
        result = self.gate_results[branch]
        if result.status != GateStatus.OK:
            return False, f"Quality gate status is {result.status.value}."
        if protected and branch == "main":
            return False, "Direct changes to the protected main branch are prohibited."
        return True, "Analysis passed; other repository policies must also permit merging."

    def merge(self, branch: str) -> str:
        allowed, reason = self.can_merge(branch)
        if not allowed:
            raise RuntimeError(f"Merge rejected: {reason}")
        analysis = self.analyses[branch]
        self.merged_commits.append(analysis.commit_sha)
        return analysis.commit_sha


def build_demo_analysis() -> Analysis:
    findings = [
        Issue(
            key="ISSUE-101",
            component="src/payments.py",
            rule="python:S3776",
            issue_type=IssueType.CODE_SMELL,
            severity=Severity.MAJOR,
            message="Payment authorization has excessive cognitive complexity.",
            effort_minutes=45,
            line=84,
        ),
        Issue(
            key="ISSUE-102",
            component="src/payments.py",
            rule="python:S3649",
            issue_type=IssueType.VULNERABILITY,
            severity=Severity.CRITICAL,
            message="A query uses untrusted input without safe parameterization.",
            effort_minutes=90,
            line=132,
        ),
        Issue(
            key="ISSUE-103",
            component="tests/test_payments.py",
            rule="python:S2699",
            issue_type=IssueType.CODE_SMELL,
            severity=Severity.MAJOR,
            message="A test does not contain an assertion.",
            effort_minutes=15,
            line=47,
        ),
        Issue(
            key="ISSUE-104",
            component="src/legacy_adapter.py",
            rule="python:S1481",
            issue_type=IssueType.CODE_SMELL,
            severity=Severity.MINOR,
            message="An unused local variable remains in legacy code.",
            effort_minutes=10,
            line=26,
            introduced_in_current_change=False,
        ),
        Issue(
            key="ISSUE-105",
            component="src/crypto.py",
            rule="python:S4787",
            issue_type=IssueType.SECURITY_HOTSPOT,
            severity=Severity.MAJOR,
            message="Review whether the cryptographic construction is appropriate.",
            effort_minutes=30,
            line=59,
            reviewed_hotspot=False,
        ),
    ]

    return Analysis(
        project_key="payments-service",
        branch="feature/parameterized-payment-query",
        commit_sha="a91f4c2d",
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        lines_of_code=2400,
        covered_lines=1900,
        duplicated_lines=96,
        new_lines=120,
        new_covered_lines=78,
        new_duplicated_lines=12,
        issues=findings,
    )


def build_quality_gate(strict: bool = False) -> QualityGate:
    conditions = [
        GateCondition(
            "new_coverage_percent", ">=", 80.0,
            description="New executable code must meet the coverage target.",
        ),
        GateCondition(
            "new_duplicated_lines_percent", "<=", 3.0,
            description="Keep duplication in changed code below the limit.",
        ),
        GateCondition(
            "new_bugs", "=", 0,
            description="New bugs are not permitted.",
        ),
        GateCondition(
            "new_vulnerabilities", "=", 0,
            description="New security vulnerabilities are not permitted.",
        ),
        GateCondition(
            "new_blocker_issues", "=", 0,
            description="No new blocker issues are permitted.",
        ),
        GateCondition(
            "security_hotspots_reviewed_percent", ">=", 100.0,
            scope="overall",
            description="All active security hotspots must be reviewed.",
        ),
    ]
    if strict:
        conditions.extend([
            GateCondition(
                "new_critical_issues", "=", 0,
                description="Strict policy prohibits new critical issues.",
            ),
            GateCondition(
                "new_technical_debt_minutes", "<=", 30,
                description="Limit remediation effort introduced by the change.",
            ),
        ])
    return QualityGate("Production Quality Gate", conditions)


def print_report(analysis: Analysis, result: GateResult) -> None:
    print(f"\nProject: {analysis.project_key}")
    print(f"Branch: {analysis.branch}")
    print(f"Commit: {analysis.commit_sha}")
    print(f"Analysis time: {analysis.analyzed_at}")
    print(f"Quality gate: {result.status.value}")
    print(f"Reason: {result.explanation}")

    print("\nQuality metrics")
    for name, value in sorted(result.metrics.items()):
        suffix = "%" if name.endswith("_percent") else ""
        if name.endswith("_minutes"):
            suffix = " min"
        print(f"  {name:42} {value}{suffix}")

    print("\nGate condition evaluation")
    for condition in result.evaluated_conditions:
        state = "PASS" if condition["passed"] else "FAIL"
        print(
            f"  [{state}] {condition['metric']}: "
            f"{condition['actual']} {condition['operator']} "
            f"{condition['threshold']}"
        )

    if result.failed_conditions:
        print("\nBlocking conditions")
        for item in result.failed_conditions:
            print(f"  {item.get('metric', 'unknown')}: {item}")

    print("\nActive findings")
    for issue in analysis.active_issues():
        scope = "new code" if issue.introduced_in_current_change else "existing code"
        print(
            f"  {issue.key} | {issue.issue_type.value} | {issue.severity.value} | "
            f"{issue.component}:{issue.line} | {scope} | "
            f"{issue.effort_minutes} min | {issue.message}"
        )


def run_self_tests() -> None:
    analysis = build_demo_analysis()
    metrics = analysis.metrics()

    assert metrics["new_bugs"] == 0
    assert metrics["new_vulnerabilities"] == 1
    assert metrics["new_technical_debt_minutes"] == 180
    assert metrics["technical_debt_minutes"] == 190
    assert metrics["new_coverage_percent"] == 65.0

    gate = build_quality_gate()
    failed = gate.evaluate(analysis)
    assert failed.status == GateStatus.ERROR

    passing_analysis = Analysis(
        project_key="healthy-service",
        branch="feature/safe-change",
        commit_sha="b72a6e1",
        analyzed_at=datetime.now(timezone.utc).isoformat(),
        lines_of_code=1000,
        covered_lines=900,
        duplicated_lines=10,
        new_lines=100,
        new_covered_lines=90,
        new_duplicated_lines=2,
        issues=[],
    )
    passing = gate.evaluate(passing_analysis)
    assert passing.status == GateStatus.OK

    assert gate.evaluate(None).status == GateStatus.NO_ANALYSIS

    workflow = RepositoryWorkflow(gate)
    workflow.publish_analysis(passing_analysis)
    assert workflow.can_merge("feature/safe-change")[0]
    assert workflow.merge("feature/safe-change") == "b72a6e1"

    try:
        workflow.merge("missing-branch")
    except RuntimeError:
        pass
    else:
        raise AssertionError("A branch without an analysis must not merge.")

    try:
        GateCondition("coverage_percent", "approximately", 80)
    except ValueError:
        pass
    else:
        raise AssertionError("Unsupported operators must be rejected.")

    try:
        Analysis(
            project_key="invalid",
            branch="feature/bad",
            commit_sha="bad",
            analyzed_at="",
            lines_of_code=10,
            covered_lines=11,
            duplicated_lines=0,
            new_lines=2,
            new_covered_lines=1,
            new_duplicated_lines=0,
            issues=[],
        )
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid coverage counts must be rejected.")

    print("All self-tests passed.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Simulate SonarQube quality metrics and quality gates."
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Print machine-readable analysis and gate results."
    )
    parser.add_argument(
        "--strict", action="store_true",
        help="Add critical-issue and technical-debt gate conditions."
    )
    parser.add_argument(
        "--test", action="store_true",
        help="Run executable assertions and exit."
    )
    args = parser.parse_args()

    try:
        if args.test:
            run_self_tests()
            return 0

        analysis = build_demo_analysis()
        gate = build_quality_gate(args.strict)
        result = gate.evaluate(analysis)

        if args.json:
            payload = {
                "analysis": {
                    **{
                        key: value
                        for key, value in asdict(analysis).items()
                        if key != "issues"
                    },
                    "issues": [
                        {
                            **asdict(issue),
                            "issue_type": issue.issue_type.value,
                            "severity": issue.severity.value,
                        }
                        for issue in analysis.issues
                    ],
                },
                "gate": {
                    "name": gate.name,
                    "status": result.status.value,
                    "metrics": result.metrics,
                    "failed_conditions": result.failed_conditions,
                    "evaluated_conditions": result.evaluated_conditions,
                    "explanation": result.explanation,
                },
            }
            print(json.dumps(payload, indent=2))
        else:
            print_report(analysis, result)

        return 0 if result.status == GateStatus.OK else 1
    except (ValueError, RuntimeError, TypeError) as exc:
        print(f"Execution failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
