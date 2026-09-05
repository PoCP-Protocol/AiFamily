"""Parent-facing query surface for `FamilyExperienceSignal`: cross-family,
de-identified "did this help a family like mine" signals — the "小红书-style"
search this platform substitutes for UGC personal stories.

No family/tenant scoping applies here (see
`domain/family_experience_signal.py`'s privacy invariant) — same reasoning
as `improvement_candidate_routes.py`: this is a de-identified, cross-family
query surface, so it does not depend on `family_need`'s `FamilyNeedActor` or
any other family-scoped auth dependency.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from ..application.family_experience_signal import (
    FamilyExperienceSignalRepository,
    summarize_family_experience_by_component,
)
from ..domain.family_experience_signal import NeedCategoryLabel

router = APIRouter(
    prefix="/product-intelligence/experience-signals",
    tags=["product-intelligence-experience-signals"],
)

_repository: FamilyExperienceSignalRepository | None = None


def configure_family_experience_signal_repository(
    repository: FamilyExperienceSignalRepository | None,
) -> None:
    global _repository
    _repository = repository


def clear_family_experience_signal_wiring() -> None:
    configure_family_experience_signal_repository(None)


def _require_repository() -> FamilyExperienceSignalRepository:
    if _repository is None:
        raise HTTPException(status_code=503, detail="family_experience_signal_repository_not_wired")
    return _repository


@router.get("/summary")
async def get_family_experience_signal_summary(
    category: NeedCategoryLabel = Query(...),
) -> dict:
    """"Search a similar problem" query: every component families with a
    `category` need have tried, grouped by component, with how many said it
    helped.

    Returns only `component_id`/`helped_count`/`partially_helped_count`/
    `did_not_help_count`/`total_count`/`helped_rate`/`is_low_confidence` per
    component — no family/tenant/child field exists on this aggregate to
    leak (see `domain/family_experience_signal.py`).

    `is_low_confidence` is true when `total_count` is too small for
    `helped_rate` to mean anything; callers must not present `helped_rate`
    as a confident stat when this is true (see
    `ComponentExperienceSummary.is_low_confidence`).
    """

    repo = _require_repository()
    summaries = await summarize_family_experience_by_component(repo, category=category)
    return {
        "action": "GET_FAMILY_EXPERIENCE_SIGNAL_SUMMARY",
        "boundary": "CROSS_FAMILY_DEIDENTIFIED_SIGNAL_NOT_A_FAMILY_RECORD",
        "category": category,
        "components": [
            {
                "component_id": summary.component_id,
                "helped_count": summary.helped_count,
                "partially_helped_count": summary.partially_helped_count,
                "did_not_help_count": summary.did_not_help_count,
                "total_count": summary.total_count,
                "helped_rate": summary.helped_rate,
                "is_low_confidence": summary.is_low_confidence,
            }
            for summary in summaries
        ],
    }


__all__ = [
    "clear_family_experience_signal_wiring",
    "configure_family_experience_signal_repository",
    "router",
]
