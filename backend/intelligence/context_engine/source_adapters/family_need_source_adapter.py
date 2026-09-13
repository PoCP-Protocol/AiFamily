"""FamilyNeed → WorldStateAtom adapter (AIFAMILY-WM-002).

`backend.domains.family_need.domain.entities.FamilyNeed` is the authoritative
source. This adapter projects a need's *confirmation status*, not the raw
family expression — `NeedSignal.raw_text` (the family's original words) is a
`SELF_REPORT`/`OTHER_REPORT` concern for a future WM-002 increment, not this
one; this file only handles the confirmed/unconfirmed FamilyNeed aggregate,
kept deliberately narrow so the "no new engines this task" boundary holds.

`family.confirmed_need` vs `family.active_need` is chosen from `need.status`:
anything at or past `CONFIRMED` in the N1-N8 lifecycle is a confirmed need;
everything before that (including `REJECTED`/`PAUSED`, which are still part
of what the family is currently working through) is projected as active. This
is a v1 simplification, not a claim that rejected needs are "confirmed" —
see the module docstring on scope.
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

_CONFIRMED_OR_LATER = frozenset(
    {
        NeedStatus.CONFIRMED,
        NeedStatus.PROFILED,
        NeedStatus.SOLUTIONING,
        NeedStatus.FULFILLING,
        NeedStatus.FULFILLED,
        NeedStatus.CLOSED,
    }
)


def _aware(moment: datetime | None) -> datetime:
    if moment is None:
        return datetime.now(UTC)
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def family_need_atom(need: object, *, scope: ContextScope, atom_id: str) -> WorldStateAtom:
    """Project one `FamilyNeed` aggregate into a Platform Core FACT atom."""

    predicate = (
        "family.confirmed_need" if need.status in _CONFIRMED_OR_LATER else "family.active_need"
    )
    return WorldStateAtom(
        atom_id=atom_id,
        scope=scope,
        subject_ids=tuple(need.subject_person_ids),
        epistemic_kind=WorldStateEpistemicKind.FACT,
        predicate=predicate,
        value_ref=need.statement,
        asserted_by=_SYSTEM_ASSERTED_BY,
        attributed_actor_type=WorldStateActorType.SYSTEM,
        provenance=f"family-need-domain:family_needs:{need.need_id}",
        observed_at=_aware(need.created_at),
        recorded_at=_aware(need.updated_at),
        valid_from=_aware(need.created_at),
        source_refs=(f"family-need-domain:family_needs:{need.need_id}",),
    )


__all__ = ["family_need_atom"]
