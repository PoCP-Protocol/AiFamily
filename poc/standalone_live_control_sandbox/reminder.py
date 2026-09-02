"""Fail-closed reminder planning for synthetic live registrations.

The planner never sends a notification. It produces a deterministic draft for
the canonical notification service after rechecking registration, session,
adult scope, and purpose-specific Consent projections.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum

from poc.standalone_live_control_sandbox.control_plane import (
    LIVE_ATTENDANCE_PURPOSE,
    SANDBOX_SOURCE,
    CanonicalConsentDecision,
    GuardianContext,
    Registration,
    RegistrationStatus,
    ReviewStatus,
    SessionStatus,
)


class ReminderRejected(RuntimeError):
    """The reminder cannot safely be proposed."""


class ReminderWindow(StrEnum):
    DAY_BEFORE = "DAY_BEFORE"
    HOUR_BEFORE = "HOUR_BEFORE"
    STARTING = "STARTING"


@dataclass(frozen=True, slots=True)
class ReminderSessionProjection:
    session_ref: str
    tenant_id: str
    family_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    review_status: ReviewStatus
    status: SessionStatus
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


@dataclass(frozen=True, slots=True)
class ReminderDraft:
    reminder_ref: str
    registration_ref: str
    session_ref: str
    tenant_id: str
    family_id: str
    guardian_id: str
    purpose: str
    window: ReminderWindow
    title: str
    deliver_at: datetime
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True
    external_effect: bool = False
    requires_canonical_notification: bool = True


def plan_reminder(
    *,
    registration: Registration,
    session: ReminderSessionProjection,
    guardian: GuardianContext,
    consent: CanonicalConsentDecision,
    now: datetime,
) -> ReminderDraft:
    """Create one notification draft without producing an external effect."""

    _require_synthetic(session)
    _require_scope(registration, session, guardian, consent)
    if registration.status is not RegistrationStatus.CONFIRMED:
        raise ReminderRejected("registration is not active")
    if session.review_status is not ReviewStatus.APPROVED:
        raise ReminderRejected("session approval is not active")
    if session.status not in {SessionStatus.SCHEDULED, SessionStatus.LIVE}:
        raise ReminderRejected("session is unavailable")
    if session.ends_at.astimezone(UTC) <= now.astimezone(UTC):
        raise ReminderRejected("session has ended")
    if not _active_consent(consent, guardian, now):
        raise ReminderRejected("live attendance Consent is not active")

    starts_at = session.starts_at.astimezone(UTC)
    current = now.astimezone(UTC)
    until_start = starts_at - current
    if until_start > timedelta(hours=24):
        raise ReminderRejected("session is outside the reminder horizon")
    if until_start > timedelta(hours=1):
        window = ReminderWindow.DAY_BEFORE
        deliver_at = starts_at - timedelta(hours=24)
    elif until_start > timedelta(minutes=5):
        window = ReminderWindow.HOUR_BEFORE
        deliver_at = starts_at - timedelta(hours=1)
    else:
        window = ReminderWindow.STARTING
        deliver_at = current

    return ReminderDraft(
        reminder_ref=f"reminder.synthetic.{registration.registration_ref}.{window.value.lower()}",
        registration_ref=registration.registration_ref,
        session_ref=session.session_ref,
        tenant_id=guardian.tenant_id,
        family_id=guardian.family_id,
        guardian_id=guardian.guardian_id,
        purpose=LIVE_ATTENDANCE_PURPOSE,
        window=window,
        title=f"小橘灯直播提醒：{session.title}",
        deliver_at=max(deliver_at, current),
    )


def _require_synthetic(session: ReminderSessionProjection) -> None:
    if session.source != SANDBOX_SOURCE or not session.fixture_only:
        raise ReminderRejected("synthetic reminder boundary required")


def _require_scope(
    registration: Registration,
    session: ReminderSessionProjection,
    guardian: GuardianContext,
    consent: CanonicalConsentDecision,
) -> None:
    expected = (guardian.tenant_id, guardian.family_id, guardian.guardian_id)
    if (registration.tenant_id, registration.family_id, registration.guardian_id) != expected:
        raise ReminderRejected("registration scope mismatch")
    if (session.tenant_id, session.family_id) != expected[:2]:
        raise ReminderRejected("session scope mismatch")
    if (consent.tenant_id, consent.family_id, consent.guardian_id) != expected:
        raise ReminderRejected("Consent scope mismatch")
    if registration.session_ref != session.session_ref:
        raise ReminderRejected("registration session mismatch")
    if registration.consent_ref != consent.consent_ref:
        raise ReminderRejected("registration Consent reference mismatch")


def _active_consent(
    consent: CanonicalConsentDecision,
    guardian: GuardianContext,
    now: datetime,
) -> bool:
    return (
        consent.granted
        and consent.purpose == LIVE_ATTENDANCE_PURPOSE
        and consent.tenant_id == guardian.tenant_id
        and consent.family_id == guardian.family_id
        and consent.guardian_id == guardian.guardian_id
        and (consent.expires_at is None or consent.expires_at.astimezone(UTC) > now.astimezone(UTC))
    )
