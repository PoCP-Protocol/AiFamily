# ADR-0131: Deterministic Product Factory compiler before model execution

- Status: Accepted
- Date: 2026-08-31
- Scope: Design Copilot / IPD-PDM-PLM

## Decision

Product definitions are admitted to the next IPD step only after a pure,
deterministic compiler runs twelve checks: schema, components, compatibility,
workflow, resources, AI use case, context boundary, safety, Human Gate, cost,
evaluation and SLA. The compiler receives an explicit immutable catalog/context
and returns a read-only report; an empty catalog fails closed.

The compiler accepts a ProductDefinition-shaped value through a boundary
protocol and keeps the business domain import type-only. It never calls a model,
provider, repository or business Named Action, and it does not promote a draft.

## Consequences

- Compile failures are replayable and explainable before any simulation or
  release candidate is created.
- Catalog/version ownership stays outside the AI runtime and can later be
  backed by PostgreSQL or a registry without changing the check contract.
- A passing compile report is evidence for a Human Gate, not a substitute for
  human approval or pilot evidence.
