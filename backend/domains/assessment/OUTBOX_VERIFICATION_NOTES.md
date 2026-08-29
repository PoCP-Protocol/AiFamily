# Transactional Outbox Verification — Assessment Domain

Task: FAMILY-AI-PYTHON-ONLY-VERTICAL-P0-001 (Batch 1), Migration Plan §9
"Must complete" item — Transactional Outbox.

## What was verified

The Assessment domain's Python port (`domains/assessment/`) claims to port
NestJS's `AssessmentService.auditAndEmit` / `GrowthHypothesisService.decide`
pattern: writing a business-state change, an `audit_logs` row, and an
`outbox_events` row inside **one** database transaction, so a caller
observing the system from outside always sees either all three or none —
never a business-state change without its corresponding event.

This task did not trust "the code looks like it's on the same connection" —
it ran real assertions against a real PostgreSQL 16 instance (Docker
container `family-py-outbox-verify`, port 15438, all 47
`database/migrations/*.sql` files applied in filename order, disposed after
the run) and inspected durable state from a **second, independent**
connection after the command under test finished (or after a simulated
mid-command failure), which is the only way to distinguish "same connection,
same transaction" from "same connection, but the transaction boundary
doesn't actually cover this step."

New test file:
`domains/assessment/tests/test_transactional_outbox_invariant.py`
(3 tests, all pass against real Postgres):

1. `test_start_save_submit_each_write_matching_outbox_and_audit_rows` —
   happy path. Runs `start` → `save_response` → `submit`, commits, then
   reads `outbox_events` and `audit_logs` from a **fresh** connection.
   Confirms all three events (`AssessmentSessionStarted`,
   `AssessmentResponseSaved`, `AssessmentSessionSubmitted`) and all three
   audit rows exist, `result='SUCCESS'`, and the outbox payload content
   (`status`, `evidence_id`, `boundary`) matches the receipt returned to the
   caller. The test cleans up its own committed rows afterward.

