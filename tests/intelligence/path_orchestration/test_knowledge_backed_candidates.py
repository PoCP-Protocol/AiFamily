import pytest

from backend.intelligence.knowledge.contracts import KnowledgeClaim, KnowledgeSource
from backend.intelligence.knowledge.registry import KnowledgeRegistry
from backend.intelligence.model_gateway.gateway import build_gateway
from backend.intelligence.model_gateway.provider_registry import (
    DEFAULT_PROVIDER_RECORDS,
    ProviderRegistry,
)
from backend.intelligence.model_gateway.providers.fake import deterministic_provider
from backend.intelligence.path_orchestration.candidate_explanation_adapter import (
    GatewayBackedCandidateExplanationAdapter,
)
from backend.intelligence.path_orchestration.contracts import FamilyPathContext, PathDraftEvidence
from backend.intelligence.path_orchestration.knowledge_backed_candidates import (
    KnowledgeBackedCapabilityCandidatePort,
)
from backend.packages.contracts.evidence import Provenance

# NOTE: this test file constructs its own PUBLISHED+verified claims to
# exercise the pipeline's logic end-to-end. This is a test fixture, not
# production seed content — a real deployment must never present
# `verified=True` knowledge that hasn't actually gone through knowledge
# governance review.


def evidence(ref: str) -> PathDraftEvidence:
    return PathDraftEvidence(ref, "family_need", "v1", "guardian-confirmed context")


def context(*, family_id="family-a", tags=(), unknowns=()) -> FamilyPathContext:
    return FamilyPathContext(
        tenant_id="tenant-1",
        family_id=family_id,
        need_id=f"need-{family_id}",
        need_statement="家庭希望获得更适合当前情境的支持",
        subject_ids=(f"child-{family_id}",),
        context_snapshot_ref=f"snapshot-{family_id}",
        evidence=(evidence(f"need-evidence-{family_id}"),),
        fit_tags=frozenset(tags),
        unknowns=tuple(unknowns),
        feedback_refs=(f"feedback-{family_id}",),
    )


def _verified_registry(claims: tuple[tuple[str, str, str], ...]) -> KnowledgeRegistry:
    """claims: tuple of (claim_id, scope, text). Registers one shared verified source."""

    registry = KnowledgeRegistry(
        sources=(
            KnowledgeSource(
                source_id="test-verified-source",
                title="Test fixture source",
                license_ref="test-fixture-license",
                owner="test-suite",
                scope="*",
                verified=True,
                status="ACTIVE",
            ),
        )
    )
    for claim_id, scope, text in claims:
        claim = KnowledgeClaim(
            claim_id=claim_id,
            text=text,
            source_id="test-verified-source",
            provenance=Provenance(level="E3", source_ref="test-verified-source"),
            scope=scope,
            status="PUBLISHED",
            allowed_purposes=("path_orchestration_candidate_generation",),
        )
        registry.register_claim(claim)
    return registry


def _explanation_adapter(build_fn):
    provider = deterministic_provider(build_fn)
    gateway = build_gateway(
        environment="test",
        providers={provider.provider_id: provider},
        registry=ProviderRegistry(DEFAULT_PROVIDER_RECORDS),
    )
    return GatewayBackedCandidateExplanationAdapter(
        gateway, provider_id=provider.provider_id
    ), provider


def _echo_explanation(req):
    return {
        "title": f"标题:{req.payload['claim_text'][:8]}",
        "description": req.payload["claim_text"],
    }


@pytest.mark.asyncio
async def test_candidate_count_tracks_registry_content_not_a_fixed_pool():
    registry_empty = _verified_registry(())
    registry_two = _verified_registry(
        (
            ("claim-reading", "reading", "把固定的共读时间放进情绪平稳的一段。"),
            ("claim-general", "general", "先整理已观察到的现象再讨论。"),
        )
    )
    adapter, provider = _explanation_adapter(_echo_explanation)

    port_empty = KnowledgeBackedCapabilityCandidatePort(registry_empty, adapter)
    port_two = KnowledgeBackedCapabilityCandidatePort(registry_two, adapter)

    ctx = context(tags={"reading"})
    empty_result = await port_empty.list_candidates(scope=None, context=ctx)
    two_result = await port_two.list_candidates(scope=None, context=ctx)

    assert empty_result == ()
    assert len(two_result) == 2
    assert len(provider.invocations) == 2


