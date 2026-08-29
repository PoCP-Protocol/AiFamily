-- TENANCY-V2 T2(FAMILY-PLATFORM-TENANCY-FOUNDATION-001 Phase 1 T2)
-- account-scoped session:token → account → available family contexts。
-- 附加迁移:person_id/family_id 改可空(支持零家庭 Account 会话;不 drop 旧字段),加 account_ref→accounts。
-- 现有会话不受影响(旧行 person_id/family_id 保留)。

-- 允许 account-scoped(尚未选家庭)会话
ALTER TABLE identity_sessions ALTER COLUMN person_id DROP NOT NULL;
ALTER TABLE identity_sessions ALTER COLUMN family_id DROP NOT NULL;

-- 关联到正式 Account 域(旧 account_id varchar 外部引用保留;新增 UUID FK)
ALTER TABLE identity_sessions ADD COLUMN IF NOT EXISTS account_ref uuid NULL REFERENCES accounts(account_id);
CREATE INDEX IF NOT EXISTS idx_sessions_account_ref ON identity_sessions(account_ref);
