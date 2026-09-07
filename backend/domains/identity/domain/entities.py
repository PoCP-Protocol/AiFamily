"""Business identity aggregates: Account, IdentitySession, OtpChallenge.

Plain dataclasses, not pydantic models — mirrors `domains/membership/domain`'s
convention of keeping the domain layer free of any persistence or transport
concern. `model_dump()`-shaped mapping to ORM rows happens in the
infrastructure layer via `dataclasses.asdict`, not by inheriting from an ORM
base here.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .errors import IdentityValidationError


@dataclass(frozen=True, slots=True)
class Account:
    """A registered identity. `external_ref` is the caller-supplied identifier
    dev/test exchanges for a session (`<account>:<family>` convention);
    production issuance is expected to bind it to a real login proof instead
    (OTP, password, SSO) once one of those channels exists — see
    `OtpChallenge` below for the frozen shape that first channel will use.
    """

    account_id: str
    external_ref: str
    created_at: datetime

    def __post_init__(self) -> None:
        if not self.account_id:
            raise IdentityValidationError("ACCOUNT_ID_REQUIRED")
        if not self.external_ref:
            raise IdentityValidationError("EXTERNAL_REF_REQUIRED")


@dataclass(frozen=True, slots=True)
class IdentitySession:
    """A bearer session bound to an account and (optionally) a family scope.

    `revoked_at` is `None` while the session is live. `is_valid_at(now)` is the
    single place expiry *and* revocation are both checked — callers must not
    reimplement this comparison, so a future change to either rule only needs
    one edit.
    """

    session_id: str
    account_id: str
    family_id: str
    issued_at: datetime
    expires_at: datetime
    revoked_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.session_id:
            raise IdentityValidationError("SESSION_ID_REQUIRED")
        if not self.account_id:
            raise IdentityValidationError("ACCOUNT_ID_REQUIRED")
        if not self.family_id:
            raise IdentityValidationError("FAMILY_ID_REQUIRED")
        if self.expires_at <= self.issued_at:
            raise IdentityValidationError("EXPIRES_AT_MUST_BE_AFTER_ISSUED_AT")

    def is_valid_at(self, now: datetime) -> bool:
        if self.revoked_at is not None:
            return False
        return now < self.expires_at

    def revoke(self, *, at: datetime) -> IdentitySession:
        """Return a new, revoked copy. Frozen dataclass: never mutate in place —
        the audit trail must be able to trust that a session object handed to
        one caller cannot be silently flipped live by another (same rationale
        as `ActorContext`, `backend/platform/identity/context.py`)."""

        if self.revoked_at is not None:
            return self
        return IdentitySession(
            session_id=self.session_id,
            account_id=self.account_id,
            family_id=self.family_id,
            issued_at=self.issued_at,
            expires_at=self.expires_at,
            revoked_at=at,
        )


@dataclass(frozen=True, slots=True)
class OtpChallenge:
    """A one-time-passcode challenge for a login/verification flow.

    **Not wired to any endpoint yet.** This shape and `OtpSender` (see
    `application/ports.py`) exist so the *next* increment (real login proof)
    has a designed seam rather than an invented one, per
    `governance/DOMAIN_REGISTRY.yaml` -> `auth_identity.known_gaps`: "源仓库
    OtpService 的 StubOtpSender 是唯一显式标注的替换点". Deciding which SMS/email
    provider to integrate is a business/legal decision (contracts, opt-in
    consent copy, delivery SLAs) out of scope for this slice — same posture
    `backend/intelligence/model_gateway` takes toward model provider selection.
    """

    challenge_id: str
    account_id: str
    channel: str  # "sms" | "email" — free-form until a real sender exists
    destination: str
    code_hash: str
    created_at: datetime
    expires_at: datetime
    consumed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.challenge_id:
            raise IdentityValidationError("CHALLENGE_ID_REQUIRED")
        if not self.account_id:
            raise IdentityValidationError("ACCOUNT_ID_REQUIRED")
        if self.channel not in ("sms", "email"):
            raise IdentityValidationError("CHANNEL_MUST_BE_SMS_OR_EMAIL")
        if not self.destination:
            raise IdentityValidationError("DESTINATION_REQUIRED")
        if not self.code_hash:
            raise IdentityValidationError("CODE_HASH_REQUIRED")
        if self.expires_at <= self.created_at:
            raise IdentityValidationError("EXPIRES_AT_MUST_BE_AFTER_CREATED_AT")

    def is_valid_at(self, now: datetime) -> bool:
        if self.consumed_at is not None:
            return False
        return now < self.expires_at
