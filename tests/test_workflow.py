"""Verify persistence, history, and CLI behavior without executing framework tests."""

import json
from unittest.mock import patch

import pytest

from qa_agent import cli as qa
from qa_agent import storage
from qa_agent.workflow import run_workflow
from tests.builders import write_result


def state(status="passed", outcome="passed", bug_reports=None):
    return {
        "run_result": {
            "run_id": "a" * 32,
            "suite": "api",
            "status": status,
            "exit_code": 0 if status == "passed" else 1,
        },
        "triage": {"clusters": [], "outcomes": {"t1": outcome}, "failed_tests": 0},
        "report": "Saved evidence",
        "bug_reports": bug_reports or {},
    }


@pytest.mark.parametrize("status", ["passed", "unsuccessful"])
def test_workflow_saves_evidence_once(status):
    with patch("qa_agent.workflow.graph.invoke", return_value=state(status)) as graph:
        result = run_workflow("api")
    graph.assert_called_once_with({"request": {"suite": "api", "marker": None, "use_llm": False}})
    folder = storage.RUNS_DIR / result["run_id"]
    assert json.loads((folder / "summary.json").read_text()) == result
    assert (folder / "report.md").read_text() == "Saved evidence\n"
    assert result["outcomes"] == {"t1": "passed"}
    assert result["duration_seconds"] >= 0


def test_bug_report_drafts_are_saved_next_to_the_report():
    drafts = {"C1": "# Draft", "C1-model": "# Model draft", "../escape": "nope"}
    with patch("qa_agent.workflow.graph.invoke", return_value=state(bug_reports=drafts)):
        result = run_workflow("api")
    folder = storage.RUNS_DIR / result["run_id"] / "bug-reports"
    assert sorted(path.name for path in folder.iterdir()) == ["C1-model.md", "C1.md"]


def test_previous_summaries_are_history_of_the_same_suite():
    for run_id, suite, started in (("1" * 32, "api", "2026-10-01"), ("2" * 32, "ui", "2026-10-02")):
        storage.save_summary(
            {
                "run_id": run_id,
                "suite": suite,
                "status": "passed",
                "report": "r",
                "started_at": started,
                "outcomes": {"t1": "passed"},
            }
        )
    newer = {"run_id": "3" * 32, "suite": "api", "status": "unsuccessful", "report": "r"}
    storage.save_summary({**newer, "started_at": "2026-10-03"})

    history = storage.previous_summaries("api", exclude="3" * 32)

    assert [summary["run_id"] for summary in history] == ["1" * 32]


def test_workflow_discloses_save_error_without_retrying():
    with (
        patch("qa_agent.workflow.graph.invoke", return_value=state()) as graph,
        patch("pathlib.Path.mkdir", side_effect=PermissionError("Read-only disk")),
    ):
        result = run_workflow()
    assert result["status"] == "passed"
    assert result["artifacts_status"] == "save_error"
    assert "Read-only disk" in result["artifacts_error"]
    graph.assert_called_once()


@pytest.mark.parametrize(
    ("status", "expected"), [("passed", 0), ("unsuccessful", 1), ("timeout", 1)]
)
def test_cli_run_returns_verdict_and_passes_options(status, expected, capsys):
    result = {"status": status, "report": "Evidence", "artifacts_status": "saved"}
    with patch("qa_agent.workflow.run_workflow", return_value=result) as workflow:
        assert qa.main(["run", "--suite", "ui", "--marker", "smoke", "--json"]) == expected
    assert json.loads(capsys.readouterr().out) == result
    workflow.assert_called_once_with("ui", "smoke", use_llm=False)


def test_cli_rejects_unknown_suite():
    with pytest.raises(SystemExit):
        qa.main(["run", "--suite", "everything"])


def test_cli_show_reads_without_execution(capsys):
    with patch("qa_agent.workflow.graph.invoke", return_value=state()):
        saved = run_workflow()
    with patch("qa_agent.workflow.run_workflow") as workflow:
        assert qa.main(["show", saved["run_id"], "--json"]) == 0
    assert json.loads(capsys.readouterr().out) == saved
    workflow.assert_not_called()


@pytest.mark.parametrize("run_id", ["../outside", "b" * 32])
def test_cli_rejects_invalid_or_missing_saved_run(run_id):
    assert qa.main(["show", run_id]) == 2


def test_cli_save_error_is_nonzero():
    with patch(
        "qa_agent.workflow.run_workflow",
        return_value={
            "status": "passed",
            "report": "Tests passed",
            "artifacts_status": "save_error",
            "artifacts_error": "Disk full",
        },
    ):
        assert qa.main(["run"]) == 2


def test_cli_triage_reads_existing_results_and_writes_outputs(results_dir, tmp_path, capsys):
    """The CI entry point: no execution, a Markdown report, and bug-report drafts."""
    write_result(
        results_dir,
        "test_validation",
        "failed",
        statusDetails={"message": "AssertionError: Expected API error to contain 'X'"},
    )
    out = tmp_path / "triage"
    with patch("qa_agent.runner.subprocess.run") as execute:
        code = qa.main(["triage", str(results_dir), "--out", str(out)])
    execute.assert_not_called()
    assert code == 1
    report = capsys.readouterr().out
    assert "# Test triage: existing results" in report
    assert "No tests were executed" in report
    assert (out / "report.md").read_text().startswith("# Test triage")
    assert (out / "bug-reports" / "C1.md").is_file()


@pytest.mark.parametrize(("status", "expected"), [("passed", 0), (None, 2)])
def test_cli_triage_exit_codes(results_dir, status, expected, capsys):
    if status:
        write_result(results_dir, "test_ok", status)
    assert qa.main(["triage", str(results_dir)]) == expected
