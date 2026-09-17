"""HTTP request bodies — port of `StartAssessmentRequest` /
`SaveAssessmentResponseRequest` (packages/contracts/src/ui02-assessment.ts)
and the growth-hypothesis decision body validated inline in
`family.controller.ts` (`decideGrowthHypothesis`).
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


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
    # ADR-0158 Slice A `FAMILY_DECISION` node: CONFIRM (accept as-is),
    # EDIT (confirm a rewritten statement — requires `parent_note`), PARTIAL
    # (accept part of it), DISMISS (reject), LATER (defer). See
    # `growth_hypothesis_commands.py` module docstring for what each writes.
    decision_type: Literal["CONFIRM", "EDIT", "PARTIAL", "DISMISS", "LATER"]
    # Human-Gate-reviewed-draft binding. Intent-creating production paths
    # require the complete tuple. The canonical path resolves a viewed-
    # understanding receipt; the legacy AI interpretation path resolves an
    # accepted durable HumanTask and rejects an incomplete or stale tuple.
    scope_ref: str = ""
    signal_version: int = 0
    reviewed_draft_ref: str = ""
    draft_version: int = 0
    provenance_ref: str = ""
    human_gate_receipt_ref: str = ""
    # Free-text guardian note. Required (non-blank) for EDIT — it is the
    # rewritten understanding statement being confirmed instead of the AI's
    # draft. Optional for PARTIAL/LATER (which part / why deferring).
    # Ignored for CONFIRM/DISMISS.
    parent_note: str = ""


class DecideAssessmentHumanTaskRequestBody(BaseModel):
    """The only client-owned fields at the Assessment Human Gate boundary."""

    model_config = ConfigDict(extra="forbid")

    outcome: Literal["ACCEPT", "REJECT"]
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _normalise_reason(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalised = value.strip()
        return normalised or None
