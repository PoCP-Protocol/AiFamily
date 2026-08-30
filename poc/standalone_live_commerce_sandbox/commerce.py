"""Synthetic H-LIVE-08 commerce contract.

This experiment makes the product requirement for tips, points, memberships,
and expert settlement explicit without creating a second financial ledger.
Every stateful action is delegated to an AiFamily canonical Commerce,
Entitlement, Points, or Settlement port.  The in-memory objects below are
test doubles that record calls; they do not hold balances or move money.

Only an authenticated adult may initiate a commercial action.  Children are
never exposed to public tipping, ranking, referral, or automated marketing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

SANDBOX_SOURCE = "SANDBOX_SYNTHETIC"


class CommerceBoundaryError(ValueError):
    """A commerce fixture violates the explicit sandbox boundary."""


class CommerceRejected(RuntimeError):
    """The commercial action is not permitted."""


class CommerceScopeViolation(CommerceRejected):
    """A commercial action crossed tenant/family scope."""


class CommerceIdempotencyConflict(CommerceRejected):
    """An idempotency key was reused for a different commercial command."""


class ActorType(StrEnum):
    ADULT = "ADULT"
    CHILD = "CHILD"
    EXPERT = "EXPERT"


class SessionState(StrEnum):
    LIVE = "LIVE"
    ENDED = "ENDED"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"


@dataclass(frozen=True, slots=True)
class AccountContext:
    tenant_id: str
    family_id: str
    actor_id: str
    actor_type: ActorType

    def __post_init__(self) -> None:
        if not all((self.tenant_id, self.family_id, self.actor_id)):
            raise ValueError("account scope fields must not be empty")


@dataclass(frozen=True, slots=True)
class LiveSessionContext:
    tenant_id: str
    family_id: str
    session_ref: str
    state: SessionState = SessionState.LIVE
    approved: bool = True
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True

    def __post_init__(self) -> None:
        if not self.fixture_only or self.source != SANDBOX_SOURCE:
            raise CommerceBoundaryError("commerce fixture must be explicitly synthetic")
        if not all((self.tenant_id, self.family_id, self.session_ref)):
            raise ValueError("session identity and scope must not be empty")


@dataclass(frozen=True, slots=True)
class AttendanceEvidence:
    tenant_id: str
    family_id: str
    session_ref: str
    guardian_id: str
    accepted: bool
    receipt_ref: str
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True

    def __post_init__(self) -> None:
        if not self.fixture_only or self.source != SANDBOX_SOURCE:
            raise CommerceBoundaryError("attendance evidence must be explicitly synthetic")


@dataclass(frozen=True, slots=True)
class DeliveryEvidence:
    tenant_id: str
    expert_id: str
    session_ref: str
    accepted_by_human: bool
    delivery_ref: str
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True

    def __post_init__(self) -> None:
        if not self.fixture_only or self.source != SANDBOX_SOURCE:
            raise CommerceBoundaryError("delivery evidence must be explicitly synthetic")


@dataclass(frozen=True, slots=True)
class TipReceipt:
    payment_ref: str
    ledger_entry_ref: str
    audit_ref: str


@dataclass(frozen=True, slots=True)
class MembershipReceipt:
    payment_ref: str
    entitlement_ref: str
    audit_ref: str


@dataclass(frozen=True, slots=True)
class PointAwardReceipt:
    points_entry_ref: str
    audit_ref: str


@dataclass(frozen=True, slots=True)
class SettlementReceipt:
    settlement_ref: str
    ledger_entry_ref: str
    audit_ref: str


class CanonicalCommercePort(Protocol):
    """AiFamily-owned payment and entitlement boundary."""

    def send_tip(
        self,
        *,
        tenant_id: str,
        family_id: str,
        purchaser_id: str,
        session_ref: str,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
    ) -> TipReceipt: ...

    def purchase_membership(
        self,
        *,
        tenant_id: str,
        family_id: str,
        purchaser_id: str,
        membership_sku: str,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
    ) -> MembershipReceipt: ...


class CanonicalPointsPort(Protocol):
    """AiFamily-owned points ledger; balances are not duplicated here."""

    def award_points(
        self,
        *,
        tenant_id: str,
        family_id: str,
        guardian_id: str,
        receipt_ref: str,
        points: int,
        idempotency_key: str,
    ) -> PointAwardReceipt: ...


class CanonicalSettlementPort(Protocol):
    """AiFamily-owned expert settlement boundary."""

    def settle_expert(
        self,
        *,
        tenant_id: str,
        expert_id: str,
        delivery_ref: str,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
    ) -> SettlementReceipt: ...


class InMemoryCanonicalCommerceFixture:
    """Call-recording fake; it has no balance, wallet, or payment state."""

    def __init__(self) -> None:
        self.tip_calls: list[dict[str, object]] = []
        self.membership_calls: list[dict[str, object]] = []
        self._tips: dict[str, tuple[str, TipReceipt]] = {}
        self._memberships: dict[str, tuple[str, MembershipReceipt]] = {}

    def send_tip(self, **kwargs: object) -> TipReceipt:
        key = str(kwargs["idempotency_key"])
        previous = self._tips.get(key)
        if previous is not None:
            fingerprint, receipt = previous
            if fingerprint != _fingerprint(kwargs):
                raise CommerceIdempotencyConflict("tip key was reused for another command")
            return receipt
        receipt = TipReceipt(
            payment_ref=f"payment.synthetic.{len(self.tip_calls) + 1}",
            ledger_entry_ref=f"ledger.synthetic.tip.{len(self.tip_calls) + 1}",
            audit_ref=f"audit.synthetic.tip.{len(self.tip_calls) + 1}",
        )
        self._tips[key] = (_fingerprint(kwargs), receipt)
        self.tip_calls.append(dict(kwargs))
        return receipt

    def purchase_membership(self, **kwargs: object) -> MembershipReceipt:
        key = str(kwargs["idempotency_key"])
        previous = self._memberships.get(key)
        if previous is not None:
            fingerprint, receipt = previous
            if fingerprint != _fingerprint(kwargs):
                raise CommerceIdempotencyConflict("membership key was reused for another command")
            return receipt
        receipt = MembershipReceipt(
            payment_ref=f"payment.synthetic.membership.{len(self.membership_calls) + 1}",
            entitlement_ref=f"entitlement.synthetic.{len(self.membership_calls) + 1}",
            audit_ref=f"audit.synthetic.membership.{len(self.membership_calls) + 1}",
        )
        self._memberships[key] = (_fingerprint(kwargs), receipt)
        self.membership_calls.append(dict(kwargs))
        return receipt


class InMemoryCanonicalPointsFixture:
    """Call-recording fake; it never computes or exposes a family total."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self._by_key: dict[str, tuple[str, PointAwardReceipt]] = {}

    def award_points(self, **kwargs: object) -> PointAwardReceipt:
        key = str(kwargs["idempotency_key"])
        previous = self._by_key.get(key)
        if previous is not None:
            fingerprint, receipt = previous
            if fingerprint != _fingerprint(kwargs):
                raise CommerceIdempotencyConflict("points key was reused for another command")
            return receipt
        receipt = PointAwardReceipt(
            points_entry_ref=f"points.synthetic.{len(self.calls) + 1}",
            audit_ref=f"audit.synthetic.points.{len(self.calls) + 1}",
        )
        self._by_key[key] = (_fingerprint(kwargs), receipt)
        self.calls.append(dict(kwargs))
        return receipt


