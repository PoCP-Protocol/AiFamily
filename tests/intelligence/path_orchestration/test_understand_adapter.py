import json

import pytest

from backend.intelligence.model_gateway.errors import ModelGatewayError
from backend.intelligence.model_gateway.gateway import build_gateway
from backend.intelligence.model_gateway.provider_registry import (
    DEFAULT_PROVIDER_RECORDS,
    ProviderRegistry,
)
from backend.intelligence.model_gateway.providers.fake import FakeProvider, deterministic_provider
from backend.intelligence.path_orchestration.contracts import (
    FamilyPathContext,
    PathDraftError,
    PathDraftEvidence,
)
from backend.intelligence.path_orchestration.understand_adapter import (
    UNDERSTAND_USE_CASE,
    GatewayBackedUnderstandAdapter,
    de_identify,
)


def evidence(ref: str) -> PathDraftEvidence:
    return PathDraftEvidence(ref, "family_need", "v1", "guardian-confirmed context")


def context(*, family_id="family-a", tags=(), unknowns=()) -> FamilyPathContext:
    return FamilyPathContext(
        tenant_id="tenant-1",
        family_id=family_id,
        need_id=f"need-{family_id}",
        need_statement="家庭希望获得更适合当前情境的支持——包含具体姓名与住址等身份信息",
        subject_ids=(f"child-{family_id}",),
        context_snapshot_ref=f"snapshot-{family_id}",
        evidence=(evidence(f"need-evidence-{family_id}"),),
        fit_tags=frozenset(tags),
        unknowns=tuple(unknowns),
        feedback_refs=(f"feedback-{family_id}",),
    )


def _test_gateway(provider: FakeProvider):
    return build_gateway(
        environment="test",
        providers={provider.provider_id: provider},
        registry=ProviderRegistry(DEFAULT_PROVIDER_RECORDS),
    )


@pytest.mark.asyncio
async def test_de_identify_drops_every_family_identifying_field():
    ctx = context(family_id="family-secret", tags={"reading"}, unknowns=("最喜欢哪本书？",))
    probe = de_identify(ctx)

    payload_text = json.dumps(probe.to_payload(), ensure_ascii=False)
    assert "family-secret" not in payload_text
    assert "tenant-1" not in payload_text
    assert "身份信息" not in payload_text
    assert "住址" not in payload_text
    assert probe.fit_tags == frozenset({"reading"})
    assert probe.unknowns == ("最喜欢哪本书？",)


@pytest.mark.asyncio
async def test_understand_actually_invokes_the_gateway_and_never_leaks_identity():
    provider = deterministic_provider(
        lambda req: {
            "perspective": f"tags:{sorted(req.payload['fit_tags'])}",
            "guiding_question": "?",
        }
    )
    gateway = _test_gateway(provider)
    adapter = GatewayBackedUnderstandAdapter(gateway, provider_id=provider.provider_id)

    ctx = context(family_id="family-a", tags={"reading", "bedtime_routine"})
    probe = de_identify(ctx)
    draft = await adapter.understand(probe=probe, context_snapshot_ref=ctx.context_snapshot_ref)

    assert len(provider.invocations) == 1
    sent = provider.invocations[0]
    assert sent.use_case == UNDERSTAND_USE_CASE
    assert sent.data_class == "OPERATIONAL_TEXT"
    sent_text = json.dumps(sent.payload, ensure_ascii=False)
    assert "family-a" not in sent_text
    assert "tenant-1" not in sent_text
    assert "身份信息" not in sent_text
    assert draft.provenance.provider_id == provider.provider_id
    assert draft.output["perspective"] == "tags:['bedtime_routine', 'reading']"


@pytest.mark.asyncio
async def test_two_different_family_contexts_produce_two_different_model_inputs():
    provider = deterministic_provider(lambda req: {"perspective": "x", "guiding_question": "?"})
    gateway = _test_gateway(provider)
    adapter = GatewayBackedUnderstandAdapter(gateway, provider_id=provider.provider_id)

    ctx_a = context(family_id="family-a", tags={"reading"})
    ctx_b = context(family_id="family-b", tags={"screen_time"})

    await adapter.understand(
        probe=de_identify(ctx_a), context_snapshot_ref=ctx_a.context_snapshot_ref
    )
    await adapter.understand(
        probe=de_identify(ctx_b), context_snapshot_ref=ctx_b.context_snapshot_ref
    )

    assert len(provider.invocations) == 2
    assert provider.invocations[0].payload != provider.invocations[1].payload
    assert provider.invocations[0].payload["fit_tags"] == ["reading"]
    assert provider.invocations[1].payload["fit_tags"] == ["screen_time"]


