-- 0009_m2_wave3_observe_review — M2 Wave 3 Observe & Review.
-- Additive only: observation is not fact/causal effect; review is not profile mutation.

CREATE TABLE IF NOT EXISTS outcome_observations (
  observation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_person_id uuid NOT NULL REFERENCES persons(person_id),
  observer_person_id uuid NOT NULL REFERENCES persons(person_id),
  intervention_episode_id uuid NOT NULL REFERENCES intervention_episodes(episode_id),
  perspective_type varchar(32) NOT NULL CHECK (perspective_type IN ('PARENT_OBSERVATION','CHILD_OBSERVATION')),
  observation_text text NOT NULL CHECK (char_length(observation_text) BETWEEN 1 AND 2000),
  action_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  reflection_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
  observed_at timestamptz NOT NULL,
  boundary varchar(80) NOT NULL DEFAULT 'OBSERVATION_IS_NOT_FACT_OR_CAUSAL_EFFECT',
  policy_version varchar(48) NOT NULL DEFAULT 'M2_106_DETERMINISTIC_V1',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT outcome_observations_boundary_check CHECK (boundary = 'OBSERVATION_IS_NOT_FACT_OR_CAUSAL_EFFECT')
);

ALTER TABLE outcome_observations
  ADD COLUMN IF NOT EXISTS action_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS reflection_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS limitations jsonb NOT NULL DEFAULT '[]'::jsonb;

CREATE INDEX IF NOT EXISTS idx_outcome_observations_episode
ON outcome_observations(family_id, intervention_episode_id, observed_at DESC);

CREATE TABLE IF NOT EXISTS growth_reviews (
  review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  onboarding_id uuid NOT NULL REFERENCES growth_journeys(journey_id),
  intervention_episode_id uuid NOT NULL REFERENCES intervention_episodes(episode_id),
  priority_id uuid NOT NULL REFERENCES growth_priorities(priority_id),
  dimension_id varchar(16) NOT NULL CHECK (dimension_id IN ('P03','R03','R04','R05')),
  status varchar(24) NOT NULL DEFAULT 'COMPLETED' CHECK (status = 'COMPLETED'),
  action_summary jsonb NOT NULL,
  observation_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  limitations jsonb NOT NULL DEFAULT '[]'::jsonb,
  boundary varchar(80) NOT NULL DEFAULT 'REVIEW_IS_NOT_PROFILE_MUTATION_OR_DIAGNOSIS',
  policy_version varchar(48) NOT NULL DEFAULT 'M2_106_DETERMINISTIC_V1',
  completed_by_actor_id varchar(128) NOT NULL,
  completed_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT growth_reviews_boundary_check CHECK (boundary = 'REVIEW_IS_NOT_PROFILE_MUTATION_OR_DIAGNOSIS')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_growth_reviews_episode
ON growth_reviews(intervention_episode_id);

CREATE TABLE IF NOT EXISTS next_step_decisions (
  decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  review_id uuid NOT NULL REFERENCES growth_reviews(review_id),
  intervention_episode_id uuid NOT NULL REFERENCES intervention_episodes(episode_id),
  decision varchar(24) NOT NULL CHECK (decision IN ('CONTINUE','ADJUST','PAUSE','REVIEW_REQUIRED')),
  rationale text NULL CHECK (rationale IS NULL OR char_length(rationale) <= 2000),
  boundary varchar(80) NOT NULL DEFAULT 'NEXT_STEP_DECISION_IS_NOT_NEXT_ACTION',
  policy_version varchar(48) NOT NULL DEFAULT 'M2_106_DETERMINISTIC_V1',
  decided_by_actor_id varchar(128) NOT NULL,
  decided_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT next_step_decisions_boundary_check CHECK (boundary = 'NEXT_STEP_DECISION_IS_NOT_NEXT_ACTION')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_next_step_decisions_review
ON next_step_decisions(review_id);