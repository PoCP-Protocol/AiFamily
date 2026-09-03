---
id: ADR-0061
title: Governed Agent Definition registry loader
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0061：Agent Definition 注册表加载

## 背景

`AI_USE_CASE_REGISTRY.yaml` 已登记 Agent 的能力边界，但运行时此前只能由
组合根手工构造 `AgentDefinition`，容易出现文档与实际白名单漂移。

## 决策

新增 `AgentDefinitionRegistry`，从显式路径加载治理 YAML 中的 `agents` 节，
并 fail-closed 校验必填策略、工具/用例白名单、唯一 ID 和
`may_mutate_business_state=false`。注册表只负责静态定义；家庭范围、目的、TTL、
预算和撤回仍由 `AgentAuthorization` 租约与 `AgentRuntime` 校验。

## 后果与缺口

- 测试、预发布和生产组合根可以加载同一份 Agent 定义，减少配置漂移。
- 加载器不执行模型、不调用业务域、不授予动态授权。
- 当前仍未建立版本化/持久化 registry 发布工作流和配置签名；生产组合根必须显式
  提供受控路径，不能从请求参数加载注册表。

