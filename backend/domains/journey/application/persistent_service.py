"""Async application facade for the persisted Journey MVP scenario.

The HTTP composition root can inject this facade in place of the in-memory
candidate.  It owns request transactions, while the repository owns SQL
mapping.  No method commits until the domain write and the injected canonical
event writer have both succeeded.
"""

from __future__ import annotations

from collections.abc import Callable
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..domain.errors import JourneyConflictError, JourneyForbiddenError, JourneyValidationError
from ..infrastructure.sqlalchemy_repository import (
    EventWriter,
    SqlAlchemyJourneyRepository,
    canonical_event_writer,
)
from .plan_service import (
    HUMAN_CONFIRMED_INTENT_BOUNDARY,
    ConfirmedGrowthIntent,
    FamilyPractice,
    JourneyPlan,
    JourneyPlanStatus,
    PracticeRecord,
)

EventWriterFactory = Callable[[AsyncSession], EventWriter]


class PersistentJourneyPlanService:
    """Application service for the user-visible persisted Journey flow."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        event_writer_factory: EventWriterFactory = canonical_event_writer,
    ) -> None:
        self._session_factory = session_factory
        self._event_writer_factory = event_writer_factory

    async def create_plan_from_intent(
        self, *, intent: ConfirmedGrowthIntent, idempotency_key: str
    ) -> dict[str, object]:
        self._require_key(idempotency_key)
        if intent.boundary != HUMAN_CONFIRMED_INTENT_BOUNDARY:
            raise JourneyForbiddenError("unconfirmed_growth_intent")
        plan = JourneyPlan(
            plan_id=str(
                uuid5(
                    NAMESPACE_URL,
                    f"journey-plan:{intent.tenant_id}:{intent.family_id}:{intent.intent_id}",
                )
            ),
            tenant_id=intent.tenant_id,
            family_id=intent.family_id,
            actor_id=intent.actor_id,
            focus_id=intent.need_type,
            goal_text=intent.goal_text.strip(),
            intent_id=intent.intent_id,
            evidence_refs=intent.evidence_refs,
            knowledge_refs=intent.knowledge_refs,
        )
        if not plan.goal_text:
            raise JourneyValidationError("journey_goal_required")
        async with self._session_factory() as session:
            repository = SqlAlchemyJourneyRepository(session, self._event_writer_factory(session))
            await repository.create_plan(plan)
            await session.commit()
        return {"plan": plan.as_dict(), "created": True, "replayed": False}

    async def confirm_plan(
        self, *, tenant_id: str, family_id: str, actor_id: str, plan_id: str, idempotency_key: str
    ) -> dict[str, object]:
        self._require_key(idempotency_key)
        async with self._session_factory() as session:
            repository = SqlAlchemyJourneyRepository(session, self._event_writer_factory(session))
            await repository.confirm_plan(
                plan_id=plan_id, actor_id=actor_id, tenant_id=tenant_id, family_id=family_id
            )
            await session.commit()
            result = await repository.read_plan(
                plan_id=plan_id, tenant_id=tenant_id, family_id=family_id
            )
        return {"plan": result["plan"], "replayed": False}

    async def add_practice(
        self,
        *,
        tenant_id: str,
        family_id: str,
        actor_id: str,
        plan_id: str,
        title: str,
        rationale: str,
        day_index: int,
        idempotency_key: str,
    ) -> dict[str, object]:
        self._require_key(idempotency_key)
        if not title.strip() or not rationale.strip() or not 1 <= day_index <= 21:
            raise JourneyValidationError("journey_practice_invalid")
        practice = FamilyPractice(
            practice_id=str(uuid5(NAMESPACE_URL, f"journey-practice:{plan_id}:{day_index}")),
            plan_id=plan_id,
            tenant_id=tenant_id,
            family_id=family_id,
            title=title.strip(),
            rationale=rationale.strip(),
            day_index=day_index,
        )
        async with self._session_factory() as session:
            repository = SqlAlchemyJourneyRepository(session, self._event_writer_factory(session))
            row = await repository._get_plan(plan_id, tenant_id, family_id)
            if row.status != JourneyPlanStatus.ACTIVE.value:
                raise JourneyConflictError("journey_plan_not_active")
            await repository.add_practice(practice, actor_id=actor_id)
            await session.commit()
        return {"practice": practice.as_dict(), "replayed": False}

    async def record_practice(
        self,
        *,
        tenant_id: str,
        family_id: str,
        actor_id: str,
        plan_id: str,
        practice_id: str,
        observation: str,
        blocker: str | None,
        idempotency_key: str,
    ) -> dict[str, object]:
        self._require_key(idempotency_key)
        if not observation.strip():
            raise JourneyValidationError("journey_practice_observation_invalid")
        record = PracticeRecord(
            record_id=str(uuid5(NAMESPACE_URL, f"journey-record:{practice_id}:{idempotency_key}")),
            practice_id=practice_id,
            plan_id=plan_id,
            tenant_id=tenant_id,
            family_id=family_id,
            observation=observation.strip(),
            blocker=blocker.strip() if blocker and blocker.strip() else None,
        )
        async with self._session_factory() as session:
            repository = SqlAlchemyJourneyRepository(session, self._event_writer_factory(session))
            row = await repository._get_plan(plan_id, tenant_id, family_id)
            if row.status != JourneyPlanStatus.ACTIVE.value:
                raise JourneyConflictError("journey_plan_not_active")
            await repository.record_practice(record, actor_id=actor_id)
            await session.commit()
        return {"record": record.as_dict(), "replayed": False}

    async def read_plan(self, *, plan_id: str, tenant_id: str, family_id: str) -> dict[str, object]:
        async with self._session_factory() as session:
            repository = SqlAlchemyJourneyRepository(session, self._event_writer_factory(session))
            return await repository.read_plan(
                plan_id=plan_id, tenant_id=tenant_id, family_id=family_id
            )

    @staticmethod
    def _require_key(key: str) -> None:
        if not key.strip():
            raise JourneyValidationError("journey_idempotency_key_required")
