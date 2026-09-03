"""Operator query surface for `ImprovementCandidate`: cross-family,
de-identified "this component did not help" signals.

No family/tenant scoping applies here (see
`domain/improvement_candidate.py`'s privacy invariant) — this is why the
route intentionally does not depend on `family_need`'s `FamilyNeedActor` or
any other family-scoped auth dependency. It is an internal
product/content-team query, not a family-facing endpoint, so it is kept as
simple as `course_routes.py`'s own module-level `configure_*` wiring rather
than adding a new authorization layer this PR's scope does not call for.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..application.improvement_candidate import (
    ImprovementCandidateRepository,
    list_improvement_candidates,
)

router = APIRouter(
    prefix="/product-intelligence/improvement-candidates",
    tags=["product-intelligence-improvement-candidates"],
)

_repository: ImprovementCandidateRepository | None = None


def configure_improvement_candidate_repository(
    repository: ImprovementCandidateRepository | None,
) -> None:
    global _repository
    _repository = repository


def clear_improvement_candidate_wiring() -> None:
    configure_improvement_candidate_repository(None)


def _require_repository() -> ImprovementCandidateRepository:
    if _repository is None:
        raise HTTPException(status_code=503, detail="improvement_candidate_repository_not_wired")
    return _repository


@router.get("")
async def list_product_improvement_candidates() -> dict:
    """List every de-identified "did not help" signal recorded so far.

    Deliberately returns only `component_id`/`component_shape`/`decision`/
    `category`/`intervention_tier`/`recorded_at` per candidate — no
    family/tenant/child field exists on this aggregate to leak (see
    `domain/improvement_candidate.py`).
    """

    repo = _require_repository()
    candidates = await list_improvement_candidates(repo)
    return {
        "action": "LIST_PRODUCT_IMPROVEMENT_CANDIDATES",
        "boundary": "CROSS_FAMILY_DEIDENTIFIED_SIGNAL_NOT_A_FAMILY_RECORD",
        "candidates": [
            {
                "candidate_id": candidate.candidate_id,
                "component_id": candidate.component_id,
                "component_shape": candidate.component_shape,
                "decision": candidate.decision,
                "category": candidate.category,
                "intervention_tier": candidate.intervention_tier,
                "recorded_at": candidate.recorded_at.isoformat(),
            }
            for candidate in candidates
        ],
    }


__all__ = [
    "clear_improvement_candidate_wiring",
    "configure_improvement_candidate_repository",
    "router",
]
