"""Commands and their handlers for UI-02 (Assessment) — ported 1:1 from
`AssessmentService.start` / `.saveResponse` / `.submit`
(apps/api/src/modules/family/assessment.service.ts). Every idempotency-key /
advisory-lock / evidence-record / audit / outbox step from the NestJS
implementation is preserved; this is a translation, not a redesign.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass

from ..domain.errors import (
    AssessmentConflictError,
    AssessmentForbiddenError,
    AssessmentNotFoundError,
    AssessmentValidationError,
)
from ..domain.policies import assert_response_value
from ..domain.value_objects import MUTATION_RECEIPT_BOUNDARY, AssessmentResponseType
from .ports import AssessmentRepositoryPort

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE
)


def _is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


def _hash_request(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class MutationMeta:
    correlation_id: str
    idempotency_key: str
    source: str

    def require(self) -> None:
        if not self.idempotency_key or not self.idempotency_key.strip():
            raise AssessmentValidationError("idempotency_key_required")
        if len(self.idempotency_key) > 128:
            raise AssessmentValidationError("idempotency_key_too_long")


@dataclass(frozen=True)
class StartAssessmentCommand:
    family_id: str
    tenant_id: str
    actor_id: str
    subject_person_id: str
    tool_ref: str | None
    meta: MutationMeta


@dataclass(frozen=True)
class SaveAssessmentResponseCommand:
    family_id: str
    tenant_id: str
    actor_id: str
    session_id: str
    item_ref: str
    response_type: AssessmentResponseType
    response_value: str | bool
    meta: MutationMeta


@dataclass(frozen=True)
class SubmitAssessmentCommand:
    family_id: str
    tenant_id: str
    actor_id: str
    session_id: str
    meta: MutationMeta


class AssessmentCommandHandler:
    """Port of `AssessmentService` mutation methods. Repository transaction
    boundaries are the caller's responsibility (FastAPI dependency / unit of
    work), mirroring `this.repository.withTransaction(...)` in the NestJS
    version — the handler receives an already-scoped repository.
    """

    def __init__(self, repository: AssessmentRepositoryPort):
        self._repository = repository

    async def start(self, command: StartAssessmentCommand) -> dict:
        command.meta.require()
        if not _is_uuid(command.subject_person_id):
            raise AssessmentValidationError("valid_subject_person_id_required")
        tool_ref = (command.tool_ref or "").strip() or "FAMILY_SUPPORT_NEEDS"
        request_hash = _hash_request({"subject_person_id": command.subject_person_id, "tool_ref": tool_ref})

        await self._repository.lock_operation(
            command.tenant_id, command.family_id, "START_ASSESSMENT", command.meta.idempotency_key
        )
        replay = await self._repository.load_operation_replay(
            command.tenant_id, command.family_id, "START_ASSESSMENT", command.meta.idempotency_key, request_hash
        )
        if replay is not None:
            return {**replay, "replayed": True}

        await self._repository.assert_tenant_family_scope(command.tenant_id, command.family_id, command.actor_id)
        await self._repository.assert_subject_consent(command.family_id, command.subject_person_id, "ASSESSMENT")

        tool = await self._repository.load_active_tool(tool_ref)
        if tool is None:
            raise AssessmentNotFoundError("active_assessment_tool_not_found")

        existing_session_id = await self._repository.find_in_progress_session(
            command.tenant_id, command.family_id, command.subject_person_id, tool.tool_ref, tool.version_no
        )
        session_id = existing_session_id or await self._repository.insert_session(
            command.tenant_id,
            command.family_id,
            command.subject_person_id,
            tool.tool_ref,
            tool.version_no,
            command.actor_id,
        )

        session = await self._repository.load_session(command.family_id, session_id)
        receipt = {
            "action": "START_ASSESSMENT",
            "replayed": False,
            "session": session.model_dump(mode="json"),
            "boundary": MUTATION_RECEIPT_BOUNDARY,
        }
        await self._repository.persist_operation(
            command.tenant_id,
            command.family_id,
            session_id,
            command.actor_id,
            "START_ASSESSMENT",
            request_hash,
            receipt,
            command.meta.correlation_id,
            command.meta.idempotency_key,
        )
        await self._repository.write_audit_and_outbox(
            command.family_id,
            command.actor_id,
            session_id,
            "START_ASSESSMENT",
            "AssessmentSessionStarted",
            receipt,
            command.meta.correlation_id,
            command.meta.idempotency_key,
            command.meta.source,
        )
        return receipt

    async def save_response(self, command: SaveAssessmentResponseCommand) -> dict:
        command.meta.require()
        if not _is_uuid(command.session_id):
            raise AssessmentValidationError("valid_assessment_session_id_required")
        item_ref = (command.item_ref or "").strip()
        if not item_ref or command.response_type not in ("SINGLE_CHOICE", "TEXT", "BOOLEAN"):
            raise AssessmentValidationError("valid_assessment_response_required")

        request_hash = _hash_request(
            {
                "session_id": command.session_id,
                "item_ref": item_ref,
                "response_type": command.response_type,
                "response_value": command.response_value,
            }
        )

        await self._repository.lock_operation(
            command.tenant_id, command.family_id, "SAVE_ASSESSMENT_RESPONSE", command.meta.idempotency_key
        )
        replay = await self._repository.load_operation_replay(
            command.tenant_id,
            command.family_id,
            "SAVE_ASSESSMENT_RESPONSE",
            command.meta.idempotency_key,
            request_hash,
        )
        if replay is not None:
            return {**replay, "replayed": True}

        await self._repository.assert_tenant_family_scope(command.tenant_id, command.family_id, command.actor_id)
        session = await self._repository.load_session_for_update(
            command.family_id, command.tenant_id, command.session_id
        )
        if not session.is_editable():
            raise AssessmentConflictError("submitted_assessment_is_immutable")
        await self._repository.assert_subject_consent(command.family_id, session.subject_person_id, "ASSESSMENT")

        tool = await self._repository.load_tool_version(session.tool_ref, session.tool_version)
        item = tool.find_item(item_ref)
        if item is None or item.response_type != command.response_type:
            raise AssessmentValidationError("assessment_item_contract_mismatch")
        assert_response_value(item.response_type, item.options, command.response_value)

        await self._repository.upsert_response(
            command.session_id, item_ref, command.response_type, command.response_value, command.actor_id
        )

        session = await self._repository.load_session(command.family_id, command.session_id)
        receipt = {
            "action": "SAVE_ASSESSMENT_RESPONSE",
            "replayed": False,
            "session": session.model_dump(mode="json"),
            "boundary": MUTATION_RECEIPT_BOUNDARY,
        }
        await self._repository.persist_operation(
            command.tenant_id,
            command.family_id,
            command.session_id,
            command.actor_id,
            "SAVE_ASSESSMENT_RESPONSE",
            request_hash,
            receipt,
            command.meta.correlation_id,
            command.meta.idempotency_key,
        )
        await self._repository.write_audit_and_outbox(
            command.family_id,
            command.actor_id,
            command.session_id,
            "SAVE_ASSESSMENT_RESPONSE",
            "AssessmentResponseSaved",
            receipt,
            command.meta.correlation_id,
            command.meta.idempotency_key,
            command.meta.source,
        )
        return receipt

    async def submit(self, command: SubmitAssessmentCommand) -> dict:
        command.meta.require()
        if not _is_uuid(command.session_id):
            raise AssessmentValidationError("valid_assessment_session_id_required")
        request_hash = _hash_request({"session_id": command.session_id})

        await self._repository.lock_operation(
            command.tenant_id, command.family_id, "SUBMIT_ASSESSMENT", command.meta.idempotency_key
        )
        replay = await self._repository.load_operation_replay(
            command.tenant_id, command.family_id, "SUBMIT_ASSESSMENT", command.meta.idempotency_key, request_hash
        )
        if replay is not None:
            return {**replay, "replayed": True}

        await self._repository.assert_tenant_family_scope(command.tenant_id, command.family_id, command.actor_id)
        session = await self._repository.load_session_for_update(
            command.family_id, command.tenant_id, command.session_id
        )
        if not session.is_editable():
            raise AssessmentConflictError("assessment_session_not_editable")
        await self._repository.assert_subject_consent(command.family_id, session.subject_person_id, "ASSESSMENT")

        tool = await self._repository.load_tool_version(session.tool_ref, session.tool_version)
        answered = session.answered_item_refs()
        missing = [item.item_ref for item in tool.items if item.required and item.item_ref not in answered]
        if missing:
            raise AssessmentValidationError(f"required_assessment_responses_missing:{','.join(missing)}")

        await self._repository.mark_session_submitted(command.session_id)

        evidence_payload = {
            "assessment_session_id": command.session_id,
            "tool_ref": session.tool_ref,
            "tool_version": session.tool_version,
            "response_refs": [response.assessment_response_id for response in session.responses],
            "truth_class": "FAMILY_PERSPECTIVE",
            "not_a_score": True,
            "not_a_diagnosis": True,
        }
        evidence_id = await self._repository.insert_assessment_evidence(
            command.family_id, command.session_id, evidence_payload
        )

        session = await self._repository.load_session(command.family_id, command.session_id)
        receipt = {
            "action": "SUBMIT_ASSESSMENT",
            "replayed": False,
            "session": session.model_dump(mode="json"),
            "evidence_id": evidence_id,
            "boundary": MUTATION_RECEIPT_BOUNDARY,
        }
        await self._repository.persist_operation(
            command.tenant_id,
            command.family_id,
            command.session_id,
            command.actor_id,
            "SUBMIT_ASSESSMENT",
            request_hash,
            receipt,
            command.meta.correlation_id,
            command.meta.idempotency_key,
        )
        await self._repository.write_audit_and_outbox(
            command.family_id,
            command.actor_id,
            command.session_id,
            "SUBMIT_ASSESSMENT",
            "AssessmentSessionSubmitted",
            receipt,
            command.meta.correlation_id,
            command.meta.idempotency_key,
            command.meta.source,
        )
        return receipt
