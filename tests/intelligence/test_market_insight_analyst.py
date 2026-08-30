import pytest

from backend.intelligence.market_insight.analyst import (
    build_market_insight_request,
    run_market_insight_draft,
)
from backend.intelligence.model_gateway.contracts import ModelDraft
from backend.intelligence.model_gateway.gateway import ModelGateway
from backend.intelligence.model_gateway.provider_registry import ProviderRecord, ProviderRegistry
from backend.intelligence.model_gateway.providers.fake import FakeProvider


def _gateway(response: dict) -> tuple[ModelGateway, FakeProvider]:
    provider = FakeProvider({"market.insight.generate": response})
    record = ProviderRecord(
        provider_id=provider.provider_id,
        vendor="aifamily-internal",
        model="fake-deterministic",
        model_version="1.0.0",
        status="INTERNAL_APPROVED",
        approved_environments=("test",),
        sub_delegates=False,
        security_assessment_ref="N/A",
        processing_agreement_ref="N/A",
        deletion_on_termination_committed=True,
    )
    return (
        ModelGateway(
            {provider.provider_id: provider},
            environment="test",
            registry=ProviderRegistry([record]),
        ),
        provider,
    )


VALID_OUTPUT = {
    "statement": "家长在学习辅导责任转移上存在持续摩擦",
    "opportunity_signal": "可能需要分阶段责任转移服务",
    "assumptions": ["反馈来自重复出现的家庭场景"],
    "evidence_refs": ["signal:1", "feedback:1"],
}


@pytest.mark.asyncio
async def test_analyst_can_complete_market_insight_analysis_loop() -> None:
    gateway, provider = _gateway(VALID_OUTPUT)
    draft = await run_market_insight_draft(
        gateway,
        provider_id=provider.provider_id,
        signal_id="signal-1",
        signal_text="多名家长反馈作业辅导冲突反复出现",
        evidence_refs=("signal:1", "feedback:1"),
        context_snapshot_ref="ops-context:1",
    )

    assert isinstance(draft, ModelDraft)
    assert draft.status == "DRAFT"
    assert draft.may_mutate_business_state is False
    assert draft.output["evidence_refs"] == ["signal:1", "feedback:1"]
    assert len(provider.invocations) == 1


@pytest.mark.asyncio
async def test_model_cannot_invent_an_evidence_reference() -> None:
    bad = {**VALID_OUTPUT, "evidence_refs": ["signal:1", "made-up:999"]}
    gateway, provider = _gateway(bad)
    with pytest.raises(ValueError, match="REFERENCE_NOT_ALLOWED"):
        await run_market_insight_draft(
            gateway,
            provider_id=provider.provider_id,
            signal_id="signal-1",
            signal_text="市场信号",
            evidence_refs=("signal:1",),
            context_snapshot_ref="ops-context:1",
        )


def test_request_requires_non_empty_unique_evidence() -> None:
    with pytest.raises(ValueError, match="EVIDENCE_REQUIRED"):
        build_market_insight_request(
            signal_id="signal-1",
            signal_text="市场信号",
            evidence_refs=(),
            context_snapshot_ref="ops-context:1",
        )
    with pytest.raises(ValueError, match="EVIDENCE_DUPLICATE"):
        build_market_insight_request(
            signal_id="signal-1",
            signal_text="市场信号",
            evidence_refs=("signal:1", "signal:1"),
            context_snapshot_ref="ops-context:1",
        )
