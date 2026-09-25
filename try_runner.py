"""Demonstrate the low-level runner without import-time execution."""

import json

from qa_agent.runner import run_unit_tests

if __name__ == "__main__":
    print(json.dumps(run_unit_tests(), indent=2))
