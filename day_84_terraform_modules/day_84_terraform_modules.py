#!/usr/bin/env python3
"""
Terraform Modules: Reusable Infrastructure Modules

A self-contained infrastructure module management simulator covering:
- Module definitions and reusable interfaces
- Semantic versioning and source pinning
- Input validation and output contracts
- Module composition and dependency resolution
- Dependency graph validation
- Infrastructure planning and state management
- Deployment simulation and drift detection
- Security and failure handling

Run:
    python terraform_modules.py
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ModuleError(Exception):
    """Base exception for module operations."""


class ValidationError(ModuleError):
    pass


class DependencyError(ModuleError):
    pass


class DeploymentError(ModuleError):
    pass


class ResourceAction(str, Enum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"
    NO_CHANGE = "no_change"


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, value: str) -> "Version":
        match = re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", value)
        if not match:
            raise ValidationError(f"Invalid semantic version: {value}")
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True)
class InputDefinition:
    name: str
    expected_type: type
    required: bool = True
    default: Any = None
    sensitive: bool = False
    description: str = ""

    def validate(self, value: Any) -> None:
        if value is None:
            if self.required:
                raise ValidationError(f"Required input '{self.name}' is missing.")
            return

        if self.expected_type is int and isinstance(value, bool):
            raise ValidationError(f"Input '{self.name}' must be an integer.")

        if not isinstance(value, self.expected_type):
            raise ValidationError(
                f"Input '{self.name}' must be {self.expected_type.__name__}."
            )


@dataclass(frozen=True)
class OutputDefinition:
    name: str
    description: str
    sensitive: bool = False


@dataclass(frozen=True)
class ResourceDefinition:
    name: str
    resource_type: str
    configuration: dict[str, Any]
    depends_on: tuple[str, ...] = ()


@dataclass
class ModuleSpec:
    name: str
    version: Version
    source: str
    inputs: dict[str, InputDefinition]
    outputs: dict[str, OutputDefinition]
    resources: list[ResourceDefinition]
    dependencies: list[str] = field(default_factory=list)

    def validate_inputs(self, supplied: dict[str, Any]) -> dict[str, Any]:
        unknown = set(supplied) - set(self.inputs)

        if unknown:
            raise ValidationError(
                f"Unknown inputs for {self.name}: {sorted(unknown)}"
            )

        resolved = {}

        for name, definition in self.inputs.items():
            value = supplied.get(name, definition.default)

            if value is None and not definition.required:
                resolved[name] = None
                continue

            definition.validate(value)
            resolved[name] = value

        return resolved

    def fingerprint(self) -> str:
        """Create a deterministic identifier for the module definition."""
        content = {
            "name": self.name,
            "version": str(self.version),
            "source": self.source,
            "inputs": sorted(self.inputs),
            "outputs": sorted(self.outputs),
            "resources": [
                {
                    "name": resource.name,
                    "type": resource.resource_type,
                    "configuration": resource.configuration,
                    "dependencies": resource.depends_on,
                }
                for resource in self.resources
            ],
        }

        serialized = json.dumps(content, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()


@dataclass(frozen=True)
class ModuleCall:
    instance_name: str
    module_name: str
    version_constraint: str
    inputs: dict[str, Any]


@dataclass
class PlannedResource:
    address: str
    desired_configuration: dict[str, Any]
    action: ResourceAction
    current_configuration: dict[str, Any] | None = None


@dataclass
class InfrastructureState:
    resources: dict[str, dict[str, Any]] = field(default_factory=dict)
    outputs: dict[str, Any] = field(default_factory=dict)
    revision: int = 0


class ModuleCatalog:
    """Registry for reusable module versions."""

    def __init__(self):
        self.modules: dict[str, dict[Version, ModuleSpec]] = {}

    def register(self, module: ModuleSpec) -> None:
        if not module.name or not module.source:
            raise ValidationError("Module name and source are required.")

        versions = self.modules.setdefault(module.name, {})

        if module.version in versions:
            raise ValidationError(
                f"Module {module.name}@{module.version} already exists."
            )

        versions[module.version] = module

    def resolve(self, name: str, constraint: str) -> ModuleSpec:
        if name not in self.modules:
            raise ValidationError(f"Module '{name}' does not exist.")

        available = sorted(self.modules[name], reverse=True)

        if constraint.startswith("="):
            requested = Version.parse(constraint[1:].strip())
            if requested not in available:
                raise ValidationError(f"Version {requested} is unavailable.")
            return self.modules[name][requested]

        match = re.fullmatch(r"~>\s*(\d+)\.(\d+)(?:\.(\d+))?", constraint)

        if match:
            major, minor, patch = map(
                lambda value: int(value) if value is not None else 0,
                match.groups(),
            )

            candidates = [
                version for version in available
                if version.major == major
                and (
                    version.minor == minor
                    if match.group(3) is not None
                    else version.minor >= minor
                )
                and (
                    version.patch >= patch
                    if match.group(3) is not None
                    else True
                )
            ]

            if match.group(3) is not None:
                candidates = [
                    version for version in candidates
                    if version.minor == minor
                ]

            if candidates:
                return self.modules[name][max(candidates)]

        raise ValidationError(
            f"No compatible version of {name} for '{constraint}'."
        )


class DependencyResolver:
    """Topological sorting with circular dependency detection."""

    @staticmethod
    def resolve(graph: dict[str, list[str]]) -> list[str]:
        visited: set[str] = set()
        active: set[str] = set()
        result: list[str] = []

        def visit(node: str) -> None:
            if node in active:
                raise DependencyError(
                    f"Circular dependency detected at '{node}'."
                )

            if node in visited:
                return

            active.add(node)

            for dependency in graph.get(node, []):
                if dependency not in graph:
                    raise DependencyError(
                        f"Unknown dependency '{dependency}' of '{node}'."
                    )
                visit(dependency)

            active.remove(node)
            visited.add(node)
            result.append(node)

        for node in graph:
            visit(node)

        return result


class InfrastructureEngine:
    def __init__(self, catalog: ModuleCatalog):
        self.catalog = catalog
        self.state = InfrastructureState()

    def build_graph(
        self,
        calls: list[ModuleCall],
        resolved_modules: dict[str, ModuleSpec],
    ) -> dict[str, list[str]]:
        graph = {}

        for call in calls:
            module = resolved_modules[call.instance_name]

            dependencies = list(module.dependencies)

            for dependency in dependencies:
                if dependency not in resolved_modules:
                    raise DependencyError(
                        f"{call.instance_name} requires missing module "
                        f"'{dependency}'."
                    )

            graph[call.instance_name] = dependencies

        return graph

    def plan(self, calls: list[ModuleCall]) -> list[PlannedResource]:
        instances = [call.instance_name for call in calls]

        if len(instances) != len(set(instances)):
            raise ValidationError("Module instance names must be unique.")

        resolved_modules = {}
        resolved_inputs = {}

        for call in calls:
            module = self.catalog.resolve(
                call.module_name,
                call.version_constraint,
            )

            resolved_modules[call.instance_name] = module
            resolved_inputs[call.instance_name] = module.validate_inputs(
                call.inputs
            )

        graph = self.build_graph(calls, resolved_modules)
        order = DependencyResolver.resolve(graph)

        plans = []

        for instance in order:
            module = resolved_modules[instance]
            inputs = resolved_inputs[instance]

            for resource in module.resources:
                address = (
                    f"module.{instance}.{resource.resource_type}.{resource.name}"
                )

                desired = {
                    **resource.configuration,
                    "module_inputs": inputs,
                    "module_fingerprint": module.fingerprint(),
                }

                current = self.state.resources.get(address)

                if current is None:
                    action = ResourceAction.CREATE
                elif current != desired:
                    action = ResourceAction.UPDATE
                else:
                    action = ResourceAction.NO_CHANGE

                plans.append(
                    PlannedResource(
                        address=address,
                        desired_configuration=desired,
                        action=action,
                        current_configuration=current,
                    )
                )

        return plans

    def apply(self, plans: list[PlannedResource]) -> None:
        """Apply a plan atomically to the in-memory state."""

        staged = dict(self.state.resources)

        for plan in plans:
            if plan.action in (
                ResourceAction.CREATE,
                ResourceAction.UPDATE,
            ):
                staged[plan.address] = plan.desired_configuration

            elif plan.action == ResourceAction.DELETE:
                staged.pop(plan.address, None)

        self.state.resources = staged
        self.state.revision += 1

    def detect_drift(
        self,
        actual_resources: dict[str, dict[str, Any]],
    ) -> list[str]:
        drifted = []

        for address, desired in self.state.resources.items():
            actual = actual_resources.get(address)

            if actual != desired:
                drifted.append(address)

        return drifted

    def destroy(self, plans: list[PlannedResource]) -> None:
        staged = dict(self.state.resources)

        for plan in plans:
            staged.pop(plan.address, None)

        self.state.resources = staged
        self.state.revision += 1


def build_example() -> tuple[ModuleCatalog, list[ModuleCall]]:
    catalog = ModuleCatalog()

    network = ModuleSpec(
        name="network",
        version=Version.parse("1.2.0"),
        source="registry.example.com/platform/network",
        inputs={
            "environment": InputDefinition("environment", str),
            "cidr": InputDefinition("cidr", str),
            "region": InputDefinition("region", str),
        },
        outputs={
            "network_id": OutputDefinition("network_id", "Network identifier"),
        },
        resources=[
            ResourceDefinition(
                name="main",
                resource_type="aws_vpc",
                configuration={
                    "enable_dns_support": True,
                    "enable_dns_hostnames": True,
                },
            )
        ],
    )

    application = ModuleSpec(
        name="application",
        version=Version.parse("2.1.0"),
        source="registry.example.com/platform/application",
        inputs={
            "environment": InputDefinition("environment", str),
            "instance_type": InputDefinition(
                "instance_type", str, default="t3.small", required=False
            ),
        },
        outputs={
            "application_id": OutputDefinition(
                "application_id", "Application identifier"
            )
        },
        resources=[
            ResourceDefinition(
                name="web",
                resource_type="aws_instance",
                configuration={
                    "monitoring": True,
                    "encrypted_volume": True,
                },
            )
        ],
        dependencies=["network"],
    )

    catalog.register(network)
    catalog.register(application)

    calls = [
        ModuleCall(
            instance_name="network",
            module_name="network",
            version_constraint="~> 1.2.0",
            inputs={
                "environment": "production",
                "cidr": "10.20.0.0/16",
                "region": "ap-south-1",
            },
        ),
        ModuleCall(
            instance_name="application",
            module_name="application",
            version_constraint="= 2.1.0",
            inputs={
                "environment": "production",
                "instance_type": "t3.medium",
            },
        ),
    ]

    return catalog, calls


def main() -> None:
    catalog, calls = build_example()
    engine = InfrastructureEngine(catalog)

    print("TERRAFORM MODULE MANAGEMENT SIMULATION")
    print("=" * 55)

    plans = engine.plan(calls)

    print("\nInfrastructure plan:")

    for plan in plans:
        print(f"{plan.action.value.upper():12} {plan.address}")

    engine.apply(plans)

    print(f"\nState revision: {engine.state.revision}")
    print(f"Managed resources: {len(engine.state.resources)}")

    # A second plan should contain no changes.
    second_plan = engine.plan(calls)

    print("\nSecond plan:")

    for plan in second_plan:
        print(f"{plan.action.value.upper():12} {plan.address}")

    # Simulate an externally modified resource.
    actual = dict(engine.state.resources)

    address = next(iter(actual))
    actual[address] = {**actual[address], "enable_dns_support": False}

    print("\nDrift detection:")
    print(engine.detect_drift(actual))

    # Validation demonstration.
    try:
        catalog.resolve("network", "= 9.0.0")
    except ValidationError as error:
        print(f"\nExpected version error: {error}")

    try:
        DependencyResolver.resolve({
            "network": ["application"],
            "application": ["network"],
        })
    except DependencyError as error:
        print(f"Expected dependency error: {error}")

    print("\nAll demonstrations completed.")


if __name__ == "__main__":
    main()
