"""Durable, fail-closed persistence for AgentAuthorization leases.

The lease store is an AI-runtime boundary.  It persists authorization metadata
and an append-only audit trail, but never invokes a model provider or writes a
Family/Growth fact.  Session ownership remains with the composition root:
methods only flush and never commit or close the SQLAlchemy session.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import JSON, BigInteger, DateTime, Integer, String, Text, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AuthorizationBudget,
)


class AgentAuthorizationPersistenceBase(DeclarativeBase):
    """Metadata for AI-runtime authorization tables only."""


class AgentAuthorizationRow(AgentAuthorizationPersistenceBase):
    __tablename__ = "ai_agent_authorizations"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    authorization_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(128), nullable=False)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    allowed_use_cases: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    allowed_tools: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    issued_by: Mapped[str] = mapped_column(String(128), nullable=False)
    issued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    max_steps: Mapped[int] = mapped_column(Integer, nullable=False)
    max_cost_micros: Mapped[int | None] = mapped_column(BigInteger)
    policy_version: Mapped[str] = mapped_column(String(128), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    audit_ref: Mapped[str] = mapped_column(String(256), nullable=False)


class AgentAuthorizationAuditRow(AgentAuthorizationPersistenceBase):
    __tablename__ = "ai_agent_authorization_audits"

    tenant_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    event_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    authorization_id: Mapped[str] = mapped_column(String(128), nullable=False)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    audit_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    audit_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False, default=dict)


class AgentAuthorizationPersistenceError(ValueError):
    """Base error for invalid or conflicting lease operations."""


class AgentAuthorizationNotFound(AgentAuthorizationPersistenceError):
    """A lease is not visible in the requested tenant/family scope."""


class AgentAuthorizationConflict(AgentAuthorizationPersistenceError):
    """An idempotency or revoke operation conflicts with stored state."""


@dataclass(frozen=True, slots=True)
class AgentAuthorizationScope:
    tenant_id: str
    family_id: str

    def __post_init__(self) -> None:
        if not self.tenant_id or not self.family_id:
            raise AgentAuthorizationPersistenceError("AUTHORIZATION_SCOPE_REQUIRED")


@dataclass(frozen=True, slots=True)
class AgentAuthorizationAuditEvent:
    event_id: str
    authorization_id: str
    scope: AgentAuthorizationScope
    event_type: str
    actor_id: str
    audit_ref: str
    occurred_at: datetime
    metadata: Mapping[str, Any]

    def __post_init__(self) -> None:
        if not all(
            (
                self.event_id,
                self.authorization_id,
                self.event_type,
                self.actor_id,
                self.audit_ref,
            )
        ):
            raise AgentAuthorizationPersistenceError("AUTHORIZATION_AUDIT_IDENTITY_REQUIRED")
        _require_aware(self.occurred_at, "occurred_at")
        if not isinstance(self.metadata, Mapping):
            raise AgentAuthorizationPersistenceError("AUTHORIZATION_AUDIT_METADATA_REQUIRED")
        object.__setattr__(self, "metadata", dict(self.metadata))


class AgentAuthorizationLeaseStore(Protocol):
    async def issue(self, authorization: AgentAuthorization) -> AgentAuthorization: ...

    async def revoke(
        self,
        authorization_id: str,
        *,
        scope: AgentAuthorizationScope,
        revoked_at: datetime,
        actor_id: str,
        audit_ref: str,
    ) -> AgentAuthorization: ...

    async def get(
        self, authorization_id: str, *, scope: AgentAuthorizationScope
    ) -> AgentAuthorization | None: ...

    async def find_active(
        self,
        *,
        scope: AgentAuthorizationScope,
        agent_id: str,
        use_case: str,
        issued_by: str | None = None,
        requested_tools: Iterable[str] = (),
        estimated_steps: int = 1,
        estimated_cost_micros: int | None = None,
        now: datetime | None = None,
    ) -> AgentAuthorization | None: ...

    async def audit(
        self, *, scope: AgentAuthorizationScope, authorization_id: str
    ) -> tuple[AgentAuthorizationAuditEvent, ...]: ...


class SqlAlchemyAgentAuthorizationLeaseStore:
    """SQLAlchemy lease adapter with explicit transaction ownership."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def issue(self, authorization: AgentAuthorization) -> AgentAuthorization:
        _validate_authorization(authorization)
        existing = await self._session.scalar(
            select(AgentAuthorizationRow).where(
                AgentAuthorizationRow.tenant_id == authorization.tenant_id,
                AgentAuthorizationRow.authorization_id == authorization.authorization_id,
            )
        )
        if existing is not None:
            if _row_to_authorization(existing) != authorization:
                raise AgentAuthorizationConflict("AUTHORIZATION_ISSUE_REPLAY_MISMATCH")
            return authorization
        row = AgentAuthorizationRow(
            tenant_id=authorization.tenant_id,
            authorization_id=authorization.authorization_id,
            agent_id=authorization.agent_id,
            family_id=authorization.family_id,
            allowed_use_cases=sorted(authorization.allowed_use_cases),
            allowed_tools=sorted(authorization.allowed_tools),
            issued_by=authorization.issued_by,
            issued_at=_aware(authorization.issued_at),
            expires_at=_aware(authorization.expires_at),
            revoked_at=_aware(authorization.revoked_at) if authorization.revoked_at else None,
            max_steps=authorization.budget.max_steps,
            max_cost_micros=authorization.budget.max_cost_micros,
            policy_version=authorization.policy_version,
            reason=authorization.reason,
            audit_ref=authorization.audit_ref,
        )
        self._session.add(row)
        self._session.add(
            _audit_row(
                authorization,
                event_id=f"{authorization.authorization_id}:issued",
                event_type="ISSUED",
                actor_id=authorization.issued_by,
                audit_ref=authorization.audit_ref,
                occurred_at=authorization.issued_at,
                metadata={"expires_at": authorization.expires_at.isoformat()},
            )
        )
        await self._session.flush()
        return authorization

    async def revoke(
        self,
        authorization_id: str,
        *,
        scope: AgentAuthorizationScope,
        revoked_at: datetime,
        actor_id: str,
        audit_ref: str,
    ) -> AgentAuthorization:
        if not authorization_id or not actor_id or not audit_ref:
            raise AgentAuthorizationPersistenceError("AUTHORIZATION_REVOKE_METADATA_REQUIRED")
        _require_aware(revoked_at, "revoked_at")
        row = await self._get_row(authorization_id, scope)
        current = _row_to_authorization(row)
        if revoked_at < current.issued_at:
            raise AgentAuthorizationPersistenceError("AUTHORIZATION_REVOKED_AT_BEFORE_ISSUE")
        if row.revoked_at is not None:
            if _aware(row.revoked_at) != revoked_at:
                raise AgentAuthorizationConflict("AUTHORIZATION_REVOKE_REPLAY_MISMATCH")
            existing_audit = await self._session.scalar(
                select(AgentAuthorizationAuditRow).where(
                    AgentAuthorizationAuditRow.tenant_id == scope.tenant_id,
                    AgentAuthorizationAuditRow.event_id == f"{authorization_id}:revoked",
                )
            )
            if existing_audit is not None and (
                existing_audit.actor_id != actor_id or existing_audit.audit_ref != audit_ref
            ):
                raise AgentAuthorizationConflict("AUTHORIZATION_REVOKE_REPLAY_MISMATCH")
            return current
        row.revoked_at = revoked_at
        self._session.add(
            AgentAuthorizationAuditRow(
                tenant_id=scope.tenant_id,
                event_id=f"{authorization_id}:revoked",
                authorization_id=authorization_id,
                family_id=scope.family_id,
                event_type="REVOKED",
                actor_id=actor_id,
                audit_ref=audit_ref,
                occurred_at=revoked_at,
                audit_metadata={},
            )
        )
        await self._session.flush()
        return _row_to_authorization(row)

    async def get(
        self, authorization_id: str, *, scope: AgentAuthorizationScope
    ) -> AgentAuthorization | None:
        row = await self._session.scalar(
            select(AgentAuthorizationRow).where(
                AgentAuthorizationRow.tenant_id == scope.tenant_id,
                AgentAuthorizationRow.family_id == scope.family_id,
                AgentAuthorizationRow.authorization_id == authorization_id,
            )
        )
        return _row_to_authorization(row) if row is not None else None

    async def find_active(
        self,
        *,
        scope: AgentAuthorizationScope,
        agent_id: str,
        use_case: str,
        issued_by: str | None = None,
        requested_tools: Iterable[str] = (),
        estimated_steps: int = 1,
        estimated_cost_micros: int | None = None,
        now: datetime | None = None,
    ) -> AgentAuthorization | None:
        """Resolve only a currently valid lease; all non-matches return None."""

        if not agent_id or not use_case or estimated_steps < 1:
            return None
        if issued_by is not None and not issued_by.strip():
            return None
        if estimated_cost_micros is not None and estimated_cost_micros < 0:
            return None
        instant = now or datetime.now(UTC)
        if instant.tzinfo is None:
            return None
        requested = frozenset(requested_tools)
        statement = select(AgentAuthorizationRow).where(
                AgentAuthorizationRow.tenant_id == scope.tenant_id,
                AgentAuthorizationRow.family_id == scope.family_id,
                AgentAuthorizationRow.agent_id == agent_id,
                AgentAuthorizationRow.issued_at <= instant,
                AgentAuthorizationRow.expires_at > instant,
            )
        if issued_by is not None:
            statement = statement.where(AgentAuthorizationRow.issued_by == issued_by)
        rows = await self._session.scalars(
            statement.order_by(AgentAuthorizationRow.issued_at.desc())
        )
        for row in rows:
            if row.revoked_at is not None and _aware(row.revoked_at) <= instant:
                continue
            if use_case not in frozenset(row.allowed_use_cases or ()):
                continue
            if not requested.issubset(frozenset(row.allowed_tools or ())):
                continue
            if estimated_steps > row.max_steps:
                continue
            if (
                estimated_cost_micros is not None
                and (row.max_cost_micros is None or estimated_cost_micros > row.max_cost_micros)
            ):
                continue
            return _row_to_authorization(row)
        return None

    async def audit(
        self, *, scope: AgentAuthorizationScope, authorization_id: str
    ) -> tuple[AgentAuthorizationAuditEvent, ...]:
        rows = await self._session.scalars(
            select(AgentAuthorizationAuditRow)
            .where(
                AgentAuthorizationAuditRow.tenant_id == scope.tenant_id,
                AgentAuthorizationAuditRow.family_id == scope.family_id,
                AgentAuthorizationAuditRow.authorization_id == authorization_id,
            )
            .order_by(AgentAuthorizationAuditRow.occurred_at)
        )
        return tuple(_row_to_audit(row) for row in rows)

    async def _get_row(
        self, authorization_id: str, scope: AgentAuthorizationScope
    ) -> AgentAuthorizationRow:
        row = await self._session.scalar(
            select(AgentAuthorizationRow).where(
                AgentAuthorizationRow.tenant_id == scope.tenant_id,
                AgentAuthorizationRow.family_id == scope.family_id,
                AgentAuthorizationRow.authorization_id == authorization_id,
            )
        )
        if row is None:
            raise AgentAuthorizationNotFound("AUTHORIZATION_NOT_FOUND")
        return row


