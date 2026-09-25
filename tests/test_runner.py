import subprocess
from unittest.mock import patch

from qa_agent.runner import run_unit_tests


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
