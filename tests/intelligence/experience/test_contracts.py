from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceContractError,
    ExperienceEvent,
    ExperienceEventType,
    ExperienceMediaRef,
    ExperienceModality,
    ExperienceNode,
    ExperienceProvenance,
    ExperienceScope,
    FeedbackSignal,
    FeedbackSignalType,
    FeedbackTargetType,
    MemoryLevel,
    MemoryRef,
    MemoryScope,
    ModalityOperation,
    ProvenanceKind,
    RecommendationDecision,
    RecommendationStatus,
    ScopeMismatchError,
    assert_scope_compatible,
)
from backend.platform.idempotency.keys import IdempotencyKey, InMemoryIdempotencyStore


def _scope(
    *,
    tenant_id: str = "tenant-a",
    family_id: str = "family-a",
    subjects: tuple[str, ...] = ("child-a",),
    purpose: str = "growth_support",
    data_class: str = "FAMILY_PRIVATE_TEXT",
) -> ExperienceScope:
    return ExperienceScope(
        global_id=f"g-{tenant_id}-{family_id}",
        tenant_id=tenant_id,
        region_id="CN",
        family_id=family_id,
        subject_ids=subjects,
        purpose=purpose,
        consent_version="consent.v1",
        consent_granted=True,
        data_class=data_class,  # type: ignore[arg-type]
        locale="zh-CN",
        content_locale="zh-CN",
        model_locale="zh-CN",
        policy_locale="zh-CN",
        deletion_ref=DeletionRef("del-001", "experience.v1"),
        correlation_id="corr-001",
        causation_id="cause-001",
    )


def _provenance(kind: ProvenanceKind = ProvenanceKind.USER) -> ExperienceProvenance:
    values: dict[str, object] = {
        "provenance_ref": "prov-001",
        "source_refs": ("ui://UI-03",),
        "kind": kind,
        "policy_version": "experience-policy.v1",
    }
    if kind is ProvenanceKind.AI_DRAFT:
        values.update(
            context_snapshot_ref="ctx-001",
            model_attempt_ref="attempt-001",
        )
    return ExperienceProvenance(**values)  # type: ignore[arg-type]


def _media(
    *,
    tenant_id: str = "tenant-a",
    family_id: str = "family-a",
    subjects: tuple[str, ...] = ("child-a",),
    modality: ExperienceModality = ExperienceModality.VOICE,
    operation: ModalityOperation = ModalityOperation.INPUT,
    data_class: str = "FAMILY_PRIVATE_TEXT",
    consent_granted: bool = True,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
) -> ExperienceMediaRef:
    created = created_at or datetime.now(UTC)
    return ExperienceMediaRef(
        media_id="media-001",
        media_ref="cell://media-001",
        tenant_id=tenant_id,
        region_id="CN",
        family_id=family_id,
        subject_ids=subjects,
        modality=modality,
        operation=operation,
        purpose="growth_support",
        consent_version="consent.v1",
        consent_granted=consent_granted,
        data_class=data_class,  # type: ignore[arg-type]
        locale="zh-CN",
        provenance=_provenance(),
        deletion_ref=DeletionRef("media-del-001", "media.v1"),
        correlation_id="corr-media-001",
        causation_id="cause-media-001",
        created_at=created,
        expires_at=expires_at,
    )


def _memory(
    *,
    tenant_id: str = "tenant-a",
    family_id: str = "family-a",
    subjects: tuple[str, ...] = ("child-a",),
    memory_scope: MemoryScope = MemoryScope.CHILD,
    level: MemoryLevel = MemoryLevel.M1_SESSION,
    purpose: str = "growth_support",
    consent_granted: bool = True,
    created_at: datetime | None = None,
    expires_at: datetime | None = None,
    derived_memory_ids: tuple[str, ...] = ("memory-transcript-001",),
    unbounded: bool = False,
) -> MemoryRef:
    created = created_at or datetime.now(UTC)
    expiry = None if unbounded else (
        expires_at or (created.replace(microsecond=0) + timedelta(days=1))
    )
    return MemoryRef(
        memory_id="memory-001",
        memory_ref="cell://memory-001",
        tenant_id=tenant_id,
        region_id="CN",
        family_id=family_id,
        subject_ids=subjects,
        memory_scope=memory_scope,
        level=level,
        purpose=purpose,
        consent_version="consent.v1",
        consent_granted=consent_granted,
        data_class="MINOR_PERSONAL_DATA",  # type: ignore[arg-type]
        locale="zh-CN",
        provenance=_provenance(),
        deletion_ref=DeletionRef("memory-del-001", "memory.v1"),
        source_ref="evt-voice-001",
        correlation_id="corr-memory-001",
        causation_id="cause-memory-001",
        created_at=created,
        expires_at=expiry,
        derived_memory_ids=derived_memory_ids,
    )


