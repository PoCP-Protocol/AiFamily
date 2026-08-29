-- 0047_family_growth_hypothesis_runtime — persisted UI-03 Growth Hypothesis runtime
-- Growth hypotheses are human-reviewable support hypotheses. They are not child facts,
-- family labels, diagnoses, scores, rankings, or accepted actions.

ALTER TABLE family_assessment_sessions
  DROP CONSTRAINT IF EXISTS family_assessment_sessions_status_check;

ALTER TABLE family_assessment_sessions
  ADD CONSTRAINT family_assessment_sessions_status_check
  CHECK (status IN ('DRAFT','IN_PROGRESS','SUBMITTED','ANALYZING','READY','ACKNOWLEDGED','ANALYSIS_FAILED','EXITED'));

ALTER TABLE family_assessment_operations
  DROP CONSTRAINT IF EXISTS family_assessment_operations_action_name_check;

ALTER TABLE family_assessment_operations
  ADD CONSTRAINT family_assessment_operations_action_name_check
  CHECK (action_name IN ('START_ASSESSMENT','SAVE_ASSESSMENT_RESPONSE','SUBMIT_ASSESSMENT','GENERATE_GROWTH_HYPOTHESIS','EXIT_ASSESSMENT'));

CREATE TABLE IF NOT EXISTS family_growth_hypotheses (
  growth_hypothesis_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  hypothesis_ref varchar(256) NOT NULL,
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_person_id uuid NOT NULL REFERENCES persons(person_id),
  assessment_session_id uuid NOT NULL REFERENCES family_assessment_sessions(assessment_session_id) ON DELETE CASCADE,
  statement text NOT NULL,
  explanation text NOT NULL,
  confidence varchar(24) NOT NULL DEFAULT 'low' CHECK (confidence IN ('low','medium','high')),
  source varchar(64) NOT NULL DEFAULT 'ASSESSMENT_AI_SUBSYSTEM',
  evidence_refs uuid[] NOT NULL DEFAULT '{}',
  limitations text[] NOT NULL DEFAULT '{}',
  model_run_ref uuid NULL REFERENCES family_assessment_ai_runs(assessment_ai_run_id),
  model_component_ref varchar(128) NULL,
  model_provider varchar(64) NOT NULL,
  model_name varchar(128) NOT NULL,
  skill_ref varchar(128) NOT NULL,
  skill_version varchar(32) NOT NULL,
  output_schema_version varchar(64) NOT NULL,
  output_hash varchar(128) NOT NULL,
  fact_boundary varchar(96) NOT NULL DEFAULT 'HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS'
    CHECK (fact_boundary='HYPOTHESIS_NOT_FACT_OR_DIAGNOSIS'),
  status varchar(24) NOT NULL DEFAULT 'PROPOSED'
    CHECK (status IN ('PROPOSED','ACKNOWLEDGED','DISMISSED','SUPERSEDED')),
  hypothesis_body jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, family_id, assessment_session_id, skill_ref, skill_version, output_schema_version),
  UNIQUE (tenant_id, family_id, hypothesis_ref)
);

CREATE INDEX IF NOT EXISTS idx_family_growth_hypotheses_session
  ON family_growth_hypotheses(tenant_id, family_id, assessment_session_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_family_growth_hypotheses_subject
  ON family_growth_hypotheses(tenant_id, family_id, subject_person_id, status, updated_at DESC);