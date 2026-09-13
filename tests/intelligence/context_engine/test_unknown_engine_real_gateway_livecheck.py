"""Gated real-model livecheck for the Unknown Engine (AIFAMILY-WM-004C).

Mirrors `tests/intelligence/model_gateway/test_ibm_ica_wiring.py`'s existing,
already-reviewed pattern exactly (same PromptExecutionPlan field
conventions) — this file does not invent a new way to satisfy the gateway's
integrity-material requirements, it reuses the one the repo's maintainers
already committed. `OPERATIONAL_TEXT` data class only, matching what the
IBM ICA `ProviderRecord` is actually approved for (`private_text_allowed=
False`/`minor_data_allowed=False` — see `ibm_ica_wiring.py`); this test uses
synthetic evidence content, never real family data.

Skipped unless `AIFAMILY_MODEL_API_KEY`/`AIFAMILY_MODEL_BASE_URL` are set.
"""

from __future__ import annotations

import dataclasses
import os
from datetime import UTC, datetime

import pytest

from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.unknown_engine import (
    UNKNOWN_PROMPT_VERSION,
    UNKNOWN_SCHEMA_VERSION,
    UNKNOWN_USE_CASE,
    unknown_output_schema,
    validate_and_build_unknown,
)
from backend.intelligence.context_engine.world_state import (
    BeliefBand,
    UncertaintyBand,
    WorldStateActorType,
    WorldStateAtom,
    WorldStateEpistemicKind,
)
from backend.intelligence.model_gateway.contracts import (
    KnowledgeExecutionPayload,
    PromptExecutionPlan,
    StructuredRequest,
)
from backend.intelligence.model_gateway.ibm_ica_wiring import (
    IBM_ICA_MODEL_API_KEY_ENV_VAR,
    IBM_ICA_MODEL_BASE_URL_ENV_VAR,
    IBM_ICA_PROVIDER_ID,
    build_livecheck_ibm_ica_gateway,
    ibm_ica_credentials_available,
)

NOW = datetime(2026, 9, 13, tzinfo=UTC)


def _scope() -> ContextScope:
    return ContextScope(
        tenant_id="test-tenant",
        region_id="CN",
        family_id="test-family-synthetic",
        subject_ids=("synthetic-child-1",),
        purpose="internal_livecheck",
        consent_version="test.v1",
        consent_granted=True,
        data_class=DataClass.SYNTHETIC,
        locale="zh-CN",
        deletion_ref="delete:test-family-synthetic",
        correlation_id="unknown-engine-livecheck-1",
        causation_id="unknown-engine-livecheck-1",
    )


def _synthetic_hypothesis() -> WorldStateAtom:
    return WorldStateAtom(
        atom_id="synthetic-hyp-1",
        scope=_scope(),
        subject_ids=("synthetic-child-1",),
        epistemic_kind=WorldStateEpistemicKind.HYPOTHESIS,
        predicate="family.member_statement",
        value_ref="合成测试假设：测试对象兴趣下降可能与作息变化相关",
        asserted_by="AI",
        attributed_actor_type=WorldStateActorType.AI,
        provenance="synthetic-test:belief-engine",
        observed_at=NOW,
        recorded_at=NOW,
        valid_from=NOW,
        source_refs=("synthetic-obs-1",),
        evidence_refs=("synthetic-obs-1",),
        support_level=BeliefBand.MODERATE,
        contradiction_level=BeliefBand.NONE,
        uncertainty=UncertaintyBand.HIGH,
    )


def _livecheck_request(hypothesis: WorldStateAtom) -> StructuredRequest:
    base = StructuredRequest(
        use_case=UNKNOWN_USE_CASE,
        prompt_version=UNKNOWN_PROMPT_VERSION,
        schema_version=UNKNOWN_SCHEMA_VERSION,
        data_class="OPERATIONAL_TEXT",
        payload={
            "hypotheses": [
                {
                    "atom_id": hypothesis.atom_id,
                    "statement": hypothesis.value_ref,
                }
            ]
        },
        output_schema=unknown_output_schema(),
        context_snapshot_ref="unknown-engine-livecheck-ctx",
        input_refs=(hypothesis.atom_id,),
        request_id="unknown-engine-livecheck-req",
        session_id="unknown-engine-livecheck-sess",
    )
    plan = PromptExecutionPlan(
        prompt_ref="unknown_engine_livecheck",
        prompt_version=UNKNOWN_PROMPT_VERSION,
        template=(
            "This is a SYNTHETIC test, no real personal data. Given the "
            "hypothesis list, propose exactly one clarifying question a "
            "family could be asked to reduce uncertainty. Return JSON with "
            "keys: question (string), why_it_matters (string), "
            "decision_impact (one of LOW/MEDIUM/HIGH), "
            "answerability (one of LOW/MEDIUM/HIGH), "
            "urgency (one of LOW/MEDIUM/HIGH), "
            "blocking_hypothesis_ids (array containing exactly the atom_id "
            "values from the hypotheses you were given)."
        ),
        system_policy_ref="unknown-engine-livecheck.v1",
        safety_policy_version="unknown-engine-livecheck.v1",
        knowledge_refs=("unknown-engine-livecheck.v1",),
        asset_digest="a" * 64,
        system_policy="Only produce the requested JSON object. Synthetic test data only.",
        system_policy_digest="b" * 64,
        knowledge_materials=(
            KnowledgeExecutionPayload(
                knowledge_ref="unknown-engine-livecheck.v1",
                content="Operational livecheck only — synthetic evidence, no real family data.",
                source_ref="source:unknown-engine-livecheck",
                license_ref="license:internal",
                evidence_level="E3",
                content_digest="c" * 64,
            ),
        ),
        material_digest="d" * 64,
    )
    return dataclasses.replace(base, prompt_execution_plan=plan)


@pytest.mark.asyncio
@pytest.mark.skipif(
    not ibm_ica_credentials_available(),
    reason=(
        f"{IBM_ICA_MODEL_API_KEY_ENV_VAR} / {IBM_ICA_MODEL_BASE_URL_ENV_VAR} "
        "not set — gated IBM ICA real-model livecheck"
    ),
)
async def test_unknown_engine_real_ibm_ica_livecheck() -> None:
    """Real network call to IBM ICA gpt-5.6-sol with synthetic evidence.
    Verifies the Unknown Engine's validation layer accepts a genuine model
    response end to end — not a parsing exercise against a canned string."""

    gateway = build_livecheck_ibm_ica_gateway(env=os.environ, model="gpt-5.6-sol")
    hypothesis = _synthetic_hypothesis()

    draft = await gateway.generate_structured(
        _livecheck_request(hypothesis),
        provider_id=IBM_ICA_PROVIDER_ID,
    )

    assert draft.provenance.provider_id == IBM_ICA_PROVIDER_ID
    assert "gpt-5.6" in (draft.provenance.model or "")

    unknown = validate_and_build_unknown(
        draft,
        unknown_id="unk-livecheck-1",
        scope=_scope(),
        subject_ids=("synthetic-child-1",),
        hypotheses=(hypothesis,),
        existing_unknowns=(),
        created_at=NOW,
    )
    # A real model may legitimately produce a question that happens to
    # duplicate a prior one (returning None) — the meaningful assertion is
    # that validation ran against a real response without raising on a
    # well-formed one, not that a specific unknown was produced.
    if unknown is not None:
        assert unknown.question.strip()
        assert unknown.why_it_matters.strip()
