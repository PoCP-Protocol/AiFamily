from __future__ import annotations

from copy import deepcopy

import pytest

from backend.intelligence.experience.growth_plan_review_envelope import (
    DynamicGrowthPlanDraftValidator,
    GrowthPlanReviewEnvelopeError,
    TrustedGrowthPlanDraft,
)


def _output() -> dict[str, object]:
    return {
        "draft_status": "DRAFT",
        "intent_ref": "intent-21",
        "onboarding_ref": "onboarding-21",
        "priority_ref": "priority-21",
        "horizon_days": 21,
        "boundary_labels": [
            "plan_draft_not_active",
            "guardian_confirmation_required",
        ],
        "evidence_refs": ["evidence:confirmed-intent"],
        "pause_policy": {"allowed": True, "streak_penalty": False},
        "stages": [
            {
                "stage_id": "MICRO_ACTION",
                "goal": "完成一个可停止的五分钟行动",
                "small_actions": ["一起选择五分钟任务"],
                "evidence_refs": ["evidence:confirmed-intent"],
            },
            {
                "stage_id": "HUMAN_SERVICE_OR_PAUSE",
                "goal": "需要时转人工服务，否则安全暂停",
                "service_option": "REQUEST_HUMAN",
                "evidence_refs": ["evidence:service-boundary"],
            },
        ],
    }


def _trusted(**changes: object) -> TrustedGrowthPlanDraft:
    values: dict[str, object] = {
        "draft_id": "draft:dynamic-21",
        "provenance_ref": "model-draft:dynamic-21",
        "stable_digest": "a" * 64,
        "tenant_id": "tenant-a",
        "family_id": "family-a",
        "subject_person_id": "child-a",
        "intent_id": "intent-21",
        "onboarding_id": "onboarding-21",
        "priority_id": "priority-21",
        "allowed_evidence_refs": (
            "evidence:confirmed-intent",
            "evidence:service-boundary",
        ),
        "output": _output(),
    }
    values.update(changes)
    return TrustedGrowthPlanDraft(**values)  # type: ignore[arg-type]


def _validate(trusted: TrustedGrowthPlanDraft):  # type: ignore[no-untyped-def]
    return DynamicGrowthPlanDraftValidator().validate(
        trusted,
        tenant_id="tenant-a",
        family_id="family-a",
        subject_person_id="child-a",
    )


def test_21_day_micro_action_and_human_service_pause_are_valid_dynamic_draft() -> None:
    receipt = _validate(_trusted())

    assert receipt.status == "VALIDATED_DRAFT"
    assert receipt.horizon_days == 21
    assert receipt.stage_ids == ("MICRO_ACTION", "HUMAN_SERVICE_OR_PAUSE")
    assert receipt.may_mutate_business_state is False
    assert len(receipt.receipt_digest) == 64


def test_stage_names_and_horizon_are_not_a_fixed_90_day_template() -> None:
    output = _output()
    output["horizon_days"] = 7
    output["stages"] = [
        {
            "stage_id": "ONE_SAFE_STEP",
            "evidence_refs": ["evidence:confirmed-intent"],
        }
    ]

    receipt = _validate(_trusted(output=output))

    assert receipt.horizon_days == 7
    assert receipt.stage_ids == ("ONE_SAFE_STEP",)


@pytest.mark.parametrize(
    ("tenant_id", "family_id", "subject_person_id"),
    [
        ("tenant-other", "family-a", "child-a"),
        ("tenant-a", "family-other", "child-a"),
        ("tenant-a", "family-a", "child-other"),
    ],
)
def test_cross_scope_review_is_rejected(
    tenant_id: str,
    family_id: str,
    subject_person_id: str,
) -> None:
    with pytest.raises(GrowthPlanReviewEnvelopeError, match="SCOPE_MISMATCH"):
        DynamicGrowthPlanDraftValidator().validate(
            _trusted(),
            tenant_id=tenant_id,
            family_id=family_id,
            subject_person_id=subject_person_id,
        )


@pytest.mark.parametrize(
    ("mutation", "error"),
    [
        ({"draft_status": "ACTIVE"}, "STATUS_REQUIRED"),
        ({"horizon_days": 0}, "HORIZON_INVALID"),
        ({"family_score": 99}, "FACT_WRITE_FORBIDDEN"),
    ],
)
def test_active_invalid_or_fact_writing_model_output_is_rejected(
    mutation: dict[str, object],
    error: str,
) -> None:
    output = deepcopy(_output())
    output.update(mutation)

    with pytest.raises(GrowthPlanReviewEnvelopeError, match=error):
        _validate(_trusted(output=output))


def test_unknown_evidence_and_unsafe_pause_are_rejected() -> None:
    unknown = deepcopy(_output())
    unknown["stages"][0]["evidence_refs"] = ["client:invented"]  # type: ignore[index]
    with pytest.raises(GrowthPlanReviewEnvelopeError, match="EVIDENCE_REF_UNKNOWN"):
        _validate(_trusted(output=unknown))

    unsafe_pause = deepcopy(_output())
    unsafe_pause["pause_policy"] = {"allowed": False, "streak_penalty": True}
    with pytest.raises(GrowthPlanReviewEnvelopeError, match="SAFE_PAUSE_REQUIRED"):
        _validate(_trusted(output=unsafe_pause))
