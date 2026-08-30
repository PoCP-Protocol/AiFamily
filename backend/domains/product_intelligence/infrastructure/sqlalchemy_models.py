"""SQLAlchemy ORM models for the Product Intelligence domain.

No shared `packages/persistence` Base exists yet repo-wide (Batch 1 has not
bootstrapped one as of this PR) — this module defines its own
`declarative_base()` as a temporary measure, to be merged into a shared
Base once `packages/persistence` exists. JSON columns (not Postgres ARRAY)
are used for list fields so the same models work against both real
Postgres and the SQLite engine used by this PR's tests (Override #6 item 4
— no real-PG integration test in this PR yet).
"""

from __future__ import annotations

from sqlalchemy import Column, Float, Integer, String, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.types import JSON
from sqlalchemy.types import DateTime as _DateTime

Base = declarative_base()

# PR-001R item 7 (real-Postgres integration test): entities always produce
# timezone-aware UTC datetimes (`domain/entities.py`, PR-001R item 6), and
# the migration's columns are `timestamptz`. Passing the bare `DateTime`
# class to `Column()` defaults to `timezone=False`, which SQLite silently
# accepts (it has no real datetime type) but real Postgres rejects with
# "can't subtract offset-naive and offset-aware datetimes" on the very
# first insert. Every `Column(DateTime, ...)` below uses this
# pre-constructed `timezone=True` instance instead, so SQLAlchemy maps it
# to Postgres `TIMESTAMP WITH TIME ZONE` (matching the migration) while
# remaining a no-op for SQLite.
DateTime = _DateTime(timezone=True)


class MarketSignalRow(Base):
    __tablename__ = "product_intelligence_market_signals"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    raw_text = Column(Text, nullable=False)
    source_ref = Column(String, nullable=True)
    evidence_refs = Column(JSON, nullable=False, default=list)


class SignalClusterRow(Base):
    __tablename__ = "product_intelligence_signal_clusters"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    label = Column(String, nullable=False)
    signal_ids = Column(JSON, nullable=False, default=list)
    evidence_refs = Column(JSON, nullable=False, default=list)


class MarketTrendRow(Base):
    __tablename__ = "product_intelligence_market_trends"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    cluster_ids = Column(JSON, nullable=False, default=list)
    evidence_refs = Column(JSON, nullable=False, default=list)


class CustomerSegmentRow(Base):
    __tablename__ = "product_intelligence_customer_segments"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    label = Column(String, nullable=False)
    definition = Column(Text, nullable=False)


class EvidenceRow(Base):
    __tablename__ = "product_intelligence_evidence"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    description = Column(Text, nullable=False)
    evidence_ref = Column(String, nullable=False)


class CompetitorEvidenceRow(Base):
    """Tenant-scoped DRAFT evidence card; never a competitor ranking."""

    __tablename__ = "product_intelligence_competitor_evidence"
    id = Column(String, primary_key=True)
    version = Column(String, nullable=False, default="1.0.0")
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False, default="DRAFT")
    evidence_refs = Column(JSON, nullable=False, default=list)
    assumptions = Column(JSON, nullable=False, default=list)
    unknowns = Column(JSON, nullable=False, default=list)
    next_validation = Column(Text, nullable=False)
    expires_at = Column(DateTime, nullable=False)
    provenance_ref = Column(String, nullable=True)
    competitor_ref = Column(String, nullable=False)
    claim = Column(Text, nullable=False)
    source_refs = Column(JSON, nullable=False, default=list)
    evidence_status = Column(String, nullable=False)
    demand_ref = Column(String, nullable=True)
    market_insight_ref = Column(String, nullable=True)
    source_type = Column(String, nullable=False)


class CustomerInsightRow(Base):
    __tablename__ = "product_intelligence_customer_insights"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    statement = Column(Text, nullable=False)
    signal_id = Column(String, nullable=True)
    segment_id = Column(String, nullable=True)
    evidence_refs = Column(JSON, nullable=False, default=list)
    generated_by = Column(String, nullable=True)
    model_ref = Column(String, nullable=True)
    prompt_use_case_version = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)


class UnmetNeedRow(Base):
    __tablename__ = "product_intelligence_unmet_needs"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    statement = Column(Text, nullable=False)
    insight_id = Column(String, nullable=True)
    evidence_refs = Column(JSON, nullable=False, default=list)


class OpportunityRow(Base):
    __tablename__ = "product_intelligence_opportunities"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    insight_id = Column(String, nullable=False)
    statement = Column(Text, nullable=False)
    evidence_refs = Column(JSON, nullable=False, default=list)
    generated_by = Column(String, nullable=True)
    model_ref = Column(String, nullable=True)
    prompt_use_case_version = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)


class GrowthProblemRow(Base):
    __tablename__ = "product_intelligence_growth_problems"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    symptom = Column(Text, nullable=False)
    opportunity_id = Column(String, nullable=True)
    evidence_refs = Column(JSON, nullable=False, default=list)


class GrowthHypothesisRow(Base):
    __tablename__ = "product_intelligence_growth_hypotheses"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    problem_id = Column(String, nullable=False)
    statement = Column(Text, nullable=False)
    supporting_evidence_refs = Column(JSON, nullable=False, default=list)
    counter_evidence_refs = Column(JSON, nullable=False, default=list)
    assumptions = Column(JSON, nullable=False, default=list)
    expected_observations = Column(JSON, nullable=False, default=list)
    falsification_conditions = Column(JSON, nullable=False, default=list)
    generated_by = Column(String, nullable=True)
    model_ref = Column(String, nullable=True)
    prompt_use_case_version = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    validated_by = Column(String, nullable=True)
    validated_at = Column(DateTime, nullable=True)
    validation_reason = Column(Text, nullable=True)


