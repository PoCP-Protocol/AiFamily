-- 0041_ui03_growth_hypothesis_confirmation — UI-03 evidence-bound interpretation
-- A hypothesis is explanatory, never a canonical child/family fact or diagnosis.

CREATE TABLE IF NOT EXISTS family_need_types (
  need_type_ref varchar(96) NOT NULL,
  version_no integer NOT NULL CHECK (version_no > 0),
  source_focus_ref varchar(96) NOT NULL,
  title varchar(160) NOT NULL,
  description text NOT NULL,
  required_capability_keys text[] NOT NULL,
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','ACTIVE','RETIRED')),
  admission_status varchar(24) NOT NULL CHECK (admission_status IN ('ADMITTED','HOLD','REJECTED')),
  boundary jsonb NOT NULL,
  effective_from timestamptz NOT NULL DEFAULT now(),
  effective_to timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (need_type_ref, version_no),
  UNIQUE (source_focus_ref, version_no)
);

INSERT INTO family_need_types(need_type_ref,version_no,source_focus_ref,title,description,required_capability_keys,status,admission_status,boundary) VALUES
('PARENT_CHILD_COMMUNICATION_CONFLICT',1,'PARENT_CHILD_COMMUNICATION','亲子沟通支持','帮助家庭尝试更可持续的倾听、表达和冲突修复方式',ARRAY['CAP_PARENT_COACHING'],'ACTIVE','ADMITTED','{"not_a_family_label":true,"not_a_diagnosis":true}'::jsonb),
('LEARNING_HABITS_SUPPORT',1,'LEARNING_HABITS','学习习惯支持','帮助家庭减少催促并建立可开始、可回看的学习节奏',ARRAY['CAP_HABIT_COACHING'],'ACTIVE','ADMITTED','{"not_a_family_label":true,"not_a_diagnosis":true}'::jsonb),
('EMOTION_REGULATION_SUPPORT',1,'EMOTION_REGULATION','情绪调节支持','帮助家庭先识别和照顾情绪，再共同处理问题',ARRAY['CAP_EMOTIONAL_SUPPORT'],'ACTIVE','ADMITTED','{"not_a_family_label":true,"not_a_diagnosis":true}'::jsonb),
('DEVICE_BOUNDARY_SUPPORT',1,'DEVICE_USE_CONTEXT','数字使用边界支持','帮助家庭共同形成清楚且可执行的数字使用约定',ARRAY['CAP_FAMILY_BOUNDARY_COACHING'],'ACTIVE','ADMITTED','{"not_a_family_label":true,"not_a_diagnosis":true}'::jsonb),
('SELF_REGULATION_SUPPORT',1,'SELF_REGULATION','自我管理支持','帮助孩子逐步参与目标、选择与行动回看',ARRAY['CAP_SELF_MANAGEMENT_COACHING'],'ACTIVE','ADMITTED','{"not_a_family_label":true,"not_a_diagnosis":true}'::jsonb)
ON CONFLICT (need_type_ref,version_no) DO NOTHING;

ALTER TABLE growth_intents
  ADD COLUMN IF NOT EXISTS source_type varchar(48) NOT NULL DEFAULT 'NEED_SIGNAL',
  ADD COLUMN IF NOT EXISTS source_ref varchar(256) NULL,
  ADD COLUMN IF NOT EXISTS evidence_refs uuid[] NOT NULL DEFAULT '{}',
  ADD COLUMN IF NOT EXISTS boundary varchar(96) NOT NULL DEFAULT 'HUMAN_CONFIRMED_INTENT_NOT_OUTCOME';
CREATE UNIQUE INDEX IF NOT EXISTS uq_growth_intent_assessment_hypothesis
  ON growth_intents(family_id,source_type,source_ref)
  WHERE source_type='ASSESSMENT_HYPOTHESIS' AND source_ref IS NOT NULL;

CREATE TABLE IF NOT EXISTS family_growth_hypothesis_decisions (
  hypothesis_decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  assessment_session_id uuid NOT NULL REFERENCES family_assessment_sessions(assessment_session_id),
  hypothesis_ref varchar(256) NOT NULL,
  decision_type varchar(24) NOT NULL CHECK (decision_type IN ('CONFIRM','DISMISS')),
  actor_person_id uuid NOT NULL REFERENCES persons(person_id),
  intent_id uuid NULL REFERENCES growth_intents(intent_id),
  idempotency_key varchar(128) NOT NULL,
  request_hash varchar(128) NOT NULL,
  response_body jsonb NOT NULL,
  correlation_id varchar(128) NOT NULL,
  decided_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id,family_id,decision_type,idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_growth_hypothesis_decisions_source
  ON family_growth_hypothesis_decisions(family_id,hypothesis_ref,decided_at DESC);
