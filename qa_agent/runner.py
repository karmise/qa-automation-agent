"""Execute the configured unit suite without importing MCP or LangGraph."""

import subprocess
from uuid import uuid4

from . import storage
from .settings import load_settings


def _decode_output(value: str | bytes | None) -> str:
    """Normalize partial subprocess output, including timeout byte strings."""
    return value.decode("utf-8", errors="replace") if isinstance(value, bytes) else value or ""


def run_unit_tests() -> dict:
    """Run the Restful Booker framework unit tests and return their output."""
    run_id = uuid4().hex
    results_dir = storage.run_directory(run_id) / "allure-results"

    try:
        settings = load_settings()
        project, python, timeout = settings.project, settings.python, settings.timeout
        results_dir.mkdir(parents=True, exist_ok=False)
        result = subprocess.run(
            [str(python), "-m", "pytest", "tests/unit", "-q", f"--alluredir={results_dir}"],
            cwd=project,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        return {
            "status": "timeout",
            "stdout": _decode_output(error.stdout),
            "stderr": _decode_output(error.stderr),
            "error": f"Unit test execution exceeded {timeout} seconds",
            "run_id": run_id,
        }
    except (OSError, ValueError) as error:
        return {"status": "launch_error", "error": str(error), "run_id": run_id}

    return {
        "status": "passed" if result.returncode == 0 else "unsuccessful",
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "run_id": run_id,
    }
