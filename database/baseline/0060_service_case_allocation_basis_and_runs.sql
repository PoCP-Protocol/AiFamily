-- 0056_service_case_allocation_basis_and_runs
-- FAMILY-SERVICE-COLLAB-ALLOCATION-P0-002-C:
--   1) case-level allocation basis (PLATFORM / QUALITY_RESERVE) no longer borrows a
--      VERIFIED contribution row as its foreign key basis; contribution_ref becomes
--      optional and basis_type/basis_ref carry the real semantics.
--   2) a dedicated allocation-run table records which policy snapshot produced a
--      case's allocation batch (previously only implied by two columns on service_cases).
--   3) allocation_bucket is unified onto CASE_STEWARD; the legacy STEWARD bucket value
--      is backfilled and then removed from the allowed set.
--   4) basis_type / beneficiary_kind become bounded enums instead of free text.
--   5) a database-level trigger enforces the 100-unit case ceiling independently of
--      the application-layer sum, so the constraint holds even if a future write path
--      bypasses OrchestrationService.

-- --- unify legacy STEWARD bucket into CASE_STEWARD before tightening the CHECK ---
UPDATE service_contribution_allocations SET allocation_bucket = 'CASE_STEWARD' WHERE allocation_bucket = 'STEWARD';

ALTER TABLE service_contribution_allocations
  DROP CONSTRAINT IF EXISTS service_contribution_allocations_allocation_bucket_check;
ALTER TABLE service_contribution_allocations
  ADD CONSTRAINT service_contribution_allocations_allocation_bucket_check
  CHECK (allocation_bucket IN ('PLATFORM','CONTENT_RESOURCE','CASE_STEWARD','DELIVERY_RESOURCE','QUALITY_RESERVE'));

-- --- contribution_ref is no longer a mandatory borrowed basis for case-level buckets ---
ALTER TABLE service_contribution_allocations ALTER COLUMN contribution_ref DROP NOT NULL;
ALTER TABLE service_contribution_allocations
  DROP CONSTRAINT IF EXISTS service_contribution_allocations_contribution_ref_allocation_bucket_key;

-- --- bounded enums for basis_type / beneficiary_kind (previously unchecked free text) ---
ALTER TABLE service_contribution_allocations
  DROP CONSTRAINT IF EXISTS service_contribution_allocations_basis_type_check;
ALTER TABLE service_contribution_allocations
  ADD CONSTRAINT service_contribution_allocations_basis_type_check
  CHECK (basis_type IS NULL OR basis_type IN ('CASE','CONTRIBUTION','CONTRIBUTION_WEIGHT'));

ALTER TABLE service_contribution_allocations
  DROP CONSTRAINT IF EXISTS service_contribution_allocations_beneficiary_kind_check;
ALTER TABLE service_contribution_allocations
  ADD CONSTRAINT service_contribution_allocations_beneficiary_kind_check
  CHECK (beneficiary_kind IS NULL OR beneficiary_kind IN ('PLATFORM','INTERNAL_ACTOR','ADMITTED_PROVIDER'));

ALTER TABLE service_contribution_allocations
  ADD CONSTRAINT service_contribution_allocations_basis_ref_required
  CHECK (basis_type IS NULL OR (basis_ref IS NOT NULL AND length(basis_ref) > 0));

-- case-level buckets (basis_type='CASE') must not borrow a contribution as their basis;
-- contribution-level buckets (basis_type='CONTRIBUTION'/'CONTRIBUTION_WEIGHT') must carry one.
ALTER TABLE service_contribution_allocations
  ADD CONSTRAINT service_contribution_allocations_case_basis_has_no_contribution
  CHECK (basis_type IS DISTINCT FROM 'CASE' OR contribution_ref IS NULL);
ALTER TABLE service_contribution_allocations
  ADD CONSTRAINT service_contribution_allocations_contribution_basis_requires_contribution
  CHECK (basis_type NOT IN ('CONTRIBUTION','CONTRIBUTION_WEIGHT') OR contribution_ref IS NOT NULL);

-- --- allocation run: one record per finalize, carrying the policy snapshot used ---
CREATE TABLE IF NOT EXISTS service_case_allocation_runs (
  allocation_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  case_ref uuid NOT NULL REFERENCES service_cases(case_id),
  policy_ref varchar(160) NOT NULL,
  policy_version integer NOT NULL,
  triggered_by_actor_ref varchar(128) NOT NULL,
  total_units numeric(12,2) NOT NULL CHECK (total_units >= 0 AND total_units <= 100),
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (case_ref)
);
COMMENT ON TABLE service_case_allocation_runs IS 'One row per case finalize; records the policy snapshot and total that produced the allocation batch. No payment/settlement semantics.';

ALTER TABLE service_contribution_allocations
  ADD COLUMN IF NOT EXISTS allocation_run_ref uuid NULL REFERENCES service_case_allocation_runs(allocation_run_id);
CREATE INDEX IF NOT EXISTS idx_contribution_allocations_run ON service_contribution_allocations(allocation_run_ref);

-- --- database-level defense-in-depth: no case's allocation rows may ever sum past 100 ---
CREATE OR REPLACE FUNCTION enforce_case_allocation_total_ceiling() RETURNS trigger AS $$
DECLARE
  total numeric(12,2);
BEGIN
  SELECT coalesce(sum(units), 0) INTO total
    FROM service_contribution_allocations
   WHERE case_ref = NEW.case_ref;
  IF total > 100.0001 THEN
    RAISE EXCEPTION 'case_allocation_total_exceeds_100: case_ref=%, total=%', NEW.case_ref, total
      USING ERRCODE = '23514';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_enforce_case_allocation_total_ceiling ON service_contribution_allocations;
CREATE CONSTRAINT TRIGGER trg_enforce_case_allocation_total_ceiling
  AFTER INSERT OR UPDATE ON service_contribution_allocations
  FOR EACH ROW EXECUTE FUNCTION enforce_case_allocation_total_ceiling();
