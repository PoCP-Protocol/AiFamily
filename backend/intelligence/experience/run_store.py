"""Async SQLAlchemy persistence for :class:`DurableExperienceRun`.

The run store is an AI-runtime ledger, not a domain repository.  It persists a
run, its append-only transition log and its draft checkpoints in three tables
owned by the experience runtime.  Every read requires the complete
tenant/family/subject scope; a matching run id in another scope is never
returned.

The adapter deliberately receives an ``AsyncSession`` and flushes only.  The
composition root decides the transaction boundary, so a caller can commit the
run log together with an outbox message without this module importing a domain
table.  Model output is retained only as ``DRAFT`` data and media are opaque
references (never bytes or data URLs).
"""

from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.experience.runs import (
    DurableExperienceRun,
    RunCheckpoint,
    RunContractError,
    RunEvent,
    RunEventType,
    RunSnapshot,
    RunState,
)


class ExperienceRunPersistenceBase(DeclarativeBase):
    """Metadata boundary for experience-run persistence tables."""


class ExperienceRunRow(ExperienceRunPersistenceBase):
    __tablename__ = "experience_runs"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    request_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    latest_checkpoint_id: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    # HTTP-facing ledger metadata.  These fields are deliberately kept on the
    # runtime-owned run envelope rather than a domain table: create retries and
    # deletion state must survive a process restart while remaining outside the
    # Family/Growth fact model.
    create_idempotency_key: Mapped[str | None] = mapped_column(String(256))
    create_fingerprint: Mapped[str | None] = mapped_column(Text)
    create_status: Mapped[str | None] = mapped_column(String(16))
    create_response_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    deletion_state: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class ExperienceRunEventRow(ExperienceRunPersistenceBase):
    __tablename__ = "experience_run_events"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "run_id",
            "event_id",
            name="uq_experience_run_event_id",
        ),
        UniqueConstraint(
            "tenant_id",
            "run_id",
            "idempotency_key",
            name="uq_experience_run_event_idempotency",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    target_state: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str | None] = mapped_column(String(256))
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ExperienceRunCheckpointRow(ExperienceRunPersistenceBase):
    __tablename__ = "experience_run_checkpoints"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "run_id",
            "checkpoint_id",
            name="uq_experience_run_checkpoint_id",
        ),
    )

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    checkpoint_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[str] = mapped_column(String(32), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    artifact_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    draft_payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")


@dataclass(frozen=True, slots=True)
class RunScope:
    """Explicit read scope required for every run load/replay operation."""

    tenant_id: str
    family_id: str
    subject_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.family_id:
            raise RunContractError("RUN_SCOPE_TENANT_AND_FAMILY_REQUIRED")
        if not self.subject_ids or any(not value for value in self.subject_ids):
            raise RunContractError("RUN_SCOPE_SUBJECTS_REQUIRED")
        if len(set(self.subject_ids)) != len(self.subject_ids):
            raise RunContractError("RUN_SCOPE_SUBJECTS_MUST_BE_UNIQUE")


@dataclass(frozen=True, slots=True)
class RunReplay:
    """Immutable replay projection plus the contract state machine."""

    run: DurableExperienceRun
    snapshot: RunSnapshot
    events: tuple[RunEvent, ...]
    checkpoints: tuple[RunCheckpoint, ...]


_FORBIDDEN_FACT_KEYS = frozenset(
    {
        "family_score",
        "family_rank",
        "ranking",
        "authoritative_fact",
        "canonical_state",
    }
)
_INLINE_MEDIA_RE = re.compile(r"^(?:data:|data%3a)", re.IGNORECASE)
_DRAFT_STATUS_KEYS = frozenset({"status", "draft_status"})


def _jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return str(value)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return json.loads(json.dumps(value, default=str))


def _fingerprint_event(event: RunEvent) -> str:
    body = {
        "event_id": event.event_id,
        "run_id": event.run_id,
        "event_type": event.event_type.value,
        "target_state": event.target_state.value,
        "payload": _jsonable(event.payload),
        "idempotency_key": event.idempotency_key,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)


def _fingerprint_checkpoint(checkpoint: RunCheckpoint) -> str:
    body = {
        "checkpoint_id": checkpoint.checkpoint_id,
        "run_id": checkpoint.run_id,
        "event_sequence": checkpoint.event_sequence,
        "state": checkpoint.state.value,
        "payload": _jsonable(checkpoint.payload),
        "artifact_refs": list(checkpoint.artifact_refs),
        "draft_payload": _jsonable(checkpoint.draft_payload),
        "status": checkpoint.status,
    }
    return json.dumps(body, sort_keys=True, separators=(",", ":"), default=str)


def _assert_safe_mapping(value: object, *, path: str) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if isinstance(key, str) and key.lower() in _FORBIDDEN_FACT_KEYS:
                raise RunContractError(f"{path}.{key} cannot become a business fact")
            _assert_safe_mapping(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_safe_mapping(item, path=f"{path}[{index}]")
    elif isinstance(value, bytes):
        raise RunContractError(f"{path} cannot contain raw bytes")


def _assert_media_refs(checkpoint: RunCheckpoint) -> None:
    for reference in checkpoint.artifact_refs:
        if not reference or len(reference) > 2_048:
            raise RunContractError("MEDIA_REFERENCE_INVALID")
        if _INLINE_MEDIA_RE.match(reference) or "base64" in reference.lower():
            raise RunContractError("MEDIA_REFERENCE_MUST_NOT_BE_INLINE")
        if any(character.isspace() for character in reference):
            raise RunContractError("MEDIA_REFERENCE_INVALID")


def _assert_draft_status(value: object, *, path: str) -> None:
    """Prevent a persisted model artifact from masquerading as approved state."""

    if isinstance(value, Mapping):
        for key, item in value.items():
            if (
                isinstance(key, str)
                and key.lower() in _DRAFT_STATUS_KEYS
                and item != "DRAFT"
            ):
                raise RunContractError("RUN_DRAFT_STATUS_MUST_REMAIN_DRAFT")
            _assert_draft_status(item, path=f"{path}.{key}")
    elif isinstance(value, (list, tuple)):
        for index, item in enumerate(value):
            _assert_draft_status(item, path=f"{path}[{index}]")


def _normalise_datetime(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


class SqlAlchemyExperienceRunStore:
    """Async save/load adapter for the AI-runtime run ledger."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, run: DurableExperienceRun) -> RunSnapshot:
        """Append a run state to storage, refusing replay conflicts.

        Existing rows must be a prefix of the incoming append-only log.  A
        stale or differently scoped run cannot overwrite newer execution state.
        """

        self._assert_run_safe(run)
        tenant_id = run.tenant_id
        row = await self._session.get(
            ExperienceRunRow, {"tenant_id": tenant_id, "run_id": run.run_id}
        )
        if row is None:
            row = ExperienceRunRow(
                tenant_id=tenant_id,
                run_id=run.run_id,
                family_id=run.family_id,
                subject_ids=list(run.subject_ids),
                request_ref=run.snapshot.request_ref,
                state=run.state.value,
                version=0,
                latest_checkpoint_id=None,
                status="DRAFT",
            )
            self._session.add(row)
            await self._session.flush()
        else:
            self._assert_row_scope(row, run.family_id, run.subject_ids)
            if row.request_ref != run.snapshot.request_ref:
                raise RunContractError("RUN_REQUEST_REF_CONFLICT")

        existing_events = await self._event_rows(tenant_id, run.run_id)
        if len(existing_events) > len(run.events):
            raise RunContractError("RUN_REPLAY_STALE_VERSION")
        for sequence, event in enumerate(run.events, start=1):
            if sequence <= len(existing_events):
                self._assert_event_row_matches(existing_events[sequence - 1], event, sequence)
                continue
            event_row = ExperienceRunEventRow(
                tenant_id=tenant_id,
                run_id=run.run_id,
                event_id=event.event_id,
                event_sequence=sequence,
                event_type=event.event_type.value,
                target_state=event.target_state.value,
                payload=_jsonable(event.payload),
                idempotency_key=event.idempotency_key,
                occurred_at=_normalise_datetime(event.occurred_at),
            )
            self._session.add(event_row)
            await self._session.flush()
            existing_events.append(event_row)

        existing_checkpoints = await self._checkpoint_rows(tenant_id, run.run_id)
        known_checkpoints = {item.checkpoint_id: item for item in existing_checkpoints}
        for checkpoint in run.checkpoints:
            existing = known_checkpoints.get(checkpoint.checkpoint_id)
            if existing is not None:
                self._assert_checkpoint_row_matches(existing, checkpoint)
                continue
            row_checkpoint = ExperienceRunCheckpointRow(
                tenant_id=tenant_id,
                run_id=run.run_id,
                checkpoint_id=checkpoint.checkpoint_id,
                event_sequence=checkpoint.event_sequence,
                state=checkpoint.state.value,
                payload=_jsonable(checkpoint.payload),
                artifact_refs=list(checkpoint.artifact_refs),
                draft_payload=(
                    _jsonable(checkpoint.draft_payload)
                    if checkpoint.draft_payload is not None
                    else None
                ),
                created_at=_normalise_datetime(checkpoint.created_at),
                status=checkpoint.status,
            )
            self._session.add(row_checkpoint)
            await self._session.flush()
            known_checkpoints[checkpoint.checkpoint_id] = row_checkpoint

        snapshot = run.snapshot
        row.family_id = run.family_id
        row.subject_ids = list(run.subject_ids)
        row.request_ref = snapshot.request_ref
        row.state = snapshot.state.value
        row.version = snapshot.version
        row.latest_checkpoint_id = snapshot.latest_checkpoint_id
        row.status = snapshot.status
        await self._session.flush()
        return snapshot

    async def load(self, *, scope: RunScope, run_id: str) -> DurableExperienceRun:
        """Load a scoped state machine; context-rich replay is via ``replay``."""

        return (await self.replay(scope=scope, run_id=run_id)).run

    async def replay(self, *, scope: RunScope, run_id: str) -> RunReplay:
        """Read and replay the append-only ledger without writing domain state."""

        row = await self._session.get(
            ExperienceRunRow, {"tenant_id": scope.tenant_id, "run_id": run_id}
        )
        if row is None:
            raise RunContractError("RUN_NOT_FOUND")
        self._assert_row_scope(row, scope.family_id, scope.subject_ids)
        event_rows = await self._event_rows(scope.tenant_id, run_id)
        checkpoint_rows = await self._checkpoint_rows(scope.tenant_id, run_id)
        events = tuple(self._event_from_row(item) for item in event_rows)
        checkpoints = tuple(self._checkpoint_from_row(item) for item in checkpoint_rows)
        run = self._rebuild_run(row, events, checkpoints)
        snapshot = run.replay()
        if (
            snapshot.state.value != row.state
            or snapshot.version != row.version
            or snapshot.latest_checkpoint_id != row.latest_checkpoint_id
            or snapshot.status != row.status
        ):
            raise RunContractError("CORRUPT_RUN_PERSISTENCE")
        return RunReplay(
            run=run,
            snapshot=snapshot,
            events=run.events,
            checkpoints=run.checkpoints,
        )

    async def _event_rows(self, tenant_id: str, run_id: str) -> list[ExperienceRunEventRow]:
        result = await self._session.execute(
            select(ExperienceRunEventRow)
            .where(
                ExperienceRunEventRow.tenant_id == tenant_id,
                ExperienceRunEventRow.run_id == run_id,
            )
            .order_by(ExperienceRunEventRow.event_sequence)
        )
        return list(result.scalars())

    async def _checkpoint_rows(
        self, tenant_id: str, run_id: str
    ) -> list[ExperienceRunCheckpointRow]:
        result = await self._session.execute(
            select(ExperienceRunCheckpointRow)
            .where(
                ExperienceRunCheckpointRow.tenant_id == tenant_id,
                ExperienceRunCheckpointRow.run_id == run_id,
            )
            .order_by(
                ExperienceRunCheckpointRow.event_sequence,
                ExperienceRunCheckpointRow.checkpoint_id,
            )
        )
        return list(result.scalars())

    @staticmethod
    def _assert_run_safe(run: DurableExperienceRun) -> None:
        for event in run.events:
            _assert_safe_mapping(event.payload, path=f"event:{event.event_id}.payload")
        for checkpoint in run.checkpoints:
            if checkpoint.status != "DRAFT":
                raise RunContractError("RUN_CHECKPOINT_MUST_REMAIN_DRAFT")
            _assert_safe_mapping(checkpoint.payload, path=f"checkpoint:{checkpoint.checkpoint_id}")
            if checkpoint.draft_payload is not None:
                _assert_safe_mapping(
                    checkpoint.draft_payload,
                    path=f"checkpoint:{checkpoint.checkpoint_id}.draft_payload",
                )
            _assert_draft_status(checkpoint.payload, path=f"checkpoint:{checkpoint.checkpoint_id}")
            if checkpoint.draft_payload is not None:
                _assert_draft_status(
                    checkpoint.draft_payload,
                    path=f"checkpoint:{checkpoint.checkpoint_id}.draft_payload",
                )
            _assert_media_refs(checkpoint)

    @staticmethod
    def _assert_row_scope(
        row: ExperienceRunRow, family_id: str, subject_ids: tuple[str, ...]
    ) -> None:
        if row.family_id != family_id or tuple(row.subject_ids) != tuple(subject_ids):
            raise RunContractError("RUN_SCOPE_MISMATCH")

    @staticmethod
    def _assert_event_row_matches(
        row: ExperienceRunEventRow, event: RunEvent, sequence: int
    ) -> None:
        if row.event_sequence != sequence:
            raise RunContractError("RUN_EVENT_SEQUENCE_CONFLICT")
        if row.event_id != event.event_id:
            raise RunContractError("RUN_EVENT_ID_CONFLICT")
        persisted = RunEvent(
            event_id=row.event_id,
            run_id=row.run_id,
            event_type=RunEventType(row.event_type),
            target_state=RunState(row.target_state),
            payload=row.payload,
            idempotency_key=row.idempotency_key,
            occurred_at=_normalise_datetime(row.occurred_at),
        )
        if _fingerprint_event(persisted) != _fingerprint_event(event):
            raise RunContractError("IDEMPOTENCY_REPLAY_MISMATCH")

    @staticmethod
    def _assert_checkpoint_row_matches(
        row: ExperienceRunCheckpointRow, checkpoint: RunCheckpoint
    ) -> None:
        persisted = RunCheckpoint(
            checkpoint_id=row.checkpoint_id,
            run_id=row.run_id,
            event_sequence=row.event_sequence,
            state=RunState(row.state),
            payload=row.payload,
            artifact_refs=tuple(row.artifact_refs),
            draft_payload=row.draft_payload,
            created_at=_normalise_datetime(row.created_at),
            status=row.status,  # type: ignore[arg-type]
        )
        if _fingerprint_checkpoint(persisted) != _fingerprint_checkpoint(checkpoint):
            raise RunContractError("CHECKPOINT_REPLAY_MISMATCH")

    @staticmethod
    def _event_from_row(row: ExperienceRunEventRow) -> RunEvent:
        try:
            event_type = RunEventType(row.event_type)
            target_state = RunState(row.target_state)
        except ValueError as exc:
            raise RunContractError("CORRUPT_RUN_EVENT") from exc
        return RunEvent(
            event_id=row.event_id,
            run_id=row.run_id,
            event_type=event_type,
            target_state=target_state,
            payload=row.payload,
            idempotency_key=row.idempotency_key,
            occurred_at=_normalise_datetime(row.occurred_at),
        )

    @staticmethod
    def _checkpoint_from_row(row: ExperienceRunCheckpointRow) -> RunCheckpoint:
        try:
            state = RunState(row.state)
        except ValueError as exc:
            raise RunContractError("CORRUPT_RUN_CHECKPOINT") from exc
        if row.status != "DRAFT":
            raise RunContractError("CORRUPT_RUN_CHECKPOINT_STATUS")
        return RunCheckpoint(
            checkpoint_id=row.checkpoint_id,
            run_id=row.run_id,
            event_sequence=row.event_sequence,
            state=state,
            payload=row.payload,
            artifact_refs=tuple(row.artifact_refs),
            draft_payload=row.draft_payload,
            created_at=_normalise_datetime(row.created_at),
            status="DRAFT",
        )

    @staticmethod
    def _rebuild_run(
        row: ExperienceRunRow,
        events: tuple[RunEvent, ...],
        checkpoints: tuple[RunCheckpoint, ...],
    ) -> DurableExperienceRun:
        run = DurableExperienceRun(
            run_id=row.run_id,
            tenant_id=row.tenant_id,
            family_id=row.family_id,
            subject_ids=tuple(row.subject_ids),
            request_ref=row.request_ref,
        )
        checkpoints_by_id = {item.checkpoint_id: item for item in checkpoints}
        seen_checkpoints: set[str] = set()
        for event in events:
            if event.event_type is not RunEventType.CHECKPOINTED:
                run.append(event)
                continue
            checkpoint_id = event.payload.get("checkpoint_id")
            if not isinstance(checkpoint_id, str) or checkpoint_id != event.event_id:
                raise RunContractError("CORRUPT_RUN_CHECKPOINT_EVENT")
            checkpoint = checkpoints_by_id.get(checkpoint_id)
            if checkpoint is None:
                raise RunContractError("CORRUPT_RUN_CHECKPOINT_MISSING")
            key = event.idempotency_key
            prefix = "checkpoint-event:"
            if key and key.startswith(prefix):
                key = key[len(prefix) :]
            run.checkpoint(
                checkpoint_id=checkpoint.checkpoint_id,
                payload=dict(checkpoint.payload),
                artifact_refs=checkpoint.artifact_refs,
                draft_payload=(
                    dict(checkpoint.draft_payload) if checkpoint.draft_payload is not None else None
                ),
                idempotency_key=key,
            )
            # ``checkpoint`` intentionally creates a fresh marker; replace it
            # with the persisted immutable values so replay remains lossless.
            run._events[-1] = event  # type: ignore[attr-defined]
            run._checkpoints[-1] = checkpoint  # type: ignore[attr-defined]
            seen_checkpoints.add(checkpoint_id)
        if seen_checkpoints != set(checkpoints_by_id):
            raise RunContractError("CORRUPT_RUN_CHECKPOINT_ORPHAN")
        return run


__all__ = [
    "ExperienceRunCheckpointRow",
    "ExperienceRunEventRow",
    "ExperienceRunPersistenceBase",
    "ExperienceRunRow",
    "RunReplay",
    "RunScope",
    "SqlAlchemyExperienceRunStore",
]
