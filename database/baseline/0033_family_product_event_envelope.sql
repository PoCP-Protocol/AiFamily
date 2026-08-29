-- 0030_family_product_event_envelope
-- Product interaction facts for Family's bounded product loop.
-- This is not GrowthEvent, not an outcome, not a recommendation feature store.

CREATE TABLE IF NOT EXISTS family_product_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NULL REFERENCES families(family_id),
  actor_id varchar(128) NULL,
  event_type varchar(96) NOT NULL,
  object_type varchar(96) NOT NULL,
  object_id varchar(128) NULL,
  source_page_id varchar(32) NULL,
  purpose varchar(64) NOT NULL,
  consent_ref varchar(128) NULL,
  correlation_id varchar(128) NOT NULL,
  schema_version integer NOT NULL DEFAULT 1 CHECK (schema_version > 0),
  retention_class varchar(48) NOT NULL DEFAULT 'PRODUCT_EVENT_MINIMAL',
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  occurred_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by varchar(128) NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by varchar(128) NULL,
  CONSTRAINT family_product_events_family_scope_ck CHECK (
    (family_id IS NULL AND actor_id IS NULL AND consent_ref IS NULL)
    OR family_id IS NOT NULL
  ),
  CONSTRAINT family_product_events_payload_object_ck CHECK (jsonb_typeof(payload) = 'object')
);

CREATE INDEX IF NOT EXISTS idx_family_product_events_tenant_time
  ON family_product_events(tenant_id, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_family_product_events_family_time
  ON family_product_events(tenant_id, family_id, occurred_at DESC)
  WHERE family_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_family_product_events_object
  ON family_product_events(tenant_id, object_type, object_id, occurred_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_product_events_correlation_type_object
  ON family_product_events(tenant_id, correlation_id, event_type, object_type, COALESCE(object_id, ''));

COMMENT ON TABLE family_product_events IS 'Append-only Family product interaction events; not canonical growth outcomes, not cross-family profiles, no raw prompts or secrets.';
COMMENT ON COLUMN family_product_events.payload IS 'Minimal structured metadata only; raw conversation, raw media, credentials and provider output are forbidden.';
