"""Assessment-to-Growth confirmation data contract for Slice 01.

Assessment contributes a versioned, Human-Gate-reviewed understanding signal
and the immutable binding to the draft/receipt the guardian actually looked
at.  It does not create a `GrowthIntent` itself and confirmation never
re-runs an AI or interpretation adapter — see `growth_hypothesis_commands.py`
for the R9-enforcing legacy/canonical caller, and `AssessmentGrowthIntentHandoff`
below for the newer, session-or-run-scoped decide() entry point that the
Human Gate persistence adapters in `reviewed_understanding_signals.py` /
`sqlalchemy_reviewed_understanding_signals.py` are built against.

`ConfirmGrowthIntentInput`, `GrowthIntentReceipt`, and
`GrowthIntentConfirmationPort` are the original Slice 01 contract and remain
field-for-field unchanged — every existing caller (`growth_hypothesis_commands
.GrowthHypothesisCommandHandler`, `production_growth_wiring
.ProductionGrowthConfirmationWiring`, `sqlalchemy_growth_intent_confirmation
.SqlAlchemyGrowthIntentConfirmationAdapter`) keeps working against them
unmodified.
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

    Human Gate remains externally owned. Assessment receives only opaque
    references and the canonical effective-state projection needed to fail
    closed; it does not create or persist a second receipt.
    """

    tenant_id: str
    family_id: str
    assessment_session_id: str | None
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
    # Extended, all-optional binding fields — see `understanding_scope.py`
    # and `reviewed_understanding_signals.py` for the persistence adapter
    # that populates these. `assessment_session_id` above is deliberately
    # widened to `str | None`: the `/problem-understanding` scope kind has
    # no assessment session and instead carries `understanding_run_ref`.
    understanding_run_ref: str | None = None
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
        assessment_scope = self.scope_ref.endswith("/assessment")
        problem_scope = self.scope_ref.endswith("/problem-understanding")
        if not (
            assessment_scope
            and self.assessment_session_id is not None
            and self.assessment_session_id.strip()
            and self.understanding_run_ref is None
            or problem_scope
            and self.assessment_session_id is None
            and self.understanding_run_ref is not None
            and self.understanding_run_ref.strip()
        ):
            raise AssessmentValidationError("understanding_scope_binding_invalid")
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
        assessment_session_id: str | None,
        human_gate_receipt_ref: str,
        understanding_run_ref: str | None = None,
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


@dataclass(frozen=True, slots=True)
class DecideViewedUnderstandingInput:
    """Command for `AssessmentGrowthIntentHandoff.decide` — the newer,
    session-or-run-scoped entry point. Unlike `DecideGrowthHypothesisCommand`
    in `growth_hypothesis_commands.py`, this command carries the full
    reviewed-draft binding directly (no separate repository lookup for
    hypothesis evidence) and is scope-agnostic: it works for both the
    `/assessment` and `/problem-understanding` scope kinds.
    """

    tenant_id: str
    family_id: str
    actor_id: str
    actor_type: Literal["FAMILY_GUARDIAN", "FAMILY_MEMBER", "OPERATOR", "AI"]
    assessment_session_id: str | None
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
    understanding_run_ref: str | None = None


@dataclass(frozen=True, slots=True)
class UnderstandingDecisionReceipt:
    action: Literal["CONFIRM_UNDERSTANDING", "DISMISS_UNDERSTANDING"]
    outcome: Literal["INTENT_CREATED", "NO_ACTION"]
    signal_ref: str
    signal_version: int
    scope_ref: str
    human_gate_receipt_ref: str
    intent: GrowthIntentReceipt | None


class AssessmentGrowthIntentHandoff:
    """Scope-agnostic use case: confirm/dismiss a guardian-reviewed
    understanding signal without ever re-running AI or interpretation.

    This is additive to, and does not replace, `GrowthHypothesisCommandHandler`
    in `growth_hypothesis_commands.py` — that handler remains the sole
    R9-enforcing (`PolicyEngine`, `human_only=True`) caller wired into the
    legacy `/assessment`-only HTTP surface via `production_growth_wiring
    .ProductionGrowthConfirmationWiring`. `AssessmentGrowthIntentHandoff` is a
    new, narrower entry point for callers (e.g. a future `/problem-understanding`
    surface) that already hold a fully-formed, actor-typed command and do not
    need the idempotent-replay/audit-outbox persistence
    `GrowthHypothesisCommandHandler` layers on top via `AssessmentRepositoryPort`.
    """

    def __init__(
        self,
        signal_reader: ViewedUnderstandingSignalReaderPort,
        growth_intents: GrowthIntentConfirmationPort,
    ) -> None:
        self._signal_reader = signal_reader
        self._growth_intents = growth_intents

    async def decide(
        self, command: DecideViewedUnderstandingInput
    ) -> UnderstandingDecisionReceipt:
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
            understanding_run_ref=command.understanding_run_ref,
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


__all__ = [
    "AssessmentGrowthIntentHandoff",
    "ConfirmGrowthIntentInput",
    "DecideViewedUnderstandingInput",
    "GrowthIntentConfirmationPort",
    "GrowthIntentReceipt",
    "GuardianDecisionType",
    "HumanGateEffectiveStatus",
    "UnderstandingDecisionReceipt",
    "ViewedUnderstandingSignal",
    "ViewedUnderstandingSignalReaderPort",
]
