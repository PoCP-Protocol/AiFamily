from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from backend.apps.family_api.understanding_review import (
    ConfirmUnderstandingApplication,
    UnderstandingConfirmationRejected,
)
from backend.domains.assessment.application.growth_intent_handoff import (
    ViewedUnderstandingSignal,
)
from backend.domains.assessment.application.reviewed_understanding_signals import (
    RecordReviewedUnderstandingInput,
    RecordReviewedUnderstandingService,
)
from backend.intelligence.family_understanding.api import ReviewUnderstandingCommand
from backend.intelligence.family_understanding.snapshot import UnderstandingDraftSnapshot
from backend.platform.authorization.policy import PolicyEngine, PolicyRule
from backend.platform.authorization.review_receipts import (
    REVIEW_ACTION,
    REVIEW_RESOURCE_TYPE,
    ReviewReceiptIssuer,
)
from backend.platform.identity.context import ActorType

NOW = datetime(2026, 9, 1, 8, tzinfo=UTC)
EXPIRY = datetime(2026, 9, 2, 8, tzinfo=UTC)


def snapshot(**changes) -> UnderstandingDraftSnapshot:
    value = UnderstandingDraftSnapshot(
        tenant_id="11111111-1111-4111-8111-111111111111",
        family_id="22222222-2222-4222-8222-222222222222",
        understanding_run_ref="understanding-run-v1",
        artifact_ref="artifact-v1",
        artifact_version=1,
        prior_artifact_ref=None,
        provenance_ref="air-provenance:v1:sha256:v1",
        subject_person_id="33333333-3333-4333-8333-333333333333",
        desired_change="希望写作业开始时少一点冲突。",
        need_type="FAMILY_ROUTINE",
        required_capability_keys=("routine_reflection",),
        evidence_refs=("guardian-input-1",),
        source_refs=("guardian-input-1",),
        knowledge_refs=("knowledge-reviewed-1",),
        provider_id="approved-provider",
        model="understanding-model",
        model_version="2026-09",
        prompt_version="problem-understanding-v1",
        schema_version="family-understanding-v1",
        context_snapshot_ref="context-v1",
        expires_at=EXPIRY,
    )
    return replace(value, **changes)


class Snapshots:
    def __init__(self, value: UnderstandingDraftSnapshot | None) -> None:
        self.value = value

    async def load(self, **binding) -> UnderstandingDraftSnapshot | None:
        value = self.value
        if value is None:
            return None
        if any(getattr(value, key) != expected for key, expected in binding.items()):
            return None
        return value


class Signals:
    def __init__(self) -> None:
        self.commands: list[RecordReviewedUnderstandingInput] = []

    async def save_viewed_signal(
        self, command: RecordReviewedUnderstandingInput
    ) -> ViewedUnderstandingSignal:
        self.commands.append(command)
        return ViewedUnderstandingSignal(
            tenant_id=command.tenant_id,
            family_id=command.family_id,
            assessment_session_id=command.assessment_session_id,
            understanding_run_ref=command.understanding_run_ref,
            signal_ref=command.signal_ref,
            signal_version=command.signal_version,
            scope_ref=command.scope_ref,
            reviewed_draft_ref=command.reviewed_draft_ref,
            draft_version=command.draft_version,
            provenance_ref=command.provenance_ref,
            human_gate_receipt_ref=command.human_gate_receipt_ref,
            human_gate_effective_status=command.human_gate_effective_status,
            reviewed_by_actor_id=command.reviewed_by_actor_id,
            subject_person_id=command.subject_person_id,
            need_type=command.need_type,
            goal_text=command.goal_text,
            required_capability_keys=command.required_capability_keys,
            evidence_refs=command.evidence_refs,
            reviewed_at=command.reviewed_at,
            expires_at=command.expires_at,
        )

    async def load_confirmation_replay(self, **binding) -> ViewedUnderstandingSignal | None:
        for command in self.commands:
            expected = {
                "tenant_id": command.tenant_id,
                "family_id": command.family_id,
                "understanding_run_ref": command.understanding_run_ref,
                "artifact_ref": command.reviewed_draft_ref,
                "artifact_version": command.draft_version,
                "provenance_ref": command.provenance_ref,
                "actor_id": command.reviewed_by_actor_id,
                "view_event_ref": command.view_event_ref,
            }
            if expected == binding:
                signal = await self.save_viewed_signal(command)
                self.commands.pop()
                return signal
        return None


