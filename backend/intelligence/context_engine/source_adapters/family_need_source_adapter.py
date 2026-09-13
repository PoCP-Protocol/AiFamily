"""FamilyNeed → WorldStateAtom adapter (AIFAMILY-WM-002, corrected WM-005B).

`backend.domains.family_need.domain.entities.FamilyNeed` is the authoritative
source. This adapter projects a need's *current lifecycle status*, not the
raw family expression — `NeedSignal.raw_text` (the family's original words)
is a `SELF_REPORT`/`OTHER_REPORT` concern for a future WM-002 increment, not
this one.

AIFAMILY-WM-005B correction: the WM-002 version of this adapter conflated
two different things under `need.status`:

1. "is AiFamily currently working through this need" (a *current* fact) —
   REJECTED/PAUSED were wrongly included here, which is what this file now
   fixes. A rejected or paused need is not something the family is currently
   working through; projecting it as `family.active_need` told a Task
   Context consumer the opposite of the truth.
2. "did the family confirm this need" (a *historical* fact) — the WM-002
   version derived this from "status >= confirmed-like", which is an
   inference from current aggregate state, not a real confirmation event.
   `family.confirmed_need` stays registered in
   `governance/WORLD_MODEL_PREDICATE_REGISTRY.yaml`, but this adapter no
   longer manufactures it. There is currently no authoritative confirmation
   event/record for FamilyNeed (unlike growth intent, which has a real
   confirmation binding — see `growth_source_adapter.py`) to project it
   from. `CONFIRMED_NEED_EVENT_SOURCE = GAP` until one exists; see the
   AIFAMILY-WM-005B completion report.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.domains.family_need.domain.value_objects import NeedStatus
from backend.intelligence.context_engine.contracts import ContextScope
from backend.intelligence.context_engine.world_state import (
    WorldStateActorType,
    WorldStateAtom,
    WorldStateEpistemicKind,
)

_SYSTEM_ASSERTED_BY = "system:family-need-domain"

#: "AiFamily currently has an unfinished lifecycle for this need" — not
#: "the family confirmed this need". CONFIRMED is included: a
#: confirmed-but-not-yet-profiled need is still active work, and "active"
#: here must not be conflated with "family confirmed" — a need can be
#: actively worked through (CAPTURED/CLARIFYING) before any confirmation
#: exists at all.
_ACTIVE_NEED_STATUSES = frozenset(
    {
        NeedStatus.CAPTURED,
        NeedStatus.CLARIFYING,
        NeedStatus.CONFIRMED,
        NeedStatus.PROFILED,
        NeedStatus.SOLUTIONING,
        NeedStatus.FULFILLING,
    }
)


def _aware(moment: datetime | None) -> datetime:
    if moment is None:
        return datetime.now(UTC)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def family_active_need_atom(
    need: object, *, scope: ContextScope, atom_id: str
) -> WorldStateAtom | None:
    """Project one `FamilyNeed` aggregate into a `family.active_need` FACT
    atom — or `None` if its current status is not "still being worked
    through" (REJECTED/PAUSED/FULFILLED/CLOSED). Returning `None` rather
    than an atom with a misleading predicate is deliberate: a caller that
    forgets to check the return value gets no atom at all, not a wrong one.
    """

    if need.status not in _ACTIVE_NEED_STATUSES:
        return None

    return WorldStateAtom(
        atom_id=atom_id,
        scope=scope,
        subject_ids=tuple(need.subject_person_ids),
        epistemic_kind=WorldStateEpistemicKind.FACT,
        predicate="family.active_need",
        value_ref=need.statement,
        asserted_by=_SYSTEM_ASSERTED_BY,
        attributed_actor_type=WorldStateActorType.SYSTEM,
        provenance=f"family-need-domain:family_needs:{need.need_id}",
        observed_at=_aware(need.created_at),
        recorded_at=_aware(need.updated_at),
        valid_from=_aware(need.created_at),
        source_refs=(f"family-need-domain:family_needs:{need.need_id}",),
    )


__all__ = ["family_active_need_atom"]
