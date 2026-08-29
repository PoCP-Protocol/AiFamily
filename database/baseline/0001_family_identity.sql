-- 0001_family_identity — Family Identity 核心(FIX-01 重切,按语句边界,零语义改动)
-- 依赖:无。对象:pgcrypto + 身份枚举 + families/persons/family_relationships/life_stage_assignments/consents
-- 幂等:IF NOT EXISTS / DO$$ duplicate_object 守卫;可在单事务内执行。
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$ BEGIN
  CREATE TYPE family_status AS ENUM ('ACTIVE','INACTIVE','ARCHIVED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE person_type AS ENUM ('PARENT','CHILD');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE parent_role AS ENUM ('MOTHER','FATHER','GUARDIAN','OTHER_GUARDIAN');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE relationship_type AS ENUM ('PARENT_CHILD','SPOUSE','SIBLING','GUARDIAN_CHILD','OTHER');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE life_stage_code AS ENUM ('EARLY_ADOLESCENCE_12_15');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE consent_purpose AS ENUM (
    'SERVICE','ASSESSMENT','AI_PERSONALIZATION','GROWTH_TRACKING',
    'EXPERT_SERVICE','RESEARCH','MODEL_IMPROVEMENT','CONTENT_PUBLICATION'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE consent_status AS ENUM ('GRANTED','WITHDRAWN','EXPIRED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS families (
  family_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  display_name varchar(100) NOT NULL,
  status family_status NOT NULL DEFAULT 'ACTIVE',
  primary_contact_person_id uuid NULL,
  version integer NOT NULL DEFAULT 1 CHECK (version >= 1),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS persons (
  person_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  person_type person_type NOT NULL,
  parent_role parent_role NULL,
  display_name varchar(100) NOT NULL,
  birth_date date NULL,
  account_id varchar(128) NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT parent_role_only_for_parent CHECK (
    (person_type='PARENT' AND parent_role IS NOT NULL) OR
    (person_type='CHILD' AND parent_role IS NULL)
  )
);
CREATE INDEX IF NOT EXISTS idx_persons_family ON persons(family_id);

ALTER TABLE families
  DROP CONSTRAINT IF EXISTS fk_family_primary_contact;
ALTER TABLE families
  ADD CONSTRAINT fk_family_primary_contact
  FOREIGN KEY (primary_contact_person_id) REFERENCES persons(person_id)
  DEFERRABLE INITIALLY DEFERRED;

CREATE TABLE IF NOT EXISTS family_relationships (
  relationship_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  person_a_id uuid NOT NULL REFERENCES persons(person_id),
  person_b_id uuid NOT NULL REFERENCES persons(person_id),
  relationship_type relationship_type NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT relationship_not_self CHECK (person_a_id <> person_b_id)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_relationship_directional
ON family_relationships(family_id, person_a_id, person_b_id, relationship_type);

CREATE TABLE IF NOT EXISTS life_stage_assignments (
  assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  child_id uuid NOT NULL REFERENCES persons(person_id),
  life_stage_code life_stage_code NOT NULL,
  effective_from timestamptz NOT NULL,
  effective_to timestamptz NULL,
  source varchar(64) NOT NULL DEFAULT 'MANUAL',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT life_stage_time CHECK (effective_to IS NULL OR effective_to > effective_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_life_stage
ON life_stage_assignments(child_id)
WHERE effective_to IS NULL;

CREATE TABLE IF NOT EXISTS consents (
  consent_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_person_id uuid NOT NULL REFERENCES persons(person_id),
  guardian_person_id uuid NOT NULL REFERENCES persons(person_id),
  purpose consent_purpose NOT NULL,
  status consent_status NOT NULL,
  policy_version varchar(64) NOT NULL,
  granted_at timestamptz NOT NULL,
  withdrawn_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT withdrawn_time_consistent CHECK (
    (status='WITHDRAWN' AND withdrawn_at IS NOT NULL) OR
    (status<>'WITHDRAWN')
  )
);
CREATE INDEX IF NOT EXISTS idx_consents_subject_purpose
ON consents(subject_person_id, purpose, status);
