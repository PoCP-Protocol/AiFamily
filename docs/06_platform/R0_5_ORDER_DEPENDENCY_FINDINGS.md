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

**RE-VERIFIED after Case 01's full-repo fix landed (all 13 files converted
to `with TestClient(create_app()) as client:`). The "same root cause as
Case 01" hypothesis is DISPROVEN — Case 02 is an independent, distinct
mechanism.**

B-alone (`tests/domains/journey/test_fastapi_postgres_e2e.py`, the only
file using the `journey_e2e_*` ephemeral-database pattern), run 3
consecutive times against real Postgres (`aifamily_test` on
`127.0.0.1:55442`): **PASS / PASS / PASS.**

A→B (`test_assessment_routes.py` + `test_course_release_baseline_routes.py`
+ `test_fastapi_postgres_e2e.py`, in that order), run twice: **14 passed /
14 passed**, no failure.

**B→A (`test_fastapi_postgres_e2e.py` run FIRST, then
`test_course_release_baseline_routes.py`), run twice: 4 failed / 4 failed,
100% reproducible.** All 4 failures in the course-release file, every one
with the same signature:

```
asyncpg.exceptions.InvalidCatalogNameError: database "journey_e2e_<uuid>" does not exist
```

**Direct instrumentation disproves the obvious "DATABASE_URL env leaked"
explanation.** A temporary probe print in `get_engine()`
(`backend/platform/persistence/session.py`) showed the course-release
test's own `get_engine()` call correctly resolving
`sqlite+aiosqlite:///:memory:` — `DATABASE_URL` had been correctly reverted
by `monkeypatch`'s teardown; the failing test's *own* code path never
touches the dead `journey_e2e_*` engine. Yet the traceback shows the
`InvalidCatalogNameError` occurring **inside the same request's own call
stack** — nested under `anyio.from_thread.BlockingPortal` → `await
self.app(...)` → SQLAlchemy's `Engine(postgresql+asyncpg://.../journey_e2e_<uuid>)`
— i.e. a connection object bound to the *previous* test's already-dropped
database somehow fires **during** the current, unrelated test's request
handling, on an `Engine` object the current test never referenced.

This is consistent with a leaked async/greenlet-bridged resource (a
pending asyncpg connection or SQLAlchemy greenlet task tied to the old,
disposed `AsyncEngine`) that outlives its owning test's event loop and its
owning fixture's synchronous `clear_engine_cache()` call — which, per its
own docstring (`_dispose_engine_pool`), "does not await each driver-level
close." The leaked resource's exception then surfaces on whatever
subsequent test happens to be sharing the same worker thread/greenlet stack
when it is finally scheduled, misattributing the failure to an unrelated
test.

This is **not** the Case 01 mechanism (bare `TestClient` without `with`) —
`test_fastapi_postgres_e2e.py` (the predecessor, "A" in B→A) does not use
`TestClient` at all; it uses `httpx.AsyncClient` with `ASGITransport`
directly. Case 01's fix (already fully applied repo-wide) does not touch
this file and does not resolve this failure.

```
classification: ASYNC_RESOURCE_LIFECYCLE_LEAK (cross-event-loop, distinct from Case 01)
root cause confidence: CONFIRMED order-dependency (B alone PASS x3, A->B PASS x2, B->A FAIL x2 100%)
exact leaked-resource identity: NOT YET ISOLATED (evidence points to `baselined_database_url`
  fixture's `clear_engine_cache()` sync dispose not awaiting the underlying asyncpg
  connection's close, but the precise object holding the reference has not been
  traced with add'l instrumentation — would need per-object refcount/gc tracing,
  a deeper investigation than this pass's time budget)
```

**Recommendation, not implemented this pass (per the no-speculative-fix
rule) — pending architect review, same three candidate directions already
on record in `CI_TEST_ISOLATION_DIAGNOSIS.md`:**

1. Make `baselined_database_url`'s teardown `await`-dispose the engine
   properly (`await engine.dispose()` instead of relying on
   `clear_engine_cache()`'s sync-only dispose) before dropping the
   ephemeral database — directly targets the specific gap this fixture's
   own leak pattern exercises.
2. Key `_ENGINE_CACHE` by `(url, event_loop_id)` so a stale engine can never
   be reused across a closed loop — broader, addresses the general class,
   not just this fixture.
3. Structural: give Postgres-ephemeral-database e2e tests
   (`journey_e2e_*`-style) their own CI job/process boundary, separate from
   the fixed-shared-database test files — reduces exposure without fixing
   the underlying leak.

Recommend (1) as the narrowest, lowest-risk fix specific to this
fixture, with (2) as the durable platform-level fix for the general class —
both require architect sign-off before implementation, per this branch's
scope discipline.

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

## CROSS-CASE ROOT CAUSE: PARTIAL (updated after Case 01 fix + Case 02 re-verification)

Confirmed: four cases, at least three distinct mechanisms, no forced unified
explanation.

- **Case 01**: CONFIRMED, FIXED. `TestClient` lifecycle fixture bug (bare
  construction, no `with`). Repo-wide remediation complete (13/13 files).
- **Case 02**: CONFIRMED as order-dependent (B->A fails 100%, A->B and B
  alone are clean) but a **different** mechanism from Case 01 — an async
  resource (likely an under-disposed `AsyncEngine`/connection from the
  `journey_e2e_*` ephemeral-database fixture) leaking across a test-loop
  boundary and surfacing on an unrelated later test. NOT fixed this pass;
  documented for architect review.
- **Case 03**: CONFIRMED, FIXED. `search_path` pollution from an engine
  borrowed from the cache and returned to the pool without resetting
  `search_path`.
- **Case 04**: CONFIRMED, FIXED. Real wall-clock dependency in a TTL
  expiry test, unrelated to CI infrastructure at all.

Three of four cases are closed. Case 02 is the one remaining open item,
correctly NOT folded into Case 01's fix despite superficial similarity
(both involve Postgres and both were seen in the same CI runs) — this is
exactly the "no unified explanation without evidence" discipline the R0.5
protocol asked for.

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
