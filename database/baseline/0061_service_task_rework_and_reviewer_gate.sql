-- 0057_service_task_rework_and_reviewer_gate
-- FAMILY-SERVICE-COLLAB-ALLOCATION-P0-002-B:
--   1) REWORK_REQUIRED must produce a real, traceable rework task instead of silently
--      resetting the original task back to IN_PROGRESS (which erases the review history).
--   2) Quality review of CONTENT_RESOURCE/CASE_STEWARD/DELIVERY_RESOURCE work must be
--      performed by whoever is actually the case's assigned QUALITY_REVIEWER, not any
--      caller-supplied string.

ALTER TYPE service_task_status ADD VALUE IF NOT EXISTS 'REWORK_REQUESTED';

ALTER TABLE service_tasks
  ADD COLUMN IF NOT EXISTS rework_of_task_id uuid NULL REFERENCES service_tasks(task_id),
  ADD COLUMN IF NOT EXISTS rework_attempt integer NOT NULL DEFAULT 0 CHECK (rework_attempt >= 0);
CREATE INDEX IF NOT EXISTS idx_service_tasks_rework_of ON service_tasks(rework_of_task_id);

COMMENT ON COLUMN service_tasks.rework_of_task_id IS 'Set on the follow-up task created after a REWORK_REQUIRED review; the original task keeps its REWORK_REQUESTED history intact.';
