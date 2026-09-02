"""Caller-owned SQLAlchemy adapter for immutable understanding snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.intelligence.family_understanding.snapshot import UnderstandingDraftSnapshot

TABLE_NAME = "family_understanding_draft_snapshots"


class SqlAlchemyUnderstandingDraftSnapshots:
    """Persist and read exact server-projected drafts without committing."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save(self, snapshot: UnderstandingDraftSnapshot) -> None:
        if snapshot.expires_at <= datetime.now(UTC):
            raise ValueError("understanding snapshot is already expired")
        if snapshot.prior_artifact_ref is not None:
            await self._expire_prior_snapshot(snapshot)
        inserted = (
            await self._session.execute(
                text(
                    f"""
                    INSERT INTO {TABLE_NAME}(
                        understanding_snapshot_id,tenant_id,family_id,understanding_run_ref,
                        artifact_ref,artifact_version,prior_artifact_ref,provenance_ref,
                        subject_person_id,desired_change,need_type,required_capability_keys,
                        evidence_refs,source_refs,knowledge_refs,provider_id,model,model_version,
                        prompt_version,schema_version,context_snapshot_ref,expires_at,status
                    ) VALUES (
                        :id,:tenant,:family,:run_ref,:artifact,:version,:prior,:provenance,
                        :subject,:desired_change,:need_type,:capabilities,:evidence,:sources,
                        :knowledge,:provider,:model,:model_version,:prompt_version,:schema_version,
                        :context,:expires,'DRAFT'
                    )
                    ON CONFLICT (tenant_id,family_id,artifact_ref,artifact_version,provenance_ref)
                    DO NOTHING RETURNING understanding_snapshot_id
                    """
                ),
                _parameters(snapshot) | {"id": uuid4()},
            )
        ).first()
        stored_row = await self._load_row(
            tenant_id=snapshot.tenant_id,
            family_id=snapshot.family_id,
            artifact_ref=snapshot.artifact_ref,
            artifact_version=snapshot.artifact_version,
            provenance_ref=snapshot.provenance_ref,
            lock=True,
        )
        if stored_row is None:
            raise RuntimeError("understanding_snapshot_insert_missing")
        if (
            str(stored_row["status"]) != "DRAFT"
            or stored_row["revoked_at"] is not None
            or stored_row["expires_at"] <= datetime.now(UTC)
        ):
            raise RuntimeError("understanding_snapshot_not_effective")
        stored = _snapshot(stored_row)
        if inserted is None and stored != snapshot:
            raise RuntimeError("understanding_snapshot_idempotency_conflict")

    async def _expire_prior_snapshot(self, snapshot: UnderstandingDraftSnapshot) -> None:
        """Keep history while removing a replaced draft from the current projection."""

        await self._session.execute(
            text(
                f"UPDATE {TABLE_NAME} SET status='EXPIRED',"
                "expires_at=LEAST(expires_at,now()) "
                "WHERE tenant_id=:tenant AND family_id=:family "
                "AND understanding_run_ref=:run_ref AND artifact_ref=:prior "
                "AND artifact_version<:version AND status='DRAFT'"
            ),
            {
                "tenant": UUID(snapshot.tenant_id),
                "family": UUID(snapshot.family_id),
                "run_ref": snapshot.understanding_run_ref,
                "prior": snapshot.prior_artifact_ref,
                "version": snapshot.artifact_version,
            },
        )

    async def load(
        self,
        *,
        tenant_id: str,
        family_id: str,
        artifact_ref: str,
        artifact_version: int,
        provenance_ref: str,
    ) -> UnderstandingDraftSnapshot | None:
        row = await self._load_row(
            tenant_id=tenant_id,
            family_id=family_id,
            artifact_ref=artifact_ref,
            artifact_version=artifact_version,
            provenance_ref=provenance_ref,
            lock=True,
        )
        if row is None:
            return None
        if (
            str(row["status"]) != "DRAFT"
            or row["revoked_at"] is not None
            or row["expires_at"] <= datetime.now(UTC)
        ):
            return None
        return _snapshot(row)

    async def _load_row(
        self,
        *,
        tenant_id: str,
        family_id: str,
        artifact_ref: str,
        artifact_version: int,
        provenance_ref: str,
        lock: bool,
    ):
        suffix = " FOR UPDATE" if lock else ""
        return (
            (
                await self._session.execute(
                    text(
                        f"SELECT * FROM {TABLE_NAME} WHERE tenant_id=:tenant "
                        "AND family_id=:family AND artifact_ref=:artifact "
                        "AND artifact_version=:version AND provenance_ref=:provenance"
                        f"{suffix}"
                    ),
                    {
                        "tenant": UUID(tenant_id),
                        "family": UUID(family_id),
                        "artifact": artifact_ref,
                        "version": artifact_version,
                        "provenance": provenance_ref,
                    },
                )
            )
            .mappings()
            .first()
        )


def _parameters(snapshot: UnderstandingDraftSnapshot) -> dict[str, object]:
    return {
        "tenant": UUID(snapshot.tenant_id),
        "family": UUID(snapshot.family_id),
        "run_ref": snapshot.understanding_run_ref,
        "artifact": snapshot.artifact_ref,
        "version": snapshot.artifact_version,
        "prior": snapshot.prior_artifact_ref,
        "provenance": snapshot.provenance_ref,
        "subject": UUID(snapshot.subject_person_id),
        "desired_change": snapshot.desired_change,
        "need_type": snapshot.need_type,
        "capabilities": list(snapshot.required_capability_keys),
        "evidence": list(snapshot.evidence_refs),
        "sources": list(snapshot.source_refs),
        "knowledge": list(snapshot.knowledge_refs),
        "provider": snapshot.provider_id,
        "model": snapshot.model,
        "model_version": snapshot.model_version,
        "prompt_version": snapshot.prompt_version,
        "schema_version": snapshot.schema_version,
        "context": snapshot.context_snapshot_ref,
        "expires": snapshot.expires_at,
    }


def _snapshot(row) -> UnderstandingDraftSnapshot:
    return UnderstandingDraftSnapshot(
        tenant_id=str(row["tenant_id"]),
        family_id=str(row["family_id"]),
        understanding_run_ref=str(row["understanding_run_ref"]),
        artifact_ref=str(row["artifact_ref"]),
        artifact_version=int(row["artifact_version"]),
        prior_artifact_ref=row["prior_artifact_ref"],
        provenance_ref=str(row["provenance_ref"]),
        subject_person_id=str(row["subject_person_id"]),
        desired_change=str(row["desired_change"]),
        need_type=str(row["need_type"]),
        required_capability_keys=tuple(row["required_capability_keys"]),
        evidence_refs=tuple(row["evidence_refs"]),
        source_refs=tuple(row["source_refs"]),
        knowledge_refs=tuple(row["knowledge_refs"]),
        provider_id=str(row["provider_id"]),
        model=str(row["model"]),
        model_version=str(row["model_version"]),
        prompt_version=str(row["prompt_version"]),
        schema_version=str(row["schema_version"]),
        context_snapshot_ref=str(row["context_snapshot_ref"]),
        expires_at=row["expires_at"],
        status="DRAFT",
    )


__all__ = ["SqlAlchemyUnderstandingDraftSnapshots"]
