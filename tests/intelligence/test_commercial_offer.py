from decimal import Decimal

import pytest

from backend.intelligence.product_management.commercial_offer import (
    CommercialOfferDraft,
    CommercialOfferError,
)


def _offer(**overrides: object) -> CommercialOfferDraft:
    values: dict[str, object] = {
        "offer_id": "offer:family-growth-21d:v1",
        "package_ref": "package:family-growth-21d:v1",
        "duration_days": 21,
        "currency": "CNY",
        "price": Decimal("399.00"),
        "entitlement_refs": ("entitlement:courseware", "entitlement:coach-checkin"),
        "delivery_sla": "coach response within 1 business day",
        "refund_policy_ref": "policy:family-growth-standard-v1",
        "evidence_refs": ("claim:pilot-price-test",),
    }
    values.update(overrides)
    return CommercialOfferDraft(**values)  # type: ignore[arg-type]


def test_offer_is_draft_only_and_bounded_to_package_duration() -> None:
    offer = _offer()
    assert offer.status == "DRAFT"
    assert offer.duration_days == 21
    assert offer.price == Decimal("399.00")


@pytest.mark.parametrize(
    ("field", "value", "error"),
    [
        ("duration_days", 30, "COMMERCIAL_OFFER_DURATION_INVALID"),
        ("price", Decimal("0"), "COMMERCIAL_OFFER_PRICE_INVALID"),
        ("entitlement_refs", (), "COMMERCIAL_OFFER_ENTITLEMENTS_REQUIRED"),
        ("evidence_refs", (), "COMMERCIAL_OFFER_EVIDENCE_REQUIRED"),
        ("status", "RELEASED", "COMMERCIAL_OFFER_MUST_REMAIN_DRAFT"),
    ],
)
def test_offer_rejects_unsafe_or_unreviewed_values(field: str, value: object, error: str) -> None:
    with pytest.raises(CommercialOfferError, match=error):
        _offer(**{field: value})
