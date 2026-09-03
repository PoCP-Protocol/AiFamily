"""Durable, metadata-only archive for benchmark evaluation slices."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from sqlalchemy import JSON, DateTime, Index, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.experience.slice_runner import EvaluationSlice


class BenchmarkSliceArchiveError(ValueError):
    """Raised when a slice cannot be archived without weakening governance."""


@dataclass(frozen=True, slots=True)
class BenchmarkSliceArchive:
    report_ref: str
    dataset_fingerprint: str
    dimension: str
    value: str
    case_count: int
    slice_report_ref: str
    report_payload: dict[str, object]
    archived_at: datetime


class BenchmarkSliceArchiveBase(DeclarativeBase):
    """SQL metadata boundary for benchmark slice records."""


class BenchmarkSliceArchiveRow(BenchmarkSliceArchiveBase):
    __tablename__ = "ai_benchmark_report_slices"
    __table_args__ = (
        Index(
            "uq_ai_benchmark_report_slices_identity",
            "report_ref",
            "dimension",
            "value",
            unique=True,
        ),
        Index(
            "ix_ai_benchmark_report_slices_dataset_dimension",
            "dataset_fingerprint",
            "dimension",
            "value",
        ),
    )

    slice_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    report_ref: Mapped[str] = mapped_column(Text, nullable=False)
    dataset_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    dimension: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(128), nullable=False)
    case_count: Mapped[int] = mapped_column(nullable=False)
    slice_report_ref: Mapped[str] = mapped_column(Text, nullable=False)
    report_payload: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False)
    archived_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class BenchmarkSliceArchivePort(Protocol):
    async def archive(
        self,
        report_ref: str,
        slices: Sequence[EvaluationSlice],
        *,
        dataset_fingerprint: str,
        archived_at: datetime | None = None,
    ) -> tuple[BenchmarkSliceArchive, ...]: ...

    async def list(
        self,
        *,
        report_ref: str | None = None,
        dimension: str | None = None,
        value: str | None = None,
        limit: int = 100,
    ) -> tuple[BenchmarkSliceArchive, ...]: ...


class InMemoryBenchmarkSliceArchive:
    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self._clock = clock or (lambda: datetime.now(UTC))
        self.slices: dict[tuple[str, str, str], BenchmarkSliceArchive] = {}

    async def archive(
        self,
        report_ref: str,
        slices: Sequence[EvaluationSlice],
        *,
        dataset_fingerprint: str,
        archived_at: datetime | None = None,
    ) -> tuple[BenchmarkSliceArchive, ...]:
        built = _build_slices(report_ref, slices, dataset_fingerprint, archived_at or self._clock())
        for item in built:
            key = (item.report_ref, item.dimension, item.value)
            existing = self.slices.get(key)
            if existing is not None and existing != item:
                raise BenchmarkSliceArchiveError("SLICE_IDENTITY_CONFLICT")
        for item in built:
            self.slices[(item.report_ref, item.dimension, item.value)] = item
        return built

    async def list(
        self,
        *,
        report_ref: str | None = None,
        dimension: str | None = None,
        value: str | None = None,
        limit: int = 100,
    ) -> tuple[BenchmarkSliceArchive, ...]:
        _validate_query(report_ref, dimension, value, limit)
        values = [
            item
            for item in self.slices.values()
            if (report_ref is None or item.report_ref == report_ref)
            and (dimension is None or item.dimension == dimension)
            and (value is None or item.value == value)
        ]
        return tuple(sorted(values, key=_sort_key)[:limit])


class SqlAlchemyBenchmarkSliceArchive:
    """SQL slice archive; transaction ownership remains with the caller."""

    def __init__(
        self, session: AsyncSession, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._session = session
        self._clock = clock or (lambda: datetime.now(UTC))

    async def archive(
        self,
        report_ref: str,
        slices: Sequence[EvaluationSlice],
        *,
        dataset_fingerprint: str,
        archived_at: datetime | None = None,
    ) -> tuple[BenchmarkSliceArchive, ...]:
        built = _build_slices(report_ref, slices, dataset_fingerprint, archived_at or self._clock())
        stored: list[BenchmarkSliceArchive] = []
        for item in built:
            row = await self._session.scalar(
                select(BenchmarkSliceArchiveRow).where(
                    BenchmarkSliceArchiveRow.report_ref == item.report_ref,
                    BenchmarkSliceArchiveRow.dimension == item.dimension,
                    BenchmarkSliceArchiveRow.value == item.value,
                )
            )
            if row is not None:
                existing = _stored(row)
                if existing != item:
                    raise BenchmarkSliceArchiveError("SLICE_IDENTITY_CONFLICT")
                stored.append(existing)
                continue
            self._session.add(
                BenchmarkSliceArchiveRow(
                    slice_id=_slice_id(item),
                    report_ref=item.report_ref,
                    dataset_fingerprint=item.dataset_fingerprint,
                    dimension=item.dimension,
                    value=item.value,
                    case_count=item.case_count,
                    slice_report_ref=item.slice_report_ref,
                    report_payload=item.report_payload,
                    archived_at=item.archived_at,
                )
            )
            stored.append(item)
        await self._session.flush()
        return tuple(stored)

    async def list(
        self,
        *,
        report_ref: str | None = None,
        dimension: str | None = None,
        value: str | None = None,
        limit: int = 100,
    ) -> tuple[BenchmarkSliceArchive, ...]:
        _validate_query(report_ref, dimension, value, limit)
        statement = select(BenchmarkSliceArchiveRow).order_by(
            BenchmarkSliceArchiveRow.dimension,
            BenchmarkSliceArchiveRow.value,
        ).limit(limit)
        if report_ref is not None:
            statement = statement.where(BenchmarkSliceArchiveRow.report_ref == report_ref)
        if dimension is not None:
            statement = statement.where(BenchmarkSliceArchiveRow.dimension == dimension)
        if value is not None:
            statement = statement.where(BenchmarkSliceArchiveRow.value == value)
        result = await self._session.execute(statement)
        return tuple(_stored(row) for row in result.scalars())


def _build_slices(
    report_ref: str,
    slices: Sequence[EvaluationSlice],
    dataset_fingerprint: str,
    archived_at: datetime,
) -> tuple[BenchmarkSliceArchive, ...]:
    if not isinstance(report_ref, str) or not report_ref.strip():
        raise BenchmarkSliceArchiveError("REPORT_REF_REQUIRED")
    if not isinstance(dataset_fingerprint, str) or len(dataset_fingerprint) != 64:
        raise BenchmarkSliceArchiveError("DATASET_FINGERPRINT_INVALID")
    try:
        int(dataset_fingerprint, 16)
    except ValueError as exc:
        raise BenchmarkSliceArchiveError("DATASET_FINGERPRINT_INVALID") from exc
    if archived_at.tzinfo is None or archived_at.utcoffset() is None:
        raise BenchmarkSliceArchiveError("ARCHIVE_CLOCK_MUST_BE_TIMEZONE_AWARE")
    seen: set[tuple[str, str]] = set()
    built: list[BenchmarkSliceArchive] = []
    for item in slices:
        if not isinstance(item, EvaluationSlice):
            raise BenchmarkSliceArchiveError("SLICE_REQUIRED")
        key = (item.dimension, item.value)
        if key in seen:
            raise BenchmarkSliceArchiveError("SLICE_IDENTITY_DUPLICATE")
        seen.add(key)
        if not item.case_ids:
            raise BenchmarkSliceArchiveError("SLICE_CASES_REQUIRED")
        payload = item.report.to_ledger_payload()
        _assert_safe_payload(payload)
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        if len(encoded.encode("utf-8")) > 256_000:
            raise BenchmarkSliceArchiveError("SLICE_PAYLOAD_TOO_LARGE")
        built.append(
            BenchmarkSliceArchive(
                report_ref=report_ref,
                dataset_fingerprint=dataset_fingerprint,
                dimension=item.dimension,
                value=item.value,
                case_count=len(item.case_ids),
                slice_report_ref=item.report.report_ref,
                report_payload=payload,
                archived_at=archived_at,
            )
        )
    return tuple(sorted(built, key=lambda item: (item.dimension, item.value)))


def _validate_query(
    report_ref: str | None,
    dimension: str | None,
    value: str | None,
    limit: int,
) -> None:
    for name, item in (
        ("REPORT_REF", report_ref),
        ("SLICE_DIMENSION", dimension),
        ("SLICE_VALUE", value),
    ):
        if item is not None and (not isinstance(item, str) or not item.strip()):
            raise BenchmarkSliceArchiveError(f"{name}_INVALID")
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 100:
        raise BenchmarkSliceArchiveError("QUERY_LIMIT_INVALID")


def _assert_safe_payload(value: object, *, key: str | None = None) -> None:
    if key is not None and key.lower() in {
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
    }:
        raise BenchmarkSliceArchiveError("SLICE_PAYLOAD_CONTAINS_SENSITIVE_FIELD")
    if isinstance(value, dict):
        for nested_key, nested_value in value.items():
            if not isinstance(nested_key, str):
                raise BenchmarkSliceArchiveError("SLICE_PAYLOAD_KEY_INVALID")
            _assert_safe_payload(nested_value, key=nested_key)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _assert_safe_payload(item)


def _slice_id(item: BenchmarkSliceArchive) -> str:
    return hashlib.sha256(
        f"{item.report_ref}:{item.dataset_fingerprint}:{item.dimension}:{item.value}".encode()
    ).hexdigest()


def _stored(row: BenchmarkSliceArchiveRow) -> BenchmarkSliceArchive:
    payload = row.report_payload
    if not isinstance(payload, dict):
        raise BenchmarkSliceArchiveError("PERSISTED_SLICE_PAYLOAD_INVALID")
    _assert_safe_payload(payload)
    return BenchmarkSliceArchive(
        report_ref=row.report_ref,
        dataset_fingerprint=row.dataset_fingerprint,
        dimension=row.dimension,
        value=row.value,
        case_count=row.case_count,
        slice_report_ref=row.slice_report_ref,
        report_payload=payload,
        archived_at=row.archived_at.replace(tzinfo=UTC)
        if row.archived_at.tzinfo is None
        else row.archived_at.astimezone(UTC),
    )


def _sort_key(item: BenchmarkSliceArchive) -> tuple[str, str]:
    return item.dimension, item.value


__all__ = [
    "BenchmarkSliceArchive",
    "BenchmarkSliceArchiveBase",
    "BenchmarkSliceArchiveError",
    "BenchmarkSliceArchivePort",
    "BenchmarkSliceArchiveRow",
    "InMemoryBenchmarkSliceArchive",
    "SqlAlchemyBenchmarkSliceArchive",
]
