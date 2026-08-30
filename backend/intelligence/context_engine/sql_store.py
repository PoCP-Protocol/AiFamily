"""Durable SQL adapter for the asynchronous Context Engine port.

This adapter owns technical context projections only.  It never imports a
family aggregate and it reconstructs the public contracts before returning a
snapshot, so scope, consent, retention and provenance checks remain enforced
after a process restart.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import sqlalchemy as sa
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .async_port import AsyncContextBrokerPort
from .contracts import (
    ContextContractError,
    ContextScope,
    ContextScopeError,
    ContextSnapshot,
    DataClass,
    StateObservation,
)


class ContextPersistenceBase(DeclarativeBase):
    """Metadata for the Context Engine's technical projection tables."""


class ContextObservationRow(ContextPersistenceBase):
    __tablename__ = "ai_context_observations"

    tenant_id: Mapped[str] = mapped_column(sa.String(128), primary_key=True)
    observation_id: Mapped[str] = mapped_column(sa.String(256), primary_key=True)
    family_id: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True)
    subject_id: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True)
    dimension: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    observed_value: Mapped[str] = mapped_column(sa.Text(), nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(sa.JSON(), nullable=False)
    provenance: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    retention_policy: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    region_id: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    locale: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    data_class: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True)
    consent_version: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    consent_granted: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False)
    deletion_ref: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    correlation_id: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    causation_id: Mapped[str] = mapped_column(sa.String(256), nullable=False)


class ContextSnapshotRow(ContextPersistenceBase):
    __tablename__ = "ai_context_snapshots"

    snapshot_ref: Mapped[str] = mapped_column(sa.String(256), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True)
    region_id: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    family_id: Mapped[str] = mapped_column(sa.String(128), nullable=False, index=True)
    subject_ids: Mapped[list[str]] = mapped_column(sa.JSON(), nullable=False)
    purpose: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    data_class: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    locale: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    content_locale: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    model_locale: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    policy_locale: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    consent_granted: Mapped[bool] = mapped_column(sa.Boolean(), nullable=False)
    correlation_id: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    causation_id: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    generated_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime(timezone=True), nullable=False)
    provenance: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    deletion_ref: Mapped[str] = mapped_column(sa.String(256), nullable=False)
    source_refs: Mapped[list[str]] = mapped_column(sa.JSON(), nullable=False)


