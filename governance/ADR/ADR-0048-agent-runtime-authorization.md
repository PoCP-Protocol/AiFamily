---
id: ADR-0048
title: Agent Runtime 采用静态定义与动态授权双层边界
status: Accepted
date: 2026-08-30
---

# Agent Runtime 采用静态定义与动态授权双层边界

## 背景

AI 原生原则要求每个 Agent 的能力边界显式建模，同时高影响行为必须人工接管，
AI Runtime 永远不能写入业务事实。仅在代码中登记 Agent 名称和工具白名单，
无法表达某个家庭当前是否同意、授权是否过期或预算是否耗尽。

## 决策

1. `AgentDefinition` 是经治理审查的静态上限，声明 skills、tools、use cases、
   context/safety/handoff/budget policy；其 `may_mutate_business_state` 固定为
   `False`，不提供可写字段。
2. `AgentAuthorization` 是按 tenant/family scope 签发的动态租约，必须包含
   TTL、撤回时间、允许用例/工具、预算、签发人、原因、policy version 和 audit ref。
3. `AgentAuthorizer` 采用 fail-closed：缺少任一层定义/授权、scope 不匹配、过期或
   撤回、用例/工具超出静态或动态白名单、预算超限，均在生成请求构造前拒绝。
4. `AgentRuntime` 只依赖 provider-neutral `StructuredGenerationPort`，由
   `backend/intelligence/model_gateway` 提供实现；运行时只返回 `AgentRun` 与
   `ModelDraft`，不得 import 业务域 repository，也不得执行 Named Action。

## 后果

- 同一套 Definition、授权判定和生成链可在 dev/test/prod 复用，测试环境只替换
  数据和 provider adapter，不删减功能。
- 授权租约成为后续 Tool Runtime、Human Gate 和成本账本的组合根输入；当前实现不
  持久化授权或执行记录，持久化由后续专门能力补齐。
- 运行时在 provider 调用前拒绝非法请求，调用方可以通过 `AgentAuthorizationError`
  明确区分授权拒绝而不泄露请求 payload。

## 约束依据

- `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §3.5
- `docs/05_ai/AI_TECHNICAL_ARCHITECTURE.md` §8
- `docs/05_ai/AI_PLATFORM_FORWARD_ARCHITECTURE.md` §1
- `governance/REPOSITORY_CONSTITUTION.md` R7、R8、R9、R10

