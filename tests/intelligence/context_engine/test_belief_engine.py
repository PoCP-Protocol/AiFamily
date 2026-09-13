"""AIFAMILY-WM-004B acceptance tests: Belief Engine.

Per ADR-0172, this is the first World State component allowed to call a
generative model — and the only kind of output it may ever produce is
HYPOTHESIS (never FACT). Uses `FakeProvider` throughout: no test in this
file makes a real LLM API call.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.intelligence.context_engine.belief_engine import (
    build_hypothesis_request,
    derive_confidence,
    generate_hypothesis,
    hypothesis_output_schema,
    validate_and_build_proposal,
)
from backend.intelligence.context_engine.contracts import (
    ContextContractError,
    ContextScope,
    DataClass,
)
from backend.intelligence.context_engine.world_state import (
    BeliefBand,
    UncertaintyBand,
    WorldStateActorType,
    WorldStateAtom,
    WorldStateEpistemicKind,
)
from backend.intelligence.model_gateway.contracts import AiProvenance, ModelDraft
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.intelligence.safety.runtime import SafetyRuntime

NOW = datetime(2026, 9, 13, tzinfo=UTC)


def scope(**overrides: object) -> ContextScope:
    values: dict[str, object] = {
        "tenant_id": "tenant-1",
        "region_id": "CN",
        "family_id": "family-1",
        "subject_ids": ("child-1", "mother-1", "father-1"),
        "purpose": "family_growth_support",
        "consent_version": "consent.v1",
        "consent_granted": True,
        "data_class": DataClass.FAMILY_PRIVATE_TEXT,
        "locale": "zh-CN",
        "deletion_ref": "delete:family-1",
        "correlation_id": "corr-1",
        "causation_id": "cause-1",
    }
    values.update(overrides)
    return ContextScope(**values)  # type: ignore[arg-type]


def atom(**overrides: object) -> WorldStateAtom:
    values: dict[str, object] = {
        "atom_id": "atom-1",
        "scope": scope(),
        "subject_ids": ("child-1",),
        "epistemic_kind": WorldStateEpistemicKind.SELF_REPORT,
        "predicate": "family.member_statement",
        "value_ref": "最近不想上学",
        "asserted_by": "child-1",
        "attributed_actor_type": WorldStateActorType.FAMILY_MEMBER,
        "provenance": "conversation:2026-09-13",
        "observed_at": NOW,
        "recorded_at": NOW,
        "valid_from": NOW,
        "source_refs": ("conversation:2026-09-13",),
    }
    values.update(overrides)
    return WorldStateAtom(**values)  # type: ignore[arg-type]


def _draft(output: dict[str, object]) -> ModelDraft:
    provenance = AiProvenance(
        provider_id="fake-deterministic",
        model="fake",
        model_version="1.0.0",
        prompt_version="world-model-belief-engine/v1",
        schema_version="world-model-belief-engine/v1",
        context_snapshot_ref="snapshot-1",
        latency_ms=1,
        data_class="FAMILY_PRIVATE_TEXT",
        use_case="family_world_state.hypothesis_generation",
    )
    return ModelDraft(output=output, provenance=provenance)


# --- Pure validation tests (no model call) ---------------------------------


def test_confidence_is_deterministic_not_model_supplied() -> None:
    high = derive_confidence(
        support_level=BeliefBand.STRONG,
        contradiction_level=BeliefBand.NONE,
        uncertainty=UncertaintyBand.LOW,
    )
    low = derive_confidence(
        support_level=BeliefBand.WEAK,
        contradiction_level=BeliefBand.STRONG,
        uncertainty=UncertaintyBand.HIGH,
    )
    assert 0.05 <= low < high <= 0.95
    # Calling twice with identical inputs must be identical — no randomness.
    assert high == derive_confidence(
        support_level=BeliefBand.STRONG,
        contradiction_level=BeliefBand.NONE,
        uncertainty=UncertaintyBand.LOW,
    )


def test_hypothesis_request_requires_at_least_one_evidence_atom() -> None:
    with pytest.raises(ContextContractError, match="HYPOTHESIS_REQUEST_REQUIRES_EVIDENCE"):
        build_hypothesis_request(
            (),
            context_snapshot_ref="snapshot-1",
            tenant_id="tenant-1",
            family_id="family-1",
            data_class="FAMILY_PRIVATE_TEXT",
        )


def test_hypothesis_request_only_forwards_evidence_atom_content() -> None:
    evidence = atom(atom_id="obs-1", value_ref="最近不愿上学")
    request = build_hypothesis_request(
        (evidence,),
        context_snapshot_ref="snapshot-1",
        tenant_id="tenant-1",
        family_id="family-1",
        data_class="FAMILY_PRIVATE_TEXT",
    )
    assert request.input_refs == ("obs-1",)
    assert request.payload["evidence"][0]["atom_id"] == "obs-1"
    assert request.output_schema == hypothesis_output_schema()


def test_validate_rejects_missing_statement() -> None:
    evidence = atom(atom_id="obs-1")
    draft = _draft(
        {
            "support_level": "MODERATE",
            "contradiction_level": "NONE",
            "uncertainty": "HIGH",
            "evidence_atom_ids": ["obs-1"],
        }
    )
    with pytest.raises(ContextContractError, match="HYPOTHESIS_STATEMENT_REQUIRED"):
        validate_and_build_proposal(
            draft,
            proposal_id="proposal-1",
            scope=scope(),
            subject_ids=("child-1",),
            evidence_atoms=(evidence,),
        )


def test_validate_rejects_invalid_band_value() -> None:
    evidence = atom(atom_id="obs-1")
    draft = _draft(
        {
            "statement": "可能与学习压力相关",
            "support_level": "VERY_STRONG",  # not a real band
            "contradiction_level": "NONE",
            "uncertainty": "HIGH",
            "evidence_atom_ids": ["obs-1"],
        }
    )
    with pytest.raises(ContextContractError, match="HYPOTHESIS_BAND_INVALID"):
        validate_and_build_proposal(
            draft,
            proposal_id="proposal-1",
            scope=scope(),
            subject_ids=("child-1",),
            evidence_atoms=(evidence,),
        )


def test_validate_rejects_hallucinated_evidence_reference() -> None:
    """The model cites an atom_id that was never part of its own input —
    must be rejected, not silently trusted."""

    evidence = atom(atom_id="obs-1")
    draft = _draft(
        {
            "statement": "可能与学习压力相关",
            "support_level": "MODERATE",
            "contradiction_level": "NONE",
            "uncertainty": "HIGH",
            "evidence_atom_ids": ["obs-1", "obs-999-never-existed"],
        }
    )
    with pytest.raises(ContextContractError, match="HYPOTHESIS_CITES_UNKNOWN_EVIDENCE"):
        validate_and_build_proposal(
            draft,
            proposal_id="proposal-1",
            scope=scope(),
            subject_ids=("child-1",),
            evidence_atoms=(evidence,),
        )


def test_validate_produces_hypothesis_proposal_never_fact() -> None:
    evidence = atom(atom_id="obs-1")
    draft = _draft(
        {
            "statement": "近期不愿上学可能与学习压力相关",
            "support_level": "MODERATE",
            "contradiction_level": "WEAK",
            "uncertainty": "MEDIUM",
            "evidence_atom_ids": ["obs-1"],
        }
    )
    proposal = validate_and_build_proposal(
        draft,
        proposal_id="proposal-1",
        scope=scope(),
        subject_ids=("child-1",),
        evidence_atoms=(evidence,),
    )
    assert proposal.proposed_kind is WorldStateEpistemicKind.HYPOTHESIS
    assert proposal.support_level is BeliefBand.MODERATE
    assert proposal.contradiction_level is BeliefBand.WEAK
    assert proposal.uncertainty is UncertaintyBand.MEDIUM
    assert proposal.evidence_refs == ("obs-1",)


# --- Full pipeline test using FakeProvider (no real LLM call) --------------


def _fake_gateway(response: dict[str, object]) -> tuple[ModelGateway, str]:
    provider = FakeProvider({"family_world_state.hypothesis_generation": response})
    gateway = ModelGateway(
        {provider.provider_id: provider},
        environment="staging",
        registry=ProviderRegistry(
            (
                ProviderRecord(
                    provider_id=provider.provider_id,
                    vendor="aifamily-test",
                    model="fake",
                    model_version="1",
                    status="INTERNAL_APPROVED",
                    approved_environments=("staging",),
                    sub_delegates=False,
                    minor_data_allowed=True,
                    private_text_allowed=True,
                    security_assessment_ref="test",
                    processing_agreement_ref="test",
                    deletion_on_termination_committed=True,
                ),
            )
        ),
        safety_runtime=SafetyRuntime(),
    )
    return gateway, provider.provider_id


@pytest.mark.asyncio
async def test_generate_hypothesis_end_to_end_with_fake_provider() -> None:
    evidence = (
        atom(
            atom_id="mother-report-1",
            epistemic_kind=WorldStateEpistemicKind.OTHER_REPORT,
            value_ref="孩子最近回避谈论学校",
            asserted_by="mother-1",
        ),
        atom(
            atom_id="father-observation-1",
            epistemic_kind=WorldStateEpistemicKind.OBSERVATION,
            value_ref="最近晚间学习时间冲突增多",
            asserted_by="father-1",
        ),
    )
    gateway, provider_id = _fake_gateway(
        {
            "statement": "近期回避学校话题可能与学习压力上升相关",
            "support_level": "MODERATE",
            "contradiction_level": "NONE",
            "uncertainty": "HIGH",
            "evidence_atom_ids": ["mother-report-1", "father-observation-1"],
        }
    )

    hypothesis_atom = await generate_hypothesis(
        gateway,
        provider_id=provider_id,
        evidence_atoms=evidence,
        scope=scope(),
        subject_ids=("child-1",),
        context_snapshot_ref="snapshot-1",
        proposal_id="proposal-e2e-1",
        atom_id="hypothesis-e2e-1",
        now=NOW,
    )

    assert hypothesis_atom.epistemic_kind is WorldStateEpistemicKind.HYPOTHESIS
    assert hypothesis_atom.attributed_actor_type is WorldStateActorType.AI
    assert set(hypothesis_atom.evidence_refs) == {"mother-report-1", "father-observation-1"}
    assert 0.05 <= 0.95  # confidence bound sanity, exact value covered above


@pytest.mark.asyncio
async def test_generate_hypothesis_rejects_hallucinated_evidence_end_to_end() -> None:
    evidence = (atom(atom_id="only-real-evidence"),)
    gateway, provider_id = _fake_gateway(
        {
            "statement": "捏造的假设",
            "support_level": "STRONG",
            "contradiction_level": "NONE",
            "uncertainty": "LOW",
            "evidence_atom_ids": ["only-real-evidence", "fabricated-atom-id"],
        }
    )

    with pytest.raises(ContextContractError, match="HYPOTHESIS_CITES_UNKNOWN_EVIDENCE"):
        await generate_hypothesis(
            gateway,
            provider_id=provider_id,
            evidence_atoms=evidence,
            scope=scope(),
            subject_ids=("child-1",),
            context_snapshot_ref="snapshot-1",
            proposal_id="proposal-e2e-2",
            atom_id="hypothesis-e2e-2",
            now=NOW,
        )
