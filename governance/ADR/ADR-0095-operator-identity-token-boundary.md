---
id: ADR-0095
title: Explicit operator identity and deployment token boundary
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0095：Operator Identity 与部署令牌边界

## Context

AI 发布控制已经要求真人审批，但部署适配器仍需要一个明确的身份与令牌
来源。将密钥读取放进 AI Runtime 或从环境变量隐式读取，会造成不可审计的
权限旁路，也无法保证测试、预发布和生产使用同一失败语义。

## Decision

新增 `backend/intelligence/evaluation/operator_identity.py`：

- `OperatorIdentityPort` 只解析外部身份服务返回的非秘密 operator 元数据；
- `HttpOperatorIdentityPort` 使用注入的 HTTP client 与 bootstrap token source，
  校验 environment 一致性和 scopes，不读取环境变量、不持久化 token；
- `HttpOperatorTokenProvider` 按每次部署请求解析 operator，再向外部 key service
  交换短期 bearer token；token 仅存在调用栈内，交给现有 `HttpDeploymentPort`，
  不进入 ReleaseCandidate、数据库或 telemetry；仅拥有 `ai.release.deploy`
  （或组合根显式指定的等价 scope）的 operator 才能交换部署令牌；
- 身份服务错误、环境不匹配、空 token 和畸形响应均 fail-closed。

## Consequences

- composition root 显式注入 identity port/token provider，测试可使用 MockTransport，
  生产可替换真实 identity/key service，而不改变部署协议；
- AI Runtime 不拥有 operator 密钥，也不会从请求体或环境变量推断身份；
- 真实部署仍需在平台侧配置 mTLS/密钥轮换、token TTL、审计与撤销策略；本 ADR
  不把外部身份服务或部署平台伪装成已上线能力。

## Composition root ownership

`ReleaseDeploymentService` 的 candidate、human-control 和 receipt store 由部署
应用组合根负责组装，因为该层拥有候选状态、真人批准/回滚和事务提交的生命周期。
本模块只提供 provider-neutral `OperatorIdentityPort` 与 token source；它不读取
这些 store、不创建部署服务，也不从环境变量推断依赖。组合根必须显式注入
`OperatorIdentityPort`、短期 token provider、`DeploymentPort`、receipt store（以及
候选/控制 store），确保 staging 与 production 共享同一 fail-closed 契约。
