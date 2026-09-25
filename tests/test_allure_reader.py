import json

import pytest
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

@pytest.mark.parametrize("run_id", ["../outside", "A" * 32, "a" * 31, "", None])
def test_read_allure_failures_rejects_invalid_ids(run_id) -> None:
    """Reject malformed identifiers before looking up result files."""
    result = read_allure_failures(run_id)
    assert result["status"] == "invalid_run_id"


@pytest.mark.parametrize("invalid_content", [
    "{", "[]", '{"status": []}', '{"status": "failed", "statusDetails": []}',
    '{}',
])
def test_read_allure_failures_keeps_valid_results_when_one_file_is_invalid(
    tmp_path: Path, invalid_content: str
) -> None:
    """Return usable failures and explicit read errors for damaged results."""
    run_id = "f" * 32
    results_dir = tmp_path / run_id / "allure-results"
    results_dir.mkdir(parents=True)
    (results_dir / "bad-result.json").write_text(invalid_content, encoding="utf-8")
    (results_dir / "good-result.json").write_text(json.dumps({
        "name": "test_setup", "status": "broken",
        "statusDetails": {"message": "Setup failed"},
    }), encoding="utf-8")
    with patch("server.RUNS_DIR", tmp_path):
        result = read_allure_failures(run_id)
    assert result["status"] == "partial"
    assert result["files_found"] == 2
    assert result["files_read"] == 1
    assert result["failures"][0]["name"] == "test_setup"
    assert result["read_errors"][0]["file"] == "bad-result.json"
