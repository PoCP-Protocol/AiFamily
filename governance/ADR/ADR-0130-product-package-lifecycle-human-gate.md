# ADR-0130: Human Gate controls ProductPackage lifecycle transitions

- Status: Accepted
- Date: 2026-08-31
- Scope: Product Management / IPD-PDM-PLM

## Decision

The Product Factory may produce only a `DRAFT`. A ProductPackage lifecycle
transition is accepted only through a Human Gate decision whose outcome is
`ACCEPT`, whose actor is a registered human reviewer, and whose evidence is
complete and unique. The application adapter maps that decision to IPD `GO`
and delegates the sequential transition to the immutable package contract.

The allowed sequence is `DRAFT → PILOT → QUALIFIED → RELEASED`. A release
transition additionally requires a matching, already human-approved and
released `ReleaseBaseline`. Rejection, escalation, expired/future decisions,
non-human actors, missing evidence and baseline mismatches fail closed.

## Consequences

- AI output cannot publish or mutate a product definition by itself.
- The adapter returns an immutable package value and audit projection; the
  owning application remains responsible for transactional persistence,
  authorization re-check, idempotency and audit recording.
- PLM rollback/pause/retire remain explicit human actions and are not inferred
  from pilot metrics.
