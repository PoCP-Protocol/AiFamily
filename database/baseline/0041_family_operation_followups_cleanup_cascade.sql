-- Preserve isolated test/database cleanup semantics for derived operational metadata.
-- Follow-up entries have no independent lifecycle beyond their tenant/family scope.

ALTER TABLE family_operation_followups
  DROP CONSTRAINT IF EXISTS family_operation_followups_tenant_id_fkey;

ALTER TABLE family_operation_followups
  ADD CONSTRAINT family_operation_followups_tenant_id_fkey
  FOREIGN KEY (tenant_id) REFERENCES tenants(tenant_id) ON DELETE CASCADE;

ALTER TABLE family_operation_followups
  DROP CONSTRAINT IF EXISTS family_operation_followups_family_id_fkey;

ALTER TABLE family_operation_followups
  ADD CONSTRAINT family_operation_followups_family_id_fkey
  FOREIGN KEY (family_id) REFERENCES families(family_id) ON DELETE CASCADE;
