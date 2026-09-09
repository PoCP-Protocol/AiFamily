---
id: ADR-0164
title: Growth Plan 读取审计边界
status: Proposed
date: 2026-09-10
owner: chief-architect
---

# ADR-0164：Growth Plan 读取审计边界

## Context

Guardian 读取已验证 Growth Plan Draft 或已采纳计划时，会暴露家庭成长过程与
未成年人相关信息。现有 adoption 写入已经有 R6 mutation audit，但读取路径如果
只返回 JSON，会缺少《未成年人网络保护条例》第36条要求的访问留痕。

## Decision

1. `GrowthPlanAdoptionService.get_current` 在成功返回 Draft/Plan 前，调用 adoption
   repository 的 `record_read` port。
2. 生产 PostgreSQL adapter 通过现有 `AuditRecorder.record_read()` 与
   `platform_audit_events` 持久化；不新建 Journey 审计表或第二套审计协议。
3. 读取记录必须包含 actor、tenant、minor subject、字段集合、`growth_tracking`
   purpose、Guardian consent reference 和 correlation id。
4. 没有唯一可解析 subject scope 时 fail closed；读取返回不能以猜测的主体替代
   审计主体。
5. Guardian 必须属于 Draft/Plan 的已确认 subject scope；同家庭的其他 Guardian
   不因家庭级身份自动获得该计划的读取权。

## Consequences

开发适配器与生产适配器共享同一 port，测试可以断言读取事件；真实 PostgreSQL
HTTP/重启证据仍需在配置 `AIFAMILY_TEST_DATABASE_URL` 后补齐。该 ADR 不改变
Growth Plan 是人工采纳投影、不是 AI 事实的边界。
