-- 0007_growth_profile_draft_confirmation — M2-103 Evidence Synthesis + Limited Growth Profile.
-- Additive only: Evidence/Perspective remain source records; Profile is a confirmed interpretive working model.

ALTER TABLE growth_profiles
  ADD COLUMN IF NOT EXISTS profile_scope varchar(48) NULL,
  ADD COLUMN IF NOT EXISTS subject_person_id uuid NULL REFERENCES persons(person_id),
  ADD COLUMN IF NOT EXISTS subject_relationship_id uuid NULL REFERENCES family_relationships(relationship_id),
  ADD COLUMN IF NOT EXISTS status varchar(24) NOT NULL DEFAULT 'WORKING',
  ADD COLUMN IF NOT EXISTS basis jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS evidence_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS policy_version varchar(48) NULL,
  ADD COLUMN IF NOT EXISTS confirmed_by_actor_id varchar(128) NULL,
  ADD COLUMN IF NOT EXISTS confirmed_at timestamptz NULL,
  ADD COLUMN IF NOT EXISTS previous_profile_id uuid NULL REFERENCES growth_profiles(profile_id);

CREATE INDEX IF NOT EXISTS idx_growth_profiles_m2_subject
ON growth_profiles(family_id, profile_scope, subject_person_id, subject_relationship_id, effective_from DESC);

ALTER TABLE growth_profile_dimensions
  ADD COLUMN IF NOT EXISTS qualitative_confidence varchar(16) NULL,
  ADD COLUMN IF NOT EXISTS synthesis jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS evidence_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS policy_version varchar(48) NULL;

CREATE TABLE IF NOT EXISTS growth_profile_drafts (
  draft_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  onboarding_id uuid NOT NULL REFERENCES growth_journeys(journey_id),
  profile_scope varchar(48) NOT NULL CHECK (profile_scope IN ('PARENT_GROWTH_PROFILE','RELATIONSHIP_GROWTH_PROFILE')),
  subject_type growth_domain NOT NULL CHECK (subject_type IN ('PARENT','RELATIONSHIP')),
  subject_person_id uuid NULL REFERENCES persons(person_id),
  subject_relationship_id uuid NULL REFERENCES family_relationships(relationship_id),
  dimension_id varchar(16) NOT NULL CHECK (dimension_id IN ('P03','R03','R04','R05')),
  candidate_state varchar(16) NOT NULL CHECK (candidate_state IN ('EMERGING','DEVELOPING','PRACTICING','STABILIZING','UNRESOLVED')),
  qualitative_confidence varchar(16) NOT NULL CHECK (qualitative_confidence IN ('LOW','MEDIUM','HIGH')),
  synthesis jsonb NOT NULL,
  evidence_snapshot jsonb NOT NULL,
  policy_version varchar(48) NOT NULL,
  status varchar(16) NOT NULL DEFAULT 'DRAFT' CHECK (status IN ('DRAFT','REVIEW_REQUIRED','STALE','CONFIRMED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT growth_profile_draft_parent_subject CHECK (
    (profile_scope = 'PARENT_GROWTH_PROFILE' AND subject_type = 'PARENT' AND subject_person_id IS NOT NULL AND subject_relationship_id IS NULL)
    OR
    (profile_scope = 'RELATIONSHIP_GROWTH_PROFILE' AND subject_type = 'RELATIONSHIP' AND subject_person_id IS NULL AND subject_relationship_id IS NOT NULL)
  )
);

CREATE INDEX IF NOT EXISTS idx_growth_profile_drafts_onboarding
ON growth_profile_drafts(family_id, onboarding_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_growth_profile_drafts_subject_dimension
ON growth_profile_drafts(family_id, profile_scope, subject_person_id, subject_relationship_id, dimension_id, created_at DESC);