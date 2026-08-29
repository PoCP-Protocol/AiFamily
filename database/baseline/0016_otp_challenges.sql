-- 0016_otp_challenges — M3-W2 IAM-102:OTP 验证挑战
-- 只存目的地/验证码的 sha256(不存明文手机号/验证码);服务端过期 + 尝试次数 + 限流。
-- 验证通过后经 AuthService 签发 identity_sessions 会话。真实短信投递为可插拔 sender(默认 stub;真实厂商需凭证=IAM-102 后续)。幂等。
CREATE TABLE IF NOT EXISTS otp_challenges (
  challenge_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  destination_hash varchar(128) NOT NULL,   -- sha256(手机号等目的地)
  code_hash varchar(128) NOT NULL,          -- sha256(destination + code)
  purpose varchar(32) NOT NULL DEFAULT 'LOGIN',
  attempts integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 5,
  expires_at timestamptz NOT NULL,
  consumed_at timestamptz NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_otp_dest_active ON otp_challenges(destination_hash, created_at DESC);