2. `test_failure_inside_write_audit_and_outbox_rolls_back_business_write_too`
   — the actual invariant test. Monkeypatches
   `SqlAlchemyAssessmentRepository.write_audit_and_outbox` so it performs a
   real `audit_logs` insert on the live connection, then raises before the
   `outbox_events` insert can run (simulating "half the outbox pair already
   happened"). Calls `commands.start(...)`, catches the exception, rolls
   back the connection (mirroring what `transactional_connection` in
   `apps/family_api/db.py` does on any exception), then reads from a
   **separate** connection: zero rows in `family_assessment_sessions`,
   `audit_logs`, and `outbox_events` for that family. The
   `family_assessment_sessions` insert happened *earlier in the same command
   call*, before the injected failure — its absence is what proves the
   business write and the outbox write share one atomic unit, not just "ran
   on the same connection."

3. `test_failure_inside_write_audit_and_outbox_after_outbox_insert_still_rolls_back`
   — mirror case. Lets the **real** `write_audit_and_outbox` run to
   completion (so the `outbox_events` row genuinely exists in the open
   transaction), then raises immediately after, simulating a crash right
   after the outbox insert. After rollback, both the business write and the
   outbox row are gone. This rules out "the outbox row escapes independently
   of the business write" as well as the reverse.

### Proving the tests have teeth (not tautologies)

Before finalizing, test 3 was temporarily sabotaged (locally, not committed)
by replacing `await connection.rollback()` with `await connection.commit()`
— i.e. simulating a transaction boundary that does NOT roll back on
exception. The sabotaged test correctly **failed** (`assert existing_sessions
== 0` → `1 == 0`), confirming the test can actually detect a broken
atomicity guarantee and is not silently passing regardless of behavior. The
sabotage was reverted immediately after and the leaked test row was manually
truncated from the verification database.

(An equivalent sabotage of test 2, by making the connection's rollback a
no-op, was attempted but SQLAlchemy's `AsyncConnection.rollback`/`.execute`
are read-only attributes and cannot be monkeypatched directly — hence the
sabotage was performed on the *outer* `connection.rollback()` call site in
test 3 instead, which achieves the same falsification purpose.)

## Conclusion

**The Transactional Outbox invariant holds for the Assessment domain's
Python port, as currently wired.**

- `apps/family_api/db.py::transactional_connection()` opens exactly one
  connection and one transaction (`async with engine.connect() as conn:
  async with conn.begin(): yield conn`) per FastAPI request, and commits on
  success / rolls back on **any** exception — this boundary is what the
  command handlers run inside.
- `SqlAlchemyAssessmentRepository` never opens its own connection or
  transaction; every method (`insert_session`, `upsert_response`,
  `mark_session_submitted`, `persist_operation`, `write_audit_and_outbox`,
  etc.) executes against the single `AsyncConnection` it was constructed
  with in `apps/family_api/dependencies.py::get_repository`.
- `AssessmentCommandHandler.start` / `.save_response` / `.submit` (and
  `GrowthHypothesisCommandHandler.decide`) call all of these methods
  sequentially on that one repository instance without ever committing or
  opening a nested transaction — so the whole command body, including the
  `write_audit_and_outbox` call, is one atomic unit exactly as it is in the
  NestJS original (`this.repository.withTransaction(async (client) => {
  ...await this.auditAndEmit(client, ...) })`).
- The real-Postgres test above forced a failure at the point that matters
  most (the outbox-write step) and confirmed nothing durable survives —
  not just "the code path looks right."

No dual-write gap, no partial-commit path, and no separate
transaction/connection for the outbox write were found in the Assessment
domain's Python command handlers.

## Secondary finding (fixed, in scope)

`test_sqlalchemy_repository_integration.py::_seed_family` (the pre-existing
integration test fixture, not code written for this task) did not insert a
`family_memberships` row for the guardian actor. Since
`assertFamilyManagePermission` (ported in
`sqlalchemy_repository.py::_assert_family_manage_permission`) requires
either a legacy `CreateFamily` audit row OR an ACTIVE
`OWNER_GUARDIAN`/`GUARDIAN` `family_memberships` row, every command call in
that test file failed closed with `actor_has_family_manage_permission` the
first time it was actually run against a real Postgres instance — meaning
this "real Postgres integration test" had apparently never been executed
successfully before. Fixed by adding the missing `family_memberships` insert
to the shared `_seed_family` helper (one INSERT, no production code
touched, no existing assertions changed). All 4 tests in that file now pass
against real Postgres. This fix is included in this task's commit because it
was required to prove the new outbox tests' shared seeding helper works at
all, and it does not change any previously-passing behavior (the file had
never passed against a real database before).

## Out-of-scope finding (not fixed, reported only)

`domains/assessment/tests/test_ai_run_ledger.py` and
`test_ai_run_ledger_integration.py` are untracked files present in this
worktree that were **not** created by this task (likely a concurrent task's
WIP). Running `test_ai_run_ledger_integration.py` against the same verified
Postgres instance fails with `asyncpg.exceptions.UndefinedTableError:
relation "ai_run_ledger" does not exist` — the `ai_run_ledger` table is not
created by any of the 47 migration files verified here. This is unrelated to
the Transactional Outbox invariant and was left untouched, per this task's
scope (do not touch other tasks' untracked WIP files).

## Verification environment

- `postgres:16-alpine` in Docker, container `family-py-outbox-verify`,
  `-p 15438:5432`, database `family_pyverify` — stopped and removed after
  this task's test runs completed (confirm with `docker ps -a | grep
  family-py-outbox-verify` — should show nothing).
- All 47 files in `database/migrations/` applied via `psql` in `ls | sort`
  order; all applied cleanly with no errors.
- Tests run with `PY_ASSESSMENT_TEST_DATABASE_URL=postgresql+asyncpg://family:family@localhost:15438/family_pyverify`.

## Test run summary

- `pytest domains/assessment/tests --ignore=...integration.py
  --ignore=...outbox_invariant.py` (no DB, excludes the two real-Postgres
  integration files plus the unrelated `ai_run_ledger` files being left
  alone): 56 passed (49 pre-existing Assessment-domain tests unaffected +
  7 tests belonging to the unrelated concurrent `ai_run_ledger` unit-test
  file that happens to also be collected — not part of this task).
- `pytest domains/assessment/tests/test_sqlalchemy_repository_integration.py
  domains/assessment/tests/test_transactional_outbox_invariant.py` (real
  Postgres): **7 passed** (4 pre-existing + 3 new outbox-invariant tests).