class ContradictionModelRow(Base):
    __tablename__ = "product_intelligence_contradiction_models"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    problem_id = Column(String, nullable=False)
    primary_factor_a = Column(String, nullable=False)
    primary_factor_b = Column(String, nullable=False)
    relationship = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    supporting_hypothesis_ids = Column(JSON, nullable=False, default=list)
    evidence_refs = Column(JSON, nullable=False, default=list)
    primary_rank = Column(Integer, nullable=True)
    primary_marked_by = Column(String, nullable=True)
    primary_marked_at = Column(DateTime, nullable=True)
    reviewed_by = Column(String, nullable=True)
    reviewed_at = Column(DateTime, nullable=True)
    review_reason = Column(Text, nullable=True)
    generated_by = Column(String, nullable=True)
    model_ref = Column(String, nullable=True)
    prompt_use_case_version = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    # NOTE (PR-003 V1): this table's real Postgres migration
    # (`migrations/0058_product_intelligence_domain.sql`) predates
    # problem_id/primary_rank/reviewed_by/reviewed_at/review_reason — same
    # "ORM ahead of the pre-Alembic SQL snapshot" situation already recorded
    # in `migrations/README.md` for GrowthHypothesisRow's validated_by/at/
    # reason columns. Deferred to the same T-05 Alembic-revision follow-up
    # rather than adding another ad-hoc raw-SQL file on top of a migration
    # story that is already mid-cleanup.


class ValueArchitectureRow(Base):
    __tablename__ = "product_intelligence_value_architectures"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    problem_id = Column(String, nullable=False)
    emotional_current_state = Column(Text, nullable=False)
    emotional_desired_state = Column(Text, nullable=False)
    action_next_best_action = Column(Text, nullable=False)
    growth_outcomes = Column(JSON, nullable=False, default=list)
    economic_outcomes = Column(JSON, nullable=False, default=list)
    rationale = Column(Text, nullable=False)
    evidence_refs = Column(JSON, nullable=False, default=list)
    generated_by = Column(String, nullable=True)
    model_ref = Column(String, nullable=True)
    prompt_use_case_version = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)
    # NOTE (PR-003 V1): new table, no real Postgres migration yet — same
    # deferral as ContradictionModelRow above. Proven via the SQLite-backed
    # `sqlalchemy_repo` fixture in this PR (the same path the original
    # acceptance chain used before its own Postgres migration existed).


class GrowthStrategyRow(Base):
    __tablename__ = "product_intelligence_growth_strategies"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    problem_id = Column(String, nullable=False)
    hypothesis_ids = Column(JSON, nullable=False, default=list)
    contradiction_id = Column(String, nullable=True)
    value_architecture_id = Column(String, nullable=True)
    statement = Column(Text, nullable=False)
    applicable_segment_ref = Column(String, nullable=True)
    exclusion_conditions = Column(JSON, nullable=False, default=list)
    generated_by = Column(String, nullable=True)
    model_ref = Column(String, nullable=True)
    prompt_use_case_version = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)


class ProductConceptRow(Base):
    __tablename__ = "product_intelligence_product_concepts"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    strategy_id = Column(String, nullable=False)
    title = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    generated_by = Column(String, nullable=True)
    model_ref = Column(String, nullable=True)
    prompt_use_case_version = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)


class ProductComponentRow(Base):
    __tablename__ = "product_intelligence_product_components"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    component_type = Column(String, nullable=False)
    title = Column(String, nullable=False)


class ProductPatternRow(Base):
    __tablename__ = "product_intelligence_product_patterns"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    title = Column(String, nullable=False)
    component_ids = Column(JSON, nullable=False, default=list)


class ProductDefinitionRow(Base):
    __tablename__ = "product_intelligence_product_definitions"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    concept_id = Column(String, nullable=False)
    pattern_id = Column(String, nullable=True)
    component_ids = Column(JSON, nullable=False, default=list)
    # Education-product design fields were added after the provisional 0058
    # SQL snapshot.  They remain nullable/defaulted for backward-compatible
    # reads of legacy definitions; the domain model enforces the stronger
    # education_spec invariants when present.
    product_kind = Column(String, nullable=False, default="CUSTOM")
    duration_days = Column(Integer, nullable=True)
    zone = Column(String, nullable=False, default="HOMOGENEOUS")
    primary_contradiction = Column(Text, nullable=True)
    demand_ref = Column(String, nullable=True)
    market_insight_refs = Column(JSON, nullable=False, default=list)
    education_spec = Column(JSON, nullable=True)
    generated_by = Column(String, nullable=True)
    model_ref = Column(String, nullable=True)
    prompt_use_case_version = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)


class ServiceBlueprintVersionRow(Base):
    __tablename__ = "product_intelligence_service_blueprint_versions"
    id = Column(String, primary_key=True)
    version = Column(Integer, nullable=False, default=1)
    created_at = Column(DateTime, nullable=False)
    updated_at = Column(DateTime, nullable=False)
    created_by = Column(String, nullable=False)
    tenant_scope = Column(String, nullable=False)
    status = Column(String, nullable=False)
    product_definition_id = Column(String, nullable=False)
    checksum = Column(String, nullable=True)
