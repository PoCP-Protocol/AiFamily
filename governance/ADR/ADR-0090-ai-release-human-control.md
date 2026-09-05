---
id: ADR-0090
title: Human approval and rollback control for AI releases
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0090：AI 发布的人审批准入与回滚控制

## Context

`AiReleaseGate` 与 `ai_release_decisions` 只能证明候选版本通过了离线证据和供应商
准入检查，不能代表运营人员已经批准发布，也不能提供可审计的回滚指针。若把这两
类语义混在一起，自动评测可能被误当作生产发布授权。

## Decision

新增 `ReleaseControlStore`，以 `APPROVAL` / `ROLLBACK` 两类 append-only 事件记录
运营者对 `ADMITTED` 决策的批准和回滚目标。事件绑定稳定的 decision fingerprint、
candidate/environment、actor、reason、外部签名校验和幂等键，落入
`ai_release_controls`（migration 0031）。签名 verifier 由身份/安全系统注入，AI Runtime
只保存不可逆 `signature_ref`，不持有密钥或原始签名。`ai:*` actor、BLOCKED 决策、
空原因、无效签名和同候选回滚均 fail-closed；重复幂等键必须与原事件完全一致。

该边界只提供控制事实和查询，不调用部署系统、不改业务事实、不删除历史决策。真正
的发布执行器、签名密钥、灰度策略与部署平台仍由生产组合根显式接入。

## Consequences

- 测试与生产使用同一审批/回滚契约，重启后仍可审计控制事件。
- 评测、批准、回滚三个状态边界可分别授权和观测，降低误发布风险。
- 当前仍不是生产部署能力；需要后续接入 operator identity 的真实 verifier、部署平台和
  回滚演练，但不能因此在测试环境删掉控制路径。
