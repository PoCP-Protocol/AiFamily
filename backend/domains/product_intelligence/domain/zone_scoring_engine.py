"""Product Zone scoring engine — pure functions, no I/O.

Implements `architecture/ADR_PRODUCT_ZONE_SCORING_V0.md` §2/§2.1. Every
function here is a pure function of its arguments: no randomness, no
`datetime.now()`, no network/DB access. This is a hard requirement (ADR-
Scoring §3 / ADR-Governance §3's "canonical calculation hash" invariant):
same dimension inputs + same `ZonePolicyVersion` must always produce the
same `RecommendedZone` and the same three scores.

All threshold/floor-gate numbers are read from the `ZonePolicyVersion`
passed in (`policy.thresholds`), never hardcoded here — the specific
`PROVISIONAL_POLICY_V0` fixture values (75/40/40/50) belong in the policy
fixture (see `tests/test_zone_scoring.py::_build_policy` and, eventually,
Agent C's persisted default policy row), not in this module, precisely so a
future policy version can change them without a code change (ADR-Governance
§3).
"""
from __future__ import annotations

from .errors import ProductIntelligenceValidationError
from .zone_entities import DimensionAssessment, ZonePolicyVersion
from .zone_value_objects import DEFENSIBILITY_FLOOR_GATE_DIMENSIONS, RecommendedZone

# Canonical threshold keys this engine expects in `ZonePolicyVersion.thresholds`.
# See `ZonePolicyVersion.thresholds` docstring in `zone_entities.py`.
THRESHOLD_UNIQUE_DEFENSIBILITY_MIN = "unique_defensibility_min"
THRESHOLD_UNIQUE_FLOOR_GATE_MIN = "unique_floor_gate_min"
THRESHOLD_COMMODITY_DIFFERENTIATION_MAX = "commodity_differentiation_max"
THRESHOLD_COMMODITY_DEFENSIBILITY_MAX = "commodity_defensibility_max"

# Optional `thresholds` key (see `ZonePolicyVersion.thresholds` docstring):
# the multiplier applied to `defensibility_index` for `unique_score` when the
# assessment did NOT classify as UNIQUE. Not in `_REQUIRED_THRESHOLD_KEYS`
# because it is optional — absent means "use the V0 default" (`_DEFAULT_...`
# below), not a validation failure.
THRESHOLD_NON_GATED_UNIQUE_PENALTY_FACTOR = "non_gated_unique_penalty_factor"
_DEFAULT_NON_GATED_UNIQUE_PENALTY_FACTOR = 0.5

_REQUIRED_THRESHOLD_KEYS = (
    THRESHOLD_UNIQUE_DEFENSIBILITY_MIN,
    THRESHOLD_UNIQUE_FLOOR_GATE_MIN,
    THRESHOLD_COMMODITY_DIFFERENTIATION_MAX,
    THRESHOLD_COMMODITY_DEFENSIBILITY_MAX,
)

# ADR-Scoring §2 / chief-architect closure directive: scoring-algorithm
# versions this module knows how to execute. `score_assessment` fails closed
# (raises `ProductIntelligenceValidationError`) if a policy's
# `scoring_algorithm_version` is not in this set — see `zone_entities.py`'s
# `ZonePolicyVersion.scoring_algorithm_version` docstring for the full
# rationale (a future `ZONE_SCORING_V1` engine must not silently reinterpret
# an old `ZONE_SCORING_V0` policy under a formula it was never validated
# against, or vice versa).
_SUPPORTED_ALGORITHM_VERSIONS = frozenset({"ZONE_SCORING_V0"})


def inverse_replaceability(score: float) -> float:
    """ADR-Scoring §1.2/§2: `replaceability` is the sole negative-direction
    dimension. `inverse_replaceability = 100 - replaceability`, so a
    `replaceability` of 100 (trivially easy to replace) inverts to 0
    (contributes nothing to differentiation), and a `replaceability` of 0
    (impossible to replace) inverts to 100 (maximal contribution).
    """
    return 100.0 - score


def compute_differentiation_index(
    customer_scarcity: float,
    replaceability: float,
    weights: dict[str, float],
) -> float:
    """ADR-Scoring §2 + closure fix (see `ZonePolicyVersion.weights`
    docstring in `zone_entities.py`): `Differentiation Index` is the
    **normalized weighted average** of `customer_scarcity` and
    `inverse_replaceability`, using this group's own two weights:

        (w_cs * customer_scarcity + w_repl * inverse_replaceability(replaceability))
        / (w_cs + w_repl)

    Takes raw `replaceability` (not pre-inverted) so every caller goes
    through the same inversion step — there is exactly one place in this
    codebase that inverts it — and applies `weights["replaceability"]` to
    the *inverted* value, per the direction rule.

    `weights["customer_scarcity"] + weights["replaceability"] == 0` is fail-
    closed (raises `ProductIntelligenceValidationError`) to avoid a
    division by zero; `ZonePolicyVersion`'s validator already guarantees
    every individual weight is `>= 0`, so this can only happen if both of
    this group's weights are exactly `0.0`.
    """
    w_cs = weights["customer_scarcity"]
    w_repl = weights["replaceability"]
    weight_sum = w_cs + w_repl
    if weight_sum == 0.0:
        raise ProductIntelligenceValidationError("zone_policy_differentiation_weights_sum_to_zero")
    return (w_cs * customer_scarcity + w_repl * inverse_replaceability(replaceability)) / weight_sum


