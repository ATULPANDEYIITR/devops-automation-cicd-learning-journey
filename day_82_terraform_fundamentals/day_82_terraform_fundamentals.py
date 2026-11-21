#!/usr/bin/env python3
"""
Terraform Fundamentals: Providers, Resources, Variables, and Outputs.

A self-contained infrastructure-as-code simulator demonstrating:
- Provider configuration and validation
- Typed input variables and defaults
- Resource declarations and dependencies
- Dependency graph construction and execution ordering
- Plan and apply operations
- State management and drift detection
- Resource references and outputs
- Validation failures and rollback behavior

Run: python terraform_fundamentals.py
"""

from __future__ import annotations

import json
import re
import hashlib
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Callable


class TerraformError(Exception):
    """Base exception for infrastructure workflow errors."""


class ValidationError(TerraformError):
    pass


class ProviderError(TerraformError):
    pass


class DependencyError(TerraformError):
    pass


class StateError(TerraformError):
    pass


class ResourceAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    REPLACE = "replace"
    DESTROY = "destroy"
    NO_CHANGE = "no_change"


class ResourceStatus(str, Enum):
    PENDING = "pending"
    PLANNED = "planned"
    CREATED = "created"
    UPDATED = "updated"
    DESTROYED = "destroyed"
    FAILED = "failed"


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    region: str
    version: str
    credentials_source: str = "environment"

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_-]*", self.name):
            raise ProviderError("Invalid provider name.")

        if not re.fullmatch(r"[a-z0-9-]+", self.region):
            raise ProviderError("Invalid provider region.")

        if not re.fullmatch(r"\d+\.\d+\.\d+", self.version):
            raise ProviderError("Provider version must use semantic versioning.")

        if self.credentials_source not in {"environment", "workload_identity"}:
            raise ProviderError("Unsupported credentials source.")


@dataclass(frozen=True)
class VariableDefinition:
    name: str
    expected_type: type
    default: Any = None
    required: bool = False
    sensitive: bool = False
    validator: Callable[[Any], bool] | None = field(
        default=None, compare=False, repr=False
    )
    description: str = ""

    def resolve(self, supplied: dict[str, Any]) -> Any:
        if self.name in supplied:
            value = supplied[self.name]
        elif self.required:
            raise ValidationError(f"Required variable '{self.name}' is missing.")
        else:
            value = self.default

        # bool is a subclass of int in Python, so use exact type checks.
        if type(value) is not self.expected_type:
            raise ValidationError(
                f"Variable '{self.name}' must be "
                f"{self.expected_type.__name__}."
            )

        if self.validator and not self.validator(value):
            raise ValidationError(
                f"Variable '{self.name}' failed validation."
            )

        return value


class VariableManager:
    def __init__(self, definitions: list[VariableDefinition]):
        self.definitions = {item.name: item for item in definitions}

        if len(self.definitions) != len(definitions):
            raise ValidationError("Duplicate variable definitions.")

    def resolve(self, supplied: dict[str, Any]) -> dict[str, Any]:
        unknown = set(supplied) - set(self.definitions)

        if unknown:
            raise ValidationError(
                f"Unknown variables: {', '.join(sorted(unknown))}"
            )

        return {
            name: definition.resolve(supplied)
            for name, definition in self.definitions.items()
        }

    def display(self, values: dict[str, Any]) -> dict[str, Any]:
        return {
            name: "***REDACTED***" if self.definitions[name].sensitive else value
            for name, value in values.items()
        }


@dataclass
class Resource:
    name: str
    resource_type: str
    attributes: dict[str, Any]
    depends_on: list[str] = field(default_factory=list)
    status: ResourceStatus = ResourceStatus.PENDING

    @property
    def address(self) -> str:
        return f"{self.resource_type}.{self.name}"

    def validate(self) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", self.name):
            raise ValidationError(f"Invalid resource name: {self.name}")

        if not re.fullmatch(r"[a-z][a-z0-9_]*_[a-z][a-z0-9_]*", self.resource_type):
            raise ValidationError(f"Invalid resource type: {self.resource_type}")

        if not isinstance(self.attributes, dict):
            raise ValidationError("Resource attributes must be a dictionary.")

        if self.address in self.depends_on:
            raise DependencyError("A resource cannot depend on itself.")


@dataclass
class PlanEntry:
    address: str
    action: ResourceAction
    changes: dict[str, Any]


@dataclass
class StateRecord:
    address: str
    resource_type: str
    attributes: dict[str, Any]
    resource_id: str
    provider: str


