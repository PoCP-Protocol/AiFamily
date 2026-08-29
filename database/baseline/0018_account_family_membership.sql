-- TENANCY-V2 T1(FAMILY-PLATFORM-TENANCY-FOUNDATION-001 Phase 1)
-- Account 域 + Account↔Person 绑定 + FamilyMembership。加表 + 回填;不改 persons/families/growth 语义。
-- 不变量:persons.family_id 保留(不 drop);family_memberships.family_id 必等于 persons.family_id。
-- CANONICAL_SEMANTIC_DELTA = 0(纯附加)。Account 不是 Family 数据 owner(TENANCY-001 INV-2)。

-- ---------- 枚举 ----------
DO $$ BEGIN
  CREATE TYPE account_status AS ENUM ('ACTIVE','DISABLED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE account_binding_status AS ENUM ('ACTIVE','REVOKED');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE family_role AS ENUM ('OWNER_GUARDIAN','GUARDIAN','ADULT_MEMBER','CHILD_SUBJECT');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN
  CREATE TYPE family_membership_status AS ENUM ('INVITED','ACTIVE','REVOKED','LEFT');
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

-- ---------- accounts ----------
-- 登录凭证主体(Account ≠ Person,TENANCY-001 INV-3)。external_ref 映射旧 persons.account_id(如 phone:139...)。
CREATE TABLE IF NOT EXISTS accounts (
  account_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  external_ref varchar(128) NULL UNIQUE,   -- 旧 persons.account_id 的规范化引用;可空(内部签发)
  status account_status NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- account_person_bindings ----------
-- 一个 Account 可绑定 0..N 个 family-scoped Person(不全局合并 Person)。
CREATE TABLE IF NOT EXISTS account_person_bindings (
  binding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  account_id uuid NOT NULL REFERENCES accounts(account_id),
  person_id uuid NOT NULL REFERENCES persons(person_id),
  status account_binding_status NOT NULL DEFAULT 'ACTIVE',
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz NULL,
  CONSTRAINT uq_account_person UNIQUE (account_id, person_id)
);
CREATE INDEX IF NOT EXISTS idx_apb_account ON account_person_bindings(account_id);
CREATE INDEX IF NOT EXISTS idx_apb_person ON account_person_bindings(person_id);

-- ---------- family_memberships ----------
-- Person 属于 Family 的成员关系 + 家庭内角色。Family 拥有数据(INV-1);角色仅在此边有效(INV-7)。
CREATE TABLE IF NOT EXISTS family_memberships (
  membership_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  family_id uuid NOT NULL REFERENCES families(family_id),
  person_id uuid NOT NULL REFERENCES persons(person_id),
  role family_role NOT NULL,
  status family_membership_status NOT NULL DEFAULT 'ACTIVE',
  invited_by_person_id uuid NULL REFERENCES persons(person_id),
  joined_at timestamptz NULL,
  revoked_at timestamptz NULL,
  left_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT uq_family_person UNIQUE (family_id, person_id)
);
CREATE INDEX IF NOT EXISTS idx_fm_family ON family_memberships(family_id);
CREATE INDEX IF NOT EXISTS idx_fm_person ON family_memberships(person_id);

-- ---------- 回填 accounts(从 persons.account_id 去重) ----------
INSERT INTO accounts (external_ref)
SELECT DISTINCT p.account_id
FROM persons p
WHERE p.account_id IS NOT NULL
  AND NOT EXISTS (SELECT 1 FROM accounts a WHERE a.external_ref = p.account_id);

-- ---------- 回填 account_person_bindings ----------
INSERT INTO account_person_bindings (account_id, person_id)
SELECT a.account_id, p.person_id
FROM persons p
JOIN accounts a ON a.external_ref = p.account_id
WHERE p.account_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM account_person_bindings b
    WHERE b.account_id = a.account_id AND b.person_id = p.person_id
  );

-- ---------- 回填 family_memberships(每个既有 person 一条) ----------
-- 角色:primary_contact → OWNER_GUARDIAN;其它 PARENT → GUARDIAN;CHILD → CHILD_SUBJECT。
INSERT INTO family_memberships (family_id, person_id, role, status, joined_at)
SELECT
  p.family_id,
  p.person_id,
  CASE
    WHEN p.person_type = 'CHILD' THEN 'CHILD_SUBJECT'::family_role
    WHEN f.primary_contact_person_id = p.person_id THEN 'OWNER_GUARDIAN'::family_role
    WHEN p.person_type = 'PARENT' THEN 'GUARDIAN'::family_role
    ELSE 'ADULT_MEMBER'::family_role
  END,
  'ACTIVE'::family_membership_status,
  p.created_at
FROM persons p
JOIN families f ON f.family_id = p.family_id
WHERE NOT EXISTS (
  SELECT 1 FROM family_memberships m
  WHERE m.family_id = p.family_id AND m.person_id = p.person_id
);
