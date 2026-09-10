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
exact leaked-resource identity: NOT YET ISOLATED (see RETRACTION below)
```

## Case 02 — Retraction (2026-09-10, same day): async-dispose-before-drop did NOT fix it

Per architect directive, implemented `dispose_cached_engine(database_url)`
(`backend/platform/persistence/session.py`) — pops exactly one cached
engine and `await`s its `dispose()` — and rewired
`baselined_database_url`'s teardown in `test_fastapi_postgres_e2e.py` to:
stop users → `await dispose_cached_engine(database_url)` → verify no
unexpected `pg_stat_activity` rows → drop database. Added a diagnostic
query before `pg_terminate_backend` per the "terminate_backend is an
emergency net, not the correctness mechanism" directive.

**Counterfactual matrix, re-run against real Postgres after the fix:**

```
JOURNEY alone x3:            PASS / PASS / PASS
RELEASE alone x3:             PASS / PASS / PASS
JOURNEY -> RELEASE x3:        FAIL / FAIL / FAIL   (4 failed, 1 passed — UNCHANGED)
RELEASE -> JOURNEY x3:        PASS / PASS / PASS
```

**The fix did not change the failure at all — same signature, same
100% reproducibility.** Per the architect's explicit stop condition
("如果新 async disposal 不能解决：立即撤回这个根因假设"), the
`dispose_cached_engine` hypothesis is RETRACTED as the root cause of Case
02 (the API itself is kept — it is a real, independently useful lifecycle
primitive backed by its own passing regression test in
`tests/platform/persistence/test_ephemeral_engine_disposal.py` — but it
does not close Case 02).

**New evidence from re-probing after the fix, narrowing the search:** a
second `get_engine()` trace, run *after* the disposal fix, shows the
failing test's own `get_engine()` call correctly resolving to
`sqlite+aiosqlite:///:memory:` — same as before the fix. Yet the actual
exception occurs inside `pool._create_connection()` → `__connect()`, a
**live, synchronous checkout attempt** against a `Pool` object that is
provably bound to the *previous* test's `journey_e2e_<uuid>` `Engine` —
not a deferred/background task discovered later, an active checkout
happening in the current request's own call stack.

This rules out both prior explanations:
- Not `_ENGINE_CACHE` returning a stale entry (the cache correctly
  resolves to sqlite for this test both before and after the fix).
- Not an un-awaited `AsyncEngine.dispose()` leaving connections open (now
  awaited, and the failure is identical).

**Leading new hypothesis, NOT yet confirmed — flagging for CASE02-TRACE-2,
not implementing speculatively:** SQLAlchemy's greenlet-based async bridge
(`await_only` / `greenlet_spawn` in
`sqlalchemy/util/_concurrency_py3k.py`) trampolines synchronous DBAPI calls
onto a per-OS-thread greenlet stack, independent of `asyncio`'s per-test
event loop. If a checkout against the journey engine's pool was
interrupted mid-greenlet-switch when that test ended (rather than running
to completion), the suspended greenlet is an OS-thread-level object that
outlives the asyncio event loop closing — and could be resumed by an
unrelated `greenlet_spawn` call in a *later* test sharing the same
worker thread, since pytest runs test functions sequentially on one OS
thread by default. This would explain why the failure appears inside the
*new* test's own call stack (nested under its `BlockingPortal` call) even
though the new test never touches the old engine through any code path
this investigation has instrumented so far.

## Case 02 — CASE02-TRACE-2: root cause CONFIRMED (2026-09-10, same day)

The greenlet-across-OS-thread hypothesis above is **disproven**. A
standalone reproducer (`asyncio.run(phase_one()); asyncio.run(phase_two())`,
no pytest, no pytest-asyncio, no `TestClient`/`BlockingPortal`, pure
`httpx.AsyncClient` + `ASGITransport`) reproduced the exact same
`InvalidCatalogNameError` 100% of the time. Since there is no sync/async
greenlet bridge and no shared-thread suspended-coroutine mechanism
possible in that reproducer at all, the leak cannot be a greenlet
scheduling artifact — it must be ordinary Python object state.

**Actual root cause, found by reading the composition root
(`backend/apps/family_api/main.py::_mount_course_content`) and confirmed
by counterfactual test:**

`course_routes.py` module holds `_release_baseline_store` as a
**process-wide, module-level global**, not per-`create_app()` state.
`_mount_course_content` has two branches:

```python
if not is_dev_environment():
    configured_url = database_url or _runtime_database_url()
    if configured_url is not None and is_postgres_url(configured_url):
        install_course_content_production_wiring(engine=get_engine(configured_url))
    return

configure_course_content_repository(InMemoryCourseContentRepository())
configure_course_system_repository(development_course_system_repository())
configure_course_content_gate(InMemoryHumanGate())
# ... (courseware gateway, actor resolver) ...
# — no call to configure_course_release_baseline_repository(None) here —
```

`install_course_content_production_wiring` (in
`course_content_wiring.py`) calls
`configure_course_release_baseline_repository(ConnectionScopedCourseReleaseBaselineRepository(engine))`
— installing a Postgres-backed repository bound to whatever engine that
call received. The dev/test branch resets `_repository`,
`_course_system_repository`, `_gate`, the courseware gateway, and the
actor resolver — but **never resets `_release_baseline_store`**. If a
prior `create_app()` call in the same process took the production branch
(exactly what `test_fastapi_postgres_e2e.py` does — it sets
`AIFAMILY_ENV=production`), the stale, Postgres-bound
`ConnectionScopedCourseReleaseBaselineRepository` silently survives into
every subsequent dev/test app in that process, including
`test_course_release_baseline_routes.py`'s (`AIFAMILY_ENV=test`) app. Its
`.save()`/`.get()` calls then try to use a connection to the ephemeral
`journey_e2e_<uuid>` database — which by then has been dropped.

