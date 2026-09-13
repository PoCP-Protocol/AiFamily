"""AIFAMILY-WM-005 acceptance tests: Goal Proposal.

`GoalProposal` is an AI-authored, not-yet-decided candidate goal generated
from a primary contradiction. Uses `FakeProvider` throughout: no test in this
file makes a real LLM API call.
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
from backend.intelligence.context_engine.goal_proposal import (
    GOAL_PROPOSAL_USE_CASE,
    build_goal_proposal_request,
    generate_goal_proposal,
    goal_proposal_output_schema,
    validate_and_build_goal_proposal,
)
from backend.intelligence.context_engine.world_state import (
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
        prompt_version="world-model-goal-proposal/v1",
        schema_version="world-model-goal-proposal/v1",
        context_snapshot_ref="snapshot-1",
        latency_ms=1,
        data_class="FAMILY_PRIVATE_TEXT",
        use_case="family_world_state.goal_proposal_generation",
    )
    return ModelDraft(output=output, provenance=provenance)


_VALID_OUTPUT: dict[str, object] = {
    "statement": "帮助孩子在未来两周内更愿意谈论学校话题",
    "desired_change": "孩子主动分享学校经历的频率提升",
    "success_criteria": ["孩子每周至少一次主动谈及学校话题"],
    "expected_observation": "家长记录到孩子主动谈及学校的次数增加",
    "measurement_window": "14 days",
    "failure_criteria": ["两周后孩子仍完全回避学校话题"],
    "stop_criteria": ["孩子明确表示不愿被追问此话题"],
    "escalation_criteria": ["孩子表现出自伤或危机信号"],
    "evidence_atom_ids": ["obs-1"],
}


# --- Pure validation tests (no model call) ---------------------------------


def test_goal_proposal_request_requires_at_least_one_evidence_atom() -> None:
    with pytest.raises(ContextContractError, match="GOAL_PROPOSAL_REQUEST_REQUIRES_EVIDENCE"):
        build_goal_proposal_request(
            (),
            primary_contradiction_statement="孩子想要独立但家长想要掌控",
            context_snapshot_ref="snapshot-1",
            tenant_id="tenant-1",
            family_id="family-1",
            data_class="FAMILY_PRIVATE_TEXT",
        )


def test_goal_proposal_request_forwards_evidence_and_contradiction() -> None:
    evidence = atom(atom_id="obs-1", value_ref="最近不愿上学")
    request = build_goal_proposal_request(
        (evidence,),
        primary_contradiction_statement="孩子想要独立但家长想要掌控",
        context_snapshot_ref="snapshot-1",
        tenant_id="tenant-1",
        family_id="family-1",
        data_class="FAMILY_PRIVATE_TEXT",
    )
    assert request.input_refs == ("obs-1",)
    assert request.payload["evidence"][0]["atom_id"] == "obs-1"
    assert request.payload["primary_contradiction_statement"] == "孩子想要独立但家长想要掌控"
    assert request.output_schema == goal_proposal_output_schema()


def test_validate_rejects_missing_success_criteria() -> None:
    evidence = atom(atom_id="obs-1")
    output = dict(_VALID_OUTPUT)
    output["success_criteria"] = []
    draft = _draft(output)
    with pytest.raises(ContextContractError, match="GOAL_PROPOSAL_REQUIRES_SUCCESS_CRITERIA"):
        validate_and_build_goal_proposal(
            draft,
            goal_proposal_id="goal-1",
            scope=scope(),
            subject_ids=("child-1",),
            evidence_atoms=(evidence,),
            family_need_ref=None,
            reasoning_ref="primary-contradiction-1",
            created_at=NOW,
        )


def test_validate_rejects_missing_failure_criteria() -> None:
    evidence = atom(atom_id="obs-1")
    output = dict(_VALID_OUTPUT)
    output["failure_criteria"] = []
    draft = _draft(output)
    with pytest.raises(ContextContractError, match="GOAL_PROPOSAL_REQUIRES_FAILURE_CRITERIA"):
        validate_and_build_goal_proposal(
            draft,
            goal_proposal_id="goal-1",
            scope=scope(),
            subject_ids=("child-1",),
            evidence_atoms=(evidence,),
            family_need_ref=None,
            reasoning_ref="primary-contradiction-1",
            created_at=NOW,
        )


def test_validate_rejects_missing_stop_criteria() -> None:
    evidence = atom(atom_id="obs-1")
    output = dict(_VALID_OUTPUT)
    output["stop_criteria"] = []
    draft = _draft(output)
    with pytest.raises(ContextContractError, match="GOAL_PROPOSAL_REQUIRES_STOP_CRITERIA"):
        validate_and_build_goal_proposal(
            draft,
            goal_proposal_id="goal-1",
            scope=scope(),
            subject_ids=("child-1",),
            evidence_atoms=(evidence,),
            family_need_ref=None,
            reasoning_ref="primary-contradiction-1",
            created_at=NOW,
        )


def test_validate_rejects_missing_escalation_criteria() -> None:
    evidence = atom(atom_id="obs-1")
    output = dict(_VALID_OUTPUT)
    output["escalation_criteria"] = []
    draft = _draft(output)
    with pytest.raises(ContextContractError, match="GOAL_PROPOSAL_REQUIRES_ESCALATION_CRITERIA"):
        validate_and_build_goal_proposal(
            draft,
            goal_proposal_id="goal-1",
            scope=scope(),
            subject_ids=("child-1",),
            evidence_atoms=(evidence,),
            family_need_ref=None,
            reasoning_ref="primary-contradiction-1",
            created_at=NOW,
        )


def test_validate_rejects_hallucinated_evidence_reference() -> None:
    """The model cites an atom_id that was never part of its own input —
    must be rejected, not silently trusted."""

    evidence = atom(atom_id="obs-1")
    output = dict(_VALID_OUTPUT)
    output["evidence_atom_ids"] = ["obs-1", "obs-999-never-existed"]
    draft = _draft(output)
    with pytest.raises(ContextContractError, match="GOAL_PROPOSAL_CITES_UNKNOWN_EVIDENCE"):
        validate_and_build_goal_proposal(
            draft,
            goal_proposal_id="goal-1",
            scope=scope(),
            subject_ids=("child-1",),
            evidence_atoms=(evidence,),
            family_need_ref=None,
            reasoning_ref="primary-contradiction-1",
            created_at=NOW,
        )


def test_validate_produces_goal_proposal_with_full_learning_contract() -> None:
    evidence = atom(atom_id="obs-1")
    draft = _draft(dict(_VALID_OUTPUT))
    proposal = validate_and_build_goal_proposal(
        draft,
        goal_proposal_id="goal-1",
        scope=scope(),
        subject_ids=("child-1",),
        evidence_atoms=(evidence,),
        family_need_ref="need-1",
        reasoning_ref="primary-contradiction-1",
        created_at=NOW,
    )
    assert proposal.goal_proposal_id == "goal-1"
    assert proposal.family_need_ref == "need-1"
    assert proposal.reasoning_ref == "primary-contradiction-1"
    assert proposal.success_criteria
    assert proposal.failure_criteria
    assert proposal.stop_criteria
    assert proposal.escalation_criteria
    assert proposal.expected_observation
    assert proposal.measurement_window == "14 days"
    assert proposal.evidence_refs == ("obs-1",)


def test_goal_proposal_allows_missing_family_need_ref() -> None:
    """A goal can be proposed before a formal Need record exists."""

    evidence = atom(atom_id="obs-1")
    draft = _draft(dict(_VALID_OUTPUT))
    proposal = validate_and_build_goal_proposal(
        draft,
        goal_proposal_id="goal-2",
        scope=scope(),
        subject_ids=("child-1",),
        evidence_atoms=(evidence,),
        family_need_ref=None,
        reasoning_ref="primary-contradiction-1",
        created_at=NOW,
    )
    assert proposal.family_need_ref is None


def test_goal_proposal_construction_rejects_empty_success_criteria_directly() -> None:
    """Even direct construction (bypassing validate_and_build_*) must reject
    an empty success_criteria tuple — the dataclass's own __post_init__ is
    the real enforcement point, not just the validator."""

    from backend.intelligence.context_engine.goal_proposal import GoalProposal

    with pytest.raises(ContextContractError, match="GOAL_PROPOSAL_REQUIRES_SUCCESS_CRITERIA"):
        GoalProposal(
            goal_proposal_id="goal-3",
            scope=scope(),
            subject_ids=("child-1",),
            statement="statement",
            desired_change="change",
            success_criteria=(),
            evidence_refs=("obs-1",),
            reasoning_ref="ref-1",
            expected_observation="observation",
            measurement_window="7 days",
            failure_criteria=("failure",),
            stop_criteria=("stop",),
            escalation_criteria=("escalation",),
            created_at=NOW,
        )


# --- Full pipeline test using FakeProvider (no real LLM call) --------------


_AGENT_ID = "family_world_model_cognition"


def _fake_runtime(response: dict[str, object]) -> tuple[AgentRuntime, AgentAuthorization]:
    """AIFAMILY-FIL-001: `generate_goal_proposal()` executes through
    `AgentRuntime`, not a directly-held `ModelGateway` — this builds a
    minimal real `AgentRuntime` (still backed by `FakeProvider`, still no
    real LLM API call)."""

    provider = FakeProvider({"family_world_state.goal_proposal_generation": response})
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
        allowed_use_cases=frozenset({GOAL_PROPOSAL_USE_CASE}),
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
        allowed_use_cases=frozenset({GOAL_PROPOSAL_USE_CASE}),
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
async def test_generate_goal_proposal_end_to_end_with_fake_provider() -> None:
    evidence = (
        atom(
            atom_id="mother-report-1",
            epistemic_kind=WorldStateEpistemicKind.OTHER_REPORT,
            value_ref="孩子最近回避谈论学校",
            asserted_by="mother-1",
        ),
    )
    runtime, authorization = _fake_runtime(
        {
            "statement": "帮助孩子在未来两周内更愿意谈论学校话题",
            "desired_change": "孩子主动分享学校经历的频率提升",
            "success_criteria": ["孩子每周至少一次主动谈及学校话题"],
            "expected_observation": "家长记录到孩子主动谈及学校的次数增加",
            "measurement_window": "14 days",
            "failure_criteria": ["两周后孩子仍完全回避学校话题"],
            "stop_criteria": ["孩子明确表示不愿被追问此话题"],
            "escalation_criteria": ["孩子表现出自伤或危机信号"],
            "evidence_atom_ids": ["mother-report-1"],
        }
    )

    proposal = await generate_goal_proposal(
        runtime,
        agent_id=_AGENT_ID,
        authorization=authorization,
        request_id="request-e2e-1",
        evidence_atoms=evidence,
        primary_contradiction_statement="孩子想要独立但家长想要掌控",
        scope=scope(),
        subject_ids=("child-1",),
        context_snapshot_ref="snapshot-1",
        goal_proposal_id="goal-e2e-1",
        family_need_ref=None,
        reasoning_ref="primary-contradiction-e2e-1",
        now=NOW,
    )

    assert proposal.goal_proposal_id == "goal-e2e-1"
    assert proposal.evidence_refs == ("mother-report-1",)
    assert proposal.success_criteria
    assert proposal.escalation_criteria


@pytest.mark.asyncio
async def test_generate_goal_proposal_rejects_hallucinated_evidence_end_to_end() -> None:
    evidence = (atom(atom_id="only-real-evidence"),)
    output = dict(_VALID_OUTPUT)
    output["evidence_atom_ids"] = ["only-real-evidence", "fabricated-atom-id"]
    runtime, authorization = _fake_runtime(output)

    with pytest.raises(ContextContractError, match="GOAL_PROPOSAL_CITES_UNKNOWN_EVIDENCE"):
        await generate_goal_proposal(
            runtime,
            agent_id=_AGENT_ID,
            authorization=authorization,
            request_id="request-e2e-2",
            evidence_atoms=evidence,
            primary_contradiction_statement="孩子想要独立但家长想要掌控",
            scope=scope(),
            subject_ids=("child-1",),
            context_snapshot_ref="snapshot-1",
            goal_proposal_id="goal-e2e-2",
            family_need_ref=None,
            reasoning_ref="primary-contradiction-e2e-2",
            now=NOW,
        )
