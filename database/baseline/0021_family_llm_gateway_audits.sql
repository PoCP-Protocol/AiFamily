-- FAMILY_LLM_GATEWAY_001
-- Minimal, replay-safe audit metadata for real LLM calls with DEV/TEST fixtures.
-- Deliberately excludes API keys, authorization headers, prompts, responses,
-- implicit reasoning, full family profiles, and any free-form personal content.

CREATE TABLE IF NOT EXISTS family_llm_gateway_audits (
  audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  actor_person_id uuid NOT NULL REFERENCES persons(person_id),
  trace_id varchar(96) NOT NULL,
  environment varchar(8) NOT NULL CHECK (environment IN ('DEV', 'TEST')),
  use_case varchar(80) NOT NULL,
  fixture_id varchar(120) NOT NULL,
  fixture_version varchar(96) NOT NULL,
  page_id varchar(48) NOT NULL,
  model_id varchar(160) NULL,
  policy_version varchar(96) NOT NULL,
  schema_version varchar(96) NOT NULL,
  gateway_decision varchar(40) NOT NULL CHECK (gateway_decision IN ('ALLOW_DRAFT', 'BLOCK_INPUT', 'BLOCK_OUTPUT', 'BLOCK_CONFIGURATION', 'PROVIDER_FAILURE')),
  input_block_reason varchar(96) NULL,
  output_block_reason varchar(96) NULL,
  allowed_state_upper_bound varchar(48) NOT NULL,
  tool_names text[] NOT NULL DEFAULT '{}',
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_family_llm_audit_trace ON family_llm_gateway_audits(trace_id, created_at);
CREATE INDEX IF NOT EXISTS idx_family_llm_audit_family ON family_llm_gateway_audits(family_id, created_at DESC);
