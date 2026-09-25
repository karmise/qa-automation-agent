"""Command-line entry point for execution and read-only report review."""

import argparse
import json
import re
import sys

import server
from workflow import run_workflow


def main(argv: list[str] | None = None) -> int:
    """Return a nonzero exit code for failed execution or report persistence."""
    parser = argparse.ArgumentParser(description="Run or review framework unit-test triage")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run unit tests once and save the triage report")
    run.add_argument("--json", action="store_true", help="Print the structured workflow result")
    show = commands.add_parser("show", help="Read a saved result without running tests")
    show.add_argument("run_id")
    show.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "run":
        result = run_workflow()
        code = 0 if result["status"] == "passed" else 1
        if result["artifacts_status"] != "saved":
            print(f"Report save error: {result['artifacts_error']}", file=sys.stderr)
            code = 2
    else:
        if not re.fullmatch(r"[0-9a-f]{32}", args.run_id):
            print("Expected a 32-character lowercase hexadecimal run ID", file=sys.stderr)
            return 2
        try:
            result = json.loads((server.RUNS_DIR / args.run_id / "summary.json").read_text())
            if not isinstance(result, dict) or result.get("run_id") != args.run_id or not isinstance(result.get("report"), str):
                raise ValueError("Invalid saved summary or mismatched run ID")
        except (OSError, ValueError) as error:
            print(f"Cannot read saved report: {error}", file=sys.stderr)
            return 2
        code = 0
    print(json.dumps(result, indent=2) if args.json else result["report"])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
