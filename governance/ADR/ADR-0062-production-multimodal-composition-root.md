---
id: ADR-0062
title: Explicit production composition root for the Web multimodal experience
status: Accepted
date: 2026-08-30
owners: [ai-architecture, family-api]
---

# ADR-0062：Web 多模态体验的显式生产组合根

## Context

`backend/intelligence/experience/api.py` 的 resolver 在未注入时必须返回
503；`backend/apps/family_api/main.py:create_app()` 只有在调用方显式传入
`experience_runtime_resolver` 时才覆盖该依赖。此前没有任何生产 resolver 组装
身份/同意 `ContextScope`、`ModelGateway`、SQL ModelDraft registry 和 Durable
Run ledger，因此 Web 生产路径安全但永远不可用。现有 synthetic wiring 只允许
`test` 环境，不能成为生产回退。

同时，ADR-0045 已确定 ModelDraft 需要可重启查询的持久 registry，ADR-0050 已
确定异步 ExperienceRun ledger 必须由 composition root 注入 session/事务。若把
session 放进全局 resolver，会造成连接泄漏；若每个请求重新构造 fake，则会把
合成输出伪装成模型能力。

## Decision

新增 `ProductionExperienceRuntimeResolver`，作为显式、可注入的生产组合根：

1. 由部署提供 `scope_resolver(family_id)`；它负责认证、租户/家庭/主体绑定与
   consent，HTTP 请求体不能覆盖这些字段。
2. 由部署注入已经通过 `ProviderRegistry` 的 `ModelGateway` 与
   `MultimodalRouter`；组合根不读取供应商 SDK、不绕过准入、不创建 Fake provider。
3. 每次生成使用短生命周期 `AsyncSession`，在同一事务中保存 SQL ModelDraft
   与 provenance；ExperienceRun 使用 `SessionPerCallExperienceRunLedger`，并
   通过 `AsyncExperienceRunLedgerBridge` 暴露给 HTTP。
4. 组合根只接受 `staging` / `production` 环境，拒绝 `test` 和其他未声明环境、
   synthetic scope、跨家庭 scope 和缺失的多主体 ModelDraft subject；生产配置缺失
   仍由 HTTP resolver 返回 503。
5. 所有结果保持 `DRAFT`，人工确认和 Named Action 仍是后续边界，不因生产 wiring
   而自动写入任何领域事实。

## Alternatives Considered

### 继续默认 503

支持理由：最安全，不会误发家庭数据。

否决理由：只能证明 fail-closed，无法交付 Web 多模态产品；生产路径没有任何可用
的组合实现。

### 在 `main.py` 内自动从环境变量创建 Fake 或未审查供应商

支持理由：启动后立即可演示，减少部署参数。

否决理由：违反 R5/R7 和 ADR-0006；缺少合规证据时不能把 synthetic 或未知供应商
呈现为真实 AI。

### 在 resolver 中长期持有一个 AsyncSession

支持理由：可以尝试把 draft 与 run 写入同一连接。

否决理由：FastAPI dependency 没有统一 teardown，跨请求持有 session 会泄漏连接；
且 durable ledger 已有明确的 per-call 生命周期边界。

## Consequences

### 正面

- 生产组合根终于可以接入真实认证/同意实现和已准入的多模态模型。
- SQL Draft、provenance 与 Durable Run 的边界均可测试，重启回放不再调用模型。
- 没有配置时仍然明确失败，不会悄悄降级到合成数据。

### 负面 / 代价

- 需要部署方提供 scope resolver、数据库和经治理的 provider registry。
- Draft 保存与 Run finalize 是两个显式事务边界；若要跨表原子提交，需要后续统一
  Unit of Work，而不是在 resolver 中偷偷共享 session。

### 需要接受的风险

- ContextBroker 当前仍由注入实现决定是否持久化；生产部署必须提供满足保留/删除要求
  的实现，不能把进程内 broker 当作跨进程事实库。组合根只依赖 `snapshot()` /
  `read()` 端口，不会偷偷替换成内存实现。

## Enforcement

- `backend/apps/family_api/production_experience_wiring.py`
- `tests/apps/family_api/test_production_experience_wiring.py`
- `tests/apps/family_api/test_experience_router_mount.py`
- `tests/architecture/test_no_direct_provider_calls.py`
- `ModelGateway` 的 `ProviderRegistry.admit()`、SQL Draft CHECK 约束和 HTTP DRAFT
  response model

## References

- ADR-0045：Durable ModelDraft provenance registry
- ADR-0050：Async ExperienceRun ledger 通过组合根接入 HTTP
- ADR-0006：未成年人数据合规约束进入架构
