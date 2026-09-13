"""AIFAMILY-WM-003 acceptance tests: Growth Intent + FamilyConfirmedOutcome
source adapters.

Pure transform tests (no I/O), matching the WM-002 pattern in
`test_source_adapters.py`.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from backend.domains.family_need.domain.entities import FamilyConfirmedOutcome
from backend.domains.family_need.domain.value_objects import (
    ActorType,
    FamilyOutcomeDecision,
    NeedContext,
)
from backend.domains.family_need.domain.value_objects import (
    DataClass as NeedDataClass,
)
from backend.domains.growth.application.growth_intent_confirmation import (
    ValidatedConfirmationBinding,
)
from backend.intelligence.context_engine.contracts import ContextScope, DataClass
from backend.intelligence.context_engine.source_adapters.family_need_outcome_source_adapter import (
    family_confirmed_outcome_atom,
)
from backend.intelligence.context_engine.source_adapters.growth_source_adapter import (
    growth_intent_atom,
)
from backend.intelligence.context_engine.world_state import (
    WorldStateActorType,
    WorldStateEpistemicKind,
)

NOW = datetime(2026, 9, 13, tzinfo=UTC)
UUID_A = "11111111-1111-1111-1111-111111111111"
UUID_B = "22222222-2222-2222-2222-222222222222"
UUID_C = "33333333-3333-3333-3333-333333333333"
UUID_D = "44444444-4444-4444-4444-444444444444"


def scope(**overrides: object) -> ContextScope:
    values: dict[str, object] = {
        "tenant_id": "tenant-1",
        "region_id": "CN",
        "family_id": "family-1",
        "subject_ids": (UUID_A,),
        "purpose": "family_growth_support",
        "consent_version": "consent.v1",
        "consent_granted": True,
        "data_class": DataClass.MINOR_PERSONAL_DATA,
        "locale": "zh-CN",
        "deletion_ref": "delete:family-1",
        "correlation_id": "corr-1",
        "causation_id": "cause-1",
    }
    values.update(overrides)
    return ContextScope(**values)  # type: ignore[arg-type]


class _CommandLike:
    def __init__(self, **kwargs: object) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)


def _confirmed_binding(**overrides: object) -> ValidatedConfirmationBinding:
    values: dict[str, object] = {
        "tenant_id": UUID_A,
        "family_id": UUID_B,
        "actor_id": UUID_C,
        "subject_person_id": UUID_A,
        "signal_ref": "signal-1",
        "signal_version": 1,
        "scope_ref": f"family://{UUID_A}/{UUID_B}/assessment",
        "reviewed_draft_ref": "draft-1",
        "draft_version": 1,
        "provenance_ref": "provenance-1",
        "human_gate_receipt_ref": "receipt-1",
        "need_type": "COMMUNICATION",
        "goal_text": "改善晚间沟通方式",
        "required_capability_keys": ("family_communication_coaching",),
        "evidence_refs": (UUID_D,),
        "correlation_id": "corr-1",
        "idempotency_key": "idem-1",
    }
    values.update(overrides)
    return ValidatedConfirmationBinding.from_command(_CommandLike(**values))


def _need_context(**overrides: object) -> NeedContext:
    values: dict[str, object] = {
        "tenant_id": "tenant-1",
        "family_id": "family-1",
        "subject_person_ids": ("child-1",),
        "purpose": "FAMILY_NEED",
        "consent_version": "consent-v1",
        "data_class": NeedDataClass.MINOR_PERSONAL_DATA,
        "actor_id": "mother-1",
        "actor_type": ActorType.FAMILY_GUARDIAN,
        "correlation_id": "corr-1",
    }
    values.update(overrides)
    return NeedContext(**values)  # type: ignore[arg-type]


def _confirmed_outcome(**overrides: object) -> FamilyConfirmedOutcome:
    values: dict[str, object] = {
        "context": _need_context(),
        "need_id": "need-1",
        "fulfillment_ref": "booking-service-record:booking-1",
        "decision": FamilyOutcomeDecision.HELPED,
        "confirmed_by": "mother-1",
    }
    values.update(overrides)
    return FamilyConfirmedOutcome.confirm(**values)


# --- Growth Intent adapter --------------------------------------------------


def test_growth_intent_atom_is_a_fact_atom_on_active_goal() -> None:
    binding = _confirmed_binding()
    atom = growth_intent_atom(
        binding,
        scope=scope(subject_ids=(UUID_A,)),
        atom_id="goal-atom-1",
        confirmed_at=NOW,
        confirmer_actor_type=WorldStateActorType.FAMILY_GUARDIAN,
    )
    assert atom.epistemic_kind is WorldStateEpistemicKind.FACT
    assert atom.predicate == "family.active_goal"
    assert atom.value_ref == "改善晚间沟通方式"
    assert atom.evidence_refs == (UUID_D,)


def test_growth_intent_atom_refuses_ai_confirmer() -> None:
    binding = _confirmed_binding()
    with pytest.raises(ValueError, match="GROWTH_INTENT_ATOM_CONFIRMER_CANNOT_BE_AI"):
        growth_intent_atom(
            binding,
            scope=scope(subject_ids=(UUID_A,)),
            atom_id="goal-atom-2",
            confirmed_at=NOW,
            confirmer_actor_type=WorldStateActorType.AI,
        )


def test_growth_intent_atom_refuses_wrong_boundary() -> None:
    binding = _confirmed_binding()
    tampered = object.__new__(type(binding))
    for field in binding.__dataclass_fields__:
        object.__setattr__(tampered, field, getattr(binding, field))
    object.__setattr__(tampered, "boundary", "SOMETHING_ELSE")

    with pytest.raises(ValueError, match="GROWTH_INTENT_ATOM_REQUIRES_HUMAN_CONFIRMED_BOUNDARY"):
        growth_intent_atom(
            tampered,
            scope=scope(subject_ids=(UUID_A,)),
            atom_id="goal-atom-3",
            confirmed_at=NOW,
            confirmer_actor_type=WorldStateActorType.FAMILY_GUARDIAN,
        )


# --- FamilyConfirmedOutcome adapter -----------------------------------------


def test_family_confirmed_outcome_atom_is_a_fact_atom() -> None:
    outcome = _confirmed_outcome()
    atom = family_confirmed_outcome_atom(outcome, atom_id="outcome-atom-1")
    assert atom.epistemic_kind is WorldStateEpistemicKind.FACT
    assert atom.predicate == "family.outcome"
    assert atom.value_ref == "HELPED"
    assert atom.attributed_actor_type is WorldStateActorType.FAMILY_GUARDIAN
    assert "booking-service-record:booking-1" in atom.source_refs


def test_family_confirmed_outcome_atom_never_attributed_to_ai() -> None:
    """`FamilyConfirmedOutcome.__post_init__` already rejects AI/SYSTEM
    confirmers (`assert_family_outcome_confirmer`) — this test documents
    that the adapter has no path that could override that."""

    outcome = _confirmed_outcome()
    atom = family_confirmed_outcome_atom(outcome, atom_id="outcome-atom-2")
    assert atom.attributed_actor_type is not WorldStateActorType.AI


def test_family_confirmed_outcome_atom_maps_data_class() -> None:
    outcome = _confirmed_outcome(context=_need_context(data_class=NeedDataClass.FAMILY_PRIVATE))
    atom = family_confirmed_outcome_atom(outcome, atom_id="outcome-atom-3")
    assert atom.scope.data_class is DataClass.FAMILY_PRIVATE_TEXT