# Short aliases keep the seam discoverable for callers that do not need to
# spell out the lease implementation detail.
AgentAuthorizationStore = AgentAuthorizationLeaseStore
SqlAlchemyAgentAuthorizationStore = SqlAlchemyAgentAuthorizationLeaseStore


def _validate_authorization(authorization: AgentAuthorization) -> None:
    if not isinstance(authorization, AgentAuthorization):
        raise AgentAuthorizationPersistenceError("AUTHORIZATION_TYPE_REQUIRED")
    _require_aware(authorization.issued_at, "issued_at")
    _require_aware(authorization.expires_at, "expires_at")
    if authorization.revoked_at is not None:
        _require_aware(authorization.revoked_at, "revoked_at")


def _row_to_authorization(row: AgentAuthorizationRow) -> AgentAuthorization:
    return AgentAuthorization(
        authorization_id=row.authorization_id,
        agent_id=row.agent_id,
        tenant_id=row.tenant_id,
        family_id=row.family_id,
        allowed_use_cases=frozenset(row.allowed_use_cases or ()),
        allowed_tools=frozenset(row.allowed_tools or ()),
        issued_by=row.issued_by,
        issued_at=_aware(row.issued_at),
        expires_at=_aware(row.expires_at),
        revoked_at=_aware(row.revoked_at) if row.revoked_at else None,
        budget=AuthorizationBudget(
            max_steps=row.max_steps,
            max_cost_micros=row.max_cost_micros,
        ),
        policy_version=row.policy_version,
        reason=row.reason,
        audit_ref=row.audit_ref,
    )


