from datetime import UTC, datetime

import pytest

from backend.domains.product_intelligence.application.course_delivery_projection import (
    compile_course_delivery_projection,
)
from backend.domains.product_intelligence.domain.course_content import CourseContent, CourseLesson
from backend.domains.product_intelligence.domain.errors import ProductIntelligenceValidationError


def _course(*, status: str = "PUBLISHED", assets: bool = True) -> CourseContent:
    lessons = tuple(
        CourseLesson(
            lesson_id=f"lesson-{i}", sequence=i, title=f"第{i}课",
            knowledge_point="知识", action_task=f"行动{i}",
            media_asset_ids=(f"asset-{i}",) if assets else (),
            stage_id=f"S{(i - 1) // 4 + 1}",
            bom_line_ref=f"courseware:family-growth:lesson-{i:02d}@v1",
        ) for i in range(1, 25)
    )
    now = datetime.now(UTC)
    return CourseContent(
        id="course-1", version=1, status=status, tenant_scope="tenant-a",
        created_by="author", created_at=now, updated_at=now, title="成长课",
        course_system_version_ref="course-system:family-growth@v1",
        problem_statement="问题", assessment_criteria=("标准",), learning_goal="目标",
        lessons=lessons, review_cadence="每周", outcome_metrics=("指标",),
        content_accuracy_claim_refs=("claim-1",),
    )


def test_published_24_lessons_compile_to_service_projection() -> None:
    projection = compile_course_delivery_projection(_course())
    assert projection.ready_lessons == 24
    assert projection.publishable_to_service is True
    assert projection.lessons[0].family_action == "行动1"


def test_missing_courseware_blocks_service_publication() -> None:
    projection = compile_course_delivery_projection(_course(assets=False))
    assert projection.ready_lessons == 0
    assert projection.blocked_lessons == 24
    assert projection.publishable_to_service is False


def test_draft_cannot_be_exposed_as_service_product() -> None:
    with pytest.raises(ProductIntelligenceValidationError, match="published"):
        compile_course_delivery_projection(_course(status="DRAFT"))
