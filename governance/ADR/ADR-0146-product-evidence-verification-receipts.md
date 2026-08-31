# ADR-0146: Product evidence verification is an immutable human receipt

- Status: Accepted
- Date: 2026-09-01
- Owners: Product Intelligence / AI Platform
- Related: ADR-0140, ADR-0145

## Context

ProductPackage admission needs evidence that is traceable, current and reviewed.
The legacy competitor source-card request accepted an `evidence_status` string
from the browser, so `VERIFIED` could not be treated as an authoritative fact.
An AI confidence value, a reachable URL and a source record are also not human
verification decisions.

The platform therefore needs to separate the source, the review proposal, the
human decision, the accepted action and the resulting receipt. This follows the
same IPD/PDM rule used for product adoption: evidence may inform a decision but
cannot advance itself.

## Decision

### Source records never self-verify

Product-research source cards remain observations with status `UNKNOWN` at the
HTTP boundary. A browser cannot write `VERIFIED`, a verifier identity, a policy
result or a validity window through this boundary. Import and internal
persistence paths require equivalent fail-closed enforcement before production.

### Only an accepted Named Action creates a receipt

The only materialization action is `VERIFY_PRODUCT_EVIDENCE`. It must come from
a persisted HumanTask with an `ACCEPT` decision by an `OPERATOR`. The owning
domain reloads that task and compares the complete proposal, decision and
NamedActionRequest lineage before it writes anything.

The reviewer needs the explicit
`product_intelligence.evidence.verify` permission. The evidence creator cannot
verify the same version (maker-checker/four-eyes rule). The accepted decision
must include a reason.

### Receipt semantics

`EvidenceVerificationReceipt` is immutable and freezes:

- trusted tenant, evidence identity, version, platform-record snapshot hash and source ref;
- the exact claim and applicability scopes, methods and policy criteria;
- explicit integrity `PASS`, relevance `RELEVANT` and outcome `VERIFIED` that
  were present in the reviewed action arguments;
- task, proposal, decision, request and verifier lineage;
- decision time, server record time, validity window and canonical hashes.

`VERIFIED` applies only to the frozen claim scope. It does not mean that the
whole source is true, that a ProductPackage is approved or that a family growth
outcome is proven. Confidence never substitutes for verification.

Expiry is derived at read time from `valid_until`; historical outcome and
decision fields are not rewritten. A later revocation or supersession must be a
separate append-only record. It must not delete or silently edit the receipt.

### Safety and privacy

The receipt is designed to store a stable source reference and platform-record
digest rather than raw family or child content; callers remain responsible for
data classification and redaction until a source-admission control is added.
The digest does not prove the bytes behind an external reference. No family
score, family ranking, competitor ranking or automated approval is introduced.
Privacy withdrawal will require a controlled source redaction/tombstone plus a
separate receipt-impact event.

## Delivery boundary

This iteration provides the immutable domain contract, accepted NamedAction
materializer, SQL repository, audit and SQLite integration proof. It also makes
the legacy competitor source-card HTTP request accept only `UNKNOWN`.

It is not production available until all of these are complete:

1. an explicit verification-proposal and operator-review HTTP/Web flow;
2. append-only revocation/supersession and impacted-decision records;
3. the shared Alembic chain is committed and its next single linear migration
   creates the receipt table;
4. registry owners record the capability without overwriting concurrent WIP;
5. real PostgreSQL migration, concurrency and worker-claim tests pass;
6. Demand, MarketInsight, Component/Skill/Metric/Guardrail catalogs and an
   operations-scoped ModelDraft index provide authoritative read ports;
7. `ProductPackageSourceResolver` consumes active exact receipts and rechecks
   them in the same transaction as package submission.
8. the shared accepted-action runtime dependency is committed and the receipt
   adapter is registered without relying on workspace-only files.

Until then this is an independently testable evidence-governance seam, not a
mounted Web or production capability.

## Consequences

- Legacy client-declared `VERIFIED` values can no longer enter through the
  competitor source-card request.
- Accepted review, materialization and product admission remain distinct.
- Source version drift, wrong tenant, missing permission, self-review, expired
  policy and persisted lineage tampering fail closed.
- ProductPackage can later consume receipt IDs instead of trusting source-card
  status strings.
