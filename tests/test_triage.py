"""Rule-based classification, cause grouping, history, and change awareness."""

import pytest
from builders import evidence, failure, request, response, status_message

from qa_agent.triage import cause_key, classify, describe_history, facts, normalize, triage

SANDBOX = "https://sandbox.example"


def test_teardown_timeout_is_environment_not_product() -> None:
    test = failure(
        status="broken",
        exception="ResourceCleanupError",
        phase="teardown",
        fixture="Manage test-owned API resources",
        passed_steps=4,
        message=(
            "ResourceCleanupError: Failed to clean up test resources:\n"
            f"- room 'api-1': GET {SANDBOX}/api/room failed after 15004.5 ms: "
            "ReadTimeout: Read timed out. (read timeout=15)"
        ),
        http=[
            request("GET", f"{SANDBOX}/api/room"),
            {
                "kind": "failure",
                "method": "GET",
                "url": f"{SANDBOX}/api/room",
                "error": "ReadTimeout: Read timed out. (read timeout=15)",
            },
        ],
    )

    category, confidence, reasons = classify(test)

    assert (category, confidence) == ("environment", "high")
    assert "teardown" in reasons[0] and "4 test steps had passed" in reasons[0]
    assert "ReadTimeout" in reasons[1]


def test_cleanup_timeout_does_not_hide_a_failed_business_assertion() -> None:
    test = failure(
        message="AssertionError: Expected API error to contain 'Firstname should not be blank'",
        http=[
            {
                "kind": "failure",
                "method": "GET",
                "url": f"{SANDBOX}/api/room",
                "error": "ReadTimeout: Read timed out. (read timeout=15)",
            }
        ],
    )
    assert classify(test)[0] == "product_suspected"
    assert cause_key(test).startswith("call|AssertionError")


def test_gateway_error_in_a_setup_fixture_is_environment() -> None:
    """Fixtures mention only the status; the logged response must agree."""
    test = failure(
        status="broken",
        exception="RuntimeError",
        phase="setup",
        fixture="Authenticate the API administrator",
        message="RuntimeError: could not authenticate the administrator: 502 Upstream unavailable",
        http=[
            request("POST", f"{SANDBOX}/api/auth/login"),
            response("POST", f"{SANDBOX}/api/auth/login", "502", "Upstream unavailable"),
        ],
    )

    assert classify(test)[0] == "environment"
    assert cause_key(test) == "gateway|sandbox.example"


@pytest.mark.parametrize(
    ("actual", "category", "confidence"),
    [
        ("503 Service Unavailable", "environment", "high"),
        ("500 Internal Server Error", "product_suspected", "high"),
        ("400 Bad Request", "product_suspected", "medium"),
    ],
)
def test_status_assertions_are_classified_by_status(actual, category, confidence) -> None:
    test = failure(message=status_message("Rooms", "200 OK", actual, "GET", f"{SANDBOX}/api/room"))
    assert classify(test)[:2] == (category, confidence)


def test_schema_and_dto_mismatches_are_contract_changes() -> None:
    schema = failure(message="AssertionError: Response does not match JSON Schema 'branding':")
    dto = failure(
        exception="TypeError",
        message="TypeError: 'roomid' must be an integer",
        trace_tail="src/restful_booker/api/dto/room.py:40: TypeError",
    )
    assert classify(schema)[0] == "product_suspected"
    assert "JSON Schema" in classify(schema)[2][0]
    assert classify(dto)[0] == "product_suspected"


def test_python_errors_in_test_code_are_test_defects() -> None:
    test = failure(exception="AttributeError", message="AttributeError: 'NoneType' has no 'id'")
    assert classify(test)[:2] == ("test_defect", "high")


def test_ui_locator_timeout_needs_human_review() -> None:
    test = failure(
        exception="TimeoutError",
        message="TimeoutError: Locator expected to be visible\nwaiting for get_by_role('button')",
    )
    assert classify(test)[0] == "needs_review"


def test_known_defects_and_fixed_defects() -> None:
    assert classify(failure(xpass_strict=True))[0] == "known_defect_fixed"
    assert classify(failure(exception="KnownSandboxDefectError"))[0] == "known_defect"


def test_unexplained_assertion_in_body_is_a_suspected_product_defect() -> None:
    category, confidence, reasons = classify(
        failure(message="AssertionError: Expected 'Firstname should not be blank'")
    )
    assert (category, confidence) == ("product_suspected", "medium")
    assert "'Verify the API error message'" in reasons[0]


