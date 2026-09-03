---
id: ADR-0096
title: Metadata-only telemetry for release deployment operations
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0096：发布部署操作接入 metadata-only 观测

## Context

`ReleaseDeploymentService` 已在外部副作用前检查人工控制和幂等 receipt，但如果没有
统一观测，canary、active 和 rollback 的成功、失败及稳定错误码无法进入现有
TelemetrySink。部署平台也不应把候选报告、签名、家庭数据或异常文本复制到观测系统。

## Decision

在 `ReleaseDeploymentService` 上增加可选的 `TelemetrySink` 注入。每次真正调用
`DeploymentPort` 前启动一个稳定 operation span，属性仅允许 provider/model/version、
environment 和 deployment phase；成功或异常时以 `OK`/`ERROR` 结束，并只记录稳定错误码。
receipt 幂等重放不再次调用外部端口，也不产生新的外部部署副作用。trace id 由候选和
环境的不可逆摘要派生，不保存幂等键、控制签名、报告内容或家庭 payload。

## Consequences

- staging 与 production 可复用同一部署观测契约，测试只替换 TelemetrySink 和
  DeploymentPort。
- OpenTelemetry/SQL sink 的既有 allowlist 与 operation 幂等继续执行，观测不会扩大
  数据处理范围。
- 观测 sink 的部署、保留期限、告警与删除 worker 仍由运行平台负责；缺失 sink 时
  部署服务保持原有显式注入语义，不自动安装 synthetic adapter。
