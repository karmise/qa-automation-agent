import sys

from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from server import read_allure_failures, run_unit_tests


class QAState(TypedDict, total=False):
    run_result: dict
    allure_result: dict
    report: str


def execute_tests(state: QAState) -> dict:
    """Run the framework unit tests and store the result."""
    print("Executing tests", file=sys.stderr)
    return {"run_result": run_unit_tests()}


def choose_next_step(state: QAState) -> Literal["read_allure", "build_report"]:
    """Read Allure only when pytest reports failed tests."""
    result = state["run_result"]

    if result["status"] == "unsuccessful" and result.get("exit_code") == 1:
        return "read_allure"

    return "build_report"


def read_allure(state: QAState) -> dict:
    """Read Allure results and verify their run identity."""
    print("Reading Allure", file=sys.stderr)
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


def build_report(state: QAState) -> dict:
    """Report execution evidence, diagnostic limits, and a next step."""
    print("Building report", file=sys.stderr)
    result = state["run_result"]
    lines = [
        f"Run ID: {result['run_id']}",
        f"Status: {result['status']}",
        f"Exit code: {result.get('exit_code', 'unavailable')}",
        "Scope: Restful Booker framework unit tests only. API and UI tests were not run.",
    ]

    if result.get("error"):
        lines.append(f"Error: {result['error']}")
    for key, label in (("stdout", "Pytest output"), ("stderr", "Standard error")):
        if result.get(key):
            lines.append(f"{label}:\n{result[key].strip()}")

    next_step = "Inspect the execution output before deciding whether to rerun."
    if result["status"] == "passed":
        next_step = "No unit-test failure investigation is needed."
    elif result["status"] == "timeout":
        next_step = "Investigate the timeout before explicitly requesting another run."
    elif result["status"] == "launch_error":
        next_step = "Check the project directory, Python executable, and filesystem permissions."
    elif result.get("exit_code") == 5:
        next_step = "Check test discovery: pytest collected no tests."

    allure = state.get("allure_result")
    if allure is not None:
        status = allure["status"]
        lines.append(f"Allure status: {status}")
        if allure.get("error"):
            lines.append(f"Allure error: {allure['error']}")
        if "files_found" in allure:
            lines.append(
                f"Allure files read: {allure['files_read']}/{allure['files_found']}"
            )

        if status in {"ok", "partial"}:
            for failure in allure.get("failures", []):
                name = failure.get("full_name") or failure.get("name") or "Unknown test"
                lines.append(f"Failed test: {name}")
                lines.append(f"Test status: {failure.get('status', 'unknown')}")
                message = failure.get("details", {}).get("message")
                if message:
                    lines.append(f"Failure message: {message}")
            for error in allure.get("read_errors", []):
                lines.append(f"Allure read error: {error['file']}: {error['error']}")

        if status == "no_results":
            lines.append("Allure diagnostics are unavailable; the pytest run remains unsuccessful.")
            next_step = "Inspect pytest output and Allure result generation for this run."
        elif status == "partial":
            lines.append("Allure diagnostics are incomplete; the failure list may be incomplete.")
            next_step = "Inspect pytest output and the unreadable Allure files for this run."
        elif status == "run_id_mismatch":
            lines.append(f"Rejected Allure run ID: {allure.get('received_run_id')}")
            next_step = "Investigate the run ID mismatch; do not use the rejected results."
        elif status == "ok" and not allure.get("failures"):
            lines.append("Allure contains no failures, but pytest reported failure. The run remains unsuccessful.")
            next_step = "Investigate the disagreement between pytest output and this run's Allure files."
        elif status == "ok":
            next_step = "Inspect the reported assertions and application behavior before proposing a fix."
        else:
            next_step = "Investigate the Allure lookup error using this run's pytest output."

    lines.append(f"Next step: {next_step}")
    return {"report": "\n".join(lines)}


builder = StateGraph(QAState)

builder.add_node("execute_tests", execute_tests)
builder.add_node("read_allure", read_allure)
builder.add_node("build_report", build_report)

builder.add_edge(START, "execute_tests")
builder.add_conditional_edges("execute_tests", choose_next_step)
builder.add_edge("read_allure", "build_report")
builder.add_edge("build_report", END)

graph = builder.compile()


if __name__ == "__main__":
    final_state = graph.invoke({})
    print(final_state["report"])
