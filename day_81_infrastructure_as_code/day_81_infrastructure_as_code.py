#!/usr/bin/env python3
"""
Infrastructure as Code (IaC): Declarative Infrastructure Management

Demonstrates:
- Declarative infrastructure definitions
- Resource dependencies and topological ordering
- Desired state versus actual state
- Infrastructure planning and execution
- Create, update, delete, replace, and no-op operations
- Drift detection
- Idempotent execution
- Protected resources
- JSON state persistence
- Validation and failure handling
- Infrastructure security policies
"""

from __future__ import annotations

import argparse
import json
import logging
import tempfile
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s"
)
logger = logging.getLogger("iac")


class Action(str, Enum):
    CREATE = "CREATE"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    REPLACE = "REPLACE"
    NO_OP = "NO_OP"


class ResourceError(Exception):
    pass


class ValidationError(ResourceError):
    pass


class StateError(ResourceError):
    pass


class DeploymentError(ResourceError):
    pass


@dataclass
class Resource:
    resource_id: str
    resource_type: str
    properties: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)
    protected: bool = False
    immutable_properties: list[str] = field(default_factory=list)

    def validate(self) -> None:
        if not self.resource_id.strip():
            raise ValidationError("Resource ID cannot be empty")

        if not self.resource_type.strip():
            raise ValidationError("Resource type cannot be empty")

        if not isinstance(self.properties, dict):
            raise ValidationError("Properties must be a dictionary")

        if self.resource_id in self.depends_on:
            raise ValidationError("Resource cannot depend on itself")

        if len(self.depends_on) != len(set(self.depends_on)):
            raise ValidationError("Duplicate dependencies detected")

        if self.resource_type == "network":
            cidr = self.properties.get("cidr")
            if not cidr:
                raise ValidationError("Network requires a CIDR")

        if self.resource_type == "server":
            if self.properties.get("cpu", 0) <= 0:
                raise ValidationError("Server CPU must be positive")

            if self.properties.get("memory_gb", 0) <= 0:
                raise ValidationError("Server memory must be positive")

            if not self.properties.get("network_id"):
                raise ValidationError("Server requires a network")


@dataclass
class PlanItem:
    resource_id: str
    action: Action
    reason: str
    before: dict[str, Any] | None
    after: dict[str, Any] | None


@dataclass
class InfrastructureState:
    resources: dict[str, dict[str, Any]] = field(default_factory=dict)
    revision: int = 0

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)

        payload = {
            "revision": self.revision,
            "resources": self.resources
        }

        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8"
        )
        temporary.replace(path)

    @classmethod
    def load(cls, path: Path) -> InfrastructureState:
        if not path.exists():
            return cls()

        try:
            payload = json.loads(path.read_text(encoding="utf-8"))

            if not isinstance(payload, dict):
                raise StateError("Invalid state document")

            resources = payload.get("resources", {})
            revision = payload.get("revision", 0)

            if not isinstance(resources, dict):
                raise StateError("Invalid resource state")

            if not isinstance(revision, int) or revision < 0:
                raise StateError("Invalid state revision")

            return cls(resources=resources, revision=revision)

        except (json.JSONDecodeError, OSError) as exc:
            raise StateError(f"Cannot load state: {exc}") from exc


class InfrastructureDefinition:
    def __init__(self) -> None:
        self.resources: dict[str, Resource] = {}

    def add(self, resource: Resource) -> None:
        resource.validate()

        if resource.resource_id in self.resources:
            raise ValidationError(
                f"Duplicate resource: {resource.resource_id}"
            )

        self.resources[resource.resource_id] = resource

    def validate_dependencies(self) -> None:
        for resource in self.resources.values():
            for dependency in resource.depends_on:
                if dependency not in self.resources:
                    raise ValidationError(
                        f"{resource.resource_id} depends on "
                        f"missing resource {dependency}"
                    )

        self.deployment_order()

    def deployment_order(self) -> list[str]:
        """Return a topological ordering using Kahn's algorithm."""

        indegree = {
            resource_id: 0
            for resource_id in self.resources
        }

        dependents: dict[str, list[str]] = {
            resource_id: []
            for resource_id in self.resources
        }

        for resource in self.resources.values():
            for dependency in resource.depends_on:
                indegree[resource.resource_id] += 1
                dependents[dependency].append(resource.resource_id)

        queue = sorted(
            resource_id
            for resource_id, degree in indegree.items()
            if degree == 0
        )

        result = []

        while queue:
            current = queue.pop(0)
            result.append(current)

            for dependent in sorted(dependents[current]):
                indegree[dependent] -= 1

                if indegree[dependent] == 0:
                    queue.append(dependent)
                    queue.sort()

        if len(result) != len(self.resources):
            raise ValidationError(
                "Dependency cycle detected"
            )

        return result