class StateManager:
    def __init__(self):
        self.records: dict[str, StateRecord] = {}

    def get(self, address: str) -> StateRecord | None:
        return self.records.get(address)

    def save(self, record: StateRecord) -> None:
        self.records[record.address] = record

    def remove(self, address: str) -> None:
        self.records.pop(address, None)

    def snapshot(self) -> dict[str, StateRecord]:
        return {
            address: StateRecord(
                record.address,
                record.resource_type,
                record.attributes.copy(),
                record.resource_id,
                record.provider,
            )
            for address, record in self.records.items()
        }

    def restore(self, snapshot: dict[str, StateRecord]) -> None:
        self.records = snapshot

    def serialize(self) -> str:
        return json.dumps(
            {
                address: asdict(record)
                for address, record in self.records.items()
            },
            indent=2,
        )

    def detect_drift(self, desired: dict[str, Resource]) -> list[str]:
        drift = []

        for address, resource in desired.items():
            existing = self.get(address)

            if existing is None:
                drift.append(f"{address}: missing from state")

            elif existing.attributes != resource.attributes:
                drift.append(f"{address}: desired configuration differs from state")

        return drift


class InfrastructureEngine:
    def __init__(
        self,
        provider: ProviderConfig,
        variables: VariableManager,
        supplied_variables: dict[str, Any],
    ):
        provider.validate()

        self.provider = provider
        self.variable_manager = variables
        self.variables = variables.resolve(supplied_variables)
        self.state = StateManager()
        self.resources: dict[str, Resource] = {}
        self.outputs: dict[str, Any] = {}

    def add_resource(self, resource: Resource) -> None:
        resource.validate()

        if resource.address in self.resources:
            raise ValidationError(
                f"Duplicate resource: {resource.address}"
            )

        self.resources[resource.address] = resource

    def resolve_attributes(self, value: Any) -> Any:
        if isinstance(value, str):
            return value.format(**self.variables)

        if isinstance(value, list):
            return [self.resolve_attributes(item) for item in value]

        if isinstance(value, dict):
            return {
                key: self.resolve_attributes(item)
                for key, item in value.items()
            }

        return value

    def execution_order(self) -> list[str]:
        visited: set[str] = set()
        active: set[str] = set()
        ordered: list[str] = []

        def visit(address: str) -> None:
            if address in active:
                raise DependencyError(
                    f"Circular dependency detected at {address}"
                )

            if address in visited:
                return

            if address not in self.resources:
                raise DependencyError(
                    f"Unknown dependency: {address}"
                )

            active.add(address)

            for dependency in self.resources[address].depends_on:
                visit(dependency)

            active.remove(address)
            visited.add(address)
            ordered.append(address)

        for address in sorted(self.resources):
            visit(address)

        return ordered

    def plan(self) -> list[PlanEntry]:
        order = self.execution_order()
        plan: list[PlanEntry] = []

        for address in order:
            resource = self.resources[address]
            desired = self.resolve_attributes(resource.attributes)
            existing = self.state.get(address)

            if existing is None:
                action = ResourceAction.CREATE
                changes = {"after": desired}

            elif existing.attributes == desired:
                action = ResourceAction.NO_CHANGE
                changes = {}

            else:
                action = ResourceAction.UPDATE
                changes = {
                    "before": existing.attributes,
                    "after": desired,
                }

            resource.status = ResourceStatus.PLANNED

            plan.append(PlanEntry(address, action, changes))

        # Detect resources present in state but absent from configuration.
        for address in sorted(set(self.state.records) - set(self.resources)):
            plan.append(
                PlanEntry(
                    address,
                    ResourceAction.DESTROY,
                    {"before": self.state.records[address].attributes},
                )
            )

        return plan

    @staticmethod
    def generate_resource_id(address: str, attributes: dict[str, Any]) -> str:
        serialized = json.dumps(attributes, sort_keys=True)
        digest = hashlib.sha256(
            f"{address}:{serialized}".encode()
        ).hexdigest()[:16]

        return f"tf-{digest}"

    def apply(self, plan: list[PlanEntry]) -> None:
        snapshot = self.state.snapshot()

        try:
            for entry in plan:
                resource = self.resources.get(entry.address)

                if entry.action == ResourceAction.DESTROY:
                    self.state.remove(entry.address)
                    continue

                if entry.action == ResourceAction.NO_CHANGE:
                    continue

                if resource is None:
                    raise StateError(
                        f"Missing resource configuration: {entry.address}"
                    )

                attributes = self.resolve_attributes(resource.attributes)

                # Simulate provider-level validation.
                if attributes.get("simulate_failure") is True:
                    raise ProviderError(
                        f"Provider failed while creating {entry.address}"
                    )

                attributes.pop("simulate_failure", None)

                record = StateRecord(
                    address=entry.address,
                    resource_type=resource.resource_type,
                    attributes=attributes,
                    resource_id=self.generate_resource_id(
                        entry.address, attributes
                    ),
                    provider=self.provider.name,
                )

                self.state.save(record)

                resource.status = (
                    ResourceStatus.CREATED
                    if entry.action == ResourceAction.CREATE
                    else ResourceStatus.UPDATED
                )

        except Exception:
            self.state.restore(snapshot)

            for resource in self.resources.values():
                if resource.status != ResourceStatus.PENDING:
                    resource.status = ResourceStatus.FAILED

            raise

    def evaluate_outputs(
        self,
        definitions: dict[str, tuple[str, str]],
    ) -> dict[str, Any]:
        """
        Each output maps to (resource address, attribute name).
        """
        result = {}

        for output_name, (address, attribute) in definitions.items():
            record = self.state.get(address)

            if record is None:
                raise StateError(
                    f"Output '{output_name}' references missing resource."
                )

            if attribute not in record.attributes:
                raise StateError(
                    f"Attribute '{attribute}' does not exist on {address}."
                )

            result[output_name] = record.attributes[attribute]

        self.outputs = result
        return result


