import pytest
from pydantic import ValidationError

from backend.domains.product_intelligence.domain.courseware_draft import CoursewareDraft
from backend.domains.product_intelligence.domain.errors import ProductIntelligenceValidationError


def _draft(**changes):
    payload = {
        "draft_id": "courseware-draft:1",
        "tenant_scope": "tenant-a",
        "product_package_version_ref": "product-package:family@v1",
        "course_system_version_ref": "course-system:family@v1",
        "lesson_sequence": 1,
        "asset_bundle_version_ref": "asset-bundle:family-1@v1",
        "kind": "DECK",
        "prompt_ref": "prompt:lesson-1@v1",
        "model_provenance_ref": "model-draft:abc",
        "output_locator": "object://drafts/courseware-1",
    }
    payload.update(changes)
    return CoursewareDraft(**payload)


def test_courseware_draft_defaults_to_non_publishable_draft():
    draft = _draft()
    assert draft.status == "DRAFT"
    assert draft.is_publishable() is False


def test_courseware_draft_requires_lesson_range_and_provenance():
    with pytest.raises(ValidationError, match="lesson_sequence"):
        _draft(lesson_sequence=25)
    with pytest.raises(ProductIntelligenceValidationError, match="model_provenance_ref"):
        _draft(model_provenance_ref="")


def test_courseware_draft_is_publishable_only_after_all_governance_checks():
    draft = _draft(
        status="APPROVED", rights_status="CLEARED", safety_status="CLEARED", quality_status="PASSED"
    )
    assert draft.is_publishable() is True