@pytest.mark.asyncio
async def test_explanation_adapter_is_genuinely_invoked_once_per_claim():
    registry = _verified_registry((("claim-a", "general", "先整理已观察到的现象再讨论。"),))
    adapter, provider = _explanation_adapter(_echo_explanation)
    port = KnowledgeBackedCapabilityCandidatePort(registry, adapter)

    result = await port.list_candidates(scope=None, context=context(tags={"reading"}))

    assert len(result) == 1
    assert len(provider.invocations) == 1
    sent = provider.invocations[0]
    assert sent.payload["claim_text"] == "先整理已观察到的现象再讨论。"
    assert sent.data_class == "OPERATIONAL_TEXT"


@pytest.mark.asyncio
async def test_candidate_content_traces_back_to_the_retrieved_claim_not_invented_text():
    claim_text = "先记录一周内屏幕使用的具体场景，再和孩子一起商量哪些场景可以替换。"
    registry = _verified_registry((("claim-screen", "screen_time", claim_text),))
    adapter, _ = _explanation_adapter(_echo_explanation)
    port = KnowledgeBackedCapabilityCandidatePort(registry, adapter)

    result = await port.list_candidates(scope=None, context=context(tags={"screen_time"}))

    assert len(result) == 1
    candidate = result[0]
    assert candidate.capability_ref == "knowledge:claim-screen"
    assert candidate.description == claim_text
    assert candidate.evidence[0].ref == "claim-screen"
    assert candidate.evidence[0].excerpt == claim_text


@pytest.mark.asyncio
async def test_unverified_source_claims_are_never_retrieved_even_if_published():
    # Registering a claim under an unverified source and confirming it never
    # surfaces is the guardrail this whole design depends on: candidate
    # content can only ever come from claims a real knowledge-governance
    # process has verified, never from a source that merely calls itself
    # PUBLISHED.
    registry = KnowledgeRegistry(
        sources=(
            KnowledgeSource(
                source_id="unverified-source",
                title="Not actually reviewed",
                license_ref="n/a",
                owner="test-suite",
                scope="*",
                verified=False,
                status="ACTIVE",
            ),
        )
    )
    registry.register_claim(
        KnowledgeClaim(
            claim_id="claim-unverified",
            text="这条声明没有经过验证。",
            source_id="unverified-source",
            provenance=Provenance(level="unverified", source_ref="unverified-source"),
            scope="general",
            status="PUBLISHED",
        )
    )
    adapter, provider = _explanation_adapter(_echo_explanation)
    port = KnowledgeBackedCapabilityCandidatePort(registry, adapter)

    result = await port.list_candidates(scope=None, context=context(tags={"reading"}))

    assert result == ()
    assert provider.invocations == []


@pytest.mark.asyncio
async def test_different_family_contexts_retrieve_different_candidate_sets():
    registry = _verified_registry(
        (
            ("claim-reading", "reading", "亲子共读的建议。"),
            ("claim-screen", "screen_time", "屏幕使用的建议。"),
        )
    )
    adapter, _ = _explanation_adapter(_echo_explanation)
    port = KnowledgeBackedCapabilityCandidatePort(registry, adapter)

    reading_family = await port.list_candidates(scope=None, context=context(tags={"reading"}))
    screen_family = await port.list_candidates(scope=None, context=context(tags={"screen_time"}))

    assert {c.capability_ref for c in reading_family} == {"knowledge:claim-reading"}
    assert {c.capability_ref for c in screen_family} == {"knowledge:claim-screen"}
