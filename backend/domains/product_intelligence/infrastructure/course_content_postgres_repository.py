"""PostgreSQL adapter for the `CourseContent` repository interface.

Schema is created by
``database/migrations/versions/0056_course_content.py`` (single
``course_content`` table; nested ``lessons`` stored as JSONB — see that
migration's docstring for why no child table exists). One repository
instance owns one ``AsyncConnection``; the caller owns the transaction
boundary, mirroring ``backend/domains/family_need/infrastructure/
postgres_repository.py``.

Method signatures match `InMemoryCourseContentRepository` exactly so this
adapter is a drop-in replacement behind the same
`CourseContentRepository` protocol used by
`backend/domains/product_intelligence/application/course_publication.py`.
"""

from __future__ import annotations

import json

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.course_content import CourseContent, CourseLesson
from ..domain.errors import ProductIntelligenceNotFoundError


def _dump(value: object) -> str:
    return json.dumps(value, default=str, sort_keys=True)


def _lessons_to_json(lessons: tuple[CourseLesson, ...]) -> list[dict]:
    return [
        {
            "lesson_id": lesson.lesson_id,
            "sequence": lesson.sequence,
            "title": lesson.title,
            "knowledge_point": lesson.knowledge_point,
            "action_task": lesson.action_task,
            "media_asset_ids": list(lesson.media_asset_ids),
            "tool_refs": list(lesson.tool_refs),
        }
        for lesson in lessons
    ]


def _lessons_from_json(rows: list[dict] | None) -> tuple[CourseLesson, ...]:
    if not rows:
        return ()
    return tuple(
        CourseLesson(
            lesson_id=row["lesson_id"],
            sequence=row["sequence"],
            title=row["title"],
            knowledge_point=row["knowledge_point"],
            action_task=row["action_task"],
            media_asset_ids=tuple(row.get("media_asset_ids") or ()),
            tool_refs=tuple(row.get("tool_refs") or ()),
        )
        for row in rows
    )


def _course_from_row(row) -> CourseContent:
    return CourseContent(
        id=row["id"],
        version=row["version"],
        status=row["status"],
        tenant_scope=row["tenant_scope"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        title=row["title"],
        product_component_id=row["product_component_id"],
        problem_statement=row["problem_statement"],
        assessment_criteria=tuple(row["assessment_criteria"] or ()),
        learning_goal=row["learning_goal"],
        lessons=_lessons_from_json(row["lessons"]),
        ai_coach_prompt_ref=row["ai_coach_prompt_ref"],
        review_cadence=row["review_cadence"],
        outcome_metrics=tuple(row["outcome_metrics"] or ()),
        content_accuracy_claim_refs=tuple(row["content_accuracy_claim_refs"] or ()),
        reviewed_by=row["reviewed_by"],
        reviewed_at=row["reviewed_at"],
        review_reason=row["review_reason"],
        published_at=row["published_at"],
    )


class SqlAlchemyCourseContentRepository:
    """One connection per instance; caller owns commit/rollback."""

    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    async def save_course_content(self, course: CourseContent) -> None:
        params = {
            "id": course.id,
            "tenant_scope": course.tenant_scope,
            "version": course.version,
            "status": course.status,
            "created_by": course.created_by,
            "created_at": course.created_at,
            "updated_at": course.updated_at,
            "title": course.title,
            "product_component_id": course.product_component_id,
            "problem_statement": course.problem_statement,
            "assessment_criteria": _dump(list(course.assessment_criteria)),
            "learning_goal": course.learning_goal,
            "lessons": _dump(_lessons_to_json(course.lessons)),
            "ai_coach_prompt_ref": course.ai_coach_prompt_ref,
            "review_cadence": course.review_cadence,
            "outcome_metrics": _dump(list(course.outcome_metrics)),
            "content_accuracy_claim_refs": _dump(list(course.content_accuracy_claim_refs)),
            "reviewed_by": course.reviewed_by,
            "reviewed_at": course.reviewed_at,
            "review_reason": course.review_reason,
            "published_at": course.published_at,
        }
        await self._connection.execute(
            text(
                """
                insert into course_content(
                  id, tenant_scope, version, status, created_by, created_at, updated_at,
                  title, product_component_id, problem_statement, assessment_criteria,
                  learning_goal, lessons, ai_coach_prompt_ref, review_cadence,
                  outcome_metrics, content_accuracy_claim_refs, reviewed_by, reviewed_at,
                  review_reason, published_at
                ) values (
                  :id, :tenant_scope, :version, :status, :created_by, :created_at, :updated_at,
                  :title, :product_component_id, :problem_statement, :assessment_criteria,
                  :learning_goal, :lessons, :ai_coach_prompt_ref, :review_cadence,
                  :outcome_metrics, :content_accuracy_claim_refs, :reviewed_by, :reviewed_at,
                  :review_reason, :published_at
                )
                on conflict (tenant_scope, id) do update set
                  version=excluded.version, status=excluded.status, updated_at=excluded.updated_at,
                  title=excluded.title, product_component_id=excluded.product_component_id,
                  problem_statement=excluded.problem_statement,
                  assessment_criteria=excluded.assessment_criteria,
                  learning_goal=excluded.learning_goal, lessons=excluded.lessons,
                  ai_coach_prompt_ref=excluded.ai_coach_prompt_ref,
                  review_cadence=excluded.review_cadence,
                  outcome_metrics=excluded.outcome_metrics,
                  content_accuracy_claim_refs=excluded.content_accuracy_claim_refs,
                  reviewed_by=excluded.reviewed_by, reviewed_at=excluded.reviewed_at,
                  review_reason=excluded.review_reason, published_at=excluded.published_at
                where course_content.version <= excluded.version
                """
            ),
            params,
        )

    async def load_course_content(self, course_id: str, tenant_scope: str) -> CourseContent:
        result = await self._connection.execute(
            text(
                """
                select * from course_content
                where tenant_scope=:tenant_scope and id=:id
                """
            ),
            {"tenant_scope": tenant_scope, "id": course_id},
        )
        row = result.mappings().first()
        if row is None:
            raise ProductIntelligenceNotFoundError("course_content_not_found")
        return _course_from_row(row)

    async def list_published_course_content(self, tenant_scope: str) -> list[CourseContent]:
        result = await self._connection.execute(
            text(
                """
                select * from course_content
                where tenant_scope=:tenant_scope and status='PUBLISHED'
                """
            ),
            {"tenant_scope": tenant_scope},
        )
        return [_course_from_row(row) for row in result.mappings().all()]


__all__ = ["SqlAlchemyCourseContentRepository"]
