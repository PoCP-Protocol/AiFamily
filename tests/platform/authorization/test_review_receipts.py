from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.platform.authorization import PolicyEngine, PolicyRule
from backend.platform.authorization.review_receipts import (
    REVIEW_ACTION,
    REVIEW_RESOURCE_TYPE,
    ReviewReceiptBinding,
    ReviewReceiptDenied,
    ReviewReceiptInvalid,
    ReviewReceiptIssuer,
)
from backend.platform.identity.context import ActorContext, ActorType

NOW = datetime(2026, 9, 1, 9, 0, tzinfo=UTC)


def actor(actor_type: ActorType = ActorType.HUMAN) -> ActorContext:
    return ActorContext(
        actor_id="guardian-1",
        actor_type=actor_type,
        tenant_id="tenant-1",
        correlation_id="correlation-1",
    )


def binding(**changes) -> ReviewReceiptBinding:
    value = ReviewReceiptBinding(
        tenant_id="tenant-1",
        family_id="family-1",
        scope_ref="family://tenant-1/family-1/problem-understanding",
        artifact_ref="air-artifact:v1:sha256:draft-1",
        artifact_version=1,
        provenance_ref="air-provenance:v1:sha256:provenance-1",
        view_event_ref="view-event-1",
        viewed_at=NOW,
        expires_at=NOW + timedelta(hours=1),
    )
    return replace(value, **changes)


def issuer(*, register: bool = True) -> ReviewReceiptIssuer:
    policy = PolicyEngine()
    if register:
        policy.register(
            PolicyRule(
                action=REVIEW_ACTION,
                resource_type=REVIEW_RESOURCE_TYPE,
                human_only=True,
            )
        )
    return ReviewReceiptIssuer(policy, signing_key=b"r" * 32)


def test_short_signing_key_is_rejected() -> None:
    with pytest.raises(ValueError, match="32 bytes"):
        ReviewReceiptIssuer(PolicyEngine(), signing_key=b"too-short")


def test_human_allow_issues_stable_effective_opaque_receipt() -> None:
    service = issuer()

    first = service.issue(actor(), binding(), evaluated_at=NOW)
    replay = service.issue(actor(), binding(), evaluated_at=NOW)

    assert first == replay
    assert first.status == "EFFECTIVE"
    assert first.receipt_ref.startswith("review-receipt:v1:sha256:")
    assert "tenant-1" not in first.receipt_ref
    assert service.validate(first, actor(), binding(), evaluated_at=NOW) == first


def test_ai_actor_is_denied_by_human_only_policy() -> None:
    with pytest.raises(ReviewReceiptDenied, match="human_only"):
        issuer().issue(actor(ActorType.AI), binding(), evaluated_at=NOW)


def test_unregistered_action_is_denied_fail_closed() -> None:
    with pytest.raises(ReviewReceiptDenied, match="fail-closed"):
        issuer(register=False).issue(actor(), binding(), evaluated_at=NOW)


def test_view_only_policy_cannot_issue_an_effective_confirmation_receipt() -> None:
    policy = PolicyEngine()
    policy.register(
        PolicyRule(
            action="view_family_understanding",
            resource_type=REVIEW_RESOURCE_TYPE,
            human_only=True,
        )
    )
    service = ReviewReceiptIssuer(policy, signing_key=b"r" * 32)

    with pytest.raises(ReviewReceiptDenied, match="fail-closed"):
        service.issue(actor(), binding(), evaluated_at=NOW)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", ""),
        ("family_id", " "),
        ("scope_ref", ""),
        ("artifact_ref", ""),
        ("provenance_ref", ""),
        ("view_event_ref", ""),
    ],
)
def test_empty_binding_is_rejected(field: str, value: str) -> None:
    with pytest.raises(ReviewReceiptInvalid, match="binding"):
        issuer().issue(actor(), binding(**{field: value}), evaluated_at=NOW)


@pytest.mark.parametrize(
    "changed",
    [
        {"tenant_id": "tenant-2"},
        {"family_id": "family-2"},
        {"scope_ref": "family://tenant-1/family-2/problem-understanding"},
    ],
)
def test_cross_scope_binding_is_rejected(changed: dict[str, str]) -> None:
    with pytest.raises(ReviewReceiptDenied, match="scope"):
        issuer().issue(actor(), binding(**changed), evaluated_at=NOW)


def test_expired_binding_is_rejected_fail_closed() -> None:
    expired = binding(expires_at=NOW)

    with pytest.raises(ReviewReceiptInvalid, match="expired"):
        issuer().issue(actor(), expired, evaluated_at=NOW)


@pytest.mark.parametrize(
    "changed",
    [
        {"family_id": "family-2", "scope_ref": "family://tenant-1/family-2/problem-understanding"},
        {"artifact_ref": "air-artifact:v1:sha256:draft-2"},
        {"artifact_version": 2},
        {"provenance_ref": "air-provenance:v1:sha256:provenance-2"},
        {"view_event_ref": "view-event-2"},
        {"viewed_at": NOW + timedelta(seconds=1)},
        {"expires_at": NOW + timedelta(hours=2)},
    ],
)
def test_any_binding_change_produces_a_different_ref(changed: dict[str, object]) -> None:
    service = issuer()

    original = service.issue(actor(), binding(), evaluated_at=NOW)
    changed_binding = binding(**changed)
    changed_receipt = service.issue(
        actor(),
        changed_binding,
        evaluated_at=changed_binding.viewed_at,
    )

    assert changed_receipt.receipt_ref != original.receipt_ref


def test_validation_rejects_stale_binding_and_expired_receipt() -> None:
    service = issuer()
    receipt = service.issue(actor(), binding(), evaluated_at=NOW)

    with pytest.raises(ReviewReceiptInvalid, match="binding mismatch"):
        service.validate(
            receipt,
            actor(),
            binding(artifact_version=2),
            evaluated_at=NOW,
        )
    with pytest.raises(ReviewReceiptInvalid, match="expired"):
        service.validate(
            receipt,
            actor(),
            binding(),
            evaluated_at=NOW + timedelta(hours=1),
        )
