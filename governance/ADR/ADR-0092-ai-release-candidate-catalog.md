---
id: ADR-0092
title: Separate AI release candidate catalog from human control events
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0092：AI Release Candidate Catalog 与控制事件分层

## Context

评测决策、真人批准和回滚操作具有不同生命周期。若只依赖控制事件查询当前候选，
会把不可变模型元数据、评测证据和可变部署状态混为一体，难以支持重启读取、候选
切换和后续部署系统接入。

## Decision

新增 `ReleaseCandidateCatalog` 与 `ai_release_candidates`（migration 0032）。目录
保存 candidate/provider/model/version/report_ref 的不可变元数据，并将状态投影为
`BLOCKED → ADMITTED → APPROVED → ROLLED_BACK`。状态推进必须引用匹配的
`ReleaseControlEvent`；批准前不能回滚，回滚目标必须是同环境已批准候选。目录不调用
部署系统、不删除历史控制事件，事务仍由组合根提交。

## Consequences

- 运营查询可以直接读取当前候选状态，控制账本仍保留完整审批/回滚审计。
- 测试和生产可复用同一目录契约，后续接灰度/部署平台时不需要改写 AI 评测数据。
- 当前仍不代表真实部署已完成；候选目录与部署执行器之间的同步、签名密钥服务和
  PostgreSQL 并发压测由后续生产接线负责。
