from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.domains.assessment.application.growth_intent_handoff import (
    ViewedUnderstandingSignal,
)
from backend.domains.assessment.application.reviewed_understanding_signals import (
    RecordReviewedUnderstandingInput,
    RecordReviewedUnderstandingService,
)
from backend.domains.assessment.domain.errors import AssessmentForbiddenError
from backend.domains.assessment.domain.understanding_scope import (
    is_supported_understanding_scope,
)


def command(scope_ref: str) -> RecordReviewedUnderstandingInput:
    return RecordReviewedUnderstandingInput(
        tenant_id="tenant-1",
        family_id="family-1",
        assessment_session_id="session-1",
        signal_ref="understanding:artifact-1",
        signal_version=1,
        scope_ref=scope_ref,
        reviewed_draft_ref="artifact-1",
        draft_version=1,
        provenance_ref="air-provenance:v1:sha256:one",
        draft_source="MODEL_GATEWAY",
        output_schema_ref="family_problem_understanding.v1",
        view_event_ref="view-event-1",
        human_gate_receipt_ref="gate-receipt-1",
        human_gate_effective_status="EFFECTIVE",
        reviewed_by_actor_id="guardian-1",
        reviewed_by_actor_type="FAMILY_GUARDIAN",
        reviewed_at=datetime(2026, 9, 1, tzinfo=UTC),
        expires_at=None,
        subject_person_id="person-1",
        need_type="PARENT_CHILD_COMMUNICATION",
        goal_text="减少遇到困难题时的催促冲突",
        required_capability_keys=("FAMILY_COMMUNICATION",),
        evidence_refs=("guardian-input-1",),
    )


class Writer:
    def __init__(self) -> None:
        self.saved: RecordReviewedUnderstandingInput | None = None

    async def save_viewed_signal(
        self, value: RecordReviewedUnderstandingInput
    ) -> ViewedUnderstandingSignal:
        self.saved = value
        return ViewedUnderstandingSignal(
            tenant_id=value.tenant_id,
            family_id=value.family_id,
            assessment_session_id=value.assessment_session_id,
            signal_ref=value.signal_ref,
            signal_version=value.signal_version,
            scope_ref=value.scope_ref,
            reviewed_draft_ref=value.reviewed_draft_ref,
            draft_version=value.draft_version,
            provenance_ref=value.provenance_ref,
            human_gate_receipt_ref=value.human_gate_receipt_ref,
            human_gate_effective_status=value.human_gate_effective_status,
            reviewed_by_actor_id=value.reviewed_by_actor_id,
            subject_person_id=value.subject_person_id,
            need_type=value.need_type,
            goal_text=value.goal_text,
            required_capability_keys=value.required_capability_keys,
            evidence_refs=value.evidence_refs,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["assessment", "problem-understanding"])
async def test_reviewed_signal_accepts_only_declared_family_scope_kinds(kind: str) -> None:
    writer = Writer()
    value = command(f"family://tenant-1/family-1/{kind}")

    saved = await RecordReviewedUnderstandingService(writer).record_viewed(value)

    assert saved.scope_ref == value.scope_ref
    assert writer.saved == value


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scope_ref",
    [
        "family://tenant-1/family-2/problem-understanding",
        "family://tenant-2/family-1/problem-understanding",
        "family://tenant-1/family-1/unknown",
        "family://tenant-1/family-1/problem-understanding/extra",
    ],
)
async def test_reviewed_signal_rejects_cross_family_or_unknown_scope(scope_ref: str) -> None:
    writer = Writer()

    with pytest.raises(AssessmentForbiddenError) as exc:
        await RecordReviewedUnderstandingService(writer).record_viewed(command(scope_ref))

    assert exc.value.code == "human_gate_scope_mismatch"
    assert writer.saved is None


def test_scope_helper_is_closed_to_two_exact_refs() -> None:
    assert is_supported_understanding_scope(
        scope_ref="family://tenant-1/family-1/problem-understanding",
        tenant_id="tenant-1",
        family_id="family-1",
    )
    assert not is_supported_understanding_scope(
        scope_ref="family://tenant-1/family-1/problem-understanding-v2",
        tenant_id="tenant-1",
        family_id="family-1",
    )