def compute_defensibility_index(
    data_advantage: float,
    network_effect: float,
    learning_effect: float,
    switching_cost: float,
    weights: dict[str, float],
) -> float:
    """ADR-Scoring §2 + closure fix: `Defensibility Index` is the
    **normalized weighted average** of the four defensibility dimensions,
    using this group's own four weights:

        (w_da*data_advantage + w_ne*network_effect + w_le*learning_effect + w_sc*switching_cost)
        / (w_da + w_ne + w_le + w_sc)

    `PROVISIONAL_POLICY_V0` sets all four weights to `1.0`, which reduces
    exactly to the original equal-weighted `/4` average — this preserves
    V0's existing business results; only a non-default policy changes the
    output. Weight sum `== 0` is fail-closed (see
    `compute_differentiation_index` for the identical rationale).
    """
    w_da = weights["data_advantage"]
    w_ne = weights["network_effect"]
    w_le = weights["learning_effect"]
    w_sc = weights["switching_cost"]
    weight_sum = w_da + w_ne + w_le + w_sc
    if weight_sum == 0.0:
        raise ProductIntelligenceValidationError("zone_policy_defensibility_weights_sum_to_zero")
    return (
        w_da * data_advantage + w_ne * network_effect + w_le * learning_effect + w_sc * switching_cost
    ) / weight_sum


def _dimension_scores_from_assessments(
    dimension_assessments: list[DimensionAssessment],
) -> dict[str, float]:
    return {d.dimension: d.score for d in dimension_assessments}


def _require_threshold_keys(policy: ZonePolicyVersion) -> None:
    missing = [k for k in _REQUIRED_THRESHOLD_KEYS if k not in policy.thresholds]
    if missing:
        raise ProductIntelligenceValidationError("zone_policy_thresholds_missing_required_keys")


def classify_zone(
    differentiation_index: float,
    defensibility_index: float,
    dimension_scores: dict[str, float],
    policy: ZonePolicyVersion,
) -> RecommendedZone:
    """ADR-Scoring §2.1 classification rule, thresholds read from
    `policy.thresholds` (never hardcoded):

    ```
    UNIQUE      IF  defensibility_index >= thresholds[unique_defensibility_min]
                AND every floor-gate dimension >= thresholds[unique_floor_gate_min]

    COMMODITY   IF  differentiation_index < thresholds[commodity_differentiation_max]
                AND defensibility_index < thresholds[commodity_defensibility_max]

    ADVANTAGE   otherwise
    ```

    UNIQUE is checked first because it is the only branch with a floor gate
    that a naive average-based ADVANTAGE/COMMODITY check could not express;
    checking it first also matches the ADR's framing of UNIQUE as the
    exceptional case a pure weighted-sum would wrongly grant to a product
    that is high on average but collapsed on one pillar (the floor gate only
    matters as a *disqualifier* for UNIQUE, so evaluating it before
    COMMODITY/ADVANTAGE is the only order that gives the floor gate any
    effect).
    """
    _require_threshold_keys(policy)
    thresholds = policy.thresholds

    floor_gate_min = thresholds[THRESHOLD_UNIQUE_FLOOR_GATE_MIN]
    passes_floor_gate = all(
        dimension_scores.get(dim, 0.0) >= floor_gate_min for dim in DEFENSIBILITY_FLOOR_GATE_DIMENSIONS
    )
    if defensibility_index >= thresholds[THRESHOLD_UNIQUE_DEFENSIBILITY_MIN] and passes_floor_gate:
        return "UNIQUE"

    if (
        differentiation_index < thresholds[THRESHOLD_COMMODITY_DIFFERENTIATION_MAX]
        and defensibility_index < thresholds[THRESHOLD_COMMODITY_DEFENSIBILITY_MAX]
    ):
        return "COMMODITY"

    return "ADVANTAGE"


def _clamp01_to_100(value: float) -> float:
    return max(0.0, min(100.0, value))


