"""
Deployment Strategy Simulator
Strategies: Recreate, Rolling, Blue-Green

Models deployment lifecycle, infrastructure capacity, health checks,
traffic routing, rollback, deployment history, and failure handling.

Python 3.10+
Standard library only.
"""

from __future__ import annotations

import json
import logging
import random
import time
import uuid

from dataclasses import dataclass, asdict, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Optional


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("deployment")


class DeploymentStrategy(Enum):
    RECREATE = "recreate"
    ROLLING = "rolling"
    BLUE_GREEN = "blue_green"


class DeploymentStatus(Enum):
    PENDING = "pending"
    PREPARING = "preparing"
    DEPLOYING = "deploying"
    VALIDATING = "validating"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class InstanceStatus(Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"


@dataclass
class DeploymentConfig:
    application: str
    version: str
    strategy: DeploymentStrategy
    replicas: int = 4
    batch_size: int = 2
    max_surge: int = 1
    max_unavailable: int = 1
    health_threshold: float = 0.95
    traffic_weight: int = 100
    health_failure_rate: float = 0.0
    startup_failure_rate: float = 0.0

    def validate(self) -> None:
        if not self.application.strip():
            raise ValueError("Application name cannot be empty")

        if not self.version.strip():
            raise ValueError("Version cannot be empty")

        if self.replicas < 1:
            raise ValueError("At least one replica is required")

        if self.batch_size < 1:
            raise ValueError("Batch size must be positive")

        if self.max_surge < 0 or self.max_unavailable < 0:
            raise ValueError("Capacity limits cannot be negative")

        if self.max_surge + self.max_unavailable < 1:
            raise ValueError(
                "Deployment must permit either additional capacity "
                "or temporary unavailability"
            )

        if not 0 <= self.health_threshold <= 1:
            raise ValueError("Invalid health threshold")

        if not 0 <= self.health_failure_rate <= 1:
            raise ValueError("Invalid health failure rate")

        if not 0 <= self.startup_failure_rate <= 1:
            raise ValueError("Invalid startup failure rate")

        if not 0 <= self.traffic_weight <= 100:
            raise ValueError("Traffic weight must be between 0 and 100")


@dataclass
class Instance:
    instance_id: str
    version: str
    status: InstanceStatus = InstanceStatus.STOPPED


@dataclass
class DeploymentRecord:
    deployment_id: str
    application: str
    version: str
    strategy: str
    status: str
    started_at: str
    completed_at: Optional[str] = None
    previous_version: Optional[str] = None
    error: Optional[str] = None
    metrics: dict = field(default_factory=dict)


class DeploymentError(Exception):
    """Base deployment exception."""


class HealthCheckError(DeploymentError):
    """Raised when deployment health checks fail."""


class CapacityError(DeploymentError):
    """Raised when infrastructure capacity is exceeded."""


class DeploymentManager:

    def __init__(
        self,
        initial_version: str,
        capacity: int = 10,
        random_seed: int = 42
    ):
        if capacity < 1:
            raise ValueError("Capacity must be positive")

        self.capacity = capacity
        self.random = random.Random(random_seed)

        self.instances = [
            Instance(
                instance_id=f"instance-{i + 1}",
                version=initial_version,
                status=InstanceStatus.HEALTHY
            )
            for i in range(4)
        ]

        if len(self.instances) > capacity:
            raise CapacityError("Initial infrastructure exceeds capacity")

        self.active_version = initial_version
        self.previous_version = None
        self.traffic_version = initial_version
        self.history: list[DeploymentRecord] = []
        self.events: list[dict] = []

    def _event(self, event_type: str, details: dict) -> None:
        self.events.append({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event_type,
            "details": details
        })

        logger.info("%s: %s", event_type, details)

    def _healthy_instances(self) -> list[Instance]:
        return [
            instance for instance in self.instances
            if instance.status == InstanceStatus.HEALTHY
        ]

    def _new_instance(self, version: str) -> Instance:
        return Instance(
            instance_id=str(uuid.uuid4())[:8],
            version=version,
            status=InstanceStatus.STARTING
        )

    def _start_instance(
        self,
        instance: Instance,
        config: DeploymentConfig
    ) -> None:
        if self.random.random() < config.startup_failure_rate:
            instance.status = InstanceStatus.UNHEALTHY
            raise DeploymentError(
                f"Instance {instance.instance_id} failed to start"
            )

        instance.status = InstanceStatus.HEALTHY

    def _health_check(
        self,
        config: DeploymentConfig,
        instances: Optional[list[Instance]] = None
    ) -> bool:
        targets = instances if instances is not None else self.instances

        if not targets:
            return False

        healthy = sum(
            instance.status == InstanceStatus.HEALTHY
            for instance in targets
        )

        ratio = healthy / len(targets)

        self._event("HEALTH_CHECK", {
            "healthy": healthy,
            "total": len(targets),
            "ratio": round(ratio, 3),
            "required": config.health_threshold
        })

        return (
            ratio >= config.health_threshold
            and all(
                instance.status == InstanceStatus.HEALTHY
                for instance in targets
            )
        )

    def _simulate_application_health(
        self,
        config: DeploymentConfig,
        instances: list[Instance]
    ) -> None:
        if self.random.random() < config.health_failure_rate:
            if instances:
                instances[0].status = InstanceStatus.UNHEALTHY

    def _capacity_check(self, required: int) -> None:
        if required > self.capacity:
            raise CapacityError(
                f"Required instances: {required}; "
                f"available capacity: {self.capacity}"
            )

    def _recreate(self, config: DeploymentConfig) -> None:
        """
        Stop old instances before starting new instances.
        This strategy can produce downtime.
        """
        self._event("RECREATE_STOP", {
            "old_version": self.active_version
        })

        old_instances = self.instances.copy()

        for instance in self.instances:
            instance.status = InstanceStatus.STOPPED

        self.instances = []

        try:
            self._capacity_check(config.replicas)

            for _ in range(config.replicas):
                instance = self._new_instance(config.version)
                self.instances.append(instance)
                self._start_instance(instance, config)

            self._simulate_application_health(config, self.instances)

            if not self._health_check(config):
                raise HealthCheckError("Recreated instances are unhealthy")

            self._event("RECREATE_COMPLETE", {
                "version": config.version
            })

        except Exception:
            self.instances = old_instances
            raise

    def _rolling(self, config: DeploymentConfig) -> None:
        """
        Replace instances in batches while enforcing surge and
        unavailability limits.
        """
        original_instances = self.instances.copy()

        if config.max_surge == 0 and config.max_unavailable == 0:
            raise CapacityError("Rolling deployment cannot make progress")

        try:
            remaining = original_instances.copy()
            updated: list[Instance] = []

            while remaining:
                batch_count = min(
                    config.batch_size,
                    len(remaining)
                )

                old_batch = remaining[:batch_count]

                allowed_unavailable = min(
                    config.max_unavailable,
                    max(0, len(remaining) - config.max_unavailable)
                )

                if len(old_batch) > allowed_unavailable:
                    old_batch = old_batch[:allowed_unavailable]

                if not old_batch:
                    surge_count = min(
                        config.max_surge,
                        len(remaining)
                    )

                    if surge_count == 0:
                        raise CapacityError(
                            "Cannot replace instances under current policy"
                        )

                    old_batch = remaining[:surge_count]

                surge = max(0, len(self.instances) - config.replicas)

                replacement_count = min(
                    len(old_batch),
                    config.max_surge - surge
                )

                if replacement_count <= 0:
                    replacement_count = min(
                        len(old_batch),
                        config.max_unavailable
                    )

                if replacement_count <= 0:
                    raise CapacityError(
                        "No replacement capacity available"
                    )

                old_batch = old_batch[:replacement_count]

                self._event("ROLLING_BATCH", {
                    "old_instances": len(old_batch),
                    "remaining": len(remaining)
                })

                for old in old_batch:
                    old.status = InstanceStatus.STOPPED
                    self.instances.remove(old)
                    remaining.remove(old)

                for _ in old_batch:
                    replacement = self._new_instance(config.version)
                    self._capacity_check(len(self.instances) + 1)
                    self.instances.append(replacement)
                    self._start_instance(replacement, config)
                    updated.append(replacement)

                if not self._health_check(config, updated):
                    raise HealthCheckError(
                        "Rolling batch failed health validation"
                    )

            self._simulate_application_health(config, updated)

            if not self._health_check(config):
                raise HealthCheckError(
                    "Final rolling deployment health check failed"
                )

        except Exception:
            self.instances = original_instances
            raise

    def _blue_green(self, config: DeploymentConfig) -> None:
        """
        Provision a complete inactive environment, validate it,
        and switch traffic only after successful validation.
        """
        original_instances = self.instances.copy()
        original_traffic = self.traffic_version

        self._capacity_check(
            len(self.instances) + config.replicas
        )

        green: list[Instance] = []

        try:
            self._event("GREEN_PROVISIONING", {
                "version": config.version
            })

            for _ in range(config.replicas):
                instance = self._new_instance(config.version)
                green.append(instance)
                self._start_instance(instance, config)

            self.instances.extend(green)

            self._simulate_application_health(config, green)

            if not self._health_check(config, green):
                raise HealthCheckError(
                    "Green environment failed validation"
                )

            self._event("TRAFFIC_SWITCH", {
                "from": original_traffic,
                "to": config.version,
                "weight": config.traffic_weight
            })

            self.traffic_version = config.version

            if config.traffic_weight != 100:
                raise DeploymentError(
                    "Partial traffic shift requires a separate "
                    "progressive-delivery controller"
                )

            self.instances = green

        except Exception:
            self.instances = original_instances
            self.traffic_version = original_traffic
            raise

    def rollback(self, version: Optional[str] = None) -> None:
        target = version or self.previous_version

        if not target:
            raise DeploymentError("No rollback version is available")

        self._event("ROLLBACK_STARTED", {
            "target": target
        })

        self.instances = [
            Instance(
                instance_id=f"rollback-{i + 1}",
                version=target,
                status=InstanceStatus.HEALTHY
            )
            for i in range(4)
        ]

        self.active_version = target
        self.traffic_version = target

        self._event("ROLLBACK_COMPLETED", {
            "active_version": target
        })

    def deploy(self, config: DeploymentConfig) -> DeploymentRecord:
        config.validate()

        record = DeploymentRecord(
            deployment_id=str(uuid.uuid4()),
            application=config.application,
            version=config.version,
            strategy=config.strategy.value,
            status=DeploymentStatus.PENDING.value,
            started_at=datetime.now(timezone.utc).isoformat(),
            previous_version=self.active_version
        )

        self.history.append(record)

        try:
            if config.version == self.active_version:
                raise DeploymentError(
                    "Requested version is already active"
                )

            record.status = DeploymentStatus.PREPARING.value

            self._event("DEPLOYMENT_STARTED", {
                "id": record.deployment_id,
                "strategy": config.strategy.value,
                "version": config.version
            })

            record.status = DeploymentStatus.DEPLOYING.value

            if config.strategy == DeploymentStrategy.RECREATE:
                self._recreate(config)

            elif config.strategy == DeploymentStrategy.ROLLING:
                self._rolling(config)

            elif config.strategy == DeploymentStrategy.BLUE_GREEN:
                self._blue_green(config)

            else:
                raise DeploymentError("Unsupported deployment strategy")

            record.status = DeploymentStatus.SUCCEEDED.value

            self.previous_version = self.active_version
            self.active_version = config.version
            self.traffic_version = config.version

            record.metrics = {
                "instances": len(self.instances),
                "healthy_instances": len(self._healthy_instances()),
                "capacity": self.capacity,
                "traffic_version": self.traffic_version
            }

        except Exception as error:
            record.status = DeploymentStatus.FAILED.value
            record.error = str(error)

            self._event("DEPLOYMENT_FAILED", {
                "error": str(error)
            })

            if self.active_version != record.previous_version:
                self.rollback(record.previous_version)

            raise DeploymentError(str(error)) from error

        finally:
            record.completed_at = datetime.now(
                timezone.utc
            ).isoformat()

        self._event("DEPLOYMENT_FINISHED", {
            "status": record.status,
            "version": config.version
        })

        return record

    def save_history(self, filename: str = "deployment_history.json"):
        path = Path(filename)

        temporary = path.with_suffix(path.suffix + ".tmp")

        payload = {
            "active_version": self.active_version,
            "traffic_version": self.traffic_version,
            "history": [asdict(item) for item in self.history],
            "events": self.events
        }

        # Replace atomically so an interrupted write does not
        # leave a partially written history file.
        temporary.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8"
        )

        temporary.replace(path)