def test_experience_event_success_carries_n0_scope_and_is_not_a_fact_writer() -> None:
    event = ExperienceEvent(
        event_id="evt-001",
        event_type=ExperienceEventType.ENTRY_OPENED,
        node=ExperienceNode.N0,
        scope=_scope(),
        idempotency_key=IdempotencyKey("tenant-a", "evt-001"),
        provenance=_provenance(),
        actor_id="parent-a",
        occurred_at=datetime.now(UTC),
        payload={"entry_point": "assessment"},
    )

    assert event.node is ExperienceNode.N0
    assert event.tenant_id == "tenant-a"
    assert event.subject_id == "child-a"
    assert event.locale == "zh-CN"
    assert event.modality is ExperienceModality.TEXT
    assert event.deletion_ref.deletion_id == "del-001"
    assert event.may_mutate_business_state is False


def test_event_rejects_payload_that_looks_like_family_fact_or_ranking() -> None:
    with pytest.raises(ExperienceContractError, match="CANNOT_WRITE_FACT"):
        ExperienceEvent(
            event_id="evt-002",
            event_type=ExperienceEventType.CONTENT_SHOWN,
            node=ExperienceNode.N1,
            scope=_scope(),
            idempotency_key=IdempotencyKey("tenant-a", "evt-002"),
            provenance=_provenance(),
            actor_id="parent-a",
            payload={"family_rank": 1},
        )


def test_recommendation_success_requires_explainability_and_candidate_subset() -> None:
    decision = RecommendationDecision(
        decision_id="decision-001",
        request_id="request-001",
        scope=_scope(),
        idempotency_key=IdempotencyKey("tenant-a", "decision-001"),
        provenance=_provenance(ProvenanceKind.AI_DRAFT),
        strategy_version="experience-strategy.v1",
        candidate_ids=("chapter-1", "chapter-2"),
        selected_ids=("chapter-1",),
        status=RecommendationStatus.ACCEPTED,
        reason_codes=("family_goal_match",),
    )

    assert decision.profile_id == "experience_curator"
    assert decision.may_mutate_business_state is False
    assert decision.selected_ids == ("chapter-1",)

    with pytest.raises(ExperienceContractError, match="subset"):
        RecommendationDecision(
            decision_id="decision-002",
            request_id="request-002",
            scope=_scope(),
            idempotency_key=IdempotencyKey("tenant-a", "decision-002"),
            provenance=_provenance(ProvenanceKind.AI_DRAFT),
            strategy_version="experience-strategy.v1",
            candidate_ids=("chapter-1",),
            selected_ids=("service-not-in-candidates",),
        )


def test_minor_data_cannot_be_used_for_automatic_commercial_recommendation() -> None:
    with pytest.raises(ExperienceContractError, match="MINOR_COMMERCIAL_PURPOSE_FORBIDDEN"):
        _scope(
            purpose="marketing",
            data_class="MINOR_PERSONAL_DATA",
        )


def test_feedback_success_records_pause_and_requires_human_for_complaint() -> None:
    feedback = FeedbackSignal(
        feedback_id="feedback-001",
        target_type=FeedbackTargetType.RECOMMENDATION,
        target_id="decision-001",
        signal=FeedbackSignalType.PAUSED,
        scope=_scope(),
        idempotency_key=IdempotencyKey("tenant-a", "feedback-001"),
        provenance=_provenance(),
        reason_code="family_needs_a_break",
        next_preference="resume_tomorrow",
    )

    assert feedback.requires_human_review is False
    assert feedback.may_mutate_business_state is False

    complaint = FeedbackSignal(
        feedback_id="feedback-002",
        target_type=FeedbackTargetType.RECOMMENDATION,
        target_id="decision-001",
        signal=FeedbackSignalType.COMPLAINT,
        scope=_scope(),
        idempotency_key=IdempotencyKey("tenant-a", "feedback-002"),
        provenance=_provenance(),
        reason_code="content_not_respectful",
    )
    assert complaint.requires_human_review is True

    with pytest.raises(ExperienceContractError, match="negative feedback"):
        FeedbackSignal(
            feedback_id="feedback-003",
            target_type=FeedbackTargetType.RECOMMENDATION,
            target_id="decision-001",
            signal=FeedbackSignalType.NOT_HELPFUL,
            scope=_scope(),
            idempotency_key=IdempotencyKey("tenant-a", "feedback-003"),
            provenance=_provenance(),
        )


