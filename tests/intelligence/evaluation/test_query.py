from datetime import UTC, datetime

import pytest

from backend.intelligence.evaluation.operator_identity import (
    OperatorIdentity,
    OperatorIdentityError,
)
from backend.intelligence.evaluation.query import (
    EVALUATION_READ_SCOPE,
    AuthorizedEvaluationQueryService,
)
from backend.intelligence.evaluation.report_archive import InMemoryBenchmarkReportArchive
from backend.intelligence.evaluation.slice_archive import InMemoryBenchmarkSliceArchive
from backend.intelligence.experience.slice_runner import EvaluationSlice
from tests.intelligence.evaluation.test_report_archive import _report


class _IdentityPort:
    def __init__(self, identity: OperatorIdentity) -> None:
        self.identity = identity

    async def resolve(self, *, environment: str) -> OperatorIdentity:
        return self.identity


class _ArchiveRuntime:
    def __init__(self) -> None:
        self.reports = InMemoryBenchmarkReportArchive(
            clock=lambda: datetime(2026, 8, 30, tzinfo=UTC)
        )
        self.slices = InMemoryBenchmarkSliceArchive(
            clock=lambda: datetime(2026, 8, 30, tzinfo=UTC)
        )

    async def list(self, **kwargs):
        return await self.reports.list(**kwargs)

    async def list_slices(self, **kwargs):
        return await self.slices.list(**kwargs)


def _service(
    scopes: tuple[str, ...] = (EVALUATION_READ_SCOPE,),
) -> AuthorizedEvaluationQueryService:
    return AuthorizedEvaluationQueryService(
        environment="staging",
        identity_port=_IdentityPort(
            OperatorIdentity("operator-1", "staging", "auth-ref", scopes)
        ),
        archive_runtime=_ArchiveRuntime(),
    )


@pytest.mark.asyncio
async def test_authorized_query_delegates_bounded_metadata_queries() -> None:
    runtime = _service().archive_runtime
    report = _report()
    await runtime.reports.archive(report, dataset_fingerprint="a" * 64)
    await runtime.slices.archive(
        report.report_ref,
        (
            EvaluationSlice(
                dimension="locale",
                value="zh-CN",
                case_ids=("case-1",),
                report=report,
            ),
        ),
        dataset_fingerprint="a" * 64,
    )

    service = _service()
    service.archive_runtime.reports = runtime.reports
    service.archive_runtime.slices = runtime.slices
    reports = await service.list_reports(limit=1)
    slices = await service.list_slices(dimension="locale", limit=1)
    assert reports[0].report_ref == report.report_ref
    assert slices[0].value == "zh-CN"
    assert "output" not in str(reports[0].report_payload).lower()


@pytest.mark.asyncio
async def test_query_requires_scope_and_rejects_identity_mismatch() -> None:
    with pytest.raises(PermissionError, match="SCOPE_MISSING"):
        await _service(scopes=("ai.release.read",)).list_reports()

    mismatch = AuthorizedEvaluationQueryService(
        environment="production",
        identity_port=_IdentityPort(
            OperatorIdentity("operator-1", "staging", "auth-ref", (EVALUATION_READ_SCOPE,))
        ),
        archive_runtime=_ArchiveRuntime(),
    )
    with pytest.raises(OperatorIdentityError, match="ENVIRONMENT_MISMATCH"):
        await mismatch.list_reports()
