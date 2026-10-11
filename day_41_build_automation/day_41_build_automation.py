#!/usr/bin/env python3
"""Build automation: compilation, dependency installation, and packaging.

Run:
    python build_automation.py
    python build_automation.py --workspace ./build_workspace
    python build_automation.py --keep-artifacts

The demonstration uses only the Python standard library. It creates a small
Python application, resolves and validates its declared dependencies, runs
automated tests, stages a distributable source archive, and writes a SHA-256
manifest. External packages are deliberately avoided so the example works
without network access.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import zipfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable


class BuildError(RuntimeError):
    """Raised when a required build operation fails."""


@dataclass
class BuildConfig:
    project_name: str = "inventory-engine"
    version: str = "1.0.0"
    workspace: Path = Path("build_workspace")
    keep_artifacts: bool = False
    run_tests: bool = True
    create_zip: bool = True
    create_tar_gz: bool = True
    source_directory: str = "src"
    tests_directory: str = "tests"
    build_directory: str = "build"
    distribution_directory: str = "dist"
    python_minimum: tuple[int, int] = (3, 10)


@dataclass
class BuildEvent:
    stage: str
    status: str
    duration_seconds: float
    details: str
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


@dataclass
class BuildReport:
    project: str
    version: str
    success: bool = False
    events: list[BuildEvent] = field(default_factory=list)
    artifacts: list[dict[str, object]] = field(default_factory=list)

    def add_event(
        self,
        stage: str,
        status: str,
        duration: float,
        details: str,
    ) -> None:
        self.events.append(
            BuildEvent(
                stage=stage,
                status=status,
                duration_seconds=round(duration, 4),
                details=details,
            )
        )

    def write(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(asdict(self), indent=2),
            encoding="utf-8",
        )


class BuildAutomation:
    """Coordinates dependency checks, tests, staging, and artifact creation."""

    def __init__(self, config: BuildConfig) -> None:
        self.config = config
        self.root = config.workspace.resolve()
        self.source = self.root / config.source_directory
        self.tests = self.root / config.tests_directory
        self.build = self.root / config.build_directory
        self.dist = self.root / config.distribution_directory
        self.report = BuildReport(config.project_name, config.version)

    def stage(self, name: str, operation: Callable[[], str]) -> str:
        """Record a stage's outcome and duration, then propagate failures."""
        start = time.perf_counter()
        try:
            result = operation()
        except Exception as exc:
            self.report.add_event(
                name,
                "failed",
                time.perf_counter() - start,
                f"{type(exc).__name__}: {exc}",
            )
            raise
        self.report.add_event(
            name,
            "passed",
            time.perf_counter() - start,
            result,
        )
        print(f"[PASS] {name}: {result}")
        return result

    def create_demo_project(self) -> str:
        """Create deterministic project inputs without overwriting user files."""
        if self.root.exists():
            existing_marker = self.root / ".build-automation-demo"
            if not existing_marker.exists():
                if any(self.root.iterdir()):
                    raise BuildError(
                        f"Workspace {self.root} is not an empty demo workspace. "
                        "Choose a new --workspace path."
                    )
            else:
                shutil.rmtree(self.root)

        self.source.mkdir(parents=True)
        self.tests.mkdir(parents=True)
        (self.root / ".build-automation-demo").write_text(
            "Managed by build_automation.py\n",
            encoding="utf-8",
        )

        application = '''"""Small inventory domain module."""


def calculate_stock(opening: int, received: int, shipped: int) -> int:
    """Return available stock after receipts and shipments."""
    for name, value in (
        ("opening", opening),
        ("received", received),
        ("shipped", shipped),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer")
        if value < 0:
            raise ValueError(f"{name} cannot be negative")

    available = opening + received - shipped
    if available < 0:
        raise ValueError("Shipment quantity exceeds available inventory")
    return available
'''
        (self.source / "inventory.py").write_text(
            application,
            encoding="utf-8",
        )

        test_source = '''import unittest

from inventory import calculate_stock


class InventoryTests(unittest.TestCase):
    def test_receipts_and_shipments(self):
        self.assertEqual(calculate_stock(100, 30, 45), 85)

    def test_zero_activity(self):
        self.assertEqual(calculate_stock(0, 0, 0), 0)

    def test_over_shipment_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_stock(10, 0, 11)

    def test_negative_quantity_is_rejected(self):
        with self.assertRaises(ValueError):
            calculate_stock(10, -1, 0)

    def test_boolean_is_not_an_integer_quantity(self):
        with self.assertRaises(TypeError):
            calculate_stock(True, 0, 0)


if __name__ == "__main__":
    unittest.main()
'''
        (self.tests / "test_inventory.py").write_text(
            test_source,
            encoding="utf-8",
        )

        (self.root / "README.md").write_text(
            "# Inventory Engine\n\n"
            "A small inventory calculation package built by an automated "
            "build pipeline.\n\n"
            "The example uses only the Python standard library.\n",
            encoding="utf-8",
        )

        (self.root / "requirements.txt").write_text(
            "# No third-party runtime dependencies.\n",
            encoding="utf-8",
        )

        (self.root / "pyproject.toml").write_text(
            "[build-system]\n"
            'requires = ["setuptools>=68"]\n'
            'build-backend = "setuptools.build_meta"\n\n'
            "[project]\n"
            'name = "inventory-engine-demo"\n'
            'version = "1.0.0"\n'
            'description = "Inventory calculation demonstration"\n'
            'requires-python = ">=3.10"\n'
            'dependencies = []\n\n'
            "[tool.setuptools]\n"
            'package-dir = {"" = "src"}\n'
            'py-modules = ["inventory"]\n',
            encoding="utf-8",
        )

        return f"Created source, tests, and project metadata in {self.root}"

    def validate_environment(self) -> str:
        if sys.version_info < self.config.python_minimum:
            required = ".".join(map(str, self.config.python_minimum))
            raise BuildError(f"Python {required} or later is required")

        if not self.source.is_dir():
            raise BuildError("Source directory is missing")

        if not self.tests.is_dir():
            raise BuildError("Tests directory is missing")

        return (
            f"Python {platform.python_version()}, "
            f"{platform.system()}, executable {sys.executable}"
        )

    def install_dependencies(self) -> str:
        """Validate dependency declarations and install only declared packages.

        The sample has no third-party runtime dependencies. A production
        pipeline should normally create a virtual environment and install
        pinned dependencies from a lock file or trusted package index.
        """
        requirements = self.root / "requirements.txt"
        if not requirements.is_file():
            raise BuildError("requirements.txt is missing")

        entries = [
            line.strip()
            for line in requirements.read_text(encoding="utf-8").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]

        if entries:
            venv = self.build / "venv"
            subprocess.run(
                [sys.executable, "-m", "venv", str(venv)],
                check=True,
                capture_output=True,
                text=True,
            )
            if os.name == "nt":
                pip = venv / "Scripts" / "pip.exe"
            else:
                pip = venv / "bin" / "pip"

            subprocess.run(
                [str(pip), "install", "--requirement", str(requirements)],
                check=True,
                capture_output=True,
                text=True,
            )
            return f"Installed {len(entries)} declared requirement entries"

        return "Validated requirements.txt; no third-party packages required"

    def compile_python_sources(self) -> str:
        """Compile all Python files and fail the build on syntax errors."""
        import py_compile

        files = sorted(self.root.rglob("*.py"))
        if not files:
            raise BuildError("No Python source files found")

        for source_file in files:
            if any(part in {"build", "dist", "__pycache__"} for part in source_file.parts):
                continue
            py_compile.compile(str(source_file), doraise=True)

        return f"Compiled {len(files)} Python files"

    def run_tests(self) -> str:
        """Execute unittest discovery with an explicit source import path."""
        if not self.config.run_tests:
            return "Tests skipped by configuration"

        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(self.source) + os.pathsep + environment.get(
            "PYTHONPATH", ""
        )

        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "unittest",
                "discover",
                "-s",
                str(self.tests),
                "-v",
            ],
            cwd=self.root,
            env=environment,
            capture_output=True,
            text=True,
        )

        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)

        if result.returncode != 0:
            raise BuildError(f"Automated tests failed with exit code {result.returncode}")

        return "All discovered unit tests passed"

    def stage_release(self) -> Path:
        """Create an isolated staging tree so source artifacts remain untouched."""
        if self.build.exists():
            shutil.rmtree(self.build)
        self.build.mkdir(parents=True)

        release_name = f"{self.config.project_name}-{self.config.version}"
        stage = self.build / release_name
        stage.mkdir()

        shutil.copytree(self.source, stage / "src")
        shutil.copytree(self.tests, stage / "tests")
        for filename in ("README.md", "requirements.txt", "pyproject.toml"):
            shutil.copy2(self.root / filename, stage / filename)

        return stage

    @staticmethod
    def calculate_sha256(path: Path) -> str:
        """Hash large artifacts in chunks instead of reading them all at once."""
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def package_release(self, stage: Path) -> str:
        self.dist.mkdir(parents=True, exist_ok=True)
        release_name = f"{self.config.project_name}-{self.config.version}"
        created: list[Path] = []

        if self.config.create_zip:
            archive = self.dist / f"{release_name}.zip"
            with zipfile.ZipFile(
                archive,
                mode="w",
                compression=zipfile.ZIP_DEFLATED,
                compresslevel=9,
            ) as output:
                for file_path in sorted(stage.rglob("*")):
                    if file_path.is_file():
                        output.write(
                            file_path,
                            arcname=str(Path(release_name) / file_path.relative_to(stage)),
                        )
            created.append(archive)

        if self.config.create_tar_gz:
            archive = self.dist / f"{release_name}.tar.gz"
            with tarfile.open(archive, mode="w:gz") as output:
                output.add(stage, arcname=release_name, recursive=True)
            created.append(archive)

        for artifact in created:
            self.report.artifacts.append(
                {
                    "name": artifact.name,
                    "size_bytes": artifact.stat().st_size,
                    "sha256": self.calculate_sha256(artifact),
                }
            )

        if not created:
            raise BuildError("No packaging format was enabled")

        return f"Created {len(created)} release archive(s) in {self.dist}"

    def write_checksums(self) -> str:
        manifest = self.dist / "SHA256SUMS.txt"
        lines = [
            f"{item['sha256']}  {item['name']}"
            for item in self.report.artifacts
        ]
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return f"Wrote checksum manifest {manifest.name}"

    def execute(self) -> int:
        started = time.perf_counter()
        try:
            self.stage("project initialization", self.create_demo_project)
            self.stage("environment validation", self.validate_environment)

            self.build.mkdir(parents=True, exist_ok=True)
            self.stage("dependency installation", self.install_dependencies)
            self.stage("source compilation", self.compile_python_sources)
            self.stage("automated tests", self.run_tests)

            release_stage = self.stage(
                "release staging",
                lambda: str(self.stage_release()),
            )
            self.stage(
                "artifact packaging",
                lambda: self.package_release(Path(release_stage)),
            )
            self.stage("checksum generation", self.write_checksums)

            self.report.success = True
            return_code = 0
        except (BuildError, OSError, subprocess.SubprocessError, SyntaxError) as exc:
            print(f"[FAIL] {exc}", file=sys.stderr)
            return_code = 1
        finally:
            report_path = self.root / "build-report.json"
            self.report.write(report_path)
            print(f"Build report: {report_path}")
            print(f"Total elapsed: {time.perf_counter() - started:.2f}s")

            if not self.config.keep_artifacts and return_code == 0:
                # Keep release archives and the report; remove only intermediate
                # bytecode caches from the staging tree.
                for cache in self.root.rglob("__pycache__"):
                    shutil.rmtree(cache, ignore_errors=True)

        return return_code


def parse_arguments() -> BuildConfig:
    parser = argparse.ArgumentParser(description="Demonstrate a build automation pipeline")
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("build_workspace"),
        help="Workspace used for generated source and build outputs",
    )
    parser.add_argument(
        "--keep-artifacts",
        action="store_true",
        help="Retain all intermediate files for inspection",
    )
    parser.add_argument(
        "--skip-tests",
        action="store_true",
        help="Skip automated tests; not recommended for release builds",
    )
    args = parser.parse_args()

    return BuildConfig(
        workspace=args.workspace,
        keep_artifacts=args.keep_artifacts,
        run_tests=not args.skip_tests,
    )


def main() -> int:
    config = parse_arguments()
    pipeline = BuildAutomation(config)
    return pipeline.execute()


if __name__ == "__main__":
    raise SystemExit(main())
