"""Pure policies for the Family Need context.

Policies are deterministic and have no persistence or AI dependencies.  They
are intentionally strict: a caller must explicitly prove scope, consent and
human confirmation before turning a draft into a business action.
"""

from __future__ import annotations

from collections.abc import Iterable

from .errors import (
    FamilyNeedConflictError,
    FamilyNeedForbiddenError,
    FamilyNeedValidationError,
)
from .value_objects import (
    ActorType,
    DataClass,
    EmotionalGate,
    EvidenceRef,
    InterventionTier,
    NeedComplexity,
    NeedContext,
    NeedStatus,
    NeedUrgency,
    RiskLevel,
    SupplyShape,
    gate_rank,
)

ALLOWED_PURPOSES = frozenset(
    {
        "FAMILY_NEED",
        "ASSESSMENT",
        "EDUCATION",
        "SERVICE",
        "GROWTH",
        "SUPPORT",
    }
)
MANAGE_ACTOR_TYPES = frozenset({ActorType.FAMILY_GUARDIAN, ActorType.OPERATOR})
FACT_WRITER_TYPES = frozenset(
    {
        ActorType.FAMILY_MEMBER,
        ActorType.FAMILY_GUARDIAN,
        ActorType.OPERATOR,
        ActorType.PROVIDER,
        ActorType.SYSTEM,
    }
)


def assert_context(context: NeedContext) -> None:
    if context.purpose not in ALLOWED_PURPOSES:
        raise FamilyNeedValidationError("purpose_not_allowed")
    if context.data_class is DataClass.MINOR_PERSONAL_DATA and not context.subject_person_ids:
        raise FamilyNeedValidationError("minor_subject_required")
    if context.data_class is DataClass.MINOR_PERSONAL_DATA and context.purpose not in {
        "FAMILY_NEED",
        "ASSESSMENT",
        "EDUCATION",
        "GROWTH",
    }:
        raise FamilyNeedForbiddenError("minor_purpose_not_allowed")


def assert_fact_writer(actor_type: ActorType) -> None:
    """AI and anonymous actors can propose perspectives, never facts."""

    if actor_type is ActorType.AI:
        raise FamilyNeedForbiddenError("ai_cannot_write_family_need_fact")
    if actor_type not in FACT_WRITER_TYPES:
        raise FamilyNeedForbiddenError("actor_cannot_write_need_fact")


def assert_manage_actor(actor_type: ActorType) -> None:
    if actor_type not in MANAGE_ACTOR_TYPES:
        raise FamilyNeedForbiddenError("actor_cannot_manage_need")


FAMILY_OUTCOME_CONFIRMER_TYPES = frozenset({ActorType.FAMILY_GUARDIAN, ActorType.FAMILY_MEMBER})


def assert_family_outcome_confirmer(actor_type: ActorType) -> None:
    """N6/N7: only the family itself may confirm whether a delivered service
    or course actually helped. AI and SYSTEM are rejected unconditionally —
    this is the R9 boundary made concrete for the outcome-confirmation step,
    not merely the ordinary fact-writer/manage-actor checks above."""

    if actor_type not in FAMILY_OUTCOME_CONFIRMER_TYPES:
        raise FamilyNeedForbiddenError("family_outcome_confirmation_requires_family_actor")


def assert_family_scope(expected: NeedContext, supplied: NeedContext) -> None:
    """Fail closed for tenant, family, purpose and subject scope."""

    if expected.tenant_id != supplied.tenant_id:
        raise FamilyNeedForbiddenError("tenant_scope_denied")
    if expected.family_id != supplied.family_id:
        raise FamilyNeedForbiddenError("family_scope_denied")
    if expected.purpose != supplied.purpose:
        raise FamilyNeedForbiddenError("purpose_scope_denied")
    if not set(supplied.subject_person_ids).issubset(expected.subject_person_ids):
        raise FamilyNeedForbiddenError("subject_scope_denied")
    if expected.data_class is not supplied.data_class:
        raise FamilyNeedForbiddenError("data_class_scope_denied")


