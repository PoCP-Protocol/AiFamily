"""Ports (interfaces) for the Product Zone (Three-Zone Strategy Engine)
governance commands in `zone_commands.py`. Implemented by `infrastructure/`
(Agent C's file ownership — this module only defines the `Protocol`, per
the same four-layer rule as `application/ports.py`).

Kept as a separate port from `ProductIntelligenceRepositoryPort` because
`zone_entities.ProductZoneAssessment`/`ZonePolicyVersion` are Agent A's
ADR-accurate replacement types (see `domain/zone_entities.py` module
docstring) — distinct from the legacy placeholder `ProductZoneAssessment`
still declared in `domain/entities.py` and already load/save-able via
`ProductIntelligenceRepositoryPort.save_product_zone_assessment`. Mixing
the two under one Protocol would blur which `ProductZoneAssessment` a
method operates on; a separate port makes the distinction explicit at the
type-import level.

Tenancy judgment call (no explicit ADR ruling on this point, so recorded
here for other agents/Agent G to review):

- `ProductZoneAssessment` rows ARE tenant-scoped. An assessment is a
  judgment about one tenant's `ProductConcept`; cross-tenant visibility of
  a specific assessment (its dimension scores, evidence refs, review
  history) would leak one tenant's product strategy into another's. Same
  pattern as every other `load_*` in `application/ports.py`
  (PR-001R item 3): raise `ProductIntelligenceNotFoundError` for both
  "wrong id" and "right id, wrong tenant" — never a distinguishable error.
- `ZonePolicyVersion` rows are NOT tenant-scoped — they are platform-level
  configuration (the six-dimension definitions, weights, thresholds,
  classification rule, review policy) that ADR-Governance §3 describes as
  versioned shared policy, not a per-tenant business object. There is no
  tenant-specific customization concept anywhere in either ADR for
  `ZonePolicyVersion`; every tenant's assessments are scored against the
  same active policy version so that "same inputs + same policy version
  -> same result" (the canonical-hash invariant, ADR-Governance §3) holds
  platform-wide, not just within one tenant. Hence
  `load_active_zone_policy_version` takes an optional `tenant_scope` only
  for call-site symmetry/future-proofing (e.g. if a future ADR revision
  ever wants tenant-specific policy overrides) but the V0 contract MUST
  NOT filter by it — implementations should ignore it or accept `None`.
"""
from __future__ import annotations

from typing import Protocol

from ..domain.zone_entities import ProductZoneAssessment, ZonePolicyVersion


class ZoneAssessmentRepositoryPort(Protocol):
    async def save_zone_assessment(self, entity: ProductZoneAssessment) -> None: ...

    async def load_zone_assessment(self, entity_id: str, tenant_scope: str) -> ProductZoneAssessment:
        """Must raise `ProductIntelligenceNotFoundError` for both a
        nonexistent id and an id that exists under a different
        `tenant_scope` — see module docstring, same rule as every
        `load_*` in `application/ports.py`."""
        ...

    async def load_active_zone_policy_version(self, tenant_scope: str | None = None) -> ZonePolicyVersion:
        """Loads the current `status == "ACTIVE"` `ZonePolicyVersion`.
        NOT tenant-scoped in V0 — see module docstring "Tenancy judgment
        call". `tenant_scope` is accepted (optional, defaults to `None`)
        for call-site symmetry only; an implementation must not use it to
        filter results in V0."""
        ...

    async def save_zone_policy_version(self, entity: ZonePolicyVersion) -> None: ...
