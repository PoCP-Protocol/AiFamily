"""Read models for the loyalty points domain.

Every number here is derived from the append-only ledger. There is no
gamification counter stored anywhere — if a figure cannot be recomputed from
ledger rows, it is not shown. The failure being prevented is the worst one in a
points system: a parent sees 1,280 points while the ledger only accounts for 800.

`balance` therefore has no setter and no column; it is `SUM(points_delta)`.
And no field expresses points as money (no `cash_value` / `worth` / `≈¥`) —
`backend/packages/contracts/value_ordering.py` explains why, and a guardrail
test enforces it.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class LedgerEntryView(BaseModel):
    """One line of 权益账本 — also the event stream the UI animates.

    `evidence_ref` is included deliberately: the first thing a family should be
    able to see about a point is *where it came from*, not how much it is worth.
    """

    occurred_at: datetime
    entry_type: Literal["EARN", "REDEEM", "EXPIRE", "ADJUST"]
    points_delta: int
    balance_after: int
    rule_ref: str | None = None
    evidence_ref: str | None = None
    reason_code: str | None = None
    source_page_id: str


class EarnTaskView(BaseModel):
    """One row of 积分任务.

    `remaining_today` makes the cap visible instead of letting a family discover
    it by being silently refused — `[宣发P9]`「用户自愿、信息透明」.
    """

    rule_ref: str
    title: str
    explanation: str
    source_kind: str
    points_per_event: int
    daily_cap: int | None = None
    earned_today: int = 0
    remaining_today: int | None = None
    requires_qualification: bool = False


class RedemptionItemView(BaseModel):
    item_ref: str
    title: str
    reward_kind: str
    points_price: int
    affordable: bool


class RedemptionView(BaseModel):
    redemption_ref: str
    item_ref: str
    reward_kind: str
    points_spent: int
    status: str
    created_at: datetime


class MilestoneView(BaseModel):
    """An evidence-bound milestone. Every one points at something that already
    happened and cannot be taken away — 数字会花掉,事实不会."""

    code: str
    label: str
    occurred_at: datetime
    evidence_ref: str


class PointsProjection(BaseModel):
    family_id: str
    projection_version: int = 1
    visibility: Literal["FAMILY_PRIVATE"] = "FAMILY_PRIVATE"
    account_status: str | None = None
    balance: int = 0
    ledger: list[LedgerEntryView] = []
    earn_tasks: list[EarnTaskView] = []
    redemptions: list[RedemptionView] = []
    catalogue: list[RedemptionItemView] = []
    streak_days: int = 0
    milestones: list[MilestoneView] = []
    text_equivalent: str = ""


class ScreenView(BaseModel):
    """Per-surface view. `surface_id` / `feature_points` come from
    `backend/packages/contracts/ui_surfaces.py`, so a screen's payload and the
    frontend's declared feature list cannot drift silently."""

    surface_id: str
    title: str
    feature_points: list[str]
    blocks: dict
    notices: list[str] = []