def assert_subjects_in_family(
    subject_person_ids: Iterable[str], family_subject_person_ids: Iterable[str]
) -> None:
    family_subjects = set(family_subject_person_ids)
    if not set(subject_person_ids).issubset(family_subjects):
        raise FamilyNeedForbiddenError("subject_not_in_family")


def assert_evidence_scope(context: NeedContext, evidence_refs: Iterable[EvidenceRef]) -> None:
    """Require an authorized, live media provenance snapshot for every ref."""

    for evidence in evidence_refs:
        if evidence.tenant_id != context.tenant_id:
            raise FamilyNeedForbiddenError("media_tenant_scope_denied")
        if evidence.family_id != context.family_id:
            raise FamilyNeedForbiddenError("media_family_scope_denied")
        if not evidence.authorized or not evidence.consent_version:
            raise FamilyNeedForbiddenError("media_consent_required")
        if evidence.consent_version != context.consent_version:
            raise FamilyNeedForbiddenError("media_consent_version_mismatch")
        if evidence.is_expired():
            raise FamilyNeedForbiddenError("media_evidence_expired")


def assert_transition(current: NeedStatus, target: NeedStatus) -> None:
    transitions: dict[NeedStatus, frozenset[NeedStatus]] = {
        NeedStatus.CAPTURED: frozenset(
            {NeedStatus.CLARIFYING, NeedStatus.CONFIRMED, NeedStatus.REJECTED, NeedStatus.PAUSED}
        ),
        NeedStatus.CLARIFYING: frozenset(
            {NeedStatus.CONFIRMED, NeedStatus.REJECTED, NeedStatus.PAUSED}
        ),
        NeedStatus.CONFIRMED: frozenset(
            {NeedStatus.PROFILED, NeedStatus.REJECTED, NeedStatus.PAUSED}
        ),
        NeedStatus.PROFILED: frozenset(
            {NeedStatus.SOLUTIONING, NeedStatus.REJECTED, NeedStatus.PAUSED}
        ),
        NeedStatus.SOLUTIONING: frozenset(
            {NeedStatus.FULFILLING, NeedStatus.PAUSED, NeedStatus.REJECTED}
        ),
        NeedStatus.FULFILLING: frozenset({NeedStatus.FULFILLED, NeedStatus.PAUSED}),
        NeedStatus.FULFILLED: frozenset({NeedStatus.CLOSED, NeedStatus.CLARIFYING}),
        NeedStatus.PAUSED: frozenset(
            {NeedStatus.CLARIFYING, NeedStatus.CONFIRMED, NeedStatus.CLOSED}
        ),
        NeedStatus.REJECTED: frozenset({NeedStatus.CLARIFYING, NeedStatus.CLOSED}),
        NeedStatus.CLOSED: frozenset(),
    }
    if target not in transitions.get(current, frozenset()):
        raise FamilyNeedConflictError(
            f"need_transition_{current.value.lower()}_to_{target.value.lower()}_denied"
        )


def assert_solution_shape(shape: SupplyShape, components: Iterable[SupplyShape]) -> None:
    component_shapes = tuple(components)
    if shape is SupplyShape.PRODUCT and any(
        item is not SupplyShape.PRODUCT for item in component_shapes
    ):
        raise FamilyNeedValidationError("product_draft_cannot_include_non_product_component")
    if shape is SupplyShape.SERVICE and any(
        item is not SupplyShape.SERVICE for item in component_shapes
    ):
        raise FamilyNeedValidationError("service_draft_cannot_include_non_service_component")
    if shape is SupplyShape.SOLUTION and not component_shapes:
        raise FamilyNeedValidationError("solution_draft_requires_components")


def assert_commercial_gate(
    gate: EmotionalGate, shape: SupplyShape, *, commercial_intent: bool
) -> None:
    """Economic choice follows emotional safety and proven value (E3)."""

    if commercial_intent and gate_rank(gate) < gate_rank(EmotionalGate.E3_VALUE_CONFIRMED):
        raise FamilyNeedForbiddenError("economic_choice_before_value_confirmed")
    if (
        shape is SupplyShape.SOLUTION
        and commercial_intent
        and gate is EmotionalGate.E4_ECONOMIC_CHOICE
    ):
        return


