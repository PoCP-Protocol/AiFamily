"""Adult-only live commerce contract over canonical platform ports.

This module owns no wallet, payment, membership, points, or settlement data.
The in-memory port is a replayable sandbox double used to prove invariants
before integration with AiFamily's canonical commerce capabilities.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

SANDBOX_SOURCE = "SANDBOX_SYNTHETIC"


class CommerceRejected(RuntimeError):
    """A live commerce intent failed a mandatory invariant."""


class CommerceConflict(CommerceRejected):
    """An idempotency key was reused for another intent."""


class ActorRole(StrEnum):
    ADULT_GUARDIAN = "ADULT_GUARDIAN"
    CHILD = "CHILD"


class SupportKind(StrEnum):
    TIP = "TIP"
    POINTS = "POINTS"


@dataclass(frozen=True, slots=True)
class CommerceActor:
    tenant_id: str
    family_id: str
    actor_id: str
    role: ActorRole


@dataclass(frozen=True, slots=True)
class SupportIntent:
    intent_ref: str
    session_ref: str
    expert_ref: str
    tenant_id: str
    family_id: str
    kind: SupportKind
    amount: int
    currency: str
    idempotency_key: str
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


@dataclass(frozen=True, slots=True)
class RevenueAllocation:
    beneficiary_ref: str
    amount: int


@dataclass(frozen=True, slots=True)
class SupportReceipt:
    intent_ref: str
    status: str
    gross_amount: int
    allocations: tuple[RevenueAllocation, ...]
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


@dataclass(frozen=True, slots=True)
class RefundReceipt:
    refund_ref: str
    support_intent_ref: str
    status: str
    reversed_allocations: tuple[RevenueAllocation, ...]
    reason: str
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


class CanonicalCommercePort(Protocol):
    """AiFamily-owned payment/points/membership/settlement boundary."""

    def authorize_support(
        self,
        *,
        actor: CommerceActor,
        intent: SupportIntent,
        allocations: tuple[RevenueAllocation, ...],
    ) -> SupportReceipt: ...

    def active_membership(self, *, actor: CommerceActor) -> str | None: ...

    def reverse_support(
        self,
        *,
        actor: CommerceActor,
        support_intent_ref: str,
        refund_ref: str,
        reason: str,
        idempotency_key: str,
    ) -> RefundReceipt: ...


class LiveCommerceService:
    def __init__(self, commerce: CanonicalCommercePort) -> None:
        self._commerce = commerce

    def support_expert(self, *, actor: CommerceActor, intent: SupportIntent) -> SupportReceipt:
        self._assert_adult(actor)
        if actor.tenant_id != intent.tenant_id or actor.family_id != intent.family_id:
            raise CommerceRejected("support intent crossed tenant/family scope")
        if intent.source != SANDBOX_SOURCE or not intent.fixture_only:
            raise CommerceRejected("only explicit synthetic intents are accepted")
        if intent.amount <= 0:
            raise CommerceRejected("support amount must be positive")
        if intent.kind is SupportKind.TIP and intent.currency != "CNY_CENT":
            raise CommerceRejected("cash support must use CNY_CENT")
        if intent.kind is SupportKind.POINTS and intent.currency != "POINT":
            raise CommerceRejected("points support must use POINT")
        platform_amount = intent.amount * 20 // 100
        allocations = (
            RevenueAllocation(intent.expert_ref, intent.amount - platform_amount),
            RevenueAllocation("platform:aifamily", platform_amount),
        )
        return self._commerce.authorize_support(
            actor=actor,
            intent=intent,
            allocations=allocations,
        )

    def membership(self, *, actor: CommerceActor) -> str | None:
        self._assert_adult(actor)
        return self._commerce.active_membership(actor=actor)

    def refund_support(
        self,
        *,
        actor: CommerceActor,
        support_intent_ref: str,
        refund_ref: str,
        reason: str,
        idempotency_key: str,
    ) -> RefundReceipt:
        self._assert_adult(actor)
        if not all((support_intent_ref, refund_ref, reason.strip(), idempotency_key)):
            raise CommerceRejected("refund reference, reason and idempotency key are required")
        return self._commerce.reverse_support(
            actor=actor,
            support_intent_ref=support_intent_ref,
            refund_ref=refund_ref,
            reason=reason.strip(),
            idempotency_key=idempotency_key,
        )

    @staticmethod
    def _assert_adult(actor: CommerceActor) -> None:
        if actor.role is not ActorRole.ADULT_GUARDIAN:
            raise CommerceRejected("live commerce is prohibited for child actors")
        if not all((actor.tenant_id, actor.family_id, actor.actor_id)):
            raise CommerceRejected("trusted tenant/family/actor scope is required")


class InMemoryCanonicalCommerceFixture:
    """No-side-effect test double; never a production ledger."""

    def __init__(self) -> None:
        self._by_key: dict[str, tuple[CommerceActor, SupportIntent, SupportReceipt]] = {}
        self._by_intent: dict[str, tuple[CommerceActor, SupportReceipt]] = {}
        self._refunds: dict[str, tuple[str, RefundReceipt]] = {}
        self.membership_code: str | None = "ORANGE_LIGHT_MEMBER"
        self.fail_next = False

    def authorize_support(
        self,
        *,
        actor: CommerceActor,
        intent: SupportIntent,
        allocations: tuple[RevenueAllocation, ...],
    ) -> SupportReceipt:
        previous = self._by_key.get(intent.idempotency_key)
        if previous is not None:
            if previous[0] != actor or previous[1] != intent:
                raise CommerceConflict("idempotency key reused for another support intent")
            return previous[2]
        if self.fail_next:
            self.fail_next = False
            raise CommerceRejected("canonical commerce provider unavailable")
        if sum(item.amount for item in allocations) != intent.amount:
            raise CommerceRejected("revenue allocations do not conserve gross amount")
        receipt = SupportReceipt(
            intent_ref=intent.intent_ref,
            status="SANDBOX_AUTHORIZED",
            gross_amount=intent.amount,
            allocations=allocations,
        )
        self._by_key[intent.idempotency_key] = (actor, intent, receipt)
        self._by_intent[intent.intent_ref] = (actor, receipt)
        return receipt

    def active_membership(self, *, actor: CommerceActor) -> str | None:
        del actor
        return self.membership_code

    def reverse_support(
        self,
        *,
        actor: CommerceActor,
        support_intent_ref: str,
        refund_ref: str,
        reason: str,
        idempotency_key: str,
    ) -> RefundReceipt:
        previous = self._refunds.get(idempotency_key)
        if previous is not None:
            if previous[0] != support_intent_ref:
                raise CommerceConflict("refund key reused for another support intent")
            return previous[1]
        original = self._by_intent.get(support_intent_ref)
        if original is None:
            raise CommerceRejected("support intent not found")
        original_actor, receipt = original
        if (
            actor.tenant_id != original_actor.tenant_id
            or actor.family_id != original_actor.family_id
        ):
            raise CommerceRejected("refund crossed tenant/family scope")
        refund = RefundReceipt(
            refund_ref=refund_ref,
            support_intent_ref=support_intent_ref,
            status="SANDBOX_REVERSED",
            reversed_allocations=tuple(
                RevenueAllocation(item.beneficiary_ref, -item.amount)
                for item in receipt.allocations
            ),
            reason=reason,
        )
        self._refunds[idempotency_key] = (support_intent_ref, refund)
        return refund
