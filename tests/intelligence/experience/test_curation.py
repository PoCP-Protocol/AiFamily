from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.intelligence.experience.contracts import (
    DeletionRef,
    ExperienceContractError,
    ExperienceProvenance,
    ExperienceScope,
    ProvenanceKind,
)
from backend.intelligence.experience.curation import (
    ExperienceCandidate,
    RecommendationCurator,
)
from backend.intelligence.experience.gateway import ExperienceGateway
from backend.platform.idempotency.keys import IdempotencyKey


def _scope(
    *,
    tenant_id: str = "tenant-a",
    region_id: str = "CN",
    family_id: str = "family-a",
    subjects: tuple[str, ...] = ("child-a",),
) -> ExperienceScope:
    return ExperienceScope(
        global_id=f"global-{tenant_id}-{family_id}",
        tenant_id=tenant_id,
        region_id=region_id,
        family_id=family_id,
        subject_ids=subjects,
        purpose="growth_support",
        consent_version="consent.v1",
        consent_granted=True,
        data_class="MINOR_PERSONAL_DATA",  # type: ignore[arg-type]
        locale="zh-CN",
        content_locale="zh-CN",
        model_locale="zh-CN",
        policy_locale="zh-CN",
        deletion_ref=DeletionRef("delete-curation", "experience.v1"),
        correlation_id="corr-curation",
        causation_id="cause-curation",
    )


def _provenance() -> ExperienceProvenance:
    return ExperienceProvenance(
        provenance_ref="provenance-curation",
        source_refs=("catalog:synthetic",),
        kind=ProvenanceKind.SYNTHETIC_TEST,
        policy_version="experience-policy.v1",
    )


def _candidate(
    candidate_id: str,
    *,
    scope: ExperienceScope | None = None,
    priority: int = 0,
    eligible: bool = True,
    is_commercial: bool = False,
    cooldown_until: datetime | None = None,
) -> ExperienceCandidate:
    return ExperienceCandidate(
        candidate_id=candidate_id,
        source_ref=f"content:{candidate_id}",
        scope=scope or _scope(),
        content_locale="zh-CN",
        delivery_priority=priority,
        eligible=eligible,
        is_commercial=is_commercial,
        cooldown_until=cooldown_until,
    )


def test_curator_recall_filters_and_orders_without_family_ranking() -> None:
    gateway = ExperienceGateway()
    curator = RecommendationCurator(gateway)
    result = curator.curate(
        request_id="request-001",
        scope=_scope(),
        candidates=(
            _candidate("content-low", priority=1),
            _candidate("content-high", priority=9),
            _candidate(
                "content-paused",
                priority=100,
                cooldown_until=datetime.now(UTC) + timedelta(days=1),
            ),
            _candidate("content-ineligible", eligible=False),
            _candidate("content-commercial", is_commercial=True),
        ),
        strategy_version="curator.v1",
        idempotency_key=IdempotencyKey("tenant-a", "request-001"),
        provenance=_provenance(),
    )

    assert result.recalled_count == 5
    assert result.admitted_count == 2
    assert result.filtered_count == 3
    assert result.decision.candidate_ids == ("content-high", "content-low")
    assert result.decision.selected_ids == ("content-high", "content-low")
    assert "minor_commercial_blocked" in result.decision.reason_codes
    assert result.decision.may_mutate_business_state is False


def test_curator_deduplicates_identical_recall_and_rejects_candidate_collision() -> None:
    curator = RecommendationCurator(ExperienceGateway())
    base = _candidate("content-001", priority=2)
    result = curator.curate(
        request_id="request-dedup",
        scope=_scope(),
        candidates=(base, base),
        strategy_version="curator.v1",
        idempotency_key=IdempotencyKey("tenant-a", "request-dedup"),
        provenance=_provenance(),
    )
    assert result.recalled_count == 1

    with pytest.raises(ExperienceContractError, match="CANDIDATE_ID_COLLISION"):
        curator.curate(
            request_id="request-collision",
            scope=_scope(),
            candidates=(base, _candidate("content-001", priority=3)),
            strategy_version="curator.v1",
            idempotency_key=IdempotencyKey("tenant-a", "request-collision"),
            provenance=_provenance(),
        )


def test_curator_rejects_cross_scope_and_empty_admission() -> None:
    curator = RecommendationCurator(ExperienceGateway())
    with pytest.raises(ExperienceContractError, match="NO_ELIGIBLE_CANDIDATE"):
        curator.curate(
            request_id="request-cross",
            scope=_scope(),
            candidates=(_candidate("content-other", scope=_scope(region_id="EU")),),
            strategy_version="curator.v1",
            idempotency_key=IdempotencyKey("tenant-a", "request-cross"),
            provenance=_provenance(),
        )


def test_curator_is_idempotent_through_gateway() -> None:
    gateway = ExperienceGateway()
    curator = RecommendationCurator(gateway)
    kwargs = {
        "request_id": "request-replay",
        "scope": _scope(),
        "candidates": (_candidate("content-001"),),
        "strategy_version": "curator.v1",
        "idempotency_key": IdempotencyKey("tenant-a", "request-replay"),
        "provenance": _provenance(),
    }
    first = curator.curate(**kwargs)
    replay = curator.curate(**kwargs)
    assert replay.decision is first.decision
    assert len(gateway.timeline(_scope()).decisions) == 1
