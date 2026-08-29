"""Tests for `application/zone_queries.py` — the Portfolio Zone View.

Pure application-layer slice, same convention as
`test_zone_review_governance.py`: an in-memory Fake, no SQLAlchemy/DB
fixtures. The Fake here implements this Agent's own
`application/zone_query_ports.py::ZonePortfolioQueryPort` (a plain
`list[ProductZoneAssessment]` in memory) rather than touching Agent C's
`infrastructure/zone_fake_repository.py::FakeZoneAssessmentRepository`
(which has no list-all method, and is not this Agent's file to extend).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from ..application.context import ActorContext
from ..application.zone_queries import (
    RE_REVIEW_WINDOW,
    PortfolioZoneRow,
    PortfolioZoneSummary,
    get_portfolio_zone_summary,
    get_portfolio_zone_view,
)
from ..domain.zone_entities import DimensionAssessment, ProductZoneAssessment

UTC_NOW = datetime(2026, 8, 29, 12, 0, 0, tzinfo=timezone.utc)

ALL_DIMENSIONS = (
    "customer_scarcity",
    "replaceability",
    "data_advantage",
    "network_effect",
    "learning_effect",
    "switching_cost",
)


class FakePortfolioQueryPort:
    """In-memory `ZonePortfolioQueryPort` double, test-local only. Simple
    adapter over a flat list, filtering by `tenant_scope` — deliberately
    does not wrap/extend Agent C's `FakeZoneAssessmentRepository` (see
    module docstring)."""

    def __init__(self, assessments: list[ProductZoneAssessment] | None = None) -> None:
        self._assessments = list(assessments or [])

    async def list_zone_assessments(self, tenant_scope: str) -> list[ProductZoneAssessment]:
        return [a for a in self._assessments if a.tenant_scope == tenant_scope]


def _dimension_assessments(*, evidence: bool = True) -> list[DimensionAssessment]:
    return [
        DimensionAssessment(
            dimension=dimension,
            score=60.0,
            rationale="test rationale",
            evidence_refs=[f"evidence-{dimension}"] if evidence else [],
            evidence_strength=0.6,
            assessed_by="human-scorer-1",
            assessed_at=UTC_NOW,
        )
        for dimension in ALL_DIMENSIONS
    ]


def _build_assessment(
    *,
    id: str,
    tenant_scope: str = "tenant-a",
    status: str = "SCORED",
    recommended_zone: str = "ADVANTAGE",
    approved_zone: str | None = None,
    reviewed_at: datetime | None = None,
    override_reason: str | None = None,
    dimension_assessments: list[DimensionAssessment] | None = None,
) -> ProductZoneAssessment:
    kwargs = dict(
        id=id,
        version=1,
        created_at=UTC_NOW,
        updated_at=UTC_NOW,
        created_by="human-scorer-1",
        tenant_scope=tenant_scope,
        status=status,
        subject_ref=f"product-concept-{id}",
        zone_policy_version_id="zone-policy-v0",
        dimension_assessments=dimension_assessments if dimension_assessments is not None else _dimension_assessments(),
        differentiation_index=55.0,
        defensibility_index=55.0,
        commodity_score=30.0,
        advantage_score=60.0,
        unique_score=40.0,
        recommended_zone=recommended_zone,
        approved_zone=approved_zone,
        reviewed_by="human-reviewer-1" if approved_zone is not None else None,
        reviewed_at=reviewed_at,
        review_reason="looks good" if approved_zone is not None else None,
    )
    if approved_zone is not None and approved_zone != recommended_zone:
        kwargs["override_reason"] = override_reason or "reviewer judgment override"
    return ProductZoneAssessment(**kwargs)


@pytest.fixture
def context_a() -> ActorContext:
    return ActorContext(actor_id="human-1", actor_type="HUMAN", tenant_scope="tenant-a")


@pytest.fixture
def context_b() -> ActorContext:
    return ActorContext(actor_id="human-2", actor_type="HUMAN", tenant_scope="tenant-b")


# --- Summary counting: approved_zone only, not recommended_zone ------------


@pytest.mark.asyncio
async def test_summary_counts_only_approved_zone_not_recommended(context_a):
    assessments = [
        _build_assessment(id="a1", status="APPROVED", recommended_zone="COMMODITY", approved_zone="COMMODITY", reviewed_at=UTC_NOW),
        _build_assessment(id="a2", status="APPROVED", recommended_zone="ADVANTAGE", approved_zone="ADVANTAGE", reviewed_at=UTC_NOW),
        _build_assessment(id="a3", status="APPROVED", recommended_zone="UNIQUE", approved_zone="UNIQUE", reviewed_at=UTC_NOW),
        # SCORED but never approved: has a recommended_zone of UNIQUE, must
        # NOT be counted in unique_count — only in unreviewed_count.
        _build_assessment(id="a4", status="SCORED", recommended_zone="UNIQUE", approved_zone=None),
        # UNDER_REVIEW: also unreviewed.
        _build_assessment(id="a5", status="UNDER_REVIEW", recommended_zone="ADVANTAGE", approved_zone=None),
    ]
    port = FakePortfolioQueryPort(assessments)

    summary = await get_portfolio_zone_summary(port, context_a, now=UTC_NOW)

    assert summary.commodity_count == 1
    assert summary.advantage_count == 1
    assert summary.unique_count == 1
    assert summary.unreviewed_count == 2
    assert summary.total_count == 5


@pytest.mark.asyncio
async def test_summary_rejected_assessment_counts_in_its_own_bucket_not_unreviewed(context_a):
    # Chief-architect closure ruling (supersedes the prior "folded into
    # unreviewed_count" behavior): REJECTED never sets approved_zone
    # (rejection is not an approval), but it is reviewed-and-turned-down, not
    # pending review — it gets its own `rejected_count` bucket and must NOT
    # inflate `unreviewed_count`.
    assessments = [
        _build_assessment(id="r1", status="REJECTED", recommended_zone="UNIQUE", approved_zone=None),
    ]
    port = FakePortfolioQueryPort(assessments)

    summary = await get_portfolio_zone_summary(port, context_a, now=UTC_NOW)

    assert summary.rejected_count == 1
    assert summary.unreviewed_count == 0
    assert summary.unique_count == 0
    assert summary.total_count == 1


@pytest.mark.asyncio
async def test_summary_retired_assessment_counts_in_its_own_bucket_not_approved_zone(context_a):
    # RETIRED was APPROVED (only legal predecessor per
    # ZONE_ASSESSMENT_STATUS_TRANSITIONS) and still carries a non-None
    # approved_zone, but the closure ruling excludes it from the three
    # "current active distribution" zone buckets -- it must land only in
    # retired_count.
    assessments = [
        _build_assessment(id="t1", status="RETIRED", recommended_zone="UNIQUE", approved_zone="UNIQUE", reviewed_at=UTC_NOW),
    ]
    port = FakePortfolioQueryPort(assessments)

    summary = await get_portfolio_zone_summary(port, context_a, now=UTC_NOW)

    assert summary.retired_count == 1
    assert summary.unique_count == 0
    assert summary.unreviewed_count == 0
    assert summary.rejected_count == 0
    assert summary.total_count == 1


@pytest.mark.asyncio
async def test_summary_six_buckets_partition_exhaustively_with_no_overlap(context_a):
    # One assessment per legal ZoneAssessmentStatus value -- verifies the
    # six-bucket case-split covers all six states exactly once each (the
    # invariant get_portfolio_zone_summary itself asserts).
    assessments = [
        _build_assessment(id="s-draft", status="DRAFT", recommended_zone="ADVANTAGE", approved_zone=None),
        _build_assessment(id="s-scored", status="SCORED", recommended_zone="ADVANTAGE", approved_zone=None),
        _build_assessment(id="s-under-review", status="UNDER_REVIEW", recommended_zone="ADVANTAGE", approved_zone=None),
        _build_assessment(id="s-approved", status="APPROVED", recommended_zone="COMMODITY", approved_zone="COMMODITY", reviewed_at=UTC_NOW),
        _build_assessment(id="s-rejected", status="REJECTED", recommended_zone="ADVANTAGE", approved_zone=None),
        _build_assessment(id="s-retired", status="RETIRED", recommended_zone="UNIQUE", approved_zone="UNIQUE", reviewed_at=UTC_NOW),
    ]
    port = FakePortfolioQueryPort(assessments)

    summary = await get_portfolio_zone_summary(port, context_a, now=UTC_NOW)

    assert summary.unreviewed_count == 3
    assert summary.commodity_count == 1
    assert summary.advantage_count == 0
    assert summary.unique_count == 0
    assert summary.rejected_count == 1
    assert summary.retired_count == 1
    assert summary.total_count == 6
    assert (
        summary.commodity_count + summary.advantage_count + summary.unique_count
        + summary.unreviewed_count + summary.rejected_count + summary.retired_count
        == summary.total_count
    )


# --- 6-month (180-day) re-review boundary -----------------------------------


@pytest.mark.asyncio
async def test_approved_assessment_181_days_ago_is_pending_re_review(context_a):
    reviewed_at = UTC_NOW - timedelta(days=181)
    assessment = _build_assessment(
        id="stale-1", status="APPROVED", recommended_zone="ADVANTAGE",
        approved_zone="ADVANTAGE", reviewed_at=reviewed_at,
    )
    port = FakePortfolioQueryPort([assessment])

    rows = await get_portfolio_zone_view(port, context_a, now=UTC_NOW)

    assert len(rows) == 1
    assert rows[0].is_pending_re_review is True

    summary = await get_portfolio_zone_summary(port, context_a, now=UTC_NOW)
    assert summary.pending_re_review_count == 1
    # Still counted in its approved zone bucket -- staleness does not evict
    # it from the distribution, per ADR-Governance §4 ("does not silently
    # auto-invalidate").
    assert summary.advantage_count == 1


@pytest.mark.asyncio
async def test_approved_assessment_179_days_ago_is_not_pending_re_review(context_a):
    reviewed_at = UTC_NOW - timedelta(days=179)
    assessment = _build_assessment(
        id="fresh-1", status="APPROVED", recommended_zone="ADVANTAGE",
        approved_zone="ADVANTAGE", reviewed_at=reviewed_at,
    )
    port = FakePortfolioQueryPort([assessment])

    rows = await get_portfolio_zone_view(port, context_a, now=UTC_NOW)

    assert rows[0].is_pending_re_review is False

    summary = await get_portfolio_zone_summary(port, context_a, now=UTC_NOW)
    assert summary.pending_re_review_count == 0


@pytest.mark.asyncio
async def test_re_review_window_is_exactly_180_days():
    assert RE_REVIEW_WINDOW == timedelta(days=180)


@pytest.mark.asyncio
async def test_unapproved_assessment_is_never_pending_re_review(context_a):
    # SCORED, no approved_zone, no reviewed_at at all -- must not raise and
    # must not be flagged, regardless of how old created_at/updated_at are.
    assessment = _build_assessment(id="never-reviewed", status="SCORED", recommended_zone="UNIQUE", approved_zone=None)
    port = FakePortfolioQueryPort([assessment])

    rows = await get_portfolio_zone_view(port, context_a, now=UTC_NOW + timedelta(days=1000))

    assert rows[0].is_pending_re_review is False


# --- Empty portfolio ---------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_tenant_portfolio_returns_empty_view_and_zeroed_summary(context_a):
    port = FakePortfolioQueryPort([])

    rows = await get_portfolio_zone_view(port, context_a, now=UTC_NOW)
    summary = await get_portfolio_zone_summary(port, context_a, now=UTC_NOW)

    assert rows == []
    assert summary == PortfolioZoneSummary(
        commodity_count=0, advantage_count=0, unique_count=0,
        unreviewed_count=0, rejected_count=0, retired_count=0,
        pending_re_review_count=0, total_count=0,
    )


# --- Cross-tenant isolation ---------------------------------------------------


@pytest.mark.asyncio
async def test_tenant_a_assessments_never_appear_in_tenant_b_view(context_a, context_b):
    assessments = [
        _build_assessment(id="a1", tenant_scope="tenant-a", status="APPROVED", recommended_zone="UNIQUE", approved_zone="UNIQUE", reviewed_at=UTC_NOW),
        _build_assessment(id="b1", tenant_scope="tenant-b", status="APPROVED", recommended_zone="COMMODITY", approved_zone="COMMODITY", reviewed_at=UTC_NOW),
    ]
    port = FakePortfolioQueryPort(assessments)

    rows_a = await get_portfolio_zone_view(port, context_a, now=UTC_NOW)
    rows_b = await get_portfolio_zone_view(port, context_b, now=UTC_NOW)

    assert [r.assessment_id for r in rows_a] == ["a1"]
    assert [r.assessment_id for r in rows_b] == ["b1"]

    summary_a = await get_portfolio_zone_summary(port, context_a, now=UTC_NOW)
    summary_b = await get_portfolio_zone_summary(port, context_b, now=UTC_NOW)

    assert summary_a.unique_count == 1 and summary_a.commodity_count == 0
    assert summary_b.commodity_count == 1 and summary_b.unique_count == 0


# --- Row shape / evidence coverage -------------------------------------------


@pytest.mark.asyncio
async def test_row_evidence_coverage_full_when_all_six_dimensions_have_evidence(context_a):
    assessment = _build_assessment(id="cov-1", status="SCORED", recommended_zone="ADVANTAGE", approved_zone=None)
    port = FakePortfolioQueryPort([assessment])

    rows = await get_portfolio_zone_view(port, context_a, now=UTC_NOW)

    assert rows[0].evidence_coverage == 1.0
    assert set(rows[0].dimension_scores.keys()) == set(ALL_DIMENSIONS)
    assert isinstance(rows[0], PortfolioZoneRow)


@pytest.mark.asyncio
async def test_row_evidence_coverage_partial_when_some_dimensions_missing_evidence(context_a):
    # Build dimension_assessments with one dimension missing evidence_refs.
    # DimensionAssessment's own schema-level gate forbids constructing THAT
    # one dimension with an empty list directly -- so this test instead
    # mutates the model post-construction via `model_construct` bypass isn't
    # needed: we simulate the "not every real-world caller goes through the
    # evidence-gated command path" scenario documented in
    # PortfolioZoneRow.evidence_coverage's docstring by using
    # `model_copy(update=...)` with `model_config` validation skipped through
    # direct field replacement, which pydantic allows for `model_copy`.
    dims = _dimension_assessments()
    # Replace the first entry with one whose evidence_refs is empty by
    # constructing via `model_construct` (bypasses validators, matching the
    # documented "not every row is guaranteed to have come through the
    # evidence-gated command path" defensive rationale).
    dims[0] = DimensionAssessment.model_construct(
        dimension=dims[0].dimension, score=dims[0].score, rationale=dims[0].rationale,
        evidence_refs=[], evidence_strength=dims[0].evidence_strength,
        assessed_by=dims[0].assessed_by, assessed_at=dims[0].assessed_at,
    )
    assessment = _build_assessment(
        id="cov-partial", status="DRAFT", recommended_zone="ADVANTAGE",
        approved_zone=None, dimension_assessments=dims,
    )
    port = FakePortfolioQueryPort([assessment])

    rows = await get_portfolio_zone_view(port, context_a, now=UTC_NOW)

    assert rows[0].evidence_coverage == pytest.approx(5 / 6)


@pytest.mark.asyncio
async def test_row_carries_override_reason_scenario_approved_zone_differs_from_recommended(context_a):
    assessment = _build_assessment(
        id="override-1", status="APPROVED", recommended_zone="ADVANTAGE",
        approved_zone="UNIQUE", reviewed_at=UTC_NOW,
    )
    port = FakePortfolioQueryPort([assessment])

    rows = await get_portfolio_zone_view(port, context_a, now=UTC_NOW)

    assert rows[0].recommended_zone == "ADVANTAGE"
    assert rows[0].approved_zone == "UNIQUE"
