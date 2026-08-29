"""In-memory fake repository — no real SQLAlchemy implementation exists yet.

Mirrors `domains/assessment/infrastructure/fake_repository.py`'s role (the
FakeProvider test double required by
`architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` section 9), but
deliberately stops here: unlike the assessment domain, this skeleton does not
add a `sqlalchemy_repository.py` yet. Batch 2's own repositories are
currently Fake-only too (no real PG integration tests — a known,
project-owner-accepted gap per Override #4), so this skeleton matches that
same stage rather than pretending to be further along.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from ..domain.entities import GrowthProblem, Opportunity
from ..domain.errors import ProductStrategyNotFoundError


@dataclass
class FakeProductStrategyRepository:
    _problems: dict[str, GrowthProblem] = field(default_factory=dict)
    _opportunities: dict[str, Opportunity] = field(default_factory=dict)

    async def load_growth_problem(self, problem_id: str) -> GrowthProblem:
        try:
            return self._problems[problem_id]
        except KeyError:
            raise ProductStrategyNotFoundError("growth_problem_not_found") from None

    async def save_growth_problem(self, problem: GrowthProblem) -> None:
        self._problems[problem.problem_id] = problem

    async def load_opportunity(self, opportunity_id: str) -> Opportunity:
        try:
            return self._opportunities[opportunity_id]
        except KeyError:
            raise ProductStrategyNotFoundError("opportunity_not_found") from None

    async def save_opportunity(self, opportunity: Opportunity) -> None:
        self._opportunities[opportunity.opportunity_id] = opportunity

    async def list_opportunities_by_problem(self, problem_id: str) -> list[Opportunity]:
        return [o for o in self._opportunities.values() if o.problem_id == problem_id]
