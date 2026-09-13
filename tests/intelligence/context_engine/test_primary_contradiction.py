"""Acceptance tests: Primary Contradiction Engine (Golden E2E stage R4.3).

Per this module's own docstring, a `PrimaryContradictionProposal` is never a
fact or diagnosis — it must always carry at least one alternative framing and
a categorical uncertainty band. Uses `FakeProvider` throughout: no test in
this file makes a real LLM API call.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.intelligence.agent_runtime.contracts import (
    AgentAuthorization,
    AgentDefinition,
    AuthorizationBudget,
)
from backend.intelligence.agent_runtime.gateway_port import ModelGatewayExecutionPort
from backend.intelligence.agent_runtime.runtime import AgentRuntime
from backend.intelligence.context_engine.contracts import (
    ContextContractError,
    ContextScope,
    DataClass,
)
from backend.intelligence.context_engine.primary_contradiction import (
    PRIMARY_CONTRADICTION_USE_CASE,
    PrimaryContradictionProposal,
    build_primary_contradiction_request,
    generate_primary_contradiction,
    primary_contradiction_output_schema,
    validate_and_build_proposal,
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


def evidence_atom(**overrides: object) -> WorldStateAtom:
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


def hypothesis_atom(**overrides: object) -> WorldStateAtom:
    values: dict[str, object] = {
        "atom_id": "hyp-1",
        "scope": scope(),
        "subject_ids": ("child-1",),
        "epistemic_kind": WorldStateEpistemicKind.HYPOTHESIS,
        "predicate": "family.member_statement",
        "value_ref": "可能与学习压力相关",
        "asserted_by": "AI",
        "attributed_actor_type": WorldStateActorType.AI,
        "provenance": "snapshot-1",
        "observed_at": NOW,
        "recorded_at": NOW,
        "valid_from": NOW,
        "evidence_refs": ("atom-1",),
        "support_level": BeliefBand.MODERATE,
        "contradiction_level": BeliefBand.NONE,
        "uncertainty": UncertaintyBand.HIGH,
    }
    values.update(overrides)
    return WorldStateAtom(**values)  # type: ignore[arg-type]


def _draft(output: dict[str, object]) -> ModelDraft:
    provenance = AiProvenance(
        provider_id="fake-deterministic",
        model="fake",
        model_version="1.0.0",
        prompt_version="world-model-primary-contradiction/v1",
        schema_version="world-model-primary-contradiction/v1",
        context_snapshot_ref="snapshot-1",
        latency_ms=1,
        data_class="FAMILY_PRIVATE_TEXT",
        use_case="family_world_state.primary_contradiction_proposal",
    )
    return ModelDraft(output=output, provenance=provenance)


# --- Pure validation tests (no model call) ---------------------------------


def test_request_requires_at_least_one_evidence_atom() -> None:
    with pytest.raises(
        ContextContractError, match="PRIMARY_CONTRADICTION_REQUEST_REQUIRES_EVIDENCE"
    ):
        build_primary_contradiction_request(
            (),
            (),
            (),
            context_snapshot_ref="snapshot-1",
            tenant_id="tenant-1",
            family_id="family-1",
            data_class="FAMILY_PRIVATE_TEXT",
        )


def test_request_only_forwards_own_content() -> None:
    evidence = evidence_atom(atom_id="obs-1")
    hypothesis = hypothesis_atom(atom_id="hyp-1")
    request = build_primary_contradiction_request(
        (evidence,),
        (hypothesis,),
        (),
        context_snapshot_ref="snapshot-1",
        tenant_id="tenant-1",
        family_id="family-1",
        data_class="FAMILY_PRIVATE_TEXT",
    )
    assert request.input_refs == ("obs-1", "hyp-1")
    assert request.payload["evidence"][0]["atom_id"] == "obs-1"
    assert request.payload["hypotheses"][0]["atom_id"] == "hyp-1"
    assert request.output_schema == primary_contradiction_output_schema()


def test_validate_rejects_missing_statement() -> None:
    evidence = evidence_atom(atom_id="obs-1")
    draft = _draft(
        {
            "alternatives": ["也可能是同伴关系问题"],
            "uncertainty": "HIGH",
            "why_priority_now": "近期回避行为增多",
            "evidence_atom_ids": ["obs-1"],
            "supporting_hypothesis_ids": [],
            "contradiction_ids": [],
        }
    )
    with pytest.raises(ContextContractError, match="PRIMARY_CONTRADICTION_STATEMENT_REQUIRED"):
        validate_and_build_proposal(
            draft,
            proposal_id="proposal-1",
            scope=scope(),
            subject_ids=("child-1",),
            evidence_atoms=(evidence,),
            hypotheses=(),
            conflicts=(),
            created_at=NOW,
        )


def test_validate_rejects_missing_alternatives() -> None:
    evidence = evidence_atom(atom_id="obs-1")
    draft = _draft(
        {
            "statement": "核心张力是学业压力与亲子沟通不足",
            "alternatives": [],
            "uncertainty": "HIGH",
            "why_priority_now": "近期回避行为增多",
            "evidence_atom_ids": ["obs-1"],
            "supporting_hypothesis_ids": [],
            "contradiction_ids": [],
        }
    )
    with pytest.raises(ContextContractError, match="PRIMARY_CONTRADICTION_REQUIRES_ALTERNATIVES"):
        validate_and_build_proposal(
            draft,
            proposal_id="proposal-1",
            scope=scope(),
            subject_ids=("child-1",),
            evidence_atoms=(evidence,),
            hypotheses=(),
            conflicts=(),
            created_at=NOW,
        )


def test_validate_rejects_invalid_uncertainty_value() -> None:
    evidence = evidence_atom(atom_id="obs-1")
    draft = _draft(
        {
            "statement": "核心张力是学业压力与亲子沟通不足",
            "alternatives": ["也可能是同伴关系问题"],
            "uncertainty": "VERY_HIGH",  # not a real band
            "why_priority_now": "近期回避行为增多",
            "evidence_atom_ids": ["obs-1"],
            "supporting_hypothesis_ids": [],
            "contradiction_ids": [],
        }
    )
    with pytest.raises(ContextContractError, match="PRIMARY_CONTRADICTION_UNCERTAINTY_INVALID"):
        validate_and_build_proposal(
            draft,
            proposal_id="proposal-1",
            scope=scope(),
            subject_ids=("child-1",),
            evidence_atoms=(evidence,),
            hypotheses=(),
            conflicts=(),
            created_at=NOW,
        )


def test_validate_rejects_hallucinated_evidence_reference() -> None:
    evidence = evidence_atom(atom_id="obs-1")
    draft = _draft(
        {
            "statement": "核心张力是学业压力与亲子沟通不足",
            "alternatives": ["也可能是同伴关系问题"],
            "uncertainty": "HIGH",
            "why_priority_now": "近期回避行为增多",
            "evidence_atom_ids": ["obs-1", "obs-999-never-existed"],
            "supporting_hypothesis_ids": [],
            "contradiction_ids": [],
        }
    )
    with pytest.raises(ContextContractError, match="PRIMARY_CONTRADICTION_CITES_UNKNOWN_EVIDENCE"):
        validate_and_build_proposal(
            draft,
            proposal_id="proposal-1",
            scope=scope(),
            subject_ids=("child-1",),
            evidence_atoms=(evidence,),
            hypotheses=(),
            conflicts=(),
            created_at=NOW,
        )


def test_validate_rejects_hallucinated_hypothesis_reference() -> None:
    evidence = evidence_atom(atom_id="obs-1")
    hypothesis = hypothesis_atom(atom_id="hyp-1")
    draft = _draft(
        {
            "statement": "核心张力是学业压力与亲子沟通不足",
            "alternatives": ["也可能是同伴关系问题"],
            "uncertainty": "HIGH",
            "why_priority_now": "近期回避行为增多",
            "evidence_atom_ids": ["obs-1"],
            "supporting_hypothesis_ids": ["hyp-1", "hyp-999-never-existed"],
            "contradiction_ids": [],
        }
    )
    with pytest.raises(
        ContextContractError, match="PRIMARY_CONTRADICTION_CITES_UNKNOWN_HYPOTHESIS"
    ):
        validate_and_build_proposal(
            draft,
            proposal_id="proposal-1",
            scope=scope(),
            subject_ids=("child-1",),
            evidence_atoms=(evidence,),
            hypotheses=(hypothesis,),
            conflicts=(),
            created_at=NOW,
        )


def test_validate_produces_valid_proposal() -> None:
    evidence = evidence_atom(atom_id="obs-1")
    hypothesis = hypothesis_atom(atom_id="hyp-1")
    draft = _draft(
        {
            "statement": "核心张力是学业压力与亲子沟通不足",
            "alternatives": ["也可能是同伴关系问题", "也可能是睡眠不足导致情绪波动"],
            "uncertainty": "MEDIUM",
            "why_priority_now": "近两周回避行为明显增多，且家长已注意到情绪变化",
            "evidence_atom_ids": ["obs-1"],
            "supporting_hypothesis_ids": ["hyp-1"],
            "contradiction_ids": [],
        }
    )
    proposal = validate_and_build_proposal(
        draft,
        proposal_id="proposal-1",
        scope=scope(),
        subject_ids=("child-1",),
        evidence_atoms=(evidence,),
        hypotheses=(hypothesis,),
        conflicts=(),
        created_at=NOW,
    )
    assert isinstance(proposal, PrimaryContradictionProposal)
    assert proposal.statement == "核心张力是学业压力与亲子沟通不足"
    assert proposal.alternatives == (
        "也可能是同伴关系问题",
        "也可能是睡眠不足导致情绪波动",
    )
    assert proposal.uncertainty is UncertaintyBand.MEDIUM
    assert proposal.evidence_refs == ("obs-1",)
    assert proposal.supporting_hypothesis_refs == ("hyp-1",)
    assert proposal.contradiction_refs == ()


def test_proposal_construction_rejects_zero_alternatives_directly() -> None:
    """Belt and suspenders: the dataclass's own `__post_init__` must also
    reject an empty `alternatives` tuple, independent of the draft-level
    check in `validate_and_build_proposal`."""

    with pytest.raises(ContextContractError, match="PRIMARY_CONTRADICTION_REQUIRES_ALTERNATIVES"):
        PrimaryContradictionProposal(
            proposal_id="proposal-1",
            scope=scope(),
            subject_ids=("child-1",),
            statement="核心张力是学业压力与亲子沟通不足",
            evidence_refs=("obs-1",),
            supporting_hypothesis_refs=(),
            contradiction_refs=(),
            alternatives=(),
            uncertainty=UncertaintyBand.MEDIUM,
            why_priority_now="近两周回避行为明显增多",
            created_at=NOW,
        )


# --- Full pipeline test using FakeProvider (no real LLM call) --------------


_AGENT_ID = "family_world_model_cognition"


def _fake_runtime(response: dict[str, object]) -> tuple[AgentRuntime, AgentAuthorization]:
    """AIFAMILY-FIL-001: `generate_primary_contradiction()` executes through
    `AgentRuntime`, not a directly-held `ModelGateway` — mirrors
    `test_belief_engine._fake_runtime`."""

    provider = FakeProvider({"family_world_state.primary_contradiction_proposal": response})
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
    definition = AgentDefinition(
        agent_id=_AGENT_ID,
        name="Family World Model Cognition",
        allowed_use_cases=frozenset({PRIMARY_CONTRADICTION_USE_CASE}),
        context_policy="test-context-policy",
        safety_policy="test-safety-policy",
        human_handoff_policy="test-handoff-policy",
        budget_policy="test-budget-policy",
    )
    runtime = AgentRuntime(
        ModelGatewayExecutionPort(gateway, provider.provider_id),
        [definition],
    )
    authorization = AgentAuthorization(
        authorization_id="auth-test-1",
        agent_id=_AGENT_ID,
        tenant_id="tenant-1",
        family_id="family-1",
        allowed_use_cases=frozenset({PRIMARY_CONTRADICTION_USE_CASE}),
        allowed_tools=frozenset(),
        issued_by="test-suite",
        issued_at=NOW,
        expires_at=NOW.replace(year=NOW.year + 1),
        revoked_at=None,
        budget=AuthorizationBudget(max_steps=1),
        policy_version="test-policy-v1",
        reason="test",
        audit_ref="audit-test-1",
    )
    return runtime, authorization


@pytest.mark.asyncio
async def test_generate_primary_contradiction_end_to_end_with_fake_provider() -> None:
    evidence = (
        evidence_atom(
            atom_id="mother-report-1",
            epistemic_kind=WorldStateEpistemicKind.OTHER_REPORT,
            value_ref="孩子最近回避谈论学校",
            asserted_by="mother-1",
        ),
    )
    hypotheses = (hypothesis_atom(atom_id="hyp-1", evidence_refs=("mother-report-1",)),)
    runtime, authorization = _fake_runtime(
        {
            "statement": "核心张力是学业压力与亲子沟通不足",
            "alternatives": ["也可能是同伴关系问题"],
            "uncertainty": "MEDIUM",
            "why_priority_now": "近两周回避行为明显增多",
            "evidence_atom_ids": ["mother-report-1"],
            "supporting_hypothesis_ids": ["hyp-1"],
            "contradiction_ids": [],
        }
    )

    proposal = await generate_primary_contradiction(
        runtime,
        agent_id=_AGENT_ID,
        authorization=authorization,
        request_id="request-e2e-1",
        evidence_atoms=evidence,
        hypotheses=hypotheses,
        conflicts=(),
        scope=scope(),
        subject_ids=("child-1",),
        context_snapshot_ref="snapshot-1",
        proposal_id="proposal-e2e-1",
        now=NOW,
    )

    assert isinstance(proposal, PrimaryContradictionProposal)
    assert proposal.alternatives == ("也可能是同伴关系问题",)
    assert proposal.uncertainty is UncertaintyBand.MEDIUM
    assert proposal.evidence_refs == ("mother-report-1",)
    assert proposal.supporting_hypothesis_refs == ("hyp-1",)


@pytest.mark.asyncio
async def test_generate_primary_contradiction_rejects_hallucinated_hypothesis_end_to_end() -> None:
    evidence = (evidence_atom(atom_id="only-real-evidence"),)
    hypotheses = (hypothesis_atom(atom_id="only-real-hypothesis"),)
    runtime, authorization = _fake_runtime(
        {
            "statement": "捏造的矛盾",
            "alternatives": ["捏造的替代解释"],
            "uncertainty": "LOW",
            "why_priority_now": "捏造的紧迫性",
            "evidence_atom_ids": ["only-real-evidence"],
            "supporting_hypothesis_ids": ["only-real-hypothesis", "fabricated-hyp-id"],
            "contradiction_ids": [],
        }
    )

    with pytest.raises(
        ContextContractError, match="PRIMARY_CONTRADICTION_CITES_UNKNOWN_HYPOTHESIS"
    ):
        await generate_primary_contradiction(
            runtime,
            agent_id=_AGENT_ID,
            authorization=authorization,
            request_id="request-e2e-2",
            evidence_atoms=evidence,
            hypotheses=hypotheses,
            conflicts=(),
            scope=scope(),
            subject_ids=("child-1",),
            context_snapshot_ref="snapshot-1",
            proposal_id="proposal-e2e-2",
            now=NOW,
        )
