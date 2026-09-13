"""Family Core → WorldStateAtom adapter (AIFAMILY-WM-002).

`backend.domains.family.domain.entities.Family/FamilyMember/FamilyRelationship`
are the authoritative source; this module only projects them into the
Platform Core predicates registered in
`governance/WORLD_MODEL_PREDICATE_REGISTRY.yaml` (`family.member_of`,
`family.relationship`). Every atom produced here is `FACT`, attributed to
`SYSTEM` — these are confirmed rows from the Family Truth Plane, not AI
perspectives, so `WorldStateActorType.SYSTEM` (not `AI`) is the only
attribution that keeps `WorldStateAtom.__post_init__`'s
`AI_CANNOT_ASSERT_THIS_EPISTEMIC_KIND` invariant meaningful: a human reading
these atoms must be able to trust that "SYSTEM asserted this FACT" means "the
Family domain's own write path confirmed this", not "a model guessed this".
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.intelligence.context_engine.contracts import ContextScope
from backend.intelligence.context_engine.world_state import (
    WorldStateActorType,
    WorldStateAtom,
    WorldStateEpistemicKind,
)

_SYSTEM_ASSERTED_BY = "system:family-domain"


def _aware(moment: datetime) -> datetime:
    """Family Core deliberately stores naive-UTC timestamps (see
    `backend.domains.family.domain.entities.utcnow` docstring) so a
    naive/aware round trip never produces a false SQLite comparison failure.
    The World State Kernel requires timezone-aware datetimes throughout, so
    this adapter is the one place that reconciles the two conventions."""

    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def family_member_atom(member: object, *, scope: ContextScope, atom_id: str) -> WorldStateAtom:
    """Project one `FamilyMember` row into a `family.member_of` FACT atom."""

    return WorldStateAtom(
        atom_id=atom_id,
        scope=scope,
        subject_ids=(member.person_id,),
        epistemic_kind=WorldStateEpistemicKind.FACT,
        predicate="family.member_of",
        value_ref=member.family_id,
        asserted_by=_SYSTEM_ASSERTED_BY,
        attributed_actor_type=WorldStateActorType.SYSTEM,
        provenance=f"family-domain:persons:{member.person_id}",
        observed_at=_aware(member.created_at),
        recorded_at=_aware(member.updated_at),
        valid_from=_aware(member.created_at),
        source_refs=(f"family-domain:persons:{member.person_id}",),
    )


def family_relationship_atom(
    relationship: object, *, scope: ContextScope, atom_id: str
) -> WorldStateAtom:
    """Project one `FamilyRelationship` row into a `family.relationship` FACT
    atom. Deliberately does not infer consent or authority from the
    relationship — see `FamilyRelationship`'s own docstring
    ("authorises nothing"); this adapter only carries that same fact forward,
    it does not add meaning the source domain did not put there."""

    return WorldStateAtom(
        atom_id=atom_id,
        scope=scope,
        subject_ids=(relationship.person_a_id, relationship.person_b_id),
        epistemic_kind=WorldStateEpistemicKind.FACT,
        predicate="family.relationship",
        value_ref=relationship.relationship_type,
        asserted_by=_SYSTEM_ASSERTED_BY,
        attributed_actor_type=WorldStateActorType.SYSTEM,
        provenance=f"family-domain:family_relationships:{relationship.relationship_id}",
        observed_at=_aware(relationship.created_at),
        recorded_at=_aware(relationship.created_at),
        valid_from=_aware(relationship.created_at),
        source_refs=(f"family-domain:family_relationships:{relationship.relationship_id}",),
    )


__all__ = ["family_member_atom", "family_relationship_atom"]
