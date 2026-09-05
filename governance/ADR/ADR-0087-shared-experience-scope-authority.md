# ADR-0087: Shared scope authority for Draft and feedback reads

- Status: Accepted
- Date: 2026-08-30

## Decision

Feedback read requests must derive their `ExperienceScope` from the same
authenticated Draft runtime resolver used by multimodal generation. The
`SharedExperienceFeedbackRuntimeResolver` delegates family resolution to that
runtime, adapts its trusted `ContextScope` once, and then opens a separate
session-per-call reader for Achievement/Notification/Analytics projections.

The feedback HTTP body has no scope, consent, provider or identity controls.
Deployments may still inject a dedicated resolver, but it must perform the same
identity/consent/deletion checks and is responsible for proving parity.

## Consequences

- Draft and feedback reads cannot silently disagree about tenant/family/subject
  authorization when the shared resolver is used;
- projection reads remain isolated from generation transactions and never call a
  model provider;
- a real deployment must wire the shared resolver and durable session factory;
  an absent resolver remains a fail-closed 503.
