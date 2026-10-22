"""Graph routing: one execution, evidence identity, triage, and the optional model step."""

import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
from builders import status_message

from qa_agent.graph import graph

RUN_ID = "b" * 32


def run_result(status="unsuccessful", exit_code=1, **fields) -> dict:
    return {
        "run_id": RUN_ID,
        "suite": "api",
        "marker": None,
        "status": status,
        "exit_code": exit_code,
        "stdout": "pytest output",
        "stderr": "",
        **fields,
    }


def failing_evidence(**fields) -> dict:
    test = {
        "id": "t1",
        "title": "Booking rejects invalid guest details",
        "node_id": "tests/api/test_booking_api.py::test_booking_rejects_invalid_guest_details",
        "file": "tests/api/test_booking_api.py",
        "status": "failed",
        "exception": "AssertionError",
        "message": "AssertionError: Expected API error to contain 'Firstname should not be blank'",
        "phase": "call",
        "failed_step": "Verify the API error message",
        "passed_steps": 2,
        "http": [],
        "attachments": [],
    }
    return {
        "run_id": RUN_ID,
        "status": "ok",
        "files_found": 1,
        "files_read": 1,
        "counts": {
            "passed": 0,
            "failed": 1,
            "broken": 0,
            "skipped": 0,
            "unknown": 0,
            "known_defects": 0,
        },
        "tests": [test],
        "read_errors": [],
        "environment": {"Base URL": "https://sandbox"},
        **fields,
    }


def invoke(run: dict, evidence: dict | None = None, **request):
    with (
        patch("qa_agent.graph.run_tests", return_value=run) as runner,
        patch("qa_agent.graph.read_run_evidence", return_value=evidence) as reader,
    ):
        state = graph.invoke({"request": {"suite": "api", **request}})
    return state, runner, reader


def test_requested_suite_and_marker_reach_the_runner() -> None:
    _, runner, _ = invoke(run_result("passed", 0), failing_evidence(tests=[]), marker="smoke")
    runner.assert_called_once_with("api", "smoke")


def test_passed_run_still_records_outcomes_for_history() -> None:
    passed = failing_evidence(tests=[{"id": "t1", "status": "passed"}])
    state, runner, reader = invoke(run_result("passed", 0), passed)

    runner.assert_called_once()
    reader.assert_called_once_with(RUN_ID)
    assert state["triage"]["outcomes"] == {"t1": "passed"}
    assert state["triage"]["clusters"] == []
    assert "No failure investigation is needed" in state["report"]


def test_failed_run_is_grouped_and_reported() -> None:
    state, _, reader = invoke(run_result(), failing_evidence())

    reader.assert_called_once_with(RUN_ID)
    report = state["report"]
    assert "**Status:** unsuccessful" in report
    assert "1 failed test, 1 distinct cause" in report
    assert "Suspected product defect or contract change" in report
    assert "Booking rejects invalid guest details" in report
    assert "bug-reports/C1.md" in report
    assert "C1" in state["bug_reports"]
    assert "Draft generated from automated test evidence" in state["bug_reports"]["C1"]


@pytest.mark.parametrize(
    ("status", "error"),
    [
        ("timeout", "Api test execution exceeded 60 seconds"),
        ("launch_error", "Python executable not found"),
    ],
)
def test_execution_errors_skip_evidence(status: str, error: str) -> None:
    run = {"run_id": RUN_ID, "suite": "api", "status": status, "error": error}
    state, _, reader = invoke(run)

    reader.assert_not_called()
    assert "evidence" not in state
    assert f"**Error:** {error}" in state["report"]
    assert "**Exit code:** unavailable" in state["report"]


@pytest.mark.parametrize("exit_code", [2, 3, 4, 5])
def test_pytest_errors_skip_evidence_and_show_output(exit_code: int) -> None:
    state, _, reader = invoke(run_result(exit_code=exit_code))

    reader.assert_not_called()
    assert "pytest output" in state["report"]
    if exit_code == 5:
        assert "pytest collected no tests" in state["report"]


def test_evidence_from_another_run_is_rejected() -> None:
    state, _, _ = invoke(run_result(), failing_evidence(run_id="c" * 32))

    assert state["evidence"]["status"] == "run_id_mismatch"
    assert "Booking rejects invalid guest details" not in state["report"]
    assert "Rejected Allure run ID: " + "c" * 32 in state["report"]
    assert "**Status:** unsuccessful" in state["report"]


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ({"run_id": RUN_ID, "status": "no_results", "tests": []}, "diagnostics are unavailable"),
        (
            failing_evidence(status="partial", read_errors=[{"file": "bad.json", "error": "{"}]),
            "diagnostics are incomplete",
        ),
        (failing_evidence(tests=[]), "The run remains unsuccessful"),
    ],
)
def test_inconclusive_evidence_never_turns_failure_into_success(evidence, expected) -> None:
    state, _, _ = invoke(run_result(), evidence)
    assert "**Status:** unsuccessful" in state["report"]
    assert expected in state["report"]
    assert "**Next step:**" in state["report"]


def test_model_review_runs_only_when_requested() -> None:
    opinion = {
        "status": "ok",
        "summary": "The booking validation message changed.",
        "clusters": {
            "C1": {
                "category": "environment",
                "confidence": "low",
                "explanation": "Could be a stale deployment.",
                "next_step": "Check the deployed version.",
                "bug_report": None,
            }
        },
        "ignored": [],
    }
    with patch("qa_agent.graph.model_review", return_value=opinion) as model:
        without, _, _ = invoke(run_result(), failing_evidence())
        model.assert_not_called()
        with_model, _, _ = invoke(run_result(), failing_evidence(), use_llm=True)
    model.assert_called_once()
    report = with_model["report"]
    assert "**Model summary:** The booking validation message changed." in report
    assert "DISAGREES: environment" in report
    assert "Model summary" not in without["report"]


def test_runner_and_reader_share_the_run_directory() -> None:
    """Exercise the real runner, reader, triage, and report with only pytest replaced."""
    message = status_message(
        "Report", "200 OK", "503 Service Unavailable", "GET", "https://sandbox/api/report/1"
    )

    def fake_pytest(command: list, **kwargs) -> subprocess.CompletedProcess:
        if command[0] == "git":
            return subprocess.CompletedProcess(command, 128, "", "not a repository")
        results = Path(
            next(arg.split("=", 1)[1] for arg in command if arg.startswith("--alluredir="))
        )
        (results / "demo-result.json").write_text(
            json.dumps(
                {
                    "historyId": "h1",
                    "name": "Room report is available",
                    "fullName": "tests.api.test_report_api#test_room_report",
                    "status": "failed",
                    "statusDetails": {"message": message},
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(command, 1, "1 failed", "")

    with patch("qa_agent.runner.subprocess.run", side_effect=fake_pytest) as pytest_run:
        state = graph.invoke({"request": {"suite": "api"}})

    assert [call.args[0][0] for call in pytest_run.call_args_list].count("git") >= 1
    assert sum("pytest" in call.args[0] for call in pytest_run.call_args_list) == 1
    assert state["evidence"]["run_id"] == state["run_result"]["run_id"]
    cluster = state["triage"]["clusters"][0]
    assert cluster["category"] == "environment"
    assert "Room report is available" in state["report"]
