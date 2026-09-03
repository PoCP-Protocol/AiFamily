"""Minimal "family completed this course" fact — not a per-lesson tracker.

This module deliberately does not build a lesson-by-lesson check-in system.
The vertical slice this closes needs exactly one thing: a family that was
matched to a `PUBLISHED` `CourseContent` (via `family_need`'s SOLUTION shape
and `CourseSupplyAdapter`) can mark that course completed, and that fact must
be visible to the family's growth journey
(`backend.domains.journey.application.outcome_loop.GrowthOutcomeLoop`) the
same way a completed service booking already is
(`family_need.api.routes.complete_booking_and_review`). A richer per-lesson
progress model is future work; recording "completed" once per
(family, need, course) is enough to prove the loop closes.

`CourseCompletionRecord` is intentionally not a state machine: it has no
transitions, only a factory. Marking the same course complete twice for the
same family/need is a caller-level idempotency concern (the HTTP route uses
the ordinary `idempotency-key` header plus the outcome loop's own replay
guard), not something this module needs to re-derive.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from ..domain.course_content import CourseContent
from ..domain.errors import (
    ProductIntelligenceConflictError,
    ProductIntelligenceValidationError,
)
from .context import ActorContext
from .course_publication import CourseContentRepository


def _new_id() -> str:
    return f"course-completion-{uuid.uuid4()}"


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class CourseCompletionRecord:
    """One family finished one published course, for one family need.

    No score, no percentage, no per-lesson breakdown — see module docstring.
    """

    completion_id: str
    tenant_scope: str
    course_content_id: str
    course_title: str
    family_id: str
    need_id: str
    subject_person_id: str
    completed_by: str
    completed_at: datetime


async def mark_course_completed_for_family(
    repo: CourseContentRepository,
    context: ActorContext,
    *,
    course_content_id: str,
    family_id: str,
    need_id: str,
    subject_person_id: str,
) -> CourseCompletionRecord:
    """Record that `family_id` finished the `PUBLISHED` course for `need_id`.

    Requires the course to actually be `PUBLISHED` in this tenant scope — a
    family cannot "complete" a course that was never admitted through the
    Human Gate lifecycle. Raises `ProductIntelligenceConflictError` for any
    other status (mirrors the fail-closed shape used across this domain,
    e.g. `CourseContent.retire`'s own status guard).
    """

    if not family_id.strip() or not need_id.strip() or not subject_person_id.strip():
        raise ProductIntelligenceValidationError("course_completion_scope_required")
    course: CourseContent = await repo.load_course_content(
        course_content_id, context.tenant_scope
    )
    if course.status != "PUBLISHED":
        raise ProductIntelligenceConflictError("course_completion_requires_published_course")
    return CourseCompletionRecord(
        completion_id=_new_id(),
        tenant_scope=context.tenant_scope,
        course_content_id=course.id,
        course_title=course.title,
        family_id=family_id,
        need_id=need_id,
        subject_person_id=subject_person_id,
        completed_by=context.actor_id,
        completed_at=_now(),
    )


__all__ = ["CourseCompletionRecord", "mark_course_completed_for_family"]
