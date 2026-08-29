-- Complete 90-day Journey execution: phase-scoped daily actions remain action records,
-- never diagnoses, outcomes, scores, rankings, or external effects.

ALTER TABLE growth_actions
  ADD COLUMN IF NOT EXISTS journey_plan_id uuid NULL REFERENCES family_journey_plans(plan_id),
  ADD COLUMN IF NOT EXISTS journey_phase varchar(24) NULL;

ALTER TABLE growth_actions
  DROP CONSTRAINT IF EXISTS growth_actions_wave2_day_check;

ALTER TABLE growth_actions
  ADD CONSTRAINT growth_actions_wave2_day_check CHECK (day_index IS NULL OR day_index BETWEEN 1 AND 90);

ALTER TABLE growth_actions
  DROP CONSTRAINT IF EXISTS growth_actions_journey_phase_check;

ALTER TABLE growth_actions
  ADD CONSTRAINT growth_actions_journey_phase_check CHECK (
    journey_phase IS NULL OR journey_phase IN ('SEE', 'PARENT_FIRST', 'CO_CREATE', 'STABILIZE')
  );

ALTER TABLE growth_actions
  DROP CONSTRAINT IF EXISTS growth_actions_journey_plan_phase_check;

ALTER TABLE growth_actions
  ADD CONSTRAINT growth_actions_journey_plan_phase_check CHECK (
    (journey_plan_id IS NULL AND journey_phase IS NULL)
    OR (journey_plan_id IS NOT NULL AND journey_phase IS NOT NULL)
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_growth_actions_journey_plan_day
  ON growth_actions(journey_plan_id, day_index)
  WHERE journey_plan_id IS NOT NULL AND day_index IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_growth_actions_journey_plan_today
  ON growth_actions(family_id, journey_plan_id, journey_phase, due_date, status)
  WHERE journey_plan_id IS NOT NULL;
