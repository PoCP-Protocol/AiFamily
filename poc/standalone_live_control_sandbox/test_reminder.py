from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from poc.standalone_live_control_sandbox.control_plane import (
    LIVE_ATTENDANCE_PURPOSE,
    CanonicalConsentDecision,
    GuardianContext,
    Registration,
    RegistrationStatus,
    ReviewStatus,
    SessionStatus,
)
from poc.standalone_live_control_sandbox.reminder import (
    ReminderRejected,
    ReminderSessionProjection,
    ReminderWindow,
    plan_reminder,
)

NOW = datetime(2026, 9, 3, 8, tzinfo=UTC)
GUARDIAN = GuardianContext("tenant.synthetic", "family.synthetic", "guardian.synthetic")
REGISTRATION = Registration(
    registration_ref="registration.synthetic.1",
    session_ref="live.synthetic.1",
    tenant_id=GUARDIAN.tenant_id,
    family_id=GUARDIAN.family_id,
    guardian_id=GUARDIAN.guardian_id,
    consent_ref="consent.synthetic.1",
    status=RegistrationStatus.CONFIRMED,
    correlation_id="correlation.synthetic.1",
)
CONSENT = CanonicalConsentDecision(
    consent_ref="consent.synthetic.1",
    tenant_id=GUARDIAN.tenant_id,
    family_id=GUARDIAN.family_id,
    guardian_id=GUARDIAN.guardian_id,
    purpose=LIVE_ATTENDANCE_PURPOSE,
    granted=True,
    expires_at=NOW + timedelta(days=2),
)


def session(**changes: object) -> ReminderSessionProjection:
    values: dict[str, object] = {
        "session_ref": "live.synthetic.1",
        "tenant_id": GUARDIAN.tenant_id,
        "family_id": GUARDIAN.family_id,
        "title": "家庭沟通练习",
        "starts_at": NOW + timedelta(hours=2),
        "ends_at": NOW + timedelta(hours=3),
        "review_status": ReviewStatus.APPROVED,
        "status": SessionStatus.SCHEDULED,
    }
    values.update(changes)
    return ReminderSessionProjection(**values)


def test_plans_a_draft_without_sending_an_external_notification() -> None:
    draft = plan_reminder(
        registration=REGISTRATION,
        session=session(),
        guardian=GUARDIAN,
        consent=CONSENT,
        now=NOW,
    )

    assert draft.window is ReminderWindow.DAY_BEFORE
    assert draft.deliver_at == NOW
    assert draft.external_effect is False
    assert draft.requires_canonical_notification is True
    assert draft.source == "SANDBOX_SYNTHETIC"
    assert draft.fixture_only is True


@pytest.mark.parametrize(
    "starts_at, expected",
    [
        (NOW + timedelta(minutes=30), ReminderWindow.HOUR_BEFORE),
        (NOW + timedelta(minutes=3), ReminderWindow.STARTING),
    ],
)
def test_chooses_a_bounded_reminder_window(
    starts_at: datetime,
    expected: ReminderWindow,
) -> None:
    draft = plan_reminder(
        registration=REGISTRATION,
        session=session(starts_at=starts_at, ends_at=starts_at + timedelta(hours=1)),
        guardian=GUARDIAN,
        consent=CONSENT,
        now=NOW,
    )
    assert draft.window is expected
    assert draft.deliver_at >= NOW


@pytest.mark.parametrize(
    "registration, projected_session, consent",
    [
        (replace(REGISTRATION, status=RegistrationStatus.CANCELLED), session(), CONSENT),
        (replace(REGISTRATION, status=RegistrationStatus.REVOKED), session(), CONSENT),
        (REGISTRATION, session(review_status=ReviewStatus.WITHDRAWN), CONSENT),
        (REGISTRATION, session(status=SessionStatus.WITHDRAWN), CONSENT),
        (REGISTRATION, session(ends_at=NOW), CONSENT),
        (REGISTRATION, session(family_id="family.other"), CONSENT),
        (REGISTRATION, session(source="BASELINE_CONTENT"), CONSENT),
        (REGISTRATION, session(), replace(CONSENT, granted=False)),
        (REGISTRATION, session(), replace(CONSENT, purpose="marketing")),
        (REGISTRATION, session(), replace(CONSENT, expires_at=NOW)),
        (REGISTRATION, session(), replace(CONSENT, guardian_id="guardian.other")),
    ],
)
def test_cancelled_withdrawn_expired_and_cross_scope_inputs_fail_closed(
    registration: Registration,
    projected_session: ReminderSessionProjection,
    consent: CanonicalConsentDecision,
) -> None:
    with pytest.raises(ReminderRejected):
        plan_reminder(
            registration=registration,
            session=projected_session,
            guardian=GUARDIAN,
            consent=consent,
            now=NOW,
        )


def test_sessions_outside_the_horizon_do_not_create_reminders() -> None:
    with pytest.raises(ReminderRejected, match="outside the reminder horizon"):
        plan_reminder(
            registration=REGISTRATION,
            session=session(
                starts_at=NOW + timedelta(days=2),
                ends_at=NOW + timedelta(days=2, hours=1),
            ),
            guardian=GUARDIAN,
            consent=CONSENT,
            now=NOW,
        )
