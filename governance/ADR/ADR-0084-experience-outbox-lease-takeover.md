# ADR-0084: Experience Outbox lease and takeover

- Status: Accepted
- Date: 2026-08-30

## Decision

The Experience Outbox delivery ledger owns a short-lived lease identified by
an operational `worker_id`. A worker must claim a message before consuming it.
An active lease held by another worker is skipped; after `lease_until`, a new
worker may take over and increment the durable attempt number. The same worker
may retry before expiry. Successful publication or dead-letter acknowledgement
clears the lease.

The lease contains no event payload and does not replace domain authorization.
It is a delivery-concurrency guard only; consumers remain idempotent because a
crash can occur after projection and before acknowledgement.

## Consequences

- multiple relays no longer intentionally consume the same pending row while a
  healthy lease is active;
- crashed workers are recoverable without manual data edits;
- operational identity and lease TTL are explicit composition dependencies;
- PostgreSQL row locking and deployment-level scheduler/observability still
  require environment integration and concurrency testing.
