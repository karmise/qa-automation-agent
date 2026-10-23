"""Stable MCP launcher and compatibility imports for learning scripts."""

from qa_agent.mcp_server import (
    main,
    mcp,
    project_info,
    read_allure_failures,
    run_unit_tests,
    show_run,
    triage_results,
    triage_tests,
    triage_unit_tests,
)

__all__ = [
    "main",
    "mcp",
    "project_info",
    "read_allure_failures",
    "run_unit_tests",
    "show_run",
    "triage_results",
    "triage_tests",
    "triage_unit_tests",
]

if __name__ == "__main__":
    main()
