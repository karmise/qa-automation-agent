from pathlib import Path

from mcp.server import MCPServer
import subprocess

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


@mcp.tool()
def run_unit_tests() -> dict:
    """Run the Restful Booker framework unit tests and return their output."""
    project = Path(
        "/Users/karmise/Documents/Codex/2026-07-29/restful-booker-platform"
    )
    python = project / ".venv" / "bin" / "python"

    try:
        result = subprocess.run(
            [str(python), "-m", "pytest", "tests/unit", "-q"],
            cwd=project,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "error": "Unit test execution exceeded 60 seconds",
        }
    except OSError as error:
        return {
            "status": "launch_error",
            "error": str(error),
        }

    return {
        "status": "passed" if result.returncode == 0 else "unsuccessful",
        "exit_code": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")