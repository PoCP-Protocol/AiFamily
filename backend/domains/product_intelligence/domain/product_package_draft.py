"""Immutable PDM package draft version owned by Product Intelligence."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import ProductIntelligenceValidationError
from .evidence_verification import VerificationMethod

PackageAuthorType = Literal["HUMAN", "AI"]
ApprovedZone = Literal["COMMODITY", "ADVANTAGE", "UNIQUE"]
ProductKind = Literal["MICRO_CAMP", "SCALE_PLAN", "CUSTOM"]
EvidenceClaimType = Literal[
    "FAMILY_NEED",
    "MARKET_EXISTENCE",
    "COMPETITOR_CAPABILITY",
    "GROWTH_MECHANISM",
    "GROWTH_EFFECT",
    "SAFETY_RISK",
    "PRIVACY_CONSENT",
    "CONTENT_ACCURACY",
    "DELIVERY_FEASIBILITY",
    "ENGAGEMENT_USABILITY",
]


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


class ProductPackageEvidenceRequirement(BaseModel):
    """Server-owned evidence requirement resolved from the source draft."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    receipt_locator: str
    claim_type: EvidenceClaimType
    required_claim_refs: tuple[str, ...]
    required_applicability_refs: tuple[str, ...]

    @field_validator("receipt_locator")
    @classmethod
    def locator_is_non_empty(cls, value: str) -> str:
        return _text(value, "receipt_locator")

    @field_validator("required_claim_refs", "required_applicability_refs")
    @classmethod
    def required_refs_are_valid(cls, value: tuple[str, ...], info):
        return _refs(value, info.field_name)


class EvidenceAdmissionSnapshot(BaseModel):
    """Receipt-backed evidence admission for one exact material claim."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    admission_status: Literal["ADMITTED"] = "ADMITTED"
    reason_codes: tuple[str, ...] = ()
    claim_type: EvidenceClaimType
    required_claim_refs: tuple[str, ...]
    required_applicability_refs: tuple[str, ...]
    receipt_id: str
    receipt_hash: str
    evidence_id: str
    evidence_version: int = Field(ge=1)
    evidence_record_hash: str
    evidence_ref: str
    claim_scope: tuple[str, ...]
    applicability_scope: tuple[str, ...]
    criteria_refs: tuple[str, ...]
    verification_methods: tuple[VerificationMethod, ...]
    verification_purpose: Literal["product_package_admission"]
    verification_policy_version: str
    receipt_outcome: Literal["VERIFIED"]
    integrity_check: Literal["PASS"]
    relevance: Literal["RELEVANT"]
    task_id: str
    proposal_id: str
    decision_id: str
    verified_at: datetime
    valid_until: datetime
    admission_policy_version: Literal["family-education-evidence-admission:v1"]
    admitted_at: datetime

    @field_validator(
        "receipt_id",
        "receipt_hash",
        "evidence_id",
        "evidence_record_hash",
        "evidence_ref",
        "verification_policy_version",
        "task_id",
        "proposal_id",
        "decision_id",
    )
    @classmethod
    def reference_is_non_empty(cls, value: str, info) -> str:
        return _text(value, info.field_name)

    @field_validator(
        "required_claim_refs",
        "required_applicability_refs",
        "claim_scope",
        "applicability_scope",
        "criteria_refs",
    )
    @classmethod
    def scopes_are_non_empty_and_unique(cls, value: tuple[str, ...], info):
        return _refs(value, info.field_name)

    @model_validator(mode="after")
    def admission_is_coherent(self) -> EvidenceAdmissionSnapshot:
        if self.reason_codes:
            raise ProductIntelligenceValidationError(
                "product_package_admitted_evidence_cannot_have_reason_codes"
            )
        for value, field_name in (
            (self.verified_at, "verified_at"),
            (self.valid_until, "valid_until"),
            (self.admitted_at, "admitted_at"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ProductIntelligenceValidationError(
                    f"product_package_{field_name}_must_be_aware"
                )
        if not self.verified_at <= self.admitted_at < self.valid_until:
            raise ProductIntelligenceValidationError(
                "product_package_evidence_admission_time_invalid"
            )
        if not set(self.required_claim_refs).issubset(self.claim_scope):
            raise ProductIntelligenceValidationError(
                "product_package_claim_scope_not_covered"
            )
        if not set(self.required_applicability_refs).issubset(self.applicability_scope):
            raise ProductIntelligenceValidationError(
                "product_package_applicability_scope_not_covered"
            )
        return self


class ProductPackageDraftContent(BaseModel):
    """Normalized content from which the immutable checksum is calculated."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.2"] = "1.2"
    draft_id: str
    version_id: str
    version: Literal["1.2.0"] = "1.2.0"
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
    evidence_admissions: tuple[EvidenceAdmissionSnapshot, ...]
    assumptions: tuple[str, ...]
    unknowns: tuple[str, ...]
    next_validation: str
    source_draft_locator: str
    intent_hash: str
    resolved_request_hash: str
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
        "source_draft_locator",
        "source_provenance_ref",
        "model_ref",
        "prompt_use_case_version",
    )
    @classmethod
    def text_fields_are_non_empty(cls, value: str, info) -> str:
        return _text(value, info.field_name)

    @field_validator("intent_hash", "resolved_request_hash")
    @classmethod
    def hashes_are_sha256(cls, value: str, info) -> str:
        normalized = _text(value, info.field_name)
        if len(normalized) != 64 or any(
            character not in "0123456789abcdef" for character in normalized
        ):
            raise ProductIntelligenceValidationError(
                f"product_package_{info.field_name}_must_be_sha256"
            )
        return normalized

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
        receipt_refs = tuple(item.receipt_id for item in self.evidence_admissions)
        if len(set(receipt_refs)) != len(receipt_refs):
            raise ProductIntelligenceValidationError(
                "product_package_evidence_admissions_must_be_unique"
            )
        if set(receipt_refs) != set(self.evidence_refs):
            raise ProductIntelligenceValidationError(
                "product_package_evidence_admissions_must_match_refs"
            )
        if any(item.valid_until < self.expires_at for item in self.evidence_admissions):
            raise ProductIntelligenceValidationError(
                "product_package_evidence_expires_before_package"
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
    "EvidenceAdmissionSnapshot",
    "EvidenceClaimType",
    "ProductPackageEvidenceRequirement",
    "ProductPackageDraftContent",
    "ProductPackageDraftVersion",
    "product_package_content_hash",
]
