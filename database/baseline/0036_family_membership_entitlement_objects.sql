-- Family membership / benefit formal slice.
-- DEV/TEST only: no payment, renewal, notification, production entitlement or external adapter effect.
-- Object boundaries:
--   * plan + benefit definition = PLATFORM/TENANT catalogue masters.
--   * subscription + grant + ledger = Tenant/Family transaction facts.
--   * projection view = read-only family-private asset read model.

DO $$ BEGIN
  CREATE TYPE family_membership_scope AS ENUM ('PLATFORM', 'TENANT');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE family_membership_plan_status AS ENUM ('DRAFT', 'ACTIVE', 'SUSPENDED', 'RETIRED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE family_membership_subscription_status AS ENUM ('PENDING', 'ACTIVE', 'PAUSED', 'EXPIRED', 'CANCELLED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE family_membership_benefit_status AS ENUM ('PENDING', 'AVAILABLE', 'CONSUMED', 'REVOKED', 'EXPIRED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE family_membership_benefit_action AS ENUM ('GRANT', 'CONSUME', 'REVOKE');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE family_membership_allocation_type AS ENUM ('COUNT', 'ACCESS', 'CREDIT');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- Supply master: no family/actor/subject columns are applicable. Tenant scope is optional by design.
CREATE TABLE IF NOT EXISTS family_membership_plans (
  plan_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scope_type family_membership_scope NOT NULL DEFAULT 'PLATFORM',
  tenant_id uuid NULL REFERENCES tenants(tenant_id),
  plan_ref varchar(128) NOT NULL,
  version_no integer NOT NULL DEFAULT 1 CHECK (version_no > 0),
  title varchar(160) NOT NULL,
  status family_membership_plan_status NOT NULL DEFAULT 'ACTIVE',
  source_ref varchar(160) NOT NULL,
  fixture_only boolean NOT NULL DEFAULT true CHECK (fixture_only = true),
  attributes_schema_version integer NOT NULL DEFAULT 1 CHECK (attributes_schema_version > 0),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  effective_from timestamptz NOT NULL DEFAULT now(),
  effective_to timestamptz NULL,
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by varchar(128) NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by varchar(128) NULL,
  CONSTRAINT family_membership_plan_scope_ck CHECK (
    (scope_type = 'PLATFORM' AND tenant_id IS NULL) OR
    (scope_type = 'TENANT' AND tenant_id IS NOT NULL)
  ),
  CONSTRAINT family_membership_plan_attributes_ck CHECK (jsonb_typeof(attributes) = 'object'),
  CONSTRAINT family_membership_plan_effective_ck CHECK (effective_to IS NULL OR effective_to > effective_from)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_membership_platform_plan_version
  ON family_membership_plans(plan_ref, version_no) WHERE scope_type = 'PLATFORM';
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_membership_tenant_plan_version
  ON family_membership_plans(tenant_id, plan_ref, version_no) WHERE scope_type = 'TENANT';
CREATE INDEX IF NOT EXISTS idx_family_membership_plan_active
  ON family_membership_plans(scope_type, tenant_id, status, effective_from);

-- Catalogue master: tenant_id is applicable only for tenant-scoped plan definitions; no family/actor/subject fields.
CREATE TABLE IF NOT EXISTS family_membership_benefit_definitions (
  benefit_definition_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  plan_id uuid NOT NULL REFERENCES family_membership_plans(plan_id),
  tenant_id uuid NULL REFERENCES tenants(tenant_id),
  benefit_ref varchar(128) NOT NULL,
  version_no integer NOT NULL DEFAULT 1 CHECK (version_no > 0),
  title varchar(160) NOT NULL,
  allocation_type family_membership_allocation_type NOT NULL DEFAULT 'COUNT',
  units_per_grant integer NOT NULL DEFAULT 1 CHECK (units_per_grant >= 0),
  valid_days integer NULL CHECK (valid_days IS NULL OR valid_days > 0),
  status family_membership_plan_status NOT NULL DEFAULT 'ACTIVE',
  fixture_only boolean NOT NULL DEFAULT true CHECK (fixture_only = true),
  attributes_schema_version integer NOT NULL DEFAULT 1 CHECK (attributes_schema_version > 0),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  effective_from timestamptz NOT NULL DEFAULT now(),
  effective_to timestamptz NULL,
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by varchar(128) NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by varchar(128) NULL,
  CONSTRAINT family_membership_benefit_definition_attributes_ck CHECK (jsonb_typeof(attributes) = 'object'),
  CONSTRAINT family_membership_benefit_definition_effective_ck CHECK (effective_to IS NULL OR effective_to > effective_from),
  UNIQUE (plan_id, benefit_ref, version_no)
);
CREATE INDEX IF NOT EXISTS idx_family_membership_benefit_definition_active
  ON family_membership_benefit_definitions(plan_id, tenant_id, status, effective_from);

-- Family transaction fact. actor is mandatory server-derived; subject is optional for family-level plans.
CREATE TABLE IF NOT EXISTS family_membership_subscriptions (
  membership_subscription_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  actor_person_id uuid NOT NULL REFERENCES persons(person_id),
  subject_person_id uuid NULL REFERENCES persons(person_id),
  subscription_ref varchar(128) NOT NULL,
  plan_id uuid NOT NULL REFERENCES family_membership_plans(plan_id),
  plan_ref varchar(128) NOT NULL,
  plan_version integer NOT NULL CHECK (plan_version > 0),
  status family_membership_subscription_status NOT NULL DEFAULT 'PENDING',
  consent_ref varchar(160) NOT NULL,
  environment varchar(16) NOT NULL CHECK (environment IN ('DEV', 'TEST')),
  source_system varchar(32) NOT NULL DEFAULT 'TEST_NOOP_ADAPTER',
  external_effect boolean NOT NULL DEFAULT false CHECK (external_effect = false),
  attributes_schema_version integer NOT NULL DEFAULT 1 CHECK (attributes_schema_version > 0),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  effective_from timestamptz NOT NULL DEFAULT now(),
  effective_to timestamptz NULL,
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
  correlation_id varchar(128) NOT NULL,
  idempotency_key varchar(160) NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by varchar(128) NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by varchar(128) NOT NULL,
  cancelled_at timestamptz NULL,
  CONSTRAINT family_membership_subscription_attributes_ck CHECK (jsonb_typeof(attributes) = 'object'),
  CONSTRAINT family_membership_subscription_effective_ck CHECK (effective_to IS NULL OR effective_to > effective_from),
  CONSTRAINT family_membership_subscription_cancelled_ck CHECK ((status <> 'CANCELLED') OR cancelled_at IS NOT NULL),
  UNIQUE (tenant_id, family_id, subscription_ref)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_membership_subscription_idempotency
  ON family_membership_subscriptions(tenant_id, family_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_family_membership_subscription_scope
  ON family_membership_subscriptions(tenant_id, family_id, status, effective_from DESC);

-- Family transaction fact: each grant is tied to one subscription and one versioned benefit definition.
CREATE TABLE IF NOT EXISTS family_membership_benefit_grants (
  benefit_grant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  actor_person_id uuid NOT NULL REFERENCES persons(person_id),
  subject_person_id uuid NULL REFERENCES persons(person_id),
  membership_subscription_id uuid NOT NULL REFERENCES family_membership_subscriptions(membership_subscription_id),
  benefit_definition_id uuid NOT NULL REFERENCES family_membership_benefit_definitions(benefit_definition_id),
  benefit_ref varchar(128) NOT NULL,
  grant_ref varchar(128) NOT NULL,
  allocation_type family_membership_allocation_type NOT NULL,
  allocated_units integer NOT NULL CHECK (allocated_units >= 0),
  remaining_units integer NOT NULL CHECK (remaining_units >= 0 AND remaining_units <= allocated_units),
  status family_membership_benefit_status NOT NULL DEFAULT 'PENDING',
  environment varchar(16) NOT NULL CHECK (environment IN ('DEV', 'TEST')),
  source_system varchar(32) NOT NULL DEFAULT 'TEST_NOOP_ADAPTER',
  external_effect boolean NOT NULL DEFAULT false CHECK (external_effect = false),
  attributes_schema_version integer NOT NULL DEFAULT 1 CHECK (attributes_schema_version > 0),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  valid_from timestamptz NOT NULL DEFAULT now(),
  valid_to timestamptz NULL,
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
  correlation_id varchar(128) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by varchar(128) NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by varchar(128) NOT NULL,
  revoked_at timestamptz NULL,
  CONSTRAINT family_membership_benefit_grant_attributes_ck CHECK (jsonb_typeof(attributes) = 'object'),
  CONSTRAINT family_membership_benefit_grant_validity_ck CHECK (valid_to IS NULL OR valid_to > valid_from),
  CONSTRAINT family_membership_benefit_grant_revoked_ck CHECK ((status <> 'REVOKED') OR revoked_at IS NOT NULL),
  UNIQUE (tenant_id, family_id, grant_ref)
);
CREATE INDEX IF NOT EXISTS idx_family_membership_benefit_grant_scope
  ON family_membership_benefit_grants(tenant_id, family_id, status, valid_from DESC);

-- Append-only benefit fact ledger. actor is required; subject remains optional for family-level membership benefits.
CREATE TABLE IF NOT EXISTS family_membership_benefit_ledger (
  membership_benefit_ledger_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  actor_person_id uuid NOT NULL REFERENCES persons(person_id),
  subject_person_id uuid NULL REFERENCES persons(person_id),
  benefit_grant_id uuid NOT NULL REFERENCES family_membership_benefit_grants(benefit_grant_id),
  ledger_ref varchar(128) NOT NULL,
  action family_membership_benefit_action NOT NULL,
  units integer NOT NULL CHECK (units >= 0),
  remaining_units_after integer NOT NULL CHECK (remaining_units_after >= 0),
  source_page_id varchar(32) NOT NULL CHECK (source_page_id IN ('UI-30', 'UI-31', 'UI-32')),
  environment varchar(16) NOT NULL CHECK (environment IN ('DEV', 'TEST')),
  source_system varchar(32) NOT NULL DEFAULT 'TEST_NOOP_ADAPTER',
  external_effect boolean NOT NULL DEFAULT false CHECK (external_effect = false),
  attributes_schema_version integer NOT NULL DEFAULT 1 CHECK (attributes_schema_version > 0),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  correlation_id varchar(128) NOT NULL,
  idempotency_key varchar(160) NULL,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by varchar(128) NOT NULL,
  CONSTRAINT family_membership_benefit_ledger_attributes_ck CHECK (jsonb_typeof(attributes) = 'object'),
  UNIQUE (tenant_id, family_id, ledger_ref)
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_membership_benefit_ledger_idempotency
  ON family_membership_benefit_ledger(tenant_id, family_id, idempotency_key) WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_family_membership_benefit_ledger_scope
  ON family_membership_benefit_ledger(tenant_id, family_id, benefit_grant_id, occurred_at DESC);

CREATE OR REPLACE VIEW family_customer_membership_asset_projection_v AS
SELECT
  s.tenant_id,
  s.family_id,
  s.membership_subscription_id,
  s.subscription_ref,
  s.plan_ref,
  s.plan_version,
  s.status AS subscription_status,
  s.subject_person_id,
  s.effective_from,
  s.effective_to,
  s.row_version AS subscription_row_version,
  g.benefit_grant_id,
  g.benefit_ref,
  g.status AS benefit_status,
  g.allocated_units,
  g.remaining_units,
  g.valid_from,
  g.valid_to,
  g.row_version AS benefit_row_version,
  g.created_at AS benefit_created_at,
  g.updated_at AS benefit_updated_at
FROM family_membership_subscriptions s
LEFT JOIN family_membership_benefit_grants g
  ON g.membership_subscription_id = s.membership_subscription_id
  AND g.tenant_id = s.tenant_id
  AND g.family_id = s.family_id
  AND g.status = 'AVAILABLE'
  AND (g.valid_to IS NULL OR g.valid_to > now())
WHERE s.status = 'ACTIVE'
  AND s.effective_from <= now()
  AND (s.effective_to IS NULL OR s.effective_to > now());

COMMENT ON TABLE family_membership_plans IS 'Versioned PLATFORM/TENANT membership catalogue master. It never stores Family facts, payment or external subscription state.';
COMMENT ON TABLE family_membership_benefit_definitions IS 'Versioned plan-owned benefit catalogue master with schema-controlled extensibility.';
COMMENT ON TABLE family_membership_subscriptions IS 'Tenant/Family membership transaction fact. DEV/TEST no-op receipt only; no payment, renewal or notification.';
COMMENT ON TABLE family_membership_benefit_grants IS 'Tenant/Family benefit grant transaction fact. It is distinct from generic commerce entitlements.';
COMMENT ON TABLE family_membership_benefit_ledger IS 'Append-only benefit grant/consume/revoke ledger fact. It is never a client write target.';
COMMENT ON VIEW family_customer_membership_asset_projection_v IS 'Read-only Family-private current asset projection: ACTIVE subscriptions plus AVAILABLE non-expired benefits only; revoked/consumed history remains in base facts and append-only ledger.';
