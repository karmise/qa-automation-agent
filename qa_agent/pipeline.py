"""Triage steps shared by the graph and the read-only CI entry point.

Standard library only, so `qa.py triage` runs in CI without installing LangGraph.
"""

from pathlib import Path

from . import git_context, llm, storage
from .evidence import read_results
from .reporting import build_report
from .settings import load_settings
from .triage import history_of, triage


def read_run_evidence(run_id: str) -> dict:
    """Read this run's own Allure directory and label the evidence with its run ID."""
    if not storage.valid_run_id(run_id):
        return {"status": "invalid_run_id", "error": storage.INVALID_RUN_ID, "tests": []}
    evidence = read_results(storage.run_directory(run_id) / "allure-results")
    return {"run_id": run_id, **evidence}


def collect_context(suite: str, run_id: str) -> dict:
    """History from saved runs plus Git facts; missing pieces never stop triage."""
    previous = storage.previous_summaries(suite, exclude=run_id)
    context: dict = {"previous_runs": len(previous), "history": history_of(previous)}
    try:
        project = load_settings().project
    except ValueError as error:
        return {**context, "git": {"head": None, "error": str(error)}, "changes": {"files": []}}
    git = git_context.snapshot(project)
    last_git = ((previous[0].get("context") or {}).get("git")) if previous else None
    return {**context, "git": git, "changes": git_context.changes_since(project, last_git, git)}


def analyze(evidence: dict, context: dict) -> dict:
    return triage(evidence, context.get("history"), context.get("changes"))


def model_review(result: dict, run: dict, context: dict, evidence: dict) -> dict:
    """Ask the configured model command for a second opinion on existing clusters."""
    try:
        settings = load_settings()
    except ValueError as error:
        return {"status": "config_error", "error": str(error)}
    if not settings.llm_command:
        return {"status": "disabled", "error": "Set llm_command in agent.toml"}
    review_context = {
        "suite": run.get("suite"),
        "base_url": (evidence.get("environment") or {}).get("Base URL"),
        "commit": (context.get("git") or {}).get("head"),
    }
    return llm.review(settings.llm_command, settings.llm_timeout, result, review_context)


def public_context(context: dict | None) -> dict | None:
    """Saved context excludes the bulky per-test history it was computed from."""
    if context is None:
        return None
    return {key: value for key, value in context.items() if key != "history"}


def evidence_summary(evidence: dict | None) -> dict | None:
    """Saved evidence keeps counts and errors; per-test detail lives in the triage."""
    if evidence is None:
        return None
    return {key: value for key, value in evidence.items() if key != "tests"}


def triage_results(results_dir: str | Path, use_llm: bool = False) -> dict:
    """Triage an existing Allure directory, such as a CI artifact, without running tests."""
    folder = Path(results_dir).expanduser().resolve()
    evidence = read_results(folder)
    result = analyze(evidence, {})
    if evidence["status"] in ("no_results", "read_error"):
        status = "unknown"
    else:
        status = "unsuccessful" if result["failed_tests"] else "passed"
    run = {"run_id": "existing-results", "status": status, "results_dir": str(folder)}
    review = model_review(result, run, {}, evidence) if use_llm else None
    state = {"run_result": run, "evidence": evidence, "triage": result, "llm_review": review}
    return {
        "status": status,
        "results_dir": str(folder),
        "evidence": evidence_summary(evidence),
        "triage": result,
        "llm_review": review,
        **build_report(state),
    }
