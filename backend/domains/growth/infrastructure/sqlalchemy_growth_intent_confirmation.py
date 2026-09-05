"""PostgreSQL GrowthIntent confirmation adapter bound to a caller-owned session."""

from __future__ import annotations

import json
from dataclasses import asdict, replace
from datetime import UTC, datetime
from uuid import UUID, uuid4, uuid5

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domains.assessment.application.growth_intent_handoff import (
    ConfirmGrowthIntentInput,
    GrowthIntentConfirmationPort,
    GrowthIntentReceipt,
)
from backend.domains.growth.application.growth_intent_confirmation import (
    ACTION_NAME,
    SOURCE_TYPE,
    GrowthConfirmationConflictError,
    ValidatedConfirmationBinding,
)
from backend.platform.audit import AuditEvent, AuditRecorder
from backend.platform.outbox import OutboxEvent, OutboxWriterPort, SqlAlchemyOutboxWriter

_IDEMPOTENCY_NAMESPACE = UUID("92773b6e-c8dd-49cc-9051-b14b202dc19c")
_RECEIPT_NAMESPACE = UUID("e4f09473-ad4f-4455-9380-7b790d2fc39b")


class SqlAlchemyGrowthIntentConfirmationAdapter(GrowthIntentConfirmationPort):
    """Stage intent, Audit, Outbox, and receipt without committing.

    The caller must bind this adapter to the same ``AsyncSession`` used by the
    Assessment atomic callback.  Any raised exception therefore leaves commit
    and rollback entirely under the canonical outer UnitOfWork.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        outbox_writer: OutboxWriterPort | None = None,
    ) -> None:
        self._session = session
        self._outbox = outbox_writer or SqlAlchemyOutboxWriter()

    async def confirm_growth_intent(self, command: ConfirmGrowthIntentInput) -> GrowthIntentReceipt:
        binding = ValidatedConfirmationBinding.from_command(command)
        request_hash = binding.request_hash()
        storage_key = _storage_key(binding)
        replay = await self._load_replay_or_reserve(storage_key, request_hash)
        if replay is not None:
            return replace(replay, replayed=True)

        intent_id = await self._load_or_insert_consistent_intent(binding)
        receipt = GrowthIntentReceipt(
            intent_id=str(intent_id),
            signal_ref=binding.signal_ref,
            signal_version=binding.signal_version,
            scope_ref=binding.scope_ref,
            reviewed_draft_ref=binding.reviewed_draft_ref,
            draft_version=binding.draft_version,
            provenance_ref=binding.provenance_ref,
            human_gate_receipt_ref=binding.human_gate_receipt_ref,
            receipt_ref=_receipt_ref(storage_key, request_hash),
        )
        envelope = {
            **binding.receipt_binding(),
            "intent_id": receipt.intent_id,
            "receipt_ref": receipt.receipt_ref,
            "request_hash": request_hash,
        }
        await self._flush_audit(binding, receipt, envelope)
        await self._outbox.append(
            self._session,
            OutboxEvent.create(
                tenant_id=binding.tenant_id,
                family_id=binding.family_id,
                aggregate_type="GrowthIntent",
                aggregate_id=receipt.intent_id,
                event_name="GrowthIntentConfirmed",
                event_version=1,
                idempotency_key=binding.idempotency_key,
                request_hash=request_hash,
                correlation_id=binding.correlation_id,
                payload=envelope,
            ),
        )
        await self._persist_receipt(storage_key, receipt)
        return receipt

    async def _load_replay_or_reserve(
        self, storage_key: str, request_hash: str
    ) -> GrowthIntentReceipt | None:
        inserted = (
            await self._session.execute(
                text(
                    """
                    insert into idempotency_keys(
                        idempotency_key,action_name,request_hash,response_code,response_body,
                        created_at,expires_at
                    ) values (:key,:action,:request_hash,null,null,:created_at,null)
                    on conflict (idempotency_key) do nothing
                    returning idempotency_key
                    """
                ),
                {
                    "key": storage_key,
                    "action": ACTION_NAME,
                    "request_hash": request_hash,
                    "created_at": datetime.now(UTC),
                },
            )
        ).first()
        row = (
            (
                await self._session.execute(
                    text(
                        "select action_name,request_hash,response_body from idempotency_keys "
                        "where idempotency_key=:key for update"
                    ),
                    {"key": storage_key},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            raise RuntimeError("idempotency_reservation_missing")
        if row["action_name"] != ACTION_NAME or row["request_hash"] != request_hash:
            raise GrowthConfirmationConflictError("idempotency_key_payload_mismatch")
        if inserted is not None:
            return None
        if row["response_body"] is None:
            raise GrowthConfirmationConflictError("idempotency_receipt_incomplete")
        return _receipt_from_dict(dict(row["response_body"]))

    async def _load_or_insert_consistent_intent(
        self, binding: ValidatedConfirmationBinding
    ) -> UUID:
        row = (
            (
                await self._session.execute(
                    text(
                        """
                    select intent_id,subject_person_id,need_type,goal_text,
                           required_capability_keys,status,confirmed_by,evidence_refs,boundary
                    from growth_intents
                    where family_id=:family_id and source_type=:source_type
                      and source_ref=:source_ref
                    for update
                    """
                    ),
                    {
                        "family_id": UUID(binding.family_id),
                        "source_type": SOURCE_TYPE,
                        "source_ref": binding.signal_ref,
                    },
                )
            )
            .mappings()
            .first()
        )
        if row is not None:
            if not _intent_matches(row, binding):
                raise GrowthConfirmationConflictError("existing_growth_intent_mismatch")
            return UUID(str(row["intent_id"]))

        intent_id = uuid4()
        await self._session.execute(
            text(
                """
                insert into growth_intents(
                    intent_id,family_id,subject_person_id,signal_ref,need_type,goal_text,
                    required_capability_keys,status,close_reason,confirmed_by,confirmed_at,
                    source_type,source_ref,evidence_refs,boundary
                ) values (
                    :intent_id,:family_id,:subject_person_id,null,:need_type,:goal_text,
                    :required_capability_keys,'OPEN',null,:confirmed_by,:confirmed_at,
                    :source_type,:source_ref,:evidence_refs,:boundary
                )
                """
            ),
            {
                "intent_id": intent_id,
                "family_id": UUID(binding.family_id),
                "subject_person_id": UUID(binding.subject_person_id),
                "need_type": binding.need_type,
                "goal_text": binding.goal_text,
                "required_capability_keys": list(binding.required_capability_keys),
                "confirmed_by": UUID(binding.actor_id),
                "confirmed_at": datetime.now(UTC),
                "source_type": SOURCE_TYPE,
                "source_ref": binding.signal_ref,
                "evidence_refs": [UUID(value) for value in binding.evidence_refs],
                "boundary": binding.boundary,
            },
        )
        return intent_id

    async def _flush_audit(
        self,
        binding: ValidatedConfirmationBinding,
        receipt: GrowthIntentReceipt,
        envelope: dict[str, object],
    ) -> None:
        recorder = AuditRecorder()
        recorder.record(
            AuditEvent(
                actor_id=binding.actor_id,
                tenant_id=binding.tenant_id,
                action="growth_intent.confirm",
                resource_type="GrowthIntent",
                resource_id=receipt.intent_id,
                reason="guardian confirmed the reviewed family understanding",
                correlation_id=binding.correlation_id,
                before=None,
                after=envelope,
            )
        )
        await recorder.flush(self._session)

    async def _persist_receipt(self, storage_key: str, receipt: GrowthIntentReceipt) -> None:
        result = await self._session.execute(
            text(
                "update idempotency_keys set response_code=200,response_body=:body "
                "where idempotency_key=:key and response_body is null"
            ),
            {
                "key": storage_key,
                "body": json.dumps(asdict(receipt), sort_keys=True, separators=(",", ":")),
            },
        )
        if result.rowcount != 1:
            raise GrowthConfirmationConflictError("idempotency_receipt_persist_conflict")


def _storage_key(binding: ValidatedConfirmationBinding) -> str:
    identity = ":".join((binding.tenant_id, binding.family_id, binding.idempotency_key))
    return f"growth-confirm:{uuid5(_IDEMPOTENCY_NAMESPACE, identity)}"


def _receipt_ref(storage_key: str, request_hash: str) -> str:
    return f"growth-confirmation:{uuid5(_RECEIPT_NAMESPACE, f'{storage_key}:{request_hash}')}"


def _receipt_from_dict(value: dict) -> GrowthIntentReceipt:
    return GrowthIntentReceipt(
        intent_id=str(value["intent_id"]),
        signal_ref=str(value["signal_ref"]),
        signal_version=int(value["signal_version"]),
        scope_ref=str(value["scope_ref"]),
        reviewed_draft_ref=str(value["reviewed_draft_ref"]),
        draft_version=int(value["draft_version"]),
        provenance_ref=str(value["provenance_ref"]),
        human_gate_receipt_ref=str(value["human_gate_receipt_ref"]),
        receipt_ref=str(value["receipt_ref"]),
        boundary=value["boundary"],
        replayed=bool(value.get("replayed", False)),
    )


def _intent_matches(row, binding: ValidatedConfirmationBinding) -> bool:
    return (
        str(row["subject_person_id"]) == binding.subject_person_id
        and row["need_type"] == binding.need_type
        and row["goal_text"] == binding.goal_text
        and tuple(row["required_capability_keys"]) == binding.required_capability_keys
        and row["status"] == "OPEN"
        and str(row["confirmed_by"]) == binding.actor_id
        and tuple(str(value) for value in row["evidence_refs"]) == binding.evidence_refs
        and row["boundary"] == binding.boundary
    )


__all__ = ["SqlAlchemyGrowthIntentConfirmationAdapter"]
