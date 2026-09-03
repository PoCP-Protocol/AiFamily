"""Read-only Growth Graph projection for AI retrieval.

Business domains remain the source of truth.  A projector may append an
immutable, evidence-bound edge here; AI callers can only query the scoped
projection.  No model/provider is imported and no domain fact is mutated.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy import JSON, DateTime, Index, String, delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceContractError,
    ExperienceProvenance,
    ExperienceScope,
    ProvenanceKind,
    ScopeMismatchError,
)


class GrowthGraphError(ExperienceContractError):
    """Raised when a graph projection violates its immutable contract."""


class GrowthGraphEdge:
    """One immutable, scope-bound edge projected from a domain event."""

    __slots__ = (
        "edge_id",
        "scope",
        "source_node",
        "target_node",
        "relation",
        "event_ref",
        "evidence_refs",
        "provenance",
        "observed_at",
        "expires_at",
    )

    def __init__(
        self,
        *,
        edge_id: str,
        scope: ExperienceScope,
        source_node: str,
        target_node: str,
        relation: str,
        event_ref: str,
        evidence_refs: Sequence[str],
        provenance: ExperienceProvenance,
        observed_at: datetime,
        expires_at: datetime | None = None,
    ) -> None:
        if not all((edge_id, source_node, target_node, relation, event_ref)):
            raise GrowthGraphError("GRAPH_EDGE_ID_NODES_RELATION_EVENT_REQUIRED")
        if not isinstance(scope, ExperienceScope):
            raise GrowthGraphError("EXPERIENCE_SCOPE_REQUIRED")
        if not evidence_refs or any(not value for value in evidence_refs):
            raise GrowthGraphError("GRAPH_EDGE_EVIDENCE_REQUIRED")
        if len(set(evidence_refs)) != len(evidence_refs):
            raise GrowthGraphError("GRAPH_EDGE_EVIDENCE_MUST_BE_UNIQUE")
        if not isinstance(provenance, ExperienceProvenance):
            raise GrowthGraphError("GRAPH_EDGE_PROVENANCE_REQUIRED")
        if observed_at.tzinfo is None:
            raise GrowthGraphError("GRAPH_EDGE_TIMESTAMP_REQUIRES_TIMEZONE")
        if expires_at is not None and expires_at <= observed_at:
            raise GrowthGraphError("GRAPH_EDGE_EXPIRY_INVALID")
        for value in (source_node, target_node, relation, event_ref):
            if len(value) > 256:
                raise GrowthGraphError("GRAPH_EDGE_FIELD_TOO_LONG")
        self.edge_id = edge_id
        self.scope = scope
        self.source_node = source_node
        self.target_node = target_node
        self.relation = relation
        self.event_ref = event_ref
        self.evidence_refs = tuple(evidence_refs)
        self.provenance = provenance
        self.observed_at = observed_at
        self.expires_at = expires_at

    def is_expired(self, moment: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        current = moment or datetime.now(UTC)
        return current >= self.expires_at

    def assert_readable_by(self, scope: ExperienceScope) -> None:
        if self.scope.tenant_id != scope.tenant_id:
            raise ScopeMismatchError("CROSS_TENANT_GRAPH_QUERY")
        if self.scope.region_id != scope.region_id or self.scope.family_id != scope.family_id:
            raise ScopeMismatchError("CROSS_FAMILY_GRAPH_QUERY")
        if not set(self.scope.subject_ids).issubset(scope.subject_ids):
            raise ScopeMismatchError("CROSS_SUBJECT_GRAPH_QUERY")
        if self.scope.purpose != scope.purpose:
            raise GrowthGraphError("GRAPH_PURPOSE_MISMATCH")
        if self.scope.consent_version != scope.consent_version or not scope.consent_granted:
            raise GrowthGraphError("GRAPH_CONSENT_REQUIRED")


class GrowthGraphDeletionProof:
    """Audit result for a tenant/family/subject projection deletion."""

    __slots__ = (
        "proof_id",
        "tenant_id",
        "region_id",
        "family_id",
        "subject_id",
        "deleted_edge_ids",
        "requested_by",
        "deleted_at",
    )

    def __init__(
        self,
        *,
        proof_id: str,
        tenant_id: str,
        region_id: str,
        family_id: str,
        subject_id: str,
        deleted_edge_ids: Sequence[str],
        requested_by: str,
        deleted_at: datetime,
    ) -> None:
        if not all((proof_id, tenant_id, region_id, family_id, subject_id, requested_by)):
            raise GrowthGraphError("GRAPH_DELETION_PROOF_FIELDS_REQUIRED")
        self.proof_id = proof_id
        self.tenant_id = tenant_id
        self.region_id = region_id
        self.family_id = family_id
        self.subject_id = subject_id
        self.deleted_edge_ids = tuple(deleted_edge_ids)
        self.requested_by = requested_by
        self.deleted_at = deleted_at


@runtime_checkable
class GrowthGraphQueryPort(Protocol):
    """AI-facing read port; projection writes are worker-only operations."""

    async def query(
        self,
        scope: ExperienceScope,
        *,
        subject_id: str | None = None,
        relation: str | None = None,
        now: datetime | None = None,
    ) -> tuple[GrowthGraphEdge, ...]: ...


class GrowthGraphPersistenceBase(DeclarativeBase):
    """Metadata boundary for the technical graph projection."""


class GrowthGraphEdgeRow(GrowthGraphPersistenceBase):
    __tablename__ = "ai_growth_graph_edges"
    __table_args__ = (
        Index("ix_ai_growth_graph_scope_time", "tenant_id", "family_id", "observed_at"),
    )

    edge_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    region_id: Mapped[str] = mapped_column(String(16), nullable=False)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    purpose: Mapped[str] = mapped_column(String(128), nullable=False)
    consent_version: Mapped[str] = mapped_column(String(128), nullable=False)
    data_class: Mapped[str] = mapped_column(String(64), nullable=False)
    locale: Mapped[str] = mapped_column(String(32), nullable=False)
    scope_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    source_node: Mapped[str] = mapped_column(String(256), nullable=False)
    target_node: Mapped[str] = mapped_column(String(256), nullable=False)
    relation: Mapped[str] = mapped_column(String(128), nullable=False)
    event_ref: Mapped[str] = mapped_column(String(256), nullable=False)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    provenance_payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    deletion_id: Mapped[str] = mapped_column(String(256), nullable=False)
    retention_policy: Mapped[str] = mapped_column(String(128), nullable=False)
    correlation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    causation_id: Mapped[str] = mapped_column(String(256), nullable=False)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    stable_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)


class GrowthGraphDeletionProofRow(GrowthGraphPersistenceBase):
    __tablename__ = "ai_growth_graph_deletion_proofs"

    proof_id: Mapped[str] = mapped_column(String(256), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    region_id: Mapped[str] = mapped_column(String(16), nullable=False)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    subject_id: Mapped[str] = mapped_column(String(128), nullable=False)
    deleted_edge_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    requested_by: Mapped[str] = mapped_column(String(256), nullable=False)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class SqlAlchemyGrowthGraphProjection(GrowthGraphQueryPort):
    """Durable projection adapter used by a worker and read-only AI callers."""

    durability_mode = "DURABLE"

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def project(self, edge: GrowthGraphEdge) -> GrowthGraphEdge:
        fingerprint = _fingerprint(edge)
        existing = await self._session.get(GrowthGraphEdgeRow, edge.edge_id)
        if existing is not None:
            if existing.tenant_id != edge.scope.tenant_id:
                raise ScopeMismatchError("CROSS_TENANT_GRAPH_WRITE")
            if existing.stable_fingerprint != fingerprint:
                raise GrowthGraphError("GRAPH_EDGE_IDEMPOTENCY_CONFLICT")
            return _edge_from_row(existing)
        self._session.add(_row_from_edge(edge, fingerprint))
        await self._session.flush()
        return edge

    async def query(
        self,
        scope: ExperienceScope,
        *,
        subject_id: str | None = None,
        relation: str | None = None,
        now: datetime | None = None,
    ) -> tuple[GrowthGraphEdge, ...]:
        if not isinstance(scope, ExperienceScope):
            raise GrowthGraphError("EXPERIENCE_SCOPE_REQUIRED")
        if not scope.consent_granted:
            raise GrowthGraphError("GRAPH_CONSENT_REQUIRED")
        if subject_id is not None and subject_id not in scope.subject_ids:
            raise ScopeMismatchError("GRAPH_SUBJECT_QUERY_DENIED")
        current = now or datetime.now(UTC)
        statement = select(GrowthGraphEdgeRow).where(
            GrowthGraphEdgeRow.tenant_id == scope.tenant_id,
            GrowthGraphEdgeRow.family_id == scope.family_id,
            GrowthGraphEdgeRow.purpose == scope.purpose,
            GrowthGraphEdgeRow.consent_version == scope.consent_version,
        )
        if relation is not None:
            statement = statement.where(GrowthGraphEdgeRow.relation == relation)
        rows = (
            await self._session.scalars(
                statement.order_by(GrowthGraphEdgeRow.observed_at)
            )
        ).all()
        result: list[GrowthGraphEdge] = []
        for row in rows:
            edge = _edge_from_row(row)
            if subject_id is not None and subject_id not in edge.scope.subject_ids:
                continue
            if edge.is_expired(current):
                continue
            edge.assert_readable_by(scope)
            result.append(edge)
        return tuple(result)

    async def cascade_delete(
        self,
        *,
        tenant_id: str,
        region_id: str,
        family_id: str,
        subject_id: str,
        requested_by: str,
    ) -> GrowthGraphDeletionProof:
        if not all((tenant_id, region_id, family_id, subject_id, requested_by)):
            raise GrowthGraphError("GRAPH_DELETION_FIELDS_REQUIRED")
        rows = (
            await self._session.scalars(
                select(GrowthGraphEdgeRow).where(
                    GrowthGraphEdgeRow.tenant_id == tenant_id,
                    GrowthGraphEdgeRow.family_id == family_id,
                )
            )
        ).all()
        ids = tuple(row.edge_id for row in rows if subject_id in row.subject_ids)
        proof_id = f"proof:graph:{tenant_id}:{family_id}:{subject_id}"
        existing = await self._session.get(GrowthGraphDeletionProofRow, proof_id)
        if existing is not None:
            return _proof_from_row(existing)
        if ids:
            await self._session.execute(
                delete(GrowthGraphEdgeRow).where(GrowthGraphEdgeRow.edge_id.in_(ids))
            )
        proof = GrowthGraphDeletionProof(
            proof_id=proof_id,
            tenant_id=tenant_id,
            region_id=region_id,
            family_id=family_id,
            subject_id=subject_id,
            deleted_edge_ids=ids,
            requested_by=requested_by,
            deleted_at=datetime.now(UTC),
        )
        self._session.add(_proof_row(proof))
        await self._session.flush()
        return proof


def _aware(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def _scope_payload(scope: ExperienceScope) -> dict[str, Any]:
    return {
        "global_id": scope.global_id,
        "tenant_id": scope.tenant_id,
        "region_id": scope.region_id,
        "family_id": scope.family_id,
        "subject_ids": list(scope.subject_ids),
        "purpose": scope.purpose,
        "consent_version": scope.consent_version,
        "consent_granted": scope.consent_granted,
        "data_class": str(scope.data_class),
        "locale": scope.locale,
        "content_locale": scope.content_locale,
        "model_locale": scope.model_locale,
        "policy_locale": scope.policy_locale,
        "deletion_id": scope.deletion_ref.deletion_id,
        "retention_policy": scope.deletion_ref.retention_policy,
        "correlation_id": scope.correlation_id,
        "causation_id": scope.causation_id,
    }


def _scope_from_payload(value: Mapping[str, Any]) -> ExperienceScope:
    return ExperienceScope(
        global_id=str(value["global_id"]),
        tenant_id=str(value["tenant_id"]),
        region_id=str(value["region_id"]),
        family_id=str(value["family_id"]),
        subject_ids=tuple(str(item) for item in value["subject_ids"]),
        purpose=str(value["purpose"]),
        consent_version=str(value["consent_version"]),
        consent_granted=bool(value["consent_granted"]),
        data_class=value["data_class"],  # type: ignore[arg-type]
        locale=str(value["locale"]),
        content_locale=str(value["content_locale"]),
        model_locale=str(value["model_locale"]),
        policy_locale=str(value["policy_locale"]),
        deletion_ref=DeletionRef(str(value["deletion_id"]), str(value["retention_policy"])),
        correlation_id=str(value["correlation_id"]),
        causation_id=str(value["causation_id"]),
    )


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
    return ExperienceProvenance(
        provenance_ref=str(value["provenance_ref"]),
        source_refs=tuple(str(item) for item in value["source_refs"]),
        kind=ProvenanceKind(str(value["kind"])),
        policy_version=str(value["policy_version"]),
        context_snapshot_ref=value.get("context_snapshot_ref"),
        model_attempt_ref=value.get("model_attempt_ref"),
        captured_at=_aware(datetime.fromisoformat(str(value["captured_at"]))),
    )


def _row_from_edge(edge: GrowthGraphEdge, fingerprint: str) -> GrowthGraphEdgeRow:
    scope = edge.scope
    return GrowthGraphEdgeRow(
        edge_id=edge.edge_id,
        tenant_id=scope.tenant_id,
        region_id=scope.region_id,
        family_id=scope.family_id,
        subject_ids=list(scope.subject_ids),
        purpose=scope.purpose,
        consent_version=scope.consent_version,
        data_class=str(scope.data_class),
        locale=scope.locale,
        scope_payload=_scope_payload(scope),
        source_node=edge.source_node,
        target_node=edge.target_node,
        relation=edge.relation,
        event_ref=edge.event_ref,
        evidence_refs=list(edge.evidence_refs),
        provenance_payload=_provenance_payload(edge.provenance),
        deletion_id=scope.deletion_ref.deletion_id,
        retention_policy=scope.deletion_ref.retention_policy,
        correlation_id=scope.correlation_id,
        causation_id=scope.causation_id,
        observed_at=_aware(edge.observed_at),
        expires_at=_aware(edge.expires_at) if edge.expires_at else None,
        stable_fingerprint=fingerprint,
    )


def _edge_from_row(row: GrowthGraphEdgeRow) -> GrowthGraphEdge:
    scope = _scope_from_payload(row.scope_payload)
    return GrowthGraphEdge(
        edge_id=row.edge_id,
        scope=scope,
        source_node=row.source_node,
        target_node=row.target_node,
        relation=row.relation,
        event_ref=row.event_ref,
        evidence_refs=tuple(row.evidence_refs),
        provenance=_provenance_from_payload(row.provenance_payload),
        observed_at=_aware(row.observed_at),
        expires_at=_aware(row.expires_at) if row.expires_at else None,
    )


def _fingerprint(edge: GrowthGraphEdge) -> str:
    payload = {
        "edge_id": edge.edge_id,
        "scope": _scope_payload(edge.scope),
        "source_node": edge.source_node,
        "target_node": edge.target_node,
        "relation": edge.relation,
        "event_ref": edge.event_ref,
        "evidence_refs": edge.evidence_refs,
        "provenance": _provenance_payload(edge.provenance),
        "observed_at": _aware(edge.observed_at).isoformat(),
        "expires_at": _aware(edge.expires_at).isoformat() if edge.expires_at else None,
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _proof_row(proof: GrowthGraphDeletionProof) -> GrowthGraphDeletionProofRow:
    return GrowthGraphDeletionProofRow(
        proof_id=proof.proof_id,
        tenant_id=proof.tenant_id,
        region_id=proof.region_id,
        family_id=proof.family_id,
        subject_id=proof.subject_id,
        deleted_edge_ids=list(proof.deleted_edge_ids),
        requested_by=proof.requested_by,
        deleted_at=_aware(proof.deleted_at),
    )


def _proof_from_row(row: GrowthGraphDeletionProofRow) -> GrowthGraphDeletionProof:
    return GrowthGraphDeletionProof(
        proof_id=row.proof_id,
        tenant_id=row.tenant_id,
        region_id=row.region_id,
        family_id=row.family_id,
        subject_id=row.subject_id,
        deleted_edge_ids=tuple(row.deleted_edge_ids),
        requested_by=row.requested_by,
        deleted_at=_aware(row.deleted_at),
    )


__all__ = [
    "GrowthGraphDeletionProof",
    "GrowthGraphEdge",
    "GrowthGraphError",
    "GrowthGraphEdgeRow",
    "GrowthGraphDeletionProofRow",
    "GrowthGraphPersistenceBase",
    "GrowthGraphQueryPort",
    "SqlAlchemyGrowthGraphProjection",
]