def test_cross_tenant_and_cross_subject_joins_are_rejected() -> None:
    base = ExperienceEvent(
        event_id="evt-scope",
        event_type=ExperienceEventType.CONTENT_SELECTED,
        node=ExperienceNode.N1,
        scope=_scope(),
        idempotency_key=IdempotencyKey("tenant-a", "evt-scope"),
        provenance=_provenance(),
        actor_id="parent-a",
    )
    other_tenant = ExperienceEvent(
        event_id="evt-other-tenant",
        event_type=ExperienceEventType.CONTENT_SELECTED,
        node=ExperienceNode.N1,
        scope=_scope(tenant_id="tenant-b", family_id="family-b", subjects=("child-a",)),
        idempotency_key=IdempotencyKey("tenant-b", "evt-other-tenant"),
        provenance=_provenance(),
        actor_id="parent-b",
    )
    other_subject = ExperienceEvent(
        event_id="evt-other-subject",
        event_type=ExperienceEventType.CONTENT_SELECTED,
        node=ExperienceNode.N1,
        scope=_scope(subjects=("child-b",)),
        idempotency_key=IdempotencyKey("tenant-a", "evt-other-subject"),
        provenance=_provenance(),
        actor_id="parent-a",
    )

    with pytest.raises(ScopeMismatchError, match="CROSS_TENANT_SCOPE"):
        assert_scope_compatible(base, other_tenant)
    with pytest.raises(ScopeMismatchError, match="CROSS_SUBJECT_SCOPE"):
        assert_scope_compatible(base, other_subject)


def test_feedback_binding_rejects_cross_tenant_target() -> None:
    feedback = FeedbackSignal(
        feedback_id="feedback-cross",
        target_type=FeedbackTargetType.EVENT,
        target_id="evt-other-tenant",
        signal=FeedbackSignalType.HELPFUL,
        scope=_scope(),
        idempotency_key=IdempotencyKey("tenant-a", "feedback-cross"),
        provenance=_provenance(),
    )
    target = ExperienceEvent(
        event_id="evt-other-tenant",
        event_type=ExperienceEventType.CONTENT_SHOWN,
        node=ExperienceNode.N1,
        scope=_scope(tenant_id="tenant-b", family_id="family-b"),
        idempotency_key=IdempotencyKey("tenant-b", "evt-other-tenant"),
        provenance=_provenance(),
        actor_id="parent-b",
    )

    with pytest.raises(ScopeMismatchError, match="CROSS_TENANT_SCOPE"):
        feedback.assert_targets(target)


def test_idempotency_is_tenant_scoped_and_contract_rejects_wrong_tenant_key() -> None:
    store = InMemoryIdempotencyStore()
    assert store.check_and_reserve(IdempotencyKey("tenant-a", "same-request")) is True
    assert store.check_and_reserve(IdempotencyKey("tenant-a", "same-request")) is False
    assert store.check_and_reserve(IdempotencyKey("tenant-b", "same-request")) is True

    with pytest.raises(ScopeMismatchError, match="IDEMPOTENCY_TENANT_MISMATCH"):
        ExperienceEvent(
            event_id="evt-wrong-key",
            event_type=ExperienceEventType.ENTRY_OPENED,
            node=ExperienceNode.N0,
            scope=_scope(),
            idempotency_key=IdempotencyKey("tenant-b", "evt-wrong-key"),
            provenance=_provenance(),
            actor_id="parent-a",
        )


def test_invalid_locale_is_rejected_instead_of_falling_back_silently() -> None:
    with pytest.raises(ExperienceContractError, match="CONTENT_LOCALE_UNSUPPORTED"):
        ExperienceScope(
            global_id="g-1",
            tenant_id="tenant-a",
            region_id="CN",
            family_id="family-a",
            subject_ids=("child-a",),
            purpose="growth_support",
            consent_version="consent.v1",
            consent_granted=True,
            data_class="FAMILY_PRIVATE_TEXT",  # type: ignore[arg-type]
            locale="zh-CN",
            content_locale="not a locale",
            model_locale="zh-CN",
            policy_locale="zh-CN",
            deletion_ref=DeletionRef("del-001", "experience.v1"),
            correlation_id="corr-001",
            causation_id="cause-001",
        )


def test_supported_multimodal_input_and_output_carry_operation_provenance() -> None:
    for modality in (
        ExperienceModality.TEXT,
        ExperienceModality.VOICE,
        ExperienceModality.IMAGE,
        ExperienceModality.AUDIO,
        ExperienceModality.VIDEO,
        ExperienceModality.INTERACTIVE_CARD,
    ):
        media = _media(
            modality=modality,
            operation=ModalityOperation.OUTPUT,
            data_class="OPERATIONAL_TEXT",
        )
        assert media.modality is modality
        assert media.operation is ModalityOperation.OUTPUT
        assert media.provenance.provenance_ref
        assert media.deletion_ref.deletion_id


