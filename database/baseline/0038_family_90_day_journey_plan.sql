-- 0035_family_90_day_journey_plan
-- A 90-day Family Growth Journey is a family-confirmed cadence aggregate.
-- It does not create an outcome, diagnosis, payment, notification or external effect.

CREATE TABLE IF NOT EXISTS family_journey_plans (
  plan_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  onboarding_id uuid NOT NULL REFERENCES growth_journeys(journey_id),
  priority_id uuid NOT NULL REFERENCES growth_priorities(priority_id),
  title varchar(160) NOT NULL,
  status varchar(24) NOT NULL DEFAULT 'DRAFT'
    CHECK (status IN ('DRAFT', 'ACTIVE', 'PAUSED', 'COMPLETED', 'ARCHIVED')),
  current_phase varchar(24) NOT NULL DEFAULT 'SEE'
    CHECK (current_phase IN ('SEE', 'PARENT_FIRST', 'CO_CREATE', 'STABILIZE')),
  current_day smallint NOT NULL DEFAULT 1 CHECK (current_day BETWEEN 1 AND 90),
  total_days smallint NOT NULL DEFAULT 90 CHECK (total_days = 90),
  confirmed_by_actor_id varchar(128) NULL,
  confirmed_at timestamptz NULL,
  paused_at timestamptz NULL,
  completed_at timestamptz NULL,
  version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
  policy_version varchar(48) NOT NULL DEFAULT 'JOURNEY_90_DAY_V1',
  boundary varchar(96) NOT NULL DEFAULT 'PLAN_IS_FAMILY_CONFIRMED_CADENCE_NOT_DIAGNOSIS_OR_OUTCOME'
    CHECK (boundary = 'PLAN_IS_FAMILY_CONFIRMED_CADENCE_NOT_DIAGNOSIS_OR_OUTCOME'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK ((status = 'DRAFT' AND confirmed_at IS NULL AND confirmed_by_actor_id IS NULL)
      OR (status <> 'DRAFT' AND confirmed_at IS NOT NULL AND confirmed_by_actor_id IS NOT NULL))
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_family_journey_plan_active_or_draft
  ON family_journey_plans(family_id, onboarding_id)
  WHERE status IN ('DRAFT', 'ACTIVE', 'PAUSED');

CREATE INDEX IF NOT EXISTS idx_family_journey_plans_family_status
  ON family_journey_plans(family_id, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS family_journey_plan_phases (
  plan_phase_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id uuid NOT NULL REFERENCES family_journey_plans(plan_id) ON DELETE CASCADE,
  phase varchar(24) NOT NULL CHECK (phase IN ('SEE', 'PARENT_FIRST', 'CO_CREATE', 'STABILIZE')),
  start_day smallint NOT NULL CHECK (start_day BETWEEN 1 AND 90),
  end_day smallint NOT NULL CHECK (end_day BETWEEN 1 AND 90 AND end_day >= start_day),
  status varchar(24) NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING', 'ACTIVE', 'REVIEW_DUE', 'COMPLETED', 'BLOCKED')),
  focus_dimensions jsonb NOT NULL DEFAULT '[]'::jsonb,
  review_due_day smallint NOT NULL CHECK (review_due_day BETWEEN 1 AND 90),
  boundary varchar(96) NOT NULL DEFAULT 'PHASE_TRANSITION_REQUIRES_REVIEW_AND_FAMILY_DECISION'
    CHECK (boundary = 'PHASE_TRANSITION_REQUIRES_REVIEW_AND_FAMILY_DECISION'),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (review_due_day = end_day)
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_family_journey_plan_phase
  ON family_journey_plan_phases(plan_id, phase);

CREATE UNIQUE INDEX IF NOT EXISTS uq_family_journey_plan_phase_range
  ON family_journey_plan_phases(plan_id, start_day, end_day);
