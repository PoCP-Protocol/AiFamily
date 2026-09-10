import pytest

from backend.domains.product_intelligence.domain.course_content import CourseLesson
from backend.intelligence.product_management.courseware_generation import (
    build_courseware_request,
    validate_courseware_draft,
)


def _lesson() -> CourseLesson:
    return CourseLesson(
        lesson_id="lesson-01",
        sequence=1,
        title="看见家庭现状",
        knowledge_point="事实与评价分离",
        action_task="完成一次事实记录",
    )


def test_courseware_request_is_evidence_bound_and_non_mutating() -> None:
    request = build_courseware_request(
        lesson=_lesson(), evidence_refs=("claim:1",), context_snapshot_ref="snapshot:1"
    )
    assert request.use_case == "product.courseware.generate"
    assert request.output_schema["required"] == [
        "title",
        "outline",
        "family_action",
        "evidence_refs",
    ]
    assert request.policy_context.may_mutate_business_state is False


def test_courseware_validation_rejects_fabricated_evidence() -> None:
    with pytest.raises(ValueError, match="EVIDENCE_REFERENCE_NOT_ALLOWED"):
        validate_courseware_draft(
            type(
                "Draft",
                (),
                    {
                        "status": "DRAFT",
                        "may_mutate_business_state": False,
                        "output": {
                        "title": "课件",
                        "outline": ["页1"],
                        "family_action": "行动",
                        "evidence_refs": ["claim:other"],
                    }
                },
            )(),
            evidence_refs=("claim:1",),
        )


def test_courseware_request_rejects_duplicate_evidence() -> None:
    with pytest.raises(ValueError, match="EVIDENCE_DUPLICATE"):
        build_courseware_request(
            lesson=_lesson(),
            evidence_refs=("claim:1", "claim:1"),
            context_snapshot_ref="snapshot:1",
        )
