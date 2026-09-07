from __future__ import annotations

import pytest

from backend.intelligence.knowledge.contracts import KnowledgeClaim, KnowledgeSource
from backend.intelligence.knowledge.registry import KnowledgeRegistry
from backend.intelligence.knowledge.runtime import (
    KnowledgeContext,
    KnowledgeDraftRequest,
    KnowledgeDraftRuntime,
    KnowledgeRuntimeError,
)
from backend.intelligence.model_gateway.contracts import (
    KnowledgeExecutionPayload,
    PromptExecutionPlan,
)
from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.providers.fake import FakeProvider
from backend.packages.contracts.evidence import Provenance
from tests.intelligence.model_gateway.test_fail_closed import build


def _plan() -> PromptExecutionPlan:
    return PromptExecutionPlan(
        prompt_ref="family-understanding",
        prompt_version="prompt.v1",
        template="Produce a bounded understanding draft.",
        system_policy_ref="family-safety.v1",
        safety_policy_version="family-safety.v1",
        knowledge_refs=("claim:family-1",),
        asset_digest="a" * 64,
        system_policy="Return a DRAFT only; never write facts.",
        system_policy_digest="b" * 64,
        knowledge_materials=(
            KnowledgeExecutionPayload(
                knowledge_ref="claim:family-1",
                content="A bounded family-support claim.",
                source_ref="source:family-1",
                license_ref="license:test",
                evidence_level="E6",
                content_digest="d" * 64,
            ),
        ),
        material_digest="c" * 64,
    )


def _claim(*, status: str = "REVIEWED", expires_at=None) -> KnowledgeClaim:
    return KnowledgeClaim(
        claim_id="claim:family-1",
        text="A bounded family-support claim.",
        source_id="source:family-1",
        provenance=Provenance(level="E6", source_ref="source:family-1"),
        scope="family_growth",
        status=status,  # type: ignore[arg-type]
        allowed_purposes=("family_understanding",),
        expires_at=expires_at,
    )


def _runtime(provider: FakeProvider) -> KnowledgeDraftRuntime:
    source = KnowledgeSource(
        source_id="source:family-1",
        title="Reviewed family support source",
        license_ref="license:test",
        owner="research",
        scope="family_growth",
        verified=True,
    )
    registry = KnowledgeRegistry(sources=(source,))
    registry.register_claim(_claim(status="REVIEWED"))
    registry.transition_claim("claim:family-1", "PUBLISHED")
    return KnowledgeDraftRuntime(registry, build(provider))


def _request(**changes: object) -> KnowledgeDraftRequest:
    context = KnowledgeContext(
        tenant_id="tenant-a",
        family_id="family-a",
        purpose="family_understanding",
        scope="family_growth",
        context_snapshot_ref="ctx:family-a:1",
        data_class="SYNTHETIC",
        correlation_id="corr:family-a:1",
    )
    values: dict[str, object] = {
        "context": context,
        "provider_id": "fake-deterministic",
        "prompt_version": "prompt.v1",
        "schema_version": "understanding.v1",
        "payload": {"confirmed_need": "家庭沟通节奏"},
        "output_schema": {
            "type": "object",
            "required": ["summary"],
            "properties": {"summary": {"type": "string"}},
        },
        "prompt_execution_plan": _plan(),
    }
    values.update(changes)
    return KnowledgeDraftRequest(**values)  # type: ignore[arg-type]


@pytest.mark.asyncio
async def test_published_knowledge_is_bound_to_one_gateway_draft() -> None:
    provider = FakeProvider({"family_understanding": {"summary": "基于证据的理解草案"}})
    draft = await _runtime(provider).generate_draft(_request())

    assert draft.status == "DRAFT"
    assert draft.may_mutate_business_state is False
    assert draft.provenance.provider_id == "fake-deterministic"
    assert draft.provenance.context_snapshot_ref == "ctx:family-a:1"
    assert provider.invocations[0].payload["knowledge_claim_refs"] == ("claim:family-1",)


@pytest.mark.asyncio
async def test_missing_or_expired_knowledge_fails_before_provider_call() -> None:
    provider = FakeProvider({"family_understanding": {"summary": "不会调用"}})
    runtime = _runtime(provider)
    # Replace with an empty registry to prove knowledge admission is fail-closed.
    runtime = KnowledgeDraftRuntime(KnowledgeRegistry(), build(provider))

    with pytest.raises(KnowledgeRuntimeError, match="KNOWLEDGE_NOT_AVAILABLE"):
        await runtime.generate_draft(_request())
    assert provider.invocations == []


@pytest.mark.asyncio
async def test_provider_failure_remains_fail_closed() -> None:
    provider = FakeProvider(fail_with="PROVIDER_5XX")

    with pytest.raises(ModelGatewayError, match="PROVIDER_5XX"):
        await _runtime(provider).generate_draft(_request())
