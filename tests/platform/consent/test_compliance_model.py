"""ConsentGrant's three legal gaps, closed and tested.

Maps 1:1 onto `docs/06_platform/CONSENT.md` §3 gaps 1, 3 and 4:

* gap 1 — no REFUSED state, so "asked and declined" was indistinguishable from
  "never asked" (《儿童个人信息网络保护规定》第10条 requires a refusal option, and
  an unrecordable refusal is not provably offered).
* gap 3 — no `expires_at`, so `ConsentStatus.EXPIRED` was a dead enum member no
  code could ever produce (第10条 advance disclosure of retention period, 第12条
  no retention beyond necessity).
* gap 4 — no age or guardianship, so PIPL 第28/31条's under-14 rule had nothing
  to stand on.

`docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §9 is also tested here, in
the negative: the 14 line must not be turned into "guardians of 14–17 year olds
lose their channel". See `test_fourteen_line_is_only_about_requiring_consent`.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from backend.platform.consent.gate import ConsentGate
from backend.platform.consent.models import (
    GUARDIAN_CONSENT_AGE_THRESHOLD,
    ConsentGrant,
    ConsentPurpose,
    ConsentStatus,
    GuardianRelation,
    SubjectAge,
)

NOW = datetime(2026, 8, 29, 12, 0, tzinfo=UTC)
CHILD = "person-child"
GUARDIAN = "person-guardian"
ADULT = "person-adult"


def _child_grant(
    status: ConsentStatus = ConsentStatus.GRANTED,
    *,
    expires_at: datetime | None = None,
) -> ConsentGrant:
    return ConsentGrant(
        consent_id="consent-1",
        subject_person_id=CHILD,
        guardian_person_id=GUARDIAN,
        purpose=ConsentPurpose.ASSESSMENT,
        status=status,
        granted_at=NOW,
        subject_age=SubjectAge(years=9),
        guardian_relation=GuardianRelation.GUARDIAN,
        expires_at=expires_at,
    )


# --------------------------------------------------------------------------
# gap 1 — REFUSED
# --------------------------------------------------------------------------


def test_refused_is_a_distinct_status_from_withdrawn_and_from_absence() -> None:
    """Three different facts must be three different states.

    "Never asked" is an empty grant list. "Asked and declined" is REFUSED.
    "Given then taken back" is WITHDRAWN. Before REFUSED existed the first two
    were the same thing on disk, so nothing could prove the refusal option had
    been offered, and nothing could stop a refusal being re-prompted as if it
    were an open question.
    """
    assert ConsentStatus.REFUSED is not ConsentStatus.WITHDRAWN
    refused = _child_grant(ConsentStatus.REFUSED)
    assert refused.status_at(NOW) is ConsentStatus.REFUSED


def test_refused_grant_denies() -> None:
    grants = [_child_grant(ConsentStatus.REFUSED)]
    assert ConsentGate.check(CHILD, ConsentPurpose.ASSESSMENT, grants, at=NOW) is False


def test_a_refusal_is_visible_where_an_absent_grant_is_not() -> None:
    """The gate answers False either way — the *record* is what differs."""
    refused = [_child_grant(ConsentStatus.REFUSED)]
    absent: list[ConsentGrant] = []

    assert ConsentGate.check(CHILD, ConsentPurpose.ASSESSMENT, refused, at=NOW) is False
    assert ConsentGate.check(CHILD, ConsentPurpose.ASSESSMENT, absent, at=NOW) is False
    assert [g.status_at(NOW) for g in refused] == [ConsentStatus.REFUSED]
    assert [g.status_at(NOW) for g in absent] == []


# --------------------------------------------------------------------------
# gap 3 — expires_at / EXPIRED is reachable
# --------------------------------------------------------------------------


def test_expired_status_is_now_reachable_without_anyone_writing_it() -> None:
    """The dead-enum test. Nothing rewrites `status`; expiry is derived."""
    grant = _child_grant(expires_at=NOW + timedelta(days=30))

    assert grant.status_at(NOW) is ConsentStatus.GRANTED
    assert grant.status_at(NOW + timedelta(days=31)) is ConsentStatus.EXPIRED
    assert grant.status is ConsentStatus.GRANTED, "stored status must not be mutated"


def test_gate_denies_after_expiry_with_no_scheduled_job_in_the_loop() -> None:
    grants = [_child_grant(expires_at=NOW + timedelta(days=30))]

    assert ConsentGate.check(CHILD, ConsentPurpose.ASSESSMENT, grants, at=NOW) is True
    assert (
        ConsentGate.check(CHILD, ConsentPurpose.ASSESSMENT, grants, at=NOW + timedelta(days=31))
        is False
    )


def test_expiry_is_inclusive_at_the_boundary() -> None:
    """At exactly `expires_at` the grant is over. A retention period that lasted
    one instant longer than disclosed is still a retention period exceeded."""
    expires = NOW + timedelta(days=30)
    grant = _child_grant(expires_at=expires)

    assert grant.status_at(expires - timedelta(microseconds=1)) is ConsentStatus.GRANTED
    assert grant.status_at(expires) is ConsentStatus.EXPIRED


def test_grant_without_expires_at_does_not_expire() -> None:
    """`None` means "no period recorded", which the model must not silently
    reinterpret as either "expired" or "expires soon"."""
    grant = _child_grant()
    assert grant.status_at(NOW + timedelta(days=36500)) is ConsentStatus.GRANTED


@pytest.mark.parametrize("terminal", [ConsentStatus.WITHDRAWN, ConsentStatus.REFUSED])
def test_terminal_statuses_do_not_become_expired(terminal: ConsentStatus) -> None:
    """A withdrawal must keep reading as a withdrawal forever.

    If expiry overwrote it, the audit trail would lose the reason — and
    "expired" invites a renewal prompt where "withdrawn" forbids one.
    """
    grant = _child_grant(terminal, expires_at=NOW + timedelta(days=1))
    assert grant.status_at(NOW + timedelta(days=2)) is terminal


def test_expires_at_must_be_after_granted_at() -> None:
    with pytest.raises(ValueError, match="after granted_at"):
        _child_grant(expires_at=NOW)


def test_mixed_naive_and_aware_timestamps_are_rejected_at_construction() -> None:
    """Better a construction error than a TypeError inside a legal gate."""
    with pytest.raises(ValueError, match="both be naive or"):
        ConsentGrant(
            consent_id="consent-1",
            subject_person_id=CHILD,
            guardian_person_id=GUARDIAN,
            purpose=ConsentPurpose.ASSESSMENT,
            status=ConsentStatus.GRANTED,
            granted_at=NOW.replace(tzinfo=None),
            subject_age=SubjectAge(years=9),
            guardian_relation=GuardianRelation.GUARDIAN,
            expires_at=NOW + timedelta(days=1),
        )


def test_naive_grant_still_expires_when_checked_with_an_aware_moment() -> None:
    """The domains use naive-UTC `utcnow()`; callers use `datetime.now(UTC)`.

    A TypeError here would be a crash in a consent check, i.e. an outage on a
    legal gate. Both halves must still reach the same verdict.
    """
    naive_now = NOW.replace(tzinfo=None)
    grant = ConsentGrant(
        consent_id="consent-1",
        subject_person_id=CHILD,
        guardian_person_id=GUARDIAN,
        purpose=ConsentPurpose.ASSESSMENT,
        status=ConsentStatus.GRANTED,
        granted_at=naive_now,
        subject_age=SubjectAge(years=9),
        guardian_relation=GuardianRelation.GUARDIAN,
        expires_at=naive_now + timedelta(days=30),
    )

    assert grant.status_at(NOW) is ConsentStatus.GRANTED
    assert grant.status_at(NOW + timedelta(days=31)) is ConsentStatus.EXPIRED


# --------------------------------------------------------------------------
# gap 4 — age and guardianship
# --------------------------------------------------------------------------


def test_under_fourteen_requires_a_distinct_guardian() -> None:
    """PIPL art. 31. SELF for a child means the child consented for themselves."""
    with pytest.raises(ValueError, match="requires guardian_relation"):
        ConsentGrant(
            consent_id="consent-1",
            subject_person_id=CHILD,
            guardian_person_id=CHILD,
            purpose=ConsentPurpose.ASSESSMENT,
            status=ConsentStatus.GRANTED,
            granted_at=NOW,
            subject_age=SubjectAge(years=9),
            guardian_relation=GuardianRelation.SELF,
        )


def test_under_fourteen_with_no_guardianship_relation_is_refused() -> None:
    with pytest.raises(ValueError, match="requires guardian_relation"):
        ConsentGrant(
            consent_id="consent-1",
            subject_person_id=CHILD,
            guardian_person_id=GUARDIAN,
            purpose=ConsentPurpose.ASSESSMENT,
            status=ConsentStatus.GRANTED,
            granted_at=NOW,
            subject_age=SubjectAge(years=9),
            guardian_relation=GuardianRelation.NONE,
        )


def test_under_fourteen_guardian_must_not_be_the_subject() -> None:
    with pytest.raises(ValueError, match="cannot be their own guardian"):
        ConsentGrant(
            consent_id="consent-1",
            subject_person_id=CHILD,
            guardian_person_id=CHILD,
            purpose=ConsentPurpose.ASSESSMENT,
            status=ConsentStatus.GRANTED,
            granted_at=NOW,
            subject_age=SubjectAge(years=9),
            guardian_relation=GuardianRelation.GUARDIAN,
        )


@pytest.mark.parametrize("years", [0, 13])
def test_boundary_below_fourteen_requires_a_guardian(years: int) -> None:
    assert SubjectAge(years=years).requires_guardian_consent is True


@pytest.mark.parametrize("years", [14, 17, 40])
def test_at_and_above_fourteen_may_self_consent(years: int) -> None:
    assert SubjectAge(years=years).requires_guardian_consent is False
    grant = ConsentGrant(
        consent_id="consent-1",
        subject_person_id=ADULT,
        guardian_person_id=ADULT,
        purpose=ConsentPurpose.SERVICE,
        status=ConsentStatus.GRANTED,
        granted_at=NOW,
        subject_age=SubjectAge(years=years),
        guardian_relation=GuardianRelation.SELF,
    )
    assert grant.is_active_at(NOW) is True


def test_self_relation_requires_guardian_id_to_equal_subject_id() -> None:
    with pytest.raises(ValueError, match="SELF requires"):
        ConsentGrant(
            consent_id="consent-1",
            subject_person_id=ADULT,
            guardian_person_id=GUARDIAN,
            purpose=ConsentPurpose.SERVICE,
            status=ConsentStatus.GRANTED,
            granted_at=NOW,
            subject_age=SubjectAge(years=40),
            guardian_relation=GuardianRelation.SELF,
        )


def test_fourteen_line_is_only_about_requiring_consent() -> None:
    """COMPLIANCE_HARD_CONSTRAINTS §9: the 14 line must not close a channel.

    A 15-year-old's grant recorded by a *guardian* must remain representable and
    in force. 《未成年人网络保护条例》第34条 gives the minor and the guardian
    parallel rights with no age split, so an implementation that rejected
    guardian_relation=GUARDIAN once the subject turned 14 would have implemented
    the misreading §9 explicitly corrects.
    """
    grant = ConsentGrant(
        consent_id="consent-teen",
        subject_person_id="person-teen",
        guardian_person_id=GUARDIAN,
        purpose=ConsentPurpose.GROWTH_TRACKING,
        status=ConsentStatus.GRANTED,
        granted_at=NOW,
        subject_age=SubjectAge(years=15),
        guardian_relation=GuardianRelation.GUARDIAN,
    )

    assert grant.is_active_at(NOW) is True
    assert ConsentGate.check("person-teen", ConsentPurpose.GROWTH_TRACKING, [grant], at=NOW) is True


def test_threshold_constant_is_fourteen() -> None:
    """Pinned so a "tidy-up" cannot quietly move a statutory boundary."""
    assert GUARDIAN_CONSENT_AGE_THRESHOLD == 14


@pytest.mark.parametrize("years", [-1, 151])
def test_implausible_ages_are_rejected(years: int) -> None:
    with pytest.raises(ValueError):
        SubjectAge(years=years)
