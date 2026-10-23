"""Exercise both the in-memory MCP protocol and real stdio transport."""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

from mcp import Client, StdioServerParameters

import server
from tests.builders import write_result


def decode(response):
    assert not response.is_error
    return json.loads(response.content[0].text)


def test_mcp_lists_triage_and_compatibility_tools():
    async def check():
        async with Client(server.mcp) as client:
            return {tool.name for tool in (await client.list_tools()).tools}

    assert asyncio.run(check()) >= {
        "triage_tests",
        "triage_results",
        "show_run",
        "triage_unit_tests",
        "run_unit_tests",
        "read_allure_failures",
        "project_info",
    }


def test_mcp_triage_tests_runs_the_requested_suite_once_and_saves():
    async def check():
        async with Client(server.mcp) as client:
            response = await client.call_tool("triage_tests", {"suite": "api", "marker": "smoke"})
            result = decode(response)
            assert result["status"] == "unsuccessful"
            assert result["evidence"]["status"] == "no_results"
            assert result["artifacts_status"] == "saved"
            assert "diagnostics are unavailable" in result["report"]

    with patch(
        "qa_agent.graph.run_tests",
        return_value={
            "run_id": "c" * 32,
            "suite": "api",
            "marker": "smoke",
            "status": "unsuccessful",
            "exit_code": 1,
            "stdout": "1 failed",
            "stderr": "",
        },
    ) as runner:
        asyncio.run(check())
    runner.assert_called_once_with("api", "smoke")


def test_mcp_triage_results_is_read_only(results_dir):
    write_result(
        results_dir,
        "test_validation",
        "failed",
        statusDetails={"message": "AssertionError: Expected 'X'"},
    )

    async def check():
        async with Client(server.mcp) as client:
            return decode(
                await client.call_tool("triage_results", {"results_path": str(results_dir)})
            )

    with patch("qa_agent.runner.subprocess.run") as execute:
        result = asyncio.run(check())
    execute.assert_not_called()
    assert result["triage"]["clusters"][0]["category"] == "product_suspected"
    assert "llm_review" in result and result["llm_review"] is None


def test_stdio_workflow_returns_configuration_error_without_protocol_corruption(tmp_path):
    async def check():
        env = dict(os.environ)
        env.update(
            {
                "QA_AGENT_CONFIG": str(tmp_path / "missing.toml"),
                "QA_RUNS_DIR": str(tmp_path / "runs"),
            }
        )
        env.pop("QA_PROJECT_PATH", None)
        env.pop("QA_PYTHON_PATH", None)
        params = StdioServerParameters(
            command=sys.executable,
            args=[str(Path(server.__file__).resolve())],
            env=env,
        )
        async with Client(params, read_timeout_seconds=20) as client:
            result = decode(await client.call_tool("triage_unit_tests", {}))
            assert result["status"] == "launch_error"
            assert "QA_PROJECT_PATH" in result["report"]
            assert result["artifacts_status"] == "saved"
            saved = tmp_path / "runs" / result["run_id"] / "summary.json"
            assert json.loads(saved.read_text())["run_id"] == result["run_id"]

    asyncio.run(check())
