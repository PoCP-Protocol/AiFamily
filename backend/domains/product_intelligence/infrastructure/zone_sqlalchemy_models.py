"""SQLAlchemy ORM models for the Product Zone (Three-Zone Strategy Engine)
tables added by `database/migrations/0059_product_zone_engine_v0.sql`.

Reuses the shared `Base`/`DateTime` (timezone-aware) from
`sqlalchemy_models.py` rather than declaring a second `declarative_base()`
— a second Base would make `Base.metadata.create_all` in `tests/conftest.py`
miss these tables unless every test file remembered to import both, and
would be a second source of truth for "is this the same table registry".

See `0059_product_zone_engine_v0.sql` for the ADR-Governance §3 rationale
on why `dimension_assessments` is one `JSON` column (a `list[dict]`, i.e.
`DimensionAssessment.model_dump()` results) rather than a child table.
"""
from __future__ import annotations

from sqlalchemy import CheckConstraint, Column, Float, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.types import JSON

from .sqlalchemy_models import Base, DateTime


class ZonePolicyVersionRow(Base):
    __tablename__ = "product_intelligence_zone_policy_versions"
    id = Column(String, primary_key=True)
    policy_id = Column(String, nullable=False)
    version = Column(Integer, nullable=False)
    dimension_definitions = Column(JSON, nullable=False)
    weights = Column(JSON, nullable=False)
    thresholds = Column(JSON, nullable=False)
    classification_rules = Column(Text, nullable=False)
    review_policy = Column(JSON, nullable=False)
    effective_from = Column(DateTime, nullable=False)
    status = Column(String, nullable=False)
    checksum = Column(String, nullable=False)
    scoring_algorithm_version = Column(
        String, nullable=False, server_default="ZONE_SCORING_V0"
    )
    """Closure fix (chief-architect review, mirrors
    `domain/zone_entities.py::ZonePolicyVersion.scoring_algorithm_version`,
    added by Agent B after this table's original 0059 shape). `server_default`
    covers any pre-existing row from before this column existed (see the
    `0060` migration's `ALTER TABLE ... ADD COLUMN IF NOT EXISTS ... DEFAULT
    'ZONE_SCORING_V0'`); new rows going through `save_zone_policy_version`
    always supply the entity's real value explicitly (the domain field has
    its own non-server default of the same literal), so the server default
    is a backfill safety net, not the normal write path."""

    __table_args__ = (
        UniqueConstraint("policy_id", "version", name="uq_zone_policy_versions_policy_id_version"),
        CheckConstraint("status IN ('DRAFT', 'ACTIVE', 'RETIRED')", name="ck_zone_policy_versions_status"),
    )


class ProductZoneAssessmentRow(Base):
    """Maps `domain/zone_entities.py::ProductZoneAssessment` (the
    ADR-accurate type). Distinct table from the legacy
    `sqlalchemy_models.ProductZoneAssessmentRow` (table name
    `product_intelligence_zone_assessments`, mapping the pre-ADR placeholder
    `domain/entities.py::ProductZoneAssessment`) — see this migration's
    header comment for why the two tables/models coexist without collision.
    """

    __tablename__ = "product_intelligence_zone_assessments_v0"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    subject_type = Column(String, nullable=False)
    subject_ref = Column(String, ForeignKey("product_intelligence_product_concepts.id"), nullable=False)
    zone_policy_version_id = Column(String, nullable=False)
    dimension_assessments = Column(JSON, nullable=False)
    differentiation_index = Column(Float, nullable=False)
    defensibility_index = Column(Float, nullable=False)
    commodity_score = Column(Float, nullable=False)
    advantage_score = Column(Float, nullable=False)
    unique_score = Column(Float, nullable=False)
    recommended_zone = Column(String, nullable=False)
    approved_zone = Column(String, nullable=True)
    override_reason = Column(Text, nullable=True)
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_reason = Column(Text, nullable=True)
    assessment_origin = Column(String, nullable=False)

    __table_args__ = (
        CheckConstraint("subject_type = 'PRODUCT_CONCEPT'", name="ck_zone_assessments_v0_subject_type"),
        CheckConstraint(
            "recommended_zone IN ('COMMODITY', 'ADVANTAGE', 'UNIQUE')",
            name="ck_zone_assessments_v0_recommended_zone",
        ),
        CheckConstraint(
            "approved_zone IS NULL OR approved_zone IN ('COMMODITY', 'ADVANTAGE', 'UNIQUE')",
            name="ck_zone_assessments_v0_approved_zone",
        ),
        CheckConstraint(
            "assessment_origin IN ('HUMAN', 'RULE', 'AI_PROPOSAL')",
            name="ck_zone_assessments_v0_assessment_origin",
        ),
        CheckConstraint(
            "status IN ('DRAFT', 'SCORED', 'UNDER_REVIEW', 'APPROVED', 'REJECTED', 'RETIRED')",
            name="ck_zone_assessments_v0_status",
        ),
        Index("ix_product_intelligence_zone_assessments_v0_tenant_scope", "tenant_scope"),
        Index("ix_product_intelligence_zone_assessments_v0_subject_ref", "subject_ref"),
    )
