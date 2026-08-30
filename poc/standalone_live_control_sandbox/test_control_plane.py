"""Executable synthetic tests for the H-LIVE-02 control-plane boundary."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from poc.standalone_live_control_sandbox.control_plane import (
    LIVE_ATTENDANCE_PURPOSE,
    SANDBOX_SOURCE,
    CanonicalConsentDecision,
    ConsentRequired,
    GuardianContext,
    IdempotencyConflict,
    InMemoryAtomicRegistrationStore,
    LiveSessionFixture,
    RegistrationRejected,
    RegistrationStatus,
    ReviewStatus,
    SandboxBoundaryError,
    SandboxLiveControlPlane,
    ScopeViolation,
    SessionStatus,
)

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)
GUARDIAN = GuardianContext(
    tenant_id="tenant.synthetic",
    family_id="family.synthetic",
    guardian_id="guardian.synthetic",
)


class FakeCanonicalConsent:
    def __init__(self, decision: CanonicalConsentDecision) -> None:
        self.decision = decision
        self.calls: list[dict[str, str]] = []

    def require_grant(self, **kwargs: object) -> CanonicalConsentDecision:
        self.calls.append({key: str(value) for key, value in kwargs.items() if key != "now"})
        return self.decision


def session(**overrides: object) -> LiveSessionFixture:
    values: dict[str, object] = {
        "tenant_id": "tenant.synthetic",
        "family_id": "family.synthetic",
        "session_ref": "live.synthetic.1",
        "title": "合成家庭沟通直播",
        "review_status": ReviewStatus.APPROVED,
        "status": SessionStatus.SCHEDULED,
        "audience_scope": frozenset({"guardian.synthetic"}),
        "starts_at": NOW - timedelta(minutes=5),
        "ends_at": NOW + timedelta(hours=1),
    }
    values.update(overrides)
    return LiveSessionFixture(**values)


def consent(**overrides: object) -> CanonicalConsentDecision:
    values: dict[str, object] = {
        "consent_ref": "consent.synthetic.1",
        "tenant_id": "tenant.synthetic",
        "family_id": "family.synthetic",
        "guardian_id": "guardian.synthetic",
        "purpose": LIVE_ATTENDANCE_PURPOSE,
        "granted": True,
        "expires_at": NOW + timedelta(hours=2),
    }
    values.update(overrides)
    return CanonicalConsentDecision(**values)


def make_plane(decision: CanonicalConsentDecision | None = None):
    consent_port = FakeCanonicalConsent(decision or consent())
    store = InMemoryAtomicRegistrationStore()
    return SandboxLiveControlPlane(consent=consent_port, audit_outbox=store), consent_port, store


def test_register_calls_canonical_consent_and_atomic_audit_outbox() -> None:
    plane, consent_port, store = make_plane()

    receipt = plane.register(
        session=session(),
        guardian=GUARDIAN,
        idempotency_key="idem-1",
        correlation_id="corr-1",
        now=NOW,
    )

    assert receipt.replayed is False
    assert receipt.registration.status is RegistrationStatus.CONFIRMED
    assert consent_port.calls[0]["purpose"] == LIVE_ATTENDANCE_PURPOSE
    assert len(store.commits) == 1
    registration, audit, event_type, key = store.commits[0]
    assert registration.consent_ref == "consent.synthetic.1"
    assert audit.action == "register_live_session"
    assert event_type == "live.registration.confirmed"
    assert key == "idem-1"


def test_replay_is_idempotent_and_does_not_call_consent_or_commit_again() -> None:
    plane, consent_port, store = make_plane()
    first = plane.register(
        session=session(),
        guardian=GUARDIAN,
        idempotency_key="idem-replay",
        correlation_id="corr-1",
        now=NOW,
    )
    second = plane.register(
        session=session(),
        guardian=GUARDIAN,
        idempotency_key="idem-replay",
        correlation_id="corr-2",
        now=NOW,
    )

    assert second.replayed is True
    assert second.registration == first.registration
    assert len(consent_port.calls) == 1
    assert len(store.commits) == 1


def test_idempotency_key_conflict_is_fail_closed() -> None:
    plane, _, _ = make_plane()
    plane.register(
        session=session(),
        guardian=GUARDIAN,
        idempotency_key="idem-conflict",
        correlation_id="corr-1",
        now=NOW,
    )
    with pytest.raises(IdempotencyConflict):
        plane.register(
            session=session(session_ref="live.synthetic.2"),
            guardian=GUARDIAN,
            idempotency_key="idem-conflict",
            correlation_id="corr-2",
            now=NOW,
        )


@pytest.mark.parametrize(
    "overrides, error",
    [
        ({"review_status": ReviewStatus.WITHDRAWN}, RegistrationRejected),
        ({"status": SessionStatus.WITHDRAWN}, RegistrationRejected),
        ({"status": SessionStatus.EXPIRED}, RegistrationRejected),
        ({"ends_at": NOW - timedelta(seconds=1)}, RegistrationRejected),
        ({"family_id": "family.other"}, ScopeViolation),
        ({"audience_scope": frozenset({"guardian.other"})}, ScopeViolation),
    ],
)
def test_session_and_scope_negative_paths(
    overrides: dict[str, object], error: type[Exception]
) -> None:
    plane, _, _ = make_plane()
    with pytest.raises(error):
        plane.register(
            session=session(**overrides),
            guardian=GUARDIAN,
            idempotency_key="idem-negative",
            correlation_id="corr-negative",
            now=NOW,
        )


def test_consent_must_be_purpose_specific_active_and_in_scope() -> None:
    for decision in (
        consent(granted=False),
        consent(purpose="service"),
        consent(expires_at=NOW),
        consent(family_id="family.other"),
        consent(guardian_id="guardian.other"),
    ):
        plane, _, store = make_plane(decision)
        with pytest.raises(ConsentRequired):
            plane.register(
                session=session(),
                guardian=GUARDIAN,
                idempotency_key="idem-consent",
                correlation_id="corr-consent",
                now=NOW,
            )
        assert store.commits == []


def test_atomic_commit_failure_leaves_no_sandbox_receipt() -> None:
    plane, _, store = make_plane()
    store.fail_next_commit = True
    with pytest.raises(RuntimeError, match="atomic commit"):
        plane.register(
            session=session(),
            guardian=GUARDIAN,
            idempotency_key="idem-failure",
            correlation_id="corr-failure",
            now=NOW,
        )
    assert store.commits == []
    assert store.receipt_for("idem-failure") is None


def test_fixture_boundary_is_explicit_and_baseline_content_is_rejected() -> None:
    with pytest.raises(SandboxBoundaryError):
        session(source="BASELINE_CONTENT")
    with pytest.raises(SandboxBoundaryError):
        session(fixture_only=False)
    assert session().source == SANDBOX_SOURCE
    assert session().fixture_only is True
