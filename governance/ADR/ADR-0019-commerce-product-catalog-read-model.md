---
id: ADR-0019
title: Commerce product catalogue read model for mobile UI-13/UI-14
status: accepted
date: 2026-08-30
---

# Commerce product catalogue read model

## Context

The mobile Mall (UI-13) and Product Detail (UI-14) screens need an admitted
product catalogue. The database baseline already defines
`family_product_offerings` as a versioned, fixture-only supply master, but the
Python commerce domain and the mobile read endpoint were absent. The existing
mobile presentation metadata is not a source of product identity.

## Decision

Introduce a small read-only commerce catalogue capability at
`backend/domains/commerce`:

- product identity and admission come from `ProductOffering`, not from the
  frontend presentation list;
- the development repository seeds only `fixture_only=true` platform products;
- UI-13/UI-14 read through
  `/families/{familyId}/orchestration/test-loop/commerce/products`;
- order intents, entitlements, payment, and fulfilment are explicitly outside
  this slice and remain unimplemented production capabilities;
- the production dependency fails closed until a SQLAlchemy repository and the
  existing baseline table are wired.

## Consequences

The mobile screens can consume canonical product refs and versions while
retaining presentation-only pricing/visual metadata. Development data is
idempotent and carries no external effect. Production readiness still requires
an ORM repository, Alembic/runtime migration wiring, and the separate order
intent capability.
