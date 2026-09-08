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

from dataclasses import asdict
from datetime import UTC, datetime
from typing import Literal, NoReturn

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from backend.intelligence.human_gate.contracts import ActorType, DecisionOutcome, HumanDecision
from backend.intelligence.human_gate.gate import InMemoryHumanGate
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.product_management.application.course_release_lifecycle import (
    CourseReleaseLifecycleError,
    advance_course_release_lifecycle,
)
from backend.intelligence.product_management.course_release_baseline import (
    compile_course_release_baseline,
)
from backend.intelligence.product_management.courseware_generation import generate_courseware_draft
from backend.intelligence.product_management.ipd_contracts import GateEvidence, ReleaseBaseline

from ..application.context import ActorContext
from ..application.course_delivery_projection import compile_course_delivery_projection
from ..application.course_publication import (
    CourseContentRepository,
    create_course_content_draft,
    decide_course_content_review,
    get_course_content,
    list_published_course_content,
    submit_course_content_for_review,
)
from ..application.course_system_queries import (
    CourseSystemRepository,
    get_course_system,
)
from ..domain.course_content import CourseLesson
from ..domain.course_system import CourseSystem
from ..domain.errors import ProductIntelligenceDomainError
from .courseware_dependencies import get_courseware_gateway
from .dependencies import get_actor_context

router = APIRouter(prefix="/product-intelligence/courses", tags=["product-intelligence-courses"])

COURSE_RELEASE_REVIEW_PERMISSION = "product_intelligence.course_release.review"

_ERROR_STATUS = {
    "ProductIntelligenceValidationError": 400,
    "ProductIntelligenceForbiddenError": 403,
    "ProductIntelligenceNotFoundError": 404,
}

_repository: CourseContentRepository | None = None
_course_system_repository: CourseSystemRepository | None = None
_gate: InMemoryHumanGate | None = None
_release_baselines: dict[tuple[str, str], ReleaseBaseline] = {}
_release_baseline_store = None


def configure_course_content_repository(repository: CourseContentRepository | None) -> None:
    global _repository
    _repository = repository


def configure_course_system_repository(repository: CourseSystemRepository | None) -> None:
    global _course_system_repository
    _course_system_repository = repository


def configure_course_content_gate(gate: InMemoryHumanGate | None) -> None:
    global _gate
    _gate = gate


def clear_course_content_wiring() -> None:
    configure_course_content_repository(None)
    configure_course_system_repository(None)
    configure_course_content_gate(None)
    _release_baselines.clear()
    configure_course_release_baseline_repository(None)


def configure_course_release_baseline_store(
    store: dict[tuple[str, str], ReleaseBaseline] | None,
) -> None:
    """Install the owning app's release-baseline store; ``None`` is fail-closed."""

    global _release_baselines
    _release_baselines = store if store is not None else {}


def configure_course_release_baseline_repository(repository) -> None:  # noqa: ANN001
    global _release_baseline_store
    _release_baseline_store = repository


async def get_course_content_repository() -> CourseContentRepository:
    if _repository is None:
        raise RuntimeError("course_content repository not configured — no owning app exists yet")
    return _repository


async def get_course_content_gate() -> InMemoryHumanGate:
    if _gate is None:
        raise RuntimeError("course_content Human Gate not configured — no owning app exists yet")
    return _gate


async def get_course_system_repository() -> CourseSystemRepository:
    if _course_system_repository is None:
        raise RuntimeError("course_system repository not configured")
    return _course_system_repository


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
    stage_id: str | None = None
    bom_line_ref: str | None = None


class GenerateCoursewareDraftRequest(BaseModel):
    lesson: CourseLessonRequest
    evidence_refs: list[str] = Field(min_length=1)
    context_snapshot_ref: str
    provider_id: str
    product_package_version_ref: str
    course_system_version_ref: str
    asset_bundle_version_ref: str
    kind: Literal["DECK", "WORKSHEET", "IMAGE", "VIDEO", "AUDIO", "DOCUMENT"] = "DECK"


class GenerateCoursewareDraftResponse(BaseModel):
    model_draft: dict[str, object]
    courseware_draft: dict[str, object]


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
    course_system_version_ref: str | None = None
    ai_coach_prompt_ref: str | None = None


class SubmitCourseContentReviewRequest(BaseModel):
    ttl_hours: int = Field(default=24 * 14, ge=1)


class DecideCourseContentReviewRequest(BaseModel):
    task_id: str
    approved: bool
    reason: str


class CompileCourseReleaseBaselineRequest(BaseModel):
    payload: dict[str, object]


