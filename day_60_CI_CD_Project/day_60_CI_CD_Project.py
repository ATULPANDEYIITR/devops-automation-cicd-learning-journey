#!/usr/bin/env python3
"""
Self-contained CI/CD demonstration:
Build -> Test -> Scan -> Package -> Dockerize

Requires Python 3.10 or later. Docker is optional and is invoked only
when --docker is supplied.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import re
import shutil
import subprocess
import sys
import zipfile
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Callable


APP_SOURCE = r'''
import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


class InventoryStore:
    """Thread-safe inventory storage with strict input validation."""

    SKU_PATTERN = re.compile(r"[A-Z0-9][A-Z0-9-]{0,31}")

    def __init__(self):
        self._items = {}
        self._lock = threading.RLock()

    def add(self, sku: str, quantity: int) -> None:
        if not isinstance(sku, str) or not self.SKU_PATTERN.fullmatch(sku):
            raise ValueError("SKU must contain 1-32 uppercase letters, digits or hyphens")
        if isinstance(quantity, bool) or not isinstance(quantity, int) or quantity <= 0:
            raise ValueError("Quantity must be a positive integer")

        with self._lock:
            if sku in self._items:
                raise ValueError(f"SKU already exists: {sku}")
            self._items[sku] = quantity

    def list_items(self):
        with self._lock:
            return [
                {"sku": sku, "quantity": quantity}
                for sku, quantity in sorted(self._items.items())
            ]


def create_handler(store: InventoryStore):
    class InventoryHandler(BaseHTTPRequestHandler):
        def _send_json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            route = urlparse(self.path).path

            if route == "/health":
                self._send_json(200, {"status": "ok"})
            elif route == "/inventory":
                self._send_json(200, {"items": store.list_items()})
            else:
                self._send_json(404, {"error": "not_found"})

        def log_message(self, format_string, *args):
            # Avoid logging potentially sensitive request data.
            return

    return InventoryHandler


def main():
    port_text = os.environ.get("PORT", "8080")
    try:
        port = int(port_text)
    except ValueError as exc:
        raise SystemExit("PORT must be an integer") from exc

    if not 1 <= port <= 65535:
        raise SystemExit("PORT must be between 1 and 65535")

    store = InventoryStore()
    store.add("SKU-100", 25)
    store.add("SKU-200", 12)

    server = ThreadingHTTPServer(
        ("0.0.0.0", port),
        create_handler(store),
    )

    try:
        print(f"Inventory service listening on port {port}", flush=True)
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
'''.lstrip()


TEST_SOURCE = r'''
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from service import InventoryStore


class InventoryStoreTests(unittest.TestCase):
    def setUp(self):
        self.store = InventoryStore()

    def test_add_and_list_items(self):
        self.store.add("SKU-20", 5)
        self.store.add("SKU-10", 8)
        self.assertEqual(
            self.store.list_items(),
            [
                {"sku": "SKU-10", "quantity": 8},
                {"sku": "SKU-20", "quantity": 5},
            ],
        )

    def test_duplicate_sku_is_rejected(self):
        self.store.add("SKU-10", 5)
        with self.assertRaises(ValueError):
            self.store.add("SKU-10", 7)

    def test_invalid_sku_is_rejected(self):
        for sku in ("", "lowercase", "INVALID SKU", "A" * 33):
            with self.subTest(sku=sku):
                with self.assertRaises(ValueError):
                    self.store.add(sku, 1)

    def test_invalid_quantity_is_rejected(self):
        for quantity in (0, -1, True, 2.5, "5"):
            with self.subTest(quantity=quantity):
                with self.assertRaises(ValueError):
                    self.store.add("SKU-10", quantity)

    def test_empty_inventory(self):
        self.assertEqual(self.store.list_items(), [])


if __name__ == "__main__":
    unittest.main()
'''.lstrip()


DOCKERFILE = """\
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

WORKDIR /app

COPY --chown=10001:10001 src/ ./src/

USER 10001:10001

EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \\
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2)"

