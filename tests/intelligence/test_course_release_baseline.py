import pytest

from backend.intelligence.product_management.course_release_baseline import (
    compile_course_release_baseline,
)


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
