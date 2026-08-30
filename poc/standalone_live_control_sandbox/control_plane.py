"""Synthetic H-LIVE-02 control-plane contract.

This module is a disposable sandbox for validating the orchestration boundary
between the standalone Live product and AiFamily Platform Core.  It is not a
production domain, database adapter, consent ledger, audit ledger, or HTTP
route.  In particular, consent, audit/outbox, and idempotency are ports: the
production implementation must be supplied by the canonical platform owners.

The sandbox deliberately models one user action only: an authenticated adult
registers for an approved, current, Family-scoped live session after the
canonical Consent port confirms the purpose-specific grant.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from hashlib import sha256
from typing import Protocol

SANDBOX_SOURCE = "SANDBOX_SYNTHETIC"
LIVE_ATTENDANCE_PURPOSE = "live_attendance"


class SandboxBoundaryError(ValueError):
    """A synthetic fixture violates the explicit sandbox boundary."""


class RegistrationRejected(RuntimeError):
    """The authenticated adult cannot register for this session."""


class ConsentRequired(RegistrationRejected):
    """The canonical Consent port did not grant the required purpose."""


class ScopeViolation(RegistrationRejected):
    """A request crossed its authenticated tenant or family boundary."""


class IdempotencyConflict(RegistrationRejected):
    """One idempotency key was reused for a different command."""


class SessionStatus(StrEnum):
    SCHEDULED = "SCHEDULED"
    LIVE = "LIVE"
    WITHDRAWN = "WITHDRAWN"
    EXPIRED = "EXPIRED"


class ReviewStatus(StrEnum):
    APPROVED = "APPROVED"
    WITHDRAWN = "WITHDRAWN"
    REJECTED = "REJECTED"


class RegistrationStatus(StrEnum):
    CONFIRMED = "CONFIRMED"
    CANCELLED = "CANCELLED"
    REVOKED = "REVOKED"


@dataclass(frozen=True, slots=True)
class GuardianContext:
    """Authenticated adult context derived by the host application."""

    tenant_id: str
    family_id: str
    guardian_id: str

    def __post_init__(self) -> None:
        if not all((self.tenant_id, self.family_id, self.guardian_id)):
            raise ValueError("guardian context fields must not be empty")


@dataclass(frozen=True, slots=True)
class LiveSessionFixture:
    """A synthetic projection used only by this sandbox."""

    tenant_id: str
    family_id: str
    session_ref: str
    title: str
    review_status: ReviewStatus
    status: SessionStatus
    audience_scope: frozenset[str]
    starts_at: datetime
    ends_at: datetime
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True

    def __post_init__(self) -> None:
        if not self.fixture_only or self.source != SANDBOX_SOURCE:
            raise SandboxBoundaryError("control fixture must be explicitly synthetic")
        if not all((self.tenant_id, self.family_id, self.session_ref, self.title)):
            raise ValueError("live session identity and title must not be empty")
        if self.ends_at <= self.starts_at:
            raise ValueError("live session end must follow start")
        if not self.audience_scope:
            raise ValueError("live session audience scope must not be empty")


@dataclass(frozen=True, slots=True)
class CanonicalConsentDecision:
    """Read-only result returned by AiFamily's canonical Consent boundary."""

    consent_ref: str
    tenant_id: str
    family_id: str
    guardian_id: str
    purpose: str
    granted: bool
    expires_at: datetime | None = None


class CanonicalConsentPort(Protocol):
    """Production-owned purpose-specific Consent lookup; no local ledger."""

    def require_grant(
        self,
        *,
        tenant_id: str,
        family_id: str,
        guardian_id: str,
        purpose: str,
        session_ref: str,
        now: datetime,
    ) -> CanonicalConsentDecision: ...


@dataclass(frozen=True, slots=True)
class MutationAudit:
    """Data sent to canonical Audit/Outbox, never stored by this sandbox."""

    action: str
    actor_id: str
    tenant_id: str
    family_id: str
    resource_ref: str
    purpose: str
    correlation_id: str


