"""Port of `GrowthHypothesisService.decide` (growth-hypothesis.service.ts).

CONFIRM bridges to the `growth_intents` table with
`boundary='HUMAN_CONFIRMED_INTENT_NOT_OUTCOME'` — this is the Named Action
boundary the migration plan (section 6/10) requires: AI Runtime output
(the hypothesis draft) never writes canonical state directly; only this
human-confirmed decision does.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal

from ..domain.errors import AssessmentConflictError, AssessmentNotFoundError, AssessmentValidationError
from ..domain.value_objects import GROWTH_INTENT_BOUNDARY, GrowthHypothesisDecisionType
from .ports import AssessmentInterpretationPort, AssessmentRepositoryPort
from .queries import _map_hypothesis

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE
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


class GrowthHypothesisCommandHandler:
    def __init__(self, repository: AssessmentRepositoryPort, interpretation: AssessmentInterpretationPort):
        self._repository = repository
        self._interpretation = interpretation

    async def decide(self, command: DecideGrowthHypothesisCommand) -> dict:
        if not command.idempotency_key or not command.idempotency_key.strip():
            raise AssessmentValidationError("idempotency_key_required")
        if not _is_uuid(command.assessment_session_id) or not command.hypothesis_ref.strip() or command.decision_type not in ("CONFIRM", "DISMISS"):
            raise AssessmentValidationError("valid_hypothesis_decision_required")

        action: Literal["CONFIRM_GROWTH_HYPOTHESIS", "DISMISS_GROWTH_HYPOTHESIS"] = (
            "CONFIRM_GROWTH_HYPOTHESIS" if command.decision_type == "CONFIRM" else "DISMISS_GROWTH_HYPOTHESIS"
        )
        request_hash = _hash_request(
            {
                "assessment_session_id": command.assessment_session_id,
                "hypothesis_ref": command.hypothesis_ref,
                "decision_type": command.decision_type,
            }
        )

        await self._repository.lock_hypothesis_decision(command.tenant_id, command.family_id, command.hypothesis_ref)
        replay = await self._repository.load_hypothesis_decision_replay(
            command.tenant_id, command.family_id, command.decision_type, command.idempotency_key
        )
        if replay is not None:
            if replay.get("request_hash") != request_hash:
                raise AssessmentConflictError("idempotency_key_payload_mismatch")
            return {**replay["response_body"], "replayed": True}

        await self._repository.assert_tenant_family_scope(command.tenant_id, command.family_id, command.actor_id)
        evidence = await self._repository.load_hypothesis_evidence(
            command.family_id, command.tenant_id, command.assessment_session_id
        )
        if evidence is None:
            raise AssessmentNotFoundError("growth_hypothesis_not_found")

        interpretation = await self._interpretation.interpret(command.family_id, evidence, "DEEP_AI_INTERPRETATION")
        hypothesis = _map_hypothesis(evidence, interpretation)
        if hypothesis["hypothesis_ref"] != command.hypothesis_ref:
            raise AssessmentConflictError("growth_hypothesis_reference_mismatch")

        await self._repository.assert_subject_consent(command.family_id, evidence.subject_person_id, "ASSESSMENT")

        intent: dict | None = None
        if command.decision_type == "CONFIRM":
            intent = await self._repository.load_or_create_growth_intent(
                family_id=command.family_id,
                subject_person_id=evidence.subject_person_id,
                need_type=evidence.need_type_ref,
                goal_text=evidence.description,
                required_capability_keys=evidence.required_capability_keys,
                confirmed_by=command.actor_id,
                source_ref=hypothesis["hypothesis_ref"],
                evidence_refs=[evidence.assessment_evidence_id],
            )
            assert intent.get("boundary", GROWTH_INTENT_BOUNDARY) == GROWTH_INTENT_BOUNDARY

        receipt = {
            "action": action,
            "outcome": "INTENT_CREATED" if command.decision_type == "CONFIRM" else "NO_ACTION",
            "hypothesis_ref": hypothesis["hypothesis_ref"],
            "intent": intent,
            "replayed": False,
        }
        await self._repository.persist_hypothesis_decision(
            tenant_id=command.tenant_id,
            family_id=command.family_id,
            session_id=evidence.assessment_session_id,
            hypothesis_ref=hypothesis["hypothesis_ref"],
            decision_type=command.decision_type,
            actor_id=command.actor_id,
            intent_id=intent["intent_id"] if intent else None,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
            receipt=receipt,
            correlation_id=command.correlation_id,
        )
        return receipt
