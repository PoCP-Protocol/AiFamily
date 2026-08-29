"""Ports (interfaces) the application layer depends on — implemented by
`infrastructure/`. Domain code never imports SQLAlchemy/FastAPI directly;
it depends on these Protocols instead, per the four-layer rule in
`architecture/FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` section 3.

No TS/Nest service to mirror method-for-method (new domain) — method set is
the minimum needed to load/save the two entities in `domain/entities.py`,
reverse-derived from the `packages/contracts/product_strategy.py` schemas.
"""
from __future__ import annotations

from typing import Protocol

from ..domain.entities import GrowthProblem, Opportunity


class ProductStrategyRepositoryPort(Protocol):
    async def load_growth_problem(self, problem_id: str) -> GrowthProblem: ...

    async def save_growth_problem(self, problem: GrowthProblem) -> None: ...

    async def load_opportunity(self, opportunity_id: str) -> Opportunity: ...

    async def save_opportunity(self, opportunity: Opportunity) -> None: ...

    async def list_opportunities_by_problem(self, problem_id: str) -> list[Opportunity]: ...
