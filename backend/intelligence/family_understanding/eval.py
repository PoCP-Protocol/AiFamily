"""Deterministic AIR-01 replay adapter over the canonical Model Gateway."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

from backend.intelligence.family_understanding.contracts import (
    OUTPUT_SCHEMA,
    SCHEMA_VERSION,
    USE_CASE,
    FamilyUnderstandingContextV1,
    ProblemUnderstandingDraftV1,
)
from backend.intelligence.model_gateway.contracts import StructuredRequest
from backend.intelligence.model_gateway.gateway import ModelGateway

_PROMPT_INJECTION = re.compile(
    r"ignore\s+(all\s+)?previous|system\s+prompt|<\s*/?system\s*>|越过.*指令|忽略.*指令",
    re.IGNORECASE,
)
_PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_CN_ID = re.compile(r"(?<![0-9Xx])\d{17}[0-9Xx](?![0-9Xx])")


class FamilyUnderstandingRejected(ValueError):
    """Fail-closed use-case boundary rejection with a stable reason code."""

    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


@dataclass(frozen=True, slots=True)
class EvaluationArtifact:
    run_id: str
    request_hash: str
    artifact_hash: str
    draft: ProblemUnderstandingDraftV1
    fixture_only: bool = True


class FamilyUnderstandingEvaluator:
    """One-use-case adapter; it stores replay artifacts, never business state."""

    def __init__(
        self,
        gateway: ModelGateway,
        *,
        provider_id: str,
        prompt_version: str = "family-understanding-prompt.v1",
    ) -> None:
        self._gateway = gateway
        self._provider_id = provider_id
        self._prompt_version = prompt_version
        self._replays: dict[str, EvaluationArtifact] = {}

    async def evaluate(
        self,
        context: FamilyUnderstandingContextV1,
        *,
        run_id: str,
        tenant_id: str,
        family_id: str,
    ) -> EvaluationArtifact:
        if not run_id.strip():
            raise FamilyUnderstandingRejected("RUN_ID_REQUIRED")
        try:
            context.assert_scope(tenant_id=tenant_id, family_id=family_id)
        except ValueError as exc:
            raise FamilyUnderstandingRejected("SCOPE_MISMATCH") from exc
        self._screen_inputs(context)

        payload = context.to_gateway_payload()
        request_hash = _digest(
            {
                "use_case": USE_CASE,
                "prompt_version": self._prompt_version,
                "schema_version": SCHEMA_VERSION,
                "context_snapshot_ref": context.snapshot_ref,
                "payload": payload,
            }
        )
        replay = self._replays.get(run_id)
        if replay is not None:
            if replay.request_hash != request_hash:
                raise FamilyUnderstandingRejected("REPLAY_INPUT_MISMATCH")
            return replay

        request = StructuredRequest(
            use_case=USE_CASE,
            prompt_version=self._prompt_version,
            schema_version=SCHEMA_VERSION,
            data_class=context.data_class,
            payload=payload,
            output_schema=OUTPUT_SCHEMA,
            context_snapshot_ref=context.snapshot_ref,
            input_refs=context.source_refs + context.knowledge_ref_ids,
            request_id=run_id,
        )
        model_draft = await self._gateway.generate_structured(
            request, provider_id=self._provider_id
        )
        try:
            typed_draft = ProblemUnderstandingDraftV1.from_gateway_output(
                model_draft.output,
                provenance=model_draft.provenance,
                context=context,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise FamilyUnderstandingRejected("GROUNDING_INVALID") from exc

        artifact_hash = _digest(
            {
                "request_hash": request_hash,
                "provider_id": typed_draft.provenance.provider_id,
                "model": typed_draft.provenance.model,
                "model_version": typed_draft.provenance.model_version,
                "prompt_version": typed_draft.provenance.prompt_version,
                "schema_version": typed_draft.provenance.schema_version,
                "output": model_draft.output,
                "status": typed_draft.status,
                "may_mutate_business_state": typed_draft.may_mutate_business_state,
            }
        )
        artifact = EvaluationArtifact(
            run_id=run_id,
            request_hash=request_hash,
            artifact_hash=artifact_hash,
            draft=typed_draft,
        )
        self._replays[run_id] = artifact
        return artifact

    @staticmethod
    def _screen_inputs(context: FamilyUnderstandingContextV1) -> None:
        combined = "\n".join(item.text for item in context.inputs)
        if _PROMPT_INJECTION.search(combined):
            raise FamilyUnderstandingRejected("PROMPT_INJECTION_DETECTED")
        if _PHONE.search(combined) or _CN_ID.search(combined):
            raise FamilyUnderstandingRejected("DIRECT_IDENTIFIER_DETECTED")


def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(encoded).hexdigest()
