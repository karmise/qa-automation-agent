"""Run the graph once and persist evidence for later review."""

from datetime import UTC, datetime
from time import monotonic

from . import storage
from .graph import graph
from .pipeline import evidence_summary, public_context


def run_workflow(suite: str = "unit", marker: str | None = None, use_llm: bool = False) -> dict:
    """Execute a fresh graph state and save a report without retrying tests."""
    started_at = datetime.now(UTC).isoformat()
    start = monotonic()
    state = graph.invoke({"request": {"suite": suite, "marker": marker, "use_llm": use_llm}})
    run = state["run_result"]
    triage = state.get("triage")
    result = {
        "run_id": run["run_id"],
        "suite": run.get("suite", suite),
        "marker": run.get("marker", marker),
        "status": run["status"],
        "exit_code": run.get("exit_code"),
        "started_at": started_at,
        "duration_seconds": round(monotonic() - start, 3),
        "run_result": run,
        "evidence": evidence_summary(state.get("evidence")),
        "context": public_context(state.get("context")),
        "triage": triage,
        "outcomes": (triage or {}).get("outcomes", {}),
        "causes": (triage or {}).get("causes", {}),
        "llm_review": state.get("llm_review"),
        "report": state["report"],
        "bug_reports": state.get("bug_reports") or {},
        "artifacts_status": "saved",
    }
    try:
        storage.save_summary(result)
    except OSError as error:
        result["artifacts_status"] = "save_error"
        result["artifacts_error"] = str(error)
    return result
