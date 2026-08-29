"""Read-only query port for the Product Zone (Three-Zone Strategy Engine)
portfolio view — `zone_queries.py` (this Agent's file). CQRS-style split from
`zone_ports.py` (Agent B's write-side `ZoneAssessmentRepositoryPort`),
deliberately NOT extending or reusing that Protocol:

- `zone_ports.py` is explicitly Agent B's file ownership per the PR-002 task
  split (its own module docstring: "Implemented by `infrastructure/`
  (Agent C's file ownership)"). This Agent's task brief is scoped to new
  files only ("不要去改Agent B的文件") — adding a list-method to that
  Protocol would mean editing a file this Agent does not own, and would also
  force every existing implementer of `ZoneAssessmentRepositoryPort`
  (Agent C's `FakeZoneAssessmentRepository` / SQLAlchemy repository, plus
  Agent B's own test-local Fake in `test_zone_review_governance.py`) to grow
  a new method just to keep satisfying the Protocol's structural typing —
  unnecessary coupling for a read-only, portfolio-reporting concern that has
  nothing to do with the single-assessment load/save lifecycle.
- Portfolio reporting is a distinct read-model concern (fan-out over *all*
  of a tenant's assessments) from the write-side's per-id
  load/save/transition operations. Keeping it as its own minimal Protocol
  means an infrastructure adapter can implement just this one method
  (e.g. wrapping Agent C's `FakeZoneAssessmentRepository._assessments` dict,
  or a SQL `SELECT ... WHERE tenant_scope = ...` in a future PR) without
  having to also implement the write-side contract, and vice versa.

No FastAPI/SQLAlchemy dependency here, same four-layer rule as the rest of
this domain's `application/*_ports.py` modules.
"""
from __future__ import annotations

from typing import Protocol

from ..domain.zone_entities import ProductZoneAssessment


class ZonePortfolioQueryPort(Protocol):
    async def list_zone_assessments(self, tenant_scope: str) -> list[ProductZoneAssessment]:
        """Returns every `ProductZoneAssessment` belonging to `tenant_scope`,
        in any order (`zone_queries.py` does not assume/require a particular
        ordering from the port — sort there if a caller ever needs one).

        Tenant isolation is this method's responsibility, same rule as every
        `load_*`/`list_*` elsewhere in this domain (PR-001R item 3): an
        implementation must never return another tenant's assessments here,
        and — unlike `load_zone_assessment`'s "wrong id vs. wrong tenant"
        ambiguity requirement — there is no id-guessing risk to hide for a
        list method, so a tenant with zero assessments simply gets `[]`,
        not an error.
        """
        ...
