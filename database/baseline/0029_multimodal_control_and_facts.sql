-- 0026_multimodal_control_and_facts
-- DEV/TEST controlled multimodal foundation.
-- Raw media, provider raw output and credentials are intentionally not persisted here.

DO $$ BEGIN
  CREATE TYPE multimodal_asset_status AS ENUM ('RECEIVED','QUARANTINED','PROCESSING','DERIVED','WITHDRAWN','DELETED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE multimodal_processing_status AS ENUM ('REQUESTED','BLOCKED','PROCESSING','SUCCEEDED','FAILED','WITHDRAWN');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE multimodal_visibility AS ENUM ('FAMILY_PRIVATE','TENANT_PRIVATE','PLATFORM_REVIEW_ONLY');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE multimodal_consent_status AS ENUM ('GRANTED','WITHDRAWN','EXPIRED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS multimodal_capability_profiles (
  capability_profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  capability_ref varchar(128) NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  modality varchar(32) NOT NULL CHECK (modality IN ('IMAGE','AUDIO','VIDEO','DOCUMENT','SCREENSHOT','OCR','ASR')),
  input_media_types jsonb NOT NULL DEFAULT '[]'::jsonb,
  max_size_bytes bigint NULL CHECK (max_size_bytes IS NULL OR max_size_bytes > 0),
  max_duration_ms bigint NULL CHECK (max_duration_ms IS NULL OR max_duration_ms > 0),
  supported_pages jsonb NOT NULL DEFAULT '[]'::jsonb,
  model_ref varchar(128) NULL,
  environment_allowlist jsonb NOT NULL DEFAULT '["DEV","TEST"]'::jsonb,
  risk_class varchar(32) NOT NULL DEFAULT 'LOW' CHECK (risk_class IN ('LOW','REVIEW','HIGH_RISK')),
  validator_ref varchar(128) NULL,
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','ACTIVE','HOLD','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (capability_ref, version)
);

CREATE TABLE IF NOT EXISTS multimodal_processing_policies (
  processing_policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  policy_ref varchar(128) NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  purpose varchar(64) NOT NULL,
  allowed_modalities jsonb NOT NULL DEFAULT '[]'::jsonb,
  required_consent_purpose varchar(128) NOT NULL,
  retention_seconds bigint NOT NULL CHECK (retention_seconds > 0),
  human_gate_required boolean NOT NULL DEFAULT false,
  allowed_state_upper_bound varchar(64) NOT NULL DEFAULT 'DERIVED_DRAFT_PRIVATE',
  external_effect varchar(16) NOT NULL DEFAULT 'NONE' CHECK (external_effect = 'NONE'),
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','ACTIVE','HOLD','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (policy_ref, version)
);

CREATE TABLE IF NOT EXISTS multimodal_output_schemas (
  output_schema_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  schema_ref varchar(128) NOT NULL,
  version integer NOT NULL CHECK (version > 0),
  allowed_fields jsonb NOT NULL DEFAULT '[]'::jsonb,
  forbidden_fields jsonb NOT NULL DEFAULT '["Need","Intent","Decision","Plan","Case","Outcome","GrowthProfile","diagnosis","risk_level","permanent_label"]'::jsonb,
  visibility multimodal_visibility NOT NULL DEFAULT 'FAMILY_PRIVATE',
  write_back_target varchar(64) NOT NULL DEFAULT 'DERIVED_ARTIFACT' CHECK (write_back_target = 'DERIVED_ARTIFACT'),
  validator_ref varchar(128) NOT NULL,
  text_equivalent_required boolean NOT NULL DEFAULT true,
  status varchar(24) NOT NULL CHECK (status IN ('DRAFT','ACTIVE','HOLD','RETIRED')),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (schema_ref, version)
);

CREATE TABLE IF NOT EXISTS multimodal_consents (
  multimodal_consent_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  purpose varchar(128) NOT NULL,
  scope jsonb NOT NULL DEFAULT '{}'::jsonb,
  granted_by_account_id uuid NOT NULL REFERENCES accounts(account_id),
  policy_ref varchar(128) NOT NULL,
  policy_version integer NOT NULL CHECK (policy_version > 0),
  status multimodal_consent_status NOT NULL DEFAULT 'GRANTED',
  granted_at timestamptz NOT NULL DEFAULT now(),
  withdrawn_at timestamptz NULL,
  expires_at timestamptz NULL,
  CONSTRAINT multimodal_consent_time CHECK (expires_at IS NULL OR expires_at > granted_at)
);
CREATE INDEX IF NOT EXISTS idx_multimodal_consents_scope
  ON multimodal_consents(tenant_id, family_id, purpose, status);

CREATE TABLE IF NOT EXISTS multimodal_assets (
  multimodal_asset_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  created_by_account_id uuid NOT NULL REFERENCES accounts(account_id),
  source_kind varchar(32) NOT NULL CHECK (source_kind IN ('GUARDIAN_UPLOAD','SCREENSHOT_VALIDATION','SYNTHETIC_FIXTURE')),
  media_type varchar(128) NOT NULL,
  content_hash varchar(128) NOT NULL,
  size_bytes bigint NOT NULL CHECK (size_bytes > 0),
  storage_ref varchar(512) NOT NULL,
  purpose varchar(128) NOT NULL,
  multimodal_consent_id uuid NOT NULL REFERENCES multimodal_consents(multimodal_consent_id),
  visibility multimodal_visibility NOT NULL DEFAULT 'FAMILY_PRIVATE',
  retention_until timestamptz NOT NULL,
  status multimodal_asset_status NOT NULL DEFAULT 'RECEIVED',
  created_at timestamptz NOT NULL DEFAULT now(),
  withdrawn_at timestamptz NULL,
  deleted_at timestamptz NULL,
  UNIQUE (tenant_id, family_id, content_hash, purpose)
);
CREATE INDEX IF NOT EXISTS idx_multimodal_assets_family
  ON multimodal_assets(tenant_id, family_id, status, purpose);

CREATE TABLE IF NOT EXISTS multimodal_processing_runs (
  processing_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  multimodal_asset_id uuid NOT NULL REFERENCES multimodal_assets(multimodal_asset_id),
  capability_ref varchar(128) NOT NULL,
  capability_version integer NOT NULL CHECK (capability_version > 0),
  policy_ref varchar(128) NOT NULL,
  policy_version integer NOT NULL CHECK (policy_version > 0),
  model_ref varchar(128) NULL,
  output_schema_ref varchar(128) NOT NULL,
  request_hash varchar(128) NOT NULL,
  status multimodal_processing_status NOT NULL DEFAULT 'REQUESTED',
  failure_code varchar(128) NULL,
  external_effect varchar(16) NOT NULL DEFAULT 'NONE' CHECK (external_effect = 'NONE'),
  started_at timestamptz NULL,
  completed_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (tenant_id, family_id, request_hash)
);
CREATE INDEX IF NOT EXISTS idx_multimodal_runs_asset
  ON multimodal_processing_runs(tenant_id, family_id, multimodal_asset_id, status);

CREATE TABLE IF NOT EXISTS multimodal_derived_artifacts (
  derived_artifact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  processing_run_id uuid NOT NULL REFERENCES multimodal_processing_runs(processing_run_id),
  asset_id uuid NOT NULL REFERENCES multimodal_assets(multimodal_asset_id),
  artifact_kind varchar(64) NOT NULL,
  artifact_schema_ref varchar(128) NOT NULL,
  payload_hash varchar(128) NOT NULL,
  visibility multimodal_visibility NOT NULL DEFAULT 'FAMILY_PRIVATE',
  state_upper_bound varchar(64) NOT NULL DEFAULT 'DERIVED_DRAFT_PRIVATE',
  human_review_status varchar(24) NOT NULL DEFAULT 'NOT_REQUIRED' CHECK (human_review_status IN ('NOT_REQUIRED','PENDING','APPROVED','REJECTED')),
  expires_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  withdrawn_at timestamptz NULL
);
CREATE INDEX IF NOT EXISTS idx_multimodal_artifacts_family
  ON multimodal_derived_artifacts(tenant_id, family_id, visibility, expires_at);

CREATE TABLE IF NOT EXISTS multimodal_audit_events (
  multimodal_audit_event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NULL REFERENCES tenants(tenant_id),
  family_id uuid NULL REFERENCES families(family_id),
  processing_run_id uuid NULL REFERENCES multimodal_processing_runs(processing_run_id),
  capability_ref varchar(128) NULL,
  policy_version integer NULL,
  schema_ref varchar(128) NULL,
  decision varchar(32) NOT NULL,
  block_code varchar(128) NULL,
  state_upper_bound varchar(64) NULL,
  correlation_id varchar(128) NOT NULL,
  input_hash varchar(128) NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_multimodal_audit_scope
  ON multimodal_audit_events(tenant_id, family_id, created_at);

COMMENT ON TABLE multimodal_capability_profiles IS 'Multimodal control master; no credentials or raw family data.';
COMMENT ON TABLE multimodal_processing_policies IS 'Purpose/consent/retention/risk policy; external effects are always NONE in this slice.';
COMMENT ON TABLE multimodal_output_schemas IS 'Validated output contract; write-back target is restricted to DERIVED_ARTIFACT.';
COMMENT ON TABLE multimodal_assets IS 'Family-scoped input metadata; raw object content is outside database and never in audit.';
COMMENT ON TABLE multimodal_processing_runs IS 'Processing fact with hashes and policy refs; no provider raw output or prompt.';
COMMENT ON TABLE multimodal_derived_artifacts IS 'Private derived draft; cannot become core ontology without explicit text-equivalent Named Action.';
COMMENT ON TABLE multimodal_audit_events IS 'Minimal multimodal governance audit; no raw media, prompt, provider response or API key.';
