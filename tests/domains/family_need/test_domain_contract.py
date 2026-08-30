from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.domains.family_need.application.ports import (
    NeedClarificationInput,
    NeedProfileInput,
    NeedSignalInput,
    SolutionDraftInput,
)
from backend.domains.family_need.application.service import FamilyNeedApplicationService
from backend.domains.family_need.domain.entities import (
    FamilyNeed,
    NeedProfile,
    NeedSignal,
    SolutionDraft,
)
from backend.domains.family_need.domain.errors import (
    FamilyNeedConflictError,
    FamilyNeedForbiddenError,
)
from backend.domains.family_need.domain.value_objects import (
    AcceptanceCriterion,
    ActorType,
    DataClass,
    EmotionalGate,
    EvidenceKind,
    EvidenceRef,
    NeedCategory,
    NeedComplexity,
    NeedContext,
    NeedSignalSource,
    NeedStatus,
    NeedUrgency,
    RiskLevel,
    SolutionComponentRef,
    SupplyShape,
)
from backend.domains.family_need.infrastructure.fake_repository import (
    FakeFamilyNeedPolicy,
    FakeFamilyNeedRepository,
    FakeSupplyReferencePort,
)


def context(
    *,
    tenant_id: str = "tenant-a",
    family_id: str = "family-a",
    actor_type: ActorType = ActorType.FAMILY_GUARDIAN,
    data_class: DataClass = DataClass.MINOR_PERSONAL_DATA,
) -> NeedContext:
    return NeedContext(
        tenant_id=tenant_id,
        family_id=family_id,
        subject_person_ids=("child-a",),
        purpose="FAMILY_NEED",
        consent_version="consent-v1",
        data_class=data_class,
        actor_id="guardian-a",
        actor_type=actor_type,
        provenance_ref="family-expression-1",
        correlation_id="corr-1",
    )


def captured_need() -> tuple[NeedSignal, FamilyNeed]:
    signal = NeedSignal.capture(
        context=context(),
        source=NeedSignalSource.FAMILY_EXPRESSED,
        raw_text="我们最近在作业和沟通上都很累，希望先有一个小改变。",
        signal_id="signal-1",
    )
    need = FamilyNeed.from_signal(
        signal,
        statement="晚间作业沟通容易升级成争吵",
        desired_outcome="一家人可以更平静地完成一次晚间沟通",
        category=NeedCategory.EDUCATION,
        need_id="need-1",
    )
    return signal, need


def confirmed_need() -> FamilyNeed:
    _, need = captured_need()
    return need.start_clarification().confirm("guardian-a")


def profile_for(need: FamilyNeed) -> NeedProfile:
    return NeedProfile.from_need(
        need,
        urgency=NeedUrgency.SOON,
        complexity=NeedComplexity.SIMPLE,
        risk_level=RiskLevel.LOW,
        preferred_shapes=(SupplyShape.PRODUCT, SupplyShape.SERVICE),
        required_capability_keys=("family_communication",),
        confirmed_by_actor_id="guardian-a",
        profile_id="profile-1",
    )


def test_successfully_captures_confirms_profiles_and_drafts_solution() -> None:
    evidence = EvidenceRef(
        media_ref="media-1",
        kind=EvidenceKind.VOICE_TRANSCRIPT,
        tenant_id="tenant-a",
        family_id="family-a",
        provenance_ref="voice-upload-1",
        consent_version="consent-v1",
        data_class=DataClass.MINOR_PERSONAL_DATA,
    )
    signal, _ = captured_need()
    signal = replace(signal, evidence_refs=(evidence,))
    need = FamilyNeed.from_signal(
        signal,
        statement="晚间作业沟通容易升级成争吵",
        desired_outcome="一家人可以更平静地完成一次晚间沟通",
        category=NeedCategory.EDUCATION,
        need_id="need-1",
    )
    confirmed = need.start_clarification().confirm("guardian-a")
    profile = profile_for(confirmed)
    draft = SolutionDraft.propose(
        need=confirmed,
        profile=profile,
        shape=SupplyShape.PRODUCT,
        components=(
            SolutionComponentRef(
                component_id="education-kit-1", shape=SupplyShape.PRODUCT, version="v1"
            ),
        ),
        acceptance_criteria=(AcceptanceCriterion("criterion-1", "家庭确认完成一次小行动"),),
        draft_id="draft-1",
    )

    assert signal.status.value == "ACTIVE"
    assert signal.evidence_refs[0].kind is EvidenceKind.VOICE_TRANSCRIPT
    assert need.evidence_refs == signal.evidence_refs
    assert confirmed.status is NeedStatus.CONFIRMED
    assert profile.need_id == confirmed.need_id
    assert draft.may_execute is False
    approved = draft.submit_for_family_review(profile=profile).approve("guardian-a")
    assert approved.may_execute is True
    assert approved.approved_by_actor_id == "guardian-a"
    assert approved.emotional_gate is EmotionalGate.E3_VALUE_CONFIRMED


