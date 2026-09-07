import pytest

from backend.intelligence.product_management.course_release_baseline import (
    compile_course_release_baseline,
)
from backend.intelligence.product_management.ipd_contracts import GateEvidence


def _payload():
    return {
        "schema_version": "1.0", "course_system_version_ref": "course-system:family-growth@v1",
        "product_package_version_ref": "product-package:family-growth@v1",
        "product_definition_version_ref": "product-definition:family-growth@v1",
        "course_content_version_ref": "course-content:family-growth@v1",
        "safety_policy_version_ref": "safety:family@v1",
        "prompt_bundle_version_ref": "prompts:family@v1",
        "evidence_receipt_refs": ["receipt:1"], "delivery_channel": "WEB",
        "lessons": [
            {
                "lesson_version_ref": f"lesson:{i}@v1",
                "asset_bundle_version_ref": f"asset:{i}@v1",
                "skill_version_refs": [f"skill:{i}@v1"],
            }
            for i in range(1, 25)
        ],
    }


def test_course_release_compiles_to_shared_draft_baseline():
    baseline = compile_course_release_baseline(_payload())
    assert baseline.status.value == "DRAFT"
    assert baseline.blueprint_version_id == "course-system:family-growth@v1"


def test_course_release_requires_all_lessons():
    payload = _payload()
    payload["lessons"] = payload["lessons"][:23]
    with pytest.raises(ValueError, match="24_LESSONS"):
        compile_course_release_baseline(payload)


@pytest.mark.parametrize(
    ("field", "message"),
    [
        ("evidence_receipt_refs", "COURSE_RELEASE_EVIDENCE_REQUIRED"),
        ("prompt_bundle_version_ref", "COURSE_RELEASE_VERSION_REFS_REQUIRED"),
    ],
)
def test_course_release_rejects_ungoverned_global_refs(field, message):
    payload = _payload()
    payload[field] = []
    with pytest.raises((ValueError, Exception), match=message):
        compile_course_release_baseline(payload)


def test_course_release_rejects_lesson_without_skill_or_asset_ref():
    payload = _payload()
    payload["lessons"][0]["skill_version_refs"] = []
    with pytest.raises(ValueError, match="LESSON_REFS_REQUIRED"):
        compile_course_release_baseline(payload)


def test_course_release_draft_enters_shared_human_release_lifecycle():
    baseline = compile_course_release_baseline(_payload())
    evidence = (GateEvidence("evidence-1", "QA", "qa://course-24", "课件治理通过"),)
    reviewed = baseline.approve(
        decided_by="human:operator-1", human_gate_ref="gate:course-24", evidence=evidence
    )
    released = reviewed.release(decided_by="human:operator-1", evidence=evidence)
    assert released.status.value == "RELEASED"
    assert released.approved_by == "human:operator-1"


def test_course_release_requires_evidence_for_release_after_approval():
    baseline = compile_course_release_baseline(_payload())
    evidence = (GateEvidence("evidence-1", "QA", "qa://course-24", "课件治理通过"),)
    reviewed = baseline.approve(
        decided_by="human:operator-1", human_gate_ref="gate:course-24", evidence=evidence
    )
    with pytest.raises(Exception, match="RELEASE_EVIDENCE_REQUIRED"):
        reviewed.release(decided_by="human:operator-1", evidence=())


def test_course_release_supports_pause_rollback_and_retire():
    baseline = compile_course_release_baseline(_payload())
    evidence = (GateEvidence("evidence-1", "QA", "qa://course-24", "治理证据"),)
    released = baseline.approve(
        decided_by="human:operator-1", human_gate_ref="gate:course-24", evidence=evidence
    ).release(decided_by="human:operator-1", evidence=evidence)
    paused = released.pause(decided_by="human:operator-1", evidence=evidence)
    rolled_back = paused.rollback(
        target_ref="course-release:course-content:family-growth@v0",
        decided_by="human:operator-1",
        evidence=evidence,
    )
    retired = rolled_back.retire(decided_by="human:operator-1", evidence=evidence)
    assert paused.status.value == "PAUSED"
    assert rolled_back.rollback_target_ref.endswith("@v0")
    assert retired.status.value == "RETIRED"
