---
id: ADR-0063
title: Request-scoped identity and consent before multimodal context
status: Accepted
date: 2026-08-30
owners: [family-api, platform-identity, platform-consent]
---

# ADR-0063：多模态体验先做请求级身份与同意解析

## Context

`backend/intelligence/experience/api.py` 的 request body 明确禁止
`tenant_id`、`family_id`、`subject_ids`、`consent` 和 provider 字段，但原生产
resolver 只接收 URL 的 `family_id` 并由部署自行返回 `ContextScope`。如果部署
没有统一的账号→租户/家庭链和 consent 检查，body 虽然不能伪造 scope，resolver
仍可能构造一个未经验证的 scope。

平台已经提供 `TrustedTenantScopeResolver`（`backend/platform/identity/
trusted_context.py`）和无缓存的 `ConsentGate`（`backend/platform/consent/gate.py`），
但两者此前没有连接到 multimodal experience。家庭教育场景要求撤回同意在下一次
请求立即生效，不能把一次 ALLOW 缓存在 resolver 中。

## Decision

新增 `AuthenticatedExperienceScopeResolver`：

1. 从部署提供的 request-scoped `principal_resolver` 获取已认证 account 与
   correlation/causation id；它不读取模型输入 body。
2. 调用 `TrustedTenantScopeResolver(account_id, family_id)`，任何缺失、非 active
   或跨家庭链都统一拒绝。
3. 由部署提供当前主体集合和 consent rows；对每个主体用 `ConsentGate.check`
   和声明的 `ConsentPurpose` 重新判断，任意主体缺失/撤回/过期即拒绝。
4. 仅在上述检查全部通过后构造 immutable `ContextScope`，携带 tenant、family、
   subject、purpose、consent version、deletion ref 和 correlation ids。
5. 该 resolver 作为 `ProductionExperienceRuntimeResolver.scope_resolver` 的
   显式输入；默认 `family_api` 未配置 resolver 的 503 行为不改变。

## Alternatives Considered

### 只在 route 中检查 URL family_id

支持理由：实现最少，现有 `_assert_family_scope` 已有跨家庭保护。

否决理由：不能证明账号拥有该家庭，也不能验证 tenant/membership 生命周期或 consent
撤回，属于把认证责任留给调用者自觉。

### 在 ContextScope 中默认 `consent_granted=True`

支持理由：减少每个部署的接线工作。

否决理由：会把缺少 consent store 变成静默放行，违反 R6、R9 和未成年人数据硬约束；
缺配置必须拒绝。

### resolver 内缓存一次 consent 决策

支持理由：减少数据库读取和 Gate 计算。

否决理由：撤回 consent 无法即时生效；`ConsentGate` 的设计明确要求调用者每次
传入 freshly-read grants。

## Consequences

### 正面

- AI 请求的 trusted scope 有统一、可测试的身份和 consent 前置边界。
- 跨家庭、无 membership、无 consent、withdrawn/expired consent 都在触达 Gateway
  前被拒绝。
- correlation/deletion 元数据可进入 provenance 与 Durable Run。

### 负面 / 代价

- 部署必须提供 request-scoped principal、主体列表和实时 consent store；平台不再
  用默认租户/家庭猜测。
- 当前 `TrustedTenantScope` 只证明家庭链，不负责列出全部主体；主体解析仍是显式
  端口，需由家庭/成员域后续接入真实仓储。

## Enforcement

- `backend/apps/family_api/trusted_experience_scope.py`
- `tests/apps/family_api/test_trusted_experience_scope.py`
- `backend/platform/identity/trusted_context.py`
- `backend/platform/consent/gate.py`
- `tests/architecture/test_no_direct_provider_calls.py`

## References

- ADR-0006：未成年人数据合规约束进入架构
- ADR-0062：Web 多模态体验的显式生产组合根
- `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`
