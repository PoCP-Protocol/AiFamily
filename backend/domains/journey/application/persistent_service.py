"""Async application facade for the persisted Journey MVP scenario.

The HTTP composition root can inject this facade in place of the in-memory
candidate.  It owns request transactions, while the repository owns SQL
mapping.  No method commits until the domain write and the injected canonical
event writer have both succeeded.
"""

from __future__ import annotations

from collections.abc import Callable
from hashlib import sha256
from json import dumps
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
    PhaseReview,
    PhaseReviewDecision,
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
            key = self._scoped_key(
                intent.tenant_id, intent.family_id, "create_plan", idempotency_key
            )
            replay = await repository.begin_idempotency(
                key=key,
                action="JOURNEY_MVP.create_plan",
                request_hash=self._request_hash(
                    {
                        "intent_id": intent.intent_id,
                        "tenant_id": intent.tenant_id,
                        "family_id": intent.family_id,
                        "actor_id": intent.actor_id,
                        "need_type": intent.need_type,
                        "goal_text": intent.goal_text,
                        "evidence_refs": intent.evidence_refs,
                        "knowledge_refs": intent.knowledge_refs,
                        "boundary": intent.boundary,
                    }
                ),
            )
            if replay is not None:
                return replay
            await repository.create_plan(plan)
            result = {"plan": plan.as_dict(), "created": True, "replayed": False}
            await repository.complete_idempotency(key=key, response=result)
            await session.commit()
        return result

    async def confirm_plan(
        self, *, tenant_id: str, family_id: str, actor_id: str, plan_id: str, idempotency_key: str
    ) -> dict[str, object]:
        self._require_key(idempotency_key)
        async with self._session_factory() as session:
            repository = SqlAlchemyJourneyRepository(session, self._event_writer_factory(session))
            key = self._scoped_key(tenant_id, family_id, "confirm_plan", idempotency_key)
            replay = await repository.begin_idempotency(
                key=key,
                action="JOURNEY_MVP.confirm_plan",
                request_hash=self._request_hash({"plan_id": plan_id, "actor_id": actor_id}),
            )
            if replay is not None:
                return replay
            await repository.confirm_plan(
                plan_id=plan_id, actor_id=actor_id, tenant_id=tenant_id, family_id=family_id
            )
            result = await repository.read_plan(
                plan_id=plan_id, tenant_id=tenant_id, family_id=family_id
            )
            response = {"plan": result["plan"], "replayed": False}
            await repository.complete_idempotency(key=key, response=response)
            await session.commit()
        return response

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
            key = self._scoped_key(tenant_id, family_id, "add_practice", idempotency_key)
            replay = await repository.begin_idempotency(
                key=key,
                action="JOURNEY_MVP.add_practice",
                request_hash=self._request_hash(
                    {
                        "plan_id": plan_id,
                        "title": title,
                        "rationale": rationale,
                        "day_index": day_index,
                    }
                ),
            )
            if replay is not None:
                return replay
            row = await repository._get_plan(plan_id, tenant_id, family_id)
            if row.status != JourneyPlanStatus.ACTIVE.value:
                raise JourneyConflictError("journey_plan_not_active")
            await repository.add_practice(practice, actor_id=actor_id)
            result = {"practice": practice.as_dict(), "replayed": False}
            await repository.complete_idempotency(key=key, response=result)
            await session.commit()
        return result

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
            key = self._scoped_key(tenant_id, family_id, "record_practice", idempotency_key)
            replay = await repository.begin_idempotency(
                key=key,
                action="JOURNEY_MVP.record_practice",
                request_hash=self._request_hash(
                    {
                        "plan_id": plan_id,
                        "practice_id": practice_id,
                        "observation": observation,
                        "blocker": blocker,
                    }
                ),
            )
            if replay is not None:
                return replay
            row = await repository._get_plan(plan_id, tenant_id, family_id)
            if row.status != JourneyPlanStatus.ACTIVE.value:
                raise JourneyConflictError("journey_plan_not_active")
            await repository.record_practice(record, actor_id=actor_id)
            result = {"record": record.as_dict(), "replayed": False}
            await repository.complete_idempotency(key=key, response=result)
            await session.commit()
        return result

    async def read_plan(self, *, plan_id: str, tenant_id: str, family_id: str) -> dict[str, object]:
        async with self._session_factory() as session:
            repository = SqlAlchemyJourneyRepository(session, self._event_writer_factory(session))
            return await repository.read_plan(
                plan_id=plan_id, tenant_id=tenant_id, family_id=family_id
            )

    async def review_phase(
        self,
        *,
        tenant_id: str,
        family_id: str,
        actor_id: str,
        plan_id: str,
        decision: PhaseReviewDecision,
        observation: str,
        idempotency_key: str,
    ) -> dict[str, object]:
        self._require_key(idempotency_key)
        if not observation.strip() or len(observation) > 2000:
            raise JourneyValidationError("journey_observation_invalid")
        review = PhaseReview(
            review_id=str(uuid5(NAMESPACE_URL, f"journey-review:{plan_id}:{idempotency_key}")),
            plan_id=plan_id,
            tenant_id=tenant_id,
            family_id=family_id,
            decision=decision,
            observation=observation.strip(),
        )
        async with self._session_factory() as session:
            repository = SqlAlchemyJourneyRepository(session, self._event_writer_factory(session))
            key = self._scoped_key(tenant_id, family_id, "review_phase", idempotency_key)
            replay = await repository.begin_idempotency(
                key=key,
                action="JOURNEY_MVP.review_phase",
                request_hash=self._request_hash(
                    {
                        "plan_id": plan_id,
                        "decision": decision.value,
                        "observation": observation,
                    }
                ),
            )
            if replay is not None:
                return replay
            row = await repository._get_plan(plan_id, tenant_id, family_id)
            if row.status != JourneyPlanStatus.ACTIVE.value:
                raise JourneyConflictError("journey_plan_not_active")
            await repository.review_phase(review, actor_id=actor_id)
            result = await repository.read_plan(
                plan_id=plan_id, tenant_id=tenant_id, family_id=family_id
            )
            response = {"plan": result["plan"], "review": review.as_dict(), "replayed": False}
            await repository.complete_idempotency(key=key, response=response)
            await session.commit()
        return response

    @staticmethod
    def _scoped_key(tenant_id: str, family_id: str, action: str, raw_key: str) -> str:
        return sha256(f"{tenant_id}:{family_id}:{action}:{raw_key}".encode()).hexdigest()

    @staticmethod
    def _request_hash(payload: object) -> str:
        return sha256(
            dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
        ).hexdigest()

    @staticmethod
    def _require_key(key: str) -> None:
        if not key.strip():
            raise JourneyValidationError("journey_idempotency_key_required")
