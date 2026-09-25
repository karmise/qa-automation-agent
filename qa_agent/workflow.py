"""Run the graph once and persist evidence for later review."""

from datetime import UTC, datetime
from time import monotonic

from . import storage
from .graph import graph


def run_workflow() -> dict:
    """Execute a fresh graph state and save a report without retrying tests."""
    started_at = datetime.now(UTC).isoformat()
    start = monotonic()
    state = graph.invoke({})
    run = state["run_result"]
    result = {
        "run_id": run["run_id"],
        "status": run["status"],
        "exit_code": run.get("exit_code"),
        "started_at": started_at,
        "duration_seconds": round(monotonic() - start, 3),
        "run_result": run,
        "allure_result": state.get("allure_result"),
        "report": state["report"],
        "artifacts_status": "saved",
    }
    try:
        storage.save_summary(result)
    except OSError as error:
        result["artifacts_status"] = "save_error"
        result["artifacts_error"] = str(error)
    return result
