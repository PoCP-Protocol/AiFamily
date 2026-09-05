"""Adult contribution-ledger contracts.

This module is deliberately separate from the existing points commands.  A
contribution is a verified business fact; a PlatformPoint entry is one possible
release consequence.  FGCN contribution units and settlement amounts are
different ledgers and are represented by different value objects here.
"""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Final, Literal

from pydantic import BaseModel, Field, model_validator


class ContributionError(Exception):
    """Base error mapped by the contribution HTTP adapter."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class ContributionValidationError(ContributionError):
    pass


class ContributionForbiddenError(ContributionError):
    pass


class ContributionNotFoundError(ContributionError):
    pass


class ContributionConflictError(ContributionError):
    pass


class ContributionStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    REVIEWED = "REVIEWED"
    VERIFIED = "VERIFIED"
    HELD = "HELD"
    RELEASED = "RELEASED"
    REJECTED = "REJECTED"
    APPEAL = "APPEAL"
    REVERSED = "REVERSED"


ContentType = Literal["ARTICLE", "AUDIO", "IMAGE", "VIDEO", "TEMPLATE"]
REWARD_BASIS: Final[str] = "VERIFIED_ADULT_CONTRIBUTION"
POINTS_PER_RELEASED_CONTRIBUTION: Final[int] = 20
FORBIDDEN_REWARD_BASIS_TOKENS: Final[frozenset[str]] = frozenset(
    {
        "child",
        "minor",
        "exposure",
        "like",
        "likes",
        "score",
        "grade",
        "ranking",
        "emotion",
        "sentiment",
        "growth_outcome",
        "growth-result",
    }
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class ContributionRecord(BaseModel):
    contribution_id: str
    tenant_id: str
    contributor_family_id: str
    contributor_person_id: str
    contributor_is_adult: bool
    adult_verification_ref: str
    consumer_family_id: str
    content_ref: str
    content_type: ContentType
    content_version: int = Field(default=1, ge=1)
    purpose: str
    copyright_attestation_ref: str
    privacy_redaction_ref: str
    status: ContributionStatus = ContributionStatus.SUBMITTED
    review_ref: str | None = None
    reviewed_by: str | None = None
    use_confirmation_ref: str | None = None
    use_confirmed_by: str | None = None
    hold_reason: str | None = None
    release_ref: str | None = None
    platform_point_entry_id: str | None = None
    appeal_ref: str | None = None
    appeal_reason: str | None = None
    reversal_ref: str | None = None
    decision_code: str | None = None
    created_at: datetime = Field(default_factory=utcnow)
    updated_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def validate_required_references(self) -> ContributionRecord:
        required = {
            "contribution_id": self.contribution_id,
            "tenant_id": self.tenant_id,
            "contributor_family_id": self.contributor_family_id,
            "contributor_person_id": self.contributor_person_id,
            "adult_verification_ref": self.adult_verification_ref,
            "consumer_family_id": self.consumer_family_id,
            "content_ref": self.content_ref,
            "purpose": self.purpose,
            "copyright_attestation_ref": self.copyright_attestation_ref,
            "privacy_redaction_ref": self.privacy_redaction_ref,
        }
        if any(not value.strip() for value in required.values()):
            raise ContributionValidationError("contribution_reference_required")
        return self

    def transition(self, target: ContributionStatus) -> None:
        allowed: dict[ContributionStatus, frozenset[ContributionStatus]] = {
            ContributionStatus.SUBMITTED: frozenset(
                {ContributionStatus.REVIEWED, ContributionStatus.REJECTED}
            ),
            ContributionStatus.REVIEWED: frozenset(
                {ContributionStatus.VERIFIED, ContributionStatus.REJECTED}
            ),
            ContributionStatus.VERIFIED: frozenset({ContributionStatus.HELD}),
            ContributionStatus.HELD: frozenset({ContributionStatus.RELEASED}),
            ContributionStatus.RELEASED: frozenset(
                {ContributionStatus.APPEAL, ContributionStatus.REVERSED}
            ),
            ContributionStatus.APPEAL: frozenset(
                {
                    ContributionStatus.RELEASED,
                    ContributionStatus.VERIFIED,
                    ContributionStatus.REJECTED,
                    ContributionStatus.REVERSED,
                }
            ),
            ContributionStatus.REJECTED: frozenset({ContributionStatus.APPEAL}),
            ContributionStatus.REVERSED: frozenset(),
        }
        if target not in allowed[self.status]:
            raise ContributionConflictError(
                f"invalid_contribution_transition:{self.status}->{target}"
            )
        self.status = target
        self.updated_at = utcnow()


class ReviewDecision(BaseModel):
    review_ref: str
    reviewer_person_id: str
    content_approved: bool
    copyright_approved: bool
    safety_approved: bool
    reason_code: str

    @property
    def approved(self) -> bool:
        return self.content_approved and self.copyright_approved and self.safety_approved


class PlatformPoint(BaseModel):
    """A points-ledger entry; it is not FGCN capacity or cash."""

    entry_id: str
    tenant_id: str
    family_id: str
    contribution_id: str
    points_delta: int
    reward_basis: Literal["VERIFIED_ADULT_CONTRIBUTION", "REFUND_REVERSAL"]
    reversal_of_entry_id: str | None = None
    created_at: datetime = Field(default_factory=utcnow)

    @model_validator(mode="after")
    def validate_sign_and_basis(self) -> PlatformPoint:
        if self.reward_basis == "VERIFIED_ADULT_CONTRIBUTION" and self.points_delta <= 0:
            raise ContributionValidationError("platform_point_release_must_be_positive")
        if self.reward_basis == "REFUND_REVERSAL" and (
            self.points_delta >= 0 or not self.reversal_of_entry_id
        ):
            raise ContributionValidationError("platform_point_reversal_must_be_negative")
        return self


class FGCNContributionUnit(BaseModel):
    """Case allocation units; never a points or money representation."""

    unit_id: str
    contribution_id: str
    units: int = Field(gt=0)
    allocation_basis_ref: str


class SettlementAmount(BaseModel):
    """Adult settlement amount; never stored on the points ledger."""

    settlement_id: str
    contribution_id: str
    minor_units: int = Field(gt=0)
    currency: str = Field(min_length=3, max_length=3)
    settlement_basis_ref: str


class ContributionAuditEvent(BaseModel):
    event_id: str
    tenant_id: str
    family_id: str
    actor_person_id: str
    actor: str
    action: str
    resource_id: str
    before_status: ContributionStatus | None
    after_status: ContributionStatus
    reason_code: str
    correlation_id: str
    created_at: datetime = Field(default_factory=utcnow)


class ContributionOutboxEvent(BaseModel):
    event_id: str
    tenant_id: str
    family_id: str
    aggregate_id: str
    event_type: str
    payload: dict[str, str]
    correlation_id: str
    created_at: datetime = Field(default_factory=utcnow)


class ContributionOperation(BaseModel):
    operation_id: str
    tenant_id: str
    family_id: str
    idempotency_key: str
    action: str
    request_fingerprint: str
    resource_id: str
    created_at: datetime = Field(default_factory=utcnow)


def require_human_actor(actor: str) -> None:
    if actor.startswith(("ai:", "system:")):
        raise ContributionForbiddenError("human_actor_required")


def require_adult(adult_verified: bool, verification_ref: str) -> None:
    if not adult_verified or not verification_ref.strip():
        raise ContributionForbiddenError("adult_contributor_required")


def require_family_scope(record: ContributionRecord, family_id: str, *, role: str) -> None:
    expected = record.contributor_family_id if role == "contributor" else record.consumer_family_id
    if expected != family_id:
        raise ContributionForbiddenError("family_scope_denied")


def require_safe_reward_basis(basis: str) -> None:
    normalized = basis.strip().lower()
    if any(token in normalized for token in FORBIDDEN_REWARD_BASIS_TOKENS):
        raise ContributionForbiddenError("child_or_outcome_reward_basis_forbidden")
    if basis != REWARD_BASIS:
        raise ContributionValidationError("unsupported_reward_basis")
