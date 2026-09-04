"""Real-Postgres proof that provider admission is a database fact, not a
call-site fixture.

Before this test, "is this teacher admitted to receive an FGCN task" was
answered one of two ways depending on caller: `_DevProviderAdmissionQuery`
(`backend/apps/family_api/dev_wiring.py`) read an in-process
`FakeServiceRepository`, and every other caller supplied a hand-built
`ProviderAdmissionSnapshot` directly in test code
(`admission_test_doubles.py`, the durable-assignment Postgres test's own
`_AdmittedProviderAdmission`). Neither ever queried a table.

`SqlAlchemyProviderAdmissionQuery` (`backend.domains.service.fgcn.
infrastructure.sqlalchemy_provider_admission`) is the real adapter: it reads
the pre-existing, already-migrated `family_service_providers` row (the same
row `ServiceProvider.is_bookable` already gates bookings on) and its
`attributes` JSONB for the FGCN-specific capability/purpose facts. This test
writes a provider row through the same `SqlAlchemyServiceRepository` production
code already uses, closes that session, opens an independent one, and proves
`resolve()` reads the row back — not memory.

Gated: skipped entirely unless `AIFAMILY_TEST_DATABASE_URL` is set. Same
pattern as `test_family_need_durable_assignment_postgres.py` and
`tests/support/postgres.postgres_schema_engine`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.domains.service.domain.entities import ServiceProvider
from backend.domains.service.fgcn.contracts import GateServiceScope
from backend.domains.service.fgcn.infrastructure.sqlalchemy_provider_admission import (
    SqlAlchemyProviderAdmissionQuery,
)
from backend.domains.service.infrastructure.sqlalchemy_models import Base
from backend.domains.service.infrastructure.sqlalchemy_repository import (
    SqlAlchemyServiceRepository,
)
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

TENANT_ID = "tenant-fgcn-admission-postgres"
PROVIDER_REF = "TEACHER_LI"


def _scope() -> GateServiceScope:
    return GateServiceScope(
        tenant_id=TENANT_ID,
        family_id="family-fgcn-admission-postgres",
        subject_person_id="child-fgcn-admission-postgres",
        purpose="family_service_collaboration",
        consent_version="consent.v1",
        correlation_id="corr:fgcn-admission-postgres",
    )


def _admitted_teacher_row() -> ServiceProvider:
    # `ServiceProviderRow.effective_from`/`created_at`/`updated_at` are mapped
    # as naive `DateTime` (see `sqlalchemy_models.py`'s own docstring: types are
    # widened so the same model runs against SQLite too), so this repository's
    # write path needs a naive value even though the domain entity itself
    # requires a timezone-aware one elsewhere in the codebase.
    now = datetime.now(UTC).replace(tzinfo=None)
    return ServiceProvider(
        provider_id="provider-fgcn-admission-postgres-1",
        scope_type="TENANT",
        tenant_id=TENANT_ID,
        provider_ref=PROVIDER_REF,
        display_name="李老师",
        provider_kind="TEACHER",
        qualification_status="ACTIVE",
        admission_status="ADMITTED",
        source_ref="test.fgcn.provider_admission_postgres",
        effective_from=now,
        created_at=now,
        created_by="system:test",
        updated_at=now,
        updated_by="system:test",
        attributes={
            "fgcn_capability_keys": ["parent_communication_support"],
            "fgcn_allowed_purposes": ["family_service_collaboration"],
            "fgcn_capacity_available": 2,
        },
    )


@pytest.mark.asyncio
@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_provider_admission_is_read_from_postgres_not_memory() -> None:
    async with postgres_schema_engine(Base.metadata) as engine:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        # 1. Write the provider admission fact through the real repository and
        #    commit. This session is then closed and discarded.
        async with session_factory() as writer_session:
            repo = SqlAlchemyServiceRepository(writer_session)
            await repo.save_provider(_admitted_teacher_row())
            await repo.commit()

        # 2. Resolve through an entirely independent session/query object. If
        #    the admission fact only lived in the writer's session or in any
        #    Python-process memory, this would find nothing.
        async with session_factory() as reader_session:
            query = SqlAlchemyProviderAdmissionQuery(reader_session)
            snapshot = await query.resolve(
                provider_ref=PROVIDER_REF,
                assignee_kind="COACH",
                required_capability_keys=("parent_communication_support",),
                scope=_scope(),
            )

        assert snapshot is not None
        assert snapshot.provider_ref == PROVIDER_REF
        assert snapshot.admission_status == "ACTIVE"
        assert snapshot.capability_keys == ("parent_communication_support",)
        assert snapshot.allowed_purposes == ("family_service_collaboration",)
        assert snapshot.capacity_available == 2


@pytest.mark.asyncio
@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_unknown_provider_ref_is_a_refusal_not_an_allow() -> None:
    async with postgres_schema_engine(Base.metadata) as engine:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with session_factory() as reader_session:
            query = SqlAlchemyProviderAdmissionQuery(reader_session)
            snapshot = await query.resolve(
                provider_ref="NO_SUCH_PROVIDER",
                assignee_kind="COACH",
                required_capability_keys=(),
                scope=_scope(),
            )

        assert snapshot is None


@pytest.mark.asyncio
@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_suspended_provider_is_a_refusal() -> None:
    async with postgres_schema_engine(Base.metadata) as engine:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        now = datetime.now(UTC).replace(tzinfo=None)
        suspended = ServiceProvider(
            provider_id="provider-fgcn-admission-postgres-suspended",
            scope_type="TENANT",
            tenant_id=TENANT_ID,
            provider_ref="TEACHER_SUSPENDED",
            display_name="停用教师",
            provider_kind="TEACHER",
            qualification_status="ACTIVE",
            admission_status="SUSPENDED",
            source_ref="test.fgcn.provider_admission_postgres",
            effective_from=now,
            status="SUSPENDED",
            created_at=now,
            created_by="system:test",
            updated_at=now,
            updated_by="system:test",
            attributes={
                "fgcn_capability_keys": ["parent_communication_support"],
                "fgcn_allowed_purposes": ["family_service_collaboration"],
            },
        )

        async with session_factory() as writer_session:
            repo = SqlAlchemyServiceRepository(writer_session)
            await repo.save_provider(suspended)
            await repo.commit()

        async with session_factory() as reader_session:
            query = SqlAlchemyProviderAdmissionQuery(reader_session)
            snapshot = await query.resolve(
                provider_ref="TEACHER_SUSPENDED",
                assignee_kind="COACH",
                required_capability_keys=(),
                scope=_scope(),
            )

        assert snapshot is None


@pytest.mark.asyncio
@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_expired_qualification_is_a_refusal_even_when_status_still_says_active() -> None:
    """`qualification_status` is never automatically revisited when a real
    certificate lapses — `qualification_expires_at` is the only thing that
    actually fails closed on expiry (see this adapter's own docstring)."""

    async with postgres_schema_engine(Base.metadata) as engine:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        now = datetime.now(UTC).replace(tzinfo=None)
        expired = ServiceProvider(
            provider_id="provider-fgcn-admission-postgres-expired",
            scope_type="TENANT",
            tenant_id=TENANT_ID,
            provider_ref="TEACHER_EXPIRED",
            display_name="资质过期教师",
            provider_kind="TEACHER",
            qualification_status="ACTIVE",
            qualification_type="TEACHING_CERTIFICATE",
            qualification_expires_at=now - timedelta(days=1),
            admission_status="ADMITTED",
            source_ref="test.fgcn.provider_admission_postgres",
            effective_from=now,
            created_at=now,
            created_by="system:test",
            updated_at=now,
            updated_by="system:test",
            attributes={
                "fgcn_capability_keys": ["parent_communication_support"],
                "fgcn_allowed_purposes": ["family_service_collaboration"],
            },
        )

        async with session_factory() as writer_session:
            repo = SqlAlchemyServiceRepository(writer_session)
            await repo.save_provider(expired)
            await repo.commit()

        async with session_factory() as reader_session:
            query = SqlAlchemyProviderAdmissionQuery(reader_session)
            snapshot = await query.resolve(
                provider_ref="TEACHER_EXPIRED",
                assignee_kind="COACH",
                required_capability_keys=(),
                scope=_scope(),
            )

        assert snapshot is None


@pytest.mark.asyncio
@pytest.mark.skipif(postgres_test_url() is None, reason=SKIP_REASON)
async def test_future_expiry_still_admits() -> None:
    """A qualification with a future expiry date must not be rejected —
    proves the check is a real date comparison, not an accidental
    always-reject on any non-null `qualification_expires_at`."""

    async with postgres_schema_engine(Base.metadata) as engine:
        session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        now = datetime.now(UTC).replace(tzinfo=None)
        still_valid = ServiceProvider(
            provider_id="provider-fgcn-admission-postgres-valid-expiry",
            scope_type="TENANT",
            tenant_id=TENANT_ID,
            provider_ref="TEACHER_VALID_EXPIRY",
            display_name="资质有效教师",
            provider_kind="TEACHER",
            qualification_status="ACTIVE",
            qualification_type="TEACHING_CERTIFICATE",
            qualification_expires_at=now + timedelta(days=365),
            admission_status="ADMITTED",
            source_ref="test.fgcn.provider_admission_postgres",
            effective_from=now,
            created_at=now,
            created_by="system:test",
            updated_at=now,
            updated_by="system:test",
            attributes={
                "fgcn_capability_keys": ["parent_communication_support"],
                "fgcn_allowed_purposes": ["family_service_collaboration"],
                "fgcn_capacity_available": 1,
            },
        )

        async with session_factory() as writer_session:
            repo = SqlAlchemyServiceRepository(writer_session)
            await repo.save_provider(still_valid)
            await repo.commit()

        async with session_factory() as reader_session:
            query = SqlAlchemyProviderAdmissionQuery(reader_session)
            snapshot = await query.resolve(
                provider_ref="TEACHER_VALID_EXPIRY",
                assignee_kind="COACH",
                required_capability_keys=(),
                scope=_scope(),
            )

        assert snapshot is not None
        assert snapshot.provider_ref == "TEACHER_VALID_EXPIRY"
