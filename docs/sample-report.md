# Test triage: api suite

- **Run ID:** `3809dd67897e40289840384b4cfec80f`
- **Status:** unsuccessful
- **Exit code:** 1
- **Scope:** Restful Booker api tests. Other suites were not run.
- **Target:** http://127.0.0.1:54637 · commit `9f02558440` on feature/agent-ready with 2 uncommitted files

## Summary

24 executed: 20 passed, 4 failed, 0 broken. 2 known defects (expected failures).

## What needs attention: 4 failed tests, 3 distinct causes

| Cluster | Likely cause | Confidence | Tests | Signal |
| --- | --- | --- | --- | --- |
| C1 | Suspected product defect or contract change | medium | 1 | Response does not match JSON Schema 'branding': |
| C2 | Suspected product defect or contract change | medium | 1 | Expected API error to contain 'Firstname should not be blank', but response was: {"errors… |
| C3 | Environment or infrastructure | high | 2 | A confirmed booking should block the same dates in the reservation calendar |

### C1 · Suspected product defect or contract change · confidence: medium

**Why the rules think so**
- The response no longer matches its JSON Schema: a contract change, or the schema in the tests is outdated.

**Affected tests (1)**
- Branding matches the public contract — `tests/api/test_branding_api.py::test_branding_matches_public_contract` (phase: call; new failure)

**Evidence**
```text
AssertionError: Response does not match JSON Schema 'branding':
- $.contact: 'email' is a required property
-> GET http://127.0.0.1:54637/api/branding
<- 200 {"address":{"county":"Dilbery","line1":"Shady Meadows B&B","line2":"Shadows valley","postCode":"N1 1AA","postTown":"Newingtonfordburyshire"},"contact":{"name":"Shady Meadows B&B","phone":"012345678901"},"description":"Welcome to Shady Meadows, a delightful Bed & Breakfast nestled in the hills on Newingtonfordburyshire. A place so beautiful you will never want to leave. All our rooms have comfortable beds and we provide breakfast from the locally sourced supermarket. It is a delightful place.","directions":"Welcome to Shady Meadows, a delightful Bed & Breakfast nestled in the hills on N…
```

**Next step:** Reproduce the captured request manually. If the behavior is confirmed and not an intended change, file the drafted bug report; if it is intended, update the contract.
**Bug report draft:** `bug-reports/C1.md`

### C2 · Suspected product defect or contract change · confidence: medium

**Why the rules think so**
- A business assertion failed in the test body at step 'Verify the API error message' after 2 passing steps.

**Affected tests (1)**
- Booking rejects invalid guest details — `tests/api/test_booking_api.py::test_booking_rejects_invalid_guest_details` (phase: call; failed before)

**Evidence**
```text
AssertionError: Expected API error to contain 'Firstname should not be blank', but response was: {"errors": ["First name is required", "size must be between 3 and 18", "size must be between 11 and 21", "must be a well-formed email address"]}
-> POST http://127.0.0.1:54637/api/booking {"bookingdates":{"checkin":"2026-12-21","checkout":"2026-12-23"},"depositpaid":false,"email":"invalid-email","firstname":"","lastname":"Guest1b037546","phone":"123","roomid":45}
<- 400 {"errors":["First name is required","size must be between 3 and 18","size must be between 11 and 21","must be a well-formed email address"]}
```

**Next step:** Reproduce the captured request manually. If the behavior is confirmed and not an intended change, file the drafted bug report; if it is intended, update the contract.
**Bug report draft:** `bug-reports/C2.md`

### C3 · Environment or infrastructure · confidence: high

**Why the rules think so**
- GET http://127.0.0.1:54637/api/report/room/52 answered 503: a gateway or availability error, typical for deployments and infrastructure problems.

**Affected tests (2)**
- Created booking appears as an unavailable room period — `tests/api/test_report_api.py::test_created_booking_appears_as_unavailable_room_period` (phase: call; new failure)
- New room report matches the public contract — `tests/api/test_report_api.py::test_new_room_report_matches_contract` (phase: call; new failure)

**Evidence**
```text
AssertionError: A confirmed booking should block the same dates in the reservation calendar
Expected: 200 OK
Actual: 503 Service Unavailable
Request: GET http://127.0.0.1:54637/api/report/room/52
Response body: <h1>503 Service unavailable</h1>
-> GET http://127.0.0.1:54637/api/report/room/52
<- 503 <h1>503 Service unavailable</h1>
```

**Next step:** Check the target environment's health. Rerun only after it recovers; this is not evidence of a product defect.

## Known defects (expected failures)
- Unknown room identifier returns not found — Known RBP defect: an unknown room returns 500 instead of 404
- Unknown message identifier returns not found — Known RBP defect: an unknown message returns 500 instead of 404

## Diagnostics
- Allure files read: 26/26

## Limits
- Categories are hypotheses from visible rules; the pytest verdict is authoritative.
- Nothing was rerun automatically. Flaky suspicion comes only from saved history.

**Next step:** Start with C1: Reproduce the captured request manually. If the behavior is confirmed and not an intended change, file the drafted bug report; if it is intended, update the contract.
