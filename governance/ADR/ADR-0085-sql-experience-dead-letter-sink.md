# ADR-0085: SQL metadata-only Experience dead-letter sink

- Status: Accepted
- Date: 2026-08-30

## Decision

Production Experience Outbox composition may use
`SqlAlchemyExperienceDeadLetterSink`. It stores one idempotent row per
`message_id` containing event type, tenant/family scope, attempt count, bounded
error text and terminal timestamp. It intentionally does not store `payload`;
the source outbox remains the authoritative opaque envelope for controlled
replay and deletion handling.

The sink participates in the relay's caller-owned transaction. A duplicate
write with identical stable metadata is a no-op; a mismatch is rejected rather
than silently overwriting an audit record.

## Consequences

- the default deployment can persist DLQ metadata without leaking raw family
  content into an operational index;
- terminal delivery state remains queryable across restarts;
- replay tooling must explicitly authorize reading the source outbox envelope;
- retention/deletion policy and a production alerting transport remain
  deployment responsibilities.
