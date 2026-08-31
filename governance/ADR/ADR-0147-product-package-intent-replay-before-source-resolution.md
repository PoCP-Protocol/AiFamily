# ADR-0147: Replay ProductPackage intent before mutable source resolution

- Status: Accepted
- Date: 2026-09-01
- Owners: Product Intelligence / PDM Platform
- Related: ADR-0145, ADR-0146

## Context

ProductPackage review submission resolves browser-safe design intent into
server-owned facts before it creates an immutable draft and Human Gate task.
Those facts include evidence state and will change as receipts expire, sources
drift, or a resolver becomes temporarily unavailable.

Resolving those sources before checking durable idempotency makes a successful
request unsafe to retry: the same browser request can fail later even though
its draft and review task already exist. It can also hide a changed browser
payload behind an equivalent resolver result.

## Decision

The HTTP boundary computes a canonical SHA-256 hash over every field in
`ProductPackageDesignIntent`, including the opaque source locator, evidence
locators and requested TTL. After authorization and before source resolution,
the repository looks up `(tenant_scope, actor_id, idempotency_key)`:

- no row: resolve current trusted sources and continue submission;
- same intent hash: return the frozen draft and HumanTask as an HTTP replay;
- different intent hash: fail with `PRODUCT_PACKAGE_INTENT_REPLAY_MISMATCH`.

The immutable ProductPackage draft contract is versioned to 1.1 and freezes
`intent_hash`, `resolved_request_hash` and `source_draft_locator`; its content
hash therefore covers them. Persistence stores the fields as lineage scalars
and verifies them against the draft payload on read.

The existing server-resolution request hash remains mandatory. Persistence
checks both hashes during normal and concurrent replay so that neither a
changed browser intent nor changed trusted resolution can be silently reused.

An unavailable resolver does not block an exact durable replay. It still fails
closed for a new idempotency key. Authorization always runs before replay, so a
historical result is not an authentication bypass.

## Consequences

- Network retries remain deterministic after receipt expiry or source drift.
- Changed intent is rejected before mutable source access.
- Readback and replay expose only the already frozen `SUBMITTED_FOR_REVIEW`
  result; they do not re-approve or adopt a product.
- Receipt validation can now be added as a composable source-resolution stage
  without breaking durable replay semantics.

## Delivery boundary

This is an independently tested HTTP and SQLite seam. It is not deployable
until the shared linear Alembic chain has a migration for the new columns and
real PostgreSQL same-key concurrency tests pass. The production receipt-backed
resolver, Web readiness workbench, revocation/impact ledger, registry entries
and canonical application wiring remain separate required work.
