"""Human approval and rollback controls for an admitted AI candidate.

The release gate answers whether a candidate satisfies evidence thresholds.  It
does not authorize deployment.  This module is the next, deliberately narrow,
control-plane boundary: an operator can approve an immutable gate decision and
can later record a rollback pointer.  Both operations are append-only,
idempotent, and have no deployment side effect.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol

from sqlalchemy import CheckConstraint, DateTime, Index, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.evaluation.release_gate import ReleaseDecision
from backend.intelligence.evaluation.release_persistence import decision_fingerprint

ReleaseControlKind = Literal["APPROVAL", "ROLLBACK"]


class ReleaseControlError(ValueError):
    """Raised when a release control request is unsafe or malformed."""


class ReleaseControlBase(DeclarativeBase):
    """Metadata boundary owned by the AI release control adapter."""


class ReleaseControlRow(ReleaseControlBase):
    """Append-only operator control event; no deployment state is stored."""

    __tablename__ = "ai_release_controls"
    __table_args__ = (
        CheckConstraint("kind IN ('APPROVAL', 'ROLLBACK')", name="ck_ai_release_controls_kind"),
        Index("uq_ai_release_controls_idempotency", "idempotency_key", unique=True),
        Index(
            "ix_ai_release_controls_candidate_environment",
            "candidate_id",
            "environment",
            "created_at",
        ),
    )

    control_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    decision_id: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_id: Mapped[str] = mapped_column(String(256), nullable=False)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(256), nullable=False)
    target_candidate_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    signature_ref: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_algorithm: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


@dataclass(frozen=True, slots=True)
class ReleaseControlEvent:
    """Portable event returned by either persistence implementation."""

    control_id: str
    kind: ReleaseControlKind
    idempotency_key: str
    decision_id: str
    candidate_id: str
    environment: str
    actor_id: str
    target_candidate_id: str | None
    reason: str
    signature_ref: str
    signature_algorithm: str
    created_at: datetime


class ReleaseControlStore(Protocol):
    async def approve(
        self,
        decision: ReleaseDecision,
        *,
        actor_id: str,
        idempotency_key: str,
        reason: str,
        signature: str,
        signature_algorithm: str = "external",
    ) -> ReleaseControlEvent: ...

    async def rollback(
        self,
        decision: ReleaseDecision,
        *,
        target_candidate_id: str,
        actor_id: str,
        idempotency_key: str,
        reason: str,
        signature: str,
        signature_algorithm: str,
    ) -> ReleaseControlEvent: ...


class ReleaseSignatureVerifier(Protocol):
    """External identity/security boundary; the AI runtime never owns keys."""

    def verify(self, *, payload: bytes, signature: str, actor_id: str) -> bool: ...


class InMemoryReleaseControlStore:
    """Deterministic store for local and contract tests."""

    def __init__(
        self,
        *,
        signature_verifier: ReleaseSignatureVerifier,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self.events: list[ReleaseControlEvent] = []
        self._signature_verifier = signature_verifier
        self._clock = clock or (lambda: datetime.now(UTC))

    async def approve(
        self,
        decision: ReleaseDecision,
        *,
        actor_id: str,
        idempotency_key: str,
        reason: str,
        signature: str,
        signature_algorithm: str = "external",
    ) -> ReleaseControlEvent:
        return self._append(
            "APPROVAL",
            decision,
            target_candidate_id=None,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            reason=reason,
            signature=signature,
            signature_algorithm=signature_algorithm,
        )

    async def rollback(
        self,
        decision: ReleaseDecision,
        *,
        target_candidate_id: str,
        actor_id: str,
        idempotency_key: str,
        reason: str,
        signature: str,
        signature_algorithm: str = "external",
    ) -> ReleaseControlEvent:
        return self._append(
            "ROLLBACK",
            decision,
            target_candidate_id=target_candidate_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            reason=reason,
            signature=signature,
            signature_algorithm=signature_algorithm,
        )

    def _append(
        self,
        kind: ReleaseControlKind,
        decision: ReleaseDecision,
        *,
        target_candidate_id: str | None,
        actor_id: str,
        idempotency_key: str,
        reason: str,
        signature: str,
        signature_algorithm: str,
    ) -> ReleaseControlEvent:
        _validate_request(
            decision,
            actor_id,
            idempotency_key,
            reason,
            kind,
            target_candidate_id,
            signature,
            signature_algorithm,
        )
        if not self._signature_verifier.verify(
            payload=_signature_payload(decision, actor_id, idempotency_key, reason),
            signature=signature,
            actor_id=actor_id,
        ):
            raise ReleaseControlError("SIGNATURE_INVALID")
        if kind == "ROLLBACK" and not any(
            event.kind == "APPROVAL"
            and event.decision_id == decision_fingerprint(decision)
            and event.environment == decision.environment
            for event in self.events
        ):
            raise ReleaseControlError("ROLLBACK_REQUIRES_APPROVAL")
        for event in self.events:
            if event.idempotency_key == idempotency_key:
                if event != _event_preview(
                    kind,
                    decision,
                    actor_id,
                    idempotency_key,
                    reason,
                    target_candidate_id,
                    event.created_at,
                    event.signature_ref,
                    event.signature_algorithm,
                ):
                    raise ReleaseControlError("IDEMPOTENCY_KEY_CONFLICT")
                return event
        created_at = self._clock()
        _aware(created_at)
        event = _event_preview(
            kind,
            decision,
            actor_id,
            idempotency_key,
            reason,
            target_candidate_id,
            created_at,
            _signature_ref(signature),
            signature_algorithm,
        )
        self.events.append(event)
        return event


class SqlAlchemyReleaseControlStore:
    """SQL adapter; stages events and leaves transaction ownership to caller."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        signature_verifier: ReleaseSignatureVerifier,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._session = session
        self._signature_verifier = signature_verifier
        self._clock = clock or (lambda: datetime.now(UTC))

    async def approve(
        self,
        decision: ReleaseDecision,
        *,
        actor_id: str,
        idempotency_key: str,
        reason: str,
        signature: str,
        signature_algorithm: str = "external",
    ) -> ReleaseControlEvent:
        return await self._append(
            "APPROVAL",
            decision,
            target_candidate_id=None,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            reason=reason,
            signature=signature,
            signature_algorithm=signature_algorithm,
        )

    async def rollback(
        self,
        decision: ReleaseDecision,
        *,
        target_candidate_id: str,
        actor_id: str,
        idempotency_key: str,
        reason: str,
        signature: str,
        signature_algorithm: str = "external",
    ) -> ReleaseControlEvent:
        return await self._append(
            "ROLLBACK",
            decision,
            target_candidate_id=target_candidate_id,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            reason=reason,
            signature=signature,
            signature_algorithm=signature_algorithm,
        )

    async def _append(
        self,
        kind: ReleaseControlKind,
        decision: ReleaseDecision,
        *,
        target_candidate_id: str | None,
        actor_id: str,
        idempotency_key: str,
        reason: str,
        signature: str,
        signature_algorithm: str,
    ) -> ReleaseControlEvent:
        _validate_request(
            decision,
            actor_id,
            idempotency_key,
            reason,
            kind,
            target_candidate_id,
            signature,
            signature_algorithm,
        )
        if not self._signature_verifier.verify(
            payload=_signature_payload(decision, actor_id, idempotency_key, reason),
            signature=signature,
            actor_id=actor_id,
        ):
            raise ReleaseControlError("SIGNATURE_INVALID")
        if kind == "ROLLBACK":
            approved = await self._session.scalar(
                select(ReleaseControlRow).where(
                    ReleaseControlRow.kind == "APPROVAL",
                    ReleaseControlRow.decision_id == decision_fingerprint(decision),
                    ReleaseControlRow.environment == decision.environment,
                )
            )
            if approved is None:
                raise ReleaseControlError("ROLLBACK_REQUIRES_APPROVAL")
        existing = await self._session.scalar(
            select(ReleaseControlRow).where(ReleaseControlRow.idempotency_key == idempotency_key)
        )
        if existing is not None:
            event = _stored(existing)
            if event != _event_preview(
                kind,
                decision,
                actor_id,
                idempotency_key,
                reason,
                target_candidate_id,
                event.created_at,
                event.signature_ref,
                event.signature_algorithm,
            ):
                raise ReleaseControlError("IDEMPOTENCY_KEY_CONFLICT")
            return event
        created_at = self._clock()
        _aware(created_at)
        event = _event_preview(
            kind,
            decision,
            actor_id,
            idempotency_key,
            reason,
            target_candidate_id,
            created_at,
            _signature_ref(signature),
            signature_algorithm,
        )
        self._session.add(
            ReleaseControlRow(
                control_id=event.control_id,
                kind=event.kind,
                idempotency_key=event.idempotency_key,
                decision_id=event.decision_id,
                candidate_id=event.candidate_id,
                environment=event.environment,
                actor_id=event.actor_id,
                target_candidate_id=event.target_candidate_id,
                reason=event.reason,
                signature_ref=event.signature_ref,
                signature_algorithm=event.signature_algorithm,
                created_at=event.created_at,
            )
        )
        await self._session.flush()
        return event

    async def list_events(
        self, *, candidate_id: str | None = None, environment: str | None = None
    ) -> tuple[ReleaseControlEvent, ...]:
        statement = select(ReleaseControlRow).order_by(
            ReleaseControlRow.created_at, ReleaseControlRow.control_id
        )
        if candidate_id is not None:
            statement = statement.where(ReleaseControlRow.candidate_id == candidate_id)
        if environment is not None:
            statement = statement.where(ReleaseControlRow.environment == environment)
        result = await self._session.execute(statement)
        return tuple(_stored(row) for row in result.scalars())


