"""Deterministic failure triage: group failures by cause and explain each verdict.

Rules are deliberately simple and visible. Each cluster carries the reasons that
produced its category so that a person or a model can disagree with them.
"""

import re
from collections import Counter
from urllib.parse import urlsplit

CATEGORIES = {
    "product_suspected": "Suspected product defect or contract change",
    "known_defect_fixed": "Known defect appears fixed",
    "test_defect": "Test or framework defect",
    "needs_review": "Needs human review",
    "environment": "Environment or infrastructure",
    "known_defect": "Known defect reproduced",
}
NEXT_STEPS = {
    "product_suspected": (
        "Reproduce the captured request manually. If the behavior is confirmed and not an "
        "intended change, file the drafted bug report; if it is intended, update the contract."
    ),
    "known_defect_fixed": (
        "Confirm the fix with the developers, then remove the xfail marker so the test guards it."
    ),
    "test_defect": "Fix the test or fixture. Product behavior has not been shown to be wrong.",
    "needs_review": (
        "Open the screenshot or trace and decide whether the UI changed, the locator is outdated, "
        "or the page was slow."
    ),
    "environment": (
        "Check the target environment's health. Rerun only after it recovers; "
        "this is not evidence of a product defect."
    ),
    "known_defect": "No action unless the defect's priority changed.",
}
CONFIDENCE = ("low", "medium", "high")

ENV_ERROR = re.compile(
    r"ReadTimeout|ConnectTimeout|ConnectionError|ConnectionRefused|Connection refused|"
    r"Connection reset|RemoteDisconnected|NameResolution|Name or service not known|"
    r"nodename nor servname|Temporary failure in name resolution|SSLError|"
    r"Max retries exceeded|net::ERR_|NS_ERROR_|ApiTransportError"
)
ACTUAL_STATUS = re.compile(r"^Actual: (?P<status>\d{3})\b", re.MULTILINE)
GATEWAY_STATUSES = ("502", "503", "504")
REQUEST_LINE = re.compile(r"^Request: (?P<method>[A-Z]+) (?P<url>\S+)", re.MULTILINE)
QUOTED_WORD = re.compile(r"'([\w-]+)'")
CODE_ERRORS = {
    "AttributeError",
    "TypeError",
    "NameError",
    "ImportError",
    "ModuleNotFoundError",
    "KeyError",
    "IndexError",
    "SyntaxError",
    "UnboundLocalError",
    "FixtureLookupError",
}
SCHEMA_ERRORS = {"ValidationError", "SchemaError"}
UI_WAIT = re.compile(r"waiting for (?:locator|get_by)|Locator expected|to_be_visible|to_have_text")
TEST_PATHS = ("tests/", "fixtures/")
CONTRACT_PATHS = ("src/restful_booker/contracts/", "src/restful_booker/api/schemas/")

HEX_ID = re.compile(r"(?<![0-9a-f])(?=[0-9a-f]*\d)[0-9a-f]{8,}(?![0-9a-f])")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
NUMBER = re.compile(r"\d+(?:\.\d+)?")
MODULE_PREFIX = re.compile(r"^(?:[a-z_]\w*\.)+(?=[A-Z]\w*: )")


def normalize(text: str) -> str:
    """Remove volatile values so that one cause produces one signature."""
    text = MODULE_PREFIX.sub("", text)
    text = UUID.sub("<id>", text)
    text = HEX_ID.sub("<id>", text)
    text = NUMBER.sub("<n>", text)
    return " ".join(text.split())


def _endpoint(url: str) -> tuple[str, str]:
    """Return host and an ID-free path, such as '/api/room/{id}'."""
    parts = urlsplit(url)
    path = "/".join("{id}" if segment.isdigit() else segment for segment in parts.path.split("/"))
    return parts.hostname or "", path


def _transport_failure(test: dict) -> dict | None:
    """A logged network failure counts only when the failure message reports it.

    A later cleanup timeout must not hide an earlier failed business assertion.
    """
    message = test.get("message", "")
    return next(
        (
            event
            for event in test.get("http", [])
            if event["kind"] == "failure" and event.get("error", "")[:40] in message
        ),
        None,
    )