class CanonicalAuditOutboxPort(Protocol):
    """Production-owned atomic mutation + AuditEvent + Outbox boundary."""

    def commit_registration(
        self,
        *,
        registration: Registration,
        audit: MutationAudit,
        event_type: str,
        idempotency_key: str,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class Registration:
    registration_ref: str
    session_ref: str
    tenant_id: str
    family_id: str
    guardian_id: str
    consent_ref: str
    status: RegistrationStatus
    correlation_id: str


@dataclass(frozen=True, slots=True)
class RegistrationReceipt:
    registration: Registration
    replayed: bool = False
    source: str = SANDBOX_SOURCE
    fixture_only: bool = True


class InMemoryAtomicRegistrationStore:
    """Test double for the canonical atomic repository.

    This is intentionally an in-memory fixture, not a second product ledger.
    It records only sandbox command receipts so that failure atomicity and
    idempotent replay can be tested before a real Platform Core adapter exists.
    """

    def __init__(self) -> None:
        self._by_key: dict[str, tuple[str, Registration]] = {}
        self.commits: list[tuple[Registration, MutationAudit, str, str]] = []
        self.fail_next_commit = False

    def commit_registration(
        self,
        *,
        registration: Registration,
        audit: MutationAudit,
        event_type: str,
        idempotency_key: str,
    ) -> None:
        if self.fail_next_commit:
            self.fail_next_commit = False
            raise RuntimeError("synthetic atomic commit failure")
        fingerprint = _command_fingerprint(registration.session_ref, registration.family_id)
        self._by_key[idempotency_key] = (fingerprint, registration)
        self.commits.append((registration, audit, event_type, idempotency_key))

    def receipt_for(self, idempotency_key: str) -> tuple[str, Registration] | None:
        return self._by_key.get(idempotency_key)


class SandboxLiveControlPlane:
    """H-LIVE-02 registration orchestration over explicit platform ports."""

    def __init__(
        self,
        *,
        consent: CanonicalConsentPort,
        audit_outbox: CanonicalAuditOutboxPort,
    ) -> None:
        self._consent = consent
        self._audit_outbox = audit_outbox

    def register(
        self,
        *,
        session: LiveSessionFixture,
        guardian: GuardianContext,
        idempotency_key: str,
        correlation_id: str,
        now: datetime,
    ) -> RegistrationReceipt:
        """Register an adult after a live-attendance Consent decision.

        No media capability, room URL, notification, payment, or external
        provider call is created here.  The only mutation is delegated to the
        canonical atomic Audit/Outbox port.
        """

        if not idempotency_key or not correlation_id:
            raise ValueError("idempotency_key and correlation_id are required")
        if session.tenant_id != guardian.tenant_id or session.family_id != guardian.family_id:
            raise ScopeViolation("session is outside the authenticated family scope")
        if session.review_status is not ReviewStatus.APPROVED:
            raise RegistrationRejected("live session is not approved")
        if session.status in {SessionStatus.WITHDRAWN, SessionStatus.EXPIRED}:
            raise RegistrationRejected("live session is unavailable")
        if session.ends_at.astimezone(UTC) <= now.astimezone(UTC):
            raise RegistrationRejected("live session is expired")
        if guardian.guardian_id not in session.audience_scope:
            raise ScopeViolation("guardian is outside the audience scope")

        fingerprint = _command_fingerprint(session.session_ref, session.family_id)
        previous = self._lookup(idempotency_key)
        if previous is not None:
            previous_fingerprint, previous_registration = previous
            if previous_fingerprint != fingerprint:
                raise IdempotencyConflict("idempotency key was reused for another session")
            return RegistrationReceipt(registration=previous_registration, replayed=True)

        decision = self._consent.require_grant(
            tenant_id=guardian.tenant_id,
            family_id=guardian.family_id,
            guardian_id=guardian.guardian_id,
            purpose=LIVE_ATTENDANCE_PURPOSE,
            session_ref=session.session_ref,
            now=now,
        )
        if not _consent_is_valid(decision, guardian, now):
            raise ConsentRequired("canonical live-attendance Consent is not active")

        registration = Registration(
            registration_ref=f"registration.synthetic.{len(self._commits()) + 1}",
            session_ref=session.session_ref,
            tenant_id=guardian.tenant_id,
            family_id=guardian.family_id,
            guardian_id=guardian.guardian_id,
            consent_ref=decision.consent_ref,
            status=RegistrationStatus.CONFIRMED,
            correlation_id=correlation_id,
        )
        audit = MutationAudit(
            action="register_live_session",
            actor_id=guardian.guardian_id,
            tenant_id=guardian.tenant_id,
            family_id=guardian.family_id,
            resource_ref=registration.registration_ref,
            purpose=LIVE_ATTENDANCE_PURPOSE,
            correlation_id=correlation_id,
        )
        self._audit_outbox.commit_registration(
            registration=registration,
            audit=audit,
            event_type="live.registration.confirmed",
            idempotency_key=idempotency_key,
        )
        return RegistrationReceipt(registration=registration)

    def _lookup(self, idempotency_key: str) -> tuple[str, Registration] | None:
        lookup = getattr(self._audit_outbox, "receipt_for", None)
        if lookup is None:
            return None
        return lookup(idempotency_key)

    def _commits(self) -> list[object]:
        commits = getattr(self._audit_outbox, "commits", None)
        return commits if commits is not None else []


def _consent_is_valid(
    decision: CanonicalConsentDecision, guardian: GuardianContext, now: datetime
) -> bool:
    if not decision.granted:
        return False
    if decision.purpose != LIVE_ATTENDANCE_PURPOSE:
        return False
    if decision.tenant_id != guardian.tenant_id:
        return False
    if decision.family_id != guardian.family_id:
        return False
    if decision.guardian_id != guardian.guardian_id:
        return False
    return decision.expires_at is None or decision.expires_at.astimezone(UTC) > now.astimezone(UTC)


def _command_fingerprint(session_ref: str, family_id: str) -> str:
    return sha256(f"{family_id}:{session_ref}".encode()).hexdigest()
