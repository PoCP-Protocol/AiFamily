-- 0034_family_page_task_source_page_id
-- Forward compatibility migration for Family Page Objects task facts.
-- Only legacy TEST_FIXTURE task rows are deterministically backfilled to UI-09 so that
-- previously stored DEV/TEST fixtures remain addressable. This backfill is not a business conclusion.
-- Any non-test task without an explicit source_page_id fails closed and requires an explicit mapping.

ALTER TABLE family_page_task_items
  ADD COLUMN IF NOT EXISTS source_page_id varchar(5);

UPDATE family_page_task_items
SET source_page_id = 'UI-09'
WHERE source = 'TEST_FIXTURE'
  AND source_page_id IS NULL;

DO $$ BEGIN
  IF EXISTS (
    SELECT 1
    FROM family_page_task_items
    WHERE source_page_id IS NULL
  ) THEN
    RAISE EXCEPTION
      'family_page_task_items rows without source_page_id require explicit page mapping before migration 0034 can continue';
  END IF;
END $$;

ALTER TABLE family_page_task_items
  ALTER COLUMN source_page_id SET NOT NULL;

DO $$ BEGIN
  ALTER TABLE family_page_task_items
    ADD CONSTRAINT family_page_task_source_page_id_ck
    CHECK (source_page_id ~ '^UI-(0[1-9]|[12][0-9]|3[0-4])$');
EXCEPTION WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_family_page_tasks_family_page_status
  ON family_page_task_items(family_id, source_page_id, status, created_at DESC);
