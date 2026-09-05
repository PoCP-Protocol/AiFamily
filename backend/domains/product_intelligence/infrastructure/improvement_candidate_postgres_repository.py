"""PostgreSQL adapter for `ImprovementCandidateRepository`.

Schema is created by
``database/migrations/versions/0060_product_improvement_candidates.py``
(single ``product_improvement_candidates`` table). One repository instance
owns one ``AsyncConnection``, mirroring
``backend/domains/product_intelligence/infrastructure/
course_content_postgres_repository.py``.

No tenant/family column exists on this table by design — see
`domain/improvement_candidate.py`'s privacy invariant.
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection

from ..domain.improvement_candidate import ImprovementCandidate


def _candidate_from_row(row) -> ImprovementCandidate:
    return ImprovementCandidate(
        candidate_id=row["candidate_id"],
        component_id=row["component_id"],
        component_shape=row["component_shape"],
        decision=row["decision"],
        category=row["category"],
        intervention_tier=row["intervention_tier"],
        recorded_at=row["recorded_at"],
    )


class SqlAlchemyImprovementCandidateRepository:
    """Drop-in replacement for `InMemoryImprovementCandidateRepository`
    behind the same `ImprovementCandidateRepository` protocol."""

    def __init__(self, connection: AsyncConnection):
        self._connection = connection

    async def save_improvement_candidate(self, candidate: ImprovementCandidate) -> None:
        await self._connection.execute(
            text(
                """
                insert into product_improvement_candidates(
                  candidate_id, component_id, component_shape, decision, category,
                  intervention_tier, recorded_at
                ) values (
                  :candidate_id, :component_id, :component_shape, :decision, :category,
                  :intervention_tier, :recorded_at
                )
                on conflict (candidate_id) do nothing
                """
            ),
            {
                "candidate_id": candidate.candidate_id,
                "component_id": candidate.component_id,
                "component_shape": candidate.component_shape,
                "decision": candidate.decision,
                "category": candidate.category,
                "intervention_tier": candidate.intervention_tier,
                "recorded_at": candidate.recorded_at,
            },
        )

    async def list_improvement_candidates(self) -> tuple[ImprovementCandidate, ...]:
        result = await self._connection.execute(
            text(
                """
                select * from product_improvement_candidates
                order by recorded_at desc
                """
            )
        )
        return tuple(_candidate_from_row(row) for row in result.mappings().all())


__all__ = ["SqlAlchemyImprovementCandidateRepository"]