def test_rejection_pause_and_resume_are_explicit_and_reversible() -> None:
    _, need = captured_need()
    rejected = need.start_clarification().reject("家庭暂时不想继续澄清")
    assert rejected.status is NeedStatus.REJECTED
    with pytest.raises(FamilyNeedConflictError, match="need_transition_rejected_to_paused_denied"):
        rejected.pause("should not silently resume")

    paused = need.pause("本周家庭需要休息")
    assert paused.status is NeedStatus.PAUSED
    resumed = paused.resume()
    assert resumed.status is NeedStatus.CLARIFYING
    assert resumed.pause_reason is None


def test_ai_cannot_write_need_signal_or_confirm_need() -> None:
    with pytest.raises(ValueError, match="ai_cannot_write_family_need_fact"):
        NeedSignal.capture(
            context=context(actor_type=ActorType.AI),
            source=NeedSignalSource.FAMILY_CONVERSATION,
            raw_text="AI inferred a need",
        )

    _, need = captured_need()
    clarified = need.start_clarification()
    with pytest.raises(FamilyNeedForbiddenError, match="ai_cannot_write_family_need_fact"):
        clarified.confirm("agent-1", actor_type=ActorType.AI)


@pytest.mark.asyncio
async def test_cross_tenant_reads_and_policy_checks_fail_closed() -> None:
    repository = FakeFamilyNeedRepository()
    signal, _ = captured_need()

    await repository.save_signal(signal)
    hidden = await repository.get_signal(
        tenant_id="tenant-b", family_id="family-a", signal_id=signal.signal_id
    )
    assert hidden is None

    policy = FakeFamilyNeedPolicy()
    policy.bind_family("tenant-a", "family-a")
    policy.grant_actor("family-a", "guardian-a", ActorType.FAMILY_GUARDIAN)
    with pytest.raises(FamilyNeedForbiddenError, match="tenant_family_scope_denied"):
        await policy.assert_tenant_family_scope(
            context=context(tenant_id="tenant-b"), actor_id="guardian-a"
        )


def test_expired_signal_is_rejected_and_stale_profile_is_not_reused() -> None:
    expired = NeedSignal.capture(
        context=context(),
        source=NeedSignalSource.FAMILY_SEARCH,
        raw_text="过期的需求",
        expires_at=datetime.now(UTC) - timedelta(minutes=1),
    )
    assert expired.is_expired()
    with pytest.raises(FamilyNeedConflictError, match="need_signal_expired"):
        FamilyNeed.from_signal(expired, statement="x", desired_outcome="y")

    need = confirmed_need()
    profile = profile_for(need)
    stale_profile = replace(profile, version=profile.version + 1)
    with pytest.raises(FamilyNeedConflictError, match="family_need_version_stale"):
        profile.ensure_current(replace(need, version=need.version + 1))
    draft = SolutionDraft.propose(
        need=need,
        profile=profile,
        shape=SupplyShape.PRODUCT,
        components=(SolutionComponentRef("kit", SupplyShape.PRODUCT, "v1"),),
    )
    with pytest.raises(FamilyNeedConflictError, match="family_need_version_stale"):
        draft.ensure_fresh(stale_profile)


def test_economic_choice_requires_emotional_value_gate() -> None:
    need = confirmed_need()
    profile = profile_for(need)
    with pytest.raises(FamilyNeedForbiddenError, match="economic_choice_before_value_confirmed"):
        SolutionDraft.propose(
            need=need,
            profile=profile,
            shape=SupplyShape.PRODUCT,
            components=(SolutionComponentRef("paid-kit", SupplyShape.PRODUCT, "v1"),),
            commercial_intent=True,
        )


