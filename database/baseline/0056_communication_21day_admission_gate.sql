-- D0 admission is deliberately separate from runtime Day 1.
-- It records eligibility and safety routing only; it is not an outcome or score.
CREATE TABLE IF NOT EXISTS family_growth_camp_admissions (
  admission_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_person_id uuid NOT NULL REFERENCES persons(person_id),
  program_ref varchar(96) NOT NULL DEFAULT 'communication-21day',
  status varchar(24) NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','ADMITTED','HUMAN_GATE_REQUIRED','REJECTED','EXPIRED')),
  baseline jsonb NOT NULL DEFAULT '{}'::jsonb,
  risk_signals jsonb NOT NULL DEFAULT '[]'::jsonb,
  decision_boundary varchar(120) NOT NULL DEFAULT 'ADMISSION_NOT_DIAGNOSIS_NOT_OUTCOME',
  decided_by_actor_id varchar(128) NULL,
  decided_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (family_id, subject_person_id, program_ref)
);
CREATE INDEX IF NOT EXISTS idx_family_growth_camp_admissions_scope
  ON family_growth_camp_admissions(tenant_id, family_id, program_ref, status);