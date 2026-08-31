# ADR-0148: ProductPackage uses receipt-backed evidence admission snapshots

- Status: Accepted
- Date: 2026-09-01
- Owners: Product Intelligence / PDM Platform
- Related: ADR-0146, ADR-0147

## Context

Product discovery tools are useful for linking feedback to product work, and
PLM systems are useful for freezing revision-controlled decision objects. A
link or a `VERIFIED` string is nevertheless not evidence admission. Family
education also requires explicit claim and applicability limits: a parent
interview about usability cannot prove a growth effect, and one age or scenario
cannot be silently generalized to another.

ProductPackage v1.1 still froze `{evidence_ref, VERIFIED}` values produced by a
source resolver. It did not prove which Human Gate receipt, evidence revision,
claim scope or validity window supported the review submission.

## Decision

### Browser supplies locators; trusted source owns requirements

The browser supplies only an ordered set of opaque receipt locators. It cannot
define, shrink or replace the evidence policy. For every locator, the trusted
server-side ProductPackage source resolver must supply:

- one family-education claim type;
- exact required claim references;
- exact required applicability references.

The trusted requirement locator sequence must exactly equal the browser locator
sequence before admission begins. The browser also cannot supply admission
status, receipt outcome, policy result, verifier, tenant, evidence hash or Human
Gate lineage. Required refs use deterministic identifiers such as role, age
band, scenario, region and language refs. The server does not use fuzzy text or
an LLM to infer coverage.

### Receipt-backed admission replaces status strings

ProductPackage v1.2 removes `evidence_statuses` and freezes an immutable
`EvidenceAdmissionSnapshot` for every receipt. A snapshot contains the exact
receipt and evidence identities, hashes and versions; reviewed claim and
applicability scopes; methods, criteria, policy and purpose; Human Gate task,
proposal and decision lineage; verification/admission/expiry times; and the
server admission-policy version.

Only `ADMITTED` snapshots may be written into a submitted draft. `ADMITTED`
means the exact receipt may support the exact claim and applicability refs for
this ProductPackage review. It does not mean the full source is true, the
product is approved, or family growth impact is proven. There is no aggregate
score or family/child ranking.

### Deterministic fail-closed checks

The receipt-backed resolver requires:

- same tenant and exact receipt ID;
- current time within the receipt validity window;
- supported receipt policy and required integrity methods;
- no direct supersession marker while the proper impact ledger is absent;
- required claim and applicability refs are subsets of reviewed scopes;
- current Evidence is ACTIVE and exactly matches receipt ID, version, ref and
  platform-record hash;
- no duplicate receipt or duplicate underlying evidence revision.

The Package review expiry is capped at the earliest admitted receipt expiry.

### Final same-transaction revalidation

Initial resolution is not an authorization ticket. After exact idempotency
replay checks and before any draft, HumanTask or audit write, the submission
repository reloads every receipt and locks each mutable Evidence row in the
same SQL session. It reconstructs the admission snapshots and requires an
exact match using a newly sampled commit-time clock. Drift or expiry rolls back
the session and fails the whole transaction before writes.

Historical exact replay remains replay-first and does not re-evaluate current
evidence. A changed browser intent still conflicts.

## Versioning

New writes use ProductPackage schema `1.2` / version `1.2.0`. This is an
explicit hard cut in the non-production test schema. v1.1 has no committed
Alembic deployment, so no persisted production rows are silently upgraded.
If a deployed v1.1 lineage is later discovered, a separate compatibility
reader and migration decision are required before release.

## Delivery boundary

This iteration provides the domain snapshot, deterministic admission compiler,
request-scoped SQL reader, evidence row lock, final revalidation, HTTP
composition and SQLite tests. It is not production available until:

1. the linear Alembic chain creates both receipt and v1.2 package structures;
2. PostgreSQL lock, same-key race and evidence-drift races pass;
3. append-only receipt revocation/supersession and impact projection exist;
4. Evidence master data has typed source/evidence descriptors so claim-type
   minimum-source rules can be enforced;
5. Web readiness, registry entries and canonical app wiring are delivered.

Until then, the system must describe this as an independently testable
receipt-backed admission seam, not a mounted production capability.
