---
id: ADR-0020
title: DEV/TEST no-op commerce intent flow
status: accepted
date: 2026-08-30
---

# DEV/TEST no-op commerce intent flow

## Context

UI-14 needs to preserve a family's interest in a product and render that state
on revisit. The baseline separates `family_order_intents` and
`family_entitlements` from the product catalogue, and explicitly forbids using
these records as payment or production order state.

## Decision

Implement a named, idempotent `submit_order_intent` command and a private
customer projection. The command snapshots product identity/version, creates a
DEV/TEST `PENDING` no-op entitlement, and sets `external_effect=false`. It
requires the authenticated family context and an idempotency key. Missing or
foreign product refs are rejected; replay returns the original receipt.

Payment, notification, fulfilment, and production entitlement transitions stay
outside this capability and require a separate decision and human-gated flow.

## Consequences

UI-14 can show a durable local/remote intent receipt without implying a
purchase. The fake and SQLite repositories exercise the same family isolation
and replay semantics. A production deployment still needs real session wiring,
consent policy, and an independently approved payment adapter.
