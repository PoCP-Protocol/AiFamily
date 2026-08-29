-- 0039_vs00_tenant_trusted_context
-- VS-00 trusted root: Account -> TenantMembership -> TenantFamilyBinding -> FamilyMembership -> Person.
-- Existing direct-customer data is backfilled into one explicit platform tenant; no Family ownership changes.

INSERT INTO tenants(tenant_ref, display_name, tenant_type, status, region_ref, plan_ref)
VALUES ('FAMILY_DIRECT', 'Family Direct Customer Tenant', 'DIRECT_CUSTOMER', 'ACTIVE', 'CN', 'FAMILY_DIRECT_V1')
ON CONFLICT (tenant_ref) DO UPDATE
SET display_name = EXCLUDED.display_name,
    status = 'ACTIVE',
    updated_at = now();

INSERT INTO tenant_family_bindings(tenant_id, family_id, status, effective_from, migration_ref)
SELECT
  t.tenant_id,
  f.family_id,
  'ACTIVE'::tenant_binding_status,
  now(),
  'VS00_0039_DIRECT_BACKFILL'
FROM tenants t
CROSS JOIN families f
WHERE t.tenant_ref = 'FAMILY_DIRECT'
  AND NOT EXISTS (
    SELECT 1 FROM tenant_family_bindings existing
    WHERE existing.family_id = f.family_id AND existing.status = 'ACTIVE'
  );

-- Bind every existing account to the tenant that actually owns its family. This
-- also preserves already-bound enterprise/sandbox families instead of forcing
-- their accounts into FAMILY_DIRECT.
INSERT INTO tenant_account_memberships(tenant_id, account_id, role, status, valid_from)
SELECT DISTINCT
  tfb.tenant_id,
  b.account_id,
  'TENANT_VIEWER'::tenant_membership_role,
  'ACTIVE'::tenant_membership_status,
  now()
FROM account_person_bindings b
JOIN family_memberships fm
  ON fm.person_id = b.person_id
 AND fm.status = 'ACTIVE'
JOIN tenant_family_bindings tfb
  ON tfb.family_id = fm.family_id
 AND tfb.status = 'ACTIVE'
 AND tfb.effective_from <= now()
 AND (tfb.effective_to IS NULL OR tfb.effective_to > now())
WHERE b.status = 'ACTIVE'
ON CONFLICT (tenant_id, account_id) DO NOTHING;

CREATE INDEX IF NOT EXISTS idx_tenant_context_account_family
  ON tenant_account_memberships(account_id, tenant_id, status);

COMMENT ON INDEX idx_tenant_context_account_family IS
  'VS-00 trusted context lookup: active Account membership inside Tenant before Family resolution.';
