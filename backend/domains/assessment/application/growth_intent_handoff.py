"""Assessment-to-Growth confirmation data contract for Slice 01.

Assessment contributes a versioned, Human-Gate-reviewed understanding signal
and the immutable binding to the draft/receipt the guardian actually looked
at.  It does not create a `GrowthIntent` itself and confirmation never
re-runs an AI or interpretation adapter — see `growth_hypothesis_commands.py`
for the R9-enforcing caller.

This module is a thin data contract only (dataclasses + `Protocol`s). It
intentionally does not carry a Human Gate persistence adapter, gate
issuance/replay endpoint, or any other human_gate infrastructure — those are
tracked and merged on a separate line of work.  `GrowthHypothesisCommandHandler`
is the sole caller of `GrowthIntentConfirmationPort` in this codebase and is
responsible for its own actor-identity and `PolicyEngine` (R9) checks before
ever constructing a `ConfirmGrowthIntentInput` or looking up a viewed signal;
this module makes no such policy decision itself.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Protocol

from ..domain.errors import AssessmentValidationError

GuardianDecisionType = Literal["CONFIRM", "DISMISS"]
HumanGateEffectiveStatus = Literal["EFFECTIVE", "NOT_REVIEWED", "REVOKED", "EXPIRED"]


@dataclass(frozen=True, slots=True)
class ViewedUnderstandingSignal:
    """Canonical, immutable binding for the draft the guardian reviewed.

    Human Gate remains externally owned. Assessment receives only opaque
    references and the canonical effective-state projection needed to fail
    closed; it does not create or persist a second receipt.
    """

    tenant_id: str
    family_id: str
    assessment_session_id: str
    signal_ref: str
    signal_version: int
    scope_ref: str
    reviewed_draft_ref: str
    draft_version: int
    provenance_ref: str
    human_gate_receipt_ref: str
    human_gate_effective_status: HumanGateEffectiveStatus
    reviewed_by_actor_id: str
    subject_person_id: str
    need_type: str
    goal_text: str
    required_capability_keys: tuple[str, ...]
    evidence_refs: tuple[str, ...]

    def __post_init__(self) -> None:
        required = (
            self.tenant_id,
            self.family_id,
            self.assessment_session_id,
            self.signal_ref,
            self.scope_ref,
            self.reviewed_draft_ref,
            self.provenance_ref,
            self.human_gate_receipt_ref,
            self.reviewed_by_actor_id,
            self.subject_person_id,
            self.need_type,
            self.goal_text,
        )
        if not all(value.strip() for value in required):
            raise AssessmentValidationError("viewed_understanding_signal_required")
        if self.signal_version < 1:
            raise AssessmentValidationError("understanding_signal_version_invalid")
        if self.draft_version < 1:
            raise AssessmentValidationError("reviewed_draft_version_invalid")
        if not self.evidence_refs:
            raise AssessmentValidationError("understanding_signal_evidence_required")


@dataclass(frozen=True, slots=True)
class ConfirmGrowthIntentInput:
    """Exactly what `ValidatedConfirmationBinding.from_command` consumes.

    Field set mirrors `growth_intent_confirmation.ConfirmationCommandLike`
    (the structural protocol the Growth domain actually type-checks
    against) so that any caller assembling one of these is guaranteed to
    satisfy that protocol.
    """

    tenant_id: str
    family_id: str
    actor_id: str
    subject_person_id: str
    signal_ref: str
    signal_version: int
    scope_ref: str
    reviewed_draft_ref: str
    draft_version: int
    provenance_ref: str
    human_gate_receipt_ref: str
    need_type: str
    goal_text: str
    required_capability_keys: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    correlation_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class GrowthIntentReceipt:
    """Durable receipt returned by `GrowthIntentConfirmationPort.confirm_growth_intent`."""

    intent_id: str
    signal_ref: str
    signal_version: int
    scope_ref: str
    reviewed_draft_ref: str
    draft_version: int
    provenance_ref: str
    human_gate_receipt_ref: str
    receipt_ref: str
    boundary: str = "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"
    replayed: bool = False


class ViewedUnderstandingSignalReaderPort(Protocol):
    async def load_viewed_signal(
        self,
        *,
        tenant_id: str,
        family_id: str,
        assessment_session_id: str,
        human_gate_receipt_ref: str,
    ) -> ViewedUnderstandingSignal | None: ...


class GrowthIntentConfirmationPort(Protocol):
    """Growth-owned seam: create (or replay) a canonical GrowthIntent.

    Implemented in production by
    `backend.domains.growth.infrastructure.sqlalchemy_growth_intent_confirmation
    .SqlAlchemyGrowthIntentConfirmationAdapter`.
    """

    async def confirm_growth_intent(
        self, command: ConfirmGrowthIntentInput
    ) -> GrowthIntentReceipt: ...


__all__ = [
    "ConfirmGrowthIntentInput",
    "GrowthIntentConfirmationPort",
    "GrowthIntentReceipt",
    "GuardianDecisionType",
    "HumanGateEffectiveStatus",
    "ViewedUnderstandingSignal",
    "ViewedUnderstandingSignalReaderPort",
]
