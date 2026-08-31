"""PostgreSQL writer/reader for guardian-reviewed understanding signals."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID, uuid4

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domains.assessment.application.growth_intent_handoff import (
    ViewedUnderstandingSignal,
    ViewedUnderstandingSignalReaderPort,
)
from backend.domains.assessment.application.reviewed_understanding_signals import (
    RecordReviewedUnderstandingInput,
    ReviewedUnderstandingSignalWriterPort,
)
from backend.domains.assessment.domain.errors import AssessmentConflictError


class SqlAlchemyReviewedUnderstandingSignals(
    ViewedUnderstandingSignalReaderPort,
    ReviewedUnderstandingSignalWriterPort,
):
    """Stage reviewed-signal writes in a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def save_viewed_signal(
        self, command: RecordReviewedUnderstandingInput
    ) -> ViewedUnderstandingSignal:
        inserted = (
            await self._session.execute(
                text(
                    """
                    insert into assessment_reviewed_understanding_signals(
                        reviewed_signal_id,tenant_id,family_id,assessment_session_id,
                        signal_ref,signal_version,scope_ref,reviewed_draft_ref,draft_version,
                        provenance_ref,draft_source,output_schema_ref,view_event_ref,
                        human_gate_receipt_ref,effective_status,
                        reviewed_by_actor_id,reviewed_at,expires_at,subject_person_id,
                        need_type,goal_text,required_capability_keys,evidence_refs
                    ) values (
                        :reviewed_signal_id,:tenant_id,:family_id,:assessment_session_id,
                        :signal_ref,:signal_version,:scope_ref,:reviewed_draft_ref,:draft_version,
                        :provenance_ref,:draft_source,:output_schema_ref,:view_event_ref,
                        :human_gate_receipt_ref,'EFFECTIVE',
                        :reviewed_by_actor_id,:reviewed_at,:expires_at,:subject_person_id,
                        :need_type,:goal_text,:required_capability_keys,:evidence_refs
                    )
                    on conflict (tenant_id,family_id,human_gate_receipt_ref) do nothing
                    returning reviewed_signal_id
                    """
                ),
                {
                    "reviewed_signal_id": uuid4(),
                    "tenant_id": UUID(command.tenant_id),
                    "family_id": UUID(command.family_id),
                    "assessment_session_id": UUID(command.assessment_session_id),
                    "signal_ref": command.signal_ref,
                    "signal_version": command.signal_version,
                    "scope_ref": command.scope_ref,
                    "reviewed_draft_ref": command.reviewed_draft_ref,
                    "draft_version": command.draft_version,
                    "provenance_ref": command.provenance_ref,
                    "draft_source": command.draft_source,
                    "output_schema_ref": command.output_schema_ref,
                    "view_event_ref": command.view_event_ref,
                    "human_gate_receipt_ref": command.human_gate_receipt_ref,
                    "reviewed_by_actor_id": UUID(command.reviewed_by_actor_id),
                    "reviewed_at": command.reviewed_at,
                    "expires_at": command.expires_at,
                    "subject_person_id": UUID(command.subject_person_id),
                    "need_type": command.need_type,
                    "goal_text": command.goal_text,
                    "required_capability_keys": list(command.required_capability_keys),
                    "evidence_refs": list(command.evidence_refs),
                },
            )
        ).first()
        signal = await self._load_by_gate_receipt(
            tenant_id=command.tenant_id,
            family_id=command.family_id,
            assessment_session_id=command.assessment_session_id,
            human_gate_receipt_ref=command.human_gate_receipt_ref,
            lock=True,
        )
        if signal is None:
            raise RuntimeError("reviewed_understanding_insert_missing")
        if inserted is None and not _matches_command(signal, command):
            raise AssessmentConflictError("reviewed_understanding_idempotency_conflict")
        return signal

    async def load_viewed_signal(
        self,
        *,
        tenant_id: str,
        family_id: str,
        assessment_session_id: str,
        human_gate_receipt_ref: str,
    ) -> ViewedUnderstandingSignal | None:
        return await self._load_by_gate_receipt(
            tenant_id=tenant_id,
            family_id=family_id,
            assessment_session_id=assessment_session_id,
            human_gate_receipt_ref=human_gate_receipt_ref,
            lock=False,
        )

    async def _load_by_gate_receipt(
        self,
        *,
        tenant_id: str,
        family_id: str,
        assessment_session_id: str,
        human_gate_receipt_ref: str,
        lock: bool,
    ) -> ViewedUnderstandingSignal | None:
        suffix = " for update" if lock else ""
        row = (
            (
                await self._session.execute(
                    text(
                        "select * from assessment_reviewed_understanding_signals "
                        "where tenant_id=:tenant_id and family_id=:family_id "
                        "and assessment_session_id=:assessment_session_id "
                        f"and human_gate_receipt_ref=:human_gate_receipt_ref{suffix}"
                    ),
                    {
                        "tenant_id": UUID(tenant_id),
                        "family_id": UUID(family_id),
                        "assessment_session_id": UUID(assessment_session_id),
                        "human_gate_receipt_ref": human_gate_receipt_ref,
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        status = str(row["effective_status"])
        now = datetime.now(UTC)
        if row["revoked_at"] is not None:
            status = "REVOKED"
        elif row["expires_at"] is not None and row["expires_at"] <= now:
            status = "EXPIRED"
        return ViewedUnderstandingSignal(
            tenant_id=str(row["tenant_id"]),
            family_id=str(row["family_id"]),
            assessment_session_id=str(row["assessment_session_id"]),
            signal_ref=str(row["signal_ref"]),
            signal_version=int(row["signal_version"]),
            scope_ref=str(row["scope_ref"]),
            reviewed_draft_ref=str(row["reviewed_draft_ref"]),
            draft_version=int(row["draft_version"]),
            provenance_ref=str(row["provenance_ref"]),
            human_gate_receipt_ref=str(row["human_gate_receipt_ref"]),
            human_gate_effective_status=status,
            reviewed_by_actor_id=str(row["reviewed_by_actor_id"]),
            subject_person_id=str(row["subject_person_id"]),
            need_type=str(row["need_type"]),
            goal_text=str(row["goal_text"]),
            required_capability_keys=tuple(row["required_capability_keys"]),
            evidence_refs=tuple(row["evidence_refs"]),
            reviewed_at=row["reviewed_at"],
            expires_at=row["expires_at"],
            revoked_at=row["revoked_at"],
            revocation_ref=row["revocation_ref"],
            draft_source=str(row["draft_source"]),
            output_schema_ref=str(row["output_schema_ref"]),
            view_event_ref=str(row["view_event_ref"]),
        )


def _matches_command(
    signal: ViewedUnderstandingSignal, command: RecordReviewedUnderstandingInput
) -> bool:
    return (
        signal.signal_ref == command.signal_ref
        and signal.signal_version == command.signal_version
        and signal.scope_ref == command.scope_ref
        and signal.reviewed_draft_ref == command.reviewed_draft_ref
        and signal.draft_version == command.draft_version
        and signal.provenance_ref == command.provenance_ref
        and signal.draft_source == command.draft_source
        and signal.output_schema_ref == command.output_schema_ref
        and signal.view_event_ref == command.view_event_ref
        and signal.reviewed_by_actor_id == command.reviewed_by_actor_id
        and signal.reviewed_at == command.reviewed_at
        and signal.expires_at == command.expires_at
        and signal.subject_person_id == command.subject_person_id
        and signal.need_type == command.need_type
        and signal.goal_text == command.goal_text
        and signal.required_capability_keys == command.required_capability_keys
        and signal.evidence_refs == command.evidence_refs
    )


__all__ = ["SqlAlchemyReviewedUnderstandingSignals"]
