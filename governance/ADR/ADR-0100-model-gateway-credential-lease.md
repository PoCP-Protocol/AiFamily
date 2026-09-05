# ADR-0100：Model Gateway 凭据租约边界

## 状态

Accepted — 2026-08-30

## 决策

Model Gateway 增加 `ProviderCredentialPort` 与短期 `CredentialLease` 契约，并提供
`HttpProviderCredentialPort`、`SecretManagerCredentialPort` 与显式 HTTP 组合工厂。
`SecretManagerCredentialPort` 将 metadata resolver 与 secret reader 分离，先完成
provider-scoped 租约校验，再读取 secret，便于接入 KMS/Secret Manager 而不把供应商
SDK 带入领域层。模型适配器可以接收由外部
密钥服务签发的 provider-scoped、带过期时间凭据，但不得
持久化、记录或向领域层返回 secret。组合根通过显式注入 port 取得租约；测试可
注入合成实现，生产可接 mTLS/KMS/Secret Manager 实现。现有环境变量工厂保留为
兼容路径，真实生产接线必须提供外部 credential port，轮换/撤销由外部密钥服务
负责。

## 约束

- 未注册或未批准 provider 仍在读取凭据前被拒绝。
- lease 的 provider、环境由调用方绑定，过期、空值或 provider mismatch 一律
  fail-closed。
- Secret Manager 适配器必须先读取非敏感租约 metadata，再按 provider/environment
  解析 secret reference；metadata 不匹配或 secret reader 异常时不得继续 provider
  外呼，也不得在异常、repr 或运行记录中暴露 secret。
- 已撤销或已过期 metadata 必须在解析 secret reference 之前拒绝，避免无效租约
  触碰密钥存储。
- secret 不进入 provenance、attempt、telemetry、异常文本或治理 registry。
- 本 ADR 不声称已接入真实供应商、mTLS 或密钥服务；这些仍需部署验收证据。

## 证据

- `backend/intelligence/model_gateway/credentials.py`
- `backend/intelligence/model_gateway/composition.py`（含
  `build_secret_manager_openai_compatible_gateway_from_registry`）
- `backend/intelligence/model_gateway/providers/openai_compatible.py`
- `tests/intelligence/model_gateway/test_composition.py`
- `tests/intelligence/model_gateway/test_credentials.py`（metadata-first、provider
  mismatch、secret failure 与不泄露断言）
