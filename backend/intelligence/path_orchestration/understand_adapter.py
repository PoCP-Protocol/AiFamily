"""Real Model-Gateway-backed UNDERSTAND primitive for path_orchestration.

Answers ADR-0158's "Slice C-01 从头到尾没有调用过一次AI" challenge (see the
ADR's "Codex 回应 Claude ... Slice C-01 零模型调用" and follow-up threads):
`ContextDrivenPathDraftPlanner` in `planner.py` stays a deterministic
scaffold (schema/scope/dedup/replay guardrails, per that discussion's
decision point 2) and this module adds the actual generative seam next to it.

Compliance boundary, not a style choice: `FamilyPathContext` carries
`need_statement`, `evidence[].excerpt`, `tenant_id`, `family_id`, `need_id` and
`context_snapshot_ref` — every one of those can identify a specific family or
minor subject. No currently-registered external provider has
`minor_data_allowed=True` (see `provider_registry.DEFAULT_PROVIDER_RECORDS`
and `ibm_ica_wiring.py`'s explicit 第16条 gap), so none of those fields may
reach `StructuredRequest.payload`. `_de_identify` is the enforcement point:
it produces an `UnderstandProbe` containing only `fit_tags` and `unknowns` —
categorical labels, not family-identifying content — and this module never
constructs a `StructuredRequest` from anything else.
"""

from __future__ import annotations

import hashlib
from typing import Protocol

from backend.intelligence.model_gateway.contracts import (
    ModelDraft,
    PromptExecutionPlan,
    StructuredRequest,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import ModelGateway

from .contracts import FamilyPathContext, PathDraftError

UNDERSTAND_USE_CASE = "path_orchestration_understand_v1"
UNDERSTAND_OUTPUT_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "perspective": {"type": "string"},
        "guiding_question": {"type": "string"},
    },
    "required": ["perspective", "guiding_question"],
    "additionalProperties": False,
}

_UNDERSTAND_TEMPLATE = (
    "You receive a de-identified set of category tags describing a family's "
    "stated growth focus (`fit_tags`) and open unknowns (`unknowns`). You do "
    "not receive and must not infer any family-identifying detail. Return a "
    "short, non-diagnostic `perspective` (one interpretation of what these tags "
    "suggest, phrased as an observation a human reviewer can accept, edit, or "
    "reject) and one `guiding_question` a guardian could answer to narrow the "
    "unknowns. Never produce a score, ranking, or diagnosis."
)
_UNDERSTAND_SYSTEM_POLICY = (
    "You are a bounded interpretation assistant for a family-growth platform. "
    "Input is category tags only, never family-identifying content. Output "
    "must match the given JSON schema exactly. Never claim certainty, never "
    "diagnose, never rank or score a family."
)


class UnderstandProbe:
    """De-identified projection of a `FamilyPathContext` — the only shape this
    module is allowed to send to a model provider."""

    __slots__ = ("fit_tags", "unknowns")

    def __init__(self, fit_tags: frozenset[str], unknowns: tuple[str, ...]) -> None:
        self.fit_tags = fit_tags
        self.unknowns = unknowns

    def to_payload(self) -> dict:
        return {
            "fit_tags": sorted(self.fit_tags),
            "unknowns": list(self.unknowns),
        }


def de_identify(context: FamilyPathContext) -> UnderstandProbe:
    """The enforcement point: strips every family/minor-identifying field.

    Deliberately does not accept or forward `tenant_id`, `family_id`,
    `need_id`, `need_statement`, or `evidence[].excerpt` — see module
    docstring. Only categorical `fit_tags`/`unknowns` survive.
    """

    return UnderstandProbe(fit_tags=context.fit_tags, unknowns=context.unknowns)


def _reviewed_prompt_execution_plan() -> PromptExecutionPlan:
    """Fixed, in-code reviewed prompt for the UNDERSTAND primitive.

    A real content-review workflow (versioned registry entry, sign-off ref)
    is a separate decision for whoever owns prompt governance — see
    ADR-0158. This is the minimum needed for `StructuredRequest` to pass its
    own `PromptExecutionPlan` requirement honestly: the template and policy
    below are the actual text sent, not a placeholder swapped later.
    """

    return PromptExecutionPlan(
        prompt_ref=UNDERSTAND_USE_CASE,
        prompt_version="v1",
        template=_UNDERSTAND_TEMPLATE,
        system_policy_ref="path_orchestration_understand_policy_v1",
        safety_policy_version="v1",
        knowledge_refs=(),
        asset_digest=hashlib.sha256(_UNDERSTAND_TEMPLATE.encode()).hexdigest(),
        system_policy=_UNDERSTAND_SYSTEM_POLICY,
        system_policy_digest=hashlib.sha256(_UNDERSTAND_SYSTEM_POLICY.encode()).hexdigest(),
        knowledge_materials=(),
        material_digest=hashlib.sha256(b"path_orchestration_understand_no_knowledge").hexdigest(),
    )


class UnderstandPort(Protocol):
    async def understand(
        self, *, probe: UnderstandProbe, context_snapshot_ref: str
    ) -> ModelDraft: ...


class GatewayBackedUnderstandAdapter:
    """Real UNDERSTAND primitive: routes through the shared Model Gateway.

    Never imports a provider SDK directly (R7) — `gateway` is the caller's
    already-admitted `ModelGateway`, built the same way every other real
    caller in this repository builds one
    (`backend.intelligence.model_gateway.gateway.build_gateway` /
    `backend.intelligence.model_gateway.ibm_ica_wiring.build_livecheck_ibm_ica_gateway`).
    This class adds no second model entry point.
    """

    def __init__(
        self, gateway: ModelGateway, *, provider_id: str, data_class: str = "OPERATIONAL_TEXT"
    ) -> None:
        if data_class not in ("OPERATIONAL_TEXT", "SYNTHETIC"):
            raise PathDraftError(
                "UNDERSTAND adapter only ever sends de-identified category tags — "
                "FAMILY_PRIVATE_TEXT/MINOR_PERSONAL_DATA are not de-identifiable "
                "shapes and must never be requested here"
            )
        self._gateway = gateway
        self._provider_id = provider_id
        self._data_class = data_class

    async def understand(self, *, probe: UnderstandProbe, context_snapshot_ref: str) -> ModelDraft:
        if not context_snapshot_ref.strip():
            raise PathDraftError("understand requires a context_snapshot_ref")
        request = StructuredRequest(
            use_case=UNDERSTAND_USE_CASE,
            prompt_version="v1",
            schema_version="v1",
            data_class=self._data_class,
            payload=probe.to_payload(),
            output_schema=UNDERSTAND_OUTPUT_SCHEMA,
            context_snapshot_ref=context_snapshot_ref,
            prompt_execution_plan=_reviewed_prompt_execution_plan(),
        )
        try:
            return await self._gateway.generate_structured(request, provider_id=self._provider_id)
        except ModelGatewayError:
            raise


__all__ = [
    "UNDERSTAND_OUTPUT_SCHEMA",
    "UNDERSTAND_USE_CASE",
    "GatewayBackedUnderstandAdapter",
    "UnderstandPort",
    "UnderstandProbe",
    "de_identify",
]
