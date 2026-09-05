"""Signed, append-only controls for exact atomic ReleaseSet transitions."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from sqlalchemy import CheckConstraint, DateTime, Index, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.evaluation.release_control import ReleaseSignatureVerifier

from .release_set import FamilyExperienceReleaseSet

ReleaseSetControlKind = Literal["APPLY", "ROLLBACK"]


class ReleaseSetControlError(ValueError):
    """A deployment control is unsigned, inconsistent, or replay-conflicting."""


class ReleaseSetControlBase(DeclarativeBase):
    """Metadata boundary for exact ReleaseSet controls."""


class ReleaseSetControlRow(ReleaseSetControlBase):
    __tablename__ = "ai_family_experience_release_set_controls"
    __table_args__ = (
        CheckConstraint("kind IN ('APPLY', 'ROLLBACK')", name="ck_ai_release_set_control_kind"),
        CheckConstraint(
            "(kind = 'APPLY' AND target_release_set_id IS NULL) OR "
            "(kind = 'ROLLBACK' AND target_release_set_id IS NOT NULL "
            "AND target_release_set_id <> source_release_set_id)",
            name="ck_ai_release_set_control_target",
        ),
        Index("uq_ai_release_set_control_idempotency", "idempotency_key", unique=True),
    )

    control_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    rollout_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    source_release_set_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_release_set_id: Mapped[str | None] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    use_case: Mapped[str] = mapped_column(String(256), nullable=False)
    data_class: Mapped[str] = mapped_column(String(64), nullable=False)
    runtime_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_effective_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(256), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    signature_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class ReleaseSetControlEvent:
    control_id: str
    idempotency_key: str
    kind: ReleaseSetControlKind
    phase: str
    rollout_percent: int
    source_release_set_id: str
    target_release_set_id: str | None
    environment: str
    use_case: str
    data_class: str
    runtime_config_digest: str
    expected_effective_sequence: int
    actor_id: str
    reason: str
    signature_ref: str
    signature_algorithm: str
    created_at: datetime

    def __post_init__(self) -> None:
        required = (
            self.control_id,
            self.idempotency_key,
            self.source_release_set_id,
            self.environment,
            self.use_case,
            self.data_class,
            self.runtime_config_digest,
            self.actor_id,
            self.reason,
            self.signature_ref,
            self.signature_algorithm,
        )
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise ReleaseSetControlError("RELEASE_SET_CONTROL_FIELDS_REQUIRED")
        if self.actor_id.startswith("ai:"):
            raise ReleaseSetControlError("AI_RELEASE_SET_CONTROLLER_NOT_ALLOWED")
        if self.expected_effective_sequence < 0:
            raise ReleaseSetControlError("RELEASE_SET_CONTROL_SEQUENCE_INVALID")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ReleaseSetControlError("RELEASE_SET_CONTROL_TIME_MUST_BE_AWARE")
        valid_target = (
            self.kind == "APPLY" and self.target_release_set_id is None
        ) or (
            self.kind == "ROLLBACK"
            and isinstance(self.target_release_set_id, str)
            and bool(self.target_release_set_id.strip())
            and self.target_release_set_id != self.source_release_set_id
        )
        if not valid_target:
            raise ReleaseSetControlError("RELEASE_SET_CONTROL_TARGET_INVALID")
        valid_rollout = (
            self.kind == "APPLY"
            and self.phase == "CANARY"
            and 1 <= self.rollout_percent <= 99
        ) or (
            self.kind == "APPLY"
            and self.phase == "ACTIVE"
            and self.rollout_percent == 100
        ) or (
            self.kind == "ROLLBACK"
            and self.phase == "ROLLED_BACK"
            and self.rollout_percent == 0
        )
        if not valid_rollout:
            raise ReleaseSetControlError("RELEASE_SET_CONTROL_PHASE_INVALID")


class ReleaseSetControlReader(Protocol):
    durability_mode: str

    async def get(self, control_id: str) -> ReleaseSetControlEvent | None: ...


class InMemoryReleaseSetControlStore:
    durability_mode = "IN_MEMORY"

    def __init__(
        self,
        *,
        signature_verifier: ReleaseSignatureVerifier,
        clock=None,
    ) -> None:
        self._verifier = signature_verifier
        self._clock = clock or (lambda: datetime.now(UTC))
        self._events: dict[str, ReleaseSetControlEvent] = {}
        self._by_key: dict[str, str] = {}

    async def authorize(
        self,
        source: FamilyExperienceReleaseSet,
        *,
        kind: ReleaseSetControlKind,
        phase: str,
        rollout_percent: int,
        target: FamilyExperienceReleaseSet | None,
        expected_effective_sequence: int,
        actor_id: str,
        idempotency_key: str,
        reason: str,
        signature: str,
        signature_algorithm: str,
    ) -> ReleaseSetControlEvent:
        event = _authorize(
            source,
            kind=kind,
            phase=phase,
            rollout_percent=rollout_percent,
            target=target,
            expected_effective_sequence=expected_effective_sequence,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            reason=reason,
            signature=signature,
            signature_algorithm=signature_algorithm,
            signature_verifier=self._verifier,
            created_at=self._clock(),
        )
        existing_id = self._by_key.get(idempotency_key)
        if existing_id is not None:
            existing = self._events[existing_id]
            if existing != event:
                raise ReleaseSetControlError("RELEASE_SET_CONTROL_CONFLICT")
            return existing
        self._events[event.control_id] = event
        self._by_key[idempotency_key] = event.control_id
        return event

    async def get(self, control_id: str) -> ReleaseSetControlEvent | None:
        return self._events.get(control_id)


class SqlAlchemyReleaseSetControlStore:
    durability_mode = "DURABLE"

    def __init__(
        self,
        session: AsyncSession,
        *,
        signature_verifier: ReleaseSignatureVerifier,
        clock=None,
    ) -> None:
        self._session = session
        self._verifier = signature_verifier
        self._clock = clock or (lambda: datetime.now(UTC))

    async def authorize(
        self,
        source: FamilyExperienceReleaseSet,
        **values,
    ) -> ReleaseSetControlEvent:
        event = _authorize(
            source,
            signature_verifier=self._verifier,
            created_at=self._clock(),
            **values,
        )
        existing = await self._session.scalar(
            select(ReleaseSetControlRow).where(
                ReleaseSetControlRow.idempotency_key == event.idempotency_key
            )
        )
        if existing is not None:
            stored = _stored(existing)
            if stored != event:
                raise ReleaseSetControlError("RELEASE_SET_CONTROL_CONFLICT")
            return stored
        self._session.add(_row(event))
        await self._session.flush()
        return event

    async def get(self, control_id: str) -> ReleaseSetControlEvent | None:
        row = await self._session.get(ReleaseSetControlRow, control_id)
        return None if row is None else _stored(row)


class SessionPerCallReleaseSetControlReader:
    durability_mode = "DURABLE"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        self._session_factory = session_factory

    async def get(self, control_id: str) -> ReleaseSetControlEvent | None:
        async with self._session_factory() as session:
            row = await session.get(ReleaseSetControlRow, control_id)
            return None if row is None else _stored(row)


def _authorize(
    source: FamilyExperienceReleaseSet,
    *,
    kind: ReleaseSetControlKind,
    phase: str,
    rollout_percent: int,
    target: FamilyExperienceReleaseSet | None,
    expected_effective_sequence: int,
    actor_id: str,
    idempotency_key: str,
    reason: str,
    signature: str,
    signature_algorithm: str,
    signature_verifier: ReleaseSignatureVerifier,
    created_at: datetime,
) -> ReleaseSetControlEvent:
    if not isinstance(source, FamilyExperienceReleaseSet):
        raise ReleaseSetControlError("RELEASE_SET_CONTROL_SOURCE_REQUIRED")
    if kind == "ROLLBACK" and not isinstance(target, FamilyExperienceReleaseSet):
        raise ReleaseSetControlError("RELEASE_SET_CONTROL_TARGET_REQUIRED")
    if kind == "APPLY" and target is not None:
        raise ReleaseSetControlError("RELEASE_SET_CONTROL_TARGET_INVALID")
    effective = target if kind == "ROLLBACK" else source
    if effective is None:  # pragma: no cover - narrowed above
        raise ReleaseSetControlError("RELEASE_SET_CONTROL_TARGET_REQUIRED")
    if target is not None and _scope(source) != _scope(target):
        raise ReleaseSetControlError("RELEASE_SET_CONTROL_SCOPE_MISMATCH")
    required = (actor_id, idempotency_key, reason, signature, signature_algorithm)
    if not all(isinstance(value, str) and value.strip() for value in required):
        raise ReleaseSetControlError("RELEASE_SET_CONTROL_AUTH_REQUIRED")
    if actor_id.startswith("ai:"):
        raise ReleaseSetControlError("AI_RELEASE_SET_CONTROLLER_NOT_ALLOWED")
    payload = _payload(
        source,
        kind=kind,
        phase=phase,
        rollout_percent=rollout_percent,
        target=target,
        expected_effective_sequence=expected_effective_sequence,
        actor_id=actor_id,
        idempotency_key=idempotency_key,
        reason=reason,
        signature_algorithm=signature_algorithm,
    )
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    if not signature_verifier.verify(payload=encoded, signature=signature, actor_id=actor_id):
        raise ReleaseSetControlError("RELEASE_SET_CONTROL_SIGNATURE_INVALID")
    signature_ref = hashlib.sha256(signature.encode()).hexdigest()
    control_id = hashlib.sha256(encoded + signature_ref.encode()).hexdigest()
    return ReleaseSetControlEvent(
        control_id=control_id,
        idempotency_key=idempotency_key,
        kind=kind,
        phase=phase,
        rollout_percent=rollout_percent,
        source_release_set_id=source.release_set_id,
        target_release_set_id=target.release_set_id if target is not None else None,
        environment=source.environment,
        use_case=source.use_case,
        data_class=source.data_class,
        runtime_config_digest=effective.runtime_config_digest,
        expected_effective_sequence=expected_effective_sequence,
        actor_id=actor_id,
        reason=reason,
        signature_ref=signature_ref,
        signature_algorithm=signature_algorithm,
        created_at=created_at,
    )


def _payload(source, **values) -> dict[str, object]:
    target = values["target"]
    kind = values["kind"]
    effective = target if kind == "ROLLBACK" else source
    return {
        "kind": kind,
        "phase": values["phase"],
        "rollout_percent": values["rollout_percent"],
        "source_release_set_id": source.release_set_id,
        "target_release_set_id": target.release_set_id if target is not None else None,
        "environment": source.environment,
        "use_case": source.use_case,
        "data_class": source.data_class,
        "runtime_config_digest": effective.runtime_config_digest,
        "expected_effective_sequence": values["expected_effective_sequence"],
        "actor_id": values["actor_id"],
        "idempotency_key": values["idempotency_key"],
        "reason": values["reason"],
        "signature_algorithm": values["signature_algorithm"],
    }


def _scope(value: FamilyExperienceReleaseSet) -> tuple[str, str, str]:
    return value.environment, value.use_case, value.data_class


def _row(value: ReleaseSetControlEvent) -> ReleaseSetControlRow:
    return ReleaseSetControlRow(**{
        name: getattr(value, name)
        for name in ReleaseSetControlEvent.__dataclass_fields__
    })


def _stored(row: ReleaseSetControlRow) -> ReleaseSetControlEvent:
    created_at = (
        row.created_at.replace(tzinfo=UTC)
        if row.created_at.tzinfo is None
        else row.created_at
    )
    return ReleaseSetControlEvent(
        control_id=row.control_id,
        idempotency_key=row.idempotency_key,
        kind=row.kind,  # type: ignore[arg-type]
        phase=row.phase,
        rollout_percent=row.rollout_percent,
        source_release_set_id=row.source_release_set_id,
        target_release_set_id=row.target_release_set_id,
        environment=row.environment,
        use_case=row.use_case,
        data_class=row.data_class,
        runtime_config_digest=row.runtime_config_digest,
        expected_effective_sequence=row.expected_effective_sequence,
        actor_id=row.actor_id,
        reason=row.reason,
        signature_ref=row.signature_ref,
        signature_algorithm=row.signature_algorithm,
        created_at=created_at,
    )


__all__ = [
    "InMemoryReleaseSetControlStore",
    "ReleaseSetControlBase",
    "ReleaseSetControlError",
    "ReleaseSetControlEvent",
    "ReleaseSetControlReader",
    "ReleaseSetControlRow",
    "SessionPerCallReleaseSetControlReader",
    "SqlAlchemyReleaseSetControlStore",
]
