-- 0040_ui02_versioned_family_assessment — VS-01 / UI-02 commercial assessment facts
-- Assessment means a family support-needs confirmation. It is not a score,
-- diagnosis, clinical instrument, or child profile.

CREATE TABLE IF NOT EXISTS family_assessment_tools (
  tool_ref varchar(96) NOT NULL,
  version_no integer NOT NULL CHECK (version_no > 0),
  title varchar(160) NOT NULL,
  purpose varchar(240) NOT NULL,
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','ACTIVE','RETIRED')),
  admission_status varchar(24) NOT NULL CHECK (admission_status IN ('ADMITTED','HOLD','REJECTED')),
  evidence_level varchar(8) NOT NULL DEFAULT 'E1',
  schema_ref varchar(160) NOT NULL,
  item_schema jsonb NOT NULL,
  boundary jsonb NOT NULL,
  effective_from timestamptz NOT NULL DEFAULT now(),
  effective_to timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tool_ref, version_no),
  CONSTRAINT family_assessment_tool_window CHECK (effective_to IS NULL OR effective_to > effective_from)
);

CREATE TABLE IF NOT EXISTS family_assessment_sessions (
  assessment_session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_person_id uuid NOT NULL REFERENCES persons(person_id),
  tool_ref varchar(96) NOT NULL,
  tool_version integer NOT NULL,
  status varchar(24) NOT NULL DEFAULT 'IN_PROGRESS' CHECK (status IN ('IN_PROGRESS','SUBMITTED','EXITED')),
  started_by_person_id uuid NOT NULL REFERENCES persons(person_id),
  started_at timestamptz NOT NULL DEFAULT now(),
  submitted_at timestamptz NULL,
  exited_at timestamptz NULL,
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  FOREIGN KEY (tool_ref, tool_version) REFERENCES family_assessment_tools(tool_ref, version_no)
);
CREATE INDEX IF NOT EXISTS idx_family_assessment_sessions_scope
  ON family_assessment_sessions(tenant_id, family_id, status, updated_at DESC);

-- Append-only answer revisions. Exactly one current revision may exist while a
-- session is editable; submitted sessions are protected again in the service.
CREATE TABLE IF NOT EXISTS family_assessment_responses (
  assessment_response_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  assessment_session_id uuid NOT NULL REFERENCES family_assessment_sessions(assessment_session_id) ON DELETE CASCADE,
  item_ref varchar(96) NOT NULL,
  response_type varchar(32) NOT NULL CHECK (response_type IN ('SINGLE_CHOICE','TEXT','BOOLEAN')),
  response_value jsonb NOT NULL,
  author_person_id uuid NOT NULL REFERENCES persons(person_id),
  captured_at timestamptz NOT NULL DEFAULT now(),
  visibility varchar(32) NOT NULL DEFAULT 'FAMILY_PRIVATE',
  revision integer NOT NULL CHECK (revision > 0),
  is_current boolean NOT NULL DEFAULT true,
  superseded_at timestamptz NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_assessment_current_response
  ON family_assessment_responses(assessment_session_id, item_ref) WHERE is_current;
CREATE INDEX IF NOT EXISTS idx_family_assessment_response_history
  ON family_assessment_responses(assessment_session_id, item_ref, revision DESC);

CREATE TABLE IF NOT EXISTS family_assessment_operations (
  assessment_operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  assessment_session_id uuid NULL REFERENCES family_assessment_sessions(assessment_session_id),
  action_name varchar(64) NOT NULL CHECK (action_name IN ('START_ASSESSMENT','SAVE_ASSESSMENT_RESPONSE','SUBMIT_ASSESSMENT','EXIT_ASSESSMENT')),
  actor_person_id uuid NOT NULL REFERENCES persons(person_id),
  idempotency_key varchar(128) NOT NULL,
  request_hash varchar(128) NOT NULL,
  response_body jsonb NOT NULL,
  correlation_id varchar(128) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, family_id, action_name, idempotency_key)
);

INSERT INTO family_assessment_tools(
  tool_ref, version_no, title, purpose, status, admission_status,
  evidence_level, schema_ref, item_schema, boundary, effective_from
) VALUES (
  'FAMILY_SUPPORT_NEEDS', 1, '家庭支持需要与服务偏好确认',
  '帮助家庭整理此刻最希望获得支持的场景与偏好', 'ACTIVE', 'ADMITTED',
  'E1', 'family://assessment/FAMILY_SUPPORT_NEEDS/v1',
  '{
    "items": [
      {"item_ref":"FOCUS","response_type":"SINGLE_CHOICE","required":true,"options":["LEARNING_HABITS","EMOTION_REGULATION","PARENT_CHILD_COMMUNICATION","DEVICE_USE_CONTEXT","SELF_REGULATION"]},
      {"item_ref":"FAMILY_STRUCTURE","response_type":"SINGLE_CHOICE","required":false,"options":["TWO_PARENT","SINGLE_PARENT","BLENDED","PREFER_NOT_TO_SAY"]},
      {"item_ref":"CHILD_GENDER","response_type":"SINGLE_CHOICE","required":false,"options":["BOY","GIRL","SELF_DESCRIBED","PREFER_NOT_TO_SAY"]}
    ]
  }'::jsonb,
  '{"truth_class":"FAMILY_PERSPECTIVE","not_a_score":true,"not_a_diagnosis":true,"no_eligibility_effect":true,"withdrawable":true,"training_use":false}'::jsonb,
  now()
) ON CONFLICT (tool_ref, version_no) DO NOTHING;
