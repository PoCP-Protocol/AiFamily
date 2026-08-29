"""HTTP request bodies — port of `StartAssessmentRequest` /
`SaveAssessmentResponseRequest` (packages/contracts/src/ui02-assessment.ts)
and the growth-hypothesis decision body validated inline in
`family.controller.ts` (`decideGrowthHypothesis`).
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class StartAssessmentRequestBody(BaseModel):
    subject_person_id: str
    tool_ref: str | None = None


class SaveAssessmentResponseRequestBody(BaseModel):
    item_ref: str
    response_type: Literal["SINGLE_CHOICE", "TEXT", "BOOLEAN"]
    response_value: str | bool


class DecideGrowthHypothesisRequestBody(BaseModel):
    assessment_session_id: str
    hypothesis_ref: str
    decision_type: Literal["CONFIRM", "DISMISS"]
