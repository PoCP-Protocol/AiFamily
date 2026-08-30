"""ConsentGate.check semantics — withdrawn consent must take effect immediately.

This is the requirement carried over from
`FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` section 10 and kept in force by
REPOSITORY_CONSTITUTION.md's disposition for `platform_consent`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.platform.consent.gate import ConsentGate
from backend.platform.consent.models import ConsentGrant, ConsentPurpose, ConsentStatus

EVALUATION_TIME = datetime(2026, 8, 30, 12, 0, tzinfo=UTC)


class _TimeAwareGrant:
    """Small test double for the newer ConsentGrant time-aware contract."""

    subject_person_id = "person-1"
    purpose = ConsentPurpose.ASSESSMENT

    def __init__(self, effective_from: datetime, effective_to: datetime) -> None:
        self._effective_from = effective_from
        self._effective_to = effective_to

    @property
    def is_active(self) -> bool:
        return False

    def is_active_at(self, at: datetime) -> bool:
        return self._effective_from <= at < self._effective_to


def _grant(
    status: ConsentStatus, purpose: ConsentPurpose = ConsentPurpose.ASSESSMENT
) -> ConsentGrant:
    return ConsentGrant(
        consent_id="consent-1",
        subject_person_id="person-1",
        guardian_person_id="guardian-1",
        purpose=purpose,
        status=status,
        granted_at=datetime.now(UTC),
    )


def test_active_grant_for_matching_purpose_is_allowed() -> None:
    grants = [_grant(ConsentStatus.GRANTED)]
    assert ConsentGate.check("person-1", ConsentPurpose.ASSESSMENT, grants) is True


def test_explicit_evaluation_time_is_accepted_for_legacy_grants() -> None:
    grants = [_grant(ConsentStatus.GRANTED, purpose=ConsentPurpose.ASSESSMENT)]
    assert (
        ConsentGate.check(
            "person-1",
            ConsentPurpose.ASSESSMENT,
            grants,
            at=EVALUATION_TIME,
        )
        is True
    )


def test_explicit_evaluation_time_preserves_effective_window_boundaries() -> None:
    grant = _TimeAwareGrant(
        effective_from=EVALUATION_TIME,
        effective_to=EVALUATION_TIME + timedelta(days=1),
    )

    assert (
        ConsentGate.check(
            "person-1",
            ConsentPurpose.ASSESSMENT,
            [grant],
            at=EVALUATION_TIME - timedelta(microseconds=1),
        )
        is False
    )
    assert (
        ConsentGate.check(
            "person-1",
            ConsentPurpose.ASSESSMENT,
            [grant],
            at=EVALUATION_TIME,
        )
        is True
    )
    assert (
        ConsentGate.check(
            "person-1",
            ConsentPurpose.ASSESSMENT,
            [grant],
            at=EVALUATION_TIME + timedelta(days=1),
        )
        is False
    )


def test_withdrawn_grant_is_denied_immediately() -> None:
    grants = [_grant(ConsentStatus.WITHDRAWN)]
    assert ConsentGate.check("person-1", ConsentPurpose.ASSESSMENT, grants) is False


def test_withdrawal_takes_effect_without_any_cache_across_calls() -> None:
    """Simulate a grant being withdrawn between two calls to check().

    The gate holds no state between calls, so passing the updated grant
    list on the second call must immediately flip the decision — there is
    no cached ALLOW from the first call that could leak through.
    """
    active_grants = [_grant(ConsentStatus.GRANTED)]
    assert ConsentGate.check("person-1", ConsentPurpose.ASSESSMENT, active_grants) is True

    withdrawn_grants = [_grant(ConsentStatus.WITHDRAWN)]
    assert ConsentGate.check("person-1", ConsentPurpose.ASSESSMENT, withdrawn_grants) is False


def test_grant_for_a_different_purpose_does_not_leak_permission() -> None:
    grants = [_grant(ConsentStatus.GRANTED, purpose=ConsentPurpose.SERVICE)]
    assert ConsentGate.check("person-1", ConsentPurpose.AI_PERSONALIZATION, grants) is False


def test_no_grants_at_all_is_denied() -> None:
    assert ConsentGate.check("person-1", ConsentPurpose.ASSESSMENT, []) is False


def test_grant_for_a_different_subject_does_not_leak_permission() -> None:
    grants = [_grant(ConsentStatus.GRANTED)]
    assert ConsentGate.check("some-other-person", ConsentPurpose.ASSESSMENT, grants) is False
