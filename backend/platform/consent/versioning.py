"""Canonical, provider-neutral consent snapshot versioning."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256


@dataclass(frozen=True, slots=True)
class ConsentVersionEntry:
    consent_id: str
    status: str
    granted_at: datetime
    guardian_person_id: str
    subject_age: int
    policy_version: str

    def __post_init__(self) -> None:
        if not all(
            isinstance(value, str) and value.strip()
            for value in (
                self.consent_id,
                self.status,
                self.guardian_person_id,
                self.policy_version,
            )
        ):
            raise ValueError("consent version entry is incomplete")
        if not isinstance(self.granted_at, datetime):
            raise ValueError("consent granted_at must be a datetime")
        if self.subject_age < 0 or self.subject_age > 150:
            raise ValueError("consent subject age is invalid")

    def signature(self) -> str:
        return "|".join(
            (
                self.consent_id,
                self.status.lower(),
                self.granted_at.isoformat(),
                self.guardian_person_id,
                str(self.subject_age),
                self.policy_version,
            )
        )


def canonical_consent_version(entries: Iterable[ConsentVersionEntry]) -> str:
    signatures = sorted(entry.signature() for entry in entries)
    material = "\n".join(signatures).encode("utf-8")
    return f"db:{sha256(material).hexdigest()[:24]}"


__all__ = ["ConsentVersionEntry", "canonical_consent_version"]
