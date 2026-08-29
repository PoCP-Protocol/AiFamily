"""Assessment domain entities.

Ported from `AssessmentSessionDto` / `AssessmentResponseDto`
(`packages/contracts/src/ui02-assessment.ts`) and the row shape loaded by
`GrowthHypothesisService.loadHypothesisRow`
(`apps/api/src/modules/family/growth-hypothesis.service.ts`).
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from .value_objects import AssessmentResponseType, AssessmentSessionStatus


class AssessmentResponse(BaseModel):
    assessment_response_id: str
    item_ref: str
    response_type: AssessmentResponseType
    response_value: str | bool
    revision: int
    captured_at: datetime
    visibility: str = "FAMILY_PRIVATE"


class AssessmentSession(BaseModel):
    assessment_session_id: str
    family_id: str
    subject_person_id: str
    tool_ref: str
    tool_version: int
    status: AssessmentSessionStatus
    started_at: datetime
    submitted_at: datetime | None
    row_version: int
    responses: list[AssessmentResponse] = []

    def is_editable(self) -> bool:
        return self.status == AssessmentSessionStatus.IN_PROGRESS

    def answered_item_refs(self) -> set[str]:
        return {response.item_ref for response in self.responses}


class GrowthHypothesisEvidence(BaseModel):
    """Row shape read for UI-03 — one confirmed assessment session mapped to
    exactly one candidate hypothesis (H1), per the NestJS
    `HypothesisRow` type. A session maps to at most one hypothesis in the
    current single-need-type-per-focus design; this is a straight port, not
    a redesign.
    """

    assessment_session_id: str
    subject_person_id: str
    subject_display_name: str
    submitted_at: datetime | None
    tool_ref: str
    tool_version: int
    assessment_response_id: str
    focus_ref: str
    assessment_evidence_id: str
    need_type_ref: str
    need_type_version: int
    title: str
    description: str
    required_capability_keys: list[str]
    response_set: list[dict]  # [{item_ref, response_type, response_value}, ...] — same shape fed to family-model
