"""Database-backed Journey application adapter for authenticated composition roots."""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncEngine

from backend.platform.persistence.session import get_engine, is_postgres_url

from ..application.service import JourneyActor, JourneyService
from ..domain.models import GrowthPriorityDecision, PhaseDecision
from .sqlalchemy_policy import SqlAlchemyJourneyPolicy
from .sqlalchemy_repository import SqlAlchemyJourneyRepository
from .transaction import JourneyTransactionRunner

ReadOperation = Callable[[JourneyService], Awaitable[dict]]


class SqlAlchemyJourneyApplication:
    def __init__(
        self, engine: AsyncEngine, transaction_runner: JourneyTransactionRunner | None = None
    ):
        self._engine = engine
        self._transactions = transaction_runner or JourneyTransactionRunner(engine)

    async def _read(self, operation: ReadOperation) -> dict:
        async with self._engine.connect() as connection:
            service = JourneyService(
                SqlAlchemyJourneyRepository(connection), SqlAlchemyJourneyPolicy(connection)
            )
            return await operation(service)

    async def get_current(self, actor: JourneyActor) -> dict:
        return await self._read(lambda service: service.get_current(actor))

    async def get_growth_priority(self, actor: JourneyActor, onboarding_id: str) -> dict:
        return await self._read(
            lambda service: service.get_growth_priority(actor, onboarding_id)
        )

    async def get_plan_preview(self, actor: JourneyActor, onboarding_id: str) -> dict:
        return await self._read(lambda service: service.get_plan_preview(actor, onboarding_id))

    async def get_service_journey(self, actor: JourneyActor, onboarding_id: str) -> dict:
        return await self._read(
            lambda service: service.get_service_journey(actor, onboarding_id)
        )

    async def refresh_plan_preview(
        self,
        actor: JourneyActor,
        onboarding_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> dict:
        return await self._transactions.execute(
            actor=actor,
            action="RefreshJourneyPlanPreview",
            resource_type="JourneyPlanPreview",
            resource_id=onboarding_id,
            event_name="JourneyPlanPreviewRefreshed",
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            request_payload={"onboarding_id": onboarding_id},
            operation=lambda service: service.refresh_plan_preview(
                actor, onboarding_id, idempotency_key, correlation_id
            ),
        )

    async def confirm_growth_priority(
        self,
        actor: JourneyActor,
        onboarding_id: str,
        draft_id: str,
        decision: GrowthPriorityDecision,
        idempotency_key: str,
        correlation_id: str,
    ) -> dict:
        return await self._transactions.execute(
            actor=actor,
            action="ConfirmGrowthPriority",
            resource_type="GrowthPriority",
            resource_id=lambda response: (
                response["priority"]["priority_id"]
                if response.get("priority")
                else onboarding_id
            ),
            event_name="GrowthPriorityConfirmed",
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            request_payload={
                "onboarding_id": onboarding_id,
                "draft_id": draft_id,
                "decision": decision.value,
            },
            operation=lambda service: service.confirm_growth_priority(
                actor, onboarding_id, draft_id, decision, idempotency_key, correlation_id
            ),
        )

    async def create(
        self,
        actor: JourneyActor,
        onboarding_id: str,
        priority_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> dict:
        return await self._transactions.execute(
            actor=actor,
            action="CreateJourneyPlan",
            resource_type="JourneyPlan",
            resource_id=lambda response: response["plan"]["plan_id"],
            event_name="JourneyPlanCreated",
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            request_payload={"onboarding_id": onboarding_id, "priority_id": priority_id},
            operation=lambda service: service.create(
                actor, onboarding_id, priority_id, idempotency_key, correlation_id
            ),
        )

    async def confirm(
        self,
        actor: JourneyActor,
        plan_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> dict:
        return await self._transactions.execute(
            actor=actor,
            action="ConfirmJourneyPlan",
            resource_type="JourneyPlan",
            resource_id=plan_id,
            event_name="JourneyPlanConfirmed",
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            request_payload={"plan_id": plan_id},
            operation=lambda service: service.confirm(
                actor, plan_id, idempotency_key, correlation_id
            ),
        )

    async def review(
        self,
        actor: JourneyActor,
        plan_id: str,
        decision: PhaseDecision,
        idempotency_key: str,
        correlation_id: str,
    ) -> dict:
        return await self._transactions.execute(
            actor=actor,
            action="ReviewJourneyPhase",
            resource_type="JourneyPlan",
            resource_id=plan_id,
            event_name="JourneyPhaseReviewed",
            idempotency_key=idempotency_key,
            correlation_id=correlation_id,
            request_payload={"plan_id": plan_id, "decision": decision.value},
            operation=lambda service: service.review(
                actor, plan_id, decision, idempotency_key, correlation_id
            ),
        )


def build_postgres_journey_application(database_url: str) -> SqlAlchemyJourneyApplication:
    if not is_postgres_url(database_url):
        raise RuntimeError("journey_production_requires_postgresql")
    return SqlAlchemyJourneyApplication(get_engine(database_url))
