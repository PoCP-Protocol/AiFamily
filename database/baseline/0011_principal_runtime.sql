-- 0011_principal_runtime — M3-101A-B Principal 域持久化(L3,隔离于 Family/Growth canonical)
-- 依赖:0001(families)。principal_* 与 product_events 均为 Principal/产品域,非 canonical truth/state。
-- 不得用 Growth canonical 表存 Principal 内容;这些表不参与 Growth Named Action。幂等 + 单事务可执行。

CREATE TABLE IF NOT EXISTS principal_sessions (
  session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_ref varchar(128) NOT NULL,
  actor_id varchar(128) NOT NULL,
  status varchar(16) NOT NULL DEFAULT 'OPEN',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_principal_sessions_family ON principal_sessions(family_id, created_at DESC);

CREATE TABLE IF NOT EXISTS principal_messages (
  message_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES principal_sessions(session_id) ON DELETE CASCADE,
  family_id uuid NOT NULL REFERENCES families(family_id),
  sender varchar(16) NOT NULL,            -- USER | PRINCIPAL
  body text NOT NULL,                      -- L3;最小化/脱敏为代码职责,不进 canonical
  correlation_id varchar(128) NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_principal_messages_session ON principal_messages(session_id, created_at);

CREATE TABLE IF NOT EXISTS principal_responses (
  response_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES principal_sessions(session_id) ON DELETE CASCADE,
  family_id uuid NOT NULL REFERENCES families(family_id),
  risk_route varchar(16) NOT NULL,         -- NORMAL | REVIEW | HIGH_RISK
  schema_valid boolean NOT NULL,
  output jsonb NOT NULL DEFAULT '{}'::jsonb, -- 结构化输出(非 canonical fact)
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_principal_responses_session ON principal_responses(session_id, created_at);

CREATE TABLE IF NOT EXISTS principal_action_proposals (
  proposal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  response_id uuid NOT NULL REFERENCES principal_responses(response_id) ON DELETE CASCADE,
  session_id uuid NOT NULL REFERENCES principal_sessions(session_id) ON DELETE CASCADE,
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_ref varchar(128) NOT NULL,
  proposal_type varchar(64) NOT NULL,
  recommended_intervention_id varchar(64) NOT NULL,  -- 只指既有已批准 Intervention(如 LISTEN_BEFORE_RESPOND)
  display_title varchar(200) NOT NULL,
  display_instruction text NOT NULL,
  rationale text NULL,
  risk_route varchar(16) NOT NULL,
  canonical boolean NOT NULL DEFAULT false CHECK (canonical = false), -- 硬约束:proposal 永远非 canonical
  status varchar(16) NOT NULL DEFAULT 'PROPOSED',
  expires_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_principal_proposals_session ON principal_action_proposals(session_id, created_at);

CREATE TABLE IF NOT EXISTS principal_feedback (
  feedback_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  response_id uuid NOT NULL REFERENCES principal_responses(response_id) ON DELETE CASCADE,
  family_id uuid NOT NULL REFERENCES families(family_id),
  actor_id varchar(128) NOT NULL,
  rating varchar(16) NULL,
  note text NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS principal_model_runs (
  model_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  request_id varchar(128) NOT NULL,
  session_id uuid NULL REFERENCES principal_sessions(session_id) ON DELETE SET NULL,
  family_id_ref uuid NULL,                 -- 引用,非 FK 拷贝;不内联 FamilyAggregate
  model_provider varchar(32) NOT NULL,     -- fake(101A);external 未授权
  model_name varchar(128) NULL,
  model_version varchar(64) NULL,
  prompt_version varchar(64) NULL,
  soul_version varchar(64) NULL,
  soul_hash varchar(128) NULL,
  scenario_id varchar(64) NULL,
  method_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  source_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  input_hash varchar(128) NULL,            -- 默认存 hash,非明文
  output_hash varchar(128) NULL,
  risk_route varchar(16) NULL,
  schema_validation varchar(16) NULL,      -- valid | invalid
  latency_ms integer NULL,
  token_usage jsonb NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_principal_model_runs_session ON principal_model_runs(session_id, created_at DESC);

CREATE TABLE IF NOT EXISTS principal_human_handoffs (
  handoff_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  session_id uuid NOT NULL REFERENCES principal_sessions(session_id) ON DELETE CASCADE,
  family_id uuid NOT NULL REFERENCES families(family_id),
  subject_ref varchar(128) NOT NULL,
  risk_route varchar(16) NOT NULL,         -- HIGH_RISK | REVIEW
  trigger_reason varchar(64) NOT NULL,     -- precheck | postcheck | scenario
  status varchar(16) NOT NULL DEFAULT 'OPEN',
  assigned_role varchar(64) NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- 产品事件(append-only);principal_action_proposal_accepted 等属 ProductEvent,≠ GrowthEvent
CREATE TABLE IF NOT EXISTS product_events (
  product_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_name varchar(128) NOT NULL,
  family_id uuid NULL REFERENCES families(family_id),
  session_id uuid NULL,
  correlation_id varchar(128) NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_product_events_name_time ON product_events(event_name, occurred_at DESC);
