"""Allure parsing: phases, steps, HTTP logs, known defects, and damaged files."""

from qa_agent.evidence import read_results
from tests.builders import http_log, write_container, write_result


def test_teardown_failure_is_located_in_its_fixture(results_dir) -> None:
    """A cleanup timeout after a passing body is attributed to the teardown fixture."""
    message = (
        "restful_booker.api.resource_lifecycle.ResourceCleanupError: Failed to clean up:\n"
        "- room 'api-1': GET https://sandbox/api/room failed: ReadTimeout: read timed out"
    )
    write_result(
        results_dir,
        "test_cleanup",
        "broken",
        statusDetails={"message": message, "trace": "src/lifecycle.py:116: ResourceCleanupError"},
        steps=[{"name": "Create a guest booking", "status": "passed"}] * 3,
    )
    write_container(
        results_dir,
        "lifecycle",
        ["uuid-test_cleanup"],
        afters=[
            {
                "name": "Manage test-owned API resources::0",
                "status": "broken",
                "statusDetails": {"message": message},
            }
        ],
    )

    test = read_results(results_dir)["tests"][0]

    assert test["phase"] == "teardown"
    assert test["fixture"] == "Manage test-owned API resources"
    assert test["exception"] == "ResourceCleanupError"
    assert test["passed_steps"] == 3
    assert test["failed_step"] is None
    assert test["node_id"] == "tests/api/test_demo.py::test_cleanup"


def test_setup_failure_and_deepest_failed_step(results_dir) -> None:
    write_result(
        results_dir,
        "test_setup",
        "broken",
        statusDetails={"message": "RuntimeError: could not authenticate"},
        steps=[
            {"name": "Open", "status": "passed"},
            {
                "name": "Book",
                "status": "failed",
                "steps": [{"name": "Verify the HTTP response status", "status": "failed"}],
            },
        ],
    )
    write_container(
        results_dir,
        "auth",
        ["uuid-test_setup"],
        befores=[{"name": "Authenticate the API administrator", "status": "broken"}],
    )

    test = read_results(results_dir)["tests"][0]

    assert test["phase"] == "setup"
    assert test["fixture"] == "Authenticate the API administrator"
    assert test["failed_step"] == "Book > Verify the HTTP response status"
    assert test["exception"] == "RuntimeError"


def test_http_log_keeps_failure_exchange_without_headers(results_dir) -> None:
    """Old calls are trimmed, but an error response keeps its request; secrets stay out."""
    filler = [
        f"HTTP response | method=GET | url=https://sandbox/api/room/{n} | status=200 | "
        'headers={"Set-Cookie":"token=secret"} | body={}'
        for n in range(10)
    ]
    log = http_log(
        "HTTP request | method=POST | url=https://sandbox/api/booking | params={} | "
        'headers={"Cookie":"token=secret"} | cookies={} | body={"firstname":""}',
        "HTTP response | method=POST | url=https://sandbox/api/booking | status=400 | "
        'elapsed_ms=12.5 | headers={"A":"b"} | body={"errors": ["a | b"]}',
        *filler,
    )
    results_dir.mkdir(parents=True)
    (results_dir / "log-attachment.txt").write_text(log, encoding="utf-8")
    write_result(
        results_dir,
        "test_booking",
        "failed",
        statusDetails={"message": "AssertionError: Expected API error"},
        attachments=[{"name": "log", "source": "log-attachment.txt", "type": "text/plain"}],
    )

    http = read_results(results_dir)["tests"][0]["http"]

    assert http[0] == {
        "time": "2026-10-22 20:08:00",
        "kind": "request",
        "method": "POST",
        "url": "https://sandbox/api/booking",
        "body": '{"firstname":""}',
    }
    assert http[1]["status"] == "400"
    assert http[1]["body"] == '{"errors": ["a | b"]}'
    assert "secret" not in str(http)
    assert len(http) <= 16


def test_attachments_outside_results_directory_are_ignored(results_dir, tmp_path) -> None:
    (tmp_path / "secret.txt").write_text(http_log("HTTP failure | url=leak"), encoding="utf-8")
    write_result(
        results_dir,
        "test_ui",
        "failed",
        statusDetails={"message": "AssertionError: missing"},
        attachments=[
            {"name": "log", "source": "../secret.txt", "type": "text/plain"},
            {"name": "Browser state at failure", "source": "shot.png", "type": "image/png"},
        ],
    )

    test = read_results(results_dir)["tests"][0]

    assert test["http"] == []
    assert test["attachments"] == [
        {
            "name": "Browser state at failure",
            "type": "image/png",
            "path": str(results_dir / "shot.png"),
        }
    ]


def test_expected_failures_are_known_defects_not_failures(results_dir) -> None:
    write_result(
        results_dir,
        "test_known",
        "skipped",
        statusDetails={"message": "XFAIL Known RBP defect: 500 instead of 404\n\ndetails"},
    )
    write_result(results_dir, "test_ok", "passed")

    result = read_results(results_dir)

    assert result["counts"]["known_defects"] == 1
    assert result["counts"]["passed"] == 1
    known = next(test for test in result["tests"] if test["status"] == "skipped")
    assert known["known_defect"] is True
    assert known["reason"] == "Known RBP defect: 500 instead of 404"


def test_strict_xpass_is_flagged(results_dir) -> None:
    write_result(
        results_dir,
        "test_fixed",
        "failed",
        statusDetails={"message": "[XPASS(strict)] Known RBP defect"},
    )
    assert read_results(results_dir)["tests"][0]["xpass_strict"] is True


def test_damaged_result_is_reported_and_valid_results_are_kept(results_dir) -> None:
    write_result(results_dir, "test_ok", "broken", statusDetails={"message": "Setup failed"})
    (results_dir / "bad-result.json").write_text("{", encoding="utf-8")

    result = read_results(results_dir)

    assert result["status"] == "partial"
    assert result["files_found"] == 2
    assert result["files_read"] == 1
    assert result["read_errors"][0]["file"] == "bad-result.json"


def test_missing_directory_has_no_results(tmp_path) -> None:
    result = read_results(tmp_path / "missing")
    assert result["status"] == "no_results"
    assert result["tests"] == []


def test_environment_properties_are_read(results_dir) -> None:
    write_result(results_dir, "test_ok", "passed")
    (results_dir / "environment.properties").write_text(
        "Base URL=https://sandbox\nPython=3.12\n", encoding="utf-8"
    )
    assert read_results(results_dir)["environment"] == {
        "Base URL": "https://sandbox",
        "Python": "3.12",
    }
