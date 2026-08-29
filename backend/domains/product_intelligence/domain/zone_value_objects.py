"""Value objects/status enums for the Product Zone (Three-Zone Strategy Engine)
sub-domain of `product_intelligence`.

Frozen contract source: `architecture/ADR_PRODUCT_ZONE_SCORING_V0.md` (dimension
semantics/formula/classification) and `architecture/ADR_PRODUCT_ZONE_GOVERNANCE_V0.md`
(lifecycle/evidence-gating/review). Do not change any value here without a new ADR —
per both ADRs' preamble, this is a frozen contract for PR-002 Wave 0, not something a
code-review comment may revise.

This module has no FastAPI/SQLAlchemy dependency, same four-layer rule as
`value_objects.py` / `entities.py` in this domain.
"""
from __future__ import annotations

from typing import Literal

# --- ADR-Scoring §1.2 — the six frozen dimension names, direction documented
# there (customer_scarcity/data_advantage/network_effect/learning_effect/
# switching_cost are positive-direction; replaceability is the sole
# negative-direction dimension — see `zone_scoring_engine.inverse_replaceability`).
ZoneDimensionName = Literal[
    "customer_scarcity",
    "replaceability",
    "data_advantage",
    "network_effect",
    "learning_effect",
    "switching_cost",
]

ZONE_DIMENSION_NAMES: frozenset[str] = frozenset(
    {
        "customer_scarcity",
        "replaceability",
        "data_advantage",
        "network_effect",
        "learning_effect",
        "switching_cost",
    }
)
"""Set form of `ZoneDimensionName`, for membership/coverage checks (e.g.
`ProductZoneAssessment` validating that `dimension_assessments` covers exactly
these six names, no more, no fewer, no duplicates)."""

# --- ADR-Scoring §2.1 — the four "floor gate" dimensions the UNIQUE
# classification rule checks individually (in addition to the Defensibility
# Index average). Kept as a named constant here so `zone_scoring_engine.py`
# does not re-derive/hardcode this subset.
DEFENSIBILITY_FLOOR_GATE_DIMENSIONS: tuple[ZoneDimensionName, ...] = (
    "data_advantage",
    "network_effect",
    "learning_effect",
    "switching_cost",
)

# --- ADR-Governance §5 — the persisted lifecycle state machine.
#
# NOTE on `PENDING_RE_REVIEW`: ADR-Governance §4 ("Re-review cadence") says an
# expired-but-still-APPROVED assessment is marked `PENDING_RE_REVIEW` by the
# "schema/query layer", not that a persisted `status` column ever stores that
# literal value via a normal lifecycle transition. Reading §4 and §5 together:
# §5's frozen state machine (DRAFT -> SCORED -> UNDER_REVIEW -> APPROVED ->
# RETIRED, with UNDER_REVIEW -> REJECTED) has no arrow into or out of
# `PENDING_RE_REVIEW` at all — it is not one of the boxes in the diagram.
#
# V0 decision (Agent A, domain layer): treat `PENDING_RE_REVIEW` as a
# **derived, query-time flag**, not a fifth-plus legal value of the persisted
# `status` field / not a node in `ZONE_ASSESSMENT_STATUS_TRANSITIONS` below.
# The persisted `status` on an expired approval stays `APPROVED` (that is
# still true — the approval was never revoked); staleness is a computed
# property (e.g. `approved_at`/`reviewed_at` + the ADR's 6-month window,
# compared against "now" at query time — Agent D/Portfolio-query scope per
# ADR-Governance §4's own parenthetical, not this module's job to compute).
# `ZoneAssessmentStatus` therefore only carries the six real persisted states;
# `PENDING_RE_REVIEW` is exposed as a separate literal
# (`ZoneAssessmentQueryFlag`) so calling code has a documented name to import
# without it being mistaken for a seventh transition target.
ZoneAssessmentStatus = Literal[
    "DRAFT",
    "SCORED",
    "UNDER_REVIEW",
    "APPROVED",
    "REJECTED",
    "RETIRED",
]

ZoneAssessmentQueryFlag = Literal["PENDING_RE_REVIEW"]
"""Not a `status` value. A query-time-only annotation a repository/read-model
may attach alongside `status == "APPROVED"` when the ADR-Governance §4 6-month
re-review window has elapsed. Kept here (rather than invented ad hoc by a
future Agent D) so there is one canonical name and one canonical docstring
explaining why it is not in `ZoneAssessmentStatus`."""

RecommendedZone = Literal["COMMODITY", "ADVANTAGE", "UNIQUE"]
"""ADR-Scoring §2.1 classification-rule output. Deterministic, computed by
`zone_scoring_engine.classify_zone` at scoring time — never hand-set."""

ApprovedZone = Literal["COMMODITY", "ADVANTAGE", "UNIQUE"]
"""ADR-Governance §2: a distinct field from `RecommendedZone` — the outcome of
Human Review, may differ from the recommended zone (in which case
`ProductZoneAssessment.override_reason` becomes required — see
`zone_entities.py`). Same three literal values, kept as a separate type alias
(rather than reusing `RecommendedZone`) so a reader of `zone_entities.py`
sees at the type level that these are two independently-settable fields, per
ADR-Governance §2's explicit "never one field silently overwritten by the
other" rule.
"""

AssessmentOrigin = Literal["HUMAN", "RULE", "AI_PROPOSAL"]
"""ADR-Governance §6. `live_model_call_authorized = false` for PR-002 — a
mocked `AI_PROPOSAL` origin may appear in contract tests/fixtures, but no
command or route in this PR calls a real model provider (Agent F/
AUTHORIZATION_REGISTRY scope, not enforced by this data field itself)."""

ZONE_ASSESSMENT_STATUS_TRANSITIONS: dict[str, frozenset[str]] = {
    "DRAFT": frozenset({"SCORED"}),
    "SCORED": frozenset({"UNDER_REVIEW"}),
    "UNDER_REVIEW": frozenset({"APPROVED", "REJECTED"}),
    "APPROVED": frozenset({"RETIRED"}),
    "REJECTED": frozenset(),
    "RETIRED": frozenset(),
}
"""ADR-Governance §5 frozen state machine, as an explicit adjacency map:
`ZONE_ASSESSMENT_STATUS_TRANSITIONS[from_status]` is the set of legal
`to_status` values. `DRAFT -> APPROVED` directly is illegal by construction
(not reachable via any single hop, and no code in this PR chains hops
implicitly). `REJECTED`/`RETIRED` are terminal — empty successor sets."""


def is_legal_zone_status_transition(from_status: str, to_status: str) -> bool:
    """Pure predicate over `ZONE_ASSESSMENT_STATUS_TRANSITIONS`. Domain-layer
    helper only — this module does not decide *who* (which `actor_type`/
    permission) may cause a transition; that is ADR-Governance §4's
    `product_intelligence.zone.review` permission check, owned by the
    application layer (Agent B), not this domain module.
    """
    return to_status in ZONE_ASSESSMENT_STATUS_TRANSITIONS.get(from_status, frozenset())