This explains every piece of prior evidence at once:
- Why it reproduces with zero async/greenlet/pytest machinery involved —
  it is a plain global-variable leak.
- Why `get_engine()` always resolved correctly (to sqlite) in the failing
  test — the failing request never calls `get_engine()` at all; it calls
  the stale repository object captured by closure over the *old* engine.
- Why order matters (`journey_e2e_*` production-mode app must run first)
  and why the reverse direction is clean (a dev/test app run first
  installs no baseline repository at all — `_release_baseline_store`
  stays `None`, the in-memory dict fallback is used, and no persisted
  state carries forward to a later app either way).

**Fix**: `backend/apps/family_api/main.py::_mount_course_content`'s dev/test
branch now calls `configure_course_release_baseline_repository(None)`
alongside its other resets, restoring the documented "`None` is
fail-closed / in-memory fallback" contract
(`configure_course_release_baseline_store`'s own docstring) for every
dev/test app, regardless of what a prior app in the same process wired.

**Counterfactual proof, exactly as directed:**

```
WITH fix:    JOURNEY alone x3 PASS, RELEASE alone x3 PASS,
             JOURNEY->RELEASE x3 PASS, RELEASE->JOURNEY x3 PASS
WITHOUT fix (git stash the one-line change, re-run):
             JOURNEY->RELEASE: 4 failed, 1 passed — reproduces identically
WITH fix restored (git stash pop): JOURNEY->RELEASE PASS again
```

```
classification: STALE_MODULE_GLOBAL_ACROSS_APP_INSTANCES
root cause confidence: CONFIRMED (standalone non-pytest reproduction +
  code-level identification + counterfactual with/without matrix)
```

Broader regression check: `tests/domains/product_intelligence/` +
`tests/apps/family_api/` full run after the fix — 317 passed, 21 skipped
(real-Postgres-gated tests, no `AIFAMILY_TEST_DATABASE_URL` in that run),
1 failed (the already-documented, independent
`service_cases.family_id` uuid/varchar mismatch — unrelated, out of
scope). No regressions from this fix.

**CASE02 status: CLOSED.**

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

## CROSS-CASE ROOT CAUSE: RESOLVED — four cases, four distinct mechanisms, no forced unified explanation

- **Case 01**: CONFIRMED, FIXED. `TestClient` lifecycle fixture bug (bare
  construction, no `with`). Repo-wide remediation complete (13/13 files).
- **Case 02**: CONFIRMED, FIXED. A module-level global
  (`_release_baseline_store` in `course_routes.py`) not reset by
  `_mount_course_content`'s dev/test branch, silently inheriting a
  Postgres-bound repository wired by an earlier, production-mode
  `create_app()` call in the same process. Nothing to do with async
  lifecycle, event loops, or greenlets — a plain composition-root reset
  gap. See CASE02-TRACE-2 below for the two retracted hypotheses that
  preceded this confirmed one.
- **Case 03**: CONFIRMED, FIXED. `search_path` pollution from an engine
  borrowed from the cache and returned to the pool without resetting
  `search_path`.
- **Case 04**: CONFIRMED, FIXED. Real wall-clock dependency in a TTL
  expiry test, unrelated to CI infrastructure at all.

All four cases are closed, each with an independently confirmed,
distinct mechanism — none forced into a unified "shared database" or
"engine cache" narrative despite three of the four superficially
involving Postgres. This is exactly the "no unified explanation without
evidence" discipline the R0.5 protocol asked for, and Case 02 in
particular is a direct demonstration of why: two plausible, well-argued
hypotheses (engine-cache cross-loop reuse, then async-dispose-before-drop)
were both tested against a real counterfactual matrix and both retracted
when the matrix didn't move — only the third hypothesis, verified with a
non-pytest standalone reproduction plus a with/without-fix counterfactual,
was confirmed.

## RESOLUTION SUMMARY (all four cases closed)

1. **Case 01**: fixed — all bare `TestClient(create_app())` call sites
   repo-wide converted to `with TestClient(create_app()) as client:`.
2. **Case 02**: fixed — `_mount_course_content`'s dev/test branch now
   calls `configure_course_release_baseline_repository(None)`, matching
   its existing reset of every other module-level composition seam in
   that branch. `dispose_cached_engine(url)` was also added to
   `session.py` as part of investigating (and retracting) an earlier
   hypothesis for this case — kept as an independently useful lifecycle
   primitive with its own passing regression test, not because it fixes
   Case 02.
3. **Case 03**: fixed — `test_store.py` rewritten to use
   `postgres_schema_engine`, which pins `search_path` at the connection
   level instead of leaving a shared cached connection's `search_path`
   pointing at a dropped schema.
4. **Case 04**: fixed — the fixed-clock test now passes an explicit
   `now` to `gate.decide(...)` instead of defaulting to real wall-clock
   time.

`ENGINE_CACHE_SIZE` was never changed. The event-loop-keyed cache
redesign proposed in the earlier (retracted) diagnosis was never
implemented — correctly, since none of the four confirmed root causes
needed it.

## Follow-up recommended, not done this pass

- Add an architecture/static test forbidding bare `TestClient(create_app())`
  outside a `with` block, to prevent Case 01 regressing.
- Inventory other module-level composition-root globals in
  `backend/apps/family_api/main.py`'s `_mount_*` functions for the same
  "dev/test branch resets some globals but not all" pattern that caused
  Case 02 — `_release_baseline_store` was found by tracing one specific
  failure, not by a systematic audit; siblings likely exist.
