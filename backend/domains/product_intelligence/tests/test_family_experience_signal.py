"""Unit coverage for `ComponentExperienceSummary.is_low_confidence` — the
small-sample-false-consensus guard: a `helped_rate` computed from too few
signals must be flagged, not presented as a confident stat (see
`application/family_experience_signal.py`'s `MIN_SAMPLE_SIZE_FOR_CONFIDENT_RATE`).

Uses the in-memory repository directly rather than the full HTTP/Postgres
e2e chain — no family_need/course_content/FGCN wiring needed to exercise
this aggregate's own logic.
"""

from __future__ import annotations

import asyncio

from backend.domains.product_intelligence.application.family_experience_signal import (
    MIN_SAMPLE_SIZE_FOR_CONFIDENT_RATE,
    record_family_experience_signal,
    summarize_family_experience_by_component,
)
from backend.domains.product_intelligence.infrastructure import (
    family_experience_signal_repository as fes_repo,
)


def _record_n(
    repo: fes_repo.InMemoryFamilyExperienceSignalRepository, *, component_id: str, n: int
) -> None:
    async def _run() -> None:
        for _ in range(n):
            await record_family_experience_signal(
                repo,
                component_id=component_id,
                component_shape="SERVICE",
                decision="HELPED",
                category="EDUCATION",
                intervention_tier="LIGHT_GUIDANCE",
            )

    asyncio.run(_run())


def test_summary_is_low_confidence_below_the_minimum_sample_size() -> None:
    repo = fes_repo.InMemoryFamilyExperienceSignalRepository()
    _record_n(repo, component_id="COMMUNICATION", n=MIN_SAMPLE_SIZE_FOR_CONFIDENT_RATE - 1)

    async def _run() -> tuple:
        return await summarize_family_experience_by_component(repo, category="EDUCATION")

    (summary,) = asyncio.run(_run())
    assert summary.total_count == MIN_SAMPLE_SIZE_FOR_CONFIDENT_RATE - 1
    assert summary.is_low_confidence is True


def test_summary_is_not_low_confidence_at_the_minimum_sample_size() -> None:
    repo = fes_repo.InMemoryFamilyExperienceSignalRepository()
    _record_n(repo, component_id="COMMUNICATION", n=MIN_SAMPLE_SIZE_FOR_CONFIDENT_RATE)

    async def _run() -> tuple:
        return await summarize_family_experience_by_component(repo, category="EDUCATION")

    (summary,) = asyncio.run(_run())
    assert summary.total_count == MIN_SAMPLE_SIZE_FOR_CONFIDENT_RATE
    assert summary.is_low_confidence is False