ENTRYPOINT ["python", "src/service.py"]
"""


class StageStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class StageResult:
    name: str
    status: StageStatus
    started_at: str
    finished_at: str
    duration_seconds: float
    detail: str


@dataclass
class PipelineConfig:
    workspace: Path
    docker_enabled: bool
    image_tag: str


class PipelineError(RuntimeError):
    pass


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_safe_workspace(root: Path) -> Path:
    root = root.expanduser().resolve()

    if root.exists() and root.is_symlink():
        raise PipelineError("Workspace must not be a symbolic link")

    root.mkdir(parents=True, exist_ok=True)
    marker = root / ".ci_cd_demo_workspace"

    if marker.exists():
        if not marker.is_file():
            raise PipelineError("Workspace marker is not a regular file")
    elif any(root.iterdir()):
        raise PipelineError(
            f"Refusing to use a non-empty directory without a workspace marker: {root}"
        )
    else:
        marker.write_text("Managed by the CI/CD demonstration pipeline.\n", encoding="utf-8")

    return root


def prepare_project(root: Path) -> None:
    """Create a repeatable sample project without touching unrelated directories."""

    for directory in ("build", "dist", "docker-context"):
        target = root / directory
        if target.exists():
            if target.is_symlink():
                raise PipelineError(f"Refusing to remove symbolic link: {target}")
            shutil.rmtree(target)

    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "tests").mkdir(parents=True, exist_ok=True)

    (root / "src" / "service.py").write_text(APP_SOURCE, encoding="utf-8")
    (root / "tests" / "test_service.py").write_text(TEST_SOURCE, encoding="utf-8")


def run_command(
    arguments: list[str],
    cwd: Path,
    timeout: int = 60,
) -> str:
    """Run a process without a shell and return its captured output."""

    try:
        completed = subprocess.run(
            arguments,
            cwd=cwd,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise PipelineError(
            f"Command timed out after {timeout} seconds: {arguments[0]}"
        ) from exc
    except OSError as exc:
        raise PipelineError(f"Unable to execute {arguments[0]}: {exc}") from exc

    output = (completed.stdout or "") + (completed.stderr or "")

    if completed.returncode != 0:
        raise PipelineError(
            f"Command failed with exit code {completed.returncode}: "
            f"{' '.join(arguments)}\n{output[-6000:]}"
        )

    return output[-6000:]


def build_stage(config: PipelineConfig) -> str:
    root = config.workspace
    output = run_command(
        [sys.executable, "-m", "compileall", "-q", "src", "tests"],
        root,
        timeout=60,
    )
    return "Python source and test modules compiled successfully. " + output.strip()


def test_stage(config: PipelineConfig) -> str:
    output = run_command(
        [
            sys.executable,
            "-m",
            "unittest",
            "discover",
            "-s",
            "tests",
            "-v",
        ],
        config.workspace,
        timeout=60,
    )
    return output.strip() or "Unit tests completed successfully."


def scan_stage(config: PipelineConfig) -> str:
    """
    Perform a small static policy scan.

    This is a learning example, not a substitute for dependency analysis,
    secret scanning, SAST or container vulnerability scanning.
    """

    root = config.workspace
    findings: list[str] = []
    secret_pattern = re.compile(
        r"""(?i)(api[_-]?key|password|secret|access[_-]?token)\s*[:=]\s*['"][^'"]{8,}"""
    )

    forbidden_calls = {"eval", "exec", "compile"}

    source_files = sorted((root / "src").glob("*.py"))
    if not source_files:
        raise PipelineError("Security scan found no Python source files")

    for source_file in source_files:
        text = source_file.read_text(encoding="utf-8")
        try:
            tree = ast.parse(text, filename=str(source_file))
        except SyntaxError as exc:
            findings.append(f"{source_file.name}:{exc.lineno}: invalid Python syntax")
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                function = node.func
                if isinstance(function, ast.Name) and function.id in forbidden_calls:
                    findings.append(
                        f"{source_file.name}:{node.lineno}: prohibited call {function.id}"
                    )

                if (
                    isinstance(function, ast.Attribute)
                    and isinstance(function.value, ast.Name)
                    and function.value.id in {"os", "subprocess"}
                    and function.attr in {"system", "popen", "Popen", "run", "call"}
                ):
                    findings.append(
                        f"{source_file.name}:{node.lineno}: process execution requires review"
                    )

        for line_number, line in enumerate(text.splitlines(), start=1):
            if secret_pattern.search(line):
                findings.append(
                    f"{source_file.name}:{line_number}: possible hard-coded credential"
                )

    if findings:
        raise PipelineError("Static security policy failed:\n" + "\n".join(findings))

    return f"Scanned {len(source_files)} source file(s); no configured policy violations."


