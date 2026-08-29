"""Portfolio Zone View — read-model over `ProductZoneAssessment` for a
tenant's whole product portfolio. `architecture/ADR_PRODUCT_ZONE_GOVERNANCE_V0.md`
§4 ("Re-review cadence") assigns the `PENDING_RE_REVIEW` derived flag to
"Agent D/Portfolio-query scope" explicitly — that flag is computed here, not
persisted (see `domain/zone_value_objects.py` `ZoneAssessmentQueryFlag`
docstring for why it is a query-time annotation, not a status value).

Chief-architect directive (relayed in this Agent's task brief, restated here
so a future reader does not have to dig it out of a chat log): "portfolio
query uses `approved_zone`, not unreviewed recommendation" — the three
zone-distribution counts in `PortfolioZoneSummary` are keyed off
`approved_zone` exclusively (equivalently, `status == "APPROVED"` — see
`zone_entities.py`: only the `APPROVED` transition ever sets `approved_zone`,
and every other status leaves it `None`). An assessment that has been
`SCORED` (has a `recommended_zone`) but never reached `APPROVED` contributes
to `unreviewed_count` only; its `recommended_zone` is visible on the
per-row `PortfolioZoneRow` for a reviewer's benefit, but is never folded
into `commodity_count`/`advantage_count`/`unique_count`. Counting an
unapproved recommendation as if it were a governed classification would let
an AI-proposed or not-yet-human-reviewed score silently drive portfolio-level
reporting — exactly the kind of ungoverned number this ADR pair's Human
Review gate (§4) exists to prevent.

Chief-architect closure ruling (PR-002R, supersedes the "open question" this
module previously flagged about `REJECTED`): the six persisted
`ZoneAssessmentStatus` values (`DRAFT`, `SCORED`, `UNDER_REVIEW`, `APPROVED`,
`REJECTED`, `RETIRED` — see `zone_value_objects.py`) are partitioned into
exactly six mutually-exclusive, jointly-exhaustive summary buckets, not four:

- `unreviewed_count` — `status in (DRAFT, SCORED, UNDER_REVIEW)` only.
  `REJECTED` is no longer folded in here (previous version of this module
  did fold it in, matching the "no approved_zone -> unreviewed" rule
  literally, but that conflated "not yet reviewed" with "reviewed and
  turned down", which reads as an inflated pending-review queue to a
  portfolio-level reader).
- `rejected_count` — `status == REJECTED`, its own bucket now.
- `retired_count` — `status == RETIRED`, its own bucket now. A `RETIRED`
  assessment was `APPROVED` at some point (per
  `ZONE_ASSESSMENT_STATUS_TRANSITIONS`, the only edge into `RETIRED` is from
  `APPROVED`) and still carries a non-`None` `approved_zone`, but per this
  ruling it is deliberately excluded from `commodity_count`/
  `advantage_count`/`unique_count` — those three are "current active
  portfolio distribution" buckets, and a retired assessment is closed
  history, not a live classification a reviewer should read as part of
  today's commercial mix. It is still surfaced (as its own count) so that
  history is not silently discarded from the summary entirely.
- `commodity_count`/`advantage_count`/`unique_count` — `status == APPROVED`
  (equivalently `approved_zone is not None`, since only `APPROVED` sets it),
  split by `approved_zone`. Unchanged from the prior ruling above.

Invariant (checked by an `assert` in `get_portfolio_zone_summary` itself, not
just by a test, since it is a correctness property of the code's own
partition logic, not merely an expected test outcome):
`commodity_count + advantage_count + unique_count + unreviewed_count +
rejected_count + retired_count == total_count == len(assessments)`. This
holds because every assessment has exactly one `status` value, and the six
buckets above are an exact case-split over `ZoneAssessmentStatus`'s six
legal values with no value left uncovered and no value counted twice.

No financial/revenue/profit metric is computed anywhere in this module —
per this Agent's task brief and the ADR's V0 scope, this domain has no
reliable commercial-financial data source wired in yet, and inventing one
(even as a mock) would manufacture a fake operating metric. `PortfolioZoneRow`/
`PortfolioZoneSummary` intentionally carry zero revenue/margin-shaped fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from ..domain.zone_entities import ProductZoneAssessment
from ..domain.zone_value_objects import ZONE_DIMENSION_NAMES, ApprovedZone, RecommendedZone, ZoneAssessmentStatus
from .context import ActorContext
from .zone_query_ports import ZonePortfolioQueryPort

# ADR-Governance §4: "an implicit 6-month validity window ... shorter than a
# generic annual cycle". No calendar-month API is used deliberately — 6
# *calendar* months is itself ambiguous (28-31 day months, leap years), and
# the ADR text only ever says "6-month"/"6 months" as an approximation, not
# a day-precise legal deadline. `180 days` is this module's chosen concrete
# approximation of "6 months"; it is NOT a precise calendar-6-months
# calculation (e.g. Feb 28 + 6 calendar months = Aug 28, which is 181 or 182
# days depending on the year) — flagged here plainly per the task brief's
# own instruction to "写清楚这是近似值不是精确日历月".
RE_REVIEW_WINDOW = timedelta(days=180)


@dataclass(frozen=True)
class PortfolioZoneRow:
    """One row of the Portfolio Zone View — one `ProductZoneAssessment`,
    projected to the fields a portfolio-level reviewer needs without having
    to open the full entity. `product_concept_ref` is `subject_ref` renamed
    for readability at this read-model's call sites (V0's only legal
    `subject_type` is `PRODUCT_CONCEPT` — see `zone_entities.py`
    `_subject_type_is_v0_fixed` — so "product concept ref" is an accurate,
    not just convenient, name here)."""

    assessment_id: str
    product_concept_ref: str
    approved_zone: ApprovedZone | None
    recommended_zone: RecommendedZone
    dimension_scores: dict[str, float]
    differentiation_index: float
    defensibility_index: float
    zone_policy_version_id: str
    evidence_coverage: float
    """Fraction (0.0-1.0) of the six frozen dimensions
    (`zone_value_objects.ZONE_DIMENSION_NAMES`) whose `DimensionAssessment`
    has a non-empty `evidence_refs` list. Not a boolean: the ADR-Governance
    §1 hard gate already forces `evidence_refs` non-empty at the
    `DimensionAssessment` schema level (see `zone_entities.py`
    `_evidence_refs_non_empty`), so for any assessment that has actually
    been scored via the real `score_zone_assessment` command this will
    always read `1.0`. It is computed as a fraction rather than hardcoded
    to `1.0`/collapsed to a bool anyway, for two reasons: (1) defense in
    depth — this read-model should not silently assume every row it is ever
    handed came through that one command path (e.g. a future ingestion path,
    or a still-`DRAFT` row with placeholder dimension rows that happen to
    carry a non-empty-but-placeholder ref — see `zone_commands.py`'s own
    documented caveat about the `"pending_initial_assessment"` placeholder
    ref string); (2) a fraction is strictly more informative to a reviewer
    than a bool with no loss of information (`== 1.0` recovers the bool)."""
    review_status: ZoneAssessmentStatus
    is_pending_re_review: bool
    """`True` iff `approved_zone is not None and reviewed_at is not None`
    and `now - reviewed_at > RE_REVIEW_WINDOW` (180 days, see module
    docstring). Mirrors `ZoneAssessmentQueryFlag` ("PENDING_RE_REVIEW") from
    `domain/zone_value_objects.py` as a computed field on this read-model,
    per that module's explicit assignment of the computation to
    "Agent D/Portfolio-query scope"."""


@dataclass(frozen=True)
class PortfolioZoneSummary:
    """Tenant-wide zone distribution. Six counts are mutually exclusive and
    sum exactly to `total_count` (see module docstring "Chief-architect
    closure ruling" for the full six-bucket partition rationale):
    `commodity_count + advantage_count + unique_count + unreviewed_count +
    rejected_count + retired_count == total_count == len(assessments)`.
    `get_portfolio_zone_summary` asserts this invariant itself before
    returning. See module docstring for why the three zone counts are keyed
    off `approved_zone`/`status == APPROVED`, never `recommended_zone`."""

    commodity_count: int = 0
    advantage_count: int = 0
    unique_count: int = 0
    unreviewed_count: int = 0
    """`status in (DRAFT, SCORED, UNDER_REVIEW)` — assessments that have not
    yet completed human review either way. Does NOT include `REJECTED`
    (its own `rejected_count` bucket, per the closure ruling) or `RETIRED`
    (its own `retired_count` bucket)."""
    rejected_count: int = 0
    """`status == REJECTED` — reviewed and turned down. Kept out of
    `unreviewed_count` (closure ruling) so a portfolio reader does not read
    a rejected assessment as "still pending review"."""
    retired_count: int = 0
    """`status == RETIRED` — was `APPROVED` (the only legal predecessor per
    `ZONE_ASSESSMENT_STATUS_TRANSITIONS`), now closed out. Deliberately
    excluded from `commodity_count`/`advantage_count`/`unique_count`: those
    three are the *current* active-portfolio distribution, and a retired
    assessment is historical, not part of today's commercial mix — but it is
    still counted here rather than dropped from the summary silently."""
    pending_re_review_count: int = 0
    """Not part of the six-way partition above (a `PENDING_RE_REVIEW`
    assessment is still `APPROVED` and already counted in one of the three
    zone buckets) — a separate, overlapping count surfaced because
    ADR-Governance §4 explicitly wants staleness "visible... not silently
    treated as still-current" at the portfolio level, not just on the
    single-row view."""
    total_count: int = 0


def _evidence_coverage(assessment: ProductZoneAssessment) -> float:
    covered = sum(1 for d in assessment.dimension_assessments if d.evidence_refs)
    total = len(ZONE_DIMENSION_NAMES)
    return covered / total if total else 0.0


def _is_pending_re_review(assessment: ProductZoneAssessment, *, now: datetime) -> bool:
    if assessment.approved_zone is None or assessment.reviewed_at is None:
        return False
    return (now - assessment.reviewed_at) > RE_REVIEW_WINDOW


def _to_row(assessment: ProductZoneAssessment, *, now: datetime) -> PortfolioZoneRow:
    return PortfolioZoneRow(
        assessment_id=assessment.id,
        product_concept_ref=assessment.subject_ref,
        approved_zone=assessment.approved_zone,
        recommended_zone=assessment.recommended_zone,
        dimension_scores=assessment.dimension_score_map(),
        differentiation_index=assessment.differentiation_index,
        defensibility_index=assessment.defensibility_index,
        zone_policy_version_id=assessment.zone_policy_version_id,
        evidence_coverage=_evidence_coverage(assessment),
        review_status=assessment.status,
        is_pending_re_review=_is_pending_re_review(assessment, now=now),
    )


async def get_portfolio_zone_view(
    port: ZonePortfolioQueryPort, context: ActorContext, *, now: datetime,
) -> list[PortfolioZoneRow]:
    """`now` is caller-supplied (never `datetime.now()` internally) so the
    180-day re-review boundary is deterministically testable — per this
    Agent's task brief instruction to keep this function free of
    non-reproducible wall-clock calls."""
    assessments = await port.list_zone_assessments(context.tenant_scope)
    return [_to_row(a, now=now) for a in assessments]


async def get_portfolio_zone_summary(
    port: ZonePortfolioQueryPort, context: ActorContext, *, now: datetime,
) -> PortfolioZoneSummary:
    assessments = await port.list_zone_assessments(context.tenant_scope)

    commodity_count = 0
    advantage_count = 0
    unique_count = 0
    unreviewed_count = 0
    rejected_count = 0
    retired_count = 0
    pending_re_review_count = 0

    for assessment in assessments:
        if assessment.status in ("DRAFT", "SCORED", "UNDER_REVIEW"):
            unreviewed_count += 1
        elif assessment.status == "REJECTED":
            rejected_count += 1
        elif assessment.status == "RETIRED":
            retired_count += 1
        elif assessment.status == "APPROVED":
            if assessment.approved_zone == "COMMODITY":
                commodity_count += 1
            elif assessment.approved_zone == "ADVANTAGE":
                advantage_count += 1
            elif assessment.approved_zone == "UNIQUE":
                unique_count += 1

        if _is_pending_re_review(assessment, now=now):
            pending_re_review_count += 1

    total_count = len(assessments)
    # Correctness invariant, not merely a test expectation (see module
    # docstring "Chief-architect closure ruling"): the six buckets above are
    # an exact case-split over the six legal `ZoneAssessmentStatus` values,
    # so they must sum to `total_count` with no double-count/no gap. An
    # `APPROVED` assessment whose `approved_zone` is somehow `None` (should
    # be structurally impossible per `zone_entities.py`'s transition logic,
    # but this assert is the fail-closed backstop if that invariant is ever
    # violated upstream) would silently fall through all three zone
    # branches above and break this sum — surface that loudly here rather
    # than returning a summary that quietly does not add up.
    assert (
        commodity_count + advantage_count + unique_count
        + unreviewed_count + rejected_count + retired_count
        == total_count
    ), "portfolio_zone_summary_bucket_invariant_violated"

    return PortfolioZoneSummary(
        commodity_count=commodity_count,
        advantage_count=advantage_count,
        unique_count=unique_count,
        unreviewed_count=unreviewed_count,
        rejected_count=rejected_count,
        retired_count=retired_count,
        pending_re_review_count=pending_re_review_count,
        total_count=total_count,
    )
