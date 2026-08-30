---
id: ADR-0048
title: Trusted tenant scope resolution
status: accepted
date: 2026-08-30
decision_owner: chief-architect
supersedes: null
superseded_by: null
---

# ADR-0048：可信租户作用域解析

## 背景

`ActorContext` 只携带不可变的 `tenant_id` 字符串，不能证明账号确实属于该租户，
也不能证明请求的 Family 当前由该租户拥有。仅依赖客户端提交的 `tenant_id` 或
在每个 Domain 手写过滤，会把身份认证、授权和数据隔离混成多个容易遗漏的约定。

当前数据库基线已经定义了 `accounts`、`tenant_account_memberships`、
`tenant_family_bindings`、`account_person_bindings` 和 `family_memberships`，因此需要
先把这条可信链在平台边界固定下来，再接入真实认证和数据库级隔离。

## 决策

1. 认证适配器只负责验证凭据并提供可信的 `account_id`；客户端传入的 `tenant_id`
   不参与租户作用域解析。
2. `TrustedTenantScopeResolver` 统一按以下链路解析请求作用域：
   `Account → TenantAccountMembership → TenantFamilyBinding → AccountPersonBinding
   → FamilyMembership → Family`。
3. 账号、租户、租户成员关系、租户-Family 绑定和 Family 成员关系必须处于有效状态，
   且时间窗口有效；任何缺失、失效、过期或多行歧义都 fail-closed，并对调用方统一
   返回 `TENANT_SCOPE_UNAVAILABLE`，不泄露租户或 Family 是否存在。
4. `TrustedTenantScope.actor_context()` 只能使用服务端解析出的租户生成
   `ActorContext`。Tenant 角色与 Family 角色分开保存，不能用其中一个替代另一个。
5. SQL 适配器只返回单行且完整的 ACTIVE 链路；重复结果、未知枚举值和字段缺失均视为
   不可用。适配器不提交事务、不管理认证会话生命周期。
6. 本 ADR 只确定平台身份解析边界。真实认证适配器、带租户上下文的 Unit of Work、
   PostgreSQL `SET LOCAL app.tenant_id` / RLS、按租户的数据仓储策略分别作为后续
   实现项，不得把当前解析器测试误报为生产隔离已完成。

## 被否决的方案

### A. 信任客户端 `tenant_id`

拒绝：客户端可伪造其他租户的标识；即使授权规则存在，也没有服务端证据证明该账号与
请求 Family 的关系。

### B. 每个 Domain 自行拼接租户过滤

拒绝：过滤规则会在多个查询点重复，任一遗漏都会形成跨租户读取或写入；租户边界应在
共享平台层和数据库层形成纵深防御。

### C. 找不到链路时默认使用唯一/默认租户

拒绝：默认租户会把“身份未解析”变成“获得访问权”，违反 fail-closed 和最小权限原则。

## 后果与未决项

正面结果是身份链拥有单一实现位置、稳定错误语义和可测试的歧义拒绝行为；授权层可以
消费同一个服务器解析出的 Tenant Context。

当前仍有明确缺口：

- `auth_identity` 业务域尚未完成，当前没有生产 JWT、API Key 或会话适配器；
- `SqlAlchemyUnitOfWork` 尚未自动把可信租户绑定到每个数据库事务；
- 尚未执行 PostgreSQL `SET LOCAL app.tenant_id`，也没有 RLS policy；
- 现有 Domain 仓储仍可能依赖显式 `tenant_id` 过滤，尚未由数据库统一兜底；
- `tenancy` 业务聚合（租户生命周期、成员邀请/撤销、Family 绑定迁移）尚未落地。

## 验证与证据

- `backend/platform/identity/trusted_context.py`
- `tests/platform/identity/test_trusted_context.py`
- `database/baseline/0028_tenant_master_data_foundation.sql`
- `database/baseline/0042_vs00_tenant_trusted_context.sql`
- `governance/REPOSITORY_CONSTITUTION.md` R6、R8、R12、R14
