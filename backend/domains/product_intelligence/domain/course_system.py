"""Versioned course-system and courseware BOM contracts.

This is design-time product data.  It does not publish a course or create a
delivery fact; publication remains owned by the existing CourseContent Human
Gate lifecycle.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .courseware_draft import CoursewareDraft
from .errors import ProductIntelligenceValidationError

CoursewareKind = Literal["DECK", "WORKSHEET", "IMAGE", "VIDEO", "AUDIO", "DOCUMENT"]
CoursewareQaStatus = Literal["DRAFT", "REVIEW_REQUIRED", "APPROVED"]
CoursewareRightsStatus = Literal["UNKNOWN", "CLEARED", "RESTRICTED"]
CoursewareSafetyStatus = Literal["UNKNOWN", "REVIEW_REQUIRED", "CLEARED"]
JourneyKind = Literal["MICRO_CAMP", "SCALE_PLAN"]


def _required(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductIntelligenceValidationError(f"course_system_{field_name}_required")
    return value.strip()


class CourseSystemStage(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    stage_id: str
    title: str
    lesson_start: int = Field(ge=1)
    lesson_end: int = Field(ge=1)
    outcome: str

    @field_validator("stage_id", "title", "outcome")
    @classmethod
    def non_empty(cls, value: str, info) -> str:
        return _required(value, info.field_name)

    @model_validator(mode="after")
    def validate_range(self) -> CourseSystemStage:
        if self.lesson_end - self.lesson_start != 3:
            raise ProductIntelligenceValidationError("course_system_stage_must_span_four_lessons")
        return self


class CoursewareArtifactRef(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    artifact_id: str
    kind: CoursewareKind
    version_ref: str
    provenance_ref: str
    qa_status: CoursewareQaStatus = "DRAFT"
    rights_status: CoursewareRightsStatus = "UNKNOWN"
    safety_status: CoursewareSafetyStatus = "UNKNOWN"

    @field_validator("artifact_id", "version_ref", "provenance_ref")
    @classmethod
    def non_empty(cls, value: str, info) -> str:
        return _required(value, info.field_name)


class CoursewareBomLine(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lesson_sequence: int = Field(ge=1, le=24)
    artifacts: tuple[CoursewareArtifactRef, ...]

    @field_validator("artifacts")
    @classmethod
    def artifacts_required(
        cls, value: tuple[CoursewareArtifactRef, ...]
    ) -> tuple[CoursewareArtifactRef, ...]:
        if not value:
            raise ProductIntelligenceValidationError("courseware_bom_artifacts_required")
        return value


class CourseJourneyBinding(BaseModel):
    """Design-time mapping from curriculum lessons to a service journey."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    journey_id: str
    kind: JourneyKind
    duration_days: Literal[21, 90]
    lesson_sequences: tuple[int, ...]
    service_task_refs: tuple[str, ...]
    outcome: str

    @field_validator("journey_id", "outcome")
    @classmethod
    def non_empty(cls, value: str, info) -> str:
        return _required(value, info.field_name)

    @field_validator("lesson_sequences", "service_task_refs")
    @classmethod
    def refs_required(cls, value: tuple, info) -> tuple:
        if not value or any(not item for item in value):
            raise ProductIntelligenceValidationError(f"course_journey_{info.field_name}_required")
        return value

    @model_validator(mode="after")
    def validate_duration_kind(self) -> CourseJourneyBinding:
        expected = {"MICRO_CAMP": 21, "SCALE_PLAN": 90}[self.kind]
        if self.duration_days != expected:
            raise ProductIntelligenceValidationError("course_journey_duration_kind_mismatch")
        if any(sequence < 1 or sequence > 24 for sequence in self.lesson_sequences):
            raise ProductIntelligenceValidationError("course_journey_lesson_sequence_invalid")
        return self


class CourseSystem(BaseModel):
    """Product-level curriculum map referenced by a ProductPackage version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    system_id: str
    version: int = Field(ge=1)
    tenant_scope: str
    product_package_version_ref: str
    stages: tuple[CourseSystemStage, ...]
    bom: tuple[CoursewareBomLine, ...] = ()
    courseware_drafts: tuple[CoursewareDraft, ...] = ()
    journey_bindings: tuple[CourseJourneyBinding, ...] = ()

    @field_validator("system_id", "tenant_scope", "product_package_version_ref")
    @classmethod
    def non_empty(cls, value: str, info) -> str:
        return _required(value, info.field_name)

    @model_validator(mode="after")
    def validate_coverage(self) -> CourseSystem:
        if len(self.stages) != 6:
            raise ProductIntelligenceValidationError("course_system_requires_six_stages")
        expected_start = 1
        for stage in self.stages:
            if stage.lesson_start != expected_start:
                raise ProductIntelligenceValidationError("course_system_stage_coverage_invalid")
            expected_start = stage.lesson_end + 1
        if expected_start != 25:
            raise ProductIntelligenceValidationError("course_system_must_cover_24_lessons")
        sequences = tuple(line.lesson_sequence for line in self.bom)
        if len(set(sequences)) != len(sequences):
            raise ProductIntelligenceValidationError(
                "courseware_bom_lesson_sequence_must_be_unique"
            )
        for draft in self.courseware_drafts:
            if draft.course_system_version_ref != f"course-system:{self.system_id}@v{self.version}":
                raise ProductIntelligenceValidationError("courseware_draft_system_ref_mismatch")
            if draft.product_package_version_ref != self.product_package_version_ref:
                raise ProductIntelligenceValidationError("courseware_draft_package_ref_mismatch")
        journey_kinds = {binding.kind for binding in self.journey_bindings}
        if len(journey_kinds) != len(self.journey_bindings):
            raise ProductIntelligenceValidationError("course_journey_kind_must_be_unique")
        return self


__all__ = [
    "CourseJourneyBinding",
    "CourseSystem",
    "CourseSystemStage",
    "CoursewareArtifactRef",
    "CoursewareBomLine",
]
