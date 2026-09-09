"""S4 HTTP contract over PostgreSQL with a reconnect readback.

This is the smallest runnable family behaviour in the Service value stream:
an authorised guardian sees admitted supply, requests a slot, a human confirms
it, and the guardian cancels before delivery.  The same test proves the refusal
paths and reconnects through a fresh SQLAlchemy connection before asserting the
persisted cancellation and released capacity.
"""

from __future__ import annotations

from datetime import timedelta

import httpx
import pytest
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.domains.service.api import dependencies as deps
from backend.domains.service.api.routes import router as service_router
from backend.domains.service.application.context import ActionContext
from backend.domains.service.domain.entities import utcnow
from backend.domains.service.infrastructure.fake_repository import FakeConsentQuery
from backend.domains.service.infrastructure.sqlalchemy_models import Base
from backend.domains.service.infrastructure.sqlalchemy_repository import (
    SqlAlchemyServiceRepository,
)
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.identity.context import ActorContext, ActorType, TenantStatus
from backend.platform.identity.directory import InMemoryTenantDirectory
from tests.domains.service.helpers import CHILD, CONSENT_REF, FAMILY, GUARDIAN, TENANT, granted
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

pytestmark = pytest.mark.asyncio


class _HttpState:
    def __init__(self, repo: SqlAlchemyServiceRepository) -> None:
        self.repo = repo
        self.consent = FakeConsentQuery()
        self.recorder = AuditRecorder()
        self.idempotency_key: str | None = None

    def action_context(self) -> ActionContext:
        return ActionContext(
            tenant_id=TENANT,
            family_id=FAMILY,
            actor_person_id=GUARDIAN,
            actor="guardian:001",
            correlation_id="corr-s4-http-pg",
            environment="TEST",
            idempotency_key=self.idempotency_key,
        )

    def actor_context(self) -> ActorContext:
        return ActorContext(
            actor_id="guardian:001",
            actor_type=ActorType.HUMAN,
            tenant_id=TENANT,
            correlation_id="corr-s4-http-pg",
        )

    def headers(self, key: str) -> dict[str, str]:
        self.idempotency_key = key
        return {"idempotency-key": key}


def _build_app(state: _HttpState) -> FastAPI:
    app = FastAPI()
    app.include_router(service_router)

    async def repository() -> SqlAlchemyServiceRepository:
        return state.repo

    async def consent_query() -> FakeConsentQuery:
        return state.consent

    async def action_context() -> ActionContext:
        return state.action_context()

    async def actor_context() -> ActorContext:
        return state.actor_context()

    tenant_directory = InMemoryTenantDirectory({TENANT: TenantStatus.ACTIVE})
    app.dependency_overrides[deps.get_repository] = repository
    app.dependency_overrides[deps.get_consent_query] = consent_query
    app.dependency_overrides[deps.get_action_context] = action_context
    app.dependency_overrides[deps.get_actor_context] = actor_context
    app.dependency_overrides[deps.get_tenant_directory] = lambda: tenant_directory
    app.dependency_overrides[deps.get_audit_recorder] = lambda: state.recorder
    return app


