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
from sqlalchemy.types import DateTime as _DateTime
from sqlalchemy.types import JSON

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
    primary_factor_a = Column(String, nullable=False)
    primary_factor_b = Column(String, nullable=False)
    relationship = Column(String, nullable=False)
    description = Column(Text, nullable=True)
    supporting_hypothesis_ids = Column(JSON, nullable=False, default=list)
    evidence_refs = Column(JSON, nullable=False, default=list)
    generated_by = Column(String, nullable=True)
    model_ref = Column(String, nullable=True)
    prompt_use_case_version = Column(String, nullable=True)
    confidence = Column(Float, nullable=True)


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
