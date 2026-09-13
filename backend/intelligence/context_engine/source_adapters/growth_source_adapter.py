"""Growth (confirmed intent) → WorldStateAtom adapter (AIFAMILY-WM-003).

`backend.domains.growth.application.growth_intent_confirmation
.ValidatedConfirmationBinding` is the authoritative source — it is the
immutable record of a Growth Intent *after* Assessment's same-UoW human-gate
checks (`growth_intents.boundary = 'HUMAN_CONFIRMED_INTENT_NOT_OUTCOME'`).
This adapter projects it as `family.active_goal`, not `family.confirmed_need`
— a confirmed growth intent is a goal the family has committed to work on,
not the need itself (`family_need_source_adapter.py` already covers the
need side).

`confirmed_at` is not a field on `ValidatedConfirmationBinding` itself (it is
assigned at write time by the SQLAlchemy adapter, see
`backend/domains/growth/infrastructure/sqlalchemy_growth_intent_confirmation
.py:222`) — this adapter takes it as an explicit parameter rather than
guessing `datetime.now()`, so a caller replaying a historical row can supply
the real value instead of silently getting "now".
"""

from __future__ import annotations

from datetime import datetime

from backend.intelligence.context_engine.contracts import ContextScope
from backend.intelligence.context_engine.world_state import (
    WorldStateActorType,
    WorldStateAtom,
    WorldStateEpistemicKind,
)

_HUMAN_CONFIRMED_BOUNDARY = "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"


def growth_intent_atom(
    binding: object,
    *,
    scope: ContextScope,
    atom_id: str,
    confirmed_at: datetime,
    confirmer_actor_type: WorldStateActorType,
) -> WorldStateAtom:
    """Project one confirmed `ValidatedConfirmationBinding` into a
    `family.active_goal` FACT atom.

    `confirmer_actor_type` is a required parameter, not a default guess:
    `ValidatedConfirmationBinding` carries only `actor_id` (a string), not
    which kind of family actor confirmed it (`FAMILY_GUARDIAN` vs
    `FAMILY_MEMBER` — Growth's own `PolicyEngine.human_only=True` only
    guarantees "some human", not which role). A caller that already resolved
    the actor (e.g. from `ActorContext`) must supply the real type here
    rather than this adapter silently assuming `FAMILY_GUARDIAN`.

    Refuses to project a binding whose `boundary` is not the expected
    human-confirmed marker — this adapter must not become a second place
    that could accidentally launder an unconfirmed draft into a FACT atom
    (the boundary check that matters is already enforced upstream in Growth;
    this is a defence-in-depth restatement of the same rule, not a new one).
    """

    if getattr(binding, "boundary", None) != _HUMAN_CONFIRMED_BOUNDARY:
        raise ValueError("GROWTH_INTENT_ATOM_REQUIRES_HUMAN_CONFIRMED_BOUNDARY")
    if confirmer_actor_type is WorldStateActorType.AI:
        raise ValueError("GROWTH_INTENT_ATOM_CONFIRMER_CANNOT_BE_AI")

    return WorldStateAtom(
        atom_id=atom_id,
        scope=scope,
        subject_ids=(binding.subject_person_id,),
        epistemic_kind=WorldStateEpistemicKind.FACT,
        predicate="family.active_goal",
        value_ref=binding.goal_text,
        asserted_by=binding.actor_id,
        attributed_actor_type=confirmer_actor_type,
        provenance=binding.provenance_ref,
        observed_at=confirmed_at,
        recorded_at=confirmed_at,
        valid_from=confirmed_at,
        source_refs=(binding.signal_ref, binding.reviewed_draft_ref),
        evidence_refs=tuple(binding.evidence_refs),
    )


__all__ = ["growth_intent_atom"]
