---
id: ADR-0057
title: ToolCall 结果以待人工确认状态进入 Durable Outbox
status: Accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0057：ToolCall 结果以待人工确认状态进入 Durable Outbox

## 背景

Tool Runtime 已经能够生成带 scope/provenance 的 `ToolCallResult`，但进程
内结果会在重启、多实例或 Human Gate worker 暂时不可用时丢失。直接把
`PendingNamedAction` 交给领域服务又会模糊“候选动作”和“已接受 Named
Action”的边界。平台需要一条可重放、可审计且不执行命令的耐久化投递链。

## 决策

1. 在 `backend/intelligence/tool_runtime/action_outbox.py` 建立
   `ToolActionOutboxEnvelope`、`ToolActionOutboxStore` 和
   `SqlAlchemyToolActionOutbox`。Envelope 只接受 `ToolCallResult`，并把
   action、`GateScope`、provenance、risk、创建/过期时间和 schema version
   编码为 JSON；不包含人类 decision、actor 或 domain execution handle。
2. Outbox 以 `(tenant_id, call_id)` 作为幂等身份，保存稳定内容指纹。重复
   调用若只改变运行时生成时间戳则返回原记录；action、scope、provenance
   或状态发生变化即 fail-closed。`status` 的数据库约束固定为
   `PENDING_HUMAN_CONFIRMATION`，不得伪装成已接受动作。
3. 复用 `ExperienceOutboxWorker` 的 at-least-once worker seam：先投递给
   注入的 Human Gate inbox consumer，成功后才 `mark_published`；异常保留
   pending 或进入 DLQ。Tool Action outbox 不导入业务域、不调用模型供应商，
   SQL adapter 只 `add`/`flush`，事务由 composition root 管理。
4. 当前 migration 为 `0014_tool_action_outbox`。生产组合根还必须接入真实
   Human Gate inbox、并发租约/attempt 计数、durable DLQ 和领域侧二次授权；
   本 ADR 不授权任何自动执行路径。

## 后果

- ToolCall 在进程重启、重复投递与 worker 重试时仍可恢复，审计能看到原始
  家庭/主体范围和来源链。
- 测试与生产可共享同一 envelope、幂等和人工闸门前状态；仅替换数据库和
  inbox/DLQ 适配器，保持功能 parity。
- 额外引入一张 AI runtime 元数据表和 migration；在 migration 被 Git 跟踪
  后必须通过 PostgreSQL upgrade→downgrade→upgrade 门禁。

## 约束依据

- `governance/REPOSITORY_CONSTITUTION.md` R6、R7、R8、R9、R10
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §3.5、§4
- `governance/ADR/ADR-0051-experience-outbox-worker.md`
- `governance/ADR/ADR-0054-governed-tool-runtime-human-gated-actions.md`
