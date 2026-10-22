"""Execute one allowed target suite without importing MCP or LangGraph."""

import os
import subprocess
from uuid import uuid4

from . import storage
from .settings import load_settings

SUITES = ("unit", "api", "ui")
MARKERS = ("smoke", "regression")


def _decode_output(value: str | bytes | None) -> str:
    """Normalize partial subprocess output, including timeout byte strings."""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def run_tests(suite: str = "unit", marker: str | None = None) -> dict:
    """Run one Restful Booker suite once; only fixed suites and markers are accepted."""
    run_id = uuid4().hex
    folder = storage.run_directory(run_id)
    results_dir = folder / "allure-results"
    request = {"run_id": run_id, "suite": suite, "marker": marker}

    if suite not in SUITES:
        return {**request, "status": "launch_error", "error": f"Unknown suite: {suite}"}
    if marker is not None and marker not in MARKERS:
        return {**request, "status": "launch_error", "error": f"Unknown marker: {marker}"}

    command_suffix = ["-m", marker] if marker else []
    if suite == "ui":
        # Screenshots and traces belong to this run, not to a shared artifacts directory.
        command_suffix.append(f"--output={folder / 'playwright'}")

    try:
        settings = load_settings()
        project, python, timeout = settings.project, settings.python, settings.timeout
        results_dir.mkdir(parents=True, exist_ok=False)
        result = subprocess.run(
            [
                str(python),
                "-m",
                "pytest",
                f"tests/{suite}",
                "-q",
                f"--alluredir={results_dir}",
                *command_suffix,
            ],
            cwd=project,
            env={**os.environ, **settings.env} if settings.env else None,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        return {
            **request,
            "status": "timeout",
            "stdout": _decode_output(error.stdout),
            "stderr": _decode_output(error.stderr),
            "error": f"{suite.capitalize()} test execution exceeded {timeout} seconds",
        }
    except (OSError, ValueError) as error:
        return {**request, "status": "launch_error", "error": str(error)}

    return {
        **request,
        "status": "passed" if result.returncode == 0 else "unsuccessful",
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


def run_unit_tests() -> dict:
    """Run the Restful Booker framework unit tests and return their output."""
    return run_tests("unit")
