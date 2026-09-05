"""SQLAlchemy mapping for the existing ``family_product_offerings`` table.

Column names follow baseline migration 0034.  UUIDs and jsonb are represented
as strings/JSON so the same mapping works with the SQLite test path.
"""

from sqlalchemy import Boolean, Column, DateTime, Integer, String
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import JSON

Base = declarative_base()


class ProductOfferingRow(Base):
    __tablename__ = "family_product_offerings"

    product_id = Column(String, primary_key=True)
    scope_type = Column(String, nullable=False, default="PLATFORM")
    tenant_id = Column(String, nullable=True)
    product_ref = Column(String, nullable=False)
    version_no = Column(Integer, nullable=False, default=1)
    title = Column(String, nullable=False)
    admission_status = Column(String, nullable=False, default="ADMITTED")
    source_ref = Column(String, nullable=False)
    price_plan_ref = Column(String, nullable=True)
    entitlement_policy_ref = Column(String, nullable=True)
    fixture_only = Column(Boolean, nullable=False, default=True)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    status = Column(String, nullable=False, default="ACTIVE")
    effective_from = Column(DateTime, nullable=False)
    effective_to = Column(DateTime, nullable=True)
    row_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=True)
    created_by = Column(String, nullable=True)
    updated_at = Column(DateTime, nullable=True)
    updated_by = Column(String, nullable=True)


class OrderIntentRow(Base):
    __tablename__ = "family_order_intents"

    order_intent_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    family_id = Column(String, nullable=False)
    actor_person_id = Column(String, nullable=False)
    intent_ref = Column(String, nullable=False)
    product_id = Column(String, nullable=False)
    source_page_id = Column(String, nullable=False)
    consent_ref = Column(String, nullable=False, default="DEV_SYNTHETIC_CONSENT")
    status = Column(String, nullable=False, default="DRAFT")
    catalog_snapshot = Column(JSON, nullable=False, default=dict)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    environment = Column(String, nullable=False, default="DEV")
    source_system = Column(String, nullable=False, default="TEST_FIXTURE")
    external_effect = Column(Boolean, nullable=False, default=False)
    correlation_id = Column(String, nullable=False, default="")
    idempotency_key = Column(String, nullable=True)
    retention_class = Column(String, nullable=False, default="COMMERCE_INTENT_TEST")
    row_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False, default="system:dev-commerce")
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String, nullable=False, default="system:dev-commerce")


class EntitlementRow(Base):
    __tablename__ = "family_entitlements"

    entitlement_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    family_id = Column(String, nullable=False)
    source_order_intent_id = Column(String, nullable=False)
    entitlement_ref = Column(String, nullable=False)
    status = Column(String, nullable=False, default="PENDING")
    environment = Column(String, nullable=False, default="DEV")
    source_system = Column(String, nullable=False, default="TEST_NOOP_ADAPTER")
    external_effect = Column(Boolean, nullable=False, default=False)
    attributes_schema_version = Column(Integer, nullable=False, default=1)
    attributes = Column(JSON, nullable=False, default=dict)
    available_at = Column(DateTime, nullable=True)
    expires_at = Column(DateTime, nullable=True)
    row_version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False, default="system:dev-commerce")
    updated_at = Column(DateTime, nullable=False)
    updated_by = Column(String, nullable=False, default="system:dev-commerce")
