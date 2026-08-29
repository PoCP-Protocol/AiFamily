-- 0014_principal_model_attempts — M3-INT-001 B1:Provider Attempt 账本
-- 一次逻辑 Run(principal_model_runs)可对应 0..N 次对具体 provider 的真实 attempt(含 failover/timeout)。
-- §25 外呼前先 STARTED 落库;§26 failover 每次都留痕。不存明文输入。幂等。
CREATE TABLE IF NOT EXISTS principal_model_attempts (
  attempt_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id varchar(128) NOT NULL,               -- 关联逻辑 Run(principal_model_runs.request_id)
  session_id uuid NULL REFERENCES principal_sessions(session_id) ON DELETE SET NULL,
  provider varchar(48) NOT NULL,                  -- provider_id(如 anthropic-cc-switch / zhipu-glm4v)
  model_name varchar(128) NULL,
  failover_sequence integer NOT NULL DEFAULT 0,   -- 0=primary,1=第一备…
  status varchar(16) NOT NULL DEFAULT 'STARTED',  -- STARTED | SUCCESS | FAILURE
  failure_kind varchar(32) NULL,                  -- TIMEOUT/NETWORK_ERROR/PROVIDER_4XX/5XX/INVALID_JSON/...
  latency_ms integer NULL,
  token_input integer NULL,
  token_output integer NULL,
  estimated_cost numeric(12,6) NULL,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_principal_attempts_request ON principal_model_attempts(request_id);
CREATE INDEX IF NOT EXISTS idx_principal_attempts_session ON principal_model_attempts(session_id, created_at DESC);
