"""Conditional unit-test triage using independently testable services."""

import logging
from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from .allure import read_allure_failures
from .reporting import build_report
from .runner import run_unit_tests

logger = logging.getLogger(__name__)


class QAState(TypedDict, total=False):
    run_result: dict
    allure_result: dict
    report: str


def execute_tests(state: QAState) -> dict:
    """Run the framework unit tests and store the result."""
    logger.info("Executing tests")
    return {"run_result": run_unit_tests()}


def choose_next_step(state: QAState) -> Literal["read_allure", "build_report"]:
    """Read Allure only when pytest reports failed tests."""
    result = state["run_result"]

    if result["status"] == "unsuccessful" and result.get("exit_code") == 1:
        return "read_allure"

    return "build_report"


def read_allure(state: QAState) -> dict:
    """Read Allure results and verify their run identity."""
    logger.info("Reading Allure")
    run_id = state["run_result"]["run_id"]
    allure_result = read_allure_failures(run_id)

    if allure_result.get("run_id") != run_id:
        return {
            "allure_result": {
                "run_id": run_id,
                "received_run_id": allure_result.get("run_id"),
                "status": "run_id_mismatch",
                "error": "Allure run ID does not match the test run",
            }
        }

    return {"allure_result": allure_result}


builder = StateGraph(QAState)

builder.add_node("execute_tests", execute_tests)
builder.add_node("read_allure", read_allure)
builder.add_node("build_report", build_report)

builder.add_edge(START, "execute_tests")
builder.add_conditional_edges("execute_tests", choose_next_step)
builder.add_edge("read_allure", "build_report")
builder.add_edge("build_report", END)

graph = builder.compile()
