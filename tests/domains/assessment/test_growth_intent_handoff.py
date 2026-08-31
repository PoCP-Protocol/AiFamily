from __future__ import annotations

from dataclasses import replace

import pytest

from backend.domains.assessment.application.growth_intent_handoff import (
    AssessmentGrowthIntentHandoff,
    ConfirmGrowthIntentInput,
    DecideViewedUnderstandingInput,
    GrowthIntentReceipt,
    ViewedUnderstandingSignal,
)
from backend.domains.assessment.domain.errors import (
    AssessmentConflictError,
    AssessmentForbiddenError,
)


def viewed_signal() -> ViewedUnderstandingSignal:
    return ViewedUnderstandingSignal(
        tenant_id="tenant-1",
        family_id="family-1",
        assessment_session_id="assessment-1",
        signal_ref="ASSESSMENT:assessment-1:FAMILY_SUPPORT_NEEDS:v2:H1",
        signal_version=2,
        subject_person_id="person-1",
        need_type="PARENT_CHILD_COMMUNICATION",
        goal_text="希望晚饭后的作业安排少一点争吵",
        required_capability_keys=("FAMILY_COMMUNICATION",),
        evidence_refs=("assessment-evidence-1",),
    )


class SignalReader:
    def __init__(self, signal: ViewedUnderstandingSignal | None = None) -> None:
        self.signal = signal if signal is not None else viewed_signal()
        self.calls = 0

    async def load_viewed_signal(self, **_: str) -> ViewedUnderstandingSignal | None:
        self.calls += 1
        return self.signal


class GrowthIntents:
    def __init__(self) -> None:
        self.commands: list[ConfirmGrowthIntentInput] = []

    async def confirm_growth_intent(
        self, command: ConfirmGrowthIntentInput
    ) -> GrowthIntentReceipt:
        self.commands.append(command)
        return GrowthIntentReceipt(
            intent_id="intent-1",
            signal_ref=command.signal_ref,
            signal_version=command.signal_version,
            receipt_ref="receipt-1",
        )


def decision(decision_type: str = "CONFIRM") -> DecideViewedUnderstandingInput:
    signal = viewed_signal()
    return DecideViewedUnderstandingInput(
        tenant_id=signal.tenant_id,
        family_id=signal.family_id,
        actor_id="guardian-1",
        actor_type="FAMILY_GUARDIAN",
        assessment_session_id=signal.assessment_session_id,
        signal_ref=signal.signal_ref,
        signal_version=signal.signal_version,
        decision_type=decision_type,  # type: ignore[arg-type]
        correlation_id="corr-1",
        idempotency_key="idem-1",
    )


@pytest.mark.asyncio
async def test_confirm_delegates_exact_viewed_signal_version_without_ai_dependency() -> None:
    reader = SignalReader()
    growth = GrowthIntents()
    handoff = AssessmentGrowthIntentHandoff(reader, growth)

    receipt = await handoff.decide(decision())

    assert receipt.outcome == "INTENT_CREATED"
    assert receipt.signal_ref == viewed_signal().signal_ref
    assert receipt.signal_version == 2
    assert receipt.intent is not None
    assert receipt.intent.boundary == "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"
    assert growth.commands == [
        ConfirmGrowthIntentInput(
            tenant_id="tenant-1",
            family_id="family-1",
            actor_id="guardian-1",
            subject_person_id="person-1",
            signal_ref=viewed_signal().signal_ref,
            signal_version=2,
            need_type="PARENT_CHILD_COMMUNICATION",
            goal_text="希望晚饭后的作业安排少一点争吵",
            required_capability_keys=("FAMILY_COMMUNICATION",),
            evidence_refs=("assessment-evidence-1",),
            correlation_id="corr-1",
            idempotency_key="idem-1",
        )
    ]
    assert not hasattr(handoff, "_interpretation")


@pytest.mark.asyncio
async def test_dismiss_records_no_growth_intent() -> None:
    growth = GrowthIntents()
    handoff = AssessmentGrowthIntentHandoff(SignalReader(), growth)

    receipt = await handoff.decide(decision("DISMISS"))

    assert receipt.outcome == "NO_ACTION"
    assert receipt.intent is None
    assert growth.commands == []


@pytest.mark.asyncio
async def test_stale_signal_version_is_rejected_before_growth_call() -> None:
    growth = GrowthIntents()
    handoff = AssessmentGrowthIntentHandoff(SignalReader(), growth)

    with pytest.raises(AssessmentConflictError) as exc:
        await handoff.decide(replace(decision(), signal_version=1))

    assert exc.value.code == "understanding_signal_version_conflict"
    assert growth.commands == []


@pytest.mark.asyncio
async def test_non_guardian_cannot_confirm_or_dismiss() -> None:
    growth = GrowthIntents()
    handoff = AssessmentGrowthIntentHandoff(SignalReader(), growth)

    with pytest.raises(AssessmentForbiddenError) as exc:
        await handoff.decide(replace(decision(), actor_type="AI"))

    assert exc.value.code == "guardian_confirmation_required"
    assert growth.commands == []


@pytest.mark.asyncio
async def test_growth_receipt_must_reference_same_signal_version() -> None:
    class StaleGrowthIntents(GrowthIntents):
        async def confirm_growth_intent(
            self, command: ConfirmGrowthIntentInput
        ) -> GrowthIntentReceipt:
            self.commands.append(command)
            return GrowthIntentReceipt(
                intent_id="intent-stale",
                signal_ref=command.signal_ref,
                signal_version=command.signal_version + 1,
                receipt_ref="receipt-stale",
            )

    growth = StaleGrowthIntents()
    handoff = AssessmentGrowthIntentHandoff(SignalReader(), growth)

    with pytest.raises(AssessmentConflictError) as exc:
        await handoff.decide(decision())

    assert exc.value.code == "growth_intent_receipt_signal_mismatch"
