"""PostgreSQL adapter for `FamilyExperienceSignalRepository`.

Schema is created by
``database/migrations/versions/0064_family_experience_signals.py`` (single
``family_experience_signals`` table). One repository instance owns one
``AsyncConnection``, mirroring
``improvement_candidate_postgres_repository.py``.

No tenant/family column exists on this table by design — see
`domain/family_experience_signal.py`'s privacy invariant.

`summarize_by_component` does the helped/partially-helped/did-not-help
tally and rate calculation as a real SQL `GROUP BY` + conditional `sum`,
not by pulling every row into Python — this is the query behind the
"search a similar problem" experience, and it should scale with the
database, not with how many rows fit in a Python list.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..application.family_experience_signal import ComponentExperienceSummary
from ..domain.family_experience_signal import FamilyExperienceSignal, NeedCategoryLabel


def _signal_from_row(row) -> FamilyExperienceSignal:
    return FamilyExperienceSignal(
        signal_id=row["signal_id"],
        component_id=row["component_id"],
        component_shape=row["component_shape"],
        decision=row["decision"],
        category=row["category"],
        intervention_tier=row["intervention_tier"],
        recorded_at=row["recorded_at"],
    )


class SqlAlchemyFamilyExperienceSignalRepository:
    """Drop-in replacement for `InMemoryFamilyExperienceSignalRepository`
    behind the same `FamilyExperienceSignalRepository` protocol."""

    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    async def save_family_experience_signal(self, signal: FamilyExperienceSignal) -> None:
        await self._connection.execute(
            text(
                """
                insert into family_experience_signals(
                  signal_id, component_id, component_shape, decision, category,
                  intervention_tier, recorded_at
                ) values (
                  :signal_id, :component_id, :component_shape, :decision, :category,
                  :intervention_tier, :recorded_at
                )
                on conflict (signal_id) do nothing
                """
            ),
            {
                "signal_id": signal.signal_id,
                "component_id": signal.component_id,
                "component_shape": signal.component_shape,
                "decision": signal.decision,
                "category": signal.category,
                "intervention_tier": signal.intervention_tier,
                "recorded_at": signal.recorded_at,
            },
        )

    async def list_family_experience_signals(self) -> tuple[FamilyExperienceSignal, ...]:
        result = await self._connection.execute(
            text(
                """
                select * from family_experience_signals
                order by recorded_at desc
                """
            )
        )
        return tuple(_signal_from_row(row) for row in result.mappings().all())

    async def summarize_by_component(
        self, *, category: NeedCategoryLabel
    ) -> tuple[ComponentExperienceSummary, ...]:
        result = await self._connection.execute(
            text(
                """
                select
                  component_id,
                  sum(case when decision = 'HELPED' then 1 else 0 end) as helped_count,
                  sum(case when decision = 'PARTIALLY_HELPED' then 1 else 0 end)
                    as partially_helped_count,
                  sum(case when decision = 'DID_NOT_HELP' then 1 else 0 end)
                    as did_not_help_count,
                  count(*) as total_count
                from family_experience_signals
                where category = :category
                group by component_id
                order by total_count desc
                """
            ),
            {"category": category},
        )
        summaries = []
        for row in result.mappings().all():
            total = row["total_count"]
            helped = row["helped_count"]
            summaries.append(
                ComponentExperienceSummary(
                    component_id=row["component_id"],
                    category=category,
                    helped_count=helped,
                    partially_helped_count=row["partially_helped_count"],
                    did_not_help_count=row["did_not_help_count"],
                    total_count=total,
                    helped_rate=(helped / total) if total > 0 else 0.0,
                )
            )
        return tuple(summaries)


__all__ = ["SqlAlchemyFamilyExperienceSignalRepository"]
