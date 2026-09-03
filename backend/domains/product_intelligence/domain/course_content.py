"""Course content aggregate for Product Intelligence.

No TS predecessor. This module is the answer to a deliberate scope split:
`entities.py::ProductComponent` / `EducationProductSpec` are *product
metadata* (they say a course-shaped product exists, spans N days, and is
built from a list of opaque component/skill ids) — neither carries the
actual teaching content (chapters, lessons, media). `CourseContent` is that
content aggregate. It is a sibling of `ProductPackageDraftContent`, not a
replacement for it: a `CourseContent` is one of the "things" a
`ProductPackageDraftVersion`/`ProductDefinition` can point at via
`component_ids`, the same way it can point at any other `ProductComponent`.

Structure follows the nine-part blueprint the project owner has been using
in course-design discussions (Problem/Assessment/Goal/Knowledge/Lesson/
Tool/Action/AICoach/Review/Outcome), kept intentionally thin per component
(a label + short narrative + refs), because this PR's job is to make the
content aggregate *exist and be governable*, not to build a full curriculum
authoring UI.

Content accuracy is not self-certified: `CourseContent` carries
`content_accuracy_claim_refs` (ids into the existing `Evidence`/claim
machinery) rather than a new claim type — `CONTENT_ACCURACY` already exists
in `product_package_draft.EvidenceClaimType`; a course reuses it instead of
inventing a course-specific claim taxonomy.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import ProductIntelligenceValidationError

CourseContentStatus = Literal["DRAFT", "UNDER_REVIEW", "PUBLISHED", "RETIRED"]


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductIntelligenceValidationError(f"course_content_{field_name}_required")
    return value.strip()


def _refs(
    values: tuple[str, ...], field_name: str, *, allow_empty: bool = False
) -> tuple[str, ...]:
    normalized = tuple(_text(value, field_name) for value in values)
    if not allow_empty and not normalized:
        raise ProductIntelligenceValidationError(f"course_content_{field_name}_required")
    if len(set(normalized)) != len(normalized):
        raise ProductIntelligenceValidationError(f"course_content_{field_name}_must_be_unique")
    return normalized


class CourseMediaAsset(BaseModel):
    """One piece of reference material (video/deck/worksheet/audio) a lesson
    points at. This aggregate stores the reference, not the binary — the
    same "content lives elsewhere, this is the pointer" convention used by
    `evidence_ref` throughout this domain."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    asset_id: str
    media_kind: Literal["VIDEO", "DECK", "WORKSHEET", "AUDIO", "DOCUMENT", "LINK"]
    title: str
    locator: str

    @field_validator("asset_id", "title", "locator")
    @classmethod
    def _non_empty(cls, value: str, info) -> str:
        return _text(value, info.field_name)