def command(**changes) -> ReviewUnderstandingCommand:
    value = ReviewUnderstandingCommand(
        tenant_id=snapshot().tenant_id,
        family_id=snapshot().family_id,
        actor_id=snapshot().subject_person_id,
        subject_person_id=snapshot().subject_person_id,
        consent_ref="consent-current",
        artifact_ref="artifact-v1",
        artifact_version=1,
        provenance_ref="air-provenance:v1:sha256:v1",
        view_event_ref="view-event-v1",
    )
    return replace(value, **changes)


def application(
    value: UnderstandingDraftSnapshot | None, signals: Signals
) -> ConfirmUnderstandingApplication:
    policy = PolicyEngine()
    policy.register(
        PolicyRule(
            action=REVIEW_ACTION,
            resource_type=REVIEW_RESOURCE_TYPE,
            allowed_actor_types=frozenset({ActorType.HUMAN}),
            human_only=True,
        )
    )
    return ConfirmUnderstandingApplication(
        Snapshots(value),
        ReviewReceiptIssuer(policy, signing_key=b"confirmation-test-key-32-bytes!!"),
        RecordReviewedUnderstandingService(signals),
        confirmation_replays=signals,
        clock=lambda: NOW,
    )


@pytest.mark.asyncio
async def test_confirmation_uses_only_server_snapshot_and_records_problem_scope() -> None:
    signals = Signals()
    result = await application(snapshot(), signals).review(command())

    assert result.status == "EFFECTIVE"
    assert result.scope_ref.endswith("/problem-understanding")
    assert result.receipt_ref.startswith("review-receipt:v1:sha256:")
    recorded = signals.commands[0]
    assert recorded.assessment_session_id is None
    assert recorded.understanding_run_ref == "understanding-run-v1"
    assert recorded.goal_text == "希望写作业开始时少一点冲突。"
    assert recorded.evidence_refs == ("guardian-input-1",)


@pytest.mark.asyncio
async def test_same_exact_confirmation_is_replay_stable() -> None:
    signals = Signals()
    service = application(snapshot(), signals)

    first = await service.review(command())
    replay = await service.review(command())

    assert replay.receipt_ref == first.receipt_ref
    assert len(signals.commands) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "changed",
    [
        {"family_id": "44444444-4444-4444-8444-444444444444"},
        {"artifact_version": 2},
        {"provenance_ref": "air-provenance:v1:sha256:v2"},
    ],
)
async def test_cross_scope_or_stale_binding_cannot_confirm(changed: dict[str, object]) -> None:
    with pytest.raises(
        UnderstandingConfirmationRejected, match="UNDERSTANDING_SNAPSHOT_NOT_EFFECTIVE"
    ):
        await application(snapshot(), Signals()).review(command(**changed))


@pytest.mark.asyncio
async def test_v1_receipt_is_not_inherited_by_v2() -> None:
    signals = Signals()
    v1 = await application(snapshot(), signals).review(command())
    v2_snapshot = snapshot(
        understanding_run_ref="understanding-run-v2",
        artifact_ref="artifact-v2",
        artifact_version=2,
        prior_artifact_ref="artifact-v1",
        provenance_ref="air-provenance:v1:sha256:v2",
    )
    v2 = await application(v2_snapshot, signals).review(
        command(
            artifact_ref="artifact-v2",
            artifact_version=2,
            provenance_ref="air-provenance:v1:sha256:v2",
            view_event_ref="view-event-v2",
        )
    )

    assert v2.receipt_ref != v1.receipt_ref
    assert signals.commands[-1].understanding_run_ref == "understanding-run-v2"


@pytest.mark.asyncio
async def test_revoked_or_expired_snapshot_reader_result_fails_closed() -> None:
    with pytest.raises(
        UnderstandingConfirmationRejected, match="UNDERSTANDING_SNAPSHOT_NOT_EFFECTIVE"
    ):
        await application(None, Signals()).review(command())
