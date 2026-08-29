-- FAMILY-AI-PRODUCT-INTELLIGENCE-V0-1-PR-001
-- Product Intelligence Domain V0.1 (project owner Override #6, CURRENT_SPRINT.md).
-- Signal -> Insight -> Opportunity -> GrowthProblem -> GrowthHypothesis -> GrowthStrategy -> ProductConcept
-- acceptance chain, plus the remaining objects from instruction 01 (model+migration only, no
-- application-service behaviour yet). No AI Use Case Registry / model-provider wiring in this PR.

CREATE TABLE IF NOT EXISTS product_intelligence_market_signals (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL,
  raw_text text NOT NULL,
  source_ref varchar(160),
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS product_intelligence_signal_clusters (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL,
  label varchar(240) NOT NULL,
  signal_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS product_intelligence_market_trends (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL,
  description text NOT NULL,
  cluster_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS product_intelligence_customer_segments (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL,
  label varchar(240) NOT NULL,
  definition text NOT NULL
);

CREATE TABLE IF NOT EXISTS product_intelligence_evidence (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL,
  description text NOT NULL,
  evidence_ref varchar(240) NOT NULL
);

CREATE TABLE IF NOT EXISTS product_intelligence_customer_insights (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL,
  statement text NOT NULL,
  signal_id varchar(160) REFERENCES product_intelligence_market_signals(id),
  segment_id varchar(160),
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  generated_by varchar(160),
  model_ref varchar(160),
  prompt_use_case_version varchar(160),
  confidence double precision
);

CREATE TABLE IF NOT EXISTS product_intelligence_unmet_needs (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL,
  statement text NOT NULL,
  insight_id varchar(160) REFERENCES product_intelligence_customer_insights(id),
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS product_intelligence_opportunities (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL,
  insight_id varchar(160) NOT NULL REFERENCES product_intelligence_customer_insights(id),
  statement text NOT NULL,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  generated_by varchar(160),
  model_ref varchar(160),
  prompt_use_case_version varchar(160),
  confidence double precision
);

CREATE TABLE IF NOT EXISTS product_intelligence_growth_problems (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL,
  symptom text NOT NULL,
  opportunity_id varchar(160) REFERENCES product_intelligence_opportunities(id),
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS product_intelligence_growth_hypotheses (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','UNDER_REVIEW','VALIDATED','REJECTED','RETIRED')),
  problem_id varchar(160) NOT NULL REFERENCES product_intelligence_growth_problems(id),
  statement text NOT NULL,
  supporting_evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  counter_evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  assumptions jsonb NOT NULL DEFAULT '[]'::jsonb,
  expected_observations jsonb NOT NULL DEFAULT '[]'::jsonb,
  falsification_conditions jsonb NOT NULL DEFAULT '[]'::jsonb,
  generated_by varchar(160),
  model_ref varchar(160),
  prompt_use_case_version varchar(160),
  confidence double precision,
  validated_by varchar(160),
  validated_at timestamptz,
  validation_reason text
);

CREATE TABLE IF NOT EXISTS product_intelligence_contradiction_models (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','UNDER_REVIEW','APPROVED','RETIRED')),
  primary_factor_a varchar(240) NOT NULL,
  primary_factor_b varchar(240) NOT NULL,
  relationship varchar(240) NOT NULL,
  description text,
  supporting_hypothesis_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  generated_by varchar(160),
  model_ref varchar(160),
  prompt_use_case_version varchar(160),
  confidence double precision
);

CREATE TABLE IF NOT EXISTS product_intelligence_growth_strategies (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','UNDER_REVIEW','APPROVED','RETIRED')),
  problem_id varchar(160) NOT NULL REFERENCES product_intelligence_growth_problems(id),
  hypothesis_ids jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_array_length(hypothesis_ids) > 0),
  contradiction_id varchar(160) REFERENCES product_intelligence_contradiction_models(id),
  statement text NOT NULL,
  applicable_segment_ref varchar(160),
  exclusion_conditions jsonb NOT NULL DEFAULT '[]'::jsonb,
  generated_by varchar(160),
  model_ref varchar(160),
  prompt_use_case_version varchar(160),
  confidence double precision
);

CREATE TABLE IF NOT EXISTS product_intelligence_zone_assessments (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL,
  subject_ref varchar(160) NOT NULL,
  subject_type varchar(64) NOT NULL,
  customer_scarcity double precision NOT NULL,
  replaceability double precision NOT NULL,
  data_advantage double precision NOT NULL,
  network_effect double precision NOT NULL,
  learning_effect double precision NOT NULL,
  switching_cost double precision NOT NULL,
  commodity_score double precision NOT NULL,
  advantage_score double precision NOT NULL,
  unique_score double precision NOT NULL,
  zone varchar(24) NOT NULL CHECK (zone IN ('COMMODITY','ADVANTAGE','UNIQUE')),
  assessment_reason text,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  assessor varchar(160) NOT NULL
);

CREATE TABLE IF NOT EXISTS product_intelligence_product_concepts (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','UNDER_REVIEW','APPROVED','RETIRED')),
  strategy_id varchar(160) NOT NULL REFERENCES product_intelligence_growth_strategies(id),
  title varchar(240) NOT NULL,
  description text,
  generated_by varchar(160),
  model_ref varchar(160),
  prompt_use_case_version varchar(160),
  confidence double precision
);

CREATE TABLE IF NOT EXISTS product_intelligence_product_components (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL,
  component_type varchar(64) NOT NULL,
  title varchar(240) NOT NULL
);

CREATE TABLE IF NOT EXISTS product_intelligence_product_patterns (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL,
  title varchar(240) NOT NULL,
  component_ids jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS product_intelligence_product_definitions (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL,
  concept_id varchar(160) NOT NULL REFERENCES product_intelligence_product_concepts(id),
  pattern_id varchar(160) REFERENCES product_intelligence_product_patterns(id),
  component_ids jsonb NOT NULL DEFAULT '[]'::jsonb
);

CREATE TABLE IF NOT EXISTS product_intelligence_service_blueprint_versions (
  id varchar(160) PRIMARY KEY,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL,
  updated_at timestamptz NOT NULL,
  created_by varchar(160) NOT NULL,
  tenant_scope varchar(160) NOT NULL,
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','ACTIVE','RETIRED')),
  product_definition_id varchar(160) NOT NULL REFERENCES product_intelligence_product_definitions(id),
  checksum varchar(160)
);