def _gateway(test: dict) -> tuple[str, str, str] | None:
    """Return (status, method, URL) when the failure is a 502/503/504 answer.

    Assertions state it as 'Actual: 503'; fixtures often only mention the status, so
    the closest logged response must agree with the message.
    """
    message = test.get("message", "")
    actual, request = ACTUAL_STATUS.search(message), REQUEST_LINE.search(message)
    if actual and actual["status"] in GATEWAY_STATUSES:
        return (
            actual["status"],
            request["method"] if request else "",
            request["url"] if request else "",
        )
    responses = [event for event in test.get("http", []) if event["kind"] == "response"]
    last = responses[-1] if responses else None
    if (
        last
        and last.get("status") in GATEWAY_STATUSES
        and re.search(rf"\b{last['status']}\b", message)
    ):
        return last["status"], last.get("method", ""), last.get("url", "")
    return None


def _endpoints(tests: list[dict]) -> list[str]:
    """Distinct ID-free endpoints of the HTTP exchanges closest to each failure."""
    found = []
    for test in tests:
        events = [event for event in test.get("http", []) if event["kind"] != "request"]
        if events and events[-1].get("url"):
            found.append(f"{events[-1].get('method', '')} {_endpoint(events[-1]['url'])[1]}")
    return sorted(set(found))


def cause_key(test: dict) -> str:
    """Group by the shared cause: host for outages, endpoint for HTTP errors, text otherwise."""
    failure = _transport_failure(test)
    if failure:
        error_type = failure.get("error", "").split(":", 1)[0]
        return f"transport|{error_type}|{_endpoint(failure.get('url', ''))[0]}"
    gateway = _gateway(test)
    if gateway:
        return f"gateway|{_endpoint(gateway[2])[0]}"
    message = test.get("message", "")
    status, request = ACTUAL_STATUS.search(message), REQUEST_LINE.search(message)
    if status and request:
        _, path = _endpoint(request["url"])
        return f"status|{status['status']}|{request['method']} {path}"
    head = normalize(message)[:240]
    return f"{test.get('phase')}|{test.get('exception')}|{head}"


def _outside_body(test: dict) -> str:
    return (
        f"The failure happened during {test['phase']} in fixture '{test.get('fixture')}', "
        f"outside the test body ({test.get('passed_steps', 0)} test steps had passed)."
    )


