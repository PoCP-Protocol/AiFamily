# ADR-0136: Demand-driven product factory operating loop

- Status: Accepted
- Date: 2026-08-31
- Scope: Service Product AI Platform / IPD-PDM-PLM

## Context

The repository already contains product-factory draft contracts, deterministic
compiler checks and several target-state blueprints. The missing operating
decision is how market evidence, product definition, small pilots and lifecycle
feedback form one governed loop. Without that decision, additional AI screens
could become disconnected generators that cannot prove why a product should be
built or scaled.

External evidence is recorded in
`docs/13_research/market/SERVICE_PRODUCT_PLATFORM_BENCHMARK.md`.

## Decision

AiFamily will operate the service-product platform as a demand-driven loop:

1. capture a family-scenario signal as a `DemandFrame` draft;
2. create separately persisted `CompetitorEvidence` and `MarketInsight` drafts;
3. require insights and concepts to cite their source evidence;
4. compose versioned components and skills into a `ProductPackage` draft;
5. run deterministic compilation before a named human Gate;
6. validate accepted packages through a capacity-bounded pilot cohort;
7. feed delivery, safety, experience and cost evidence into a PLM decision of
   modify, scale, pause or stop.

AI may research, cluster, challenge, draft, compose and simulate throughout the
loop. AI output remains a draft or recommendation and cannot directly publish a
product, mutate canonical family facts, change entitlements, or target minors
with automated commercial marketing. Provider calls remain behind the Model
Gateway.

The transferable SHEIN mechanism is small-batch validation and selective scale,
not sales velocity as proof of educational effect. A pilot must retain explicit
capacity, safety, consent, pause and stop conditions.

## Consequences

- The first implementation slice is a Web Market Evidence Workbench: create
  competitor evidence as `UNKNOWN`, read it back from persistence, and reference
  it from a market-insight draft.
- Product discovery objects remain separate, versionable and traceable instead
  of becoming one mutable document.
- Non-verified, stale or contradicted evidence cannot satisfy a progression Gate.
- Later multimodal generation consumes accepted product definitions through the
  Model Gateway and produces governed assets, not standalone provider output.
- PLM scale decisions need operational evidence and named human accountability;
  model confidence alone is insufficient.

## Alternatives rejected

- **Chat-first product design:** fast to demo but loses object lifecycle,
  evidence lineage and deterministic admission checks.
- **Forecast-first portfolio planning:** invites subjective trend claims before
  observed family-scenario evidence.
- **Automatic AI publishing:** conflicts with draft-only AI outputs, Human Gate
  requirements and minor-safety constraints.
- **Direct model integrations per domain:** creates provider coupling and bypasses
  centralized safety, cost and provenance controls.

## Verification

- Component tests prove UNKNOWN evidence is visibly blocked from Gate progression.
- API tests prove competitor evidence can be created and read back under the
  same authorized tenant before it is referenced by a market insight.
- Architecture tests continue to reject direct model-provider calls and broken
  governance boundaries.
