-- TENANCY-T3-PHASE-A: Account -> Party binding for granted Case read runtime.
-- This migration does not grant access; CaseAccessGrant remains mandatory.

CREATE INDEX IF NOT EXISTS idx_account_party_binding_runtime
  ON account_party_bindings(account_id, party_id, status, valid_from)
  WHERE status='ACTIVE';

COMMENT ON TABLE account_party_bindings IS 'Account to Party identity binding; never bypasses CaseAccessGrant.';
