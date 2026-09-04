"""Shared, minimized DTO for the Live recommendation connection layer.

It is a sandbox contract, not a new canonical FamilyNeed or plan model.  Its
inputs must be supplied by the existing platform owners; the DTO explicitly
excludes child profiles, rankings, room tokens, payment state, and AI facts.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from .family_need_service_adapter import (
    SANDBOX_SOURCE,
    AdultContext,
    ConfirmedNeedProjection,
    LiveNeedBridgeRejected,
)


@dataclass(frozen=True, slots=True)
class DynamicPlanProjection:
    plan_ref: str
    tenant_id: str
    family_id: str
    status: str
    next_step: str
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


@dataclass(frozen=True, slots=True)
class LiveFamilyNeedRecommendationDTO:
    session_ref: str
    need_id: str
    plan_ref: str
    growth_theme: str
    need_statement: str
    recommendation_reason: str
    audience_label: str
    next_step: str
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True
    external_effect: bool = False

    def as_json(self) -> dict[str, object]:
        return asdict(self)


def build_recommendation(
    *,
    session_ref: str,
    need: ConfirmedNeedProjection,
    plan: DynamicPlanProjection,
    guardian: AdultContext,
    now: datetime,
) -> LiveFamilyNeedRecommendationDTO:
    if guardian.actor_type != "FAMILY_GUARDIAN":
        raise LiveNeedBridgeRejected("recommendations are adult-only")
    if not session_ref or need.status not in {"CONFIRMED", "PROFILED", "SOLUTIONING"}:
        raise LiveNeedBridgeRejected("a confirmed FamilyNeed and session are required")
    if need.expires_at.astimezone(UTC) <= now.astimezone(UTC):
        raise LiveNeedBridgeRejected("FamilyNeed projection has expired")
    if not need.growth_theme or not plan.next_step:
        raise LiveNeedBridgeRejected("growth theme and plan next step are required")
    if (
        need.tenant_id != guardian.tenant_id
        or need.family_id != guardian.family_id
        or plan.tenant_id != guardian.tenant_id
        or plan.family_id != guardian.family_id
        or plan.status != "ACTIVE"
        or plan.source != SANDBOX_SOURCE
        or not plan.fixture_only
    ):
        raise LiveNeedBridgeRejected("recommendation projection is out of scope")
    return LiveFamilyNeedRecommendationDTO(
        session_ref=session_ref,
        need_id=need.need_id,
        plan_ref=plan.plan_ref,
        growth_theme=need.growth_theme,
        need_statement="放学后的沟通常常以争执收场。",
        recommendation_reason=f"本场围绕“{need.growth_theme}”提供当前方案需要的练习。",
        audience_label="希望减少冲突的家长与照护者",
        next_step=plan.next_step,
    )
