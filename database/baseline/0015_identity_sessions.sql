-- 0015_identity_sessions — M3-W2 IAM-101:消费端真实身份会话令牌
-- 服务端不透明 Bearer 令牌(存 sha256,不存明文);令牌 → person(某 family 的成员)可信绑定。
-- 复用 persons.account_id 作外部账号引用。真实 OTP/微信验证器 = IAM-102。幂等。
CREATE TABLE IF NOT EXISTS identity_sessions (
  session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  token_hash varchar(128) NOT NULL UNIQUE,        -- sha256(opaque token);明文只在签发响应里出现一次
  person_id uuid NOT NULL REFERENCES persons(person_id),
  family_id uuid NOT NULL REFERENCES families(family_id),
  account_id varchar(128) NULL,                   -- 外部账号引用(手机号/微信 openid 等,IAM-102 落实)
  issued_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  revoked_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_identity_sessions_person ON identity_sessions(person_id);
CREATE INDEX IF NOT EXISTS idx_identity_sessions_active ON identity_sessions(token_hash) WHERE revoked_at IS NULL;
