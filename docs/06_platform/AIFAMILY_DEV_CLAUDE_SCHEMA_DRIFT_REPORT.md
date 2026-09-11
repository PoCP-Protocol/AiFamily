---
id: FAMILY-R0-DB-DRIFT-001A-001B
title: aifamily_dev_claude schema drift forensic and rehearsal report
type: evidence
status: draft
version: 1.0
owner: platform
created: 2026-09-11
updated: 2026-09-11
canonical: false
---

# R0 database drift evidence

NOT_CANONICAL — 本文是指定本地数据库的取证与恢复演练证据，不是全局系统能力或 R0 CLOSED 声明。

## Scope and immutable baseline

- TASK_ID: FAMILY-R0-DB-DRIFT-001A / 001B
- SOURCE_DB_MUTATED: NO
- Source: `aifamily_dev_claude`, local PostgreSQL 16.13, port 55442.
- Repository/test base: `7e3041b53b98f7fd847810ad2d87d590af753080`.
- Repository migration head: `0079_platform_notification_control_plane`.
- Source Alembic revision before and after: `0069_ai_run_ledger`.
- Highest contiguous structural semantic revision: **`0066_fgcn_provider_qualification_fields`**.
- Owned worktree: `D:/AiFamily-r0-db-drift-forensics`; branch: `codex/r0-db-drift-forensics`.
- Allowed changes: this report and the one-off script in `tools/db_recovery/`.

All source catalog/data snapshots ran in read-only, repeatable-read transactions with a 30-second statement timeout and 2-second lock timeout. Source export used read-only `pg_dump`. No source upgrade, downgrade, stamp, DDL, truncation or session termination occurred. Application and pytest writes were directed to separate rehearsal copies.

## Physical classification

The earlier inference that a reported 0069 implied a complete 0069 physical prefix is disproved. Four 0067 tables and the 0068 table are absent. The complete catalog matches a hybrid of 0066 plus 0069 and 0074–0076 structural effects; the two 0073 seed records also match. This establishes the structural prefix, not universal business-data correctness.

- 0067 — NOT_APPLIED: `family_service_actions`, `family_service_family_feedback`, `family_service_outbox_events`, `family_service_quality_decisions` absent (109 expected catalog facts).
- 0068 — NOT_APPLIED: `assessment_reviewed_understanding_signals` absent (47 facts).
- 0069 — APPLIED_TRACKED: its own 22 catalog facts match; this does not repair its missing predecessors.
- 0070 — NOT_APPLIED: four service-case reference columns remain non-null UUID with four legacy foreign keys; head requires non-null varchar(128) and removal of those foreign keys (12 changed facts).
- 0071 — NOT_APPLIED: identity receipt table and associated column/index effects absent (11 facts).
- 0072 — NOT_APPLIED: parent-note column absent; old two-value check constraint remains (3 facts).
- 0073 — APPLIED_UNTRACKED: FAMILY_SUPPORT_NEEDS versions 3 and 4 match title, purpose, status, admission, evidence level, schema, JSON items and boundary. Effective timestamps were checked for presence, not equality with a newly seeded reference.
- 0074 — APPLIED_UNTRACKED: complete `course_system` signature, including columns, primary key, check and index, matches (11 facts).
- 0075 — APPLIED_UNTRACKED: nullable varchar(256) `course_system_version_ref` matches (1 fact).
- 0076 — APPLIED_UNTRACKED: complete `course_release_baseline` signature matches (26 facts).
- 0077 — NOT_APPLIED (30 facts).
- 0078 — NOT_APPLIED (20 facts).
- 0079 — NOT_APPLIED (36 facts).

PARTIALLY_APPLIED / DIVERGENT / UNKNOWN: none within the inspected catalog and explicit seed effects. The migration bookkeeping is noncontiguous. No execution log proves who or which process produced this state; manual execution, metadata creation and revision stamping remain hypotheses, not drift-origin findings.

## Clone and head comparison

- REHEARSAL_DB: `aifamily_dev_claude_rehearsal_20260911001924`.
- HEAD_REFERENCE_DB: `aifamily_head_reference_20260911001924`, created empty and migrated using repository migrations.
- Unrepaired test copy: `aifamily_dev_claude_rehearsal_20260911002846`.
- Repaired test copy: `aifamily_dev_claude_rehearsal_20260911002847`.

The source had 229 tables, 3197 columns, 1138 constraints and 614 indexes. The fresh head has 239 tables, 3372 columns, 1177 constraints and 640 indexes. Both have 60 enums, 13 application triggers, 7 views, 45 functions, 2 sequences and 2 extensions.

The raw source-to-head delta contains 10 added relations, 179 added/4 replaced column records, 44 added/5 replaced constraint records and 26 added indexes. Other inspected catalog categories match.

