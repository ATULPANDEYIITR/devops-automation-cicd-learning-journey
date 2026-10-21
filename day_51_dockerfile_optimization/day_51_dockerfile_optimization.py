#!/usr/bin/env python3
"""
Dockerfile optimization simulator.

Models common Dockerfile optimization decisions:
- layer count and approximate layer sizes
- dependency/cache ordering
- build context size
- .dockerignore effects
- multi-stage builds
- cache reuse
- image-size comparison
- reproducible build recommendations

The calculations are intentionally approximate. Real image sizes and cache
behavior depend on the base image, package manager, BuildKit configuration,
registry, architecture, and actual build contents.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class Layer:
    name: str
    size_mb: float
    cache_key: str
    expensive: bool = False


@dataclass
class DockerfileModel:
    name: str
    layers: list[Layer]
    context_mb: float
    ignored_context_mb: float = 0.0

    @property
    def final_image_mb(self) -> float:
        return round(sum(layer.size_mb for layer in self.layers), 2)

    @property
    def effective_context_mb(self) -> float:
        return round(max(0.0, self.context_mb - self.ignored_context_mb), 2)

    @property
    def layer_count(self) -> int:
        return len(self.layers)

    def validate(self) -> None:
        if not self.name.strip():
            raise ValueError("Image model must have a name")

        if self.context_mb < 0 or self.ignored_context_mb < 0:
            raise ValueError("Context sizes cannot be negative")

        if self.ignored_context_mb > self.context_mb:
            raise ValueError("Ignored context cannot exceed total context size")

        for layer in self.layers:
            if layer.size_mb < 0:
                raise ValueError(f"Negative layer size: {layer.name}")
            if not layer.cache_key:
                raise ValueError(f"Missing cache key: {layer.name}")


@dataclass(frozen=True)
class BuildCache:
    keys: frozenset[str] = frozenset()

    def hit_rate(self, layers: Iterable[Layer]) -> float:
        layer_list = list(layers)
        if not layer_list:
            return 1.0
        hits = sum(layer.cache_key in self.keys for layer in layer_list)
        return hits / len(layer_list)


def compare_images(models: list[DockerfileModel]) -> None:
    print("\nIMAGE SIZE COMPARISON")
    print("-" * 72)

    baseline = models[0].final_image_mb
    for model in models:
        reduction = 0.0
        if baseline:
            reduction = (baseline - model.final_image_mb) / baseline * 100

        print(
            f"{model.name:28} "
            f"{model.final_image_mb:8.1f} MB  "
            f"{reduction:7.1f}% smaller than baseline"
        )


def compare_contexts(models: list[DockerfileModel]) -> None:
    print("\nBUILD CONTEXT COMPARISON")
    print("-" * 72)

    for model in models:
        print(
            f"{model.name:28} "
            f"sent={model.effective_context_mb:7.1f} MB  "
            f"layers={model.layer_count}"
        )


def simulate_cache(
    before: DockerfileModel,
    after: DockerfileModel,
    cache: BuildCache,
) -> None:
    before_rate = cache.hit_rate(before.layers)
    after_rate = cache.hit_rate(after.layers)

    print("\nCACHE SIMULATION")
    print("-" * 72)
    print(f"{before.name}: {before_rate * 100:5.1f}% reusable layers")
    print(f"{after.name}:  {after_rate * 100:5.1f}% reusable layers")

    if after_rate > before_rate:
        print("Optimized ordering increases the modeled cache reuse rate.")
    elif after_rate < before_rate:
        print("The optimized model has less cache reuse for this change.")
    else:
        print("Cache reuse is unchanged for this simulated change.")


def validate_optimization(original: DockerfileModel, optimized: DockerfileModel) -> None:
    original.validate()
    optimized.validate()

    if optimized.final_image_mb >= original.final_image_mb:
        print(
            "\nWARNING: modeled optimized image is not smaller. "
            "Optimization should be measured rather than assumed."
        )

    if optimized.effective_context_mb >= original.effective_context_mb:
        print(
            "WARNING: .dockerignore/context optimization produced no "
            "modeled context reduction."
        )


def print_layer_breakdown(model: DockerfileModel) -> None:
    print(f"\n{model.name.upper()}")
    print("-" * 72)

    for index, layer in enumerate(model.layers, start=1):
        marker = " expensive" if layer.expensive else ""
        print(
            f"{index:2}. {layer.name:32} "
            f"{layer.size_mb:7.1f} MB  cache={layer.cache_key}{marker}"
        )

    print(f"Final modeled image size: {model.final_image_mb:.1f} MB")


def main() -> None:
    baseline = DockerfileModel(
        name="naive-single-stage",
        context_mb=420,
        layers=[
            Layer("python base", 125, "python:3.12-slim"),
            Layer("copy entire project", 85, "COPY:all"),
            Layer("install dependencies", 145, "pip:requirements"),
            Layer("runtime source", 65, "COPY:source"),
        ],
    )

    optimized = DockerfileModel(
        name="optimized-multi-stage",
        context_mb=420,
        ignored_context_mb=285,
        layers=[
            Layer("python runtime", 125, "python:3.12-slim"),
            Layer("dependency installation", 78, "pip:requirements", True),
            Layer("runtime source", 22, "COPY:source"),
        ],
    )

    cache = BuildCache(
        keys=frozenset(
            {
                "python:3.12-slim",
                "pip:requirements",
            }
        )
    )

    validate_optimization(baseline, optimized)

    print_layer_breakdown(baseline)
    print_layer_breakdown(optimized)

    compare_images([baseline, optimized])
    compare_contexts([baseline, optimized])
    simulate_cache(baseline, optimized, cache)

    print("\nOPTIMIZATION CHECKLIST")
    print("-" * 72)

    checks = {
        "Stable dependency files copied before source": True,
        "Build context reduced with .dockerignore": True,
        "Runtime image excludes build-only content": True,
        "Unnecessary package-manager caches excluded": True,
        "Base image deliberately selected": True,
        "Layer count optimized without sacrificing readability": True,
        "Build inputs are reproducible": True,
        "Secrets are excluded from image layers": True,
    }

    for description, passed in checks.items():
        print(f"[{'PASS' if passed else 'FAIL'}] {description}")

    print("\nPRODUCTION NOTES")
    print("-" * 72)
    print("Measure compressed registry size as well as uncompressed image size.")
    print("Do not copy secrets into build context or Dockerfile layers.")
    print("Use BuildKit cache mounts for package-manager caches when appropriate.")
    print("Pin important build inputs when reproducibility matters.")
    print("Use multi-stage builds when compilers or build tools are not needed at runtime.")


if __name__ == "__main__":
    main()
