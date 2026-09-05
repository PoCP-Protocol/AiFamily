---
id: ADR-0046
title: Bind ExperienceRun drafts to Human Gate Named Action requests
status: accepted
date: 2026-08-30
decision_owner: project-owner
supersedes: null
superseded_by: null
---

# ADR-0046：ExperienceRun 草案与 Human Gate 请求的作用域绑定

## 背景

`ExperienceRun` 已能以 append-only 事件和 checkpoint 记录一次多模态草案生成，
Human Gate 也能独立保存 proposal、真人 decision 和 `NamedActionRequest`。但两者
此前没有正式的关联边界：调用方可以把任意 `run_id` 放入 action arguments，且闸门
不会证明被审核的 `ModelDraft` 就是该 run 的 checkpoint 产物。重放或跨 run 串接时，
这会削弱可解释性和作用域隔离。

## 决策

1. 新增 experience→Human Gate bridge 作为非领域 adapter。提交 proposal 前必须满足：
   `DurableExperienceRun.state == SUCCEEDED`、存在 `DRAFT` checkpoint，且 checkpoint
   的 `draft_payload` 与传入 `ModelDraft.output` 完全一致。
2. bridge 要求 `GateScope` 的 tenant/family/subjects 与 run 完全相等，并要求
   `GateScope.correlation_id == run.request_ref`。不满足任一条件即 fail closed。
3. bridge 生成并覆盖两个只读绑定参数：`run_id` 为 run 的真实 id，
   `experience_run_ref` 为 `experience-run:{tenant}:{family}:{run_id}`。调用方提供的
   不同值拒绝，不能覆盖；accepted `NamedActionRequest` 必须保留这两个值和原 scope。
   这里的“不可伪造”指 adapter 控制派生和 drift rejection，不把该引用当作独立的
   认证凭据；真人和领域仍须执行自己的授权。
4. bridge 只委托现有 Human Gate，不写领域事实；`ACCEPT` 仍只返回请求，
   `REJECT`/`ESCALATE` 不产生请求。Human Gate 自身的 proposal-id replay 继续提供幂等。
5. 本 ADR 的第一步只提供可替换的 in-memory adapter seam。SQL Human Gate、Outbox
   和业务 Named Action 可复用同一绑定校验，但不在本 ADR 内改变其 schema 或事务边界。
6. 新增 provider-neutral `NamedActionRelay` outbox-consumer seam。只有已 ACCEPT 的
   `RunBoundNamedActionEnvelope` 才可发布；in-memory relay 按 `request_id` 幂等，
   相同内容重放为 no-op，内容冲突拒绝。relay 不执行领域命令，也不自动提交事务。

## 验收

- run 未成功、无 checkpoint、草案内容不等于 checkpoint、scope/correlation 不匹配、
  或伪造 `run_id`/`experience_run_ref` 均被拒绝；run 与 gate 状态不被部分修改。
- 同一 proposal 重放返回同一 HumanTask；真人 ACCEPT 的请求保留 run 绑定；
  REJECT/ESCALATE 返回 `None`。
- 同一 accepted request 通过 relay 重放返回同一 receipt；相同 request id 的不同
  scope/run_ref/provenance 内容被拒绝。

## 边界

`SUCCEEDED` 仍只表示草案生成完成，不表示任何家庭、成长、服务或商业事实已生效。
事实变更仍必须经过业务域自己的授权、同意、幂等、事务和审计。
