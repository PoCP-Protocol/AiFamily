"""Durable, provider-neutral memory reference store.

The memory layer persists only ``MemoryRef`` governance metadata and opaque
source references. It never stores raw prompts, media bytes, or model output.
Scope and consent checks remain owned by the shared experience contracts so a
restart does not weaken the in-memory adapter's guarantees.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Index, String, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceContractError,
    ExperienceProvenance,
    ExperienceScope,
    MemoryLevel,
    MemoryRef,
    MemoryScope,
    ProvenanceKind,
    ScopeMismatchError,
)
from backend.intelligence.experience.memory_adapter import MemoryDeletionProof


class MemoryPersistenceBase(DeclarativeBase):
    """Metadata boundary for durable memory projection tables."""


class MemoryRefRow(MemoryPersistenceBase):
    __tablename__ = "ai_memories"
    __table_args__ = (
        Index("ix_ai_memories_scope_expiry", "tenant_id", "family_id", "expires_at"),
        Index("ix_ai_memories_deletion", "tenant_id", "deletion_id"),
    )

    memory_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    region_id: Mapped[str] = mapped_column(String(16), nullable=False)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    memory_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    memory_scope: Mapped[str] = mapped_column(String(32), nullable=False)
    level: Mapped[str] = mapped_column(String(8), nullable=False)
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_granted: Mapped[bool] = mapped_column(nullable=False)
    data_class: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(32), nullable=False)
    provenance_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    deletion_id: Mapped[str] = mapped_column(String(256), nullable=False)
    retention_policy: Mapped[str] = mapped_column(String(128), nullable=False)
    source_ref: Mapped[str] = mapped_column(String(512), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    causation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    derived_memory_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    stable_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class MemoryDeletionProofRow(MemoryPersistenceBase):
    __tablename__ = "ai_memory_deletion_proofs"
    proof_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    deletion_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    region_id: Mapped[str] = mapped_column(String(16), nullable=False)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    deleted_memory_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(256), nullable=False)
    provenance_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyMemoryStore:
    """Async durable store for confirmed memory references and deletion proofs."""

    durability_mode = "DURABLE"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def put(self, memory: MemoryRef) -> MemoryRef:
        _validate_memory(memory)
        fingerprint = _fingerprint(memory)
        existing = await self._session.get(MemoryRefRow, memory.memory_id)
        if existing is not None:
            if existing.tenant_id != memory.tenant_id:
                raise ScopeMismatchError("CROSS_TENANT_MEMORY_WRITE")
            if existing.stable_fingerprint != fingerprint:
                raise ExperienceContractError("MEMORY_IDEMPOTENCY_CONFLICT")
            return _memory_from_row(existing)
        self._session.add(_row_from_memory(memory, fingerprint))
        await self._session.flush()
        return memory

    async def retrieve(
        self,
        memory_id: str,
        scope: ExperienceScope,
        *,
        purpose: str,
        moment: datetime | None = None,
    ) -> MemoryRef:
        _validate_scope(scope)
        row = await self._session.get(MemoryRefRow, memory_id)
        if row is None:
            raise ExperienceContractError("MEMORY_NOT_FOUND")
        memory = _memory_from_row(row)
        memory.assert_readable_by(scope, purpose=purpose, moment=moment)
        return memory

    async def delete(
        self,
        memory_id: str,
        scope: ExperienceScope,
        *,
        requested_by: str,
    ) -> MemoryDeletionProof:
        _validate_scope(scope)
        if not requested_by:
            raise ExperienceContractError("MEMORY_DELETION_ACTOR_REQUIRED")
        row = await self._session.get(MemoryRefRow, memory_id)
        if row is None:
            proof = await self._find_proof_for_memory(memory_id, scope)
            if proof is not None:
                return proof
            raise ExperienceContractError("MEMORY_NOT_FOUND")
        memory = _memory_from_row(row)
        memory.assert_scope(scope)
        existing = await self._session.scalar(
            select(MemoryDeletionProofRow).where(
                MemoryDeletionProofRow.deletion_id == memory.deletion_ref.deletion_id
            )
        )
        if existing is not None:
            return _proof_from_row(existing)
        deleted_ids = memory.deletion_cascade_ids()
        await self._session.execute(
            delete(MemoryRefRow).where(
                MemoryRefRow.tenant_id == scope.tenant_id,
                MemoryRefRow.memory_id.in_(deleted_ids),
            )
        )
        proof = MemoryDeletionProof(
            proof_id=f"proof:{memory.deletion_ref.deletion_id}",
            deletion_id=memory.deletion_ref.deletion_id,
            tenant_id=memory.tenant_id,
            region_id=memory.region_id,
            family_id=memory.family_id,
            subject_ids=memory.subject_ids,
            deleted_memory_ids=deleted_ids,
            requested_by=requested_by,
            provenance_ref=memory.provenance.provenance_ref,
            correlation_id=memory.correlation_id,
            deleted_at=datetime.now(UTC),
        )
        self._session.add(_proof_row(proof))
        await self._session.flush()
        return proof

    async def cascade_delete(
        self,
        memory_id: str,
        scope: ExperienceScope,
        *,
        requested_by: str,
    ) -> MemoryDeletionProof:
        """Explicit deletion-worker alias for source/derived fan-out."""

        return await self.delete(memory_id, scope, requested_by=requested_by)

    async def get_deletion_proof(
        self, proof_id: str, scope: ExperienceScope
    ) -> MemoryDeletionProof:
        _validate_scope(scope)
        row = await self._session.get(MemoryDeletionProofRow, proof_id)
        if row is None:
            raise ExperienceContractError("MEMORY_DELETION_PROOF_NOT_FOUND")
        proof = _proof_from_row(row)
        if proof.tenant_id != scope.tenant_id:
            raise ScopeMismatchError("CROSS_TENANT_MEMORY_DELETE_PROOF")
        if proof.family_id != scope.family_id or frozenset(proof.subject_ids) != frozenset(
            scope.subject_ids
        ):
            raise ScopeMismatchError("CROSS_FAMILY_MEMORY_DELETE_PROOF")
        return proof

    async def list_recent_by_source_prefix(
        self,
        source_ref_prefix: str,
        scope: ExperienceScope,
        *,
        purpose: str,
        limit: int = 3,
        moment: datetime | None = None,
    ) -> list[MemoryRef]:
        """Most-recent-first memories whose `source_ref` starts with a prefix.

        Used by conversational callers (e.g. the AI Coach) that need "the
        last N turns for this need/session" without a dedicated per-use-case
        table: `source_ref` already carries an honest, caller-chosen
        identifier (see `store_coach_turn`), so a prefix scan over it is
        real data, not an invented index. Still scoped and consent/expiry
        checked exactly like `retrieve` — a caller cannot use this to read
        past `assert_readable_by`'s guarantees.
        """

        _validate_scope(scope)
        if limit < 1:
            raise ExperienceContractError("MEMORY_LIST_LIMIT_INVALID")
        rows = (
            await self._session.scalars(
                select(MemoryRefRow)
                .where(
                    MemoryRefRow.tenant_id == scope.tenant_id,
                    MemoryRefRow.family_id == scope.family_id,
                    MemoryRefRow.source_ref.startswith(source_ref_prefix),
                )
                .order_by(MemoryRefRow.created_at.desc())
                .limit(limit * 4)
            )
        ).all()
        results: list[MemoryRef] = []
        for row in rows:
            memory = _memory_from_row(row)
            try:
                memory.assert_readable_by(scope, purpose=purpose, moment=moment)
            except (ScopeMismatchError, ExperienceContractError):
                continue
            results.append(memory)
            if len(results) >= limit:
                break
        return results

    async def purge_expired(self, *, now: datetime | None = None, limit: int = 500) -> int:
        """Delete expired references; proofs remain as the deletion audit trail."""

        if limit < 1:
            raise ExperienceContractError("MEMORY_PURGE_LIMIT_INVALID")
        current = now or datetime.now(UTC)
        rows = (
            await self._session.scalars(
                select(MemoryRefRow)
                .where(MemoryRefRow.expires_at <= current)
                .order_by(MemoryRefRow.expires_at, MemoryRefRow.memory_id)
                .limit(limit)
            )
        ).all()
        count = 0
        for row in rows:
            memory = _memory_from_row(row)
            await self.delete(
                memory.memory_id,
                _scope_from_memory(memory),
                requested_by="retention-worker",
            )
            count += 1
        return count

    async def _find_proof_for_memory(
        self, memory_id: str, scope: ExperienceScope
    ) -> MemoryDeletionProof | None:
        rows = (
            await self._session.scalars(
                select(MemoryDeletionProofRow).where(
                    MemoryDeletionProofRow.tenant_id == scope.tenant_id
                )
            )
        ).all()
        for row in rows:
            proof = _proof_from_row(row)
            if memory_id in proof.deleted_memory_ids:
                if proof.family_id != scope.family_id:
                    raise ScopeMismatchError("CROSS_FAMILY_MEMORY_DELETE")
                return proof
        return None


def _validate_memory(memory: MemoryRef) -> None:
    if not isinstance(memory, MemoryRef):
        raise ExperienceContractError("MEMORY_REF_REQUIRED")


def _validate_scope(scope: ExperienceScope) -> None:
    if not isinstance(scope, ExperienceScope):
        raise ExperienceContractError("EXPERIENCE_SCOPE_REQUIRED")


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _provenance_payload(value: ExperienceProvenance) -> dict[str, Any]:
    return {
        "provenance_ref": value.provenance_ref,
        "source_refs": list(value.source_refs),
        "kind": value.kind.value,
        "policy_version": value.policy_version,
        "context_snapshot_ref": value.context_snapshot_ref,
        "model_attempt_ref": value.model_attempt_ref,
        "captured_at": _aware(value.captured_at).isoformat(),
    }


def _provenance_from_payload(value: Mapping[str, Any]) -> ExperienceProvenance:
    try:
        return ExperienceProvenance(
            provenance_ref=str(value["provenance_ref"]),
            source_refs=tuple(str(item) for item in value["source_refs"]),
            kind=ProvenanceKind(str(value["kind"])),
            policy_version=str(value["policy_version"]),
            context_snapshot_ref=value.get("context_snapshot_ref"),
            model_attempt_ref=value.get("model_attempt_ref"),
            captured_at=_aware(datetime.fromisoformat(str(value["captured_at"]))),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ExperienceContractError("MEMORY_PROVENANCE_PAYLOAD_INVALID") from exc


def _row_from_memory(memory: MemoryRef, fingerprint: str) -> MemoryRefRow:
    return MemoryRefRow(
        memory_id=memory.memory_id,
        tenant_id=memory.tenant_id,
        region_id=memory.region_id,
        family_id=memory.family_id,
        subject_ids=list(memory.subject_ids),
        memory_ref=memory.memory_ref,
        memory_scope=memory.memory_scope.value,
        level=memory.level.value,
        purpose=memory.purpose,
        consent_version=memory.consent_version,
        consent_granted=memory.consent_granted,
        data_class=str(memory.data_class),
        locale=memory.locale,
        provenance_payload=_provenance_payload(memory.provenance),
        deletion_id=memory.deletion_ref.deletion_id,
        retention_policy=memory.deletion_ref.retention_policy,
        source_ref=memory.source_ref,
        correlation_id=memory.correlation_id,
        causation_id=memory.causation_id,
        created_at=_aware(memory.created_at),
        expires_at=_aware(memory.expires_at),
        derived_memory_ids=list(memory.derived_memory_ids),
        stable_fingerprint=fingerprint,
    )


def _memory_from_row(row: MemoryRefRow) -> MemoryRef:
    return MemoryRef(
        memory_id=row.memory_id,
        memory_ref=row.memory_ref,
        tenant_id=row.tenant_id,
        region_id=row.region_id,
        family_id=row.family_id,
        subject_ids=tuple(row.subject_ids),
        memory_scope=MemoryScope(row.memory_scope),
        level=MemoryLevel(row.level),
        purpose=row.purpose,
        consent_version=row.consent_version,
        consent_granted=row.consent_granted,
        data_class=row.data_class,  # type: ignore[arg-type]
        locale=row.locale,
        provenance=_provenance_from_payload(row.provenance_payload),
        deletion_ref=DeletionRef(row.deletion_id, row.retention_policy),
        source_ref=row.source_ref,
        correlation_id=row.correlation_id,
        causation_id=row.causation_id,
        created_at=_aware(row.created_at),
        expires_at=_aware(row.expires_at),
        derived_memory_ids=tuple(row.derived_memory_ids),
    )


def _scope_from_memory(memory: MemoryRef) -> ExperienceScope:
    return ExperienceScope(
        global_id=f"retention:{memory.tenant_id}:{memory.family_id}",
        tenant_id=memory.tenant_id,
        region_id=memory.region_id,
        family_id=memory.family_id,
        subject_ids=memory.subject_ids,
        purpose=memory.purpose,
        consent_version=memory.consent_version,
        consent_granted=True,
        data_class=memory.data_class,
        locale=memory.locale,
        content_locale=memory.locale,
        model_locale=memory.locale,
        policy_locale=memory.locale,
        deletion_ref=memory.deletion_ref,
        correlation_id=memory.correlation_id,
        causation_id=memory.causation_id,
    )


def _fingerprint(memory: MemoryRef) -> str:
    payload = {
        "memory_id": memory.memory_id,
        "memory_ref": memory.memory_ref,
        "scope": [memory.tenant_id, memory.region_id, memory.family_id, memory.subject_ids],
        "memory_scope": memory.memory_scope.value,
        "level": memory.level.value,
        "purpose": memory.purpose,
        "consent_version": memory.consent_version,
        "data_class": str(memory.data_class),
        "locale": memory.locale,
        "provenance": _provenance_payload(memory.provenance),
        "deletion": [memory.deletion_ref.deletion_id, memory.deletion_ref.retention_policy],
        "source_ref": memory.source_ref,
        "correlation_id": memory.correlation_id,
        "causation_id": memory.causation_id,
        "created_at": _aware(memory.created_at).isoformat(),
        "expires_at": _aware(memory.expires_at).isoformat(),
        "derived_memory_ids": memory.derived_memory_ids,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _proof_row(proof: MemoryDeletionProof) -> MemoryDeletionProofRow:
    return MemoryDeletionProofRow(
        proof_id=proof.proof_id,
        deletion_id=proof.deletion_id,
        tenant_id=proof.tenant_id,
        region_id=proof.region_id,
        family_id=proof.family_id,
        subject_ids=list(proof.subject_ids),
        deleted_memory_ids=list(proof.deleted_memory_ids),
        requested_by=proof.requested_by,
        provenance_ref=proof.provenance_ref,
        correlation_id=proof.correlation_id,
        deleted_at=_aware(proof.deleted_at),
    )


def _proof_from_row(row: MemoryDeletionProofRow) -> MemoryDeletionProof:
    return MemoryDeletionProof(
        proof_id=row.proof_id,
        deletion_id=row.deletion_id,
        tenant_id=row.tenant_id,
        region_id=row.region_id,
        family_id=row.family_id,
        subject_ids=tuple(row.subject_ids),
        deleted_memory_ids=tuple(row.deleted_memory_ids),
        requested_by=row.requested_by,
        provenance_ref=row.provenance_ref,
        correlation_id=row.correlation_id,
        deleted_at=_aware(row.deleted_at),
    )


__all__ = [
    "MemoryPersistenceBase",
    "MemoryRefRow",
    "MemoryDeletionProofRow",
    "SqlAlchemyMemoryStore",
]
