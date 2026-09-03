---
id: ADR-0060
title: AI release admission gate for evaluated providers
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0060：AI release admission gate

## Context

`multimodal_eval` and `model_benchmark` produce offline, provider-neutral
evidence, while `model_gateway/provider_registry` is the only authority that
decides whether a provider may be reached in an environment.  Without one
deterministic seam, an operator could mistake a good benchmark score for
production approval, or approve a provider whose compliance record is missing.

## Decision

Add `backend/intelligence/evaluation/release_gate.py` with a pure
`AiReleaseGate.evaluate()` operation.  It accepts an immutable benchmark report,
an injected `ProviderRegistry`, an explicit environment and data class, and
reviewable quality/safety/schema/refusal/provenance, latency and cost limits.
The operation:

1. selects exactly one candidate (multi-candidate reports require an explicit
   candidate id);
2. calls `ProviderRegistry.admit()` before considering the report releasable;
3. checks provider/model/version identity and every configured threshold;
4. returns an auditable `ReleaseDecision` (`ADMITTED` or `BLOCKED`) with stable
   failure codes and an opaque report reference.

Unknown providers, non-approved statuses/environments, missing evidence,
threshold breaches and benchmark compliance failures all block.  The gate does
not call a model, deploy a release, mutate a domain fact, or bypass Human Gate;
the caller must still perform the separately governed Named Action and human
approval flow.

## Consequences

- Test and production use the same fail-closed decision contract; only the
  injected registry/environment and data change.
- Approval is explainable and replayable from the benchmark report and registry
  record, with no raw media or model output copied into the decision.
- Thresholds are intentionally conservative defaults and must be changed by a
  reviewed configuration change, not by a provider adapter.
- This is an admission seam. The evaluated decision is now persisted by the
  separate `ReleaseAdmissionService`/`SqlAlchemyReleaseDecisionSink` ledger
  (ADR-0070), but a signed release catalog, rollback controller and production
  composition-root wiring remain explicit follow-up work.
