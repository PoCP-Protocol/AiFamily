-- Family service booking minimal slice: ServiceProvider -> ServiceOffering -> AvailabilitySlot
-- -> BookingRequest -> BookingServiceRecord. DEV/TEST only, zero notification/external booking effects.

DO $$ BEGIN
  CREATE TYPE family_service_provider_status AS ENUM ('DRAFT','ACTIVE','SUSPENDED','RETIRED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE family_availability_slot_status AS ENUM ('AVAILABLE','RESERVED','BLOCKED','EXPIRED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE family_booking_request_status AS ENUM ('DRAFT','REQUESTED','CONFIRMED','CANCELLED','EXPIRED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE family_booking_record_status AS ENUM ('PENDING','SCHEDULED','CANCELLED','COMPLETED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS family_service_providers (
  provider_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  scope_type family_product_scope NOT NULL DEFAULT 'TENANT',
  tenant_id uuid NULL REFERENCES tenants(tenant_id),
  provider_ref varchar(128) NOT NULL,
  display_name varchar(160) NOT NULL,
  provider_kind varchar(48) NOT NULL CHECK (provider_kind IN ('TEACHER','SALON_HOST','SERVICE_TEAM')),
  qualification_ref varchar(160) NULL,
  qualification_status varchar(24) NOT NULL CHECK (qualification_status IN ('ACTIVE','MISSING','EXPIRED')),
  admission_status varchar(24) NOT NULL CHECK (admission_status IN ('ADMITTED','EXPIRED','SUSPENDED')),
  source_ref varchar(160) NOT NULL,
  fixture_only boolean NOT NULL DEFAULT true CHECK (fixture_only = true),
  attributes_schema_version integer NOT NULL DEFAULT 1 CHECK (attributes_schema_version > 0),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  status family_service_provider_status NOT NULL DEFAULT 'ACTIVE',
  effective_from timestamptz NOT NULL DEFAULT now(),
  effective_to timestamptz NULL,
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by varchar(128) NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by varchar(128) NULL,
  CONSTRAINT family_service_provider_scope_ck CHECK (
    (scope_type = 'PLATFORM' AND tenant_id IS NULL) OR
    (scope_type = 'TENANT' AND tenant_id IS NOT NULL)
  ),
  CONSTRAINT family_service_provider_effective_ck CHECK (effective_to IS NULL OR effective_to > effective_from),
  CONSTRAINT family_service_provider_attributes_ck CHECK (jsonb_typeof(attributes) = 'object')
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_platform_service_provider
  ON family_service_providers(provider_ref) WHERE scope_type='PLATFORM';
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_tenant_service_provider
  ON family_service_providers(tenant_id, provider_ref) WHERE scope_type='TENANT';

CREATE TABLE IF NOT EXISTS family_service_offerings (
  service_offering_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  provider_id uuid NOT NULL REFERENCES family_service_providers(provider_id),
  service_offering_ref varchar(128) NOT NULL,
  version_no integer NOT NULL DEFAULT 1 CHECK (version_no > 0),
  title varchar(160) NOT NULL,
  admission_status varchar(24) NOT NULL CHECK (admission_status IN ('ADMITTED','EXPIRED','SUSPENDED')),
  source_ref varchar(160) NOT NULL,
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
  CONSTRAINT family_service_offering_effective_ck CHECK (effective_to IS NULL OR effective_to > effective_from),
  CONSTRAINT family_service_offering_attributes_ck CHECK (jsonb_typeof(attributes) = 'object'),
  UNIQUE (tenant_id, service_offering_ref, version_no)
);
CREATE INDEX IF NOT EXISTS idx_family_service_offering_visible
  ON family_service_offerings(tenant_id, status, admission_status, effective_from);

CREATE TABLE IF NOT EXISTS family_service_availability_slots (
  availability_slot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  provider_id uuid NOT NULL REFERENCES family_service_providers(provider_id),
  service_offering_id uuid NOT NULL REFERENCES family_service_offerings(service_offering_id),
  availability_slot_ref varchar(128) NOT NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz NOT NULL,
  channel varchar(16) NOT NULL CHECK (channel IN ('VIDEO','TEXT','OFFLINE')),
  capacity integer NOT NULL DEFAULT 1 CHECK (capacity > 0),
  reserved_count integer NOT NULL DEFAULT 0 CHECK (reserved_count >= 0 AND reserved_count <= capacity),
  status family_availability_slot_status NOT NULL DEFAULT 'AVAILABLE',
  fixture_only boolean NOT NULL DEFAULT true CHECK (fixture_only = true),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT family_service_slot_window_ck CHECK (ends_at > starts_at),
  CONSTRAINT family_service_slot_attributes_ck CHECK (jsonb_typeof(attributes) = 'object'),
  UNIQUE (tenant_id, availability_slot_ref)
);
CREATE INDEX IF NOT EXISTS idx_family_service_slot_available
  ON family_service_availability_slots(tenant_id, service_offering_id, status, starts_at);

CREATE TABLE IF NOT EXISTS family_booking_requests (
  booking_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  actor_person_id uuid NOT NULL REFERENCES persons(person_id),
  booking_ref varchar(128) NOT NULL,
  service_offering_id uuid NOT NULL REFERENCES family_service_offerings(service_offering_id),
  availability_slot_id uuid NOT NULL REFERENCES family_service_availability_slots(availability_slot_id),
  source_page_id varchar(32) NOT NULL CHECK (source_page_id IN ('UI-19','UI-20','UI-21','UI-24')),
  consent_ref varchar(160) NOT NULL,
  status family_booking_request_status NOT NULL DEFAULT 'DRAFT',
  service_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  attributes_schema_version integer NOT NULL DEFAULT 1 CHECK (attributes_schema_version > 0),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  environment varchar(16) NOT NULL CHECK (environment IN ('DEV','TEST')),
  source_system varchar(32) NOT NULL DEFAULT 'TEST_FIXTURE',
  external_effect boolean NOT NULL DEFAULT false CHECK (external_effect = false),
  correlation_id varchar(128) NOT NULL,
  idempotency_key varchar(160) NULL,
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
  retention_class varchar(48) NOT NULL DEFAULT 'SERVICE_BOOKING_TEST',
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by varchar(128) NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by varchar(128) NOT NULL,
  cancelled_at timestamptz NULL,
  expires_at timestamptz NULL,
  CONSTRAINT family_booking_snapshot_ck CHECK (jsonb_typeof(service_snapshot) = 'object'),
  CONSTRAINT family_booking_attributes_ck CHECK (jsonb_typeof(attributes) = 'object'),
  CONSTRAINT family_booking_cancelled_ck CHECK ((status <> 'CANCELLED') OR cancelled_at IS NOT NULL),
  UNIQUE (tenant_id, family_id, booking_ref)
);
CREATE INDEX IF NOT EXISTS idx_family_booking_requests_scope
  ON family_booking_requests(tenant_id, family_id, status, created_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS uq_family_booking_idempotency
  ON family_booking_requests(tenant_id, family_id, idempotency_key)
  WHERE idempotency_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS family_booking_service_records (
  booking_service_record_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  source_booking_request_id uuid NOT NULL REFERENCES family_booking_requests(booking_request_id),
  status family_booking_record_status NOT NULL DEFAULT 'PENDING',
  environment varchar(16) NOT NULL CHECK (environment IN ('DEV','TEST')),
  source_system varchar(32) NOT NULL DEFAULT 'TEST_NOOP_ADAPTER',
  external_effect boolean NOT NULL DEFAULT false CHECK (external_effect = false),
  attributes_schema_version integer NOT NULL DEFAULT 1 CHECK (attributes_schema_version > 0),
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  row_version integer NOT NULL DEFAULT 1 CHECK (row_version > 0),
  created_at timestamptz NOT NULL DEFAULT now(),
  created_by varchar(128) NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by varchar(128) NOT NULL,
  CONSTRAINT family_booking_record_attributes_ck CHECK (jsonb_typeof(attributes) = 'object'),
  UNIQUE (tenant_id, family_id, source_booking_request_id)
);
CREATE INDEX IF NOT EXISTS idx_family_booking_service_record_scope
  ON family_booking_service_records(tenant_id, family_id, status, created_at DESC);

CREATE OR REPLACE VIEW family_customer_service_booking_projection_v AS
SELECT
  b.tenant_id,
  b.family_id,
  b.booking_request_id,
  b.booking_ref,
  b.status AS booking_status,
  o.service_offering_ref,
  s.availability_slot_ref,
  s.starts_at,
  s.ends_at,
  s.channel,
  r.booking_service_record_id,
  r.status AS service_record_status,
  b.environment,
  b.source_system,
  b.external_effect,
  b.created_at,
  b.updated_at
FROM family_booking_requests b
JOIN family_service_offerings o ON o.service_offering_id=b.service_offering_id
JOIN family_service_availability_slots s ON s.availability_slot_id=b.availability_slot_id
LEFT JOIN family_booking_service_records r ON r.source_booking_request_id=b.booking_request_id;

COMMENT ON TABLE family_service_providers IS 'Versioned service-provider supply master; not a family booking fact.';
COMMENT ON TABLE family_service_offerings IS 'Versioned admitted service supply master bound to one qualified provider and tenant scope.';
COMMENT ON TABLE family_service_availability_slots IS 'Versioned fixture-only availability inventory. It does not send calendar notifications.';
COMMENT ON TABLE family_booking_requests IS 'Family-scoped booking intent; it is not a confirmed real-world appointment.';
COMMENT ON TABLE family_booking_service_records IS 'DEV/TEST no-op service record receipt derived from a booking request.';
COMMENT ON VIEW family_customer_service_booking_projection_v IS 'Read-only family service booking projection; never a write target.';
