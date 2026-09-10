---
id: PLATFORM-CI-R0.5-STEP2-FINDINGS
title: R0.5 Step 2 — Order Dependency / Root Cause Findings
status: current
owner: chief-architect
updated: 2026-09-10
baseline_sha: 7e3041b5
---

# R0.5 Step 2 Findings

## Baseline

`git merge-base --is-ancestor 7e3041b5 HEAD` → success. Investigation
branch `infra/ci-postgres-isolation` includes the consent P0 fix.

## Case 01 — `test_course_release_baseline_routes.py`

```
failing nodeid: tests/domains/product_intelligence/test_course_release_baseline_routes.py::test_release_baseline_route_persists_approves_and_restores
failure signature: AttributeError: 'NoneType' object has no attribute 'send'
                    (during SQLAlchemy pool teardown's do_terminate ->
                    asyncpg connection.close() -> event loop.create_task
                    -> RuntimeError: Event loop is closed, surfaced as an
                    unraisable exception in a later teardown phase)
database URL class: fixed shared DATABASE_URL (not a per-test ephemeral db)
```

**B alone, 3 consecutive runs: FAIL / FAIL / FAIL** (100% reproducible with
zero predecessor tests — ran as the ONLY test collected in the process).

**ORDER_DEPENDENCY = NOT_APPLICABLE.** This case does not need any
predecessor A to fail — the R0.5 protocol's "B alone" step alone already
disproves cross-test pollution as this case's cause. Recording this
explicitly rather than skipping to A-then-B, since finding "B alone FAILS"
is itself conclusive evidence against the shared-database-pollution
hypothesis for this specific case.

**Engine-cache experiment** (no_cleanup / sync `clear_engine_cache()` /
async `await engine.dispose()` between test functions in this file): all
three modes produced **identical results** (2 failed, 2 passed, same
failure). This DISPROVES engine-cache disposal as this case's root cause —
directly contradicts the earlier (now retracted) hypothesis that
`_ENGINE_CACHE` cross-event-loop reuse was sufficient to explain this
failure. The engine identity reuse observed earlier is real but is a
correlated side-effect, not the causal mechanism for this specific failure.

**Actual root cause, isolated by direct reproduction**: the failing test
constructs the client as a bare `client = TestClient(create_app())` — never
using it as a context manager (`with TestClient(create_app()) as client:`).
Starlette's TestClient needs the `with` block to run ASGI lifespan
startup/shutdown and to correctly own the anyio blocking-portal/event-loop
bridge it uses to run the async app from sync test code. Without `with`,
that bridge's teardown races against the async Postgres connection's own
cleanup, producing "Event loop is closed" when the connection pool later
tries to gracefully close it.

**Direct fix verification**: reproduced the exact same HTTP call
(POST /product-intelligence/courses/release-baselines) wrapped in
`with TestClient(create_app()) as client:` instead of the bare form —
**zero errors**, clean 200 response, no teardown exception. This is a
minimal, targeted, one-line-per-call-site fix, not a CI infrastructure
change.

```
classification: TEST_FIXTURE_BUG
root cause confidence: CONFIRMED (direct before/after reproduction)
```

## Cross-file scope of the same defect pattern

`grep -rn "= TestClient(create_app())"` (bare form, no `with`) across the
repo found this pattern in **at least 11 files, 30+ call sites**, including
`test_assessment_routes.py` (the file with the recurring `assert 401 == 403`
and "attached to a different loop" failures from earlier R0 rounds),
`test_default_vertical_growth_http.py`, `test_need_fulfillment_e2e.py`,
`test_family_need_routes.py`, `test_engagement_router_mount.py`, and others.
Not every call site necessarily triggers the bug — it only manifests when
the app composition actually opens a real async Postgres engine during the
test (SQLite-only or dependency-overridden tests may never hit the code path
that races). This is consistent with why only some of these files showed up
as CI failures while others didn't.

**This is not an "isolation infrastructure" fix — it's a test-fixture
correctness fix**, scoped to `tests/` and possibly
`backend/domains/commerce/tests/` call sites. Recommending a follow-up
architecture test that forbids the bare `TestClient(create_app())` form
outside a `with` block, to prevent regression.

## Case 02 — journey_e2e_* database-not-found (assessment_http /
## course_release_baseline reports seen in earlier full-suite CI runs)

**Not yet independently re-verified with the same engine-identity-tracing
rigor as Case 01.** Given Case 01's disproof of the engine-cache-disposal
hypothesis, and given that `test_course_release_baseline_routes.py` is one
of the files reporting this exact symptom in CI, the leading hypothesis is
now that **this is the SAME root cause as Case 01** (bare TestClient
without `with`, in the same file) rather than an independent
cross-database-lifecycle leak. Not yet confirmed — flagging as
UNRESOLVED-BUT-LIKELY-SAME-AS-CASE-01, pending a repeat of Case 01's fix
applied to this file and a clean re-run.

```
classification: UNRESOLVED (leading hypothesis: same as Case 01)
root cause confidence: LOW-MEDIUM (not independently traced)
```

## Case 03 — platform_audit_events does not exist
## (test_s4_http_postgres_closure.py)

Not yet investigated this pass — no `TestClient(create_app())` bare-form
call site found in this file via grep, so it does NOT obviously share Case
01's mechanism. Requires independent B-alone / A-then-B / B-then-A
investigation.

```
classification: UNRESOLVED
root cause confidence: NONE YET
```

## Case 04 — test_daily_action_postgres.py HumanGate TASK_EXPIRED

No TestClient/create_app() usage found in this file at all — it exercises
the repository/application layer directly, not over HTTP. This does NOT fit
the Case 01 mechanism or any CI-isolation hypothesis so far. **Leading
hypothesis: independent, real application-layer bug** (e.g. a
clock/deadline calculation issue in the HumanGate expiry check), unrelated
to test isolation. Recommend investigating this one as a real functional
bug candidate, same protocol as the consent-withdrawal case, not as CI
infrastructure.

```
classification: UNRESOLVED (leading hypothesis: REAL_FUNCTIONAL_BUG, not CI-isolation-related)
root cause confidence: NONE YET (not investigated this pass)
```

## CROSS-CASE ROOT CAUSE: PARTIAL

Not one unified root cause. Case 01 is CONFIRMED as a TestClient lifecycle
fixture bug, independent of any other test. Case 02 is suspected to share
Case 01's mechanism but unconfirmed. Cases 03 and 04 show no evidence of
sharing Case 01's or each other's mechanism and need independent
investigation — explicitly NOT forcing a unified explanation across all
four, per the R0.5 directive.

## FIX RECOMMENDATION (not implemented this pass, pending architect review)

1. **Case 01 (and likely 02)**: fix the bare `TestClient(create_app())` call
   sites to use `with TestClient(create_app()) as client:` — a small, scoped
   test-file diff, not a CI/infra change. Add an architecture/static test
   forbidding the bare form to prevent regression.
2. **Case 03**: needs its own B-alone / A-then-B / B-then-A investigation —
   not yet done.
3. **Case 04**: needs independent functional-bug investigation (likely
   unrelated to CI isolation at all) — treat with the same rigor as the
   consent-withdrawal P0, not folded into the CI-isolation effort.
4. Do not change ENGINE_CACHE_SIZE. Do not implement the event-loop-keyed
   cache redesign proposed in the earlier (now partially retracted)
   diagnosis doc until Case 02 is independently confirmed to actually need
   it — Case 01's disproof means that fix might not be necessary at all for
   the cases we have direct evidence on.
