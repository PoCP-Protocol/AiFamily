"""Domain objects for the first GrowthIntent to Journey vertical slice.

This module is intentionally separate from the existing Journey WIP.  The
current ``growth_journeys`` table predates this command and has no intent
foreign-key column.  Persistence therefore writes a separately queryable
intent binding in the same transaction; the deterministic identifier is only
an idempotency aid and is not the binding proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, UUID, uuid5

from .errors import (
    JourneyConflictError,
    JourneyForbiddenError,
    JourneyNotFoundError,
    JourneyValidationError,
)

CONFIRMED_INTENT_BOUNDARY = "HUMAN_CONFIRMED_INTENT_NOT_OUTCOME"
GROWTH_TRACKING_PURPOSE = "GROWTH_TRACKING"
GROWTH_ONBOARDING_ACTION = "StartGrowthOnboarding"
GROWTH_ONBOARDING_EVENT = "GrowthOnboardingStarted"
GROWTH_ONBOARDING_EVENT_VERSION = 1
GROWTH_JOURNEY_TYPE = "PARENT_CHILD_COMMUNICATION_CONFLICT"
GROWTH_JOURNEY_PHASE = "ONBOARDING"
GROWTH_JOURNEY_STATUS = "ACTIVE"


class GrowthOnboardingValidationError(JourneyValidationError):
    """The command or scope is malformed."""


class GrowthOnboardingForbiddenError(JourneyForbiddenError):
    """The actor lacks the required family or consent scope."""


class GrowthOnboardingNotFoundError(JourneyNotFoundError):
    """The requested confirmed intent or onboarding is not visible."""


class GrowthOnboardingConflictError(JourneyConflictError):
    """A replay or uniqueness request conflicts with stored state."""


@dataclass(frozen=True)
class GrowthOnboardingScope:
    tenant_id: str
    family_id: str
    actor_id: str


@dataclass(frozen=True)
class ConfirmedGrowthIntent:
    """The minimum cross-domain read contract consumed by Journey.

    The current canonical schema stores a confirmed intent as an ``OPEN`` row
    with immutable confirmation markers and the human-confirmed boundary.
    Confirmation is therefore the conjunction of all four facts, rather than
    a shortcut that treats every OPEN row as confirmed.
    """

    intent_id: str
    tenant_id: str
    family_id: str
    subject_person_id: str
    need_type: str
    goal_text: str
    required_capability_keys: tuple[str, ...]
    status: str
    confirmed_by: str | None
    confirmed_at: datetime | None
    boundary: str

    @property
    def is_confirmed(self) -> bool:
        return (
            self.status == "OPEN"
            and bool(self.confirmed_by and self.confirmed_by.strip())
            and self.confirmed_at is not None
            and self.boundary == CONFIRMED_INTENT_BOUNDARY
        )


@dataclass(frozen=True)
class GrowthOnboarding:
    onboarding_id: str
    tenant_id: str
    family_id: str
    intent_id: str
    subject_person_id: str
    journey_type: str
    phase: str
    status: str
    started_by_actor_id: str
    started_at: datetime
    version: int = 1
    binding_id: str | None = None

    @classmethod
    def start(
        cls,
        scope: GrowthOnboardingScope,
        intent: ConfirmedGrowthIntent,
        *,
        started_at: datetime | None = None,
    ) -> GrowthOnboarding:
        onboarding_id = str(
            uuid5(
                NAMESPACE_URL,
                f"growth-onboarding:{scope.tenant_id}:{scope.family_id}:{intent.intent_id}",
            )
        )
        return cls(
            onboarding_id=onboarding_id,
            tenant_id=scope.tenant_id,
            family_id=scope.family_id,
            intent_id=intent.intent_id,
            subject_person_id=intent.subject_person_id,
            journey_type=GROWTH_JOURNEY_TYPE,
            phase=GROWTH_JOURNEY_PHASE,
            status=GROWTH_JOURNEY_STATUS,
            started_by_actor_id=scope.actor_id,
            started_at=started_at or datetime.now(UTC),
        )

    @property
    def started_event_id(self) -> str:
        return str(uuid5(NAMESPACE_URL, f"{GROWTH_ONBOARDING_EVENT}:{self.onboarding_id}"))

    def as_dict(self) -> dict[str, object]:
        return {
            "onboarding_id": self.onboarding_id,
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
            "intent_id": self.intent_id,
            "subject_person_id": self.subject_person_id,
            "journey_type": self.journey_type,
            "phase": self.phase,
            "status": self.status,
            "started_by_actor_id": self.started_by_actor_id,
            "started_at": self.started_at.isoformat(),
            "version": self.version,
            "intent_binding": {
                "binding_id": self.binding_id,
                "tenant_id": self.tenant_id,
                "family_id": self.family_id,
                "intent_id": self.intent_id,
                "onboarding_id": self.onboarding_id,
                "subject_person_id": self.subject_person_id,
            },
        }


@dataclass(frozen=True)
class GrowthOnboardingStarted:
    event_id: str
    tenant_id: str
    family_id: str
    actor_id: str
    intent_id: str
    onboarding_id: str
    subject_person_id: str
    occurred_at: datetime
    event_version: int = GROWTH_ONBOARDING_EVENT_VERSION

    @classmethod
    def from_onboarding(
        cls, onboarding: GrowthOnboarding, *, occurred_at: datetime | None = None
    ) -> GrowthOnboardingStarted:
        return cls(
            event_id=onboarding.started_event_id,
            tenant_id=onboarding.tenant_id,
            family_id=onboarding.family_id,
            actor_id=onboarding.started_by_actor_id,
            intent_id=onboarding.intent_id,
            onboarding_id=onboarding.onboarding_id,
            subject_person_id=onboarding.subject_person_id,
            occurred_at=occurred_at or onboarding.started_at,
        )

    def as_dict(self) -> dict[str, object]:
        return {
            "event_id": self.event_id,
            "event_name": GROWTH_ONBOARDING_EVENT,
            "event_version": self.event_version,
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
            "actor_id": self.actor_id,
            "intent_id": self.intent_id,
            "onboarding_id": self.onboarding_id,
            "subject_person_id": self.subject_person_id,
            "occurred_at": self.occurred_at.isoformat(),
        }


def validate_uuid(value: str, code: str) -> None:
    try:
        UUID(value)
    except (ValueError, AttributeError, TypeError) as error:
        raise GrowthOnboardingValidationError(code) from error
