from pytest import raises

from backend.domains.product_intelligence.domain.course_system import (
    CourseSystem,
    CourseSystemStage,
    CoursewareArtifactRef,
    CoursewareBomLine,
)
from backend.domains.product_intelligence.domain.errors import ProductIntelligenceValidationError


def _stages() -> tuple[CourseSystemStage, ...]:
    return tuple(
        CourseSystemStage(
            stage_id=f"S{index}",
            title=f"阶段 {index}",
            lesson_start=(index - 1) * 4 + 1,
            lesson_end=index * 4,
            outcome=f"阶段 {index} 产出",
        )
        for index in range(1, 7)
    )


def test_course_system_covers_six_stages_and_can_bind_bom() -> None:
    system = CourseSystem(
        system_id="course-system:family-growth",
        version=1,
        tenant_scope="dev",
        product_package_version_ref="product-package:family-growth@v1",
        stages=_stages(),
        bom=(
            CoursewareBomLine(
                lesson_sequence=1,
                artifacts=(
                    CoursewareArtifactRef(
                        artifact_id="deck:lesson-01",
                        kind="DECK",
                        version_ref="deck:lesson-01@v1",
                        provenance_ref="generation-run:abc",
                    ),
                ),
            ),
        ),
    )
    assert system.stages[-1].lesson_end == 24
    assert system.bom[0].artifacts[0].qa_status == "DRAFT"


def test_design_time_system_binds_all_24_lesson_positions() -> None:
    from backend.domains.product_intelligence.infrastructure.course_system_repository import (
        development_course_system_repository,
    )

    system = development_course_system_repository()._by_key[
        ("dev-tenant", "course-system:family-growth")
    ]
    assert [line.lesson_sequence for line in system.bom] == list(range(1, 25))
    assert all(line.artifacts[0].qa_status == "DRAFT" for line in system.bom)


def test_course_system_rejects_stage_gap_and_duplicate_bom_position() -> None:
    stages = list(_stages())
    stages[2] = stages[2].model_copy(update={"lesson_start": 10, "lesson_end": 13})
    with raises(ProductIntelligenceValidationError, match="stage_coverage_invalid"):
        CourseSystem(
            system_id="course-system:family-growth",
            version=1,
            tenant_scope="dev",
            product_package_version_ref="product-package:family-growth@v1",
            stages=tuple(stages),
        )

    with raises(ProductIntelligenceValidationError, match="lesson_sequence_must_be_unique"):
        CourseSystem(
            system_id="course-system:family-growth",
            version=1,
            tenant_scope="dev",
            product_package_version_ref="product-package:family-growth@v1",
            stages=_stages(),
            bom=(
                CoursewareBomLine(
                    lesson_sequence=1,
                    artifacts=(
                        CoursewareArtifactRef(
                            artifact_id="a",
                            kind="IMAGE",
                            version_ref="a@v1",
                            provenance_ref="run:a",
                        ),
                    ),
                ),
                CoursewareBomLine(
                    lesson_sequence=1,
                    artifacts=(
                        CoursewareArtifactRef(
                            artifact_id="b",
                            kind="IMAGE",
                            version_ref="b@v1",
                            provenance_ref="run:b",
                        ),
                    ),
                ),
            ),
        )


def test_course_content_lineage_rejects_wrong_bom_reference() -> None:
    from datetime import UTC, datetime

    from backend.domains.product_intelligence.domain.course_content import (
        CourseContent,
        CourseLesson,
    )

    lessons = tuple(
        CourseLesson(
            lesson_id=f"lesson-{index:02d}",
            sequence=index,
            title=f"课时{index}",
            knowledge_point="知识",
            action_task="行动",
            stage_id=f"S{(index - 1) // 4 + 1}",
            bom_line_ref=(
                f"courseware:family-growth:lesson-{index:02d}@v2"
                if index == 1
                else f"courseware:family-growth:lesson-{index:02d}@v1"
            ),
        )
        for index in range(1, 25)
    )
    with raises(ProductIntelligenceValidationError, match="lesson_lineage_invalid"):
        CourseContent(
            id="course-content:test",
            tenant_scope="dev",
            created_by="author",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
            title="课程",
            course_system_version_ref="course-system:family-growth@v1",
            problem_statement="问题",
            assessment_criteria=("标准",),
            learning_goal="目标",
            lessons=lessons,
            review_cadence="每6节",
            outcome_metrics=("指标",),
            content_accuracy_claim_refs=("claim:1",),
        )
