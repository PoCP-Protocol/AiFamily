# ADR-0143: Server-owned ProductDefinition operator review surface

- Status: Accepted
- Date: 2026-09-01
- Scope: Product Intelligence / Web operator review / Human Gate

## Context

ADR-0141 introduced the downstream accepted-action handler that can create a
`ProductDefinition(DRAFT)`. The Web Concept Decision room still creates only a
browser-local intent, and a browser must never manufacture actor, tenant,
proposal, decision, provenance, approved zone or `NamedActionRequest` fields.
The durable Human Gate already owns immutable `ActionProposal`, `HumanDecision`
and `NamedActionRequest` snapshots.

## Decision

Product Intelligence exposes a separate operator review surface over existing
durable Human Gate tasks whose action is exactly
`ADOPT_PRODUCT_CONCEPT_AS_DEFINITION` and whose purpose is exactly
`service_product_definition_adoption`.

The surface follows these rules:

1. list and detail reads are tenant-scoped and require a trusted human
   `ActorContext` with `product_intelligence.product_definition.review`;
2. the app identity bridge may receive an explicit trusted
   `PermissionResolver`; no resolver means an empty permission set, never a
   default grant;
3. the Web decision body contains only `outcome` and mandatory `reason`;
   identity and all governance lineage come from the authenticated context and
   stored task;
4. `If-Match` binds the decision to the complete task resource snapshot, while
   `Idempotency-Key` derives a stable server decision id;
5. an exact durable replay is returned before rejecting an old ETag, while a
   changed replay conflicts; the resource ETag changes when status, decision or
   request state changes;
6. ACCEPT creates only a pending `NamedActionRequest`; REJECT and ESCALATE do
   not. The Web must not claim that a ProductDefinition exists until the
   accepted worker returns its execution receipt;
7. decision and audit are flushed and committed through the same Human Gate
   session, with rollback on failure;
8. expired OPEN rows are omitted from the queue. The existing Human Gate
   expiry worker remains the only component that persists the EXPIRED
   transition and audit.

No new table or migration is introduced; the surface reads and decides the
existing `ai_human_tasks` aggregate.

## Current delivery boundary

The router, trusted permission seam, SQL/fake adapters and Web workbench are
implemented and independently tested. The current `family_api/main.py` does
not call `mount_product_factory_router`, and production composition has not yet
installed a concrete `PermissionResolver`. Therefore this is a verified
application surface, not a production-available Web workflow.

The upstream ProductPackage DRAFT is also not yet persisted as the source of a
Human Gate proposal. That next slice requires a domain-owned immutable draft
record and an Alembic migration. The current shared migration chain must be
linearized before allocating that revision.

## Consequences

- Web operators can use one fail-closed queue/detail/decision contract once the
  owning app installs the router, session and authorization policy.
- The browser cannot turn a local Decision DRAFT into evidence of approval.
- Product package submission, production app mounting, accepted worker handler
  registration and real PostgreSQL concurrency remain explicit next steps.

## Verification

- Backend tests cover permission, tenant hiding, purpose and expiry filtering,
  ETag conflict, exact idempotent replay, changed replay, forged body fields,
  ACCEPT/REJECT semantics and SQL audit persistence.
- Web tests cover Bearer transport, lineage validation, decision body shape,
  explicit reason, two-step confirmation and honest pending-execution copy.
- Desktop and 390-pixel browser checks verify the accessible five-tab workspace
  and PDM Review empty state without horizontal overflow.
