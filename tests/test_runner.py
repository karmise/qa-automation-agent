import subprocess
from unittest.mock import patch

import pytest

from qa_agent import runner, storage
from qa_agent.runner import run_tests, run_unit_tests
from qa_agent.settings import Settings


@pytest.mark.parametrize(
    ("suite", "marker", "error"),
    [("all", None, "Unknown suite: all"), ("api", "not smoke", "Unknown marker: not smoke")],
)
def test_only_fixed_suites_and_markers_are_executed(suite, marker, error) -> None:
    """Agent-supplied values never become arbitrary pytest arguments."""
    with patch("qa_agent.runner.subprocess.run") as execute:
        result = run_tests(suite, marker)
    execute.assert_not_called()
    assert result["status"] == "launch_error"
    assert result["error"] == error


def test_ui_run_keeps_browser_artifacts_in_its_run_directory(tmp_path, monkeypatch) -> None:
    settings = Settings(
        project=tmp_path, python=tmp_path / "python", env={"RBP_BASE_URL": "http://proxy"}
    )
    monkeypatch.setattr(runner, "load_settings", lambda: settings)
    completed = subprocess.CompletedProcess([], 0, "15 passed", "")
    with patch("qa_agent.runner.subprocess.run", return_value=completed) as execute:
        result = run_tests("ui", "smoke")
    command = execute.call_args.args[0]
    folder = storage.run_directory(result["run_id"])
    assert command[3:] == [
        "tests/ui",
        "-q",
        f"--alluredir={folder / 'allure-results'}",
        "-m",
        "smoke",
        f"--output={folder / 'playwright'}",
    ]
    assert execute.call_args.kwargs["env"]["RBP_BASE_URL"] == "http://proxy"
    assert result["suite"] == "ui"
    assert result["marker"] == "smoke"


def test_run_unit_tests_reports_timeout() -> None:
    """Return a timeout status when the test process exceeds its time limit."""
    with patch("qa_agent.runner.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.TimeoutExpired(
            cmd=["pytest", "tests/unit"],
            timeout=60,
        )

        result = run_unit_tests()

    assert result["status"] == "timeout"
    assert result["error"] == "Unit test execution exceeded 60 seconds"
    mock_run.assert_called_once()


def test_run_unit_tests_reports_launch_error() -> None:
    """Return a launch error when the Python executable is missing."""
    with patch("qa_agent.runner.subprocess.run") as mock_run:
        mock_run.side_effect = FileNotFoundError("Python executable not found")

        result = run_unit_tests()

    assert result["status"] == "launch_error"
    assert result["error"] == "Python executable not found"
    mock_run.assert_called_once()


def test_run_unit_tests_reports_failed_tests() -> None:
    """Preserve the exit code and output when tests fail."""
    with patch("qa_agent.runner.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pytest", "tests/unit", "-q"],
            returncode=1,
            stdout="1 failed, 20 passed",
            stderr="",
        )

        result = run_unit_tests()

    assert result["status"] == "unsuccessful"
    assert result["exit_code"] == 1
    assert result["stdout"] == "1 failed, 20 passed"
    assert result["stderr"] == ""
    mock_run.assert_called_once()


def test_run_unit_tests_reports_success() -> None:
    with patch("qa_agent.runner.subprocess.run") as mock_run:
        mock_run.return_value = subprocess.CompletedProcess(
            args=["pytest", "tests/unit", "-q"],
            returncode=0,
            stdout="21 passed",
            stderr="",
        )

        result = run_unit_tests()

    assert result["status"] == "passed"
    assert result["exit_code"] == 0
    assert result["stdout"] == "21 passed"
    assert result["stderr"] == ""
    mock_run.assert_called_once()
