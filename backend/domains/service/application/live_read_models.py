"""Read models for the first Xiaojudeng Live slice.

H-LIVE-01 is deliberately a read-only boundary.  The public model contains
only the information an authorised adult needs to decide whether a session is
relevant; room URLs, media capabilities, child facts, rankings, purchases and
AI conclusions do not have a field here and therefore cannot leak through this
route accidentally.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LiveSessionStatus = Literal["SCHEDULED", "LIVE", "WITHDRAWN", "EXPIRED"]
LiveReviewStatus = Literal["APPROVED", "WITHDRAWN", "REJECTED"]
FamilyVisibility = Literal["FAMILY_SCOPED"]


class LiveSessionProjection(BaseModel):
    """Canonical projection supplied by the owning live provider.

    ``tenant_id`` and ``family_id`` are integrity fields used for server-side
    scope verification.  They are intentionally not part of the public view.
    """

    model_config = ConfigDict(extra="forbid")

    tenant_id: str
    family_id: str
    session_ref: str
    title: str = Field(min_length=1)
    presenter_name: str = Field(min_length=1)
    audience_scope: tuple[str, ...]
    starts_at: datetime
    ends_at: datetime
    review_ref: str = Field(min_length=1)
    review_version: str = Field(min_length=1)
    review_status: LiveReviewStatus
    status: LiveSessionStatus
    family_visibility: FamilyVisibility
    as_of: datetime
    source: str = Field(min_length=1)
    fixture_only: bool

    @model_validator(mode="after")
    def validate_contract(self) -> LiveSessionProjection:
        if self.ends_at <= self.starts_at:
            raise ValueError("live_session_end_must_follow_start")
        source = self.source.upper()
        if self.fixture_only and source != "TEST_FIXTURE":
            raise ValueError("fixture_source_must_be_explicit")
        if not self.fixture_only and source == "TEST_FIXTURE":
            raise ValueError("test_fixture_must_be_explicitly_marked")
        if source == "BASELINE_CONTENT":
            raise ValueError("baseline_content_is_not_a_live_source")
        return self


class LiveSessionDetailView(BaseModel):
    """Stable public response for an approved, current Family-scoped session."""

    model_config = ConfigDict(extra="forbid")

    session_ref: str
    title: str
    presenter_name: str
    audience_scope: tuple[str, ...]
    starts_at: datetime
    ends_at: datetime
    review_ref: str
    review_version: str
    status: LiveSessionStatus
    family_visibility: FamilyVisibility
    as_of: datetime
    source: str
    fixture_only: bool

    @classmethod
    def from_projection(cls, projection: LiveSessionProjection) -> LiveSessionDetailView:
        return cls(
            session_ref=projection.session_ref,
            title=projection.title,
            presenter_name=projection.presenter_name,
            audience_scope=projection.audience_scope,
            starts_at=projection.starts_at,
            ends_at=projection.ends_at,
            review_ref=projection.review_ref,
            review_version=projection.review_version,
            status=projection.status,
            family_visibility=projection.family_visibility,
            as_of=projection.as_of,
            source=projection.source,
            fixture_only=projection.fixture_only,
        )
