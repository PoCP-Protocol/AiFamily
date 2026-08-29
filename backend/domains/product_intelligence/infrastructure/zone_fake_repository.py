"""In-memory fake implementing `application/zone_ports.py::
ZoneAssessmentRepositoryPort`, mirroring `fake_repository.py`'s role for
the acceptance-chain port. Distinct from the minimal test-local
`FakeZoneAssessmentRepository` defined inside
`tests/test_zone_review_governance.py` (Agent B's test file, not touched
here) — this module is the one importable fake meant for reuse across
this Agent's own persistence/API tests (`tests/test_zone_api_endpoints.py`)
and any future caller that wants a DB-free double of this port.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.errors import ProductIntelligenceNotFoundError
from ..domain.zone_entities import ProductZoneAssessment, ZonePolicyVersion


@dataclass
class FakeZoneAssessmentRepository:
    _assessments: dict[str, ProductZoneAssessment] = field(default_factory=dict)
    _policy_versions: dict[str, ZonePolicyVersion] = field(default_factory=dict)

    async def save_zone_assessment(self, entity: ProductZoneAssessment) -> None:
        self._assessments[entity.id] = entity

    async def load_zone_assessment(self, entity_id: str, tenant_scope: str) -> ProductZoneAssessment:
        entity = self._assessments.get(entity_id)
        if entity is None or entity.tenant_scope != tenant_scope:
            # PR-001R item 3, same rule as `fake_repository.py`: a caller
            # cannot distinguish "wrong id" from "right id, wrong tenant".
            raise ProductIntelligenceNotFoundError("zone_assessment_not_found")
        return entity

    async def load_active_zone_policy_version(self, tenant_scope: str | None = None) -> ZonePolicyVersion:
        # NOT tenant-scoped in V0 — see `application/zone_ports.py` module
        # docstring "Tenancy judgment call". `tenant_scope` is accepted for
        # call-site symmetry only and must not be used to filter here.
        for policy in self._policy_versions.values():
            if policy.status == "ACTIVE":
                return policy
        raise ProductIntelligenceNotFoundError("zone_policy_version_not_found")

    async def save_zone_policy_version(self, entity: ZonePolicyVersion) -> None:
        self._policy_versions[entity.policy_id] = entity
