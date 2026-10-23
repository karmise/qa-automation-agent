# Five-minute demo: AI-assisted failure triage

A walkthrough for showing what an agent adds to an existing test automation
setup. Everything runs locally against the public Restful Booker sandbox.

## Before the call

```bash
cd qa-automation-agent
.venv/bin/python -m pytest tests -q              # harness is green
.venv/bin/python qa.py run --suite api           # green baseline, gives history
.venv/bin/python -m demo.run_demo release-regression > /tmp/regression.md
.venv/bin/python -m demo.run_demo outage > /tmp/outage.md
```

Keep both reports open. Live runs take about a minute each and depend on the
public sandbox; the saved reports are the fallback (`qa.py show <run_id>`).

## 1. The problem (30 seconds)

> "Your suite tells you *what* failed. On a red nightly run somebody still opens
> Allure, reads stack traces and HTTP logs, and decides: product bug, broken
> environment, broken test, or known defect. That is repetitive, and it is where
> I would start with AI — not in writing more tests."

## 2. Mixed causes in one run (2 minutes)

Show `release-regression`. A local proxy injected three faults into the live
sandbox: a changed validation message, a 503 from the report service, and a
missing field in the branding response.

Walk through the table at the top: four red tests, three distinct causes.

- **Branding contract** — schema says `contact.email` is required and missing.
  Suspected contract change; a bug-report draft with the exact request exists.
- **Booking validation text** — expected "Firstname should not be blank", got
  "First name is required". Suspected product change. The draft contains the
  request body to reproduce it.
- **Report service 503** — gateway/availability error: environment, no bug.

Point at "Why the rules think so": every verdict has visible reasons, and the
history column says whether the test passed in the previous run. A test counts
as flaky only when it passes and fails with the same cause.

A real example from the plain sandbox, without any injected fault: one test
failed because `GET /api/room` timed out inside a setup or cleanup fixture. The
report shows that the test body was not at fault and classifies it as
environment, not as a booking defect.

## 3. One outage, many red tests (1 minute)

Show `outage`: every room, booking, and message call returned 502. In the
verified run, 21 of 26 tests failed and the report has exactly one environment
cluster that states they share one root cause; the 5 auth and branding tests
still passed. Failures inside setup fixtures are attributed to the 502, not to
the test code.

> "Without grouping, that is many tickets or many minutes. With it, it is one
> line: the environment is down."

## 4. Where the model comes in (1 minute)

The rules do bookkeeping: evidence, grouping, categories. The model does
judgment and wording: it reviews each cluster, may disagree with the rules
(shown as DISAGREES), and rewrites bug-report drafts. Two ways to run it:

- In Claude Code through MCP: "Why did the API tests fail?" → the
  agent calls `triage_tests` once and explains the clusters.
- Headless: `qa.py triage <dir> --llm` sends compact, masked evidence to
  `claude -p` with no tools and validates the JSON answer.

Safety in one sentence each:

- Test output is untrusted data (`demo.run_demo prompt-injection` puts
  instructions into an HTTP body; they stay quoted evidence).
- E-mails, card-length numbers, and code/pin/token fields are masked before
  any model call.
- The model cannot change the pytest verdict and the tool never reruns tests.

## 5. CI (30 seconds)

The Restful Booker workflow runs `qa.py triage` after a failed API or UI job.
It needs only the Python standard library, writes the report to the GitHub job
summary, uploads bug-report drafts, and cannot change the job result.

## How this maps to a team's existing automation

1. Start read-only: run `triage` on existing CI artifacts. No change to tests.
2. Adapt the evidence parser and rules to the team's assertion messages and
   logs. This is days, not weeks, because the rules are small and visible.
3. Add the data-masking list for the domain before any model call
   (for prepaid products: codes, PINs, serials, card numbers, client e-mails).
4. Measure: time from red build to diagnosis, share of clusters where the
   human agreed with the category, and false "product" alarms.
5. Only then add the model review, and record agreement in an evaluation log.

## Honest limits

- The rules are tuned to this framework's messages and logs.
- Flaky detection uses saved history only; nothing is rerun automatically.
- Bug reports are drafts for a person to reproduce and file.
- The CI step is defined but has not yet been observed on a real failing run.
