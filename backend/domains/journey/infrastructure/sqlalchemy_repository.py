"""SQLAlchemy persistence for the Journey MVP scenario.

The adapter stores the same business objects as the in-memory candidate.  It
does not commit: callers own the transaction and provide the canonical event
writer.  Consequently a domain write and its audit/outbox event either commit
together or both roll back.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from json import dumps
from typing import Any
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Integer, String, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from ..application.plan_service import (
    FamilyPractice,
    JourneyPlan,
    JourneyPlanStatus,
    PracticeRecord,
    PracticeStatus,
)


class JourneyBase(DeclarativeBase):
    pass


class JourneyPlanRow(JourneyBase):
    __tablename__ = "family_mvp_journey_plans"

    plan_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    actor_id: Mapped[str] = mapped_column(String(128), nullable=False)
    intent_id: Mapped[str | None] = mapped_column(String(128), nullable=True, unique=True)
    focus_id: Mapped[str] = mapped_column(String(128), nullable=False)
    goal_text: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    current_phase: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    review_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evidence_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    knowledge_refs: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=lambda: datetime.now(UTC)
    )


class JourneyPracticeRow(JourneyBase):
    __tablename__ = "family_mvp_journey_practices"

    practice_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    plan_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    rationale: Mapped[str] = mapped_column(String(1000), nullable=False)
    day_index: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)


class JourneyPracticeRecordRow(JourneyBase):
    __tablename__ = "family_mvp_journey_practice_records"

    record_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    practice_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    plan_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(128), nullable=False)
    family_id: Mapped[str] = mapped_column(String(128), nullable=False)
    observation: Mapped[str] = mapped_column(String(2000), nullable=False)
    blocker: Mapped[str | None] = mapped_column(String(500), nullable=True)


EventWriter = Callable[[str, str, str, str, str], Any]


def canonical_event_writer(session: AsyncSession) -> EventWriter:
    """Build a writer for the platform's existing audit and outbox tables.

    The returned callable deliberately does not commit.  It is intended to be
    passed to :class:`SqlAlchemyJourneyRepository` while the caller owns one
    transaction, so a missing audit or outbox row rolls the Journey mutation
    back with it.  `audit_logs` and `outbox_events` are platform tables from
    the baseline; this function does not create a Journey-specific event
    ledger.
    """

    async def write_event(
        action: str, resource_id: str, actor_id: str, tenant_id: str, family_id: str
    ) -> None:
        correlation_id = str(uuid4())
        payload = {
            "tenant_id": tenant_id,
            "family_id": family_id,
            "resource_id": resource_id,
            "action": action,
        }
        await session.execute(
            text(
                """
                INSERT INTO audit_logs
                    (family_id, actor_type, actor_id, action_name, resource_type,
                     resource_id, correlation_id, idempotency_key, result, metadata)
                VALUES
                    (:family_id, 'PERSON', :actor_id, :action, 'JOURNEY_MVP',
                     :resource_id, :correlation_id, :resource_id, 'SUCCESS',
                     CAST(:metadata AS jsonb))
                """
            ),
            {
                "family_id": family_id,
                "actor_id": actor_id,
                "action": action,
                "resource_id": resource_id,
                "correlation_id": correlation_id,
                "metadata": dumps(payload),
            },
        )
        await session.execute(
            text(
                """
                INSERT INTO outbox_events
                    (aggregate_type, aggregate_id, event_name, event_version,
                     event_id, correlation_id, payload, occurred_at)
                VALUES
                    ('JOURNEY_MVP', :resource_id, :event_name, 1, :event_id,
                     :correlation_id, CAST(:payload AS jsonb), :occurred_at)
                """
            ),
            {
                "resource_id": resource_id,
                "event_name": action,
                "event_id": str(uuid4()),
                "correlation_id": correlation_id,
                "payload": dumps(payload),
                "occurred_at": datetime.now(UTC),
            },
        )

    return write_event


class SqlAlchemyJourneyRepository:
    """Persistence adapter; all methods participate in caller's transaction."""

    def __init__(self, session: AsyncSession, event_writer: EventWriter) -> None:
        self._session = session
        self._event_writer = event_writer

    async def create_plan(self, plan: JourneyPlan) -> None:
        self._session.add(
            JourneyPlanRow(
                plan_id=plan.plan_id,
                tenant_id=plan.tenant_id,
                family_id=plan.family_id,
                actor_id=plan.actor_id,
                intent_id=plan.intent_id,
                focus_id=plan.focus_id,
                goal_text=plan.goal_text,
                status=plan.status.value,
                current_phase=plan.current_phase,
                review_count=plan.review_count,
                evidence_refs=list(plan.evidence_refs),
                knowledge_refs=list(plan.knowledge_refs),
            )
        )
        await self._event_writer(
            "PLAN_CREATED", plan.plan_id, plan.actor_id, plan.tenant_id, plan.family_id
        )

    async def confirm_plan(
        self, *, plan_id: str, actor_id: str, tenant_id: str, family_id: str
    ) -> None:
        row = await self._get_plan(plan_id, tenant_id, family_id)
        row.status = JourneyPlanStatus.ACTIVE.value
        await self._event_writer("PLAN_CONFIRMED", plan_id, actor_id, tenant_id, family_id)

    async def add_practice(self, practice: FamilyPractice, *, actor_id: str) -> None:
        self._session.add(
            JourneyPracticeRow(
                practice_id=practice.practice_id,
                plan_id=practice.plan_id,
                tenant_id=practice.tenant_id,
                family_id=practice.family_id,
                title=practice.title,
                rationale=practice.rationale,
                day_index=practice.day_index,
                status=practice.status.value,
            )
        )
        await self._event_writer(
            "PRACTICE_PLANNED",
            practice.practice_id,
            actor_id,
            practice.tenant_id,
            practice.family_id,
        )

    async def record_practice(self, record: PracticeRecord, *, actor_id: str) -> None:
        practice = await self._session.get(JourneyPracticeRow, record.practice_id)
        if practice is None or practice.plan_id != record.plan_id:
            raise LookupError("journey_practice_not_found")
        self._session.add(
            JourneyPracticeRecordRow(
                record_id=record.record_id,
                practice_id=record.practice_id,
                plan_id=record.plan_id,
                tenant_id=record.tenant_id,
                family_id=record.family_id,
                observation=record.observation,
                blocker=record.blocker,
            )
        )
        practice.status = PracticeStatus.RECORDED.value
        await self._event_writer(
            "PRACTICE_RECORDED", record.record_id, actor_id, record.tenant_id, record.family_id
        )

    async def read_plan(self, *, plan_id: str, tenant_id: str, family_id: str) -> dict[str, object]:
        row = await self._get_plan(plan_id, tenant_id, family_id)
        practices = (
            await self._session.scalars(
                select(JourneyPracticeRow).where(JourneyPracticeRow.plan_id == plan_id)
            )
        ).all()
        records = (
            await self._session.scalars(
                select(JourneyPracticeRecordRow).where(JourneyPracticeRecordRow.plan_id == plan_id)
            )
        ).all()
        plan = JourneyPlan(
            plan_id=row.plan_id,
            tenant_id=row.tenant_id,
            family_id=row.family_id,
            actor_id=row.actor_id,
            focus_id=row.focus_id,
            goal_text=row.goal_text,
            status=JourneyPlanStatus(row.status),
            current_phase=row.current_phase,
            review_count=row.review_count,
            intent_id=row.intent_id,
            evidence_refs=tuple(row.evidence_refs),
            knowledge_refs=tuple(row.knowledge_refs),
        )
        return {
            "plan": plan.as_dict(),
            "practices": [
                {
                    "practice_id": item.practice_id,
                    "plan_id": item.plan_id,
                    "title": item.title,
                    "rationale": item.rationale,
                    "day_index": item.day_index,
                    "status": item.status,
                }
                for item in practices
            ],
            "records": [
                {
                    "record_id": item.record_id,
                    "practice_id": item.practice_id,
                    "plan_id": item.plan_id,
                    "observation": item.observation,
                    "blocker": item.blocker,
                }
                for item in records
            ],
        }

    async def _get_plan(self, plan_id: str, tenant_id: str, family_id: str) -> JourneyPlanRow:
        row = await self._session.get(JourneyPlanRow, plan_id)
        if row is None:
            raise LookupError("journey_plan_not_found")
        if row.tenant_id != tenant_id or row.family_id != family_id:
            raise PermissionError("journey_plan_scope_denied")
        return row
