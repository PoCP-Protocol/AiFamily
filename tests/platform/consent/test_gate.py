"""ConsentGate.check semantics — withdrawn consent must take effect immediately.

This is the requirement carried over from
`FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md` section 10 and kept in force by
REPOSITORY_CONSTITUTION.md's disposition for `platform_consent`.
"""

from __future__ import annotations

from datetime import UTC, datetime

from backend.platform.consent.gate import ConsentGate
from backend.platform.consent.models import ConsentGrant, ConsentPurpose, ConsentStatus


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
