-- 0002_platform_foundation — 平台基础(FIX-01 重切)
-- 依赖:0001(families 供 audit_logs.family_id FK)。对象:audit_logs / outbox_events / idempotency_keys
-- 幂等:IF NOT EXISTS;可在单事务内执行。
CREATE TABLE IF NOT EXISTS audit_logs (
  audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NULL REFERENCES families(family_id),
  actor_type varchar(32) NOT NULL,
  actor_id varchar(128) NOT NULL,
  action_name varchar(128) NOT NULL,
  resource_type varchar(64) NOT NULL,
  resource_id varchar(128) NULL,
  correlation_id varchar(128) NOT NULL,
  idempotency_key varchar(128) NULL,
  result varchar(32) NOT NULL,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_audit_family_time ON audit_logs(family_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_corr ON audit_logs(correlation_id);

CREATE TABLE IF NOT EXISTS outbox_events (
  outbox_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  aggregate_type varchar(64) NOT NULL,
  aggregate_id varchar(128) NOT NULL,
  event_name varchar(128) NOT NULL,
  event_version integer NOT NULL,
  event_id uuid NOT NULL UNIQUE,
  correlation_id varchar(128) NOT NULL,
  payload jsonb NOT NULL,
  occurred_at timestamptz NOT NULL,
  published_at timestamptz NULL,
  retry_count integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_outbox_unpublished
ON outbox_events(created_at)
WHERE published_at IS NULL;

CREATE TABLE IF NOT EXISTS idempotency_keys (
  idempotency_key varchar(128) PRIMARY KEY,
  action_name varchar(128) NOT NULL,
  request_hash varchar(128) NOT NULL,
  response_code integer NULL,
  response_body jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NULL
);
