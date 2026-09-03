"""Durable, metadata-only archive for multimodal benchmark reports."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import JSON, DateTime, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.experience.multimodal_eval import (
    EvaluationReleaseDecision,
    MultimodalEvaluationReport,
)

_SENSITIVE_KEYS = frozenset(
    {
        "prompt",
        "output",
        "input",
        "payload",
        "raw_media",
        "media_bytes",
        "media_content",
        "api_key",
        "secret",
        "credential",
    }
)
_MAX_PAYLOAD_BYTES = 256_000


class BenchmarkReportArchiveError(ValueError):
    """Raised when a report cannot be archived without weakening governance."""


@dataclass(frozen=True, slots=True)
class BenchmarkReportArchive:
    report_ref: str
    case_version: str
    dataset_fingerprint: str
    total_cases: int
    report_payload: Mapping[str, object]
    archived_at: datetime


class BenchmarkReportArchiveBase(DeclarativeBase):
    """SQL metadata boundary for benchmark reports."""


class BenchmarkReportArchiveRow(BenchmarkReportArchiveBase):
    __tablename__ = "ai_benchmark_reports"

    archive_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    report_ref: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    case_version: Mapped[str] = mapped_column(String(128), nullable=False)
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    total_cases: Mapped[int] = mapped_column(nullable=False)
    report_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BenchmarkReportArchivePort(Protocol):
    async def archive(
        self,
        report: MultimodalEvaluationReport,
        *,
        dataset_fingerprint: str,
        gate: EvaluationReleaseDecision | None = None,
    ) -> BenchmarkReportArchive: ...

    async def get(self, report_ref: str) -> BenchmarkReportArchive | None: ...

    async def list(
        self,
        *,
        case_version: str | None = None,
        dataset_fingerprint: str | None = None,
        limit: int = 50,
    ) -> tuple[BenchmarkReportArchive, ...]: ...


class InMemoryBenchmarkReportArchive:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self.reports: dict[str, BenchmarkReportArchive] = {}

    async def archive(
        self,
        report: MultimodalEvaluationReport,
        *,
        dataset_fingerprint: str,
        gate: EvaluationReleaseDecision | None = None,
    ) -> BenchmarkReportArchive:
        archive = _build_archive(report, dataset_fingerprint, gate, self._clock())
        existing = self.reports.get(archive.report_ref)
        if existing is not None:
            if existing != archive:
                raise BenchmarkReportArchiveError("REPORT_REF_CONFLICT")
            return existing
        self.reports[archive.report_ref] = archive
        return archive

    async def get(self, report_ref: str) -> BenchmarkReportArchive | None:
        if not isinstance(report_ref, str) or not report_ref.strip():
            raise BenchmarkReportArchiveError("REPORT_REF_REQUIRED")
        return self.reports.get(report_ref)

    async def list(
        self,
        *,
        case_version: str | None = None,
        dataset_fingerprint: str | None = None,
        limit: int = 50,
    ) -> tuple[BenchmarkReportArchive, ...]:
        _validate_query(case_version, dataset_fingerprint, limit)
        values = [
            item
            for item in self.reports.values()
            if (case_version is None or item.case_version == case_version)
            and (
                dataset_fingerprint is None
                or item.dataset_fingerprint == dataset_fingerprint
            )
        ]
        return tuple(
            sorted(
                values,
                key=lambda item: (item.archived_at, item.report_ref),
                reverse=True,
            )[:limit]
        )


class SqlAlchemyBenchmarkReportArchive:
    """SQL archive; add/flush only, transaction owned by the composition root."""

    def __init__(
        self, session: AsyncSession, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._session = session
        self._clock = clock or (lambda: datetime.now(UTC))

    async def archive(
        self,
        report: MultimodalEvaluationReport,
        *,
        dataset_fingerprint: str,
        gate: EvaluationReleaseDecision | None = None,
    ) -> BenchmarkReportArchive:
        archive = _build_archive(report, dataset_fingerprint, gate, self._clock())
        existing = await self._session.scalar(
            select(BenchmarkReportArchiveRow).where(
                BenchmarkReportArchiveRow.report_ref == archive.report_ref
            )
        )
        if existing is not None:
            stored = _stored(existing)
            if not _same_archive(stored, archive):
                raise BenchmarkReportArchiveError("REPORT_REF_CONFLICT")
            return stored
        self._session.add(
            BenchmarkReportArchiveRow(
                archive_id=_archive_id(archive.report_ref, archive.dataset_fingerprint),
                report_ref=archive.report_ref,
                case_version=archive.case_version,
                dataset_fingerprint=archive.dataset_fingerprint,
                total_cases=archive.total_cases,
                report_payload=dict(archive.report_payload),
                archived_at=archive.archived_at,
            )
        )
        await self._session.flush()
        return archive

    async def get(self, report_ref: str) -> BenchmarkReportArchive | None:
        if not isinstance(report_ref, str) or not report_ref.strip():
            raise BenchmarkReportArchiveError("REPORT_REF_REQUIRED")
        row = await self._session.scalar(
            select(BenchmarkReportArchiveRow).where(
                BenchmarkReportArchiveRow.report_ref == report_ref
            )
        )
        return _stored(row) if row is not None else None

    async def list(
        self,
        *,
        case_version: str | None = None,
        dataset_fingerprint: str | None = None,
        limit: int = 50,
    ) -> tuple[BenchmarkReportArchive, ...]:
        _validate_query(case_version, dataset_fingerprint, limit)
        statement = select(BenchmarkReportArchiveRow).order_by(
            BenchmarkReportArchiveRow.archived_at.desc(),
            BenchmarkReportArchiveRow.report_ref,
        ).limit(limit)
        if case_version is not None:
            statement = statement.where(BenchmarkReportArchiveRow.case_version == case_version)
        if dataset_fingerprint is not None:
            statement = statement.where(
                BenchmarkReportArchiveRow.dataset_fingerprint == dataset_fingerprint
            )
        result = await self._session.execute(statement)
        return tuple(_stored(row) for row in result.scalars())


def _build_archive(
    report: MultimodalEvaluationReport,
    dataset_fingerprint: str,
    gate: EvaluationReleaseDecision | None,
    archived_at: datetime,
) -> BenchmarkReportArchive:
    if not isinstance(report, MultimodalEvaluationReport):
        raise BenchmarkReportArchiveError("REPORT_REQUIRED")
    if not isinstance(dataset_fingerprint, str) or len(dataset_fingerprint) != 64:
        raise BenchmarkReportArchiveError("DATASET_FINGERPRINT_INVALID")
    try:
        int(dataset_fingerprint, 16)
    except ValueError as exc:
        raise BenchmarkReportArchiveError("DATASET_FINGERPRINT_INVALID") from exc
    if archived_at.tzinfo is None or archived_at.utcoffset() is None:
        raise BenchmarkReportArchiveError("ARCHIVE_CLOCK_MUST_BE_TIMEZONE_AWARE")
    payload = report.to_ledger_payload(gate)
    _assert_safe_payload(payload)
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raise BenchmarkReportArchiveError("REPORT_PAYLOAD_TOO_LARGE")
    return BenchmarkReportArchive(
        report_ref=report.report_ref,
        case_version=report.case_version,
        dataset_fingerprint=dataset_fingerprint,
        total_cases=report.total_cases,
        report_payload=payload,
        archived_at=archived_at,
    )


def _assert_safe_payload(value: object, *, key: str | None = None) -> None:
    if key is not None and key.lower() in _SENSITIVE_KEYS:
        raise BenchmarkReportArchiveError("REPORT_PAYLOAD_CONTAINS_SENSITIVE_FIELD")
    if isinstance(value, Mapping):
        for nested_key, nested_value in value.items():
            if not isinstance(nested_key, str):
                raise BenchmarkReportArchiveError("REPORT_PAYLOAD_KEY_INVALID")
            _assert_safe_payload(nested_value, key=nested_key)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_safe_payload(item)


def _validate_query(
    case_version: str | None,
    dataset_fingerprint: str | None,
    limit: int,
) -> None:
    if case_version is not None and (not isinstance(case_version, str) or not case_version.strip()):
        raise BenchmarkReportArchiveError("CASE_VERSION_INVALID")
    if dataset_fingerprint is not None:
        if not isinstance(dataset_fingerprint, str) or len(dataset_fingerprint) != 64:
            raise BenchmarkReportArchiveError("DATASET_FINGERPRINT_INVALID")
        try:
            int(dataset_fingerprint, 16)
        except ValueError as exc:
            raise BenchmarkReportArchiveError("DATASET_FINGERPRINT_INVALID") from exc
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise BenchmarkReportArchiveError("QUERY_LIMIT_INVALID")


def _archive_id(report_ref: str, dataset_fingerprint: str) -> str:
    return hashlib.sha256(f"{report_ref}:{dataset_fingerprint}".encode()).hexdigest()


def _stored(row: BenchmarkReportArchiveRow) -> BenchmarkReportArchive:
    payload = row.report_payload
    if not isinstance(payload, dict):
        raise BenchmarkReportArchiveError("PERSISTED_REPORT_PAYLOAD_INVALID")
    _assert_safe_payload(payload)
    return BenchmarkReportArchive(
        report_ref=row.report_ref,
        case_version=row.case_version,
        dataset_fingerprint=row.dataset_fingerprint,
        total_cases=row.total_cases,
        report_payload=payload,
        archived_at=_normalise_timestamp(row.archived_at),
    )


def _same_archive(left: BenchmarkReportArchive, right: BenchmarkReportArchive) -> bool:
    """Compare idempotency fields while tolerating database timestamp precision."""

    return (
        left.report_ref == right.report_ref
        and left.case_version == right.case_version
        and left.dataset_fingerprint == right.dataset_fingerprint
        and left.total_cases == right.total_cases
        and left.report_payload == right.report_payload
    )


def _normalise_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


__all__ = [
    "BenchmarkReportArchive",
    "BenchmarkReportArchiveBase",
    "BenchmarkReportArchiveError",
    "BenchmarkReportArchivePort",
    "BenchmarkReportArchiveRow",
    "InMemoryBenchmarkReportArchive",
    "SqlAlchemyBenchmarkReportArchive",
]
