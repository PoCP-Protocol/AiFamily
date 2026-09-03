# ADR-0083: Durable Experience Outbox runtime

- Status: Accepted
- Date: 2026-08-30

## Decision

Experience events are relayed through an explicit `ProductionExperienceOutboxRuntime`.
Every bounded poll opens a fresh SQL session and composes the existing opaque
outbox, a metadata-only delivery-attempt ledger, an injected consumer, and an
injected dead-letter sink. The worker acknowledges an outbox row only after the
consumer (or DLQ sink) succeeds. Attempt counts and terminal status survive
process restarts; raw family payload remains only in the outbox and is not
duplicated into operational DLQ metadata.

Staging and production use the same composition path. A deployment scheduler,
worker identity, queue lease/takeover policy, and concrete DLQ storage remain
explicit infrastructure dependencies rather than being silently synthesized.

## Consequences

- transient failures can be retried with durable attempt numbers;
- operators can inspect message id, attempts, status, error and timestamps
  without reading sensitive event payloads;
- consumer implementations remain provider-neutral and can project achievements
  or growth graphs without direct model-provider access;
- deployment still needs a recurring scheduler and concurrency/lease validation.