class CourseReleaseEvidenceRequest(BaseModel):
    evidence_id: str
    kind: str
    reference: str
    summary: str


class CourseReleaseLifecycleRequest(BaseModel):
    action: Literal["APPROVE", "RELEASE", "PAUSE", "ROLLBACK", "RETIRE"]
    decision_id: str
    task_id: str
    reason: str | None = None
    evidence: list[CourseReleaseEvidenceRequest] = Field(min_length=1)
    rollback_target_ref: str | None = None


class CourseCurriculumLesson(BaseModel):
    """Read-only lesson projection for the Web course workbench.

    This is a design-time projection: it exposes governed BOM references and
    stage boundaries without pretending that AI-generated content is a fact.
    """

    sequence: int
    stage_id: str
    stage_title: str
    stage_outcome: str
    artifact_ids: tuple[str, ...]
    artifact_kinds: tuple[str, ...]


class CourseCurriculumProjection(BaseModel):
    system_id: str
    version: int
    tenant_scope: str
    lessons: tuple[CourseCurriculumLesson, ...]


@router.get("/system/{system_id}", response_model=CourseSystem)
async def get_system(
    system_id: str,
    repository: CourseSystemRepository = Depends(get_course_system_repository),
    context: ActorContext = Depends(get_actor_context),
):
    try:
        return await get_course_system(
            repository, system_id=system_id, tenant_scope=context.tenant_scope
        )
    except ProductIntelligenceDomainError as exc:
        _raise_http(exc)


@router.get("/system/{system_id}/curriculum", response_model=CourseCurriculumProjection)
async def get_curriculum_projection(
    system_id: str,
    repository: CourseSystemRepository = Depends(get_course_system_repository),
    context: ActorContext = Depends(get_actor_context),
):
    """Return the normalized 24-lesson curriculum used by the Web UI."""

    try:
        system = await get_course_system(
            repository, system_id=system_id, tenant_scope=context.tenant_scope
        )
    except ProductIntelligenceDomainError as exc:
        _raise_http(exc)

    stages_by_sequence = {
        sequence: stage
        for stage in system.stages
        for sequence in range(stage.lesson_start, stage.lesson_end + 1)
    }
    bom_by_sequence = {line.lesson_sequence: line for line in system.bom}
    lessons = tuple(
        CourseCurriculumLesson(
            sequence=sequence,
            stage_id=stages_by_sequence[sequence].stage_id,
            stage_title=stages_by_sequence[sequence].title,
            stage_outcome=stages_by_sequence[sequence].outcome,
            artifact_ids=tuple(
                artifact.artifact_id for artifact in bom_by_sequence.get(sequence, ()).artifacts
            )
            if sequence in bom_by_sequence
            else (),
            artifact_kinds=tuple(
                artifact.kind for artifact in bom_by_sequence.get(sequence, ()).artifacts
            )
            if sequence in bom_by_sequence
            else (),
        )
        for sequence in range(1, 25)
    )
    return CourseCurriculumProjection(
        system_id=system.system_id,
        version=system.version,
        tenant_scope=system.tenant_scope,
        lessons=lessons,
    )


@router.post(
    "/system/{system_id}/courseware-drafts", response_model=GenerateCoursewareDraftResponse
)
async def generate_courseware_draft_endpoint(
    system_id: str,
    body: GenerateCoursewareDraftRequest,
    gateway=Depends(get_courseware_gateway),
    repository: CourseSystemRepository = Depends(get_course_system_repository),
    context: ActorContext = Depends(get_actor_context),
):
    """Generate a governed DRAFT candidate through Model Gateway only.

    This endpoint deliberately returns candidates and never persists or publishes
    a business entity. Promotion remains a separate human-gated action.
    """
    try:
        system = await get_course_system(
            repository, system_id=system_id, tenant_scope=context.tenant_scope
        )
        if body.course_system_version_ref != f"{system.system_id}@v{system.version}":
            raise HTTPException(status_code=400, detail="COURSE_SYSTEM_VERSION_MISMATCH")
        lesson = CourseLesson(**body.lesson.model_dump())
        model_draft, candidate = await generate_courseware_draft(
            gateway,
            provider_id=body.provider_id,
            lesson=lesson,
            evidence_refs=body.evidence_refs,
            context_snapshot_ref=body.context_snapshot_ref,
            tenant_scope=context.tenant_scope,
            product_package_version_ref=body.product_package_version_ref,
            course_system_version_ref=body.course_system_version_ref,
            asset_bundle_version_ref=body.asset_bundle_version_ref,
            kind=body.kind,
        )
    except ProductIntelligenceDomainError as exc:
        _raise_http(exc)
    except ModelGatewayError as exc:
        raise HTTPException(status_code=502, detail=f"MODEL_GATEWAY_{exc.kind}") from exc
    return GenerateCoursewareDraftResponse(
        model_draft={
            "output": model_draft.output,
            "status": model_draft.status,
            "provenance": asdict(model_draft.provenance),
        },
        courseware_draft=candidate.model_dump(),
    )


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
                    stage_id=lesson.stage_id,
                    bom_line_ref=lesson.bom_line_ref,
                )
                for lesson in body.lessons
            ],
            review_cadence=body.review_cadence,
            outcome_metrics=body.outcome_metrics,
            content_accuracy_claim_refs=body.content_accuracy_claim_refs,
            product_component_id=body.product_component_id,
            course_system_version_ref=body.course_system_version_ref,
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


