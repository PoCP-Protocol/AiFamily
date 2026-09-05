# ADR-0129: Persist education-product design fields on ProductDefinition

- Status: Accepted
- Date: 2026-08-31
- Scope: Product Intelligence / IPD-PDM-PLM

## Context

The domain `ProductDefinition` now carries the design contract for family
education products (including 21-day and 90-day packages), demand/market
traceability and AI provenance. The provisional `0058` SQL snapshot and its
SQLAlchemy row only stored the original concept/pattern/component fields.
Writing the richer domain object therefore failed at the persistence boundary.

## Decision

Add nullable/defaulted columns through a post-baseline Alembic revision
`0038_product_definition`. Existing rows remain readable as `CUSTOM`/
`HOMOGENEOUS` definitions, while new education definitions persist their
specification, references and provenance. Domain validation remains the source
of truth for required fields and 21/90-day invariants; the database migration
does not promote a draft or bypass human gates.

## Consequences

- Product Factory drafts can be persisted without dropping IPD fields.
- Legacy rows remain compatible and can be migrated deliberately later.
- `education_spec` is JSON at this boundary; a future normalized component
  registry may add foreign keys without changing the draft contract.
- Release/publish still requires the existing human-gated PLM command.
