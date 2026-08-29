"""Product Zone (Three-Zone Strategy Engine) entities.

Frozen contract source: `architecture/ADR_PRODUCT_ZONE_SCORING_V0.md` and
`architecture/ADR_PRODUCT_ZONE_GOVERNANCE_V0.md`. See `zone_value_objects.py`
module docstring for the same caveat: this is a Wave-0-frozen contract, not a
draft.

This module has no FastAPI/SQLAlchemy dependency — same four-layer rule as
`entities.py` in this domain. It intentionally does not replace or subclass
the placeholder `ProductZoneAssessment` in `entities.py` (that class predates
this ADR pair and is out of this Agent's file ownership per the PR-002 task
split — Agent C/infrastructure decides how/whether to retire it when wiring
persistence); this module defines the ADR-accurate version under its own
name so downstream (application/infrastructure) code has one unambiguous
import to move to.

Scoring math (index/score computation, zone classification) intentionally
does NOT live here — see `zone_scoring_engine.py`. Entities only hold data
and validate structural invariants (shape, non-emptiness, required
cross-field consistency); they do not compute derived numbers themselves,
per the task brief ("computed by the scoring engine, not by the constructor").
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator

from .entities import _CommonFields
from .errors import ProductIntelligenceValidationError
from .zone_value_objects import (
    ZONE_DIMENSION_NAMES,
    AssessmentOrigin,
    ApprovedZone,
    RecommendedZone,
    ZoneAssessmentStatus,
    ZoneDimensionName,
)

# ADR-Scoring §2 / chief-architect closure directive: the scoring-algorithm
# version this codebase currently knows how to execute. A `ZonePolicyVersion`
# whose `scoring_algorithm_version` is not in this set must be fail-closed by
# `zone_scoring_engine.score_assessment` — see that module's
# `_SUPPORTED_ALGORITHM_VERSIONS` re-export/check. Kept as a plain string
# (not an enum/Literal) on `ZonePolicyVersion` itself, deliberately, so a
# future PR introducing `ZONE_SCORING_V1` does not require a schema
# migration to widen a `Literal` — only an engine-side allowlist change.
ZONE_SCORING_ALGORITHM_V0 = "ZONE_SCORING_V0"


def _require_non_empty_str(value: str, field_name: str) -> str:
    if not value or not value.strip():
        raise ProductIntelligenceValidationError(f"{field_name}_must_not_be_empty")
    return value


class DimensionAssessment(BaseModel):
    """One scored dimension out of the six frozen in ADR-Scoring §1.2.

    `evidence_refs` non-emptiness is a hard schema-level gate per
    ADR-Governance §1 ("A dimension score with an empty `evidence_refs` list
    is a schema-level validation error, not a soft warning") — enforced here
    via `field_validator`, not deferred to the scoring engine or application
    layer.
    """

    dimension: ZoneDimensionName
    score: float = Field(ge=0.0, le=100.0)
    rationale: str
    evidence_refs: list[str]
    evidence_strength: float = Field(default=0.5, ge=0.0, le=1.0)
    """ADR-Scoring §3 leaves the exact representation to this PR
    ("expected evidence type" table, no schema mandate beyond "at least one
    ref required"). V0 chooses a normalized `[0, 1]` float — 0 = weakest
    plausible evidence, 1 = strongest (e.g. third-party-verified longitudinal
    data) — rather than a free-form string, so a future policy/weights change
    (ADR-Governance §3 `weights`) has a numeric field to key off of without a
    schema migration. Default `0.5` (neutral/unstated) is a placeholder, not
    a claim about typical evidence quality.
    """
    assessed_by: str
    assessed_at: datetime

    @field_validator("rationale")
    @classmethod
    def _rationale_non_empty(cls, value: str) -> str:
        return _require_non_empty_str(value, "rationale")

    @field_validator("assessed_by")
    @classmethod
    def _assessed_by_non_empty(cls, value: str) -> str:
        return _require_non_empty_str(value, "assessed_by")

    @field_validator("evidence_refs")
    @classmethod
    def _evidence_refs_non_empty(cls, value: list[str]) -> list[str]:
        if not value:
            raise ProductIntelligenceValidationError("dimension_assessment_requires_evidence_refs")
        return value

    @field_validator("assessed_at")
    @classmethod
    def _assessed_at_is_timezone_aware(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ProductIntelligenceValidationError("assessed_at_must_be_timezone_aware")
        return value


class ZonePolicyVersion(BaseModel):
    """ADR-Governance §3 — "the mechanism for recompute, don't rewrite
    history". Every field listed there is represented verbatim; `checksum`
    is a deterministic sha256 over the policy-defining fields (excludes
    `policy_id`/`effective_from`/`status`, which are identity/lifecycle
    metadata about the version, not part of what is being hashed — two
    policy versions with identical rules but different `policy_id`/
    `effective_from` would otherwise get different checksums for no
    substantive reason).
    """

    policy_id: str
    version: int = Field(ge=1)
    dimension_definitions: dict[str, str]
    """Direction table from ADR-Scoring §1.2, versioned as data — e.g.
    `{"customer_scarcity": "positive", "replaceability": "negative", ...}`.
    """
    weights: dict[str, float]
    """ADR-Scoring §2: equal-weight in V0 (`PROVISIONAL_POLICY_V0`), but kept
    as policy data (not hardcoded in the scoring engine) so a future policy
    can change weighting without touching historical assessments' stored
    results (ADR-Governance §3).

    Closure fix (chief-architect review): this field previously existed and
    was checksummed, but `zone_scoring_engine.compute_differentiation_index`/
    `compute_defensibility_index` never actually read it — every policy
    version produced identical scores regardless of `weights`. Now the
    engine reads these per-dimension weights and computes a **normalized**
    weighted average within each of the two independent groups:

    - Differentiation group: `{customer_scarcity, replaceability}` (the
      `replaceability` weight applies to `inverse_replaceability`, per
      ADR-Scoring §1.2's direction rule).
    - Defensibility group: `{data_advantage, network_effect,
      learning_effect, switching_cost}`.

    Design decision on normalization (there is no ADR requirement that the
    six raw weights sum to any particular total): each group's weighted
    average divides by the **sum of that group's own weights**
    (`weight_i / sum(weights in group)`), not by a global sum across all six
    keys. This means a policy author does not need to make the six raw
    weights add up to 1.0/100/anything — the formula is scale-invariant
    within each group (doubling every weight in a group leaves that group's
    index unchanged), which is the standard definition of a weighted
    average. It also means the two groups are normalized independently:
    changing the *relative* weights between, say, `customer_scarcity` and
    `replaceability` changes `differentiation_index`, but has no effect on
    `defensibility_index` (and vice versa) — consistent with ADR-Scoring
    §2's two-index structure being a deliberate grouping of collinear
    dimensions, not one global six-way weighted sum.

    V0's default/fixture policy sets every weight to `1.0` (see
    `tests/test_zone_scoring.py::_build_policy`), which — after
    normalization — reduces exactly to the equal-weighted `/2` and `/4`
    averages the ADR specifies. This preserves all existing V0 business
    results; only a *non-default* policy (different relative weights) now
    changes scoring output, which was previously impossible.

    Validated below (`_weights_cover_all_six_dimensions_non_negative`): must
    contain all six `ZONE_DIMENSION_NAMES` keys (fail closed if any is
    missing) and every value must be `>= 0` (a negative weight would invert
    a dimension's contribution to the average, which is not a weighting
    scheme this ADR licenses)."""
    thresholds: dict[str, float]
    """ADR-Scoring §2.1 fixture values, e.g.
    `{"unique_defensibility_min": 75.0, "unique_floor_gate_min": 50.0,
    "commodity_differentiation_max": 40.0, "commodity_defensibility_max": 40.0}`.
    `zone_scoring_engine.classify_zone` reads these keys — see that module's
    docstring for the exact key names it expects.

    Also carries `non_gated_unique_penalty_factor` (default `0.5` if the key
    is absent — see `zone_scoring_engine.compute_three_scores`). Closure fix:
    this multiplier was previously a hardcoded `0.5` literal inside
    `compute_three_scores`, invisible to policy versioning/checksums despite
    materially affecting `unique_score` for every non-UNIQUE assessment. It
    is kept inside this dict (rather than as a new top-level field) so no
    database migration is required (`thresholds` is already a JSON/JSONB
    column in both the SQLAlchemy model and the `0059_product_zone_engine_v0`
    migration) — a new top-level field would need a new NOT NULL column
    with a backfill for every already-persisted policy row. Because it lives
    in `thresholds`, it is automatically covered by `compute_checksum()`
    (which already hashes the whole `thresholds` dict), so changing the
    penalty factor across policy versions changes the checksum, same as any
    other threshold."""
    classification_rules: str
    """The floor-gated classification rule, recorded as data (a human-
    readable rule description/DSL string) alongside the executable
    implementation in `zone_scoring_engine.classify_zone`, per
    ADR-Governance §3 ("the floor-gated rule itself, as data, not hardcoded
    in application code"). V0 does not build a rule-interpreter — the
    executable behavior is `classify_zone`; this field is the audit-trail
    description of that behavior for a given policy version, so a reviewer
    can read what a version *claims* to do without reading Python."""
    review_policy: dict[str, int]
    """ADR-Governance §4, e.g. `{"unique_requires_reviewers": 1}` in the V0
    fixture (single-reviewer default for every tier — the ADR is explicit
    that the research does not establish a UNIQUE-only double-sign rule, so
    V0 ships the mechanism as configurable policy data, not a hardcoded
    business rule)."""
    effective_from: datetime
    status: str = Field(default="DRAFT")
    """`DRAFT | ACTIVE | RETIRED` per ADR-Governance §3. Kept as a plain
    `str` (not a `Literal`) here deliberately: policy lifecycle is a distinct,
    much simpler state machine from `ZoneAssessmentStatus` and this PR does
    not need to over-formalize it; validated to be one of the three values
    below so a typo is still caught."""
    checksum: str | None = None
    """Populated by `compute_checksum()` if left `None` at construction —
    see `model_validator` below. Exposed as a field (not a computed
    `@property`) so it can be persisted verbatim and compared later without
    recomputation, per ADR-Governance §3's "so 'same policy version' is
    verifiable"."""
    scoring_algorithm_version: str = Field(default=ZONE_SCORING_ALGORITHM_V0)
    """Closure fix (chief-architect review): ADR-Scoring's own framing —
    "influences the result -> either policy data or a traceable algorithm
    version" — previously had no traceable version at all; the scoring
    *code* (`zone_scoring_engine.py`) had no version identifier a persisted
    policy row could reference. This field records which version of the
    scoring algorithm (`compute_differentiation_index` /
    `compute_defensibility_index` / `compute_three_scores` / `classify_zone`
    as a bundle) a given policy version's stored results were computed
    under. `zone_scoring_engine.score_assessment` checks this value against
    its own `_SUPPORTED_ALGORITHM_VERSIONS` allowlist and fails closed if it
    does not recognize it — so a future `ZONE_SCORING_V1` engine cannot
    silently reinterpret an old `ZONE_SCORING_V0` policy (or vice versa)
    under a formula it was never validated against. Included in
    `compute_checksum()` for the same reason `weights`/`thresholds` are:
    it is part of what determines the output for given dimension inputs."""

    @field_validator("status")
    @classmethod
    def _status_is_legal(cls, value: str) -> str:
        if value not in {"DRAFT", "ACTIVE", "RETIRED"}:
            raise ProductIntelligenceValidationError("zone_policy_version_status_illegal")
        return value

    @field_validator("policy_id")
    @classmethod
    def _policy_id_non_empty(cls, value: str) -> str:
        return _require_non_empty_str(value, "policy_id")

    @field_validator("weights")
    @classmethod
    def _weights_cover_all_six_dimensions_non_negative(cls, value: dict[str, float]) -> dict[str, float]:
        # Closure fix: fail closed if a policy omits any of the six frozen
        # dimensions' weights (silently defaulting a missing weight would
        # let a policy author accidentally zero out a dimension's
        # contribution with no record of having done so) or supplies a
        # negative weight (would invert that dimension's sign inside a
        # weighted average, which no ADR licenses).
        missing = ZONE_DIMENSION_NAMES - value.keys()
        if missing:
            raise ProductIntelligenceValidationError("zone_policy_weights_missing_required_dimensions")
        negative = [k for k, v in value.items() if v < 0.0]
        if negative:
            raise ProductIntelligenceValidationError("zone_policy_weights_must_be_non_negative")
        return value

    def compute_checksum(self) -> str:
        """Deterministic sha256 over the policy-defining fields, JSON-encoded
        with sorted keys so field/dict-key ordering never changes the hash.
        Excludes `checksum` itself (obviously), `policy_id`, `effective_from`,
        and `status` — see class docstring for why those are excluded.

        Includes `scoring_algorithm_version` alongside `weights`/`thresholds`
        (closure fix) — see that field's docstring: it is part of what
        determines the scoring result for given inputs, so it belongs in the
        same "policy-defining fields" hash as the rest.
        """
        payload = {
            "version": self.version,
            "dimension_definitions": self.dimension_definitions,
            "weights": self.weights,
            "thresholds": self.thresholds,
            "classification_rules": self.classification_rules,
            "review_policy": self.review_policy,
            "scoring_algorithm_version": self.scoring_algorithm_version,
        }
        canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @model_validator(mode="after")
    def _fill_checksum_if_missing(self) -> "ZonePolicyVersion":
        if self.checksum is None:
            object.__setattr__(self, "checksum", self.compute_checksum())
        return self


class ProductZoneAssessment(_CommonFields):
    """ADR-Scoring + ADR-Governance's `ProductZoneAssessment`. Distinct from
    (and not a replacement for) the placeholder class of the same short name
    still defined in `entities.py` — see this module's docstring.
    """

    status: ZoneAssessmentStatus = "DRAFT"
    subject_type: str = "PRODUCT_CONCEPT"
    subject_ref: str
    zone_policy_version_id: str
    dimension_assessments: list[DimensionAssessment]
    differentiation_index: float
    defensibility_index: float
    commodity_score: float
    advantage_score: float
    unique_score: float
    recommended_zone: RecommendedZone
    approved_zone: ApprovedZone | None = None
    override_reason: str | None = None
    reviewed_by: str | None = None
    reviewed_at: datetime | None = None
    review_reason: str | None = None
    assessment_origin: AssessmentOrigin = "RULE"

    @field_validator("subject_type")
    @classmethod
    def _subject_type_is_v0_fixed(cls, value: str) -> str:
        # ADR-Scoring §1.1: the only legal subject_type in V0 is
        # PRODUCT_CONCEPT. Component/ProductDefinition/AIUseCase/Capability
        # are explicitly out of scope for this PR.
        if value != "PRODUCT_CONCEPT":
            raise ProductIntelligenceValidationError("zone_assessment_subject_type_must_be_product_concept")
        return value

    @field_validator("subject_ref", "zone_policy_version_id")
    @classmethod
    def _refs_non_empty(cls, value: str, info) -> str:
        return _require_non_empty_str(value, info.field_name)

    @field_validator("dimension_assessments")
    @classmethod
    def _dimension_assessments_cover_all_six_exactly_once(
        cls, value: list[DimensionAssessment], info
    ) -> list[DimensionAssessment]:
        # Integration fix (PR-002, flagged by Agent B's "Cross-Agent interface
        # note" in application/zone_commands.py): a DRAFT assessment has not
        # been scored yet — ADR-Governance frames DRAFT as "not yet scored" —
        # so it may legitimately have zero dimension_assessments. Forcing six
        # placeholder rows (the original workaround) meant a fake, always-
        # non-empty evidence_refs=["pending_initial_assessment"] value could
        # satisfy the "no evidence -> not reviewable" gate elsewhere by
        # accident. From SCORED onward, the exactly-six-unique rule is
        # unconditional, same as before.
        status = info.data.get("status")
        if status == "DRAFT" and len(value) == 0:
            return value
        if len(value) != 6:
            raise ProductIntelligenceValidationError("zone_assessment_requires_exactly_six_dimension_assessments")
        seen = [d.dimension for d in value]
        if len(set(seen)) != 6 or set(seen) != ZONE_DIMENSION_NAMES:
            raise ProductIntelligenceValidationError("zone_assessment_dimension_assessments_must_cover_all_six_uniquely")
        return value

    @model_validator(mode="after")
    def _override_reason_required_when_approved_zone_diverges(self) -> "ProductZoneAssessment":
        if self.approved_zone is not None and self.approved_zone != self.recommended_zone and not self.override_reason:
            raise ProductIntelligenceValidationError("zone_assessment_override_requires_override_reason")
        return self

    def dimension_score_map(self) -> dict[str, float]:
        """Convenience accessor used by callers (e.g. the scoring engine's
        caller, or a future review UI) that need `{dimension: score}` rather
        than the full `DimensionAssessment` objects. Pure, no side effects.
        """
        return {d.dimension: d.score for d in self.dimension_assessments}

    def transition_to(
        self,
        *,
        new_status: ZoneAssessmentStatus,
        actor_id: str,
        reason: str | None = None,
    ) -> "ProductZoneAssessment":
        """Apply a lifecycle transition per ADR-Governance §5, returning a new
        (version-bumped) instance. This method only enforces the *shape* of
        the transition (legal from/to per
        `zone_value_objects.ZONE_ASSESSMENT_STATUS_TRANSITIONS`,
        evidence-gate for entering `UNDER_REVIEW`/`APPROVED`, and the
        `approved_zone`/`override_reason` pairing). It deliberately does NOT
        check `actor_type`/permissions (`product_intelligence.zone.review`)
        — that is the application layer's (Agent B's) responsibility, per
        this Agent's task-brief scope ("you only manage the legality of the
        state transition, not who has authority to invoke it").
        """
        from .zone_value_objects import is_legal_zone_status_transition

        if not is_legal_zone_status_transition(self.status, new_status):
            raise ProductIntelligenceValidationError("zone_assessment_illegal_status_transition")

        if new_status in ("UNDER_REVIEW", "APPROVED"):
            # ADR-Governance §1: "NO EVIDENCE -> NOT REVIEWABLE". An
            # unscored DRAFT (0 dimension_assessments, per the integration
            # fix above) must never reach here either — `any()` over an
            # empty list is vacuously False, so the length check is
            # required in addition to the per-dimension evidence check, not
            # redundant with it.
            if len(self.dimension_assessments) != 6 or any(not d.evidence_refs for d in self.dimension_assessments):
                raise ProductIntelligenceValidationError("zone_assessment_missing_evidence_not_reviewable")

        now = datetime.now(timezone.utc)
        update: dict[str, object] = {
            "status": new_status,
            "updated_at": now,
            "version": self.version + 1,
        }
        if new_status in ("APPROVED", "REJECTED"):
            update["reviewed_by"] = actor_id
            update["reviewed_at"] = now
            update["review_reason"] = reason
        return self.model_copy(update=update)
