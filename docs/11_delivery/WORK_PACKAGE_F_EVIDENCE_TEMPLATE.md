# Work Package F — QA/Red-Team Evidence Template

This template records acceptance evidence for one approved integration ref.
Documentation, component presence, local unit tests, fake adapters, skipped
tests, and same-process refreshes are not passing evidence for the hard gates.

## Run identity

| Field | Value |
|---|---|
| Approved integration ref | `72eec31d178e14a32aa6a05b4189c8c515119975` |
| Branch/worktree | |
| Commit author | |
| QA operator | |
| Date/time and timezone | |
| OS/runtime versions | |
| Database URL fingerprint (no secret) | |
| Fresh database name/identity | |
| Migration head | |
| Browser/runtime | |

## Scenario result

Use one copy of this section per scenario in
`tests/acceptance/work_package_f_scenarios.py`.

| Field | Value |
|---|---|
| Scenario ID | `F-__` |
| Status | `PASS` / `FAIL` / `BLOCKED` / `NOT_RUN` |
| Hard gate | |
| Start command | |
| Application start command | |
| HTTP request command/tool | |
| Browser flow | |
| Database query command | |
| Process restart command | |

### Evidence

| Evidence type | Exact artifact/locator | Observation |
|---|---|---|
| Ref identity | | |
| Default `create_app` proof | | |
| Real HTTP request/response | | |
| PostgreSQL schema/rows | | |
| Restart process A/B logs | | |
| Browser URL/title/DOM | | |
| Screenshot path | | |
| Console warnings/errors | | |
| Provenance chain | | |
| Audit/outbox/deletion proof | | |

### Red-team counterexample

| Attack/state | Expected | Actual | Status |
|---|---|---|---|
| Replay with same idempotency key | | | |
| Replay with changed payload | | | |
| Deleted source/readback | | | |
| Cross-family request | | | |
| Cross-tenant request | | | |
| Missing Guardian | | | |
| Revoked/expired Guardian or consent | | | |
| Provider/context failure | | | |

### Verdict rule

`PASS` requires every hard gate and every required proof. Any skipped test,
fake/in-memory substitute, missing browser proof, missing fresh-PostgreSQL
proof, or unexplained warning is `FAIL` or `BLOCKED`, never `PASS`.

## Final sign-off

| Gate | Result | Evidence reference |
|---|---|---|
| Same approved ref for A–E and F | | |
| Default composition root | | |
| Real HTTP | | |
| Fresh PostgreSQL | | |
| Restart readback | | |
| Browser golden path | | |
| Two-family difference | | |
| Guardian four states | | |
| Published Knowledge provenance | | |
| ModelGateway provenance | | |
| Replay/deletion/cross-scope negatives | | |

**Overall verdict:** `PASS` / `FAIL` / `BLOCKED`

**Blocking findings:**

1. 
