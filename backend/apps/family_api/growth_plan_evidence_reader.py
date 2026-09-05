"""Fail-closed SQL evidence reader for the governed UI-05 plan draft."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Mapping
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from backend.apps.family_api.growth_plan_ai_wiring import (
    CONFIRMED_INTENT_BOUNDARY,
    GrowthPlanEvidence,
)
from backend.intelligence.context_engine.contracts import ContextScope, DataClass

PRIORITY_BOUNDARY = "PRIORITY_IS_HUMAN_CONFIRMED_PRACTICE_FOCUS"
GROWTH_JOURNEY_TYPE = "PARENT_CHILD_COMMUNICATION_CONFLICT"
_ALLOWED_DIMENSIONS = frozenset({"P03", "R03", "R04", "R05"})


class GrowthPlanEvidenceNotFoundError(LookupError):
    """The requested evidence is not visible in the trusted scope."""


class GrowthPlanEvidenceForbiddenError(PermissionError):
    """The current actor or lifecycle envelope cannot read the evidence."""


class GrowthPlanEvidenceConflictError(RuntimeError):
    """Canonical rows disagree or violate their reviewed invariants."""


ActorIdResolver = Callable[[], str]


@dataclass(frozen=True, slots=True)
class SqlAlchemyGrowthPlanEvidenceReader:
    """Resolve the complete evidence bundle from one trusted onboarding id.

    Intent, priority and subject identities are never accepted from a request.
    One SQL statement gives the read a single database snapshot and deliberately
    has no ``LIMIT 1`` fallback: zero rows are invisible and duplicates are an
    integrity conflict.
    """

    session_factory: async_sessionmaker[AsyncSession]
    actor_id_resolver: ActorIdResolver

    def __post_init__(self) -> None:
        if not isinstance(self.session_factory, async_sessionmaker):
            raise TypeError("growth plan evidence reader requires async_sessionmaker")
        if not callable(self.actor_id_resolver):
            raise TypeError("growth plan evidence actor resolver must be callable")

    async def load(self, *, scope: ContextScope, onboarding_id: str) -> GrowthPlanEvidence:
        _assert_read_scope(scope)
        if not isinstance(onboarding_id, str) or not onboarding_id.strip():
            raise ValueError("growth plan onboarding id is required")
        actor_id = self.actor_id_resolver()
        if inspect.isawaitable(actor_id):
            actor_id = await actor_id
        if not isinstance(actor_id, str) or not actor_id.strip():
            raise GrowthPlanEvidenceForbiddenError("AUTHENTICATED_GUARDIAN_REQUIRED")

        async with self.session_factory() as session:
            result = await session.execute(
                text(_EVIDENCE_SQL),
                {
                    "tenant_id": scope.tenant_id,
                    "family_id": scope.family_id,
                    "subject_person_id": scope.subject_ids[0],
                    "onboarding_id": onboarding_id,
                    "actor_id": actor_id,
                    "intent_boundary": CONFIRMED_INTENT_BOUNDARY,
                    "priority_boundary": PRIORITY_BOUNDARY,
                    "journey_type": GROWTH_JOURNEY_TYPE,
                },
            )
            rows = result.mappings().all()
        if not rows:
            raise GrowthPlanEvidenceNotFoundError("GROWTH_PLAN_EVIDENCE_NOT_VISIBLE")
        if len(rows) != 1:
            raise GrowthPlanEvidenceConflictError("GROWTH_PLAN_EVIDENCE_NOT_UNIQUE")
        return _map_evidence(rows[0])


def _assert_read_scope(scope: ContextScope) -> None:
    scope.assert_active()
    if scope.subject_id is None:
        raise GrowthPlanEvidenceForbiddenError("SINGLE_GROWTH_PLAN_SUBJECT_REQUIRED")
    if scope.purpose.lower() != "growth_tracking":
        raise GrowthPlanEvidenceForbiddenError("GROWTH_TRACKING_SCOPE_REQUIRED")
    if scope.data_class is not DataClass.MINOR_PERSONAL_DATA:
        raise GrowthPlanEvidenceForbiddenError("MINOR_PERSONAL_DATA_SCOPE_REQUIRED")


def _map_evidence(row: Mapping[str, object]) -> GrowthPlanEvidence:
    dimension_id = str(row["dimension_id"])
    if dimension_id not in _ALLOWED_DIMENSIONS:
        raise GrowthPlanEvidenceConflictError("GROWTH_PRIORITY_DIMENSION_INVALID")
    capabilities = tuple(str(value) for value in (row["required_capability_keys"] or ()))
    try:
        return GrowthPlanEvidence(
            intent_id=str(row["intent_id"]),
            onboarding_id=str(row["onboarding_id"]),
            priority_id=str(row["priority_id"]),
            subject_person_id=str(row["subject_person_id"]),
            need_type=str(row["need_type"]),
            goal_text=str(row["goal_text"]),
            required_capability_keys=capabilities,
            dimension_id=dimension_id,
            confirmed_by_actor_id=str(row["intent_confirmed_by"]),
            confirmed_at=row["intent_confirmed_at"],  # type: ignore[arg-type]
            priority_confirmed_by_actor_id=str(row["priority_confirmed_by"]),
            priority_confirmed_at=row["priority_confirmed_at"],  # type: ignore[arg-type]
            onboarding_version=int(row["onboarding_version"]),
            priority_policy_version=str(row["priority_policy_version"]),
            boundary=str(row["intent_boundary"]),
        )
    except (KeyError, TypeError, ValueError, PermissionError) as exc:
        raise GrowthPlanEvidenceConflictError("GROWTH_PLAN_EVIDENCE_INVALID") from exc


_EVIDENCE_SQL = """
select b.intent_id,
       b.onboarding_id,
       b.subject_person_id,
       gi.need_type,
       gi.goal_text,
       gi.required_capability_keys,
       gi.confirmed_by as intent_confirmed_by,
       gi.confirmed_at as intent_confirmed_at,
       gi.boundary as intent_boundary,
       j.version as onboarding_version,
       gp.priority_id,
       gp.dimension_id,
       gp.policy_version as priority_policy_version,
       gp.confirmed_by_actor_id as priority_confirmed_by,
       gp.confirmed_at as priority_confirmed_at
