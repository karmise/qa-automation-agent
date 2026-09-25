"""Verify persistence and CLI behavior without executing framework tests."""

import json
from unittest.mock import patch

import pytest

import qa
import server
from workflow import run_workflow


def state(status="passed"):
    return {"run_result": {"run_id": "a" * 32, "status": status,
                           "exit_code": 0 if status == "passed" else 1},
            "report": "Saved evidence"}


@pytest.mark.parametrize("status", ["passed", "unsuccessful"])
def test_workflow_saves_evidence_once(status):
    with patch("workflow.graph.invoke", return_value=state(status)) as graph:
        result = run_workflow()
    graph.assert_called_once_with({})
    folder = server.RUNS_DIR / result["run_id"]
    assert json.loads((folder / "summary.json").read_text()) == result
    assert (folder / "report.txt").read_text() == "Saved evidence\n"
    assert result["duration_seconds"] >= 0
    assert not (folder / "summary.json.tmp").exists()


def test_workflow_discloses_save_error_without_retrying():
    with (patch("workflow.graph.invoke", return_value=state()) as graph,
          patch("pathlib.Path.mkdir", side_effect=PermissionError("Read-only disk"))):
        result = run_workflow()
    assert result["status"] == "passed"
    assert result["artifacts_status"] == "save_error"
    assert "Read-only disk" in result["artifacts_error"]
    graph.assert_called_once()


@pytest.mark.parametrize(("status", "expected"), [("passed", 0), ("unsuccessful", 1), ("timeout", 1)])
def test_cli_returns_verdict(status, expected, capsys):
    result = {"status": status, "report": "Evidence", "artifacts_status": "saved"}
    with patch("qa.run_workflow", return_value=result) as workflow:
        assert qa.main(["run", "--json"]) == expected
    assert json.loads(capsys.readouterr().out) == result
    workflow.assert_called_once_with()


def test_cli_show_reads_without_execution(capsys):
    with patch("workflow.graph.invoke", return_value=state()):
        saved = run_workflow()
    with patch("qa.run_workflow") as workflow:
        assert qa.main(["show", saved["run_id"], "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    workflow.assert_not_called()


@pytest.mark.parametrize("run_id", ["../outside", "b" * 32])
def test_cli_rejects_invalid_or_missing_saved_run(run_id):
    with patch("qa.run_workflow") as workflow:
        assert qa.main(["show", run_id]) == 2
    workflow.assert_not_called()


def test_cli_save_error_is_nonzero():
    with patch("qa.run_workflow", return_value={
        "status": "passed", "report": "Tests passed",
        "artifacts_status": "save_error", "artifacts_error": "Disk full",
    }):
        assert qa.main(["run"]) == 2
