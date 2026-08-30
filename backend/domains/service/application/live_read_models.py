"""Read-side shapes for the H-LIVE-01 approved-session detail.

The internal candidate carries admission and scope data so the application
query can fail closed before constructing the public response.  The public
model deliberately has no room URL, playback token, child profile, ranking,
purchase CTA, AI output, or mutation fields.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

PUBLIC_LIVE_SESSION_FIELDS: tuple[str, ...] = (
    "session_ref",
    "title",
    "host_display_name",
    "audience_scope",
    "starts_at",
    "ends_at",
    "approval_ref",
    "approval_version",
    "status",
    "family_visibility",
    "as_of",
    "source",
    "fixture_only",
)


def _require_aware(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("live session timestamps must include a timezone")
    return value


class LiveSessionCandidate(BaseModel):
    """Provider-side record, including fields that must never be exposed."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: str = Field(min_length=1)
    family_id: str = Field(min_length=1)
    session_ref: str = Field(min_length=1)
    title: str = Field(min_length=1)
    host_display_name: str = Field(min_length=1)
    audience_scope: str = Field(min_length=1)
    starts_at: datetime
    ends_at: datetime
    approval_ref: str = Field(min_length=1)
    approval_version: str = Field(min_length=1)
    status: str = Field(min_length=1)
    family_visibility: str = Field(min_length=1)
    approved: bool
    source: str = Field(min_length=1)
    fixture_only: bool

    @field_validator("starts_at", "ends_at")
    @classmethod
    def timestamps_are_aware(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @field_validator("audience_scope")
    @classmethod
    def scope_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("audience_scope must not be blank")
        return value


class ApprovedLiveSessionDetail(BaseModel):
    """The stable, read-only H-LIVE-01 wire contract."""

    model_config = ConfigDict(extra="forbid")

    session_ref: str = Field(min_length=1)
    title: str = Field(min_length=1)
    host_display_name: str = Field(min_length=1)
    audience_scope: str = Field(min_length=1)
    starts_at: datetime
    ends_at: datetime
    approval_ref: str = Field(min_length=1)
    approval_version: str = Field(min_length=1)
    status: Literal["SCHEDULED", "LIVE"]
    family_visibility: Literal["FAMILY"]
    as_of: datetime
    source: str = Field(min_length=1)
    fixture_only: bool

    @field_validator("starts_at", "ends_at", "as_of")
    @classmethod
    def timestamps_are_aware(cls, value: datetime) -> datetime:
        return _require_aware(value)

    @field_validator("audience_scope")
    @classmethod
    def scope_is_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("audience_scope must not be blank")
        return value
