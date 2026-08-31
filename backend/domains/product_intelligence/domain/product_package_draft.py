"""Immutable PDM package draft version owned by Product Intelligence."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import ProductIntelligenceValidationError

PackageAuthorType = Literal["HUMAN", "AI"]
ApprovedZone = Literal["COMMODITY", "ADVANTAGE", "UNIQUE"]
ProductKind = Literal["MICRO_CAMP", "SCALE_PLAN", "CUSTOM"]


def _text(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductIntelligenceValidationError(f"product_package_{field_name}_required")
    return value.strip()


def _refs(values: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    normalized = tuple(_text(value, field_name) for value in values)
    if not normalized:
        raise ProductIntelligenceValidationError(f"product_package_{field_name}_required")
    if len(set(normalized)) != len(normalized):
        raise ProductIntelligenceValidationError(f"product_package_{field_name}_must_be_unique")
    return normalized


class EvidenceStatusSnapshot(BaseModel):
    """One immutable evidence decision captured with the version."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_ref: str
    status: Literal["VERIFIED"]

    @field_validator("evidence_ref")
    @classmethod
    def evidence_ref_is_non_empty(cls, value: str) -> str:
        return _text(value, "evidence_ref")


class ProductPackageDraftContent(BaseModel):
    """Normalized content from which the immutable checksum is calculated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    draft_id: str
    version_id: str
    version: Literal["1.0.0"] = "1.0.0"
    status: Literal["DRAFT"] = "DRAFT"
    tenant_scope: str
    authored_by: str
    author_type: PackageAuthorType
    created_at: datetime
    expires_at: datetime
    concept_id: str
    zone_assessment_id: str
    zone_assessment_version: int = Field(ge=1)
    zone_policy_version_id: str
    approved_zone: ApprovedZone
    upstream_decision_draft_ref: str
    product_kind: ProductKind
    duration_days: int = Field(ge=1, le=180)
    primary_contradiction: str
    demand_ref: str
    market_insight_refs: tuple[str, ...]
    competitor_evidence_refs: tuple[str, ...]
    component_ids: tuple[str, ...]
    skill_ids: tuple[str, ...]
    success_metric_ids: tuple[str, ...]
    guardrail_ids: tuple[str, ...]
    stop_conditions: tuple[str, ...]
    pause_policy: str
    human_gate_policy: str
    evidence_refs: tuple[str, ...]
    evidence_statuses: tuple[EvidenceStatusSnapshot, ...]
    assumptions: tuple[str, ...]
    unknowns: tuple[str, ...]
    next_validation: str
    source_provenance_ref: str
    model_ref: str
    prompt_use_case_version: str
    confidence: float = Field(ge=0.0, le=1.0)

    @field_validator(
        "draft_id",
        "version_id",
        "tenant_scope",
        "authored_by",
        "concept_id",
        "zone_assessment_id",
        "zone_policy_version_id",
        "upstream_decision_draft_ref",
        "primary_contradiction",
        "demand_ref",
        "pause_policy",
        "human_gate_policy",
        "next_validation",
        "source_provenance_ref",
        "model_ref",
        "prompt_use_case_version",
    )
    @classmethod
    def text_fields_are_non_empty(cls, value: str, info) -> str:
        return _text(value, info.field_name)

    @field_validator(
        "market_insight_refs",
        "competitor_evidence_refs",
        "component_ids",
        "skill_ids",
        "success_metric_ids",
        "guardrail_ids",
        "stop_conditions",
        "evidence_refs",
        "assumptions",
        "unknowns",
    )
    @classmethod
    def reference_fields_are_non_empty_and_unique(cls, value: tuple[str, ...], info):
        return _refs(value, info.field_name)

    @model_validator(mode="after")
    def content_is_coherent(self) -> ProductPackageDraftContent:
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ProductIntelligenceValidationError("product_package_created_at_must_be_aware")
        if self.expires_at.tzinfo is None or self.expires_at.utcoffset() is None:
            raise ProductIntelligenceValidationError("product_package_expires_at_must_be_aware")
        if self.expires_at <= self.created_at:
            raise ProductIntelligenceValidationError("product_package_expiry_must_follow_creation")
        status_refs = tuple(item.evidence_ref for item in self.evidence_statuses)
        if len(set(status_refs)) != len(status_refs):
            raise ProductIntelligenceValidationError(
                "product_package_evidence_statuses_must_be_unique"
            )
        if set(status_refs) != set(self.evidence_refs):
            raise ProductIntelligenceValidationError(
                "product_package_evidence_statuses_must_match_refs"
            )
        return self


def product_package_content_hash(content: ProductPackageDraftContent) -> str:
    """Hash the exact normalized JSON representation persisted by the repository."""

    payload = content.model_dump(mode="json")
    payload.pop("content_hash", None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


class ProductPackageDraftVersion(ProductPackageDraftContent):
    """Frozen design snapshot; it is neither approval nor product fact."""

    content_hash: str

    @field_validator("content_hash")
    @classmethod
    def content_hash_is_non_empty(cls, value: str) -> str:
        return _text(value, "content_hash")

    @model_validator(mode="after")
    def content_hash_matches_snapshot(self) -> ProductPackageDraftVersion:
        if self.content_hash != product_package_content_hash(self):
            raise ProductIntelligenceValidationError("product_package_content_hash_mismatch")
        return self


__all__ = [
    "EvidenceStatusSnapshot",
    "ProductPackageDraftContent",
    "ProductPackageDraftVersion",
    "product_package_content_hash",
]
