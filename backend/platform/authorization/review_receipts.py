"""Fail-closed authorization receipts for an adult viewing an AI draft.

The receipt is an opaque, deterministic proof of the exact immutable binding
that passed ``PolicyEngine``.  This module does not persist a ledger or create a
reviewed business fact; the Assessment-owned reviewed-signal transaction stores
the binding and receipt reference.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from backend.platform.authorization.policy import PolicyEngine
from backend.platform.identity.context import ActorContext

REVIEW_ACTION = "view_family_understanding"
REVIEW_RESOURCE_TYPE = "UnderstandingDraft"
_RECEIPT_PREFIX = "review-receipt:v1:sha256:"


class ReviewReceiptDenied(PermissionError):
    """The actor or trusted scope did not pass authorization."""


class ReviewReceiptInvalid(ValueError):
    """The proposed or presented receipt binding is invalid."""


@dataclass(frozen=True, slots=True)
class ReviewReceiptBinding:
    tenant_id: str
    family_id: str
    scope_ref: str
    artifact_ref: str
    artifact_version: int
    provenance_ref: str
    view_event_ref: str
    viewed_at: datetime
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class ReviewReceipt:
    receipt_ref: str
    status: Literal["EFFECTIVE"]
    expires_at: datetime

    def __post_init__(self) -> None:
        if not self.receipt_ref.startswith(_RECEIPT_PREFIX):
            raise ReviewReceiptInvalid("review receipt ref is invalid")
        if self.status != "EFFECTIVE":
            raise ReviewReceiptInvalid("review receipt status is not effective")


class ReviewReceiptIssuer:
    """Issue and validate exact-binding receipts after a fail-closed policy check."""

    def __init__(self, policy: PolicyEngine, *, signing_key: bytes) -> None:
        if len(signing_key) < 32:
            raise ValueError("review receipt signing_key must contain at least 32 bytes")
        self._policy = policy
        self._signing_key = bytes(signing_key)

    def issue(
        self,
        actor: ActorContext,
        binding: ReviewReceiptBinding,
        *,
        evaluated_at: datetime,
    ) -> ReviewReceipt:
        self._assert_binding(actor, binding, evaluated_at=evaluated_at)
        self._assert_allowed(actor)
        return ReviewReceipt(
            receipt_ref=_receipt_ref(actor, binding, signing_key=self._signing_key),
            status="EFFECTIVE",
            expires_at=binding.expires_at,
        )

    def validate(
        self,
        receipt: ReviewReceipt,
        actor: ActorContext,
        binding: ReviewReceiptBinding,
        *,
        evaluated_at: datetime,
    ) -> ReviewReceipt:
        self._assert_binding(actor, binding, evaluated_at=evaluated_at)
        self._assert_allowed(actor)
        expected_ref = _receipt_ref(actor, binding, signing_key=self._signing_key)
        if not hmac.compare_digest(receipt.receipt_ref, expected_ref) or (
            receipt.expires_at != binding.expires_at
        ):
            raise ReviewReceiptInvalid("review receipt binding mismatch")
        return receipt

    def _assert_allowed(self, actor: ActorContext) -> None:
        decision = self._policy.check(actor, REVIEW_ACTION, REVIEW_RESOURCE_TYPE)
        if not decision.allowed:
            raise ReviewReceiptDenied(decision.reason)

    @staticmethod
    def _assert_binding(
        actor: ActorContext,
        binding: ReviewReceiptBinding,
        *,
        evaluated_at: datetime,
    ) -> None:
        required = (
            binding.tenant_id,
            binding.family_id,
            binding.scope_ref,
            binding.artifact_ref,
            binding.provenance_ref,
            binding.view_event_ref,
        )
        if not all(value.strip() for value in required) or binding.artifact_version < 1:
            raise ReviewReceiptInvalid("review receipt binding is incomplete")
        if actor.tenant_id != binding.tenant_id:
            raise ReviewReceiptDenied("review receipt tenant scope mismatch")
        expected_scope = (
            f"family://{binding.tenant_id}/{binding.family_id}/problem-understanding"
        )
        if binding.scope_ref != expected_scope:
            raise ReviewReceiptDenied("review receipt family scope mismatch")
        for name, value in (
            ("viewed_at", binding.viewed_at),
            ("expires_at", binding.expires_at),
            ("evaluated_at", evaluated_at),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ReviewReceiptInvalid(f"review receipt {name} must be timezone-aware")
        if binding.expires_at <= binding.viewed_at:
            raise ReviewReceiptInvalid("review receipt is expired or has invalid expiry")
        if evaluated_at < binding.viewed_at:
            raise ReviewReceiptInvalid("review receipt cannot be evaluated before the view")
        if evaluated_at >= binding.expires_at:
            raise ReviewReceiptInvalid("review receipt has expired")


def _receipt_ref(
    actor: ActorContext,
    binding: ReviewReceiptBinding,
    *,
    signing_key: bytes,
) -> str:
    payload = {
        "actor_id": actor.actor_id,
        "actor_type": actor.actor_type.value,
        "tenant_id": binding.tenant_id,
        "family_id": binding.family_id,
        "scope_ref": binding.scope_ref,
        "artifact_ref": binding.artifact_ref,
        "artifact_version": binding.artifact_version,
        "provenance_ref": binding.provenance_ref,
        "view_event_ref": binding.view_event_ref,
        "viewed_at": binding.viewed_at.astimezone(UTC).isoformat(),
        "expires_at": binding.expires_at.astimezone(UTC).isoformat(),
    }
    canonical = json.dumps(payload, ensure_ascii=True, separators=(",", ":"), sort_keys=True)
    digest = hmac.new(signing_key, canonical.encode("utf-8"), hashlib.sha256).hexdigest()
    return _RECEIPT_PREFIX + digest


__all__ = [
    "REVIEW_ACTION",
    "REVIEW_RESOURCE_TYPE",
    "ReviewReceipt",
    "ReviewReceiptBinding",
    "ReviewReceiptDenied",
    "ReviewReceiptInvalid",
    "ReviewReceiptIssuer",
]
