# FGCN service-collaboration P0 slice

This package is the first executable service-collaboration slice for AiFamily.
It maps the governed path:

```text
published blueprint
  → ServiceCase (frozen snapshot)
  → ServiceTask (template + acceptance criteria)
  → Human Gate NamedActionRequest
  → TaskAssignment (one accepted responsible person)
  → Delivery evidence
  → quality verification
  → ServiceContribution
  → one 100-unit shadow AllocationStatement
```

The business orchestration remains intentionally deterministic and in-memory,
while `SqlAlchemyFGCNRepository` now provides a durable adapter for the same
P0 facts. `SqlAlchemyHumanGate` persists the reviewed proposal, human decision,
scope, and provenance reference; `consume_accepted_human_task` is a one-shot
worker handler that delegates the accepted request to the durable assignment
command. Re-running that handler after a worker crash is safe because the
command replays by request id. The handler is not yet a resident queue
process: lease/claim, notifications, dead-letter handling, and production
identity/consent factories remain follow-up work. These components do not call
a model provider, accept payment, calculate family scores, or write settlement
records. A persisted `ServiceContribution` also retains its `delivery_ref`;
without that link, a post-restart contribution could not be traced back to the
accepted delivery and must be rejected.
