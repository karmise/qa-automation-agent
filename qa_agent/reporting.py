"""Pure report rendering: no processes, files, or model calls."""


def build_report(state: dict) -> dict:
    """Report execution evidence, diagnostic limits, and a next step."""
    result = state["run_result"]
    lines = [
        f"Run ID: {result['run_id']}",
        f"Status: {result['status']}",
        f"Exit code: {result.get('exit_code', 'unavailable')}",
        "Scope: Restful Booker framework unit tests only. API and UI tests were not run.",
    ]

    if result.get("error"):
        lines.append(f"Error: {result['error']}")
    for key, label in (("stdout", "Pytest output"), ("stderr", "Standard error")):
        if result.get(key):
            lines.append(f"{label}:\n{result[key].strip()}")

    next_step = "Inspect the execution output before deciding whether to rerun."
    if result["status"] == "passed":
        next_step = "No unit-test failure investigation is needed."
    elif result["status"] == "timeout":
        next_step = "Investigate the timeout before explicitly requesting another run."
    elif result["status"] == "launch_error":
        next_step = "Check the project directory, Python executable, and filesystem permissions."
    elif result.get("exit_code") == 5:
        next_step = "Check test discovery: pytest collected no tests."

    allure = state.get("allure_result")
    if allure is not None:
        status = allure["status"]
        lines.append(f"Allure status: {status}")
        if allure.get("error"):
            lines.append(f"Allure error: {allure['error']}")
        if "files_found" in allure:
            lines.append(f"Allure files read: {allure['files_read']}/{allure['files_found']}")

        if status in {"ok", "partial"}:
            for failure in allure.get("failures", []):
                name = failure.get("full_name") or failure.get("name") or "Unknown test"
                lines.append(f"Failed test: {name}")
                lines.append(f"Test status: {failure.get('status', 'unknown')}")
                message = failure.get("details", {}).get("message")
                if message:
                    lines.append(f"Failure message: {message}")
            for error in allure.get("read_errors", []):
                lines.append(f"Allure read error: {error['file']}: {error['error']}")

        if status == "no_results":
            lines.append("Allure diagnostics are unavailable; the pytest run remains unsuccessful.")
            next_step = "Inspect pytest output and Allure result generation for this run."
        elif status == "partial":
            lines.append("Allure diagnostics are incomplete; the failure list may be incomplete.")
            next_step = "Inspect pytest output and the unreadable Allure files for this run."
        elif status == "run_id_mismatch":
            lines.append(f"Rejected Allure run ID: {allure.get('received_run_id')}")
            next_step = "Investigate the run ID mismatch; do not use the rejected results."
        elif status == "ok" and not allure.get("failures"):
            lines.append(
                "Allure contains no failures, but pytest reported failure. The run remains unsuccessful."
            )
            next_step = (
                "Investigate the disagreement between pytest output and this run's Allure files."
            )
        elif status == "ok":
            next_step = (
                "Inspect the reported assertions and application behavior before proposing a fix."
            )
        else:
            next_step = "Investigate the Allure lookup error using this run's pytest output."

    lines.append(f"Next step: {next_step}")
    return {"report": "\n".join(lines)}
