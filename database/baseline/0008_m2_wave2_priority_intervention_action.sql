-- 0008_m2_wave2_priority_intervention_action — M2 Wave 2 Decide & Act.
-- Additive only: priority is a human-confirmed practice focus; action completion is not outcome.

ALTER TABLE growth_priorities
  ADD COLUMN IF NOT EXISTS onboarding_id uuid NULL REFERENCES growth_journeys(journey_id),
  ADD COLUMN IF NOT EXISTS status varchar(24) NOT NULL DEFAULT 'ACTIVE',
  ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
  ADD COLUMN IF NOT EXISTS boundary varchar(80) NOT NULL DEFAULT 'PRIORITY_IS_HUMAN_CONFIRMED_PRACTICE_FOCUS',
  ADD COLUMN IF NOT EXISTS reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS policy_version varchar(48) NULL,
  ADD COLUMN IF NOT EXISTS superseded_at timestamptz NULL,
  ADD COLUMN IF NOT EXISTS previous_priority_id uuid NULL REFERENCES growth_priorities(priority_id);

UPDATE growth_priorities
SET status = 'SUPERSEDED', superseded_at = COALESCE(superseded_at, now())
WHERE rank <> 1;

ALTER TABLE growth_priorities
  ALTER COLUMN rank SET DEFAULT 1;

ALTER TABLE growth_priorities
  DROP CONSTRAINT IF EXISTS growth_priorities_rank_check;

ALTER TABLE growth_priorities
  ADD CONSTRAINT growth_priorities_rank_check CHECK (rank = 1 OR status = 'SUPERSEDED');

ALTER TABLE growth_priorities
  DROP CONSTRAINT IF EXISTS growth_priorities_active_rank_check;

ALTER TABLE growth_priorities
  ADD CONSTRAINT growth_priorities_active_rank_check CHECK (status <> 'ACTIVE' OR rank = 1);

ALTER TABLE growth_priorities
  DROP CONSTRAINT IF EXISTS growth_priorities_status_check;

ALTER TABLE growth_priorities
  ADD CONSTRAINT growth_priorities_status_check CHECK (status IN ('ACTIVE','SUPERSEDED'));

ALTER TABLE growth_priorities
  DROP CONSTRAINT IF EXISTS growth_priorities_dimension_check;

ALTER TABLE growth_priorities
  ADD CONSTRAINT growth_priorities_dimension_check CHECK (dimension_id IN ('P03','R03','R04','R05'));

ALTER TABLE growth_priorities
  DROP CONSTRAINT IF EXISTS growth_priorities_boundary_check;

ALTER TABLE growth_priorities
  ADD CONSTRAINT growth_priorities_boundary_check CHECK (boundary = 'PRIORITY_IS_HUMAN_CONFIRMED_PRACTICE_FOCUS');

CREATE UNIQUE INDEX IF NOT EXISTS uq_growth_priorities_one_active_primary
ON growth_priorities(family_id, onboarding_id)
WHERE status = 'ACTIVE';

CREATE INDEX IF NOT EXISTS idx_growth_priorities_onboarding
ON growth_priorities(family_id, onboarding_id, status, created_at DESC);

