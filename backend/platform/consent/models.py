"""Consent value objects.

`ConsentPurpose` mirrors the purpose taxonomy referenced by the source
repository's `specs/ontology/consent.schema.yaml` (see
governance/MIGRATION_MANIFEST.yaml capability `platform_consent`). Only the
taxonomy shape is reused; no code from that file is copied.

Three legal gaps recorded in `docs/06_platform/CONSENT.md` §3 are closed here.

**REFUSED (gaps 1).** 《儿童个人信息网络保护规定》第10条 requires the consent
interface to offer a refusal option and to disclose its consequences. A refusal
that is not recordable is not offered in any provable sense: with only
GRANTED / WITHDRAWN / EXPIRED, "we asked and the guardian said no" was
indistinguishable from "we never asked". Those two must be distinguishable,
because they lead to different obligations — a refusal must not be re-prompted
as though it were a fresh unanswered question, and it is the evidence that the
option existed.

**`expires_at` (gap 3).** 第10条 requires the storage period and the
end-of-period handling to be disclosed *in advance*, and 第12条 forbids
retention beyond necessity. `ConsentStatus.EXPIRED` already existed but no code
could ever produce it — a dead enum member. It is now derived from
`expires_at`, so expiry is a computed property of the grant rather than
something a caller has to remember to write.

**Age and guardianship (gap 4).** PIPL 第28/31条: for a subject under 14 every
piece of personal information is sensitive, and guardian consent is required.
`SubjectAge` and `GuardianRelation` make the check expressible. See
`ConsentGrant.__post_init__` and note carefully what the 14 line is *not* used
for, documented on `GuardianRelation`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum

#: The age below which every item of a subject's personal information is
#: sensitive personal information and guardian consent is mandatory (PIPL 第28条
#: "以及不满十四周岁未成年人的个人信息", 第31条).
#:
#: `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §9 corrects a common
#: misreading and that correction is binding here: this line governs **consent
#: to collect** and the default of guardian-facing monitoring UI. It must not be
#: used to close the statutory data-request channel for guardians of 14–17 year
#: olds — 《未成年人网络保护条例》第34条 gives the minor **and** the guardian
#: parallel rights with no age split. Nothing in this module keys any access
#: decision on age; it only decides whether guardian consent is *required*.
GUARDIAN_CONSENT_AGE_THRESHOLD = 14


def _as_comparable(moment: datetime, reference: datetime) -> datetime:
    """Put `moment` on the same naive/aware footing as `reference`.

    Grants may legitimately carry naive-UTC timestamps (see
    `ConsentGrant.__post_init__` on gap 7), while callers naturally pass
    `datetime.now(UTC)`. Comparing across the two raises TypeError, which would
    turn a missed expiry into a crash — and a crash in a consent check is a
    denial of service on a legal gate. Naive values are treated as UTC, which is
    what both domains' `utcnow()` actually produces.
    """
    if reference.tzinfo is None and moment.tzinfo is not None:
        return moment.astimezone(UTC).replace(tzinfo=None)
    if reference.tzinfo is not None and moment.tzinfo is None:
        return moment.replace(tzinfo=UTC)
    return moment


class ConsentPurpose(StrEnum):
    """Why a subject's data may be processed.

    A grant is always scoped to exactly one purpose — a grant for
    SERVICE does not imply a grant for AI_PERSONALIZATION. Widening scope
    (e.g. "consent for anything") is intentionally not representable.
    """

    SERVICE = "service"
    ASSESSMENT = "assessment"
    AI_PERSONALIZATION = "ai_personalization"
    GROWTH_TRACKING = "growth_tracking"


class ConsentStatus(StrEnum):
    """Lifecycle status of a single consent grant.

    ``REFUSED`` is not a synonym for ``WITHDRAWN``. Withdrawn means consent was
    given and later taken back; refused means it was offered and declined, and
    was therefore never in force. Both deny, but they are different facts, and
    only the second is evidence that 第10条's refusal option existed.
    """

    GRANTED = "granted"
    REFUSED = "refused"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class GuardianRelation(StrEnum):
    """How the guardian of record relates to the subject.

    ``SELF`` is how an adult (or a minor consenting on their own behalf where
    that is lawful) is represented: subject and guardian are the same person.
    ``GUARDIAN`` is a distinct person acting for the subject. ``NONE`` means no
    guardianship relation has been established — which is refused for a subject
    under `GUARDIAN_CONSENT_AGE_THRESHOLD`, because PIPL 第31条 requires one.

    This is a declared relation, not a verified one. Verifying that a given
    person really is a subject's guardian requires the Account →
    TenantMembership → Family binding chain (`governance/DOMAIN_REGISTRY.yaml` →
    `auth_identity`, `family_core`) and is still absent — see
    `docs/06_platform/CONSENT.md` §3. What this type removes is the previous
    situation where the relation could not even be *stated*, so no layer could
    check it.
    """

    SELF = "self"
    GUARDIAN = "guardian"
    NONE = "none"


@dataclass(frozen=True, slots=True)
class SubjectAge:
    """The subject's age in whole years at the time consent was recorded.

    A value object rather than a bare `int` so that "14" cannot arrive from
    somewhere that meant a year, a count, or a score. Negative and absurd values
    are rejected at construction: an age nobody can have would otherwise flow
    into the under-14 test and silently decide a compliance question.
    """

    years: int

    def __post_init__(self) -> None:
        if self.years < 0:
            raise ValueError("SubjectAge.years must not be negative")
        if self.years > 150:
            raise ValueError("SubjectAge.years is implausible; expected 0..150")

    @property
    def requires_guardian_consent(self) -> bool:
        """True below 14 (PIPL 第28/31条).

        Read this as "guardian consent is mandatory for collection", never as
        "the guardian loses rights at 14" — see
        `GUARDIAN_CONSENT_AGE_THRESHOLD`.
        """
        return self.years < GUARDIAN_CONSENT_AGE_THRESHOLD


@dataclass(frozen=True, slots=True)
class ConsentGrant:
    """A single consent decision.

    `subject_person_id` is the person the data is about; `guardian_person_id`
    is who recorded the decision on the subject's behalf. `guardian_relation`
    states how those two relate, and `subject_age` is what makes the under-14
    rule checkable at all.

    This is a pure value object: constructing one does not write anything
    anywhere. It does, however, refuse to represent a combination that is
    unlawful on its face — see `__post_init__`.
    """

    consent_id: str
    subject_person_id: str
    guardian_person_id: str
    purpose: ConsentPurpose
    status: ConsentStatus
    granted_at: datetime
    subject_age: SubjectAge
    guardian_relation: GuardianRelation
    #: When this grant stops being in force. ``None`` means "no expiry
    #: recorded", which is *not* the same as "never expires": callers that must
    #: satisfy 第10条's advance disclosure of the retention period have to set
    #: it. It is nullable so that an unexpiring grant is visibly missing a
    #: period rather than being given a fake far-future one.
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.consent_id:
            raise ValueError("ConsentGrant.consent_id must not be empty")
        if not self.subject_person_id:
            raise ValueError("ConsentGrant.subject_person_id must not be empty")
        if not self.guardian_person_id:
            raise ValueError("ConsentGrant.guardian_person_id must not be empty")

        # `granted_at` is deliberately *not* required to be timezone-aware.
        # That is `docs/06_platform/CONSENT.md` §3 gap 7, which remains open: the
        # service and membership domains both use a naive-UTC `utcnow()` because
        # the SQLite fast test path drops tzinfo, and tightening it here would
        # change their semantics rather than this module's. What is enforced is
        # that `granted_at` and `expires_at` are *comparable* — a mix of naive
        # and aware would raise TypeError deep inside `status_at`, turning an
        # expiry check into a crash.
        if self.expires_at is not None:
            if (self.expires_at.tzinfo is None) != (self.granted_at.tzinfo is None):
                raise ValueError(
                    "ConsentGrant.granted_at and expires_at must both be naive or "
                    "both be timezone-aware; a mixed pair cannot be compared"
                )
            if self.expires_at <= self.granted_at:
                raise ValueError(
                    "ConsentGrant.expires_at must be after granted_at — a grant that "
                    "expires at or before the moment it was given was never in force"
                )

        # PIPL 第31条. A subject under 14 needs a guardian who is someone else;
        # SELF would mean a child consented for themselves, and NONE would mean
        # no guardianship was established at all.
        if self.subject_age.requires_guardian_consent:
            if self.guardian_relation is not GuardianRelation.GUARDIAN:
                raise ValueError(
                    "a subject under "
                    f"{GUARDIAN_CONSENT_AGE_THRESHOLD} requires guardian_relation="
                    "GUARDIAN (PIPL art. 31: guardian consent is mandatory), got "
                    f"{self.guardian_relation.value!r}"
                )
            if self.guardian_person_id == self.subject_person_id:
                raise ValueError(
                    "guardian_person_id must differ from subject_person_id for a "
                    f"subject under {GUARDIAN_CONSENT_AGE_THRESHOLD} — a child cannot "
                    "be their own guardian"
                )
        elif self.guardian_relation is GuardianRelation.SELF:
            if self.guardian_person_id != self.subject_person_id:
                raise ValueError(
                    "guardian_relation=SELF requires guardian_person_id == subject_person_id"
                )

    def status_at(self, moment: datetime) -> ConsentStatus:
        """The effective status at `moment`, with expiry applied.

        This is where `ConsentStatus.EXPIRED` finally comes from. It is derived
        rather than stored so a grant cannot sit in a database looking GRANTED
        past its own retention period just because no scheduled job has run yet
        — the same argument `ConsentGate` makes for holding no cache.

        Terminal statuses are returned untouched: a WITHDRAWN or REFUSED grant
        does not become EXPIRED, because the reason it denies is not the
        passage of time and an audit trail must keep saying why.
        """
        if self.status is not ConsentStatus.GRANTED:
            return self.status
        if self.expires_at is None:
            return ConsentStatus.GRANTED
        if _as_comparable(moment, self.expires_at) >= self.expires_at:
            return ConsentStatus.EXPIRED
        return ConsentStatus.GRANTED

    def is_active_at(self, moment: datetime) -> bool:
        """True iff this grant is in force at `moment`."""
        return self.status_at(moment) is ConsentStatus.GRANTED

    @property
    def is_active(self) -> bool:
        """In force *now*.

        Kept as a property because callers read it as a plain predicate, but it
        is no longer a bare status comparison: it evaluates expiry against the
        current time, so a grant past `expires_at` reports False without anyone
        having had to run a job that rewrites its status.
        """
        return self.is_active_at(datetime.now(UTC))
