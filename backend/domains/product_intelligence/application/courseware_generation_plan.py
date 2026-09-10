"""Deterministic generation plan for a governed courseware BOM.

The plan is intentionally provider-neutral: it only expands lesson BOM slots
into auditable work items.  A Model Gateway worker may execute each item later;
creating the plan never claims that an asset exists or passed review.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from ..domain.course_content import CourseLesson

CoursewarePlanKind = Literal["DECK", "WORKSHEET", "DOCUMENT"]
PLAN_KINDS: tuple[CoursewarePlanKind, ...] = ("DECK", "WORKSHEET", "DOCUMENT")


@dataclass(frozen=True, slots=True)
class CoursewareGenerationItem:
    lesson_id: str
    lesson_sequence: int
    kind: CoursewarePlanKind
    asset_bundle_version_ref: str
    prompt_ref: str
    status: Literal["PLANNED"] = "PLANNED"


def build_courseware_generation_plan(
    *, lessons: tuple[CourseLesson, ...], prompt_version: str = "courseware-generator.v1"
) -> tuple[CoursewareGenerationItem, ...]:
    """Expand lesson BOM references into stable, human-gated work items."""

    if not lessons:
        raise ValueError("COURSEWARE_PLAN_LESSONS_REQUIRED")
    ordered = tuple(sorted(lessons, key=lambda lesson: lesson.sequence))
    if len({lesson.sequence for lesson in ordered}) != len(ordered):
        raise ValueError("COURSEWARE_PLAN_SEQUENCE_DUPLICATE")
    prompt_ref = f"prompt:{prompt_version}"
    return tuple(
        CoursewareGenerationItem(
            lesson_id=lesson.lesson_id,
            lesson_sequence=lesson.sequence,
            kind=kind,
            asset_bundle_version_ref=(
                f"courseware:family-growth:lesson-{lesson.sequence:02d}:"
                f"{kind.lower()}@v1"
            ),
            prompt_ref=prompt_ref,
        )
        for lesson in ordered
        for kind in PLAN_KINDS
    )


__all__ = ["CoursewareGenerationItem", "PLAN_KINDS", "build_courseware_generation_plan"]
