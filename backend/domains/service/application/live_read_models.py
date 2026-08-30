"""H-LIVE-01 read shapes.

The candidate is an adapter-facing shape.  The public detail is intentionally
smaller: it exposes no booking, entry, playback, media, child identity, or
guardian list fields.  It carries source and fixture markers so synthetic data
cannot silently look like production data.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LiveSessionStatus = Literal["SCHEDULED", "LIVE", "ENDED"]
AudienceScope = Literal["FAMILY_GUARDIANS"]
LiveSourceSystem = Literal["CANONICAL_LIVE", "TEST_FIXTURE"]
LiveEnvironment = Literal["DEV", "TEST", "PRODUCTION"]


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name}_must_be_timezone_aware")


class LiveSessionCandidate(BaseModel):
    """Untrusted adapter result that must pass all read gates."""

    model_config = ConfigDict(extra="forbid")

    session_ref: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    family_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    starts_at: datetime
    ends_at: datetime
    status: LiveSessionStatus
    audience_scope: AudienceScope
    guardian_person_ids: tuple[str, ...] = Field(min_length=1)
    approved: bool
    effective_from: datetime
    effective_to: datetime | None = None
    source_system: LiveSourceSystem
    environment: LiveEnvironment
    fixture_only: bool
    external_effect: bool = False

    @model_validator(mode="after")
    def validate_shape_and_source(self) -> LiveSessionCandidate:
        for name in ("starts_at", "ends_at", "effective_from"):
            _require_aware(getattr(self, name), name)
        if self.effective_to is not None:
            _require_aware(self.effective_to, "effective_to")
            if self.effective_to <= self.effective_from:
                raise ValueError("live_session_effective_window_invalid")
        if self.ends_at <= self.starts_at:
            raise ValueError("live_session_window_invalid")
        if self.external_effect:
            raise ValueError("live_session_external_effect_not_allowed")
        if self.source_system == "TEST_FIXTURE":
            if self.environment not in ("DEV", "TEST") or not self.fixture_only:
                raise ValueError("live_session_fixture_boundary_invalid")
        elif self.fixture_only:
            raise ValueError("live_session_canonical_source_cannot_be_fixture")
        return self

    def is_unexpired_at(self, now: datetime) -> bool:
        _require_aware(now, "now")
        return self.effective_from <= now and (self.effective_to is None or now < self.effective_to)


class LiveSessionDetail(BaseModel):
    """The complete H-LIVE-01 public read shape, and nothing more."""

    model_config = ConfigDict(extra="forbid")

    schema_version: Literal["h-live-01.v1"] = "h-live-01.v1"
    session_ref: str
    tenant_id: str
    family_id: str
    title: str
    starts_at: datetime
    ends_at: datetime
    status: LiveSessionStatus
    audience_scope: AudienceScope
    approved: Literal[True] = True
    source_system: LiveSourceSystem
    environment: LiveEnvironment
    fixture_only: bool
    external_effect: Literal[False] = False


PUBLIC_LIVE_SESSION_FIELDS: tuple[str, ...] = (
    "session_ref",
    "tenant_id",
    "family_id",
    "title",
    "starts_at",
    "ends_at",
    "status",
    "audience_scope",
    "approved",
    "source_system",
    "environment",
    "fixture_only",
    "external_effect",
)


def public_detail(candidate: LiveSessionCandidate) -> LiveSessionDetail:
    """Project only the approved read fields; never leak audience internals."""

    return LiveSessionDetail(
        session_ref=candidate.session_ref,
        tenant_id=candidate.tenant_id,
        family_id=candidate.family_id,
        title=candidate.title,
        starts_at=candidate.starts_at,
        ends_at=candidate.ends_at,
        status=candidate.status,
        audience_scope=candidate.audience_scope,
        source_system=candidate.source_system,
        environment=candidate.environment,
        fixture_only=candidate.fixture_only,
    )


__all__ = [
    "AudienceScope",
    "LiveSessionCandidate",
    "LiveSessionDetail",
    "LiveSessionStatus",
    "PUBLIC_LIVE_SESSION_FIELDS",
    "public_detail",
]