def classify(test: dict) -> tuple[str, str, list[str]]:
    """Return category, confidence, and human-readable reasons for one failed test."""
    message = test.get("message", "")
    exception = test.get("exception") or ""
    trace = test.get("trace_tail", "")
    phase = test.get("phase", "call")
    reasons: list[str] = []
    if phase != "call":
        reasons.append(_outside_body(test))

    if test.get("xpass_strict"):
        return "known_defect_fixed", "high", ["The test is a strict expected failure but passed."]
    if exception == "KnownSandboxDefectError":
        return "known_defect", "high", ["The assertion matched an explicitly declared defect."]

    failure = _transport_failure(test)
    if failure or ENV_ERROR.search(message):
        detail = failure.get("error", "") if failure else message.split("\n", 1)[0]
        where = f"{failure.get('method')} {failure.get('url')}" if failure else "the target"
        reasons.append(f"Network error talking to {where}: {detail[:300]}")
        return "environment", "high", reasons

    gateway = _gateway(test)
    if gateway:
        code, method, url = gateway
        reasons.append(
            f"{method} {url} answered {code}: a gateway or availability error, "
            "typical for deployments and infrastructure problems."
        )
        return "environment", "high", reasons

    status = ACTUAL_STATUS.search(message)
    request = REQUEST_LINE.search(message)
    endpoint = f"{request['method']} {request['url']}" if request else "the application"
    if status and status["status"].startswith("5"):
        reasons.append(f"{endpoint} answered {status['status']}: the application failed.")
        return "product_suspected", "high", reasons
    if status:
        where = "a precondition request" if phase == "setup" else "the request under test"
        reasons.append(f"Unexpected status {status['status']} for {where}: {endpoint}.")
        return "product_suspected", "medium", reasons

    if exception in SCHEMA_ERRORS or "JSON Schema" in message or "Failed validating" in message:
        reasons.append(
            "The response no longer matches its JSON Schema: a contract change, "
            "or the schema in the tests is outdated."
        )
        return "product_suspected", "medium", reasons
    if exception in CODE_ERRORS and "/api/dto/" in trace:
        reasons.append("The response did not match the typed DTO, so the contract changed.")
        return "product_suspected", "medium", reasons
    if exception in CODE_ERRORS:
        reasons.append(
            f"Python {exception} in test or framework code: the test crashed before it "
            "could judge the product."
        )
        return "test_defect", "high", reasons

    if exception == "TimeoutError" and ("page.goto" in trace or "navigat" in message.lower()):
        reasons.append("A page navigation timed out: the site was slow or unavailable.")
        return "environment", "medium", reasons
    if exception == "TimeoutError" or UI_WAIT.search(message):
        reasons.append(
            "A UI element did not reach the expected state in time: the UI changed, "
            "the locator is outdated, or the page was slow."
        )
        return "needs_review", "medium", reasons

    if phase != "call":
        return "test_defect", "medium", reasons
    if exception == "AssertionError":
        step = test.get("failed_step")
        reasons.append(
            f"A business assertion failed in the test body"
            f"{f' at step {step!r}' if step else ''} after "
            f"{test.get('passed_steps', 0)} passing steps."
        )
        return "product_suspected", "medium", reasons
    reasons.append(f"No rule matched {exception or 'this failure'}.")
    return "needs_review", "low", reasons


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _relevance(event: dict, message: str) -> int:
    """Score how strongly the failure message points at one logged HTTP answer.

    Cleanup calls run after the failure, so 'the last call' is often the wrong one.
    """
    url = event.get("url", "")
    path = urlsplit(url).path
    score = 0
    if url and url in message:
        score += 4
    elif path and path in message:
        score += 3
    if event.get("status") and f"Actual: {event['status']}" in message:
        score += 3
    body = _squash(event.get("body", ""))
    if len(body) > 8 and body[:80] in _squash(message):
        score += 3
    if event["kind"] == "failure" and event.get("error", "")[:60] in message:
        score += 4
    if any(len(word) > 3 and word in path for word in QUOTED_WORD.findall(message)):
        score += 2
    if event.get("method") == "DELETE":
        score -= 1
    return score


def facts(test: dict) -> dict:
    """Message highlights and the HTTP exchange that the failure message refers to."""
    message = test.get("message", "")
    lines = [MODULE_PREFIX.sub("", line.strip()) for line in message.splitlines() if line.strip()]
    expected = [line for line in lines if line.startswith(("Expected", "Known defect"))]
    actual = [line for line in lines if line.startswith(("Actual", "Response body", "- $"))]
    http = test.get("http", [])
    answers = [index for index, event in enumerate(http) if event["kind"] != "request"]
    response = request = None
    if answers:
        best = max(answers, key=lambda index: (_relevance(http[index], message), index))
        response = http[best]
        request = next(
            (
                event
                for event in reversed(http[:best])
                if event["kind"] == "request" and event.get("method") == response.get("method")
            ),
            None,
        )
    return {
        "summary": lines[0].removeprefix("AssertionError: ") if lines else None,
        "message_lines": [line[:400] for line in lines[:6]],
        "expected": expected,
        "actual": actual,
        "request": request,
        "response": response,
        "attachments": test.get("attachments", []),
    }


def history_of(previous: list[dict]) -> dict[str, list[dict]]:
    """Map test IDs to their previous status and failure cause, most recent run first."""
    history: dict[str, list[dict]] = {}
    for summary in previous:
        causes = summary.get("causes") or {}
        for test_id, status in (summary.get("outcomes") or {}).items():
            history.setdefault(test_id, []).append({"status": status, "cause": causes.get(test_id)})
    return history


