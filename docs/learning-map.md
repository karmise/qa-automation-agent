# Review guide and capability mapping

## One complete run

A user asks why the Restful Booker API tests fail. The coding agent selects the
`triage-test-failures` skill and calls `triage_tests(suite="api")` once. The MCP
tool calls `qa_agent.workflow.run_workflow`, which invokes a fresh LangGraph
state. The runner allocates a run ID and executes only the allowed suite with
the target project's Python.

When pytest ran (exit 0 or 1), the graph reads that run's Allure directory and
rejects evidence with another run ID. The triage step builds one signature per
cause (host for outages, endpoint for HTTP status errors, normalized message
otherwise), classifies each cluster with visible rules, and adds history from
earlier runs of the same suite and Git changes since the previous run. Only
when asked and when there are clusters, a model reviews them. The report keeps
pytest's verdict, lists causes with evidence and next steps, and the workflow
saves `report.md`, bug-report drafts, and `summary.json`.

`qa.py triage <dir>` runs the same pipeline without LangGraph or execution, for
CI artifacts. Reviewing a saved run enters neither the graph nor pytest.

## What the first version taught

The first version ran only the unit suite and reformatted pytest output. It was
a correct harness with no use case: `pytest tests/unit` was faster and clearer.
The value of an agent appears where the input is unstructured and needs
judgment: many red tests from one outage, a failure in a cleanup fixture after a
passing test body, a changed validation text versus a broken gateway. That is
why this version spends most of its code on evidence and causes, and keeps the
model at the edge, where wording and disagreement matter.

## Concepts to explain in your own words

1. Why the agent and target framework have different virtual environments.
2. How an MCP tool differs from a Python function and from a skill.
3. What the graph state contains and how both conditional edges choose a path.
4. Why one cause can produce 26 red tests, and how the signature groups them.
5. Why a teardown timeout after passing steps is not a product defect.
6. Why an empty failure list cannot prove success after pytest exits 1.
7. Why rules come first and the model second; what each is better at.
8. Why the model has no tools, receives evidence marked as untrusted, and
   cannot change the verdict.
9. How saved history and Git changes lower or raise confidence.
10. Why passing harness tests do not demonstrate correct LLM decisions.

## Capability mapping

| Capability | Implemented evidence | Honest limitation |
| --- | --- | --- |
| Useful AI in a QA process | Failure triage that groups red runs by cause, with bug-report drafts; verified on the live sandbox with injected faults | Rules are tuned to one framework's messages |
| MCP integration | Local server, typed tool arguments, real stdio client test, read-only and executing tools | No hosted multi-user MCP service |
| Agent Skills | Packaged skill with scope, tool choice, no-retry and untrusted-output rules; project skills in the Booker repo | Manual eval results must be recorded from real sessions |
| Agentic workflows | LangGraph with two decision points; optional model node | The model step is optional; no autonomous code repair |
| Prompt-injection awareness | Evidence marked untrusted, block escaping, no tools, validated output, demo scenario | Not a guarantee against every model behavior |
| Data protection | E-mails, card-length numbers, and code/pin/token fields masked before any model call | Pattern-based; a real system needs its own field list and review |
| Harness building | Timeouts, run isolation, evidence identity checks, regression suite, CI definition | Not a production reliability guarantee |
| CI integration | Standard-library triage step writing to the GitHub job summary | Not yet observed in a real GitHub Actions failure run |
| Evaluation | 134 deterministic tests; manual behavior cases 1–10 | Cases 4–10 are prepared, not recorded live evaluations |

## Deliberately outside this project

Automatic ticket filing, automatic test or code repair, automatic reruns,
model benchmarks, cost tracking, and production monitoring. Do not present this
project as evidence of production experience with those capabilities.

## Refactoring decisions

- Keep CLI and MCP as thin adapters so execution does not depend on either transport.
- Keep the triage pipeline in the standard library so CI needs no installation.
- Keep report rendering pure and progress logging separate from protocol output.
- Show rule reasons and model disagreements instead of hiding either.
- Preserve existing tool names and entry points to avoid breaking installed MCP configuration.
- Test observable behavior and boundary failures, including real stdio transport.
