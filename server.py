"""Stable MCP launcher and compatibility imports for learning scripts."""

from qa_agent.mcp_server import (
    main,
)
from qa_agent.mcp_server import (
    mcp as mcp,
)
from qa_agent.mcp_server import (
    project_info as project_info,
)
from qa_agent.mcp_server import (
    read_allure_failures as read_allure_failures,
)
from qa_agent.mcp_server import (
    run_unit_tests as run_unit_tests,
)
from qa_agent.mcp_server import (
    triage_unit_tests as triage_unit_tests,
)

if __name__ == "__main__":
    main()
