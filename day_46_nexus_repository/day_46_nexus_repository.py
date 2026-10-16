#!/usr/bin/env python3
"""
Nexus Repository: Repository Types, Artifact Publishing and Retrieval

A self-contained repository-management simulation covering:
- Hosted, proxy, and group repositories.
- Maven, npm, PyPI, and Docker artifact coordinates.
- Artifact publishing, metadata validation, checksums, and immutable releases.
- Proxy caching, upstream retrieval, and group repository resolution.
- Authentication, repository permissions, and deployment policies.
- Pagination, deletion controls, retention, and audit events.
- Executable examples and automated assertions.

Uses only the Python standard library. The in-memory implementation is
an educational model, not a replacement for a production Nexus server.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Iterable, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class RepositoryError(Exception):
    """Base exception for repository operations."""


class ValidationError(RepositoryError):
    """Artifact coordinates or content are invalid."""


class AuthorizationError(RepositoryError):
    """The principal lacks permission for an operation."""


class ArtifactNotFoundError(RepositoryError):
    """An artifact cannot be resolved."""


class DuplicateArtifactError(RepositoryError):
    """An immutable artifact coordinate already exists."""


class UpstreamError(RepositoryError):
    """An upstream repository request failed."""


class RepositoryType(str, Enum):
    HOSTED = "hosted"
    PROXY = "proxy"
    GROUP = "group"


class Format(str, Enum):
    RAW = "raw"
    MAVEN = "maven2"
    NPM = "npm"
    PYPI = "pypi"
    DOCKER = "docker"


class Permission(str, Enum):
    READ = "read"
    PUBLISH = "publish"
    DELETE = "delete"
    ADMIN = "admin"


@dataclass(frozen=True)
class Principal:
    username: str
    permissions: dict[str, frozenset[Permission]]

    def can(self, repository: str, permission: Permission) -> bool:
        granted = self.permissions.get(repository, frozenset())
        wildcard = self.permissions.get("*", frozenset())
        return (
            permission in granted
            or Permission.ADMIN in granted
            or permission in wildcard
            or Permission.ADMIN in wildcard
        )


@dataclass(frozen=True)
class ArtifactCoordinate:
    """
    Canonical identity for a repository artifact.

    Maven paths follow group/artifact/version conventions.
    npm and PyPI use package/version coordinates.
    Docker uses image/tag coordinates.
    Raw artifacts use explicit paths.
    """

    format: Format
    name: str
    version: str
    classifier: str = ""
    extension: str = ""
    path: str = ""

    def validate(self) -> None:
        if not self.name or not self.version:
            raise ValidationError("Artifact name and version are required.")

        if any(ord(ch) < 32 for ch in self.name + self.version):
            raise ValidationError("Control characters are not allowed.")

        if any(part in {".", ".."} for part in self.name.split("/")):
            raise ValidationError("Unsafe artifact name.")

        if "/" in self.version or "\\" in self.version:
            raise ValidationError("Version cannot contain path separators.")

        if self.format == Format.MAVEN:
            parts = self.name.split(":")
            if len(parts) != 2 or not all(parts):
                raise ValidationError(
                    "Maven name must use groupId:artifactId."
                )
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", parts[0]):
                raise ValidationError("Invalid Maven group identifier.")
            if not re.fullmatch(r"[A-Za-z0-9_.-]+", parts[1]):
                raise ValidationError("Invalid Maven artifact identifier.")
            if not self.extension or "/" in self.extension:
                raise ValidationError("Maven extension is required.")
        elif self.format == Format.NPM:
            if not re.fullmatch(
                r"(?:@[a-z0-9._-]+/)?[a-z0-9._~-]+",
                self.name,
            ):
                raise ValidationError("Invalid npm package name.")
        elif self.format == Format.PYPI:
            if not re.fullmatch(r"[A-Za-z0-9._-]+", self.name):
                raise ValidationError("Invalid PyPI package name.")
        elif self.format == Format.DOCKER:
            if not re.fullmatch(
                r"[a-z0-9]+(?:[._/-][a-z0-9]+)*",
                self.name,
            ):
                raise ValidationError("Invalid Docker image name.")
        elif self.format == Format.RAW:
            normalized = self.path.replace("\\", "/")
            if not normalized or normalized.startswith("/"):
                raise ValidationError("Raw path must be relative.")
            if any(part in {"", ".", ".."} for part in normalized.split("/")):
                raise ValidationError("Unsafe raw artifact path.")

    def storage_key(self) -> str:
        self.validate()

        if self.format == Format.MAVEN:
            group, artifact = self.name.split(":")
            filename = f"{artifact}-{self.version}"
            if self.classifier:
                filename += f"-{self.classifier}"
            filename += f".{self.extension}"
            return (
                f"{group.replace('.', '/')}/{artifact}/"
                f"{self.version}/{filename}"
            )

        if self.format == Format.NPM:
            package = self.name.replace("/", "%2f")
            return f"{package}/-/{package.split('%2f')[-1]}-{self.version}.tgz"

        if self.format == Format.PYPI:
            normalized = re.sub(r"[-_.]+", "-", self.name).lower()
            return f"{normalized}/{self.version}/{self.path or self.name}"

        if self.format == Format.DOCKER:
            return f"{self.name}/manifests/{self.version}"

        return self.path.replace("\\", "/")


@dataclass(frozen=True)
class Artifact:
    coordinate: ArtifactCoordinate
    content: bytes
    sha256: str
    published_by: str
    published_at: float
    properties: dict[str, str] = field(default_factory=dict)

    @staticmethod
    def create(
        coordinate: ArtifactCoordinate,
        content: bytes,
        username: str,
        properties: Optional[dict[str, str]] = None,
    ) -> "Artifact":
        coordinate.validate()

        if not isinstance(content, bytes) or not content:
            raise ValidationError("Artifact content must be non-empty bytes.")

        return Artifact(
            coordinate=coordinate,
            content=content,
            sha256=hashlib.sha256(content).hexdigest(),
            published_by=username,
            published_at=time.time(),
            properties=dict(properties or {}),
        )


@dataclass
class Repository:
    name: str
    repository_type: RepositoryType
    format: Format
    members: list[str] = field(default_factory=list)
    upstream: Optional[str] = None
    allow_redeploy: bool = False
    artifacts: dict[str, Artifact] = field(default_factory=dict)
    cache_hits: int = 0
    cache_misses: int = 0

    def __post_init__(self) -> None:
        if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9._-]*", self.name):
            raise ValidationError("Invalid repository name.")

        if self.repository_type == RepositoryType.GROUP:
            if not self.members:
                raise ValidationError("A group requires member repositories.")
            if self.upstream:
                raise ValidationError("A group cannot have an upstream URL.")

        if self.repository_type == RepositoryType.PROXY and not self.upstream:
            raise ValidationError("A proxy repository requires an upstream URL.")

        if self.repository_type != RepositoryType.HOSTED and self.allow_redeploy:
            raise ValidationError(
                "Redeployment policy applies only to hosted repositories."
            )


class NexusModel:
    def __init__(self) -> None:
        self.repositories: dict[str, Repository] = {}
        self.audit_log: list[dict[str, object]] = {}

    def add_repository(self, repository: Repository) -> None:
        if repository.name in self.repositories:
            raise ValidationError(f"Repository already exists: {repository.name}")

        for member in repository.members:
            if member not in self.repositories:
                raise ValidationError(f"Unknown group member: {member}")

        self.repositories[repository.name] = repository
        self.audit_log.append({
            "action": "repository_created",
            "repository": repository.name,
            "time": time.time(),
        })

    def _repository(self, name: str) -> Repository:
        try:
            return self.repositories[name]
        except KeyError as exc:
            raise RepositoryError(f"Unknown repository: {name}") from exc

    def _authorize(
        self,
        principal: Principal,
        repository: str,
        permission: Permission,
    ) -> None:
        if not principal.can(repository, permission):
            raise AuthorizationError(
                f"{principal.username} lacks {permission.value} "
                f"permission on {repository}."
            )

    def publish(
        self,
        repository_name: str,
        coordinate: ArtifactCoordinate,
        content: bytes,
        principal: Principal,
        properties: Optional[dict[str, str]] = None,
    ) -> Artifact:
        repository = self._repository(repository_name)

        self._authorize(principal, repository_name, Permission.PUBLISH)

        if repository.repository_type != RepositoryType.HOSTED:
            raise RepositoryError("Publishing is allowed only to hosted repositories.")

        if coordinate.format != repository.format:
            raise ValidationError("Artifact format does not match repository format.")

        artifact = Artifact.create(
            coordinate, content, principal.username, properties
        )
        key = coordinate.storage_key()

        existing = repository.artifacts.get(key)
        if existing and not repository.allow_redeploy:
            raise DuplicateArtifactError(
                f"Immutable release already exists at {repository_name}/{key}."
            )

        repository.artifacts[key] = artifact
        self.audit_log.append({
            "action": "artifact_published",
            "repository": repository_name,
            "key": key,
            "sha256": artifact.sha256,
            "user": principal.username,
            "time": artifact.published_at,
        })
        return artifact

    def retrieve(
        self,
        repository_name: str,
        coordinate: ArtifactCoordinate,
        principal: Principal,
    ) -> Artifact:
        self._authorize(principal, repository_name, Permission.READ)
        return self._resolve(repository_name, coordinate, set())

    def _resolve(
        self,
        repository_name: str,
        coordinate: ArtifactCoordinate,
        visited: set[str],
    ) -> Artifact:
        if repository_name in visited:
            raise RepositoryError("Repository group or proxy resolution cycle detected.")

        visited.add(repository_name)
        repository = self._repository(repository_name)

        if coordinate.format != repository.format:
            raise ValidationError("Artifact format does not match repository format.")

        key = coordinate.storage_key()
        cached = repository.artifacts.get(key)
        if cached:
            repository.cache_hits += 1
            return cached

        repository.cache_misses += 1

        if repository.repository_type == RepositoryType.HOSTED:
            raise ArtifactNotFoundError(f"Artifact not found: {repository_name}/{key}")

        if repository.repository_type == RepositoryType.GROUP:
            errors: list[str] = []
            for member in repository.members:
                try:
                    return self._resolve(member, coordinate, visited.copy())
                except ArtifactNotFoundError as exc:
                    errors.append(str(exc))
                except UpstreamError as exc:
                    errors.append(str(exc))

            raise ArtifactNotFoundError(
                f"Artifact unavailable in group {repository_name}: "
                + "; ".join(errors)
            )

        assert repository.upstream is not None
        artifact = self._fetch_upstream(repository, coordinate, key)
        repository.artifacts[key] = artifact
        return artifact

    def _fetch_upstream(
        self,
        repository: Repository,
        coordinate: ArtifactCoordinate,
        key: str,
    ) -> Artifact:
        """
        A concrete HTTP retrieval implementation.

        The URL is built only from a configured HTTPS upstream and a validated
        relative artifact key. Real deployments should use a repository-format
        client for metadata, authentication, redirects, and checksum files.
        """
        base = repository.upstream
        assert base is not None

        if not base.startswith("https://"):
            raise UpstreamError("Upstream URL must use HTTPS.")

        if "@" in base.split("://", 1)[1].split("/", 1)[0]:
            raise UpstreamError("Credentials must not appear in upstream URLs.")

        from urllib.parse import quote, urlsplit

        parsed = urlsplit(base)
        if not parsed.hostname or parsed.username or parsed.password:
            raise UpstreamError("Invalid upstream URL.")

        safe_key = "/".join(quote(part, safe="") for part in key.split("/"))
        url = base.rstrip("/") + "/" + safe_key
        request = Request(url, headers={"User-Agent": "NexusLearningClient/1.0"})

        try:
            with urlopen(request, timeout=10) as response:
                if response.status != 200:
                    raise UpstreamError(f"Upstream returned HTTP {response.status}.")
                content = response.read(20 * 1024 * 1024 + 1)
                if len(content) > 20 * 1024 * 1024:
                    raise UpstreamError("Artifact exceeds the 20 MiB demo limit.")
        except HTTPError as exc:
            if exc.code == 404:
                raise ArtifactNotFoundError(f"Upstream artifact not found: {key}") from exc
            raise UpstreamError(f"Upstream HTTP failure: {exc.code}") from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise UpstreamError(f"Upstream request failed: {exc}") from exc

        if not content:
            raise UpstreamError("Upstream returned an empty artifact.")

        return Artifact.create(
            coordinate,
            content,
            username=f"upstream:{repository.name}",
            properties={"source": "upstream", "url": url},
        )

    def delete(
        self,
        repository_name: str,
        coordinate: ArtifactCoordinate,
        principal: Principal,
    ) -> None:
        repository = self._repository(repository_name)
        self._authorize(principal, repository_name, Permission.DELETE)

        if repository.repository_type != RepositoryType.HOSTED:
            raise RepositoryError("Deletion is allowed only on hosted repositories.")

        key = coordinate.storage_key()
        if key not in repository.artifacts:
            raise ArtifactNotFoundError(key)

        artifact = repository.artifacts.pop(key)
        self.audit_log.append({
            "action": "artifact_deleted",
            "repository": repository_name,
            "key": key,
            "sha256": artifact.sha256,
            "user": principal.username,
            "time": time.time(),
        })

    def list_artifacts(
        self,
        repository_name: str,
        principal: Principal,
        prefix: str = "",
        offset: int = 0,
        limit: int = 50,
    ) -> list[dict[str, object]]:
        self._authorize(principal, repository_name, Permission.READ)

        if offset < 0 or not 1 <= limit <= 200:
            raise ValidationError("Offset must be non-negative and limit must be 1..200.")

        repository = self._repository(repository_name)
        matching = sorted(
            (key, artifact)
            for key, artifact in repository.artifacts.items()
            if key.startswith(prefix)
        )
        return [
            {
                "path": key,
                "format": artifact.coordinate.format.value,
                "sha256": artifact.sha256,
                "size": len(artifact.content),
                "published_by": artifact.published_by,
            }
            for key, artifact in matching[offset:offset + limit]
        ]

    def verify_checksum(self, artifact: Artifact) -> bool:
        return hashlib.sha256(artifact.content).hexdigest() == artifact.sha256

    def audit_json(self) -> str:
        return json.dumps(self.audit_log, indent=2, sort_keys=True)


def build_demo() -> tuple[NexusModel, Principal, Principal]:
    nexus = NexusModel()

    nexus.add_repository(Repository(
        name="maven-releases",
        repository_type=RepositoryType.HOSTED,
        format=Format.MAVEN,
    ))
    nexus.add_repository(Repository(
        name="maven-central-cache",
        repository_type=RepositoryType.PROXY,
        format=Format.MAVEN,
        upstream="https://repo1.maven.org/maven2",
    ))
    nexus.add_repository(Repository(
        name="maven-public",
        repository_type=RepositoryType.GROUP,
        format=Format.MAVEN,
        members=["maven-releases", "maven-central-cache"],
    ))
    nexus.add_repository(Repository(
        name="npm-internal",
        repository_type=RepositoryType.HOSTED,
        format=Format.NPM,
    ))
    nexus.add_repository(Repository(
        name="pypi-internal",
        repository_type=RepositoryType.HOSTED,
        format=Format.PYPI,
    ))
    nexus.add_repository(Repository(
        name="docker-internal",
        repository_type=RepositoryType.HOSTED,
        format=Format.DOCKER,
    ))

    developer = Principal(
        username="release-engineer",
        permissions={
            "maven-releases": frozenset({Permission.READ, Permission.PUBLISH}),
            "npm-internal": frozenset({Permission.READ, Permission.PUBLISH}),
            "pypi-internal": frozenset({Permission.READ, Permission.PUBLISH}),
            "docker-internal": frozenset({Permission.READ, Permission.PUBLISH}),
            "maven-public": frozenset({Permission.READ}),
            "maven-central-cache": frozenset({Permission.READ}),
        },
    )

    consumer = Principal(
        username="build-agent",
        permissions={
            "maven-public": frozenset({Permission.READ}),
            "maven-releases": frozenset({Permission.READ}),
            "maven-central-cache": frozenset({Permission.READ}),
            "npm-internal": frozenset({Permission.READ}),
            "pypi-internal": frozenset({Permission.READ}),
            "docker-internal": frozenset({Permission.READ}),
        },
    )
    return nexus, developer, consumer


def run_tests() -> None:
    nexus, developer, consumer = build_demo()

    release = ArtifactCoordinate(
        format=Format.MAVEN,
        name="com.example.payment:payment-client",
        version="2.4.0",
        extension="jar",
    )
    published = nexus.publish(
        "maven-releases",
        release,
        b"payment-client-2.4.0 binary content",
        developer,
        {"team": "payments", "release": "stable"},
    )
    assert nexus.verify_checksum(published)

    retrieved = nexus.retrieve("maven-public", release, consumer)
    assert retrieved.sha256 == published.sha256
    assert retrieved.content == published.content

    try:
        nexus.publish(
            "maven-releases",
            release,
            b"different binary",
            developer,
        )
    except DuplicateArtifactError:
        pass
    else:
        raise AssertionError("Immutable release redeployment must fail.")

    try:
        nexus.publish(
            "maven-public",
            release,
            b"unauthorized target",
            developer,
        )
    except RepositoryError:
        pass
    else:
        raise AssertionError("A group must reject publishing.")

    try:
        nexus.retrieve("maven-releases", release, consumer)
    except ArtifactNotFoundError:
        raise AssertionError("Published artifact should be retrievable.")

    try:
        nexus.retrieve(
            "maven-releases",
            ArtifactCoordinate(
                format=Format.MAVEN,
                name="com.example.missing:missing-library",
                version="9.9.9",
                extension="jar",
            ),
            consumer,
        )
    except ArtifactNotFoundError:
        pass
    else:
        raise AssertionError("Missing artifacts must raise an error.")

    npm_coordinate = ArtifactCoordinate(
        format=Format.NPM,
        name="@example/payment-sdk",
        version="1.3.0",
    )
    nexus.publish(
        "npm-internal",
        npm_coordinate,
        b"npm package archive",
        developer,
    )
    assert nexus.retrieve("npm-internal", npm_coordinate, consumer).content

    pypi_coordinate = ArtifactCoordinate(
        format=Format.PYPI,
        name="payment_utils",
        version="0.8.2",
        path="payment_utils-0.8.2-py3-none-any.whl",
    )
    nexus.publish(
        "pypi-internal",
        pypi_coordinate,
        b"wheel archive",
        developer,
    )
    assert nexus.retrieve("pypi-internal", pypi_coordinate, consumer).content

    docker_coordinate = ArtifactCoordinate(
        format=Format.DOCKER,
        name="payments/api",
        version="2.4.0",
    )
    nexus.publish(
        "docker-internal",
        docker_coordinate,
        b"container manifest",
        developer,
    )
    assert nexus.retrieve("docker-internal", docker_coordinate, consumer).content

    try:
        nexus.retrieve("npm-internal", npm_coordinate, Principal("guest", {}))
    except AuthorizationError:
        pass
    else:
        raise AssertionError("Unauthorized access must fail.")

    print("Repository artifact inventory:")
    print(json.dumps(
        nexus.list_artifacts("maven-releases", consumer),
        indent=2,
    ))
    print("\nAudit event count:", len(nexus.audit_log))
    print("Checksum verification:", nexus.verify_checksum(published))
    print("All offline tests passed.")


if __name__ == "__main__":
    run_tests()
