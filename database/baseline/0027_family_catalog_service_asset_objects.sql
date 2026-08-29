-- 0024_family_catalog_service_asset_objects — Family 商城/服务/活动/社区/资产对象（DEV/TEST）
-- 只保存可追溯的测试候选与家庭私有投影；不保存真实支付金额、联系人、外发内容或生产供给。

CREATE TABLE IF NOT EXISTS family_admitted_catalog_items (
  catalog_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  item_ref varchar(128) NOT NULL,
  item_kind varchar(48) NOT NULL CHECK (item_kind IN ('PRODUCT','PRACTICE','COURSE','COMMUNITY_TEMPLATE')),
  title varchar(160) NOT NULL,
  version integer NOT NULL DEFAULT 1 CHECK (version > 0),
  admission_status varchar(24) NOT NULL CHECK (admission_status IN ('ADMITTED','EXPIRED')),
  evidence_level varchar(16) NOT NULL CHECK (evidence_level IN ('E1','E2','E3','UNVERIFIED')),
  source_ref varchar(160) NOT NULL,
  risk_flags text[] NOT NULL DEFAULT '{}',
  qualification_ref varchar(160) NULL,
  price_ref varchar(128) NULL,
  fixture_only boolean NOT NULL DEFAULT true CHECK (fixture_only = true),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(item_ref, version)
);
CREATE INDEX IF NOT EXISTS idx_family_catalog_item_kind ON family_admitted_catalog_items(item_kind, admission_status);

CREATE TABLE IF NOT EXISTS family_service_provider_catalog (
  provider_catalog_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  provider_ref varchar(128) NOT NULL UNIQUE,
  display_name varchar(160) NOT NULL,
  provider_kind varchar(48) NOT NULL CHECK (provider_kind IN ('TEACHER','SALON_HOST','SERVICE_TEAM')),
  qualification_ref varchar(160) NULL,
  qualification_status varchar(24) NOT NULL CHECK (qualification_status IN ('ACTIVE','MISSING','EXPIRED')),
  admission_status varchar(24) NOT NULL CHECK (admission_status IN ('ADMITTED','EXPIRED')),
  source_ref varchar(160) NOT NULL,
  fixture_only boolean NOT NULL DEFAULT true CHECK (fixture_only = true),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_family_provider_catalog_status ON family_service_provider_catalog(provider_kind, admission_status, qualification_status);

CREATE TABLE IF NOT EXISTS family_activity_catalog (
  activity_catalog_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  activity_ref varchar(128) NOT NULL UNIQUE,
  title varchar(160) NOT NULL,
  activity_kind varchar(48) NOT NULL CHECK (activity_kind IN ('SALON','WORKSHOP','FAMILY_EVENT')),
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NULL,
  admission_status varchar(24) NOT NULL CHECK (admission_status IN ('ADMITTED','EXPIRED')),
  qualification_ref varchar(160) NULL,
  source_ref varchar(160) NOT NULL,
  fixture_only boolean NOT NULL DEFAULT true CHECK (fixture_only = true),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_family_activity_catalog_status ON family_activity_catalog(admission_status, starts_at);

CREATE OR REPLACE VIEW family_customer_asset_projection AS
SELECT
  operation_id AS asset_id,
  family_id,
  page_id,
  operation_kind AS asset_kind,
  fixture_ref AS source_ref,
  fixture_version,
  status,
  environment,
  source,
  external_effect,
  created_at,
  cancelled_at
FROM test_experience_operations;
