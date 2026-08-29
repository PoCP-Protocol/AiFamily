-- 0022_test_experience_workflows — Family / 伐木累 34 页正式 DEV/TEST 体验工作流
-- 只处理 TEST_FIXTURE、DEV/TEST 环境与隔离外部副作用。禁止真实支付、真实预约、真实社区外发、自由文本或生产数据。

DO $$ BEGIN
  CREATE TYPE test_experience_operation_kind AS ENUM (
    'COMMERCE_INVITE',
    'COMMERCE_GROUP',
    'SERVICE_BOOKING',
    'EVENT_REGISTRATION',
    'COMMUNITY_TEMPLATE_PUBLICATION'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE test_experience_operation_status AS ENUM ('CREATED', 'CONFIRMED', 'CANCELLED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS test_experience_operations (
  operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  actor_person_id uuid NOT NULL REFERENCES persons(person_id),
  page_id varchar(16) NOT NULL,
  operation_kind test_experience_operation_kind NOT NULL,
  fixture_version varchar(96) NOT NULL,
  fixture_ref varchar(128) NOT NULL,
  channel varchar(48) NULL,
  status test_experience_operation_status NOT NULL DEFAULT 'CONFIRMED',
  environment varchar(16) NOT NULL CHECK (environment IN ('DEV', 'TEST')),
  source varchar(32) NOT NULL CHECK (source = 'TEST_FIXTURE'),
  correlation_id varchar(128) NOT NULL,
  idempotency_key varchar(160) NULL,
  external_effect boolean NOT NULL DEFAULT false CHECK (external_effect = false),
  created_at timestamptz NOT NULL DEFAULT now(),
  cancelled_at timestamptz NULL,
  CONSTRAINT test_experience_operation_environment_source CHECK (environment IN ('DEV', 'TEST') AND source = 'TEST_FIXTURE')
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_test_experience_operations_family_idempotency
  ON test_experience_operations(family_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_test_experience_operations_family_created
  ON test_experience_operations(family_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_test_experience_operations_family_kind
  ON test_experience_operations(family_id, operation_kind, status);

-- 客户后台只读投影直接从 test_experience_operations 派生；不建立真实订单、权益、联系人、消息或社区内容表。
