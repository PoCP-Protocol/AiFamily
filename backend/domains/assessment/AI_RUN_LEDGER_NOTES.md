# AI Run Ledger — design notes

Implements the "AI Run Ledger" item from
`architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` §9 (Batch 1
"Must complete"), recording the "AI Run" step of §6's runtime call chain:

```
Python Business Domain -> Consent & Purpose -> Immutable Context Snapshot
-> Python AI Runtime -> Skill -> Model Provider -> Schema/Evidence/Safety/Eval
-> AI Run -> Domain Draft -> family/human confirmation -> Domain Command
```

## What was missing

Before this change, `ClaudeInterpretationAdapter.interpret()` and
`DeterministicInterpretationAdapter.interpret()` returned a draft (or
raised) with **zero durable trace** that the call happened: no record of
which generator ran, which model, how long it took, token usage, or
whether it failed boundary validation vs. a provider error.

## Design

- `domain/ai_run.py` — `AiRunRecord` (pydantic), one record per
  `interpret()` call. Fields: `run_id`, `assessment_session_id`,
  `service_depth`, `generator` (`deterministic`|`gateway`), `model_name`,
  `started_at`/`completed_at`, `input_tokens`/`output_tokens`, `outcome`
  (`success`|`boundary_violation`|`provider_error`), `error_detail`.
- `application/ports.py` — `AiRunLedgerPort.record(run) -> None`.
- `infrastructure/ai_run_ledger.py` — `SqlAlchemyAiRunLedger`, real
  implementation writing to the new `ai_run_ledger` table
  (`database/migrations/0045_ai_run_ledger.sql`).
- `infrastructure/fake_ai_run_ledger.py` — `FakeAiRunLedger`, in-memory,
  used by unit tests.

### Style reference, not a literal port

The NestJS side has **no** Assessment-domain equivalent of an AI Run
Ledger. The closest existing pattern researched for this task is the
Principal module's provider-attempt ledger:
`database/migrations/0014_principal_model_attempts.sql`
(`principal_model_attempts` table) plus `principal.repository.ts`'s
`begin()`/`finish()` methods — a STARTED row written before the external
call, updated to SUCCESS/FAILURE with latency/token/model_name after.

`AiRunRecord`/`ai_run_ledger` borrows that general shape (status-like
`outcome`, `model_name`, token counters, `started_at`/`finished_at`) but
diverges deliberately:

1. **One row per call, not a run/attempt two-table split.** Principal's
   schema separates a logical run (`principal_model_runs`) from N
   provider attempts (`principal_model_attempts`, one row per
   failover/retry). This domain's `AssessmentInterpretationPort` has
   exactly one generator per call today (deterministic fallback OR live
   Claude — no failover), so a single-record shape is the simplest
   design that is still correct. If failover across providers is added
   to this domain's AI Runtime later, splitting into a run/attempt pair
   the way Principal does is the natural next step — not done
   preemptively here, since there is nothing to failover between yet.
2. **`outcome` includes `boundary_violation`,** which Principal's ledger
   has no equivalent for. Principal's `failure_kind` covers
   transport/provider failures only; this domain's
   `assert_interpretation_boundary` is a fail-closed *content* check
   with no Principal-side analog (Principal doesn't validate model
   output against a construct-ref whitelist the way this domain does),
   so the ledger needed a distinct outcome value to distinguish "the
   model call succeeded but its output failed our safety boundary" from
   "the model call itself failed."
3. **No STARTED-then-updated two-phase write.** Principal pre-writes a
   STARTED row before the external call so a crash mid-call still leaves
   a trace. This domain's calls are not long-running/streamed, and
   `record()` is called exactly once at the end of `interpret()`
   (success or failure) — if that gap (crash between call start and
   ledger write) matters later, add `record_started`/`record_completed`
   methods to `AiRunLedgerPort` rather than overloading the current
   single-record shape.
4. **No raw model input/output stored**, consistent with
   `principal_model_attempts`'s own posture — only call metadata.

## Coverage

Every `interpret()` exit path writes exactly one record before returning
or raising:

- `ClaudeInterpretationAdapter`: provider transport exception ->
  `provider_error` (re-raises the original exception unchanged); missing
  text block / refusal -> `provider_error`; boundary validation failure
  -> `boundary_violation`; clean success -> `success` (with token usage).
- `DeterministicInterpretationAdapter`: always `success`, `generator="deterministic"`,
  `model_name=None` — the point is precisely to leave a trace that this
  session's draft came from the rule-based fallback, not a live model.

Both adapters take the ledger as an **optional, defaulted** constructor
argument (`ai_run_ledger: AiRunLedgerPort | None = None`) so existing call
sites (unit tests, any code constructing these adapters directly) keep
working unchanged. `apps/family_api/dependencies.py` wires the real
`SqlAlchemyAiRunLedger` per-request.

## Fail-open for ledger writes, by deliberate choice — not fail-closed

`SqlAlchemyAiRunLedger.record()` catches and logs any write failure
rather than raising. Rationale: a ledger write is a diagnostic/audit
side-channel on top of an AI Runtime call whose result (draft or domain
error) has *already been computed*. Letting a transient ledger DB error
turn an otherwise-successful interpretation into a user-facing failure —
or replace/mask a genuine boundary-violation error already being raised —
would make the audit mechanism itself a new failure mode for the feature
it's meant to observe. This is a narrower exception to this project's
general fail-closed posture: the AI *content* boundary checks
(`assert_interpretation_boundary`, `is_live_external_ai_authorized`)
remain strictly fail-closed and are completely unaffected by ledger write
outcomes — only the ledger's own write path is fail-open. If the project
owner later decides audit-write failures for AI Runtime calls should
block the response (fail-closed), that's a policy decision for a human
to make explicitly, not something this implementation defaulted to
silently.

## Verification performed

- Unit tests: `tests/test_ai_run_ledger.py` (7 cases) — covers success,
  boundary violation, provider transport exception, refusal/no-text-block,
  and the deterministic fallback's always-success trace, for both
  adapters, plus a backward-compatibility check that omitting the ledger
  still works.
- Real-database integration test: `tests/test_ai_run_ledger_integration.py`
  (2 cases, gated on `PY_ASSESSMENT_TEST_DATABASE_URL` like the existing
  `test_sqlalchemy_repository_integration.py`). Verified against a
  disposable `postgres:16-alpine` container (migrations 0001-0045 applied
  in order) that `SqlAlchemyAiRunLedger.record()` actually inserts a
  readable row into `ai_run_ledger`, for both a `success` and a
  `boundary_violation` outcome. Container was removed after verification;
  this test is skipped in normal CI/local runs unless that env var is set.
- Full existing suite (`pytest domains/assessment/tests --ignore=...`)
  re-run after all changes: unaffected, all previously-passing tests
  still pass.
