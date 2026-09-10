from pathlib import Path

from mcp.server import MCPServer

mcp = MCPServer("QA Automation Agent")


@mcp.tool()
def project_info(project_path: str) -> dict:
    """Check the test project directory and list available test suites."""
    project = Path(project_path).expanduser().resolve()

    if not project.is_dir():
        return {
            "path": str(project),
            "error": "Project directory not found",
        }

    suites = [
        name
        for name in ("unit", "api", "ui")
        if (project / "tests" / name).is_dir()
    ]

    return {
        "name": project.name,
        "path": str(project),
        "test_suites": suites,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")