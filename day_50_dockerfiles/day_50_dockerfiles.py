from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import os
import shlex
import subprocess
import tempfile


class DockerfileError(ValueError):
    """Raised when a Dockerfile contains an invalid or unsafe instruction."""


@dataclass(frozen=True)
class DockerInstruction:
    keyword: str
    arguments: str
    line_number: int


@dataclass
class DockerfileModel:
    instructions: list[DockerInstruction] = field(default_factory=list)

    @property
    def base_image(self) -> str | None:
        for instruction in self.instructions:
            if instruction.keyword == "FROM":
                return instruction.arguments.split()[0]
        return None

    def instructions_by(self, keyword: str) -> list[DockerInstruction]:
        return [
            item
            for item in self.instructions
            if item.keyword == keyword.upper()
        ]


ALLOWED_INSTRUCTIONS = {
    "FROM",
    "RUN",
    "COPY",
    "CMD",
    "ENTRYPOINT",
    "ENV",
    "WORKDIR",
    "EXPOSE",
    "USER",
}


def parse_dockerfile(text: str) -> DockerfileModel:
    model = DockerfileModel()

    logical_lines: list[tuple[int, str]] = []
    buffer = ""
    start_line = 0

    for number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()

        if not line:
            continue

        if line.startswith("#") and not buffer:
            continue

        if not buffer:
            start_line = number

        if line.endswith("\\"):
            buffer += line[:-1].rstrip() + " "
            continue

        buffer += line
        logical_lines.append((start_line, buffer))
        buffer = ""

    if buffer:
        raise DockerfileError("Dockerfile ends with an incomplete continuation.")

    for line_number, line in logical_lines:
        parts = line.split(None, 1)
        keyword = parts[0].upper()
        arguments = parts[1].strip() if len(parts) == 2 else ""

        if keyword not in ALLOWED_INSTRUCTIONS:
            raise DockerfileError(
                f"Line {line_number}: unsupported instruction {keyword!r}."
            )

        if not arguments:
            raise DockerfileError(
                f"Line {line_number}: {keyword} requires arguments."
            )

        model.instructions.append(
            DockerInstruction(keyword, arguments, line_number)
        )

    validate_model(model)
    return model


def validate_model(model: DockerfileModel) -> None:
    from_instructions = model.instructions_by("FROM")

    if not from_instructions:
        raise DockerfileError("A Dockerfile must contain FROM.")

    if len(from_instructions) > 1:
        raise DockerfileError(
            "This learning model expects one FROM instruction."
        )

    first_instruction = model.instructions[0]
    if first_instruction.keyword != "FROM":
        raise DockerfileError("FROM must be the first effective instruction.")

    env_values = model.instructions_by("ENV")
    for env in env_values:
        tokens = shlex.split(env.arguments)
        if not tokens:
            raise DockerfileError(
                f"Line {env.line_number}: ENV has no variables."
            )

        if "=" not in env.arguments and len(tokens) < 2:
            raise DockerfileError(
                f"Line {env.line_number}: invalid ENV syntax."
            )

    for copy in model.instructions_by("COPY"):
        if copy.arguments.startswith("--from="):
            raise DockerfileError(
                f"Line {copy.line_number}: multi-stage COPY is outside this model."
            )


def show_instruction_roles(model: DockerfileModel) -> None:
    descriptions = {
        "FROM": "Selects the base image and starts the build stage.",
        "RUN": "Executes commands while constructing an image layer.",
        "COPY": "Copies build-context files into the image.",
        "ENV": "Defines environment variables available in image/container execution.",
        "CMD": "Defines the default command and arguments.",
        "ENTRYPOINT": "Defines the executable that normally remains fixed.",
    }

    for instruction in model.instructions:
        description = descriptions.get(
            instruction.keyword,
            "Additional Dockerfile configuration."
        )
        print(
            f"Line {instruction.line_number}: "
            f"{instruction.keyword:<11} {instruction.arguments}"
        )
        print(f"  {description}")


