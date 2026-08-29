-- Family commerce minimal slice: ProductOffering -> OrderIntent -> FamilyEntitlement.
-- DEV/TEST only: all receipts are explicitly no-op/sandbox facts; no payment, notification,
-- external order or production entitlement can be created by these tables.

DO $$ BEGIN
  CREATE TYPE family_product_scope AS ENUM ('PLATFORM','TENANT');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE family_product_status AS ENUM ('DRAFT','ACTIVE','SUSPENDED','RETIRED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE family_order_intent_status AS ENUM ('DRAFT','SUBMITTED','CANCELLED','EXPIRED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE family_entitlement_status AS ENUM ('PENDING','AVAILABLE','REVOKED','EXPIRED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS family_product_offerings (
  product_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scope_type family_product_scope NOT NULL DEFAULT 'PLATFORM',
  tenant_id uuid NULL REFERENCES tenants(tenant_id),
  product_ref varchar(128) NOT NULL,
  version_no integer NOT NULL DEFAULT 1 CHECK (version_no > 0),
  title varchar(160) NOT NULL,
  admission_status varchar(24) NOT NULL CHECK (admission_status IN ('ADMITTED','EXPIRED','SUSPENDED')),
  source_ref varchar(160) NOT NULL,
  price_plan_ref varchar(128) NULL,
  entitlement_policy_ref varchar(128) NULL,
  fixture_only boolean NOT NULL DEFAULT true CHECK (fixture_only = true),
  attributes_schema_version integer NOT NULL DEFAULT 1 CHECK (attributes_schema_version > 0),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  status family_product_status NOT NULL DEFAULT 'ACTIVE',
  effective_from timestamptz NOT NULL DEFAULT now(),
  effective_to timestamptz NULL,
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by varchar(128) NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by varchar(128) NULL,
  CONSTRAINT family_product_offering_scope_ck CHECK (
    (scope_type = 'PLATFORM' AND tenant_id IS NULL) OR
    (scope_type = 'TENANT' AND tenant_id IS NOT NULL)
  ),
  CONSTRAINT family_product_offering_effective_ck CHECK (effective_to IS NULL OR effective_to > effective_from),
  CONSTRAINT family_product_offering_attributes_ck CHECK (jsonb_typeof(attributes) = 'object')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_platform_product_version
  ON family_product_offerings(product_ref, version_no)
  WHERE scope_type = 'PLATFORM';
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_tenant_product_version
  ON family_product_offerings(tenant_id, product_ref, version_no)
  WHERE scope_type = 'TENANT';
CREATE INDEX IF NOT EXISTS idx_family_product_offering_active
  ON family_product_offerings(scope_type, tenant_id, status, admission_status, effective_from);

CREATE TABLE IF NOT EXISTS family_order_intents (
  order_intent_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  actor_person_id uuid NOT NULL REFERENCES persons(person_id),
  intent_ref varchar(128) NOT NULL,
  product_id uuid NOT NULL REFERENCES family_product_offerings(product_id),
  source_page_id varchar(32) NOT NULL CHECK (source_page_id IN ('UI-14','UI-17')),
  consent_ref varchar(160) NOT NULL,
  status family_order_intent_status NOT NULL DEFAULT 'DRAFT',
  catalog_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  attributes_schema_version integer NOT NULL DEFAULT 1 CHECK (attributes_schema_version > 0),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  environment varchar(16) NOT NULL CHECK (environment IN ('DEV','TEST')),
  source_system varchar(32) NOT NULL DEFAULT 'TEST_FIXTURE',
  external_effect boolean NOT NULL DEFAULT false CHECK (external_effect = false),
  correlation_id varchar(128) NOT NULL,
  idempotency_key varchar(160) NULL,
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
  retention_class varchar(48) NOT NULL DEFAULT 'COMMERCE_INTENT_TEST',
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by varchar(128) NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by varchar(128) NOT NULL,
  cancelled_at timestamptz NULL,
  expires_at timestamptz NULL,
  CONSTRAINT family_order_intent_attributes_ck CHECK (jsonb_typeof(attributes) = 'object'),
  CONSTRAINT family_order_intent_snapshot_ck CHECK (jsonb_typeof(catalog_snapshot) = 'object'),
  CONSTRAINT family_order_intent_cancelled_ck CHECK ((status <> 'CANCELLED') OR cancelled_at IS NOT NULL),
  CONSTRAINT family_order_intent_expiry_ck CHECK (expires_at IS NULL OR expires_at > created_at),
  UNIQUE (tenant_id, family_id, intent_ref)
);
CREATE INDEX IF NOT EXISTS idx_family_order_intents_scope
  ON family_order_intents(tenant_id, family_id, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_order_intent_idempotency
  ON family_order_intents(tenant_id, family_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS family_order_intent_lines (
  order_intent_line_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  order_intent_id uuid NOT NULL REFERENCES family_order_intents(order_intent_id) ON DELETE CASCADE,
  line_no integer NOT NULL CHECK (line_no > 0),
  product_id uuid NOT NULL REFERENCES family_product_offerings(product_id),
  product_ref varchar(128) NOT NULL,
  product_version integer NOT NULL CHECK (product_version > 0),
  status varchar(24) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','CANCELLED')),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT family_order_intent_line_attributes_ck CHECK (jsonb_typeof(attributes) = 'object'),
  UNIQUE (order_intent_id, line_no)
);
CREATE INDEX IF NOT EXISTS idx_family_order_intent_lines_scope
  ON family_order_intent_lines(tenant_id, family_id, order_intent_id);

CREATE TABLE IF NOT EXISTS family_entitlements (
  entitlement_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  source_order_intent_id uuid NOT NULL REFERENCES family_order_intents(order_intent_id),
  entitlement_ref varchar(128) NOT NULL,
  status family_entitlement_status NOT NULL DEFAULT 'PENDING',
  environment varchar(16) NOT NULL CHECK (environment IN ('DEV','TEST')),
  source_system varchar(32) NOT NULL DEFAULT 'TEST_NOOP_ADAPTER',
  external_effect boolean NOT NULL DEFAULT false CHECK (external_effect = false),
  attributes_schema_version integer NOT NULL DEFAULT 1 CHECK (attributes_schema_version > 0),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  available_at timestamptz NULL,
  expires_at timestamptz NULL,
  revoked_at timestamptz NULL,
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by varchar(128) NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by varchar(128) NOT NULL,
  CONSTRAINT family_entitlement_attributes_ck CHECK (jsonb_typeof(attributes) = 'object'),
  CONSTRAINT family_entitlement_available_ck CHECK ((status <> 'AVAILABLE') OR available_at IS NOT NULL),
  CONSTRAINT family_entitlement_expiry_ck CHECK (expires_at IS NULL OR expires_at > created_at),
  UNIQUE (tenant_id, family_id, entitlement_ref, source_order_intent_id)
);
CREATE INDEX IF NOT EXISTS idx_family_entitlements_scope
  ON family_entitlements(tenant_id, family_id, status, available_at DESC);

CREATE OR REPLACE VIEW family_customer_commerce_projection_v AS
SELECT
  e.tenant_id,
  e.family_id,
  e.entitlement_id AS asset_id,
  e.entitlement_ref AS asset_ref,
  e.status AS entitlement_status,
  e.source_order_intent_id,
  e.available_at,
  e.expires_at,
  e.environment,
  e.source_system,
  e.external_effect,
  e.created_at,
  e.updated_at
FROM family_entitlements e;

COMMENT ON TABLE family_product_offerings IS 'Versioned supply master. Stable core columns plus schema-controlled attributes; fixture_only remains true for DEV/TEST.';
COMMENT ON TABLE family_order_intents IS 'Family-scoped commercial intent fact. It never represents payment, external order, production enrollment or notification.';
COMMENT ON TABLE family_order_intent_lines IS 'Extensible intent line relation; prevents product arrays from being embedded in order intent JSON.';
COMMENT ON TABLE family_entitlements IS 'Family-scoped DEV/TEST no-op entitlement receipt. Distinct from an order intent and external production entitlement.';
COMMENT ON VIEW family_customer_commerce_projection_v IS 'Read-only customer asset projection over entitlement facts; never a write target.';
