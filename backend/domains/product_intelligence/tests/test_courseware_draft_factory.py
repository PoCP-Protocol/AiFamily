from backend.domains.product_intelligence.application.courseware_draft_factory import (
    build_courseware_draft_candidate,
)
from backend.domains.product_intelligence.domain.course_content import CourseLesson


def test_factory_builds_non_publishable_draft_with_lineage() -> None:
    draft = build_courseware_draft_candidate(
        lesson=CourseLesson(
            lesson_id="lesson-01",
            sequence=1,
            title="看见家庭现状",
            knowledge_point="事实与评价分离",
            action_task="完成一次事实记录",
        ),
        tenant_scope="tenant-a",
        product_package_version_ref="product-package:family-growth@v1",
        course_system_version_ref="course-system:family-growth@v1",
        asset_bundle_version_ref="asset-bundle:lesson-01@v1",
        kind="DECK",
        prompt_ref="prompt:courseware-deck@v1",
        model_provenance_ref="model-gateway:fake@v1",
        output_locator="draft://courseware/lesson-01/deck",
    )
    assert draft.status == "DRAFT"
    assert draft.lesson_sequence == 1
    assert draft.is_publishable() is False
