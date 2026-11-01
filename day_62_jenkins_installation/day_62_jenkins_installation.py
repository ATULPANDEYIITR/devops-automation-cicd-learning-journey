#!/usr/bin/env python3

"""
Jenkins installation, configuration, and plugin governance simulator.

This self-contained program models:
- Jenkins installation prerequisites
- Controller configuration
- Plugin installation and dependency validation
- Plugin compatibility and security policy checks
- Job configuration
- Credential references without storing secrets
- Build execution
- Failure handling and diagnostics
- Configuration export

The program does not install software on the host. It provides an executable
model of the decisions and validation normally performed during Jenkins setup.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from enum import Enum
import json
import platform
import re
import sys
from typing import Iterable


class InstallationStatus(Enum):
    NOT_STARTED = "not_started"
    VALIDATED = "validated"
    INSTALLED = "installed"
    FAILED = "failed"


class PluginStatus(Enum):
    AVAILABLE = "available"
    INSTALLED = "installed"
    FAILED = "failed"


class BuildStatus(Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


class JenkinsError(Exception):
    """Base exception for Jenkins configuration failures."""


class ValidationError(JenkinsError):
    """Raised when an installation or configuration rule fails."""


class PluginError(JenkinsError):
    """Raised when plugin dependency or compatibility validation fails."""


class BuildError(JenkinsError):
    """Raised when a build cannot execute."""


@dataclass(frozen=True)
class Plugin:
    name: str
    version: str
    required_java: int
    dependencies: tuple[str, ...] = ()
    security_level: str = "approved"


@dataclass
class PluginRecord:
    plugin: Plugin
    status: PluginStatus = PluginStatus.AVAILABLE
    reason: str = ""


@dataclass
class JenkinsConfig:
    controller_name: str
    jenkins_version: str
    java_major: int
    http_port: int = 8080
    executors: int = 2
    csrf_protection: bool = True
    anonymous_read: bool = False
    allow_signup: bool = False
    url: str = "http://localhost:8080/"


@dataclass
class CredentialReference:
    credential_id: str
    kind: str
    owner: str
    secret_value: str = field(repr=False, default="")

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9._-]{3,64}", self.credential_id):
            raise ValidationError("Invalid credential identifier.")
        if not self.secret_value:
            raise ValidationError("Credential secret cannot be empty.")

    def safe_view(self) -> dict:
        return {
            "credential_id": self.credential_id,
            "kind": self.kind,
            "owner": self.owner,
            "secret_value": "***REDACTED***",
        }


@dataclass
class JenkinsJob:
    name: str
    repository: str
    branch: str
    credential_id: str | None = None
    required_plugins: set[str] = field(default_factory=set)
    status: BuildStatus = BuildStatus.QUEUED

    def validate(self) -> None:
        if not re.fullmatch(r"[A-Za-z0-9._/-]{1,120}", self.name):
            raise ValidationError(f"Invalid job name: {self.name}")
        if not self.repository.startswith(("https://", "ssh://", "git@")):
            raise ValidationError(f"Unsupported repository URL: {self.repository}")
        if not self.branch:
            raise ValidationError("Branch cannot be empty.")


@dataclass
class BuildResult:
    job_name: str
    build_number: int
    status: BuildStatus
    stages: list[dict]
    diagnostics: list[str]


class JenkinsInstallation:
    """Models a controlled Jenkins installation and configuration workflow."""

    MIN_JAVA = 17
    MIN_EXECUTORS = 1
    MAX_EXECUTORS = 32

    def __init__(self) -> None:
        self.status = InstallationStatus.NOT_STARTED
        self.config: JenkinsConfig | None = None
        self.plugins: dict[str, PluginRecord] = {}
        self.credentials: dict[str, CredentialReference] = {}
        self.jobs: dict[str, JenkinsJob] = {}
        self.build_counter: dict[str, int] = {}
        self.audit_log: list[str] = []

    def log(self, message: str) -> None:
        self.audit_log.append(message)

    def validate_prerequisites(
        self,
        java_major: int,
        http_port: int,
        executors: int,
    ) -> None:
        if java_major < self.MIN_JAVA:
            raise ValidationError(
                f"Jenkins controller requires Java {self.MIN_JAVA}+ "
                f"for this model; received Java {java_major}."
            )

        if not 1024 <= http_port <= 65535:
            raise ValidationError("HTTP port must be between 1024 and 65535.")

        if not self.MIN_EXECUTORS <= executors <= self.MAX_EXECUTORS:
            raise ValidationError(
                f"Executors must be between {self.MIN_EXECUTORS} "
                f"and {self.MAX_EXECUTORS}."
            )

        self.status = InstallationStatus.VALIDATED
        self.log("Prerequisites validated.")

    def install(self, config: JenkinsConfig) -> None:
        if self.status != InstallationStatus.VALIDATED:
            raise JenkinsError("Prerequisites must be validated first.")

        self.validate_prerequisites(
            config.java_major,
            config.http_port,
            config.executors,
        )

        if not config.csrf_protection:
            raise ValidationError("CSRF protection must remain enabled.")

        if config.allow_signup:
            raise ValidationError(
                "Open user signup is disabled by the security baseline."
            )

        if config.anonymous_read:
            raise ValidationError(
                "Anonymous read access is disabled by the security baseline."
            )

        if not config.url.endswith("/"):
            raise ValidationError("Jenkins URL must end with '/'.")

        self.config = config
        self.status = InstallationStatus.INSTALLED
        self.log(f"Installed controller {config.controller_name}.")

    def register_plugins(self, plugins: Iterable[Plugin]) -> None:
        for plugin in plugins:
            if plugin.name in self.plugins:
                raise PluginError(f"Duplicate plugin: {plugin.name}")
            self.plugins[plugin.name] = PluginRecord(plugin=plugin)

    def install_plugins(self, requested: Iterable[str]) -> None:
        if self.status != InstallationStatus.INSTALLED:
            raise PluginError("Jenkins must be installed before plugins.")

        requested_set = set(requested)

        missing = requested_set - self.plugins.keys()
        if missing:
            raise PluginError(
                f"Plugins are not present in the catalog: {sorted(missing)}"
            )

        visiting: set[str] = set()
        installed: set[str] = set()

        def install_one(name: str) -> None:
            if name in installed:
                return

            if name in visiting:
                raise PluginError(f"Circular plugin dependency detected: {name}")

            visiting.add(name)
            record = self.plugins[name]
            plugin = record.plugin

            if plugin.required_java > self.config.java_major:
                raise PluginError(
                    f"{name} requires Java {plugin.required_java}, "
                    f"controller has Java {self.config.java_major}."
                )

            if plugin.security_level != "approved":
                raise PluginError(
                    f"Plugin {name} is not approved by the security baseline."
                )

            for dependency in plugin.dependencies:
                if dependency not in self.plugins:
                    raise PluginError(
                        f"Missing dependency {dependency} for {name}."
                    )
                install_one(dependency)

            visiting.remove(name)
            installed.add(name)
            record.status = PluginStatus.INSTALLED
            record.reason = "Dependency validation passed."
            self.log(f"Installed plugin {name} {plugin.version}.")

        for plugin_name in requested_set:
            install_one(plugin_name)

    def add_credential(self, credential: CredentialReference) -> None:
        if credential.credential_id in self.credentials:
            raise ValidationError(
                f"Credential already exists: {credential.credential_id}"
            )

        # Only a reference is used by jobs. The secret is never written to
        # the audit log or configuration export.
        self.credentials[credential.credential_id] = credential
        self.log(f"Registered credential reference {credential.credential_id}.")

    def add_job(self, job: JenkinsJob) -> None:
        job.validate()

        if job.name in self.jobs:
            raise ValidationError(f"Job already exists: {job.name}")

        not_installed = {
            plugin
            for plugin in job.required_plugins
            if plugin not in self.plugins
            or self.plugins[plugin].status != PluginStatus.INSTALLED
        }

        if not_installed:
            raise ValidationError(
                f"Job requires unavailable plugins: {sorted(not_installed)}"
            )

        if job.credential_id and job.credential_id not in self.credentials:
            raise ValidationError(
                f"Unknown credential reference: {job.credential_id}"
            )

        self.jobs[job.name] = job
        self.build_counter[job.name] = 0
        self.log(f"Created job {job.name}.")

    def run_build(self, job_name: str, test_passes: bool = True) -> BuildResult:
        if job_name not in self.jobs:
            raise BuildError(f"Unknown job: {job_name}")

        job = self.jobs[job_name]
        self.build_counter[job_name] += 1
        number = self.build_counter[job_name]

        stages: list[dict] = []
        diagnostics: list[str] = []

        job.status = BuildStatus.RUNNING

        stages.append({"name": "Checkout", "status": "SUCCESS"})
        stages.append({"name": "Dependency Validation", "status": "SUCCESS"})

        if test_passes:
            stages.append({"name": "Test", "status": "SUCCESS"})
            stages.append({"name": "Package", "status": "SUCCESS"})
            job.status = BuildStatus.SUCCESS
            diagnostics.append("Build completed successfully.")
        else:
            stages.append({"name": "Test", "status": "FAILED"})
            job.status = BuildStatus.FAILED
            diagnostics.append(
                "Tests failed; deployment stages were not executed."
            )

        self.log(
            f"Build {job.name}#{number} completed with {job.status.value}."
        )

        return BuildResult(
            job_name=job.name,
            build_number=number,
            status=job.status,
            stages=stages,
            diagnostics=diagnostics,
        )

    def export_safe_configuration(self) -> str:
        if self.config is None:
            raise JenkinsError("Jenkins has not been installed.")

        data = {
            "controller": asdict(self.config),
            "plugins": [
                {
                    "name": record.plugin.name,
                    "version": record.plugin.version,
                    "status": record.status.value,
                    "reason": record.reason,
                }
                for record in self.plugins.values()
            ],
            "credentials": [
                credential.safe_view()
                for credential in self.credentials.values()
            ],
            "jobs": [
                {
                    "name": job.name,
                    "repository": job.repository,
                    "branch": job.branch,
                    "credential_id": job.credential_id,
                    "required_plugins": sorted(job.required_plugins),
                }
                for job in self.jobs.values()
            ],
        }

        return json.dumps(data, indent=2)

    def health_report(self) -> dict:
        installed_plugins = sum(
            record.status == PluginStatus.INSTALLED
            for record in self.plugins.values()
        )

        return {
            "installation_status": self.status.value,
            "controller": (
                self.config.controller_name if self.config else None
            ),
            "plugin_count": installed_plugins,
            "job_count": len(self.jobs),
            "credential_reference_count": len(self.credentials),
            "host_platform": platform.system(),
            "python_version": sys.version.split()[0],
        }


def create_demo_environment() -> JenkinsInstallation:
    jenkins = JenkinsInstallation()

    config = JenkinsConfig(
        controller_name="ci-controller-prod",
        jenkins_version="2.5xx",
        java_major=21,
        http_port=8080,
        executors=4,
        csrf_protection=True,
        anonymous_read=False,
        allow_signup=False,
        url="http://localhost:8080/",
    )

    jenkins.validate_prerequisites(
        config.java_major,
        config.http_port,
        config.executors,
    )
    jenkins.install(config)

    plugins = [
        Plugin(
            name="git",
            version="5.6.0",
            required_java=17,
        ),
        Plugin(
            name="credentials",
            version="1400.v1897",
            required_java=17,
        ),
        Plugin(
            name="workflow-api",
            version="1400.v7fd",
            required_java=17,
        ),
        Plugin(
            name="workflow-job",
            version="1500.v1",
            required_java=17,
            dependencies=("workflow-api",),
        ),
        Plugin(
            name="pipeline-model-definition",
            version="2.22",
            required_java=17,
            dependencies=("workflow-job", "credentials"),
        ),
    ]

    jenkins.register_plugins(plugins)

    jenkins.install_plugins(
        [
            "git",
            "credentials",
            "pipeline-model-definition",
        ]
    )

    jenkins.add_credential(
        CredentialReference(
            credential_id="git-readonly",
            kind="username-password",
            owner="ci-service",
            secret_value="example-secret-never-exported",
        )
    )

    jenkins.add_job(
        JenkinsJob(
            name="orders-service-main",
            repository="https://git.example.internal/orders-service.git",
            branch="main",
            credential_id="git-readonly",
            required_plugins={
                "git",
                "credentials",
                "pipeline-model-definition",
            },
        )
    )

    return jenkins


def run_validation_tests() -> None:
    jenkins = create_demo_environment()

    successful = jenkins.run_build("orders-service-main", test_passes=True)
    assert successful.status == BuildStatus.SUCCESS
    assert successful.build_number == 1

    failed = jenkins.run_build("orders-service-main", test_passes=False)
    assert failed.status == BuildStatus.FAILED
    assert failed.build_number == 2

    exported = jenkins.export_safe_configuration()
    assert "example-secret-never-exported" not in exported
    assert "***REDACTED***" in exported

    try:
        jenkins.validate_prerequisites(java_major=11, http_port=8080, executors=2)
    except ValidationError:
        pass
    else:
        raise AssertionError("Unsupported Java version was accepted.")

    try:
        jenkins.add_job(
            JenkinsJob(
                name="bad-repository",
                repository="ftp://invalid.example/repo",
                branch="main",
            )
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Invalid repository URL was accepted.")

    print("Validation tests: PASS")
    print(json.dumps(jenkins.health_report(), indent=2))
    print("\nSafe configuration export:")
    print(exported)
    print("\nAudit events:")
    for event in jenkins.audit_log:
        print(f"- {event}")


if __name__ == "__main__":
    run_validation_tests()
