ALTER TABLE family_curriculum_operations
  DROP CONSTRAINT IF EXISTS family_curriculum_operations_action_name_check;
ALTER TABLE family_curriculum_operations
  ADD CONSTRAINT family_curriculum_operations_action_name_check
  CHECK (action_name IN (
    'ENROLL_GROWTH_CAMP_21',
    'CHECK_IN_GROWTH_CAMP_21_DAY',
    'RELEASE_CURRICULUM_DRAFT',
    'ADMIT_GROWTH_CAMP_21_SUBJECT'
  ));