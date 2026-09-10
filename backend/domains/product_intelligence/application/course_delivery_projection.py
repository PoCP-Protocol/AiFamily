"""Compile published course content into a service-product delivery read model.

The projection is deliberately read-only: it does not create journey facts or
mutate a family's state.  It gives Product Studio and downstream delivery
adapters one auditable view of the 24 lesson contract and its courseware gates.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

from ..domain.course_content import CourseContent
from ..domain.errors import ProductIntelligenceValidationError

DeliveryStatus = Literal["READY", "MISSING_COURSEWARE", "INCOMPLETE_LINEAGE"]


class LessonDeliveryProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    sequence: int
    lesson_id: str
    stage_id: str
    product_outcome: str
    family_action: str
    courseware_refs: tuple[str, ...]
    status: DeliveryStatus


class CourseDeliveryProjection(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    course_content_id: str
    course_system_version_ref: str
    product_component_id: str | None
    lessons: tuple[LessonDeliveryProjection, ...]
    ready_lessons: int
    blocked_lessons: int
    publishable_to_service: bool


def compile_course_delivery_projection(course: CourseContent) -> CourseDeliveryProjection:
    """Compile a 24-lesson course into a delivery contract.

    Only a published course with complete CourseSystem lineage can be exposed
    as a service product.  Courseware is represented by references; binaries
    and family execution remain owned by their respective domains.
    """

    if course.status != "PUBLISHED":
        raise ProductIntelligenceValidationError("course_delivery_requires_published_course")
    if course.course_system_version_ref is None or len(course.lessons) != 24:
        raise ProductIntelligenceValidationError("course_delivery_lineage_incomplete")

    lessons: list[LessonDeliveryProjection] = []
    for lesson in course.lessons:
        expected_stage = f"S{(lesson.sequence - 1) // 4 + 1}"
        status: DeliveryStatus = "READY"
        if lesson.stage_id != expected_stage or lesson.bom_line_ref is None:
            status = "INCOMPLETE_LINEAGE"
        elif not lesson.media_asset_ids:
            status = "MISSING_COURSEWARE"
        lessons.append(
            LessonDeliveryProjection(
                sequence=lesson.sequence,
                lesson_id=lesson.lesson_id,
                stage_id=lesson.stage_id or expected_stage,
                product_outcome=f"{expected_stage}家庭成长行动产出",
                family_action=lesson.action_task,
                courseware_refs=lesson.media_asset_ids,
                status=status,
            )
        )

    ready = sum(lesson.status == "READY" for lesson in lessons)
    return CourseDeliveryProjection(
        course_content_id=course.id,
        course_system_version_ref=course.course_system_version_ref,
        product_component_id=course.product_component_id,
        lessons=tuple(lessons),
        ready_lessons=ready,
        blocked_lessons=len(lessons) - ready,
        publishable_to_service=ready == 24,
    )


__all__ = [
    "CourseDeliveryProjection",
    "LessonDeliveryProjection",
    "compile_course_delivery_projection",
]
