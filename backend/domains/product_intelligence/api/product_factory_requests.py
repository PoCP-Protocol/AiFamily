"""Strict request contracts for the Product Factory draft API.

Identity, tenant scope and actor type are deliberately absent from these
models.  The API dependency supplies them from trusted authentication context;
putting them in JSON would allow a caller to impersonate another tenant.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _refs(values: list[str], field_name: str) -> list[str]:
    normalised = [value.strip() for value in values]
    if not normalised or any(not value for value in normalised):
        raise ValueError(f"{field_name}_must_not_be_empty")
    if len(set(normalised)) != len(normalised):
        raise ValueError(f"{field_name}_must_be_unique")
    return normalised


class _DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_refs: list[str] = Field(min_length=1)
    assumptions: list[str] = Field(min_length=1)
    unknowns: list[str] = Field(min_length=1)
    next_validation: str = Field(min_length=1)
    expires_at: datetime
    provenance_ref: str | None = None
    model_ref: str | None = None
    prompt_use_case_version: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)

    @field_validator("evidence_refs")
    @classmethod
    def evidence_refs_are_valid(cls, value: list[str]) -> list[str]:
        return _refs(value, "evidence_refs")

    @field_validator("assumptions")
    @classmethod
    def assumptions_are_valid(cls, value: list[str]) -> list[str]:
        return _refs(value, "assumptions")

    @field_validator("unknowns")
    @classmethod
    def unknowns_are_valid(cls, value: list[str]) -> list[str]:
        return _refs(value, "unknowns")

    @field_validator("next_validation", "provenance_ref", "model_ref", "prompt_use_case_version")
    @classmethod
    def text_is_trimmed(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value

    @field_validator("expires_at")
    @classmethod
    def expiry_is_aware_and_future(cls, value: datetime) -> datetime:
        """Reject invalid drafts before an application command can persist anything.

        The route creates the parent domain record before constructing its draft
        envelope.  Keeping this guard in the request contract makes expiry
        validation fail-closed at the HTTP boundary and avoids an orphaned
        ``MarketSignal``/``CustomerInsight`` when a caller sends a stale draft.
        """

        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("expires_at_must_be_timezone_aware")
        if value <= datetime.now(UTC):
            raise ValueError("expires_at_must_be_in_the_future")
        return value


class CreateDemandFrameRequest(_DraftRequest):
    statement: str = Field(min_length=1)
    scenario: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    target_segment: str = Field(min_length=1)
    locale: str = Field(default="zh-CN", min_length=1)
    purpose: str = Field(default="product_discovery", min_length=1)

    @field_validator("source_refs")
    @classmethod
    def source_refs_are_valid(cls, value: list[str]) -> list[str]:
        return _refs(value, "source_refs")

    @field_validator("statement", "scenario", "target_segment", "locale", "purpose")
    @classmethod
    def required_text_is_trimmed(cls, value: str) -> str:
        return value.strip()

class CreateMarketInsightDraftRequest(_DraftRequest):
    demand_ref: str = Field(min_length=1)
    statement: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    competitor_evidence_refs: list[str] = Field(default_factory=list)
    segment_ref: str | None = None

    @field_validator("source_refs")
    @classmethod
    def source_refs_are_valid(cls, value: list[str]) -> list[str]:
        return _refs(value, "source_refs")

    @field_validator("competitor_evidence_refs")
    @classmethod
    def competitor_refs_are_valid(cls, value: list[str]) -> list[str]:
        return _refs(value, "competitor_evidence_refs") if value else value

    @field_validator("demand_ref", "statement", "segment_ref")
    @classmethod
    def text_is_trimmed(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value


class CreateCompetitorEvidenceCardRequest(_DraftRequest):
    competitor_ref: str = Field(min_length=1)
    claim: str = Field(min_length=1)
    source_refs: list[str] = Field(min_length=1)
    evidence_status: Literal["VERIFIED", "UNKNOWN", "STALE", "CONTRADICTED"] = "UNKNOWN"
    demand_ref: str | None = None
    market_insight_ref: str | None = None
    source_type: str = Field(default="PUBLIC", min_length=1)

    @field_validator("source_refs")
    @classmethod
    def source_refs_are_valid(cls, value: list[str]) -> list[str]:
        return _refs(value, "source_refs")

    @field_validator("competitor_ref", "claim", "demand_ref", "market_insight_ref", "source_type")
    @classmethod
    def text_is_trimmed(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else value


class CreateProductPackageDraftRequest(_DraftRequest):
    concept_id: str = Field(min_length=1)
    product_kind: Literal["MICRO_CAMP", "SCALE_PLAN", "CUSTOM"]
    duration_days: Literal[21, 90]
    zone: Literal["HOMOGENEOUS", "ADVANTAGE", "UNIQUE_CANDIDATE", "EXCLUSIVE_CANDIDATE"]
    primary_contradiction: str = Field(min_length=1)
    demand_ref: str = Field(min_length=1)
    market_insight_refs: list[str] = Field(min_length=1)
    competitor_evidence_refs: list[str] = Field(min_length=1)
    component_ids: list[str] = Field(min_length=1)
    skill_ids: list[str] = Field(min_length=1)
    success_metric_ids: list[str] = Field(min_length=1)
    guardrail_ids: list[str] = Field(min_length=1)
    stop_conditions: list[str] = Field(min_length=1)
    pause_policy: str = Field(min_length=1)
    human_gate_policy: str = Field(min_length=1)

    @field_validator(
        "market_insight_refs",
        "competitor_evidence_refs",
        "component_ids",
        "skill_ids",
        "success_metric_ids",
        "guardrail_ids",
        "stop_conditions",
    )
    @classmethod
    def list_refs_are_valid(cls, value: list[str], info) -> list[str]:
        return _refs(value, info.field_name)

    @field_validator(
        "concept_id",
        "primary_contradiction",
        "demand_ref",
        "pause_policy",
        "human_gate_policy",
    )
    @classmethod
    def required_text_is_trimmed(cls, value: str) -> str:
        return value.strip()
