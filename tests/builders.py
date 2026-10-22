"""Build Allure files and evidence records in the shapes the real framework produces."""

import json
from pathlib import Path

LOG_PREFIX = "2026-10-22 20:08:00 | INFO     | restful_booker.api.http | "


def http_log(*lines: str) -> str:
    """Render framework HTTP log lines as captured by pytest."""
    return "\n".join(LOG_PREFIX + line for line in lines) + "\n"


def write_result(folder: Path, name: str, status: str, **fields) -> dict:
    """Write one Allure result file in the format produced by allure-pytest."""
    folder.mkdir(parents=True, exist_ok=True)
    result = {
        "uuid": f"uuid-{name}",
        "historyId": f"history-{name}",
        "name": name.replace("_", " ").capitalize(),
        "fullName": f"tests.api.test_demo#{name}",
        "status": status,
        **fields,
    }
    (folder / f"{name}-result.json").write_text(json.dumps(result), encoding="utf-8")
    return result


def write_container(folder: Path, name: str, children: list[str], **fields) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    container = {"uuid": f"container-{name}", "children": children, **fields}
    (folder / f"{name}-container.json").write_text(json.dumps(container), encoding="utf-8")


def failure(**fields) -> dict:
    """One failed-test evidence record as produced by qa_agent.evidence."""
    record = {
        "id": "history-test",
        "title": "Booking rejects invalid guest details",
        "full_name": "tests.api.test_booking_api#test_booking_rejects_invalid_guest_details",
        "file": "tests/api/test_booking_api.py",
        "node_id": "tests/api/test_booking_api.py::test_booking_rejects_invalid_guest_details",
        "status": "failed",
        "exception": "AssertionError",
        "message": "",
        "trace_tail": "",
        "phase": "call",
        "fixture": None,
        "failed_step": "Verify the API error message",
        "passed_steps": 2,
        "http": [],
        "attachments": [],
        "xpass_strict": False,
        "severity": "normal",
    }
    return record | fields


def status_message(because: str, expected: str, actual: str, method: str, url: str) -> str:
    """The framework's ApiAssertions.has_status failure message."""
    return (
        f"AssertionError: {because}\nExpected: {expected}\nActual: {actual}\n"
        f"Request: {method} {url}\nResponse body: <h1>{actual}</h1>"
    )


def response(method: str, url: str, status: str, body: str = "{}") -> dict:
    return {"kind": "response", "method": method, "url": url, "status": status, "body": body}


def request(method: str, url: str, body: str = "{}") -> dict:
    return {"kind": "request", "method": method, "url": url, "body": body}


def evidence(*tests: dict) -> dict:
    return {"status": "ok", "tests": list(tests)}


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data), encoding="utf-8")