class Planner:
    def __init__(
        self,
        definition: InfrastructureDefinition,
        state: InfrastructureState
    ) -> None:
        self.definition = definition
        self.state = state

    @staticmethod
    def properties(resource: Resource) -> dict[str, Any]:
        return resource.properties.copy()

    def create_plan(self) -> list[PlanItem]:
        self.definition.validate_dependencies()

        desired_ids = set(self.definition.resources)
        actual_ids = set(self.state.resources)

        plan = []

        for resource_id in self.definition.deployment_order():
            desired = self.definition.resources[resource_id]
            current = self.state.resources.get(resource_id)

            if current is None:
                action = Action.CREATE
                reason = "Resource does not exist"
                before = None

            else:
                before = current.get("properties", {})
                after = self.properties(desired)

                immutable_changed = any(
                    before.get(key) != after.get(key)
                    for key in desired.immutable_properties
                )

                if immutable_changed:
                    action = Action.REPLACE
                    reason = "Immutable property changed"

                elif before != after:
                    action = Action.UPDATE
                    reason = "Desired properties differ from actual state"

                else:
                    action = Action.NO_OP
                    reason = "Resource already matches desired state"

            plan.append(
                PlanItem(
                    resource_id=resource_id,
                    action=action,
                    reason=reason,
                    before=before,
                    after=self.properties(desired)
                )
            )

        # Delete resources that are no longer declared.
        for resource_id in sorted(actual_ids - desired_ids):
            current = self.state.resources[resource_id]

            if current.get("protected", False):
                raise ValidationError(
                    f"Cannot delete protected resource {resource_id}"
                )

            plan.append(
                PlanItem(
                    resource_id=resource_id,
                    action=Action.DELETE,
                    reason="Resource removed from desired configuration",
                    before=current.get("properties", {}),
                    after=None
                )
            )

        # Check whether deleting a dependency would leave a managed
        # dependent resource without its required infrastructure.
        deleting = {
            item.resource_id
            for item in plan
            if item.action == Action.DELETE
        }

        for resource_id in deleting:
            current = self.state.resources[resource_id]

            for dependent_id, dependent in self.state.resources.items():
                if dependent_id == resource_id:
                    continue

                if resource_id in dependent.get("depends_on", []):
                    if dependent_id not in deleting:
                        raise ValidationError(
                            f"Cannot delete {resource_id}: "
                            f"{dependent_id} still depends on it"
                        )

        return plan


class InfrastructureEngine:
    def __init__(
        self,
        definition: InfrastructureDefinition,
        state: InfrastructureState
    ) -> None:
        self.definition = definition
        self.state = state

    def apply(self, plan: list[PlanItem]) -> None:
        """Apply a validated plan to the simulated infrastructure."""

        original = json.loads(
            json.dumps(self.state.resources)
        )
        original_revision = self.state.revision

        try:
            # Create and update dependencies before their dependents.
            for item in plan:
                if item.action in (
                    Action.CREATE,
                    Action.UPDATE,
                    Action.REPLACE
                ):
                    resource = self.definition.resources[item.resource_id]

                    self.state.resources[item.resource_id] = {
                        "resource_type": resource.resource_type,
                        "properties": resource.properties.copy(),
                        "depends_on": resource.depends_on.copy(),
                        "protected": resource.protected
                    }

                    logger.info(
                        "%s %s",
                        item.action.value,
                        item.resource_id
                    )

            # Delete dependents before their dependencies.
            for item in reversed(plan):
                if item.action == Action.DELETE:
                    self.state.resources.pop(item.resource_id)
                    logger.info("DELETE %s", item.resource_id)

            changed = any(
                item.action != Action.NO_OP
                for item in plan
            )

            if changed:
                self.state.revision += 1

        except Exception as exc:
            self.state.resources = original
            self.state.revision = original_revision
            raise DeploymentError(
                f"Deployment failed and state was restored: {exc}"
            ) from exc


def detect_drift(
    definition: InfrastructureDefinition,
    state: InfrastructureState
) -> list[str]:
    """Compare declared properties with recorded actual properties."""

    differences = []

    for resource_id, desired in definition.resources.items():
        current = state.resources.get(resource_id)

        if current is None:
            differences.append(f"{resource_id}: missing resource")
            continue

        if current.get("properties") != desired.properties:
            differences.append(f"{resource_id}: property drift")

    for resource_id in set(state.resources) - set(definition.resources):
        differences.append(f"{resource_id}: unmanaged resource")

    return differences