class ContextSnapshotObservationRow(ContextPersistenceBase):
    __tablename__ = "ai_context_snapshot_observations"

    snapshot_ref: Mapped[str] = mapped_column(sa.String(256), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(sa.String(128), primary_key=True)
    observation_id: Mapped[str] = mapped_column(sa.String(256), primary_key=True)
    position: Mapped[int] = mapped_column(sa.Integer(), primary_key=True)


def _aware(moment: datetime) -> datetime:
    """SQLite returns naive datetimes even for timezone-aware columns."""

    return moment.replace(tzinfo=UTC) if moment.tzinfo is None else moment


def _observation_from_row(row: ContextObservationRow) -> StateObservation:
    return StateObservation(
        observation_id=row.observation_id,
        tenant_id=row.tenant_id,
        family_id=row.family_id,
        subject_id=row.subject_id,
        dimension=row.dimension,
        observed_value=row.observed_value,
        evidence_refs=tuple(row.evidence_refs),
        provenance=row.provenance,
        observed_at=_aware(row.observed_at),
        data_class=DataClass(row.data_class),
        purpose=row.purpose,
        consent_version=row.consent_version,
        consent_granted=row.consent_granted,
        region_id=row.region_id,
        locale=row.locale,
        deletion_ref=row.deletion_ref,
        correlation_id=row.correlation_id,
        causation_id=row.causation_id,
        expires_at=_aware(row.expires_at),
        retention_policy=row.retention_policy,
    )


class AsyncSqlContextBroker(AsyncContextBrokerPort):
    """Session-per-operation durable Context Broker.

    Each method opens and commits its own short-lived session.  This keeps the
    adapter safe for request-scoped applications and makes a completed
    snapshot readable from a fresh session or another process.  A caller that
    needs atomic context + business writes should compose both ports under a
    higher-level unit of work; this adapter does not claim cross-store atomicity.
    """

    durability_mode = "DURABLE"

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        if not isinstance(session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        self._session_factory = session_factory

    async def append(self, observation: StateObservation) -> None:
        if not isinstance(observation, StateObservation):
            raise ContextContractError("STATE_OBSERVATION_REQUIRED")
        row = ContextObservationRow(
            tenant_id=observation.tenant_id,
            observation_id=observation.observation_id,
            family_id=observation.family_id,
            subject_id=observation.subject_id,
            dimension=observation.dimension,
            observed_value=observation.observed_value,
            evidence_refs=list(observation.evidence_refs),
            provenance=observation.provenance,
            observed_at=observation.observed_at,
            expires_at=observation.expires_at,
            retention_policy=observation.retention_policy or "",
            region_id=observation.region_id,
            locale=observation.locale,
            data_class=observation.data_class.value,
            purpose=observation.purpose,
            consent_version=observation.consent_version,
            consent_granted=observation.consent_granted,
            deletion_ref=observation.deletion_ref,
            correlation_id=observation.correlation_id,
            causation_id=observation.causation_id,
        )
        async with self._session_factory() as session:
            session.add(row)
            try:
                await session.commit()
            except IntegrityError as exc:
                await session.rollback()
                raise ContextContractError("OBSERVATION_ID_ALREADY_EXISTS") from exc

    async def snapshot(
        self,
        tenant_id: str | None = None,
        subject_id: str | None = None,
        *,
        scope: ContextScope | None = None,
        now: datetime | None = None,
        snapshot_ttl: timedelta = timedelta(minutes=15),
    ) -> ContextSnapshot:
        if scope is None:
            raise ContextContractError("CONTEXT_SCOPE_REQUIRED")
        scope.assert_active()
        if tenant_id is not None and tenant_id != scope.tenant_id:
            raise ContextScopeError("CROSS_TENANT_CONTEXT_QUERY")
        if subject_id is not None and subject_id not in scope.subject_ids:
            raise ContextScopeError("CONTEXT_SUBJECT_QUERY_DENIED")
        if snapshot_ttl <= timedelta(0):
            raise ContextContractError("SNAPSHOT_TTL_INVALID")
        current = now or datetime.now(UTC)
        if current.tzinfo is None:
            raise ContextContractError("snapshot timestamp requires a timezone")
        async with self._session_factory() as session:
            statement = select(ContextObservationRow).where(
                ContextObservationRow.tenant_id == scope.tenant_id,
                ContextObservationRow.family_id == scope.family_id,
                ContextObservationRow.subject_id.in_(scope.subject_ids),
                ContextObservationRow.purpose == scope.purpose,
                ContextObservationRow.consent_version == scope.consent_version,
                ContextObservationRow.consent_granted.is_(True),
                ContextObservationRow.expires_at > current,
            )
            if subject_id is not None:
                statement = statement.where(ContextObservationRow.subject_id == subject_id)
            rows = (
                await session.execute(
                    statement.order_by(
                        ContextObservationRow.observed_at,
                        ContextObservationRow.observation_id,
                    )
                )
            ).scalars().all()
            observations = tuple(_observation_from_row(row) for row in rows)
            snapshot = ContextSnapshot(
                snapshot_ref=f"context:{uuid4().hex}",
                scope=scope,
                generated_at=current,
                observations=observations,
                expires_at=current + snapshot_ttl,
                provenance="context-broker:sql",
                deletion_ref=scope.deletion_ref,
                source_refs=tuple(
                    ref for observation in observations for ref in observation.evidence_refs
                ),
            )
            session.add(
                ContextSnapshotRow(
                    snapshot_ref=snapshot.snapshot_ref,
                    tenant_id=scope.tenant_id,
                    region_id=scope.region_id,
                    family_id=scope.family_id,
                    subject_ids=list(scope.subject_ids),
                    purpose=scope.purpose,
                    consent_version=scope.consent_version,
                    data_class=scope.data_class.value,
                    locale=scope.locale,
                    content_locale=scope.content_locale,
                    model_locale=scope.model_locale,
                    policy_locale=scope.policy_locale,
                    consent_granted=scope.consent_granted,
                    correlation_id=scope.correlation_id,
                    causation_id=scope.causation_id,
                    generated_at=current,
                    expires_at=snapshot.expires_at,
                    provenance=snapshot.provenance,
                    deletion_ref=scope.deletion_ref,
                    source_refs=list(snapshot.source_refs),
                )
            )
            session.add_all(
                ContextSnapshotObservationRow(
                    snapshot_ref=snapshot.snapshot_ref,
                    tenant_id=scope.tenant_id,
                    observation_id=observation.observation_id,
                    position=position,
                )
                for position, observation in enumerate(observations)
            )
            await session.commit()
            return snapshot

    async def read(
        self,
        snapshot_ref: str,
        scope: ContextScope,
        *,
        now: datetime | None = None,
    ) -> ContextSnapshot:
        scope.assert_active()
        moment = now or datetime.now(UTC)
        if moment.tzinfo is None:
            raise ContextContractError("snapshot timestamp requires a timezone")
        async with self._session_factory() as session:
            snapshot_row = await session.get(ContextSnapshotRow, snapshot_ref)
            if snapshot_row is None:
                raise ContextContractError("CONTEXT_SNAPSHOT_NOT_FOUND")
            if snapshot_row.tenant_id != scope.tenant_id:
                raise ContextScopeError("CROSS_TENANT_CONTEXT_SNAPSHOT")
            if snapshot_row.family_id != scope.family_id:
                raise ContextScopeError("CROSS_FAMILY_CONTEXT_SNAPSHOT")
            if frozenset(snapshot_row.subject_ids) != frozenset(scope.subject_ids):
                raise ContextScopeError("CROSS_SUBJECT_CONTEXT_SNAPSHOT")
            if snapshot_row.purpose != scope.purpose:
                raise ContextContractError("CONTEXT_PURPOSE_MISMATCH")
            if snapshot_row.consent_version != scope.consent_version:
                raise ContextContractError("CONTEXT_CONSENT_VERSION_MISMATCH")
            expires_at = _aware(snapshot_row.expires_at)
            if expires_at <= moment:
                raise ContextContractError("CONTEXT_SNAPSHOT_EXPIRED")
            links = (
                await session.execute(
                    select(ContextSnapshotObservationRow)
                    .where(ContextSnapshotObservationRow.snapshot_ref == snapshot_ref)
                    .order_by(ContextSnapshotObservationRow.position)
                )
            ).scalars().all()
            observations: list[StateObservation] = []
            for link in links:
                row = await session.get(
                    ContextObservationRow,
                    (link.tenant_id, link.observation_id),
                )
                if row is not None:
                    observations.append(_observation_from_row(row))
            reconstructed_scope = ContextScope(
                tenant_id=snapshot_row.tenant_id,
                region_id=snapshot_row.region_id,
                family_id=snapshot_row.family_id,
                subject_ids=tuple(snapshot_row.subject_ids),
                purpose=snapshot_row.purpose,
                consent_version=snapshot_row.consent_version,
                consent_granted=True,
                data_class=DataClass(snapshot_row.data_class),
                locale=snapshot_row.locale,
                content_locale=snapshot_row.content_locale,
                model_locale=snapshot_row.model_locale,
                policy_locale=snapshot_row.policy_locale,
                deletion_ref=snapshot_row.deletion_ref,
                correlation_id=snapshot_row.correlation_id,
                causation_id=snapshot_row.causation_id,
            )
            return ContextSnapshot(
                snapshot_ref=snapshot_row.snapshot_ref,
                scope=reconstructed_scope,
                generated_at=_aware(snapshot_row.generated_at),
                observations=tuple(observations),
                expires_at=expires_at,
                provenance=snapshot_row.provenance,
                deletion_ref=snapshot_row.deletion_ref,
                source_refs=tuple(snapshot_row.source_refs),
            )

    async def delete_subject(self, tenant_id: str, subject_id: str) -> int:
        async with self._session_factory() as session:
            observations = (
                await session.execute(
                    select(ContextObservationRow).where(
                        ContextObservationRow.tenant_id == tenant_id,
                        ContextObservationRow.subject_id == subject_id,
                    )
                )
            ).scalars().all()
            observation_keys = {
                (row.tenant_id, row.observation_id) for row in observations
            }
            snapshots = (
                await session.execute(
                    select(ContextSnapshotRow).where(ContextSnapshotRow.tenant_id == tenant_id)
                )
            ).scalars().all()
            snapshot_refs = {
                row.snapshot_ref for row in snapshots if subject_id in row.subject_ids
            }
            if snapshot_refs:
                await session.execute(
                    delete(ContextSnapshotObservationRow).where(
                        ContextSnapshotObservationRow.snapshot_ref.in_(snapshot_refs)
                    )
                )
                await session.execute(
                    delete(ContextSnapshotRow).where(
                        ContextSnapshotRow.snapshot_ref.in_(snapshot_refs)
                    )
                )
            if observation_keys:
                await session.execute(
                    delete(ContextSnapshotObservationRow).where(
                        sa.tuple_(
                            ContextSnapshotObservationRow.tenant_id,
                            ContextSnapshotObservationRow.observation_id,
                        ).in_(observation_keys)
                    )
                )
            await session.execute(
                delete(ContextObservationRow).where(
                    ContextObservationRow.tenant_id == tenant_id,
                    ContextObservationRow.subject_id == subject_id,
                )
            )
            await session.commit()
            return len(observations)


__all__ = [
    "AsyncSqlContextBroker",
    "ContextObservationRow",
    "ContextPersistenceBase",
    "ContextSnapshotObservationRow",
    "ContextSnapshotRow",
]
