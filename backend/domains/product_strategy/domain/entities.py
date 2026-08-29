"""Product Strategy domain entities.

No TS predecessor — new domain, schema authored directly against
`architecture/FAMILY_PRODUCT_INTELLIGENCE_PLATFORM_TARGET_ARCHITECTURE_DRAFT_001.md`
§4, restated here as behaviour-bearing entities (the `packages/contracts`
versions are plain data schemas with no methods).

This module has no FastAPI / SQLAlchemy / provider-SDK dependency, per the
four-layer rule in `architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md`
section 3.
"""
from __future__ import annotations

from pydantic import BaseModel

# Absolute package import: `backend.domains` and `backend.packages` are sibling
# subpackages of the installed `backend` package, so relative dots cannot cross
# between them. Resolution never depends on process cwd (constitution R12).
from backend.packages.contracts.evidence import NON_ESTABLISHING_LEVELS, Provenance

from .errors import ProductStrategyValidationError


class GrowthProblem(BaseModel):
    problem_id: str
    symptom: str
    insight_id: str | None = None
    provenance: Provenance


class Opportunity(BaseModel):
    opportunity_id: str
    problem_id: str
    status: str = "WATCH"
    provenance: Provenance

    def promote_to_invest(self, real_evidence: Provenance) -> Opportunity:
        """Move to INVEST status. Guardrail: refuses to promote on
        simulated/inferred/unverified/unknown evidence — see
        `packages/contracts/evidence.py` `NON_ESTABLISHING_LEVELS`. This is
        the "simulated data cannot self-certify" rule (`CLAUDE.md` section 4)
        encoded as a runtime check, not just documentation.

        Returns a new `Opportunity` instance rather than mutating `self`,
        matching the rest of this skeleton's immutability convention.
        """
        if real_evidence.level in NON_ESTABLISHING_LEVELS:
            raise ProductStrategyValidationError(
                "opportunity_promotion_requires_establishing_evidence"
            )
        return self.model_copy(update={"status": "INVEST", "provenance": real_evidence})