`pg_dump`/`pg_restore` rewrites 196 CHECK expressions and 2 partial-index predicates from literal varchar-array-to-text casts to equivalent per-element casts. Raw differences are retained in local evidence. Comparison normalizes **only unbounded varchar literal casts to text**, preserving labels and order. It does not ignore arbitrary SQL, bounded varchar, functions, constraint names or types. After this normalization the restored clone equals the source, and the repaired clone equals fresh head: **SCHEMA_DIFF = 0**.

Inspected fields include column types/nullability/defaults/identity/generated/collation; constraint definitions, validation and deferrability; index definitions/readiness/validity/uniqueness; enum labels; triggers and enabled state; views/functions; sequence parameters; RLS/policies; extensions and schema names. This is not a comparison of database roles, grants, physical storage or all server settings.

## Reconciliation and safeguards

The one-off script reuses existing migration `upgrade()` functions in this order: **0067, 0068, 0070, 0071, 0072, 0077, 0078, 0079**. Already-applied 0073–0076 are retained. No historical migration file was changed.

Each step uses a transaction, advisory lock, frozen migration-file hash, pre/post full catalog hash and original-row projection hash. Unknown schema, changed original data, unexpected bookkeeping or a failed postcondition stops processing; the current transaction rolls back. The script supports only the nine frozen physical stages of this incident. It is not a general repair service.

The target URL must use PostgreSQL on 127.0.0.1:55442 and a timestamped `aifamily_dev_claude_rehearsal_` database name. Passing the source URL was tested and rejected **before connection**. The script contains no database creation or stamp action. The read-only baseline snapshot is a required local input; it is intentionally not published with database dumps.

All eight steps completed on the rehearsal. Repeating `--apply` at the final stage executed zero migrations. Only after schema equality, original-data checks and migration tests passed, an explicit `alembic stamp head` was performed against the rehearsal database. A new process then read revision `0079_platform_notification_control_plane` and again performed zero repair operations.

Original business-data projection SHA-256, excluding Alembic bookkeeping:
`75258e7f61971b60dc97cd6a6c653a0858524d518a551bcb6f349589dcd73c4f`.

Normalized repaired/reference schema SHA-256:
`2437f8af0545d4b22247a472155e08bb40db30c52da11328a3a4cda145b0c3f4`.

## Validation evidence

- Specified BLOCKER-001 test `test_self_help_failure_escalates_to_real_teacher_through_fgcn_human_gate`: unrepaired copy **1 failed**, first error missing `identity_receipts`; repaired copy **1 passed**. The unrepaired run does not independently reproduce the later service-case UUID failure because it stops earlier.
- `tests/database/test_alembic_baseline_applies.py` plus course-system PostgreSQL integration: **7 passed, 5 skipped**. Skips explicitly concern tests for revisions already registered in this checkout (0010, 0012–0015); they are not missing-database skips. Fresh baseline and repeatable downgrade/upgrade tests ran.
- Identity PostgreSQL repository and FGCN durable assignment suites: **5 passed**.
- `tests/architecture`: **138 passed, 1 skipped** (no vector storage exists).
- `uv run ruff check .`: **PASS**.
- Initial test invocation used an unavailable psycopg driver and failed collection. Corrected invocations used the installed asyncpg driver; only those results are reported above.
- Application composition and HTTP behavior were exercised by the specified TestClient end-to-end test. A standalone deployed-server/browser acceptance run was not performed.

Source before/after catalogs, all 229 table row-count/content digests and Alembic revision are identical. Source has 97 rows including one bookkeeping row. The repaired rehearsal preserved all original row projections before stamp; after stamp the original 96 business rows still match. Both sequence value/called states match. All 1177 repaired constraints are validated. These checks establish preservation of this small source dataset, not broad production-data coverage.

Local evidence is retained at `D:/AiFamily-r0-db-drift-evidence-20260911`: catalog snapshots, classification, raw clone delta, per-stage receipts, test logs, final verification and post-stamp inspection. The private dump and detailed snapshots are not committed. The recovery command is `uv run python tools/db_recovery/reconcile_aifamily_dev_claude_20260911.py --baseline-snapshot <source_before.json> [--apply]`, with the separately approved rehearsal URL in `AIFAMILY_REHEARSAL_DATABASE_URL`.

## Stop and next recommendation

The rehearsal succeeded; **the source remains unrepaired**. R0 is not CLOSED: full-suite/current main CI closure and the separately approved S4 fixture fix still require their own exact-ref evidence. PR #27 remains Draft; no R2.1 implementation or main merge is included here.

Future R2 work follows the user's Convergence First instruction: freeze target owner, switch real callers and production wiring, remove duplicate ownership and add guards. AgentRun, IntelligenceRun and GatewayAttempt remain distinct. R2 work and the roadmap/ADR changes belong to a separate change after the R0 gate; this database report does not claim those changes are implemented.
