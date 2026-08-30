"""Synthetic H-LIVE-04 moderation and stop-switch contract.

The implementation is deliberately a disposable contract/mock.  It models
the boundary between a Live product and the canonical Audit/Outbox service;
it is not a production moderation service, takedown ledger, media runtime, or
automated safety decision engine.

The only user behavior covered here is: an adult viewer submits a report, a
human moderator reviews it, and only the human decision may stop presentation
of the synthetic session.  A report alone never stops a session.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Protocol

SANDBOX_SOURCE = "SANDBOX_SYNTHETIC"


class ModerationBoundaryError(ValueError):
    """A synthetic moderation fixture violates an explicit boundary."""


class ModerationRejected(RuntimeError):
    """The requested moderation action is not permitted."""


class ModerationScopeViolation(ModerationRejected):
    """A report or decision crossed its tenant/family scope."""


class ModerationIdempotencyConflict(ModerationRejected):
    """A decision key was reused for a different moderation action."""


class ActorType(StrEnum):
    ADULT_VIEWER = "ADULT_VIEWER"
    CHILD = "CHILD"
    HUMAN_MODERATOR = "HUMAN_MODERATOR"
    AI_AGENT = "AI_AGENT"


class SessionState(StrEnum):
    LIVE = "LIVE"
    STOPPED = "STOPPED"
    WITHDRAWN = "WITHDRAWN"


class ReportStatus(StrEnum):
    PENDING = "PENDING"
    DISMISSED = "DISMISSED"
    STOPPED = "STOPPED"


class ModerationAction(StrEnum):
    DISMISS = "DISMISS"
    STOP_SESSION = "STOP_SESSION"


@dataclass(frozen=True, slots=True)
class ScopedActor:
    tenant_id: str
    family_id: str
    actor_id: str
    actor_type: ActorType

    def __post_init__(self) -> None:
        if not all((self.tenant_id, self.family_id, self.actor_id)):
            raise ValueError("actor scope fields must not be empty")


@dataclass(slots=True)
class LiveSessionFixture:
    tenant_id: str
    family_id: str
    session_ref: str
    state: SessionState = SessionState.LIVE
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True

    def __post_init__(self) -> None:
        if not self.fixture_only or self.source != SANDBOX_SOURCE:
            raise ModerationBoundaryError("moderation fixture must be explicitly synthetic")
        if not all((self.tenant_id, self.family_id, self.session_ref)):
            raise ValueError("session scope and reference must not be empty")


@dataclass(frozen=True, slots=True)
class ModerationReport:
    report_ref: str
    session_ref: str
    tenant_id: str
    family_id: str
    reporter_id: str
    reason: str
    status: ReportStatus = ReportStatus.PENDING


@dataclass(frozen=True, slots=True)
class ModerationAudit:
    action: str
    actor_id: str
    tenant_id: str
    family_id: str
    resource_ref: str
    report_ref: str | None
    reason: str
    occurred_at: datetime


class CanonicalAuditOutboxPort(Protocol):
    """Production-owned atomic audit/outbox boundary."""

    def commit_moderation(
        self,
        *,
        audit: ModerationAudit,
        event_type: str,
        idempotency_key: str,
    ) -> None: ...

    def commit_stop_switch(
        self,
        *,
        audits: tuple[ModerationAudit, ...],
        event_type: str,
        idempotency_key: str,
    ) -> None: ...


class InMemoryAuditOutboxFixture:
    """Sandbox-only test double; it is not a canonical audit ledger."""

    def __init__(self) -> None:
        self.commits: list[tuple[ModerationAudit, str, str]] = []
        self._keys: dict[str, tuple[str, ModerationAudit]] = {}
        self.fail_next_commit = False

    def commit_moderation(
        self,
        *,
        audit: ModerationAudit,
        event_type: str,
        idempotency_key: str,
    ) -> None:
        if self.fail_next_commit:
            self.fail_next_commit = False
            raise RuntimeError("synthetic moderation commit failure")
        action_fingerprint = f"{audit.action}:{audit.resource_ref}:{audit.report_ref}"
        previous = self._keys.get(idempotency_key)
        if previous is not None:
            if previous[0] != action_fingerprint:
                raise ModerationIdempotencyConflict(
                    "moderation idempotency key was reused for another action"
                )
            return
        self._keys[idempotency_key] = (action_fingerprint, audit)
        self.commits.append((audit, event_type, idempotency_key))

    def commit_stop_switch(
        self,
        *,
        audits: tuple[ModerationAudit, ...],
        event_type: str,
        idempotency_key: str,
    ) -> None:
        """Commit every stop-switch audit as one synthetic transaction."""

        if self.fail_next_commit:
            self.fail_next_commit = False
            raise RuntimeError("synthetic moderation commit failure")
        fingerprint = "|".join(
            f"{audit.action}:{audit.resource_ref}:{audit.report_ref}" for audit in audits
        )
        previous = self._keys.get(idempotency_key)
        if previous is not None:
            if previous[0] != fingerprint:
                raise ModerationIdempotencyConflict(
                    "moderation idempotency key was reused for another action"
                )
            return
        self._keys[idempotency_key] = (fingerprint, audits[0])
        self.commits.extend(
            (audit, event_type, f"{idempotency_key}:{audit.resource_ref}") for audit in audits
        )


class SandboxModerator:
    """Human-reviewed moderation over synthetic sessions."""

    def __init__(self, *, audit_outbox: CanonicalAuditOutboxPort) -> None:
        self._audit_outbox = audit_outbox
        self._reports: dict[str, ModerationReport] = {}
        self._sessions: dict[str, LiveSessionFixture] = {}
        self._decisions: dict[str, tuple[str, ModerationReport]] = {}
        self._switches: dict[str, tuple[str, ...]] = {}

    def register_session(self, session: LiveSessionFixture) -> None:
        if session.session_ref in self._sessions:
            raise ValueError("session already registered")
        self._sessions[session.session_ref] = session

    def submit_report(
        self,
        *,
        session_ref: str,
        reporter: ScopedActor,
        report_ref: str,
        reason: str,
    ) -> ModerationReport:
        """Accept a report without changing session state."""

        session = self._session(session_ref)
        self._assert_scope(session, reporter)
        if reporter.actor_type is not ActorType.ADULT_VIEWER:
            raise ModerationRejected("only an authenticated adult may submit a public report")
        if not reason.strip() or not report_ref:
            raise ValueError("report reference and reason are required")
        if session.state is not SessionState.LIVE:
            raise ModerationRejected("report target is no longer live")
        if report_ref in self._reports:
            return self._reports[report_ref]
        report = ModerationReport(
            report_ref=report_ref,
            session_ref=session_ref,
            tenant_id=reporter.tenant_id,
            family_id=reporter.family_id,
            reporter_id=reporter.actor_id,
            reason=reason.strip(),
        )
        self._reports[report_ref] = report
        return report

    def review_report(
        self,
        *,
        report_ref: str,
        moderator: ScopedActor,
        action: ModerationAction,
        decision_key: str,
        reason: str,
        occurred_at: datetime,
    ) -> ModerationReport:
        """Apply only a human decision; AI cannot stop or dismiss content."""

        report = self._report(report_ref)
        session = self._session(report.session_ref)
        self._assert_scope(session, moderator)
        if moderator.actor_type is not ActorType.HUMAN_MODERATOR:
            raise ModerationRejected("only a human moderator may decide a report")
        if not decision_key or not reason.strip():
            raise ValueError("decision key and reason are required")

        previous = self._decisions.get(decision_key)
        if previous is not None:
            previous_action, previous_report = previous
            if previous_action != action.value or previous_report.report_ref != report_ref:
                raise ModerationIdempotencyConflict("decision key was reused")
            return previous_report

        if report.status is not ReportStatus.PENDING:
            raise ModerationRejected("report has already been decided")
        next_status = (
            ReportStatus.STOPPED
            if action is ModerationAction.STOP_SESSION
            else ReportStatus.DISMISSED
        )
        audit = ModerationAudit(
            action=f"moderation.{action.value.lower()}",
            actor_id=moderator.actor_id,
            tenant_id=moderator.tenant_id,
            family_id=moderator.family_id,
            resource_ref=session.session_ref,
            report_ref=report_ref,
            reason=reason.strip(),
            occurred_at=occurred_at,
        )
        self._audit_outbox.commit_moderation(
            audit=audit,
            event_type=f"live.moderation.{action.value.lower()}",
            idempotency_key=decision_key,
        )
        # State changes happen after the canonical atomic boundary succeeds.
        if action is ModerationAction.STOP_SESSION:
            session.state = SessionState.STOPPED
        decided = ModerationReport(
            report_ref=report.report_ref,
            session_ref=report.session_ref,
            tenant_id=report.tenant_id,
            family_id=report.family_id,
            reporter_id=report.reporter_id,
            reason=report.reason,
            status=next_status,
        )
        self._reports[report_ref] = decided
        self._decisions[decision_key] = (action.value, decided)
        return decided

    def engage_stop_switch(
        self,
        *,
        moderator: ScopedActor,
        decision_key: str,
        reason: str,
        occurred_at: datetime,
    ) -> tuple[str, ...]:
        """Stop all live sessions through a human-controlled fail-safe."""

        if moderator.actor_type is not ActorType.HUMAN_MODERATOR:
            raise ModerationRejected("stop switch requires a human moderator")
        if not decision_key or not reason.strip():
            raise ValueError("decision key and reason are required")
        if decision_key in self._switches:
            return self._switches[decision_key]
        stopped = tuple(
            session
            for session in self._sessions.values()
            if session.tenant_id == moderator.tenant_id
            and session.family_id == moderator.family_id
            and session.state is SessionState.LIVE
        )
        audits = tuple(
            ModerationAudit(
                action="moderation.stop_switch",
                actor_id=moderator.actor_id,
                tenant_id=moderator.tenant_id,
                family_id=moderator.family_id,
                resource_ref=session.session_ref,
                report_ref=None,
                reason=reason.strip(),
                occurred_at=occurred_at,
            )
            for session in stopped
        )
        self._audit_outbox.commit_stop_switch(
            audits=audits,
            event_type="live.moderation.stop_switch",
            idempotency_key=decision_key,
        )
        for session in stopped:
            session.state = SessionState.STOPPED
        refs = tuple(session.session_ref for session in stopped)
        self._switches[decision_key] = refs
        return refs

    def _session(self, session_ref: str) -> LiveSessionFixture:
        try:
            return self._sessions[session_ref]
        except KeyError as exc:
            raise ModerationRejected("live session not found") from exc

    def _report(self, report_ref: str) -> ModerationReport:
        try:
            return self._reports[report_ref]
        except KeyError as exc:
            raise ModerationRejected("moderation report not found") from exc

    @staticmethod
    def _assert_scope(session: LiveSessionFixture, actor: ScopedActor) -> None:
        if session.tenant_id != actor.tenant_id or session.family_id != actor.family_id:
            raise ModerationScopeViolation("moderation request crossed tenant/family scope")
