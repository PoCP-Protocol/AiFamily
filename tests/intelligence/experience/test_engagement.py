from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.experience.contracts import ExperienceEventType
from backend.intelligence.experience.engagement import (
    EngagementAuthorization,
    EngagementContractError,
    EngagementDraft,
    EngagementDraftApplication,
    EngagementDraftCommand,
    EngagementDraftService,
)
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from tests.intelligence.experience.test_gateway import _event, _scope
from tests.intelligence.model_gateway.test_fail_closed import build


def _command(*, events=None, **overrides: object) -> EngagementDraftCommand:
    selected = tuple(
        events or (_event(event_id="action-1", event_type=ExperienceEventType.ACTION_COMPLETED),)
    )
    values: dict[str, object] = {
        "request_id": "engagement-001",
        "provider_id": "fake-deterministic",
        "authorization": EngagementAuthorization(
            scope=selected[0].scope,
            authorization_ref="auth-001",
            actor_id="guardian-a",
            authorized_event_ids=tuple(event.event_id for event in selected),
        ),
        "events": selected,
        "context_snapshot_ref": "ctx-engagement-001",
    }
    values.update(overrides)
    return EngagementDraftCommand(**values)  # type: ignore[arg-type]


def _output(*, evidence_refs: list[str] | None = None) -> dict[str, object]:
    candidate = {"candidate_id": "achievement-1", "text": "记录这次尝试"}
    if evidence_refs is not None:
        candidate["evidence_refs"] = evidence_refs
    return {
        "pacing": [{"candidate_id": "pace-1", "text": "保持轻量节奏"}],
        "instant_feedback": [{"candidate_id": "feedback-1", "text": "看见一次尝试"}],
        "growth_narrative": [{"candidate_id": "story-1", "text": "今天形成了一个小线索"}],
        "difficulty_adjustment": [{"candidate_id": "difficulty-1", "text": "下一步减少一个变量"}],
        "achievement_candidates": [candidate],
    }


@pytest.mark.asyncio
async def test_engagement_service_returns_draft_candidates_bound_to_event() -> None:
    event = _event(event_id="action-1", event_type=ExperienceEventType.ACTION_COMPLETED)
    provider = FakeProvider({"family-engagement-draft": _output(evidence_refs=["action-1"])})
    result = await EngagementDraftService(build(provider)).generate_draft(_command(events=(event,)))

    assert isinstance(result, EngagementDraft)
    assert result.request_id == "engagement-001"
    assert result.evidence_event_ids == ("action-1",)
    assert result.achievement_candidates[0]["evidence_refs"] == ["action-1"]
    assert result.draft.status == "DRAFT"
    assert result.draft.may_mutate_business_state is False
    request = provider.invocations[0]
    assert request.input_refs == ("action-1",)
    assert request.payload["events"][0]["evidence_ref"] == "experience-event:action-1"


def test_command_rejects_event_outside_explicit_authorization() -> None:
    event = _event(event_id="action-1")
    authorization = EngagementAuthorization(
        scope=event.scope,
        authorization_ref="auth-001",
        actor_id="guardian-a",
        authorized_event_ids=("different-event",),
    )
    with pytest.raises(EngagementContractError, match="EVENT_NOT_AUTHORIZED"):
        _command(authorization=authorization, events=(event,))


def test_command_rejects_cross_scope_event() -> None:
    first = _event(event_id="action-1")
    other = _event(event_id="action-2", scope=_scope(family_id="family-b"))
    with pytest.raises(EngagementContractError, match="EVENT_SCOPE_NOT_AUTHORIZED"):
        _command(events=(first, other))


@pytest.mark.asyncio
async def test_achievement_candidate_must_cite_real_event() -> None:
    provider = FakeProvider({"family-engagement-draft": _output(evidence_refs=["unknown-event"])})
    with pytest.raises(EngagementContractError, match="ACHIEVEMENT_EVIDENCE_NOT_REAL_EVENT"):
        await EngagementDraftService(build(provider)).generate_draft(_command())


@pytest.mark.asyncio
async def test_achievement_candidate_requires_evidence_reference() -> None:
    provider = FakeProvider({"family-engagement-draft": _output()})
    with pytest.raises(EngagementContractError, match="ACHIEVEMENT_EVIDENCE_REQUIRED"):
        await EngagementDraftService(build(provider)).generate_draft(_command())


@pytest.mark.asyncio
async def test_engagement_rechecks_authorization_expiry_before_gateway_call() -> None:
    event = _event(event_id="action-1", event_type=ExperienceEventType.ACTION_COMPLETED)
    authorization = EngagementAuthorization(
        scope=event.scope,
        authorization_ref="auth-expiring",
        actor_id="guardian-a",
        authorized_event_ids=(event.event_id,),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    provider = FakeProvider({"family-engagement-draft": _output(evidence_refs=[event.event_id])})
    service = EngagementDraftService(
        build(provider), clock=lambda: datetime.now(UTC) + timedelta(minutes=10)
    )

    with pytest.raises(EngagementContractError, match="AUTHORIZATION_EXPIRED"):
        await service.generate_draft(_command(events=(event,), authorization=authorization))

    assert provider.invocations == []


@pytest.mark.asyncio
async def test_engagement_application_reads_events_from_server_port_in_requested_order() -> None:
    first = _event(event_id="action-1", event_type=ExperienceEventType.ACTION_COMPLETED)
    second = _event(event_id="action-2", event_type=ExperienceEventType.ACTION_STARTED)

    class Reader:
        def __init__(self) -> None:
            self.calls: list[tuple[str, ...]] = []

        async def read(self, *, scope, event_ids):  # type: ignore[no-untyped-def]
            assert scope == first.scope
            self.calls.append(event_ids)
            return (second, first)

    provider = FakeProvider(
        {"family-engagement-draft": _output(evidence_refs=["action-1", "action-2"])}
    )
    reader = Reader()
    result = await EngagementDraftApplication(
        EngagementDraftService(build(provider)), reader
    ).generate_draft(
        request_id="engagement-read-001",
        provider_id="fake-deterministic",
        scope=first.scope,
        actor_id="guardian-a",
        authorization_ref="auth-001",
        event_ids=("action-1", "action-2"),
        context_snapshot_ref="ctx-engagement-read-001",
    )

    assert result.evidence_event_ids == ("action-1", "action-2")
    assert reader.calls == [("action-1", "action-2")]
    assert provider.invocations[0].input_refs == ("action-1", "action-2")


@pytest.mark.asyncio
async def test_engagement_application_rejects_reader_missing_requested_event() -> None:
    event = _event(event_id="action-1", event_type=ExperienceEventType.ACTION_COMPLETED)

    class Reader:
        def read(self, *, scope, event_ids):  # type: ignore[no-untyped-def]
            return ()

    provider = FakeProvider({"family-engagement-draft": _output(evidence_refs=["action-1"])})
    application = EngagementDraftApplication(EngagementDraftService(build(provider)), Reader())

    with pytest.raises(EngagementContractError, match="EXPERIENCE_EVENTS_NOT_FOUND"):
        await application.generate_draft(
            request_id="engagement-read-missing",
            provider_id="fake-deterministic",
            scope=event.scope,
            actor_id="guardian-a",
            authorization_ref="auth-001",
            event_ids=("action-1",),
            context_snapshot_ref="ctx-engagement-read-missing",
        )
    assert provider.invocations == []
