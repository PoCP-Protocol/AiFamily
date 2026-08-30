"""Executable synthetic tests for the H-LIVE-08 commerce boundary."""

from __future__ import annotations

import pytest

from poc.standalone_live_commerce_sandbox.commerce import (
    SANDBOX_SOURCE,
    AccountContext,
    ActorType,
    AttendanceEvidence,
    CommerceBoundaryError,
    CommerceIdempotencyConflict,
    CommerceRejected,
    CommerceScopeViolation,
    DeliveryEvidence,
    InMemoryCanonicalCommerceFixture,
    InMemoryCanonicalPointsFixture,
    InMemoryCanonicalSettlementFixture,
    LiveCommerceSandbox,
    LiveSessionContext,
    SessionState,
)

ADULT = AccountContext("tenant.synthetic", "family.synthetic", "adult.1", ActorType.ADULT)
CHILD = AccountContext("tenant.synthetic", "family.synthetic", "child.1", ActorType.CHILD)
OTHER = AccountContext("tenant.synthetic", "family.other", "adult.2", ActorType.ADULT)
SESSION = LiveSessionContext("tenant.synthetic", "family.synthetic", "live.synthetic.1")


def make_sandbox() -> tuple[
    LiveCommerceSandbox,
    InMemoryCanonicalCommerceFixture,
    InMemoryCanonicalPointsFixture,
    InMemoryCanonicalSettlementFixture,
]:
    commerce = InMemoryCanonicalCommerceFixture()
    points = InMemoryCanonicalPointsFixture()
    settlement = InMemoryCanonicalSettlementFixture()
    return (
        LiveCommerceSandbox(commerce=commerce, points=points, settlement=settlement),
        commerce,
        points,
        settlement,
    )


def test_adult_can_tip_through_canonical_commerce_once() -> None:
    sandbox, commerce, _, _ = make_sandbox()
    first = sandbox.send_tip(
        session=SESSION,
        purchaser=ADULT,
        amount_minor=500,
        currency="CNY",
        idempotency_key="tip.1",
    )
    second = sandbox.send_tip(
        session=SESSION,
        purchaser=ADULT,
        amount_minor=500,
        currency="CNY",
        idempotency_key="tip.1",
    )
    assert first == second
    assert len(commerce.tip_calls) == 1
    assert not hasattr(sandbox, "balance")

    with pytest.raises(CommerceIdempotencyConflict):
        sandbox.send_tip(
            session=SESSION,
            purchaser=ADULT,
            amount_minor=600,
            currency="CNY",
            idempotency_key="tip.1",
        )


def test_membership_points_and_settlement_use_separate_canonical_ports() -> None:
    sandbox, commerce, points, settlement = make_sandbox()
    membership = sandbox.purchase_membership(
        purchaser=ADULT,
        membership_sku="family.monthly.synthetic",
        amount_minor=9900,
        currency="CNY",
        idempotency_key="membership.1",
    )
    point_receipt = sandbox.award_points(
        evidence=AttendanceEvidence(
            "tenant.synthetic",
            "family.synthetic",
            "live.synthetic.1",
            "adult.1",
            True,
            "attendance.1",
        ),
        recipient=ADULT,
        points=100,
        idempotency_key="points.1",
    )
    settlement_receipt = sandbox.settle_expert(
        evidence=DeliveryEvidence(
            "tenant.synthetic", "expert.1", "live.synthetic.1", True, "delivery.1"
        ),
        amount_minor=3000,
        currency="CNY",
        idempotency_key="settle.1",
    )
    assert membership.entitlement_ref.startswith("entitlement.synthetic.")
    assert point_receipt.points_entry_ref.startswith("points.synthetic.")
    assert settlement_receipt.settlement_ref.startswith("settlement.synthetic.")
    assert len(commerce.membership_calls) == 1
    assert len(points.calls) == 1
    assert len(settlement.calls) == 1


def test_children_cross_family_and_unapproved_or_withdrawn_session_fail_closed() -> None:
    sandbox, _, _, _ = make_sandbox()
    with pytest.raises(CommerceRejected):
        sandbox.send_tip(
            session=SESSION,
            purchaser=CHILD,
            amount_minor=100,
            currency="CNY",
            idempotency_key="tip.child",
        )
    with pytest.raises(CommerceScopeViolation):
        sandbox.send_tip(
            session=SESSION,
            purchaser=OTHER,
            amount_minor=100,
            currency="CNY",
            idempotency_key="tip.scope",
        )
    for bad_session in (
        LiveSessionContext(
            "tenant.synthetic", "family.synthetic", "live.withdrawn", SessionState.WITHDRAWN
        ),
        LiveSessionContext(
            "tenant.synthetic", "family.synthetic", "live.unapproved", approved=False
        ),
    ):
        with pytest.raises(CommerceRejected):
            sandbox.send_tip(
                session=bad_session,
                purchaser=ADULT,
                amount_minor=100,
                currency="CNY",
                idempotency_key=f"tip.{bad_session.session_ref}",
            )


def test_points_need_accepted_attendance_and_settlement_needs_human_delivery() -> None:
    sandbox, _, _, _ = make_sandbox()
    not_accepted = AttendanceEvidence(
        "tenant.synthetic",
        "family.synthetic",
        "live.synthetic.1",
        "adult.1",
        False,
        "attendance.bad",
    )
    with pytest.raises(CommerceRejected):
        sandbox.award_points(
            evidence=not_accepted,
            recipient=ADULT,
            points=1,
            idempotency_key="points.bad",
        )
    not_human = DeliveryEvidence(
        "tenant.synthetic", "expert.1", "live.synthetic.1", False, "delivery.bad"
    )
    with pytest.raises(CommerceRejected):
        sandbox.settle_expert(
            evidence=not_human,
            amount_minor=1,
            currency="CNY",
            idempotency_key="settle.bad",
        )
    with pytest.raises(CommerceScopeViolation):
        sandbox.award_points(
            evidence=AttendanceEvidence(
                "tenant.synthetic",
                "family.synthetic",
                "live.synthetic.1",
                "adult.other",
                True,
                "attendance.other",
            ),
            recipient=ADULT,
            points=1,
            idempotency_key="points.other",
        )


def test_invalid_amounts_and_fixture_boundary_fail_closed() -> None:
    sandbox, _, _, _ = make_sandbox()
    with pytest.raises(ValueError):
        sandbox.send_tip(
            session=SESSION,
            purchaser=ADULT,
            amount_minor=0,
            currency="CNY",
            idempotency_key="tip.zero",
        )
    with pytest.raises(CommerceBoundaryError):
        LiveSessionContext("tenant.synthetic", "family.synthetic", "real", source="real")
    with pytest.raises(CommerceBoundaryError):
        AttendanceEvidence(
            "tenant.synthetic",
            "family.synthetic",
            "live.real",
            "adult.1",
            True,
            "attendance.real",
            source="real",
        )
    assert SESSION.source == SANDBOX_SOURCE
    assert SESSION.fixture_only is True
