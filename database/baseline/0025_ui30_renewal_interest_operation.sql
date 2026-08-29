-- 0023_ui30_renewal_interest_operation — UI-30 DEV renewal interest only
-- This adds a controlled draft operation kind. It never charges, renews, changes entitlements, or sends notifications.

DO $$ BEGIN
  ALTER TYPE test_experience_operation_kind ADD VALUE IF NOT EXISTS 'MEMBERSHIP_RENEWAL_DRAFT';
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
