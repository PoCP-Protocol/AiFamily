"""Fail-closed PostgreSQL policy adapter for Journey operations.

Legacy consent rows do not yet carry the age/relation/expiry fields required to
construct platform ``ConsentGrant`` values. Until that schema gap is closed we
query current grants directly, without caching, and require all three purposes.
This is deliberately narrower than claiming full ConsentGate integration.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.errors import JourneyForbiddenError, JourneyNotFoundError

_REQUIRED_CONSENTS = {"SERVICE", "ASSESSMENT", "GROWTH_TRACKING"}


class SqlAlchemyJourneyPolicy:
    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    async def assert_can_read(self, family_id: str, actor_id: str) -> None:
        await self._assert_family_manage_permission(family_id, actor_id)

    async def assert_can_manage(self, family_id: str, actor_id: str) -> None:
        await self._assert_family_manage_permission(family_id, actor_id)

    async def assert_creation_preconditions(
        self, family_id: str, onboarding_id: str, actor_id: str
    ) -> None:
        await self._assert_family_manage_permission(family_id, actor_id)
        subject_id = await self._resolve_subject(family_id, onboarding_id)
        await self._assert_required_consents(family_id, subject_id)
        await self._assert_normal_safety_route(family_id, onboarding_id)
        await self._assert_no_active_intervention(family_id, onboarding_id, subject_id)

    async def _assert_family_manage_permission(self, family_id: str, actor_id: str) -> None:
        result = await self._connection.execute(
            text(
                """
                select 1 where exists (
                  select 1 from audit_logs
                  where family_id=:family_id and actor_id=:actor_id
                    and action_name='CreateFamily' and result='SUCCESS'
                ) or exists (
                  select 1 from family_memberships
                  where family_id=:family_id and person_id::text=:actor_id
                    and status='ACTIVE' and role in ('OWNER_GUARDIAN','GUARDIAN')
                )
                """
            ),
            {"family_id": family_id, "actor_id": actor_id},
        )
        if result.first() is None:
            raise JourneyForbiddenError("actor_has_family_manage_permission")

    async def _resolve_subject(self, family_id: str, onboarding_id: str) -> str:
        result = await self._connection.execute(
            text(
                """
                select subject_person_id from growth_priorities
                where family_id=:family_id and onboarding_id=:onboarding_id
                  and status='ACTIVE' and subject_person_id is not null
                union all
                select gp.subject_person_id from growth_profiles gp
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
                order by subject_person_id limit 1
                """
            ),
            {"family_id": family_id, "onboarding_id": onboarding_id},
        )
        row = result.first()
        if row is None:
            raise JourneyNotFoundError("growth_subject_unresolved")
        return str(row.subject_person_id)

    async def _assert_required_consents(self, family_id: str, subject_id: str) -> None:
        result = await self._connection.execute(
            text(
                """
                select purpose::text as purpose from consents
                where family_id=:family_id and subject_person_id=:subject_id
                  and purpose in ('SERVICE','ASSESSMENT','GROWTH_TRACKING')
                  and status='GRANTED'
                """
            ),
            {"family_id": family_id, "subject_id": subject_id},
        )
        granted = {row.purpose for row in result}
        missing = sorted(_REQUIRED_CONSENTS - granted)
        if missing:
            raise JourneyForbiddenError(f"missing_required_consent:{','.join(missing)}")

    async def _assert_normal_safety_route(self, family_id: str, onboarding_id: str) -> None:
        result = await self._connection.execute(
            text(
                """
                select payload->'safety_disposition'->>'severity' as severity,
                       payload->'safety_disposition'->>'disposition' as disposition
                from growth_events
                where family_id=:family_id and event_type='GrowthOnboardingStarted'
                  and payload->>'onboarding_id'=:onboarding_id
                order by occurred_at desc limit 1
                """
            ),
            {"family_id": family_id, "onboarding_id": onboarding_id},
        )
        row = result.first()
        if row is None or row.severity != "LOW" or row.disposition != "NORMAL":
            raise JourneyForbiddenError("normal_safety_route_not_verified")
        non_normal = await self._connection.execute(
            text(
                """
                select 1 from perspectives
                where family_id=:family_id and onboarding_id=:onboarding_id and (
                  safety_disposition='{}'::jsonb
                  or safety_disposition->>'disposition'<>'NORMAL'
                  or safety_disposition->>'severity'<>'LOW'
                ) limit 1
                """
            ),
            {"family_id": family_id, "onboarding_id": onboarding_id},
        )
        if non_normal.first() is not None:
            raise JourneyForbiddenError("normal_safety_route_not_verified")

    async def _assert_no_active_intervention(
        self, family_id: str, onboarding_id: str, subject_id: str
    ) -> None:
        result = await self._connection.execute(
            text(
                """
                select 1 from intervention_episodes
                where family_id=:family_id and onboarding_id=:onboarding_id
                  and subject_person_id=:subject_id and status='ACTIVE'
                limit 1
                """
            ),
            {
                "family_id": family_id,
                "onboarding_id": onboarding_id,
                "subject_id": subject_id,
            },
        )
        if result.first() is not None:
            raise JourneyForbiddenError("active_intervention_episode_exists")
