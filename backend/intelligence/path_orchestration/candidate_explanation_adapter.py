"""Real Model-Gateway-backed rewording of an already-retrieved knowledge claim.

This is deliberately narrower than "generate a candidate": the model never
decides *which* candidates exist (that is `knowledge_candidate_source.py`'s
job, done entirely by deterministic registry lookup) — it only rewords an
already-published `KnowledgeClaim.text` into a parent-readable title and
description. The reviewed prompt explicitly forbids adding any fact, name,
or claim not already present in the given text, because a
`CapabilityCandidate` is supposed to be a reviewed capability, not a model
invention — see ADR-0158's discussion of why a fixed pool "context-driven"
in name only is a disguised if/else table, and the mirror-image risk here:
a model "explaining" a candidate must not become a model inventing one.
"""

from __future__ import annotations

import hashlib

from backend.intelligence.model_gateway.contracts import (
    ModelDraft,
    PromptExecutionPlan,
    StructuredRequest,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway

from .contracts import PathDraftError

CANDIDATE_EXPLANATION_USE_CASE = "path_orchestration_candidate_explanation_v1"
CANDIDATE_EXPLANATION_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "description": {"type": "string"},
    },
    "required": ["title", "description"],
    "additionalProperties": False,
}

_EXPLANATION_TEMPLATE = (
    "You receive `claim_text` — an already-reviewed, published knowledge "
    "claim — and `fit_tags`, de-identified category labels describing why "
    "this claim was retrieved for a family. Produce a short parent-readable "
    "`title` and `description` that reword claim_text in plain language. "
    "You MUST NOT add any fact, institution name, service name, outcome "
    "promise, or detail that is not already present in claim_text. If "
    "claim_text is too sparse to describe safely, keep the description "
    "close to a direct paraphrase rather than filling gaps."
)
_EXPLANATION_SYSTEM_POLICY = (
    "You are a bounded rewording assistant. You never invent capabilities, "
    "services, or facts. Your only job is to reword the given claim_text "
    "into parent-friendly language. Output must match the given JSON "
    "schema exactly. Never produce a score, ranking, or diagnosis."
)


def _reviewed_prompt_execution_plan() -> PromptExecutionPlan:
    return PromptExecutionPlan(
        prompt_ref=CANDIDATE_EXPLANATION_USE_CASE,
        prompt_version="v1",
        template=_EXPLANATION_TEMPLATE,
        system_policy_ref="path_orchestration_candidate_explanation_policy_v1",
        safety_policy_version="v1",
        knowledge_refs=(),
        asset_digest=hashlib.sha256(_EXPLANATION_TEMPLATE.encode()).hexdigest(),
        system_policy=_EXPLANATION_SYSTEM_POLICY,
        system_policy_digest=hashlib.sha256(_EXPLANATION_SYSTEM_POLICY.encode()).hexdigest(),
        knowledge_materials=(),
        material_digest=hashlib.sha256(
            b"path_orchestration_candidate_explanation_no_knowledge"
        ).hexdigest(),
    )


class GatewayBackedCandidateExplanationAdapter:
    """Rewords one knowledge claim into a candidate title/description.

    Routes through the shared Model Gateway (R7) — no second model entry
    point. `claim_text` is a public, already-published knowledge claim (not
    family-identifying), so OPERATIONAL_TEXT/SYNTHETIC is the correct data
    class; this is enforced at construction time, matching
    `GatewayBackedUnderstandAdapter`'s pattern in understand_adapter.py.
    """

    def __init__(
        self, gateway: ModelGateway, *, provider_id: str, data_class: str = "OPERATIONAL_TEXT"
    ) -> None:
        if data_class not in ("OPERATIONAL_TEXT", "SYNTHETIC"):
            raise PathDraftError(
                "candidate explanation only ever sends already-published "
                "knowledge claim text — FAMILY_PRIVATE_TEXT/MINOR_PERSONAL_DATA "
                "are not applicable here and must never be requested"
            )
        self._gateway = gateway
        self._provider_id = provider_id
        self._data_class = data_class

    async def explain(
        self, *, claim_text: str, fit_tags: frozenset[str], context_snapshot_ref: str
    ) -> ModelDraft:
        if not claim_text.strip():
            raise PathDraftError("candidate explanation requires non-empty claim_text")
        if not context_snapshot_ref.strip():
            raise PathDraftError("candidate explanation requires a context_snapshot_ref")
        request = StructuredRequest(
            use_case=CANDIDATE_EXPLANATION_USE_CASE,
            prompt_version="v1",
            schema_version="v1",
            data_class=self._data_class,
            payload={"claim_text": claim_text, "fit_tags": sorted(fit_tags)},
            output_schema=CANDIDATE_EXPLANATION_OUTPUT_SCHEMA,
            context_snapshot_ref=context_snapshot_ref,
            prompt_execution_plan=_reviewed_prompt_execution_plan(),
        )
        try:
            return await self._gateway.generate_structured(request, provider_id=self._provider_id)
        except ModelGatewayError:
            raise


__all__ = [
    "CANDIDATE_EXPLANATION_OUTPUT_SCHEMA",
    "CANDIDATE_EXPLANATION_USE_CASE",
    "GatewayBackedCandidateExplanationAdapter",
]
