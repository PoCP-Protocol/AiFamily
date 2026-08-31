"""Compatibility facade for guardian decisions on reviewed understanding.

Canonical GrowthIntent creation is delegated through the Growth-owned port.
The confirmation path consumes an immutable Human Gate binding and never
re-runs interpretation or AI.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from typing import Literal

from ..domain.errors import (
    AssessmentConflictError,
    AssessmentForbiddenError,
    AssessmentNotFoundError,
    AssessmentValidationError,
)
from ..domain.value_objects import GrowthHypothesisDecisionType
from .growth_intent_handoff import (
    AssessmentGrowthIntentHandoff,
    DecideViewedUnderstandingInput,
    GrowthIntentConfirmationPort,
    ViewedUnderstandingSignal,
    ViewedUnderstandingSignalReaderPort,
)
from .ports import AssessmentRepositoryPort

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def _is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


def _hash_request(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DecideGrowthHypothesisCommand:
    family_id: str
    tenant_id: str
    actor_id: str
    assessment_session_id: str
    hypothesis_ref: str
    decision_type: GrowthHypothesisDecisionType
    correlation_id: str
    idempotency_key: str
    scope_ref: str = ""
    signal_version: int = 0
    reviewed_draft_ref: str = ""
    draft_version: int = 0
    provenance_ref: str = ""
    human_gate_receipt_ref: str = ""


class _LoadedSignalReader:
    def __init__(self, signal: ViewedUnderstandingSignal) -> None:
        self._signal = signal

    async def load_viewed_signal(self, **_: str) -> ViewedUnderstandingSignal:
        return self._signal


class GrowthHypothesisCommandHandler:
    def __init__(
        self,
        repository: AssessmentRepositoryPort,
        viewed_signals: ViewedUnderstandingSignalReaderPort,
        growth_intents: GrowthIntentConfirmationPort | None = None,
    ) -> None:
        self._repository = repository
        self._viewed_signals = viewed_signals
        self._growth_intents = growth_intents

    async def decide(self, command: DecideGrowthHypothesisCommand) -> dict:
        self._validate_command(command)

        # Canonical family permission is checked before gate lookup or replay.
        await self._repository.assert_tenant_family_scope(
            command.tenant_id, command.family_id, command.actor_id
        )
        signal = await self._viewed_signals.load_viewed_signal(
            tenant_id=command.tenant_id,
            family_id=command.family_id,
            assessment_session_id=command.assessment_session_id,
            human_gate_receipt_ref=command.human_gate_receipt_ref,
        )
        if signal is None:
            raise AssessmentNotFoundError("understanding_signal_not_found")
        self._validate_signal_binding(command, signal)
        await self._repository.assert_subject_consent(
            command.family_id, signal.subject_person_id, "ASSESSMENT"
        )

        request_hash = _hash_request(
            {
                "tenant_id": command.tenant_id,
                "family_id": command.family_id,
                "actor_id": command.actor_id,
                "assessment_session_id": command.assessment_session_id,
                "signal_ref": command.hypothesis_ref,
                "signal_version": command.signal_version,
                "scope_ref": command.scope_ref,
                "reviewed_draft_ref": command.reviewed_draft_ref,
                "draft_version": command.draft_version,
                "provenance_ref": command.provenance_ref,
                "human_gate_receipt_ref": command.human_gate_receipt_ref,
                "decision_type": command.decision_type,
            }
        )
        await self._repository.lock_hypothesis_decision(
            command.tenant_id, command.family_id, command.hypothesis_ref
        )
        replay = await self._repository.load_hypothesis_decision_replay(
            command.tenant_id, command.family_id, command.decision_type, command.idempotency_key
        )
        if replay is not None:
            if replay.get("request_hash") != request_hash:
                raise AssessmentConflictError("idempotency_key_payload_mismatch")
            return {**replay["response_body"], "replayed": True}

        if self._growth_intents is None:
            raise AssessmentValidationError("growth_intent_handoff_not_wired")
        handoff = AssessmentGrowthIntentHandoff(
            _LoadedSignalReader(signal), self._growth_intents
        )
        decision = await handoff.decide(
            DecideViewedUnderstandingInput(
                tenant_id=command.tenant_id,
                family_id=command.family_id,
                actor_id=command.actor_id,
                actor_type="FAMILY_GUARDIAN",
                assessment_session_id=command.assessment_session_id,
                signal_ref=command.hypothesis_ref,
                signal_version=command.signal_version,
                scope_ref=command.scope_ref,
                reviewed_draft_ref=command.reviewed_draft_ref,
                draft_version=command.draft_version,
                provenance_ref=command.provenance_ref,
                human_gate_receipt_ref=command.human_gate_receipt_ref,
                decision_type=command.decision_type,
                correlation_id=command.correlation_id,
                idempotency_key=command.idempotency_key,
            )
        )

        action: Literal["CONFIRM_GROWTH_HYPOTHESIS", "DISMISS_GROWTH_HYPOTHESIS"] = (
            "CONFIRM_GROWTH_HYPOTHESIS"
            if command.decision_type == "CONFIRM"
            else "DISMISS_GROWTH_HYPOTHESIS"
        )
        intent = None
        if decision.intent is not None:
            intent = {
                **asdict(decision.intent),
                "need_type": signal.need_type,
                "status": "OPEN",
                "required_capability_keys": list(signal.required_capability_keys),
                "evidence_refs": list(signal.evidence_refs),
            }
        receipt = {
            "action": action,
            "outcome": decision.outcome,
            "hypothesis_ref": decision.signal_ref,
            "signal_version": decision.signal_version,
            "human_gate_receipt_ref": decision.human_gate_receipt_ref,
            "intent": intent,
            "replayed": False,
        }
        await self._repository.persist_hypothesis_decision(
            tenant_id=command.tenant_id,
            family_id=command.family_id,
            session_id=signal.assessment_session_id,
            hypothesis_ref=decision.signal_ref,
            decision_type=command.decision_type,
            actor_id=command.actor_id,
            intent_id=decision.intent.intent_id if decision.intent else None,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
            receipt=receipt,
            correlation_id=command.correlation_id,
        )
        return receipt

    @staticmethod
    def _validate_command(command: DecideGrowthHypothesisCommand) -> None:
        if not command.idempotency_key.strip():
            raise AssessmentValidationError("idempotency_key_required")
        refs = (
            command.hypothesis_ref,
            command.scope_ref,
            command.reviewed_draft_ref,
            command.provenance_ref,
            command.human_gate_receipt_ref,
        )
        if (
            not _is_uuid(command.assessment_session_id)
            or not all(value.strip() for value in refs)
            or command.signal_version < 1
            or command.draft_version < 1
            or command.decision_type not in ("CONFIRM", "DISMISS")
        ):
            raise AssessmentValidationError("valid_reviewed_understanding_decision_required")

    @staticmethod
    def _validate_signal_binding(
        command: DecideGrowthHypothesisCommand, signal: ViewedUnderstandingSignal
    ) -> None:
        if signal.tenant_id != command.tenant_id or signal.family_id != command.family_id:
            raise AssessmentForbiddenError("family_access_denied")
        if signal.scope_ref != command.scope_ref:
            raise AssessmentForbiddenError("human_gate_scope_mismatch")
        if signal.reviewed_by_actor_id != command.actor_id:
            raise AssessmentForbiddenError("human_gate_actor_mismatch")
        if signal.human_gate_effective_status != "EFFECTIVE":
            raise AssessmentForbiddenError("human_gate_receipt_not_effective")
        if (
            signal.signal_ref != command.hypothesis_ref
            or signal.signal_version != command.signal_version
        ):
            raise AssessmentConflictError("understanding_signal_version_conflict")
        if signal.human_gate_receipt_ref != command.human_gate_receipt_ref:
            raise AssessmentConflictError("human_gate_receipt_mismatch")
        if (
            signal.reviewed_draft_ref != command.reviewed_draft_ref
            or signal.draft_version != command.draft_version
            or signal.provenance_ref != command.provenance_ref
        ):
            raise AssessmentConflictError("reviewed_draft_binding_mismatch")
