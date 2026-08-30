"""Ports for the Journey application layer.

The ports keep HTTP, persistence, and identity composition outside the domain.
Every method carries tenant and family scope so a future PostgreSQL adapter
cannot accidentally turn a family projection into a global feed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from ..domain.models import JourneyAction, JourneyPlan, PhaseReview


@dataclass(frozen=True, slots=True)
class JourneyActor:
    """Trusted identity resolved by the composition root."""

    actor_id: str
    tenant_id: str
    family_id: str
    actor_type: str = "HUMAN"


class JourneyRepository(Protocol):
    async def get_current(
        self, tenant_id: str, family_id: str, onboarding_id: str | None = None
    ) -> JourneyPlan | None: ...

    async def get(self, tenant_id: str, family_id: str, plan_id: str) -> JourneyPlan | None: ...

    async def save_plan(self, plan: JourneyPlan) -> None: ...

    async def has_confirmed_priority(
        self, tenant_id: str, family_id: str, onboarding_id: str, priority_id: str
    ) -> bool: ...

    async def append_action(self, action: JourneyAction) -> None: ...

    async def list_actions(
        self, tenant_id: str, family_id: str, plan_id: str
    ) -> list[JourneyAction]: ...

    async def append_review(self, review: PhaseReview) -> None: ...

    async def list_reviews(
        self, tenant_id: str, family_id: str, plan_id: str
    ) -> list[PhaseReview]: ...

    async def load_idempotency(
        self, tenant_id: str, family_id: str, operation: str, key: str
    ) -> tuple[str, dict] | None: ...

    async def save_idempotency(
        self,
        tenant_id: str,
        family_id: str,
        operation: str,
        key: str,
        fingerprint: str,
        response: dict,
    ) -> None: ...


class JourneyPolicy(Protocol):
    async def assert_can_read(self, actor: JourneyActor) -> None: ...

    async def assert_can_manage(self, actor: JourneyActor) -> None: ...


class JourneyClock(Protocol):
    def now(self) -> datetime: ...
