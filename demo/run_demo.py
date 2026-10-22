"""One-command demo: run the API suite through the fault proxy and print the triage.

    .venv/bin/python -m demo.run_demo release-regression
    .venv/bin/python -m demo.run_demo prompt-injection --llm

The proxy runs only for the duration of this command; nothing else is changed.
"""

import argparse
import io
import os
import sys

from demo.fault_proxy import SCENARIOS, start
from qa_agent import cli


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("scenario", choices=SCENARIOS, nargs="?", default="release-regression")
    parser.add_argument("--suite", choices=("api", "ui"), default="api")
    parser.add_argument("--llm", action="store_true", help="Ask the configured model for a review")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    log = io.StringIO()
    server = start(args.scenario, log=log)
    host, port = server.server_address[:2]
    # The runner passes its environment to pytest, so the framework targets the proxy.
    os.environ["RBP_BASE_URL"] = f"http://{host}:{port}"
    print(f"Scenario '{args.scenario}': proxy on {os.environ['RBP_BASE_URL']}", file=sys.stderr)
    try:
        command = ["run", "--suite", args.suite]
        command += ["--llm"] if args.llm else []
        command += ["--json"] if args.json else []
        code = cli.main(command)
    finally:
        server.shutdown()
    injected = [line for line in log.getvalue().splitlines() if "[fault:" in line]
    print(f"\nProxy injected {len(injected)} faulty responses:", file=sys.stderr)
    for line in sorted(set(injected)):
        print(f"  {line}", file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
