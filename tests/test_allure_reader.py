import json
from pathlib import Path
from unittest.mock import patch

from server import read_allure_failures


def test_read_allure_failures_excludes_passed_tests(tmp_path: Path) -> None:
    """Exclude passed tests from the failure list."""
    run_id = "a" * 32
    results_dir = tmp_path / run_id / "allure-results"
    results_dir.mkdir(parents=True)

    result_file = results_dir / "passed-result.json"
    result_file.write_text(
        json.dumps({
            "name": "test_example",
            "status": "passed",
        }),
        encoding="utf-8",
    )

    with patch("server.RUNS_DIR", tmp_path):
        result = read_allure_failures(run_id)

    assert result["status"] == "ok"
    assert result["run_id"] == run_id
    assert result["files_read"] == 1
    assert result["failures"] == []
    assert result["read_errors"] == []


def test_read_allure_failures_isolates_runs(tmp_path: Path) -> None:
    """Read failures only from the requested run."""
    failed_run_id = "a" * 32
    passed_run_id = "b" * 32

    runs = [
        (failed_run_id, "test_old_failure", "failed"),
        (passed_run_id, "test_new_success", "passed"),
    ]

    for run_id, name, status in runs:
        results_dir = tmp_path / run_id / "allure-results"
        results_dir.mkdir(parents=True)
        (results_dir / "result-result.json").write_text(
            json.dumps({
                "name": name,
                "status": status,
            }),
            encoding="utf-8",
        )

    with patch("server.RUNS_DIR", tmp_path):
        failed_result = read_allure_failures(failed_run_id)
        passed_result = read_allure_failures(passed_run_id)

    assert failed_result["status"] == "ok"
    assert failed_result["run_id"] == failed_run_id
    assert failed_result["files_read"] == 1
    assert failed_result["read_errors"] == []
    assert len(failed_result["failures"]) == 1
    assert failed_result["failures"][0]["name"] == "test_old_failure"

    assert passed_result["status"] == "ok"
    assert passed_result["run_id"] == passed_run_id
    assert passed_result["files_read"] == 1
    assert passed_result["read_errors"] == []
    assert passed_result["failures"] == []


def test_read_allure_failures_reports_missing_run(tmp_path: Path) -> None:
    """Report missing results instead of treating them as a passing run."""
    run_id = "c" * 32

    with patch("server.RUNS_DIR", tmp_path):
        result = read_allure_failures(run_id)

    assert result["status"] == "no_results"
    assert result["run_id"] == run_id
    assert result["error"] == "No Allure test result files found"