def _event_preview(
    kind: ReleaseControlKind,
    decision: ReleaseDecision,
    actor_id: str,
    idempotency_key: str,
    reason: str,
    target_candidate_id: str | None,
    created_at: datetime,
    signature_ref: str,
    signature_algorithm: str,
) -> ReleaseControlEvent:
    decision_id = decision_fingerprint(decision)
    payload = {
        "kind": kind,
        "decision_id": decision_id,
        "candidate_id": decision.candidate_id,
        "environment": decision.environment,
        "actor_id": actor_id,
        "target_candidate_id": target_candidate_id,
        "reason": reason,
        "idempotency_key": idempotency_key,
        "signature_ref": signature_ref,
        "signature_algorithm": signature_algorithm,
    }
    control_id = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return ReleaseControlEvent(
        control_id,
        kind,
        idempotency_key,
        decision_id,
        decision.candidate_id,
        decision.environment,
        actor_id,
        target_candidate_id,
        reason,
        signature_ref,
        signature_algorithm,
        created_at,
    )


def _validate_request(
    decision: ReleaseDecision,
    actor_id: str,
    idempotency_key: str,
    reason: str,
    kind: ReleaseControlKind,
    target_candidate_id: str | None,
    signature: str,
    signature_algorithm: str,
) -> None:
    if not isinstance(decision, ReleaseDecision) or not decision.admitted:
        raise ReleaseControlError("RELEASE_DECISION_MUST_BE_ADMITTED")
    for value, code in (
        (actor_id, "ACTOR_ID_REQUIRED"),
        (idempotency_key, "IDEMPOTENCY_KEY_REQUIRED"),
        (reason, "REASON_REQUIRED"),
        (signature, "SIGNATURE_REQUIRED"),
        (signature_algorithm, "SIGNATURE_ALGORITHM_REQUIRED"),
    ):
        if not isinstance(value, str) or not value.strip():
            raise ReleaseControlError(code)
    if len(idempotency_key) > 256:
        raise ReleaseControlError("IDEMPOTENCY_KEY_TOO_LONG")
    if actor_id.startswith("ai:"):
        raise ReleaseControlError("AI_ACTOR_NOT_ALLOWED")
    if kind == "ROLLBACK" and (
        not isinstance(target_candidate_id, str) or not target_candidate_id.strip()
    ):
        raise ReleaseControlError("ROLLBACK_TARGET_REQUIRED")
    if target_candidate_id == decision.candidate_id:
        raise ReleaseControlError("ROLLBACK_TARGET_MUST_DIFFER")


