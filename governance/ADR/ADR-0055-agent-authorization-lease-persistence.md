---
id: ADR-0055
title: AgentAuthorization 采用可撤回的持久化授权租约
status: Accepted
date: 2026-08-30
---

# ADR-0055：AgentAuthorization 采用可撤回的持久化授权租约

## 背景

Agent Runtime 原先只接收进程内 `AgentAuthorization` 值对象。进程重启、
多 worker 或撤回操作会造成授权状态不一致，无法满足生产环境的最小审计与
租户/家庭隔离要求。Tool Runtime 也依赖该动态授权边界，因此必须有一个
provider-neutral、可组合的持久化 seam。

## 决策

1. 在 `backend/intelligence/agent_runtime/authorization_persistence.py` 建立
   `AgentAuthorizationLeaseStore` 协议和 SQLAlchemy 实现。租约保留 agent、
   tenant/family scope、use-case/tool 白名单、issued/expires/revoked 时间、
   budget、policy/reason/audit 元数据。
2. `issue` 以 `(tenant_id, authorization_id)` 幂等；相同 ID 但内容不同 fail-closed。
   `revoke` 是幂等的状态转换，并写入 append-only `ISSUED/REVOKED` 审计事件。
   过期由 `find_active` 的当前时间查询计算，不依赖定时任务；任何 scope、用例、
   工具或预算不匹配均返回 `None`，调用方必须拒绝执行。
3. SQLAlchemy adapter 只 `add`/`flush`，不 `commit`、不 `close`，由组合根把授权、
   AgentRun、outbox 等写入放进同一事务。
4. 租约表只保存 AI 运行时授权元数据，不保存家庭总分、排名或其他领域事实；
   不导入模型供应商 SDK，不执行 Tool/Named Action。ToolAuthorization 仍是从
   AgentAuthorization 派生的短期运行时值对象，后续可复用同一 store 做独立租约。

## 后果

- 多实例运行时可在每次请求前从一致的数据库视图解析有效租约，撤回立即生效。
- 租约发行和撤回可按 actor/audit_ref 审计与重放，测试环境和生产环境使用同一
  fail-closed 语义。
- 当前 migration `0013` 需要在 Git 跟踪后重新执行 PostgreSQL upgrade→downgrade→upgrade
  门禁；并发 worker 的行级并发冲突、独立 ToolAuthorization 持久化和真实身份/同意
  组合根接线留待后续迭代。

## 约束依据

- `governance/REPOSITORY_CONSTITUTION.md` R6、R7、R8、R9、R10
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §3.5、§4
- `governance/ADR/ADR-0048-agent-runtime-authorization.md`
- `governance/ADR/ADR-0054-governed-tool-runtime-human-gated-actions.md`