def test_emotional_gates_progress_one_step_before_economic_choice() -> None:
    unready = confirmed_need()
    with pytest.raises(FamilyNeedConflictError, match="emotional_gate_cannot_skip"):
        unready.advance_emotional_gate(EmotionalGate.E4_ECONOMIC_CHOICE, "guardian-a")
    need = confirmed_need().advance_emotional_gate(EmotionalGate.E3_VALUE_CONFIRMED, "guardian-a")
    assert need.emotional_gate is EmotionalGate.E3_VALUE_CONFIRMED
    with pytest.raises(FamilyNeedConflictError, match="economic_gate_requires_solution_context"):
        need.advance_emotional_gate(EmotionalGate.E4_ECONOMIC_CHOICE, "guardian-a")


def test_media_without_consent_expired_or_cross_tenant_is_rejected() -> None:
    base = {
        "media_ref": "image-1",
        "kind": EvidenceKind.IMAGE_EVIDENCE,
        "tenant_id": "tenant-a",
        "family_id": "family-a",
        "provenance_ref": "upload-1",
        "data_class": DataClass.MINOR_PERSONAL_DATA,
    }
    for overrides, code in (
        ({"consent_version": None}, "media_consent_required"),
        ({"consent_version": "consent-v1", "authorized": False}, "media_consent_required"),
        (
            {
                "consent_version": "consent-v1",
                "expires_at": datetime.now(UTC) - timedelta(minutes=1),
            },
            "media_evidence_expired",
        ),
        ({"consent_version": "consent-v1", "tenant_id": "tenant-b"}, "media_tenant_scope_denied"),
    ):
        evidence = EvidenceRef(**(base | overrides))
        with pytest.raises(FamilyNeedForbiddenError, match=code):
            NeedSignal.capture(
                context=context(),
                source=NeedSignalSource.FAMILY_CONVERSATION,
                raw_text="带媒体证据的表达",
                evidence_refs=(evidence,),
            )


@pytest.mark.asyncio
async def test_supply_reference_port_returns_explicit_resource_gap() -> None:
    reference = FakeSupplyReferencePort()
    component = SolutionComponentRef("teacher-session", SupplyShape.SERVICE, "v1")
    reference.add_component(component, tenant_id="tenant-a")
    reference.set_capacity("teacher-session", 0)
    gap = await reference.check_resource_capacity(
        tenant_id="tenant-a",
        family_id="family-a",
        need_id="need-1",
        component_refs=(component,),
    )
    assert gap is not None
    assert gap.need_id == "need-1"
    assert gap.reason.value == "NO_CAPACITY"


def _service_fixture() -> tuple[
    FamilyNeedApplicationService, FakeFamilyNeedRepository, FakeFamilyNeedPolicy
]:
    repository = FakeFamilyNeedRepository()
    policy = FakeFamilyNeedPolicy()
    policy.bind_family("tenant-a", "family-a")
    policy.grant_actor("family-a", "guardian-a", ActorType.FAMILY_GUARDIAN)
    policy.add_subject("family-a", "child-a")
    policy.grant_consent("family-a", "child-a", "FAMILY_NEED", "consent-v1")
    return FamilyNeedApplicationService(repository, policy), repository, policy


@pytest.mark.asyncio
async def test_application_service_closes_n0_to_n1_and_emits_events() -> None:
    service, repository, _ = _service_fixture()
    command = NeedSignalInput(
        context=context(),
        source=NeedSignalSource.FAMILY_EXPRESSED,
        raw_text="我们很累，希望今晚少一次争吵。",
        statement="晚间沟通容易升级",
        desired_outcome="今晚完成一次平静的沟通",
        idempotency_key="capture-1",
    )

    result = await service.capture_signal(command)
    assert result.replayed is False
    assert result.need.status is NeedStatus.CAPTURED
    assert [event.event_name for event in repository.events] == [
        "family_need.signal_captured",
        "family_need.created",
    ]
    assert repository.events[0].tenant_id == "tenant-a"
    assert repository.events[0].purpose == "FAMILY_NEED"
    assert repository.events[0].consent_version == "consent-v1"

    replay = await service.capture_signal(command)
    assert replay.replayed is True
    assert replay.signal.signal_id == result.signal.signal_id
    assert len(repository.signals) == 1
    assert len(repository.events) == 2


