"""Commerce catalogue entities.

Only the supply master is represented here.  Order intents and entitlements
remain family facts and are deliberately outside this read-only slice.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

ProductScope = Literal["PLATFORM", "TENANT"]
ProductStatus = Literal["DRAFT", "ACTIVE", "SUSPENDED", "RETIRED"]
AdmissionStatus = Literal["ADMITTED", "EXPIRED", "SUSPENDED"]


class ProductOffering(BaseModel):
    product_id: str
    scope_type: ProductScope = "PLATFORM"
    tenant_id: str | None = None
    product_ref: str
    version_no: int = Field(default=1, gt=0)
    title: str
    admission_status: AdmissionStatus = "ADMITTED"
    source_ref: str
    price_plan_ref: str | None = None
    entitlement_policy_ref: str | None = None
    fixture_only: bool = True
    attributes_schema_version: int = Field(default=1, gt=0)
    attributes: dict[str, object] = Field(default_factory=dict)
    status: ProductStatus = "ACTIVE"
    effective_from: datetime
    effective_to: datetime | None = None

    @model_validator(mode="after")
    def validate_scope_and_fixture(self) -> ProductOffering:
        if self.scope_type == "PLATFORM" and self.tenant_id is not None:
            raise ValueError("platform_product_must_not_have_tenant")
        if self.scope_type == "TENANT" and self.tenant_id is None:
            raise ValueError("tenant_product_requires_tenant")
        if not self.fixture_only:
            raise ValueError("product_must_be_fixture_only")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("product_effective_to_must_follow_from")
        return self

    @property
    def is_bookable(self) -> bool:
        return self.status == "ACTIVE" and self.admission_status == "ADMITTED"
