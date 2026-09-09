"""Request models for the SERVICE endpoints.

The absences are the contract. None of these carries `tenant_id`, `family_id`,
`actor_person_id`, `environment`, `correlation_id` or `idempotency_key`: those
are server-derived (`application/context.py`) or header-borne, so no request body
can inject them. A test asserts this by putting a foreign `family_id` in the body
and showing it has no effect.

`decided_by` is likewise absent. `assert_human_actor` inspects a *claim*, so a
client-supplied decider would let an AI-authenticated caller launder itself into
a human one. It is derived from `ctx.actor` in the route.

Field naming is snake_case throughout, matching the rest of
`contracts/openapi/UI_API_ENDPOINT_INVENTORY.md`. The one camelCase outlier that
inventory records (`startGrowthOnboarding`) is another domain's problem and is
not copied here.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel

from ..domain.value_objects import (
    AdmissionStatus,
    Channel,
    FamilyFeedbackOutcome,
    FeedbackAuthorRole,
    FeedbackIssueCode,
    ProviderKind,
    QualificationStatus,
    QualityDecisionStatus,
    ServiceActionType,
    ServiceQualityRating,
)


class RegisterServiceProviderRequest(BaseModel):
    provider_ref: str
    display_name: str
    provider_kind: ProviderKind
    qualification_status: QualificationStatus
    admission_status: AdmissionStatus
    source_ref: str
    qualification_ref: str | None = None


class PublishServiceOfferingRequest(BaseModel):
    provider_id: str
    service_offering_ref: str
    title: str
    admission_status: AdmissionStatus
    source_ref: str
    version_no: int = 1
    scenario_ref: str = "S-01_21_DAY_EVENING_STUDY_START_CONFLICT_REDUCTION"


class OpenAvailabilitySlotRequest(BaseModel):
    service_offering_id: str
    availability_slot_ref: str
    starts_at: datetime
    ends_at: datetime
    channel: Channel
    capacity: int = 1


class SubmitBookingRequest(BaseModel):
    """`subject_person_id` is required, not optional.

    It is the person being served, and the consent check needs a subject:
    "does this family have consent" is not a well-formed question, because
    consent belongs to a person. Making it optional would mean a caller could
    omit it and reach a code path with nothing to check.
    """

    service_offering_id: str
    availability_slot_id: str
    booking_ref: str
    source_page_id: str
    subject_person_id: str
    consent_ref: str


class FulfilServiceRecordRequest(BaseModel):
    """`quality_rating` rates the provider's delivered session, never the family.

    Optional because a family that does not want to evaluate the session must
    still be able to close it — a required rating makes "say nothing"
    impossible.
    """

    quality_rating: ServiceQualityRating | None = None


class RecordFamilyFeedbackRequest(BaseModel):
    subject_person_id: str
    author_role: FeedbackAuthorRole
    outcome: FamilyFeedbackOutcome
    issue_codes: list[FeedbackIssueCode] = []
    consent_ref: str


class DecideServiceQualityRequest(BaseModel):
    delivery_record_id: str
    status: QualityDecisionStatus
    family_feedback_id: str | None = None


class RecordServiceActionRequest(BaseModel):
    action_type: ServiceActionType
    delivery_record_id: str | None = None
    family_feedback_id: str | None = None
    sla_due_at: datetime | None = None
    occurred_at: datetime | None = None


class CreatePrivateCheckinDraftRequest(BaseModel):
    """No free-text field, by design. `action_ref` is allow-listed
    (`CHECKIN_ACTION_REFS`); an allow-list cannot carry a child fact."""

    action_ref: str
