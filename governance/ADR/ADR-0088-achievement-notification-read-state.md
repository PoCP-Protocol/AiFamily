# ADR-0088: Scope-local achievement notification read state

- Status: Accepted
- Date: 2026-08-30

## Decision

The achievement notification inbox exposes a `POST .../notifications/{id}/read`
operation that changes only the notification projection from `UNREAD` to
`READ`. The server resolves the authenticated `ExperienceScope` and requires
the notification's tenant and family to match that scope; clients cannot send
scope or provider controls.

Mobile callers must provide an `Idempotency-Key` and correlation headers. The
projection transition is state-idempotent: repeated requests return the same
`READ` receipt and timestamp, while the immutable achievement/event facts and
AI provenance are never rewritten.

## Consequences

- The feedback loop has an explicit seen/acknowledged state instead of a
  read-only unread snapshot.
- Retries are safe without an additional business-fact ledger because setting
  an already-read projection is a convergent operation.
- Notification retention/deletion remains a separate deployment concern and
  must use the same scope/deletion authority.
