from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.evaluation.report_archive import BenchmarkReportArchiveBase
from backend.intelligence.evaluation.slice_archive import (
    BenchmarkSliceArchiveBase,
    BenchmarkSliceArchiveError,
    InMemoryBenchmarkSliceArchive,
    SqlAlchemyBenchmarkSliceArchive,
)
from backend.intelligence.experience.slice_runner import EvaluationSlice
from tests.intelligence.evaluation.test_report_archive import _report


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(BenchmarkReportArchiveBase.metadata.create_all)
        await connection.run_sync(BenchmarkSliceArchiveBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _slices():
    report = _report()
    return report, (
        EvaluationSlice(
            dimension="locale",
            value="zh-CN",
            case_ids=("case-1",),
            report=report,
        ),
        EvaluationSlice(
            dimension="modality",
            value="text",
            case_ids=("case-1",),
            report=report,
        ),
    )


@pytest.mark.asyncio
async def test_in_memory_slice_archive_is_idempotent_and_queryable() -> None:
    report, slices = _slices()
    archive = InMemoryBenchmarkSliceArchive(clock=lambda: datetime(2026, 8, 30, tzinfo=UTC))
    first = await archive.archive(
        report.report_ref, slices, dataset_fingerprint="a" * 64
    )
    second = await archive.archive(
        report.report_ref, slices, dataset_fingerprint="a" * 64
    )
    assert first == second
    assert len(await archive.list(report_ref=report.report_ref, dimension="locale")) == 1
    with pytest.raises(BenchmarkSliceArchiveError, match="QUERY_LIMIT_INVALID"):
        await archive.list(limit=0)


@pytest.mark.asyncio
async def test_sql_slice_archive_round_trips(session_factory) -> None:
    report, slices = _slices()
    async with session_factory() as session:
        archive = SqlAlchemyBenchmarkSliceArchive(
            session, clock=lambda: datetime(2026, 8, 30, tzinfo=UTC)
        )
        stored = await archive.archive(
            report.report_ref, slices, dataset_fingerprint="a" * 64
        )
        listed = await archive.list(report_ref=report.report_ref)
        await session.commit()
    assert stored == listed
    assert tuple(item.dimension for item in listed) == ("locale", "modality")
