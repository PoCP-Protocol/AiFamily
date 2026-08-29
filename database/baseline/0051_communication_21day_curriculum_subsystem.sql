-- G1B_21DAY_CURRICULUM_AI_SUBSYSTEM_INTERNAL
-- Persist only reviewed draft and parent process state; runtime owns schedule.
CREATE TABLE IF NOT EXISTS family_curriculum_drafts (
  draft_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NULL REFERENCES tenants(tenant_id),
  family_id uuid NULL REFERENCES families(family_id),
  scope_type varchar(24) NOT NULL DEFAULT 'PLATFORM'
    CHECK (scope_type IN ('PLATFORM','TENANT','FAMILY')),
  program_ref varchar(96) NOT NULL DEFAULT 'communication-21day',
  program_version varchar(32) NOT NULL DEFAULT '1.0.0',
  status varchar(32) NOT NULL DEFAULT 'SYNTHETIC_RULE_BASED_DRAFT'
    CHECK (status IN ('SYNTHETIC_RULE_BASED_DRAFT','SUBMITTED','APPROVED','REJECTED')),
  source_boundary varchar(96) NOT NULL DEFAULT 'E1_PRODUCT_STRUCTURE_PLUS_PUBLIC_DESIGN_RESEARCH',
  model_gateway_status varchar(32) NOT NULL DEFAULT 'NOOP_NOT_INVOKED'
    CHECK (model_gateway_status = 'NOOP_NOT_INVOKED'),
  human_review varchar(48) NOT NULL DEFAULT 'REQUIRED_BEFORE_PUBLISH_OR_ASSIGN',
  course_boundary varchar(96) NOT NULL DEFAULT 'NOT_OFFICIAL_SYLLABUS_NOT_OUTCOME_NOT_DIAGNOSIS',
  draft_body jsonb NOT NULL,
  source_lineage jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_by_actor_id varchar(128) NOT NULL,
  reviewed_by_actor_id varchar(128) NULL,
  review_note varchar(1000) NULL,
  reviewed_at timestamptz NULL,
  released_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
ALTER TABLE family_curriculum_drafts
  ADD COLUMN IF NOT EXISTS family_id uuid NULL REFERENCES families(family_id),
  ADD COLUMN IF NOT EXISTS scope_type varchar(24) NOT NULL DEFAULT 'PLATFORM';
ALTER TABLE family_curriculum_drafts
  DROP CONSTRAINT IF EXISTS family_curriculum_drafts_scope_type_check;
ALTER TABLE family_curriculum_drafts
  ADD CONSTRAINT family_curriculum_drafts_scope_type_check
  CHECK (scope_type IN ('PLATFORM','TENANT','FAMILY'));
CREATE INDEX IF NOT EXISTS idx_family_curriculum_drafts_scope
  ON family_curriculum_drafts(scope_type, tenant_id, family_id);
CREATE INDEX IF NOT EXISTS idx_family_curriculum_drafts_status
  ON family_curriculum_drafts(program_ref, status, created_at DESC);

CREATE TABLE IF NOT EXISTS family_curriculum_review_operations (
  operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  draft_id uuid NOT NULL REFERENCES family_curriculum_drafts(draft_id),
  action_name varchar(64) NOT NULL CHECK (action_name IN ('REVIEW_CURRICULUM_DRAFT','RELEASE_CURRICULUM_DRAFT')),
  actor_id varchar(128) NOT NULL,
  decision varchar(16) NOT NULL CHECK (decision IN ('APPROVED','REJECTED')),
  review_note varchar(1000) NULL,
  idempotency_key varchar(128) NOT NULL,
  request_hash varchar(128) NOT NULL,
  response_body jsonb NOT NULL,
  correlation_id varchar(128) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (draft_id, action_name, idempotency_key)
);

CREATE TABLE IF NOT EXISTS family_curriculum_operations (
  operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  operation_ref varchar(128) NOT NULL,
  action_name varchar(64) NOT NULL CHECK (action_name IN ('ENROLL_GROWTH_CAMP_21','CHECK_IN_GROWTH_CAMP_21_DAY','RELEASE_CURRICULUM_DRAFT')),
  actor_id varchar(128) NOT NULL,
  idempotency_key varchar(128) NOT NULL,
  request_hash varchar(128) NOT NULL,
  response_body jsonb NOT NULL,
  correlation_id varchar(128) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (operation_ref, action_name, idempotency_key)
);
ALTER TABLE family_curriculum_operations
  DROP CONSTRAINT IF EXISTS family_curriculum_operations_action_name_check;
ALTER TABLE family_curriculum_operations
  ADD CONSTRAINT family_curriculum_operations_action_name_check
  CHECK (action_name IN ('ENROLL_GROWTH_CAMP_21','CHECK_IN_GROWTH_CAMP_21_DAY','RELEASE_CURRICULUM_DRAFT'));

-- Align persisted catalog with @family/program-runtime while preserving legacy fixtures.
INSERT INTO family_growth_camp_programs
  (program_ref, version_no, title, purpose, status, admission_status, evidence_level, boundary)
SELECT 'communication-21day', 1, title, purpose, status, admission_status, evidence_level, boundary
  FROM family_growth_camp_programs
 WHERE program_ref = 'PARENT_GROWTH_21' AND version_no = 1
ON CONFLICT (program_ref, version_no) DO NOTHING;
INSERT INTO family_growth_camp_days
  (program_ref, program_version, day_no, stage, title, intent, action_text,
   suggested_words, observation_prompt, estimated_minutes)
SELECT 'communication-21day', program_version, day_no, stage, title, intent, action_text,
       suggested_words, observation_prompt, estimated_minutes
  FROM family_growth_camp_days
 WHERE program_ref = 'PARENT_GROWTH_21' AND program_version = 1
ON CONFLICT (program_ref, program_version, day_no) DO NOTHING;