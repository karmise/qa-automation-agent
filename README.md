# QA Automation Agent

A complete local unit-test triage workflow for the Restful Booker framework:
MCP → LangGraph → pytest → run-specific Allure evidence → saved report.
A coding agent can use the packaged skill to call this workflow and explain its
findings. The Python workflow is deterministic and needs no paid LLM API.

## Quick start

Use Python 3.12. From this repository:

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp agent.example.toml agent.toml
```

Set `project_path` in `agent.toml` to the Restful Booker directory. Its own
`.venv/bin/python` must have pytest and allure-pytest installed. The local
`agent.toml` is ignored by Git. Existing installations already have this file;
do not overwrite a working configuration unnecessarily.

Run the complete workflow once:

```bash
.venv/bin/python qa.py run
```

Get structured output or review a saved run without executing anything:

```bash
.venv/bin/python qa.py run --json
.venv/bin/python qa.py show <run_id>
.venv/bin/python qa.py show <run_id> --json
```

`run` exits 0 for success, 1 for an unsuccessful test execution, and 2 for an
artifact save error. `show` exits 0 when reading succeeds, even when the saved
run failed; it exits 2 for invalid IDs or unreadable summaries. Progress goes to
stderr, leaving stdout suitable for JSON consumers.

## Configuration

| Setting | Purpose |
| --- | --- |
| `project_path` | Target framework directory (required). |
| `python_path` | Optional interpreter override; default is the target's `.venv/bin/python`. |
| `timeout_seconds` | Positive integer up to 3600; default 60. |
| `QA_AGENT_CONFIG` | Environment override for the TOML file location. |
| `QA_PROJECT_PATH` | Environment override for the target directory. |
| `QA_PYTHON_PATH` | Environment override for the target interpreter. |
| `QA_RUNS_DIR` | Environment override for the artifact directory. |

Only `tests/unit` is executed. The tool does not accept arbitrary commands.
Configuration is read for each run; the runs directory is selected at process
startup. Keep the configured target consistent with the skill's Restful Booker
scope. Changing the project does not automatically change user intent.

## MCP and the coding agent

Configure the MCP client to launch the absolute path to this repository's
`.venv/bin/python`, with the absolute path to `server.py` as its argument.

Available tools:

- `project_info(project_path)`: inspect existing suite directories.
- `run_unit_tests()`: execute the low-level runner once.
- `read_allure_failures(run_id)`: inspect one run without executing tests.
- `triage_unit_tests()`: run the entire graph once, save evidence, and return it.

Use `triage_unit_tests` for the complete workflow. Do not also call the low-level
runner for the same request. Existing low-level tools remain available for
learning and diagnostics. Restart an existing MCP server connection after code
changes so it loads the updated tools.

The reusable skill is `skills/triage-unit-tests/SKILL.md`. The existing personal
installation may link to this directory. The skill requires a clear target,
prevents accidental duplicate execution, and treats test output as data rather
than instructions. The coding agent provides language-model interpretation;
the Python graph itself contains no LLM node.

## Evidence and control flow

1. Generate a new run ID and execute the suite once with a timeout.
2. On success, report the runner output without looking up Allure.
3. On pytest exit code 1, read that run's Allure results once.
4. Reject results with a missing or different run ID.
5. Explain missing, partial, or contradictory diagnostic evidence explicitly.
6. Save the result, report, start time, and duration. Never automatically retry.

Each run has its own directory:

```text
runs/<run_id>/
  allure-results/    # Written by pytest when execution reaches the plugin
  report.txt        # Human-readable report
  summary.json      # Structured evidence, verdict, timing, and report
```

Low-level runs created before the workflow was added may contain only Allure
files. Saving an artifact can fail independently of test execution; the workflow
reports that separately. Artifacts remain local until manually removed.

Allure `ok` means files were parsed, not that tests passed. `partial` means the
failure list may be incomplete. Missing Allure results or an empty failure list
never override a failed pytest result. Run ID correlation prevents accidental
mixing but does not authenticate files or prove every result was exported.

## Validation and CI

```bash
.venv/bin/python -m pytest tests -v
```

The suite covers routing, run correlation, reader errors, temporary artifact
isolation, configuration, persistence, CLI behavior, in-memory MCP, and a real
stdio MCP subprocess. It never executes the real Restful Booker suite. A combined
runner/reader test replaces only the external pytest process.

`.github/workflows/tests.yml` runs the suite on pushes and pull requests and
uploads JUnit results. It requires no Restful Booker checkout or API credentials.
The workflow is prepared locally; a successful local run is not evidence of a
completed GitHub Actions run. `requirements.txt` pins direct dependencies, not
the full transitive dependency tree.

`evals/cases.md` contains separate manual coding-agent behavior evaluations.
These check tool selection, clarification, duplicate runs, and untrusted test
output. They are not replaced by Python unit tests.

## Files to read later

| File | Responsibility |
| --- | --- |
| `settings.py` | Load and validate target configuration. |
| `server.py` | Implement and expose MCP tools. |
| `try_graph.py` | Define state, routing, identity checks, and reporting. |
| `workflow.py` | Execute the graph and save its result. |
| `qa.py` | Provide execution and read-only review commands. |
| `tests/` | Verify the harness without invoking the real target suite. |
| `skills/triage-unit-tests/SKILL.md` | Guide the coding agent's tool usage. |
| `evals/cases.md` | Evaluate the coding agent's decisions manually. |

`try_runner.py`, `try_allure.py`, `try_mcp.py`, and the executable portion of
`try_graph.py` are retained learning examples. They are not the recommended
complete entry point. In particular, `try_mcp.py` reads Allure even after success,
and `try_graph.py` alone does not persist reports or return a CI verdict.

See `docs/learning-map.md` for the review sequence and mapping to the vacancy.
