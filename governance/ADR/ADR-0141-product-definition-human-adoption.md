# ADR-0141: Accepted Human Gate action creates the PDM draft

- Status: Accepted
- Date: 2026-09-01
- Scope: Product Intelligence / IPD-to-PDM boundary

## Context

The Product Factory currently returns an unpersisted package DRAFT, while the
Three-Zone engine separately records rule recommendations and human-approved
zones. A direct Web mutation endpoint would let a client claim a decision and
provenance without proving that an `ActionProposal` was accepted by the durable
Human Gate. That is not a Named Action and is forbidden by R8/R9.

## Decision

The first PDM adoption slice starts only from an already accepted
`NamedActionRequest`. Product Intelligence registers the explicit handler
`ADOPT_PRODUCT_CONCEPT_AS_DEFINITION` with the accepted-action dispatcher.
There is no direct `/adopt` HTTP route.

The handler must:

1. accept the immutable `NamedActionRequest`, never client-supplied actor,
   task, proposal, decision or provenance fields;
2. require `ActorType.OPERATOR`, then re-authorize every first execution
   `product_intelligence.product_definition.adopt` through an injected policy
   port owned by the composition root;
3. require a tenant-level scope (`family_id=None`), the exact purpose
   `service_product_definition_adoption`, an explicit non-placeholder
   processing-basis/consent reference and exact subject bindings to both the
   concept and assessment;
4. strict-parse reviewed action arguments and reject extra fields, including a
   client-selected `zone`;
5. load the concept and `ProductZoneAssessment` in the same tenant, accept only
   `APPROVED + approved_zone`, and require `assessment.subject_ref` to equal
   the concept id;
6. derive the PDM zone with the fixed mapping
   `COMMODITY -> HOMOGENEOUS`, `ADVANTAGE -> ADVANTAGE`, and
   `UNIQUE -> UNIQUE_CANDIDATE`;
7. create only `ProductDefinition(DRAFT)`, never a published blueprint,
   Journey, Service or Commerce fact;
8. preserve a schema-versioned, frozen `ProductDefinitionAdoptionSnapshot`
   containing request/task/proposal/decision lineage, provenance, reviewed
   assessment version/policy/approved zone, reviewer and request hash;
9. scope replay identity by tenant and Human Gate idempotency key, return the
   same definition for an exact durable replay before current permission or
   mutable assessment reads, and reject changed replays;
10. persist the definition and mutation audit in one repository transaction,
    rolling both back if either write fails.

The snapshot is nested in the existing `education_spec` JSON field for this
slice, so no migration is introduced while another migration chain is in
progress. It is separate from editable specification fields and frozen by its
Pydantic contract. If ProductDefinition editing is later introduced, moving
the snapshot to a dedicated append-only adoption ledger requires a new ADR and
migration before edits may mutate this lineage.

## Consequences

- AI remains free to research, challenge and compose product candidates, but
  cannot accept or execute its own proposal.
- The accepted-action handler and dispatcher registration map are implemented
  and independently testable.
- The global Family API accepted-worker composition does not yet register this
  handler, and the current random, unpersisted product-package DRAFT does not
  yet enter Human Gate. Therefore this slice is a verified downstream control
  point, not a production-available Web adoption workflow.
- The next slice must persist the package DRAFT, create the product
  `ActionProposal`, expose Human Gate review to Web operators, and register the
  handler in the application-owned worker composition without weakening this
  command.

## Verification

- Tests cover all three zone mappings, explicit dispatcher registration,
  operator and authorization gates, exact scope, APPROVED state, subject
  binding, extra-field rejection, exact replay and changed replay.
- Replay after the assessment lifecycle changes uses the accepted snapshot and
  produces no second audit event.
- SQL integration proves a fresh session reads both the definition and durable
  audit after one successful command commit.
- Fault-injection tests prove an audit failure rolls back the definition and
  leaves both the fake repository and SQL session reusable for a clean retry.