async def test_guardian_books_then_cancels_over_http_and_postgres_reconnects() -> None:
    if postgres_test_url() is None:
        pytest.skip(SKIP_REASON)

    async with postgres_schema_engine(Base.metadata) as engine:
        sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        async with sessions() as session:
            state = _HttpState(SqlAlchemyServiceRepository(session))
            app = _build_app(state)
            transport = httpx.ASGITransport(app=app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://service.test",
            ) as client:
                provider = await client.post(
                    f"/families/{FAMILY}/service/providers",
                    headers=state.headers("provider-s4"),
                    json={
                        "provider_ref": "S01_FAMILY_ACTION_COACH",
                        "display_name": "家庭行动教练",
                        "provider_kind": "TEACHER",
                        "qualification_status": "ACTIVE",
                        "admission_status": "ADMITTED",
                        "source_ref": "S01_REVIEW_HELP_REQUEST",
                    },
                )
                assert provider.status_code == 200, provider.text

                offering = await client.post(
                    f"/families/{FAMILY}/service/offerings",
                    headers=state.headers("offering-s4"),
                    json={
                        "provider_id": provider.json()["provider_id"],
                        "service_offering_ref": "S01_EVENING_START_SUPPORT",
                        "title": "晚间学习平稳启动支持",
                        "admission_status": "ADMITTED",
                        "source_ref": "S01_REVIEW_HELP_REQUEST",
                    },
                )
                assert offering.status_code == 200, offering.text

                starts_at = utcnow() + timedelta(days=3)
                slot = await client.post(
                    f"/families/{FAMILY}/service/availability-slots",
                    headers=state.headers("slot-s4"),
                    json={
                        "service_offering_id": offering.json()["service_offering_id"],
                        "availability_slot_ref": "S01_EVENING_SLOT_1",
                        "starts_at": starts_at.isoformat(),
                        "ends_at": (starts_at + timedelta(hours=1)).isoformat(),
                        "channel": "VIDEO",
                        "capacity": 1,
                    },
                )
                assert slot.status_code == 200, slot.text

                booking_body = {
                    "service_offering_id": offering.json()["service_offering_id"],
                    "availability_slot_id": slot.json()["availability_slot_id"],
                    "booking_ref": "S01_HELP_BOOKING_1",
                    "source_page_id": "UI-21",
                    "subject_person_id": CHILD,
                    "consent_ref": CONSENT_REF,
                }
                no_consent = await client.post(
                    f"/families/{FAMILY}/orchestration/test-loop/services/booking-requests",
                    headers=state.headers("booking-without-consent"),
                    json=booking_body,
                )
                assert no_consent.status_code == 403

                cross_family = await client.get(
                    "/families/family-foreign/orchestration/test-loop/services/offerings"
                )
                assert cross_family.status_code == 403

                state.consent.add(granted())
                booking = await client.post(
                    f"/families/{FAMILY}/orchestration/test-loop/services/booking-requests",
                    headers=state.headers("booking-s4"),
                    json=booking_body,
                )
                assert booking.status_code == 200, booking.text
                booking_id = booking.json()["booking_request_id"]

                confirmation = await client.post(
                    f"/families/{FAMILY}/service/booking-requests/{booking_id}/confirm",
                    headers=state.headers("confirm-s4"),
                )
                assert confirmation.status_code == 200, confirmation.text
                record_id = confirmation.json()["service_record"]["booking_service_record_id"]

                cancellation = await client.post(
                    f"/families/{FAMILY}/service/booking-requests/{booking_id}/cancel",
                    headers=state.headers("cancel-s4"),
                )
                replay = await client.post(
                    f"/families/{FAMILY}/service/booking-requests/{booking_id}/cancel",
                    headers=state.headers("cancel-s4"),
                )
                assert cancellation.status_code == replay.status_code == 200
                assert cancellation.json() == replay.json()

        # Dispose the connection pool to model an application process restart;
        # the next repository must reconnect and reconstruct state from PG.
        await engine.dispose()
        restarted_sessions = async_sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        async with restarted_sessions() as restarted_session:
            restarted_repo = SqlAlchemyServiceRepository(restarted_session)
            persisted_booking = await restarted_repo.load_booking(booking_id)
            persisted_record = await restarted_repo.load_service_record(record_id)
            persisted_slot = await restarted_repo.load_slot(slot.json()["availability_slot_id"])
            events = await restarted_repo.list_pending_service_events(TENANT)

            assert persisted_booking is not None and persisted_booking.status == "CANCELLED"
            assert persisted_record is not None and persisted_record.status == "CANCELLED"
            assert persisted_slot is not None
            assert (persisted_slot.reserved_count, persisted_slot.status) == (0, "AVAILABLE")
            assert sum(event.event_type == "service.booking_cancelled.v1" for event in events) == 1
            assert not any("cash" in key for event in events for key in event.payload)
            assert not any("contribution" in event.event_type for event in events)
