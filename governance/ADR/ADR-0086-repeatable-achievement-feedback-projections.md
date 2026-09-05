# ADR-0086: Repeatable achievements and governed feedback projections

- Status: Accepted
- Date: 2026-08-30

## Decision

An evidence-bound Achievement has a stable `occurrence_id`. One-time
milestones use `default`; AI evidence moments derive an occurrence from the
validated evidence set (or an explicitly bounded candidate identity). The
projection uniqueness boundary is therefore
`scope_fingerprint + achievement_key + occurrence_id`, allowing distinct
events to produce distinct family-private moments while preserving replay
conflicts.

After an achievement projection succeeds, the Experience consumer may update
two read-only projections in the same outbox transaction:

- an in-app notification inbox, keyed by `achievement_id`, with unread/read
  state and no push-provider side effect;
- scope-local analytics counters for event and achievement kinds, protected by
  a metadata-only input idempotency ledger.

Neither projection writes Family/Journey/Service/Commerce facts, computes a
family total/rank, or exposes raw event/model payloads.

## Consequences

- repeated, evidence-distinct progress can be rendered without weakening
  idempotency;
- notification and analytics replay is safe across worker restarts;
- push delivery, retention/deletion jobs, and product-level metric governance
  remain separate deployment responsibilities.
