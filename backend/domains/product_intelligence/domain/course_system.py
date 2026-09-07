"""Versioned course-system and courseware BOM contracts.

This is design-time product data.  It does not publish a course or create a
delivery fact; publication remains owned by the existing CourseContent Human
Gate lifecycle.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import ProductIntelligenceValidationError

CoursewareKind = Literal["DECK", "WORKSHEET", "IMAGE", "VIDEO", "AUDIO", "DOCUMENT"]
CoursewareQaStatus = Literal["DRAFT", "REVIEW_REQUIRED", "APPROVED"]


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


class CourseSystem(BaseModel):
    """Product-level curriculum map referenced by a ProductPackage version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    system_id: str
    version: int = Field(ge=1)
    tenant_scope: str
    product_package_version_ref: str
    stages: tuple[CourseSystemStage, ...]
    bom: tuple[CoursewareBomLine, ...] = ()

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
        return self


__all__ = ["CourseSystem", "CourseSystemStage", "CoursewareArtifactRef", "CoursewareBomLine"]
