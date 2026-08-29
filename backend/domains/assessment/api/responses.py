"""HTTP response models for OpenAPI generation only.

These mirror the hand-written TypeScript contracts in
`packages/contracts/src/ui02-assessment.ts` and
`packages/contracts/src/ui03-growth-hypothesis.ts` field-for-field (including
every optional field), NOT a fresh design. They exist purely so
`app.openapi()` (see `export_openapi.py`) produces a real schema instead of
`{"type": "object"}`.

Deliberately NOT wired as `response_model=` on any route in `routes.py`:
FastAPI's `response_model` silently drops any field present on the returned
dict but absent from the model (verified empirically — this is
`pydantic`/FastAPI's documented filtering behavior, not a bug). The six
handlers in `application/commands.py`, `application/queries.py`, and
`application/growth_hypothesis_commands.py` return plain dicts with some
genuinely dynamic shape (e.g. `scorecard` differs between the deterministic
and live-Claude interpretation adapters — see `infrastructure/*.py`), so
wiring these models as `response_model` would risk silently truncating a
real field the frontend depends on. Until every one of those dicts is
replaced by a real typed return value at the application layer (a bigger,
deliberate refactor — out of scope here per the "don't change behavior"
constraint), these models are exposed to routes only via `responses=` /
`openapi_extra` in `routes.py`, which FastAPI merges into the schema without
touching the actual runtime response.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

from ..domain.value_objects import (
    AssessmentResponseType,
    Ui02AssessmentAvailability,
)

# ---- UI-02 (assessment) ----------------------------------------------------


class AssessmentToolBoundaryModel(BaseModel):
    truth_class: Literal["FAMILY_PERSPECTIVE"]
    not_a_score: Literal[True]
    not_a_diagnosis: Literal[True]
    no_eligibility_effect: Literal[True]
    withdrawable: Literal[True]
    training_use: Literal[False]


class Ui02AssessmentToolItemModel(BaseModel):
    item_ref: str
    response_type: AssessmentResponseType
    required: bool
    options: list[str] | None = None


class Ui02AssessmentToolModel(BaseModel):
    tool_ref: str
    version_no: int
    title: str
    purpose: str
    evidence_level: Literal["E1"]
    schema_ref: str
    items: list[Ui02AssessmentToolItemModel]
    boundary: AssessmentToolBoundaryModel


class Ui02AssessmentSubjectModel(BaseModel):
    person_id: str
    display_name: str
    availability: Literal["AVAILABLE", "CONSENT_REQUIRED"]


class AssessmentResponseDtoModel(BaseModel):
    assessment_response_id: str
    item_ref: str
    response_type: AssessmentResponseType
    response_value: str | bool
    revision: int
    captured_at: str
    visibility: Literal["FAMILY_PRIVATE"]


class AssessmentSessionDtoModel(BaseModel):
    assessment_session_id: str
    family_id: str
    subject_person_id: str
    tool_ref: str
    tool_version: int
    status: Literal["IN_PROGRESS", "SUBMITTED", "EXITED"]
    started_at: str
    submitted_at: str | None
    row_version: int
    responses: list[AssessmentResponseDtoModel]


class Ui02NamedActionsModel(BaseModel):
    start: Literal["START_ASSESSMENT"]
    save_response: Literal["SAVE_ASSESSMENT_RESPONSE"]
    submit: Literal["SUBMIT_ASSESSMENT"]


class Ui02AssessmentProjectionResponse(BaseModel):
    projection_version: Literal["UI02_FAMILY_ASSESSMENT_V1"]
    tenant_id: str
    family_id: str
    availability: Ui02AssessmentAvailability
    subjects: list[Ui02AssessmentSubjectModel]
    tool: Ui02AssessmentToolModel | None
    sessions: list[AssessmentSessionDtoModel]
    named_actions: Ui02NamedActionsModel


class AssessmentMutationReceiptResponse(BaseModel):
    action: Literal["START_ASSESSMENT", "SAVE_ASSESSMENT_RESPONSE", "SUBMIT_ASSESSMENT"]
    replayed: bool
    session: AssessmentSessionDtoModel
    evidence_id: str | None = None
    boundary: Literal["FAMILY_PERSPECTIVE_NOT_SCORE_OR_DIAGNOSIS"]


# ---- UI-03 (growth hypothesis) --------------------------------------------


class Ui03SourceRefsModel(BaseModel):
    assessment_session_id: str
    assessment_response_id: str
    assessment_evidence_id: str
    tool_ref: str
    tool_version: int
    assessment_submitted_at: str | None = None


class Ui03PrincipalInterpretationModel(BaseModel):
    public_role: str
    codename: str
    opening: str
    reading: str
    boundary: str
    boundary_labels: list[str]


class Ui03GrowthScoreDimensionModel(BaseModel):
    dimension_ref: str
    label: str
    score: float
    peer_reference: float


class Ui03GrowthScorecardModel(BaseModel):
    generated_by: Literal["FAMILI_PRINCIPAL_FAMILY_EDUCATION_MODEL"]
    overall_score: float
    overall_band: str
    dimensions: list[Ui03GrowthScoreDimensionModel]
    core_issue_tags: list[str]
    recommendations: list[str]
    score_boundary: Literal["SUPPORT_ORIENTATION_SCORE_NOT_CHILD_DIAGNOSIS_OR_RANKING"]


class Ui03GrowthHypothesisModel(BaseModel):
    hypothesis_ref: str
    subject_person_id: str
    subject_display_name: str
    focus_ref: str
    need_type_ref: str
    need_type_version: int
    title: str
    statement: str
    required_capability_keys: list[str]
    source_refs: Ui03SourceRefsModel
    limitations: list[str]
    generator: Literal["DETERMINISTIC_CATALOG_POLICY_NOT_MODEL", "FAMILY_EDUCATION_ASSESSMENT_MODEL_V0_1"]
    model_draft_ref: str | None = None
    model_generator: Literal["FAMILY_EDUCATION_MODEL_RUNTIME_DETERMINISTIC", "FAMILY_EDUCATION_MODEL_RUNTIME_GATEWAY"] | None = None
    model_component_ref: str | None = None
    model_boundary_labels: list[str] | None = None
    need_refs: list[str] | None = None
    construct_refs: list[str] | None = None
    action_candidate_refs: list[str] | None = None
    fact_boundary: Literal["HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS"]
    principal: Ui03PrincipalInterpretationModel | None = None
    scorecard: Ui03GrowthScorecardModel | None = None


class Ui03NamedActionsModel(BaseModel):
    confirm: Literal["CONFIRM_GROWTH_HYPOTHESIS"]
    dismiss: Literal["DISMISS_GROWTH_HYPOTHESIS"]


class Ui03GrowthHypothesisProjectionResponse(BaseModel):
    projection_version: Literal["UI03_GROWTH_HYPOTHESIS_V1"]
    tenant_id: str
    family_id: str
    availability: Literal["READY", "NO_SUBMITTED_ASSESSMENT", "POLICY_BLOCKED"]
    hypothesis: Ui03GrowthHypothesisModel | None
    named_actions: Ui03NamedActionsModel
    ai_state: Literal["NOT_INVOKED", "MODEL_DRAFT_READY", "MODEL_GATEWAY_BLOCKED"]


class GrowthIntentModel(BaseModel):
    intent_id: str
    need_type: str
    status: Literal["OPEN"]
    required_capability_keys: list[str]
    evidence_refs: list[str]
    boundary: Literal["HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"]


class GrowthHypothesisDecisionReceiptResponse(BaseModel):
    action: Literal["CONFIRM_GROWTH_HYPOTHESIS", "DISMISS_GROWTH_HYPOTHESIS"]
    outcome: Literal["INTENT_CREATED", "NO_ACTION"]
    hypothesis_ref: str
    intent: GrowthIntentModel | None
    replayed: bool