@pytest.mark.asyncio
async def test_application_service_rejects_idempotency_payload_mismatch() -> None:
    service, _, _ = _service_fixture()
    base = NeedSignalInput(
        context=context(),
        source=NeedSignalSource.FAMILY_EXPRESSED,
        raw_text="原始表达",
        statement="需要陪伴",
        desired_outcome="找到一件小行动",
        idempotency_key="capture-2",
    )
    await service.capture_signal(base)
    with pytest.raises(FamilyNeedConflictError, match="idempotency_payload_mismatch"):
        await service.capture_signal(replace(base, raw_text="被篡改的表达"))


@pytest.mark.asyncio
async def test_idempotency_replay_still_requires_current_actor_scope() -> None:
    service, _, _ = _service_fixture()
    command = NeedSignalInput(
        context=context(),
        source=NeedSignalSource.FAMILY_EXPRESSED,
        raw_text="家庭表达",
        statement="需要支持",
        desired_outcome="完成小行动",
        idempotency_key="capture-secure",
    )
    await service.capture_signal(command)
    with pytest.raises(FamilyNeedForbiddenError, match="actor_family_scope_denied"):
        await service.capture_signal(
            replace(command, context=replace(command.context, actor_id="other-actor"))
        )


@pytest.mark.asyncio
async def test_application_service_fails_closed_without_tenant_or_consent() -> None:
    service, _, policy = _service_fixture()
    no_binding = replace(context(), tenant_id="tenant-other")
    with pytest.raises(FamilyNeedForbiddenError, match="tenant_family_scope_denied"):
        await service.capture_signal(
            NeedSignalInput(
                context=no_binding,
                source=NeedSignalSource.FAMILY_EXPRESSED,
                raw_text="越权表达",
                statement="越权需求",
                desired_outcome="不应创建",
            )
        )

    policy.grants.clear()
    with pytest.raises(FamilyNeedForbiddenError, match="consent_not_granted"):
        await service.capture_signal(
            NeedSignalInput(
                context=context(),
                source=NeedSignalSource.FAMILY_EXPRESSED,
                raw_text="没有同意",
                statement="需求",
                desired_outcome="结果",
            )
        )


@pytest.mark.asyncio
async def test_application_service_composes_service_draft_with_idempotent_replay() -> None:
    repository = FakeFamilyNeedRepository()
    policy = FakeFamilyNeedPolicy()
    policy.bind_family("tenant-a", "family-a")
    policy.grant_actor("family-a", "guardian-a", ActorType.FAMILY_GUARDIAN)
    policy.add_subject("family-a", "child-a")
    policy.grant_consent("family-a", "child-a", "FAMILY_NEED", "consent-v1")
    supply = FakeSupplyReferencePort()
    component = SolutionComponentRef("coach-1", SupplyShape.SERVICE, "v1")
    supply.add_component(component, tenant_id="tenant-a")
    service = FamilyNeedApplicationService(repository, policy, supply_port=supply)

    captured = await service.capture_signal(
        NeedSignalInput(
            context=context(),
            source=NeedSignalSource.FAMILY_EXPRESSED,
            raw_text="最近沟通很累",
            statement="需要一个沟通陪练",
            desired_outcome="一起完成一次平静沟通",
            idempotency_key="n0-1",
        )
    )
    confirmed = await service.clarify_need(
        NeedClarificationInput(
            need_id=captured.need.need_id,
            context=context(),
            statement="需要一个沟通陪练",
            desired_outcome="一起完成一次平静沟通",
            subject_person_ids=("child-a",),
            expected_version=captured.need.version,
            idempotency_key="n1-1",
        )
    )
    profile = await service.profile_need(
        NeedProfileInput(
            need_id=confirmed.need_id,
            context=context(),
            expected_need_version=confirmed.version,
            urgency="SOON",
            complexity="SIMPLE",
            risk_level="LOW",
            preferred_shapes=(SupplyShape.SERVICE,),
            required_capability_keys=("family_communication",),
            idempotency_key="n2-1",
        )
    )
    draft_input = SolutionDraftInput(
        need_id=confirmed.need_id,
        profile_id=profile.profile_id,
        context=context(),
        expected_profile_version=profile.version,
        shape=SupplyShape.SERVICE,
        component_refs=(component,),
        idempotency_key="n3-1",
    )
    result = await service.draft_solution(draft_input)
    assert result.resource_gap is None
    assert result.draft is not None
    assert result.draft.shape is SupplyShape.SERVICE
    assert result.draft.components == (component,)
    replay = await service.draft_solution(draft_input)
    assert replay.replayed is True
    assert replay.draft is not None
    assert replay.draft.draft_id == result.draft.draft_id
    assert len(repository.solution_drafts) == 1


