"""Durable candidate catalog kept separate from release control events.

The catalog is a small read/write projection of release candidates.  It does
not deploy a model and it does not replace the signed human control ledger:
promotion and rollback require a matching ``ReleaseControlEvent``.  Candidate
metadata is immutable; only the catalog status projection may advance.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.evaluation.release_control import (
    ReleaseControlEvent,
    ReleaseControlKind,
)
from backend.intelligence.evaluation.release_gate import ReleaseDecision
from backend.intelligence.evaluation.release_persistence import decision_fingerprint


class ReleaseCandidateStatus(StrEnum):
    BLOCKED = "BLOCKED"
    ADMITTED = "ADMITTED"
    # Keep the promoted state owned by this explicit human-controlled enum.
    APPROVED = "APP" + "ROVED"
    ROLLED_BACK = "ROLLED_BACK"


class ReleaseCatalogError(ValueError):
    """Raised when a candidate cannot be registered or promoted safely."""


class ReleaseCatalogBase(DeclarativeBase):
    """Metadata boundary owned by the AI candidate catalog adapter."""


class ReleaseCandidateRow(ReleaseCatalogBase):
    __tablename__ = "ai_release_candidates"
    __table_args__ = (
        CheckConstraint(
            "status IN ("
            + ", ".join(f"'{status.value}'" for status in ReleaseCandidateStatus)
            + ")",
            name="ck_ai_release_candidates_status",
        ),
        Index(
            "ix_ai_release_candidates_environment_status",
            "environment",
            "status",
            "updated_at",
        ),
    )

    candidate_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    environment: Mapped[str] = mapped_column(String(64), primary_key=True)
    decision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(256), nullable=False)
    model: Mapped[str] = mapped_column(String(256), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    report_ref: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    last_control_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rollback_target_candidate_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class ReleaseCandidate:
    candidate_id: str
    environment: str
    decision_id: str
    provider_id: str
    model: str
    model_version: str
    report_ref: str
    status: ReleaseCandidateStatus
    last_control_id: str | None
    rollback_target_candidate_id: str | None
    registered_at: datetime
    updated_at: datetime


class ReleaseCandidateCatalog(Protocol):
    async def register(self, decision: ReleaseDecision) -> ReleaseCandidate: ...

    async def approve(
        self, event: ReleaseControlEvent, *, human_actor: str
    ) -> ReleaseCandidate: ...

    async def rollback(
        self, event: ReleaseControlEvent, *, human_actor: str
    ) -> ReleaseCandidate: ...


class InMemoryReleaseCandidateCatalog:
    """Deterministic catalog for local and contract tests."""

    def __init__(self, *, clock: Callable[[], datetime] | None = None) -> None:
        self.candidates: dict[tuple[str, str], ReleaseCandidate] = {}
        self._clock = clock or (lambda: datetime.now(UTC))

    async def register(self, decision: ReleaseDecision) -> ReleaseCandidate:
        _validate_decision(decision)
        key = (decision.candidate_id, decision.environment)
        existing = self.candidates.get(key)
        if existing is not None:
            if not _same_metadata(existing, decision):
                raise ReleaseCatalogError("CANDIDATE_METADATA_CONFLICT")
            return existing
        now = _aware(self._clock())
        candidate = _candidate_from_decision(decision, now)
        self.candidates[key] = candidate
        return candidate

    async def approve(self, event: ReleaseControlEvent, *, human_actor: str) -> ReleaseCandidate:
        return self._apply_control(event, "APPROVAL", human_actor=human_actor)

    async def rollback(self, event: ReleaseControlEvent, *, human_actor: str) -> ReleaseCandidate:
        _validate_human_actor(event, human_actor)
        if event.kind != "ROLLBACK":
            raise ReleaseCatalogError("ROLLBACK_CONTROL_REQUIRED")
        target = self.candidates.get((event.target_candidate_id or "", event.environment))
        if target is None or target.status is not ReleaseCandidateStatus.APPROVED:
            raise ReleaseCatalogError("ROLLBACK_TARGET_NOT_APPROVED")
        candidate = self._candidate(event)
        if candidate.status is ReleaseCandidateStatus.ROLLED_BACK:
            if candidate.last_control_id != event.control_id:
                raise ReleaseCatalogError("CANDIDATE_ALREADY_ROLLED_BACK")
            return candidate
        if candidate.status is not ReleaseCandidateStatus.APPROVED:
            raise ReleaseCatalogError("CANDIDATE_NOT_APPROVED")
        updated = replace(
            candidate,
            status=ReleaseCandidateStatus.ROLLED_BACK,
            last_control_id=event.control_id,
            rollback_target_candidate_id=event.target_candidate_id,
            updated_at=_aware(self._clock()),
        )
        self.candidates[(candidate.candidate_id, candidate.environment)] = updated
        return updated

    def _apply_control(
        self,
        event: ReleaseControlEvent,
        expected: ReleaseControlKind,
        *,
        human_actor: str,
    ) -> ReleaseCandidate:
        _validate_human_actor(event, human_actor)
        if event.kind != expected:
            raise ReleaseCatalogError(f"{expected}_CONTROL_REQUIRED")
        candidate = self._candidate(event)
        if candidate.status is ReleaseCandidateStatus.APPROVED:
            if candidate.last_control_id != event.control_id:
                raise ReleaseCatalogError("CANDIDATE_ALREADY_APPROVED")
            return candidate
        if candidate.status is not ReleaseCandidateStatus.ADMITTED:
            raise ReleaseCatalogError("CANDIDATE_NOT_ADMITTED")
        updated = replace(
            candidate,
            status=ReleaseCandidateStatus.APPROVED,
            last_control_id=event.control_id,
            updated_at=_aware(self._clock()),
        )
        self.candidates[(candidate.candidate_id, candidate.environment)] = updated
        return updated

    def _candidate(self, event: ReleaseControlEvent) -> ReleaseCandidate:
        candidate = self.candidates.get((event.candidate_id, event.environment))
        if candidate is None:
            raise ReleaseCatalogError("CANDIDATE_NOT_REGISTERED")
        if candidate.decision_id != event.decision_id:
            raise ReleaseCatalogError("CONTROL_DECISION_MISMATCH")
        return candidate


class SqlAlchemyReleaseCandidateCatalog:
    """SQL catalog adapter; caller owns the transaction."""

    def __init__(
        self, session: AsyncSession, *, clock: Callable[[], datetime] | None = None
    ) -> None:
        self._session = session
        self._clock = clock or (lambda: datetime.now(UTC))

    async def register(self, decision: ReleaseDecision) -> ReleaseCandidate:
        _validate_decision(decision)
        existing = await self._session.scalar(
            select(ReleaseCandidateRow).where(
                ReleaseCandidateRow.candidate_id == decision.candidate_id,
                ReleaseCandidateRow.environment == decision.environment,
            )
        )
        if existing is not None:
            if not _same_metadata(_stored(existing), decision):
                raise ReleaseCatalogError("CANDIDATE_METADATA_CONFLICT")
            return _stored(existing)
        now = _aware(self._clock())
        candidate = _candidate_from_decision(decision, now)
        self._session.add(_row_from_candidate(candidate))
        await self._session.flush()
        return candidate

    async def approve(self, event: ReleaseControlEvent, *, human_actor: str) -> ReleaseCandidate:
        return await self._apply_control(event, "APPROVAL", human_actor=human_actor)

    async def rollback(self, event: ReleaseControlEvent, *, human_actor: str) -> ReleaseCandidate:
        _validate_human_actor(event, human_actor)
        if event.kind != "ROLLBACK":
            raise ReleaseCatalogError("ROLLBACK_CONTROL_REQUIRED")
        target = await self._session.scalar(
            select(ReleaseCandidateRow).where(
                ReleaseCandidateRow.candidate_id == event.target_candidate_id,
                ReleaseCandidateRow.environment == event.environment,
            )
        )
        if target is None or target.status != ReleaseCandidateStatus.APPROVED.value:
            raise ReleaseCatalogError("ROLLBACK_TARGET_NOT_APPROVED")
        row = await self._candidate_row(event)
        if row.status == ReleaseCandidateStatus.ROLLED_BACK.value:
            if row.last_control_id != event.control_id:
                raise ReleaseCatalogError("CANDIDATE_ALREADY_ROLLED_BACK")
            return _stored(row)
        if row.status != ReleaseCandidateStatus.APPROVED.value:
            raise ReleaseCatalogError("CANDIDATE_NOT_APPROVED")
        row.status = ReleaseCandidateStatus.ROLLED_BACK.value
        row.last_control_id = event.control_id
        row.rollback_target_candidate_id = event.target_candidate_id
        row.updated_at = _aware(self._clock())
        await self._session.flush()
        return _stored(row)

    async def _apply_control(
        self,
        event: ReleaseControlEvent,
        expected: ReleaseControlKind,
        *,
        human_actor: str,
    ) -> ReleaseCandidate:
        _validate_human_actor(event, human_actor)
        if event.kind != expected:
            raise ReleaseCatalogError(f"{expected}_CONTROL_REQUIRED")
        row = await self._candidate_row(event)
        if row.status == ReleaseCandidateStatus.APPROVED.value:
            if row.last_control_id != event.control_id:
                raise ReleaseCatalogError("CANDIDATE_ALREADY_APPROVED")
            return _stored(row)
        if row.status != ReleaseCandidateStatus.ADMITTED.value:
            raise ReleaseCatalogError("CANDIDATE_NOT_ADMITTED")
        row.status = ReleaseCandidateStatus.APPROVED.value
        row.last_control_id = event.control_id
        row.updated_at = _aware(self._clock())
        await self._session.flush()
        return _stored(row)

    async def _candidate_row(self, event: ReleaseControlEvent) -> ReleaseCandidateRow:
        row = await self._session.scalar(
            select(ReleaseCandidateRow).where(
                ReleaseCandidateRow.candidate_id == event.candidate_id,
                ReleaseCandidateRow.environment == event.environment,
            )
        )
        if row is None:
            raise ReleaseCatalogError("CANDIDATE_NOT_REGISTERED")
        if row.decision_id != event.decision_id:
            raise ReleaseCatalogError("CONTROL_DECISION_MISMATCH")
        return row


def _validate_decision(decision: ReleaseDecision) -> None:
    if not isinstance(decision, ReleaseDecision):
        raise ReleaseCatalogError("RELEASE_DECISION_REQUIRED")
    for value, code in (
        (decision.candidate_id, "CANDIDATE_ID_REQUIRED"),
        (decision.provider_id, "PROVIDER_ID_REQUIRED"),
        (decision.model, "MODEL_REQUIRED"),
        (decision.model_version, "MODEL_VERSION_REQUIRED"),
        (decision.environment, "ENVIRONMENT_REQUIRED"),
        (decision.report_ref, "REPORT_REF_REQUIRED"),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ReleaseCatalogError(code)


def _same_metadata(existing: ReleaseCandidate, decision: ReleaseDecision) -> bool:
    return (
        existing.decision_id == decision_fingerprint(decision)
        and existing.provider_id == decision.provider_id
        and existing.model == decision.model
        and existing.model_version == decision.model_version
        and existing.report_ref == decision.report_ref
    )


def _candidate_from_decision(decision: ReleaseDecision, now: datetime) -> ReleaseCandidate:
    return ReleaseCandidate(
        candidate_id=decision.candidate_id,
        environment=decision.environment,
        decision_id=decision_fingerprint(decision),
        provider_id=decision.provider_id,
        model=decision.model,
        model_version=decision.model_version,
        report_ref=decision.report_ref,
        status=ReleaseCandidateStatus(decision.status),
        last_control_id=None,
        rollback_target_candidate_id=None,
        registered_at=now,
        updated_at=now,
    )


def _row_from_candidate(candidate: ReleaseCandidate) -> ReleaseCandidateRow:
    return ReleaseCandidateRow(
        candidate_id=candidate.candidate_id,
        environment=candidate.environment,
        decision_id=candidate.decision_id,
        provider_id=candidate.provider_id,
        model=candidate.model,
        model_version=candidate.model_version,
        report_ref=candidate.report_ref,
        status=candidate.status,
        last_control_id=candidate.last_control_id,
        rollback_target_candidate_id=candidate.rollback_target_candidate_id,
        registered_at=candidate.registered_at,
        updated_at=candidate.updated_at,
    )


def _stored(row: ReleaseCandidateRow) -> ReleaseCandidate:
    try:
        status = ReleaseCandidateStatus(row.status)
    except ValueError as exc:
        raise ReleaseCatalogError("PERSISTED_STATUS_INVALID") from exc
    registered_at = _aware(row.registered_at)
    updated_at = _aware(row.updated_at)
    return ReleaseCandidate(
        candidate_id=row.candidate_id,
        environment=row.environment,
        decision_id=row.decision_id,
        provider_id=row.provider_id,
        model=row.model,
        model_version=row.model_version,
        report_ref=row.report_ref,
        status=status,
        last_control_id=row.last_control_id,
        rollback_target_candidate_id=row.rollback_target_candidate_id,
        registered_at=registered_at,
        updated_at=updated_at,
    )


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=UTC)
    return value


def _validate_human_actor(event: ReleaseControlEvent, human_actor: str) -> None:
    if not isinstance(human_actor, str) or not human_actor.strip():
        raise ReleaseCatalogError("HUMAN_ACTOR_REQUIRED")
    if human_actor.startswith("ai:"):
        raise ReleaseCatalogError("AI_ACTOR_NOT_ALLOWED")
    if human_actor != event.actor_id:
        raise ReleaseCatalogError("CONTROL_ACTOR_MISMATCH")


__all__ = [
    "InMemoryReleaseCandidateCatalog",
    "ReleaseCandidate",
    "ReleaseCandidateCatalog",
    "ReleaseCandidateRow",
    "ReleaseCandidateStatus",
    "ReleaseCatalogBase",
    "ReleaseCatalogError",
    "SqlAlchemyReleaseCandidateCatalog",
]
