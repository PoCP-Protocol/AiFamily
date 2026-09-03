"""Family Need aggregates.

The aggregate boundaries follow the N0-N8 need loop.  Product, service and
solution records are references only; their lifecycle is owned by their
respective domains.  All transitions return a new immutable value and are
therefore safe to replay behind an application-level idempotency port.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from uuid import uuid4

from .errors import FamilyNeedConflictError, FamilyNeedValidationError
from .policies import (
    assert_commercial_gate,
    assert_context,
    assert_emotional_gate_transition,
    assert_evidence_scope,
    assert_fact_writer,
    assert_family_outcome_confirmer,
    assert_manage_actor,
    assert_solution_shape,
    assert_subjects_in_family,
    assert_transition,
    assert_version,
    assert_we_are_family_guards,
    derive_intervention_tier,
)
from .value_objects import (
    AcceptanceCriterion,
    ActorType,
    DataClass,
    EmotionalGate,
    EvidenceRef,
    FamilyOutcomeDecision,
    InterventionTier,
    NeedCategory,
    NeedComplexity,
    NeedConstraint,
    NeedContext,
    NeedSignalSource,
    NeedSignalStatus,
    NeedStatus,
    NeedUrgency,
    ResourceGap,
    RiskLevel,
    SolutionComponentRef,
    SolutionDraftStatus,
    SupplyShape,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class NeedSignal:
    """N0: a family-originated expression, not an AI interpretation."""

    signal_id: str
    context: NeedContext
    source: NeedSignalSource
    raw_text: str
    captured_at: datetime
    status: NeedSignalStatus = NeedSignalStatus.ACTIVE
    expires_at: datetime | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        assert_context(self.context)
        assert_fact_writer(self.context.actor_type)
        assert_evidence_scope(self.context, self.evidence_refs)
        if not self.raw_text.strip():
            raise FamilyNeedValidationError("need_signal_text_required")
        if not self.signal_id.strip():
            raise FamilyNeedValidationError("need_signal_id_required")

    @property
    def tenant_id(self) -> str:
        return self.context.tenant_id

    @property
    def family_id(self) -> str:
        return self.context.family_id

    @property
    def purpose(self) -> str:
        return self.context.purpose

    @property
    def consent_version(self) -> str:
        return self.context.consent_version

    @property
    def data_class(self) -> DataClass:
        return self.context.data_class

    @classmethod
    def capture(
        cls,
        *,
        context: NeedContext,
        source: NeedSignalSource,
        raw_text: str,
        signal_id: str | None = None,
        captured_at: datetime | None = None,
        expires_at: datetime | None = None,
        evidence_refs: tuple[EvidenceRef, ...] = (),
    ) -> NeedSignal:
        return cls(
            signal_id=signal_id or str(uuid4()),
            context=context,
            source=source,
            raw_text=raw_text.strip(),
            captured_at=captured_at or utcnow(),
            expires_at=expires_at,
            evidence_refs=tuple(evidence_refs),
        )

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        expiry = self.expires_at
        candidate = now or utcnow()
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if candidate.tzinfo is None:
            candidate = candidate.replace(tzinfo=UTC)
        return expiry <= candidate

    def expire(self, *, now: datetime | None = None) -> NeedSignal:
        if not self.is_expired(now):
            raise FamilyNeedConflictError("need_signal_not_expired")
        return replace(self, status=NeedSignalStatus.EXPIRED)

    def retract(self, actor_type: ActorType = ActorType.FAMILY_GUARDIAN) -> NeedSignal:
        assert_fact_writer(actor_type)
        if self.status is not NeedSignalStatus.ACTIVE:
            raise FamilyNeedConflictError("need_signal_not_active")
        return replace(self, status=NeedSignalStatus.RETRACTED)


@dataclass(frozen=True)
class FamilyNeed:
    """N1-N8 aggregate for one family need."""

    need_id: str
    context: NeedContext
    source_signal_ids: tuple[str, ...]
    subject_person_ids: tuple[str, ...]
    statement: str
    desired_outcome: str
    category: NeedCategory = NeedCategory.EDUCATION
    status: NeedStatus = NeedStatus.CAPTURED
    emotional_gate: EmotionalGate = EmotionalGate.E0_WELCOME
    constraints: tuple[NeedConstraint, ...] = ()
    version: int = 1
    confirmed_by_actor_id: str | None = None
    rejected_reason: str | None = None
    pause_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    evidence_refs: tuple[EvidenceRef, ...] = ()

    def __post_init__(self) -> None:
        assert_context(self.context)
        assert_fact_writer(self.context.actor_type)
        assert_evidence_scope(self.context, self.evidence_refs)
        if not self.need_id.strip() or not self.source_signal_ids:
            raise FamilyNeedValidationError("family_need_identity_required")
        if not self.statement.strip() or not self.desired_outcome.strip():
            raise FamilyNeedValidationError("family_need_statement_and_outcome_required")
        if self.version < 1:
            raise FamilyNeedValidationError("family_need_version_invalid")
        assert_subjects_in_family(self.subject_person_ids, self.context.subject_person_ids)

    @property
    def tenant_id(self) -> str:
        return self.context.tenant_id

    @property
    def family_id(self) -> str:
        return self.context.family_id

    @property
    def purpose(self) -> str:
        return self.context.purpose

    @property
    def consent_version(self) -> str:
        return self.context.consent_version

    @property
    def data_class(self) -> DataClass:
        return self.context.data_class

    @property
    def subject_person_id(self) -> str | None:
        """Compatibility projection for a single-child/single-subject journey."""

        return self.subject_person_ids[0] if len(self.subject_person_ids) == 1 else None

    @classmethod
    def from_signal(
        cls,
        signal: NeedSignal,
        *,
        statement: str,
        desired_outcome: str,
        category: NeedCategory = NeedCategory.EDUCATION,
        subject_person_ids: tuple[str, ...] | None = None,
        need_id: str | None = None,
        emotional_gate: EmotionalGate = EmotionalGate.E1_SEEN,
    ) -> FamilyNeed:
        subjects = subject_person_ids or signal.context.subject_person_ids
        if signal.status is not NeedSignalStatus.ACTIVE:
            raise FamilyNeedConflictError("need_signal_not_active")
        if signal.is_expired():
            raise FamilyNeedConflictError("need_signal_expired")
        assert_subjects_in_family(subjects, signal.context.subject_person_ids)
        return cls(
            need_id=need_id or str(uuid4()),
            context=signal.context,
            source_signal_ids=(signal.signal_id,),
            subject_person_ids=tuple(subjects),
            statement=statement.strip(),
            desired_outcome=desired_outcome.strip(),
            category=category,
            emotional_gate=emotional_gate,
            created_at=utcnow(),
            updated_at=utcnow(),
            evidence_refs=signal.evidence_refs,
        )

    def start_clarification(self) -> FamilyNeed:
        assert_transition(self.status, NeedStatus.CLARIFYING)
        return replace(
            self, status=NeedStatus.CLARIFYING, updated_at=utcnow(), version=self.version + 1
        )

    def confirm(
        self, actor_id: str, actor_type: ActorType = ActorType.FAMILY_GUARDIAN
    ) -> FamilyNeed:
        assert_fact_writer(actor_type)
        if actor_type not in {
            ActorType.FAMILY_GUARDIAN,
            ActorType.FAMILY_MEMBER,
            ActorType.OPERATOR,
        }:
            raise FamilyNeedConflictError("family_need_confirmation_requires_human")
        assert_transition(self.status, NeedStatus.CONFIRMED)
        return replace(
            self,
            status=NeedStatus.CONFIRMED,
            emotional_gate=EmotionalGate.E2_SAFE_TO_ACT,
            confirmed_by_actor_id=actor_id,
            updated_at=utcnow(),
            version=self.version + 1,
        )

    def advance_emotional_gate(
        self,
        target: EmotionalGate,
        actor_id: str,
        actor_type: ActorType = ActorType.FAMILY_GUARDIAN,
    ) -> FamilyNeed:
        """Record a family-visible step from welcome to an economic choice."""

        assert_fact_writer(actor_type)
        if actor_type not in {
            ActorType.FAMILY_GUARDIAN,
            ActorType.FAMILY_MEMBER,
            ActorType.OPERATOR,
        }:
            raise FamilyNeedConflictError("emotional_gate_requires_human")
        assert_emotional_gate_transition(self.emotional_gate, target)
        if target is EmotionalGate.E3_VALUE_CONFIRMED and self.status not in {
            NeedStatus.CONFIRMED,
            NeedStatus.PROFILED,
            NeedStatus.SOLUTIONING,
            NeedStatus.FULFILLING,
            NeedStatus.FULFILLED,
        }:
            raise FamilyNeedConflictError("value_gate_requires_confirmed_need")
        if target is EmotionalGate.E4_ECONOMIC_CHOICE and self.status not in {
            NeedStatus.PROFILED,
            NeedStatus.SOLUTIONING,
            NeedStatus.FULFILLING,
            NeedStatus.FULFILLED,
        }:
            raise FamilyNeedConflictError("economic_gate_requires_solution_context")
        return replace(
            self,
            emotional_gate=target,
            confirmed_by_actor_id=self.confirmed_by_actor_id or actor_id,
            updated_at=utcnow(),
            version=self.version + 1,
        )

    def reject(self, reason: str, actor_type: ActorType = ActorType.FAMILY_GUARDIAN) -> FamilyNeed:
        assert_fact_writer(actor_type)
        if not reason.strip():
            raise FamilyNeedValidationError("family_need_rejection_reason_required")
        assert_transition(self.status, NeedStatus.REJECTED)
        return replace(
            self,
            status=NeedStatus.REJECTED,
            rejected_reason=reason.strip(),
            updated_at=utcnow(),
            version=self.version + 1,
        )

    def pause(self, reason: str, actor_type: ActorType = ActorType.FAMILY_GUARDIAN) -> FamilyNeed:
        assert_fact_writer(actor_type)
        if not reason.strip():
            raise FamilyNeedValidationError("family_need_pause_reason_required")
        assert_transition(self.status, NeedStatus.PAUSED)
        return replace(
            self,
            status=NeedStatus.PAUSED,
            pause_reason=reason.strip(),
            updated_at=utcnow(),
            version=self.version + 1,
        )

    def resume(self, actor_type: ActorType = ActorType.FAMILY_GUARDIAN) -> FamilyNeed:
        assert_fact_writer(actor_type)
        if self.status is not NeedStatus.PAUSED:
            raise FamilyNeedConflictError("family_need_not_paused")
        return replace(
            self,
            status=NeedStatus.CLARIFYING,
            pause_reason=None,
            updated_at=utcnow(),
            version=self.version + 1,
        )

    def mark_profiled(self) -> FamilyNeed:
        assert_transition(self.status, NeedStatus.PROFILED)
        return replace(
            self, status=NeedStatus.PROFILED, updated_at=utcnow(), version=self.version + 1
        )

    def mark_solutioning(self) -> FamilyNeed:
        assert_transition(self.status, NeedStatus.SOLUTIONING)
        return replace(
            self, status=NeedStatus.SOLUTIONING, updated_at=utcnow(), version=self.version + 1
        )

    def mark_fulfilling(self) -> FamilyNeed:
        assert_transition(self.status, NeedStatus.FULFILLING)
        return replace(
            self, status=NeedStatus.FULFILLING, updated_at=utcnow(), version=self.version + 1
        )

    def mark_fulfilled(self, actor_type: ActorType = ActorType.OPERATOR) -> FamilyNeed:
        assert_fact_writer(actor_type)
        assert_transition(self.status, NeedStatus.FULFILLED)
        return replace(
            self, status=NeedStatus.FULFILLED, updated_at=utcnow(), version=self.version + 1
        )

    def close(self, actor_type: ActorType = ActorType.FAMILY_GUARDIAN) -> FamilyNeed:
        assert_fact_writer(actor_type)
        assert_transition(self.status, NeedStatus.CLOSED)
        return replace(
            self, status=NeedStatus.CLOSED, updated_at=utcnow(), version=self.version + 1
        )


@dataclass(frozen=True)
class NeedProfile:
    """N2 classification; a confirmed profile never contains a family score."""

    profile_id: str
    need_id: str
    need_version: int
    context: NeedContext
    category: NeedCategory
    urgency: NeedUrgency
    complexity: NeedComplexity
    risk_level: RiskLevel
    preferred_shapes: tuple[SupplyShape, ...]
    constraints: tuple[NeedConstraint, ...] = ()
    required_capability_keys: tuple[str, ...] = ()
    locale: str | None = None
    region: str | None = None
    confirmed_by_actor_id: str | None = None
    version: int = 1
    created_at: datetime | None = None
    # System-derived Triple-P-style support intensity (see
    # `derive_intervention_tier`). This is always computed server-side from
    # urgency/complexity/risk_level; it is never accepted from a client body,
    # mirroring the existing "AI/system-derived fields cannot be supplied by
    # the caller" boundary already enforced for other derived attributes in
    # this context.
    intervention_tier: InterventionTier = InterventionTier.LIGHT_GUIDANCE

    def __post_init__(self) -> None:
        assert_context(self.context)
        if not self.profile_id.strip() or not self.need_id.strip():
            raise FamilyNeedValidationError("need_profile_identity_required")
        if not self.preferred_shapes:
            raise FamilyNeedValidationError("need_profile_supply_shape_required")
        if self.risk_level is RiskLevel.HUMAN_REVIEW_REQUIRED and not self.confirmed_by_actor_id:
            raise FamilyNeedValidationError("high_risk_profile_requires_human_confirmation")
        if self.version < 1 or self.need_version < 1:
            raise FamilyNeedValidationError("need_profile_version_invalid")
        expected_tier = derive_intervention_tier(
            urgency=self.urgency, complexity=self.complexity, risk_level=self.risk_level
        )
        if self.intervention_tier is not expected_tier:
            raise FamilyNeedValidationError("need_profile_intervention_tier_mismatch")

    @property
    def tenant_id(self) -> str:
        return self.context.tenant_id

    @property
    def family_id(self) -> str:
        return self.context.family_id

    @property
    def purpose(self) -> str:
        return self.context.purpose

    @property
    def consent_version(self) -> str:
        return self.context.consent_version

    @property
    def data_class(self) -> DataClass:
        return self.context.data_class

    @classmethod
    def from_need(
        cls,
        need: FamilyNeed,
        *,
        urgency: NeedUrgency,
        complexity: NeedComplexity,
        risk_level: RiskLevel,
        preferred_shapes: tuple[SupplyShape, ...],
        required_capability_keys: tuple[str, ...] = (),
        constraints: tuple[NeedConstraint, ...] = (),
        confirmed_by_actor_id: str | None = None,
        profile_id: str | None = None,
    ) -> NeedProfile:
        if need.status is not NeedStatus.CONFIRMED:
            raise FamilyNeedConflictError("need_must_be_confirmed_before_profile")
        if risk_level is RiskLevel.HUMAN_REVIEW_REQUIRED and not confirmed_by_actor_id:
            raise FamilyNeedConflictError("high_risk_profile_requires_human_review")
        profile = cls(
            profile_id=profile_id or str(uuid4()),
            need_id=need.need_id,
            need_version=need.version,
            context=need.context,
            category=need.category,
            urgency=urgency,
            complexity=complexity,
            risk_level=risk_level,
            preferred_shapes=tuple(preferred_shapes),
            required_capability_keys=tuple(required_capability_keys),
            constraints=tuple(constraints),
            confirmed_by_actor_id=confirmed_by_actor_id,
            created_at=utcnow(),
            intervention_tier=derive_intervention_tier(
                urgency=urgency, complexity=complexity, risk_level=risk_level
            ),
        )
        return profile

    def ensure_current(self, need: FamilyNeed) -> None:
        if need.need_id != self.need_id:
            raise FamilyNeedConflictError("need_profile_need_mismatch")
        assert_version(self.need_version, need.version)


@dataclass(frozen=True)
class SolutionDraft:
    """N3 draft; references products/services but does not create them."""

    draft_id: str
    need_id: str
    need_profile_id: str
    profile_version: int
    context: NeedContext
    shape: SupplyShape
    components: tuple[SolutionComponentRef, ...]
    emotional_gate: EmotionalGate
    commercial_intent: bool = False
    status: SolutionDraftStatus = SolutionDraftStatus.DRAFT
    author_type: ActorType = ActorType.SYSTEM
    acceptance_criteria: tuple[AcceptanceCriterion, ...] = ()
    estimated_cost_minor: int | None = None
    sla_hours: int | None = None
    can_pause: bool = True
    can_exit: bool = True
    respectful_language: bool = True
    manipulative: bool = False
    approved_by_actor_id: str | None = None
    rejection_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    # True only when the originating profile's `intervention_tier` is
    # ENHANCED_SUPPORT (Triple P Level 5: maltreatment-risk or otherwise
    # compounding-problem families). This is a "flagged, not auto-fulfilled"
    # marker, not a status: the draft still goes through the ordinary
    # DRAFT -> FAMILY_REVIEW -> APPROVED path, but an ENHANCED_SUPPORT draft
    # must never be treated by any caller as safe to auto-fulfill purely
    # because a supply reference resolved. Enforced structurally (see
    # `SolutionDraft.propose`), not left to callers to remember.
    requires_human_case_review: bool = False
    human_case_review_note: str | None = None

    def __post_init__(self) -> None:
        assert_context(self.context)
        assert_solution_shape(self.shape, (item.shape for item in self.components))
        assert_commercial_gate(
            self.emotional_gate, self.shape, commercial_intent=self.commercial_intent
        )
        assert_we_are_family_guards(
            can_pause=self.can_pause,
            can_exit=self.can_exit,
            respectful_language=self.respectful_language,
            manipulative=self.manipulative,
        )
        if self.author_type is ActorType.AI and self.status is not SolutionDraftStatus.DRAFT:
            raise FamilyNeedConflictError("ai_draft_cannot_publish_or_transition")
        if self.estimated_cost_minor is not None and self.estimated_cost_minor < 0:
            raise FamilyNeedValidationError("solution_cost_invalid")
        if self.sla_hours is not None and self.sla_hours < 0:
            raise FamilyNeedValidationError("solution_sla_invalid")
        if self.requires_human_case_review and not self.human_case_review_note:
            raise FamilyNeedValidationError("human_case_review_note_required")

    @property
    def tenant_id(self) -> str:
        return self.context.tenant_id

    @property
    def family_id(self) -> str:
        return self.context.family_id

    @property
    def purpose(self) -> str:
        return self.context.purpose

    @property
    def consent_version(self) -> str:
        return self.context.consent_version

    @property
    def data_class(self) -> DataClass:
        return self.context.data_class

    @classmethod
    def propose(
        cls,
        *,
        need: FamilyNeed,
        profile: NeedProfile,
        shape: SupplyShape,
        components: tuple[SolutionComponentRef, ...],
        emotional_gate: EmotionalGate | None = None,
        commercial_intent: bool = False,
        author_type: ActorType = ActorType.SYSTEM,
        acceptance_criteria: tuple[AcceptanceCriterion, ...] = (),
        estimated_cost_minor: int | None = None,
        sla_hours: int | None = None,
        draft_id: str | None = None,
    ) -> SolutionDraft:
        profile.ensure_current(need)
        if need.status not in {NeedStatus.CONFIRMED, NeedStatus.PROFILED, NeedStatus.SOLUTIONING}:
            raise FamilyNeedConflictError("need_not_ready_for_solution_draft")
        if shape not in profile.preferred_shapes:
            raise FamilyNeedValidationError("solution_shape_not_in_need_profile")
        gate = emotional_gate or need.emotional_gate
        requires_review = profile.intervention_tier is InterventionTier.ENHANCED_SUPPORT
        return cls(
            draft_id=draft_id or str(uuid4()),
            need_id=need.need_id,
            need_profile_id=profile.profile_id,
            profile_version=profile.version,
            context=need.context,
            shape=shape,
            components=tuple(components),
            emotional_gate=gate,
            commercial_intent=commercial_intent,
            author_type=author_type,
            acceptance_criteria=tuple(acceptance_criteria),
            estimated_cost_minor=estimated_cost_minor,
            sla_hours=sla_hours,
            created_at=utcnow(),
            updated_at=utcnow(),
            requires_human_case_review=requires_review,
            human_case_review_note=(
                "PENDING_HUMAN_CASE_REVIEW: intervention_tier=ENHANCED_SUPPORT "
                "(Triple P Level 5) — this draft must not be auto-fulfilled; "
                "a human operator must confirm before any booking/order proceeds."
                if requires_review
                else None
            ),
        )

    @property
    def may_execute(self) -> bool:
        return self.status is SolutionDraftStatus.APPROVED

    @property
    def can_withdraw(self) -> bool:
        """Alias used by UI contracts for the family exit right."""

        return self.can_exit

    def ensure_fresh(self, profile: NeedProfile) -> None:
        if self.need_profile_id != profile.profile_id:
            raise FamilyNeedConflictError("solution_profile_mismatch")
        assert_version(self.profile_version, profile.version)

    def submit_for_family_review(self, *, profile: NeedProfile) -> SolutionDraft:
        self.ensure_fresh(profile)
        if self.status is not SolutionDraftStatus.DRAFT:
            raise FamilyNeedConflictError("solution_draft_not_editable")
        return replace(self, status=SolutionDraftStatus.FAMILY_REVIEW, updated_at=utcnow())

    def approve(
        self, actor_id: str, actor_type: ActorType = ActorType.FAMILY_GUARDIAN
    ) -> SolutionDraft:
        assert_manage_actor(actor_type)
        if self.status is not SolutionDraftStatus.FAMILY_REVIEW:
            raise FamilyNeedConflictError("solution_draft_not_in_family_review")
        return replace(
            self,
            status=SolutionDraftStatus.APPROVED,
            approved_by_actor_id=actor_id,
            emotional_gate=(
                EmotionalGate.E4_ECONOMIC_CHOICE
                if self.commercial_intent
                else EmotionalGate.E3_VALUE_CONFIRMED
            ),
            updated_at=utcnow(),
        )

    def reject(
        self, reason: str, actor_type: ActorType = ActorType.FAMILY_GUARDIAN
    ) -> SolutionDraft:
        assert_manage_actor(actor_type)
        if self.status not in {SolutionDraftStatus.DRAFT, SolutionDraftStatus.FAMILY_REVIEW}:
            raise FamilyNeedConflictError("solution_draft_not_rejectable")
        if not reason.strip():
            raise FamilyNeedValidationError("solution_rejection_reason_required")
        return replace(
            self,
            status=SolutionDraftStatus.REJECTED,
            rejection_reason=reason.strip(),
            updated_at=utcnow(),
        )

    def pause(self, actor_type: ActorType = ActorType.FAMILY_GUARDIAN) -> SolutionDraft:
        assert_fact_writer(actor_type)
        if self.status not in {
            SolutionDraftStatus.DRAFT,
            SolutionDraftStatus.FAMILY_REVIEW,
            SolutionDraftStatus.APPROVED,
        }:
            raise FamilyNeedConflictError("solution_draft_not_pauseable")
        return replace(self, status=SolutionDraftStatus.PAUSED, updated_at=utcnow())

    def resume(self, actor_type: ActorType = ActorType.FAMILY_GUARDIAN) -> SolutionDraft:
        assert_fact_writer(actor_type)
        if self.status is not SolutionDraftStatus.PAUSED:
            raise FamilyNeedConflictError("solution_draft_not_paused")
        return replace(self, status=SolutionDraftStatus.FAMILY_REVIEW, updated_at=utcnow())

    def mark_stale(self, profile: NeedProfile) -> SolutionDraft:
        if self.profile_version == profile.version:
            raise FamilyNeedConflictError("solution_draft_not_stale")
        return replace(self, status=SolutionDraftStatus.STALE, updated_at=utcnow())


@dataclass(frozen=True)
class FamilyConfirmedOutcome:
    """N6/N7: the family's own verdict on whether a delivered fulfilment
    (a completed booking or a completed course) actually helped.

    This is deliberately a separate aggregate from the N5 "delivery
    happened" facts (`booking_service_record_id` / `course_completion_id`
    joined to the journey via `booking-service-record:`/`course-completion:`
    action facts). Those record that a service or course was *delivered*;
    this records whether the family says it *helped* — the two must never be
    conflated, per R9 (AI output/system delivery records never become the
    family's own outcome fact).
    """

    outcome_id: str
    context: NeedContext
    need_id: str
    fulfillment_ref: str
    decision: FamilyOutcomeDecision
    confirmed_by: str
    confirmed_at: datetime
    draft_id: str | None = None
    family_note: str | None = None

    def __post_init__(self) -> None:
        assert_context(self.context)
        assert_family_outcome_confirmer(self.context.actor_type)
        if not self.outcome_id.strip():
            raise FamilyNeedValidationError("family_confirmed_outcome_id_required")
        if not self.need_id.strip():
            raise FamilyNeedValidationError("family_confirmed_outcome_need_required")
        if not self.fulfillment_ref.strip():
            raise FamilyNeedValidationError("family_confirmed_outcome_fulfillment_ref_required")
        if not self.confirmed_by.strip():
            raise FamilyNeedValidationError("family_confirmed_outcome_confirmer_required")

    @property
    def tenant_id(self) -> str:
        return self.context.tenant_id

    @property
    def family_id(self) -> str:
        return self.context.family_id

    @classmethod
    def confirm(
        cls,
        *,
        context: NeedContext,
        need_id: str,
        fulfillment_ref: str,
        decision: FamilyOutcomeDecision,
        confirmed_by: str,
        draft_id: str | None = None,
        family_note: str | None = None,
        outcome_id: str | None = None,
        confirmed_at: datetime | None = None,
    ) -> FamilyConfirmedOutcome:
        return cls(
            outcome_id=outcome_id or str(uuid4()),
            context=context,
            need_id=need_id,
            draft_id=draft_id,
            fulfillment_ref=fulfillment_ref,
            decision=decision,
            confirmed_by=confirmed_by,
            confirmed_at=confirmed_at or utcnow(),
            family_note=family_note.strip() if family_note and family_note.strip() else None,
        )


@dataclass(frozen=True)
class AssignmentPlan:
    """N4: the fact that a confirmed draft's components were assigned to
    specific resources, and on what authority.

    This aggregate deliberately records only the assignment decision itself
    — it does not recompute or duplicate resource capacity checking (that
    remains `SupplyReferencePort.check_resource_capacity`'s job). Before this
    existed, "which resources this need was matched to" lived only inside
    `fulfil_confirmed_draft`'s call arguments and was never itself a
    queryable fact. `authorization_basis` names, in plain text, the family
    action that authorized this assignment (e.g.
    ``family_confirmed_draft:{draft_id}``) so a reader never has to guess
    whether an AI decided this on its own — it did not (see
    `FamilyNeedApplicationService.create_assignment_plan`, which is only ever
    called after the family's own draft approval).
    """

    plan_id: str
    tenant_id: str
    family_id: str
    need_id: str
    draft_id: str
    component_refs: tuple[SolutionComponentRef, ...]
    authorization_basis: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.plan_id.strip():
            raise FamilyNeedValidationError("assignment_plan_id_required")
        if not self.tenant_id.strip() or not self.family_id.strip():
            raise FamilyNeedValidationError("assignment_plan_scope_required")
        if not self.need_id.strip() or not self.draft_id.strip():
            raise FamilyNeedValidationError("assignment_plan_identity_required")
        if not self.component_refs:
            raise FamilyNeedValidationError("assignment_plan_components_required")
        if not self.authorization_basis.strip():
            raise FamilyNeedValidationError("assignment_plan_authorization_basis_required")

    @classmethod
    def create(
        cls,
        *,
        tenant_id: str,
        family_id: str,
        need_id: str,
        draft_id: str,
        component_refs: tuple[SolutionComponentRef, ...],
        authorization_basis: str,
        plan_id: str | None = None,
        created_at: datetime | None = None,
    ) -> AssignmentPlan:
        return cls(
            plan_id=plan_id or str(uuid4()),
            tenant_id=tenant_id,
            family_id=family_id,
            need_id=need_id,
            draft_id=draft_id,
            component_refs=tuple(component_refs),
            authorization_basis=authorization_basis,
            created_at=created_at or utcnow(),
        )


__all__ = [
    "AssignmentPlan",
    "FamilyConfirmedOutcome",
    "FamilyNeed",
    "NeedProfile",
    "NeedSignal",
    "SolutionDraft",
    "ResourceGap",
]
