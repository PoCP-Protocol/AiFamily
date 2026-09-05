"""Production composition root for metadata-only evaluation report archival."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.intelligence.evaluation.report_archive import (
    BenchmarkReportArchive,
    SqlAlchemyBenchmarkReportArchive,
)
from backend.intelligence.evaluation.slice_archive import (
    BenchmarkSliceArchive,
    SqlAlchemyBenchmarkSliceArchive,
)
from backend.intelligence.experience.multimodal_eval import (
    EvaluationReleaseDecision,
    MultimodalEvaluationReport,
)
from backend.intelligence.experience.slice_runner import EvaluationSlice

_PRODUCTION_ENVIRONMENTS = frozenset({"staging", "production"})


class ProductionEvaluationArchiveRuntime:
    """Archive one report in a fresh transaction; scheduling stays external."""

    def __init__(
        self,
        *,
        environment: str,
        session_factory: async_sessionmaker[AsyncSession],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if environment not in _PRODUCTION_ENVIRONMENTS:
            raise ValueError("evaluation archive runtime requires staging or production")
        if not callable(session_factory):
            raise TypeError("session_factory must be callable")
        self._environment = environment
        self._session_factory = session_factory
        self._clock = clock

    async def archive(
        self,
        report: MultimodalEvaluationReport,
        *,
        dataset_fingerprint: str,
        gate: EvaluationReleaseDecision | None = None,
    ) -> BenchmarkReportArchive:
        async with self._session_factory() as session:
            archive = SqlAlchemyBenchmarkReportArchive(session, clock=self._clock)
            result = await archive.archive(
                report,
                dataset_fingerprint=dataset_fingerprint,
                gate=gate,
            )
            await session.commit()
            return result

    async def get(self, report_ref: str) -> BenchmarkReportArchive | None:
        async with self._session_factory() as session:
            return await SqlAlchemyBenchmarkReportArchive(session).get(report_ref)

    async def list(
        self,
        *,
        case_version: str | None = None,
        dataset_fingerprint: str | None = None,
        limit: int = 50,
    ) -> tuple[BenchmarkReportArchive, ...]:
        async with self._session_factory() as session:
            return await SqlAlchemyBenchmarkReportArchive(session).list(
                case_version=case_version,
                dataset_fingerprint=dataset_fingerprint,
                limit=limit,
            )

    async def archive_slices(
        self,
        report: MultimodalEvaluationReport,
        slices: tuple[EvaluationSlice, ...],
        *,
        dataset_fingerprint: str,
        gate: EvaluationReleaseDecision | None = None,
    ) -> tuple[BenchmarkSliceArchive, ...]:
        """Atomically archive the parent report and its independently evaluated slices."""

        async with self._session_factory() as session:
            await SqlAlchemyBenchmarkReportArchive(session, clock=self._clock).archive(
                report,
                dataset_fingerprint=dataset_fingerprint,
                gate=gate,
            )
            archived = await SqlAlchemyBenchmarkSliceArchive(
                session, clock=self._clock
            ).archive(
                report.report_ref,
                slices,
                dataset_fingerprint=dataset_fingerprint,
            )
            await session.commit()
            return archived

    async def list_slices(
        self,
        *,
        report_ref: str | None = None,
        dimension: str | None = None,
        value: str | None = None,
        limit: int = 100,
    ) -> tuple[BenchmarkSliceArchive, ...]:
        async with self._session_factory() as session:
            return await SqlAlchemyBenchmarkSliceArchive(session).list(
                report_ref=report_ref,
                dimension=dimension,
                value=value,
                limit=limit,
            )


def build_production_evaluation_archive_runtime(
    *,
    environment: str,
    session_factory: async_sessionmaker[AsyncSession],
    clock: Callable[[], datetime] | None = None,
) -> ProductionEvaluationArchiveRuntime:
    """Explicit factory used by staging/production application wiring."""

    return ProductionEvaluationArchiveRuntime(
        environment=environment,
        session_factory=session_factory,
        clock=clock,
    )


__all__ = [
    "ProductionEvaluationArchiveRuntime",
    "build_production_evaluation_archive_runtime",
]
