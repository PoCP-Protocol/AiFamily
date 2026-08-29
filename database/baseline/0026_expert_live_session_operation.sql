-- Dev/test-only operation kind for the UI-01 expert live session entry.
-- It records a family-scoped viewing intent only; it does not create audio/video,
-- contact an expert, send a notification, reserve a seat, or create a booking.
DO $$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_type WHERE typname = 'test_experience_operation_kind')
     AND NOT EXISTS (
       SELECT 1
       FROM pg_enum e
       JOIN pg_type t ON t.oid = e.enumtypid
       WHERE t.typname = 'test_experience_operation_kind'
         AND e.enumlabel = 'EXPERT_LIVE_SESSION'
     ) THEN
    ALTER TYPE test_experience_operation_kind ADD VALUE 'EXPERT_LIVE_SESSION';
  END IF;
END $$;
