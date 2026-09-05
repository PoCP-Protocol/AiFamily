---
id: ADR-0094
title: HTTP deployment adapter with injected credentials and transport
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0094：HTTP 部署 Adapter 的凭据与传输边界

## Context

`DeploymentPort` 已定义部署/回滚语义，但生产仍需要一个能调用部署平台的适配器。
如果 adapter 自行读取环境密钥或让测试绕开 HTTP 契约，会重新造成环境能力漂移和凭据
散落。

## Decision

新增 `HttpDeploymentPort`：base URL、token provider、请求超时和 `httpx.AsyncClient`
全部显式注入；请求携带幂等键、control id、环境和最小候选元数据，不携带家庭数据、
Prompt 或模型输出。候选 ID 以 URL segment 编码，token source 异常、非 2xx 状态、
超时、网络和 malformed response 统一映射为稳定错误码；测试使用 `MockTransport`，
生产只替换 token provider、URL 和 transport，不改变业务路径。

## Consequences

- 密钥仍由部署/密钥服务拥有，AI Runtime 不会读取或记录它们。
- test/staging/production 的请求、错误和重放语义一致。
- 真实部署平台的权限、TLS、限流、补偿和灰度观测仍需部署团队提供证据。
