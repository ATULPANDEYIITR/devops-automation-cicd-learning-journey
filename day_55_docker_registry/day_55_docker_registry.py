#!/usr/bin/env python3
"""Simulate a secure Docker Registry workflow using only the Python standard library."""

from __future__ import annotations

import hashlib
import json
import re
import secrets
import unittest
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Iterable


class RegistryError(Exception):
    """Base exception for registry workflow failures."""


class ValidationError(RegistryError):
    """Invalid repository, tag, digest, or configuration."""


class AuthenticationError(RegistryError):
    """Missing or invalid registry credentials."""


class AuthorizationError(RegistryError):
    """The authenticated principal lacks the required permission."""


class ConflictError(RegistryError):
    """A publication conflicts with an existing immutable release."""


class Role(str, Enum):
    READER = "reader"
    PUBLISHER = "publisher"
    ADMIN = "admin"


class ImageState(str, Enum):
    BUILT = "built"
    PUBLISHED = "published"
    RETIRED = "retired"


class CheckState(str, Enum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Principal:
    username: str
    role: Role
    token: str = field(repr=False)


@dataclass
class ImageArtifact:
    repository: str
    tag: str
    digest: str
    size_bytes: int
    platform: str
    state: ImageState = ImageState.BUILT
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    @property
    def reference(self) -> str:
        return f"{self.repository}:{self.tag}"

    def to_dict(self) -> dict:
        result = asdict(self)
        result["state"] = self.state.value
        result["reference"] = self.reference
        return result


@dataclass(frozen=True)
class PublishPolicy:
    allowed_registries: frozenset[str]
    require_scan_pass: bool = True
    require_signature: bool = True
    maximum_size_bytes: int = 500_000_000
    immutable_release_tags: bool = True


@dataclass
class Registry:
    name: str
    private: bool
    principals: dict[str, Principal] = field(default_factory=dict)
    artifacts: dict[str, ImageArtifact] = field(default_factory=dict)
    audit_log: list[dict] = field(default_factory=list)

    def authenticate(self, username: str, token: str) -> Principal:
        principal = self.principals.get(username)
        if principal is None or not secrets.compare_digest(
            principal.token, token
        ):
            self._audit("authentication_failed", username, "")
            raise AuthenticationError("Invalid registry credentials.")
        self._audit("authenticated", username, "")
        return principal

    def _audit(self, action: str, actor: str, reference: str) -> None:
        self.audit_log.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "action": action,
            "actor": actor,
            "reference": reference,
        })

    def push(
        self,
        principal: Principal,
        artifact: ImageArtifact,
        policy: PublishPolicy,
        scan: CheckState,
        signature_verified: bool,
    ) -> ImageArtifact:
        if principal.role not in (Role.PUBLISHER, Role.ADMIN):
            raise AuthorizationError("Push requires publisher or admin access.")

        if self.name not in policy.allowed_registries:
            raise AuthorizationError("Registry is not allowed by policy.")

        validate_repository(artifact.repository)
        validate_tag(artifact.tag)

        if artifact.size_bytes <= 0:
            raise ValidationError("Image size must be positive.")
        if artifact.size_bytes > policy.maximum_size_bytes:
            raise ValidationError("Image exceeds the configured size limit.")
        if not re.fullmatch(r"sha256:[0-9a-f]{64}", artifact.digest):
            raise ValidationError("Invalid SHA-256 image digest.")
        if policy.require_scan_pass and scan != CheckState.PASS:
            raise RegistryError("Image vulnerability scan has not passed.")
        if policy.require_signature and not signature_verified:
            raise RegistryError("Image signature verification failed.")

        existing = self.artifacts.get(artifact.reference)
        if existing is not None:
            if existing.digest == artifact.digest:
                self._audit("push_idempotent", principal.username,
                            artifact.reference)
                return existing
            if policy.immutable_release_tags and is_release_tag(artifact.tag):
                raise ConflictError("Release tags cannot be overwritten.")

        artifact.state = ImageState.PUBLISHED
        self.artifacts[artifact.reference] = artifact
        self._audit("push", principal.username, artifact.reference)
        return artifact

    def pull(
        self,
        principal: Principal | None,
        reference: str,
    ) -> ImageArtifact:
        if self.private:
            if principal is None:
                raise AuthenticationError("Private registry login required.")
            if principal.role not in (Role.READER, Role.PUBLISHER, Role.ADMIN):
                raise AuthorizationError("Pull permission denied.")

        artifact = self.artifacts.get(reference)
        if artifact is None or artifact.state != ImageState.PUBLISHED:
            raise RegistryError("Image reference not found.")
        actor = principal.username if principal else "anonymous"
        self._audit("pull", actor, reference)
        return artifact


