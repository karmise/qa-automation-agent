"""Command-line entry point for execution, read-only triage, and report review."""

import argparse
import json
import logging
import sys
from pathlib import Path

from . import storage
from .runner import MARKERS, SUITES


def _write_outputs(result: dict, folder: str) -> None:
    """Save a read-only triage next to CI artifacts: report and bug-report drafts."""
    output = Path(folder)
    (output / "bug-reports").mkdir(parents=True, exist_ok=True)
    (output / "report.md").write_text(result["report"] + "\n", encoding="utf-8")
    for cluster_id, text in result.get("bug_reports", {}).items():
        (output / "bug-reports" / f"{cluster_id}.md").write_text(text, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    """Return a nonzero exit code for failed execution or report persistence."""
    parser = argparse.ArgumentParser(description="Run, triage, or review Restful Booker tests")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Run one suite once and save the triage report")
    run.add_argument("--suite", choices=SUITES, default="unit")
    run.add_argument("--marker", choices=MARKERS)
    run.add_argument("--llm", action="store_true", help="Ask the configured model for a review")
    run.add_argument("--json", action="store_true", help="Print the structured workflow result")
    triage = commands.add_parser(
        "triage", help="Triage an existing Allure results directory without running tests"
    )
    triage.add_argument("results_dir")
    triage.add_argument("--llm", action="store_true", help="Ask the configured model for a review")
    triage.add_argument("--out", help="Also write report.md and bug-reports/ to this directory")
    triage.add_argument("--json", action="store_true")
    show = commands.add_parser("show", help="Read a saved result without running tests")
    show.add_argument("run_id")
    show.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s", stream=sys.stderr)

    if args.command == "run":
        # LangGraph is imported only here, so read-only triage works with the standard library.
        from .workflow import run_workflow

        result = run_workflow(args.suite, args.marker, use_llm=args.llm)
        code = 0 if result["status"] == "passed" else 1
        if result["artifacts_status"] != "saved":
            print(f"Report save error: {result['artifacts_error']}", file=sys.stderr)
            code = 2
    elif args.command == "triage":
        from .pipeline import triage_results

        result = triage_results(args.results_dir, use_llm=args.llm)
        code = {"passed": 0, "unsuccessful": 1}.get(result["status"], 2)
        if args.out:
            try:
                _write_outputs(result, args.out)
            except OSError as error:
                print(f"Cannot write triage output: {error}", file=sys.stderr)
                code = 2
    else:
        try:
            result = storage.read_summary(args.run_id)
        except (OSError, ValueError) as error:
            print(f"Cannot read saved report: {error}", file=sys.stderr)
            return 2
        code = 0
    print(json.dumps(result, indent=2) if args.json else result["report"])
    return code


if __name__ == "__main__":
    raise SystemExit(main())
