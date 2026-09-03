from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from backend.intelligence.evaluation.report_archive import (
    BenchmarkReportArchiveBase,
    BenchmarkReportArchiveError,
    InMemoryBenchmarkReportArchive,
    SqlAlchemyBenchmarkReportArchive,
)
from backend.intelligence.experience.multimodal_eval import (
    MultimodalAdapterResult,
    MultimodalEvalRunner,
)
from backend.intelligence.model_gateway.contracts import AiProvenance


@pytest.fixture
async def session_factory() -> async_sessionmaker[AsyncSession]:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    async with engine.begin() as connection:
        await connection.run_sync(BenchmarkReportArchiveBase.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


def _report():
    from backend.intelligence.experience.multimodal_eval import GoldCase

    case = GoldCase(
        case_id="case-1",
        version="gold.v1",
        fixture_kind="synthetic",
        modalities=("text",),
        locale="zh-CN",
        safety_labels=("synthetic-safe",),
        expected_schema={"type": "object", "required": ["summary"]},
        media_refs=("fixture:case-1:text",),
    )

    def adapter(item: GoldCase) -> MultimodalAdapterResult:
        return MultimodalAdapterResult(
            provider_id="provider-a",
            model="model-a",
            model_version="v1",
            output={"summary": "ok"},
            refused=False,
            safety_labels=item.safety_labels,
            safety_passed=True,
            provenance=AiProvenance(
                provider_id="provider-a",
                model="model-a",
                model_version="v1",
                prompt_version="prompt.v1",
                schema_version=item.version,
                context_snapshot_ref="ctx:synthetic",
                latency_ms=20,
                data_class="SYNTHETIC",
                use_case="offline-eval",
            ),
            latency_ms=20,
            cost_microusd=1,
        )

    return MultimodalEvalRunner().run((case,), {"provider-a": adapter})


@pytest.mark.asyncio
async def test_in_memory_archive_is_idempotent_and_metadata_only() -> None:
    report = _report()
    archive = InMemoryBenchmarkReportArchive(
        clock=lambda: datetime(2026, 8, 30, tzinfo=UTC)
    )
    first = await archive.archive(report, dataset_fingerprint="a" * 64)
    second = await archive.archive(report, dataset_fingerprint="a" * 64)
    assert first == second
    assert first.total_cases == 1
    assert "output" not in str(first.report_payload).lower()
    assert await archive.get(first.report_ref) == first
    assert await archive.list(case_version="gold.v1", limit=1) == (first,)


@pytest.mark.asyncio
async def test_sql_archive_round_trips_and_rejects_report_ref_conflict(session_factory) -> None:
    report = _report()
    async with session_factory() as session:
        archive = SqlAlchemyBenchmarkReportArchive(
            session, clock=lambda: datetime(2026, 8, 30, tzinfo=UTC)
        )
        first = await archive.archive(report, dataset_fingerprint="a" * 64)
        second = await archive.archive(report, dataset_fingerprint="a" * 64)
        listed = await archive.list(dataset_fingerprint="a" * 64, limit=1)
        await session.commit()
    assert first == second
    assert listed == (first,)

    with pytest.raises(BenchmarkReportArchiveError, match="DATASET_FINGERPRINT_INVALID"):
        await InMemoryBenchmarkReportArchive().archive(report, dataset_fingerprint="invalid")
