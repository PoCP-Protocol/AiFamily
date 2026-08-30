from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.product_management.product_factory_inputs import (
    CompetitorEvidenceCard,
    DemandFrame,
    DraftStatus,
    EvidenceStatus,
    MarketInsightDraft,
    ProductFactoryInputError,
)


def _expiry() -> datetime:
    return datetime.now(UTC) + timedelta(days=7)


def _common() -> dict[str, object]:
    return {
        "evidence_refs": ("evidence:one",),
        "assumptions": ("需要通过访谈验证",),
        "unknowns": ("区域差异尚未确认",),
        "next_validation": "访谈五个目标家庭",
        "expires_at": _expiry(),
    }


def _demand(**overrides: object) -> DemandFrame:
    values = {
        **_common(),
        "demand_id": "demand:one",
        "statement": "家长需要更可执行的家庭沟通支持",
        "scenario": "家庭沟通",
        "source_refs": ("source:interview:one",),
        "target_segment": "小学阶段家长",
    }
    values.update(overrides)
    return DemandFrame(**values)


def _insight(**overrides: object) -> MarketInsightDraft:
    values = {
        **_common(),
        "insight_id": "insight:one",
        "demand_ref": "demand:one",
        "statement": "可暂停的小行动可能降低执行阻力",
        "source_refs": ("source:research:one",),
    }
    values.update(overrides)
    return MarketInsightDraft(**values)


def _competitor(**overrides: object) -> CompetitorEvidenceCard:
    values = {
        **_common(),
        "evidence_id": "competitor-evidence:one",
        "competitor_ref": "competitor:example",
        "claim": "公开资料显示其提供家庭任务提醒",
        "source_refs": ("source:competitor:one",),
        "demand_ref": "demand:one",
    }
    values.update(overrides)
    return CompetitorEvidenceCard(**values)


def test_inputs_are_immutable_draft_only_and_cannot_mutate_business_state() -> None:
    demand = _demand()
    insight = _insight()
    card = _competitor()

    assert demand.status is DraftStatus.DRAFT
    assert insight.status is DraftStatus.DRAFT
    assert card.status is DraftStatus.DRAFT
    assert demand.requires_human_confirmation is True
    assert insight.requires_human_confirmation is True
    assert card.may_mutate_business_state is False
    assert not hasattr(demand, "save")
    with pytest.raises(FrozenInstanceError):
        demand.statement = "changed"  # type: ignore[misc]


def test_expiry_alias_is_normalised_and_must_be_timezone_aware_and_future() -> None:
    expiry = _expiry()
    demand = _demand(expires_at=None, expiry=expiry)
    assert demand.expires_at == demand.expiry == expiry

    with pytest.raises(ProductFactoryInputError, match="TIMEZONE_AWARE"):
        _demand(expires_at=datetime.now())
    with pytest.raises(ProductFactoryInputError, match="IN_THE_FUTURE"):
        _demand(expires_at=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(ProductFactoryInputError, match="ALIASES_MUST_MATCH"):
        _demand(expires_at=expiry, expiry=expiry + timedelta(days=1))


def test_non_empty_source_and_evidence_refs_are_required() -> None:
    with pytest.raises(ProductFactoryInputError, match="SOURCE_REQUIRED"):
        _demand(source_refs=())
    with pytest.raises(ProductFactoryInputError, match="EVIDENCE_REQUIRED"):
        _insight(evidence_refs=())
    with pytest.raises(ProductFactoryInputError, match="MUST_BE_UNIQUE"):
        _competitor(source_refs=("source:one", "source:one"))


def test_assumptions_unknowns_and_next_validation_are_explicit() -> None:
    with pytest.raises(ProductFactoryInputError, match="ASSUMPTION_INVALID"):
        _demand(assumptions=("",))
    with pytest.raises(ProductFactoryInputError, match="UNKNOWN_INVALID"):
        _insight(unknowns=(" ",))
    with pytest.raises(ProductFactoryInputError, match="NEXT_VALIDATION_REQUIRED"):
        _competitor(next_validation="")


def test_competitor_evidence_supports_unknown_stale_and_contradicted_states() -> None:
    for state in (
        EvidenceStatus.UNKNOWN,
        EvidenceStatus.STALE,
        EvidenceStatus.CONTRADICTED,
        EvidenceStatus.VERIFIED,
    ):
        card = _competitor(evidence_status=state)
        assert card.evidence_status is state

    with pytest.raises(ProductFactoryInputError, match="EVIDENCE_STATUS_UNSUPPORTED"):
        _competitor(evidence_status="RANKED")


def test_all_artifacts_reject_non_draft_status() -> None:
    for factory in (_demand, _insight, _competitor):
        with pytest.raises(ProductFactoryInputError, match="MUST_REMAIN_DRAFT"):
            factory(status="REVIEWED")


def test_competitor_card_requires_demand_or_market_parent_reference() -> None:
    with pytest.raises(ProductFactoryInputError, match="PARENT_REF_REQUIRED"):
        _competitor(demand_ref=None)


def test_replace_cannot_promote_ai_input_to_published_status() -> None:
    demand = _demand()
    with pytest.raises(ProductFactoryInputError, match="MUST_REMAIN_DRAFT"):
        replace(demand, status="REVIEWED")
