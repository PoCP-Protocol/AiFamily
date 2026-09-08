"""Commercial readiness contract for a service-product pilot.

This is intentionally a proposal record: pricing and entitlement data are
not customer/order facts until a human-owned commerce system accepts them.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Literal


class CommercialOfferError(ValueError):
    """Raised when an offer is not safe to hand to a commerce workflow."""


OfferStatus = Literal["DRAFT"]


@dataclass(frozen=True, slots=True)
class CommercialOfferDraft:
    """Evidence-bound offer proposal for a 21/90-day ProductPackage."""

    offer_id: str
    package_ref: str
    duration_days: int
    currency: str
    price: Decimal
    entitlement_refs: tuple[str, ...]
    delivery_sla: str
    refund_policy_ref: str
    evidence_refs: tuple[str, ...]
    status: OfferStatus = "DRAFT"

    def __post_init__(self) -> None:
        required = (self.offer_id, self.package_ref, self.currency,
                    self.delivery_sla, self.refund_policy_ref)
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise CommercialOfferError("COMMERCIAL_OFFER_FIELDS_REQUIRED")
        if self.duration_days not in {21, 90}:
            raise CommercialOfferError("COMMERCIAL_OFFER_DURATION_INVALID")
        if self.currency.upper() != self.currency or len(self.currency) != 3:
            raise CommercialOfferError("COMMERCIAL_OFFER_CURRENCY_INVALID")
        if not isinstance(self.price, Decimal) or self.price <= Decimal("0"):
            raise CommercialOfferError("COMMERCIAL_OFFER_PRICE_INVALID")
        if not self.entitlement_refs:
            raise CommercialOfferError("COMMERCIAL_OFFER_ENTITLEMENTS_REQUIRED")
        if not all(isinstance(ref, str) and ref.strip() for ref in self.entitlement_refs):
            raise CommercialOfferError("COMMERCIAL_OFFER_ENTITLEMENT_REF_INVALID")
        if not self.evidence_refs:
            raise CommercialOfferError("COMMERCIAL_OFFER_EVIDENCE_REQUIRED")
        if self.status != "DRAFT":
            raise CommercialOfferError("COMMERCIAL_OFFER_MUST_REMAIN_DRAFT")


__all__ = ["CommercialOfferDraft", "CommercialOfferError", "OfferStatus"]
