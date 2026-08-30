"""Immutable consent value objects.

The platform owns the cross-domain shape of a consent decision. It does not
own identity verification, the tenant/family binding store, or persistence.
Those responsibilities remain with their respective domains and adapters.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class ConsentPurpose(StrEnum):
    """Why a subject's data may be processed."""

    SERVICE = "service"
    ASSESSMENT = "assessment"
    AI_PERSONALIZATION = "ai_personalization"
    GROWTH_TRACKING = "growth_tracking"


class ConsentStatus(StrEnum):
    """Lifecycle status of a single consent grant."""

    GRANTED = "granted"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


class GuardianRelation(StrEnum):
    """The recorded relation between the consent subject and grantor."""

    SELF = "self"
    GUARDIAN = "guardian"


@dataclass(frozen=True, slots=True)
class SubjectAge:
    """Subject age in whole years when a consent decision was recorded.

    This small value object is used by already-shipped adapters that need to
    carry the age used for a consent policy decision. It does not itself
    decide whether a person may exercise a legal right.
    """

    years: int

    def __post_init__(self) -> None:
        if not isinstance(self.years, int) or isinstance(self.years, bool):
            raise TypeError("SubjectAge.years must be an integer")
        if self.years < 0:
            raise ValueError("SubjectAge.years must not be negative")


def _is_aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _as_comparable(value: datetime, reference: datetime) -> datetime:
    """Normalise ``value`` to the naive/aware convention of ``reference``."""

    if _is_aware(reference):
        if not _is_aware(value):
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)
    if _is_aware(value):
        return value.astimezone(UTC).replace(tzinfo=None)
    return value


@dataclass(frozen=True, slots=True)
class ConsentGrant:
    """A purpose- and subject-scoped consent decision.

    ``tenant_id`` and ``family_id`` are optional only for compatibility with
    the original in-process callers. A scope-aware caller must provide both;
    :meth:`matches_scope` then fails closed when either side is absent or does
    not match. No constructor writes to a store.

    The effective interval is half-open: ``effective_from`` is inclusive and
    ``effective_to`` is exclusive. ``expires_at`` is accepted as a legacy
    spelling for ``effective_to`` because existing adapters use that name.
    """

    consent_id: str
    subject_person_id: str
    guardian_person_id: str
    purpose: ConsentPurpose
    status: ConsentStatus
    granted_at: datetime
    tenant_id: str | None = None
    family_id: str | None = None
    guardian_relation: GuardianRelation | None = None
    subject_age: SubjectAge | None = None
    effective_from: datetime | None = None
    effective_to: datetime | None = None
    withdrawn_at: datetime | None = None
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        for field_name in (
            "consent_id",
            "subject_person_id",
            "guardian_person_id",
        ):
            value = getattr(self, field_name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"ConsentGrant.{field_name} must not be empty")

        for field_name in ("tenant_id", "family_id"):
            value = getattr(self, field_name)
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ValueError(f"ConsentGrant.{field_name} must not be empty")

        if self.guardian_relation is not None and not isinstance(
            self.guardian_relation, GuardianRelation
        ):
            raise TypeError("ConsentGrant.guardian_relation must be GuardianRelation")
        if self.subject_age is not None and not isinstance(self.subject_age, SubjectAge):
            raise TypeError("ConsentGrant.subject_age must be SubjectAge")

        effective_from = self.effective_from or self.granted_at
        effective_to = self.effective_to or self.expires_at
        if (
            self.effective_to is not None
            and self.expires_at is not None
            and _as_comparable(self.effective_to, self.expires_at) != self.expires_at
        ):
            raise ValueError(
                "ConsentGrant.effective_to and expires_at must describe the same boundary"
            )
        if (
            effective_to is not None
            and _as_comparable(effective_to, effective_from) <= effective_from
        ):
            raise ValueError("ConsentGrant.effective_to must be after effective_from")

        if self.withdrawn_at is not None and not isinstance(self.withdrawn_at, datetime):
            raise TypeError("ConsentGrant.withdrawn_at must be datetime or None")

    @property
    def effective_window(self) -> tuple[datetime, datetime | None]:
        """Return the effective interval as ``(start, exclusive_end)``."""

        return self.effective_from or self.granted_at, self.effective_to or self.expires_at

    def status_at(self, moment: datetime | None = None) -> ConsentStatus:
        """Return the status at ``moment`` without mutating the grant.

        Withdrawal is terminal and takes precedence over a later expiry, so
        audit consumers can distinguish a withdrawn grant from an expired one.
        A future effective start remains ``GRANTED`` but is not active yet;
        there is no extra persisted status needed for that window state.
        """

        if self.status is not ConsentStatus.GRANTED:
            return self.status

        at = moment or datetime.now(UTC)
        if (
            self.withdrawn_at is not None
            and _as_comparable(at, self.withdrawn_at) >= self.withdrawn_at
        ):
            return ConsentStatus.WITHDRAWN

        _, effective_to = self.effective_window
        if effective_to is not None and _as_comparable(at, effective_to) >= effective_to:
            return ConsentStatus.EXPIRED
        return ConsentStatus.GRANTED

    def is_active_at(self, moment: datetime | None = None) -> bool:
        """Return whether this grant is in force at ``moment``."""

        at = moment or datetime.now(UTC)
        effective_from, effective_to = self.effective_window
        if _as_comparable(at, effective_from) < effective_from:
            return False
        if effective_to is not None and _as_comparable(at, effective_to) >= effective_to:
            return False
        return self.status_at(at) is ConsentStatus.GRANTED

    def matches_scope(
        self,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: ConsentPurpose,
    ) -> bool:
        """Return true only for an exact tenant/family/subject/purpose match."""

        return (
            self.tenant_id == tenant_id
            and self.family_id == family_id
            and self.subject_person_id == subject_person_id
            and self.purpose is purpose
        )

    def is_active_for(
        self,
        *,
        tenant_id: str,
        family_id: str,
        subject_person_id: str,
        purpose: ConsentPurpose,
        moment: datetime | None = None,
    ) -> bool:
        """Combine exact scope matching with the current effective window."""

        return self.matches_scope(
            tenant_id=tenant_id,
            family_id=family_id,
            subject_person_id=subject_person_id,
            purpose=purpose,
        ) and self.is_active_at(moment)

    @property
    def is_active(self) -> bool:
        """Whether this grant is active now."""

        return self.is_active_at()


__all__ = [
    "ConsentGrant",
    "ConsentPurpose",
    "ConsentStatus",
    "GuardianRelation",
    "SubjectAge",
]
