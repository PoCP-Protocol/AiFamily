"""Atomic deployment ledger for family-experience release sets."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Literal, Protocol
from uuid import uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Index,
    Integer,
    String,
    Text,
    or_,
    select,
)
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .release_set import FamilyExperienceReleaseSet
from .release_set_control import ReleaseSetControlEvent, ReleaseSetControlReader

ReleaseSetDeploymentOperation = Literal["APPLY", "ROLLBACK"]
ReleaseSetDeploymentPhase = Literal["CANARY", "ACTIVE", "ROLLED_BACK"]
ReleaseSetTransitionStatus = Literal["PREPARED", "ACKNOWLEDGED", "COMMITTED", "UNKNOWN"]


class ReleaseSetDeploymentError(ValueError):
    """A release-set deployment cannot be authorized or recorded safely."""


class ReleaseSetDeploymentBase(DeclarativeBase):
    """Metadata boundary for release-set deployment transitions."""


class ReleaseSetDeploymentRow(ReleaseSetDeploymentBase):
    __tablename__ = "ai_family_experience_release_set_deployments"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('APPLY', 'ROLLBACK')",
            name="ck_ai_experience_release_set_deploy_operation",
        ),
        CheckConstraint(
            "phase IN ('CANARY', 'ACTIVE', 'ROLLED_BACK')",
            name="ck_ai_experience_release_set_deploy_phase",
        ),
        CheckConstraint(
            "(phase = 'CANARY' AND rollout_percent BETWEEN 1 AND 99) OR "
            "(phase = 'ACTIVE' AND rollout_percent = 100) OR "
            "(phase = 'ROLLED_BACK' AND rollout_percent = 0)",
            name="ck_ai_experience_release_set_deploy_rollout",
        ),
        CheckConstraint(
            "(operation = 'APPLY' AND phase IN ('CANARY', 'ACTIVE') "
            "AND target_release_set_id IS NULL "
            "AND acknowledged_release_set_id = release_set_id) OR "
            "(operation = 'ROLLBACK' AND phase = 'ROLLED_BACK' "
            "AND target_release_set_id IS NOT NULL "
            "AND target_release_set_id <> release_set_id "
            "AND acknowledged_release_set_id = target_release_set_id)",
            name="ck_ai_experience_release_set_deploy_transition",
        ),
        Index(
            "uq_ai_experience_release_set_deploy_idempotency",
            "idempotency_key",
            unique=True,
        ),
        Index(
            "ix_ai_experience_release_set_deploy_scope_sequence",
            "environment",
            "use_case",
            "data_class",
            "sequence",
        ),
    )

    sequence: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    receipt_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    release_set_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_release_set_id: Mapped[str | None] = mapped_column(String(64))
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    use_case: Mapped[str] = mapped_column(String(256), nullable=False)
    data_class: Mapped[str] = mapped_column(String(64), nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    rollout_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    control_id: Mapped[str] = mapped_column(String(128), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(256), nullable=False)
    applied_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    acknowledged_release_set_id: Mapped[str] = mapped_column(String(64), nullable=False)
    external_ref: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ActiveReleaseBindingRow(ReleaseSetDeploymentBase):
    __tablename__ = "ai_family_experience_active_release_bindings"

    environment: Mapped[str] = mapped_column(String(64), primary_key=True)
    use_case: Mapped[str] = mapped_column(String(256), primary_key=True)
    data_class: Mapped[str] = mapped_column(String(64), primary_key=True)
    release_set_id: Mapped[str] = mapped_column(String(64), nullable=False)
    deployment_receipt_id: Mapped[str] = mapped_column(String(64), nullable=False)
    deployment_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    control_id: Mapped[str] = mapped_column(String(128), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ModelInvocationFenceClaimRow(ReleaseSetDeploymentBase):
    __tablename__ = "ai_model_invocation_fence_claims"

    claim_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    claim_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    request_ref: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    environment: Mapped[str] = mapped_column(String(64), nullable=False)
    use_case: Mapped[str] = mapped_column(String(256), nullable=False)
    data_class: Mapped[str] = mapped_column(String(64), nullable=False)
    release_set_id: Mapped[str] = mapped_column(String(64), nullable=False)
    deployment_receipt_id: Mapped[str] = mapped_column(String(64), nullable=False)
    deployment_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    runtime_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    control_id: Mapped[str] = mapped_column(String(128), nullable=False)
    provider_id: Mapped[str] = mapped_column(String(128), nullable=False)
    bundle_id: Mapped[str] = mapped_column(String(64), nullable=False)
    route_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ReleaseSetTransitionRow(ReleaseSetDeploymentBase):
    __tablename__ = "ai_family_experience_release_set_transitions"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PREPARED', 'ACKNOWLEDGED', 'COMMITTED', 'UNKNOWN')",
            name="ck_ai_release_set_transition_status",
        ),
        Index(
            "uq_ai_release_set_transition_idempotency",
            "idempotency_key",
            unique=True,
        ),
        CheckConstraint(
            "reconciliation_attempts >= 0",
            name="ck_ai_release_set_reconciliation_attempts",
        ),
        Index(
            "ix_ai_release_set_transition_reconcile_due",
            "environment",
            "status",
            "next_reconcile_at",
            "reconciliation_lease_until",
        ),
    )

    environment: Mapped[str] = mapped_column(String(64), primary_key=True)
    use_case: Mapped[str] = mapped_column(String(256), primary_key=True)
    data_class: Mapped[str] = mapped_column(String(64), primary_key=True)
    transition_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=False)
    control_id: Mapped[str] = mapped_column(String(128), nullable=False)
    operation: Mapped[str] = mapped_column(String(16), nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False)
    rollout_percent: Mapped[int] = mapped_column(Integer, nullable=False)
    source_release_set_id: Mapped[str] = mapped_column(String(64), nullable=False)
    target_release_set_id: Mapped[str | None] = mapped_column(String(64))
    runtime_config_digest: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_effective_sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    acknowledged_release_set_id: Mapped[str | None] = mapped_column(String(64))
    applied_config_digest: Mapped[str | None] = mapped_column(String(64))
    external_ref: Mapped[str | None] = mapped_column(Text)
    error_code: Mapped[str | None] = mapped_column(String(128))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    reconciliation_attempts: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        default=0,
        server_default="0",
    )
    reconciliation_lease_owner: Mapped[str | None] = mapped_column(String(256))
    reconciliation_lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    next_reconcile_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True, slots=True)
class ActiveReleaseBinding:
    environment: str
    use_case: str
    data_class: str
    release_set_id: str
    deployment_receipt_id: str
    deployment_sequence: int
    runtime_config_digest: str
    control_id: str
    updated_at: datetime

    def __post_init__(self) -> None:
        strings = (
            self.environment,
            self.use_case,
            self.data_class,
            self.release_set_id,
            self.deployment_receipt_id,
            self.runtime_config_digest,
            self.control_id,
        )
        if not all(value.strip() for value in strings):
            raise ReleaseSetDeploymentError("ACTIVE_RELEASE_BINDING_FIELDS_REQUIRED")
        if self.deployment_sequence <= 0:
            raise ReleaseSetDeploymentError("ACTIVE_RELEASE_BINDING_SEQUENCE_INVALID")
        if self.updated_at.tzinfo is None or self.updated_at.utcoffset() is None:
            raise ReleaseSetDeploymentError("ACTIVE_RELEASE_BINDING_TIME_MUST_BE_AWARE")


@dataclass(frozen=True, slots=True)
class ReleaseSetDeploymentAuthorization:
    control_id: str
    actor_id: str

    def __post_init__(self) -> None:
        if not self.control_id.strip() or not self.actor_id.strip():
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_AUTH_REQUIRED")
        if self.actor_id.startswith("ai:"):
            raise ReleaseSetDeploymentError("AI_RELEASE_SET_DEPLOYER_NOT_ALLOWED")


@dataclass(frozen=True, slots=True)
class ReleaseSetDeploymentAcknowledgement:
    acknowledged_release_set_id: str
    applied_config_digest: str
    external_ref: str
    transition_id: str
    control_id: str
    expected_effective_sequence: int


@dataclass(frozen=True, slots=True)
class ReleaseSetDeploymentReceipt:
    sequence: int
    receipt_id: str
    idempotency_key: str
    release_set_id: str
    target_release_set_id: str | None
    environment: str
    use_case: str
    data_class: str
    operation: ReleaseSetDeploymentOperation
    phase: ReleaseSetDeploymentPhase
    rollout_percent: int
    control_id: str
    actor_id: str
    applied_config_digest: str
    acknowledged_release_set_id: str
    external_ref: str
    created_at: datetime

    def __post_init__(self) -> None:
        required = (
            self.receipt_id,
            self.idempotency_key,
            self.release_set_id,
            self.environment,
            self.use_case,
            self.data_class,
            self.control_id,
            self.actor_id,
            self.applied_config_digest,
            self.acknowledged_release_set_id,
            self.external_ref,
        )
        if not all(isinstance(value, str) and value.strip() for value in required):
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_FIELDS_REQUIRED")
        if self.sequence < 0:
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_SEQUENCE_INVALID")
        if self.created_at.tzinfo is None or self.created_at.utcoffset() is None:
            raise ReleaseSetDeploymentError("DEPLOYMENT_TIME_MUST_BE_AWARE")
        valid_apply = (
            self.operation == "APPLY"
            and self.phase in {"CANARY", "ACTIVE"}
            and self.target_release_set_id is None
            and self.acknowledged_release_set_id == self.release_set_id
        )
        valid_rollback = (
            self.operation == "ROLLBACK"
            and self.phase == "ROLLED_BACK"
            and isinstance(self.target_release_set_id, str)
            and bool(self.target_release_set_id.strip())
            and self.target_release_set_id != self.release_set_id
            and self.acknowledged_release_set_id == self.target_release_set_id
        )
        valid_rollout = (
            (self.phase == "CANARY" and 1 <= self.rollout_percent <= 99)
            or (self.phase == "ACTIVE" and self.rollout_percent == 100)
            or (self.phase == "ROLLED_BACK" and self.rollout_percent == 0)
        )
        if not (valid_rollout and (valid_apply or valid_rollback)):
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_TRANSITION_INVALID")


@dataclass(frozen=True, slots=True)
class ReleaseSetTransitionClaim:
    transition_id: str
    idempotency_key: str
    control_id: str
    environment: str
    use_case: str
    data_class: str
    operation: ReleaseSetDeploymentOperation
    phase: ReleaseSetDeploymentPhase
    rollout_percent: int
    source_release_set_id: str
    target_release_set_id: str | None
    runtime_config_digest: str
    expected_effective_sequence: int
    status: ReleaseSetTransitionStatus
    acknowledged_release_set_id: str | None
    applied_config_digest: str | None
    external_ref: str | None
    error_code: str | None
    created_at: datetime
    updated_at: datetime

    def acknowledgement(self) -> ReleaseSetDeploymentAcknowledgement | None:
        values = (
            self.acknowledged_release_set_id,
            self.applied_config_digest,
            self.external_ref,
        )
        if not all(isinstance(value, str) and value.strip() for value in values):
            return None
        return ReleaseSetDeploymentAcknowledgement(
            acknowledged_release_set_id=values[0],  # type: ignore[arg-type]
            applied_config_digest=values[1],  # type: ignore[arg-type]
            external_ref=values[2],  # type: ignore[arg-type]
            transition_id=self.transition_id,
            control_id=self.control_id,
            expected_effective_sequence=self.expected_effective_sequence,
        )


@dataclass(frozen=True, slots=True)
class ReleaseSetReconciliationLease:
    transition: ReleaseSetTransitionClaim
    attempt: int
    worker_id: str
    lease_until: datetime

    def __post_init__(self) -> None:
        if self.attempt <= 0 or not self.worker_id.strip():
            raise ReleaseSetDeploymentError("RECONCILIATION_LEASE_INVALID")
        _aware_transition_time(self.lease_until)


class ReleaseSetTransitionCoordinator(Protocol):
    durability_mode: str

    async def prepare(
        self,
        control: ReleaseSetControlEvent,
        *,
        idempotency_key: str,
    ) -> ReleaseSetTransitionClaim: ...

    async def acknowledge(
        self,
        claim: ReleaseSetTransitionClaim,
        acknowledgement: ReleaseSetDeploymentAcknowledgement,
    ) -> ReleaseSetTransitionClaim: ...

    async def commit(
        self,
        claim: ReleaseSetTransitionClaim,
        receipt: ReleaseSetDeploymentReceipt,
    ) -> ReleaseSetDeploymentReceipt: ...

    async def mark_unknown(
        self,
        claim: ReleaseSetTransitionClaim,
        *,
        error_code: str,
    ) -> ReleaseSetTransitionClaim: ...

    async def get_by_idempotency(
        self, idempotency_key: str
    ) -> ReleaseSetTransitionClaim | None: ...

    async def claim_reconcilable(
        self,
        *,
        environment: str,
        worker_id: str,
        now: datetime,
        stale_after: timedelta,
        lease_ttl: timedelta,
        limit: int,
    ) -> tuple[ReleaseSetReconciliationLease, ...]: ...

    async def reschedule_reconciliation(
        self,
        lease: ReleaseSetReconciliationLease,
        *,
        next_reconcile_at: datetime,
        error_code: str,
    ) -> ReleaseSetTransitionClaim: ...


class ReleaseSetDeploymentPort(Protocol):
    async def apply(
        self,
        release_set: FamilyExperienceReleaseSet,
        *,
        phase: ReleaseSetDeploymentPhase,
        rollout_percent: int,
        idempotency_key: str,
        transition_id: str,
        control_id: str,
        expected_effective_sequence: int,
    ) -> ReleaseSetDeploymentAcknowledgement: ...

    async def rollback(
        self,
        source: FamilyExperienceReleaseSet,
        target: FamilyExperienceReleaseSet,
        *,
        idempotency_key: str,
        transition_id: str,
        control_id: str,
        expected_effective_sequence: int,
    ) -> ReleaseSetDeploymentAcknowledgement: ...


class ReleaseSetDeploymentStore(Protocol):
    durability_mode: str

    async def get_by_idempotency(
        self, idempotency_key: str
    ) -> ReleaseSetDeploymentReceipt | None: ...

    async def get_by_receipt_id(self, receipt_id: str) -> ReleaseSetDeploymentReceipt | None: ...

    async def append(self, receipt: ReleaseSetDeploymentReceipt) -> ReleaseSetDeploymentReceipt: ...

    async def append_if_current(
        self,
        receipt: ReleaseSetDeploymentReceipt,
        *,
        expected_effective_sequence: int,
    ) -> ReleaseSetDeploymentReceipt: ...

    async def latest_effective(
        self, *, environment: str, use_case: str, data_class: str
    ) -> ReleaseSetDeploymentReceipt | None: ...

    async def get_active_binding(
        self, *, environment: str, use_case: str, data_class: str
    ) -> ActiveReleaseBinding | None: ...

    async def was_active(self, release_set_id: str) -> bool: ...


class InMemoryReleaseSetDeploymentStore:
    durability_mode = "IN_MEMORY"

    def __init__(self) -> None:
        self._receipts: list[ReleaseSetDeploymentReceipt] = []
        self._active: dict[tuple[str, str, str], ReleaseSetDeploymentReceipt] = {}
        self._lock = asyncio.Lock()
        self._transition_coordinator = InMemoryReleaseSetTransitionCoordinator(self)

    async def get_by_idempotency(self, idempotency_key: str) -> ReleaseSetDeploymentReceipt | None:
        return next(
            (item for item in self._receipts if item.idempotency_key == idempotency_key),
            None,
        )

    async def get_by_receipt_id(self, receipt_id: str) -> ReleaseSetDeploymentReceipt | None:
        return next(
            (item for item in self._receipts if item.receipt_id == receipt_id),
            None,
        )

    async def append(self, receipt: ReleaseSetDeploymentReceipt) -> ReleaseSetDeploymentReceipt:
        current = self._active.get(_receipt_scope(receipt))
        return await self.append_if_current(
            receipt,
            expected_effective_sequence=current.sequence if current is not None else 0,
        )

    async def append_if_current(
        self,
        receipt: ReleaseSetDeploymentReceipt,
        *,
        expected_effective_sequence: int,
    ) -> ReleaseSetDeploymentReceipt:
        async with self._lock:
            return await self._append_locked(receipt, expected_effective_sequence)

    async def _append_locked(
        self,
        receipt: ReleaseSetDeploymentReceipt,
        expected_effective_sequence: int,
    ) -> ReleaseSetDeploymentReceipt:
        existing = await self.get_by_idempotency(receipt.idempotency_key)
        if existing is not None:
            if replace_sequence(receipt, existing.sequence) != existing:
                raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_CONFLICT")
            return existing
        current = self._active.get(_receipt_scope(receipt))
        current_sequence = current.sequence if current is not None else 0
        if current_sequence != expected_effective_sequence:
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_CAS_CONFLICT")
        stored = replace_sequence(receipt, len(self._receipts) + 1)
        self._receipts.append(stored)
        if stored.phase in {"ACTIVE", "ROLLED_BACK"}:
            self._active[_receipt_scope(stored)] = stored
        return stored

    async def latest_effective(
        self, *, environment: str, use_case: str, data_class: str
    ) -> ReleaseSetDeploymentReceipt | None:
        values = [
            item
            for item in self._receipts
            if (item.environment, item.use_case, item.data_class)
            == (environment, use_case, data_class)
            and item.phase in {"ACTIVE", "ROLLED_BACK"}
        ]
        return max(values, key=lambda item: item.sequence, default=None)

    async def get_active_binding(
        self, *, environment: str, use_case: str, data_class: str
    ) -> ActiveReleaseBinding | None:
        receipt = self._active.get((environment, use_case, data_class))
        return None if receipt is None else _active_binding(receipt)

    async def was_active(self, release_set_id: str) -> bool:
        return any(
            item.release_set_id == release_set_id
            and item.operation == "APPLY"
            and item.phase == "ACTIVE"
            and item.rollout_percent == 100
            for item in self._receipts
        )


class SqlAlchemyReleaseSetDeploymentStore:
    durability_mode = "DURABLE"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_idempotency(self, idempotency_key: str) -> ReleaseSetDeploymentReceipt | None:
        row = await self._session.scalar(
            select(ReleaseSetDeploymentRow).where(
                ReleaseSetDeploymentRow.idempotency_key == idempotency_key
            )
        )
        return None if row is None else _stored(row)

    async def get_by_receipt_id(self, receipt_id: str) -> ReleaseSetDeploymentReceipt | None:
        row = await self._session.scalar(
            select(ReleaseSetDeploymentRow).where(ReleaseSetDeploymentRow.receipt_id == receipt_id)
        )
        return None if row is None else _stored(row)

    async def append(self, receipt: ReleaseSetDeploymentReceipt) -> ReleaseSetDeploymentReceipt:
        projection = await self._session.get(
            ActiveReleaseBindingRow,
            _receipt_scope(receipt),
        )
        return await self.append_if_current(
            receipt,
            expected_effective_sequence=(
                projection.deployment_sequence if projection is not None else 0
            ),
        )

    async def append_if_current(
        self,
        receipt: ReleaseSetDeploymentReceipt,
        *,
        expected_effective_sequence: int,
    ) -> ReleaseSetDeploymentReceipt:
        existing = await self.get_by_idempotency(receipt.idempotency_key)
        if existing is not None:
            if replace_sequence(receipt, existing.sequence) != existing:
                raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_CONFLICT")
            return existing
        projection = await self._session.get(
            ActiveReleaseBindingRow,
            _receipt_scope(receipt),
            with_for_update=True,
        )
        current_sequence = projection.deployment_sequence if projection is not None else 0
        if current_sequence != expected_effective_sequence:
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_CAS_CONFLICT")
        row = _row(receipt)
        self._session.add(row)
        await self._session.flush()
        stored = _stored(row)
        if stored.phase in {"ACTIVE", "ROLLED_BACK"}:
            effective_release_set_id = (
                stored.release_set_id
                if stored.operation == "APPLY"
                else stored.target_release_set_id
            )
            if effective_release_set_id is None:  # pragma: no cover - receipt invariant
                raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_TARGET_REQUIRED")
            values = {
                "release_set_id": effective_release_set_id,
                "deployment_receipt_id": stored.receipt_id,
                "deployment_sequence": stored.sequence,
                "runtime_config_digest": stored.applied_config_digest,
                "control_id": stored.control_id,
                "updated_at": stored.created_at,
            }
            if projection is None:
                self._session.add(
                    ActiveReleaseBindingRow(
                        environment=stored.environment,
                        use_case=stored.use_case,
                        data_class=stored.data_class,
                        **values,
                    )
                )
            else:
                for name, value in values.items():
                    setattr(projection, name, value)
            await self._session.flush()
        return stored

    async def latest_effective(
        self, *, environment: str, use_case: str, data_class: str
    ) -> ReleaseSetDeploymentReceipt | None:
        row = await self._session.scalar(
            select(ReleaseSetDeploymentRow)
            .where(
                ReleaseSetDeploymentRow.environment == environment,
                ReleaseSetDeploymentRow.use_case == use_case,
                ReleaseSetDeploymentRow.data_class == data_class,
                ReleaseSetDeploymentRow.phase.in_(("ACTIVE", "ROLLED_BACK")),
            )
            .order_by(ReleaseSetDeploymentRow.sequence.desc())
            .limit(1)
        )
        return None if row is None else _stored(row)

    async def get_active_binding(
        self, *, environment: str, use_case: str, data_class: str
    ) -> ActiveReleaseBinding | None:
        row = await self._session.get(
            ActiveReleaseBindingRow,
            (environment, use_case, data_class),
        )
        return None if row is None else _stored_active_binding(row)

    async def was_active(self, release_set_id: str) -> bool:
        row = await self._session.scalar(
            select(ReleaseSetDeploymentRow.sequence)
            .where(
                ReleaseSetDeploymentRow.release_set_id == release_set_id,
                ReleaseSetDeploymentRow.operation == "APPLY",
                ReleaseSetDeploymentRow.phase == "ACTIVE",
                ReleaseSetDeploymentRow.rollout_percent == 100,
            )
            .limit(1)
        )
        return row is not None


class SessionPerCallReleaseSetDeploymentStore:
    """Durable service-facing facade; every operation owns its transaction."""

    durability_mode = "DURABLE"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        self._session_factory = session_factory

    async def get_by_idempotency(self, idempotency_key: str) -> ReleaseSetDeploymentReceipt | None:
        async with self._session_factory() as session:
            return await SqlAlchemyReleaseSetDeploymentStore(session).get_by_idempotency(
                idempotency_key
            )

    async def get_by_receipt_id(self, receipt_id: str) -> ReleaseSetDeploymentReceipt | None:
        async with self._session_factory() as session:
            return await SqlAlchemyReleaseSetDeploymentStore(session).get_by_receipt_id(receipt_id)

    async def append(self, receipt: ReleaseSetDeploymentReceipt) -> ReleaseSetDeploymentReceipt:
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyReleaseSetDeploymentStore(session).append(receipt)

    async def append_if_current(
        self,
        receipt: ReleaseSetDeploymentReceipt,
        *,
        expected_effective_sequence: int,
    ) -> ReleaseSetDeploymentReceipt:
        async with self._session_factory() as session, session.begin():
            return await SqlAlchemyReleaseSetDeploymentStore(session).append_if_current(
                receipt,
                expected_effective_sequence=expected_effective_sequence,
            )

    async def latest_effective(
        self, *, environment: str, use_case: str, data_class: str
    ) -> ReleaseSetDeploymentReceipt | None:
        async with self._session_factory() as session:
            return await SqlAlchemyReleaseSetDeploymentStore(session).latest_effective(
                environment=environment,
                use_case=use_case,
                data_class=data_class,
            )

    async def get_active_binding(
        self, *, environment: str, use_case: str, data_class: str
    ) -> ActiveReleaseBinding | None:
        async with self._session_factory() as session:
            return await SqlAlchemyReleaseSetDeploymentStore(session).get_active_binding(
                environment=environment,
                use_case=use_case,
                data_class=data_class,
            )

    async def was_active(self, release_set_id: str) -> bool:
        async with self._session_factory() as session:
            return await SqlAlchemyReleaseSetDeploymentStore(session).was_active(release_set_id)


class InMemoryReleaseSetTransitionCoordinator:
    durability_mode = "IN_MEMORY"

    def __init__(
        self,
        store: InMemoryReleaseSetDeploymentStore,
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._store = store
        self._clock = clock or (lambda: datetime.now(UTC))
        self._claims: dict[tuple[str, str, str], ReleaseSetTransitionClaim] = {}
        self._reconciliation: dict[
            str, tuple[int, str | None, datetime | None, datetime | None]
        ] = {}
        self._lock = asyncio.Lock()

    async def prepare(
        self,
        control: ReleaseSetControlEvent,
        *,
        idempotency_key: str,
    ) -> ReleaseSetTransitionClaim:
        scope = _control_scope(control)
        async with self._lock:
            existing = self._claims.get(scope)
            if existing is not None and existing.idempotency_key == idempotency_key:
                _assert_claim_matches_control(existing, control)
                return existing
            if existing is not None and existing.status != "COMMITTED":
                raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_IN_PROGRESS")
            latest = await self._store.latest_effective(
                environment=control.environment,
                use_case=control.use_case,
                data_class=control.data_class,
            )
            current_sequence = latest.sequence if latest is not None else 0
            if current_sequence != control.expected_effective_sequence:
                raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_STALE_CONTROL")
            now = _aware_transition_time(self._clock())
            claim = _new_transition_claim(control, idempotency_key, now)
            self._claims[scope] = claim
            self._reconciliation[claim.transition_id] = (0, None, None, None)
            return claim

    async def acknowledge(
        self,
        claim: ReleaseSetTransitionClaim,
        acknowledgement: ReleaseSetDeploymentAcknowledgement,
    ) -> ReleaseSetTransitionClaim:
        async with self._lock:
            current = self._require_current(claim)
            if current.status == "ACKNOWLEDGED":
                if current.acknowledgement() != acknowledgement:
                    raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_ACK_CONFLICT")
                return current
            if current.status not in {"PREPARED", "UNKNOWN"}:
                raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_STATE_INVALID")
            updated = replace(
                current,
                status="ACKNOWLEDGED",
                acknowledged_release_set_id=(acknowledgement.acknowledged_release_set_id),
                applied_config_digest=acknowledgement.applied_config_digest,
                external_ref=acknowledgement.external_ref,
                error_code=None,
                updated_at=_aware_transition_time(self._clock()),
            )
            self._claims[_claim_scope(current)] = updated
            return updated

    async def commit(
        self,
        claim: ReleaseSetTransitionClaim,
        receipt: ReleaseSetDeploymentReceipt,
    ) -> ReleaseSetDeploymentReceipt:
        async with self._lock:
            current = self._require_current(claim)
            if current.status == "COMMITTED":
                existing = await self._store.get_by_idempotency(current.idempotency_key)
                if existing is None:
                    raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_RECEIPT_MISSING")
                return existing
            if current.status != "ACKNOWLEDGED":
                raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_NOT_ACKNOWLEDGED")
            stored = await self._store.append_if_current(
                receipt,
                expected_effective_sequence=current.expected_effective_sequence,
            )
            self._claims[_claim_scope(current)] = replace(
                current,
                status="COMMITTED",
                updated_at=_aware_transition_time(self._clock()),
            )
            self._reconciliation.pop(current.transition_id, None)
            return stored

    async def mark_unknown(
        self,
        claim: ReleaseSetTransitionClaim,
        *,
        error_code: str,
    ) -> ReleaseSetTransitionClaim:
        async with self._lock:
            current = self._require_current(claim)
            if current.status == "UNKNOWN" and current.error_code == error_code:
                return current
            if current.status != "PREPARED":
                raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_STATE_INVALID")
            updated = replace(
                current,
                status="UNKNOWN",
                error_code=error_code[:128],
                updated_at=_aware_transition_time(self._clock()),
            )
            self._claims[_claim_scope(current)] = updated
            return updated

    async def get_by_idempotency(self, idempotency_key: str) -> ReleaseSetTransitionClaim | None:
        async with self._lock:
            return next(
                (
                    claim
                    for claim in self._claims.values()
                    if claim.idempotency_key == idempotency_key
                ),
                None,
            )

    async def claim_reconcilable(
        self,
        *,
        environment: str,
        worker_id: str,
        now: datetime,
        stale_after: timedelta,
        lease_ttl: timedelta,
        limit: int,
    ) -> tuple[ReleaseSetReconciliationLease, ...]:
        _validate_reconciliation_claim(
            environment,
            worker_id,
            now,
            stale_after,
            lease_ttl,
            limit,
        )
        async with self._lock:
            cutoff = now - stale_after
            eligible: list[ReleaseSetTransitionClaim] = []
            for claim in self._claims.values():
                _, _, lease_until, next_at = self._reconciliation.get(
                    claim.transition_id,
                    (0, None, None, None),
                )
                if (
                    claim.environment == environment
                    and claim.status in {"PREPARED", "UNKNOWN", "ACKNOWLEDGED"}
                    and claim.updated_at <= cutoff
                    and (lease_until is None or lease_until <= now)
                    and (next_at is None or next_at <= now)
                ):
                    eligible.append(claim)
            leases: list[ReleaseSetReconciliationLease] = []
            for claim in sorted(
                eligible,
                key=lambda item: (item.updated_at, item.transition_id),
            )[:limit]:
                attempts, _, _, _ = self._reconciliation.get(
                    claim.transition_id,
                    (0, None, None, None),
                )
                lease_until = now + lease_ttl
                attempt = attempts + 1
                self._reconciliation[claim.transition_id] = (
                    attempt,
                    worker_id,
                    lease_until,
                    None,
                )
                leases.append(
                    ReleaseSetReconciliationLease(
                        transition=claim,
                        attempt=attempt,
                        worker_id=worker_id,
                        lease_until=lease_until,
                    )
                )
            return tuple(leases)

    async def reschedule_reconciliation(
        self,
        lease: ReleaseSetReconciliationLease,
        *,
        next_reconcile_at: datetime,
        error_code: str,
    ) -> ReleaseSetTransitionClaim:
        next_at = _aware_transition_time(next_reconcile_at)
        if not error_code.strip():
            raise ReleaseSetDeploymentError("RECONCILIATION_ERROR_CODE_REQUIRED")
        async with self._lock:
            current = self._require_current(lease.transition)
            metadata = self._reconciliation.get(current.transition_id)
            if metadata is None or metadata[1] != lease.worker_id:
                raise ReleaseSetDeploymentError("RECONCILIATION_LEASE_LOST")
            updated = replace(
                current,
                error_code=error_code[:128],
            )
            self._claims[_claim_scope(current)] = updated
            self._reconciliation[current.transition_id] = (
                metadata[0],
                None,
                None,
                next_at,
            )
            return updated

    def _require_current(self, claim: ReleaseSetTransitionClaim) -> ReleaseSetTransitionClaim:
        current = self._claims.get(_claim_scope(claim))
        if current is None or current.transition_id != claim.transition_id:
            raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_CLAIM_STALE")
        return current


class SqlAlchemyReleaseSetTransitionCoordinator:
    durability_mode = "DURABLE"

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        *,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        self._session_factory = session_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    async def prepare(
        self,
        control: ReleaseSetControlEvent,
        *,
        idempotency_key: str,
    ) -> ReleaseSetTransitionClaim:
        try:
            async with self._session_factory() as session, session.begin():
                row = await session.get(
                    ReleaseSetTransitionRow,
                    _control_scope(control),
                    with_for_update=True,
                )
                if row is not None and row.idempotency_key == idempotency_key:
                    claim = _stored_transition(row)
                    _assert_claim_matches_control(claim, control)
                    return claim
                if row is not None and row.status != "COMMITTED":
                    raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_IN_PROGRESS")
                projection = await session.get(
                    ActiveReleaseBindingRow,
                    _control_scope(control),
                    with_for_update=True,
                )
                current_sequence = projection.deployment_sequence if projection is not None else 0
                if current_sequence != control.expected_effective_sequence:
                    raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_STALE_CONTROL")
                now = _aware_transition_time(self._clock())
                claim = _new_transition_claim(control, idempotency_key, now)
                if row is None:
                    session.add(_transition_row(claim))
                else:
                    _replace_transition_row(row, claim)
                await session.flush()
                return claim
        except IntegrityError as error:
            raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_CONCURRENT_CONFLICT") from error

    async def acknowledge(
        self,
        claim: ReleaseSetTransitionClaim,
        acknowledgement: ReleaseSetDeploymentAcknowledgement,
    ) -> ReleaseSetTransitionClaim:
        async with self._session_factory() as session, session.begin():
            row = await self._locked_claim(session, claim)
            current = _stored_transition(row)
            if current.status == "ACKNOWLEDGED":
                if current.acknowledgement() != acknowledgement:
                    raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_ACK_CONFLICT")
                return current
            if current.status not in {"PREPARED", "UNKNOWN"}:
                raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_STATE_INVALID")
            row.status = "ACKNOWLEDGED"
            row.acknowledged_release_set_id = acknowledgement.acknowledged_release_set_id
            row.applied_config_digest = acknowledgement.applied_config_digest
            row.external_ref = acknowledgement.external_ref
            row.error_code = None
            row.updated_at = _aware_transition_time(self._clock())
            await session.flush()
            return _stored_transition(row)

    async def commit(
        self,
        claim: ReleaseSetTransitionClaim,
        receipt: ReleaseSetDeploymentReceipt,
    ) -> ReleaseSetDeploymentReceipt:
        async with self._session_factory() as session, session.begin():
            row = await self._locked_claim(session, claim)
            current = _stored_transition(row)
            store = SqlAlchemyReleaseSetDeploymentStore(session)
            if current.status == "COMMITTED":
                existing = await store.get_by_idempotency(current.idempotency_key)
                if existing is None:
                    raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_RECEIPT_MISSING")
                return existing
            if current.status != "ACKNOWLEDGED":
                raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_NOT_ACKNOWLEDGED")
            stored = await store.append_if_current(
                receipt,
                expected_effective_sequence=current.expected_effective_sequence,
            )
            row.status = "COMMITTED"
            row.reconciliation_lease_owner = None
            row.reconciliation_lease_until = None
            row.next_reconcile_at = None
            row.updated_at = _aware_transition_time(self._clock())
            await session.flush()
            return stored

    async def mark_unknown(
        self,
        claim: ReleaseSetTransitionClaim,
        *,
        error_code: str,
    ) -> ReleaseSetTransitionClaim:
        async with self._session_factory() as session, session.begin():
            row = await self._locked_claim(session, claim)
            current = _stored_transition(row)
            if current.status == "UNKNOWN" and current.error_code == error_code:
                return current
            if current.status != "PREPARED":
                raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_STATE_INVALID")
            row.status = "UNKNOWN"
            row.error_code = error_code[:128]
            row.updated_at = _aware_transition_time(self._clock())
            await session.flush()
            return _stored_transition(row)

    async def get_by_idempotency(self, idempotency_key: str) -> ReleaseSetTransitionClaim | None:
        async with self._session_factory() as session:
            row = await session.scalar(
                select(ReleaseSetTransitionRow).where(
                    ReleaseSetTransitionRow.idempotency_key == idempotency_key
                )
            )
            return _stored_transition(row) if row is not None else None

    async def claim_reconcilable(
        self,
        *,
        environment: str,
        worker_id: str,
        now: datetime,
        stale_after: timedelta,
        lease_ttl: timedelta,
        limit: int,
    ) -> tuple[ReleaseSetReconciliationLease, ...]:
        _validate_reconciliation_claim(
            environment,
            worker_id,
            now,
            stale_after,
            lease_ttl,
            limit,
        )
        cutoff = now - stale_after
        async with self._session_factory() as session, session.begin():
            rows = tuple(
                (
                    await session.scalars(
                        select(ReleaseSetTransitionRow)
                        .where(
                            ReleaseSetTransitionRow.environment == environment,
                            ReleaseSetTransitionRow.status.in_(
                                ("PREPARED", "UNKNOWN", "ACKNOWLEDGED")
                            ),
                            ReleaseSetTransitionRow.updated_at <= cutoff,
                            or_(
                                ReleaseSetTransitionRow.next_reconcile_at.is_(None),
                                ReleaseSetTransitionRow.next_reconcile_at <= now,
                            ),
                            or_(
                                ReleaseSetTransitionRow.reconciliation_lease_until.is_(None),
                                ReleaseSetTransitionRow.reconciliation_lease_until <= now,
                            ),
                        )
                        .order_by(
                            ReleaseSetTransitionRow.updated_at,
                            ReleaseSetTransitionRow.transition_id,
                        )
                        .limit(limit)
                        .with_for_update(skip_locked=True)
                    )
                ).all()
            )
            leases = []
            for row in rows:
                row.reconciliation_attempts += 1
                row.reconciliation_lease_owner = worker_id
                row.reconciliation_lease_until = now + lease_ttl
                row.next_reconcile_at = None
                leases.append(
                    ReleaseSetReconciliationLease(
                        transition=_stored_transition(row),
                        attempt=row.reconciliation_attempts,
                        worker_id=worker_id,
                        lease_until=now + lease_ttl,
                    )
                )
            await session.flush()
            return tuple(leases)

    async def reschedule_reconciliation(
        self,
        lease: ReleaseSetReconciliationLease,
        *,
        next_reconcile_at: datetime,
        error_code: str,
    ) -> ReleaseSetTransitionClaim:
        next_at = _aware_transition_time(next_reconcile_at)
        if not error_code.strip():
            raise ReleaseSetDeploymentError("RECONCILIATION_ERROR_CODE_REQUIRED")
        async with self._session_factory() as session, session.begin():
            row = await self._locked_claim(session, lease.transition)
            if row.reconciliation_lease_owner != lease.worker_id:
                raise ReleaseSetDeploymentError("RECONCILIATION_LEASE_LOST")
            row.reconciliation_lease_owner = None
            row.reconciliation_lease_until = None
            row.next_reconcile_at = next_at
            row.error_code = error_code[:128]
            await session.flush()
            return _stored_transition(row)

    async def _locked_claim(
        self,
        session: AsyncSession,
        claim: ReleaseSetTransitionClaim,
    ) -> ReleaseSetTransitionRow:
        row = await session.get(
            ReleaseSetTransitionRow,
            _claim_scope(claim),
            with_for_update=True,
        )
        if row is None or row.transition_id != claim.transition_id:
            raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_CLAIM_STALE")
        return row


@dataclass(frozen=True, slots=True)
class FamilyExperienceReleaseSetDeploymentService:
    port: ReleaseSetDeploymentPort
    store: ReleaseSetDeploymentStore
    controls: ReleaseSetControlReader
    transitions: ReleaseSetTransitionCoordinator | None = None
    clock: Callable[[], datetime] | None = None

    def __post_init__(self) -> None:
        if self.transitions is not None:
            return
        if isinstance(self.store, InMemoryReleaseSetDeploymentStore):
            coordinator = self.store._transition_coordinator
            if self.clock is not None:
                # The coordinator is constructed eagerly inside the store's
                # ``__init__``, before this service (and any injected test
                # clock) exists. Keep both in lockstep so transition
                # timestamps used for reconciliation eligibility agree with
                # the clock the deployment service itself observes.
                coordinator._clock = self.clock
            object.__setattr__(self, "transitions", coordinator)
            return
        raise ReleaseSetDeploymentError("DURABLE_RELEASE_TRANSITION_COORDINATOR_REQUIRED")

    async def apply(
        self,
        release_set: FamilyExperienceReleaseSet,
        authorization: ReleaseSetDeploymentAuthorization,
        *,
        phase: ReleaseSetDeploymentPhase,
        rollout_percent: int,
        idempotency_key: str,
    ) -> ReleaseSetDeploymentReceipt:
        _validate_inputs(release_set, authorization)
        _validate_apply(phase, rollout_percent, idempotency_key)
        control = await self._control(
            authorization,
            source=release_set,
            target=None,
            operation="APPLY",
            phase=phase,
            rollout_percent=rollout_percent,
        )
        existing = await self.store.get_by_idempotency(idempotency_key)
        if existing is not None:
            if (
                existing.release_set_id != release_set.release_set_id
                or existing.operation != "APPLY"
                or existing.phase != phase
                or existing.rollout_percent != rollout_percent
                or existing.control_id != authorization.control_id
                or existing.actor_id != authorization.actor_id
            ):
                raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_CONFLICT")
            return existing
        await self._assert_expected_effective(control, release_set)
        transitions = self._transitions()
        claim = await transitions.prepare(control, idempotency_key=idempotency_key)
        acknowledgement = claim.acknowledgement()
        if acknowledgement is None:
            try:
                acknowledgement = await self.port.apply(
                    release_set,
                    phase=phase,
                    rollout_percent=rollout_percent,
                    idempotency_key=idempotency_key,
                    transition_id=claim.transition_id,
                    control_id=claim.control_id,
                    expected_effective_sequence=claim.expected_effective_sequence,
                )
            except Exception as error:
                await transitions.mark_unknown(
                    claim,
                    error_code=type(error).__name__,
                )
                raise
        _validate_acknowledgement(release_set, acknowledgement, claim)
        claim = await transitions.acknowledge(claim, acknowledgement)
        return await transitions.commit(
            claim,
            _receipt(
                release_set,
                authorization,
                acknowledgement,
                operation="APPLY",
                phase=phase,
                rollout_percent=rollout_percent,
                idempotency_key=idempotency_key,
                target_release_set_id=None,
                created_at=self._now(),
            ),
        )

    async def reconcile(
        self,
        source: FamilyExperienceReleaseSet,
        acknowledgement: ReleaseSetDeploymentAcknowledgement,
        *,
        idempotency_key: str,
        target: FamilyExperienceReleaseSet | None = None,
    ) -> ReleaseSetDeploymentReceipt:
        """Commit an externally observed result under its original human control."""

        if not isinstance(source, FamilyExperienceReleaseSet):
            raise ReleaseSetDeploymentError("RELEASE_SET_REQUIRED")
        if not isinstance(acknowledgement, ReleaseSetDeploymentAcknowledgement):
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_ACK_REQUIRED")
        if not idempotency_key.strip():
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_KEY_REQUIRED")
        transitions = self._transitions()
        claim = await transitions.get_by_idempotency(idempotency_key)
        if claim is None:
            raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_NOT_FOUND")
        existing = await self.store.get_by_idempotency(idempotency_key)
        if existing is not None:
            return existing
        control = await self.controls.get(claim.control_id)
        if control is None:
            raise ReleaseSetDeploymentError("RELEASE_SET_CONTROL_NOT_FOUND")
        _assert_claim_matches_control(claim, control)
        if claim.source_release_set_id != source.release_set_id:
            raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_SOURCE_MISMATCH")
        expected = source
        if claim.operation == "ROLLBACK":
            if (
                target is None
                or claim.target_release_set_id != target.release_set_id
                or _scope(source) != _scope(target)
            ):
                raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_TARGET_MISMATCH")
            expected = target
        elif target is not None:
            raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_TARGET_UNEXPECTED")
        _validate_acknowledgement(expected, acknowledgement, claim)
        claim = await transitions.acknowledge(claim, acknowledgement)
        authorization = ReleaseSetDeploymentAuthorization(
            claim.control_id,
            control.actor_id,
        )
        return await transitions.commit(
            claim,
            _receipt(
                source,
                authorization,
                acknowledgement,
                operation=claim.operation,
                phase=claim.phase,
                rollout_percent=claim.rollout_percent,
                idempotency_key=claim.idempotency_key,
                target_release_set_id=claim.target_release_set_id,
                created_at=self._now(),
            ),
        )

    async def rollback(
        self,
        source: FamilyExperienceReleaseSet,
        target: FamilyExperienceReleaseSet,
        authorization: ReleaseSetDeploymentAuthorization,
        *,
        idempotency_key: str,
    ) -> ReleaseSetDeploymentReceipt:
        _validate_inputs(source, authorization)
        if not isinstance(target, FamilyExperienceReleaseSet):
            raise ReleaseSetDeploymentError("RELEASE_SET_REQUIRED")
        if source.release_set_id == target.release_set_id:
            raise ReleaseSetDeploymentError("ROLLBACK_TARGET_MUST_DIFFER")
        if _scope(source) != _scope(target):
            raise ReleaseSetDeploymentError("ROLLBACK_SCOPE_MISMATCH")
        if not idempotency_key.strip():
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_KEY_REQUIRED")
        control = await self._control(
            authorization,
            source=source,
            target=target,
            operation="ROLLBACK",
            phase="ROLLED_BACK",
            rollout_percent=0,
        )
        if not await self.store.was_active(target.release_set_id):
            raise ReleaseSetDeploymentError("ROLLBACK_TARGET_WAS_NOT_ACTIVE")
        existing = await self.store.get_by_idempotency(idempotency_key)
        if existing is not None:
            if (
                existing.release_set_id != source.release_set_id
                or existing.target_release_set_id != target.release_set_id
                or existing.operation != "ROLLBACK"
                or existing.control_id != authorization.control_id
                or existing.actor_id != authorization.actor_id
            ):
                raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_CONFLICT")
            return existing
        await self._assert_expected_effective(control, source, require_source=True)
        transitions = self._transitions()
        claim = await transitions.prepare(control, idempotency_key=idempotency_key)
        acknowledgement = claim.acknowledgement()
        if acknowledgement is None:
            try:
                acknowledgement = await self.port.rollback(
                    source,
                    target,
                    idempotency_key=idempotency_key,
                    transition_id=claim.transition_id,
                    control_id=claim.control_id,
                    expected_effective_sequence=claim.expected_effective_sequence,
                )
            except Exception as error:
                await transitions.mark_unknown(
                    claim,
                    error_code=type(error).__name__,
                )
                raise
        _validate_acknowledgement(target, acknowledgement, claim)
        claim = await transitions.acknowledge(claim, acknowledgement)
        return await transitions.commit(
            claim,
            _receipt(
                source,
                authorization,
                acknowledgement,
                operation="ROLLBACK",
                phase="ROLLED_BACK",
                rollout_percent=0,
                idempotency_key=idempotency_key,
                target_release_set_id=target.release_set_id,
                created_at=self._now(),
            ),
        )

    def _transitions(self) -> ReleaseSetTransitionCoordinator:
        if self.transitions is None:  # pragma: no cover - constructor invariant
            raise ReleaseSetDeploymentError("RELEASE_TRANSITION_COORDINATOR_REQUIRED")
        return self.transitions

    def _now(self) -> datetime:
        value = self.clock() if self.clock is not None else datetime.now(UTC)
        if value.tzinfo is None or value.utcoffset() is None:
            raise ReleaseSetDeploymentError("DEPLOYMENT_TIME_MUST_BE_AWARE")
        return value

    async def _control(
        self,
        authorization: ReleaseSetDeploymentAuthorization,
        *,
        source: FamilyExperienceReleaseSet,
        target: FamilyExperienceReleaseSet | None,
        operation: ReleaseSetDeploymentOperation,
        phase: ReleaseSetDeploymentPhase,
        rollout_percent: int,
    ) -> ReleaseSetControlEvent:
        control = await self.controls.get(authorization.control_id)
        effective = target if operation == "ROLLBACK" else source
        expected = (
            operation,
            phase,
            rollout_percent,
            source.release_set_id,
            target.release_set_id if target is not None else None,
            source.environment,
            source.use_case,
            source.data_class,
            effective.runtime_config_digest if effective is not None else "",
            authorization.actor_id,
        )
        observed = (
            (
                control.kind,
                control.phase,
                control.rollout_percent,
                control.source_release_set_id,
                control.target_release_set_id,
                control.environment,
                control.use_case,
                control.data_class,
                control.runtime_config_digest,
                control.actor_id,
            )
            if control is not None
            else None
        )
        if observed != expected:
            raise ReleaseSetDeploymentError("RELEASE_SET_SIGNED_CONTROL_MISMATCH")
        return control

    async def _assert_expected_effective(
        self,
        control: ReleaseSetControlEvent,
        source: FamilyExperienceReleaseSet,
        *,
        require_source: bool = False,
    ) -> None:
        latest = await self.store.latest_effective(
            environment=source.environment,
            use_case=source.use_case,
            data_class=source.data_class,
        )
        sequence = latest.sequence if latest is not None else 0
        if control.expected_effective_sequence != sequence:
            raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_STALE_CONTROL")
        if require_source:
            if latest is None:
                raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_SOURCE_NOT_ACTIVE")
            effective_id = (
                latest.release_set_id
                if latest.operation == "APPLY"
                else latest.target_release_set_id
            )
            if effective_id != source.release_set_id:
                raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_SOURCE_NOT_ACTIVE")


def replace_sequence(
    receipt: ReleaseSetDeploymentReceipt, sequence: int
) -> ReleaseSetDeploymentReceipt:
    return replace(receipt, sequence=sequence)


def _control_scope(control: ReleaseSetControlEvent) -> tuple[str, str, str]:
    return control.environment, control.use_case, control.data_class


def _claim_scope(claim: ReleaseSetTransitionClaim) -> tuple[str, str, str]:
    return claim.environment, claim.use_case, claim.data_class


def _aware_transition_time(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_TIME_MUST_BE_AWARE")
    return value


def _new_transition_claim(
    control: ReleaseSetControlEvent,
    idempotency_key: str,
    now: datetime,
) -> ReleaseSetTransitionClaim:
    if not idempotency_key.strip():
        raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_KEY_REQUIRED")
    return ReleaseSetTransitionClaim(
        transition_id=uuid4().hex,
        idempotency_key=idempotency_key,
        control_id=control.control_id,
        environment=control.environment,
        use_case=control.use_case,
        data_class=control.data_class,
        operation=control.kind,
        phase=control.phase,  # type: ignore[arg-type]
        rollout_percent=control.rollout_percent,
        source_release_set_id=control.source_release_set_id,
        target_release_set_id=control.target_release_set_id,
        runtime_config_digest=control.runtime_config_digest,
        expected_effective_sequence=control.expected_effective_sequence,
        status="PREPARED",
        acknowledged_release_set_id=None,
        applied_config_digest=None,
        external_ref=None,
        error_code=None,
        created_at=now,
        updated_at=now,
    )


def _assert_claim_matches_control(
    claim: ReleaseSetTransitionClaim,
    control: ReleaseSetControlEvent,
) -> None:
    observed = (
        claim.control_id,
        claim.environment,
        claim.use_case,
        claim.data_class,
        claim.operation,
        claim.phase,
        claim.rollout_percent,
        claim.source_release_set_id,
        claim.target_release_set_id,
        claim.runtime_config_digest,
        claim.expected_effective_sequence,
    )
    expected = (
        control.control_id,
        control.environment,
        control.use_case,
        control.data_class,
        control.kind,
        control.phase,
        control.rollout_percent,
        control.source_release_set_id,
        control.target_release_set_id,
        control.runtime_config_digest,
        control.expected_effective_sequence,
    )
    if observed != expected:
        raise ReleaseSetDeploymentError("RELEASE_SET_TRANSITION_CONTROL_CONFLICT")


def _transition_row(claim: ReleaseSetTransitionClaim) -> ReleaseSetTransitionRow:
    return ReleaseSetTransitionRow(
        environment=claim.environment,
        use_case=claim.use_case,
        data_class=claim.data_class,
        transition_id=claim.transition_id,
        idempotency_key=claim.idempotency_key,
        control_id=claim.control_id,
        operation=claim.operation,
        phase=claim.phase,
        rollout_percent=claim.rollout_percent,
        source_release_set_id=claim.source_release_set_id,
        target_release_set_id=claim.target_release_set_id,
        runtime_config_digest=claim.runtime_config_digest,
        expected_effective_sequence=claim.expected_effective_sequence,
        status=claim.status,
        acknowledged_release_set_id=claim.acknowledged_release_set_id,
        applied_config_digest=claim.applied_config_digest,
        external_ref=claim.external_ref,
        error_code=claim.error_code,
        created_at=claim.created_at,
        updated_at=claim.updated_at,
    )


def _replace_transition_row(
    row: ReleaseSetTransitionRow,
    claim: ReleaseSetTransitionClaim,
) -> None:
    replacement = _transition_row(claim)
    reconciliation_columns = {
        "reconciliation_attempts",
        "reconciliation_lease_owner",
        "reconciliation_lease_until",
        "next_reconcile_at",
    }
    for column in ReleaseSetTransitionRow.__table__.columns:
        if column.name in reconciliation_columns:
            continue
        setattr(row, column.name, getattr(replacement, column.name))
    row.reconciliation_attempts = 0
    row.reconciliation_lease_owner = None
    row.reconciliation_lease_until = None
    row.next_reconcile_at = None


def _stored_transition(row: ReleaseSetTransitionRow) -> ReleaseSetTransitionClaim:
    return ReleaseSetTransitionClaim(
        transition_id=row.transition_id,
        idempotency_key=row.idempotency_key,
        control_id=row.control_id,
        environment=row.environment,
        use_case=row.use_case,
        data_class=row.data_class,
        operation=row.operation,  # type: ignore[arg-type]
        phase=row.phase,  # type: ignore[arg-type]
        rollout_percent=row.rollout_percent,
        source_release_set_id=row.source_release_set_id,
        target_release_set_id=row.target_release_set_id,
        runtime_config_digest=row.runtime_config_digest,
        expected_effective_sequence=row.expected_effective_sequence,
        status=row.status,  # type: ignore[arg-type]
        acknowledged_release_set_id=row.acknowledged_release_set_id,
        applied_config_digest=row.applied_config_digest,
        external_ref=row.external_ref,
        error_code=row.error_code,
        created_at=_db_transition_time(row.created_at),
        updated_at=_db_transition_time(row.updated_at),
    )


def _db_transition_time(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _validate_apply(
    phase: ReleaseSetDeploymentPhase, rollout_percent: int, idempotency_key: str
) -> None:
    valid = (phase == "CANARY" and 1 <= rollout_percent <= 99) or (
        phase == "ACTIVE" and rollout_percent == 100
    )
    if not valid:
        raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_PHASE_INVALID")
    if not idempotency_key.strip():
        raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_KEY_REQUIRED")


def _validate_reconciliation_claim(
    environment: str,
    worker_id: str,
    now: datetime,
    stale_after: timedelta,
    lease_ttl: timedelta,
    limit: int,
) -> None:
    if not environment.strip() or not worker_id.strip():
        raise ReleaseSetDeploymentError("RECONCILIATION_IDENTITY_REQUIRED")
    _aware_transition_time(now)
    if stale_after < timedelta(0) or lease_ttl <= timedelta(0):
        raise ReleaseSetDeploymentError("RECONCILIATION_DURATION_INVALID")
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 100:
        raise ReleaseSetDeploymentError("RECONCILIATION_LIMIT_INVALID")


def _validate_inputs(
    release_set: FamilyExperienceReleaseSet,
    authorization: ReleaseSetDeploymentAuthorization,
) -> None:
    if not isinstance(release_set, FamilyExperienceReleaseSet):
        raise ReleaseSetDeploymentError("RELEASE_SET_REQUIRED")
    if not isinstance(authorization, ReleaseSetDeploymentAuthorization):
        raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_AUTH_REQUIRED")


def _validate_acknowledgement(
    expected: FamilyExperienceReleaseSet,
    acknowledgement: ReleaseSetDeploymentAcknowledgement,
    claim: ReleaseSetTransitionClaim,
) -> None:
    if (
        acknowledgement.acknowledged_release_set_id != expected.release_set_id
        or acknowledgement.applied_config_digest != expected.runtime_config_digest
        or acknowledgement.transition_id != claim.transition_id
        or acknowledgement.control_id != claim.control_id
        or acknowledgement.expected_effective_sequence != claim.expected_effective_sequence
        or not acknowledgement.external_ref.strip()
    ):
        raise ReleaseSetDeploymentError("RELEASE_SET_DEPLOYMENT_ACK_MISMATCH")


def _receipt(
    release_set: FamilyExperienceReleaseSet,
    authorization: ReleaseSetDeploymentAuthorization,
    acknowledgement: ReleaseSetDeploymentAcknowledgement,
    *,
    operation: ReleaseSetDeploymentOperation,
    phase: ReleaseSetDeploymentPhase,
    rollout_percent: int,
    idempotency_key: str,
    target_release_set_id: str | None,
    created_at: datetime,
) -> ReleaseSetDeploymentReceipt:
    return ReleaseSetDeploymentReceipt(
        sequence=0,
        receipt_id=uuid4().hex,
        idempotency_key=idempotency_key,
        release_set_id=release_set.release_set_id,
        target_release_set_id=target_release_set_id,
        environment=release_set.environment,
        use_case=release_set.use_case,
        data_class=release_set.data_class,
        operation=operation,
        phase=phase,
        rollout_percent=rollout_percent,
        control_id=authorization.control_id,
        actor_id=authorization.actor_id,
        applied_config_digest=acknowledgement.applied_config_digest,
        acknowledged_release_set_id=acknowledgement.acknowledged_release_set_id,
        external_ref=acknowledgement.external_ref,
        created_at=created_at,
    )


def _scope(value: FamilyExperienceReleaseSet) -> tuple[str, str, str]:
    return value.environment, value.use_case, value.data_class


def _receipt_scope(value: ReleaseSetDeploymentReceipt) -> tuple[str, str, str]:
    return value.environment, value.use_case, value.data_class


def _row(value: ReleaseSetDeploymentReceipt) -> ReleaseSetDeploymentRow:
    return ReleaseSetDeploymentRow(
        receipt_id=value.receipt_id,
        idempotency_key=value.idempotency_key,
        release_set_id=value.release_set_id,
        target_release_set_id=value.target_release_set_id,
        environment=value.environment,
        use_case=value.use_case,
        data_class=value.data_class,
        operation=value.operation,
        phase=value.phase,
        rollout_percent=value.rollout_percent,
        control_id=value.control_id,
        actor_id=value.actor_id,
        applied_config_digest=value.applied_config_digest,
        acknowledged_release_set_id=value.acknowledged_release_set_id,
        external_ref=value.external_ref,
        created_at=value.created_at,
    )


def _stored(row: ReleaseSetDeploymentRow) -> ReleaseSetDeploymentReceipt:
    created_at = row.created_at
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return ReleaseSetDeploymentReceipt(
        sequence=row.sequence,
        receipt_id=row.receipt_id,
        idempotency_key=row.idempotency_key,
        release_set_id=row.release_set_id,
        target_release_set_id=row.target_release_set_id,
        environment=row.environment,
        use_case=row.use_case,
        data_class=row.data_class,
        operation=row.operation,  # type: ignore[arg-type]
        phase=row.phase,  # type: ignore[arg-type]
        rollout_percent=row.rollout_percent,
        control_id=row.control_id,
        actor_id=row.actor_id,
        applied_config_digest=row.applied_config_digest,
        acknowledged_release_set_id=row.acknowledged_release_set_id,
        external_ref=row.external_ref,
        created_at=created_at,
    )


def _active_binding(receipt: ReleaseSetDeploymentReceipt) -> ActiveReleaseBinding:
    release_set_id = (
        receipt.release_set_id if receipt.operation == "APPLY" else receipt.target_release_set_id
    )
    if release_set_id is None:  # pragma: no cover - receipt invariant
        raise ReleaseSetDeploymentError("ACTIVE_RELEASE_BINDING_TARGET_REQUIRED")
    return ActiveReleaseBinding(
        environment=receipt.environment,
        use_case=receipt.use_case,
        data_class=receipt.data_class,
        release_set_id=release_set_id,
        deployment_receipt_id=receipt.receipt_id,
        deployment_sequence=receipt.sequence,
        runtime_config_digest=receipt.applied_config_digest,
        control_id=receipt.control_id,
        updated_at=receipt.created_at,
    )


def _stored_active_binding(row: ActiveReleaseBindingRow) -> ActiveReleaseBinding:
    updated_at = row.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=UTC)
    return ActiveReleaseBinding(
        environment=row.environment,
        use_case=row.use_case,
        data_class=row.data_class,
        release_set_id=row.release_set_id,
        deployment_receipt_id=row.deployment_receipt_id,
        deployment_sequence=row.deployment_sequence,
        runtime_config_digest=row.runtime_config_digest,
        control_id=row.control_id,
        updated_at=updated_at,
    )


__all__ = [
    "ActiveReleaseBinding",
    "FamilyExperienceReleaseSetDeploymentService",
    "ActiveReleaseBindingRow",
    "InMemoryReleaseSetDeploymentStore",
    "InMemoryReleaseSetTransitionCoordinator",
    "ModelInvocationFenceClaimRow",
    "ReleaseSetDeploymentAcknowledgement",
    "ReleaseSetDeploymentAuthorization",
    "ReleaseSetDeploymentBase",
    "ReleaseSetDeploymentError",
    "ReleaseSetDeploymentPort",
    "ReleaseSetDeploymentReceipt",
    "ReleaseSetDeploymentRow",
    "ReleaseSetDeploymentStore",
    "ReleaseSetReconciliationLease",
    "ReleaseSetTransitionClaim",
    "ReleaseSetTransitionCoordinator",
    "ReleaseSetTransitionRow",
    "SessionPerCallReleaseSetDeploymentStore",
    "SqlAlchemyReleaseSetDeploymentStore",
    "SqlAlchemyReleaseSetTransitionCoordinator",
]