def assert_emotional_gate_transition(current: EmotionalGate, target: EmotionalGate) -> None:
    if gate_rank(target) <= gate_rank(current):
        raise FamilyNeedConflictError("emotional_gate_must_progress")
    if gate_rank(target) - gate_rank(current) > 1:
        raise FamilyNeedConflictError("emotional_gate_cannot_skip")


def assert_we_are_family_guards(
    *, can_pause: bool, can_exit: bool, respectful_language: bool, manipulative: bool
) -> None:
    if not can_pause or not can_exit:
        raise FamilyNeedValidationError("family_need_must_be_reversible")
    if not respectful_language:
        raise FamilyNeedValidationError("family_need_requires_respectful_language")
    if manipulative:
        raise FamilyNeedForbiddenError("manipulative_family_experience_denied")


def derive_intervention_tier(
    *, urgency: NeedUrgency, complexity: NeedComplexity, risk_level: RiskLevel
) -> InterventionTier:
    """Derive a Triple-P-style support intensity from the N2 profile axes.

    This is the single new business rule for graduated support intensity.
    Rules, in priority order (first match wins):

    1. ``risk_level`` at the ceiling (``HUMAN_REVIEW_REQUIRED``) always wins,
       regardless of urgency/complexity: any family situation flagged for
       mandatory human review is, by definition, not something an automated
       match should size down. -> ``ENHANCED_SUPPORT`` (Triple P Level 5).
    2. ``risk_level`` at ``HIGH`` (but not requiring review) means a
       compounding or more severe problem is present even if the family
       hasn't framed it as urgent. -> ``INTENSIVE_SELECTIVE`` (Level 4).
    3. Otherwise, when both urgency and complexity are at their lowest
       ("WHEN_READY"/"SIMPLE") and risk is "LOW", nothing about the need
       calls for direct contact yet. -> ``UNIVERSAL`` (Level 1): self-help
       content is proportionate.
    4. Otherwise, complexity is the next-strongest signal that this cannot be
       resolved with a single short interaction: "CROSS_DOMAIN" complexity
       (touching more than one life area) escalates to ``STANDARD_SELECTIVE``
       (Level 3) even at LOW/MEDIUM risk, because the coordination itself
       requires a real conversation, not a seminar.
    5. A "COMPOUND" complexity, or an urgency of "NOW"/"SOON" with anything
       above the bottom complexity, is a specific-but-contained concern that
       fits a light-touch, mostly one-off contact. -> ``LIGHT_GUIDANCE``
       (Level 2).
    6. Anything left over that is not already caught by rule 3 (i.e. some
       urgency or complexity signal is present, but weakly) also resolves to
       ``LIGHT_GUIDANCE`` (Level 2), the smallest tier above pure self-help.

    The function never reads a family score and only reads the three
    already-modelled N2 profile axes; it introduces no new persisted field
    beyond the derived ``InterventionTier`` itself.
    """

    if risk_level is RiskLevel.HUMAN_REVIEW_REQUIRED:
        return InterventionTier.ENHANCED_SUPPORT
    if risk_level is RiskLevel.HIGH:
        return InterventionTier.INTENSIVE_SELECTIVE
    if (
        urgency is NeedUrgency.WHEN_READY
        and complexity is NeedComplexity.SIMPLE
        and risk_level is RiskLevel.LOW
    ):
        return InterventionTier.UNIVERSAL
    if complexity is NeedComplexity.CROSS_DOMAIN:
        return InterventionTier.STANDARD_SELECTIVE
    return InterventionTier.LIGHT_GUIDANCE


def assert_version(expected: int, supplied: int) -> None:
    if expected != supplied:
        raise FamilyNeedConflictError("family_need_version_stale")