def test_unregistered_provider_is_rejected_at_gateway_construction_not_at_call_time():
    # Even stricter than call-time fail-closed: `ModelGateway.__init__` refuses
    # to wire a provider that has no 第16条 compliance posture in the registry
    # at all, so the governance gap surfaces at startup, never at a family's
    # first request.
    provider = FakeProvider(provider_id="not-a-registered-provider")
    with pytest.raises(ModelGatewayError):
        _test_gateway(provider)
    assert provider.invocations == []


@pytest.mark.asyncio
async def test_provider_not_approved_for_this_environment_is_fail_closed():
    # "openai-compatible-unassessed" is registered but only approved for
    # ("internal_livecheck",) — building the gateway with environment="test"
    # must reject the call before invoke() ever runs.
    provider = FakeProvider(provider_id="openai-compatible-unassessed")
    gateway = _test_gateway(provider)
    adapter = GatewayBackedUnderstandAdapter(gateway, provider_id=provider.provider_id)

    ctx = context(family_id="family-a", tags={"reading"})
    with pytest.raises(ModelGatewayError):
        await adapter.understand(
            probe=de_identify(ctx), context_snapshot_ref=ctx.context_snapshot_ref
        )
    assert provider.invocations == []


def test_regulated_data_class_is_rejected_at_construction_not_at_call_time():
    provider = FakeProvider()
    gateway = _test_gateway(provider)
    with pytest.raises(PathDraftError):
        GatewayBackedUnderstandAdapter(
            gateway, provider_id=provider.provider_id, data_class="MINOR_PERSONAL_DATA"
        )


@pytest.mark.asyncio
async def test_real_ibm_ica_livecheck_produces_a_schema_valid_perspective():
    """Only runs when real credentials are present (opt-in, not a CI gate).

    Proves the UNDERSTAND adapter works against the real registered provider,
    not just FakeProvider — real network latency, real schema validation of a
    real model's free-form output. Skipped everywhere credentials are absent
    (CI, most local machines) rather than failing, since this is evidence for
    a human operator to gather on demand, not a correctness gate this module
    depends on.
    """
    ibm_ica_wiring = pytest.importorskip(
        "backend.intelligence.model_gateway.ibm_ica_wiring",
        reason="ibm_ica_wiring not present on this ref yet",
    )
    IBM_ICA_LIVECHECK_ENVIRONMENT = ibm_ica_wiring.IBM_ICA_LIVECHECK_ENVIRONMENT
    IBM_ICA_PROVIDER_ID = ibm_ica_wiring.IBM_ICA_PROVIDER_ID
    build_livecheck_ibm_ica_gateway = ibm_ica_wiring.build_livecheck_ibm_ica_gateway
    ibm_ica_credentials_available = ibm_ica_wiring.ibm_ica_credentials_available

    if not ibm_ica_credentials_available():
        pytest.skip("AIFAMILY_MODEL_API_KEY/AIFAMILY_MODEL_BASE_URL not set")

    gateway = build_livecheck_ibm_ica_gateway()
    assert gateway.environment == IBM_ICA_LIVECHECK_ENVIRONMENT
    adapter = GatewayBackedUnderstandAdapter(gateway, provider_id=IBM_ICA_PROVIDER_ID)

    ctx_a = context(family_id="family-a", tags={"reading", "bedtime_routine"})
    ctx_b = context(family_id="family-b", tags={"screen_time"})

    draft_a = await adapter.understand(
        probe=de_identify(ctx_a), context_snapshot_ref=ctx_a.context_snapshot_ref
    )
    draft_b = await adapter.understand(
        probe=de_identify(ctx_b), context_snapshot_ref=ctx_b.context_snapshot_ref
    )

    for draft in (draft_a, draft_b):
        assert draft.provenance.provider_id == IBM_ICA_PROVIDER_ID
        assert draft.provenance.latency_ms > 0
        assert isinstance(draft.output["perspective"], str) and draft.output["perspective"].strip()
        assert (
            isinstance(draft.output["guiding_question"], str)
            and draft.output["guiding_question"].strip()
        )
