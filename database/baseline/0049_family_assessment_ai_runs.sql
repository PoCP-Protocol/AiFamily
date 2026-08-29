-- 0046_family_assessment_ai_runs — UI-03 derived AI draft ledger
-- AI interpretation is a private derived draft. It is not a canonical ontology fact,
-- diagnosis, score, ranking, decision, or action.

CREATE TABLE IF NOT EXISTS family_assessment_ai_runs (
  assessment_ai_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  assessment_session_id uuid NOT NULL REFERENCES family_assessment_sessions(assessment_session_id) ON DELETE CASCADE,
  assessment_evidence_id uuid NOT NULL REFERENCES evidence_records(evidence_id),
  subsystem_ref varchar(96) NOT NULL,
  subsystem_version varchar(32) NOT NULL,
  service_depth varchar(48) NOT NULL CHECK (service_depth IN ('BASIC_SELF_CHECK','DEEP_AI_INTERPRETATION')),
  request_id varchar(128) NOT NULL,
  model_provider varchar(64) NOT NULL,
  model_generator varchar(96) NOT NULL,
  model_component_ref varchar(128) NOT NULL,
  source_refs jsonb NOT NULL,
  input_hash varchar(128) NOT NULL,
  output_hash varchar(128) NOT NULL,
  output_body jsonb NOT NULL,
  state_upper_bound varchar(64) NOT NULL DEFAULT 'DERIVED_DRAFT_PRIVATE',
  boundary_labels text[] NOT NULL DEFAULT '{}',
  schema_validation varchar(24) NOT NULL CHECK (schema_validation IN ('valid','invalid')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, family_id, assessment_session_id, service_depth),
  CHECK (subsystem_ref = 'FAMILY_ASSESSMENT_AI_SUBSYSTEM'),
  CHECK (state_upper_bound = 'DERIVED_DRAFT_PRIVATE')
);

CREATE INDEX IF NOT EXISTS idx_family_assessment_ai_runs_session
  ON family_assessment_ai_runs(assessment_session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_family_assessment_ai_runs_family
  ON family_assessment_ai_runs(tenant_id, family_id, created_at DESC);