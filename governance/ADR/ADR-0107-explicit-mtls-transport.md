# ADR-0107：外部服务的显式 mTLS Transport

- 状态：Accepted
- 日期：2026-08-30
- 范围：平台身份、Model Gateway 凭据服务、部署平台

## 决策

新增 `MtlsClientConfig`，统一构造同步/异步 HTTP 客户端。配置必须由部署组合根
显式注入，并包含绝对路径的 CA bundle、客户端证书、客户端私钥和正数超时。
工厂不读取环境变量、不扫描目录、不记录证书内容；返回的 client 生命周期由
组合根负责。

身份、密钥服务和部署 adapter 继续只依赖抽象 port 与已注入 client，业务领域和
Model Gateway 不持有证书路径，也不直接管理轮换。

## 凭据租约撤销

`CredentialLease` 新增 `revoked` 语义。外部密钥服务返回撤销标记时立即抛出
`CREDENTIAL_REVOKED`，即使 `expires_at` 尚未到期也不得构造模型 adapter。该判定
发生在 provider 外呼之前，并且错误消息不包含 secret。

Provider 外呼还必须满足“租约有效期覆盖本次请求 deadline”：如果
`expires_at <= now + timeout_seconds`，请求在网络调用前以 `CREDENTIAL_EXPIRED`
拒绝，避免凭据在模型生成过程中失效。

HTTP 凭据 adapter 还提供 metadata-only 的
`POST /v1/provider-credentials/leases/revocation-status` 查询，并将部署环境绑定
到 `CredentialRevocationChecker`。HTTP Gateway 工厂通过
`check_credential_revocation=True` 显式开启该检查；默认关闭以保持组合根对外部
服务契约的显式控制。状态响应必须是严格布尔值，超时、网络、平台拒绝或非法响应
均映射为稳定的 `CREDENTIAL_*` 错误并 fail-closed。
同步实现的 revocation checker 在异步 Model Gateway 中通过线程池执行，异步实现继续
await，避免同步凭据服务阻塞事件循环。
组合工厂若收到撤销检查器但没有 `CredentialLease` 凭据端口，则在启动期直接拒绝，
禁止出现“配置了检查器但实际未执行”的假安全状态。

身份、部署和凭据 adapter 同样禁止同时传入已构造的 HTTP client 与
`MtlsClientConfig`；二者并存会导致 mTLS 配置被静默忽略，因此统一以
`*_MTLS_CLIENT_CONFLICT` 在构造期失败。

## 未完成事项

证书轮换/撤销回调、KMS/Secret Manager 托管、mTLS 端到端演练和 service mesh
策略仍属于部署环境责任，未因本 ADR 而宣称生产已接通；撤销状态 endpoint 仍需在
目标身份/密钥服务中实现并纳入部署验收。
