from typing import Literal, TypedDict

from langgraph.graph import END, START, StateGraph

from server import read_allure_failures, run_unit_tests


class QAState(TypedDict, total=False):
    run_result: dict
    allure_result: dict
    report: str


def execute_tests(state: QAState) -> dict:
    """Run the framework unit tests and store the result."""
    print("Executing tests")
    return {"run_result": run_unit_tests()}


def choose_next_step(state: QAState) -> Literal["read_allure", "build_report"]:
    """Read Allure only when pytest reports failed tests."""
    result = state["run_result"]

    if result["status"] == "unsuccessful" and result.get("exit_code") == 1:
        return "read_allure"

    return "build_report"


def read_allure(state: QAState) -> dict:
    """Read Allure results for the completed test run."""
    print("Reading Allure")
    run_id = state["run_result"]["run_id"]
    return {"allure_result": read_allure_failures(run_id)}


def build_report(state: QAState) -> dict:
    """Summarize execution and any available Allure lookup."""
    print("Building report")
    result = state["run_result"]

    lines = [
        f"Run ID: {result['run_id']}",
        f"Status: {result['status']}",
        f"Exit code: {result.get('exit_code', 'unavailable')}",
    ]

    if result.get("error"):
        lines.append(f"Error: {result['error']}")

    if "allure_result" in state:
        allure = state["allure_result"]
        lines.append(f"Allure status: {allure['status']}")

        for failure in allure.get("failures", []):
            lines.append(f"Failed test: {failure['name']}")

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