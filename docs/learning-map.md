# Review guide and vacancy mapping

## One complete run

A user identifies the Restful Booker unit suite. The coding agent selects the
triage skill and calls `triage_unit_tests` once. The MCP tool calls
`workflow.run_workflow`, which invokes a fresh LangGraph state. The runner loads
configuration, allocates a run ID, and invokes the target project's Python.

The conditional edge chooses either reporting or Allure lookup. Failed-test
results are read only from the allocated run directory. The identity guard
rejects unrelated evidence. The report retains pytest's verdict, discloses
missing evidence, and suggests an investigation step. The workflow saves both
text and structured evidence and returns them through MCP to the coding agent.

The CLI enters at `workflow.run_workflow` directly and uses exactly the same
graph. Reviewing a saved report enters neither the graph nor pytest.

## Concepts to explain in your own words later

1. Why the agent and target framework have different virtual environments.
2. How an MCP tool differs from a Python function and from a skill.
3. What the graph state contains and how a conditional edge selects the next node.
4. Why a unique run directory matters when old failures remain on disk.
5. Why timeout, failed assertion, and unavailable diagnostics are different outcomes.
6. Why an empty failure list cannot prove success after pytest exits 1.
7. What mocking replaces, and what the real stdio transport test still exercises.
8. Why passing harness tests does not demonstrate correct LLM decisions.
9. How saved JSON, timestamps, and JUnit artifacts support investigation.
10. What evidence is still needed before claiming production AI/MLOps experience.

## Vacancy mapping

| Requirement | Implemented evidence | Honest limitation |
| --- | --- | --- |
| MCP integration | Local server, typed tool arguments, real stdio client test, complete workflow tool. | No hosted multi-user MCP service. |
| Agent Skills | Packaged skill, explicit scope, tool selection and no-retry rules. | Manual eval results must be recorded from actual agent sessions. |
| Agentic workflows | Coding agent invokes a multi-step LangGraph workflow for test triage. | Python graph is deterministic; no autonomous code repair. |
| Daily coding agent use | This repository was developed with a coding agent. | Personal understanding and continued independent practice are still necessary. |
| Harness building | Timeouts, run isolation, evidence checks, regression suite, CI definition. | Not a production reliability guarantee. |
| LangGraph / LangChain | Working LangGraph state and conditional routing. | No separate LangChain model integration or LLM node. |
| Evaluation / monitoring | Harness regression tests, manual behavior cases, run metadata and saved evidence. | No model quality dashboard, drift monitoring, cost tracking, or production MLOps. |

## Deliberately outside this completed local workflow

Paid API calls, model-provider credentials, model benchmarks, production
monitoring, automatic defect tickets, and automatic test/code repair are not
implemented. An actual LLM node can be a later extension once a model runtime
and cost policy are selected. Do not present this project as evidence of
production experience with those capabilities.
