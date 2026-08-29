-- Family operation receipt follow-ups: tenant + family scoped internal operations metadata.
-- Notes and manual states are operational perspectives, never child facts, outcomes or external effects.

CREATE TABLE IF NOT EXISTS family_operation_followups (
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  operation_id uuid NOT NULL,
  follow_up_status varchar(24) NOT NULL DEFAULT 'NOT_MARKED',
  operator_note text NULL,
  updated_by_person_id uuid NOT NULL REFERENCES persons(person_id),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (tenant_id, family_id, operation_id),
  CONSTRAINT family_operation_followups_status_check CHECK (follow_up_status IN ('NOT_MARKED', 'PENDING_FOLLOW_UP', 'PROCESSED')),
  CONSTRAINT family_operation_followups_note_length_check CHECK (operator_note IS NULL OR char_length(operator_note) <= 1000)
);

CREATE INDEX IF NOT EXISTS idx_family_operation_followups_family_updated
  ON family_operation_followups(tenant_id, family_id, follow_up_status, updated_at DESC);
