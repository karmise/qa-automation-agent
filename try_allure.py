"""Inspect one run's Allure evidence without executing tests."""

import argparse
import json

from qa_agent.allure import read_allure_failures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_id", help="The ID returned by a previous execution")
    args = parser.parse_args()
    print(json.dumps(read_allure_failures(args.run_id), indent=2))


if __name__ == "__main__":
    main()