def package_stage(config: PipelineConfig) -> str:
    root = config.workspace
    package_dir = root / "dist" / "package"
    package_dir.mkdir(parents=True, exist_ok=True)

    source = root / "src" / "service.py"
    destination = package_dir / "src" / "service.py"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)

    manifest = {
        "application": "inventory-health-service",
        "version": "1.0.0",
        "created_at": utc_now(),
        "files": [
            {
                "path": "src/service.py",
                "sha256": sha256_file(destination),
                "size_bytes": destination.stat().st_size,
            }
        ],
    }

    manifest_path = package_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )

    archive_path = root / "dist" / "inventory-health-service-1.0.0.zip"

    # Fixed timestamps and sorted paths make the ZIP contents reproducible.
    with zipfile.ZipFile(
        archive_path,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for file_path in sorted(
            path for path in package_dir.rglob("*") if path.is_file()
        ):
            relative_name = file_path.relative_to(package_dir).as_posix()
            info = zipfile.ZipInfo(relative_name, date_time=(2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, file_path.read_bytes())

    return (
        f"Created release package {archive_path.name}; "
        f"SHA-256: {sha256_file(archive_path)}"
    )


def dockerize_stage(config: PipelineConfig) -> str:
    root = config.workspace
    package_dir = root / "dist" / "package"
    context = root / "docker-context"

    if not (package_dir / "src" / "service.py").is_file():
        raise PipelineError("Docker context cannot be created without a package")

    shutil.copytree(package_dir, context)
    (context / "Dockerfile").write_text(DOCKERFILE, encoding="utf-8")

    if not config.docker_enabled:
        return f"Docker context and Dockerfile created at {context}; image build not requested."

    if shutil.which("docker") is None:
        raise PipelineError("Docker was requested but the docker executable was not found")

    output = run_command(
        [
            "docker",
            "build",
            "--tag",
            config.image_tag,
            str(context),
        ],
        root,
        timeout=600,
    )

    return f"Built Docker image {config.image_tag}.\n{output.strip()}"


class Pipeline:
    def __init__(self, config: PipelineConfig):
        self.config = config
        self.results: list[StageResult] = []

        self.stages: list[tuple[str, Callable[[PipelineConfig], str]]] = [
            ("Build", build_stage),
            ("Test", test_stage),
            ("Scan", scan_stage),
            ("Package", package_stage),
            ("Dockerize", dockerize_stage),
        ]

    def execute_stage(
        self,
        name: str,
        action: Callable[[PipelineConfig], str],
    ) -> StageResult:
        started = datetime.now(timezone.utc)
        try:
            detail = action(self.config)
            status = StageStatus.SUCCEEDED
        except Exception as exc:
            detail = f"{type(exc).__name__}: {exc}"
            status = StageStatus.FAILED

        finished = datetime.now(timezone.utc)
        result = StageResult(
            name=name,
            status=status,
            started_at=started.isoformat(),
            finished_at=finished.isoformat(),
            duration_seconds=round((finished - started).total_seconds(), 3),
            detail=detail,
        )
        self.results.append(result)

        print(f"[{result.status.value.upper():9}] {name}: {detail}")

        return result

    def run(self) -> bool:
        for name, action in self.stages:
            result = self.execute_stage(name, action)
            if result.status == StageStatus.FAILED:
                for skipped_name, _ in self.stages[
                    len(self.results):
                ]:
                    skipped = StageResult(
                        name=skipped_name,
                        status=StageStatus.SKIPPED,
                        started_at="",
                        finished_at="",
                        duration_seconds=0.0,
                        detail="A preceding required stage failed.",
                    )
                    self.results.append(skipped)
                    print(f"[SKIPPED  ] {skipped_name}: preceding stage failed")
                return False

        return True


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a local Build-Test-Scan-Package-Dockerize pipeline."
    )
    parser.add_argument(
        "--workspace",
        type=Path,
        default=Path("ci_cd_python_workspace"),
        help="Dedicated workspace directory.",
    )
    parser.add_argument(
        "--docker",
        action="store_true",
        help="Build the Docker image after creating its context.",
    )
    parser.add_argument(
        "--tag",
        default="inventory-health-service:1.0.0",
        help="Docker image tag.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()

    if not re.fullmatch(
        r"[a-z0-9][a-z0-9._/-]*:[a-zA-Z0-9][a-zA-Z0-9._-]*",
        args.tag,
    ):
        print("Invalid Docker image tag.", file=sys.stderr)
        return 2

    try:
        workspace = ensure_safe_workspace(args.workspace)
        prepare_project(workspace)

        config = PipelineConfig(
            workspace=workspace,
            docker_enabled=args.docker,
            image_tag=args.tag,
        )

        pipeline = Pipeline(config)
        success = pipeline.run()

        report = {
            "pipeline": "Build -> Test -> Scan -> Package -> Dockerize",
            "status": "succeeded" if success else "failed",
            "workspace": str(workspace),
            "stages": [
                {
                    **asdict(result),
                    "status": result.status.value,
                }
                for result in pipeline.results
            ],
        }

        report_path = workspace / "pipeline-report.json"
        report_path.write_text(
            json.dumps(report, indent=2) + "\n",
            encoding="utf-8",
        )

        print(f"\nPipeline report: {report_path}")
        return 0 if success else 1

    except Exception as exc:
        print(f"Pipeline initialization failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
