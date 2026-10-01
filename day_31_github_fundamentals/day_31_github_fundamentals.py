"""
GitHub Fundamentals: Repositories, Issues, Projects, Actions, and Environments

A self-contained executable model of a GitHub-style repository workflow.
The simulation focuses on how the five areas interact without requiring
GitHub credentials or external packages.

Run:
    python github_fundamentals.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set
import json
import tempfile
import time


class IssueState(str, Enum):
    OPEN = "open"
    CLOSED = "closed"


class WorkflowStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILURE = "failure"
    CANCELLED = "cancelled"


class EnvironmentState(str, Enum):
    READY = "ready"
    WAITING = "waiting"
    DEPLOYED = "deployed"
    FAILED = "failed"


@dataclass
class Repository:
    owner: str
    name: str
    visibility: str = "private"
    default_branch: str = "main"
    branches: Set[str] = field(default_factory=lambda: {"main"})
    files: Dict[str, str] = field(default_factory=dict)

    @property
    def full_name(self) -> str:
        return f"{self.owner}/{self.name}"

    def create_branch(self, branch: str) -> None:
        if not branch or " " in branch:
            raise ValueError("Branch name must be non-empty and contain no spaces.")
        if branch in self.branches:
            raise ValueError(f"Branch '{branch}' already exists.")
        self.branches.add(branch)
        print(f"Created branch: {branch}")

    def add_file(self, path: str, content: str) -> None:
        normalized = Path(path).as_posix()
        if not normalized or normalized.startswith("../"):
            raise ValueError("Invalid repository-relative file path.")
        self.files[normalized] = content

    def repository_summary(self) -> None:
        print(f"\nRepository: {self.full_name}")
        print(f"Visibility: {self.visibility}")
        print(f"Default branch: {self.default_branch}")
        print(f"Branches: {', '.join(sorted(self.branches))}")
        print(f"Tracked files: {len(self.files)}")


@dataclass
class Issue:
    number: int
    title: str
    body: str
    labels: Set[str] = field(default_factory=set)
    assignees: List[str] = field(default_factory=list)
    state: IssueState = IssueState.OPEN
    comments: List[str] = field(default_factory=list)

    def add_comment(self, author: str, message: str) -> None:
        if not message.strip():
            raise ValueError("Issue comments cannot be empty.")
        self.comments.append(f"{author}: {message}")

    def close(self) -> None:
        self.state = IssueState.CLOSED


class IssueTracker:
    """Models repository-level issue creation, discussion, labels, and closure."""

    def __init__(self) -> None:
        self._issues: Dict[int, Issue] = {}
        self._next_number = 1

    def create(
        self,
        title: str,
        body: str,
        labels: Optional[Set[str]] = None,
        assignees: Optional[List[str]] = None,
    ) -> Issue:
        if not title.strip():
            raise ValueError("An issue requires a title.")

        issue = Issue(
            number=self._next_number,
            title=title,
            body=body,
            labels=labels or set(),
            assignees=assignees or [],
        )
        self._issues[issue.number] = issue
        self._next_number += 1
        return issue

    def get(self, number: int) -> Issue:
        if number not in self._issues:
            raise KeyError(f"Issue #{number} does not exist.")
        return self._issues[number]

    def open_issues(self) -> List[Issue]:
        return [
            issue
            for issue in self._issues.values()
            if issue.state == IssueState.OPEN
        ]


@dataclass
class ProjectItem:
    content_type: str
    content_id: str
    status: str = "Todo"
    priority: str = "Medium"
    notes: str = ""


class ProjectBoard:
    """
    A lightweight model of a GitHub Project.

    Project items represent planning information. They are intentionally
    separate from repository files and issues so that project tracking can
    aggregate work across different content types.
    """

    VALID_STATUSES = {"Todo", "In Progress", "Blocked", "Done"}
    VALID_PRIORITIES = {"Low", "Medium", "High", "Critical"}

    def __init__(self, name: str) -> None:
        self.name = name
        self.items: Dict[str, ProjectItem] = {}

    def add_item(self, item: ProjectItem) -> None:
        if item.status not in self.VALID_STATUSES:
            raise ValueError(f"Unsupported project status: {item.status}")
        if item.priority not in self.VALID_PRIORITIES:
            raise ValueError(f"Unsupported priority: {item.priority}")
        key = f"{item.content_type}:{item.content_id}"
        self.items[key] = item

    def move(self, content_type: str, content_id: str, status: str) -> None:
        if status not in self.VALID_STATUSES:
            raise ValueError(f"Unsupported project status: {status}")

        key = f"{content_type}:{content_id}"
        if key not in self.items:
            raise KeyError(f"Project item '{key}' does not exist.")

        self.items[key].status = status

    def metrics(self) -> Dict[str, int]:
        result = {status: 0 for status in self.VALID_STATUSES}
        for item in self.items.values():
            result[item.status] += 1
        return result


@dataclass
class WorkflowRun:
    workflow: str
    event: str
    branch: str
    status: WorkflowStatus = WorkflowStatus.QUEUED
    logs: List[str] = field(default_factory=list)

    def log(self, message: str) -> None:
        self.logs.append(message)


class ActionRunner:
    """
    Models the important mechanics of GitHub Actions without executing
    arbitrary shell commands.

    Real Actions runners execute workflow jobs on hosted or self-hosted
    runners. This educational runner represents those jobs as safe Python
    functions instead.
    """

    def __init__(self) -> None:
        self.runs: List[WorkflowRun] = []

    def run_ci(
        self,
        repository: Repository,
        branch: str,
        expected_files: Optional[List[str]] = None,
    ) -> WorkflowRun:
        if branch not in repository.branches:
            raise ValueError(f"Cannot run workflow: branch '{branch}' does not exist.")

        run = WorkflowRun(
            workflow="CI",
            event="push",
            branch=branch,
        )
        self.runs.append(run)
        run.status = WorkflowStatus.RUNNING
        run.log(f"Checking repository state for {repository.full_name}.")
        run.log(f"Running CI for branch '{branch}'.")

        required = expected_files or ["README.md"]
        missing = [path for path in required if path not in repository.files]

        if missing:
            run.status = WorkflowStatus.FAILURE
            run.log("Missing required files: " + ", ".join(missing))
        else:
            run.status = WorkflowStatus.SUCCESS
            run.log("Repository validation passed.")

        return run

    def latest(self, workflow: str) -> Optional[WorkflowRun]:
        matching = [run for run in self.runs if run.workflow == workflow]
        return matching[-1] if matching else None


@dataclass
class Environment:
    name: str
    variables: Dict[str, str] = field(default_factory=dict)
    secrets: Dict[str, str] = field(default_factory=dict)
    required_approvals: int = 0
    approvals: int = 0
    state: EnvironmentState = EnvironmentState.READY
    deployment_history: List[str] = field(default_factory=list)

    def request_deployment(self, actor: str) -> bool:
        """
        Environment secrets are deliberately not exposed in deployment logs.
        Production environments can also require approval before deployment.
        """
        if self.approvals < self.required_approvals:
            self.state = EnvironmentState.WAITING
            return False

        self.state = EnvironmentState.DEPLOYED
        self.deployment_history.append(actor)
        return True

    def approve(self, reviewer: str) -> None:
        if not reviewer.strip():
            raise ValueError("Reviewer identity is required.")
        self.approvals += 1
        self.state = EnvironmentState.READY


@dataclass
class Deployment:
    environment: str
    branch: str
    commit: str
    status: EnvironmentState
    actor: str


class EnvironmentManager:
    def __init__(self) -> None:
        self.environments: Dict[str, Environment] = {}
        self.deployments: List[Deployment] = []

    def register(self, environment: Environment) -> None:
        if environment.name in self.environments:
            raise ValueError(f"Environment '{environment.name}' already exists.")
        self.environments[environment.name] = environment

    def deploy(
        self,
        environment_name: str,
        branch: str,
        commit: str,
        actor: str,
    ) -> Deployment:
        if environment_name not in self.environments:
            raise KeyError(f"Unknown environment '{environment_name}'.")

        environment = self.environments[environment_name]
        allowed = environment.request_deployment(actor)

        deployment = Deployment(
            environment=environment_name,
            branch=branch,
            commit=commit,
            status=environment.state,
            actor=actor,
        )
        self.deployments.append(deployment)

        if not allowed:
            print(
                f"Deployment to '{environment_name}' is waiting for "
                f"required approvals."
            )

        return deployment


@dataclass
class PullRequest:
    number: int
    source_branch: str
    target_branch: str
    title: str
    author: str
    commits: List[str] = field(default_factory=list)
    changed_files: Dict[str, str] = field(default_factory=dict)
    issue_links: List[int] = field(default_factory=list)
    state: str = "open"

    def add_commit(self, commit_sha: str, changes: Dict[str, str]) -> None:
        if self.state != "open":
            raise RuntimeError("Only an open pull request can receive new commits.")
        if not commit_sha or len(commit_sha) < 7:
            raise ValueError("A commit identifier must be at least seven characters.")
        self.commits.append(commit_sha)
        self.changed_files.update(changes)

    def synchronize(self, base_changed: bool) -> None:
        if self.state != "open":
            raise RuntimeError("Closed pull requests cannot be synchronized.")
        if base_changed:
            print(
                f"PR #{self.number} requires synchronization because "
                f"'{self.target_branch}' changed."
            )

    def close(self) -> None:
        self.state = "closed"

    def reopen(self) -> None:
        if self.state != "closed":
            raise RuntimeError("Only a closed pull request can be reopened.")
        self.state = "open"


class PullRequestTracker:
    def __init__(self) -> None:
        self.pull_requests: Dict[int, PullRequest] = {}
        self._next_number = 1

    def create(
        self,
        source_branch: str,
        target_branch: str,
        title: str,
        author: str,
    ) -> PullRequest:
        if source_branch == target_branch:
            raise ValueError("A pull request needs distinct source and target branches.")

        pull_request = PullRequest(
            number=self._next_number,
            source_branch=source_branch,
            target_branch=target_branch,
            title=title,
            author=author,
        )
        self.pull_requests[pull_request.number] = pull_request
        self._next_number += 1
        return pull_request


def demonstrate_repository_and_issues() -> tuple[Repository, IssueTracker, ProjectBoard]:
    print("\n=== Repository and Issue Workflow ===")

    repository = Repository(
        owner="example-org",
        name="release-platform",
        visibility="private",
    )
    repository.add_file(
        "README.md",
        "# Release Platform\nRepository governance demonstration.",
    )
    repository.add_file(
        ".github/workflows/ci.yml",
        "name: CI\non: [push, pull_request]",
    )
    repository.create_branch("feature/issue-automation")
    repository.repository_summary()

    issues = IssueTracker()
    issue = issues.create(
        title="Add deployment audit information",
        body="Track who initiated each environment deployment.",
        labels={"enhancement", "deployment"},
        assignees=["maya"],
    )
    issue.add_comment("maya", "The audit record should preserve actor and commit.")
    print(f"Created issue #{issue.number}: {issue.title}")
    print(f"Issue state: {issue.state.value}")
    print(f"Issue comments: {len(issue.comments)}")

    project = ProjectBoard("Release Platform Roadmap")
    project.add_item(
        ProjectItem(
            content_type="issue",
            content_id=str(issue.number),
            status="In Progress",
            priority="High",
            notes="Required before production rollout.",
        )
    )
    print(f"Project metrics: {project.metrics()}")

    return repository, issues, project


def demonstrate_pull_request_and_actions(
    repository: Repository,
    issue: Issue,
    project: ProjectBoard,
) -> PullRequest:
    print("\n=== Pull Request and Actions Workflow ===")

    prs = PullRequestTracker()
    pull_request = prs.create(
        source_branch="feature/issue-automation",
        target_branch="main",
        title="Add deployment audit information",
        author="maya",
    )

    pull_request.add_commit(
        "a81c93d4",
        {
            "audit.py": (
                "def record_deployment(actor, commit):\n"
                "    return {'actor': actor, 'commit': commit}\n"
            )
        },
    )
    pull_request.add_commit(
        "b42e7610",
        {"tests/test_audit.py": "assert True\n"},
    )
    pull_request.issue_links.append(issue.number)

    print(
        f"PR #{pull_request.number}: "
        f"{pull_request.source_branch} -> {pull_request.target_branch}"
    )
    print(f"Commits: {len(pull_request.commits)}")
    print(f"Changed files: {len(pull_request.changed_files)}")
    print(f"Linked issue: #{issue.number}")

    project.move("issue", str(issue.number), "Done")

    actions = ActionRunner()
    ci_run = actions.run_ci(
        repository,
        pull_request.source_branch,
        expected_files=["README.md"],
    )
    print(f"Actions CI status: {ci_run.status.value}")
    print("CI logs:")
    for line in ci_run.logs:
        print(f"  {line}")

    pull_request.synchronize(base_changed=True)
    return pull_request


def demonstrate_environments() -> None:
    print("\n=== Actions Environments and Deployment Controls ===")

    manager = EnvironmentManager()

    staging = Environment(
        name="staging",
        variables={"APP_MODE": "staging"},
        secrets={"DEPLOY_TOKEN": "not-printed"},
    )
    production = Environment(
        name="production",
        variables={"APP_MODE": "production"},
        secrets={"DEPLOY_TOKEN": "not-printed"},
        required_approvals=2,
    )

    manager.register(staging)
    manager.register(production)

    staging_deployment = manager.deploy(
        environment_name="staging",
        branch="main",
        commit="b42e7610",
        actor="maya",
    )
    print(f"Staging deployment: {staging_deployment.status.value}")

    production_attempt = manager.deploy(
        environment_name="production",
        branch="main",
        commit="b42e7610",
        actor="maya",
    )
    print(f"Production deployment: {production_attempt.status.value}")

    production.approve("release-manager")
    production.approve("security-reviewer")

    production_deployment = manager.deploy(
        environment_name="production",
        branch="main",
        commit="b42e7610",
        actor="maya",
    )
    print(f"Production deployment: {production_deployment.status.value}")
    print(
        "Production deployment history:",
        production.deployment_history,
    )


def demonstrate_persistence(repository: Repository) -> None:
    print("\n=== Safe Local State Export ===")

    state = {
        "repository": {
            "full_name": repository.full_name,
            "visibility": repository.visibility,
            "default_branch": repository.default_branch,
            "branches": sorted(repository.branches),
        },
        "files": sorted(repository.files),
    }

    with tempfile.TemporaryDirectory() as directory:
        output = Path(directory) / "repository-state.json"
        output.write_text(
            json.dumps(state, indent=2),
            encoding="utf-8",
        )
        loaded = json.loads(output.read_text(encoding="utf-8"))
        print(f"Exported state to temporary file: {output.name}")
        print(f"Reloaded repository: {loaded['repository']['full_name']}")


def demonstrate_edge_cases() -> None:
    print("\n=== Validation and Failure Cases ===")

    repository = Repository(owner="example-org", name="validation-demo")

    try:
        repository.create_branch("main")
    except ValueError as error:
        print(f"Expected branch validation error: {error}")

    try:
        repository.create_branch("feature with spaces")
    except ValueError as error:
        print(f"Expected branch-name error: {error}")

    prs = PullRequestTracker()
    try:
        prs.create("main", "main", "Invalid pull request", "maya")
    except ValueError as error:
        print(f"Expected PR validation error: {error}")

    actions = ActionRunner()
    failed_run = actions.run_ci(
        repository,
        "main",
        expected_files=["README.md", "LICENSE"],
    )
    print(f"Expected CI failure status: {failed_run.status.value}")

    environment = Environment(
        name="production",
        required_approvals=1,
    )
    deployment_manager = EnvironmentManager()
    deployment_manager.register(environment)

    pending = deployment_manager.deploy(
        "production",
        "main",
        "deadbeef",
        "maya",
    )
    print(f"Expected deployment gate state: {pending.status.value}")


def performance_notes() -> None:
    """
    The model uses dictionaries for repository objects, issues, PRs, and
    project items. Average lookup is approximately O(1) under normal hash-table
    behavior. Sorting branches for presentation costs O(B log B), where B is
    the number of branches.

    Real GitHub repositories also deal with much larger objects such as commit
    graphs, workflow runs, logs, artifacts, permissions, and API pagination.
    A local simulation therefore cannot reproduce GitHub's complete storage,
    authorization, or distributed execution behavior.
    """
    print("\n=== Design and Production Notes ===")
    print("Dictionary-backed IDs provide fast direct lookup in this simulation.")
    print("Workflow execution is modeled rather than running arbitrary commands.")
    print("Environment secrets are never printed.")
    print("Production systems require authentication, authorization, auditability,")
    print("rate limiting, secure secret storage, concurrency control, and logging.")


def main() -> None:
    repository, issues, project = demonstrate_repository_and_issues()
    issue = issues.get(1)
    demonstrate_pull_request_and_actions(repository, issue, project)
    demonstrate_environments()
    demonstrate_persistence(repository)
    demonstrate_edge_cases()
    performance_notes()

    print("\n=== Final Project State ===")
    print(f"Open issues: {len(issues.open_issues())}")
    print(f"Project metrics: {project.metrics()}")
    print(f"Repository files: {sorted(repository.files)}")
    time.sleep(0.05)


if __name__ == "__main__":
    main()
