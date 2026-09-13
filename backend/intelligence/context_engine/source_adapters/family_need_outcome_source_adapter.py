"""FamilyConfirmedOutcome → WorldStateAtom adapter (AIFAMILY-WM-003,
semantics corrected in WM-003.5).

`backend.domains.family_need.domain.entities.FamilyConfirmedOutcome` is the
authoritative source — N6/N7 in the Need lifecycle, and the *only* place a
service/course's helpfulness verdict exists. `assert_family_outcome_confirmer`
already refuses AI/SYSTEM actors at construction, so by the time this adapter
sees an outcome, it is guaranteed family-asserted; this adapter's own AI
rejection check is defence in depth, matching the same pattern as
`growth_source_adapter.confirmed_growth_intent_atom`.

**WM-003.5 correction**: this adapter projects `family.confirmed_outcome`,
not `family.outcome`. `FamilyConfirmedOutcome` proves exactly one thing —
`FAMILY_CONFIRMED_FULFILLMENT_VERDICT`: the family says a specific, already-
delivered fulfilment (`fulfillment_ref`) helped/partially helped/did not
help. It does **not** prove that any observable state changed
("`child.communication_frequency` improved"), that a goal was achieved, or
that the fulfilment *caused* anything — those are three separate, stronger
claims (Observed State Change / Goal Achievement / Causal Effect) that this
adapter must never manufacture from a `HELPED` verdict. See
`test_family_confirmed_outcome_atom_does_not_imply_state_change` for the
regression test that keeps this honest.

No `evidence_refs` field exists on `FamilyConfirmedOutcome` (see the audit at
`docs/13_research/technology/AIFAMILY_WM000_TRUTH_SOURCE_ONTOLOGY_AUDIT.md`
§2) — the evidence for "this helped" is the `fulfillment_ref` itself
(a completed booking or course), carried here as a source ref rather than an
evidence ref, since it is not evidence *for* a claim but the delivered thing
the claim is *about*.

**WM-003.6 source identity**: `family_confirmed_outcome_source_identity()`
below uses `outcome.outcome_id` as `source_ref` with a fixed
`source_version = "1"`. `FamilyConfirmedOutcome` is an append-only verdict
(module docstring: "the *only* place a service/course's helpfulness verdict
exists") with no update method in `backend.domains.family_need.domain
.entities` — once a family confirms an outcome, that specific `outcome_id`
never represents a different verdict, so there is no "v2" to version.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.domains.family_need.domain.value_objects import ActorType
from backend.domains.family_need.domain.value_objects import DataClass as NeedDataClass
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.world_state import (
    WorldStateActorType,
    WorldStateAtom,
    WorldStateEpistemicKind,
)

_ACTOR_TYPE_MAP = {
    ActorType.FAMILY_GUARDIAN: WorldStateActorType.FAMILY_GUARDIAN,
    ActorType.FAMILY_MEMBER: WorldStateActorType.FAMILY_MEMBER,
}

#: Adapter contract version — see growth_source_adapter.py's equivalent
#: constant for why this exists.
FAMILY_CONFIRMED_OUTCOME_PROJECTION_VERSION = "world-fact-adapter/family-outcome/v1"


def family_confirmed_outcome_source_identity(outcome: object) -> tuple[str, str]:
    """`(source_ref, source_version)` for `append_atom`'s idempotency
    contract — see module docstring for why `outcome_id` + fixed version
    `"1"` is the correct, non-guessed choice."""

    return f"family-confirmed-outcome:{outcome.outcome_id}", "1"


# FamilyNeed's DataClass vocabulary (PUBLIC/INTERNAL/FAMILY_PRIVATE/
# SENSITIVE_PERSONAL_DATA/MINOR_PERSONAL_DATA) does not line up 1:1 with the
# World State Kernel's (SYNTHETIC/OPERATIONAL_TEXT/FAMILY_PRIVATE_TEXT/
# MINOR_PERSONAL_DATA) — passing one straight into the other's constructor
# would either raise on an unmatched value or, worse, silently succeed on
# the one accidental string collision. This is an explicit, reviewable
# mapping; anything not listed fails loudly rather than guessing.
_DATA_CLASS_MAP = {
    NeedDataClass.PUBLIC: DataClass.SYNTHETIC,
    NeedDataClass.INTERNAL: DataClass.OPERATIONAL_TEXT,
    NeedDataClass.FAMILY_PRIVATE: DataClass.FAMILY_PRIVATE_TEXT,
    NeedDataClass.SENSITIVE_PERSONAL_DATA: DataClass.FAMILY_PRIVATE_TEXT,
    NeedDataClass.MINOR_PERSONAL_DATA: DataClass.MINOR_PERSONAL_DATA,
}


def _aware(moment: datetime) -> datetime:
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def family_confirmed_outcome_atom(outcome: object, *, atom_id: str) -> WorldStateAtom:
    """Project one `FamilyConfirmedOutcome` into a `family.confirmed_outcome`
    FACT atom — a fulfilment-helpfulness verdict, nothing more (see module
    docstring for exactly what this does and does not prove).

    Builds its own `ContextScope` from `outcome.context` (a `NeedContext`)
    rather than accepting a caller-supplied scope — the outcome's own context
    already carries the exact tenant/family/subject/purpose/consent envelope
    it was confirmed under, and reusing it (instead of asking the caller to
    reconstruct an equivalent one) removes a chance for the two to drift.
    """

    context = outcome.context
    actor_type = _ACTOR_TYPE_MAP.get(context.actor_type)
    if actor_type is None:
        raise ValueError("FAMILY_OUTCOME_ATOM_REQUIRES_FAMILY_ACTOR")
    data_class = _DATA_CLASS_MAP.get(context.data_class)
    if data_class is None:
        raise ValueError("FAMILY_OUTCOME_ATOM_UNMAPPED_DATA_CLASS")

    scope = ContextScope(
        tenant_id=context.tenant_id,
        region_id="CN",
        family_id=context.family_id,
        subject_ids=tuple(context.subject_person_ids),
        purpose=context.purpose,
        consent_version=context.consent_version,
        consent_granted=True,
        data_class=data_class,
        locale="zh-CN",
        deletion_ref=f"delete:{context.family_id}",
        correlation_id=context.correlation_id,
        causation_id=f"family-need-outcome:{outcome.outcome_id}",
    )
    confirmed_at = _aware(outcome.confirmed_at)

    return WorldStateAtom(
        atom_id=atom_id,
        scope=scope,
        subject_ids=tuple(context.subject_person_ids),
        epistemic_kind=WorldStateEpistemicKind.FACT,
        predicate="family.confirmed_outcome",
        value_ref=outcome.decision.value,
        asserted_by=outcome.confirmed_by,
        attributed_actor_type=actor_type,
        provenance=f"family-need-domain:family_need_confirmed_outcomes:{outcome.outcome_id}",
        observed_at=confirmed_at,
        recorded_at=confirmed_at,
        valid_from=confirmed_at,
        source_refs=(outcome.fulfillment_ref, f"family-need:{outcome.need_id}"),
    )


__all__ = [
    "FAMILY_CONFIRMED_OUTCOME_PROJECTION_VERSION",
    "family_confirmed_outcome_atom",
    "family_confirmed_outcome_source_identity",
]
