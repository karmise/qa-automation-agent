"""Run the graph once and persist evidence for later review."""

from datetime import datetime, timezone
import json
from time import monotonic

import server
from try_graph import graph


def run_workflow() -> dict:
    """Execute a fresh graph state and save a report without retrying tests."""
    started_at = datetime.now(timezone.utc).isoformat()
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
    folder = server.RUNS_DIR / run["run_id"]
    try:
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "report.txt").write_text(result["report"] + "\n", encoding="utf-8")
        temporary = folder / "summary.json.tmp"
        temporary.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        temporary.replace(folder / "summary.json")
    except OSError as error:
        result["artifacts_status"] = "save_error"
        result["artifacts_error"] = str(error)
    return result