def compare_startup_behavior() -> None:
    print("\nCMD versus ENTRYPOINT:")

    examples = [
        (
            "CMD [\"python\", \"app.py\"]",
            "The command is a default and can normally be replaced at runtime."
        ),
        (
            "ENTRYPOINT [\"python\", \"app.py\"]",
            "The executable is fixed; runtime arguments are normally appended."
        ),
    ]

    for syntax, behavior in examples:
        print(f"  {syntax}")
        print(f"    {behavior}")


def build_safe_environment() -> dict[str, str]:
    """Create an explicit environment instead of blindly copying process state."""
    safe = {
        "APP_ENV": "production",
        "PYTHONUNBUFFERED": "1",
    }

    for key, value in safe.items():
        if not key.replace("_", "").isalnum():
            raise DockerfileError(f"Invalid environment variable name: {key}")

        if "\n" in value or "\r" in value:
            raise DockerfileError(
                f"Environment value for {key} contains a newline."
            )

    return safe


def demonstrate_copy_validation(context: Path) -> None:
    """COPY can only access files inside the build context."""
    context = context.resolve()

    candidates = [
        context / "app.py",
        context.parent / "secret.txt",
    ]

    print("\nBuild-context validation:")

    for candidate in candidates:
        resolved = candidate.resolve()
        try:
            resolved.relative_to(context)
            allowed = True
        except ValueError:
            allowed = False

        status = "allowed" if allowed else "rejected"
        print(f"  {candidate}: {status}")


def validate_production_dockerfile(text: str) -> None:
    model = parse_dockerfile(text)

    if model.base_image is None:
        raise DockerfileError("No base image was found.")

    entrypoint = model.instructions_by("ENTRYPOINT")
    cmd = model.instructions_by("CMD")

    if not entrypoint and not cmd:
        raise DockerfileError(
            "The image should define CMD or ENTRYPOINT for this example."
        )

    if any("password" in item.arguments.lower()
           or "secret" in item.arguments.lower()
           for item in model.instructions_by("ENV")):
        raise DockerfileError(
            "Do not place passwords or secrets in Dockerfile ENV instructions."
        )

    print("\nProduction validation:")
    print(f"  Base image: {model.base_image}")
    print(f"  RUN instructions: {len(model.instructions_by('RUN'))}")
    print(f"  COPY instructions: {len(model.instructions_by('COPY'))}")
    print(f"  ENV instructions: {len(model.instructions_by('ENV'))}")
    print(f"  CMD instructions: {len(cmd)}")
    print(f"  ENTRYPOINT instructions: {len(entrypoint)}")
    print("  Secret check: passed")


def main() -> None:
    dockerfile = r"""
FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 APP_ENV=production

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py .

ENTRYPOINT ["python", "app.py"]
CMD ["--port", "8000"]
""".strip()

    print("Dockerfile analysis")
    print("===================")

    try:
        model = parse_dockerfile(dockerfile)
        show_instruction_roles(model)
        validate_production_dockerfile(dockerfile)
    except DockerfileError as error:
        print(f"Validation error: {error}")
        return

    compare_startup_behavior()

    environment = build_safe_environment()
    print("\nRuntime environment:")
    for key, value in environment.items():
        print(f"  {key}={value}")

    with tempfile.TemporaryDirectory() as directory:
        context = Path(directory)
        (context / "app.py").write_text(
            'print("container started")\n',
            encoding="utf-8",
        )
        demonstrate_copy_validation(context)

    print("\nLayer and cache considerations:")
    print("  FROM establishes the base image.")
    print("  RUN creates filesystem changes that form image layers.")
    print("  COPY adds build-context content and participates in cache invalidation.")
    print("  ENV records image configuration used by later build steps and containers.")
    print("  CMD and ENTRYPOINT configure container startup rather than build-time execution.")

    print("\nSecurity considerations:")
    print("  Never put credentials directly in ENV or RUN commands.")
    print("  Keep the build context small and exclude secrets with .dockerignore.")
    print("  Prefer trusted, pinned or digest-referenced base images for controlled builds.")
    print("  Avoid unnecessary packages and commands in RUN layers.")

    print("\nOperational check:")
    print(f"  Current process platform: {os.name}")
    print("  Docker CLI execution is intentionally not required for this simulation.")
    print("  The parser and policy checks can therefore run without Docker installed.")


if __name__ == "__main__":
    main()