def demonstrate():
    manager = DeploymentManager(
        initial_version="1.0.0",
        capacity=12
    )

    scenarios = [
        DeploymentConfig(
            application="payment-api",
            version="1.1.0",
            strategy=DeploymentStrategy.ROLLING,
            replicas=4,
            batch_size=1,
            max_surge=1,
            max_unavailable=1
        ),
        DeploymentConfig(
            application="payment-api",
            version="1.2.0",
            strategy=DeploymentStrategy.BLUE_GREEN,
            replicas=4
        ),
        DeploymentConfig(
            application="payment-api",
            version="1.3.0",
            strategy=DeploymentStrategy.RECREATE,
            replicas=4
        )
    ]

    for config in scenarios:
        try:
            record = manager.deploy(config)
            print(
                f"{record.strategy}: {record.status} "
                f"version={record.version}"
            )
        except DeploymentError as error:
            print(f"Deployment failed: {error}")

    print("\nDeployment history:")

    for record in manager.history:
        print(
            record.version,
            record.strategy,
            record.status
        )

    manager.save_history()


def run_tests():
    manager = DeploymentManager("1.0.0", capacity=12)

    result = manager.deploy(
        DeploymentConfig(
            application="inventory-api",
            version="2.0.0",
            strategy=DeploymentStrategy.ROLLING,
            replicas=4,
            batch_size=1
        )
    )

    assert result.status == "succeeded"
    assert manager.active_version == "2.0.0"

    old_version = manager.active_version

    try:
        manager.deploy(
            DeploymentConfig(
                application="inventory-api",
                version="3.0.0",
                strategy=DeploymentStrategy.BLUE_GREEN,
                replicas=4,
                health_failure_rate=1.0
            )
        )
    except DeploymentError:
        pass

    assert manager.active_version == old_version
    assert manager.traffic_version == old_version

    try:
        DeploymentConfig(
            application="",
            version="4.0.0",
            strategy=DeploymentStrategy.RECREATE
        ).validate()
    except ValueError:
        pass
    else:
        raise AssertionError("Invalid configuration was accepted")

    print("All deployment tests passed.")


if __name__ == "__main__":
    run_tests()
    demonstrate()
