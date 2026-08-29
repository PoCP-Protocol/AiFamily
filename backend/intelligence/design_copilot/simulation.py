"""SimulationLab — STRUCTURE_ONLY.

Encodes the same "simulated data cannot self-certify" guardrail as
`domains/product_strategy/domain/entities.py` `Opportunity.promote_to_invest`,
deliberately duplicated here rather than sharing one gate function. Two
independent enforcement points mean a bug in one doesn't silently let
simulated evidence through the other — see `CLAUDE.md` section 4 and
`architecture/FAMILY_PRODUCT_INTELLIGENCE_PLATFORM_TARGET_ARCHITECTURE_DRAFT_001.md`
§2.

This class has no real synthetic-family model — `run()` is not implemented.
It exists to fix the guardrail's shape in code before any simulation content
is built, per the project-owner-approved compromise (structure first,
guessed parameters never).
"""
from __future__ import annotations

from backend.packages.contracts.evidence import NON_ESTABLISHING_LEVELS, Provenance
from backend.packages.contracts.product_factory import ProductDefinition


class ProductStrategyValidationError(Exception):
    """Mirrors `domains.product_strategy.domain.errors.ProductStrategyValidationError`
    without importing across domain boundaries — `intelligence/` is not a
    domain and should not depend on a specific domain's error hierarchy.
    """


class SimulationResult:
    """`provenance.level` is always `"simulated"` — set here, not accepted
    as a constructor argument, so no caller can smuggle a non-simulated
    provenance into a simulation result.
    """

    def __init__(self, product_id: str, synthetic_family_id: str, outcome_summary: str):
        self.product_id = product_id
        self.synthetic_family_id = synthetic_family_id
        self.outcome_summary = outcome_summary
        self.provenance = Provenance(
            level="simulated", source_ref=f"simulation:{synthetic_family_id}"
        )


class SimulationLab:
    def run(self, product: ProductDefinition, synthetic_family: dict) -> SimulationResult:
        """Run `product` against one synthetic family profile. Not
        implemented — no calibrated synthetic-family model exists yet (see
        DRAFT doc §2: calibration requires real family data, which this
        skeleton must not invent).
        """
        raise NotImplementedError("待真实家庭数据校准模拟器参数后实现,当前仅占位签名")

    def promote_to_pilot(
        self, simulation_result: SimulationResult, real_evidence: Provenance
    ) -> None:
        """Gate for Simulation → Pilot promotion. Refuses unless
        `real_evidence` is NOT simulated/inferred/unverified/unknown —
        i.e. a simulation result alone, no matter how favorable, can never
        authorize moving to a real family pilot.
        """
        if real_evidence.level in NON_ESTABLISHING_LEVELS:
            raise ProductStrategyValidationError("pilot_promotion_requires_establishing_evidence")