from growth_onboarding_intent_bindings b
join tenant_family_bindings tfb
  on tfb.tenant_family_binding_id=b.tenant_family_binding_id
 and tfb.tenant_id=b.tenant_id
 and tfb.family_id=b.family_id
join growth_journeys j
  on j.family_id=b.family_id and j.journey_id=b.onboarding_id
join growth_intents gi
  on gi.family_id=b.family_id and gi.intent_id=b.intent_id
 and gi.subject_person_id=b.subject_person_id
join growth_priorities gp
  on gp.family_id=b.family_id and gp.onboarding_id=b.onboarding_id
 and gp.subject_person_id=b.subject_person_id
join family_memberships subject_membership
  on subject_membership.family_id=b.family_id
 and subject_membership.person_id=b.subject_person_id
 and subject_membership.status='ACTIVE'
join family_memberships actor_membership
  on actor_membership.family_id=b.family_id
 and actor_membership.person_id::text=:actor_id
 and actor_membership.status='ACTIVE'
 and actor_membership.role in ('OWNER_GUARDIAN','GUARDIAN')
where b.tenant_id=cast(:tenant_id as uuid)
  and b.family_id=cast(:family_id as uuid)
  and b.onboarding_id=cast(:onboarding_id as uuid)
  and b.subject_person_id=cast(:subject_person_id as uuid)
  and tfb.status='ACTIVE'
  and tfb.effective_from<=CURRENT_TIMESTAMP
  and (tfb.effective_to is null or tfb.effective_to>CURRENT_TIMESTAMP)
  and j.journey_type=:journey_type
  and j.phase='ONBOARDING'
  and j.status='ACTIVE'
  and j.version>=1
  and gi.status='OPEN'
  and gi.confirmed_by is not null
  and gi.confirmed_at is not null
  and gi.boundary=:intent_boundary
  and cardinality(gi.required_capability_keys)>0
  and gp.status='ACTIVE'
  and gp.boundary=:priority_boundary
  and gp.policy_version is not null
  and gp.confirmed_by_actor_id is not null
  and gp.confirmed_at is not null
  and gp.version>=1
"""


__all__ = [
    "GrowthPlanEvidenceConflictError",
    "GrowthPlanEvidenceForbiddenError",
    "GrowthPlanEvidenceNotFoundError",
    "SqlAlchemyGrowthPlanEvidenceReader",
]
