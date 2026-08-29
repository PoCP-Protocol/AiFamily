"""Product Learning schemas — STRUCTURE_ONLY.

`ProductHealthScore` dimensions are all `float | None` with no default
weighting — per the project-owner-approved compromise, no guessed parameter
is allowed to ship in this skeleton. Filling these in requires real
post-publish family usage data, not invented weights.
"""

from __future__ import annotations

from pydantic import BaseModel

from .evidence import Provenance


class ProductHealthScore(BaseModel):
    product_id: str
    customer_value: float | None = None
    engagement: float | None = None
    ai_quality: float | None = None
    service_quality: float | None = None
    unit_economics: float | None = None
    differentiation: float | None = None
    defensibility: float | None = None
    provenance: Provenance
