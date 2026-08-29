-- UI-09 commercial task execution lifecycle.
-- Keeps GrowthAction as the canonical family fact and persists interaction state
-- so App/Web can read the same state after a client or API restart.

ALTER TABLE growth_actions
  ADD COLUMN IF NOT EXISTS execution_status varchar(24),
  ADD COLUMN IF NOT EXISTS started_at timestamptz NULL,
  ADD COLUMN IF NOT EXISTS paused_at timestamptz NULL,
  ADD COLUMN IF NOT EXISTS cancelled_at timestamptz NULL,
  ADD COLUMN IF NOT EXISTS row_version integer NOT NULL DEFAULT 1;

UPDATE growth_actions
SET execution_status = CASE status
  WHEN 'COMPLETED' THEN 'COMPLETED'
  WHEN 'PARTIAL' THEN 'PARTIAL'
  WHEN 'NOT_COMPLETED' THEN 'NOT_COMPLETED'
  ELSE 'NOT_STARTED'
END
WHERE execution_status IS NULL;

ALTER TABLE growth_actions
  ALTER COLUMN execution_status SET DEFAULT 'NOT_STARTED',
  ALTER COLUMN execution_status SET NOT NULL;

ALTER TABLE growth_actions
  DROP CONSTRAINT IF EXISTS growth_actions_execution_status_check;

ALTER TABLE growth_actions
  ADD CONSTRAINT growth_actions_execution_status_check CHECK (
    execution_status IN ('NOT_STARTED','IN_PROGRESS','PAUSED','COMPLETED','PARTIAL','NOT_COMPLETED','CANCELLED')
  );

ALTER TABLE growth_actions
  DROP CONSTRAINT IF EXISTS growth_actions_row_version_check;

ALTER TABLE growth_actions
  ADD CONSTRAINT growth_actions_row_version_check CHECK (row_version > 0);

CREATE INDEX IF NOT EXISTS idx_growth_actions_family_due_execution
  ON growth_actions(family_id, due_date, execution_status, day_index);