class InMemoryCanonicalSettlementFixture:
    """Call-recording fake; settlement is not executed in the sandbox."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []
        self._by_key: dict[str, tuple[str, SettlementReceipt]] = {}

    def settle_expert(self, **kwargs: object) -> SettlementReceipt:
        key = str(kwargs["idempotency_key"])
        previous = self._by_key.get(key)
        if previous is not None:
            fingerprint, receipt = previous
            if fingerprint != _fingerprint(kwargs):
                raise CommerceIdempotencyConflict("settlement key was reused for another command")
            return receipt
        receipt = SettlementReceipt(
            settlement_ref=f"settlement.synthetic.{len(self.calls) + 1}",
            ledger_entry_ref=f"ledger.synthetic.settlement.{len(self.calls) + 1}",
            audit_ref=f"audit.synthetic.settlement.{len(self.calls) + 1}",
        )
        self._by_key[key] = (_fingerprint(kwargs), receipt)
        self.calls.append(dict(kwargs))
        return receipt


class LiveCommerceSandbox:
    """Guarded orchestration over canonical commerce ports."""

    def __init__(
        self,
        *,
        commerce: CanonicalCommercePort,
        points: CanonicalPointsPort,
        settlement: CanonicalSettlementPort,
    ) -> None:
        self.commerce = commerce
        self.points = points
        self.settlement = settlement

    def send_tip(
        self,
        *,
        session: LiveSessionContext,
        purchaser: AccountContext,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
    ) -> TipReceipt:
        self._assert_adult(purchaser)
        self._assert_scope(session, purchaser)
        self._assert_commercially_available(session)
        if amount_minor <= 0 or not currency or not idempotency_key:
            raise ValueError("tip amount, currency and idempotency key are required")
        return self.commerce.send_tip(
            tenant_id=purchaser.tenant_id,
            family_id=purchaser.family_id,
            purchaser_id=purchaser.actor_id,
            session_ref=session.session_ref,
            amount_minor=amount_minor,
            currency=currency,
            idempotency_key=idempotency_key,
        )

    def purchase_membership(
        self,
        *,
        purchaser: AccountContext,
        membership_sku: str,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
    ) -> MembershipReceipt:
        self._assert_adult(purchaser)
        if not membership_sku or amount_minor <= 0 or not currency or not idempotency_key:
            raise ValueError("membership sku, price, currency and idempotency key are required")
        return self.commerce.purchase_membership(
            tenant_id=purchaser.tenant_id,
            family_id=purchaser.family_id,
            purchaser_id=purchaser.actor_id,
            membership_sku=membership_sku,
            amount_minor=amount_minor,
            currency=currency,
            idempotency_key=idempotency_key,
        )

    def award_points(
        self,
        *,
        evidence: AttendanceEvidence,
        recipient: AccountContext,
        points: int,
        idempotency_key: str,
    ) -> PointAwardReceipt:
        self._assert_adult(recipient)
        if evidence.tenant_id != recipient.tenant_id or evidence.family_id != recipient.family_id:
            raise CommerceScopeViolation("points evidence crossed tenant/family scope")
        if evidence.guardian_id != recipient.actor_id:
            raise CommerceScopeViolation("points evidence belongs to another guardian")
        if not evidence.accepted:
            raise CommerceRejected("points require accepted attendance evidence")
        if points <= 0 or not idempotency_key:
            raise ValueError("points and idempotency key are required")
        return self.points.award_points(
            tenant_id=recipient.tenant_id,
            family_id=recipient.family_id,
            guardian_id=recipient.actor_id,
            receipt_ref=evidence.receipt_ref,
            points=points,
            idempotency_key=idempotency_key,
        )

    def settle_expert(
        self,
        *,
        evidence: DeliveryEvidence,
        amount_minor: int,
        currency: str,
        idempotency_key: str,
    ) -> SettlementReceipt:
        if not evidence.accepted_by_human:
            raise CommerceRejected("expert settlement requires human-accepted delivery")
        if amount_minor <= 0 or not currency or not idempotency_key:
            raise ValueError("settlement amount, currency and idempotency key are required")
        return self.settlement.settle_expert(
            tenant_id=evidence.tenant_id,
            expert_id=evidence.expert_id,
            delivery_ref=evidence.delivery_ref,
            amount_minor=amount_minor,
            currency=currency,
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _assert_adult(actor: AccountContext) -> None:
        if actor.actor_type is not ActorType.ADULT:
            raise CommerceRejected("commercial actions are adult-only")

    @staticmethod
    def _assert_scope(session: LiveSessionContext, actor: AccountContext) -> None:
        if session.tenant_id != actor.tenant_id or session.family_id != actor.family_id:
            raise CommerceScopeViolation("commerce request crossed tenant/family scope")

    @staticmethod
    def _assert_commercially_available(session: LiveSessionContext) -> None:
        if not session.approved or session.state is not SessionState.LIVE:
            raise CommerceRejected("session is not commercially available")


def _fingerprint(values: dict[str, object]) -> str:
    """Stable comparison of a fake command, excluding the idempotency key."""

    return repr(
        sorted((key, str(value)) for key, value in values.items() if key != "idempotency_key")
    )