def demonstrate() -> None:
    print("\n=== TERRAFORM FUNDAMENTALS SIMULATOR ===")

    variable_definitions = [
        VariableDefinition(
            name="environment",
            expected_type=str,
            default="development",
            validator=lambda value: value in {
                "development", "staging", "production"
            },
            description="Deployment environment.",
        ),
        VariableDefinition(
            name="instance_count",
            expected_type=int,
            default=2,
            validator=lambda value: 1 <= value <= 10,
        ),
        VariableDefinition(
            name="instance_type",
            expected_type=str,
            default="t3.small",
            validator=lambda value: bool(
                re.fullmatch(r"[a-z0-9]+\.[a-z0-9]+", value)
            ),
        ),
        VariableDefinition(
            name="database_password",
            expected_type=str,
            required=True,
            sensitive=True,
            validator=lambda value: len(value) >= 12,
        ),
    ]

    manager = VariableManager(variable_definitions)

    engine = InfrastructureEngine(
        provider=ProviderConfig(
            name="aws",
            region="ap-south-1",
            version="5.80.0",
        ),
        variables=manager,
        supplied_variables={
            "environment": "development",
            "instance_count": 2,
            "instance_type": "t3.small",
            "database_password": "SecurePassword123!",
        },
    )

    print("\n1. Provider configuration")
    print(asdict(engine.provider))

    print("\n2. Resolved variables")
    print(manager.display(engine.variables))

    engine.add_resource(
        Resource(
            name="network",
            resource_type="aws_vpc",
            attributes={
                "cidr_block": "10.0.0.0/16",
                "environment": "{environment}",
            },
        )
    )

    engine.add_resource(
        Resource(
            name="application",
            resource_type="aws_instance",
            attributes={
                "instance_type": "{instance_type}",
                "count": "{instance_count}",
                "environment": "{environment}",
                "simulate_failure": False,
            },
            depends_on=["aws_vpc.network"],
        )
    )

    engine.add_resource(
        Resource(
            name="database",
            resource_type="aws_db_instance",
            attributes={
                "engine": "postgres",
                "environment": "{environment}",
                "password_configured": True,
            },
            depends_on=["aws_vpc.network"],
        )
    )

    print("\n3. Dependency execution order")
    for address in engine.execution_order():
        print(f"  -> {address}")

    print("\n4. Infrastructure plan")
    plan = engine.plan()

    for entry in plan:
        print(
            f"{entry.action.value.upper():12} "
            f"{entry.address}: {entry.changes}"
        )

    print("\n5. Apply infrastructure")
    engine.apply(plan)

    for address, record in engine.state.records.items():
        print(
            f"{address}: ID={record.resource_id}, "
            f"provider={record.provider}"
        )

    print("\n6. Evaluate outputs")
    outputs = engine.evaluate_outputs(
        {
            "vpc_cidr": ("aws_vpc.network", "cidr_block"),
            "application_type": (
                "aws_instance.application",
                "instance_type",
            ),
        }
    )

    print(json.dumps(outputs, indent=2))

    print("\n7. Second plan")
    for entry in engine.plan():
        print(f"{entry.action.value.upper():12} {entry.address}")

    print("\n8. Drift detection")
    desired = {
        address: resource
        for address, resource in engine.resources.items()
    }

    print(engine.state.detect_drift(desired))

    print("\n9. Invalid variable test")
    try:
        manager.resolve({
            "environment": "invalid",
            "instance_count": 100,
            "instance_type": "t3.small",
            "database_password": "short",
        })
    except ValidationError as error:
        print(f"Expected validation failure: {error}")

    print("\n10. Circular dependency test")
    cyclic = InfrastructureEngine(
        engine.provider,
        manager,
        engine.variables,
    )

    cyclic.add_resource(
        Resource(
            "first",
            "aws_instance",
            {},
            depends_on=["aws_instance.second"],
        )
    )

    cyclic.add_resource(
        Resource(
            "second",
            "aws_instance",
            {},
            depends_on=["aws_instance.first"],
        )
    )

    try:
        cyclic.execution_order()
    except DependencyError as error:
        print(f"Expected dependency failure: {error}")

    print("\n11. State serialization")
    print(engine.state.serialize())

    print("\nTerraform fundamentals demonstration completed.")


if __name__ == "__main__":
    demonstrate()
