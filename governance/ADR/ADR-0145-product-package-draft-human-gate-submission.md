# ADR-0145: ProductPackage DRAFT is an immutable Product Intelligence version

- Status: Accepted
- Date: 2026-09-01
- Owners: Product Intelligence / AI Platform
- Related: ADR-0140, ADR-0141, ADR-0143

## Context

The Product Factory can compose a Web response named `ProductPackageDraft`, but
that response is currently transient: it has no durable version, no readback,
and no server-owned hand-off to Human Gate. Treating that response as an
approved package would skip the IPD decision boundary and violate R6, R8 and
R9.

There is also a second `ProductPackage` contract under AI Runtime. That object
is a provider-neutral proposal/lifecycle contract. It does not own product
facts and must not become a competing PDM master-data implementation.

Market benchmarks consistently separate a versioned source artifact, a change
proposal, an approval decision and execution authorization. They also retain
the exact source version, evidence lineage and author checkpoint used by a
task, rather than silently rebasing an old task onto new configuration.

## Decision

### Canonical owner and semantics

`product_intelligence` owns the durable `ProductPackageDraftVersion`. It is an
immutable design snapshot with the only legal status `DRAFT`. It is not a
`ProductDefinition`, a release baseline, an approval or a delivery fact.

AI Runtime may construct provider-neutral draft values, but it cannot persist
them to a business repository or advance their lifecycle. The Product
Intelligence application performs the anti-corruption mapping.

### Frozen source and evidence

Every version freezes:

- concept and approved ProductZoneAssessment identity, assessment version,
  policy version and approved zone;
- upstream decision draft, demand, market and competitor evidence references;
- component, Skill, metric, guardrail, stop and pause configuration;
- exact VERIFIED evidence reference set, assumptions and unknowns;
- source AI provenance, model and prompt-use-case version;
- author identity from trusted `ActorContext`, timestamps and a canonical
  content hash.

The request cannot supply tenant or actor identity. A future HTTP adapter must
also remove `zone`: the application derives it only from the approved,
tenant-scoped assessment. Confidence remains explanatory metadata and never
approves a proposal.

### DRAFT and ActionProposal remain distinct

Explicitly submitting a DRAFT for review creates a separate `ActionProposal`
for the fixed named action
`ADOPT_PRODUCT_CONCEPT_AS_DEFINITION`. The proposal references the exact draft
and carries only the strict `ProductDefinitionAdoptionArguments`; richer
package evidence remains on the immutable source version.

The resulting HumanTask is `OPEN`. Creation does not decide the task, create a
NamedActionRequest, persist a ProductDefinition, enter PILOT or advance PLM.
Those transitions remain separate human-controlled steps.

Only a trusted human actor with explicit submit permission may perform this
transition. AI generation completion, autosave and page load cannot call it.
The current slice does not yet provide a separate server-side SAVED_DRAFT
checkpoint; the Web must not label this review-submission endpoint as autosave.

### Atomicity, replay and tenancy

The draft row, HumanTask and both audit records share one `AsyncSession` and
one commit. Any failure rolls the whole submission back.

`(tenant_scope, actor_id, idempotency_key)` is unique. An exact replay returns
the original draft and task, even if the current assessment later changes. A
different request body with the same key conflicts. Reads are tenant scoped;
wrong tenant and missing identifiers are intentionally indistinguishable.

### Versioning

The first slice creates immutable version `1.0.0`. Updating it in place is
forbidden. A later revision API will create a new version and explicit
`supersedes_ref`; stale proposal/rebase handling is deferred to that slice.

## Delivery boundary

This ADR's first implementation provides the domain contract, SQL repository,
atomic Human Gate submission and SQLite-backed integration proof. It does not
claim production availability until all of these are true:

1. the shared Alembic chain through its then-current head is committed and the
   next single linear migration creates the draft table without a second head;
2. `DOMAIN_REGISTRY.yaml` and `CAPABILITY_REGISTRY.yaml` are updated by or with
   their current owners, without overwriting concurrent WIP;
3. the strict HTTP create/read adapter is paired with a production source
   resolver that consumes server-owned evidence-verification receipts and AI
   provenance records rather than trusting browser or legacy card status;
4. the Web workbench performs create-read verification before it offers Human
   Gate submission;
5. real PostgreSQL concurrency and migration-vs-ORM tests pass.

Until then the surface is independently testable application infrastructure,
not a production-mounted capability.

## Consequences

- The Product Factory gains a stable PDM source version instead of relying on
  a random response DTO.
- Existing ProductDefinition operator review can consume the generated OPEN
  HumanTask without a second review mechanism.
- No browser-controlled zone or direct AI-to-fact transition is introduced.
- Migration and governance promotion remain explicit blockers rather than
  being hidden behind `metadata.create_all` test success.
