"""Assessment-to-Growth confirmation contract for Slice 01.

Assessment contributes versioned evidence and an understanding signal.  It
does not create a GrowthIntent itself and confirmation never re-runs an AI or
interpretation adapter.  The Growth owner receives exactly the signal/version
the guardian reviewed and owns idempotency plus the returned intent receipt.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Literal, Protocol

from ..domain.errors import (
    AssessmentConflictError,
    AssessmentForbiddenError,
    AssessmentNotFoundError,
    AssessmentValidationError,
)
from ..domain.value_objects import GROWTH_INTENT_BOUNDARY

GuardianDecisionType = Literal["CONFIRM", "DISMISS"]
HumanGateEffectiveStatus = Literal["EFFECTIVE", "NOT_REVIEWED", "REVOKED", "EXPIRED"]


@dataclass(frozen=True, slots=True)
class ViewedUnderstandingSignal:
    """Canonical, immutable binding for the draft the guardian reviewed.

    Human Gate remains externally owned.  Assessment receives only opaque
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
    reviewed_at: datetime | None = None
    expires_at: datetime | None = None
    revoked_at: datetime | None = None
    revocation_ref: str | None = None
    draft_source: str | None = None
    output_schema_ref: str | None = None
    view_event_ref: str | None = None

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
    intent_id: str
    signal_ref: str
    signal_version: int
    scope_ref: str
    reviewed_draft_ref: str
    draft_version: int
    provenance_ref: str
    human_gate_receipt_ref: str
    receipt_ref: str
    boundary: Literal["HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"] = GROWTH_INTENT_BOUNDARY
    replayed: bool = False


@dataclass(frozen=True, slots=True)
class DecideViewedUnderstandingInput:
    tenant_id: str
    family_id: str
    actor_id: str
    actor_type: Literal["FAMILY_GUARDIAN", "FAMILY_MEMBER", "OPERATOR", "AI"]
    assessment_session_id: str
    signal_ref: str
    signal_version: int
    scope_ref: str
    reviewed_draft_ref: str
    draft_version: int
    provenance_ref: str
    human_gate_receipt_ref: str
    decision_type: GuardianDecisionType
    correlation_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class UnderstandingDecisionReceipt:
    action: Literal["CONFIRM_UNDERSTANDING", "DISMISS_UNDERSTANDING"]
    outcome: Literal["INTENT_CREATED", "NO_ACTION"]
    signal_ref: str
    signal_version: int
    scope_ref: str
    human_gate_receipt_ref: str
    intent: GrowthIntentReceipt | None


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
    async def confirm_growth_intent(
        self, command: ConfirmGrowthIntentInput
    ) -> GrowthIntentReceipt: ...


class AssessmentGrowthIntentHandoff:
    """Compatibility use case that delegates canonical intent creation."""

    def __init__(
        self,
        signal_reader: ViewedUnderstandingSignalReaderPort,
        growth_intents: GrowthIntentConfirmationPort,
    ) -> None:
        self._signal_reader = signal_reader
        self._growth_intents = growth_intents

    async def decide(self, command: DecideViewedUnderstandingInput) -> UnderstandingDecisionReceipt:
        if command.actor_type != "FAMILY_GUARDIAN":
            raise AssessmentForbiddenError("guardian_confirmation_required")
        if command.decision_type not in ("CONFIRM", "DISMISS"):
            raise AssessmentValidationError("understanding_decision_invalid")
        if not command.idempotency_key.strip():
            raise AssessmentValidationError("idempotency_key_required")
        binding_refs = (
            command.scope_ref,
            command.reviewed_draft_ref,
            command.provenance_ref,
            command.human_gate_receipt_ref,
        )
        if not all(value.strip() for value in binding_refs) or command.draft_version < 1:
            raise AssessmentValidationError("reviewed_draft_binding_required")

        signal = await self._signal_reader.load_viewed_signal(
            tenant_id=command.tenant_id,
            family_id=command.family_id,
            assessment_session_id=command.assessment_session_id,
            human_gate_receipt_ref=command.human_gate_receipt_ref,
        )
        if signal is None:
            raise AssessmentNotFoundError("understanding_signal_not_found")
        if signal.tenant_id != command.tenant_id or signal.family_id != command.family_id:
            raise AssessmentForbiddenError("family_access_denied")
        if signal.scope_ref != command.scope_ref:
            raise AssessmentForbiddenError("human_gate_scope_mismatch")
        if signal.reviewed_by_actor_id != command.actor_id:
            raise AssessmentForbiddenError("human_gate_actor_mismatch")
        if signal.human_gate_effective_status != "EFFECTIVE":
            raise AssessmentForbiddenError("human_gate_receipt_not_effective")
        if (
            signal.signal_ref != command.signal_ref
            or signal.signal_version != command.signal_version
        ):
            raise AssessmentConflictError("understanding_signal_version_conflict")
        if signal.human_gate_receipt_ref != command.human_gate_receipt_ref:
            raise AssessmentConflictError("human_gate_receipt_mismatch")
        if (
            signal.reviewed_draft_ref != command.reviewed_draft_ref
            or signal.draft_version != command.draft_version
            or signal.provenance_ref != command.provenance_ref
        ):
            raise AssessmentConflictError("reviewed_draft_binding_mismatch")

        if command.decision_type == "DISMISS":
            return UnderstandingDecisionReceipt(
                action="DISMISS_UNDERSTANDING",
                outcome="NO_ACTION",
                signal_ref=signal.signal_ref,
                signal_version=signal.signal_version,
                scope_ref=signal.scope_ref,
                human_gate_receipt_ref=signal.human_gate_receipt_ref,
                intent=None,
            )

        intent = await self._growth_intents.confirm_growth_intent(
            ConfirmGrowthIntentInput(
                tenant_id=signal.tenant_id,
                family_id=signal.family_id,
                actor_id=command.actor_id,
                subject_person_id=signal.subject_person_id,
                signal_ref=signal.signal_ref,
                signal_version=signal.signal_version,
                scope_ref=signal.scope_ref,
                reviewed_draft_ref=signal.reviewed_draft_ref,
                draft_version=signal.draft_version,
                provenance_ref=signal.provenance_ref,
                human_gate_receipt_ref=signal.human_gate_receipt_ref,
                need_type=signal.need_type,
                goal_text=signal.goal_text,
                required_capability_keys=signal.required_capability_keys,
                evidence_refs=signal.evidence_refs,
                correlation_id=command.correlation_id,
                idempotency_key=command.idempotency_key,
            )
        )
        if (
            intent.signal_ref != signal.signal_ref
            or intent.signal_version != signal.signal_version
            or intent.scope_ref != signal.scope_ref
            or intent.reviewed_draft_ref != signal.reviewed_draft_ref
            or intent.draft_version != signal.draft_version
            or intent.provenance_ref != signal.provenance_ref
            or intent.human_gate_receipt_ref != signal.human_gate_receipt_ref
            or intent.boundary != GROWTH_INTENT_BOUNDARY
        ):
            raise AssessmentConflictError("growth_intent_receipt_signal_mismatch")
        return UnderstandingDecisionReceipt(
            action="CONFIRM_UNDERSTANDING",
            outcome="INTENT_CREATED",
            signal_ref=signal.signal_ref,
            signal_version=signal.signal_version,
            scope_ref=signal.scope_ref,
            human_gate_receipt_ref=signal.human_gate_receipt_ref,
            intent=intent,
        )
