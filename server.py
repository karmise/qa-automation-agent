from pathlib import Path

from mcp.server import MCPServer
import subprocess
import json
import os
from uuid import uuid4

from settings import load_settings

mcp = MCPServer("QA Automation Agent")
RUNS_DIR = Path(os.environ.get("QA_RUNS_DIR", Path(__file__).resolve().parent / "runs")).expanduser().resolve()


@mcp.tool()
def project_info(project_path: str) -> dict:
    """Check the test project directory and list available test suites."""
    project = Path(project_path).expanduser().resolve()

    if not project.is_dir():
        return {
            "path": str(project),
            "error": "Project directory not found",
        }

    suites = [
        name
        for name in ("unit", "api", "ui")
        if (project / "tests" / name).is_dir()
    ]

    return {
        "name": project.name,
        "path": str(project),
        "test_suites": suites,
    }


@mcp.tool()
def run_unit_tests() -> dict:
    """Run the Restful Booker framework unit tests and return their output."""
    run_id = uuid4().hex
    results_dir = RUNS_DIR / run_id / "allure-results"

    try:
        settings = load_settings()
        project, python, timeout = settings["project"], settings["python"], settings["timeout"]
        results_dir.mkdir(parents=True, exist_ok=False)
        result = subprocess.run(
            [str(python), "-m", "pytest", "tests/unit", "-q", f"--alluredir={results_dir}"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "error": f"Unit test execution exceeded {timeout} seconds",
            "run_id": run_id
        }
    except (OSError, ValueError) as error:
        return {
            "status": "launch_error",
            "error": str(error),
            "run_id": run_id
        }

    return {
        "status": "passed" if result.returncode == 0 else "unsuccessful",
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "run_id": run_id
    }


@mcp.tool()
def read_allure_failures(run_id: str) -> dict:
    """Read failed and broken Allure results for a specific run."""
    if (
        not isinstance(run_id, str)
        or len(run_id) != 32
        or any(char not in "0123456789abcdef" for char in run_id)
    ):
        return {
            "status": "invalid_run_id",
            "error": "Expected a 32-character lowercase hexadecimal run ID",
        }

    results_dir = RUNS_DIR / run_id / "allure-results"
    result_files = sorted(results_dir.glob("*-result.json"))

    if not result_files:
        return {
            "run_id": run_id,
            "status": "no_results",
            "error": "No Allure test result files found",
        }

    failures = []
    read_errors = []

    for file in result_files:
        try:
            result = json.loads(file.read_text(encoding="utf-8"))
            if not isinstance(result, dict):
                raise ValueError("Expected a JSON object")
            if result.get("status") not in (
                "passed", "failed", "broken", "skipped", "unknown"
            ):
                raise ValueError("Expected a valid Allure test status")
            if not isinstance(result.get("statusDetails", {}), dict):
                raise ValueError("Expected statusDetails to be a JSON object")
        except (OSError, ValueError) as error:
            read_errors.append({
                "file": file.name,
                "error": str(error),
            })
            continue

        if result.get("status") in {"failed", "broken"}:
            failures.append({
                "uuid": result.get("uuid"),
                "name": result.get("name"),
                "full_name": result.get("fullName"),
                "status": result.get("status"),
                "details": result.get("statusDetails", {}),
            })

    return {
        "run_id": run_id,
        "status": "partial" if read_errors else "ok",
        "files_found": len(result_files),
        "files_read": len(result_files) - len(read_errors),
        "failures": failures,
        "read_errors": read_errors,
    }


@mcp.tool()
def triage_unit_tests() -> dict:
    """Run the configured framework unit suite once, diagnose failures, and save a report."""
    from workflow import run_workflow

    return run_workflow()


if __name__ == "__main__":
    mcp.run(transport="stdio")
