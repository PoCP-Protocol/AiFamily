---
id: PLT-TENANCY-001
title: 平台租户架构与可信作用域
type: platform
status: current
version: 1.0
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: true
supersedes: null
superseded_by: null
---

# Tenancy — 租户架构与可信作用域

本文件记录 AiFamily 当前已经存在的多租户实现和未完成项。它不是“生产多租户已完成”
的声明；当前完成的是租户授权门与 Account→Tenant→Family 的平台解析器，数据库级隔离、
真实认证和租户业务闭环仍在后续阶段。

## 1. 边界与所有权

Tenant 是客户/组织级隔离命名空间，Family 是家庭业务主体。Tenant 不取代 Family，
也不拥有家庭成长事实。一个请求要进入 Family 业务作用域，必须同时证明：

```text
verified Account
  → active TenantAccountMembership
  → active TenantFamilyBinding
  → active AccountPersonBinding
  → active FamilyMembership
  → requested Family
```

数据库基线位于 `database/baseline/0028_tenant_master_data_foundation.sql`，现有回填与
可信链索引位于 `database/baseline/0042_vs00_tenant_trusted_context.sql`。

## 2. 已实现的运行时契约

`backend/platform/identity/trusted_context.py` 提供：

- `TrustedTenantScope`：服务器解析出的账号、Tenant、Family、区域、Tenant 角色及链路状态；
- `TrustedTenantScopeResolver`：对缺失、非 ACTIVE 或歧义作用域统一抛出
  `TenantScopeError("TENANT_SCOPE_UNAVAILABLE")`；
- `SqlAlchemyTrustedTenantScopeStore`：按完整关系链查询，只接受一行完整 ACTIVE 结果；
- `InMemoryTrustedTenantScopeStore`：仅供测试/dev wiring，拒绝重复 key，不提供默认租户；
- `TrustedTenantScope.actor_context()`：只能从已解析的服务器 Tenant 生成 `ActorContext`，
  不接受客户端 Tenant ID。

租户授权门仍由 `backend/platform/authorization/policy.py` 的 `TenantDirectory` 执行：
未知、SUSPENDED、ARCHIVED 租户默认 DENY。可信作用域解析器与授权门互补：前者证明请求
属于哪个租户和 Family，后者阻止非 ACTIVE 租户继续执行策略。

## 3. 生命周期状态

| 层 | 允许继续访问的状态 | 其它状态的处理 |
|---|---|---|
| Tenant | `ACTIVE` | `SUSPENDED` / `ARCHIVED` → DENY |
| Tenant account membership | `ACTIVE` 且时间窗口有效 | `INVITED` / `SUSPENDED` / `REVOKED` → DENY |
| Tenant-Family binding | `ACTIVE` 且时间窗口有效 | `SUSPENDED` / `MIGRATING` / `REVOKED` → DENY |
| Account / Account-Person / Family membership | `ACTIVE` | 缺失或非 ACTIVE → DENY |

所有失败统一为不可用作用域，避免把“无权访问”与“租户不存在”区分给不可信调用方。

## 4. 现状核对表

| 能力 | 状态 | 证据 |
|---|---|---|
| 不可信客户端 Tenant ID 不参与解析 | 真实存在 | `TrustedTenantScopeResolver` 参数只有 `account_id`、`family_id` |
| Account→Tenant→Family 可信链 | 真实存在（平台适配器） | `SqlAlchemyTrustedTenantScopeStore` + 单元测试 |
| 未知/失效/歧义链路 fail-closed | 真实存在 | `TenantScopeError` 与 `test_trusted_context.py` |
| 真实认证（JWT/API Key/Identity Session） | 不存在 | `auth_identity` 仍为 `NOT_STARTED` |
| 租户上下文自动注入 UoW | 不存在 | `SqlAlchemyUnitOfWork` 尚未绑定 Trusted Scope |
| PostgreSQL `SET LOCAL app.tenant_id` / RLS | 不存在 | 尚无对应迁移或事务 hook |
| 全域仓储数据库隔离 | 未完成 | 部分域仍依赖显式查询过滤 |
| Tenant 生命周期与成员管理业务域 | 不存在 | `tenancy` 聚合尚未落地 |

## 5. 下一步实现顺序

1. 完成 `auth_identity` 的生产认证适配器，只向平台提供 verified `account_id`；
2. 在 API composition root 中解析 Trusted Scope，并将它绑定到请求生命周期；
3. 在 `SqlAlchemyUnitOfWork` 开启事务后执行租户上下文设置，生产 PostgreSQL 使用
   `SET LOCAL app.tenant_id`，同时添加 RLS policy 与真实数据库验收测试；
4. 将现有域仓储迁移到统一的 tenant-scoped port，禁止只靠调用方自觉传过滤字段；
5. 在独立的 `tenancy` 业务域实现租户生命周期、成员关系和 Family binding 迁移，并为
   所有状态变更补 Audit/Event/幂等边界。

以上每一步都必须保留 fail-closed：缺少真实身份、租户作用域或数据库隔离接线时，
请求应拒绝，而不是退回默认租户或无租户查询。

## 6. 设计决策

可信链的边界与后续缺口见 `governance/ADR/ADR-0048-trusted-tenant-scope-resolution.md`。
租户授权门的实际契约见 `docs/06_platform/IDENTITY.md` 与
`docs/06_platform/AUTHORIZATION.md`。
