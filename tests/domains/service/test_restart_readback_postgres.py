"""Explicit restart/readback evidence for the SERVICE booking chain.

This is intentionally separate from the parametrized acceptance tests: the
writer session is closed before a fresh session reads the facts back.  It
proves durable PostgreSQL state, not an in-memory identity map.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.domains.service.application import commands
from backend.domains.service.infrastructure.fake_repository import FakeConsentQuery
from backend.domains.service.infrastructure.sqlalchemy_models import Base
from backend.domains.service.infrastructure.sqlalchemy_repository import (
    SqlAlchemyServiceRepository,
)
from backend.platform.audit.recorder import AuditRecorder
from backend.platform.audit.store import AuditBase
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

from .helpers import CHILD, CONSENT_REF, granted, make_ctx, seed_supply

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def service_session_factory():
    if postgres_test_url() is None:
        pytest.skip(SKIP_REASON)
    async with postgres_schema_engine(Base.metadata) as engine:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
            await connection.run_sync(AuditBase.metadata.create_all)
        factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        yield factory


async def test_booking_state_survives_session_restart(service_session_factory) -> None:
    consent = FakeConsentQuery()
    consent.add(granted())

    async with service_session_factory() as session:
        repo = SqlAlchemyServiceRepository(session)
        recorder = AuditRecorder()
        _provider, offering, slot = await seed_supply(repo, recorder=recorder)
        booking = await commands.submit_booking_request(
            repo,
            make_ctx(idempotency_key="restart-booking"),
            recorder,
            consent,
            service_offering_id=offering.service_offering_id,
            availability_slot_id=slot.availability_slot_id,
            booking_ref="RESTART-BOOKING",
            source_page_id="UI-21",
            subject_person_id=CHILD,
            consent_ref=CONSENT_REF,
        )
        await session.commit()

    # A new session represents a restarted API worker.
    async with service_session_factory() as restarted_session:
        restarted_repo = SqlAlchemyServiceRepository(restarted_session)
        loaded_booking = await restarted_repo.load_booking(booking.booking_request_id)
        loaded_slot = await restarted_repo.load_slot(slot.availability_slot_id)

    assert loaded_booking.booking_ref == "RESTART-BOOKING"
    assert loaded_booking.status == "REQUESTED"
    assert loaded_booking.external_effect is False
    assert loaded_slot.reserved_count == 1
    assert loaded_slot.status == "RESERVED"
