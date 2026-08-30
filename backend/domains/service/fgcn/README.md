# FGCN service-collaboration P0 slice

This package is the first executable service-collaboration slice for AiFamily.
It maps the governed path:

```text
published blueprint
  → ServiceCase (frozen snapshot)
  → ServiceTask (template + acceptance criteria)
  → Human Gate NamedActionRequest
  → TaskAssignment (one accepted responsible person)
  → Delivery evidence
  → quality verification
  → ServiceContribution
  → one 100-unit shadow AllocationStatement
```

The business orchestration remains intentionally deterministic and in-memory,
while `SqlAlchemyFGCNRepository` now provides a durable adapter for the same
P0 facts. Case opening claims the existing platform `idempotency_keys` row with
an opaque tenant-scoped key and request hash; the claim, case, audit, and
response binding commit together. `SqlAlchemyHumanGate` persists the reviewed proposal, human decision,
scope, and provenance reference; `consume_accepted_human_task` is a one-shot
worker handler that first acquires a durable claim/lease and then delegates the
accepted request to the durable assignment command. Re-running that handler
after a worker crash is safe because an expired lease can be taken over and the
command replays by request id. The handler is not yet a resident queue
process: notifications, dead-letter handling, and production identity/consent
factories remain follow-up work. These components do not call a model provider,
accept payment, calculate family scores, or write settlement records. A
persisted `ServiceContribution` also retains its `delivery_ref`;
without that link, a post-restart contribution could not be traced back to the
accepted delivery and must be rejected.

Before the assignment command writes a `TaskAssignment`, it consumes a
provider-admission query snapshot. The snapshot must identify the requested
provider and role, be `ACTIVE`, allow the case purpose, and cover every
`required_capability_keys` declared by the task. FGCN does not own provider
qualification facts; an absent or failed admission query rejects the command.
The snapshot must also report a non-negative integer `capacity_available`.
Zero capacity is an explicit `RESOURCE_GAP` refusal, so no assignment, task
transition, or contribution can be created. This is a check of the upstream
snapshot only: atomic capacity reservation under concurrent requests remains
an upstream provider-supply dependency and is not represented as cash,
settlement, or a local FGCN fact.

Before the case-opening command writes a `ServiceCase`, it consumes a separate
`CaseEntryDependencyQuery` snapshot. The snapshot must prove a `CONFIRMED`
GrowthIntent, an `ACTIVE` Consent whose subject/purpose/version exactly match
the case scope, and an `ACTIVE` tenant-family binding for the same tenant and
family. Missing or failed queries reject the opening command. This is a
boundary contract, not an Onboarding or FamilyNeed implementation: until the
upstream Fake/Postgres/HTTP paths are equivalent and backed by real-PostgreSQL
evidence, neither can be described as a complete FGCN entry. The default
production seam remains rejecting until those facts are explicitly wired.

The same facts can be inspected through the read-only
`build_fgcn_pdca_projection` projection as a deterministic PDCA cycle:

```text
PLAN  = case intent/plan/blueprint + admitted capability/capacity snapshot
DO    = one accepted responsible person + concrete delivery evidence
CHECK = a human, non-delivery-person PASSED QualityDecision
ACT   = verified contribution + completed case + persisted shadow allocation
```

The projection reports the first unmet phase and explicit blockers. It never
calls a model, writes a fact, assigns a provider, accepts delivery, or
finalizes allocation. `RESOURCE_GAP`, missing delivery evidence, missing
human quality review, missing contribution, incomplete case closure, and a
missing/mismatched shadow-finalization marker remain visible as blockers.
AI may propose through the existing Model Gateway/Human Gate path, but it
cannot perform assignment, quality acceptance, or allocation finalization.