def test_unsupported_modality_is_rejected() -> None:
    with pytest.raises(ExperienceContractError, match="MEDIA_MODALITY_UNSUPPORTED"):
        _media(modality="pdf")  # type: ignore[arg-type]


def test_media_requires_consent_for_private_or_minor_input() -> None:
    with pytest.raises(ExperienceContractError, match="MEDIA_CONSENT_REQUIRED"):
        _media(consent_granted=False, data_class="MINOR_PERSONAL_DATA")


def test_expired_media_is_not_playable() -> None:
    now = datetime.now(UTC)
    media = _media(
        modality=ExperienceModality.VIDEO,
        operation=ModalityOperation.PLAYBACK,
        created_at=now.replace(year=now.year - 1),
        expires_at=now.replace(microsecond=0),
        data_class="OPERATIONAL_TEXT",
    )

    with pytest.raises(ExperienceContractError, match="MEDIA_EXPIRED"):
        media.assert_playable(now)


def test_cross_tenant_media_attachment_is_rejected() -> None:
    with pytest.raises(ScopeMismatchError, match="CROSS_TENANT_MEDIA_SCOPE"):
        ExperienceEvent(
            event_id="evt-media-cross",
            event_type=ExperienceEventType.CONTENT_SHOWN,
            node=ExperienceNode.N1,
            scope=_scope(),
            idempotency_key=IdempotencyKey("tenant-a", "evt-media-cross"),
            provenance=_provenance(),
            actor_id="parent-a",
            media_refs=(_media(tenant_id="tenant-b", family_id="family-b"),),
        )


def test_memory_scopes_are_explicit_bounded_and_delete_as_a_cascade() -> None:
    child_memory = _memory(level=MemoryLevel.M2_JOURNEY)
    relationship_memory = _memory(
        memory_scope=MemoryScope.FAMILY_RELATIONSHIP,
        subjects=("child-a", "guardian-a"),
        derived_memory_ids=("memory-ocr-001", "memory-transcript-002"),
    )

    assert child_memory.memory_scope is MemoryScope.CHILD
    assert child_memory.expires_at is not None
    assert child_memory.deletion_cascade_ids() == (
        "memory-001",
        "memory-transcript-001",
    )
    assert relationship_memory.deletion_cascade_ids() == (
        "memory-001",
        "memory-ocr-001",
        "memory-transcript-002",
    )


def test_memory_read_rejects_cross_tenant_subject_and_purpose_scope() -> None:
    memory = _memory()
    with pytest.raises(ScopeMismatchError, match="CROSS_TENANT_MEMORY_READ"):
        memory.assert_readable_by(
            _scope(tenant_id="tenant-b", family_id="family-b"),
            purpose="growth_support",
        )
    with pytest.raises(ScopeMismatchError, match="MEMORY_SUBJECT_READ_DENIED"):
        memory.assert_readable_by(_scope(subjects=("child-b",)), purpose="growth_support")
    with pytest.raises(ExperienceContractError, match="MEMORY_PURPOSE_MISMATCH"):
        memory.assert_readable_by(_scope(), purpose="assessment")


def test_memory_attachment_rejects_cross_tenant_scope() -> None:
    with pytest.raises(ScopeMismatchError, match="CROSS_TENANT_MEMORY_SCOPE"):
        ExperienceEvent(
            event_id="evt-memory-cross",
            event_type=ExperienceEventType.CONTENT_SHOWN,
            node=ExperienceNode.N1,
            scope=_scope(),
            idempotency_key=IdempotencyKey("tenant-a", "evt-memory-cross"),
            provenance=_provenance(),
            actor_id="parent-a",
            memory_refs=(_memory(tenant_id="tenant-b", family_id="family-b"),),
        )


def test_memory_read_rejects_expiry_and_missing_consent() -> None:
    now = datetime.now(UTC)
    expired = _memory(
        created_at=now.replace(year=now.year - 1),
        expires_at=now.replace(microsecond=0),
    )
    with pytest.raises(ExperienceContractError, match="MEMORY_EXPIRED"):
        expired.assert_readable_by(_scope(), purpose="growth_support", moment=now)

    with pytest.raises(ExperienceContractError, match="MEMORY_CONSENT_REQUIRED"):
        _memory(consent_granted=False)


def test_memory_scope_and_unbounded_retention_are_rejected() -> None:
    with pytest.raises(ExperienceContractError, match="requires at least two"):
        _memory(
            memory_scope=MemoryScope.FAMILY_RELATIONSHIP,
            subjects=("child-a",),
        )
    with pytest.raises(ExperienceContractError, match="MEMORY_EXPIRY_REQUIRED"):
        _memory(unbounded=True, created_at=datetime.now(UTC), derived_memory_ids=())
