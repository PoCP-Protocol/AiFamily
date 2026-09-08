"""Real FamilyNeed -> vertical AGI context seam.

This adapter only reads the FamilyNeed repository.  It does not call a model,
write a fact, or create a second context model; the vertical runtime consumes
the returned ``FamilyGrowthContext`` through its existing port.
"""

from __future__ import annotations

from backend.intelligence.agi_vertical_runtime import FamilyGrowthContext

from .ai_coach import build_family_context
from .ports import FamilyNeedRepositoryPort


async def read_vertical_agi_context(
    repository: FamilyNeedRepositoryPort,
    *,
    tenant_id: str,
    family_id: str,
    family_need_id: str,
) -> FamilyGrowthContext:
    context, snapshot_ref, _data_class, consent_version, subject_ids = await build_family_context(
        repository,
        tenant_id=tenant_id,
        family_id=family_id,
        need_id=family_need_id,
    )
    return FamilyGrowthContext(
        tenant_id=tenant_id,
        family_id=family_id,
        subject_ids=tuple(subject_ids),
        purpose="family-growth-understanding",
        consent_version=consent_version,
        context_snapshot_ref=snapshot_ref,
        values={"family_need_id": family_need_id, **context},
    )


__all__ = ["read_vertical_agi_context"]