def build_infrastructure() -> InfrastructureDefinition:
    definition = InfrastructureDefinition()

    definition.add(
        Resource(
            resource_id="production-network",
            resource_type="network",
            properties={
                "cidr": "10.20.0.0/16",
                "region": "ap-south-1"
            },
            protected=True,
            immutable_properties=["cidr"]
        )
    )

    definition.add(
        Resource(
            resource_id="application-server",
            resource_type="server",
            properties={
                "cpu": 4,
                "memory_gb": 16,
                "network_id": "production-network",
                "image": "ubuntu-24.04"
            },
            depends_on=["production-network"]
        )
    )

    definition.add(
        Resource(
            resource_id="application-storage",
            resource_type="storage",
            properties={
                "size_gb": 100,
                "encrypted": True,
                "versioning": True
            },
            protected=True
        )
    )

    definition.add(
        Resource(
            resource_id="application-firewall",
            resource_type="firewall",
            properties={
                "allow_https": True,
                "allow_ssh": False,
                "default_action": "DENY"
            },
            depends_on=["production-network"]
        )
    )

    definition.validate_dependencies()
    return definition


def print_plan(plan: list[PlanItem]) -> None:
    print("\nINFRASTRUCTURE PLAN")
    print("-" * 75)

    for item in plan:
        print(
            f"{item.action.value:10} "
            f"{item.resource_id:25} "
            f"{item.reason}"
        )

    print("-" * 75)


def run_demo(state_path: Path | None = None) -> None:
    definition = build_infrastructure()

    state = (
        InfrastructureState.load(state_path)
        if state_path
        else InfrastructureState()
    )

    planner = Planner(definition, state)
    plan = planner.create_plan()

    print_plan(plan)

    engine = InfrastructureEngine(definition, state)
    engine.apply(plan)

    print(f"\nState revision: {state.revision}")

    if state_path:
        state.save(state_path)
        print(f"State saved: {state_path}")

    # A second plan should contain only NO_OP operations.
    second_plan = planner.create_plan()

    print("\nSECOND PLAN: IDEMPOTENCY CHECK")
    print_plan(second_plan)

    assert all(
        item.action == Action.NO_OP
        for item in second_plan
    )

    # Simulate an external infrastructure modification.
    state.resources["application-server"]["properties"]["cpu"] = 8

    print("\nDRIFT DETECTION")
    for difference in detect_drift(definition, state):
        print(f"- {difference}")

    # Reconciliation restores the declared configuration.
    repair_plan = planner.create_plan()
    engine.apply(repair_plan)

    assert not detect_drift(definition, state)

    print("\nInfrastructure reconciled successfully.")


def run_tests() -> None:
    definition = build_infrastructure()

    state = InfrastructureState()
    planner = Planner(definition, state)

    plan = planner.create_plan()

    assert len(plan) == 4
    assert plan[0].action == Action.CREATE

    engine = InfrastructureEngine(definition, state)
    engine.apply(plan)

    assert len(state.resources) == 4

    second_plan = planner.create_plan()
    assert all(item.action == Action.NO_OP for item in second_plan)

    state.resources["application-server"]["properties"]["cpu"] = 8

    assert detect_drift(definition, state)

    repair = planner.create_plan()
    engine.apply(repair)

    assert not detect_drift(definition, state)

    # Dependency cycles must be rejected.
    cyclic = InfrastructureDefinition()

    cyclic.add(
        Resource("a", "service", {}, depends_on=["b"])
    )
    cyclic.add(
        Resource("b", "service", {}, depends_on=["a"])
    )

    try:
        cyclic.validate_dependencies()
        raise AssertionError("Cycle was not detected")
    except ValidationError:
        pass

    # Protected resources cannot be removed.
    protected_state = InfrastructureState(
        resources={
            "production-network": {
                "properties": {"cidr": "10.20.0.0/16"},
                "protected": True,
                "depends_on": []
            }
        }
    )

    empty_definition = InfrastructureDefinition()

    try:
        Planner(empty_definition, protected_state).create_plan()
        raise AssertionError("Protected deletion was not rejected")
    except ValidationError:
        pass

    print("All tests passed.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Declarative Infrastructure as Code simulator"
    )

    parser.add_argument(
        "--state",
        type=Path,
        help="Optional JSON state file"
    )

    parser.add_argument(
        "--test",
        action="store_true",
        help="Run validation and behavior tests"
    )

    args = parser.parse_args()

    try:
        if args.test:
            run_tests()
        else:
            run_demo(args.state)

    except ResourceError as exc:
        logger.error("%s", exc)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