def validate_repository(repository: str) -> None:
    """Validate a simplified lowercase Docker repository path."""
    if not repository or repository != repository.lower():
        raise ValidationError("Repository names must be lowercase.")
    if len(repository) > 255:
        raise ValidationError("Repository name is too long.")
    components = repository.split("/")
    component_pattern = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*")
    if not all(component_pattern.fullmatch(part) for part in components):
        raise ValidationError("Invalid repository path.")


def validate_tag(tag: str) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}", tag):
        raise ValidationError("Invalid image tag.")


def is_release_tag(tag: str) -> bool:
    return bool(re.fullmatch(r"v\d+\.\d+\.\d+", tag))


def build_artifact(
    repository: str,
    tag: str,
    content: bytes,
    platform: str = "linux/amd64",
) -> ImageArtifact:
    validate_repository(repository)
    validate_tag(tag)
    if not content:
        raise ValidationError("Image manifest content cannot be empty.")
    if platform not in {"linux/amd64", "linux/arm64", "linux/arm/v7"}:
        raise ValidationError("Unsupported demonstration platform.")
    digest = "sha256:" + hashlib.sha256(content).hexdigest()
    return ImageArtifact(
        repository=repository,
        tag=tag,
        digest=digest,
        size_bytes=len(content),
        platform=platform,
    )


def report(registry: Registry) -> dict:
    published = [
        item for item in registry.artifacts.values()
        if item.state == ImageState.PUBLISHED
    ]
    return {
        "registry": registry.name,
        "private": registry.private,
        "published_images": len(published),
        "total_bytes": sum(item.size_bytes for item in published),
        "images": [item.to_dict() for item in sorted(
            published, key=lambda image: image.reference
        )],
        "audit_events": len(registry.audit_log),
    }


class RegistryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.registry = Registry("registry.example.com", private=True)
        self.publisher = Principal("release-bot", Role.PUBLISHER, "secret-token")
        self.reader = Principal("deployment-bot", Role.READER, "read-token")
        self.registry.principals[self.publisher.username] = self.publisher
        self.registry.principals[self.reader.username] = self.reader
        self.policy = PublishPolicy(
            allowed_registries=frozenset({"registry.example.com"})
        )
        self.artifact = build_artifact(
            "platform/orders", "v1.2.0", b"example image manifest"
        )

    def test_publish_and_pull(self) -> None:
        published = self.registry.push(
            self.publisher, self.artifact, self.policy,
            CheckState.PASS, True
        )
        self.assertEqual(published.state, ImageState.PUBLISHED)
        self.assertEqual(
            self.registry.pull(self.reader, published.reference).digest,
            published.digest,
        )

    def test_private_pull_requires_identity(self) -> None:
        with self.assertRaises(AuthenticationError):
            self.registry.pull(None, self.artifact.reference)

    def test_reader_cannot_publish(self) -> None:
        with self.assertRaises(AuthorizationError):
            self.registry.push(
                self.reader, self.artifact, self.policy,
                CheckState.PASS, True
            )

    def test_release_tag_cannot_be_replaced(self) -> None:
        self.registry.push(
            self.publisher, self.artifact, self.policy, CheckState.PASS, True
        )
        replacement = build_artifact(
            "platform/orders", "v1.2.0", b"different image manifest"
        )
        with self.assertRaises(ConflictError):
            self.registry.push(
                self.publisher, replacement, self.policy,
                CheckState.PASS, True
            )

    def test_scan_failure_blocks_publication(self) -> None:
        with self.assertRaises(RegistryError):
            self.registry.push(
                self.publisher, self.artifact, self.policy, CheckState.FAIL, True
            )

    def test_invalid_tag(self) -> None:
        with self.assertRaises(ValidationError):
            build_artifact("platform/orders", "bad tag", b"manifest")


def main() -> None:
    registry = Registry("registry.example.com", private=True)
    publisher = Principal("ci-release", Role.PUBLISHER, "demo-publisher-token")
    reader = Principal("production-deployer", Role.READER, "demo-reader-token")
    registry.principals[publisher.username] = publisher
    registry.principals[reader.username] = reader

    policy = PublishPolicy(
        allowed_registries=frozenset({registry.name}),
        require_scan_pass=True,
        require_signature=True,
    )

    artifact = build_artifact(
        "commerce/orders-api",
        "v2.4.1",
        b'{"schemaVersion":2,"mediaType":"application/vnd.oci.image.manifest.v1+json"}',
    )

    registry.authenticate(publisher.username, publisher.token)
    registry.push(publisher, artifact, policy, CheckState.PASS, True)
    pulled = registry.pull(reader, artifact.reference)

    print("Published artifact:")
    print(json.dumps(pulled.to_dict(), indent=2))
    print("\nRegistry report:")
    print(json.dumps(report(registry), indent=2))

    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RegistryTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
