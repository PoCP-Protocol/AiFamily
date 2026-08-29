-- 0025_tenant_master_data_foundation
-- DEV/TEST first foundation for the 32-object master-data baseline.
-- Compatibility rule: existing Family/Account semantics remain valid; Tenant binding is additive.

DO $$ BEGIN
  CREATE TYPE tenant_status AS ENUM ('ACTIVE','SUSPENDED','ARCHIVED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE tenant_type AS ENUM ('DIRECT_CUSTOMER','PARTNER','INTERNAL_SANDBOX');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE tenant_membership_role AS ENUM ('TENANT_OWNER','TENANT_ADMIN','TENANT_OPERATOR','TENANT_VIEWER');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE tenant_membership_status AS ENUM ('INVITED','ACTIVE','SUSPENDED','REVOKED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE tenant_binding_status AS ENUM ('ACTIVE','SUSPENDED','MIGRATING','REVOKED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS tenants (
  tenant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_ref varchar(128) NOT NULL UNIQUE,
  display_name varchar(160) NOT NULL,
  tenant_type tenant_type NOT NULL,
  status tenant_status NOT NULL DEFAULT 'ACTIVE',
  region_ref varchar(64) NOT NULL DEFAULT 'TEST-LOCAL',
  plan_ref varchar(128) NULL,
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS tenant_account_memberships (
  tenant_membership_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  account_id uuid NOT NULL REFERENCES accounts(account_id),
  role tenant_membership_role NOT NULL,
  status tenant_membership_status NOT NULL DEFAULT 'INVITED',
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_to timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT tenant_membership_time CHECK (valid_to IS NULL OR valid_to > valid_from),
  CONSTRAINT uq_tenant_account_membership UNIQUE (tenant_id, account_id)
);
CREATE INDEX IF NOT EXISTS idx_tenant_account_membership_account
  ON tenant_account_memberships(account_id, status);

CREATE TABLE IF NOT EXISTS tenant_family_bindings (
  tenant_family_binding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  status tenant_binding_status NOT NULL DEFAULT 'ACTIVE',
  effective_from timestamptz NOT NULL DEFAULT now(),
  effective_to timestamptz NULL,
  migration_ref varchar(128) NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT tenant_family_binding_time CHECK (effective_to IS NULL OR effective_to > effective_from),
  CONSTRAINT uq_tenant_family_binding_version UNIQUE (tenant_id, family_id, effective_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_tenant_family_binding
  ON tenant_family_bindings(family_id)
  WHERE status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_tenant_family_bindings_tenant
  ON tenant_family_bindings(tenant_id, status);

CREATE TABLE IF NOT EXISTS tenant_policy_profiles (
  tenant_policy_profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  policy_version varchar(128) NOT NULL,
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','ACTIVE','RETIRED')),
  allowed_pages jsonb NOT NULL DEFAULT '[]'::jsonb,
  allowed_tools jsonb NOT NULL DEFAULT '[]'::jsonb,
  llm_policy_ref varchar(128) NULL,
  retention_policy_ref varchar(128) NULL,
  external_adapter_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, policy_version)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_active_tenant_policy
  ON tenant_policy_profiles(tenant_id)
  WHERE status = 'ACTIVE';

CREATE TABLE IF NOT EXISTS tenant_catalog_bindings (
  tenant_catalog_binding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  catalog_object_type varchar(64) NOT NULL,
  catalog_object_ref varchar(160) NOT NULL,
  catalog_version integer NOT NULL CHECK (catalog_version > 0),
  visibility varchar(24) NOT NULL CHECK (visibility IN ('VISIBLE','HIDDEN')),
  status varchar(24) NOT NULL CHECK (status IN ('ADMITTED','SUSPENDED','EXPIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, catalog_object_type, catalog_object_ref, catalog_version)
);
CREATE INDEX IF NOT EXISTS idx_tenant_catalog_binding_visible
  ON tenant_catalog_bindings(tenant_id, status, visibility, catalog_object_type);

COMMENT ON TABLE tenants IS 'Tenant master data: commercial/customer isolation namespace; not Family data owner.';
COMMENT ON TABLE tenant_account_memberships IS 'Account membership and role inside a Tenant; must be active before Tenant context.';
COMMENT ON TABLE tenant_family_bindings IS 'Authoritative Tenant-to-Family binding; exactly one ACTIVE binding per Family.';
COMMENT ON TABLE tenant_policy_profiles IS 'Tenant policy may restrict, never widen, platform safety/model/tool policy.';
COMMENT ON TABLE tenant_catalog_bindings IS 'Tenant-specific visibility/admission/version binding over platform catalog objects.';
