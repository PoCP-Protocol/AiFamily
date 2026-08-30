# ADR-0133: Tenant-scoped competitor evidence DRAFT persistence

- Status: Accepted
- Date: 2026-08-31
- Scope: Product Intelligence / IPD market insight

## Decision

竞品分析只保存可追溯的证据卡（claim、source_refs、evidence_status 及
DRAFT envelope），不保存竞品分数、排名或“最佳竞品”结论。证据卡写入独立的
`product_intelligence_competitor_evidence` 表，并由应用组合根传入
`tenant_scope` 与 `created_by`；请求体不得声明或覆盖这些边界字段。

若仓储未提供该写端口，HTTP 接口返回 503 并保持 fail-closed。写入成功仍只返回
DRAFT，不能绕过 Human Gate 推进产品生命周期。

## Consequences

- 市场洞察链路可以从公开资料形成可复核的竞品证据输入。
- 租户边界和审计来源在 Fake 与 SQLAlchemy 实现中保持一致。
- 真实数据库部署必须执行迁移 `0039_competitor_evidence`；竞品排名与评分能力
  明确不属于本平台的证据层。
