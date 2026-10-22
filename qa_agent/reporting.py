"""Pure Markdown rendering: no processes, files, or model calls."""

import json

MAX_OUTPUT = 3_000
MAX_SIGNAL = 90
HISTORY_WORDS = {True: "new failure", False: "failed before"}


def _cell(text: object) -> str:
    return " ".join(str(text).split()).replace("|", "\\|")


def _short(text: object, limit: int) -> str:
    value = " ".join(str(text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _plural(count: int, noun: str) -> str:
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _tail(text: str) -> str:
    text = text.strip()
    return text if len(text) <= MAX_OUTPUT else "…" + text[-MAX_OUTPUT:]


def _scope(run: dict) -> str:
    if run.get("results_dir"):
        return f"Existing Allure results in `{run['results_dir']}`. No tests were executed."
    marker = f" with marker '{run['marker']}'" if run.get("marker") else ""
    return f"Restful Booker {run.get('suite', 'unit')} tests{marker}. Other suites were not run."


def _target(state: dict) -> str | None:
    environment = (state.get("evidence") or {}).get("environment") or {}
    git = (state.get("context") or {}).get("git") or {}
    parts = []
    if environment.get("Base URL"):
        parts.append(environment["Base URL"])
    if git.get("head"):
        dirty = len(git.get("dirty_files", []))
        parts.append(
            f"commit `{git['head'][:10]}`"
            + (f" on {git['branch']}" if git.get("branch") else "")
            + (f" with {dirty} uncommitted files" if dirty else "")
        )
    return " · ".join(parts) or None


def _history(row: dict) -> str:
    history = row["history"]
    if history["flaky_suspected"]:
        return f"flaky? {history['flips']} result changes recently"
    if not history["previous"]:
        return "no history"
    return HISTORY_WORDS[history["new_failure"]]


def _exchange(facts: dict) -> list[str]:
    lines = list(facts.get("message_lines") or [*facts["expected"], *facts["actual"]])
    request, response = facts.get("request"), facts.get("response")
    if request:
        body = request.get("body")
        lines.append(
            f"-> {request.get('method')} {request.get('url')}"
            + (f" {body}" if body and body != "{}" else "")
        )
    if response and response["kind"] == "failure":
        lines.append(f"<- transport failure: {response.get('error')}")
    elif response:
        lines.append(f"<- {response.get('status')} {response.get('body', '')}")
    if not lines and facts.get("summary"):
        lines.append(facts["summary"])
    return lines


def _evidence_notes(state: dict) -> tuple[list[str], str | None]:
    """Explain missing or doubtful diagnostics; never let them change the verdict."""
    run = state["run_result"]
    evidence = state.get("evidence")
    if evidence is None:
        return [], None
    status = evidence["status"]
    failed_run = run["status"] == "unsuccessful"
    notes = []
    if evidence.get("error"):
        notes.append(f"Allure error: {evidence['error']}")
    if "files_found" in evidence:
        notes.append(f"Allure files read: {evidence['files_read']}/{evidence['files_found']}")
    for error in evidence.get("read_errors", []):
        notes.append(f"Allure read error: {error['file']}: {error['error']}")
    if status == "no_results":
        notes.append("Allure diagnostics are unavailable; the pytest verdict stands.")
        return notes, "Inspect pytest output and Allure result generation for this run."
    if status == "partial":
        notes.append("Allure diagnostics are incomplete; the failure list may be incomplete.")
        return notes, "Inspect pytest output and the unreadable Allure files for this run."
    if status == "run_id_mismatch":
        notes.append(f"Rejected Allure run ID: {evidence.get('received_run_id')}")
        return notes, "Investigate the run ID mismatch; do not use the rejected results."
    if status == "read_error":
        return notes, "Investigate the Allure lookup error using this run's pytest output."
    triage = state.get("triage") or {}
    if failed_run and not triage.get("failed_tests"):
        notes.append(
            "Allure contains no failures, but pytest reported failure. The run remains unsuccessful."
        )
        return notes, "Investigate the disagreement between pytest output and Allure files."
    return notes, None


def _counts(evidence: dict) -> str:
    counts = evidence["counts"]
    executed = counts["passed"] + counts["failed"] + counts["broken"] + counts["unknown"]
    other_skipped = counts["skipped"] - counts["known_defects"]
    text = (
        f"{executed} executed: {counts['passed']} passed, {counts['failed']} failed, "
        f"{counts['broken']} broken. {counts['known_defects']} known defects (expected failures)"
    )
    return text + (f", {other_skipped} skipped." if other_skipped else ".")


def _cluster_section(cluster: dict, opinion: dict | None, has_draft: bool) -> list[str]:
    lines = [
        "",
        f"### {cluster['id']} · {cluster['label']} · confidence: {cluster['confidence']}",
        "",
        "**Why the rules think so**",
        *(f"- {reason}" for reason in cluster["reasons"]),
        "",
        f"**Affected tests ({len(cluster['tests'])})**",
    ]
    for row in cluster["tests"][:15]:
        where = f"phase: {row['phase']}" + (
            f", fixture: {row['fixture']}" if row.get("fixture") else ""
        )
        lines.append(f"- {row['title']} — `{row['node_id']}` ({where}; {_history(row)})")
    if len(cluster["tests"]) > 15:
        lines.append(f"- … and {len(cluster['tests']) - 15} more")
    exchange = _exchange(cluster["facts"])
    if exchange:
        lines += ["", "**Evidence**", "```text", *(_short(line, 600) for line in exchange), "```"]
    for attachment in cluster["facts"]["attachments"]:
        lines.append(f"- Attachment `{attachment['name']}`: `{attachment['path']}`")
    if opinion:
        verdict = (
            "agrees"
            if opinion["category"] == cluster["category"]
            else f"DISAGREES: {opinion['category']} — needs a human decision"
        )
        lines += [
            "",
            f"**Model review** ({verdict}, confidence: {opinion['confidence']})",
            "",
            opinion["explanation"],
        ]
        next_step = opinion["next_step"]
    else:
        next_step = cluster["next_step"]
    lines += ["", f"**Next step:** {next_step}"]
    if has_draft:
        lines.append(f"**Bug report draft:** `bug-reports/{cluster['id']}.md`")
    return lines


def bug_report(cluster: dict, state: dict) -> str:
    """Draft a bug report from captured evidence; a person verifies it before filing."""
    run = state["run_result"]
    facts = cluster["facts"]
    first = cluster["tests"][0]
    title = _short(f"{first['title']}: {facts['summary'] or cluster['exception']}", 120)
    request = facts.get("request")
    response = facts.get("response")
    tests = ", ".join(f"`{row['node_id']}`" for row in cluster["tests"][:10])
    lines = [
        f"# {title}",
        "",
        "> Draft generated from automated test evidence. Reproduce it before filing.",
        "",
        f"- **Target:** {_target(state) or 'unknown'}",
        f"- **Run:** `{run.get('results_dir') or run['run_id']}`"
        + (f" ({run['suite']} suite)" if run.get("suite") else ""),
        f"- **Affected tests:** {tests}",
        "",
        "## Steps to reproduce",
    ]
    if request:
        lines.append(f"1. Send `{request.get('method')} {request.get('url')}`")
        if request.get("body") and request["body"] != "{}":
            body = request["body"]
            try:
                body = json.dumps(json.loads(body), indent=2)
            except ValueError:
                pass
            lines += ["   ```json", *(f"   {line}" for line in body.splitlines()), "   ```"]
    else:
        lines.append(f"1. Run `pytest {first['node_id']}`")
    expected = facts["expected"] or [
        f"Not stated in the failure message; the failed check was: {facts['summary']}"
    ]
    lines += ["", "## Expected", *(f"- {line}" for line in expected)]
    # Schema violations are already list items such as "- $.contact: ...".
    lines += ["", "## Actual", *(f"- {line.removeprefix('- ')}" for line in facts["actual"])]
    if response and response["kind"] == "response":
        lines.append(f"- Response {response.get('status')}: `{_short(response.get('body'), 600)}`")
    if not facts["actual"] and not response:
        lines.append(f"- {facts['summary']}")
    lines += ["", "## Why this looks like a product issue", *(f"- {r}" for r in cluster["reasons"])]
    return "\n".join(lines) + "\n"


def build_report(state: dict) -> dict:
    """Render the verdict, grouped causes, evidence limits, and next steps."""
    run = state["run_result"]
    if run.get("results_dir"):
        lines = ["# Test triage: existing results", "", f"- **Status:** {run['status']}"]
    else:
        lines = [
            f"# Test triage: {run.get('suite', 'unit')} suite",
            "",
            f"- **Run ID:** `{run['run_id']}`",
            f"- **Status:** {run['status']}",
            f"- **Exit code:** {run.get('exit_code', 'unavailable')}",
        ]
    lines.append(f"- **Scope:** {_scope(run)}")
    target = _target(state)
    if target:
        lines.append(f"- **Target:** {target}")

    next_step = "Inspect the execution output before deciding whether to rerun."
    if run.get("error"):
        lines += ["", f"**Error:** {run['error']}"]
    if run["status"] == "timeout":
        next_step = "Investigate the timeout before explicitly requesting another run."
    elif run["status"] == "launch_error":
        next_step = "Check the project directory, Python executable, and filesystem permissions."
    elif run.get("exit_code") == 5:
        next_step = "Check test discovery: pytest collected no tests."
    elif run["status"] == "passed":
        next_step = "No failure investigation is needed."

    evidence = state.get("evidence") or {}
    triage = state.get("triage") or {}
    review = state.get("llm_review") or {}
    notes, evidence_step = _evidence_notes(state)
    next_step = evidence_step or next_step
    clusters = triage.get("clusters", [])
    opinions = review.get("clusters", {}) if review.get("status") == "ok" else {}
    drafts = {
        cluster["id"]
        for cluster in clusters
        if "product_suspected"
        in (cluster["category"], (opinions.get(cluster["id"]) or {}).get("category"))
    }

    if evidence.get("counts"):
        lines += ["", "## Summary", "", _counts(evidence)]
    if review.get("status") == "ok":
        lines += ["", f"> **Model summary:** {review['summary']}"]

    if clusters:
        lines += [
            "",
            f"## What needs attention: {_plural(triage['failed_tests'], 'failed test')}, "
            f"{_plural(len(clusters), 'distinct cause')}",
            "",
            "| Cluster | Likely cause | Confidence | Tests | Signal |",
            "| --- | --- | --- | --- | --- |",
        ]
        for cluster in clusters:
            signal = cluster["facts"]["summary"] or cluster["exception"] or ""
            lines.append(
                f"| {cluster['id']} | {_cell(cluster['label'])} | {cluster['confidence']} | "
                f"{len(cluster['tests'])} | {_cell(_short(signal, MAX_SIGNAL))} |"
            )
        for cluster in clusters:
            lines += _cluster_section(cluster, opinions.get(cluster["id"]), cluster["id"] in drafts)
        top = clusters[0]
        next_step = f"Start with {top['id']}: {(opinions.get(top['id']) or top)['next_step']}"

    if triage.get("known_defects"):
        lines += ["", "## Known defects (expected failures)"]
        lines += [f"- {item['title']} — {item['reason']}" for item in triage["known_defects"]]

    if notes:
        lines += ["", "## Diagnostics", *(f"- {note}" for note in notes)]
    if review.get("status") not in (None, "ok", "disabled", "skipped"):
        lines.append(f"- Model review unavailable ({review['status']}): {review.get('error')}")

    if run["status"] != "passed" and (not clusters or run.get("exit_code") != 1):
        for key, label in (("stdout", "Pytest output"), ("stderr", "Standard error")):
            if run.get(key):
                lines += ["", f"**{label}:**", "```text", _tail(run[key]), "```"]

    if clusters:
        lines += [
            "",
            "## Limits",
            "- Categories are hypotheses from visible rules"
            + (" and a model review" if opinions else "")
            + "; the pytest verdict is authoritative.",
            "- Nothing was rerun automatically. Flaky suspicion comes only from saved history.",
        ]
    lines += ["", f"**Next step:** {next_step}"]
    reports = {
        cluster["id"]: bug_report(cluster, state) for cluster in clusters if cluster["id"] in drafts
    }
    for cluster_id, opinion in opinions.items():
        if opinion.get("bug_report"):
            reports[f"{cluster_id}-model"] = opinion["bug_report"]
    return {"report": "\n".join(lines), "bug_reports": reports}