def _aware(value: datetime) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReleaseControlError("CLOCK_MUST_BE_TIMEZONE_AWARE")


def _signature_payload(
    decision: ReleaseDecision,
    actor_id: str,
    idempotency_key: str,
    reason: str,
) -> bytes:
    """Canonical bytes supplied to an external signature verifier."""

    payload = {
        "decision_id": decision_fingerprint(decision),
        "candidate_id": decision.candidate_id,
        "environment": decision.environment,
        "actor_id": actor_id,
        "idempotency_key": idempotency_key,
        "reason": reason,
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )


def _signature_ref(signature: str) -> str:
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()


def _stored(row: ReleaseControlRow) -> ReleaseControlEvent:
    if row.kind not in {"APPROVAL", "ROLLBACK"}:
        raise ReleaseControlError("PERSISTED_KIND_INVALID")
    created_at = row.created_at
    if created_at.tzinfo is None or created_at.utcoffset() is None:
        created_at = created_at.replace(tzinfo=UTC)
    return ReleaseControlEvent(
        row.control_id,
        row.kind,
        row.idempotency_key,
        row.decision_id,
        row.candidate_id,
        row.environment,
        row.actor_id,
        row.target_candidate_id,
        row.reason,
        row.signature_ref,
        row.signature_algorithm,
        created_at,
    )  # type: ignore[arg-type]


__all__ = [
    "InMemoryReleaseControlStore",
    "ReleaseControlBase",
    "ReleaseControlError",
    "ReleaseControlEvent",
    "ReleaseControlKind",
    "ReleaseControlRow",
    "ReleaseControlStore",
    "ReleaseSignatureVerifier",
    "SqlAlchemyReleaseControlStore",
]
