from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime

import pytest

from backend.intelligence.knowledge.persistence import (
    KnowledgeClaimStatusProjection,
    KnowledgeLifecycleEvent,
    KnowledgeSelectionReceipt,
    PersistedKnowledgeClaimVersion,
    content_digest,
    selection_item,
)
from backend.packages.contracts.evidence import Provenance


def _claim(text: str = "活动转换可能影响任务开始。") -> PersistedKnowledgeClaimVersion:
    return PersistedKnowledgeClaimVersion(
        claim_id="knowledge:transition",
        version="1.0.0",
        content_digest=content_digest(text),
        text=text,
        source_id="source:reviewed",
        provenance=Provenance(level="E6", source_ref="source:reviewed"),
        scope="family_growth",
        allowed_purposes=("family_problem_understanding",),
        applicability="家庭学习任务开始阶段",
        limitations=("不能凭一次表达判断孩子能力",),
    )


def _projection(status="PUBLISHED", *, replacement_ref=None):
    return KnowledgeClaimStatusProjection(
        claim_id="knowledge:transition",
        version="1.0.0",
        status=status,
        latest_event_id="event:published",
        replacement_ref=replacement_ref,
        withdrawn=status == "RETIRED",
    )


def test_claim_version_is_content_addressed_and_immutable() -> None:
    claim = _claim()
    assert len(claim.content_digest) == 64
    with pytest.raises(FrozenInstanceError):
        claim.text = "被修改的正文"  # type: ignore[misc]
    with pytest.raises(ValueError, match="does not match"):
        replace(claim, text="不同正文")


def test_digest_is_not_globally_unique_across_claim_ids() -> None:
    first = _claim()
    second = replace(first, claim_id="knowledge:another")
    assert first.content_digest == second.content_digest
    assert first.ref != second.ref


def test_selection_receipt_contains_refs_not_claim_text() -> None:
    item = selection_item(_claim(), _projection())
    receipt = KnowledgeSelectionReceipt(
        selection_id="selection:1",
        request_ref="request:1",
        purpose="family_problem_understanding",
        scope="family_growth",
        selected_at=datetime(2026, 9, 3, tzinfo=UTC),
        items=(item,),
    )
    assert item.claim_id == "knowledge:transition"
    assert not hasattr(item, "text")
    assert "活动转换" not in repr(receipt)


@pytest.mark.parametrize("status", ["REVIEWED", "RETIRED"])
def test_unpublished_or_withdrawn_claim_cannot_enter_new_selection(status) -> None:
    with pytest.raises(ValueError, match="cannot enter"):
        selection_item(_claim(), _projection(status))


def test_retired_projection_can_point_to_replacement_without_reactivating_text() -> None:
    retired = _projection("RETIRED", replacement_ref="knowledge:transition@2.0.0")
    assert retired.withdrawn is True
    assert retired.replacement_ref == "knowledge:transition@2.0.0"
    with pytest.raises(ValueError, match="cannot enter"):
        selection_item(_claim(), retired)


def test_lifecycle_event_requires_timezone_and_opaque_reason_ref() -> None:
    event = KnowledgeLifecycleEvent(
        event_id="event:retired",
        claim_id="knowledge:transition",
        version="1.0.0",
        status="RETIRED",
        occurred_at=datetime(2026, 9, 3, tzinfo=UTC),
        actor_ref="actor:knowledge-owner",
        reason_ref="reason:license-withdrawn",
    )
    assert event.status == "RETIRED"
    with pytest.raises(ValueError, match="timezone"):
        replace(event, occurred_at=datetime(2026, 9, 3))


def test_selection_receipt_rejects_duplicate_claim_versions() -> None:
    item = selection_item(_claim(), _projection())
    with pytest.raises(ValueError, match="repeat"):
        KnowledgeSelectionReceipt(
            selection_id="selection:duplicate",
            request_ref="request:1",
            purpose="family_problem_understanding",
            scope="family_growth",
            selected_at=datetime(2026, 9, 3, tzinfo=UTC),
            items=(item, item),
        )
