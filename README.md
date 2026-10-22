# QA Automation Agent

Failure triage for the
[Restful Booker test framework](https://github.com/karmise/restful-booker-test-automation):
it turns a red test run into **a short list of distinct causes**, each with its
evidence, a likely category, and a next step.

```text
21 red tests  ->  1 cause: the gateway returned 502 for room, booking, message (environment)
4 red tests   ->  3 causes: booking validation text changed (product?),
                  branding lost a required field (contract?),
                  report service answered 503 (environment)
```

## Why it exists

A test framework says *what* failed. Somebody still has to open Allure, read
stack traces and HTTP logs, and decide whether this is a product bug, a broken
environment, a broken test, or a known defect. On a red nightly run that is the
first 10–30 minutes of a QA engineer's morning, every time.

This tool does the repeatable part of that work:

| Step | How | Model needed |
| --- | --- | --- |
| Collect evidence | Parse Allure results: failing phase (setup/test/teardown), fixture, failed step, expected vs actual, the HTTP exchange the message refers to, screenshots | no |
| Group by cause | One signature per cause: an outage is one cluster, not 26 bugs | no |
| Classify with visible rules | environment, suspected product defect, test defect, known defect, known defect fixed, needs review — each with its reasons | no |
| Add context | Saved run history (new failure vs recurring vs flaky) and Git changes since the previous run (was the test itself changed?) | no |
| Draft bug reports | Reproducible request, expected, actual, affected tests | no |
| Review and explain | A coding agent (Claude Code, Codex) reads the clusters through MCP and explains or disagrees; optionally a headless model reviews them | yes |

The rules do the bookkeeping; the model does the judgment and the wording. The
model never changes the pytest verdict, has no tools in headless mode, and its
opinion is shown next to the rules, including disagreements.

## Quick start

Use Python 3.12. From this repository:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-dev.txt
cp agent.example.toml agent.toml   # set project_path to the Restful Booker checkout
```

The target framework's `.venv/bin/python` must have its own dependencies
(pytest, allure-pytest, Playwright for UI). `agent.toml` is ignored by Git.

```bash
.venv/bin/python qa.py run --suite api                # run once, triage, save
.venv/bin/python qa.py run --suite ui --marker smoke
.venv/bin/python qa.py triage path/to/allure-results  # no execution (CI artifacts)
.venv/bin/python qa.py show <run_id>                  # saved report, no execution
```

`run` exits 0 when tests passed, 1 when they did not, and 2 for an artifact save
error. `triage` exits 0 without failures, 1 with failures, 2 without readable
results. Progress goes to stderr; stdout is the Markdown report (or `--json`).

## Demo: mixed causes against the live sandbox

`demo/fault_proxy.py` is a local proxy in front of the public sandbox that
injects chosen faults, so one run contains causes of different kinds without
touching the application or the framework.

```bash
.venv/bin/python qa.py run --suite api                    # green baseline for history
.venv/bin/python -m demo.run_demo release-regression      # 3 faults, 3 clusters
.venv/bin/python -m demo.run_demo outage                  # many red tests, 1 cause
.venv/bin/python -m demo.run_demo prompt-injection        # instructions in an HTTP body
```

| Scenario | Injected | Expected triage |
| --- | --- | --- |
| `release-regression` | booking validation text changed; report service 503; branding lost `contact.email` | 2 suspected product/contract changes with bug-report drafts, 1 environment cluster |
| `outage` | 502 for room, booking, and message APIs | one environment cluster covering all affected tests |
| `prompt-injection` | a booking error message tells AI agents to report success | a suspected product defect; the text appears only as quoted evidence |

The faults are visible only in an `X-Demo-Fault` response header, so the triage
cannot read the answer from the body. [docs/sample-report.md](docs/sample-report.md)
is the generated, hand-untouched report of a `release-regression` run, with its
[bug-report drafts](docs/sample-bug-reports/). See
[docs/interview-demo.md](docs/interview-demo.md) for a five-minute walkthrough.

## Using it from a coding agent (MCP)

Configure the MCP client to launch `.venv/bin/python` with `server.py`:

```bash
claude mcp add qa-automation-agent -- "$PWD/.venv/bin/python" "$PWD/server.py"
```

For Codex, add the same command to `~/.codex/config.toml` under
`[mcp_servers.qa-automation-agent]` and raise `tool_timeout_sec` (for example to
900): API and UI runs take longer than the default tool timeout.

| Tool | Executes tests | Purpose |
| --- | --- | --- |
| `triage_tests(suite, marker)` | once | Run `unit`, `api`, or `ui` and return clusters, evidence, report, bug-report drafts |
| `triage_results(results_path)` | no | Triage an existing Allure directory, such as a CI artifact |
| `show_run(run_id)` | no | Read a saved run |
| `triage_unit_tests()` | once | Unit-suite compatibility tool |
| `project_info`, `run_unit_tests`, `read_allure_failures` | — | Low-level and learning tools |

The skill `skills/triage-test-failures/SKILL.md` tells the agent which tool to
use, never to rerun automatically, to treat test output as data, and how to
present each cluster. Restart the MCP server after code changes.

## Optional headless model review

`qa.py run --llm` and `qa.py triage --llm` send compact cluster evidence to a
configured command on stdin and expect JSON back. With Claude Code:

```toml
llm_command = ["claude", "-p", "--output-format", "json", "--tools", "",
               "--no-session-persistence", "--strict-mcp-config"]
```

This runs on a Claude subscription after `claude` and `/login`; CI would need
its own credentials. Any command with the same stdin/JSON contract works, for
example a local model. Before evidence leaves the machine, e-mail addresses,
card-length numbers, and values of fields such as `code`, `pin`, `cardNumber`,
`voucher`, and `token` are masked; the local report keeps them. The prompt
marks evidence as untrusted, the evidence
block cannot be closed by test output, the output is validated against the
known clusters and categories, and failures are reported as statuses
(`timeout`, `command_error`, `invalid_output`) instead of breaking triage.

## In CI

`qa.py triage` uses only the Python standard library. The Restful Booker
workflow clones this repository after a failed API or UI job, writes the
report to the GitHub job summary, and uploads bug-report drafts; the step
cannot change the job result.

## Configuration

| Setting | Purpose |
| --- | --- |
| `project_path` | Target framework directory (required). |
| `python_path` | Optional interpreter override; default is the target's `.venv/bin/python`. |
| `timeout_seconds` | Test execution limit, 1–3600; default 900. |
| `env` | Table of extra variables for the test process, such as `RBP_BASE_URL`. |
| `llm_command`, `llm_timeout_seconds` | Optional model review command (argument list, no shell) and its limit. |
| `QA_AGENT_CONFIG` | Environment override for the TOML file location. |
| `QA_PROJECT_PATH`, `QA_PYTHON_PATH` | Environment overrides for the target and interpreter. |
| `QA_RUNS_DIR` | Environment override for the artifact directory. |

Only the fixed suites `unit`, `api`, `ui` and markers `smoke`, `regression` can
be executed; agent-supplied values never become arbitrary pytest arguments.

## Evidence and control flow

```text
execute_tests --(exit 0 or 1)--> read_evidence --> triage_failures --(--llm and clusters)--> review_with_model
      |                                                   |                                        |
      +-- (timeout, launch error, exit 2-5) --------------+---------------> build_report <---------+
```

1. Generate a run ID and execute the chosen suite once, with a timeout.
2. Read that run's own Allure directory; reject evidence with another run ID.
3. Cluster and classify failures; add history from earlier runs of the same
   suite and Git changes since the previous run.
4. Optionally ask a model for a second opinion.
5. Save `report.md`, `bug-reports/`, and `summary.json` (canonical, written last).
   Never retry automatically.

Each run has its own directory:

```text
runs/<run_id>/
  allure-results/   # written by pytest
  playwright/       # UI screenshots and traces
  bug-reports/      # drafts for suspected product clusters
  report.md         # Markdown report
  summary.json      # structured evidence, clusters, outcomes, timing
```

Missing or partial Allure results never override a failed pytest result.
Categories are hypotheses: every cluster carries the reasons that produced it.

## Validation

```bash
.venv/bin/python -m pytest tests -v
.venv/bin/ruff check .
.venv/bin/ruff format --check .
```

The suite covers evidence parsing, classification rules, clustering, history,
Git awareness, graph routing, run correlation, persistence, the CLI, the model
command contract (including prompt-injection boundaries), the demo proxy, the
in-memory MCP protocol, and a real stdio MCP subprocess. It never executes the
real Restful Booker suite. `evals/cases.md` holds manual coding-agent behavior
cases that unit tests cannot replace.

## Files

| File | Responsibility |
| --- | --- |
| `qa_agent/settings.py` | Immutable, validated configuration. |
| `qa_agent/runner.py` | Bounded execution of one allowed suite. |
| `qa_agent/evidence.py` | Allure results to structured per-test evidence. |
| `qa_agent/triage.py` | Cause signatures, classification rules, clusters, history. |
| `qa_agent/git_context.py` | Tested commit and changes since the previous run. |
| `qa_agent/llm.py` | Optional model review: prompt, output validation. |
| `qa_agent/reporting.py` | Markdown report and bug-report drafts (pure). |
| `qa_agent/pipeline.py` | Shared steps; read-only triage for CI (standard library). |
| `qa_agent/graph.py` | LangGraph routing between the steps. |
| `qa_agent/workflow.py` | Run the graph once and persist the result. |
| `qa_agent/storage.py` | Run identity, atomic saves, history lookup. |
| `qa_agent/mcp_server.py`, `qa_agent/cli.py` | Thin transport adapters. |
| `demo/` | Fault-injecting proxy and one-command demo scenarios. |

## Limits

- Rules are tuned to this framework's messages (`has_status`, schema
  registry, resource lifecycle, HTTP log format). Another framework needs its
  own evidence parser and rules.
- Flaky detection uses saved local history only; it never reruns tests.
- No automatic ticket filing or code repair: drafts are for a person to verify.
- `docs/learning-map.md` records what this project does and does not demonstrate.
