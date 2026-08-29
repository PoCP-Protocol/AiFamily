-- FAMILY-SERVICE-COLLAB-ALLOCATION-P0-001
-- Versioned collaboration blueprint and case-level shadow allocation.
-- No money, wallet, commission, settlement, ranking, or external side effect.

CREATE TABLE IF NOT EXISTS service_collaboration_blueprints (
  blueprint_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  blueprint_ref varchar(160) NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  applicable_program_ref varchar(160) NOT NULL,
  roles jsonb NOT NULL CHECK (jsonb_typeof(roles) = 'array'),
  task_templates jsonb NOT NULL CHECK (jsonb_typeof(task_templates) = 'array'),
  assignment_rules jsonb NOT NULL CHECK (jsonb_typeof(assignment_rules) = 'object'),
  required_capability_keys jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(required_capability_keys) = 'array'),
  allocation_policy jsonb NOT NULL CHECK (jsonb_typeof(allocation_policy) = 'object'),
  release_rules jsonb NOT NULL CHECK (jsonb_typeof(release_rules) = 'object'),
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','ACTIVE','RETIRED')),
  checksum varchar(128) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (blueprint_ref, version)
);

ALTER TABLE service_cases
  ADD COLUMN IF NOT EXISTS collaboration_blueprint_ref varchar(160),
  ADD COLUMN IF NOT EXISTS collaboration_blueprint_version integer,
  ADD COLUMN IF NOT EXISTS collaboration_blueprint_snapshot jsonb,
  ADD COLUMN IF NOT EXISTS shadow_allocation_finalized_at timestamptz,
  ADD COLUMN IF NOT EXISTS shadow_allocation_policy_ref varchar(160),
  ADD COLUMN IF NOT EXISTS shadow_allocation_policy_version integer;

ALTER TABLE service_tasks
  ADD COLUMN IF NOT EXISTS role_key varchar(96),
  ADD COLUMN IF NOT EXISTS required_capability_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS task_weight numeric(12,4) NOT NULL DEFAULT 1 CHECK (task_weight > 0);

ALTER TABLE service_contribution_allocations
  ADD COLUMN IF NOT EXISTS beneficiary_ref varchar(160),
  ADD COLUMN IF NOT EXISTS beneficiary_kind varchar(32),
  ADD COLUMN IF NOT EXISTS role_key varchar(96),
  ADD COLUMN IF NOT EXISTS policy_ref varchar(160),
  ADD COLUMN IF NOT EXISTS policy_version integer,
  ADD COLUMN IF NOT EXISTS basis_type varchar(64),
  ADD COLUMN IF NOT EXISTS basis_ref varchar(160);

ALTER TABLE service_contribution_allocations
  DROP CONSTRAINT IF EXISTS service_contribution_allocations_allocation_bucket_check;
ALTER TABLE service_contribution_allocations
  ADD CONSTRAINT service_contribution_allocations_allocation_bucket_check
  CHECK (allocation_bucket IN ('PLATFORM','CONTENT_RESOURCE','STEWARD','CASE_STEWARD','DELIVERY_RESOURCE','QUALITY_RESERVE'));

CREATE UNIQUE INDEX IF NOT EXISTS uq_task_assignments_one_accepted
  ON task_assignments(task_id) WHERE status = 'ACCEPTED';
CREATE UNIQUE INDEX IF NOT EXISTS uq_case_shadow_allocation_once
  ON service_cases(case_id) WHERE shadow_allocation_finalized_at IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_case_allocation_policy_line
  ON service_contribution_allocations(case_ref, allocation_bucket, beneficiary_ref, role_key);

INSERT INTO service_collaboration_blueprints (
  blueprint_ref, version, applicable_program_ref, roles, task_templates,
  assignment_rules, required_capability_keys, allocation_policy, release_rules,
  status, checksum
) VALUES (
  'communication-21day-service-collab', 1, 'communication-21day',
  '[{"role_key":"CASE_STEWARD","resource_type":"INTERNAL_ACTOR"},{"role_key":"CONTENT_RESOURCE","resource_type":"CATALOG_RESOURCE"},{"role_key":"DELIVERY_RESOURCE","resource_type":"ADMITTED_PROVIDER"},{"role_key":"QUALITY_REVIEWER","resource_type":"INTERNAL_ACTOR"}]'::jsonb,
  '[{"task_key":"CASE_OPEN_AND_STEWARD","role_key":"CASE_STEWARD","weight":1},{"task_key":"CONTENT_ACTIVATION","role_key":"CONTENT_RESOURCE","weight":1},{"task_key":"AI_GUIDANCE_DELIVERY","role_key":"DELIVERY_RESOURCE","weight":1},{"task_key":"HUMAN_HANDOFF","role_key":"DELIVERY_RESOURCE","weight":1,"conditional":true},{"task_key":"CLOSURE_QUALITY_REVIEW","role_key":"QUALITY_REVIEWER","weight":1}]'::jsonb,
  '{"one_steward":true,"one_accepted_assignment_per_task":true,"provider_validation":"ACTIVE_ADMITTED_CAPABILITY_RELATION_GRANT","reviewer_must_differ_from_delivery":true}'::jsonb,
  '["DE_ESCALATION","COMMUNICATION_REOPENING"]'::jsonb,
  '{"total_units":100,"buckets":{"PLATFORM":20,"CONTENT_RESOURCE":15,"CASE_STEWARD":15,"DELIVERY_RESOURCE":40,"QUALITY_RESERVE":10},"basis":"SERVICE_CONTRIBUTION_AND_QUALITY","delivery_split":"WEIGHTED_VERIFIED_CONTRIBUTIONS"}'::jsonb,
  '{"quality_reserve_default":"HELD","helpful":"RELEASE","somewhat_helpful":"RELEASE","not_helpful_yet":"HELD_AND_REWORK","unanswered":"HELD"}'::jsonb,
  'ACTIVE', 'communication-21day-service-collab:v1:shadow-100'
) ON CONFLICT (blueprint_ref, version) DO NOTHING;

COMMENT ON TABLE service_collaboration_blueprints IS 'Versioned case collaboration configuration; historical cases use frozen snapshots.';
COMMENT ON COLUMN service_cases.shadow_allocation_finalized_at IS 'Case-level shadow allocation finalization marker; not money or settlement.';
COMMENT ON TABLE service_contribution_allocations IS 'Shadow contribution units only; never a payment, commission, wallet, or settlement record.';
