---
id: ADR-0065
title: FGCN 开案前使用 GrowthIntent、Consent 与租户家庭绑定依赖门槛
status: proposed
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0065：FGCN 开案前使用 GrowthIntent、Consent 与租户家庭绑定依赖门槛

## 背景

FGCN 的业务事实从 `ServiceCase` 开始，但 `GrowthIntent`、`Consent` 和
tenant-family binding 不属于 service/FGCN 的事实所有权。若开案只校验请求
中的 `intent_ref`、scope 和 blueprint，就可能把未确认需求、已撤回或用途不符
的同意、以及跨租户/家庭的对象写成合法 ServiceCase。

Onboarding、FamilyNeed 和 Consent 的上游实现仍在其他 Agent WIP 中，且尚未
同时证明 Fake/Postgres/HTTP 的环境等价与真实 PostgreSQL 证据。因此 FGCN
不能把 FamilyNeed 或独立的 Onboarding 闭环当作完整入口。

## 决策

1. FGCN 只依赖一个只读 `CaseEntryDependencyQuery`（内存）或
   `AsyncCaseEntryDependencyQuery`（durable application command），不复制或
   拥有 GrowthIntent、Consent、tenant-family binding 存储事实。
2. 查询快照必须同时满足：`intent_ref` 一致且 GrowthIntent 为 `CONFIRMED`；
   Consent 为 `ACTIVE`，并且 subject、purpose、version 与 `GateServiceScope`
   完全一致；tenant-family binding 为 `ACTIVE`，且 tenant/family 与 scope 完全
   一致。缺失、格式错误、查询失败或任一不匹配均 fail-closed。
3. 门槛位于新 ServiceCase 首次写入之前。内存 `FGCNEngine.open_case` 与
   durable `open_service_case` 使用同一组拒绝语义；拒绝时不写业务事实，也不
   写 `OPEN_SERVICE_CASE` 审计事件。
4. 已存在且不可变字段完全一致的 durable case replay 可直接返回已存事实；这
   不会创建新的 ServiceCase。历史表没有 opening idempotency-key 列，因此
   durable command 以 case primary key 和不可变 payload 提供 replay 防护；真实
   opening-key 的跨重启唯一性仍是明确缺口，不得宣称已由本 ADR 解决。
5. 未配置依赖查询时使用拒绝型默认实现。生产接线必须由拥有各自事实的上游
   边界提供，不能在 FGCN 内部用 FamilyNeed、请求体或本地默认值替代证明。

## 正向与反向验收

正向：精确匹配的 `CONFIRMED` GrowthIntent、`ACTIVE` Consent 和
`ACTIVE` tenant-family binding 通过后，`ServiceCase` 被创建，并在同一 durable
事务中留下 `OPEN_SERVICE_CASE` 审计记录。

反向：GrowthIntent 未确认、Consent 撤回、Consent purpose/version/subject 不匹配、
tenant-family 越权或 binding 非 ACTIVE、依赖查询失败/未接线，均不能创建
ServiceCase，且拒绝前后无业务行和开案审计行。

## 未决与边界

- 本 ADR 只建立 FGCN 的入场契约，不实现或修改 Journey Onboarding、Family、
  Consent 或共享 Registry。
- 上游真实适配器、真实 PostgreSQL 证据、HTTP 等价和生产身份/授权接线完成
  前，FGCN 的开案能力仍是有依赖条件的 durable slice，不等同于完整生产入口。
- 当前历史 schema 未保存 opening idempotency key；若要提供跨重启按 key 的
  严格语义，应另行提出 schema/迁移 ADR，不在本切片隐式扩展。

## Enforcement

- `backend/domains/service/fgcn/entry.py`
- `backend/domains/service/fgcn/engine.py`
- `backend/domains/service/fgcn/application.py`
- `backend/domains/service/fgcn/README.md`
- `tests/domains/service/fgcn/entry_test_doubles.py`
- `tests/domains/service/fgcn/test_entry.py`
- `tests/domains/service/fgcn/test_fgcn_flow.py`
- `tests/domains/service/fgcn/test_persistence.py`

## References

- `governance/REPOSITORY_CONSTITUTION.md` R2、R6、R7、R8、R9、R14
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md`
- `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md`
- `governance/ADR/ADR-0036-fgcn-service-collaboration-p0-slice.md`
- `governance/ADR/ADR-0064-fgcn-provider-admission-query-gate.md`
