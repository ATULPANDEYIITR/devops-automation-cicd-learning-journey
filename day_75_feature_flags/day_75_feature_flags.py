#!/usr/bin/env python3
"""
Feature Flags: Decoupling Deployment from Feature Release

Demonstrates:
- Boolean, percentage, and targeted feature flags
- Environment-specific configuration
- User and group targeting
- Deterministic percentage rollouts
- Kill switches
- Flag lifecycle and expiration
- Audit logging
- Configuration validation
- Thread-safe evaluation and updates
- JSON persistence
- Automated assertions
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
import threading

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("feature_flags")


class FlagType(Enum):
    BOOLEAN = "boolean"
    PERCENTAGE = "percentage"
    TARGETED = "targeted"


class FlagStatus(Enum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ARCHIVED = "archived"


class Environment(Enum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class FlagError(Exception):
    """Base exception for feature flag operations."""


class FlagNotFoundError(FlagError):
    pass


class InvalidConfigurationError(FlagError):
    pass


class ExpiredFlagError(FlagError):
    pass


@dataclass
class EvaluationContext:
    user_id: str
    environment: Environment
    groups: set[str] = field(default_factory=set)
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.user_id or not self.user_id.strip():
            raise ValueError("user_id cannot be empty")

        if not isinstance(self.environment, Environment):
            raise ValueError("Invalid environment")


@dataclass
class FeatureFlag:
    key: str
    description: str
    flag_type: FlagType
    status: FlagStatus = FlagStatus.ACTIVE

    enabled_environments: set[Environment] = field(default_factory=set)
    rollout_percentage: float = 0.0

    allowed_users: set[str] = field(default_factory=set)
    allowed_groups: set[str] = field(default_factory=set)

    default_value: bool = False
    owner: str = "platform-team"

    expires_at: str | None = None
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )

    def validate(self):
        if not self.key or not self.key.replace("_", "").replace("-", "").isalnum():
            raise InvalidConfigurationError("Invalid flag key")

        if not 0 <= self.rollout_percentage <= 100:
            raise InvalidConfigurationError(
                "Rollout percentage must be between 0 and 100"
            )

        if not isinstance(self.flag_type, FlagType):
            raise InvalidConfigurationError("Invalid flag type")

        if not isinstance(self.status, FlagStatus):
            raise InvalidConfigurationError("Invalid flag status")

        if self.expires_at:
            try:
                expiration = datetime.fromisoformat(
                    self.expires_at.replace("Z", "+00:00")
                )

                if expiration.tzinfo is None:
                    raise ValueError("Expiration must include timezone")

            except ValueError as exc:
                raise InvalidConfigurationError(
                    "Invalid expiration timestamp"
                ) from exc


@dataclass
class AuditEvent:
    flag_key: str
    action: str
    actor: str
    timestamp: str
    details: dict[str, Any]


class FeatureFlagService:
    """
    Thread-safe feature flag management and evaluation service.

    Evaluation complexity:
        Boolean: O(1)
        Targeting: O(U + G) for set membership
        Percentage: O(1) hashing
    """

    def __init__(self):
        self.flags: dict[str, FeatureFlag] = {}
        self.audit_log: list[AuditEvent] = []
        self.lock = threading.RLock()

    def register(self, flag: FeatureFlag, actor: str = "system"):
        flag.validate()

        with self.lock:
            if flag.key in self.flags:
                raise InvalidConfigurationError(
                    f"Flag already exists: {flag.key}"
                )

            self.flags[flag.key] = flag

            self._audit(
                flag.key,
                "CREATED",
                actor,
                {"type": flag.flag_type.value}
            )

    def get(self, key: str) -> FeatureFlag:
        with self.lock:
            flag = self.flags.get(key)

            if flag is None:
                raise FlagNotFoundError(key)

            return flag

    @staticmethod
    def _is_expired(flag: FeatureFlag) -> bool:
        if not flag.expires_at:
            return False

        expiration = datetime.fromisoformat(
            flag.expires_at.replace("Z", "+00:00")
        )

        return datetime.now(timezone.utc) >= expiration

    @staticmethod
    def _percentage_bucket(key: str, user_id: str) -> float:
        """
        Stable allocation: the same flag and user always receive
        the same bucket, independent of process restarts.
        """
        value = hashlib.sha256(
            f"{key}:{user_id}".encode("utf-8")
        ).hexdigest()

        number = int(value[:16], 16)

        return number / (16 ** 16) * 100

    def evaluate(
        self,
        key: str,
        context: EvaluationContext
    ) -> bool:

        with self.lock:
            flag = self.flags.get(key)

            if flag is None:
                logger.warning("Unknown feature flag: %s", key)
                return False

            if flag.status != FlagStatus.ACTIVE:
                return False

            if self._is_expired(flag):
                logger.warning("Expired flag: %s", key)
                return False

            if context.environment not in flag.enabled_environments:
                return False

            # Explicit user and group targeting takes priority.
            if context.user_id in flag.allowed_users:
                return True

            if flag.allowed_groups.intersection(context.groups):
                return True

            if flag.flag_type == FlagType.BOOLEAN:
                return flag.default_value

            if flag.flag_type == FlagType.TARGETED:
                return False

            if flag.flag_type == FlagType.PERCENTAGE:
                bucket = self._percentage_bucket(
                    key,
                    context.user_id
                )

                return bucket < flag.rollout_percentage

            return False

    def update_rollout(
        self,
        key: str,
        percentage: float,
        actor: str
    ):
        if not 0 <= percentage <= 100:
            raise InvalidConfigurationError(
                "Percentage must be between 0 and 100"
            )

        with self.lock:
            flag = self.get(key)

            old_value = flag.rollout_percentage
            flag.rollout_percentage = percentage
            flag.flag_type = FlagType.PERCENTAGE

            self._audit(
                key,
                "ROLLOUT_UPDATED",
                actor,
                {
                    "old_percentage": old_value,
                    "new_percentage": percentage
                }
            )

    def disable(self, key: str, actor: str):
        """Emergency kill switch."""
        with self.lock:
            flag = self.get(key)
            flag.status = FlagStatus.DISABLED

            self._audit(key, "DISABLED", actor, {})

    def enable(self, key: str, actor: str):
        with self.lock:
            flag = self.get(key)

            if self._is_expired(flag):
                raise ExpiredFlagError(
                    f"Cannot activate expired flag: {key}"
                )

            flag.status = FlagStatus.ACTIVE

            self._audit(key, "ENABLED", actor, {})

    def archive(self, key: str, actor: str):
        with self.lock:
            flag = self.get(key)
            flag.status = FlagStatus.ARCHIVED

            self._audit(key, "ARCHIVED", actor, {})

    def _audit(
        self,
        key: str,
        action: str,
        actor: str,
        details: dict
    ):
        self.audit_log.append(
            AuditEvent(
                flag_key=key,
                action=action,
                actor=actor,
                timestamp=datetime.now(timezone.utc).isoformat(),
                details=details
            )
        )

    def save(self, filepath: str):
        """Write configuration using atomic file replacement."""
        path = Path(filepath)
        path.parent.mkdir(parents=True, exist_ok=True)

        with self.lock:
            data = []

            for flag in self.flags.values():
                item = asdict(flag)

                item["flag_type"] = flag.flag_type.value
                item["status"] = flag.status.value

                item["enabled_environments"] = [
                    environment.value
                    for environment in flag.enabled_environments
                ]

                item["allowed_users"] = sorted(flag.allowed_users)
                item["allowed_groups"] = sorted(flag.allowed_groups)

                data.append(item)

            audit = [
                asdict(event)
                for event in self.audit_log
            ]

            payload = {
                "flags": data,
                "audit_log": audit
            }

            temporary = path.with_suffix(path.suffix + ".tmp")

            try:
                with temporary.open("w", encoding="utf-8") as file:
                    json.dump(payload, file, indent=2)

                os.replace(temporary, path)

            except OSError:
                temporary.unlink(missing_ok=True)
                raise

    def load(self, filepath: str):
        """Load and validate configuration before replacing state."""
        with open(filepath, "r", encoding="utf-8") as file:
            payload = json.load(file)

        loaded_flags = {}

        for item in payload["flags"]:
            item["flag_type"] = FlagType(item["flag_type"])
            item["status"] = FlagStatus(item["status"])

            item["enabled_environments"] = {
                Environment(value)
                for value in item["enabled_environments"]
            }

            item["allowed_users"] = set(item["allowed_users"])
            item["allowed_groups"] = set(item["allowed_groups"])

            flag = FeatureFlag(**item)
            flag.validate()

            if flag.key in loaded_flags:
                raise InvalidConfigurationError(
                    f"Duplicate flag: {flag.key}"
                )

            loaded_flags[flag.key] = flag

        with self.lock:
            self.flags = loaded_flags

    def report(self) -> list[dict]:
        with self.lock:
            return [
                {
                    "key": flag.key,
                    "type": flag.flag_type.value,
                    "status": flag.status.value,
                    "rollout": flag.rollout_percentage,
                    "owner": flag.owner
                }
                for flag in self.flags.values()
            ]


def main():
    service = FeatureFlagService()

    checkout = FeatureFlag(
        key="new_checkout",
        description="New checkout experience",
        flag_type=FlagType.PERCENTAGE,
        enabled_environments={
            Environment.STAGING,
            Environment.PRODUCTION
        },
        rollout_percentage=25,
        allowed_users={"admin_001"},
        allowed_groups={"beta_testers"},
        owner="payments-team"
    )

    service.register(checkout)

    payment = FeatureFlag(
        key="instant_payment",
        description="Instant payment processing",
        flag_type=FlagType.BOOLEAN,
        enabled_environments={Environment.STAGING},
        default_value=True,
        owner="payments-team"
    )

    service.register(payment)

    contexts = [
        EvaluationContext(
            "user_001",
            Environment.PRODUCTION,
            {"standard"}
        ),
        EvaluationContext(
            "user_002",
            Environment.PRODUCTION,
            {"beta_testers"}
        ),
        EvaluationContext(
            "admin_001",
            Environment.PRODUCTION,
            {"standard"}
        ),
        EvaluationContext(
            "user_003",
            Environment.STAGING,
            {"standard"}
        )
    ]

    print("\nFEATURE FLAG EVALUATION")

    for context in contexts:
        result = service.evaluate("new_checkout", context)

        print(
            f"{context.user_id:12} "
            f"{context.environment.value:12} "
            f"enabled={result}"
        )

    # Verify deterministic allocation.
    context = contexts[0]

    first = service.evaluate("new_checkout", context)
    second = service.evaluate("new_checkout", context)

    assert first == second

    # Explicit targeting overrides percentage allocation.
    assert service.evaluate(
        "new_checkout",
        contexts[1]
    ) is True

    assert service.evaluate(
        "instant_payment",
        contexts[3]
    ) is True

    assert service.evaluate(
        "instant_payment",
        contexts[0]
    ) is False

    # Increase rollout without redeploying application code.
    service.update_rollout(
        "new_checkout",
        50,
        "release-manager"
    )

    # Emergency disable.
    service.disable(
        "new_checkout",
        "incident-commander"
    )

    assert service.evaluate(
        "new_checkout",
        contexts[1]
    ) is False

    service.enable(
        "new_checkout",
        "release-manager"
    )

    print("\nFLAG REPORT")

    for item in service.report():
        print(item)

    print("\nAUDIT EVENTS")

    for event in service.audit_log:
        print(
            event.timestamp,
            event.flag_key,
            event.action,
            event.actor
        )

    # Validate configuration persistence.
    with tempfile.TemporaryDirectory() as directory:
        path = str(Path(directory) / "flags.json")

        service.save(path)

        restored = FeatureFlagService()
        restored.load(path)

        assert "new_checkout" in restored.flags
        assert restored.flags["new_checkout"].rollout_percentage == 50

        print("\nConfiguration persistence verified.")

    # Validate invalid percentage handling.
    try:
        service.update_rollout(
            "new_checkout",
            150,
            "unauthorized-value"
        )
    except InvalidConfigurationError as error:
        print("\nExpected validation error:", error)

    print("\nAll feature flag checks passed.")


if __name__ == "__main__":
    main()
