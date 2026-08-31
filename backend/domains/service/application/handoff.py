"""Thin S4 handoff into the canonical Service booking chain.

This module consumes a confirmation receipt; it does not own FamilyNeed,
GrowthIntent, Journey, or ServiceCase.  The receipt is an immutable input from
the family-growth owner.  Once scope and the guardian's explicit decision are
validated, all mutations are delegated to ``submit_booking_request`` so the
existing consent, capacity, idempotency, audit, and persistence rules remain
the single source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from backend.platform.audit.recorder import AuditRecorder

from ..domain.entities import BookingRequest
from ..domain.errors import ServiceForbiddenError, ServiceValidationError
from . import commands
from .context import ActionContext
from .ports import ConsentQueryPort, ServiceRepositoryPort


@dataclass(frozen=True)
class HumanHelpHandoffReceipt:
    """Minimal external receipt accepted by Service, never a new aggregate."""

    receipt_ref: str
    tenant_id: str
    family_id: str
    decision: Literal["HUMAN_HELP_CONFIRMED", "SELF_HELP_CONTINUES"]


async def submit_confirmed_human_help(
    repo: ServiceRepositoryPort,
    ctx: ActionContext,
    recorder: AuditRecorder,
    consent_query: ConsentQueryPort,
    *,
    receipt: HumanHelpHandoffReceipt,
    service_offering_id: str,
    availability_slot_id: str,
    subject_person_id: str,
    consent_ref: str,
) -> BookingRequest:
    """Create a booking request only after explicit, same-scope confirmation.

    AI recommendations and an unconfirmed family need cannot call through this
    boundary.  The canonical booking command remains responsible for consent,
    provider admission, slot capacity, idempotency, audit, and commit.
    """

    if not receipt.receipt_ref.strip():
        raise ServiceValidationError("human_help_receipt_ref_required")
    if receipt.tenant_id != ctx.tenant_id or receipt.family_id != ctx.family_id:
        raise ServiceForbiddenError("confirmed_need_scope_mismatch")
    if receipt.decision != "HUMAN_HELP_CONFIRMED":
        raise ServiceForbiddenError("human_help_not_confirmed")

    return await commands.submit_booking_request(
        repo,
        ctx,
        recorder,
        consent_query,
        service_offering_id=service_offering_id,
        availability_slot_id=availability_slot_id,
        booking_ref=receipt.receipt_ref,
        source_page_id="UI-21",
        subject_person_id=subject_person_id,
        consent_ref=consent_ref,
    )
