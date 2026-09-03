"""Read-only activity catalogue master for UI-22/UI-23."""

from datetime import datetime

from pydantic import BaseModel, model_validator


class ActivityCatalogItem(BaseModel):
    activity_catalog_id: str
    activity_ref: str
    title: str
    activity_kind: str
    starts_at: datetime
    ends_at: datetime | None = None
    admission_status: str = "ADMITTED"
    source_ref: str
    fixture_only: bool = True
    attributes: dict = {}

    @model_validator(mode="after")
    def validate_master(self):
        if not self.fixture_only:
            raise ValueError("activity catalogue must be fixture-only in dev")
        if self.admission_status not in {"ADMITTED", "EXPIRED"}:
            raise ValueError("invalid activity admission status")
        return self

    @property
    def is_admitted(self) -> bool:
        return self.admission_status == "ADMITTED"
