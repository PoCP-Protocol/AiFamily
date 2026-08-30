"""Minimal contract for the canonical platform consent value object."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.platform.consent import (
    ConsentGrant,
    ConsentPurpose,
    ConsentStatus,
    GuardianRelation,
)

NOW = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


def _grant(**overrides: object) -> ConsentGrant:
    values: dict[str, object] = {
        "consent_id": "consent-1",
        "tenant_id": "tenant-1",
        "family_id": "family-1",
        "subject_person_id": "subject-1",
        "guardian_person_id": "guardian-1",
        "guardian_relation": GuardianRelation.GUARDIAN,
        "purpose": ConsentPurpose.ASSESSMENT,
        "status": ConsentStatus.GRANTED,
        "granted_at": NOW,
        "effective_from": NOW,
        "effective_to": NOW + timedelta(days=30),
    }
    values.update(overrides)
    return ConsentGrant(**values)


def test_public_model_carries_guardian_and_full_scope() -> None:
    grant = _grant()

    assert grant.guardian_relation is GuardianRelation.GUARDIAN
    assert grant.tenant_id == "tenant-1"
    assert grant.family_id == "family-1"
    assert grant.subject_person_id == "subject-1"
    assert grant.purpose is ConsentPurpose.ASSESSMENT


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("tenant_id", "tenant-2"),
        ("family_id", "family-2"),
        ("subject_person_id", "subject-2"),
    ],
)
def test_scope_mismatch_fails_closed(field: str, value: str) -> None:
    grant = _grant()
    scope = {
        "tenant_id": "tenant-1",
        "family_id": "family-1",
        "subject_person_id": "subject-1",
        "purpose": ConsentPurpose.ASSESSMENT,
    }
    scope[field] = value

    assert grant.matches_scope(**scope) is False
    assert grant.is_active_for(**scope, moment=NOW) is False


def test_purpose_is_scoped_without_cross_purpose_leakage() -> None:
    grant = _grant()

    assert (
        grant.matches_scope(
            tenant_id="tenant-1",
            family_id="family-1",
            subject_person_id="subject-1",
            purpose=ConsentPurpose.SERVICE,
        )
        is False
    )


def test_effective_window_is_start_inclusive_and_end_exclusive() -> None:
    grant = _grant()

    assert grant.is_active_at(NOW) is True
    assert grant.is_active_at(NOW + timedelta(days=30) - timedelta(microseconds=1)) is True
    assert grant.is_active_at(NOW + timedelta(days=30)) is False
    assert grant.status_at(NOW + timedelta(days=30)) is ConsentStatus.EXPIRED


def test_future_effective_window_is_not_active_yet() -> None:
    starts = NOW + timedelta(hours=1)
    grant = _grant(
        effective_from=starts,
        effective_to=starts + timedelta(days=1),
    )

    assert grant.is_active_at(NOW) is False
    assert grant.status_at(NOW) is ConsentStatus.GRANTED
    assert grant.is_active_at(starts) is True


def test_withdrawn_status_and_timestamp_deny_immediately() -> None:
    status_withdrawn = _grant(status=ConsentStatus.WITHDRAWN)
    timestamp_withdrawn = _grant(withdrawn_at=NOW)

    assert status_withdrawn.is_active_at(NOW) is False
    assert status_withdrawn.status_at(NOW) is ConsentStatus.WITHDRAWN
    assert timestamp_withdrawn.is_active_at(NOW) is False
    assert timestamp_withdrawn.status_at(NOW) is ConsentStatus.WITHDRAWN


def test_expired_status_is_always_denied_and_grants_are_immutable() -> None:
    grant = _grant(status=ConsentStatus.EXPIRED)

    assert grant.is_active_at(NOW) is False
    assert grant.status_at(NOW) is ConsentStatus.EXPIRED
    with pytest.raises(AttributeError):
        grant.status = ConsentStatus.GRANTED  # type: ignore[misc]


def test_effective_window_must_have_a_positive_duration() -> None:
    with pytest.raises(ValueError, match="after effective_from"):
        _grant(effective_to=NOW)
