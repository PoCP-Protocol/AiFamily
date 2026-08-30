# ADR-0019: 家庭测评支持卡行动闭环的持久化边界

- **Status**: Proposed
- **Date**: 2026-08-30
- **Deciders**: family-assessment-dri / chief-architect review pending
- **Supersedes**: null
- **Superseded By**: null

## Context

S-01 的第一次价值不是给家庭一个分数，而是让家长说出一件真实小事，核对一张
家庭支持卡，选择一个今晚能做的小步骤，并在第二天回来告诉平台发生了什么。
此前这段闭环只存在于 `FakeAssessmentRepository`：进程重启后反馈、行动和回访全部
消失，且 `write_audit_and_outbox()` 只兼容带 session 的旧回执。

这会让 UI 看起来完成，但不能证明家庭行为真的能被可靠地保存、回读和审计。

## Decision

1. 继续由 `backend/domains/assessment` 作为唯一 canonical owner，不创建新的
   support、journey 或 family-result domain。
2. 在同一个 PostgreSQL 数据库中增加三张能力表：
   `family_assessment_support_card_feedback`、
   `family_assessment_small_steps`、`family_assessment_checkins`。每条记录都携带
   `tenant_id`、`family_id` 和 assessment session 引用。
3. 一个 assessment session 最多有一个 `TRY_TONIGHT` 小步骤。反馈与回访是家庭
   私有、可追加的记录；它们不是 canonical Fact、临床诊断、评分、排名或结果证明。
4. `available_for_checkin_at` 由数据库写入为下一日时间。应用层和 SQL repository
   都 fail-closed 检查该时间，进程重启不能把 `NEXT_DAY` 文案变成当日可提交。
5. 业务行、幂等 receipt、canonical `audit_logs` 和 `outbox_events` 继续共享调用方
   的一个事务。事件使用既有 outbox，不创建第二个事件账本；回执可没有 session
   payload，但必须保留 action、scope、boundary 和 assessment session 引用。
6. 迁移是可逆的：降级会删除三张新增表，并恢复既有 assessment operation action
   allow-list。未完成真实 HTTP、身份、Consent store 和生产接线前，本 ADR 和代码
   只能视为候选，不代表生产能力。

## Alternatives considered

### A：扩展现有 Assessment（采用）

保留 session/evidence/consent/audit/outbox 的同一条语义链，用户行为可以在结果投影
之后自然回读，且不会复制 FamilyNeed 或 Journey。

### B：新建独立的 support 或 engagement domain（否决）

会产生第二个家庭状态入口，重复 scope、删除和审计责任，并把一个首达行为拆成
多个无法原子回滚的系统。

### C：继续只用 Fake，待生产评审时一次性替换（否决）

Fake 无法证明重启后回读、数据库约束、租户隔离或 Audit/Outbox 原子性；把这些
问题留到最后会使 UI 的“完成”无法被真实环境复现。

## Consequences

### Positive

- 家长的“补充说明→今晚一小步→次日回访”可以跨请求、跨进程重启回读。
- 反馈不会被误写成事实；行为结果仍由家庭自己表达，不被 AI 自动判定。
- 迁移、SQL repository 和 Fake 共享同一组边界字段与事件名，便于 QA 做 parity。

### Open gates

- `family_api` 仍未把真实 SQL repository、真实身份和 Consent record store 接入默认
  生产路径。
- 真实 HTTP 浏览器场景、共享事务失败回滚和持久化数据库重启后的业务数据回读还需
  QA 在 clean checkout 中复验。
- 外部模型解释仍必须经 Model Gateway；本 ADR 不授权新增 AI provider 或自动写 Fact。

## Verification

- `tests/domains/assessment/test_support_card_action_loop.py`：Fake 场景覆盖反馈、
  幂等、跨家庭拒绝、当日回访拒绝和次日回访。
- `tests/domains/assessment/test_sqlalchemy_repository_integration.py`：真实 PostgreSQL
  repository 覆盖三类持久化行为、Audit/Outbox 回执和时间门（需显式数据库环境）。
- `database/migrations/versions/0004_assessment_support_loop.py`：upgrade、downgrade、
  re-upgrade 可逆性。

