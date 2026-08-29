CREATE UNIQUE INDEX IF NOT EXISTS ux_consents_active_subject_purpose
  ON consents (family_id, subject_person_id, purpose)
  WHERE status = 'GRANTED';