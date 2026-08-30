"""Real SQLAlchemy repository implementing `ServiceRepositoryPort`.

`save_*` / `append_*` stage only; the caller commits once via `commit()` — see
the unit-of-work note on the port. That is what makes "slot capacity taken +
booking row written" atomic rather than two independent commits that can
half-fail, and it is the only reason the double-booking refusal is meaningful.

Tests run this same class against in-memory SQLite (always) and against real
Postgres when `AIFAMILY_TEST_DATABASE_URL` is set — see
`tests/domains/service/conftest.py`.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..domain.entities import (
    AvailabilitySlot,
    BookingRequest,
    FamilyFeedback,
    PrivateCheckinDraft,
    QualityDecision,
    ServiceAction,
    ServiceEvent,
    ServiceOffering,
    ServiceProvider,
    ServiceRecord,
)
from ..domain.errors import ServiceNotFoundError
from . import sqlalchemy_models as m


def _row_to_dict(row: object) -> dict:
    return {c.name: getattr(row, c.name) for c in row.__table__.columns}  # type: ignore[attr-defined]


class SqlAlchemyServiceRepository:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def commit(self) -> None:
        await self._session.commit()

    async def _stage(self, row: object) -> None:
        # `merge` rather than `add`: the domain entities are immutable and every
        # transition returns a *new* value object with the same primary key, so
        # a save is always an upsert from the session's point of view.
        await self._session.merge(row)

    async def _one(self, model, entity_id: str, code: str):
        row = await self._session.get(model, entity_id)
        if row is None:
            raise ServiceNotFoundError(code)
        return row

    async def _scoped(self, model, tenant_id: str, family_id: str):
        result = await self._session.execute(
            select(model).where(model.tenant_id == tenant_id, model.family_id == family_id)
        )
        return result.scalars().all()

    async def _by_idempotency_key(self, model, tenant_id: str, family_id: str, key: str):
        result = await self._session.execute(
            select(model).where(
                model.tenant_id == tenant_id,
                model.family_id == family_id,
                model.idempotency_key == key,
            )
        )
        return result.scalars().first()

    # -- supply masters --
    async def save_provider(self, entity: ServiceProvider) -> None:
        await self._stage(m.ServiceProviderRow(**entity.model_dump()))

    async def load_provider(self, provider_id: str) -> ServiceProvider:
        row = await self._one(m.ServiceProviderRow, provider_id, "service_provider_not_found")
        return ServiceProvider(**_row_to_dict(row))

    async def save_offering(self, entity: ServiceOffering) -> None:
        await self._stage(m.ServiceOfferingRow(**entity.model_dump()))

    async def load_offering(self, service_offering_id: str) -> ServiceOffering:
        row = await self._one(
            m.ServiceOfferingRow, service_offering_id, "service_offering_not_found"
        )
        return ServiceOffering(**_row_to_dict(row))

    async def list_offerings(self, tenant_id: str) -> list[ServiceOffering]:
        result = await self._session.execute(
            select(m.ServiceOfferingRow).where(m.ServiceOfferingRow.tenant_id == tenant_id)
        )
        return [ServiceOffering(**_row_to_dict(r)) for r in result.scalars().all()]

    # -- availability --
    async def save_slot(self, entity: AvailabilitySlot) -> None:
        await self._stage(m.AvailabilitySlotRow(**entity.model_dump()))

    async def load_slot(self, availability_slot_id: str) -> AvailabilitySlot:
        row = await self._one(
            m.AvailabilitySlotRow, availability_slot_id, "availability_slot_not_found"
        )
        return AvailabilitySlot(**_row_to_dict(row))

    async def load_slot_for_update(self, availability_slot_id: str) -> AvailabilitySlot:
        result = await self._session.execute(
            select(m.AvailabilitySlotRow)
            .where(m.AvailabilitySlotRow.availability_slot_id == availability_slot_id)
            .with_for_update()
        )
        row = result.scalars().first()
        if row is None:
            raise ServiceNotFoundError("availability_slot_not_found")
        return AvailabilitySlot(**_row_to_dict(row))

    async def list_slots(
        self, tenant_id: str, *, service_offering_id: str | None = None
    ) -> list[AvailabilitySlot]:
        stmt = select(m.AvailabilitySlotRow).where(m.AvailabilitySlotRow.tenant_id == tenant_id)
        if service_offering_id is not None:
            stmt = stmt.where(m.AvailabilitySlotRow.service_offering_id == service_offering_id)
        result = await self._session.execute(stmt)
        return [AvailabilitySlot(**_row_to_dict(r)) for r in result.scalars().all()]

    # -- booking requests --
    async def save_booking(self, entity: BookingRequest) -> None:
        await self._stage(m.BookingRequestRow(**entity.model_dump()))

    async def load_booking(self, booking_request_id: str) -> BookingRequest:
        row = await self._one(m.BookingRequestRow, booking_request_id, "booking_request_not_found")
        return BookingRequest(**_row_to_dict(row))

    async def list_bookings(self, tenant_id: str, family_id: str) -> list[BookingRequest]:
        rows = await self._scoped(m.BookingRequestRow, tenant_id, family_id)
        return [BookingRequest(**_row_to_dict(r)) for r in rows]

    async def find_booking_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> BookingRequest | None:
        row = await self._by_idempotency_key(
            m.BookingRequestRow, tenant_id, family_id, idempotency_key
        )
        return None if row is None else BookingRequest(**_row_to_dict(row))

    # -- service records --
    async def save_service_record(self, entity: ServiceRecord) -> None:
        await self._stage(m.ServiceRecordRow(**entity.model_dump()))

    async def load_service_record(self, booking_service_record_id: str) -> ServiceRecord:
        row = await self._one(
            m.ServiceRecordRow, booking_service_record_id, "service_record_not_found"
        )
        return ServiceRecord(**_row_to_dict(row))

    async def find_service_record_for_booking(
        self, tenant_id: str, family_id: str, booking_request_id: str
    ) -> ServiceRecord | None:
        result = await self._session.execute(
            select(m.ServiceRecordRow).where(
                m.ServiceRecordRow.tenant_id == tenant_id,
                m.ServiceRecordRow.family_id == family_id,
                m.ServiceRecordRow.source_booking_request_id == booking_request_id,
            )
        )
        row = result.scalars().first()
        return None if row is None else ServiceRecord(**_row_to_dict(row))

    async def list_service_records(self, tenant_id: str, family_id: str) -> list[ServiceRecord]:
        rows = await self._scoped(m.ServiceRecordRow, tenant_id, family_id)
        return [ServiceRecord(**_row_to_dict(r)) for r in rows]

    # -- feedback / quality / named actions --
    async def save_family_feedback(self, entity: FamilyFeedback) -> None:
        await self._stage(m.FamilyFeedbackRow(**entity.model_dump()))

    async def load_family_feedback(self, family_feedback_id: str) -> FamilyFeedback:
        row = await self._one(m.FamilyFeedbackRow, family_feedback_id, "family_feedback_not_found")
        return FamilyFeedback(**_row_to_dict(row))

    async def find_feedback_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> FamilyFeedback | None:
        row = await self._by_idempotency_key(
            m.FamilyFeedbackRow, tenant_id, family_id, idempotency_key
        )
        return None if row is None else FamilyFeedback(**_row_to_dict(row))

    async def save_quality_decision(self, entity: QualityDecision) -> None:
        await self._stage(m.QualityDecisionRow(**entity.model_dump()))

    async def load_quality_decision(self, quality_decision_id: str) -> QualityDecision:
        row = await self._one(
            m.QualityDecisionRow, quality_decision_id, "quality_decision_not_found"
        )
        return QualityDecision(**_row_to_dict(row))

    async def find_quality_decision_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> QualityDecision | None:
        row = await self._by_idempotency_key(
            m.QualityDecisionRow, tenant_id, family_id, idempotency_key
        )
        return None if row is None else QualityDecision(**_row_to_dict(row))

    async def save_service_action(self, entity: ServiceAction) -> None:
        await self._stage(m.ServiceActionRow(**entity.model_dump()))

    async def find_service_action_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> ServiceAction | None:
        row = await self._by_idempotency_key(
            m.ServiceActionRow, tenant_id, family_id, idempotency_key
        )
        return None if row is None else ServiceAction(**_row_to_dict(row))

    async def list_service_actions(self, tenant_id: str, family_id: str) -> list[ServiceAction]:
        rows = await self._scoped(m.ServiceActionRow, tenant_id, family_id)
        return [ServiceAction(**_row_to_dict(r)) for r in rows]

    # -- transactional service outbox --
    async def append_service_event(self, entity: ServiceEvent) -> None:
        existing = await self.find_service_event_by_idempotency_key(
            entity.tenant_id, entity.idempotency_key
        )
        if existing is not None:
            if existing.model_dump() != entity.model_dump():
                from ..domain.errors import ServiceConflictError

                raise ServiceConflictError("service_event_idempotency_replay_mismatch")
            return
        await self._stage(m.ServiceEventRow(**entity.model_dump()))

    async def find_service_event_by_idempotency_key(
        self, tenant_id: str, idempotency_key: str
    ) -> ServiceEvent | None:
        result = await self._session.execute(
            select(m.ServiceEventRow).where(
                m.ServiceEventRow.tenant_id == tenant_id,
                m.ServiceEventRow.idempotency_key == idempotency_key,
            )
        )
        row = result.scalars().first()
        return None if row is None else ServiceEvent(**_row_to_dict(row))

    async def list_pending_service_events(self, tenant_id: str) -> list[ServiceEvent]:
        result = await self._session.execute(
            select(m.ServiceEventRow).where(
                m.ServiceEventRow.tenant_id == tenant_id,
                m.ServiceEventRow.status == "PENDING",
            )
        )
        return [ServiceEvent(**_row_to_dict(r)) for r in result.scalars().all()]

    # -- private check-in drafts (append-only) --
    async def append_checkin_draft(self, entity: PrivateCheckinDraft) -> None:
        await self._stage(m.PrivateCheckinDraftRow(**entity.model_dump()))

    async def find_checkin_draft_by_idempotency_key(
        self, tenant_id: str, family_id: str, idempotency_key: str
    ) -> PrivateCheckinDraft | None:
        row = await self._by_idempotency_key(
            m.PrivateCheckinDraftRow, tenant_id, family_id, idempotency_key
        )
        return None if row is None else PrivateCheckinDraft(**_row_to_dict(row))

    async def list_checkin_drafts(
        self, tenant_id: str, family_id: str, *, onboarding_id: str | None = None
    ) -> list[PrivateCheckinDraft]:
        stmt = select(m.PrivateCheckinDraftRow).where(
            m.PrivateCheckinDraftRow.tenant_id == tenant_id,
            m.PrivateCheckinDraftRow.family_id == family_id,
        )
        if onboarding_id is not None:
            stmt = stmt.where(m.PrivateCheckinDraftRow.onboarding_id == onboarding_id)
        result = await self._session.execute(stmt)
        return [PrivateCheckinDraft(**_row_to_dict(r)) for r in result.scalars().all()]
