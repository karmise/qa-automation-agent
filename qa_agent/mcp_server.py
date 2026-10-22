"""Thin MCP transport adapter around the application services.

The calling coding agent is the language model here: tools return structured
evidence and never invoke a second model.
"""

from typing import Literal

from mcp.server import MCPServer

from . import storage
from .allure import read_allure_failures as _read_allure_failures
from .pipeline import triage_results as _triage_results
from .project import project_info as _project_info
from .runner import run_unit_tests as _run_unit_tests
from .workflow import run_workflow

mcp = MCPServer("QA Automation Agent")


@mcp.tool()
def project_info(project_path: str) -> dict:
    """Check the test project directory and list available test suites."""
    return _project_info(project_path)


@mcp.tool()
def triage_tests(
    suite: Literal["unit", "api", "ui"] = "unit",
    marker: Literal["smoke", "regression"] | None = None,
) -> dict:
    """Run one Restful Booker suite once, group failures by cause, and save the report.

    API and UI suites call the configured target environment and can take minutes.
    """
    return run_workflow(suite, marker)


@mcp.tool()
def triage_results(results_path: str) -> dict:
    """Triage an existing Allure results directory (for example a CI artifact).

    Read-only: no tests are executed and nothing is saved.
    """
    return _triage_results(results_path)


@mcp.tool()
def show_run(run_id: str) -> dict:
    """Read a saved triage result without executing tests."""
    try:
        return storage.read_summary(run_id)
    except (OSError, ValueError) as error:
        return {"run_id": run_id, "status": "read_error", "error": str(error)}


@mcp.tool()
def triage_unit_tests() -> dict:
    """Execute the unit-suite triage workflow once and save its report."""
    return run_workflow("unit")


@mcp.tool()
def run_unit_tests() -> dict:
    """Low-level: run the configured framework unit suite once and return execution evidence."""
    return _run_unit_tests()


@mcp.tool()
def read_allure_failures(run_id: str) -> dict:
    """Low-level: read failed and broken Allure results for one existing run."""
    return _read_allure_failures(run_id)


def main() -> None:
    """Serve MCP on stdio; application diagnostics must never use stdout."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