CREATE TABLE IF NOT EXISTS intervention_episodes (
  episode_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  onboarding_id uuid NOT NULL REFERENCES growth_journeys(journey_id),
  priority_id uuid NOT NULL REFERENCES growth_priorities(priority_id),
  intervention_id varchar(64) NOT NULL REFERENCES interventions(intervention_id),
  intervention_code varchar(64) NOT NULL CHECK (intervention_code = 'LISTEN_BEFORE_RESPOND'),
  status varchar(24) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','COMPLETED','CANCELLED')),
  started_by_actor_id varchar(128) NOT NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  planned_days smallint NOT NULL DEFAULT 7 CHECK (planned_days = 7),
  policy_version varchar(48) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_intervention_episodes_one_active
ON intervention_episodes(family_id, onboarding_id)
WHERE status = 'ACTIVE';

INSERT INTO interventions (
  intervention_id,
  name,
  life_stage_code,
  target_dimensions,
  applicable_conditions,
  contraindications,
  mechanism,
  action_templates,
  evidence_grade,
  risk_level,
  human_requirement,
  version,
  status
) VALUES (
  'INTERVENTION-001',
  '先听后回应',
  'EARLY_ADOLESCENCE_12_15',
  '["P03","R03","R04","R05"]'::jsonb,
  '["confirmed_growth_priority","normal_safety_route"]'::jsonb,
  '["safety_escalation","active_conflicting_intervention"]'::jsonb,
  'Parent practices listening before advice in natural communication moments.',
  '["listen_without_interrupting","reflect_understanding","ask_before_advising"]'::jsonb,
  'E1',
  'LOW',
  'PARENT_CONFIRMATION',
  1,
  'ACTIVE'
) ON CONFLICT (intervention_id) DO UPDATE SET
  name = EXCLUDED.name,
  target_dimensions = EXCLUDED.target_dimensions,
  applicable_conditions = EXCLUDED.applicable_conditions,
  contraindications = EXCLUDED.contraindications,
  mechanism = EXCLUDED.mechanism,
  action_templates = EXCLUDED.action_templates,
  status = EXCLUDED.status;

ALTER TABLE growth_actions
  ADD COLUMN IF NOT EXISTS onboarding_id uuid NULL REFERENCES growth_journeys(journey_id),
  ADD COLUMN IF NOT EXISTS priority_id uuid NULL REFERENCES growth_priorities(priority_id),
  ADD COLUMN IF NOT EXISTS intervention_episode_id uuid NULL REFERENCES intervention_episodes(episode_id),
  ADD COLUMN IF NOT EXISTS day_index smallint NULL,
  ADD COLUMN IF NOT EXISTS assignment_text text NULL,
  ADD COLUMN IF NOT EXISTS due_date date NULL,
  ADD COLUMN IF NOT EXISTS completion_status varchar(24) NULL,
  ADD COLUMN IF NOT EXISTS reflection text NULL,
  ADD COLUMN IF NOT EXISTS reflection_boundary varchar(80) NULL,
  ADD COLUMN IF NOT EXISTS boundary varchar(48) NOT NULL DEFAULT 'ACTION_IS_NOT_OUTCOME';

ALTER TABLE growth_actions
  DROP CONSTRAINT IF EXISTS growth_actions_wave2_day_check;

ALTER TABLE growth_actions
  ADD CONSTRAINT growth_actions_wave2_day_check CHECK (day_index IS NULL OR day_index BETWEEN 1 AND 7);

ALTER TABLE growth_actions
  DROP CONSTRAINT IF EXISTS growth_actions_wave2_status_check;

ALTER TABLE growth_actions
  ADD CONSTRAINT growth_actions_wave2_status_check CHECK (status IN ('ASSIGNED','PENDING','COMPLETED','PARTIAL','NOT_COMPLETED'));

ALTER TABLE growth_actions
  DROP CONSTRAINT IF EXISTS growth_actions_wave2_completion_check;

ALTER TABLE growth_actions
  ADD CONSTRAINT growth_actions_wave2_completion_check CHECK (completion_status IS NULL OR completion_status IN ('COMPLETED','PARTIAL','NOT_COMPLETED'));

ALTER TABLE growth_actions
  DROP CONSTRAINT IF EXISTS growth_actions_wave2_boundary_check;

ALTER TABLE growth_actions
  ADD CONSTRAINT growth_actions_wave2_boundary_check CHECK (boundary = 'ACTION_IS_NOT_OUTCOME');

ALTER TABLE growth_actions
  DROP CONSTRAINT IF EXISTS growth_actions_wave2_reflection_boundary_check;

ALTER TABLE growth_actions
  ADD CONSTRAINT growth_actions_wave2_reflection_boundary_check CHECK (
    reflection_boundary IS NULL OR reflection_boundary = 'REFLECTION_IS_RAW_MATERIAL_NOT_OUTCOME'
  );

CREATE UNIQUE INDEX IF NOT EXISTS uq_growth_actions_episode_day
ON growth_actions(intervention_episode_id, day_index)
WHERE intervention_episode_id IS NOT NULL AND day_index IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_growth_actions_wave2_today
ON growth_actions(family_id, onboarding_id, intervention_episode_id, day_index);