def _audit_row(
    authorization: AgentAuthorization,
    *,
    event_id: str,
    event_type: str,
    actor_id: str,
    audit_ref: str,
    occurred_at: datetime,
    metadata: Mapping[str, Any],
) -> AgentAuthorizationAuditRow:
    return AgentAuthorizationAuditRow(
        tenant_id=authorization.tenant_id,
        event_id=event_id,
        authorization_id=authorization.authorization_id,
        family_id=authorization.family_id,
        event_type=event_type,
        actor_id=actor_id,
        audit_ref=audit_ref,
        occurred_at=_aware(occurred_at),
        audit_metadata=dict(metadata),
    )


def _row_to_audit(row: AgentAuthorizationAuditRow) -> AgentAuthorizationAuditEvent:
    return AgentAuthorizationAuditEvent(
        event_id=row.event_id,
        authorization_id=row.authorization_id,
        scope=AgentAuthorizationScope(row.tenant_id, row.family_id),
        event_type=row.event_type,
        actor_id=row.actor_id,
        audit_ref=row.audit_ref,
        occurred_at=_aware(row.occurred_at),
        metadata=row.audit_metadata or {},
    )


def _require_aware(value: datetime, field: str) -> None:
    if value.tzinfo is None:
        raise AgentAuthorizationPersistenceError(
            f"AUTHORIZATION_{field.upper()}_MUST_BE_TIMEZONE_AWARE"
        )


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


__all__ = [
    "AgentAuthorizationAuditEvent",
    "AgentAuthorizationAuditRow",
    "AgentAuthorizationConflict",
    "AgentAuthorizationLeaseStore",
    "AgentAuthorizationStore",
    "AgentAuthorizationNotFound",
    "AgentAuthorizationPersistenceBase",
    "AgentAuthorizationPersistenceError",
    "AgentAuthorizationRow",
    "AgentAuthorizationScope",
    "SqlAlchemyAgentAuthorizationLeaseStore",
    "SqlAlchemyAgentAuthorizationStore",
]
