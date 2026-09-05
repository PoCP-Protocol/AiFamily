"""Family-private DEV/TEST commerce facts.

These facts record interest only.  They are not payment orders and never
trigger fulfilment, notifications, or an external provider.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

CommerceEnvironment = Literal["DEV", "TEST"]
OrderIntentStatus = Literal["DRAFT", "SUBMITTED", "CANCELLED", "EXPIRED"]
EntitlementStatus = Literal["PENDING", "AVAILABLE", "REVOKED", "EXPIRED"]


class OrderIntent(BaseModel):
    order_intent_id: str
    tenant_id: str
    family_id: str
    actor_person_id: str
    intent_ref: str
    product_id: str
    product_ref: str
    product_version: int = Field(gt=0)
    source_page_id: Literal["UI-14", "UI-17"]
    status: OrderIntentStatus = "DRAFT"
    consent_ref: str = "DEV_SYNTHETIC_CONSENT"
    catalog_snapshot: dict[str, object] = Field(default_factory=dict)
    attributes_schema_version: int = 1
    environment: CommerceEnvironment = "DEV"
    source_system: str = "TEST_FIXTURE"
    external_effect: Literal[False] = False
    idempotency_key: str
    correlation_id: str = ""
    retention_class: str = "COMMERCE_INTENT_TEST"
    row_version: int = 1
    created_at: datetime
    created_by: str = "system:dev-commerce"
    updated_at: datetime
    updated_by: str = "system:dev-commerce"
    attributes: dict[str, object] = Field(default_factory=dict)


class Entitlement(BaseModel):
    entitlement_id: str
    tenant_id: str
    family_id: str
    source_order_intent_id: str
    entitlement_ref: str
    status: EntitlementStatus = "PENDING"
    environment: CommerceEnvironment = "DEV"
    source_system: str = "TEST_NOOP_ADAPTER"
    external_effect: Literal[False] = False
    attributes: dict[str, object] = Field(default_factory=dict)
    attributes_schema_version: int = 1
    available_at: datetime | None = None
    expires_at: datetime | None = None
    row_version: int = 1
    created_at: datetime
    created_by: str = "system:dev-commerce"
    updated_at: datetime
    updated_by: str = "system:dev-commerce"

    @model_validator(mode="after")
    def available_requires_timestamp(self) -> "Entitlement":
        if self.status == "AVAILABLE" and self.available_at is None:
            raise ValueError("available_entitlement_requires_available_at")
        return self
