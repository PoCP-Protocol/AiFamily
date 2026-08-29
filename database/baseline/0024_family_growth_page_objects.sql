-- 0023_family_growth_page_objects — Family 34 页对象链（DEV/TEST 可运行，生产需独立晋级）
-- 目的：为 UI-01/UI-04/UI-05/UI-06/UI-09/UI-24/UI-29/UI-31/UI-33/UI-34 提供正式对象与只读/受控状态。
-- 约束：family_id 必须存在；source/environment 可追溯；不保存诊断、评分、永久标签或真实外部效果。

DO $$ BEGIN
  CREATE TYPE family_page_task_status AS ENUM ('OPEN','COMPLETED','PAUSED','CANCELLED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE family_support_report_status AS ENUM ('DRAFT','SHOWN','WITHDRAWN');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE family_service_record_status AS ENUM ('RECORDED','CANCELLED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS family_profile_snapshots (
  profile_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  source varchar(48) NOT NULL CHECK (source IN ('TEST_FIXTURE','FAMILY_EXPRESSION','SERVICE_PROJECTION')),
  visibility varchar(32) NOT NULL DEFAULT 'FAMILY_PRIVATE' CHECK (visibility = 'FAMILY_PRIVATE'),
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  profile_payload jsonb NOT NULL,
  created_by_person_id uuid NULL REFERENCES persons(person_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  withdrawn_at timestamptz NULL
);
CREATE INDEX IF NOT EXISTS idx_family_profile_snapshots_family ON family_profile_snapshots(family_id, created_at DESC);

CREATE TABLE IF NOT EXISTS family_support_report_snapshots (
  report_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  intent_ref uuid NULL REFERENCES growth_intents(intent_id),
  source varchar(48) NOT NULL CHECK (source IN ('FAMILY_EXPRESSION','SERVICE_RECORD','TEST_FIXTURE')),
  status family_support_report_status NOT NULL DEFAULT 'SHOWN',
  visibility varchar(32) NOT NULL DEFAULT 'FAMILY_PRIVATE' CHECK (visibility = 'FAMILY_PRIVATE'),
  evidence_refs text[] NOT NULL DEFAULT '{}',
  report_payload jsonb NOT NULL,
  created_by_person_id uuid NULL REFERENCES persons(person_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  withdrawn_at timestamptz NULL
);
CREATE INDEX IF NOT EXISTS idx_family_support_reports_family ON family_support_report_snapshots(family_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_family_support_reports_intent ON family_support_report_snapshots(intent_ref, created_at DESC);

CREATE TABLE IF NOT EXISTS family_page_task_items (
  task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_person_id uuid NULL REFERENCES persons(person_id),
  plan_ref uuid NULL REFERENCES orchestration_plans(plan_id),
  source varchar(48) NOT NULL CHECK (source IN ('TEST_FIXTURE','FAMILY_PLAN','SERVICE_CASE')),
  title varchar(160) NOT NULL,
  task_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  status family_page_task_status NOT NULL DEFAULT 'OPEN',
  idempotency_key varchar(160) NULL,
  created_by_person_id uuid NULL REFERENCES persons(person_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz NULL,
  cancelled_at timestamptz NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_page_task_idempotency ON family_page_task_items(family_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_family_page_tasks_family_status ON family_page_task_items(family_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS family_service_records (
  service_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  case_ref uuid NULL REFERENCES service_cases(case_id),
  operation_ref uuid NULL REFERENCES test_experience_operations(operation_id),
  record_kind varchar(64) NOT NULL,
  source varchar(48) NOT NULL CHECK (source IN ('TEST_FIXTURE','SERVICE_CASE','TEST_EXPERIENCE_OPERATION')),
  status family_service_record_status NOT NULL DEFAULT 'RECORDED',
  visibility varchar(32) NOT NULL DEFAULT 'FAMILY_PRIVATE' CHECK (visibility = 'FAMILY_PRIVATE'),
  record_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  external_effect boolean NOT NULL DEFAULT false CHECK (external_effect = false),
  created_by_person_id uuid NULL REFERENCES persons(person_id),
  occurred_at timestamptz NOT NULL DEFAULT now(),
  cancelled_at timestamptz NULL
);
CREATE INDEX IF NOT EXISTS idx_family_service_records_family ON family_service_records(family_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_family_service_records_operation ON family_service_records(operation_ref);
