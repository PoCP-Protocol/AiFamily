"""PostgreSQL repository for the canonical Journey aggregate.

The schema already exists in the Alembic legacy baseline (0003, 0008 and
0038), so this adapter intentionally adds no migration and creates no tables.
One repository instance owns one AsyncConnection; its caller owns the
transaction and commits the Journey/Priority/Audit/Outbox work atomically.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.models import JourneyPhase, JourneyPlan, PhaseName, PhaseStatus, PlanStatus


class SqlAlchemyJourneyRepository:
    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    async def get_current(self, family_id: str) -> JourneyPlan | None:
        result = await self._connection.execute(
            text(
                """
                select plan_id,family_id,onboarding_id,priority_id,status,current_phase,
                       confirmed_by_actor_id,confirmed_at
                from family_journey_plans
                where family_id=:family_id and status in ('DRAFT','ACTIVE','PAUSED')
                order by updated_at desc limit 1
                """
            ),
            {"family_id": family_id},
        )
        row = result.first()
        return await self._hydrate(row) if row else None

    async def get(self, family_id: str, plan_id: str) -> JourneyPlan | None:
        result = await self._connection.execute(
            text(
                """
                select plan_id,family_id,onboarding_id,priority_id,status,current_phase,
                       confirmed_by_actor_id,confirmed_at
                from family_journey_plans
                where family_id=:family_id and plan_id=:plan_id
                """
            ),
            {"family_id": family_id, "plan_id": plan_id},
        )
        row = result.first()
        return await self._hydrate(row) if row else None

    async def save(self, plan: JourneyPlan) -> None:
        await self._connection.execute(
            text(
                """
                insert into family_journey_plans(
                  plan_id,family_id,onboarding_id,priority_id,title,status,current_phase,
                  current_day,total_days,policy_version,boundary,confirmed_by_actor_id,confirmed_at
                ) values (
                  :plan_id,:family_id,:onboarding_id,:priority_id,:title,:status,:current_phase,
                  1,90,'JOURNEY_90_DAY_V1',
                  'PLAN_IS_FAMILY_CONFIRMED_CADENCE_NOT_DIAGNOSIS_OR_OUTCOME',
                  :confirmed_by_actor_id,:confirmed_at
                )
                on conflict (plan_id) do update set
                  status=excluded.status,current_phase=excluded.current_phase,
                  confirmed_by_actor_id=coalesce(
                    family_journey_plans.confirmed_by_actor_id,excluded.confirmed_by_actor_id
                  ),
                  confirmed_at=coalesce(family_journey_plans.confirmed_at,excluded.confirmed_at),
                  updated_at=now(),version=family_journey_plans.version+1
                """
            ),
            {
                "plan_id": plan.plan_id,
                "family_id": plan.family_id,
                "onboarding_id": plan.onboarding_id,
                "priority_id": plan.priority_id,
                "title": "90天家庭共同成长计划",
                "status": plan.status.value,
                "current_phase": plan.current_phase.value,
                "confirmed_by_actor_id": plan.confirmed_by_actor_id,
                "confirmed_at": plan.confirmed_at,
            },
        )
        for index, phase in enumerate(plan.phases):
            start_day, end_day = ((1, 14), (15, 35), (36, 60), (61, 90))[index]
            await self._connection.execute(
                text(
                    """
                    insert into family_journey_plan_phases(
                      plan_id,phase,start_day,end_day,status,review_due_day
                    ) values (:plan_id,:phase,:start_day,:end_day,:status,:end_day)
                    on conflict (plan_id,phase) do update set
                      status=excluded.status,updated_at=now()
                    """
                ),
                {
                    "plan_id": plan.plan_id,
                    "phase": phase.phase.value,
                    "start_day": start_day,
                    "end_day": end_day,
                    "status": phase.status.value,
                },
            )

    async def is_active_priority(
        self, family_id: str, onboarding_id: str, priority_id: str
    ) -> bool:
        result = await self._connection.execute(
            text(
                """
                select 1 from growth_priorities
                where family_id=:family_id and onboarding_id=:onboarding_id
                  and priority_id=:priority_id and status='ACTIVE'
                """
            ),
            {
                "family_id": family_id,
                "onboarding_id": onboarding_id,
                "priority_id": priority_id,
            },
        )
        return result.first() is not None

    async def get_active_priority(
        self, family_id: str, onboarding_id: str
    ) -> tuple[str, str] | None:
        result = await self._connection.execute(
            text(
                """
                select priority_id,dimension_id from growth_priorities
                where family_id=:family_id and onboarding_id=:onboarding_id and status='ACTIVE'
                order by created_at desc limit 1
                """
            ),
            {"family_id": family_id, "onboarding_id": onboarding_id},
        )
        row = result.first()
        return (str(row.priority_id), row.dimension_id) if row else None

    async def is_active_onboarding(self, family_id: str, onboarding_id: str) -> bool:
        result = await self._connection.execute(
            text(
                """
                select 1 from growth_journeys
                where family_id=:family_id and journey_id=:onboarding_id
                  and journey_type='PARENT_CHILD_COMMUNICATION_CONFLICT'
                  and phase='ONBOARDING' and status='ACTIVE'
                """
            ),
            {"family_id": family_id, "onboarding_id": onboarding_id},
        )
        return result.first() is not None

    async def get_priority_candidate(
        self, family_id: str, onboarding_id: str
    ) -> tuple[str, str, str] | None:
        result = await self._connection.execute(
            text(
                """
                select gp.profile_id,gpd.dimension_id,gp.subject_person_id
                from growth_profiles gp
                join growth_profile_dimensions gpd on gpd.profile_id=gp.profile_id
                where gp.family_id=:family_id and gp.status='WORKING'
                  and gp.confirmed_at is not null and gp.subject_person_id is not null
                  and gpd.dimension_id='R03'
                  and exists (
                    select 1 from jsonb_array_elements_text(
                      coalesce(gp.evidence_snapshot->'evidence_ids','[]'::jsonb)
                    ) evidence_ref(value)
                    join evidence_records er on er.evidence_id::text=evidence_ref.value
                    join perspectives p on p.perspective_id=er.perspective_id
                    where p.onboarding_id=:onboarding_id
                  )
                order by gp.confirmed_at desc limit 1
                """
            ),
            {"family_id": family_id, "onboarding_id": onboarding_id},
        )
        row = result.first()
        if row is None:
            return None
        return str(row.profile_id), row.dimension_id, str(row.subject_person_id)

    async def activate_priority(
        self,
        family_id: str,
        onboarding_id: str,
        priority_id: str,
        profile_id: str,
        subject_person_id: str,
        dimension_id: str,
        actor_id: str,
    ) -> None:
        await self._connection.execute(
            text(
                """
                update growth_priorities set status='SUPERSEDED',superseded_at=now()
                where family_id=:family_id and onboarding_id=:onboarding_id and status='ACTIVE'
                """
            ),
            {"family_id": family_id, "onboarding_id": onboarding_id},
        )
        await self._connection.execute(
            text(
                """
                insert into growth_priorities(
                  priority_id,family_id,subject_person_id,onboarding_id,profile_id,
                  dimension_id,rank,confirmed_by_actor_id,status,version,boundary,
                  reason_codes,evidence_refs,policy_version
                ) values (
                  :priority_id,:family_id,:subject_person_id,:onboarding_id,:profile_id,
                  :dimension_id,1,:actor_id,'ACTIVE',1,
                  'PRIORITY_IS_HUMAN_CONFIRMED_PRACTICE_FOCUS','[]'::jsonb,'[]'::jsonb,
                  'M2_104_DETERMINISTIC_V2'
                )
                """
            ),
            {
                "priority_id": priority_id,
                "family_id": family_id,
                "subject_person_id": subject_person_id,
                "onboarding_id": onboarding_id,
                "profile_id": profile_id,
                "dimension_id": dimension_id,
                "actor_id": actor_id,
            },
        )

    async def count_completed_actions(self, family_id: str, plan_id: str) -> int:
        result = await self._connection.execute(
            text(
                """
                select count(*) from growth_actions
                where family_id=:family_id and journey_plan_id=:plan_id
                  and status='COMPLETED'
                """
            ),
            {"family_id": family_id, "plan_id": plan_id},
        )
        return int(result.scalar_one())

    async def _hydrate(self, row) -> JourneyPlan:
        result = await self._connection.execute(
            text(
                """
                select phase,status from family_journey_plan_phases
                where plan_id=:plan_id order by start_day
                """
            ),
            {"plan_id": row.plan_id},
        )
        phases = tuple(
            JourneyPhase(PhaseName(item.phase), PhaseStatus(item.status)) for item in result
        )
        return JourneyPlan(
            plan_id=str(row.plan_id),
            family_id=str(row.family_id),
            onboarding_id=str(row.onboarding_id),
            priority_id=str(row.priority_id),
            status=PlanStatus(row.status),
            current_phase=PhaseName(row.current_phase),
            phases=phases,
            confirmed_by_actor_id=row.confirmed_by_actor_id,
            confirmed_at=row.confirmed_at,
        )