def test_one_outage_across_endpoints_is_one_cluster() -> None:
    """Twenty red tests caused by one gateway are one finding, not twenty bugs."""
    tests = [
        failure(
            id=f"t{n}",
            node_id=f"tests/api/test_x.py::test_{n}",
            message=status_message(
                "Rooms", "200 OK", "502 Bad Gateway", "GET", f"{SANDBOX}/api/room/{n}"
            ),
            http=[response("GET", f"{SANDBOX}/api/{'room' if n % 2 else 'branding'}", "502")],
        )
        for n in range(4)
    ]

    result = triage(evidence(*tests))

    assert result["failed_tests"] == 4
    assert len(result["clusters"]) == 1
    cluster = result["clusters"][0]
    assert cluster["category"] == "environment"
    assert any("4 of 4 executed tests" in reason for reason in cluster["reasons"])
    assert any("Affected endpoints" in reason for reason in cluster["reasons"])


def test_different_causes_are_separate_and_product_issues_come_first() -> None:
    outage = failure(
        id="a",
        message=status_message(
            "Report", "200 OK", "503 Unavailable", "GET", f"{SANDBOX}/api/report"
        ),
    )
    regression = failure(id="b", message="AssertionError: Expected API error to contain 'X'")

    clusters = triage(evidence(outage, regression))["clusters"]

    assert [cluster["category"] for cluster in clusters] == ["product_suspected", "environment"]
    assert [cluster["id"] for cluster in clusters] == ["C1", "C2"]


def test_volatile_values_do_not_split_one_cause() -> None:
    first = failure(id="a", message="AssertionError: room 'api-d5577e81' has 3 bookings")
    second = failure(id="b", message="AssertionError: room 'api-0b1c2d3e' has 7 bookings")
    assert cause_key(first) == cause_key(second)
    assert normalize("id 9f2c1a7b-1111-2222-3333-444455556666 took 15004.5 ms") == (
        "id <id> took <n> ms"
    )


def runs(*statuses: str, cause: str | None = None) -> list[dict]:
    return [{"status": status, "cause": cause} for status in statuses]


def test_history_marks_new_failures_and_flaky_tests() -> None:
    assert describe_history("failed", runs("passed", "passed"))["new_failure"] is True
    assert describe_history("failed", runs("failed"))["new_failure"] is False
    flaky = describe_history("failed", runs("passed", "failed", "passed", cause="c"), "c")
    assert flaky["flaky_suspected"] is True
    assert flaky["flips"] == 3


def test_failures_with_other_causes_do_not_make_a_test_flaky() -> None:
    """Failing in an outage, passing, then failing on a contract change is not flakiness."""
    previous = [
        {"status": "passed", "cause": None},
        {"status": "broken", "cause": "gateway|sandbox"},
    ]
    result = describe_history("failed", previous, "call|AssertionError|schema")
    assert result["flaky_suspected"] is False
    assert result["new_failure"] is True


def test_flaky_history_lowers_confidence_of_product_suspicion() -> None:
    test = failure(id="t", message="AssertionError: Expected total 300")
    key = cause_key(test)

    cluster = triage(evidence(test), history={"t": runs("passed", "failed", "passed", cause=key)})[
        "clusters"
    ][0]

    assert "flaky_suspected" in cluster["flags"]
    assert cluster["confidence"] == "low"


def test_causes_are_recorded_for_future_history() -> None:
    test = failure(id="t", message="AssertionError: Expected total 300")
    assert triage(evidence(test))["causes"] == {"t": cause_key(test)}


def test_changed_test_file_is_suspected_before_the_product() -> None:
    test = failure(message="AssertionError: Expected total 300")

    cluster = triage(evidence(test), changes={"files": ["tests/api/test_booking_api.py"]})[
        "clusters"
    ][0]

    assert "test_change_suspected" in cluster["flags"]
    assert cluster["confidence"] == "low"
    assert any("tests/api/test_booking_api.py" in reason for reason in cluster["reasons"])


def test_facts_pick_the_exchange_named_in_the_message_not_the_last_cleanup_call() -> None:
    message = status_message(
        "Report", "200 OK", "503 Unavailable", "GET", f"{SANDBOX}/api/report/11"
    )
    test = failure(
        message=message,
        http=[
            request("GET", f"{SANDBOX}/api/report/11"),
            response("GET", f"{SANDBOX}/api/report/11", "503"),
            request("DELETE", f"{SANDBOX}/api/room/11"),
            response("DELETE", f"{SANDBOX}/api/room/11", "202"),
        ],
    )

    found = facts(test)

    assert found["response"]["url"].endswith("/api/report/11")
    assert found["request"]["method"] == "GET"
    assert found["expected"] == ["Expected: 200 OK"]
    assert found["summary"] == "Report"


def test_known_defects_and_outcomes_are_reported() -> None:
    known = {"id": "k", "status": "skipped", "known_defect": True, "reason": "500 not 404"}
    passed = {"id": "p", "status": "passed"}

    result = triage(evidence(known, passed))

    assert result["clusters"] == []
    assert result["known_defects"][0]["reason"] == "500 not 404"
    assert result["outcomes"] == {"k": "skipped", "p": "passed"}
