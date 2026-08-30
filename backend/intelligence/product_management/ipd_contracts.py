"""Small, immutable IPD product-management contracts.

These objects are governance/application records, not business-domain facts.
They make a product package, its L4 requirements, and stage-gate evidence
explicit before implementation work is accepted into a release baseline.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum


class IPDContractError(ValueError):
    """Raised when a product package violates the IPD baseline."""


class IPDStage(StrEnum):
    MARKET = "MM"
    CONCEPT = "CDCP"
    PLAN = "PDCP"
    DEVELOP = "ADCP"
    QUALIFY = "LDCP"
    LAUNCH = "GA"
    LIFECYCLE = "LIFECYCLE"


class GateDecision(StrEnum):
    GO = "GO"
    NO_GO = "NO_GO"
    CONDITIONAL = "CONDITIONAL"


class ArtifactStatus(StrEnum):
    """Status shared by immutable PDM/PLM design records."""

    DRAFT = "DRAFT"
    REVIEWED = "REVIEWED"
    PILOT = "PILOT"
    QUALIFIED = "QUALIFIED"
    RELEASED = "RELEASED"
    PAUSED = "PAUSED"
    RETIRED = "RETIRED"


class ProductZone(StrEnum):
    """Three-zone strategy labels used as investment hypotheses."""

    HOMOGENEOUS = "HOMOGENEOUS"
    ADVANTAGE = "ADVANTAGE"
    EXCLUSIVE_CANDIDATE = "EXCLUSIVE_CANDIDATE"


class LifecycleRecommendation(StrEnum):
    """PLM outcome proposed by a pilot; a human must approve it."""

    SCALE = "SCALE"
    REVISE = "REVISE"
    KILL = "KILL"


class PilotStatus(StrEnum):
    PLANNED = "PLANNED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    PAUSED = "PAUSED"
    KILLED = "KILLED"
    ROLLED_BACK = "ROLLED_BACK"


# A ProductPackage's status transitions are the execution-facing slice of the
# IPD stage model.  Keeping this mapping explicit prevents a gate record from
# claiming the same MARKET→LIFECYCLE transition for every pilot/qualification/
# release decision.
_PACKAGE_STATUS_STAGES: dict[ArtifactStatus, IPDStage] = {
    ArtifactStatus.DRAFT: IPDStage.PLAN,
    ArtifactStatus.PILOT: IPDStage.DEVELOP,
    ArtifactStatus.QUALIFIED: IPDStage.QUALIFY,
    ArtifactStatus.RELEASED: IPDStage.LAUNCH,
}


def _coerce_enum(value: object, enum_type: type[StrEnum], code: str) -> StrEnum:
    try:
        return value if isinstance(value, enum_type) else enum_type(value)
    except (TypeError, ValueError) as error:
        raise IPDContractError(code) from error


def _require_refs(values: tuple[str, ...], code: str) -> None:
    if not values or any(not value or not value.strip() for value in values):
        raise IPDContractError(code)
    if len(set(values)) != len(values):
        raise IPDContractError(f"{code}_MUST_BE_UNIQUE")


def _require_human(actor: str, code: str = "HUMAN_DECIDER_REQUIRED") -> None:
    candidate = actor.strip().lower()
    if not candidate or candidate.startswith(("ai:", "agent:", "model:", "system:")):
        raise IPDContractError(code)


def _require_ai_draft(status: ArtifactStatus, generated_by: str | None) -> None:
    if (
        generated_by
        and generated_by.strip().lower().startswith(("ai:", "agent:", "model:", "system:"))
        and status is not ArtifactStatus.DRAFT
    ):
        raise IPDContractError("AI_ARTIFACT_MUST_REMAIN_DRAFT")


_REQUIREMENT_ID = re.compile(r"IPD-P[1-6]-[A-Z0-9-]+")


@dataclass(frozen=True, slots=True)
class ProductRequirement:
    """One L4 operation tied to an IPD product package and acceptance tests."""

    requirement_id: str
    charter_id: str
    capability: str
    feature: str
    operation: str
    user_story: str
    acceptance_refs: tuple[str, ...]
    domain_owner: str
    data_owner: str
    channel_refs: tuple[str, ...] = ()
    priority: int = 0

    def __post_init__(self) -> None:
        required = (
            self.requirement_id,
            self.charter_id,
            self.capability,
            self.feature,
            self.operation,
            self.user_story,
            self.domain_owner,
            self.data_owner,
        )
        if not all(required):
            raise IPDContractError("PRODUCT_REQUIREMENT_FIELDS_REQUIRED")
        if not _REQUIREMENT_ID.fullmatch(self.requirement_id):
            raise IPDContractError("PRODUCT_REQUIREMENT_ID_UNSUPPORTED")
        if not self.acceptance_refs:
            raise IPDContractError("PRODUCT_REQUIREMENT_ACCEPTANCE_REQUIRED")
        if any(not value for value in (*self.acceptance_refs, *self.channel_refs)):
            raise IPDContractError("PRODUCT_REQUIREMENT_REFS_MUST_NOT_BE_EMPTY")
        if self.priority < 0:
            raise IPDContractError("PRODUCT_REQUIREMENT_PRIORITY_INVALID")


@dataclass(frozen=True, slots=True)
class GateEvidence:
    """Evidence attached to a stage decision; paths are immutable references."""

    evidence_id: str
    kind: str
    reference: str
    summary: str

    def __post_init__(self) -> None:
        if not all((self.evidence_id, self.kind, self.reference, self.summary)):
            raise IPDContractError("GATE_EVIDENCE_FIELDS_REQUIRED")


@dataclass(frozen=True, slots=True)
class GateRecord:
    from_stage: IPDStage
    to_stage: IPDStage
    decision: GateDecision
    decided_by: str
    evidence: tuple[GateEvidence, ...]
    decided_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def __post_init__(self) -> None:
        if not self.decided_by or not self.evidence:
            raise IPDContractError("GATE_DECIDER_AND_EVIDENCE_REQUIRED")
        if not isinstance(self.from_stage, IPDStage) or not isinstance(self.to_stage, IPDStage):
            raise IPDContractError("GATE_STAGE_UNSUPPORTED")
        if not isinstance(self.decision, GateDecision):
            raise IPDContractError("GATE_DECISION_UNSUPPORTED")


@dataclass(frozen=True, slots=True)
class ProductCharter:
    """Versioned product package charter and its controlled stage progression."""

    charter_id: str
    product_id: str
    product_line: str
    version: str
    target_customer: str
    problem_statement: str
    value_hypothesis: str
    owner: str
    scope_in: tuple[str, ...]
    scope_out: tuple[str, ...]
    success_metrics: tuple[str, ...]
    requirements: tuple[ProductRequirement, ...]
    current_stage: IPDStage = IPDStage.MARKET
    gate_history: tuple[GateRecord, ...] = ()

    def __post_init__(self) -> None:
        required = (
            self.charter_id,
            self.product_id,
            self.product_line,
            self.version,
            self.target_customer,
            self.problem_statement,
            self.value_hypothesis,
            self.owner,
        )
        if not all(required):
            raise IPDContractError("PRODUCT_CHARTER_FIELDS_REQUIRED")
        if not self.scope_in or not self.scope_out or not self.success_metrics:
            raise IPDContractError("PRODUCT_CHARTER_SCOPE_AND_METRICS_REQUIRED")
        if not self.requirements:
            raise IPDContractError("PRODUCT_CHARTER_REQUIREMENTS_REQUIRED")
        requirement_ids = {requirement.requirement_id for requirement in self.requirements}
        if len(requirement_ids) != len(self.requirements):
            raise IPDContractError("PRODUCT_CHARTER_REQUIREMENTS_MUST_BE_UNIQUE")
        if any(requirement.charter_id != self.charter_id for requirement in self.requirements):
            raise IPDContractError("PRODUCT_REQUIREMENT_CHARTER_MISMATCH")
        if not isinstance(self.current_stage, IPDStage):
            raise IPDContractError("PRODUCT_CHARTER_STAGE_UNSUPPORTED")

    def advance(
        self,
        target_stage: IPDStage,
        *,
        decision: GateDecision,
        decided_by: str,
        evidence: tuple[GateEvidence, ...],
    ) -> ProductCharter:
        """Advance exactly one stage with an auditable decision."""

        if not isinstance(target_stage, IPDStage) or not isinstance(decision, GateDecision):
            raise IPDContractError("GATE_STAGE_OR_DECISION_UNSUPPORTED")
        stages = tuple(IPDStage)
        current_index = stages.index(self.current_stage)
        if current_index + 1 >= len(stages) or target_stage is not stages[current_index + 1]:
            raise IPDContractError("IPD_STAGE_TRANSITION_MUST_BE_SEQUENTIAL")
        if decision is not GateDecision.GO:
            raise IPDContractError("IPD_STAGE_ADVANCE_REQUIRES_GO")
        record = GateRecord(
            from_stage=self.current_stage,
            to_stage=target_stage,
            decision=decision,
            decided_by=decided_by,
            evidence=evidence,
        )
        return replace(
            self,
            current_stage=target_stage,
            gate_history=(*self.gate_history, record),
        )


@dataclass(frozen=True, slots=True)
class ComponentDefinition:
    """Versioned, reusable PDM component; never a family/business fact."""

    component_id: str
    version: str
    owner: str
    purpose: str
    target_scenario: str
    zone: ProductZone | str
    duration_days: int = 0
    inputs: tuple[str, ...] = ()
    outputs: tuple[str, ...] = ()
    preconditions: tuple[str, ...] = ()
    contraindications: tuple[str, ...] = ()
    roles: tuple[str, ...] = ()
    actions: tuple[str, ...] = ()
    evidence_refs: tuple[str, ...] = ()
    knowledge_refs: tuple[str, ...] = ()
    service_capacity: str | None = None
    sla: str | None = None
    unit_cost_assumption: str | None = None
    metrics: tuple[str, ...] = ()
    guardrails: tuple[str, ...] = ()
    pause_rule: str = ""
    rollback_rule: str = ""
    required_skills: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    human_gate_policy: str = ""
    status: ArtifactStatus | str = ArtifactStatus.DRAFT
    generated_by: str | None = None

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.component_id,
                self.version,
                self.owner,
                self.purpose,
                self.target_scenario,
            )
        ):
            raise IPDContractError("COMPONENT_FIELDS_REQUIRED")
        object.__setattr__(
            self,
            "zone",
            _coerce_enum(self.zone, ProductZone, "COMPONENT_ZONE_UNSUPPORTED"),
        )
        status = _coerce_enum(self.status, ArtifactStatus, "COMPONENT_STATUS_UNSUPPORTED")
        object.__setattr__(self, "status", status)
        if self.duration_days < 0:
            raise IPDContractError("COMPONENT_DURATION_INVALID")
        _require_refs(self.evidence_refs, "COMPONENT_EVIDENCE_REQUIRED")
        if self.rollback_rule == "":
            raise IPDContractError("COMPONENT_ROLLBACK_RULE_REQUIRED")
        _require_ai_draft(status, self.generated_by)

    def review(self, *, decided_by: str, evidence: tuple[GateEvidence, ...]) -> ComponentDefinition:
        _require_human(decided_by)
        if self.status is not ArtifactStatus.DRAFT:
            raise IPDContractError("COMPONENT_REVIEW_REQUIRES_DRAFT")
        if not evidence:
            raise IPDContractError("COMPONENT_REVIEW_EVIDENCE_REQUIRED")
        return replace(self, status=ArtifactStatus.REVIEWED)

    def publish(
        self,
        *,
        decided_by: str,
        evidence: tuple[GateEvidence, ...],
    ) -> ComponentDefinition:
        _require_human(decided_by)
        if self.status is not ArtifactStatus.REVIEWED:
            raise IPDContractError("COMPONENT_PUBLISH_REQUIRES_REVIEW")
        if not evidence:
            raise IPDContractError("COMPONENT_PUBLISH_EVIDENCE_REQUIRED")
        return replace(self, status=ArtifactStatus.RELEASED)


@dataclass(frozen=True, slots=True)
class SkillDefinition:
    """Versioned AI/human skill with explicit tools and handoff policy."""

    skill_id: str
    version: str
    owner: str
    purpose: str
    input_schema: str
    output_schema: str
    required_context: tuple[str, ...] = ()
    knowledge_refs: tuple[str, ...] = ()
    allowed_tools: tuple[str, ...] = ()
    forbidden_tools: tuple[str, ...] = ()
    quality_eval_refs: tuple[str, ...] = ()
    safety_policy: str = ""
    human_handoff: str = ""
    evidence_refs: tuple[str, ...] = ()
    status: ArtifactStatus | str = ArtifactStatus.DRAFT
    generated_by: str | None = None

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.skill_id,
                self.version,
                self.owner,
                self.purpose,
                self.input_schema,
                self.output_schema,
            )
        ):
            raise IPDContractError("SKILL_FIELDS_REQUIRED")
        status = _coerce_enum(self.status, ArtifactStatus, "SKILL_STATUS_UNSUPPORTED")
        object.__setattr__(self, "status", status)
        if set(self.allowed_tools) & set(self.forbidden_tools):
            raise IPDContractError("SKILL_TOOL_ALLOW_DENY_OVERLAP")
        _require_refs(self.quality_eval_refs, "SKILL_QUALITY_EVAL_REQUIRED")
        _require_refs(self.evidence_refs, "SKILL_EVIDENCE_REQUIRED")
        if not self.safety_policy or not self.human_handoff:
            raise IPDContractError("SKILL_SAFETY_AND_HANDOFF_REQUIRED")
        _require_ai_draft(status, self.generated_by)

    def review(self, *, decided_by: str, evidence: tuple[GateEvidence, ...]) -> SkillDefinition:
        _require_human(decided_by)
        if self.status is not ArtifactStatus.DRAFT:
            raise IPDContractError("SKILL_REVIEW_REQUIRES_DRAFT")
        if not evidence:
            raise IPDContractError("SKILL_REVIEW_EVIDENCE_REQUIRED")
        return replace(self, status=ArtifactStatus.REVIEWED)

    def publish(
        self,
        *,
        decided_by: str,
        evidence: tuple[GateEvidence, ...],
    ) -> SkillDefinition:
        _require_human(decided_by)
        if self.status is not ArtifactStatus.REVIEWED:
            raise IPDContractError("SKILL_PUBLISH_REQUIRES_REVIEW")
        if not evidence:
            raise IPDContractError("SKILL_PUBLISH_EVIDENCE_REQUIRED")
        return replace(self, status=ArtifactStatus.RELEASED)


@dataclass(frozen=True, slots=True)
class ProductPackage:
    """Immutable 21/90-day product package assembled from catalog versions."""

    package_id: str
    version: str
    charter_id: str
    concept_id: str
    requirement_baseline_id: str
    target_scenario: str
    duration_days: int
    zone: ProductZone | str
    component_refs: tuple[str, ...]
    skill_refs: tuple[str, ...]
    success_metrics: tuple[str, ...]
    guardrails: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    delivery_capacity: str
    unit_cost_assumption: str
    rollback_rule: str
    blueprint_version_id: str | None = None
    verification_plan_id: str | None = None
    pilot_policy_id: str | None = None
    release_baseline_id: str | None = None
    evidence_refs: tuple[str, ...] = ()
    status: ArtifactStatus | str = ArtifactStatus.DRAFT
    generated_by: str | None = None
    gate_history: tuple[GateRecord, ...] = ()

    def __post_init__(self) -> None:
        if not all(
            value.strip()
            for value in (
                self.package_id,
                self.version,
                self.charter_id,
                self.concept_id,
                self.requirement_baseline_id,
                self.target_scenario,
                self.delivery_capacity,
                self.unit_cost_assumption,
                self.rollback_rule,
            )
        ):
            raise IPDContractError("PRODUCT_PACKAGE_FIELDS_REQUIRED")
        if self.duration_days not in {21, 90}:
            raise IPDContractError("PRODUCT_PACKAGE_DURATION_MUST_BE_21_OR_90")
        object.__setattr__(
            self,
            "zone",
            _coerce_enum(self.zone, ProductZone, "PRODUCT_PACKAGE_ZONE_UNSUPPORTED"),
        )
        status = _coerce_enum(self.status, ArtifactStatus, "PRODUCT_PACKAGE_STATUS_UNSUPPORTED")
        object.__setattr__(self, "status", status)
        _require_refs(self.component_refs, "PRODUCT_PACKAGE_COMPONENTS_REQUIRED")
        _require_refs(self.skill_refs, "PRODUCT_PACKAGE_SKILLS_REQUIRED")
        _require_refs(self.success_metrics, "PRODUCT_PACKAGE_METRICS_REQUIRED")
        _require_refs(self.guardrails, "PRODUCT_PACKAGE_GUARDRAILS_REQUIRED")
        _require_refs(self.stop_conditions, "PRODUCT_PACKAGE_STOP_CONDITIONS_REQUIRED")
        _require_refs(self.evidence_refs, "PRODUCT_PACKAGE_EVIDENCE_REQUIRED")
        _require_ai_draft(status, self.generated_by)

    def advance(
        self,
        target_status: ArtifactStatus | str,
        *,
        decision: GateDecision,
        decided_by: str,
        evidence: tuple[GateEvidence, ...],
    ) -> ProductPackage:
        """Advance only DRAFT→PILOT→QUALIFIED→RELEASED with human GO."""

        target = _coerce_enum(target_status, ArtifactStatus, "PRODUCT_PACKAGE_STATUS_UNSUPPORTED")
        if decision is not GateDecision.GO:
            raise IPDContractError("PRODUCT_PACKAGE_ADVANCE_REQUIRES_GO")
        _require_human(decided_by)
        if not evidence:
            raise IPDContractError("PRODUCT_PACKAGE_ADVANCE_EVIDENCE_REQUIRED")
        order = (
            ArtifactStatus.DRAFT,
            ArtifactStatus.PILOT,
            ArtifactStatus.QUALIFIED,
            ArtifactStatus.RELEASED,
        )
        if self.status not in order or target not in order:
            raise IPDContractError("PRODUCT_PACKAGE_STATUS_NOT_ADVANCEABLE")
        if order.index(target) != order.index(self.status) + 1:
            raise IPDContractError("PRODUCT_PACKAGE_STATUS_MUST_BE_SEQUENTIAL")
        if target is ArtifactStatus.RELEASED and not self.release_baseline_id:
            raise IPDContractError("PRODUCT_PACKAGE_RELEASE_BASELINE_REQUIRED")
        record = GateRecord(
            from_stage=_PACKAGE_STATUS_STAGES[self.status],
            to_stage=_PACKAGE_STATUS_STAGES[target],
            decision=decision,
            decided_by=decided_by,
            evidence=evidence,
        )
        return replace(self, status=target, gate_history=(*self.gate_history, record))


@dataclass(frozen=True, slots=True)
class PilotRun:
    """Controlled pilot that yields a human-reviewed PLM recommendation."""

    pilot_id: str
    package_id: str
    package_version: str
    cohort_ref: str
    max_participants: int
    metrics: tuple[str, ...]
    guardrails: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    rollback_rule: str
    evidence_refs: tuple[str, ...] = ()
    status: PilotStatus | str = PilotStatus.PLANNED
    lifecycle_recommendation: LifecycleRecommendation | str | None = None
    rollback_target_ref: str | None = None
    decided_by: str | None = None
    decision_evidence: tuple[GateEvidence, ...] = ()

    def __post_init__(self) -> None:
        if not all(
            (
                self.pilot_id,
                self.package_id,
                self.package_version,
                self.cohort_ref,
                self.rollback_rule,
            )
        ):
            raise IPDContractError("PILOT_FIELDS_REQUIRED")
        if self.max_participants <= 0:
            raise IPDContractError("PILOT_PARTICIPANT_LIMIT_INVALID")
        _require_refs(self.metrics, "PILOT_METRICS_REQUIRED")
        _require_refs(self.guardrails, "PILOT_GUARDRAILS_REQUIRED")
        _require_refs(self.stop_conditions, "PILOT_STOP_CONDITIONS_REQUIRED")
        _require_refs(self.evidence_refs, "PILOT_EVIDENCE_REQUIRED")
        status = _coerce_enum(self.status, PilotStatus, "PILOT_STATUS_UNSUPPORTED")
        object.__setattr__(self, "status", status)
        if self.lifecycle_recommendation is not None:
            object.__setattr__(
                self,
                "lifecycle_recommendation",
                _coerce_enum(
                    self.lifecycle_recommendation,
                    LifecycleRecommendation,
                    "PILOT_LIFECYCLE_DECISION_UNSUPPORTED",
                ),
            )

    def start(self, *, decided_by: str, evidence: tuple[GateEvidence, ...]) -> PilotRun:
        _require_human(decided_by)
        if self.status is not PilotStatus.PLANNED:
            raise IPDContractError("PILOT_START_REQUIRES_PLANNED")
        if not evidence:
            raise IPDContractError("PILOT_START_EVIDENCE_REQUIRED")
        return replace(self, status=PilotStatus.RUNNING)

    def complete(self, *, evidence: tuple[GateEvidence, ...]) -> PilotRun:
        if self.status is not PilotStatus.RUNNING:
            raise IPDContractError("PILOT_COMPLETE_REQUIRES_RUNNING")
        if not evidence:
            raise IPDContractError("PILOT_COMPLETE_EVIDENCE_REQUIRED")
        evidence_refs = tuple(
            dict.fromkeys((*self.evidence_refs, *(item.evidence_id for item in evidence)))
        )
        return replace(self, status=PilotStatus.COMPLETED, evidence_refs=evidence_refs)

    def decide(
        self,
        recommendation: LifecycleRecommendation | str,
        *,
        decided_by: str,
        evidence: tuple[GateEvidence, ...],
    ) -> PilotRun:
        _require_human(decided_by)
        if self.status is not PilotStatus.COMPLETED:
            raise IPDContractError("PILOT_DECISION_REQUIRES_COMPLETED")
        if not evidence:
            raise IPDContractError("PILOT_DECISION_EVIDENCE_REQUIRED")
        decision = _coerce_enum(
            recommendation,
            LifecycleRecommendation,
            "PILOT_LIFECYCLE_DECISION_UNSUPPORTED",
        )
        next_status = (
            PilotStatus.KILLED
            if decision is LifecycleRecommendation.KILL
            else PilotStatus.COMPLETED
        )
        evidence_refs = tuple(
            dict.fromkeys((*self.evidence_refs, *(item.evidence_id for item in evidence)))
        )
        return replace(
            self,
            status=next_status,
            lifecycle_recommendation=decision,
            decided_by=decided_by,
            decision_evidence=evidence,
            evidence_refs=evidence_refs,
        )

    def rollback(
        self,
        *,
        target_ref: str,
        decided_by: str,
        evidence: tuple[GateEvidence, ...],
    ) -> PilotRun:
        _require_human(decided_by)
        if self.status not in {PilotStatus.RUNNING, PilotStatus.COMPLETED, PilotStatus.PAUSED}:
            raise IPDContractError("PILOT_ROLLBACK_STATUS_INVALID")
        if not target_ref or not evidence:
            raise IPDContractError("PILOT_ROLLBACK_EVIDENCE_REQUIRED")
        return replace(
            self,
            status=PilotStatus.ROLLED_BACK,
            rollback_target_ref=target_ref,
            decided_by=decided_by,
            decision_evidence=evidence,
        )


@dataclass(frozen=True, slots=True)
class ReleaseBaseline:
    """Frozen, human-approved release manifest with pause/rollback/retire."""

    release_id: str
    package_id: str
    package_version: str
    component_refs: tuple[str, ...]
    skill_refs: tuple[str, ...]
    blueprint_version_id: str
    model_refs: tuple[str, ...]
    prompt_refs: tuple[str, ...]
    schema_refs: tuple[str, ...]
    knowledge_refs: tuple[str, ...]
    migration_refs: tuple[str, ...]
    runbook_ref: str
    rollback_ref: str
    environment: str
    evidence_refs: tuple[str, ...]
    status: ArtifactStatus | str = ArtifactStatus.DRAFT
    generated_by: str | None = None
    approved_by: str | None = None
    human_gate_ref: str | None = None
    rollback_target_ref: str | None = None

    def __post_init__(self) -> None:
        required = (
            self.release_id,
            self.package_id,
            self.package_version,
            self.blueprint_version_id,
            self.runbook_ref,
            self.rollback_ref,
            self.environment,
        )
        if not all(value and value.strip() for value in required):
            raise IPDContractError("RELEASE_BASELINE_FIELDS_REQUIRED")
        for refs, code in (
            (self.component_refs, "RELEASE_BASELINE_COMPONENTS_REQUIRED"),
            (self.skill_refs, "RELEASE_BASELINE_SKILLS_REQUIRED"),
            (self.model_refs, "RELEASE_BASELINE_MODELS_REQUIRED"),
            (self.prompt_refs, "RELEASE_BASELINE_PROMPTS_REQUIRED"),
            (self.schema_refs, "RELEASE_BASELINE_SCHEMAS_REQUIRED"),
            (self.knowledge_refs, "RELEASE_BASELINE_KNOWLEDGE_REQUIRED"),
            (self.migration_refs, "RELEASE_BASELINE_MIGRATIONS_REQUIRED"),
            (self.evidence_refs, "RELEASE_BASELINE_EVIDENCE_REQUIRED"),
        ):
            _require_refs(refs, code)
        status = _coerce_enum(self.status, ArtifactStatus, "RELEASE_BASELINE_STATUS_UNSUPPORTED")
        object.__setattr__(self, "status", status)
        _require_ai_draft(status, self.generated_by)
        if (
            status in {ArtifactStatus.RELEASED, ArtifactStatus.PAUSED, ArtifactStatus.RETIRED}
            and not self.approved_by
        ):
            raise IPDContractError("RELEASE_BASELINE_HUMAN_APPROVAL_REQUIRED")

    def approve(
        self,
        *,
        decided_by: str,
        human_gate_ref: str,
        evidence: tuple[GateEvidence, ...],
    ) -> ReleaseBaseline:
        _require_human(decided_by)
        if self.status is not ArtifactStatus.DRAFT:
            raise IPDContractError("RELEASE_APPROVAL_REQUIRES_DRAFT")
        if not human_gate_ref or not evidence:
            raise IPDContractError("RELEASE_APPROVAL_EVIDENCE_REQUIRED")
        return replace(
            self,
            status=ArtifactStatus.REVIEWED,
            approved_by=decided_by,
            human_gate_ref=human_gate_ref,
        )

    def release(self, *, decided_by: str, evidence: tuple[GateEvidence, ...]) -> ReleaseBaseline:
        _require_human(decided_by)
        if self.status is not ArtifactStatus.REVIEWED:
            raise IPDContractError("RELEASE_REQUIRES_APPROVAL")
        if not evidence:
            raise IPDContractError("RELEASE_EVIDENCE_REQUIRED")
        return replace(self, status=ArtifactStatus.RELEASED, approved_by=decided_by)

    def pause(self, *, decided_by: str, evidence: tuple[GateEvidence, ...]) -> ReleaseBaseline:
        _require_human(decided_by)
        if self.status is not ArtifactStatus.RELEASED or not evidence:
            raise IPDContractError("RELEASE_PAUSE_INVALID")
        return replace(self, status=ArtifactStatus.PAUSED, approved_by=decided_by)

    def rollback(
        self,
        *,
        target_ref: str,
        decided_by: str,
        evidence: tuple[GateEvidence, ...],
    ) -> ReleaseBaseline:
        _require_human(decided_by)
        if self.status not in {ArtifactStatus.RELEASED, ArtifactStatus.PAUSED}:
            raise IPDContractError("RELEASE_ROLLBACK_STATUS_INVALID")
        if not target_ref or not evidence:
            raise IPDContractError("RELEASE_ROLLBACK_EVIDENCE_REQUIRED")
        return replace(
            self,
            status=ArtifactStatus.PAUSED,
            rollback_target_ref=target_ref,
            approved_by=decided_by,
        )

    def retire(self, *, decided_by: str, evidence: tuple[GateEvidence, ...]) -> ReleaseBaseline:
        _require_human(decided_by)
        if self.status not in {ArtifactStatus.RELEASED, ArtifactStatus.PAUSED}:
            raise IPDContractError("RELEASE_RETIRE_STATUS_INVALID")
        if not evidence:
            raise IPDContractError("RELEASE_RETIRE_EVIDENCE_REQUIRED")
        return replace(self, status=ArtifactStatus.RETIRED, approved_by=decided_by)


# Compatibility names used by product/catalog clients.
Component = ComponentDefinition
Skill = SkillDefinition
Pilot = PilotRun


__all__ = [
    "ArtifactStatus",
    "Component",
    "ComponentDefinition",
    "GateDecision",
    "GateEvidence",
    "GateRecord",
    "IPDContractError",
    "IPDStage",
    "LifecycleRecommendation",
    "Pilot",
    "PilotRun",
    "PilotStatus",
    "ProductPackage",
    "ProductCharter",
    "ProductRequirement",
    "ProductZone",
    "ReleaseBaseline",
    "Skill",
    "SkillDefinition",
]
