"""Thin MCP transport adapter around the application services."""

from mcp.server import MCPServer

from .allure import read_allure_failures as _read_allure_failures
from .project import project_info as _project_info
from .runner import run_unit_tests as _run_unit_tests
from .workflow import run_workflow

mcp = MCPServer("QA Automation Agent")


@mcp.tool()
def project_info(project_path: str) -> dict:
    """Check the test project directory and list available test suites."""
    return _project_info(project_path)


@mcp.tool()
def run_unit_tests() -> dict:
    """Run the configured framework unit suite once and return execution evidence."""
    return _run_unit_tests()


@mcp.tool()
def read_allure_failures(run_id: str) -> dict:
    """Read failed and broken Allure results for one existing run."""
    return _read_allure_failures(run_id)


@mcp.tool()
def triage_unit_tests() -> dict:
    """Execute the full triage workflow once and save its report."""
    return run_workflow()


def main() -> None:
    """Serve MCP on stdio; application diagnostics must never use stdout."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