class CourseLesson(BaseModel):
    """One lesson (课时): the `Lesson`+`Knowledge`+`Action` components of the
    nine-part blueprint, kept together because in practice they are authored
    and consumed as a unit — one sitting of learning plus what a family
    should go do afterward."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    lesson_id: str
    sequence: int = Field(ge=1)
    title: str
    knowledge_point: str
    action_task: str
    media_asset_ids: tuple[str, ...] = ()
    tool_refs: tuple[str, ...] = ()

    @field_validator("lesson_id", "title", "knowledge_point", "action_task")
    @classmethod
    def _non_empty(cls, value: str, info) -> str:
        return _text(value, info.field_name)

    @field_validator("media_asset_ids", "tool_refs")
    @classmethod
    def _refs_valid(cls, value: tuple[str, ...], info):
        return _refs(value, info.field_name, allow_empty=True)


class CourseContent(BaseModel):
    """The teaching-content aggregate governed by this domain's Human Gate
    lifecycle (DRAFT -> UNDER_REVIEW -> PUBLISHED / RETIRED).

    Fields map to the nine-part blueprint:
    - Problem       -> `problem_statement`
    - Assessment    -> `assessment_criteria`
    - Goal          -> `learning_goal`
    - Knowledge/
      Lesson/Action -> `lessons` (one entry per component, see `CourseLesson`)
    - Tool          -> `CourseLesson.tool_refs`
    - AICoach       -> `ai_coach_prompt_ref` (nullable: not every course has one)
    - Review        -> `review_cadence`
    - Outcome       -> `outcome_metrics`

    `content_accuracy_claim_refs` are ids into the existing `Evidence`
    entities carrying `evidence_ref`s admitted under the `CONTENT_ACCURACY`
    claim type (see `product_package_draft.EvidenceClaimType`) — this
    aggregate does not itself re-run receipt verification; it records which
    accepted claims back its content, same as `GrowthProblem.evidence_refs`
    does for a market problem.
    """

    model_config = ConfigDict(extra="forbid")

    id: str
    version: int = Field(default=1, ge=1)
    status: CourseContentStatus = "DRAFT"
    tenant_scope: str
    created_by: str
    created_at: datetime
    updated_at: datetime

    title: str
    product_component_id: str | None = None
    problem_statement: str
    assessment_criteria: tuple[str, ...]
    learning_goal: str
    lessons: tuple[CourseLesson, ...]
    ai_coach_prompt_ref: str | None = None
    review_cadence: str
    outcome_metrics: tuple[str, ...]
    content_accuracy_claim_refs: tuple[str, ...]

    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_reason: str | None = None
    published_at: datetime | None = None

    @field_validator(
        "id",
        "tenant_scope",
        "created_by",
        "title",
        "problem_statement",
        "learning_goal",
        "review_cadence",
    )
    @classmethod
    def _text_fields_non_empty(cls, value: str, info) -> str:
        return _text(value, info.field_name)

    @field_validator("assessment_criteria", "outcome_metrics")
    @classmethod
    def _ref_lists_non_empty(cls, value: tuple[str, ...], info):
        return _refs(value, info.field_name)

    @field_validator("content_accuracy_claim_refs")
    @classmethod
    def _accuracy_refs_non_empty(cls, value: tuple[str, ...], info):
        return _refs(value, info.field_name)

    @field_validator("lessons")
    @classmethod
    def _lessons_non_empty_and_ordered(
        cls, value: tuple[CourseLesson, ...]
    ) -> tuple[CourseLesson, ...]:
        if not value:
            raise ProductIntelligenceValidationError("course_content_lessons_required")
        lesson_ids = tuple(lesson.lesson_id for lesson in value)
        if len(set(lesson_ids)) != len(lesson_ids):
            raise ProductIntelligenceValidationError("course_content_lesson_ids_must_be_unique")
        sequences = tuple(lesson.sequence for lesson in value)
        if len(set(sequences)) != len(sequences):
            raise ProductIntelligenceValidationError(
                "course_content_lesson_sequence_must_be_unique"
            )
        return tuple(sorted(value, key=lambda lesson: lesson.sequence))

    def submit_for_review(self) -> CourseContent:
        """`DRAFT -> UNDER_REVIEW`. Same "anyone can ask, only a permissioned
        HUMAN can decide" split used by `ContradictionModel.submit_for_review`."""

        if self.status != "DRAFT":
            raise ProductIntelligenceValidationError(
                "course_content_submit_for_review_illegal_source_state"
            )
        return self.model_copy(
            update={
                "status": "UNDER_REVIEW",
                "updated_at": datetime.now(UTC),
                "version": self.version + 1,
            }
        )

    def decide_review(
        self,
        *,
        approved: bool,
        actor_id: str,
        actor_type: Literal["HUMAN", "AI", "SYSTEM"],
        reason: str,
    ) -> CourseContent:
        """`DRAFT`/`UNDER_REVIEW` -> `PUBLISHED` or `REJECTED`(`DRAFT`, retained
        for resubmission) — mirrors `ContradictionModel.decide_review`'s
        Permission Pattern: this method only enforces `actor_type == HUMAN`
        and legal source-state; the permission check itself is the
        application layer's job.
        """

        if actor_type != "HUMAN":
            raise ProductIntelligenceValidationError("course_content_review_requires_human_actor")
        if self.status not in ("DRAFT", "UNDER_REVIEW"):
            raise ProductIntelligenceValidationError("course_content_review_illegal_source_state")
        if not reason or not reason.strip():
            raise ProductIntelligenceValidationError("course_content_review_requires_reason")
        now = datetime.now(UTC)
        update = {
            "updated_at": now,
            "version": self.version + 1,
            "reviewed_by": actor_id,
            "reviewed_at": now,
            "review_reason": reason,
        }
        if approved:
            update["status"] = "PUBLISHED"
            update["published_at"] = now
        else:
            update["status"] = "DRAFT"
        return self.model_copy(update=update)

    def retire(self, *, actor_id: str, reason: str) -> CourseContent:
        if self.status != "PUBLISHED":
            raise ProductIntelligenceValidationError(
                "course_content_retire_requires_published_status"
            )
        if not reason or not reason.strip():
            raise ProductIntelligenceValidationError("course_content_retire_requires_reason")
        return self.model_copy(
            update={
                "status": "RETIRED",
                "updated_at": datetime.now(UTC),
                "version": self.version + 1,
                "reviewed_by": actor_id,
                "review_reason": reason,
            }
        )

    @model_validator(mode="after")
    def _timestamps_are_aware(self) -> CourseContent:
        for value, field_name in (
            (self.created_at, "created_at"),
            (self.updated_at, "updated_at"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ProductIntelligenceValidationError(
                    f"course_content_{field_name}_must_be_aware"
                )
        return self


__all__ = [
    "CourseContent",
    "CourseContentStatus",
    "CourseLesson",
    "CourseMediaAsset",
]
