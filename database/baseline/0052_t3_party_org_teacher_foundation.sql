-- TENANCY-T3-PATCH-2: Party / Organization / Teacher foundation.
-- Does not alter Family ownership or TenantFamilyBinding semantics.
-- No family data is exposed by these tables.

DO $$ BEGIN
  CREATE TYPE party_kind AS ENUM ('INDIVIDUAL','ORGANIZATION');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE organization_status AS ENUM ('DRAFT','ACTIVE','SUSPENDED','ENDED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE organization_membership_status AS ENUM ('INVITED','ACTIVE','SUSPENDED','ENDED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE teacher_profile_status AS ENUM ('DRAFT','PENDING_REVIEW','ADMITTED','SUSPENDED','ENDED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE provider_profile_kind AS ENUM ('INDIVIDUAL','ORGANIZATION');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE provider_profile_status AS ENUM ('DRAFT','ACTIVE','SUSPENDED','RETIRED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE provider_admission_status AS ENUM ('PENDING','ADMITTED','SUSPENDED','REJECTED','EXPIRED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS parties (
  party_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  party_kind party_kind NOT NULL,
  display_name varchar(200) NOT NULL,
  status varchar(24) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SUSPENDED','ENDED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS individual_parties (
  party_id uuid PRIMARY KEY REFERENCES parties(party_id),
  legal_name varchar(200) NULL,
  locale varchar(32) NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS account_party_bindings (
  account_party_binding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL REFERENCES accounts(account_id),
  party_id uuid NOT NULL REFERENCES parties(party_id),
  status varchar(24) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','REVOKED')),
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_to timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT account_party_binding_time CHECK (valid_to IS NULL OR valid_to > valid_from),
  UNIQUE (account_id, party_id)
);
CREATE INDEX IF NOT EXISTS idx_account_party_bindings_active
  ON account_party_bindings(account_id, status, valid_from);

CREATE TABLE IF NOT EXISTS organizations (
  organization_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  party_id uuid NOT NULL UNIQUE REFERENCES parties(party_id),
  organization_ref varchar(128) NOT NULL UNIQUE,
  legal_name varchar(200) NOT NULL,
  organization_type varchar(48) NOT NULL CHECK (organization_type IN ('SCHOOL','EDUCATION_PROVIDER','CONSULTING','NONPROFIT','ENTERPRISE','OTHER')),
  status organization_status NOT NULL DEFAULT 'DRAFT',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS organization_units (
  organization_unit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  parent_unit_id uuid NULL REFERENCES organization_units(organization_unit_id),
  unit_ref varchar(128) NOT NULL,
  display_name varchar(160) NOT NULL,
  status organization_status NOT NULL DEFAULT 'ACTIVE',
  UNIQUE (organization_id, unit_ref)
);

CREATE TABLE IF NOT EXISTS organization_tenant_bindings (
  organization_tenant_binding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  status varchar(24) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SUSPENDED','ENDED')),
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_to timestamptz NULL,
  UNIQUE (organization_id, tenant_id),
  CONSTRAINT organization_tenant_binding_time CHECK (valid_to IS NULL OR valid_to > valid_from)
);
CREATE INDEX IF NOT EXISTS idx_org_tenant_bindings_active
  ON organization_tenant_bindings(tenant_id, status, organization_id);

CREATE TABLE IF NOT EXISTS organization_memberships (
  organization_membership_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  party_id uuid NOT NULL REFERENCES parties(party_id),
  organization_unit_id uuid NULL REFERENCES organization_units(organization_unit_id),
  role varchar(48) NOT NULL CHECK (role IN ('ORG_OWNER','ORG_ADMIN','ORG_OPERATOR','ORG_TEACHER','ORG_VIEWER')),
  status organization_membership_status NOT NULL DEFAULT 'INVITED',
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_to timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT organization_membership_time CHECK (valid_to IS NULL OR valid_to > valid_from),
  UNIQUE (organization_id, party_id)
);
CREATE INDEX IF NOT EXISTS idx_org_memberships_active
  ON organization_memberships(organization_id, status, role);

CREATE TABLE IF NOT EXISTS teacher_profiles (
  teacher_profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  party_id uuid NOT NULL UNIQUE REFERENCES individual_parties(party_id),
  teacher_ref varchar(128) NOT NULL UNIQUE,
  public_display_name varchar(160) NOT NULL,
  status teacher_profile_status NOT NULL DEFAULT 'DRAFT',
  bio text NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS teacher_affiliations (
  teacher_affiliation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  teacher_profile_id uuid NOT NULL REFERENCES teacher_profiles(teacher_profile_id),
  organization_id uuid NOT NULL REFERENCES organizations(organization_id),
  organization_unit_id uuid NULL REFERENCES organization_units(organization_unit_id),
  affiliation_type varchar(32) NOT NULL CHECK (affiliation_type IN ('EMPLOYED','CONTRACTOR','PARTNER','VOLUNTEER')),
  authorization_scope jsonb NOT NULL DEFAULT '{}'::jsonb CHECK (jsonb_typeof(authorization_scope) = 'object'),
  status organization_membership_status NOT NULL DEFAULT 'INVITED',
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_to timestamptz NULL,
  CONSTRAINT teacher_affiliation_time CHECK (valid_to IS NULL OR valid_to > valid_from)
);
CREATE INDEX IF NOT EXISTS idx_teacher_affiliations_active
  ON teacher_affiliations(teacher_profile_id, status, valid_from);

CREATE TABLE IF NOT EXISTS teacher_qualifications (
  teacher_qualification_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  teacher_profile_id uuid NOT NULL REFERENCES teacher_profiles(teacher_profile_id),
  qualification_ref varchar(160) NOT NULL,
  qualification_type varchar(80) NOT NULL,
  issuer_ref varchar(160) NULL,
  status varchar(24) NOT NULL CHECK (status IN ('PENDING','ACTIVE','EXPIRED','REJECTED')),
  issued_at date NULL,
  expires_at date NULL,
  evidence_ref varchar(240) NULL,
  UNIQUE (teacher_profile_id, qualification_ref),
  CONSTRAINT teacher_qualification_dates CHECK (expires_at IS NULL OR issued_at IS NULL OR expires_at > issued_at)
);

CREATE TABLE IF NOT EXISTS teacher_capabilities (
  teacher_capability_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  teacher_profile_id uuid NOT NULL REFERENCES teacher_profiles(teacher_profile_id),
  capability_ref varchar(128) NOT NULL,
  service_domain varchar(80) NOT NULL,
  age_band varchar(80) NULL,
  languages jsonb NOT NULL DEFAULT '[]'::jsonb CHECK (jsonb_typeof(languages) = 'array'),
  status varchar(24) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('ACTIVE','SUSPENDED','ENDED')),
  UNIQUE (teacher_profile_id, capability_ref)
);

CREATE TABLE IF NOT EXISTS provider_profiles (
  provider_profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  owner_party_id uuid NOT NULL REFERENCES parties(party_id),
  provider_kind provider_profile_kind NOT NULL,
  provider_ref varchar(128) NOT NULL UNIQUE,
  display_name varchar(160) NOT NULL,
  status provider_profile_status NOT NULL DEFAULT 'DRAFT',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS provider_admissions (
  provider_admission_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_profile_id uuid NOT NULL REFERENCES provider_profiles(provider_profile_id),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  status provider_admission_status NOT NULL DEFAULT 'PENDING',
  admission_ref varchar(128) NOT NULL,
  reviewed_by_account_id uuid NULL REFERENCES accounts(account_id),
  reviewed_at timestamptz NULL,
  expires_at timestamptz NULL,
  UNIQUE (provider_profile_id, tenant_id, admission_ref)
);
CREATE INDEX IF NOT EXISTS idx_provider_admissions_tenant_status
  ON provider_admissions(tenant_id, status, provider_profile_id);

COMMENT ON TABLE parties IS 'Business participant identity; never a Family data owner.';
COMMENT ON TABLE organizations IS 'Organization business主体; does not own Family data.';
COMMENT ON TABLE teacher_profiles IS 'Professional teacher identity, separate from Account and Family Person role.';
COMMENT ON TABLE provider_profiles IS 'Commercial/fulfillment provider; seller and assigned teacher remain separate concepts.';
COMMENT ON TABLE provider_admissions IS 'Tenant-scoped provider admission; no admission means no formal publishing.';
