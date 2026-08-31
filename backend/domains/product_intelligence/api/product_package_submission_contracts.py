"""Strict browser-safe contracts for ProductPackage review submission."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..application.product_package_source_resolution import ProductPackageDesignIntent
from ..domain.product_package_draft import ProductPackageDraftVersion


def _text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("text must not be blank")
    return normalized


def _refs(value: tuple[str, ...], *, maximum: int) -> tuple[str, ...]:
    normalized = tuple(item.strip() for item in value)
    if any(not item for item in normalized) or len(set(normalized)) != len(normalized):
        raise ValueError("references must be non-empty and unique")
    if any(len(item) > maximum for item in normalized):
        raise ValueError(f"reference items must not exceed {maximum} characters")
    return normalized


class ProductPackageReviewSubmissionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source_draft_locator: str = Field(min_length=1, max_length=256)
    concept_id: str = Field(min_length=1, max_length=160)
    zone_assessment_id: str = Field(min_length=1, max_length=160)
    product_kind: Literal["MICRO_CAMP", "SCALE_PLAN", "CUSTOM"]
    duration_days: int = Field(ge=1, le=180)
    primary_contradiction: str = Field(min_length=1, max_length=2000)
    demand_ref: str = Field(min_length=1, max_length=256)
    market_insight_refs: tuple[str, ...] = Field(min_length=1, max_length=100)
    competitor_evidence_refs: tuple[str, ...] = Field(min_length=1, max_length=100)
    component_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    skill_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    success_metric_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    guardrail_ids: tuple[str, ...] = Field(min_length=1, max_length=100)
    stop_conditions: tuple[str, ...] = Field(min_length=1, max_length=100)
    pause_policy: str = Field(min_length=1, max_length=2000)
    human_gate_policy: str = Field(min_length=1, max_length=2000)
    evidence_locators: tuple[str, ...] = Field(min_length=1, max_length=100)
    assumptions: tuple[str, ...] = Field(min_length=1, max_length=100)
    unknowns: tuple[str, ...] = Field(min_length=1, max_length=100)
    next_validation: str = Field(min_length=1, max_length=2000)
    requested_ttl_hours: int = Field(default=24, ge=1, le=168)

    @field_validator(
        "source_draft_locator",
        "concept_id",
        "zone_assessment_id",
        "primary_contradiction",
        "demand_ref",
        "pause_policy",
        "human_gate_policy",
        "next_validation",
    )
    @classmethod
    def text_is_trimmed(cls, value: str) -> str:
        return _text(value)

    @field_validator(
        "market_insight_refs",
        "competitor_evidence_refs",
        "component_ids",
        "skill_ids",
        "success_metric_ids",
        "guardrail_ids",
        "evidence_locators",
    )
    @classmethod
    def refs_are_trimmed_unique_and_bounded(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _refs(value, maximum=512)

    @field_validator(
        "stop_conditions",
        "assumptions",
        "unknowns",
    )
    @classmethod
    def narrative_items_are_trimmed_unique_and_bounded(
        cls, value: tuple[str, ...]
    ) -> tuple[str, ...]:
        return _refs(value, maximum=2000)

    def to_intent(self) -> ProductPackageDesignIntent:
        return ProductPackageDesignIntent(**self.model_dump(mode="python"))


class ProductPackageReviewTaskReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    task_id: str
    status: Literal["OPEN", "DECIDED", "EXPIRED"]
    proposal_id: str
    action_name: str
    risk_level: str
    provenance_ref: str
    created_at: datetime
    expires_at: datetime


class ProductPackageReviewSubmissionResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    lifecycle_state: Literal["SUBMITTED_FOR_REVIEW"] = "SUBMITTED_FOR_REVIEW"
    draft: ProductPackageDraftVersion
    review_task: ProductPackageReviewTaskReceipt
    etag: str
    replayed: bool


__all__ = [
    "ProductPackageReviewSubmissionRequest",
    "ProductPackageReviewSubmissionResponse",
    "ProductPackageReviewTaskReceipt",
]
