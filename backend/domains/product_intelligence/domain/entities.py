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

from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator

from .errors import ProductIntelligenceForbiddenError, ProductIntelligenceValidationError
from .value_objects import (
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
    def _all_or_none_ai_provenance(self) -> "_AiProvenanceFields":
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

    def mark_validated(self, *, actor_id: str, actor_type: ActorType, reason: str) -> "GrowthHypothesis":
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
        now = datetime.now(timezone.utc)
        return self.model_copy(update={
            "status": "VALIDATED",
            "updated_at": now,
            "version": self.version + 1,
            "validated_by": actor_id,
            "validated_at": now,
            "validation_reason": reason,
        })


class ContradictionModel(_CommonFields, _AiProvenanceFields):
    status: ContradictionStatus = "DRAFT"
    primary_factor_a: str
    primary_factor_b: str
    relationship: str
    description: str | None = None
    supporting_hypothesis_ids: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)


class GrowthStrategy(_CommonFields, _AiProvenanceFields):
    status: StrategyStatus = "DRAFT"
    problem_id: str
    hypothesis_ids: list[str] = Field(default_factory=list)
    contradiction_id: str | None = None
    statement: str
    applicable_segment_ref: str | None = None
    exclusion_conditions: list[str] = Field(default_factory=list)

    @field_validator("statement")
    @classmethod
    def _statement_non_empty(cls, value: str) -> str:
        return _require_non_empty(value, "statement")

    @model_validator(mode="after")
    def _requires_at_least_one_hypothesis(self) -> "GrowthStrategy":
        if not self.hypothesis_ids:
            raise ProductIntelligenceValidationError("growth_strategy_requires_at_least_one_hypothesis")
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


class ProductComponent(_CommonFields):
    status: GenericRecordStatus = "DRAFT"
    component_type: str
    title: str


class ProductPattern(_CommonFields):
    status: GenericRecordStatus = "DRAFT"
    title: str
    component_ids: list[str] = Field(default_factory=list)


class ProductDefinition(_CommonFields):
    status: GenericRecordStatus = "DRAFT"
    concept_id: str
    pattern_id: str | None = None
    component_ids: list[str] = Field(default_factory=list)


class ServiceBlueprintVersion(_CommonFields):
    status: GenericRecordStatus = "DRAFT"
    product_definition_id: str
    checksum: str | None = None
