"""AIFAMILY-WM-004C acceptance tests: Unknown Engine.

Same discipline as `test_belief_engine.py`: deterministic scoring/ranking/
priority has no model dependency at all; the generative half is gated
behind `ModelGateway` + `FakeProvider`, no real LLM API call anywhere here.
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
from backend.intelligence.context_engine.unknown_engine import (
    UNKNOWN_USE_CASE,
    AnswerabilityBand,
    ImpactBand,
    InformationValueInputs,
    UnknownPriority,
    UrgencyBand,
    build_unknown_request,
    compute_information_value,
    compute_priority,
    generate_unknown,
    rank_unknowns,
    validate_and_build_unknown,
)
from backend.intelligence.context_engine.unknown_identity import build_unknown_key
from backend.intelligence.context_engine.world_state import (
    BeliefBand,
    UncertaintyBand,
    UnknownState,
    UnknownStatus,
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

ALLOWED_PREDICATES = ("child.school_engagement", "child.parent_communication")


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


def hypothesis_atom(**overrides: object) -> WorldStateAtom:
    values: dict[str, object] = {
        "atom_id": "hyp-1",
        "scope": scope(),
        "subject_ids": ("child-1",),
        "epistemic_kind": WorldStateEpistemicKind.HYPOTHESIS,
        "predicate": "family.member_statement",
        "value_ref": "近期不愿上学可能与学习压力相关",
        "asserted_by": "AI",
        "attributed_actor_type": WorldStateActorType.AI,
        "provenance": "belief-engine:test",
        "observed_at": NOW,
        "recorded_at": NOW,
        "valid_from": NOW,
        "source_refs": ("obs-1",),
        "evidence_refs": ("obs-1",),
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
        prompt_version="world-model-unknown-engine/v1",
        schema_version="world-model-unknown-engine/v1",
        context_snapshot_ref="snapshot-1",
        latency_ms=1,
        data_class="FAMILY_PRIVATE_TEXT",
        use_case="family_world_state.unknown_generation",
    )
    return ModelDraft(output=output, provenance=provenance)


# --- Deterministic scoring/ranking/priority (no model at all) --------------


def test_information_value_is_deterministic() -> None:
    inputs = InformationValueInputs(
        decision_impact=ImpactBand.HIGH,
        uncertainty=UncertaintyBand.HIGH,
        answerability=AnswerabilityBand.HIGH,
        urgency=UrgencyBand.HIGH,
    )
    first = compute_information_value(inputs)
    second = compute_information_value(inputs)
    assert first == second
    assert 0.0 < first < 1.0


def test_higher_bands_yield_higher_information_value() -> None:
    high = compute_information_value(
        InformationValueInputs(
            ImpactBand.HIGH, UncertaintyBand.HIGH, AnswerabilityBand.HIGH, UrgencyBand.HIGH
        )
    )
    low = compute_information_value(
        InformationValueInputs(
            ImpactBand.LOW, UncertaintyBand.LOW, AnswerabilityBand.LOW, UrgencyBand.LOW
        )
    )
    assert high > low


def test_compute_priority_is_deterministic_not_model_supplied() -> None:
    critical = compute_priority(
        decision_impact=ImpactBand.HIGH,
        answerability=AnswerabilityBand.HIGH,
        urgency=UrgencyBand.HIGH,
    )
    low = compute_priority(
        decision_impact=ImpactBand.LOW, answerability=AnswerabilityBand.LOW, urgency=UrgencyBand.LOW
    )
    assert critical is UnknownPriority.CRITICAL
    assert low is UnknownPriority.LOW
    assert critical == compute_priority(
        decision_impact=ImpactBand.HIGH,
        answerability=AnswerabilityBand.HIGH,
        urgency=UrgencyBand.HIGH,
    )


def test_rank_unknowns_orders_by_information_value_descending() -> None:
    u1 = UnknownState(
        unknown_id="u1",
        scope=scope(),
        subject_ids=("child-1",),
        question="低优先级问题",
        why_it_matters="次要",
    )
    u2 = UnknownState(
        unknown_id="u2",
        scope=scope(),
        subject_ids=("child-1",),
        question="高优先级问题",
        why_it_matters="关键",
    )
    low_inputs = InformationValueInputs(
        ImpactBand.LOW, UncertaintyBand.LOW, AnswerabilityBand.LOW, UrgencyBand.LOW
    )
    high_inputs = InformationValueInputs(
        ImpactBand.HIGH, UncertaintyBand.HIGH, AnswerabilityBand.HIGH, UrgencyBand.HIGH
    )

    ranked = rank_unknowns([(u1, low_inputs), (u2, high_inputs)])
    assert ranked[0].unknown_id == "u2"
    assert ranked[1].unknown_id == "u1"


def test_rank_unknowns_breaks_ties_deterministically_by_id() -> None:
    same_inputs = InformationValueInputs(
        ImpactBand.MEDIUM, UncertaintyBand.MEDIUM, AnswerabilityBand.MEDIUM, UrgencyBand.MEDIUM
    )
    u_b = UnknownState(
        unknown_id="b", scope=scope(), subject_ids=("child-1",), question="q1", why_it_matters="w1"
    )
    u_a = UnknownState(
        unknown_id="a", scope=scope(), subject_ids=("child-1",), question="q2", why_it_matters="w2"
    )

    ranked = rank_unknowns([(u_b, same_inputs), (u_a, same_inputs)])
    assert [u.unknown_id for u in ranked] == ["a", "b"]


# --- Pure validation tests (no model call) ---------------------------------


def test_unknown_request_requires_at_least_one_hypothesis() -> None:
    with pytest.raises(ContextContractError, match="UNKNOWN_REQUEST_REQUIRES_HYPOTHESES"):
        build_unknown_request(
            (),
            allowed_target_predicates=ALLOWED_PREDICATES,
            context_snapshot_ref="snapshot-1",
            tenant_id="tenant-1",
            family_id="family-1",
            data_class="FAMILY_PRIVATE_TEXT",
        )


def test_unknown_request_requires_allowed_target_predicates() -> None:
    with pytest.raises(
        ContextContractError, match="UNKNOWN_REQUEST_REQUIRES_ALLOWED_TARGET_PREDICATES"
    ):
        build_unknown_request(
            (hypothesis_atom(),),
            allowed_target_predicates=(),
            context_snapshot_ref="snapshot-1",
            tenant_id="tenant-1",
            family_id="family-1",
            data_class="FAMILY_PRIVATE_TEXT",
        )


def test_validate_rejects_missing_question() -> None:
    draft = _draft(
        {
            "why_it_matters": "重要",
            "target_predicate": "child.school_engagement",
            "decision_impact": "HIGH",
            "answerability": "HIGH",
            "urgency": "MEDIUM",
            "blocking_hypothesis_ids": ["hyp-1"],
        }
    )
    with pytest.raises(ContextContractError, match="UNKNOWN_QUESTION_REQUIRED"):
        validate_and_build_unknown(
            draft,
            unknown_id="unk-1",
            scope=scope(),
            subject_ids=("child-1",),
            hypotheses=(hypothesis_atom(),),
            allowed_target_predicates=ALLOWED_PREDICATES,
            existing_unknowns=(),
            created_at=NOW,
        )


def test_validate_rejects_target_predicate_not_in_allowlist() -> None:
    draft = _draft(
        {
            "question": "学校最近有没有变化？",
            "why_it_matters": "区分学校适应和其他原因",
            "target_predicate": "child_is_lazy_unregistered",
            "decision_impact": "HIGH",
            "answerability": "HIGH",
            "urgency": "MEDIUM",
            "blocking_hypothesis_ids": ["hyp-1"],
        }
    )
    with pytest.raises(ContextContractError, match="UNKNOWN_TARGET_PREDICATE_NOT_ALLOWED"):
        validate_and_build_unknown(
            draft,
            unknown_id="unk-1",
            scope=scope(),
            subject_ids=("child-1",),
            hypotheses=(hypothesis_atom(),),
            allowed_target_predicates=ALLOWED_PREDICATES,
            existing_unknowns=(),
            created_at=NOW,
        )


def test_validate_rejects_hallucinated_blocking_reference() -> None:
    draft = _draft(
        {
            "question": "学校最近有没有变化？",
            "why_it_matters": "区分学校适应和其他原因",
            "target_predicate": "child.school_engagement",
            "decision_impact": "HIGH",
            "answerability": "HIGH",
            "urgency": "MEDIUM",
            "blocking_hypothesis_ids": ["hyp-1", "hyp-999-never-existed"],
        }
    )
    with pytest.raises(ContextContractError, match="UNKNOWN_CITES_HALLUCINATED_BLOCKING_REF"):
        validate_and_build_unknown(
            draft,
            unknown_id="unk-1",
            scope=scope(),
            subject_ids=("child-1",),
            hypotheses=(hypothesis_atom(),),
            allowed_target_predicates=ALLOWED_PREDICATES,
            existing_unknowns=(),
            created_at=NOW,
        )


def test_validate_returns_none_for_duplicate_unknown_key_even_with_different_wording() -> None:
    """AIFAMILY-WM-004C B9: dedup is by canonical identity, not question
    text — a different phrasing of the same gap must still be recognized."""

    existing_key = build_unknown_key(
        tenant_id="tenant-1",
        family_id="family-1",
        subject_ids=("child-1",),
        target_predicate="child.school_engagement",
        blocking_refs=["hyp-1"],
        unknown_contract_version="world-model-unknown-engine/v1",
    )
    existing = UnknownState(
        unknown_id="unk-existing",
        scope=scope(),
        subject_ids=("child-1",),
        question="学校最近有没有变化？",
        why_it_matters="已经问过",
        target_predicate="child.school_engagement",
        blocking_refs=("hyp-1",),
        unknown_key=existing_key,
        status=UnknownStatus.OPEN,
    )
    draft = _draft(
        {
            "question": "最近学校方面是不是出了什么状况？",  # different wording
            "why_it_matters": "区分学校适应和其他原因",
            "target_predicate": "child.school_engagement",
            "decision_impact": "HIGH",
            "answerability": "HIGH",
            "urgency": "MEDIUM",
            "blocking_hypothesis_ids": ["hyp-1"],
        }
    )
    result = validate_and_build_unknown(
        draft,
        unknown_id="unk-new",
        scope=scope(),
        subject_ids=("child-1",),
        hypotheses=(hypothesis_atom(),),
        allowed_target_predicates=ALLOWED_PREDICATES,
        existing_unknowns=(existing,),
        created_at=NOW,
    )
    assert result is None


def test_validate_produces_open_unknown_with_canonical_identity() -> None:
    draft = _draft(
        {
            "question": "孩子自己认为最主要原因是什么？",
            "why_it_matters": "直接来源比第三方转述更可靠",
            "target_predicate": "child.parent_communication",
            "decision_impact": "HIGH",
            "answerability": "HIGH",
            "urgency": "HIGH",
            "blocking_hypothesis_ids": ["hyp-1"],
        }
    )
    unknown = validate_and_build_unknown(
        draft,
        unknown_id="unk-1",
        scope=scope(),
        subject_ids=("child-1",),
        hypotheses=(hypothesis_atom(),),
        allowed_target_predicates=ALLOWED_PREDICATES,
        existing_unknowns=(),
        created_at=NOW,
    )
    assert unknown is not None
    assert unknown.status is UnknownStatus.OPEN
    assert unknown.target_predicate == "child.parent_communication"
    assert unknown.blocking_refs == ("hyp-1",)
    assert unknown.priority == UnknownPriority.CRITICAL.value
    assert unknown.unknown_key == build_unknown_key(
        tenant_id="tenant-1",
        family_id="family-1",
        subject_ids=("child-1",),
        target_predicate="child.parent_communication",
        blocking_refs=["hyp-1"],
        unknown_contract_version="world-model-unknown-engine/v1",
    )


# --- Full pipeline test using FakeProvider (no real LLM call) --------------


_AGENT_ID = "family_world_model_cognition"


def _fake_runtime(response: dict[str, object]) -> tuple[AgentRuntime, AgentAuthorization]:
    """AIFAMILY-FIL-001: `generate_unknown()` now executes through
    `AgentRuntime`, not a directly-held `ModelGateway` — see
    `test_belief_engine._fake_runtime` for the same pattern."""

    provider = FakeProvider({"family_world_state.unknown_generation": response})
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
        allowed_use_cases=frozenset({UNKNOWN_USE_CASE}),
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
        allowed_use_cases=frozenset({UNKNOWN_USE_CASE}),
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
async def test_generate_unknown_end_to_end_with_fake_provider() -> None:
    runtime, authorization = _fake_runtime(
        {
            "question": "学校最近有没有发生明显变化？",
            "why_it_matters": "区分学校适应问题和其他原因",
            "target_predicate": "child.school_engagement",
            "decision_impact": "HIGH",
            "answerability": "MEDIUM",
            "urgency": "MEDIUM",
            "blocking_hypothesis_ids": ["hyp-1"],
        }
    )

    unknown = await generate_unknown(
        runtime,
        agent_id=_AGENT_ID,
        authorization=authorization,
        request_id="request-e2e-1",
        hypotheses=(hypothesis_atom(),),
        allowed_target_predicates=ALLOWED_PREDICATES,
        existing_unknowns=(),
        scope=scope(),
        subject_ids=("child-1",),
        context_snapshot_ref="snapshot-1",
        unknown_id="unk-e2e-1",
        now=NOW,
    )

    assert unknown is not None
    assert unknown.question == "学校最近有没有发生明显变化？"
    assert unknown.status is UnknownStatus.OPEN
    assert unknown.target_predicate == "child.school_engagement"


@pytest.mark.asyncio
async def test_generate_unknown_rejects_target_predicate_outside_allowlist_end_to_end() -> None:
    runtime, authorization = _fake_runtime(
        {
            "question": "学校最近有没有发生明显变化？",
            "why_it_matters": "区分学校适应问题和其他原因",
            "target_predicate": "not_a_real_predicate",
            "decision_impact": "HIGH",
            "answerability": "MEDIUM",
            "urgency": "MEDIUM",
            "blocking_hypothesis_ids": ["hyp-1"],
        }
    )

    with pytest.raises(Exception, match="UNKNOWN_TARGET_PREDICATE_NOT_ALLOWED|schema"):
        await generate_unknown(
            runtime,
            agent_id=_AGENT_ID,
            authorization=authorization,
            request_id="request-e2e-2",
            hypotheses=(hypothesis_atom(),),
            allowed_target_predicates=ALLOWED_PREDICATES,
            existing_unknowns=(),
            scope=scope(),
            subject_ids=("child-1",),
            context_snapshot_ref="snapshot-1",
            unknown_id="unk-e2e-2",
            now=NOW,
        )
