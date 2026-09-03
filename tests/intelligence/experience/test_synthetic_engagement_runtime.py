from __future__ import annotations

import pytest

from backend.intelligence.experience.synthetic_engagement_runtime import (
    SyntheticEngagementRuntimeResolver,
)


@pytest.mark.asyncio
async def test_synthetic_engagement_runtime_keeps_full_draft_contract() -> None:
    runtime = await SyntheticEngagementRuntimeResolver(
        tenant_id="tenant-test",
        subject_ids=("guardian-test", "child-test"),
    ).resolve("family-test")

    draft = await runtime.generate_draft(
        request_id="engagement-synthetic-1",
        event_ids=("event-test-1", "event-test-2"),
        payload={"tone": "encouraging"},
    )

    assert draft.draft.status == "DRAFT"
    assert draft.scope is not None
    assert draft.scope.data_class == "SYNTHETIC"
    assert draft.evidence_event_ids == ("event-test-1", "event-test-2")
    assert draft.achievement_candidates[0]["evidence_refs"] == [
        "event-test-1",
        "event-test-2",
    ]


def test_synthetic_engagement_runtime_rejects_production_environment() -> None:
    with pytest.raises(ValueError, match="dev/test"):
        SyntheticEngagementRuntimeResolver(
            tenant_id="tenant-test",
            subject_ids=("guardian-test",),
            environment="production",
        )
