"""Governed draft contract for AI-produced courseware assets.

This is product-design data, not a media file and not a published course
fact.  Providers are reached only by the Model Gateway; the draft remains
human-gated until its asset rights, safety and quality checks pass.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .errors import ProductIntelligenceValidationError

CoursewareDraftKind = Literal["DECK", "WORKSHEET", "IMAGE", "VIDEO", "AUDIO", "DOCUMENT"]
CoursewareDraftStatus = Literal["DRAFT", "REVIEW_REQUIRED", "APPROVED", "REJECTED"]
_APPROVED_STATUS = "APPROVED"


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductIntelligenceValidationError(f"courseware_draft_{field_name}_required")
    return value.strip()


class CoursewareDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    draft_id: str
    tenant_scope: str
    product_package_version_ref: str
    course_system_version_ref: str
    lesson_sequence: int = Field(ge=1, le=24)
    asset_bundle_version_ref: str
    kind: CoursewareDraftKind
    prompt_ref: str
    model_provenance_ref: str
    output_locator: str
    status: CoursewareDraftStatus = "DRAFT"
    rights_status: Literal["UNKNOWN", "CLEARED", "RESTRICTED"] = "UNKNOWN"
    safety_status: Literal["UNKNOWN", "REVIEW_REQUIRED", "CLEARED"] = "UNKNOWN"
    quality_status: Literal["UNKNOWN", "REVIEW_REQUIRED", "PASSED"] = "UNKNOWN"

    @field_validator(
        "draft_id",
        "tenant_scope",
        "product_package_version_ref",
        "course_system_version_ref",
        "asset_bundle_version_ref",
        "prompt_ref",
        "model_provenance_ref",
        "output_locator",
    )
    @classmethod
    def required_text(cls, value: str, info) -> str:
        return _text(value, info.field_name)

    def is_publishable(self) -> bool:
        return (
            self.status == _APPROVED_STATUS
            and self.rights_status == "CLEARED"
            and self.safety_status == "CLEARED"
            and self.quality_status == "PASSED"
        )


__all__ = ["CoursewareDraft", "CoursewareDraftKind", "CoursewareDraftStatus"]
