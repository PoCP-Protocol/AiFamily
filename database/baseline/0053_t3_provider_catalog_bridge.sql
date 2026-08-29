-- TENANCY-T3-PATCH-3: bridge legacy fixture supply to ProviderProfile.
-- Existing UI-19 contracts remain compatible; fixture-only constraints remain enforced.

ALTER TABLE family_service_providers
  ADD COLUMN IF NOT EXISTS provider_profile_id uuid NULL REFERENCES provider_profiles(provider_profile_id);

ALTER TABLE family_service_offerings
  ADD COLUMN IF NOT EXISTS owner_tenant_id uuid NULL REFERENCES tenants(tenant_id);

CREATE OR REPLACE FUNCTION set_family_service_offering_owner_tenant()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.owner_tenant_id IS NULL THEN
    NEW.owner_tenant_id := NEW.tenant_id;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_set_family_service_offering_owner_tenant ON family_service_offerings;
CREATE TRIGGER trg_set_family_service_offering_owner_tenant
  BEFORE INSERT OR UPDATE ON family_service_offerings
  FOR EACH ROW EXECUTE FUNCTION set_family_service_offering_owner_tenant();

UPDATE family_service_offerings
   SET owner_tenant_id = tenant_id
 WHERE owner_tenant_id IS NULL;

DO $$
DECLARE
  provider_row record;
  party_row uuid;
  profile_row uuid;
BEGIN
  FOR provider_row IN
    SELECT provider_id, provider_ref, display_name, provider_kind
      FROM family_service_providers
     WHERE provider_profile_id IS NULL
  LOOP
    INSERT INTO parties(party_kind, display_name)
      VALUES ('INDIVIDUAL', provider_row.display_name)
      RETURNING party_id INTO party_row;

    IF provider_row.provider_kind = 'TEACHER' THEN
      INSERT INTO individual_parties(party_id) VALUES (party_row);
      INSERT INTO teacher_profiles(party_id, teacher_ref, public_display_name, status)
        VALUES (party_row, provider_row.provider_ref, provider_row.display_name, 'ADMITTED')
        ON CONFLICT (teacher_ref) DO UPDATE SET updated_at=now()
        RETURNING teacher_profile_id INTO profile_row;
    ELSE
      INSERT INTO provider_profiles(owner_party_id, provider_kind, provider_ref, display_name, status)
        VALUES (party_row, 'INDIVIDUAL', provider_row.provider_ref, provider_row.display_name, 'ACTIVE')
        ON CONFLICT (provider_ref) DO UPDATE SET updated_at=now()
        RETURNING provider_profile_id INTO profile_row;
    END IF;

    IF provider_row.provider_kind = 'TEACHER' THEN
      INSERT INTO provider_profiles(owner_party_id, provider_kind, provider_ref, display_name, status)
        VALUES (party_row, 'INDIVIDUAL', provider_row.provider_ref, provider_row.display_name, 'ACTIVE')
        ON CONFLICT (provider_ref) DO UPDATE SET updated_at=now()
        RETURNING provider_profile_id INTO profile_row;
    END IF;

    UPDATE family_service_providers
       SET provider_profile_id=profile_row, updated_at=now()
     WHERE provider_id=provider_row.provider_id;
  END LOOP;
END $$;

CREATE INDEX IF NOT EXISTS idx_family_service_provider_profile
  ON family_service_providers(provider_profile_id, tenant_id, status);

CREATE OR REPLACE FUNCTION bridge_family_service_provider_to_profile()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
  party_row uuid;
  profile_row uuid;
BEGIN
  IF NEW.provider_profile_id IS NOT NULL THEN
    RETURN NEW;
  END IF;

  INSERT INTO parties(party_kind, display_name)
    VALUES ('INDIVIDUAL', NEW.display_name)
    RETURNING party_id INTO party_row;
  INSERT INTO individual_parties(party_id) VALUES (party_row);
  INSERT INTO provider_profiles(owner_party_id, provider_kind, provider_ref, display_name, status)
    VALUES (party_row, 'INDIVIDUAL', NEW.provider_ref, NEW.display_name, 'ACTIVE')
    ON CONFLICT (provider_ref) DO UPDATE SET updated_at=now()
    RETURNING provider_profile_id INTO profile_row;

  IF NEW.provider_kind = 'TEACHER' THEN
    INSERT INTO teacher_profiles(party_id, teacher_ref, public_display_name, status)
      VALUES (party_row, NEW.provider_ref, NEW.display_name, 'ADMITTED')
      ON CONFLICT (teacher_ref) DO UPDATE SET updated_at=now();
  END IF;

  NEW.provider_profile_id := profile_row;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_bridge_family_service_provider_to_profile ON family_service_providers;
CREATE TRIGGER trg_bridge_family_service_provider_to_profile
  BEFORE INSERT ON family_service_providers
  FOR EACH ROW EXECUTE FUNCTION bridge_family_service_provider_to_profile();

CREATE OR REPLACE FUNCTION bridge_family_service_provider_admission()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.provider_profile_id IS NOT NULL AND NEW.tenant_id IS NOT NULL THEN
    INSERT INTO provider_admissions(provider_profile_id, tenant_id, status, admission_ref)
      VALUES (NEW.provider_profile_id, NEW.tenant_id, 'ADMITTED', 'LEGACY_FIXTURE_' || NEW.provider_ref)
      ON CONFLICT (provider_profile_id, tenant_id, admission_ref) DO NOTHING;
  END IF;
  RETURN NEW;
END $$;

DROP TRIGGER IF EXISTS trg_bridge_family_service_provider_admission ON family_service_providers;
CREATE TRIGGER trg_bridge_family_service_provider_admission
  AFTER INSERT OR UPDATE OF provider_profile_id ON family_service_providers
  FOR EACH ROW EXECUTE FUNCTION bridge_family_service_provider_admission();

CREATE TABLE IF NOT EXISTS family_marketplace_listings (
  marketplace_listing_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  channel_tenant_id uuid NOT NULL REFERENCES tenants(tenant_id),
  provider_profile_id uuid NOT NULL REFERENCES provider_profiles(provider_profile_id),
  service_offering_id uuid NOT NULL REFERENCES family_service_offerings(service_offering_id),
  visibility varchar(24) NOT NULL DEFAULT 'VISIBLE' CHECK (visibility IN ('VISIBLE','HIDDEN','SUSPENDED')),
  admission_ref varchar(128) NULL,
  fixture_only boolean NOT NULL DEFAULT true CHECK (fixture_only = true),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (channel_tenant_id, service_offering_id)
);

COMMENT ON COLUMN family_service_providers.provider_profile_id IS 'Bridge to canonical ProviderProfile; legacy fixture rows remain query-compatible.';
COMMENT ON COLUMN family_service_offerings.owner_tenant_id IS 'Selling/owning tenant; channel and actual teacher are separate concepts.';
COMMENT ON TABLE family_marketplace_listings IS 'Tenant-scoped fixture marketplace projection; no payment or external effect.';
