---
id: PLATFORM-CI-ISOLATION-DIAGNOSIS-001
title: CI Test Isolation Root Cause Diagnosis (R0.5)
status: current
owner: chief-architect
updated: 2026-09-10
---

# CI Test Isolation Root Cause Diagnosis

## Verdict: H1 CONFIRMED (per FAMILY-AGI-R0.5 diagnostic protocol)

> `_ENGINE_CACHE` in `backend/platform/persistence/session.py` is a
> process-wide, URL-keyed cache of `AsyncEngine` objects. pytest-asyncio's
> `asyncio_mode="auto"` gives each test function its own, independent event
> loop by default. When two test functions share the same `DATABASE_URL`
> (e.g. the fixed CI-shared `aifamily_dev_ci`), the second test's call to
> `get_engine(url)` returns the FIRST test's cached engine object — whose
> underlying asyncpg connections are bound to the FIRST test's event loop,
> which pytest-asyncio has by then already closed. Any later attempt to use
> that connection (including SQLAlchemy's own connection-pool teardown
> trying to `terminate()` it) raises `RuntimeError: Event loop is closed`.

## Reproduction (minimal, no CI infrastructure needed)

```
AIFAMILY_TEST_DATABASE_URL=postgresql+asyncpg://aifamily:aifamily@127.0.0.1:55442/aifamily_test \
DATABASE_URL=postgresql+asyncpg://aifamily:aifamily@127.0.0.1:55442/aifamily_dev_ci \
uv run --python 3.12 pytest tests/domains/product_intelligence/test_course_release_baseline_routes.py -v
```

Result (verified 2026-09-10): **2 failed, 2 passed** — inside a SINGLE test
file, with NO other test file run before or after it, and NO `journey_e2e_*`
database involved at all. This rules out cross-file test-order pollution as
the primary mechanism; the file's own 4 test functions are enough to trigger
it, because each one independently calls `create_app()` → `get_engine()`
against the same fixed `DATABASE_URL`.

## Direct proof: engine identity tracing

Monkey-patching `get_engine` to print `id(engine)` and `len(_ENGINE_CACHE)`
on every call, across the same 4-test-function file, showed:

```
>>> get_engine(url='...aifamily_dev_ci') -> engine id=2141862962512, cache_size=1
>>> get_engine(url='...aifamily_dev_ci') -> engine id=2141862962512, cache_size=1
... (identical engine id for every call across all 4 test functions) ...
```

The SAME engine object survives across test-function boundaries — each of
which pytest-asyncio gives a fresh, independent event loop. This is the
mechanism, confirmed by direct evidence, not inference from stack traces
alone.

## Why the `journey_e2e_*` / `platform_audit_events` failures fit the same
## mechanism (not yet independently re-verified with engine-identity tracing,
## flagged as a follow-up, not asserted as proven)

The `journey_e2e_*`-does-not-exist failures observed in full-suite CI runs
are consistent with the same root cause: if an engine cached under a
`journey_e2e_<uuid>` URL survives (in `_ENGINE_CACHE`, capacity 8, LRU) past
the point where that ephemeral database is dropped and its owning test's
event loop is closed, a later cache hit for that same URL string would
return a dead engine bound to a closed loop and a dropped database. This is
the same defect category as the confirmed course-release case, but has not
yet been independently reproduced with engine-identity tracing the way the
course-release case was — listed here as the leading hypothesis for those
failures, not as an independently confirmed fact.

## What this is NOT

- NOT a `shared Postgres database` data-pollution problem per se (though
  data pollution on the fixed `aifamily_test`/`aifamily_dev_ci` databases
  may be a SEPARATE, additional issue worth checking independently — this
  diagnosis does not rule that out, it only confirms H1 as a real,
  independently-sufficient cause).
- NOT fixable by changing `ENGINE_CACHE_SIZE`. Cache size does not address
  the lifecycle mismatch — a cache of size 1 or size 1000 has the exact
  same defect if it caches an engine across event-loop boundaries.
- NOT the consent-withdrawal 403 bug (already independently diagnosed and
  fixed as a real, unrelated application-layer bug — see commit `7e3041b5`).

## Suggested fix direction (not implemented in this diagnosis pass)

`get_engine()` needs to be aware of which event loop it is being called
from, and must not return a cached engine created under a different (and
possibly now-closed) loop. Candidate approaches:

1. Key `_ENGINE_CACHE` by `(url, id(asyncio.get_running_loop()))` instead of
   just `url`, so a new event loop never receives a stale-loop engine —
   accepting that this reduces cache reuse across tests that legitimately
   share a loop (unlikely in the current function-scoped pytest-asyncio
   setup, so low cost).
2. Add an explicit `dispose_cached_engines()` async fixture-teardown seam
   that every Postgres-touching test must use, called before its event loop
   closes — matches the existing `clear_engine_cache()` pattern but fixes
   the "sync dispose doesn't await the async driver's close" gap the
   current implementation's own docstring already admits.
3. Move to one FastAPI `TestClient`/engine per test process boundary
   (separate CI jobs, as the R0.5 directive already proposes) as a
   structural mitigation — reduces the number of times two different event
   loops fight over the same cached engine, without fixing the underlying
   defect. Should be paired with (1) or (2), not a substitute for either.

This diagnosis stops here per the R0.5 scope — implementing the fix is the
next step, pending architect review of the three candidate directions above.
