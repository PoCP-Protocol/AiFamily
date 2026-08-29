-- TENANCY-T3-PATCH-4: ServiceRelationship / CaseAccessGrant.
-- Family remains the data owner. A relationship never implies case access.

CREATE TABLE IF NOT EXISTS service_relationships (
  service_relationship_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  counterparty_party_id uuid NOT NULL REFERENCES parties(party_id),
  provider_profile_id uuid NULL REFERENCES provider_profiles(provider_profile_id),
  purpose varchar(80) NOT NULL CHECK (purpose IN ('SERVICE_DELIVERY','EDUCATION_SUPPORT','ASSESSMENT_SUPPORT')),
  status varchar(24) NOT NULL DEFAULT 'ACTIVE' CHECK (status IN ('PENDING','ACTIVE','SUSPENDED','TERMINATED','EXPIRED')),
  effective_from timestamptz NOT NULL DEFAULT now(),
  effective_to timestamptz NULL,
  terminated_at timestamptz NULL,
  created_by_person_id uuid NULL REFERENCES persons(person_id),
  correlation_id varchar(128) NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT service_relationship_time CHECK (effective_to IS NULL OR effective_to > effective_from),
  CONSTRAINT service_relationship_termination CHECK (terminated_at IS NULL OR status = 'TERMINATED')
);
CREATE INDEX IF NOT EXISTS idx_service_relationship_family_active
  ON service_relationships(family_id, tenant_id, status, effective_from);
CREATE INDEX IF NOT EXISTS idx_service_relationship_counterparty
  ON service_relationships(counterparty_party_id, status, effective_from);

CREATE TABLE IF NOT EXISTS case_access_grants (
  case_access_grant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  service_case_id uuid NOT NULL REFERENCES service_cases(case_id),
  service_relationship_id uuid NOT NULL REFERENCES service_relationships(service_relationship_id),
  grantee_party_id uuid NOT NULL REFERENCES parties(party_id),
  scope jsonb NOT NULL CHECK (jsonb_typeof(scope) = 'object'),
  purpose varchar(80) NOT NULL CHECK (purpose IN ('SERVICE_DELIVERY','EDUCATION_SUPPORT','ASSESSMENT_SUPPORT')),
  consent_snapshot_ref varchar(160) NOT NULL,
  effective_from timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NULL,
  revoked_at timestamptz NULL,
  risk_level varchar(16) NOT NULL DEFAULT 'STANDARD' CHECK (risk_level IN ('STANDARD','ELEVATED','HIGH')),
  human_gate_ref varchar(160) NULL,
  created_by_person_id uuid NULL REFERENCES persons(person_id),
  correlation_id varchar(128) NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT case_access_grant_time CHECK (expires_at IS NULL OR expires_at > effective_from),
  CONSTRAINT case_access_grant_revoke_time CHECK (revoked_at IS NULL OR revoked_at >= effective_from),
  UNIQUE (service_case_id, grantee_party_id, purpose, effective_from)
);
CREATE INDEX IF NOT EXISTS idx_case_access_grants_active
  ON case_access_grants(service_case_id, family_id, grantee_party_id, effective_from)
  WHERE revoked_at IS NULL;

COMMENT ON TABLE service_relationships IS 'Family service relationship; never grants data access by itself.';
COMMENT ON TABLE case_access_grants IS 'Least-privilege, case-scoped access; default deny and revocable.';
