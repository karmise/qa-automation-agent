import pytest
from unittest.mock import patch

from try_graph import graph


def test_graph_skips_allure_when_tests_pass() -> None:
    """Build a success report without reading Allure."""
    run_result = {
        "status": "passed",
        "exit_code": 0,
        "stdout": "21 passed",
        "stderr": "",
        "run_id": "a" * 32,
    }

    with (
        patch(
            "try_graph.run_unit_tests",
            return_value=run_result,
        ) as mock_run,
        patch("try_graph.read_allure_failures") as mock_allure,
    ):
        result = graph.invoke({})

    mock_run.assert_called_once_with()
    mock_allure.assert_not_called()

    assert result["run_result"] == run_result
    assert "allure_result" not in result
    assert f"Run ID: {run_result['run_id']}" in result["report"]
    assert "Status: passed" in result["report"]
    assert "Exit code: 0" in result["report"]


def test_graph_reads_allure_for_the_failed_run() -> None:
    """Read Allure for the failed run and include the failure in the report."""
    run_id = "b" * 32
    run_result = {
        "status": "unsuccessful",
        "exit_code": 1,
        "stdout": "1 failed, 21 passed",
        "stderr": "",
        "run_id": run_id,
    }
    allure_result = {
        "run_id": run_id,
        "status": "ok",
        "files_found": 22,
        "files_read": 22,
        "failures": [
            {
                "name": "test_agent_failure_demo",
                "status": "failed",
            }
        ],
        "read_errors": [],
    }

    with (
        patch(
            "try_graph.run_unit_tests",
            return_value=run_result,
        ) as mock_run,
        patch(
            "try_graph.read_allure_failures",
            return_value=allure_result,
        ) as mock_allure,
    ):
        result = graph.invoke({})

    mock_run.assert_called_once_with()
    mock_allure.assert_called_once_with(run_id)

    assert result["allure_result"] == allure_result
    assert f"Run ID: {run_id}" in result["report"]
    assert "Status: unsuccessful" in result["report"]
    assert "Exit code: 1" in result["report"]
    assert "Failed test: test_agent_failure_demo" in result["report"]


@pytest.mark.parametrize(
    ("status", "error"),
    [
        ("timeout", "Unit test execution exceeded 60 seconds"),
        ("launch_error", "Python executable not found"),
    ],
)
def test_graph_reports_execution_errors_without_reading_allure(
    status: str,
    error: str,
) -> None:
    """Report execution errors without reading Allure or retrying."""
    run_id = "c" * 32
    run_result = {
        "status": status,
        "error": error,
        "run_id": run_id,
    }

    with (
        patch(
            "try_graph.run_unit_tests",
            return_value=run_result,
        ) as mock_run,
        patch("try_graph.read_allure_failures") as mock_allure,
    ):
        result = graph.invoke({})

    mock_run.assert_called_once_with()
    mock_allure.assert_not_called()

    assert "allure_result" not in result
    assert f"Run ID: {run_id}" in result["report"]
    assert f"Status: {status}" in result["report"]
    assert f"Error: {error}" in result["report"]
    assert "Exit code: unavailable" in result["report"]


def test_graph_rejects_allure_results_from_another_run() -> None:
    """Reject Allure results belonging to a different test run."""
    run_result = {
        "status": "unsuccessful",
        "exit_code": 1,
        "stdout": "1 failed",
        "stderr": "",
        "run_id": "a" * 32,
    }
    allure_result = {
        "run_id": "b" * 32,
        "status": "ok",
        "files_found": 1,
        "files_read": 1,
        "failures": [
            {"name": "test_from_another_run", "status": "failed"},
        ],
        "read_errors": [],
    }

    with (
        patch("try_graph.run_unit_tests", return_value=run_result),
        patch(
            "try_graph.read_allure_failures",
            return_value=allure_result,
        ),
    ):
        result = graph.invoke({})

    assert result["allure_result"]["status"] == "run_id_mismatch"
    assert "test_from_another_run" not in result["report"]
    assert "Allure run ID does not match the test run" in result["report"]
    assert "Status: unsuccessful" in result["report"]

@pytest.mark.parametrize(
    ("allure_status", "failures", "read_errors", "expected"),
    [
        ("no_results", [], [], "Allure diagnostics are unavailable"),
        ("partial", [{"name": "test_known_failure", "status": "broken",
                      "details": {"message": "Fixture setup failed"}}],
         [{"file": "bad-result.json", "error": "Invalid JSON"}],
         "Allure diagnostics are incomplete"),
        ("ok", [], [], "The run remains unsuccessful"),
    ],
)
def test_graph_preserves_failure_when_allure_is_inconclusive(
    allure_status: str, failures: list, read_errors: list, expected: str
) -> None:
    """Never turn absent or incomplete diagnostics into a passing run."""
    run_id = "d" * 32
    run_result = {
        "status": "unsuccessful", "exit_code": 1, "run_id": run_id,
        "stdout": "1 failed", "stderr": "Diagnostic warning",
    }
    allure_result = {
        "run_id": run_id, "status": allure_status,
        "failures": failures, "read_errors": read_errors,
    }
    with (
        patch("try_graph.run_unit_tests", return_value=run_result) as runner,
        patch("try_graph.read_allure_failures", return_value=allure_result) as reader,
    ):
        result = graph.invoke({})

    runner.assert_called_once_with()
    reader.assert_called_once_with(run_id)
    report = result["report"]
    assert "Status: unsuccessful" in report
    assert "1 failed" in report
    assert "Diagnostic warning" in report
    assert expected in report
    assert "Next step:" in report
    if allure_status == "partial":
        assert "test_known_failure" in report
        assert "Fixture setup failed" in report
        assert "bad-result.json" in report


@pytest.mark.parametrize("exit_code", [2, 3, 4, 5])
def test_graph_skips_allure_for_other_pytest_errors(exit_code: int) -> None:
    """Preserve pytest errors without treating them as test assertion failures."""
    with (
        patch("try_graph.run_unit_tests", return_value={
            "run_id": "e" * 32, "status": "unsuccessful",
            "exit_code": exit_code, "stdout": "Pytest diagnostic output", "stderr": "",
        }) as runner,
        patch("try_graph.read_allure_failures") as reader,
    ):
        result = graph.invoke({})

    runner.assert_called_once_with()
    reader.assert_not_called()
    assert "Pytest diagnostic output" in result["report"]
    assert "Status: unsuccessful" in result["report"]
    if exit_code == 5:
        assert "pytest collected no tests" in result["report"]


def test_graph_combines_runner_and_reader_using_the_same_directory() -> None:
    """Exercise the real runner and reader with only the subprocess replaced."""
    import json
    import subprocess
    from pathlib import Path

    def fake_pytest(command: list, **kwargs) -> subprocess.CompletedProcess:
        results_dir = Path(next(arg.split("=", 1)[1] for arg in command
                                if arg.startswith("--alluredir=")))
        (results_dir / "demo-result.json").write_text(json.dumps({
            "name": "test_integration_demo", "status": "failed",
            "statusDetails": {"message": "Expected 5, received 4"},
        }), encoding="utf-8")
        return subprocess.CompletedProcess(command, 1, "1 failed", "")

    with patch("server.subprocess.run", side_effect=fake_pytest) as runner:
        result = graph.invoke({})

    runner.assert_called_once()
    assert result["run_result"]["run_id"] == result["allure_result"]["run_id"]
    assert result["allure_result"]["files_read"] == 1
    assert "test_integration_demo" in result["report"]
    assert "Expected 5, received 4" in result["report"]
