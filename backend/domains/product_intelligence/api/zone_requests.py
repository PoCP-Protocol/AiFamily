"""API request DTOs for the Product Zone (Three-Zone Strategy Engine)
governance endpoints. Same convention as `api/requests.py`: actor identity/
`tenant_scope` never appear in a request body — they come exclusively from
`ActorContext` (see `api/dependencies.py::get_actor_context`).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from ..domain.zone_value_objects import ZoneDimensionName


class CreateZoneAssessmentRequest(BaseModel):
    zone_policy_version_id: str


class ZoneDimensionAssessmentInput(BaseModel):
    """Mirrors `domain/zone_entities.py::DimensionAssessment`'s
    caller-supplied fields exactly (minus nothing) — `application/
    zone_commands.py::score_zone_assessment` consumes this shape as
    `dict`s, so this DTO's field set is a direct pass-through, not a
    narrower/looser projection of the domain type.
    """

    dimension: ZoneDimensionName
    score: float
    rationale: str
    evidence_refs: list[str]
    evidence_strength: float = 0.5
    assessed_by: str | None = None
    assessed_at: datetime | None = None


class ScoreZoneAssessmentRequest(BaseModel):
    dimension_assessments: list[ZoneDimensionAssessmentInput]


class ApproveZoneAssessmentRequest(BaseModel):
    approved_zone: str
    review_reason: str
    override_reason: str | None = None


class RejectZoneAssessmentRequest(BaseModel):
    review_reason: str
