---
id: ADR-0093
title: Provider-neutral deployment and rollout port for AI releases
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0093：Provider-neutral AI 部署与灰度端口

## Context

评测、签名批准和候选目录已经形成治理链，但直接在 AI Runtime 中调用部署平台会
把供应商凭据、灰度副作用和家庭请求生命周期混在一起，也无法为测试环境提供完整
的生产同构验证。

## Decision

新增 `DeploymentPort` 与 `ReleaseDeploymentService`，仅接受已批准候选、匹配的
`ReleaseControlEvent` 和真人 actor。外部平台通过 `apply/rollback` 端口注入，服务
以 `ai_release_deployment_receipts`（migration 0033）记录 operation、phase、灰度
比例、外部引用、控制事件和幂等键。Receipt ledger 在调用端口前检查重放，端口不得
由 AI Runtime 读取模型凭据或导入 provider SDK。

## Consequences

- test/staging/production 可以复用相同的部署服务与失败矩阵，只替换显式端口适配器。
- 灰度与回滚请求可重启读取、幂等重放并与签名控制审计关联。
- 当前端口仍不代表真实平台已接入；生产需提供具备身份、权限、超时、补偿和演练证据
  的部署适配器，不能用测试替身冒充生产准入。
