"""Course draft -> Human Gate review -> publication, reusing `InMemoryHumanGate`.

Mirrors the "anyone can create/submit a DRAFT, only a permissioned HUMAN can
decide" split used throughout this domain (`contradiction_commands.py`,
`product_package_submission.py`), but deliberately does not reuse the
receipt-verification machinery in `product_package_evidence_admission.py` —
that module authenticates *market/design* claims against a cryptographic
evidence ledger; a course's `content_accuracy_claim_refs` here simply record
which existing `Evidence` records back the content, the same lightweight
reference discipline `GrowthProblem.evidence_refs` already uses. Building a
second receipt pipeline for course content is out of scope for standing the
aggregate up.

The Human Gate task itself is real (`backend.intelligence.human_gate`): a
course draft becomes an `ActionProposal` under a `PUBLISH_COURSE_CONTENT`
Named Action, an `InMemoryHumanGate` opens a task for it, and only a human
`decide()` on that task flips the course to `PUBLISHED`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from backend.intelligence.human_gate.contracts import (
    ActionProposal,
    DecisionOutcome,
    GateScope,
    HumanTask,
)
from backend.intelligence.human_gate.contracts import ActorType as GateActorType
from backend.intelligence.human_gate.gate import InMemoryHumanGate

from ..domain.course_content import CourseContent, CourseLesson
from ..domain.errors import (
    ProductIntelligenceForbiddenError,
    ProductIntelligenceNotFoundError,
    ProductIntelligenceValidationError,
)
from .context import ActorContext

COURSE_CONTENT_AUTHOR_PERMISSION = "product_intelligence.course_content.author"
COURSE_CONTENT_REVIEW_PERMISSION = "product_intelligence.course_content.review"
PUBLISH_COURSE_CONTENT_ACTION = "PUBLISH_COURSE_CONTENT"
COURSE_CONTENT_REVIEW_PURPOSE = "product_intelligence.course_content.review"
COURSE_CONTENT_PROCESSING_BASIS = "processing-basis:internal-product-design:v1"


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4()}"


def _now() -> datetime:
    return datetime.now(UTC)


class CourseContentRepository(Protocol):
    async def save_course_content(self, course: CourseContent) -> None: ...

    async def load_course_content(self, course_id: str, tenant_scope: str) -> CourseContent: ...

    async def list_published_course_content(self, tenant_scope: str) -> list[CourseContent]: ...


def _require_author_permission(context: ActorContext) -> None:
    if context.actor_type != "HUMAN" or COURSE_CONTENT_AUTHOR_PERMISSION not in context.permissions:
        raise ProductIntelligenceForbiddenError("course_content_author_permission_required")


def _require_review_permission(context: ActorContext) -> None:
    if context.actor_type != "HUMAN" or COURSE_CONTENT_REVIEW_PERMISSION not in context.permissions:
        raise ProductIntelligenceForbiddenError("course_content_review_permission_required")


async def create_course_content_draft(
    repo: CourseContentRepository,
    context: ActorContext,
    *,
    title: str,
    problem_statement: str,
    assessment_criteria: list[str],
    learning_goal: str,
    lessons: list[CourseLesson],
    review_cadence: str,
    outcome_metrics: list[str],
    content_accuracy_claim_refs: list[str],
    product_component_id: str | None = None,
    ai_coach_prompt_ref: str | None = None,
) -> CourseContent:
    """Create a `DRAFT` `CourseContent`. Requires `course_content.author`."""

    _require_author_permission(context)
    now = _now()
    course = CourseContent(
        id=_new_id("course-content"),
        tenant_scope=context.tenant_scope,
        created_by=context.actor_id,
        created_at=now,
        updated_at=now,
        title=title,
        product_component_id=product_component_id,
        problem_statement=problem_statement,
        assessment_criteria=tuple(assessment_criteria),
        learning_goal=learning_goal,
        lessons=tuple(lessons),
        ai_coach_prompt_ref=ai_coach_prompt_ref,
        review_cadence=review_cadence,
        outcome_metrics=tuple(outcome_metrics),
        content_accuracy_claim_refs=tuple(content_accuracy_claim_refs),
    )
    await repo.save_course_content(course)
    return course


@dataclass(frozen=True, slots=True)
class CourseContentSubmissionResult:
    course: CourseContent
    task: HumanTask


async def submit_course_content_for_review(
    repo: CourseContentRepository,
    gate: InMemoryHumanGate,
    context: ActorContext,
    *,
    course_content_id: str,
    ttl_hours: int = 24 * 14,
) -> CourseContentSubmissionResult:
    """`DRAFT -> UNDER_REVIEW`, then open a Human Gate task under
    `PUBLISH_COURSE_CONTENT`. Requires `course_content.author` (same actor
    who may create a draft may ask for review — the decision itself needs
    the separate `course_content.review` permission, enforced by
    `decide_course_content_review`)."""

    _require_author_permission(context)
    course = await repo.load_course_content(course_content_id, context.tenant_scope)
    submitted = course.submit_for_review()
    now = _now()
    proposal = ActionProposal(
        proposal_id=_new_id("course-content-proposal"),
        draft_id=submitted.id,
        draft_status="DRAFT",
        action_name=PUBLISH_COURSE_CONTENT_ACTION,
        action_arguments={
            "course_content_id": submitted.id,
            "title": submitted.title,
            "version": submitted.version,
        },
        scope=GateScope(
            tenant_id=context.tenant_scope,
            family_id=None,
            subject_ids=(submitted.id,),
            purpose=COURSE_CONTENT_REVIEW_PURPOSE,
            consent_version=COURSE_CONTENT_PROCESSING_BASIS,
            correlation_id=context.trace_id or f"trace:{submitted.id}",
        ),
        allowed_actor_types=(GateActorType.OPERATOR,),
        risk_level="MEDIUM",
        provenance_ref=f"course-content-draft:{submitted.id}:v{submitted.version}",
        created_at=now,
        expires_at=now + timedelta(hours=ttl_hours),
    )
    task = gate.submit(proposal)
    await repo.save_course_content(submitted)
    return CourseContentSubmissionResult(course=submitted, task=task)


async def decide_course_content_review(
    repo: CourseContentRepository,
    gate: InMemoryHumanGate,
    context: ActorContext,
    *,
    task_id: str,
    course_content_id: str,
    approved: bool,
    reason: str,
) -> CourseContentSubmissionResult:
    """The only path that can move a course to `PUBLISHED`/back to `DRAFT`.
    Requires `course_content.review`; `actor_type == HUMAN` is re-checked
    inside `CourseContent.decide_review` (defense in depth, same reasoning
    as `decide_contradiction_review`)."""

    _require_review_permission(context)
    task, _ = gate.decide(
        task_id,
        actor_id=context.actor_id,
        actor_type=GateActorType.OPERATOR,
        outcome=DecisionOutcome.ACCEPT if approved else DecisionOutcome.REJECT,
        reason=reason,
    )
    if task.proposal.action_arguments.get("course_content_id") != course_content_id:
        raise ProductIntelligenceValidationError("course_content_task_mismatch")
    course = await repo.load_course_content(course_content_id, context.tenant_scope)
    decided = course.decide_review(
        approved=approved, actor_id=context.actor_id, actor_type="HUMAN", reason=reason
    )
    await repo.save_course_content(decided)
    return CourseContentSubmissionResult(course=decided, task=task)


async def get_course_content(
    repo: CourseContentRepository, context: ActorContext, *, course_content_id: str
) -> CourseContent:
    try:
        return await repo.load_course_content(course_content_id, context.tenant_scope)
    except KeyError as exc:
        raise ProductIntelligenceNotFoundError("course_content_not_found") from exc


async def list_published_course_content(
    repo: CourseContentRepository, context: ActorContext
) -> list[CourseContent]:
    """Published-only listing for downstream `CourseSupplyAdapter` matching."""

    return await repo.list_published_course_content(context.tenant_scope)


__all__ = [
    "COURSE_CONTENT_AUTHOR_PERMISSION",
    "COURSE_CONTENT_PROCESSING_BASIS",
    "COURSE_CONTENT_REVIEW_PERMISSION",
    "COURSE_CONTENT_REVIEW_PURPOSE",
    "PUBLISH_COURSE_CONTENT_ACTION",
    "CourseContentRepository",
    "CourseContentSubmissionResult",
    "create_course_content_draft",
    "decide_course_content_review",
    "get_course_content",
    "list_published_course_content",
    "submit_course_content_for_review",
]
