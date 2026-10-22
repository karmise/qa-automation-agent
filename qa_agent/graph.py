"""Failure triage graph: execute once, gather evidence, classify, optionally ask a model."""

import logging
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .pipeline import analyze, collect_context, model_review, read_run_evidence
from .reporting import build_report
from .runner import run_tests

logger = logging.getLogger(__name__)


class QAState(TypedDict, total=False):
    request: dict
    run_result: dict
    evidence: dict
    context: dict
    triage: dict
    llm_review: dict
    report: str
    bug_reports: dict


def execute_tests(state: QAState) -> dict:
    """Run the requested suite once and store the result."""
    request = state.get("request") or {}
    suite, marker = request.get("suite", "unit"), request.get("marker")
    logger.info("Executing %s tests%s", suite, f" ({marker})" if marker else "")
    return {"run_result": run_tests(suite, marker)}


def choose_after_execution(state: QAState) -> Literal["read_evidence", "build_report"]:
    """Allure evidence exists only when pytest ran: it passed (0) or tests failed (1)."""
    result = state["run_result"]
    if result["status"] in ("passed", "unsuccessful") and result.get("exit_code") in (0, 1):
        return "read_evidence"
    return "build_report"


def read_evidence(state: QAState) -> dict:
    """Read this run's Allure results and reject evidence from any other run."""
    logger.info("Reading Allure evidence")
    run_id = state["run_result"]["run_id"]
    evidence = read_run_evidence(run_id)
    if evidence.get("run_id") != run_id:
        evidence = {
            "run_id": run_id,
            "received_run_id": evidence.get("run_id"),
            "status": "run_id_mismatch",
            "error": "Allure run ID does not match the test run",
            "tests": [],
        }
    return {"evidence": evidence}


def triage_failures(state: QAState) -> dict:
    """Group failures by cause using history and Git changes since the previous run."""
    logger.info("Classifying failures")
    run = state["run_result"]
    context = collect_context(run.get("suite", "unit"), run["run_id"])
    return {"context": context, "triage": analyze(state["evidence"], context)}


def choose_after_triage(state: QAState) -> Literal["review_with_model", "build_report"]:
    """Ask a model only when requested and there is something to review."""
    wanted = (state.get("request") or {}).get("use_llm", False)
    if wanted and state["triage"]["clusters"]:
        return "review_with_model"
    return "build_report"


def review_with_model(state: QAState) -> dict:
    logger.info("Requesting model review")
    review = model_review(state["triage"], state["run_result"], state["context"], state["evidence"])
    return {"llm_review": review}


builder = StateGraph(QAState)

builder.add_node("execute_tests", execute_tests)
builder.add_node("read_evidence", read_evidence)
builder.add_node("triage_failures", triage_failures)
builder.add_node("review_with_model", review_with_model)
builder.add_node("build_report", build_report)

builder.add_edge(START, "execute_tests")
builder.add_conditional_edges("execute_tests", choose_after_execution)
builder.add_edge("read_evidence", "triage_failures")
builder.add_conditional_edges("triage_failures", choose_after_triage)
builder.add_edge("review_with_model", "build_report")
builder.add_edge("build_report", END)

graph = builder.compile()
