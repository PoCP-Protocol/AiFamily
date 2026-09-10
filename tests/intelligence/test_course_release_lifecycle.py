from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.human_gate.contracts import ActorType, DecisionOutcome, HumanDecision
from backend.intelligence.product_management.application.course_release_lifecycle import (
    CourseReleaseLifecycleError,
    advance_course_release_lifecycle,
)
from backend.intelligence.product_management.course_release_baseline import (
    compile_course_release_baseline,
)
from backend.intelligence.product_management.ipd_contracts import GateEvidence


def _baseline():
    return compile_course_release_baseline(
        {
            "schema_version": "1.0",
            "course_system_version_ref": "course-system:family@v1",
            "product_package_version_ref": "product-package:family@v1",
            "product_definition_version_ref": "product-definition:family@v1",
            "course_content_version_ref": "course-content:family@v1",
            "safety_policy_version_ref": "safety:family@v1",
            "prompt_bundle_version_ref": "prompts:family@v1",
            "evidence_receipt_refs": ["receipt:1"],
            "lessons": [
                {
                    "lesson_version_ref": f"lesson:{i}@v1",
                    "asset_bundle_version_ref": f"asset:{i}@v1",
                    "skill_version_refs": [f"skill:{i}@v1"],
                }
                for i in range(1, 25)
            ],
        }
    )


def _decision(outcome=DecisionOutcome.ACCEPT):
    reason = "拒绝原因" if outcome is not DecisionOutcome.ACCEPT else ""
    return HumanDecision(
        "decision:1",
        "task:course-release",
        "human:operator",
        ActorType.OPERATOR,
        outcome,
        reason,
        datetime.now(UTC) - timedelta(minutes=1),
    )


def _evidence():
    return (GateEvidence("evidence:qa", "QA", "qa://course", "通过"),)


def test_course_release_lifecycle_requires_human_and_returns_audit():
    result = advance_course_release_lifecycle(
        _baseline(), action="APPROVE", decision=_decision(), evidence=_evidence()
    )
    assert result.baseline.status.value == "REVIEWED"
    assert result.audit.to_status == "REVIEWED"
    assert result.audit.evidence_ids == ("evidence:qa",)


def test_course_release_lifecycle_releases_only_after_approval():
    with pytest.raises(CourseReleaseLifecycleError, match="RELEASE_REQUIRES_APPROVAL"):
        advance_course_release_lifecycle(
            _baseline(), action="RELEASE", decision=_decision(), evidence=_evidence()
        )


def test_course_release_lifecycle_rejects_non_accept_and_missing_rollback_target():
    with pytest.raises(CourseReleaseLifecycleError, match="HUMAN_ACCEPT"):
        advance_course_release_lifecycle(
            _baseline(),
            action="APPROVE",
            decision=_decision(DecisionOutcome.REJECT),
            evidence=_evidence(),
        )
    reviewed = advance_course_release_lifecycle(
        _baseline(), action="APPROVE", decision=_decision(), evidence=_evidence()
    ).baseline
    released = advance_course_release_lifecycle(
        reviewed, action="RELEASE", decision=_decision(), evidence=_evidence()
    ).baseline
    with pytest.raises(CourseReleaseLifecycleError, match="ROLLBACK_TARGET"):
        advance_course_release_lifecycle(
            released, action="ROLLBACK", decision=_decision(), evidence=_evidence()
        )
