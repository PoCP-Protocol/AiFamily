"""S01 vertical slice: assessment signal to action readback.

The assessment domain owns the submitted-session and evidence facts.  This
module only consumes a scoped signal through ``AssessmentSignalPort`` and
turns the AI interpretation into a reviewable draft.  A human decision is
required before a growth intent is issued, and the existing
``GrowthOutcomeLoop`` remains the sole writer for action facts and challenge
reviews.

This is an in-memory contract adapter for development/test fixtures.  It does
not replace assessment's PostgreSQL repository, the Model Gateway, or the
service outbox.  The same commands and refusal semantics must be retained by
the production adapter.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from typing import Protocol
from uuid import uuid4

from backend.platform.consent import ConsentGate, ConsentGrant, ConsentPurpose

from ..domain.errors import (
    JourneyConflictError,
    JourneyForbiddenError,
    JourneyNotFoundError,
    JourneyValidationError,
)
from .outcome_loop import (
    ActionFact,
    ActionFactStatus,
    ChallengeDecision,
    ChallengeReview,
    GrowthOutcomeLoop,
)

_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    re.IGNORECASE,
)
_FORBIDDEN_FACT_KEYS = {"score", "rank", "ranking", "level", "percentile"}


class HypothesisDecision(StrEnum):
    CONFIRM = "CONFIRM"
    DISMISS = "DISMISS"


class HypothesisStatus(StrEnum):
    PROPOSED = "PROPOSED"
    CONFIRMED = "CONFIRMED"
    DISMISSED = "DISMISSED"


class AuditEventName(StrEnum):
    SIGNAL_ACCEPTED = "AssessmentSignalAccepted"
    PERSPECTIVE_DRAFTED = "GrowthPerspectiveDrafted"
    HYPOTHESIS_DRAFTED = "GrowthHypothesisDrafted"
    HYPOTHESIS_CONFIRMED = "GrowthHypothesisConfirmed"
    HYPOTHESIS_DISMISSED = "GrowthHypothesisDismissed"
    ACTION_RECORDED = "ActionFactRecorded"
    PROCESS_READBACK = "ProcessReadbackGenerated"
    CHALLENGE_CLOSED = "ChallengeClosed"


@dataclass(frozen=True)
class AssessmentSignal:
    signal_id: str
    tenant_id: str
    family_id: str
    subject_ref: str
    assessment_session_id: str
    evidence_refs: tuple[str, ...]
    summary: str
    captured_at: datetime
    locale: str


@dataclass(frozen=True)
class PerspectiveDraft:
    perspective_id: str
    signal_id: str
    tenant_id: str
    family_id: str
    subject_ref: str
    summary: str
    source_refs: tuple[str, ...]
    limitations: tuple[str, ...]
    status: str = "DRAFT"
    locale: str = "zh-CN"


@dataclass(frozen=True)
class HypothesisDraft:
    hypothesis_id: str
    perspective_id: str
    tenant_id: str
    family_id: str
    subject_ref: str
    statement: str
    source_refs: tuple[str, ...]
    limitations: tuple[str, ...]
    status: HypothesisStatus = HypothesisStatus.PROPOSED
    locale: str = "zh-CN"


@dataclass(frozen=True)
class GrowthIntentCommand:
    intent_id: str
    hypothesis_id: str
    tenant_id: str
    family_id: str
    subject_ref: str
    requested_by: str
    next_task_ref: str
    boundary: str = "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"
    locale: str = "zh-CN"


@dataclass(frozen=True)
class ActionTaskCommand:
    task_ref: str
    intent_id: str
    tenant_id: str
    family_id: str
    subject_ref: str
    day_number: int
    title: str
    issued_by: str
    locale: str = "zh-CN"


@dataclass(frozen=True)
class ProcessReadback:
    readback_id: str
    tenant_id: str
    family_id: str
    plan_id: str
    action_ids: tuple[str, ...]
    observations: tuple[str, ...]
    limitations: tuple[str, ...]
    status: str = "DRAFT"
    locale: str = "zh-CN"


@dataclass(frozen=True)
class S01AuditEvent:
    event_id: str
    name: AuditEventName
    tenant_id: str
    family_id: str
    actor_id: str
    subject_ref: str | None
    correlation_id: str
    idempotency_key: str
    source_ref: str
    created_at: datetime


class AssessmentSignalPort(Protocol):
    """Read-only boundary from assessment to the journey slice."""

    def load_submitted_signal(
        self, *, tenant_id: str, family_id: str, assessment_session_id: str
    ) -> AssessmentSignal | None: ...


class InMemoryAssessmentSignalPort:
    """Fixture-only signal source with tenant/family scope enforcement."""

    production_ready = False

    def __init__(self, signals: Iterable[AssessmentSignal] = ()) -> None:
        self._signals = {signal.signal_id: signal for signal in signals}

    def add(self, signal: AssessmentSignal) -> None:
        self._signals[signal.signal_id] = signal

    def load_submitted_signal(
        self, *, tenant_id: str, family_id: str, assessment_session_id: str
    ) -> AssessmentSignal | None:
        return next(
            (
                signal
                for signal in self._signals.values()
                if signal.tenant_id == tenant_id
                and signal.family_id == family_id
                and signal.assessment_session_id == assessment_session_id
            ),
            None,
        )


class S01VerticalSlice:
    """Application contract for S01 with explicit command/audit boundaries."""

    production_ready = False

    def __init__(
        self,
        *,
        signal_port: AssessmentSignalPort,
        outcome_loop: GrowthOutcomeLoop,
        consent_loader: Callable[[str, ConsentPurpose], Iterable[ConsentGrant]] | None = None,
        now: Callable[[], datetime] | None = None,
        locale: str = "zh-CN",
    ) -> None:
        if not locale.strip() or len(locale) > 32:
            raise JourneyValidationError("invalid_locale")
        self._signal_port = signal_port
        self._outcome_loop = outcome_loop
        self._consent_loader = consent_loader or (lambda _subject, _purpose: ())
        self._now = now or (lambda: datetime.now(UTC))
        self._locale = locale
        self._signals: dict[str, AssessmentSignal] = {}
        self._perspectives: dict[str, PerspectiveDraft] = {}
        self._hypotheses: dict[str, HypothesisDraft] = {}
        self._intents: dict[str, GrowthIntentCommand] = {}
        self._tasks: dict[str, ActionTaskCommand] = {}
        self._readbacks: dict[str, ProcessReadback] = {}
        self._decisions: dict[str, HypothesisDecision] = {}
        self._idempotency: dict[tuple[str, str, str, str], tuple[tuple[object, ...], object]] = {}
        self.audit_events: list[S01AuditEvent] = []

    def accept_signal(
        self,
        *,
        tenant_id: str,
        family_id: str,
        assessment_session_id: str,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> AssessmentSignal:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key, correlation_id)
        self._assert_uuid(assessment_session_id, "assessment_session_id")
        signal = self._signal_port.load_submitted_signal(
            tenant_id=tenant_id,
            family_id=family_id,
            assessment_session_id=assessment_session_id,
        )
        if signal is None:
            raise JourneyNotFoundError("submitted_assessment_signal_not_found")
        self._assert_scope(signal, tenant_id, family_id)
        if not signal.summary.strip() or not signal.evidence_refs:
            raise JourneyValidationError("signal_summary_and_evidence_required")
        self._assert_record_payload(signal.summary)
        self._assert_live_consent(signal.subject_ref, ConsentPurpose.ASSESSMENT)
        fingerprint = (assessment_session_id, actor_id)
        replay = self._replay("accept_signal", tenant_id, family_id, idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        self._signals[signal.signal_id] = signal
        self._append_event(
            AuditEventName.SIGNAL_ACCEPTED,
            tenant_id,
            family_id,
            actor_id,
            signal.subject_ref,
            correlation_id,
            idempotency_key,
            signal.signal_id,
        )
        self._remember("accept_signal", tenant_id, family_id, idempotency_key, fingerprint, signal)
        return signal

    def draft_hypothesis(
        self,
        *,
        signal: AssessmentSignal,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
        statement: str | None = None,
        limitations: tuple[str, ...] = (),
    ) -> HypothesisDraft:
        self._validate_scope(
            signal.tenant_id,
            signal.family_id,
            actor_id,
            idempotency_key,
            correlation_id,
        )
        accepted_signal = self._signals.get(signal.signal_id)
        if accepted_signal is None:
            raise JourneyNotFoundError("assessment_signal_not_accepted")
        if accepted_signal != signal:
            raise JourneyConflictError("assessment_signal_snapshot_conflict")
        self._assert_record_payload(signal.summary)
        self._assert_live_consent(signal.subject_ref, ConsentPurpose.AI_PERSONALIZATION)
        if not signal.evidence_refs:
            raise JourneyValidationError("signal_evidence_required")
        text = (statement or f"可先从‘{signal.summary}’这一线索开始观察").strip()
        if not text:
            raise JourneyValidationError("hypothesis_statement_required")
        fingerprint = (signal.signal_id, text, tuple(limitations), actor_id)
        replay = self._replay(
            "draft_hypothesis", signal.tenant_id, signal.family_id, idempotency_key, fingerprint
        )
        if replay is not None:
            return replay  # type: ignore[return-value]
        perspective = PerspectiveDraft(
            perspective_id=str(uuid4()),
            signal_id=signal.signal_id,
            tenant_id=signal.tenant_id,
            family_id=signal.family_id,
            subject_ref=signal.subject_ref,
            summary=signal.summary,
            source_refs=signal.evidence_refs,
            limitations=("NOT_DIAGNOSIS", *limitations),
            locale=self._locale,
        )
        hypothesis = HypothesisDraft(
            hypothesis_id=str(uuid4()),
            perspective_id=perspective.perspective_id,
            tenant_id=signal.tenant_id,
            family_id=signal.family_id,
            subject_ref=signal.subject_ref,
            statement=text,
            source_refs=signal.evidence_refs,
            limitations=("NOT_DIAGNOSIS", "DRAFT_REQUIRES_FAMILY_DECISION", *limitations),
            locale=self._locale,
        )
        self._perspectives[perspective.perspective_id] = perspective
        self._hypotheses[hypothesis.hypothesis_id] = hypothesis
        self._append_event(
            AuditEventName.PERSPECTIVE_DRAFTED,
            signal.tenant_id,
            signal.family_id,
            actor_id,
            signal.subject_ref,
            correlation_id,
            idempotency_key,
            perspective.perspective_id,
        )
        self._append_event(
            AuditEventName.HYPOTHESIS_DRAFTED,
            signal.tenant_id,
            signal.family_id,
            actor_id,
            signal.subject_ref,
            correlation_id,
            idempotency_key,
            hypothesis.hypothesis_id,
        )
        self._remember(
            "draft_hypothesis",
            signal.tenant_id,
            signal.family_id,
            idempotency_key,
            fingerprint,
            hypothesis,
        )
        return hypothesis

    def decide_hypothesis(
        self,
        *,
        tenant_id: str,
        family_id: str,
        hypothesis_id: str,
        decision: HypothesisDecision,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
        next_task_ref: str = "task:today:first-step",
    ) -> GrowthIntentCommand | None:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key, correlation_id)
        self._assert_human_actor(actor_id)
        hypothesis = self._hypotheses.get(hypothesis_id)
        if hypothesis is None:
            raise JourneyNotFoundError("growth_hypothesis_not_found")
        self._assert_scope(hypothesis, tenant_id, family_id)
        self._assert_live_consent(hypothesis.subject_ref, ConsentPurpose.GROWTH_TRACKING)
        fingerprint = (hypothesis_id, decision.value, actor_id, next_task_ref)
        replay = self._replay(
            "decide_hypothesis", tenant_id, family_id, idempotency_key, fingerprint
        )
        if replay is not None:
            return None if replay is False else replay  # type: ignore[return-value]
        previous = self._decisions.get(hypothesis_id)
        if previous is not None and previous is not decision:
            raise JourneyConflictError("hypothesis_decision_conflict")
        if previous is not None and decision is HypothesisDecision.DISMISS:
            self._remember(
                "decide_hypothesis", tenant_id, family_id, idempotency_key, fingerprint, None
            )
            return None
        if previous is not None and decision is HypothesisDecision.CONFIRM:
            existing_intent = next(
                (item for item in self._intents.values() if item.hypothesis_id == hypothesis_id),
                None,
            )
            if existing_intent is None or existing_intent.next_task_ref != next_task_ref:
                raise JourneyConflictError("hypothesis_intent_conflict")
            self._remember(
                "decide_hypothesis",
                tenant_id,
                family_id,
                idempotency_key,
                fingerprint,
                existing_intent,
            )
            return existing_intent
        self._decisions[hypothesis_id] = decision
        if decision is HypothesisDecision.DISMISS:
            dismissed = HypothesisDraft(
                **{**hypothesis.__dict__, "status": HypothesisStatus.DISMISSED}
            )
            self._hypotheses[hypothesis_id] = dismissed
            self._append_event(
                AuditEventName.HYPOTHESIS_DISMISSED,
                tenant_id,
                family_id,
                actor_id,
                hypothesis.subject_ref,
                correlation_id,
                idempotency_key,
                hypothesis_id,
            )
            self._remember(
                "decide_hypothesis", tenant_id, family_id, idempotency_key, fingerprint, None
            )
            return None
        confirmed = HypothesisDraft(**{**hypothesis.__dict__, "status": HypothesisStatus.CONFIRMED})
        self._hypotheses[hypothesis_id] = confirmed
        intent = GrowthIntentCommand(
            intent_id=str(uuid4()),
            hypothesis_id=hypothesis_id,
            tenant_id=tenant_id,
            family_id=family_id,
            subject_ref=hypothesis.subject_ref,
            requested_by=actor_id,
            next_task_ref=next_task_ref,
            locale=self._locale,
        )
        task = ActionTaskCommand(
            task_ref=next_task_ref,
            intent_id=intent.intent_id,
            tenant_id=tenant_id,
            family_id=family_id,
            subject_ref=hypothesis.subject_ref,
            day_number=1,
            title="从今天的一件小行动开始",
            issued_by=actor_id,
            locale=self._locale,
        )
        self._intents[intent.intent_id] = intent
        self._tasks[task.task_ref] = task
        self._append_event(
            AuditEventName.HYPOTHESIS_CONFIRMED,
            tenant_id,
            family_id,
            actor_id,
            hypothesis.subject_ref,
            correlation_id,
            idempotency_key,
            hypothesis_id,
        )
        self._remember(
            "decide_hypothesis", tenant_id, family_id, idempotency_key, fingerprint, intent
        )
        return intent

    def record_today_action(
        self,
        *,
        tenant_id: str,
        family_id: str,
        intent_id: str,
        plan_id: str,
        task_ref: str,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
        status: ActionFactStatus = ActionFactStatus.COMPLETED,
        evidence_refs: tuple[str, ...] = (),
    ) -> ActionFact:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key, correlation_id)
        self._assert_human_actor(actor_id)
        intent = self._intents.get(intent_id)
        if intent is None:
            raise JourneyNotFoundError("growth_intent_not_found")
        self._assert_scope(intent, tenant_id, family_id)
        task = self._tasks.get(task_ref)
        if task is None or task.intent_id != intent_id:
            raise JourneyConflictError("today_task_not_bound_to_intent")
        self._assert_live_consent(intent.subject_ref, ConsentPurpose.GROWTH_TRACKING)
        fingerprint = (
            intent_id,
            plan_id,
            task_ref,
            status.value,
            tuple(evidence_refs),
            actor_id,
        )
        replay = self._replay(
            "record_today_action", tenant_id, family_id, idempotency_key, fingerprint
        )
        if replay is not None:
            return replay  # type: ignore[return-value]
        action = self._outcome_loop.record_action(
            tenant_id=tenant_id,
            family_id=family_id,
            plan_id=plan_id,
            task_id=task_ref,
            day_number=task.day_number,
            status=status,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            evidence_refs=evidence_refs,
        )
        self._append_event(
            AuditEventName.ACTION_RECORDED,
            tenant_id,
            family_id,
            actor_id,
            intent.subject_ref,
            correlation_id,
            idempotency_key,
            action.action_id,
        )
        self._remember(
            "record_today_action", tenant_id, family_id, idempotency_key, fingerprint, action
        )
        return action

    def readback(
        self,
        *,
        tenant_id: str,
        family_id: str,
        plan_id: str,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> ProcessReadback:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key, correlation_id)
        snapshot = self._outcome_loop.snapshot(tenant_id=tenant_id, family_id=family_id)
        actions = tuple(action for action in snapshot.actions if action.plan_id == plan_id)
        fingerprint = (plan_id, actor_id)
        replay = self._replay("readback", tenant_id, family_id, idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        observations = tuple(
            "已记录一次可回读的家庭行动事实" if actions else "暂未记录该计划的行动事实",
        )
        limitations = ("PROCESS_NOT_OUTCOME", "NO_FAMILY_SCORE_OR_RANK")
        readback = ProcessReadback(
            readback_id=str(uuid4()),
            tenant_id=tenant_id,
            family_id=family_id,
            plan_id=plan_id,
            action_ids=tuple(action.action_id for action in actions),
            observations=observations,
            limitations=limitations,
            locale=self._locale,
        )
        self._append_event(
            AuditEventName.PROCESS_READBACK,
            tenant_id,
            family_id,
            actor_id,
            None,
            correlation_id,
            idempotency_key,
            readback.readback_id,
        )
        self._readbacks[readback.readback_id] = readback
        self._remember("readback", tenant_id, family_id, idempotency_key, fingerprint, readback)
        return readback

    def close_challenge(
        self,
        *,
        tenant_id: str,
        family_id: str,
        plan_id: str,
        decision: ChallengeDecision,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> ChallengeReview:
        self._validate_scope(tenant_id, family_id, actor_id, idempotency_key, correlation_id)
        self._assert_human_actor(actor_id)
        fingerprint = (plan_id, decision.value, actor_id)
        replay = self._replay("close_challenge", tenant_id, family_id, idempotency_key, fingerprint)
        if replay is not None:
            return replay  # type: ignore[return-value]
        review = self._outcome_loop.close_challenge(
            tenant_id=tenant_id,
            family_id=family_id,
            plan_id=plan_id,
            decision=decision,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
        )
        self._append_event(
            AuditEventName.CHALLENGE_CLOSED,
            tenant_id,
            family_id,
            actor_id,
            None,
            correlation_id,
            idempotency_key,
            review.review_id,
        )
        self._remember(
            "close_challenge", tenant_id, family_id, idempotency_key, fingerprint, review
        )
        return review

    def _assert_live_consent(self, subject_ref: str, purpose: ConsentPurpose) -> None:
        grants = tuple(self._consent_loader(subject_ref, purpose))
        if not ConsentGate.check(subject_ref, purpose, grants):
            raise JourneyForbiddenError("consent_required")

    def deletion_refs(self, *, tenant_id: str, family_id: str) -> tuple[str, ...]:
        """Return S01 handles for a future durable deletion cascade.

        The adapter owns only the S01 projections and audit envelope.  Action,
        challenge, outcome, story, service and annual handles stay owned by
        ``GrowthOutcomeLoop`` and are delegated to its canonical deletion
        contract.  Returning explicit handles here prevents a future delete
        implementation from silently dropping derived readbacks or evidence
        links.  This remains an in-memory contract until the durable worker is
        wired.
        """
        if not tenant_id.strip() or not family_id.strip():
            raise JourneyValidationError("tenant_and_family_required")
        refs = list(self._outcome_loop.deletion_refs(tenant_id=tenant_id, family_id=family_id))
        refs.extend(
            f"assessment-signal:{tenant_id}:{family_id}:{signal.signal_id}"
            for signal in self._signals.values()
            if signal.tenant_id == tenant_id and signal.family_id == family_id
        )
        refs.extend(
            f"s01:perspective:{tenant_id}:{family_id}:{perspective.perspective_id}"
            for perspective in self._perspectives.values()
            if perspective.tenant_id == tenant_id and perspective.family_id == family_id
        )
        refs.extend(
            f"s01:hypothesis:{tenant_id}:{family_id}:{hypothesis.hypothesis_id}"
            for hypothesis in self._hypotheses.values()
            if hypothesis.tenant_id == tenant_id and hypothesis.family_id == family_id
        )
        refs.extend(
            f"s01:intent:{tenant_id}:{family_id}:{intent.intent_id}"
            for intent in self._intents.values()
            if intent.tenant_id == tenant_id and intent.family_id == family_id
        )
        refs.extend(
            f"s01:task:{tenant_id}:{family_id}:{task.task_ref}"
            for task in self._tasks.values()
            if task.tenant_id == tenant_id and task.family_id == family_id
        )
        refs.extend(
            f"s01:readback:{tenant_id}:{family_id}:{readback.readback_id}"
            for readback in self._readbacks.values()
            if readback.tenant_id == tenant_id and readback.family_id == family_id
        )
        refs.extend(
            f"s01:audit:{tenant_id}:{family_id}:{event.event_id}"
            for event in self.audit_events
            if event.tenant_id == tenant_id and event.family_id == family_id
        )
        return tuple(sorted(set(refs)))

    def _append_event(
        self,
        name: AuditEventName,
        tenant_id: str,
        family_id: str,
        actor_id: str,
        subject_ref: str | None,
        correlation_id: str,
        idempotency_key: str,
        source_ref: str,
    ) -> None:
        self.audit_events.append(
            S01AuditEvent(
                event_id=str(uuid4()),
                name=name,
                tenant_id=tenant_id,
                family_id=family_id,
                actor_id=actor_id,
                subject_ref=subject_ref,
                correlation_id=correlation_id,
                idempotency_key=idempotency_key,
                source_ref=source_ref,
                created_at=self._timestamp(),
            )
        )

    def _timestamp(self) -> datetime:
        value = self._now()
        if value.tzinfo is None or value.utcoffset() is None:
            raise JourneyValidationError("timestamp_must_be_timezone_aware")
        return value.astimezone(UTC)

    def _replay(
        self,
        operation: str,
        tenant_id: str,
        family_id: str,
        key: str,
        fingerprint: tuple[object, ...],
    ) -> object | None:
        stored = self._idempotency.get((tenant_id, family_id, operation, key))
        if stored is None:
            return None
        if stored[0] != fingerprint:
            raise JourneyConflictError("idempotency_conflict")
        return stored[1]

    def _remember(
        self,
        operation: str,
        tenant_id: str,
        family_id: str,
        key: str,
        fingerprint: tuple[object, ...],
        value: object,
    ) -> None:
        self._idempotency[(tenant_id, family_id, operation, key)] = (fingerprint, value)

    def _validate_scope(
        self,
        tenant_id: str,
        family_id: str,
        actor_id: str,
        idempotency_key: str,
        correlation_id: str,
    ) -> None:
        if not all(value.strip() for value in (tenant_id, family_id, actor_id, correlation_id)):
            raise JourneyValidationError("scope_actor_and_correlation_required")
        if not idempotency_key.strip() or len(idempotency_key) > 128:
            raise JourneyValidationError("invalid_idempotency_key")

    @staticmethod
    def _assert_uuid(value: str, name: str) -> None:
        if not _UUID_RE.fullmatch(value):
            raise JourneyValidationError(f"{name}_must_be_uuid")

    @staticmethod
    def _assert_human_actor(actor_id: str) -> None:
        if actor_id.lower().startswith("ai:") or actor_id.upper() in {"AI", "SYSTEM"}:
            raise JourneyForbiddenError("human_confirmation_required")

    @staticmethod
    def _assert_record_payload(value: str) -> None:
        lowered = value.lower()
        if any(token in lowered for token in _FORBIDDEN_FACT_KEYS):
            raise JourneyValidationError("forbidden_score_or_rank_field")

    @staticmethod
    def _assert_scope(value: object, tenant_id: str, family_id: str) -> None:
        if (
            getattr(value, "tenant_id", None) != tenant_id
            or getattr(value, "family_id", None) != family_id
        ):
            raise JourneyForbiddenError("family_tenant_scope_violation")


__all__ = [
    "ActionTaskCommand",
    "AssessmentSignal",
    "AssessmentSignalPort",
    "AuditEventName",
    "GrowthIntentCommand",
    "HypothesisDecision",
    "HypothesisDraft",
    "HypothesisStatus",
    "InMemoryAssessmentSignalPort",
    "PerspectiveDraft",
    "ProcessReadback",
    "S01AuditEvent",
    "S01VerticalSlice",
]
