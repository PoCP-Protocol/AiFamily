"""Immutable human verification receipt for one exact product-research evidence version."""

from __future__ import annotations

import json
from datetime import datetime
from hashlib import sha256
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .errors import ProductIntelligenceValidationError

VerificationMethod = Literal[
    "SOURCE_OPENED",
    "IDENTITY_CONFIRMED",
    "CROSS_SOURCE_CHECKED",
    "DOMAIN_EXPERT_REVIEWED",
    "SYSTEM_RECORD_MATCHED",
    "EVIDENCE_RECORD_HASH_MATCHED",
]
ReceiptLifecycle = Literal["ACTIVE", "EXPIRED"]


def _text(value: str, field_name: str, maximum: int = 512) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProductIntelligenceValidationError(
            f"evidence_verification_{field_name}_required"
        )
    normalized = value.strip()
    if len(normalized) > maximum:
        raise ProductIntelligenceValidationError(
            f"evidence_verification_{field_name}_too_long"
        )
    return normalized


def _items(
    values: tuple[str, ...], field_name: str, *, maximum: int
) -> tuple[str, ...]:
    normalized = tuple(_text(value, field_name, maximum) for value in values)
    if not normalized:
        raise ProductIntelligenceValidationError(
            f"evidence_verification_{field_name}_required"
        )
    if len(set(normalized)) != len(normalized):
        raise ProductIntelligenceValidationError(
            f"evidence_verification_{field_name}_must_be_unique"
        )
    return normalized


class EvidenceVerificationReceiptContent(BaseModel):
    """Canonical fields covered by ``receipt_hash``."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    schema_version: Literal["1.0"] = "1.0"
    receipt_id: str
    version: Literal["1.0.0"] = "1.0.0"
    tenant_scope: str
    evidence_id: str
    evidence_version: int = Field(ge=1)
    evidence_record_hash: str
    evidence_ref: str
    claim_scope: tuple[str, ...]
    verification_methods: tuple[VerificationMethod, ...]
    applicability_scope: tuple[str, ...]
    criteria_refs: tuple[str, ...]
    verification_purpose: Literal["product_package_admission"]
    verification_policy_version: str
    outcome: Literal["VERIFIED"] = "VERIFIED"
    integrity_check: Literal["PASS"] = "PASS"
    relevance: Literal["RELEVANT"] = "RELEVANT"
    task_id: str
    proposal_id: str
    decision_id: str
    request_id: str
    verifier_actor_id: str
    verifier_actor_type: Literal["OPERATOR"] = "OPERATOR"
    decision_reason: str
    verified_at: datetime
    valid_until: datetime
    recorded_at: datetime
    supersedes_receipt_id: str | None = None
    request_hash: str

    @field_validator(
        "receipt_id",
        "tenant_scope",
        "evidence_id",
        "evidence_record_hash",
        "evidence_ref",
        "verification_policy_version",
        "task_id",
        "proposal_id",
        "decision_id",
        "request_id",
        "verifier_actor_id",
        "request_hash",
    )
    @classmethod
    def reference_text_is_valid(cls, value: str, info) -> str:
        return _text(value, info.field_name)

    @field_validator("decision_reason")
    @classmethod
    def decision_reason_is_valid(cls, value: str) -> str:
        return _text(value, "decision_reason", 2000)

    @field_validator("supersedes_receipt_id")
    @classmethod
    def optional_reference_is_valid(cls, value: str | None) -> str | None:
        return _text(value, "supersedes_receipt_id") if value is not None else None

    @field_validator("claim_scope", "applicability_scope")
    @classmethod
    def narrative_items_are_valid(cls, value: tuple[str, ...], info) -> tuple[str, ...]:
        return _items(value, info.field_name, maximum=2000)

    @field_validator("criteria_refs")
    @classmethod
    def criteria_refs_are_valid(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        return _items(value, "criteria_refs", maximum=512)

    @field_validator("verification_methods")
    @classmethod
    def methods_are_unique(
        cls, value: tuple[VerificationMethod, ...]
    ) -> tuple[VerificationMethod, ...]:
        if not value:
            raise ProductIntelligenceValidationError(
                "evidence_verification_methods_required"
            )
        if len(set(value)) != len(value):
            raise ProductIntelligenceValidationError(
                "evidence_verification_methods_must_be_unique"
            )
        return value

    @model_validator(mode="after")
    def times_and_lineage_are_coherent(self) -> EvidenceVerificationReceiptContent:
        for value, field_name in (
            (self.verified_at, "verified_at"),
            (self.valid_until, "valid_until"),
            (self.recorded_at, "recorded_at"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ProductIntelligenceValidationError(
                    f"evidence_verification_{field_name}_must_be_aware"
                )
        if self.valid_until <= self.verified_at:
            raise ProductIntelligenceValidationError(
                "evidence_verification_valid_until_must_follow_verification"
            )
        if self.recorded_at < self.verified_at:
            raise ProductIntelligenceValidationError(
                "evidence_verification_recorded_at_must_follow_verification"
            )
        if self.supersedes_receipt_id == self.receipt_id:
            raise ProductIntelligenceValidationError(
                "evidence_verification_cannot_supersede_itself"
            )
        return self


def evidence_verification_receipt_hash(content: EvidenceVerificationReceiptContent) -> str:
    payload = content.model_dump(mode="json")
    payload.pop("receipt_hash", None)
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


class EvidenceVerificationReceipt(EvidenceVerificationReceiptContent):
    """Append-only receipt; later revocation/supersession is a separate record."""

    receipt_hash: str

    @field_validator("receipt_hash")
    @classmethod
    def receipt_hash_is_valid(cls, value: str) -> str:
        return _text(value, "receipt_hash", 64)

    @model_validator(mode="after")
    def receipt_hash_matches(self) -> EvidenceVerificationReceipt:
        if self.receipt_hash != evidence_verification_receipt_hash(self):
            raise ProductIntelligenceValidationError(
                "evidence_verification_receipt_hash_mismatch"
            )
        return self

    def lifecycle_at(self, now: datetime) -> ReceiptLifecycle:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ProductIntelligenceValidationError(
                "evidence_verification_lifecycle_time_must_be_aware"
            )
        return "EXPIRED" if now >= self.valid_until else "ACTIVE"


__all__ = [
    "EvidenceVerificationReceipt",
    "EvidenceVerificationReceiptContent",
    "ReceiptLifecycle",
    "VerificationMethod",
    "evidence_verification_receipt_hash",
]
