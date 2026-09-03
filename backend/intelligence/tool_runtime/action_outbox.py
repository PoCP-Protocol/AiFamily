"""Durable, provider-neutral outbox for pending Named Actions.

The Tool Runtime deliberately stops at a ``ToolCallResult`` whose status is
``PENDING_HUMAN_CONFIRMATION``.  This module gives that result a durable
delivery boundary without turning it into an accepted action: a worker may
deliver the envelope to a Human Gate inbox, but no adapter in this module can
invoke a domain command, a model provider, or commit a transaction.

The SQL adapter owns only runtime metadata.  It uses ``add``/``flush`` and
leaves transaction ownership to the application composition root, which can
atomically persist a ToolCall result alongside an AgentRun and audit event.
"""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import JSON, DateTime, String, Text, UniqueConstraint, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.experience.outbox_worker import ExperienceOutboxWorker
from backend.intelligence.human_gate.contracts import GateScope
from backend.intelligence.tool_runtime.contracts import ToolCallResult

_PENDING_STATUS = "PENDING_HUMAN_CONFIRMATION"
_SCHEMA_VERSION = "tool-action.v1"
_EVENT_TYPE = "tool.named_action.pending"
_ACTION_NAME = re.compile(r"^[A-Z][A-Z0-9_]{2,63}$")
_GENERIC_ACTIONS = frozenset({"UPDATE", "PATCH", "DELETE", "WRITE", "SET"})


class ToolActionOutboxError(ValueError):
    """Base error for malformed or conflicting action envelopes."""


class ToolActionOutboxConflict(ToolActionOutboxError):
    """The same tenant/call id was appended with different stable content."""


@dataclass(frozen=True, slots=True)
class ToolActionOutboxEnvelope:
    """Immutable pending-action envelope sent to a Human Gate boundary.

    The envelope is intentionally explicit about its pre-gate state.  It has
    no ``NamedActionRequest``, human actor, decision id, or execution handle;
    all of those can only exist after the Human Gate accepts the proposal.
    """

    message_id: str
    call_id: str
    tool_id: str
    agent_id: str
    tenant_id: str
    family_id: str
    use_case: str
    action_name: str
    action_arguments: Mapping[str, Any]
    scope: GateScope
    provenance_ref: str
    risk_level: str
    status: str
    created_at: datetime
    expires_at: datetime
    schema_version: str = _SCHEMA_VERSION

    @classmethod
    def from_result(
        cls, result: ToolCallResult, *, use_case: str | None = None
    ) -> ToolActionOutboxEnvelope:
        """Build an envelope through the same fail-closed conversion helper."""

        return envelope_from_result(result, use_case=use_case)

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.message_id, "message_id"),
            (self.call_id, "call_id"),
            (self.tool_id, "tool_id"),
            (self.agent_id, "agent_id"),
            (self.tenant_id, "tenant_id"),
            (self.family_id, "family_id"),
            (self.use_case, "use_case"),
            (self.action_name, "action_name"),
            (self.provenance_ref, "provenance_ref"),
            (self.risk_level, "risk_level"),
            (self.schema_version, "schema_version"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ToolActionOutboxError(f"{field_name} is required")
        if self.status != _PENDING_STATUS:
            raise ToolActionOutboxError("TOOL_ACTION_MUST_REMAIN_PENDING_HUMAN_CONFIRMATION")
        if not _ACTION_NAME.fullmatch(self.action_name) or self.action_name in _GENERIC_ACTIONS:
            raise ToolActionOutboxError("TOOL_ACTION_NAME_INVALID")
        if not isinstance(self.scope, GateScope):
            raise ToolActionOutboxError("TOOL_ACTION_SCOPE_REQUIRED")
        if self.scope.tenant_id != self.tenant_id or self.scope.family_id != self.family_id:
            raise ToolActionOutboxError("TOOL_ACTION_SCOPE_MISMATCH")
        if self.scope.purpose != self.use_case:
            raise ToolActionOutboxError("TOOL_ACTION_PURPOSE_MISMATCH")
        if not isinstance(self.action_arguments, Mapping):
            raise ToolActionOutboxError("TOOL_ACTION_ARGUMENTS_REQUIRED")
        _jsonable(self.action_arguments)  # fail closed before touching SQL
        if self.created_at.tzinfo is None or self.expires_at.tzinfo is None:
            raise ToolActionOutboxError("TOOL_ACTION_TIMESTAMPS_MUST_BE_TIMEZONE_AWARE")
        if self.expires_at <= self.created_at:
            raise ToolActionOutboxError("TOOL_ACTION_EXPIRY_INVALID")

    @property
    def may_mutate_business_state(self) -> bool:
        return False

    @property
    def event_type(self) -> str:
        return _EVENT_TYPE

    @property
    def human_gate_state(self) -> str:
        """Stable state name used by consumers instead of inferring from fields."""

        return self.status

    def stable_payload(self) -> dict[str, Any]:
        """Return content used for idempotency (timestamps are not identity)."""

        return {
            "event_type": self.event_type,
            "message_id": self.message_id,
            "call_id": self.call_id,
            "tool_id": self.tool_id,
            "agent_id": self.agent_id,
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
            "use_case": self.use_case,
            "action_name": self.action_name,
            "action_arguments": _jsonable(self.action_arguments),
            "scope": _scope_json(self.scope),
            "provenance_ref": self.provenance_ref,
            "risk_level": self.risk_level,
            "status": self.status,
            "schema_version": self.schema_version,
        }

    def payload(self) -> dict[str, Any]:
        result = self.stable_payload()
        result.update(
            created_at=self.created_at.isoformat(),
            expires_at=self.expires_at.isoformat(),
        )
        return result


@dataclass(frozen=True, slots=True)
class StoredToolActionMessage:
    """Storage DTO consumed by a Human Gate inbox worker."""

    message_id: str
    call_id: str
    tool_id: str
    agent_id: str
    tenant_id: str
    family_id: str
    use_case: str
    action_name: str
    action_arguments: dict[str, Any]
    scope: GateScope
    provenance_ref: str
    risk_level: str
    status: str
    schema_version: str
    created_at: datetime
    expires_at: datetime
    enqueued_at: datetime
    published_at: datetime | None
    payload: dict[str, Any]

    @property
    def published(self) -> bool:
        return self.published_at is not None

    @property
    def human_gate_state(self) -> str:
        return self.status

    @property
    def may_mutate_business_state(self) -> bool:
        return False

    @property
    def event_type(self) -> str:
        return _EVENT_TYPE


class ToolActionOutboxStore(Protocol):
    async def append(
        self, result: ToolCallResult, *, use_case: str | None = None
    ) -> StoredToolActionMessage: ...

    async def pending(self, *, limit: int = 100) -> tuple[StoredToolActionMessage, ...]: ...

    async def mark_published(
        self, message_id: str, *, published_at: datetime | None = None
    ) -> StoredToolActionMessage: ...


class ToolActionOutboxBase(DeclarativeBase):
    """Metadata boundary for AI Tool Action outbox tables."""


class ToolActionOutboxRow(ToolActionOutboxBase):
    __tablename__ = "ai_tool_action_outbox"
    __table_args__ = (UniqueConstraint("tenant_id", "call_id", name="uq_ai_tool_action_call"),)

    message_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    call_id: Mapped[str] = mapped_column(String(256), nullable=False)
    tool_id: Mapped[str] = mapped_column(String(128), nullable=False)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    use_case: Mapped[str] = mapped_column(String(128), nullable=False)
    action_name: Mapped[str] = mapped_column(String(128), nullable=False)
    action_arguments: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    subject_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    provenance_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    risk_level: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(64), nullable=False)
    schema_version: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)