@router.post("/release-baselines")
async def compile_release_baseline(
    body: CompileCourseReleaseBaselineRequest,
    context: ActorContext = Depends(get_actor_context),
):
    try:
        baseline = compile_course_release_baseline(body.payload)
    except (ValueError, ProductIntelligenceDomainError) as exc:
        detail = str(exc)
        raise HTTPException(status_code=400, detail=detail) from exc
    if _release_baseline_store is not None:
        await _release_baseline_store.save(context.tenant_scope, baseline)
    else:
        _release_baselines[(context.tenant_scope, baseline.release_id)] = baseline
    return baseline


@router.get("/release-baselines/{release_id:path}")
async def get_release_baseline(
    release_id: str,
    context: ActorContext = Depends(get_actor_context),
):
    baseline = (
        await _release_baseline_store.get(context.tenant_scope, release_id)
        if _release_baseline_store is not None
        else _release_baselines.get((context.tenant_scope, release_id))
    )
    if baseline is None:
        raise HTTPException(status_code=404, detail="COURSE_RELEASE_BASELINE_NOT_FOUND")
    return baseline


@router.post("/release-baselines/{release_id:path}/lifecycle")
async def advance_release_baseline(
    release_id: str,
    body: CourseReleaseLifecycleRequest,
    context: ActorContext = Depends(get_actor_context),
):
    baseline = (
        await _release_baseline_store.get(context.tenant_scope, release_id)
        if _release_baseline_store is not None
        else _release_baselines.get((context.tenant_scope, release_id))
    )
    if baseline is None:
        raise HTTPException(status_code=404, detail="COURSE_RELEASE_BASELINE_NOT_FOUND")
    if context.actor_type != "HUMAN":
        raise HTTPException(status_code=403, detail="COURSE_RELEASE_HUMAN_ACTOR_REQUIRED")
    if COURSE_RELEASE_REVIEW_PERMISSION not in context.permissions:
        raise HTTPException(status_code=403, detail="COURSE_RELEASE_REVIEW_PERMISSION_REQUIRED")
    try:
        decision = HumanDecision(
            decision_id=body.decision_id,
            task_id=body.task_id,
            actor_id=context.actor_id,
            actor_type=ActorType.OPERATOR,
            outcome=DecisionOutcome.ACCEPT,
            reason=body.reason,
            decided_at=datetime.now(UTC),
        )
        result = advance_course_release_lifecycle(
            baseline,
            action=body.action,
            decision=decision,
            evidence=tuple(GateEvidence(**item.model_dump()) for item in body.evidence),
            rollback_target_ref=body.rollback_target_ref,
        )
    except (ValueError, CourseReleaseLifecycleError) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if _release_baseline_store is not None:
        await _release_baseline_store.save(context.tenant_scope, result.baseline)
    else:
        _release_baselines[(context.tenant_scope, release_id)] = result.baseline
    return {"baseline": result.baseline, "audit": result.audit}


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


@router.get("/{course_content_id}/delivery-projection")
async def get_delivery_projection(
    course_content_id: str,
    repo: CourseContentRepository = Depends(get_course_content_repository),
    context: ActorContext = Depends(get_actor_context),
):
    """Expose the read-only course-to-service delivery contract."""

    try:
        course = await get_course_content(repo, context, course_content_id=course_content_id)
        return compile_course_delivery_projection(course)
    except ProductIntelligenceDomainError as exc:
        _raise_http(exc)


__all__ = [
    "clear_course_content_wiring",
    "configure_course_content_gate",
    "configure_course_content_repository",
    "configure_course_release_baseline_store",
    "configure_course_release_baseline_repository",
    "COURSE_RELEASE_REVIEW_PERMISSION",
    "configure_course_system_repository",
    "router",
]
