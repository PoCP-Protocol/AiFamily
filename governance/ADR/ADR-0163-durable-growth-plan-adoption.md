# ADR-0163 Durable Growth Plan Adoption

- Status: Accepted
- Date: 2026-09-10
- Scope: Journey growth-plan adoption

## Decision

Persist the guardian's adoption of a generated growth-plan draft in the
Journey-owned `journey_adopted_growth_plans` table. Reuse the existing
`ai_model_drafts`/`ai_growth_plan_draft_reviews` registries for drafts, the
platform `idempotency_keys` table for replay protection, and the shared
`platform_audit_events` table for the mutation audit.

The record remains an adopted projection of a human-reviewed draft. It is not
an AI-created fact, diagnosis, score, ranking, or outcome.

## Consequences

The read/adopt route can be composed over PostgreSQL and survive process
restart. The migration adds no second identity, consent, context, or audit
system. Automatic execution and external side effects remain outside this
boundary.
