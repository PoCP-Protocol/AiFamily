"""Minimal Course Content API: create draft -> submit for review -> decide
review -> list/get published.

Mounted separately from `routes.py`'s router (per the task scope: only the
course-content endpoints are wired into `apps/family_api`; the rest of
`product_intelligence`'s routes remain unmounted, tracked debt). Dependency
wiring here is deliberately self-contained (its own repository + Human Gate
singleton getters) rather than reusing `dependencies.py::get_repository`,
because no SQLAlchemy mapping exists yet for `CourseContent` — see
`infrastructure/course_content_repository.py`'s docstring.
"""

from __future__ import annotations

from typing import NoReturn

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.intelligence.human_gate.gate import InMemoryHumanGate

from ..application.context import ActorContext
from ..application.course_publication import (
    CourseContentRepository,
    create_course_content_draft,
    decide_course_content_review,
    get_course_content,
    list_published_course_content,
    submit_course_content_for_review,
)
from ..domain.course_content import CourseLesson
from ..domain.errors import ProductIntelligenceDomainError
from .dependencies import get_actor_context

router = APIRouter(prefix="/product-intelligence/courses", tags=["product-intelligence-courses"])

_ERROR_STATUS = {
    "ProductIntelligenceValidationError": 400,
    "ProductIntelligenceForbiddenError": 403,
    "ProductIntelligenceNotFoundError": 404,
}

_repository: CourseContentRepository | None = None
_gate: InMemoryHumanGate | None = None


def configure_course_content_repository(repository: CourseContentRepository | None) -> None:
    global _repository
    _repository = repository


def configure_course_content_gate(gate: InMemoryHumanGate | None) -> None:
    global _gate
    _gate = gate


def clear_course_content_wiring() -> None:
    configure_course_content_repository(None)
    configure_course_content_gate(None)


async def get_course_content_repository() -> CourseContentRepository:
    if _repository is None:
        raise RuntimeError("course_content repository not configured — no owning app exists yet")
    return _repository


async def get_course_content_gate() -> InMemoryHumanGate:
    if _gate is None:
        raise RuntimeError("course_content Human Gate not configured — no owning app exists yet")
    return _gate


def _raise_http(exc: ProductIntelligenceDomainError) -> NoReturn:
    status = _ERROR_STATUS.get(type(exc).__name__, 400)
    raise HTTPException(status_code=status, detail=exc.code) from exc


class CourseLessonRequest(BaseModel):
    lesson_id: str
    sequence: int = Field(ge=1)
    title: str
    knowledge_point: str
    action_task: str
    media_asset_ids: list[str] = Field(default_factory=list)
    tool_refs: list[str] = Field(default_factory=list)


class CreateCourseContentDraftRequest(BaseModel):
    title: str
    problem_statement: str
    assessment_criteria: list[str]
    learning_goal: str
    lessons: list[CourseLessonRequest]
    review_cadence: str
    outcome_metrics: list[str]
    content_accuracy_claim_refs: list[str]
    product_component_id: str | None = None
    ai_coach_prompt_ref: str | None = None


class SubmitCourseContentReviewRequest(BaseModel):
    ttl_hours: int = Field(default=24 * 14, ge=1)


class DecideCourseContentReviewRequest(BaseModel):
    task_id: str
    approved: bool
    reason: str


@router.post("")
async def create_draft(
    body: CreateCourseContentDraftRequest,
    repo: CourseContentRepository = Depends(get_course_content_repository),
    context: ActorContext = Depends(get_actor_context),
):
    try:
        course = await create_course_content_draft(
            repo,
            context,
            title=body.title,
            problem_statement=body.problem_statement,
            assessment_criteria=body.assessment_criteria,
            learning_goal=body.learning_goal,
            lessons=[
                CourseLesson(
                    lesson_id=lesson.lesson_id,
                    sequence=lesson.sequence,
                    title=lesson.title,
                    knowledge_point=lesson.knowledge_point,
                    action_task=lesson.action_task,
                    media_asset_ids=tuple(lesson.media_asset_ids),
                    tool_refs=tuple(lesson.tool_refs),
                )
                for lesson in body.lessons
            ],
            review_cadence=body.review_cadence,
            outcome_metrics=body.outcome_metrics,
            content_accuracy_claim_refs=body.content_accuracy_claim_refs,
            product_component_id=body.product_component_id,
            ai_coach_prompt_ref=body.ai_coach_prompt_ref,
        )
    except ProductIntelligenceDomainError as exc:
        _raise_http(exc)
    return course


@router.post("/{course_content_id}/submit-for-review")
async def submit_for_review(
    course_content_id: str,
    body: SubmitCourseContentReviewRequest,
    repo: CourseContentRepository = Depends(get_course_content_repository),
    gate: InMemoryHumanGate = Depends(get_course_content_gate),
    context: ActorContext = Depends(get_actor_context),
):
    try:
        result = await submit_course_content_for_review(
            repo, gate, context, course_content_id=course_content_id, ttl_hours=body.ttl_hours
        )
    except ProductIntelligenceDomainError as exc:
        _raise_http(exc)
    return {"course": result.course, "task_id": result.task.task_id}


@router.post("/{course_content_id}/review-decision")
async def review_decision(
    course_content_id: str,
    body: DecideCourseContentReviewRequest,
    repo: CourseContentRepository = Depends(get_course_content_repository),
    gate: InMemoryHumanGate = Depends(get_course_content_gate),
    context: ActorContext = Depends(get_actor_context),
):
    try:
        result = await decide_course_content_review(
            repo,
            gate,
            context,
            task_id=body.task_id,
            course_content_id=course_content_id,
            approved=body.approved,
            reason=body.reason,
        )
    except ProductIntelligenceDomainError as exc:
        _raise_http(exc)
    return {"course": result.course, "task_id": result.task.task_id}


@router.get("/published")
async def list_published(
    repo: CourseContentRepository = Depends(get_course_content_repository),
    context: ActorContext = Depends(get_actor_context),
):
    return await list_published_course_content(repo, context)


@router.get("/{course_content_id}")
async def get_one(
    course_content_id: str,
    repo: CourseContentRepository = Depends(get_course_content_repository),
    context: ActorContext = Depends(get_actor_context),
):
    try:
        return await get_course_content(repo, context, course_content_id=course_content_id)
    except ProductIntelligenceDomainError as exc:
        _raise_http(exc)


__all__ = [
    "clear_course_content_wiring",
    "configure_course_content_gate",
    "configure_course_content_repository",
    "router",
]
