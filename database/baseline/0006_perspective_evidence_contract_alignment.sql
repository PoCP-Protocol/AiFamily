-- 0006_perspective_evidence_contract_alignment — M2-102 Perspective/Evidence contract alignment.
-- Additive migration: keeps legacy columns while adding explicit provenance, safety policy, and evidence linkage.
ALTER TABLE perspectives
  ADD COLUMN IF NOT EXISTS onboarding_id uuid NULL REFERENCES growth_journeys(journey_id),
  ADD COLUMN IF NOT EXISTS subject_person_id uuid NULL REFERENCES persons(person_id),
  ADD COLUMN IF NOT EXISTS author_person_id uuid NULL REFERENCES persons(person_id),
  ADD COLUMN IF NOT EXISTS recorded_by_actor_id varchar(128) NULL,
  ADD COLUMN IF NOT EXISTS capture_mode varchar(32) NULL,
  ADD COLUMN IF NOT EXISTS related_dimension_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  ADD COLUMN IF NOT EXISTS content jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS fact_boundary varchar(32) NOT NULL DEFAULT 'PERSPECTIVE_NOT_FACT',
  ADD COLUMN IF NOT EXISTS safety_disposition jsonb NOT NULL DEFAULT '{}'::jsonb,
  ADD COLUMN IF NOT EXISTS expressed_at timestamptz NULL,
  ADD COLUMN IF NOT EXISTS version integer NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_perspectives_onboarding_time
ON perspectives(family_id, onboarding_id, recorded_at DESC);

CREATE INDEX IF NOT EXISTS idx_perspectives_subject_type
ON perspectives(family_id, subject_person_id, perspective_type);

ALTER TABLE evidence_records
  ADD COLUMN IF NOT EXISTS perspective_id uuid NULL REFERENCES perspectives(perspective_id),
  ADD COLUMN IF NOT EXISTS source varchar(32) NULL,
  ADD COLUMN IF NOT EXISTS evidence_level varchar(8) NOT NULL DEFAULT 'E1';

CREATE INDEX IF NOT EXISTS idx_evidence_records_perspective
ON evidence_records(family_id, perspective_id);