"""Exercise both the in-memory MCP protocol and real stdio transport."""

import asyncio
import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

from mcp import Client, StdioServerParameters

import server


def decode(response):
    assert not response.is_error
    return json.loads(response.content[0].text)


def test_mcp_workflow_returns_and_saves_graph_result():
    async def check():
        async with Client(server.mcp) as client:
            response = await client.call_tool("triage_unit_tests", {})
            result = decode(response)
            assert result["status"] == "unsuccessful"
            assert result["allure_result"]["status"] == "no_results"
            assert result["artifacts_status"] == "saved"
            assert "diagnostics are unavailable" in result["report"]

    with patch(
        "qa_agent.graph.run_unit_tests",
        return_value={
            "run_id": "c" * 32,
            "status": "unsuccessful",
            "exit_code": 1,
            "stdout": "1 failed",
            "stderr": "",
        },
    ) as runner:
        asyncio.run(check())
    runner.assert_called_once_with()


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
