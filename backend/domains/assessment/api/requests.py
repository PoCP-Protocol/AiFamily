"""HTTP request bodies — port of `StartAssessmentRequest` /
`SaveAssessmentResponseRequest` (packages/contracts/src/ui02-assessment.ts)
and the growth-hypothesis decision body validated inline in
`family.controller.ts` (`decideGrowthHypothesis`).
"""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

NonEmptyRef = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
PositiveVersion = Annotated[int, Field(ge=1)]


class StartAssessmentRequestBody(BaseModel):
    subject_person_id: str
    tool_ref: str | None = None


class SaveAssessmentResponseRequestBody(BaseModel):
    item_ref: str
    response_type: Literal["SINGLE_CHOICE", "TEXT", "BOOLEAN"]
    response_value: str | bool


class DecideGrowthHypothesisRequestBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    assessment_session_id: NonEmptyRef
    hypothesis_ref: NonEmptyRef
    decision_type: Literal["CONFIRM", "DISMISS"]
    scope_ref: NonEmptyRef
    signal_version: PositiveVersion
    reviewed_draft_ref: NonEmptyRef
    draft_version: PositiveVersion
    provenance_ref: NonEmptyRef
    human_gate_receipt_ref: NonEmptyRef
