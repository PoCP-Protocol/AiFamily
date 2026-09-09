"""Port of `GrowthHypothesisService.decide` (growth-hypothesis.service.ts),
extended for ADR-0158 Slice A's `FAMILY_DECISION` node: a guardian may
CONFIRM, EDIT, PARTIAL-accept, DISMISS, or defer (LATER) a growth
hypothesis. Per decision type:

- CONFIRM: bridges to the `growth_intents` table with
  `boundary='HUMAN_CONFIRMED_INTENT_NOT_OUTCOME'` — the Named Action
  boundary the migration plan (section 6/10) requires: AI Runtime output
  (the hypothesis draft) never writes canonical state directly; only a
  human-confirmed decision does. `goal_text` is the AI's evidence
  description, unedited.
- EDIT: the guardian rewrote the understanding statement (carried as
  `parent_note`) and is confirming *that* rewritten statement, not the AI's
  original draft. This is still a real commitment — it also bridges to
  `growth_intents` with the same boundary, but `goal_text` is the guardian's
  own words (`parent_note`) rather than the AI's evidence description. R9
  (human-only) applies exactly as it does to CONFIRM: a rewritten-and-adopted
  understanding is as much a commitment as an as-is one.
- PARTIAL: the guardian accepts only part of the hypothesis. This is
  deliberately *not* a commitment — no `growth_intents` row is created,
  because a partial acceptance does not name a single, well-formed goal the
  household is signing up for. It is recorded as an audited fact only
  (`outcome=FEEDBACK_RECORDED`), carrying `parent_note` if the guardian said
  which part. R9 does not gate this path: no canonical write happens.
- LATER: the guardian is deferring, not accepting or rejecting. No
  `growth_intents` row, no interpretation re-run — this produces the
  smallest possible fact ("deferred, ask again"), not a rejection. R9 does
  not gate this path either.
- DISMISS: unchanged — the guardian rejects the hypothesis; no intent.

R9 enforcement (`PolicyEngine`, `human_only=True`): `assert_tenant_family_scope`
alone only proves the actor belongs to the family; it says nothing about
*what kind* of actor is confirming. A person_id with a GUARDIAN-shaped
membership row can belong to an AI/SYSTEM service account exactly as easily
as to a human guardian — `assert_tenant_family_scope` cannot tell the two
apart, because it never asked. `command.actor_type` (the caller's *real*,
server-derived identity — never inferred from the confirmation itself) is
what makes that distinction possible, and `_authorize_confirmation` below is
the single place that consults it before any hypothesis, evidence or intent
write happens — for both CONFIRM and EDIT, the two decision types that can
produce a `growth_intents` row.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Literal

from backend.platform.authorization.policy import Decision, PolicyEngine, PolicyRule
from backend.platform.identity.context import ActorContext
from backend.platform.identity.context import ActorType as PlatformActorType
from backend.platform.identity.directory import TenantContext, TenantDirectory, TenantStatus

from ..domain.errors import (
    AssessmentConflictError,
    AssessmentForbiddenError,
    AssessmentNotFoundError,
    AssessmentValidationError,
)
from ..domain.value_objects import GROWTH_INTENT_BOUNDARY, GrowthHypothesisDecisionType
from .growth_intent_handoff import (
    ConfirmGrowthIntentInput,
    GrowthIntentConfirmationPort,
    ViewedUnderstandingSignalReaderPort,
)
from .ports import AssessmentInterpretationPort, AssessmentRepositoryPort
from .queries import _map_hypothesis

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$", re.IGNORECASE
)

CONFIRM_GROWTH_HYPOTHESIS_ACTION = "CONFIRM_GROWTH_HYPOTHESIS"
GROWTH_HYPOTHESIS_RESOURCE_TYPE = "growth_hypothesis_decision"


def _is_uuid(value: str) -> bool:
    return bool(_UUID_RE.match(value))


def _hash_request(value: dict) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode("utf-8")).hexdigest()


def _outcome_for(
    decision_type: GrowthHypothesisDecisionType,
) -> Literal["INTENT_CREATED", "FEEDBACK_RECORDED", "NO_ACTION"]:
    """Maps decision_type to the receipt's `outcome` — the guardian-facing
    signal of *what actually happened*, independent of `action`/`decision_type`
    naming. CONFIRM/EDIT commit a `growth_intents` row (INTENT_CREATED).
    PARTIAL records an audited fact with no canonical write
    (FEEDBACK_RECORDED) — neither a rejection nor a commitment. DISMISS and
    LATER both leave no trace beyond the decision record itself (NO_ACTION):
    LATER is a deferral, not a rejection, but it is equally "no action taken
    on the hypothesis" from the growth-intent's point of view — the
    `decision_type` field (persisted verbatim) is what distinguishes a
    deferral from a rejection on replay/audit, not `outcome`.
    """

    if decision_type in _INTENT_CREATING_DECISIONS:
        return "INTENT_CREATED"
    if decision_type == "PARTIAL":
        return "FEEDBACK_RECORDED"
    return "NO_ACTION"


class _AlreadyScopedTenantDirectory(TenantDirectory):
    """Reports exactly one tenant as ACTIVE: the one this command already
    proved membership for via `assert_tenant_family_scope`.

    `PolicyEngine.check` requires a `TenantDirectory` to answer its own,
    separate "is this tenant active" veto (see `policy.py`'s module
    docstring). Assessment does not otherwise have — and this change does not
    introduce — a second, independent tenant-lifecycle store: by the time
    `_authorize_confirmation` runs, `assert_tenant_family_scope` has *already*
    fail-closed on an unknown or inactive tenant/family binding using
    Assessment's own repository-backed check. This directory exists only so
    `PolicyEngine`'s `human_only` veto — the actual R9 enforcement point this
    module needs — is reachable without asking the engine to re-derive a
    tenant status Assessment already established through a different,
    already-fail-closed path.
    """

    def __init__(self, tenant_id: str) -> None:
        self._tenant_id = tenant_id

    def resolve(self, tenant_id: str) -> TenantContext | None:
        if tenant_id != self._tenant_id:
            return None
        return TenantContext(tenant_id=tenant_id, status=TenantStatus.ACTIVE)


def build_growth_confirmation_policy_engine(tenant_id: str) -> PolicyEngine:
    """One-off `PolicyEngine` scoped to `tenant_id`, registering the single
    `human_only=True` rule R9 requires for confirming a growth hypothesis.

    A fresh engine per call is deliberate and cheap (one list append): it
    keeps the human_only rule's registration next to its own tenant scope
    instead of depending on a shared, mutable, module-level engine that every
    caller must remember to register onto correctly.
    """

    engine = PolicyEngine(_AlreadyScopedTenantDirectory(tenant_id))
    engine.register(
        PolicyRule(
            action=CONFIRM_GROWTH_HYPOTHESIS_ACTION,
            resource_type=GROWTH_HYPOTHESIS_RESOURCE_TYPE,
            allowed_actor_types=frozenset({PlatformActorType.HUMAN}),
            human_only=True,
        )
    )
    return engine


@dataclass(frozen=True)
class DecideGrowthHypothesisCommand:
    family_id: str
    tenant_id: str
    actor_id: str
    assessment_session_id: str
    hypothesis_ref: str
    decision_type: GrowthHypothesisDecisionType
    correlation_id: str
    idempotency_key: str
    # The caller's real, server-derived identity — e.g. from a bearer-token
    # principal or a service-to-service credential. Never inferred from the
    # confirmation payload itself, and never hardcoded to a human role: see
    # the module docstring and `_authorize_confirmation`.
    actor_type: PlatformActorType = PlatformActorType.HUMAN
    # Optional Human-Gate-reviewed-draft binding. Only meaningful when this
    # handler is constructed with `viewed_signals`/`growth_intents` (the
    # canonical-outbox-backed confirmation path); ignored by the legacy
    # evidence/interpretation path below.
    scope_ref: str = ""
    signal_version: int = 0
    reviewed_draft_ref: str = ""
    draft_version: int = 0
    provenance_ref: str = ""
    human_gate_receipt_ref: str = ""
    # ADR-0158 Slice A: free-text guardian note. For EDIT this *is* the
    # rewritten understanding statement the guardian is confirming instead
    # of the AI's draft (becomes `growth_intents.goal_text`); for PARTIAL it
    # optionally records which part the guardian accepted; for LATER it may
    # record why the guardian is deferring. Never interpreted as structured
    # input to the AI Runtime — see module docstring.
    parent_note: str = ""


_INTENT_CREATING_DECISIONS = frozenset({"CONFIRM", "EDIT"})
_NON_COMMITTING_DECISIONS = frozenset({"PARTIAL", "LATER"})
_GROWTH_HYPOTHESIS_DECISION_TYPES = frozenset(
    {"CONFIRM", "EDIT", "PARTIAL", "DISMISS", "LATER"}
)


def _authorize_confirmation(actor_id: str, actor_type: PlatformActorType, tenant_id: str) -> None:
    """R9 gate: only a HUMAN actor may confirm a growth hypothesis.

    `assert_tenant_family_scope` (called by `decide` immediately before this)
    proves the actor is a recognized member of the family; it is silent on
    *what kind* of actor that membership row represents. This is the seam
    that makes "an AI/SYSTEM service account holding a person_id with a
    GUARDIAN-shaped membership" indistinguishable from "a family_guardian
    confirming their own reviewed understanding" — until this check runs.

    `PolicyEngine`'s `human_only` veto is unconditional and order-independent
    (see `policy.py`): even if this action's rule set somehow also allowed AI
    or SYSTEM actor types, the veto still denies them. This call is the R9
    enforcement point for `GROWTH_CONFIRM_INTENT`; there must be exactly one.
    """

    actor = ActorContext(
        actor_id=actor_id,
        actor_type=actor_type,
        tenant_id=tenant_id,
        correlation_id=actor_id,
    )
    engine = build_growth_confirmation_policy_engine(tenant_id)
    decision: Decision = engine.check(
        actor, CONFIRM_GROWTH_HYPOTHESIS_ACTION, GROWTH_HYPOTHESIS_RESOURCE_TYPE
    )
    if not decision.allowed:
        raise AssessmentForbiddenError("growth_hypothesis_confirmation_requires_human_actor")


class GrowthHypothesisCommandHandler:
    def __init__(
        self,
        repository: AssessmentRepositoryPort,
        interpretation_or_viewed_signals: AssessmentInterpretationPort
        | ViewedUnderstandingSignalReaderPort,
        growth_intents: GrowthIntentConfirmationPort | None = None,
    ):
        self._repository = repository
        # `production_growth_wiring.ProductionGrowthConfirmationWiring` passes
        # a `ViewedUnderstandingSignalReaderPort` plus `growth_intents`; the
        # legacy in-process evidence/interpretation callers pass only an
        # `AssessmentInterpretationPort`. Both shapes only need `.interpret`
        # or `.load_viewed_signal` respectively, so the constructor accepts
        # either without a second public constructor.
        self._interpretation_or_viewed_signals = interpretation_or_viewed_signals
        self._growth_intents = growth_intents

    async def decide(self, command: DecideGrowthHypothesisCommand) -> dict:
        if not command.idempotency_key or not command.idempotency_key.strip():
            raise AssessmentValidationError("idempotency_key_required")
        if (
            not _is_uuid(command.assessment_session_id)
            or not command.hypothesis_ref.strip()
            or command.decision_type not in _GROWTH_HYPOTHESIS_DECISION_TYPES
        ):
            raise AssessmentValidationError("valid_hypothesis_decision_required")
        if command.decision_type == "EDIT" and not command.parent_note.strip():
            # EDIT means the guardian is confirming a *rewritten* statement —
            # without that rewritten text there is nothing to confirm instead
            # of the AI's draft, and this must not silently fall back to
            # confirming the unedited draft under a different label.
            raise AssessmentValidationError("edit_decision_requires_parent_note")

        action: Literal[
            "CONFIRM_GROWTH_HYPOTHESIS",
            "CALIBRATE_GROWTH_HYPOTHESIS",
            "DISMISS_GROWTH_HYPOTHESIS",
        ]
        if command.decision_type == "CONFIRM":
            action = "CONFIRM_GROWTH_HYPOTHESIS"
        elif command.decision_type in ("EDIT", "PARTIAL"):
            action = "CALIBRATE_GROWTH_HYPOTHESIS"
        else:  # DISMISS, LATER
            action = "DISMISS_GROWTH_HYPOTHESIS"
        request_hash = _hash_request(
            {
                "assessment_session_id": command.assessment_session_id,
                "hypothesis_ref": command.hypothesis_ref,
                "decision_type": command.decision_type,
                "scope_ref": command.scope_ref,
                "signal_version": command.signal_version,
                "reviewed_draft_ref": command.reviewed_draft_ref,
                "draft_version": command.draft_version,
                "provenance_ref": command.provenance_ref,
                "human_gate_receipt_ref": command.human_gate_receipt_ref,
                "parent_note": command.parent_note,
            }
        )

        await self._repository.lock_hypothesis_decision(
            command.tenant_id, command.family_id, command.hypothesis_ref
        )
        replay = await self._repository.load_hypothesis_decision_replay(
            command.tenant_id, command.family_id, command.decision_type, command.idempotency_key
        )
        if replay is not None:
            if replay.get("request_hash") != request_hash:
                raise AssessmentConflictError("idempotency_key_payload_mismatch")
            return {**replay["response_body"], "replayed": True}

        await self._repository.assert_tenant_family_scope(
            command.tenant_id, command.family_id, command.actor_id
        )
        # R9: only a HUMAN actor may confirm — checked right after the
        # ordinary family-membership scope check and before any evidence,
        # signal or intent read/write. Gates both decision types that can
        # produce a `growth_intents` row (CONFIRM and EDIT); PARTIAL/LATER/
        # DISMISS never write a canonical intent, so they are not gated
        # here. See `_authorize_confirmation`.
        if command.decision_type in _INTENT_CREATING_DECISIONS:
            _authorize_confirmation(command.actor_id, command.actor_type, command.tenant_id)

        if self._growth_intents is not None:
            return await self._decide_via_growth_intent_confirmation(command, action, request_hash)
        return await self._decide_via_legacy_evidence_interpretation(
            command, action, request_hash
        )

    async def _decide_via_legacy_evidence_interpretation(
        self,
        command: DecideGrowthHypothesisCommand,
        action: Literal[
            "CONFIRM_GROWTH_HYPOTHESIS",
            "CALIBRATE_GROWTH_HYPOTHESIS",
            "DISMISS_GROWTH_HYPOTHESIS",
        ],
        request_hash: str,
    ) -> dict:
        # The evidence contains the child's response set. Check the current
        # purpose grant before handing it to the interpretation runtime; a
        # repository implementation or cache must not turn a withdrawn grant
        # into an AI input.
        evidence = await self._repository.load_hypothesis_evidence(
            command.family_id, command.tenant_id, command.assessment_session_id
        )
        if evidence is None:
            raise AssessmentNotFoundError("growth_hypothesis_not_found")

        await self._repository.assert_subject_consent(
            command.family_id, evidence.subject_person_id, "ASSESSMENT"
        )
        interpretation = await self._interpretation_or_viewed_signals.interpret(
            command.family_id, evidence, "DEEP_AI_INTERPRETATION"
        )
        hypothesis = _map_hypothesis(evidence, interpretation)
        if hypothesis["hypothesis_ref"] != command.hypothesis_ref:
            raise AssessmentConflictError("growth_hypothesis_reference_mismatch")

        intent: dict | None = None
        if command.decision_type in _INTENT_CREATING_DECISIONS:
            # EDIT: the guardian's own rewritten statement (`parent_note`)
            # becomes the intent's goal text instead of the AI's evidence
            # description — the commitment is to what the family actually
            # said, not to the unedited draft. CONFIRM keeps the AI's
            # description verbatim.
            goal_text = (
                command.parent_note.strip()
                if command.decision_type == "EDIT"
                else evidence.description
            )
            intent = await self._repository.load_or_create_growth_intent(
                family_id=command.family_id,
                subject_person_id=evidence.subject_person_id,
                need_type=evidence.need_type_ref,
                goal_text=goal_text,
                required_capability_keys=evidence.required_capability_keys,
                confirmed_by=command.actor_id,
                source_ref=hypothesis["hypothesis_ref"],
                evidence_refs=[evidence.assessment_evidence_id],
            )
            assert intent.get("boundary", GROWTH_INTENT_BOUNDARY) == GROWTH_INTENT_BOUNDARY

        receipt = {
            "action": action,
            "outcome": _outcome_for(command.decision_type),
            "hypothesis_ref": hypothesis["hypothesis_ref"],
            "intent": intent,
            "replayed": False,
            "parent_note": command.parent_note.strip() or None,
        }
        await self._repository.persist_hypothesis_decision(
            tenant_id=command.tenant_id,
            family_id=command.family_id,
            session_id=evidence.assessment_session_id,
            hypothesis_ref=hypothesis["hypothesis_ref"],
            decision_type=command.decision_type,
            actor_id=command.actor_id,
            intent_id=intent["intent_id"] if intent else None,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
            receipt=receipt,
            correlation_id=command.correlation_id,
        )
        return receipt

    async def _decide_via_growth_intent_confirmation(
        self,
        command: DecideGrowthHypothesisCommand,
        action: Literal[
            "CONFIRM_GROWTH_HYPOTHESIS",
            "CALIBRATE_GROWTH_HYPOTHESIS",
            "DISMISS_GROWTH_HYPOTHESIS",
        ],
        request_hash: str,
    ) -> dict:
        """Canonical path: a Human-Gate-reviewed signal, confirmed through
        the Growth-owned `GrowthIntentConfirmationPort` (atomic outbox write).

        Requires the handler to have been constructed with a
        `ViewedUnderstandingSignalReaderPort` and a `GrowthIntentConfirmationPort`
        (see `production_growth_wiring.ProductionGrowthConfirmationWiring`).
        """

        signal = await self._interpretation_or_viewed_signals.load_viewed_signal(
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
            signal.signal_ref != command.hypothesis_ref
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

        await self._repository.assert_subject_consent(
            command.family_id, signal.subject_person_id, "ASSESSMENT"
        )

        intent: dict | None = None
        if command.decision_type in _INTENT_CREATING_DECISIONS:
            assert self._growth_intents is not None
            # EDIT: the guardian's rewritten statement (`parent_note`)
            # replaces the reviewed signal's `goal_text` as the commitment
            # being made — see module docstring. CONFIRM keeps the signal's
            # goal_text verbatim.
            goal_text = (
                command.parent_note.strip()
                if command.decision_type == "EDIT"
                else signal.goal_text
            )
            receipt_obj = await self._growth_intents.confirm_growth_intent(
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
                    goal_text=goal_text,
                    required_capability_keys=signal.required_capability_keys,
                    evidence_refs=signal.evidence_refs,
                    correlation_id=command.correlation_id,
                    idempotency_key=command.idempotency_key,
                )
            )
            if receipt_obj.boundary != GROWTH_INTENT_BOUNDARY:
                raise AssessmentConflictError("growth_intent_receipt_signal_mismatch")
            intent = {
                "intent_id": receipt_obj.intent_id,
                "need_type": signal.need_type,
                "status": "OPEN",
                "required_capability_keys": list(signal.required_capability_keys),
                "evidence_refs": list(signal.evidence_refs),
                "boundary": receipt_obj.boundary,
            }

        receipt = {
            "action": action,
            "outcome": _outcome_for(command.decision_type),
            "hypothesis_ref": signal.signal_ref,
            "intent": intent,
            "replayed": False,
            "parent_note": command.parent_note.strip() or None,
        }
        await self._repository.persist_hypothesis_decision(
            tenant_id=command.tenant_id,
            family_id=command.family_id,
            session_id=signal.assessment_session_id,
            hypothesis_ref=signal.signal_ref,
            decision_type=command.decision_type,
            actor_id=command.actor_id,
            intent_id=intent["intent_id"] if intent else None,
            idempotency_key=command.idempotency_key,
            request_hash=request_hash,
            receipt=receipt,
            correlation_id=command.correlation_id,
        )
        return receipt


__all__ = [
    "CONFIRM_GROWTH_HYPOTHESIS_ACTION",
    "GROWTH_HYPOTHESIS_RESOURCE_TYPE",
    "DecideGrowthHypothesisCommand",
    "GrowthHypothesisCommandHandler",
    "build_growth_confirmation_policy_engine",
]
