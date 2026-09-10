import pytest

from backend.domains.product_intelligence.application.courseware_generation_plan import (
    build_courseware_generation_plan,
)
from backend.domains.product_intelligence.domain.course_content import CourseLesson


def test_plan_expands_each_lesson_into_three_governed_slots() -> None:
    lessons = tuple(
        CourseLesson(
            lesson_id=f"lesson-{sequence:02d}",
            sequence=sequence,
            title=f"课时{sequence}",
            knowledge_point="知识点",
            action_task="行动",
        )
        for sequence in (2, 1)
    )
    plan = build_courseware_generation_plan(lessons=lessons)
    assert len(plan) == 6
    assert [(item.lesson_sequence, item.kind) for item in plan] == [
        (1, "DECK"), (1, "WORKSHEET"), (1, "DOCUMENT"),
        (2, "DECK"), (2, "WORKSHEET"), (2, "DOCUMENT"),
    ]
    assert all(item.status == "PLANNED" for item in plan)


def test_plan_rejects_duplicate_sequence() -> None:
    lesson = CourseLesson(
        lesson_id="lesson-01", sequence=1, title="课时", knowledge_point="知识", action_task="行动"
    )
    with pytest.raises(ValueError, match="SEQUENCE_DUPLICATE"):
        build_courseware_generation_plan(lessons=(lesson, lesson))
