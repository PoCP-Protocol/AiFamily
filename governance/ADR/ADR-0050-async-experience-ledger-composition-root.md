---
id: ADR-0050
title: Async ExperienceRun Ledger 通过组合根接入 HTTP
status: Accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0050：Async ExperienceRun Ledger 通过组合根接入 HTTP

## 背景

`family_api` 的 HTTP handler 是异步函数，但历史上的内存 ExperienceRun Ledger
是同步 port；生产 SQL Ledger 使用 `AsyncSession`，不能通过阻塞调用伪装成同步
实现。若两套实现各自维护一份 HTTP 语义，会造成测试与生产功能不等价。

## 决策

1. 通过 `dispatch_ledger_call` 统一调用同步和异步 ledger：同步结果原样返回，
   awaitable 结果由当前事件循环等待；禁止 `asyncio.run`、线程阻塞和隐式事务。
2. `AsyncExperienceRunLedgerBridge` 适配 API 的
   `preflight_create/finalize_create/release_create/append_interaction/replay` 契约，
   但不拥有或提交数据库事务；事务由 composition root 注入的 session/UoW 管理。
3. durable adapter 必须持久化创建幂等指纹、状态和 HTTP response projection。进程
   重启后若没有完整响应投影，API 必须返回明确的 fail-closed 错误，不得从草稿内容
   猜造响应。
4. 同一 API、状态机、错误码和人工闸门在 dev/test/prod 复用；环境只替换数据、
   session、队列和 provider adapter。

## 后果

- SQL Ledger 可以在真实 FastAPI composition root 中使用，且不牺牲事件循环和事务
  原子性。
- bridge 的预留标记仍是进程内的协调层；跨进程并发和 worker 重试必须依赖 SQL
  唯一约束与后续 outbox/worker。
- 尚未完成真实 identity/consent/context wiring 时，production resolver 继续
  fail-closed，不因 bridge 存在而自动开放能力。

## Enforcement

- `backend/intelligence/experience/async_ledger_bridge.py`
- `backend/intelligence/experience/api.py`
- `tests/intelligence/experience/test_async_ledger_bridge.py`
- `tests/apps/family_api/test_experience_router_mount.py`