def compute_three_scores(
    differentiation_index: float,
    defensibility_index: float,
    recommended_zone: RecommendedZone,
    policy: ZonePolicyVersion,
) -> tuple[float, float, float]:
    """Maps the two indices + the classification-rule verdict to the three
    non-mutually-exclusive `(commodity_score, advantage_score, unique_score)`
    fields required by ADR-Governance §2. The ADR intentionally leaves the
    exact formula to this PR ("the research recommendation... three scores
    kept... not mutually exclusive", no formula given) — this is Agent A's
    design, documented here so it is reviewable rather than implicit:

    Design (deterministic, index-driven, zone-gated):

    - `unique_score = defensibility_index` if `recommended_zone == "UNIQUE"`,
      else `defensibility_index * penalty_factor`, where `penalty_factor =
      policy.thresholds.get("non_gated_unique_penalty_factor", 0.5)`.
      Rationale: `unique_score` should track raw defensibility strength
      (that is what "unique" means in this model — see ADR-Scoring §2), but
      a product that is defensible on average yet failed the floor gate (so
      classified ADVANTAGE, not UNIQUE) should not show a `unique_score` as
      high as a product that actually cleared the gate; the penalty factor
      (versioned policy data, default `0.5` — closure fix, see
      `ZonePolicyVersion.thresholds` docstring) is a simple, legible penalty
      for "average looks unique, floor gate says no" rather than a claim
      about the "correct" discount rate.
    - `commodity_score = 100 - differentiation_index` blended with
      `100 - defensibility_index`, i.e.
      `commodity_score = ((100 - differentiation_index) + (100 - defensibility_index)) / 2`.
      Rationale: "commodity" is the ADR's low-differentiation-AND-low-
      defensibility corner (ADR-Scoring §2.1) — this is the natural
      complement of the average of both indices, so a product with both
      indices near 0 scores near 100 on commodity-ness, and a product with
      both indices near 100 scores near 0.
    - `advantage_score = 100 - abs(commodity_score - unique_score)`, clamped
      to `[0, 100]`. Rationale: ADVANTAGE is the ADR's residual/middle zone
      (§2.1 "otherwise") — a product sitting between the commodity and
      unique poles (neither score dominates) is exactly the ADVANTAGE
      profile, so `advantage_score` is designed to peak when
      `commodity_score` and `unique_score` are close to each other and fall
      as either pole pulls away. This keeps all three scores derived purely
      from the two indices (plus the zone-gate for `unique_score`), with no
      free parameters beyond the already-versioned policy thresholds.

    All three inputs are already `[0, 100]`-range indices, and the outputs
    are clamped to `[0, 100]` defensively (float arithmetic should keep them
    in range already, but the clamp makes the contract explicit).
    """
    penalty_factor = policy.thresholds.get(
        THRESHOLD_NON_GATED_UNIQUE_PENALTY_FACTOR, _DEFAULT_NON_GATED_UNIQUE_PENALTY_FACTOR
    )
    unique_score = defensibility_index if recommended_zone == "UNIQUE" else defensibility_index * penalty_factor
    commodity_score = ((100.0 - differentiation_index) + (100.0 - defensibility_index)) / 2.0
    advantage_score = 100.0 - abs(commodity_score - unique_score)

    return (
        _clamp01_to_100(commodity_score),
        _clamp01_to_100(advantage_score),
        _clamp01_to_100(unique_score),
    )


def score_assessment(
    dimension_assessments: list[DimensionAssessment],
    policy: ZonePolicyVersion,
) -> tuple[float, float, float, float, float, RecommendedZone]:
    """Combinator: six `DimensionAssessment`s + a `ZonePolicyVersion` ->
    `(differentiation_index, defensibility_index, commodity_score,
    advantage_score, unique_score, recommended_zone)`.

    Pure and deterministic: no randomness, no wall-clock reads. Does not
    validate that exactly six dimensions / all six names are present — that
    structural invariant is `ProductZoneAssessment`'s job
    (`zone_entities.py`); this function only requires that the dimension
    names it needs (`customer_scarcity`, `replaceability`, and the four
    floor-gate dimensions) are present in the input, and raises a domain
    validation error otherwise so a caller cannot silently score an
    incomplete set.

    Fail-closed algorithm-version gate (chief-architect closure directive):
    before computing anything, checks `policy.scoring_algorithm_version`
    against `_SUPPORTED_ALGORITHM_VERSIONS` — an unrecognized version raises
    `ProductIntelligenceValidationError` rather than silently scoring under
    a formula the policy was never validated against.
    """
    if policy.scoring_algorithm_version not in _SUPPORTED_ALGORITHM_VERSIONS:
        raise ProductIntelligenceValidationError("unsupported_scoring_algorithm_version")

    scores = _dimension_scores_from_assessments(dimension_assessments)
    required = {"customer_scarcity", "replaceability", *DEFENSIBILITY_FLOOR_GATE_DIMENSIONS}
    missing = required - scores.keys()
    if missing:
        raise ProductIntelligenceValidationError("zone_scoring_missing_required_dimensions")

    differentiation_index = compute_differentiation_index(
        customer_scarcity=scores["customer_scarcity"],
        replaceability=scores["replaceability"],
        weights=policy.weights,
    )
    defensibility_index = compute_defensibility_index(
        data_advantage=scores["data_advantage"],
        network_effect=scores["network_effect"],
        learning_effect=scores["learning_effect"],
        switching_cost=scores["switching_cost"],
        weights=policy.weights,
    )
    recommended_zone = classify_zone(
        differentiation_index=differentiation_index,
        defensibility_index=defensibility_index,
        dimension_scores=scores,
        policy=policy,
    )
    commodity_score, advantage_score, unique_score = compute_three_scores(
        differentiation_index=differentiation_index,
        defensibility_index=defensibility_index,
        recommended_zone=recommended_zone,
        policy=policy,
    )
    return (
        differentiation_index,
        defensibility_index,
        commodity_score,
        advantage_score,
        unique_score,
        recommended_zone,
    )
