-- 0045_family_memory_p0_subject_scope
-- P0: Family memory subject scope. Family is not subject; legacy child-scoped
-- Growth objects must carry an explicit child person reference before they can
-- be used as trusted long-term context.

ALTER TABLE growth_priorities
  ADD COLUMN IF NOT EXISTS subject_person_id uuid NULL REFERENCES persons(person_id);

ALTER TABLE intervention_episodes
  ADD COLUMN IF NOT EXISTS subject_person_id uuid NULL REFERENCES persons(person_id);

ALTER TABLE growth_actions
  ADD COLUMN IF NOT EXISTS subject_person_id uuid NULL REFERENCES persons(person_id);

UPDATE growth_priorities gp
SET subject_person_id = profile.subject_person_id
FROM growth_profiles profile
WHERE gp.profile_id = profile.profile_id
  AND gp.family_id = profile.family_id
  AND gp.subject_person_id IS NULL
  AND profile.subject_type = 'CHILD'
  AND profile.subject_person_id IS NOT NULL;

UPDATE intervention_episodes ie
SET subject_person_id = gp.subject_person_id
FROM growth_priorities gp
WHERE ie.priority_id = gp.priority_id
  AND ie.family_id = gp.family_id
  AND ie.subject_person_id IS NULL
  AND gp.subject_person_id IS NOT NULL;

UPDATE growth_actions ga
SET subject_person_id = gp.subject_person_id
FROM growth_priorities gp
WHERE ga.priority_id = gp.priority_id
  AND ga.family_id = gp.family_id
  AND ga.subject_person_id IS NULL
  AND gp.subject_person_id IS NOT NULL;

UPDATE growth_actions ga
SET subject_person_id = ie.subject_person_id
FROM intervention_episodes ie
WHERE ga.intervention_episode_id = ie.episode_id
  AND ga.family_id = ie.family_id
  AND ga.subject_person_id IS NULL
  AND ie.subject_person_id IS NOT NULL;

UPDATE growth_actions ga
SET subject_person_id = gp.subject_person_id
FROM family_journey_plans jp
JOIN growth_priorities gp
  ON gp.priority_id = jp.priority_id
 AND gp.family_id = jp.family_id
WHERE ga.journey_plan_id = jp.plan_id
  AND ga.family_id = jp.family_id
  AND ga.subject_person_id IS NULL
  AND gp.subject_person_id IS NOT NULL;

ALTER TABLE growth_priorities
  DROP CONSTRAINT IF EXISTS growth_priorities_subject_family_check;

ALTER TABLE growth_priorities
  ADD CONSTRAINT growth_priorities_subject_family_check CHECK (
    subject_person_id IS NULL OR family_id IS NOT NULL
  );

ALTER TABLE intervention_episodes
  DROP CONSTRAINT IF EXISTS intervention_episodes_subject_priority_check;

ALTER TABLE intervention_episodes
  ADD CONSTRAINT intervention_episodes_subject_priority_check CHECK (
    subject_person_id IS NULL OR priority_id IS NOT NULL
  );

ALTER TABLE growth_actions
  DROP CONSTRAINT IF EXISTS growth_actions_subject_owner_check;

ALTER TABLE growth_actions
  ADD CONSTRAINT growth_actions_subject_owner_check CHECK (
    subject_person_id IS NULL OR priority_id IS NOT NULL OR intervention_episode_id IS NOT NULL OR journey_plan_id IS NOT NULL
  );

DROP INDEX IF EXISTS uq_growth_priorities_one_active_primary;
CREATE UNIQUE INDEX IF NOT EXISTS uq_growth_priorities_one_active_primary
ON growth_priorities(family_id, subject_person_id, onboarding_id)
WHERE status = 'ACTIVE' AND subject_person_id IS NOT NULL;

DROP INDEX IF EXISTS uq_intervention_episodes_one_active;
CREATE UNIQUE INDEX IF NOT EXISTS uq_intervention_episodes_one_active
ON intervention_episodes(family_id, subject_person_id, onboarding_id)
WHERE status = 'ACTIVE' AND subject_person_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_growth_priorities_family_subject_status
ON growth_priorities(family_id, subject_person_id, status, created_at DESC)
WHERE subject_person_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_intervention_episodes_family_subject_status
ON intervention_episodes(family_id, subject_person_id, status, created_at DESC)
WHERE subject_person_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_growth_actions_family_subject_due_status
ON growth_actions(family_id, subject_person_id, due_date, status, created_at DESC)
WHERE subject_person_id IS NOT NULL;

CREATE OR REPLACE VIEW family_memory_subject_scope_migration_audit AS
SELECT 'growth_priorities'::text AS table_name,
       count(*)::integer AS total_rows,
       count(*) FILTER (WHERE subject_person_id IS NOT NULL)::integer AS scoped_rows,
       count(*) FILTER (WHERE subject_person_id IS NULL)::integer AS ambiguous_rows
FROM growth_priorities
UNION ALL
SELECT 'intervention_episodes'::text AS table_name,
       count(*)::integer AS total_rows,
       count(*) FILTER (WHERE subject_person_id IS NOT NULL)::integer AS scoped_rows,
       count(*) FILTER (WHERE subject_person_id IS NULL)::integer AS ambiguous_rows
FROM intervention_episodes
UNION ALL
SELECT 'growth_actions'::text AS table_name,
       count(*)::integer AS total_rows,
       count(*) FILTER (WHERE subject_person_id IS NOT NULL)::integer AS scoped_rows,
       count(*) FILTER (WHERE subject_person_id IS NULL)::integer AS ambiguous_rows
FROM growth_actions;