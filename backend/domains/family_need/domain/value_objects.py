"""Value objects for the Family Need bounded context.

The context is deliberately independent from AI/runtime and from product,
service, or order aggregates.  It records what a family has expressed and
what the family has confirmed; it never treats an AI perspective as a fact.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class NeedSignalSource(StrEnum):
    ASSESSMENT = "ASSESSMENT"
    FAMILY_CONVERSATION = "FAMILY_CONVERSATION"
    FAMILY_SEARCH = "FAMILY_SEARCH"
    SERVICE_FEEDBACK = "SERVICE_FEEDBACK"
    FAMILY_EXPRESSED = "FAMILY_EXPRESSED"
    SUPPORT_REQUEST = "SUPPORT_REQUEST"


class NeedSignalStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RETRACTED = "RETRACTED"
    EXPIRED = "EXPIRED"


class NeedStatus(StrEnum):
    CAPTURED = "CAPTURED"
    CLARIFYING = "CLARIFYING"
    CONFIRMED = "CONFIRMED"
    REJECTED = "REJECTED"
    PAUSED = "PAUSED"
    PROFILED = "PROFILED"
    SOLUTIONING = "SOLUTIONING"
    FULFILLING = "FULFILLING"
    FULFILLED = "FULFILLED"
    CLOSED = "CLOSED"


class NeedCategory(StrEnum):
    EDUCATION = "EDUCATION"
    FAMILY_RELATIONSHIP = "FAMILY_RELATIONSHIP"
    GROWTH_COMPANIONSHIP = "GROWTH_COMPANIONSHIP"
    LIFE_SUPPORT = "LIFE_SUPPORT"
    SERVICE_SUPPORT = "SERVICE_SUPPORT"
    OTHER = "OTHER"


class NeedUrgency(StrEnum):
    NOW = "NOW"
    SOON = "SOON"
    WHEN_READY = "WHEN_READY"


class NeedComplexity(StrEnum):
    SIMPLE = "SIMPLE"
    COMPOUND = "COMPOUND"
    CROSS_DOMAIN = "CROSS_DOMAIN"


class RiskLevel(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    HUMAN_REVIEW_REQUIRED = "HUMAN_REVIEW_REQUIRED"


class DataClass(StrEnum):
    PUBLIC = "PUBLIC"
    INTERNAL = "INTERNAL"
    FAMILY_PRIVATE = "FAMILY_PRIVATE"
    SENSITIVE_PERSONAL_DATA = "SENSITIVE_PERSONAL_DATA"
    MINOR_PERSONAL_DATA = "MINOR_PERSONAL_DATA"


class SupplyShape(StrEnum):
    PRODUCT = "PRODUCT"
    SERVICE = "SERVICE"
    SOLUTION = "SOLUTION"


class SolutionDraftStatus(StrEnum):
    DRAFT = "DRAFT"
    FAMILY_REVIEW = "FAMILY_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PAUSED = "PAUSED"
    STALE = "STALE"


class EmotionalGate(StrEnum):
    """E0-E4 gate; the first economic choice is only after E3."""

    E0_WELCOME = "E0_WELCOME"
    E1_SEEN = "E1_SEEN"
    E2_SAFE_TO_ACT = "E2_SAFE_TO_ACT"
    E3_VALUE_CONFIRMED = "E3_VALUE_CONFIRMED"
    E4_ECONOMIC_CHOICE = "E4_ECONOMIC_CHOICE"


class ResourceGapReason(StrEnum):
    NO_MATCHING_CAPABILITY = "NO_MATCHING_CAPABILITY"
    NO_CAPACITY = "NO_CAPACITY"
    CONSENT_SCOPE = "CONSENT_SCOPE"
    REGION_UNSUPPORTED = "REGION_UNSUPPORTED"
    LANGUAGE_UNSUPPORTED = "LANGUAGE_UNSUPPORTED"


class EvidenceKind(StrEnum):
    """Kinds of already-authorized evidence accepted by the need domain."""

    MEDIA_ASSET = "MEDIA_ASSET"
    VOICE_TRANSCRIPT = "VOICE_TRANSCRIPT"
    IMAGE_EVIDENCE = "IMAGE_EVIDENCE"
    TEXT_EVIDENCE = "TEXT_EVIDENCE"


class ActorType(StrEnum):
    FAMILY_MEMBER = "FAMILY_MEMBER"
    FAMILY_GUARDIAN = "FAMILY_GUARDIAN"
    OPERATOR = "OPERATOR"
    PROVIDER = "PROVIDER"
    SYSTEM = "SYSTEM"
    AI = "AI"


@dataclass(frozen=True)
class EvidenceRef:
    """Pointer to evidence owned by the media/assessment context.

    This object deliberately contains no audio, image or transcript payload.
    Transcription/OCR/model work happens outside Family Need after the caller
    has established the authorization snapshot represented here.
    """

    media_ref: str
    kind: EvidenceKind
    tenant_id: str
    family_id: str
    provenance_ref: str
    consent_version: str | None
    data_class: DataClass
    authorized: bool = True
    expires_at: datetime | None = None

    def __post_init__(self) -> None:
        for name, value in {
            "media_ref": self.media_ref,
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
            "provenance_ref": self.provenance_ref,
        }.items():
            if not value or not value.strip():
                raise ValueError(f"{name}_required")

    def is_expired(self, now: datetime | None = None) -> bool:
        if self.expires_at is None:
            return False
        expiry = self.expires_at
        candidate = now or datetime.now(UTC)
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=UTC)
        if candidate.tzinfo is None:
            candidate = candidate.replace(tzinfo=UTC)
        return expiry <= candidate


@dataclass(frozen=True)
class NeedContext:
    """Mandatory data-governance envelope carried by every aggregate."""

    tenant_id: str
    family_id: str
    purpose: str
    consent_version: str
    data_class: DataClass
    locale: str = "zh-CN"
    region: str = "CN"
    subject_person_ids: tuple[str, ...] = ()
    actor_id: str | None = None
    actor_type: ActorType = ActorType.FAMILY_MEMBER
    global_id: str | None = None
    source_system: str = "aifamily"
    environment: str = "test"
    provenance_ref: str | None = None
    correlation_id: str | None = None
    causation_id: str | None = None
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        required = {
            "tenant_id": self.tenant_id,
            "family_id": self.family_id,
            "purpose": self.purpose,
            "consent_version": self.consent_version,
        }
        for name, value in required.items():
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name}_required")
        if not re.fullmatch(r"[a-z]{2,3}(?:-[A-Z][a-z]{3})?(?:-[A-Z]{2})?", self.locale):
            raise ValueError("locale_invalid")
        if not re.fullmatch(r"[A-Z]{2,3}", self.region):
            raise ValueError("region_invalid")
        if len(set(self.subject_person_ids)) != len(self.subject_person_ids):
            raise ValueError("subject_person_ids_duplicate")
        if self.actor_type is ActorType.AI:
            raise ValueError("ai_cannot_write_family_need_fact")

    def with_actor(self, actor_id: str, actor_type: ActorType) -> NeedContext:
        return NeedContext(
            tenant_id=self.tenant_id,
            family_id=self.family_id,
            purpose=self.purpose,
            consent_version=self.consent_version,
            data_class=self.data_class,
            locale=self.locale,
            region=self.region,
            subject_person_ids=self.subject_person_ids,
            actor_id=actor_id,
            actor_type=actor_type,
            global_id=self.global_id,
            source_system=self.source_system,
            environment=self.environment,
            provenance_ref=self.provenance_ref,
            correlation_id=self.correlation_id,
            causation_id=self.causation_id,
            created_at=self.created_at,
        )

    @property
    def subject_person_id(self) -> str | None:
        """Compatibility projection for single-subject UI flows."""

        return self.subject_person_ids[0] if len(self.subject_person_ids) == 1 else None


@dataclass(frozen=True)
class NeedConstraint:
    key: str
    value: str
    source: str = "FAMILY"

    def __post_init__(self) -> None:
        if not self.key.strip() or not self.value.strip():
            raise ValueError("need_constraint_required")


@dataclass(frozen=True)
class AcceptanceCriterion:
    criterion_id: str
    description: str
    evidence_type: str = "FAMILY_CONFIRMATION"

    def __post_init__(self) -> None:
        if not self.criterion_id.strip() or not self.description.strip():
            raise ValueError("acceptance_criterion_required")


@dataclass(frozen=True)
class SolutionComponentRef:
    """Reference only; ownership remains with Product/Service domains."""

    component_id: str
    shape: SupplyShape
    version: str
    required: bool = True
    quantity: int = 1

    def __post_init__(self) -> None:
        if not self.component_id.strip() or not self.version.strip():
            raise ValueError("solution_component_reference_required")
        if self.quantity < 1:
            raise ValueError("solution_component_quantity_invalid")


@dataclass(frozen=True)
class ResourceGap:
    need_id: str
    reason: ResourceGapReason
    detail: str
    observed_at: datetime

    @classmethod
    def now(cls, need_id: str, reason: ResourceGapReason, detail: str) -> ResourceGap:
        return cls(need_id, reason, detail, datetime.now(UTC))


def gate_rank(gate: EmotionalGate) -> int:
    return tuple(EmotionalGate).index(gate)


# Concise aliases used by application adapters while keeping the canonical
# names explicit in persisted contracts.
NeedSource = NeedSignalSource
NeedRiskLevel = RiskLevel
NeedSupplyShape = SupplyShape
