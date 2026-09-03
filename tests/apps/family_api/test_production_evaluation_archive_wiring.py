from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.apps.family_api.production_evaluation_archive_wiring import (
    ProductionEvaluationArchiveRuntime,
    build_production_evaluation_archive_runtime,
)
from backend.intelligence.evaluation.report_archive import BenchmarkReportArchiveBase
from backend.intelligence.evaluation.slice_archive import BenchmarkSliceArchiveBase
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


@pytest.mark.asyncio
async def test_production_archive_runtime_commits_report_and_is_idempotent(session_factory) -> None:
    runtime = build_production_evaluation_archive_runtime(
        environment="production",
        session_factory=session_factory,
        clock=lambda: datetime(2026, 8, 30, tzinfo=UTC),
    )
    report = _report()
    first = await runtime.archive(report, dataset_fingerprint="a" * 64)
    second = await runtime.archive(report, dataset_fingerprint="a" * 64)
    assert first == second
    assert first.total_cases == 1
    assert await runtime.get(first.report_ref) == first
    assert await runtime.list(case_version="gold.v1", limit=1) == (first,)


@pytest.mark.asyncio
async def test_production_archive_runtime_atomically_archives_slices(session_factory) -> None:
    runtime = build_production_evaluation_archive_runtime(
        environment="staging",
        session_factory=session_factory,
        clock=lambda: datetime(2026, 8, 30, tzinfo=UTC),
    )
    report = _report()
    slices = (
        EvaluationSlice(
            dimension="locale",
            value="zh-CN",
            case_ids=("case-1",),
            report=report,
        ),
    )
    stored = await runtime.archive_slices(
        report, slices, dataset_fingerprint="a" * 64
    )
    assert len(stored) == 1
    assert await runtime.list_slices(report_ref=report.report_ref) == stored


def test_production_archive_runtime_rejects_non_production_environment(session_factory) -> None:
    with pytest.raises(ValueError, match="staging or production"):
        ProductionEvaluationArchiveRuntime(environment="test", session_factory=session_factory)
