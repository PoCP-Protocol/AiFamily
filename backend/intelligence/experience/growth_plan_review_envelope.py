"""Provider-neutral trust boundary for reviewing a dynamic growth-plan draft.

The boundary validates an already persisted AI ``DRAFT`` and returns an
immutable receipt that a Human Gate composition can consume.  It deliberately
does not prescribe a 90-day horizon or a fixed stage template: duration and
stage shape are product content, while scope, evidence, provenance and the
non-mutating draft boundary are trust concerns.

This module does not import Journey and cannot create or activate a business
fact.  A later Named Action still requires an explicit human decision.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Protocol


class GrowthPlanReviewEnvelopeError(ValueError):
    """A trusted growth-plan draft is not safe to enter Human Gate."""


@dataclass(frozen=True, slots=True)
class TrustedGrowthPlanDraft:
    """Server-resolved draft envelope; never construct it from request JSON."""

    draft_id: str
    provenance_ref: str
    stable_digest: str
    tenant_id: str
    family_id: str
    subject_person_id: str
    intent_id: str
    onboarding_id: str
    priority_id: str
    allowed_evidence_refs: tuple[str, ...]
    output: Mapping[str, object]

    def __post_init__(self) -> None:
        required = (
            self.draft_id,
            self.provenance_ref,
            self.stable_digest,
            self.tenant_id,
            self.family_id,
            self.subject_person_id,
            self.intent_id,
            self.onboarding_id,
            self.priority_id,
        )
        if any(not isinstance(value, str) or not value.strip() for value in required):
            raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_IDENTITY_REQUIRED")
        if not self.allowed_evidence_refs or any(
            not isinstance(value, str) or not value.strip()
            for value in self.allowed_evidence_refs
        ):
            raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_EVIDENCE_REQUIRED")
        if len(set(self.allowed_evidence_refs)) != len(self.allowed_evidence_refs):
            raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_EVIDENCE_DUPLICATED")
        if not isinstance(self.output, Mapping):
            raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_OUTPUT_REQUIRED")


class TrustedGrowthPlanDraftPort(Protocol):
    """Persistence adapter consumed by an M1/M2 Human Gate composition."""

    async def resolve_trusted_draft(
        self,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        draft_id: str,
    ) -> TrustedGrowthPlanDraft: ...


@dataclass(frozen=True, slots=True)
class GrowthPlanValidationReceipt:
    """Evidence that a dynamic draft passed the AI review boundary."""

    draft_id: str
    provenance_ref: str
    stable_digest: str
    tenant_id: str
    family_id: str
    subject_person_id: str
    horizon_days: int
    stage_ids: tuple[str, ...]
    validation_policy: str
    receipt_digest: str
    status: str = "VALIDATED_DRAFT"
    may_mutate_business_state: bool = False


@dataclass(frozen=True, slots=True)
class DynamicGrowthPlanDraftValidator:
    """Validate trust invariants without freezing product-plan topology."""

    policy_version: str = "growth-plan-review.dynamic.v1"
    minimum_horizon_days: int = 1
    maximum_horizon_days: int = 365
    maximum_stage_count: int = 32

    def __post_init__(self) -> None:
        if not self.policy_version.strip():
            raise ValueError("policy_version is required")
        if self.minimum_horizon_days <= 0:
            raise ValueError("minimum_horizon_days must be positive")
        if self.maximum_horizon_days < self.minimum_horizon_days:
            raise ValueError("maximum_horizon_days must not be below minimum")
        if self.maximum_stage_count <= 0:
            raise ValueError("maximum_stage_count must be positive")

    def validate(
        self,
        trusted: TrustedGrowthPlanDraft,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
    ) -> GrowthPlanValidationReceipt:
        if not isinstance(trusted, TrustedGrowthPlanDraft):
            raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_REQUIRED")
        if (
            trusted.tenant_id != tenant_id
            or trusted.family_id != family_id
            or trusted.subject_person_id != subject_person_id
        ):
            raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_SCOPE_MISMATCH")

        output = trusted.output
        expected_bindings = {
            "intent_ref": trusted.intent_id,
            "onboarding_ref": trusted.onboarding_id,
            "priority_ref": trusted.priority_id,
        }
        if any(output.get(key) != value for key, value in expected_bindings.items()):
            raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_BINDING_MISMATCH")
        if output.get("draft_status") != "DRAFT":
            raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_STATUS_REQUIRED")
        _reject_fact_keys(output)

        horizon_days = output.get("horizon_days")
        if (
            isinstance(horizon_days, bool)
            or not isinstance(horizon_days, int)
            or not self.minimum_horizon_days
            <= horizon_days
            <= self.maximum_horizon_days
        ):
            raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_HORIZON_INVALID")

        allowed_refs = frozenset(trusted.allowed_evidence_refs)
        _assert_evidence_refs(output.get("evidence_refs"), allowed_refs, "draft")
        stage_ids = self._validate_stages(output.get("stages"), allowed_refs)
        _assert_pause_policy(output.get("pause_policy"))
        receipt_material = {
            "draft_id": trusted.draft_id,
            "provenance_ref": trusted.provenance_ref,
            "stable_digest": trusted.stable_digest,
            "tenant_id": trusted.tenant_id,
            "family_id": trusted.family_id,
            "subject_person_id": trusted.subject_person_id,
            "horizon_days": horizon_days,
            "stage_ids": stage_ids,
            "validation_policy": self.policy_version,
            "status": "VALIDATED_DRAFT",
            "may_mutate_business_state": False,
        }
        receipt_digest = hashlib.sha256(
            json.dumps(
                receipt_material,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return GrowthPlanValidationReceipt(
            draft_id=trusted.draft_id,
            provenance_ref=trusted.provenance_ref,
            stable_digest=trusted.stable_digest,
            tenant_id=trusted.tenant_id,
            family_id=trusted.family_id,
            subject_person_id=trusted.subject_person_id,
            horizon_days=horizon_days,
            stage_ids=stage_ids,
            validation_policy=self.policy_version,
            receipt_digest=receipt_digest,
        )

    def _validate_stages(
        self,
        raw_stages: object,
        allowed_refs: frozenset[str],
    ) -> tuple[str, ...]:
        if (
            not isinstance(raw_stages, Sequence)
            or isinstance(raw_stages, (str, bytes))
            or not raw_stages
            or len(raw_stages) > self.maximum_stage_count
        ):
            raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_STAGES_INVALID")
        stage_ids: list[str] = []
        for index, raw_stage in enumerate(raw_stages):
            if not isinstance(raw_stage, Mapping):
                raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_STAGE_INVALID")
            stage_id = raw_stage.get("stage_id")
            if not isinstance(stage_id, str) or not stage_id.strip():
                raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_STAGE_ID_REQUIRED")
            stage_ids.append(stage_id.strip())
            _assert_evidence_refs(
                raw_stage.get("evidence_refs"),
                allowed_refs,
                f"stage:{index}",
            )
        if len(set(stage_ids)) != len(stage_ids):
            raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_STAGE_IDS_DUPLICATED")
        return tuple(stage_ids)


def _assert_evidence_refs(
    value: object,
    allowed_refs: frozenset[str],
    location: str,
) -> None:
    if (
        not isinstance(value, Sequence)
        or isinstance(value, (str, bytes))
        or not value
        or any(not isinstance(item, str) or not item.strip() for item in value)
    ):
        raise GrowthPlanReviewEnvelopeError(
            f"TRUSTED_DRAFT_EVIDENCE_REFS_REQUIRED:{location}"
        )
    if not set(value).issubset(allowed_refs):
        raise GrowthPlanReviewEnvelopeError(
            f"TRUSTED_DRAFT_EVIDENCE_REF_UNKNOWN:{location}"
        )


def _assert_pause_policy(value: object) -> None:
    if not isinstance(value, Mapping):
        raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_PAUSE_POLICY_REQUIRED")
    if value.get("allowed") is not True or value.get("streak_penalty") is not False:
        raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_SAFE_PAUSE_REQUIRED")


_FORBIDDEN_FACT_KEYS = frozenset(
    {
        "authoritative_fact",
        "canonical_state",
        "family_rank",
        "family_score",
        "journey_state",
        "ranking",
    }
)


def _reject_fact_keys(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_FACT_KEYS:
                raise GrowthPlanReviewEnvelopeError("TRUSTED_DRAFT_FACT_WRITE_FORBIDDEN")
            _reject_fact_keys(item)
    elif isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        for item in value:
            _reject_fact_keys(item)


__all__ = [
    "DynamicGrowthPlanDraftValidator",
    "GrowthPlanReviewEnvelopeError",
    "GrowthPlanValidationReceipt",
    "TrustedGrowthPlanDraft",
    "TrustedGrowthPlanDraftPort",
]
