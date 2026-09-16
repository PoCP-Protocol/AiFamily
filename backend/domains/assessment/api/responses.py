"""HTTP response models for the Assessment API.

UI-02 mirrors its hand-written TypeScript contract. UI-03 follows the exact
runtime shape returned by the deterministic and governed Model Gateway
adapters so ``app.openapi()`` and response validation describe the same API.

UI-03 is closed and wired as a real ``response_model``. Its scorecard is a
discriminated union because the deterministic development adapter and the
governed Model Gateway deliberately return different provenance shapes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

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
    model_config = ConfigDict(extra="forbid")

    assessment_session_id: str
    assessment_response_id: str
    assessment_evidence_id: str
    tool_ref: str
    tool_version: int
    assessment_submitted_at: datetime | None


class Ui03DeterministicScorecardModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generator: Literal["FAMILY_EDUCATION_MODEL_RUNTIME_DETERMINISTIC"]


class Ui03ModelGatewayScorecardModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    generator: Literal["MODEL_GATEWAY"]
    agent_run_ref: str
    provider_ref: str
    model_ref: str
    model_version: str
    prompt_version: str
    schema_version: str
    context_snapshot_ref: str
    input_refs: list[str]
    draft_status: Literal["DRAFT"]
    human_task_ref: str | None
    review_status: Literal["REVIEW_REQUIRED", "DRAFT_ONLY"]


Ui03ScorecardModel = Annotated[
    Ui03DeterministicScorecardModel | Ui03ModelGatewayScorecardModel,
    Field(discriminator="generator"),
]


class Ui03GrowthHypothesisModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    generator: Literal[
        "DETERMINISTIC_CATALOG_POLICY_NOT_MODEL", "FAMILY_EDUCATION_ASSESSMENT_MODEL_V0_1"
    ]
    model_draft_ref: str
    model_generator: Literal["FAMILY_EDUCATION_MODEL_RUNTIME_DETERMINISTIC", "MODEL_GATEWAY"]
    model_component_ref: str
    model_boundary_labels: list[str]
    need_refs: list[str]
    construct_refs: list[str]
    action_candidate_refs: list[str]
    fact_boundary: Literal["HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS"]
    scorecard: Ui03ScorecardModel


class Ui03NamedActionsModel(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirm: Literal["CONFIRM_GROWTH_HYPOTHESIS"]
    dismiss: Literal["DISMISS_GROWTH_HYPOTHESIS"]


class Ui03GrowthHypothesisProjectionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    projection_version: Literal["UI03_GROWTH_HYPOTHESIS_V1"]
    tenant_id: str
    family_id: str
    availability: Literal["READY", "NO_SUBMITTED_ASSESSMENT", "POLICY_BLOCKED"]
    latest_assessment_session_id: str | None
    hypothesis: Ui03GrowthHypothesisModel | None
    named_actions: Ui03NamedActionsModel
    ai_state: Literal["NOT_INVOKED", "MODEL_DRAFT_READY", "MODEL_GATEWAY_BLOCKED"]


# ---- assessment result projection (read-only, no score/ranking) -----------


class AssessmentResultObservationModel(BaseModel):
    item_ref: str
    response_value: str | bool
    kind: Literal["ASSESSMENT_RESPONSE"]


class AssessmentResultHypothesisModel(BaseModel):
    hypothesis_ref: str
    text: str
    basis: str
    status: Literal["DRAFT"]


class AssessmentResultRecommendationModel(BaseModel):
    text: str
    source: str
    status: Literal["DRAFT"]


class AssessmentResultExplanationModel(BaseModel):
    headline: str
    summary: str
    observations: list[AssessmentResultObservationModel]
    hypothesis: str
    hypotheses: list[AssessmentResultHypothesisModel]
    mechanism: str | None
    recommendations: list[AssessmentResultRecommendationModel]


class AssessmentDimensionSnapshotModel(BaseModel):
    focus_ref: str
    title: str
    observation_status: Literal["OBSERVED", "NOT_YET_OBSERVED"]
    observed_item_refs: list[str]


class AssessmentKnowledgeGroundingModel(BaseModel):
    status: Literal["GROUNDED", "UNAVAILABLE"]
    construct_ref: str | None
    card_refs: list[str]
    primary_card_ref: str | None = None
    title: str | None = None
    evidence_grade: str | None
    core_claim: str | None
    mechanism: str | None
    boundary: str


class AssessmentPlanPhaseModel(BaseModel):
    phase_ref: str
    title: str
    duration_days: int
    prompt: str


class AssessmentGrowthPlanModel(BaseModel):
    plan_ref: str
    status: Literal["DRAFT"]
    goal: str
    phases: list[AssessmentPlanPhaseModel]
    source_refs: list[str]
    boundary: Literal["FAMILY_PLAN_DRAFT_REQUIRES_FAMILY_CONFIRMATION"]


class AssessmentResultAiModel(BaseModel):
    generator: str
    model: str | None
    model_version: str | None
    prompt_version: str | None
    context_snapshot_ref: str | None
    provenance_refs: list[str]
    model_gateway_status: Literal["NOT_INVOKED", "DRAFT", "BLOCKED"]
    may_mutate_business_state: Literal[False]


class AssessmentResultModel(BaseModel):
    result_id: str
    assessment_session_id: str
    subject: dict[str, str]
    focus_ref: str
    family_need_ref: str
    title: str
    explanation: AssessmentResultExplanationModel
    dimensions: list[AssessmentDimensionSnapshotModel]
    knowledge_grounding: AssessmentKnowledgeGroundingModel
    growth_plan: AssessmentGrowthPlanModel
    evidence_lineage: dict
    ai: AssessmentResultAiModel
    boundary: Literal["FAMILY_PERSPECTIVE_NOT_SCORE_OR_DIAGNOSIS"]
    draft_metadata: dict


class AssessmentResultProjectionResponse(BaseModel):
    """Schema hint for the family-scoped, read-only assessment result."""

    projection_version: Literal["ASSESSMENT_RESULT_V1"]
    tenant_id: str
    family_id: str
    status: Literal["READY", "NO_RESULT", "CONSENT_REQUIRED", "POLICY_BLOCKED"]
    result: AssessmentResultModel | None


class GrowthIntentModel(BaseModel):
    intent_id: str
    need_type: str
    status: Literal["OPEN"]
    required_capability_keys: list[str]
    evidence_refs: list[str]
    boundary: Literal["HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"]


class GrowthHypothesisDecisionReceiptResponse(BaseModel):
    action: Literal[
        "CONFIRM_GROWTH_HYPOTHESIS",
        "CALIBRATE_GROWTH_HYPOTHESIS",
        "DISMISS_GROWTH_HYPOTHESIS",
    ]
    outcome: Literal["INTENT_CREATED", "FEEDBACK_RECORDED", "NO_ACTION"]
    hypothesis_ref: str
    intent: GrowthIntentModel | None
    replayed: bool
    parent_note: str | None = None


class AssessmentHumanTaskConfirmationBindingResponse(BaseModel):
    """Server-owned values required by the existing CONFIRM command."""

    model_config = ConfigDict(extra="forbid")

    subject_person_id: str
    assessment_session_id: str
    hypothesis_ref: str
    scope_ref: str
    signal_version: int
    reviewed_draft_ref: str
    draft_version: int
    provenance_ref: str
    human_gate_receipt_ref: str


class AssessmentHumanTaskDecisionReceiptResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    task_id: str
    decision_id: str
    status: Literal["DECIDED"]
    outcome: Literal["ACCEPT", "REJECT"]
    reason: str | None
    decided_at: str
    binding: AssessmentHumanTaskConfirmationBindingResponse | None
