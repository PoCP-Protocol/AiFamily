-- 0053_service_task_allocation_dev
-- DEV 履约协作：一客一案、一案一管家、一任务一责任人。
-- 仅记录任务履约与分配依据；不触发支付，不把成长结果当作收入依据。

DO $$ BEGIN
  CREATE TYPE service_task_status AS ENUM ('PENDING','OFFERED','ACCEPTED','IN_PROGRESS','DELIVERED','VERIFIED','CLOSED','CANCELLED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE task_assignment_status AS ENUM ('OFFERED','ACCEPTED','DECLINED','REVOKED','COMPLETED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE task_quality_state AS ENUM ('PENDING','PASSED','REWORK_REQUIRED','REJECTED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS service_tasks (
  task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_ref uuid NOT NULL REFERENCES service_cases(case_id),
  blueprint_ref varchar(128) NOT NULL,
  task_key varchar(128) NOT NULL,
  title varchar(240) NOT NULL,
  description text NOT NULL,
  status service_task_status NOT NULL DEFAULT 'PENDING',
  responsible_ref varchar(128) NULL,
  due_at timestamptz NULL,
  deliverable jsonb NULL CHECK (deliverable IS NULL OR jsonb_typeof(deliverable) = 'object'),
  verified_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (case_ref, task_key)
);
CREATE INDEX IF NOT EXISTS idx_service_tasks_case_status ON service_tasks(case_ref, status, due_at);

CREATE TABLE IF NOT EXISTS task_assignments (
  assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id uuid NOT NULL REFERENCES service_tasks(task_id),
  assignee_ref varchar(128) NOT NULL,
  assignee_kind varchar(24) NOT NULL CHECK (assignee_kind IN ('STEWARD','AI','COACH','EXPERT','CONTENT')),
  status task_assignment_status NOT NULL DEFAULT 'OFFERED',
  accepted_at timestamptz NULL,
  declined_at timestamptz NULL,
  revoked_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (task_id, assignee_ref, created_at)
);
CREATE INDEX IF NOT EXISTS idx_task_assignments_active ON task_assignments(task_id, status)
  WHERE status IN ('OFFERED','ACCEPTED');

CREATE TABLE IF NOT EXISTS task_quality_reviews (
  quality_review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  task_id uuid NOT NULL REFERENCES service_tasks(task_id),
  reviewer_ref varchar(128) NOT NULL,
  quality_state task_quality_state NOT NULL DEFAULT 'PENDING',
  review_note varchar(1000) NULL,
  reviewed_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_task_quality_reviews_task ON task_quality_reviews(task_id, created_at DESC);

CREATE TABLE IF NOT EXISTS service_contribution_allocations (
  allocation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contribution_ref uuid NOT NULL REFERENCES service_contributions(contribution_id),
  case_ref uuid NOT NULL REFERENCES service_cases(case_id),
  task_ref uuid NOT NULL REFERENCES service_tasks(task_id),
  allocation_bucket varchar(32) NOT NULL CHECK (allocation_bucket IN ('PLATFORM','CONTENT_RESOURCE','STEWARD','DELIVERY_RESOURCE','QUALITY_RESERVE')),
  units numeric(12,2) NOT NULL CHECK (units >= 0),
  release_state varchar(16) NOT NULL DEFAULT 'HELD' CHECK (release_state IN ('HELD','RELEASED')),
  reason varchar(240) NOT NULL,
  released_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (contribution_ref, allocation_bucket)
);
CREATE INDEX IF NOT EXISTS idx_contribution_allocations_case ON service_contribution_allocations(case_ref, release_state);

COMMENT ON TABLE service_tasks IS 'DEV task fulfillment unit; only VERIFIED task can produce contribution allocation basis.';
COMMENT ON TABLE task_assignments IS 'One current responsible assignee per task; no customer ownership or ranking.';
COMMENT ON TABLE service_contribution_allocations IS 'Allocation basis only; no payment or settlement side effect.';