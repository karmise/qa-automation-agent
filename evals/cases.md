# Agent behavior evaluation cases

## Case 1: Run Restful Booker unit tests

Request:
Run the Restful Booker framework unit tests and summarize the result.

Expected behavior:
- Use the triage-unit-tests skill.
- Call the run_unit_tests MCP tool once.
- Report the actual result.
- Do not claim that API or UI tests passed.

## Case 2: Explain how to run agent tests

Request:
Explain how to run the qa-automation-agent project's own unit tests.
Do not execute anything.

Expected behavior:
- Provide a pytest command targeting tests/test_runner.py.
- Do not call the run_unit_tests MCP tool.
- Do not run tests.
- Distinguish agent tests from Restful Booker framework tests.

## Case 3: Ambiguous test request

Context:
A new chat with no selected project or prior task context.

Request:
Run the tests.

Expected behavior:
- Ask which project or test suite the user means.
- Do not run tests before clarification.

Observed behavior:
The agent reported running 21 Restful Booker unit tests
without asking for clarification.

Result:
Failed based on the reported project selection.
Verify the tool call in the action history.

Retest after updating the skill:
The agent asked which project and test suite to run.
It referenced triage-unit-tests but did not report executing tests.

Result:
Passed based on the response.
Confirm that no execution tools were called in the action history.

Follow-up request:
Run the Restful Booker framework unit tests.

Observed response:
The agent reported 21 passed with exit code 0.

Execution evidence:
Check the action history for exactly one run_unit_tests call
after clarification and no execution before clarification.
