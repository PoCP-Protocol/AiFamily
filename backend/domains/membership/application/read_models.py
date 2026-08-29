"""Read models, named after the App UI surfaces they serve.

Shapes stay compatible with the frontend's existing
`FamilyApiMembershipProjection` (`apps/mobile/lib/family/family-api-projections.ts`
lines 275-302): `family_id / projection_version / visibility / subscriptions[]
/ benefits[] / text_equivalent`. The V2 lifecycle additions (`tier`,
`current_period`, `renewal_window`) are new optional blocks, so the existing
client keeps parsing.

`visibility` is hard-coded `FAMILY_PRIVATE` — every read in this domain is
family-scoped and there is no cross-family shape to return.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

from ..domain.value_objects import TierCode


class SubscriptionView(BaseModel):
    membership_subscription_id: str
    plan_ref: str
    plan_version: int
    status: str
    effective_from: datetime
    effective_to: datetime | None = None


class BenefitView(BaseModel):
    benefit_grant_id: str
    benefit_ref: str
    status: str
    allocated_units: int
    remaining_units: int
    reserved_units: int = 0
    valid_from: datetime
    valid_to: datetime | None = None


class PeriodView(BaseModel):
    membership_period_id: str
    tier_code: TierCode
    seq_no: int
    status: str
    starts_at: datetime
    ends_at: datetime | None = None


class TierTransitionView(BaseModel):
    """Why the tier is what it is. Surfaced so a family can always answer
    "how did we get here" without asking support — `activation_source_*` is the
    audit pair required by baseline invariant 1."""

    occurred_at: datetime
    from_tier_code: TierCode | None
    to_tier_code: TierCode
    direction: str
    activation_source_type: str
    activation_source_ref: str
    decided_by: str


class MembershipProjection(BaseModel):
    family_id: str
    projection_version: int = 2
    visibility: Literal["FAMILY_PRIVATE"] = "FAMILY_PRIVATE"
    tier_code: TierCode | None = None
    current_period: PeriodView | None = None
    period_history: list[PeriodView] = []
    subscriptions: list[SubscriptionView] = []
    benefits: list[BenefitView] = []
    tier_history: list[TierTransitionView] = []
    text_equivalent: str = ""


class ScreenView(BaseModel):
    """A per-surface view. `surface_id` and `feature_points` come from
    `backend/packages/contracts/ui_surfaces.py`, so a screen's backend payload
    and the frontend's declared feature list cannot drift apart silently.
    """

    surface_id: str
    title: str
    feature_points: list[str]
    blocks: dict
    notices: list[str] = []
