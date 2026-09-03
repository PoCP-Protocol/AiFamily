---
id: ADR-0098
title: Explicit production release composition root
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0098：生产发布能力的显式组合根

## Context

发布控制、候选目录、receipt、身份和 HTTP 部署 adapter 已分别具备契约。若由调用方
自行拼装，容易出现 staging/production 依赖漂移，或让客户端直接传入真人 actor，绕过
身份服务和部署 scope 校验。

## Decision

新增 `backend/apps/family_api/production_release_wiring.py`：

- `ProductionReleaseRuntime` 只接受 `staging`/`production`，每次操作从注入的
  `OperatorIdentityPort` 解析真人身份，并要求 `ai.release.deploy` scope；调用者不能
  直接提供 `human_actor`；
- `build_production_release_runtime` 组装已注入的 provider-neutral port、receipt store、
  telemetry sink 和 release service；不读取环境变量或秘密；
- `build_http_production_release_runtime` 仅负责显式实例化 identity、短期 token 和
  `HttpDeploymentPort` adapter，URL、bootstrap token source、audience、HTTP client 与
  存储均由部署层传入；
- 外部身份、token、部署平台和数据库失败保持 fail-closed，测试只替换同一端口。

## Consequences

- test/staging/production 共享同一真人授权、灰度、回滚、receipt 和观测路径；只有
  外部 adapter 与数据源替换。
- production composition root 的真实接线仍需部署团队提供 mTLS、密钥轮换/撤销、
  PostgreSQL receipt、scheduler、平台权限和演练证据；本 ADR 不宣称这些外部系统已上线。
