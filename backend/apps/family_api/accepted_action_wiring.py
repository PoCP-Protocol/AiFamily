"""Production composition root for accepted AI Named Action delivery.

The Human Gate and the delivery ledger intentionally expose different
responsibilities.  This module is the application-level join point: it binds
both stores to one SQL session, installs the FGCN handlers (including the
human-confirmed Blueprint proposal consumer), and exposes bounded worker runs.
The same assembly is used in staging and production; only the injected
session factory and provider-admission boundary differ.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.apps.family_api.growth_plan_accepted_action import (
    CurrentScopeResolver,
    GrowthPlanAcceptedActionHandler,
    JourneyDraftApplication,
)
from backend.apps.family_api.growth_plan_activation_wiring import (
    CONFIRM_JOURNEY_PLAN_ACTION,
    DailyActionInitializer,
    JourneyActivationApplication,
    JourneyPlanActivationAcceptedActionHandler,
    JourneyPlanActivationHumanGateApplication,
)
from backend.apps.family_api.growth_plan_review_wiring import (
    CREATE_JOURNEY_PLAN_ACTION,
    SqlAlchemyGrowthPlanDraftRegistry,
)
from backend.domains.service.fgcn.accepted_action import (
    build_fgcn_accepted_action_handlers,
)
from backend.domains.service.fgcn.admission import (
    DEFAULT_ASYNC_PROVIDER_ADMISSION,
    AsyncProviderAdmissionQuery,
)
from backend.domains.service.fgcn.blueprint_proposal import (
    SqlAlchemyServiceBlueprintProposalStore,
)
from backend.domains.service.fgcn.persistence import SqlAlchemyFGCNRepository
from backend.intelligence.experience.accepted_achievement import (
    ACHIEVEMENT_ACTION_NAME,
    ExperienceAchievementActionHandler,
)
from backend.intelligence.experience.achievement_persistence import (
    SqlAlchemyAchievementProjection,
)
from backend.intelligence.experience.engagement_persistence import (
    SqlAlchemyEngagementEventReader,
)
from backend.intelligence.experience.engagement_review import (
    AcceptedAchievementDraftVerifier,
    SqlAlchemyEngagementDraftReviewStore,
)
from backend.intelligence.experience.feedback_response import (
    FEEDBACK_RESPONSE_ACTION_NAME,
    ExperienceFeedbackResponseActionHandler,
)
from backend.intelligence.experience.projections import (
    SqlAlchemyAchievementNotificationProjection,
    SqlAlchemyExperienceAnalyticsProjection,
)
from backend.intelligence.human_gate import SqlAlchemyHumanGate
from backend.intelligence.tool_runtime.accepted_delivery import (
    AcceptedActionDelivery,
    AcceptedActionDeliveryStatus,
    SqlAlchemyAcceptedActionDeliveryStore,
)
from backend.intelligence.tool_runtime.accepted_dispatch import AcceptedNamedActionDispatcher
from backend.intelligence.tool_runtime.accepted_worker import (
    AcceptedActionQueue,
    AcceptedActionScheduler,
    AcceptedActionSchedulerReport,
    AcceptedNamedActionWorker,
)
from backend.platform.audit import AuditRecorder


class GrowthPlanJourneyApplication(
    JourneyDraftApplication,
    JourneyActivationApplication,
    Protocol,
):
    """Journey port required by both growth-plan accepted actions."""


class SqlAlchemyAcceptedActionQueue(AcceptedActionQueue):
    """Filter Human Gate candidates by the durable delivery ledger.

    Human Gate deliberately keeps the immutable decision in ``DECIDED``
    status after delivery.  The ledger is therefore the queue's completion
    marker.  Filtering here avoids polling successful/dead-lettered actions
    forever while retaining the Human Gate as the source of candidate ids.
    """

    def __init__(
        self,
        gate: SqlAlchemyHumanGate,
        delivery: SqlAlchemyAcceptedActionDeliveryStore,
    ) -> None:
        self._gate = gate
        self._delivery = delivery

    async def pending_accepted_task_ids(self, *, limit: int = 100) -> tuple[str, ...]:
        if limit < 0:
            raise ValueError("limit must be non-negative")
        candidates = await self._gate.pending_accepted_task_ids(limit=limit)
        pending: list[str] = []
        for task_id in candidates:
            task = await self._gate.get(task_id)
            request = task.action_request
            if request is None:
                continue
            delivery = await self._delivery.get(request.request_id)
            if delivery is None or delivery.status is AcceptedActionDeliveryStatus.PENDING:
                pending.append(task_id)
        return tuple(pending)


@dataclass(frozen=True, slots=True)
class FGCNAcceptedActionRuntime:
    """Bounded, restart-safe runtime for accepted AI actions."""

    session_factory: async_sessionmaker[AsyncSession]
    claim_owner: str
    provider_admission: AsyncProviderAdmissionQuery = DEFAULT_ASYNC_PROVIDER_ADMISSION
    max_attempts: int = 3
    growth_plan_scope_resolver: CurrentScopeResolver | None = None
    journey_application: GrowthPlanJourneyApplication | None = None
    growth_plan_daily_action_initializer: DailyActionInitializer | None = None
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("session_factory must be an async_sessionmaker")
        if not isinstance(self.claim_owner, str) or not self.claim_owner.strip():
            raise ValueError("claim_owner is required")
        if self.claim_owner.lower().startswith("ai:") or self.claim_owner.upper() in {
            "AI",
            "SYSTEM",
        }:
            raise ValueError("claim_owner must identify a workflow worker")
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        if not callable(getattr(self.provider_admission, "resolve", None)):
            raise TypeError("provider_admission must expose async resolve")
        if (self.growth_plan_scope_resolver is None) != (self.journey_application is None):
            raise ValueError(
                "growth plan scope resolver and journey application must be configured together"
            )
        if self.journey_application is not None and any(
            not callable(getattr(self.journey_application, method, None))
            for method in ("create", "get_current", "confirm")
        ):
            raise TypeError("growth plan journey application is incomplete")
        if not callable(self.clock):
            raise TypeError("accepted action runtime clock must be callable")

    async def run_until_idle(
        self,
        *,
        limit: int = 100,
        max_polls: int = 10,
        lease_ttl: timedelta = timedelta(minutes=5),
        claimed_at: datetime | None = None,
        completed_at: datetime | None = None,
    ) -> AcceptedActionSchedulerReport:
        """Run bounded delivery passes using one session per invocation."""

        async with self.session_factory() as session:
            gate = SqlAlchemyHumanGate(session)
            delivery = SqlAlchemyAcceptedActionDeliveryStore(session)
            repository = SqlAlchemyFGCNRepository(session)
            proposal_store = SqlAlchemyServiceBlueprintProposalStore(session)
            recorder = AuditRecorder()
            handlers = dict(
                build_fgcn_accepted_action_handlers(
                    repository,
                    recorder=recorder,
                    provider_admission=self.provider_admission,
                    proposal_store=proposal_store,
                )
            )
            handlers[ACHIEVEMENT_ACTION_NAME] = ExperienceAchievementActionHandler(
                SqlAlchemyAchievementProjection(session),
                recorder=recorder,
                notifications=SqlAlchemyAchievementNotificationProjection(session),
                analytics=SqlAlchemyExperienceAnalyticsProjection(session),
                verifier=AcceptedAchievementDraftVerifier(
                    SqlAlchemyEngagementDraftReviewStore(session),
                    SqlAlchemyEngagementEventReader(session),
                ),
            )
            handlers[FEEDBACK_RESPONSE_ACTION_NAME] = (
                ExperienceFeedbackResponseActionHandler(session, recorder=recorder)
            )
            if (
                self.growth_plan_scope_resolver is not None
                and self.journey_application is not None
            ):
                registry = SqlAlchemyGrowthPlanDraftRegistry(self.session_factory)
                activation_review = JourneyPlanActivationHumanGateApplication(
                    session_factory=self.session_factory,
                    clock=self.clock,
                )
                handlers[CREATE_JOURNEY_PLAN_ACTION] = GrowthPlanAcceptedActionHandler(
                    registry,
                    scope_resolver=self.growth_plan_scope_resolver,
                    journey=self.journey_application,
                    activation_review=activation_review,
                    clock=self.clock,
                )
                handlers[CONFIRM_JOURNEY_PLAN_ACTION] = (
                    JourneyPlanActivationAcceptedActionHandler(
                        registry,
                        scope_resolver=self.growth_plan_scope_resolver,
                        journey=self.journey_application,
                        daily_action_initializer=self.growth_plan_daily_action_initializer,
                        clock=self.clock,
                    )
                )
            worker = AcceptedNamedActionWorker(
                gate,
                delivery,
                AcceptedNamedActionDispatcher(handlers),
                max_attempts=self.max_attempts,
            )
            scheduler = AcceptedActionScheduler(
                worker,
                SqlAlchemyAcceptedActionQueue(gate, delivery),
            )
            return await scheduler.run_until_idle(
                claim_owner=self.claim_owner,
                limit=limit,
                max_polls=max_polls,
                lease_ttl=lease_ttl,
                claimed_at=claimed_at,
                completed_at=completed_at,
            )

    async def list_dead_letters(
        self, *, limit: int = 100
    ) -> tuple[AcceptedActionDelivery, ...]:
        """Return metadata-only dead letters for an operational inbox."""

        async with self.session_factory() as session:
            store = SqlAlchemyAcceptedActionDeliveryStore(session)
            return await store.list_dead_letters(limit=limit)


__all__ = [
    "FGCNAcceptedActionRuntime",
    "GrowthPlanJourneyApplication",
    "SqlAlchemyAcceptedActionQueue",
]
