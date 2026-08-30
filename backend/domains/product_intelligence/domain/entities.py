"""Product Intelligence domain entities.

No TS predecessor. Authored directly against the project owner's
instruction 01 (Override #6, `CURRENT_SPRINT.md`), hardened in PR-001R
(chief-architect review on PR #27). Every entity carries the required
common fields (`id/status/version/created_at/updated_at/created_by/
tenant_scope`) plus, for AI-generated types, the AI provenance fields
(`generated_by/model_ref/prompt_use_case_version/confidence`).

PR-001R hardening baked into this module (items 4/5/6 of the ruling):
- `_AiProvenanceFields` now enforces "all four fields or none" and
  `confidence` bounded to `[0, 1]` structurally (pydantic validators), not
  left as independently-optional fields a caller could partially fill.
- `GrowthHypothesis.mark_validated` takes `actor_type` (a domain value
  object, not a string-prefix convention), checks the legal source-state
  set, records `validated_by/validated_at/validation_reason`, and
  increments `version`.
- All timestamps are timezone-aware UTC (`datetime.now(timezone.utc)`), not
  naive `datetime.utcnow()`.

This module has no FastAPI/SQLAlchemy dependency — see `infrastructure/
sqlalchemy_models.py` for the persistence mapping, per the four-layer rule
in `architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` section 3.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .errors import ProductIntelligenceForbiddenError, ProductIntelligenceValidationError
from .value_objects import (
    CONTRADICTION_REVIEW_ALLOWED_FROM,
    HYPOTHESIS_VALIDATION_ALLOWED_FROM,
    ActorType,
    ContradictionStatus,
    GenericRecordStatus,
    HypothesisStatus,
    OpportunityStatus,
    ProductConceptStatus,
    StrategyStatus,
)


class _CommonFields(BaseModel):
    id: str
    version: int = 1
    created_at: datetime
    updated_at: datetime
    created_by: str
    tenant_scope: str

    @field_validator("version")
    @classmethod
    def _version_at_least_one(cls, value: int) -> int:
        if value < 1:
            raise ProductIntelligenceValidationError("version_must_be_at_least_one")
        return value

    @field_validator("id", "created_by", "tenant_scope")
    @classmethod
    def _non_empty_after_trim(cls, value: str, info) -> str:
        if not value or not value.strip():
            raise ProductIntelligenceValidationError(f"{info.field_name}_must_not_be_empty")
        return value


class _AiProvenanceFields(BaseModel):
    """Only present on records that can be AI-generated. `generated_by` is
    an actor ref (e.g. `"ai-use-case:growth.hypothesis.generate"`) — this PR
    does not wire a real AI Use Case Registry (Override #6 item 3/5), so
    these fields are populated by callers directly, not by any model
    adapter.

    PR-001R item 4: if any AI-provenance field is set, all four must be set
    — a record cannot be half-attributed to AI. `confidence` is bounded to
    `[0, 1]` unconditionally (a confidence outside that range is never
    meaningful, AI-generated or not).
    """

    generated_by: str | None = None
    model_ref: str | None = None
    prompt_use_case_version: str | None = None
    confidence: float | None = None

    @model_validator(mode="after")
    def _all_or_none_ai_provenance(self) -> _AiProvenanceFields:
        fields = (self.generated_by, self.model_ref, self.prompt_use_case_version, self.confidence)
        if any(f is not None for f in fields) and not all(f is not None for f in fields):
            raise ProductIntelligenceValidationError("ai_provenance_requires_all_fields_or_none")
        if self.confidence is not None and not (0.0 <= self.confidence <= 1.0):
            raise ProductIntelligenceValidationError("confidence_out_of_bounds")
        return self


def _require_non_empty(value: str, field_name: str) -> str:
    if not value or not value.strip():
        raise ProductIntelligenceValidationError(f"{field_name}_must_not_be_empty")
    return value


class Evidence(_CommonFields):
    status: GenericRecordStatus = "ACTIVE"
    description: str
    evidence_ref: str


class MarketSignal(_CommonFields):
    status: GenericRecordStatus = "ACTIVE"
    raw_text: str
    source_ref: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("raw_text")
    @classmethod
    def _raw_text_non_empty(cls, value: str) -> str:
        return _require_non_empty(value, "raw_text")


class SignalCluster(_CommonFields):
    status: GenericRecordStatus = "ACTIVE"
    label: str
    signal_ids: list[str]
    evidence_refs: list[str] = Field(default_factory=list)


class MarketTrend(_CommonFields):
    status: GenericRecordStatus = "ACTIVE"
    description: str
    cluster_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class CustomerSegment(_CommonFields):
    status: GenericRecordStatus = "ACTIVE"
    label: str
    definition: str


class CustomerInsight(_CommonFields, _AiProvenanceFields):
    status: GenericRecordStatus = "ACTIVE"
    statement: str
    signal_id: str | None = None
    segment_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("evidence_refs")
    @classmethod
    def _evidence_refs_are_non_empty(cls, value: list[str]) -> list[str]:
        if any(not ref or not ref.strip() for ref in value):
            raise ProductIntelligenceValidationError("evidence_refs_must_not_contain_empty_values")
        return value


class UnmetNeed(_CommonFields):
    status: GenericRecordStatus = "ACTIVE"
    statement: str
    insight_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)


class Opportunity(_CommonFields, _AiProvenanceFields):
    status: OpportunityStatus = "WATCH"
    insight_id: str
    statement: str
    evidence_refs: list[str] = Field(default_factory=list)


class GrowthProblem(_CommonFields):
    status: GenericRecordStatus = "ACTIVE"
    symptom: str
    opportunity_id: str | None = None
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator("symptom")
    @classmethod
    def _symptom_non_empty(cls, value: str) -> str:
        return _require_non_empty(value, "symptom")


class GrowthHypothesis(_CommonFields, _AiProvenanceFields):
    status: HypothesisStatus = "DRAFT"
    problem_id: str
    statement: str
    supporting_evidence_refs: list[str] = Field(default_factory=list)
    counter_evidence_refs: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    expected_observations: list[str] = Field(default_factory=list)
    falsification_conditions: list[str] = Field(default_factory=list)
    validated_by: str | None = None
    validated_at: datetime | None = None
    validation_reason: str | None = None

    @field_validator("statement")
    @classmethod
    def _statement_non_empty(cls, value: str) -> str:
        return _require_non_empty(value, "statement")

    def mark_validated(
        self, *, actor_id: str, actor_type: ActorType, reason: str
    ) -> GrowthHypothesis:
        """Only a `HUMAN` actor may validate a hypothesis — `actor_type` is
        a trusted domain value passed in by the application layer from
        `ActorContext` (see `application/context.py`), not a string
        convention on a client-supplied field. AI-generated hypotheses are
        created with `status="DRAFT"` and no code path in this domain may
        transition them to `VALIDATED` except this explicit method, called
        by an application-service handler acting on behalf of a human
        reviewer. Per Override #6 item 3 / project-owner instruction 03
        rule 4, hardened per chief-architect PR-001R ruling items 4/5:
        only `DRAFT`/`UNDER_REVIEW` may transition to `VALIDATED`
        (`REJECTED`/`RETIRED` are terminal for this transition), and the
        result records who/when/why plus a version bump.
        """
        if actor_type != "HUMAN":
            raise ProductIntelligenceForbiddenError("hypothesis_validation_requires_human_actor")
        if self.status not in HYPOTHESIS_VALIDATION_ALLOWED_FROM:
            raise ProductIntelligenceValidationError("hypothesis_validation_illegal_source_state")
        if not reason:
            raise ProductIntelligenceValidationError("hypothesis_validation_requires_reason")
        now = datetime.now(UTC)
        return self.model_copy(
            update={
                "status": "VALIDATED",
                "updated_at": now,
                "version": self.version + 1,
                "validated_by": actor_id,
                "validated_at": now,
                "validation_reason": reason,
            }
        )


class ContradictionModel(_CommonFields, _AiProvenanceFields):
    """PR-003 V1 (Contradiction & Strategy Intelligence): a contradiction is
    a claim that *two or more* hypotheses about the same `GrowthProblem` are
    in tension (e.g. `parent_control` vs `child_autonomy`) — it is not a
    single hypothesis restated. `supporting_hypothesis_ids` therefore
    requires at least two entries (validated below), matching the
    project-owner's own framing ("多 Hypothesis → Contradiction Analysis").

    `primary_rank` (nullable) lets a `GrowthProblem` have more than one
    candidate `ContradictionModel` while marking at most one as "the"
    primary contradiction currently driving strategy — set only via
    `mark_primary`/`clear_primary`, never at construction, so "is this the
    primary one" is always an explicit, auditable decision rather than a
    side effect of creation order.
    """

    status: ContradictionStatus = "DRAFT"
    problem_id: str
    primary_factor_a: str
    primary_factor_b: str
    relationship: str
    description: str | None = None
    supporting_hypothesis_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    primary_rank: int | None = None
    primary_marked_by: str | None = None
    primary_marked_at: datetime | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_reason: str | None = None

    @field_validator("supporting_hypothesis_ids")
    @classmethod
    def _requires_at_least_two_hypotheses(cls, value: list[str]) -> list[str]:
        if len(value) < 2:
            raise ProductIntelligenceValidationError(
                "contradiction_requires_at_least_two_supporting_hypotheses"
            )
        return value

    @field_validator("primary_factor_a", "primary_factor_b", "relationship")
    @classmethod
    def _factor_fields_non_empty(cls, value: str, info) -> str:
        return _require_non_empty(value, info.field_name)

    def submit_for_review(self) -> ContradictionModel:
        """`DRAFT -> UNDER_REVIEW`. No permission gate — same "anyone can ask
        for review, only a permissioned HUMAN can decide" split used by
        `zone_commands.submit_zone_review`."""
        if self.status != "DRAFT":
            raise ProductIntelligenceValidationError(
                "contradiction_submit_for_review_illegal_source_state"
            )
        return self.model_copy(
            update={
                "status": "UNDER_REVIEW",
                "updated_at": datetime.now(UTC),
                "version": self.version + 1,
            }
        )

    def decide_review(
        self, *, approved: bool, actor_id: str, actor_type: ActorType, reason: str
    ) -> ContradictionModel:
        """`DRAFT`/`UNDER_REVIEW` -> `APPROVED` or `REJECTED`. Same Permission
        Pattern split as `GrowthHypothesis.mark_validated`: this method only
        enforces `actor_type == HUMAN` and legal source-state — the
        `product_intelligence.contradiction.review` permission check itself
        is the application layer's job (see `application/contradiction_commands.py`).
        """
        if actor_type != "HUMAN":
            raise ProductIntelligenceForbiddenError("contradiction_review_requires_human_actor")
        if self.status not in CONTRADICTION_REVIEW_ALLOWED_FROM:
            raise ProductIntelligenceValidationError("contradiction_review_illegal_source_state")
        if not reason:
            raise ProductIntelligenceValidationError("contradiction_review_requires_reason")
        now = datetime.now(UTC)
        return self.model_copy(
            update={
                "status": "APPROVED" if approved else "REJECTED",
                "updated_at": now,
                "version": self.version + 1,
                "reviewed_by": actor_id,
                "reviewed_at": now,
                "review_reason": reason,
            }
        )

    def mark_primary(self, *, rank: int, actor_id: str) -> ContradictionModel:
        """Only an `APPROVED` contradiction may be marked primary — an
        unapproved (still-`DRAFT`/`UNDER_REVIEW`) contradiction has not
        cleared the Human Gate yet and cannot drive strategy. Records
        `primary_marked_by`/`primary_marked_at` — per repository R6 ("无审计
        不得改状态"), every business-state mutation must be attributable to
        an actor, and "which contradiction currently drives strategy" is a
        business-state mutation, not bookkeeping. `actor_id` here is not
        re-validated as HUMAN (that check already happened one layer up, in
        `application/contradiction_commands.py::mark_contradiction_primary`,
        before this method is ever called) — this parameter's job is
        auditability, not authorization.

        Enforcing "at most one primary per problem" is the application
        layer's job (it must compare across all of a problem's
        contradictions, which a single entity method cannot see).
        """
        if self.status != "APPROVED":
            raise ProductIntelligenceValidationError(
                "contradiction_mark_primary_requires_approved_status"
            )
        return self.model_copy(
            update={
                "primary_rank": rank,
                "primary_marked_by": actor_id,
                "primary_marked_at": datetime.now(UTC),
                "updated_at": datetime.now(UTC),
                "version": self.version + 1,
            }
        )


class ValueArchitecture(_CommonFields, _AiProvenanceFields):
    """PR-003 V1 — the project owner's four-layer value model (情绪价值→行动价值→
    成长价值→经济价值), made a first-class object a `GrowthStrategy` links to,
    per the instruction: "至少在 Domain/ADR 层把 ValueArchitecture 作为 Strategy
    的一个正式输入定义清楚".

    Deliberately thin for V1 (no sub-object per layer, no numeric scoring):
    the project owner's own framing is "先让家庭感觉更好,再让家庭变得更好,最后让
    家庭生活得更好" — a narrative structure, not a metric. Each layer is a
    short free-text field plus a `rationale`, and the whole object carries
    `evidence_refs` (non-empty, same "no evidence -> not reviewable" gate
    used everywhere else in this domain) so a value narrative is grounded in
    something a reviewer can check, not invented in the moment.
    """

    status: GenericRecordStatus = "DRAFT"
    problem_id: str
    emotional_current_state: str
    emotional_desired_state: str
    action_next_best_action: str
    growth_outcomes: list[str] = Field(default_factory=list)
    economic_outcomes: list[str] = Field(default_factory=list)
    rationale: str
    evidence_refs: list[str] = Field(default_factory=list)

    @field_validator(
        "emotional_current_state", "emotional_desired_state", "action_next_best_action", "rationale"
    )
    @classmethod
    def _narrative_fields_non_empty(cls, value: str, info) -> str:
        return _require_non_empty(value, info.field_name)

    @field_validator("evidence_refs")
    @classmethod
    def _evidence_refs_non_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ProductIntelligenceValidationError("value_architecture_requires_evidence_refs")
        return value


class GrowthStrategy(_CommonFields, _AiProvenanceFields):
    status: StrategyStatus = "DRAFT"
    problem_id: str
    hypothesis_ids: list[str] = Field(default_factory=list)
    contradiction_id: str | None = None
    value_architecture_id: str | None = None
    statement: str
    applicable_segment_ref: str | None = None
    exclusion_conditions: list[str] = Field(default_factory=list)

    @field_validator("statement")
    @classmethod
    def _statement_non_empty(cls, value: str) -> str:
        return _require_non_empty(value, "statement")

    @model_validator(mode="after")
    def _requires_at_least_one_hypothesis(self) -> GrowthStrategy:
        if not self.hypothesis_ids:
            raise ProductIntelligenceValidationError(
                "growth_strategy_requires_at_least_one_hypothesis"
            )
        return self


class ProductConcept(_CommonFields, _AiProvenanceFields):
    status: ProductConceptStatus = "DRAFT"
    strategy_id: str
    title: str
    description: str | None = None

    @field_validator("title")
    @classmethod
    def _title_non_empty(cls, value: str) -> str:
        return _require_non_empty(value, "title")


ProductZone = Literal["HOMOGENEOUS", "ADVANTAGE", "UNIQUE_CANDIDATE"]
GrowthProductKind = Literal["MICRO_CAMP", "SCALE_PLAN", "CUSTOM"]


class EducationProductSpec(BaseModel):
    """Family-education product configuration carried by a product definition.

    This is a design-time contract, not a family outcome or a child profile.
    It lets the Web product factory compose 21-day and 90-day products from
    versioned components while keeping execution facts in Journey/Service.
    """

    product_kind: GrowthProductKind
    duration_days: int
    zone: ProductZone
    primary_contradiction: str
    component_ids: list[str] = Field(default_factory=list)
    skill_ids: list[str] = Field(default_factory=list)
    success_metric_ids: list[str] = Field(default_factory=list)
    guardrail_ids: list[str] = Field(default_factory=list)
    stop_conditions: list[str] = Field(default_factory=list)
    pause_policy: str
    human_gate_policy: str

    @field_validator("primary_contradiction", "pause_policy", "human_gate_policy")
    @classmethod
    def _required_text_non_empty(cls, value: str, info) -> str:
        return _require_non_empty(value, info.field_name)

    @field_validator(
        "component_ids",
        "skill_ids",
        "success_metric_ids",
        "guardrail_ids",
        "stop_conditions",
    )
    @classmethod
    def _refs_must_be_non_empty(cls, values: list[str]) -> list[str]:
        if any(not value or not value.strip() for value in values):
            raise ProductIntelligenceValidationError("education_product_refs_must_not_be_empty")
        if len(set(values)) != len(values):
            raise ProductIntelligenceValidationError("education_product_refs_must_be_unique")
        return values

    @model_validator(mode="after")
    def _duration_matches_product_kind(self) -> EducationProductSpec:
        if self.duration_days <= 0 or self.duration_days > 180:
            raise ProductIntelligenceValidationError("education_product_duration_invalid")
        if self.product_kind == "MICRO_CAMP" and self.duration_days != 21:
            raise ProductIntelligenceValidationError("micro_camp_duration_must_be_21")
        if self.product_kind == "SCALE_PLAN" and self.duration_days != 90:
            raise ProductIntelligenceValidationError("scale_plan_duration_must_be_90")
        if not self.component_ids or not self.skill_ids or not self.success_metric_ids:
            raise ProductIntelligenceValidationError("education_product_design_refs_required")
        if not self.stop_conditions:
            raise ProductIntelligenceValidationError("education_product_stop_conditions_required")
        return self


class ProductComponent(_CommonFields):
    status: GenericRecordStatus = "DRAFT"
    component_type: str
    title: str
    zone: ProductZone = "HOMOGENEOUS"
    purpose: str | None = None
    input_refs: list[str] = Field(default_factory=list)
    output_refs: list[str] = Field(default_factory=list)
    required_skill_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    metric_ids: list[str] = Field(default_factory=list)
    owner_ref: str | None = None

    @field_validator("component_type", "title")
    @classmethod
    def _component_text_non_empty(cls, value: str, info) -> str:
        return _require_non_empty(value, info.field_name)

    @field_validator(
        "input_refs", "output_refs", "required_skill_ids", "evidence_refs", "metric_ids"
    )
    @classmethod
    def _component_refs_unique(cls, values: list[str]) -> list[str]:
        if any(not value or not value.strip() for value in values):
            raise ProductIntelligenceValidationError("product_component_refs_must_not_be_empty")
        if len(set(values)) != len(values):
            raise ProductIntelligenceValidationError("product_component_refs_must_be_unique")
        return values


class ProductPattern(_CommonFields):
    status: GenericRecordStatus = "DRAFT"
    title: str
    component_ids: list[str] = Field(default_factory=list)
    zone: ProductZone = "HOMOGENEOUS"
    duration_days: int | None = None
    primary_contradiction: str | None = None
    required_skill_ids: list[str] = Field(default_factory=list)


class ProductDefinition(_CommonFields, _AiProvenanceFields):
    status: GenericRecordStatus = "DRAFT"
    concept_id: str
    pattern_id: str | None = None
    component_ids: list[str] = Field(default_factory=list)
    product_kind: GrowthProductKind = "CUSTOM"
    duration_days: int | None = None
    zone: ProductZone = "HOMOGENEOUS"
    primary_contradiction: str | None = None
    demand_ref: str | None = None
    market_insight_refs: list[str] = Field(default_factory=list)
    education_spec: EducationProductSpec | None = None

    @model_validator(mode="after")
    def _education_spec_matches_definition(self) -> ProductDefinition:
        if self.education_spec is None:
            return self
        if not self.demand_ref or not self.demand_ref.strip():
            raise ProductIntelligenceValidationError("education_product_demand_ref_required")
        if not self.market_insight_refs:
            raise ProductIntelligenceValidationError("education_product_market_insight_required")
        if any(not value or not value.strip() for value in self.market_insight_refs):
            raise ProductIntelligenceValidationError(
                "education_product_market_insight_refs_must_not_be_empty"
            )
        if len(set(self.market_insight_refs)) != len(self.market_insight_refs):
            raise ProductIntelligenceValidationError(
                "education_product_market_insight_refs_must_be_unique"
            )
        if self.education_spec.product_kind != self.product_kind:
            raise ProductIntelligenceValidationError("education_product_kind_mismatch")
        if (
            self.duration_days is not None
            and self.education_spec.duration_days != self.duration_days
        ):
            raise ProductIntelligenceValidationError("education_product_duration_mismatch")
        if self.education_spec.zone != self.zone:
            raise ProductIntelligenceValidationError("education_product_zone_mismatch")
        if self.component_ids and set(self.education_spec.component_ids) - set(self.component_ids):
            raise ProductIntelligenceValidationError("education_product_components_mismatch")
        return self


class ServiceBlueprintVersion(_CommonFields):
    status: GenericRecordStatus = "DRAFT"
    product_definition_id: str
    checksum: str | None = None