class SqlAlchemyToolActionOutbox:
    """Async SQL adapter; transaction commit/rollback remains caller-owned."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        result: ToolCallResult,
        *,
        use_case: str | None = None,
        enqueued_at: datetime | None = None,
    ) -> StoredToolActionMessage:
        envelope = envelope_from_result(result, use_case=use_case)
        existing = await self._session.scalar(
            select(ToolActionOutboxRow).where(
                ToolActionOutboxRow.tenant_id == envelope.tenant_id,
                ToolActionOutboxRow.call_id == envelope.call_id,
            )
        )
        fingerprint = _fingerprint(envelope.stable_payload())
        if existing is not None:
            if existing.idempotency_fingerprint != fingerprint:
                raise ToolActionOutboxConflict("TOOL_ACTION_REPLAY_MISMATCH")
            return _stored(existing)
        queued = enqueued_at or datetime.now(UTC)
        if queued.tzinfo is None:
            raise ToolActionOutboxError("TOOL_ACTION_ENQUEUED_AT_MUST_BE_TIMEZONE_AWARE")
        row = ToolActionOutboxRow(
            message_id=envelope.message_id,
            call_id=envelope.call_id,
            tool_id=envelope.tool_id,
            agent_id=envelope.agent_id,
            tenant_id=envelope.tenant_id,
            family_id=envelope.family_id,
            use_case=envelope.use_case,
            action_name=envelope.action_name,
            action_arguments=dict(_jsonable(envelope.action_arguments)),
            subject_ids=list(envelope.scope.subject_ids),
            purpose=envelope.scope.purpose,
            consent_version=envelope.scope.consent_version,
            correlation_id=envelope.scope.correlation_id,
            provenance_ref=envelope.provenance_ref,
            risk_level=envelope.risk_level,
            status=envelope.status,
            schema_version=envelope.schema_version,
            created_at=_aware(envelope.created_at),
            expires_at=_aware(envelope.expires_at),
            enqueued_at=_aware(queued),
            idempotency_fingerprint=fingerprint,
            payload=envelope.payload(),
        )
        self._session.add(row)
        await self._session.flush()
        return _stored(row)

    async def pending(self, *, limit: int = 100) -> tuple[StoredToolActionMessage, ...]:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        result = await self._session.execute(
            select(ToolActionOutboxRow)
            .where(ToolActionOutboxRow.published_at.is_(None))
            .order_by(ToolActionOutboxRow.enqueued_at, ToolActionOutboxRow.message_id)
            .limit(limit)
        )
        return tuple(_stored(row) for row in result.scalars())

    async def mark_published(
        self, message_id: str, *, published_at: datetime | None = None
    ) -> StoredToolActionMessage:
        row = await self._session.get(ToolActionOutboxRow, message_id)
        if row is None:
            raise ToolActionOutboxError("TOOL_ACTION_MESSAGE_NOT_FOUND")
        if row.published_at is None:
            stamp = published_at or datetime.now(UTC)
            if stamp.tzinfo is None:
                raise ToolActionOutboxError("TOOL_ACTION_PUBLISHED_AT_MUST_BE_TIMEZONE_AWARE")
            row.published_at = stamp
            await self._session.flush()
        return _stored(row)


def envelope_from_result(
    result: ToolCallResult, *, use_case: str | None = None
) -> ToolActionOutboxEnvelope:
    """Convert a runtime result without creating a Human Gate decision."""

    if not isinstance(result, ToolCallResult):
        raise ToolActionOutboxError("TOOL_ACTION_RESULT_REQUIRED")
    scope = result.pending_action.scope
    resolved_use_case = scope.purpose if use_case is None else use_case
    if not isinstance(resolved_use_case, str) or not resolved_use_case.strip():
        raise ToolActionOutboxError("TOOL_ACTION_USE_CASE_REQUIRED")
    if scope.tenant_id != result.tenant_id or scope.family_id != result.family_id:
        raise ToolActionOutboxError("TOOL_ACTION_RESULT_SCOPE_MISMATCH")
    if scope.purpose != resolved_use_case.strip():
        raise ToolActionOutboxError("TOOL_ACTION_RESULT_PURPOSE_MISMATCH")
    if result.pending_action.expires_at <= result.created_at:
        raise ToolActionOutboxError("TOOL_ACTION_RESULT_EXPIRY_INVALID")
    identity = f"{result.tenant_id}:{result.call_id}"
    message_id = "tool-action:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return ToolActionOutboxEnvelope(
        message_id=message_id,
        call_id=result.call_id,
        tool_id=result.tool_id,
        agent_id=result.agent_id,
        tenant_id=result.tenant_id,
        family_id=result.family_id,
        use_case=resolved_use_case.strip(),
        action_name=result.pending_action.action_name,
        action_arguments=result.pending_action.action_arguments,
        scope=scope,
        provenance_ref=result.pending_action.provenance_ref,
        risk_level=result.pending_action.risk_level,
        status=result.status,
        created_at=result.created_at,
        expires_at=result.pending_action.expires_at,
    )


def _stored(row: ToolActionOutboxRow) -> StoredToolActionMessage:
    return StoredToolActionMessage(
        message_id=row.message_id,
        call_id=row.call_id,
        tool_id=row.tool_id,
        agent_id=row.agent_id,
        tenant_id=row.tenant_id,
        family_id=row.family_id,
        use_case=row.use_case,
        action_name=row.action_name,
        action_arguments=dict(row.action_arguments or {}),
        scope=GateScope(
            tenant_id=row.tenant_id,
            family_id=row.family_id,
            subject_ids=tuple(row.subject_ids or ()),
            purpose=row.purpose,
            consent_version=row.consent_version,
            correlation_id=row.correlation_id,
        ),
        provenance_ref=row.provenance_ref,
        risk_level=row.risk_level,
        status=row.status,
        schema_version=row.schema_version,
        created_at=_aware(row.created_at),
        expires_at=_aware(row.expires_at),
        enqueued_at=_aware(row.enqueued_at),
        published_at=_aware(row.published_at) if row.published_at else None,
        payload=dict(row.payload or {}),
    )


def _scope_json(scope: GateScope) -> dict[str, Any]:
    return {
        "tenant_id": scope.tenant_id,
        "family_id": scope.family_id,
        "subject_ids": list(scope.subject_ids),
        "purpose": scope.purpose,
        "consent_version": scope.consent_version,
        "correlation_id": scope.correlation_id,
    }


def _fingerprint(payload: Mapping[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (tuple, list, set, frozenset)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise ToolActionOutboxError("TOOL_ACTION_ARGUMENTS_NOT_JSON_SERIALIZABLE")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


__all__ = [
    "SqlAlchemyToolActionOutbox",
    "StoredToolActionMessage",
    "ToolActionOutboxBase",
    "ToolActionOutboxConflict",
    "ToolActionOutboxEnvelope",
    "ToolActionOutboxError",
    "ToolActionOutboxRow",
    "ToolActionOutboxStore",
    "ToolActionOutboxWorker",
    "envelope_from_result",
]


# The generic worker already implements the required at-least-once contract:
# consume first, acknowledge second, and route permanent failures to a DLQ.
# This alias documents that the Tool Action adapter intentionally reuses that
# provider-neutral worker rather than introducing a second delivery protocol.
ToolActionOutboxWorker = ExperienceOutboxWorker
