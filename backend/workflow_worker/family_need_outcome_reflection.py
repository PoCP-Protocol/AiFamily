"""Workflow-worker activity for FamilyNeed outcome reflection projection.

The process runtime owns cadence and retries; this activity owns only one
bounded, authorized poll.  It deliberately depends on the intelligence poller
port rather than a domain repository or model provider.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.intelligence.context_engine.family_need_outcome_poller import (
    FamilyNeedOutcomeReflectionPoller,
    OutcomeReflectionPollResult,
)
from backend.workflow_worker.runtime import ActivityExecution


@dataclass(frozen=True, slots=True)
class FamilyNeedOutcomeReflectionActivity:
    poller: FamilyNeedOutcomeReflectionPoller
    tenant_id: str
    family_id: str
    limit: int = 100
    _last_report: OutcomeReflectionPollResult | None = field(init=False, default=None)

    def __post_init__(self) -> None:
        if not isinstance(self.poller, FamilyNeedOutcomeReflectionPoller):
            raise TypeError("poller must be a FamilyNeedOutcomeReflectionPoller")
        if not self.tenant_id.strip() or not self.family_id.strip():
            raise ValueError("tenant and family are required")

    @property
    def name(self) -> str:
        return "family_need.outcome_reflection"

    async def run_once(self) -> ActivityExecution:
        """Execute one worker activity; deployment supplies recurrence."""

        report = await self.poller.poll_once(
            tenant_id=self.tenant_id,
            family_id=self.family_id,
            limit=self.limit,
        )
        object.__setattr__(self, "_last_report", report)
        return ActivityExecution(
            succeeded=True,
            result_type=type(report).__name__,
        )

    async def poll_once(self) -> OutcomeReflectionPollResult:
        """Expose the detailed report for direct orchestration tests."""

        report = await self.poller.poll_once(
            tenant_id=self.tenant_id,
            family_id=self.family_id,
            limit=self.limit,
        )
        object.__setattr__(self, "_last_report", report)
        return report

    @property
    def last_report(self) -> OutcomeReflectionPollResult | None:
        """Most recent bounded-pass metrics; no durable state is inferred."""

        return self._last_report


def build_family_need_outcome_reflection_activity(
    *,
    poller: FamilyNeedOutcomeReflectionPoller,
    tenant_id: str,
    family_id: str,
    limit: int = 100,
) -> FamilyNeedOutcomeReflectionActivity:
    """Explicit composition seam for the workflow-worker root.

    Dependencies are supplied by the root so this module never invents a
    database session, identity, consent scope, or deletion reference.
    """

    if limit <= 0 or limit > 1000:
        raise ValueError("event limit must be between 1 and 1000")
    return FamilyNeedOutcomeReflectionActivity(
        poller=poller,
        tenant_id=tenant_id,
        family_id=family_id,
        limit=limit,
    )


__all__ = [
    "FamilyNeedOutcomeReflectionActivity",
    "build_family_need_outcome_reflection_activity",
]
