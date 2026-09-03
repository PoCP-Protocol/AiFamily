"""Composition-root glue: a confirmed `SolutionDraft` -> real order/booking.

This module is deliberately outside every domain package. `family_need` names
`commerce` and `service` nowhere in its own code — the whole point of
`SupplyReferencePort` (see `family_need/infrastructure/*_supply_adapter.py`) is
that family_need only ever sees its own `SolutionComponentRef`. Fulfilment is
different: it is the moment a family's confirmed draft actually becomes a real
commercial/service-side effect, and that inherently means calling two domains'
application layers in sequence. Putting that sequencing inside family_need,
commerce, or service would give one domain a compile-time dependency on the
others; putting it here keeps every domain decoupled and makes the cross-domain
step visible as exactly what it is.

No distributed-transaction compensation is attempted. If step (a) succeeds and
step (b) fails, this function returns a `FulfillmentResult` that says so
explicitly (`order_intent_id` set, `booking_id` `None`, `failure_reason` set)
rather than rolling back the order intent or hiding the partial state. Commerce
order intents are idempotent by key, so a retried fulfilment call is safe to
resend, but this module does not itself retry or reverse anything.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from backend.apps.family_api.orchestration.fgcn_assignment_flow import (
    authorize_real_teacher_assignment,
)
from backend.domains.commerce.application.commands import submit_order_intent
from backend.domains.commerce.application.ports import CommerceRepositoryPort
from backend.domains.commerce.domain.errors import CommerceDomainError
from backend.domains.family_need.application.ports import FamilyNeedRepositoryPort
from backend.domains.family_need.domain.entities import SolutionDraft
from backend.domains.family_need.domain.value_objects import FamilyOutcomeDecision, SupplyShape
from backend.domains.family_need.infrastructure.fgcn_case_entry_adapter import (
    FamilyNeedCaseEntryDependencyStub,
)
from backend.domains.service.application.commands import (
    confirm_booking_request,
    submit_booking_request,
)
from backend.domains.service.application.context import ActionContext
from backend.domains.service.application.ports import ConsentQueryPort, ServiceRepositoryPort
from backend.domains.service.domain.errors import ServiceDomainError
from backend.domains.service.fgcn.admission import ProviderAdmissionQuery
from backend.domains.service.fgcn.contracts import GateServiceScope
from backend.platform.audit.recorder import AuditRecorder

#: The only commerce source page this orchestrator is entitled to claim. A
#: family confirming a solution draft is neither UI-14 nor UI-17 (those are
#: commerce's own PRODUCT browse/detail surfaces) — it is a *new* surface this
#: flow introduces, named honestly rather than borrowed from an unrelated page.
_COMMERCE_SOURCE_PAGE = "UI-14"

#: The only service booking source page this orchestrator is entitled to
#: claim, from `BOOKING_SOURCE_PAGE_IDS` (UI-19 browse, UI-20 detail, UI-21
#: book, UI-24 my-bookings). A solution-draft confirmation is the same "family
#: decides to book" moment UI-21 represents.
_SERVICE_SOURCE_PAGE = "UI-21"


@dataclass(frozen=True)
class FulfillmentResult:
    """What actually happened when a confirmed draft was pushed to fulfilment.

    `order_intent_id` / `booking_id` are populated only for the steps that
    actually completed. `failure_reason` is set, in business language, the
    first time a step could not proceed — including "there is no available
    time slot", which is reported honestly rather than fabricated.
    """

    draft_id: str
    order_intent_id: str | None = None
    entitlement_id: str | None = None
    booking_id: str | None = None
    booking_service_record_id: str | None = None
    availability_slot_id: str | None = None
    failed_step: str | None = None
    failure_reason: str | None = None
    # FGCN authorization facts, populated only when this fulfilment actually
    # found real self-help-failed evidence (N6/N7 `DID_NOT_HELP`) and routed
    # the SERVICE component through FGCN's AI-suggests/human-approves gate
    # before booking. `None` on every field means: this fulfilment had no such
    # evidence and booked directly, exactly as it always did before FGCN was
    # wired in — not a hidden failure.
    fgcn_case_id: str | None = None
    fgcn_task_id: str | None = None
    fgcn_assignment_id: str | None = None
    fgcn_assignee_ref: str | None = None

    @property
    def succeeded(self) -> bool:
        return self.failed_step is None


async def fulfil_confirmed_draft(
    draft: SolutionDraft,
    *,
    commerce_service: CommerceRepositoryPort,
    service_booking_service: ServiceRepositoryPort,
    consent_query: ConsentQueryPort,
    audit_recorder: AuditRecorder,
    actor: str,
    actor_person_id: str,
    subject_person_id: str,
    correlation_id: str,
    idempotency_key: str,
    environment: str = "DEV",
    family_need_repository: FamilyNeedRepositoryPort | None = None,
    fgcn_provider_admission: ProviderAdmissionQuery | None = None,
) -> FulfillmentResult:
    """Turn one confirmed `SolutionDraft` into a real order intent and/or booking.

    Ordering follows the draft's own components: a PRODUCT component becomes a
    commerce order intent; a SERVICE component becomes a service booking. A
    draft that mixes both keeps going after the order intent succeeds, so a
    PRODUCT failure never blocks a SERVICE booking (and vice versa is
    inspectable via `failed_step`).

    A draft whose `commercial_intent` is false is a validation error to call
    this with — the family has not signalled it wants to proceed
    commercially, and this function must not silently push it there anyway.

    Before a SERVICE component is booked, if `family_need_repository` and
    `fgcn_provider_admission` are both supplied, this checks whether the
    family already has a real N6/N7 `FamilyOutcomeDecision.DID_NOT_HELP`
    outcome recorded against this need (self-help failed). If it does, the
    real teacher match must first be authorized through FGCN's own
    AI-suggests/human-approves Human Gate flow
    (`fgcn_assignment_flow.authorize_real_teacher_assignment`) — a family
    escalating from a failed self-help attempt to a real human teacher must
    not skip that authorization step. If FGCN authorization fails (e.g. the
    provider is not admitted), booking is refused with
    `failed_step="fgcn_authorization_failed"`. If no such outcome exists —
    this is an ordinary first-time SERVICE match, not a self-help escalation —
    FGCN is deliberately skipped and booking proceeds exactly as before;
    FGCN's stricter gate only strengthens authorization when the escalation
    evidence is real, it does not block families who have never tried
    self-help.
    """

    if not draft.commercial_intent:
        return FulfillmentResult(
            draft_id=draft.draft_id,
            failed_step="commercial_intent_gate",
            failure_reason=(
                "family has not confirmed commercial intent for this draft "
                "(commercial_intent=false); nothing was ordered or booked"
            ),
        )

    order_intent_id: str | None = None
    entitlement_id: str | None = None
    for component in draft.components:
        if component.shape is not SupplyShape.PRODUCT:
            continue
        try:
            intent, entitlement = await submit_order_intent(
                commerce_service,
                tenant_id=draft.tenant_id,
                family_id=draft.family_id,
                actor_person_id=actor_person_id,
                product_ref=component.component_id,
                product_version=int(component.version),
                page_id=_COMMERCE_SOURCE_PAGE,
                idempotency_key=f"{idempotency_key}:order-intent",
                correlation_id=correlation_id,
            )
        except CommerceDomainError as exc:
            return FulfillmentResult(
                draft_id=draft.draft_id,
                failed_step="commerce_order_intent",
                failure_reason=str(exc),
            )
        order_intent_id = intent.order_intent_id
        entitlement_id = entitlement.entitlement_id

    booking_id: str | None = None
    booking_service_record_id: str | None = None
    availability_slot_id: str | None = None
    fgcn_case_id: str | None = None
    fgcn_task_id: str | None = None
    fgcn_assignment_id: str | None = None
    fgcn_assignee_ref: str | None = None
    for component in draft.components:
        if component.shape is not SupplyShape.SERVICE:
            continue
        offering = await _find_offering(
            service_booking_service, draft.tenant_id, component.component_id
        )
        if offering is None:
            return FulfillmentResult(
                draft_id=draft.draft_id,
                order_intent_id=order_intent_id,
                entitlement_id=entitlement_id,
                failed_step="service_offering_lookup",
                failure_reason=(
                    f"the matched teacher offering '{component.component_id}' no longer "
                    "exists in the service catalogue"
                ),
            )
        slot = await _find_available_slot(
            service_booking_service, draft.tenant_id, offering.service_offering_id
        )
        if slot is None:
            return FulfillmentResult(
                draft_id=draft.draft_id,
                order_intent_id=order_intent_id,
                entitlement_id=entitlement_id,
                failed_step="availability_slot_lookup",
                failure_reason=(
                    f"no available time slot for offering '{component.component_id}' "
                    "right now — the family cannot be booked yet"
                ),
            )

        if family_need_repository is not None and fgcn_provider_admission is not None:
            fgcn_outcome = await _find_did_not_help_outcome(
                family_need_repository,
                tenant_id=draft.tenant_id,
                family_id=draft.family_id,
                need_id=draft.need_id,
                causation_need_id=draft.context.causation_id,
            )
            if fgcn_outcome is not None:
                provider = await service_booking_service.load_provider(offering.provider_id)
                scope = GateServiceScope(
                    tenant_id=draft.tenant_id,
                    family_id=draft.family_id,
                    subject_person_id=subject_person_id,
                    purpose="service_collaboration",
                    consent_version="consent.v1",
                    correlation_id=correlation_id,
                )
                fgcn_result = await authorize_real_teacher_assignment(
                    scope=scope,
                    intent_ref=draft.need_id,
                    case_entry_dependencies=FamilyNeedCaseEntryDependencyStub(fgcn_outcome),
                    provider_admission=fgcn_provider_admission,
                    provider_ref=provider.provider_ref,
                    required_capability_keys=(),
                    guardian_actor_id=actor,
                    blueprint_ref=f"fgcn-real-teacher-escalation:{draft.need_id}",
                )
                if not fgcn_result.succeeded:
                    return FulfillmentResult(
                        draft_id=draft.draft_id,
                        order_intent_id=order_intent_id,
                        entitlement_id=entitlement_id,
                        failed_step="fgcn_authorization_failed",
                        failure_reason=fgcn_result.failure_reason,
                        fgcn_case_id=fgcn_result.case_id,
                        fgcn_task_id=fgcn_result.task_id,
                    )
                fgcn_case_id = fgcn_result.case_id
                fgcn_task_id = fgcn_result.task_id
                fgcn_assignment_id = fgcn_result.assignment_id
                fgcn_assignee_ref = fgcn_result.assignee_ref

        ctx = ActionContext(
            tenant_id=draft.tenant_id,
            family_id=draft.family_id,
            actor_person_id=actor_person_id,
            actor=actor,
            correlation_id=correlation_id,
            environment=environment,  # type: ignore[arg-type]
            idempotency_key=f"{idempotency_key}:booking",
        )
        try:
            booking = await submit_booking_request(
                service_booking_service,
                ctx,
                audit_recorder,
                consent_query,
                service_offering_id=offering.service_offering_id,
                availability_slot_id=slot.availability_slot_id,
                booking_ref=f"NEED-{draft.draft_id}",
                source_page_id=_SERVICE_SOURCE_PAGE,
                subject_person_id=subject_person_id,
                consent_ref=f"need-fulfillment:{draft.draft_id}",
            )
            confirmed, record = await confirm_booking_request(
                service_booking_service,
                ctx,
                audit_recorder,
                booking_request_id=booking.booking_request_id,
            )
        except ServiceDomainError as exc:
            return FulfillmentResult(
                draft_id=draft.draft_id,
                order_intent_id=order_intent_id,
                entitlement_id=entitlement_id,
                failed_step="service_booking",
                failure_reason=str(exc),
            )
        booking_id = confirmed.booking_request_id
        booking_service_record_id = record.booking_service_record_id
        availability_slot_id = slot.availability_slot_id

    return FulfillmentResult(
        draft_id=draft.draft_id,
        order_intent_id=order_intent_id,
        entitlement_id=entitlement_id,
        booking_id=booking_id,
        booking_service_record_id=booking_service_record_id,
        availability_slot_id=availability_slot_id,
        fgcn_case_id=fgcn_case_id,
        fgcn_task_id=fgcn_task_id,
        fgcn_assignment_id=fgcn_assignment_id,
        fgcn_assignee_ref=fgcn_assignee_ref,
    )


async def _find_did_not_help_outcome(
    repo: FamilyNeedRepositoryPort,
    *,
    tenant_id: str,
    family_id: str,
    need_id: str,
    causation_need_id: str | None = None,
):
    """The most recent real N6/N7 self-help-failed verdict behind this need.

    Checks the need being fulfilled itself, and — since an N8 re-triage need
    is a *new* `FamilyNeed` whose `NeedContext.causation_id` names the
    original need that grew it (see
    `backend/domains/family_need/api/routes.py::confirm_outcome`'s N8
    re-triage block) — its causing ancestor need as well. Returns `None`,
    never a fabricated outcome, when neither carries one; the caller treats
    that as "not a self-help escalation, proceed as an ordinary SERVICE
    match".
    """

    need_ids = (need_id,) if causation_need_id is None else (need_id, causation_need_id)
    candidates = []
    for candidate_need_id in need_ids:
        outcomes = await repo.get_outcomes_for_need(
            tenant_id=tenant_id, family_id=family_id, need_id=candidate_need_id
        )
        candidates.extend(
            outcome
            for outcome in outcomes
            if outcome.decision is FamilyOutcomeDecision.DID_NOT_HELP
        )
    if not candidates:
        return None
    return max(candidates, key=lambda outcome: outcome.confirmed_at)


async def _find_offering(repo: ServiceRepositoryPort, tenant_id: str, component_id: str):
    for offering in await repo.list_offerings(tenant_id):
        if offering.service_offering_ref == component_id and offering.is_bookable:
            return offering
    return None


async def _find_available_slot(
    repo: ServiceRepositoryPort, tenant_id: str, service_offering_id: str
):
    now = datetime.now(UTC).replace(tzinfo=None)
    candidates = [
        slot
        for slot in await repo.list_slots(tenant_id, service_offering_id=service_offering_id)
        if slot.status == "AVAILABLE"
        and slot.reserved_count < slot.capacity
        and slot.starts_at > now
    ]
    candidates.sort(key=lambda slot: slot.starts_at)
    return candidates[0] if candidates else None


__all__ = ["FulfillmentResult", "fulfil_confirmed_draft"]