def describe_history(current: str, previous: list[dict], cause: str | None = None) -> dict:
    """Flaky means passing and failing with the same cause; other causes are other stories.

    A test that failed during an outage and now fails on a changed contract is
    not flaky. Without a known cause, every failure counts.
    """
    recent = previous[:9]
    marks = []
    for entry in [{"status": current, "cause": cause}, *recent]:
        if entry["status"] == "passed":
            marks.append(False)
        elif entry["status"] in ("failed", "broken") and (
            cause is None or entry.get("cause") == cause
        ):
            marks.append(True)
    flips = sum(1 for left, right in zip(marks, marks[1:], strict=False) if left != right)
    return {
        "previous": [entry["status"] for entry in recent],
        "new_failure": bool(recent) and recent[0]["status"] == "passed",
        "flips": flips,
        "flaky_suspected": flips >= 2,
    }


def _merge_confidence(values: list[str]) -> str:
    return min(values, key=CONFIDENCE.index)


def triage(evidence: dict, history: dict | None = None, changes: dict | None = None) -> dict:
    """Cluster failed tests and attach the evidence and reasoning for each cluster."""
    history = history or {}
    changed = set((changes or {}).get("files", []))
    tests = evidence.get("tests", [])
    failed = [test for test in tests if test["status"] in ("failed", "broken")]
    executed = [test for test in tests if test["status"] != "skipped"]

    groups: dict[str, list[dict]] = {}
    for test in failed:
        groups.setdefault(cause_key(test), []).append(test)

    clusters = []
    for key, members in groups.items():
        verdicts = [classify(test) for test in members]
        category = Counter(verdict[0] for verdict in verdicts).most_common(1)[0][0]
        confidence = _merge_confidence([v[1] for v in verdicts if v[0] == category])
        # The first member's reasons represent the cluster; shared facts are added below.
        reasons = list(next(verdict[2] for verdict in verdicts if verdict[0] == category))
        flags = []

        endpoints = _endpoints(members)
        if len(endpoints) > 1:
            reasons.append(f"Affected endpoints: {', '.join(endpoints)}.")
        if len(members) >= 3 and len(members) * 2 >= len(executed):
            reasons.append(
                f"{len(members)} of {len(executed)} executed tests fail with this cause: "
                "one shared root cause, not separate defects."
            )
            if category == "environment":
                confidence = "high"

        member_rows = []
        for test in members:
            past = describe_history(test["status"], history.get(test["id"], []), key)
            member_rows.append(
                {
                    key_name: test.get(key_name)
                    for key_name in (
                        "id",
                        "title",
                        "node_id",
                        "file",
                        "status",
                        "phase",
                        "fixture",
                        "failed_step",
                        "severity",
                    )
                }
                | {"history": past}
            )
        if any(row["history"]["flaky_suspected"] for row in member_rows):
            flags.append("flaky_suspected")
            reasons.append("The result changed repeatedly in recent runs: possibly flaky.")
            if category == "product_suspected":
                confidence = "low"

        touched = sorted({test["file"] for test in members if test.get("file") in changed})
        contracts = sorted(file for file in changed if file.startswith(CONTRACT_PATHS))
        if touched or contracts:
            flags.append("test_change_suspected")
            reasons.append(
                "Changed since the previous run or uncommitted: "
                f"{', '.join(touched + contracts)}. Review that change before blaming the product."
            )
            if category == "product_suspected":
                confidence = "low"

        clusters.append(
            {
                "key": key,
                "category": category,
                "label": CATEGORIES[category],
                "confidence": confidence,
                "reasons": reasons,
                "flags": flags,
                "next_step": NEXT_STEPS[category],
                "exception": members[0].get("exception"),
                "facts": facts(members[0]),
                "tests": member_rows,
            }
        )

    order = list(CATEGORIES)
    clusters.sort(key=lambda cluster: (order.index(cluster["category"]), -len(cluster["tests"])))
    for number, cluster in enumerate(clusters, start=1):
        cluster["id"] = f"C{number}"

    return {
        "failed_tests": len(failed),
        "clusters": clusters,
        "known_defects": [
            {"title": test.get("title"), "node_id": test.get("node_id"), "reason": test["reason"]}
            for test in tests
            if test.get("known_defect")
        ],
        "outcomes": {test["id"]: test["status"] for test in tests if test.get("id")},
        "causes": {
            test["id"]: key for key, members in groups.items() for test in members if test.get("id")
        },
    }
