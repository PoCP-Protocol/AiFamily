"""Opt-in PostgreSQL concurrency proof for ProductPackage evidence admission.

This test intentionally uses SQLAlchemy metadata rather than claiming Alembic
deployment coverage. The shared migration chain is owned by another active
workstream; these tests prove PostgreSQL locking and unique-key behaviour only.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta

import pytest
import pytest_asyncio
from sqlalchemy import func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.human_gate.persistence import HumanGateBase, HumanTaskRow
from backend.platform.audit import AuditBase, AuditEventRow
from tests.support.postgres import SKIP_REASON, postgres_schema_engine, postgres_test_url

from ..application.product_package_submission import (
    ProductPackageSubmissionConflictError,
    submit_product_package_draft,
)
from ..infrastructure.product_package_evidence_reader import (
    SqlAlchemyProductPackageEvidenceReader,
)
from ..infrastructure.product_package_submission_repository import (
    ProductPackageDraftRow,
    SqlAlchemyProductPackageSubmissionRepository,
)
from ..infrastructure.sqlalchemy_models import Base as ProductBase
from ..infrastructure.sqlalchemy_models import EvidenceRow
from ..infrastructure.zone_sqlalchemy_models import Base as ZoneBase
from .test_product_package_submission import NOW, _context, _seed, _source

pytestmark = pytest.mark.skipif(not postgres_test_url(), reason=SKIP_REASON)


class _SynchronizedRaceRepository(SqlAlchemyProductPackageSubmissionRepository):
    def __init__(self, session: AsyncSession, *, barrier: asyncio.Barrier) -> None:
        super().__init__(session, clock=lambda: NOW)
        self._barrier = barrier
        self.misses = 0
        self.recovered_after_two_misses = False

    async def find_exact_replay(self, **kwargs):
        result = await super().find_exact_replay(**kwargs)
        if result is None:
            self.misses += 1
            # One miss is the application preflight; the second is the
            # repository's last check before revalidation and INSERT.
            if self.misses == 2:
                await self._barrier.wait()
        elif self.misses >= 2:
            # Only the IntegrityError recovery path can observe a row after
            # this repository crossed the two-miss barrier.
            self.recovered_after_two_misses = True
        return result


@pytest_asyncio.fixture
async def pg_factory() -> async_sessionmaker[AsyncSession]:
    async with postgres_schema_engine(ProductBase.metadata) as engine:
        async with engine.begin() as connection:
            await connection.run_sync(ZoneBase.metadata.create_all)
            await connection.run_sync(HumanGateBase.metadata.create_all)
            await connection.run_sync(AuditBase.metadata.create_all)
        yield async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


@pytest.mark.asyncio
async def test_same_intent_race_converges_on_one_immutable_draft(
    pg_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_factory() as session:
        await _seed(session)

    barrier = asyncio.Barrier(2)

    async def submit(offset_microseconds: int):
        evaluated_at = NOW + timedelta(microseconds=offset_microseconds)
        admissions = tuple(
            item.model_copy(update={"admitted_at": evaluated_at})
            for item in _source().evidence_admissions
        )
        async with pg_factory() as session:
            repo = _SynchronizedRaceRepository(session, barrier=barrier)
            result = await submit_product_package_draft(
                repo,
                _context(),
                _source(
                    evidence_admissions=admissions,
                    expires_at=NOW
                    + timedelta(days=7, microseconds=offset_microseconds),
                ),
                idempotency_key="pg-same-intent-race",
                now=evaluated_at,
            )
            return result, repo

    (first, first_repo), (second, second_repo) = await asyncio.wait_for(
        asyncio.gather(submit(1), submit(2)),
        timeout=10,
    )

    assert first.draft == second.draft
    assert {first.replayed, second.replayed} == {False, True}
    assert first_repo.misses == second_repo.misses == 2
    assert {
        first_repo.recovered_after_two_misses,
        second_repo.recovered_after_two_misses,
    } == {False, True}
    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(ProductPackageDraftRow)) == 1
        assert await session.scalar(select(func.count()).select_from(HumanTaskRow)) == 1
        assert await session.scalar(select(func.count()).select_from(AuditEventRow)) == 2


@pytest.mark.asyncio
async def test_locked_evidence_drift_fails_before_any_submission_write(
    pg_factory: async_sessionmaker[AsyncSession],
) -> None:
    async with pg_factory() as session:
        await _seed(session)

    async with pg_factory() as locking_session:
        reader = SqlAlchemyProductPackageEvidenceReader(
            locking_session,
            lock_evidence=True,
        )
        await reader.load_evidence("evidence:market:one", "tenant-a")

        async def submit_while_locked():
            async with pg_factory() as session:
                backend_pid = await session.scalar(text("select pg_backend_pid()"))
                assert isinstance(backend_pid, int)
                pid_ready.set_result(backend_pid)
                return await submit_product_package_draft(
                    SqlAlchemyProductPackageSubmissionRepository(
                        session,
                        clock=lambda: NOW,
                    ),
                    _context(),
                    _source(),
                    idempotency_key="pg-evidence-drift-race",
                    now=NOW,
                )

        pid_ready: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        pending = asyncio.create_task(submit_while_locked())
        backend_pid = await pid_ready

        observed_lock_wait = False
        deadline = asyncio.get_running_loop().time() + 5
        while asyncio.get_running_loop().time() < deadline:
            async with pg_factory() as observer:
                wait_type = await observer.scalar(
                    text(
                        "select wait_event_type from pg_stat_activity "
                        "where pid = :backend_pid"
                    ),
                    {"backend_pid": backend_pid},
                )
            if wait_type == "Lock":
                observed_lock_wait = True
                break
            if pending.done():
                break
            await asyncio.sleep(0.02)

        if not observed_lock_wait:
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            pytest.fail("submission never reached a PostgreSQL lock wait")
        assert not pending.done()

        await locking_session.execute(
            update(EvidenceRow)
            .where(
                EvidenceRow.id == "evidence:market:one",
                EvidenceRow.tenant_scope == "tenant-a",
            )
            .values(
                description="source changed while submission waited for row lock",
                updated_at=NOW + timedelta(minutes=1),
            )
        )
        await locking_session.commit()

    with pytest.raises(
        ProductPackageSubmissionConflictError,
        match="EVIDENCE_ADMISSION_REVALIDATION_FAILED",
    ):
        await pending

    async with pg_factory() as session:
        assert await session.scalar(select(func.count()).select_from(ProductPackageDraftRow)) == 0
        assert await session.scalar(select(func.count()).select_from(HumanTaskRow)) == 0
        assert await session.scalar(select(func.count()).select_from(AuditEventRow)) == 0
