"""Read per-run Allure evidence independently of transport and reporting."""

import json

from . import storage


def read_allure_failures(run_id: str) -> dict:
    """Read failed and broken Allure results for a specific run."""
    if not storage.valid_run_id(run_id):
        return {"status": "invalid_run_id", "error": storage.INVALID_RUN_ID}

    results_dir = storage.run_directory(run_id) / "allure-results"
    try:
        result_files = sorted(
            file for file in results_dir.iterdir() if file.name.endswith("-result.json")
        )
    except FileNotFoundError:
        result_files = []
    except OSError as error:
        return {"run_id": run_id, "status": "read_error", "error": str(error)}

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
            if result.get("status") not in ("passed", "failed", "broken", "skipped", "unknown"):
                raise ValueError("Expected a valid Allure test status")
            if not isinstance(result.get("statusDetails", {}), dict):
                raise ValueError("Expected statusDetails to be a JSON object")
        except (OSError, ValueError) as error:
            read_errors.append(
                {
                    "file": file.name,
                    "error": str(error),
                }
            )
            continue

        if result.get("status") in {"failed", "broken"}:
            failures.append(
                {
                    "uuid": result.get("uuid"),
                    "name": result.get("name"),
                    "full_name": result.get("fullName"),
                    "status": result.get("status"),
                    "details": result.get("statusDetails", {}),
                }
            )

    return {
        "run_id": run_id,
        "status": "partial" if read_errors else "ok",
        "files_found": len(result_files),
        "files_read": len(result_files) - len(read_errors),
        "failures": failures,
        "read_errors": read_errors,
    }
