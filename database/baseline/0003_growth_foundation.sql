-- 0003_growth_foundation — Growth 基础(FIX-01 重切,依赖顺序正确:先 journeys/interventions 后 actions/events)
-- 依赖:0001(families/persons/life_stage_code)。对象:growth 枚举 + growth_profiles..outcomes
-- 注:M1(Family Core)不写入这些表;此处仅建结构,为 M2 GrowthProfile 预留。幂等 + 单事务可执行。
DO $$ BEGIN
  CREATE TYPE growth_domain AS ENUM ('CHILD','PARENT','RELATIONSHIP');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE growth_state AS ENUM ('EMERGING','DEVELOPING','PRACTICING','STABILIZING');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS growth_profiles (
  profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_type growth_domain NOT NULL,
  subject_ref_id varchar(128) NOT NULL,
  life_stage_code life_stage_code NOT NULL,
  strengths jsonb NOT NULL DEFAULT '[]'::jsonb,
  growth_opportunities jsonb NOT NULL DEFAULT '[]'::jsonb,
  confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  version integer NOT NULL CHECK (version >= 1),
  effective_from timestamptz NOT NULL,
  effective_to timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT growth_profile_time CHECK (effective_to IS NULL OR effective_to > effective_from)
);
CREATE INDEX IF NOT EXISTS idx_growth_profiles_family
ON growth_profiles(family_id, subject_type, effective_from DESC);

CREATE TABLE IF NOT EXISTS growth_profile_dimensions (
  profile_id uuid NOT NULL REFERENCES growth_profiles(profile_id) ON DELETE CASCADE,
  dimension_id varchar(16) NOT NULL,
  state growth_state NOT NULL,
  observable_signals jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  PRIMARY KEY (profile_id, dimension_id)
);

CREATE TABLE IF NOT EXISTS growth_priorities (
  priority_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  profile_id uuid NOT NULL REFERENCES growth_profiles(profile_id),
  dimension_id varchar(16) NOT NULL,
  rank smallint NOT NULL CHECK (rank BETWEEN 1 AND 2),
  confirmed_by_actor_id varchar(128) NOT NULL,
  confirmed_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS interventions (
  intervention_id varchar(64) PRIMARY KEY,
  name varchar(200) NOT NULL,
  life_stage_code life_stage_code NOT NULL,
  target_dimensions jsonb NOT NULL,
  applicable_conditions jsonb NOT NULL DEFAULT '[]'::jsonb,
  contraindications jsonb NOT NULL DEFAULT '[]'::jsonb,
  mechanism text NULL,
  action_templates jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_grade varchar(8) NOT NULL,
  risk_level varchar(16) NOT NULL DEFAULT 'LOW',
  human_requirement varchar(32) NOT NULL DEFAULT 'NONE',
  version integer NOT NULL DEFAULT 1,
  status varchar(16) NOT NULL DEFAULT 'DRAFT',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS growth_journeys (
  journey_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  journey_type varchar(64) NOT NULL,
  phase varchar(32) NOT NULL,
  status varchar(16) NOT NULL,
  started_at timestamptz NOT NULL,
  completed_at timestamptz NULL,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS growth_actions (
  action_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  journey_id uuid NULL REFERENCES growth_journeys(journey_id),
  intervention_id varchar(64) NULL REFERENCES interventions(intervention_id),
  dimension_id varchar(16) NOT NULL,
  action_type varchar(64) NOT NULL,
  instruction text NOT NULL,
  status varchar(16) NOT NULL DEFAULT 'ASSIGNED',
  assigned_to_person_id uuid NULL REFERENCES persons(person_id),
  assigned_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS growth_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  event_type varchar(64) NOT NULL,
  occurred_at timestamptz NOT NULL,
  source varchar(64) NOT NULL,
  action_id uuid NULL REFERENCES growth_actions(action_id),
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_growth_events_family_time
ON growth_events(family_id, occurred_at DESC);

CREATE TABLE IF NOT EXISTS perspectives (
  perspective_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  event_id uuid NULL REFERENCES growth_events(event_id),
  person_id uuid NULL REFERENCES persons(person_id),
  perspective_type varchar(32) NOT NULL,
  statement text NOT NULL,
  recorded_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS evidence_records (
  evidence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  evidence_type varchar(32) NOT NULL,
  source_ref varchar(256) NULL,
  payload jsonb NOT NULL,
  observed_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS milestones (
  milestone_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  journey_id uuid NULL REFERENCES growth_journeys(journey_id),
  dimension_id varchar(16) NULL,
  milestone_type varchar(64) NOT NULL,
  title varchar(200) NOT NULL,
  evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  confirmed_by_actor_id varchar(128) NOT NULL,
  confirmed_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS outcomes (
  outcome_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  dimension_id varchar(16) NOT NULL,
  baseline jsonb NULL,
  current_value jsonb NULL,
  window_start timestamptz NOT NULL,
  window_end timestamptz NOT NULL,
  source varchar(64) NOT NULL,
  evidence_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  confidence numeric(5,4) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
  context jsonb NOT NULL DEFAULT '{}'::jsonb,
  possible_confounders jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT outcome_window CHECK (window_end > window_start)
);