@pytest.mark.asyncio
async def test_application_service_returns_resource_gap_without_writing_draft() -> None:
    repository = FakeFamilyNeedRepository()
    policy = FakeFamilyNeedPolicy()
    policy.bind_family("tenant-a", "family-a")
    policy.grant_actor("family-a", "guardian-a", ActorType.FAMILY_GUARDIAN)
    policy.add_subject("family-a", "child-a")
    policy.grant_consent("family-a", "child-a", "FAMILY_NEED", "consent-v1")
    supply = FakeSupplyReferencePort()
    service = FamilyNeedApplicationService(repository, policy, supply_port=supply)
    captured = await service.capture_signal(
        NeedSignalInput(
            context=context(),
            source=NeedSignalSource.FAMILY_EXPRESSED,
            raw_text="找不到合适的资源",
            statement="需要服务支持",
            desired_outcome="找到可行的下一步",
            idempotency_key="gap-n0",
        )
    )
    confirmed = await service.clarify_need(
        NeedClarificationInput(
            need_id=captured.need.need_id,
            context=context(),
            statement="需要服务支持",
            desired_outcome="找到可行的下一步",
            subject_person_ids=("child-a",),
            expected_version=captured.need.version,
        )
    )
    profile = await service.profile_need(
        NeedProfileInput(
            need_id=confirmed.need_id,
            context=context(),
            expected_need_version=confirmed.version,
            urgency="SOON",
            complexity="SIMPLE",
            risk_level="LOW",
            preferred_shapes=(SupplyShape.SERVICE,),
        )
    )
    result = await service.draft_solution(
        SolutionDraftInput(
            need_id=confirmed.need_id,
            profile_id=profile.profile_id,
            context=context(),
            expected_profile_version=profile.version,
            shape=SupplyShape.SERVICE,
            component_refs=(SolutionComponentRef("missing", SupplyShape.SERVICE, "v1"),),
            idempotency_key="gap-n3",
        )
    )
    assert result.draft is None
    assert result.resource_gap is not None
    assert result.resource_gap.reason.value == "NO_MATCHING_CAPABILITY"
    assert repository.solution_drafts == {}
    assert any(event.event_name == "family_need.resource_gap" for event in repository.events)


@pytest.mark.asyncio
async def test_application_service_rejects_stale_profile_before_matching_resources() -> None:
    repository = FakeFamilyNeedRepository()
    policy = FakeFamilyNeedPolicy()
    policy.bind_family("tenant-a", "family-a")
    policy.grant_actor("family-a", "guardian-a", ActorType.FAMILY_GUARDIAN)
    policy.add_subject("family-a", "child-a")
    policy.grant_consent("family-a", "child-a", "FAMILY_NEED", "consent-v1")
    supply = FakeSupplyReferencePort()
    component = SolutionComponentRef("kit-1", SupplyShape.PRODUCT, "v1")
    supply.add_component(component, tenant_id="tenant-a")
    service = FamilyNeedApplicationService(repository, policy, supply_port=supply)
    captured = await service.capture_signal(
        NeedSignalInput(
            context=context(),
            source=NeedSignalSource.FAMILY_EXPRESSED,
            raw_text="需求",
            statement="需要产品",
            desired_outcome="找到工具",
            idempotency_key="stale-n0",
        )
    )
    confirmed = await service.clarify_need(
        NeedClarificationInput(
            need_id=captured.need.need_id,
            context=context(),
            statement="需要产品",
            desired_outcome="找到工具",
            subject_person_ids=("child-a",),
            expected_version=captured.need.version,
        )
    )
    profile = await service.profile_need(
        NeedProfileInput(
            need_id=confirmed.need_id,
            context=context(),
            expected_need_version=confirmed.version,
            urgency="SOON",
            complexity="SIMPLE",
            risk_level="LOW",
            preferred_shapes=(SupplyShape.PRODUCT,),
        )
    )
    current_need = replace(confirmed, version=confirmed.version + 1)
    await repository.save_need(current_need)
    with pytest.raises(FamilyNeedConflictError, match="family_need_version_stale"):
        await service.draft_solution(
            SolutionDraftInput(
                need_id=current_need.need_id,
                profile_id=profile.profile_id,
                context=context(),
                expected_profile_version=profile.version,
                shape=SupplyShape.PRODUCT,
                component_refs=(component,),
            )
        )
