"""Turn one Allure results directory into compact, structured failure evidence.

Pure file reading: no processes, network, or model calls. The same parser serves
fresh runs and result directories downloaded from CI.
"""

import json
import re
from pathlib import Path

STATUSES = ("passed", "failed", "broken", "skipped", "unknown")
PROBLEM_STATUSES = ("failed", "broken")
MAX_MESSAGE = 3_000
MAX_TRACE_LINES = 60
MAX_TRACE = 6_000
MAX_BODY = 800
MAX_ATTACHMENT_BYTES = 512_000
HTTP_EVENTS_KEPT = 6

SAFE_FILE_NAME = re.compile(r"[\w.-]+")
TRACE_EXCEPTION = re.compile(r"^\S+:\d+: (?P<type>[A-Za-z_][\w.]*)\s*$", re.MULTILINE)
MESSAGE_EXCEPTION = re.compile(r"^(?P<type>(?:[a-z_]\w*\.)*[A-Z]\w*(?:Error|Exception|Timeout)): ")
FIXTURE_SUFFIX = re.compile(r"::\d+$")
HTTP_LOGGER = " | restful_booker.api.http | "


def _read_json(file: Path) -> dict:
    data = json.loads(file.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Expected a JSON object")
    return data


def _truncate(text: str, limit: int) -> str:
    return (
        text if len(text) <= limit else text[:limit] + f"... [{len(text) - limit} more characters]"
    )


def _exception_type(status: str, message: str, trace: str) -> str | None:
    """Prefer pytest's final 'file:line: Type' trace line, then the message prefix."""
    matches = TRACE_EXCEPTION.findall(trace)
    if matches:
        return matches[-1].rsplit(".", 1)[-1]
    head = MESSAGE_EXCEPTION.match(message)
    if head:
        return head.group("type").rsplit(".", 1)[-1]
    return "AssertionError" if status == "failed" else None


def _fixture_problems(results_dir: Path, files: list[Path]) -> dict[str, list[dict]]:
    """Map test UUIDs to failed fixture setup or teardown entries from containers."""
    problems: dict[str, list[dict]] = {}
    for file in files:
        try:
            container = _read_json(file)
        except (OSError, ValueError):
            continue  # Containers only refine the phase; result files remain authoritative.
        entries = [("setup", item) for item in container.get("befores", [])]
        entries += [("teardown", item) for item in container.get("afters", [])]
        for phase, item in entries:
            if not isinstance(item, dict) or item.get("status") not in PROBLEM_STATUSES:
                continue
            details = item.get("statusDetails") or {}
            problem = {
                "phase": phase,
                "fixture": FIXTURE_SUFFIX.sub("", str(item.get("name", "unknown fixture"))),
                "message": str(details.get("message", "")),
            }
            for child in container.get("children", []):
                problems.setdefault(child, []).append(problem)
    return problems


def _failed_step(steps: list) -> tuple[str | None, int]:
    """Return the deepest failing step path and the number of passed top-level steps."""
    passed = sum(1 for step in steps if isinstance(step, dict) and step.get("status") == "passed")
    path: list[str] = []
    current = steps
    while True:
        failing = next(
            (
                step
                for step in current
                if isinstance(step, dict) and step.get("status") in PROBLEM_STATUSES
            ),
            None,
        )
        if failing is None:
            break
        path.append(str(failing.get("name", "unnamed step")))
        current = failing.get("steps") or []
    return (" > ".join(path) or None), passed


def _parse_http_line(line: str) -> dict | None:
    """Parse one framework HTTP log line, dropping headers and cookies."""
    if HTTP_LOGGER not in line:
        return None
    parts = line.split(" | ")
    if len(parts) < 4 or not parts[3].startswith("HTTP "):
        return None
    event = {"time": parts[0].strip(), "kind": parts[3].removeprefix("HTTP ").strip()}
    rest = parts[4:]
    for index, part in enumerate(rest):
        key, _, value = part.partition("=")
        if key == "body":
            # Bodies may contain the separator, so the body is always the remainder.
            event["body"] = _truncate(" | ".join([value, *rest[index + 1 :]]), MAX_BODY)
            break
        if key in ("method", "url", "status", "elapsed_ms", "error"):
            event[key] = value
    return event


def _http_events(text: str) -> list[dict]:
    """Keep the latest calls, every transport failure, and every error response."""
    events = [event for line in text.splitlines() if (event := _parse_http_line(line))]
    important = {
        index
        for index, event in enumerate(events)
        if event["kind"] == "failure" or event.get("status", "").startswith(("4", "5"))
    }
    important |= set(range(max(0, len(events) - HTTP_EVENTS_KEPT), len(events)))
    # A response without its request cannot be reproduced, so keep both.
    for index in list(important):
        if (
            index > 0
            and events[index]["kind"] != "request"
            and events[index - 1]["kind"] == "request"
        ):
            important.add(index - 1)
    return [events[index] for index in sorted(important)][-16:]


def _attachments(result: dict, results_dir: Path) -> tuple[list[dict], list[dict]]:
    """Return attachment references and HTTP events from text logs in this directory."""
    references, events = [], []
    for attachment in result.get("attachments", []) or []:
        if not isinstance(attachment, dict):
            continue
        source = str(attachment.get("source", ""))
        if not SAFE_FILE_NAME.fullmatch(source):
            continue  # Never follow paths outside the results directory.
        path = results_dir / source
        kind = str(attachment.get("type", ""))
        references.append({"name": attachment.get("name"), "type": kind, "path": str(path)})
        if kind == "text/plain" and path.is_file() and path.stat().st_size <= MAX_ATTACHMENT_BYTES:
            try:
                events += _http_events(path.read_text(encoding="utf-8", errors="replace"))
            except OSError:
                continue
    return references, events


def _labels(result: dict) -> dict:
    values: dict[str, list[str]] = {}
    for label in result.get("labels", []) or []:
        if isinstance(label, dict) and "name" in label and "value" in label:
            values.setdefault(str(label["name"]), []).append(str(label["value"]))
    first = {name: items[0] for name, items in values.items()}
    return {
        "suite": first.get("subSuite") or first.get("suite"),
        "feature": first.get("feature"),
        "story": first.get("story"),
        "severity": first.get("severity"),
        "tags": values.get("tag", []),
    }


def _location(full_name: str | None) -> dict:
    """Convert 'tests.api.test_x#test_y' into a file path and pytest node ID."""
    if not full_name or "#" not in full_name:
        return {"file": None, "node_id": None}
    module, function = full_name.split("#", 1)
    file = module.replace(".", "/") + ".py"
    return {"file": file, "node_id": f"{file}::{function}"}


def _test_record(result: dict, fixtures: dict[str, list[dict]], results_dir: Path) -> dict:
    status = result["status"]
    record = {
        "id": result.get("historyId") or result.get("testCaseId") or result.get("fullName"),
        "title": result.get("name"),
        "full_name": result.get("fullName"),
        "status": status,
    }
    if status == "passed":
        return record

    details = result.get("statusDetails") or {}
    message = str(details.get("message", "") or "")
    trace = str(details.get("trace", "") or "")
    record.update(_location(result.get("fullName")))
    record.update(_labels(result))
    start, stop = result.get("start"), result.get("stop")
    if isinstance(start, int) and isinstance(stop, int):
        record["duration_ms"] = stop - start

    if status == "skipped":
        reason = message.split("\n", 1)[0]
        record["known_defect"] = reason.startswith("XFAIL")
        record["reason"] = reason.removeprefix("XFAIL").strip() or None
        return record

    problems = fixtures.get(str(result.get("uuid")), [])
    setup = [problem for problem in problems if problem["phase"] == "setup"]
    teardown = [
        problem
        for problem in problems
        if problem["phase"] == "teardown" and problem["message"][:200] == message[:200]
    ]
    phase, fixture = "call", None
    if setup:
        phase, fixture = "setup", setup[0]["fixture"]
    elif teardown:
        phase, fixture = "teardown", teardown[0]["fixture"]

    failed_step, passed_steps = _failed_step(result.get("steps", []) or [])
    attachments, http = _attachments(result, results_dir)
    trace_tail = "\n".join(trace.splitlines()[-MAX_TRACE_LINES:])
    record.update(
        {
            "exception": _exception_type(status, message, trace),
            "message": _truncate(message, MAX_MESSAGE),
            "trace_tail": _truncate(trace_tail, MAX_TRACE),
            "phase": phase,
            "fixture": fixture,
            "failed_step": failed_step,
            "passed_steps": passed_steps,
            "http": http,
            "attachments": [item for item in attachments if item["type"] != "text/plain"],
            "xpass_strict": "[XPASS(strict)]" in message,
        }
    )
    return record


def _environment(results_dir: Path) -> dict:
    path = results_dir / "environment.properties"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return {}
    pairs = (line.split("=", 1) for line in lines if "=" in line)
    return {key.strip(): value.strip() for key, value in pairs}


def read_results(results_dir: Path) -> dict:
    """Read every test result; damaged files are reported, never silently dropped."""
    try:
        files = sorted(results_dir.iterdir())
    except FileNotFoundError:
        files = []
    except OSError as error:
        return {"status": "read_error", "error": str(error), "tests": []}

    result_files = [file for file in files if file.name.endswith("-result.json")]
    if not result_files:
        return {"status": "no_results", "error": "No Allure test result files found", "tests": []}

    fixtures = _fixture_problems(
        results_dir, [file for file in files if file.name.endswith("-container.json")]
    )
    tests, read_errors = [], []
    for file in result_files:
        try:
            result = _read_json(file)
            if result.get("status") not in STATUSES:
                raise ValueError("Expected a valid Allure test status")
            if not isinstance(result.get("statusDetails", {}), dict):
                raise ValueError("Expected statusDetails to be a JSON object")
        except (OSError, ValueError) as error:
            read_errors.append({"file": file.name, "error": str(error)})
            continue
        tests.append(_test_record(result, fixtures, results_dir))

    counts = {status: 0 for status in STATUSES}
    for test in tests:
        counts[test["status"]] += 1
    counts["known_defects"] = sum(1 for test in tests if test.get("known_defect"))
    return {
        "status": "partial" if read_errors else "ok",
        "files_found": len(result_files),
        "files_read": len(tests),
        "counts": counts,
        "tests": tests,
        "read_errors": read_errors,
        "environment": _environment(results_dir),
    }
