from dataclasses import replace

import pytest

from poc.standalone_live_commerce_sandbox.contract import (
    ActorRole,
    CommerceActor,
    CommerceConflict,
    CommerceRejected,
    InMemoryCanonicalCommerceFixture,
    LiveCommerceService,
    SupportIntent,
    SupportKind,
)


def adult() -> CommerceActor:
    return CommerceActor(
        tenant_id="tenant.synthetic.alpha",
        family_id="family.synthetic.alpha",
        actor_id="guardian.synthetic.alpha",
        role=ActorRole.ADULT_GUARDIAN,
    )


def tip() -> SupportIntent:
    return SupportIntent(
        intent_ref="support.synthetic.1",
        session_ref="media.synthetic.1",
        expert_ref="expert.synthetic.1",
        tenant_id="tenant.synthetic.alpha",
        family_id="family.synthetic.alpha",
        kind=SupportKind.TIP,
        amount=500,
        currency="CNY_CENT",
        idempotency_key="support-key.synthetic.1",
    )


def test_adult_tip_preserves_amount_and_produces_expert_split() -> None:
    port = InMemoryCanonicalCommerceFixture()
    receipt = LiveCommerceService(port).support_expert(actor=adult(), intent=tip())
    assert receipt.status == "SANDBOX_AUTHORIZED"
    assert receipt.gross_amount == 500
    assert [(item.beneficiary_ref, item.amount) for item in receipt.allocations] == [
        ("expert.synthetic.1", 400),
        ("platform:aifamily", 100),
    ]


def test_points_support_uses_same_canonical_boundary() -> None:
    intent = replace(tip(), kind=SupportKind.POINTS, currency="POINT", amount=100)
    receipt = LiveCommerceService(InMemoryCanonicalCommerceFixture()).support_expert(
        actor=adult(),
        intent=intent,
    )
    assert sum(item.amount for item in receipt.allocations) == 100


def test_duplicate_support_is_idempotent_and_conflict_is_rejected() -> None:
    service = LiveCommerceService(InMemoryCanonicalCommerceFixture())
    first = service.support_expert(actor=adult(), intent=tip())
    assert service.support_expert(actor=adult(), intent=tip()) is first
    with pytest.raises(CommerceConflict):
        service.support_expert(actor=adult(), intent=replace(tip(), amount=600))


def test_child_commerce_is_absolutely_prohibited() -> None:
    child = replace(adult(), role=ActorRole.CHILD)
    with pytest.raises(CommerceRejected, match="prohibited for child"):
        LiveCommerceService(InMemoryCanonicalCommerceFixture()).support_expert(
            actor=child,
            intent=tip(),
        )


@pytest.mark.parametrize(
    ("intent", "message"),
    [
        (replace(tip(), amount=0), "positive"),
        (replace(tip(), currency="USD_CENT"), "CNY_CENT"),
        (replace(tip(), source="BACKEND"), "synthetic"),
        (replace(tip(), fixture_only=False), "synthetic"),
    ],
)
def test_invalid_or_untrusted_support_fails_closed(intent: SupportIntent, message: str) -> None:
    with pytest.raises(CommerceRejected, match=message):
        LiveCommerceService(InMemoryCanonicalCommerceFixture()).support_expert(
            actor=adult(),
            intent=intent,
        )


def test_provider_failure_creates_no_success_receipt() -> None:
    port = InMemoryCanonicalCommerceFixture()
    port.fail_next = True
    with pytest.raises(CommerceRejected, match="unavailable"):
        LiveCommerceService(port).support_expert(actor=adult(), intent=tip())
    assert port._by_key == {}


def test_cross_family_support_and_refund_are_rejected() -> None:
    port = InMemoryCanonicalCommerceFixture()
    service = LiveCommerceService(port)
    with pytest.raises(CommerceRejected, match="crossed tenant/family"):
        service.support_expert(
            actor=replace(adult(), family_id="family.synthetic.other"),
            intent=tip(),
        )
    service.support_expert(actor=adult(), intent=tip())
    with pytest.raises(CommerceRejected, match="refund crossed"):
        service.refund_support(
            actor=replace(adult(), family_id="family.synthetic.other"),
            support_intent_ref=tip().intent_ref,
            refund_ref="refund.1",
            reason="chargeback",
            idempotency_key="refund-key.1",
        )


def test_refund_reverses_every_allocation_and_is_idempotent() -> None:
    service = LiveCommerceService(InMemoryCanonicalCommerceFixture())
    service.support_expert(actor=adult(), intent=tip())
    kwargs = {
        "actor": adult(),
        "support_intent_ref": tip().intent_ref,
        "refund_ref": "refund.2",
        "reason": "adult requested refund",
        "idempotency_key": "refund-key.2",
    }
    first = service.refund_support(**kwargs)
    second = service.refund_support(**kwargs)
    assert first is second
    assert first.status == "SANDBOX_REVERSED"
    assert sum(item.amount for item in first.reversed_allocations) == -500


def test_membership_is_adult_only_and_read_through() -> None:
    service = LiveCommerceService(InMemoryCanonicalCommerceFixture())
    assert service.membership(actor=adult()) == "ORANGE_LIGHT_MEMBER"
    with pytest.raises(CommerceRejected):
        service.membership(actor=replace(adult(), role=ActorRole.CHILD))
