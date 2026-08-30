"""High-autonomy commercial insight analysis through the Model Gateway.

The analyst is intentionally broader than a summarizer: it asks the model for
an insight statement, an opportunity signal, assumptions and a next validation
direction.  It still returns the gateway's ``ModelDraft`` and never writes a
``product_intelligence`` entity.  A business application may later promote the
draft through its own Named Action.
"""

from __future__ import annotations

from collections.abc import Sequence

from backend.intelligence.model_gateway.contracts import ModelDraft, StructuredRequest
from backend.intelligence.model_gateway.gateway import ModelGateway

MARKET_INSIGHT_USE_CASE = "market.insight.generate"
MARKET_INSIGHT_SCHEMA_VERSION = "market-insight.v1"

MARKET_INSIGHT_OUTPUT_SCHEMA = {
    "type": "object",
    "required": ["statement", "opportunity_signal", "assumptions", "evidence_refs"],
    "properties": {
        "statement": {"type": "string"},
        "opportunity_signal": {"type": "string"},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "evidence_refs": {"type": "array", "items": {"type": "string"}},
    },
}


def build_market_insight_request(
    *,
    signal_id: str,
    signal_text: str,
    evidence_refs: Sequence[str],
    context_snapshot_ref: str,
    prompt_version: str = "market-insight.v1",
) -> StructuredRequest:
    """Build a structured request for the high-autonomy analyst."""

    if not signal_id.strip() or not signal_text.strip():
        raise ValueError("MARKET_INSIGHT_SIGNAL_REQUIRED")
    refs = tuple(ref.strip() for ref in evidence_refs)
    if not refs or any(not ref for ref in refs):
        raise ValueError("MARKET_INSIGHT_EVIDENCE_REQUIRED")
    if len(set(refs)) != len(refs):
        raise ValueError("MARKET_INSIGHT_EVIDENCE_DUPLICATE")
    return StructuredRequest(
        use_case=MARKET_INSIGHT_USE_CASE,
        prompt_version=prompt_version,
        schema_version=MARKET_INSIGHT_SCHEMA_VERSION,
        data_class="OPERATIONAL_TEXT",
        payload={
            "task": (
                "Analyze the market signal, identify a bounded customer insight, state the "
                "opportunity signal, list assumptions, and propose what to validate next. "
                "Do not claim causality or business success."
            ),
            "signal_id": signal_id,
            "signal_text": signal_text,
            "evidence_refs": list(refs),
        },
        output_schema=MARKET_INSIGHT_OUTPUT_SCHEMA,
        context_snapshot_ref=context_snapshot_ref,
        input_refs=refs,
    )


def validate_market_insight_draft(
    draft: ModelDraft,
    *,
    allowed_evidence_refs: Sequence[str],
) -> ModelDraft:
    """Reject fabricated citations and malformed semantic fields.

    The JSON schema proves shape, not truth.  The model's self-reported
    references are accepted only when they are a non-empty subset of the
    caller-supplied evidence allow-list.
    """

    output = draft.output
    statement = output.get("statement")
    opportunity_signal = output.get("opportunity_signal")
    assumptions = output.get("assumptions")
    refs = output.get("evidence_refs")
    if not isinstance(statement, str) or not statement.strip():
        raise ValueError("MARKET_INSIGHT_STATEMENT_REQUIRED")
    if not isinstance(opportunity_signal, str) or not opportunity_signal.strip():
        raise ValueError("MARKET_INSIGHT_OPPORTUNITY_SIGNAL_REQUIRED")
    if not isinstance(assumptions, list) or any(
        not isinstance(item, str) or not item.strip() for item in assumptions
    ):
        raise ValueError("MARKET_INSIGHT_ASSUMPTIONS_INVALID")
    if (
        not isinstance(refs, list)
        or not refs
        or any(not isinstance(item, str) or not item.strip() for item in refs)
    ):
        raise ValueError("MARKET_INSIGHT_EVIDENCE_REQUIRED")
    allowed = {ref.strip() for ref in allowed_evidence_refs if ref.strip()}
    if not set(refs).issubset(allowed):
        raise ValueError("MARKET_INSIGHT_EVIDENCE_REFERENCE_NOT_ALLOWED")
    if len(set(refs)) != len(refs):
        raise ValueError("MARKET_INSIGHT_EVIDENCE_DUPLICATE")
    return draft


async def run_market_insight_draft(
    gateway: ModelGateway,
    *,
    provider_id: str,
    signal_id: str,
    signal_text: str,
    evidence_refs: Sequence[str],
    context_snapshot_ref: str,
    prompt_version: str = "market-insight.v1",
) -> ModelDraft:
    """Run an autonomous analysis and return a validated, non-mutating draft."""

    request = build_market_insight_request(
        signal_id=signal_id,
        signal_text=signal_text,
        evidence_refs=evidence_refs,
        context_snapshot_ref=context_snapshot_ref,
        prompt_version=prompt_version,
    )
    draft = await gateway.generate_structured(request, provider_id=provider_id)
    return validate_market_insight_draft(draft, allowed_evidence_refs=evidence_refs)
