"""Consent value objects.

`ConsentPurpose` mirrors the purpose taxonomy referenced by the source
repository's `specs/ontology/consent.schema.yaml` (see
governance/MIGRATION_MANIFEST.yaml capability `platform_consent`). Only the
taxonomy shape is reused; no code from that file is copied.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


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
    """Lifecycle status of a single consent grant."""

    GRANTED = "granted"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"


@dataclass(frozen=True, slots=True)
class ConsentGrant:
    """A single consent decision.

    `subject_person_id` is the person the data is about; `guardian_person_id`
    is who granted it on the subject's behalf (may equal the subject for a
    self-consenting adult — that equality is a domain-level decision, not
    enforced here). This is a pure value object: constructing one does not
    write anything anywhere.
    """

    consent_id: str
    subject_person_id: str
    guardian_person_id: str
    purpose: ConsentPurpose
    status: ConsentStatus
    granted_at: datetime

    def __post_init__(self) -> None:
        if not self.consent_id:
            raise ValueError("ConsentGrant.consent_id must not be empty")
        if not self.subject_person_id:
            raise ValueError("ConsentGrant.subject_person_id must not be empty")
        if not self.guardian_person_id:
            raise ValueError("ConsentGrant.guardian_person_id must not be empty")

    @property
    def is_active(self) -> bool:
        return self.status is ConsentStatus.GRANTED
