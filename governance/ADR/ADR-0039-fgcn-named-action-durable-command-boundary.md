---
id: ADR-0039
title: FGCN Named Action 经同事务应用命令落成持久化分派
status: accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0039：FGCN Named Action 经同事务应用命令落成持久化分派

## 背景

ADR-0037 只建立了 FGCN 的 SQLAlchemy durable repository seam，ADR-0034 的
Human Gate 只返回 `NamedActionRequest`。两者之间如果没有应用命令，系统仍
停在“人工已接受、业务事实未落库”，重启后无法恢复分派结果。

截图中的 FGCN 目标链要求“资源匹配与授权”之后才进入交付；AI 只能给出
推荐草案，不能直接写入责任人事实。因此需要一个窄的、可审计的域命令边界。

## 决策

1. `execute_task_assignment_named_action` 是 P0 唯一把
   `CONFIRM_SERVICE_TASK_ASSIGNMENT` `NamedActionRequest` 转为持久化
   `TaskAssignment` 的应用命令。
2. 命令必须重新校验 Human Gate scope（tenant、family、subject、purpose、
   consent version、correlation），并拒绝 AI/system actor、终态案件和非
   `PENDING` 任务。
3. 命令在同一个 repository session 中依次写入任务、分派和必要的案件状态，
   通过同一事务 flush `AuditEvent` 后只 commit 一次。AI draft、proposal、
   decision 仍不是业务事实。
4. `NamedActionRequest.request_id` 是 P0 durable replay key；数据库以非空
   partial unique index 防止并发生成第二个 assignment。相同请求的重放返回原
   assignment，不新增状态或审计；同一 request id 的 assignment-relevant 内容
   变更必须拒绝。HumanTask 本身仍未持久化，因此 gate proposal/provenance 的
   完整重放比对仍是后续工作。

## Alternatives Considered

### 方案 A：继续只调用内存 `FGCNEngine`

支持理由：已经有完整 P0 状态机测试，改动最小，适合先验证业务规则。

否决理由：进程重启会丢失人工确认后的 assignment；不能作为平台事实入口。

### 方案 B：在 API 路由里直接写 `TaskAssignmentRow`

支持理由：可以快速暴露一个可调用端点，减少应用层代码。

否决理由：会绕过 FGCN 领域重校验、AuditRecorder 和统一事务边界，也会把
请求体变成伪造 actor/scope 的入口。API/worker 应调用本 ADR 的应用命令。

### 方案 C：由 Human Gate 直接导入 service repository 并写事实

支持理由：人工接受后可以立即完成业务动作。

否决理由：破坏 AI Runtime 与业务域边界；Human Gate 的职责是产出
`NamedActionRequest`，业务域必须拥有自己的授权、事务和状态机。

## 正向与反向询证

正向：已写入的 case/task + Human Gate 接受请求，经命令后可在新 session
加载 assignment、任务责任人、案件状态和三条审计事件。

反向：跨 family、跨 correlation、AI/system 确认、终态案件、已分派任务、
请求内容篡改、重复 source request id 都不能写入第二条分派；审计 flush 或
commit 不成功时，调用方事务不得被当作成功。

## Consequences

### 正面

- 人工确认后的 assignment 有 durable 结果，可在新 session 中重建任务责任人与案件状态。
- 业务事实和审计事件共享一次提交，重复请求不会制造第二个责任人。
- 应用命令保持窄边界，AI 仍然只能生成 draft/recommendation。

### 负面 / 代价

- 必须先执行 0004、0005 migration；旧库不能加载 P0 ORM。
- 当前 `InMemoryHumanGate` 仍无法在重启后恢复 proposal/decision/provenance。
- 并发冲突仍由数据库约束兜底，细化为可读领域错误需要后续 worker/异常适配。

## Enforcement

- `tests/domains/service/fgcn/test_persistence.py` 验证 durable round-trip、精确重放、scope/actor 拒绝和审计失败回滚。
- `TaskAssignmentRow` 与 Alembic 0005 的 partial unique index 防止非空 request id 重复。
- `governance/CAPABILITY_REGISTRY.yaml`、`DOMAIN_REGISTRY.yaml` 和
  `MIGRATION_MANIFEST.yaml` 登记实现与缺口。
- 当前尚无生产 FastAPI caller；ADR-0040 提供了 one-shot worker handler，但常驻
  worker/lease 与生产 wiring 仍是未完成状态。

## References

- `governance/ADR/ADR-0034-ai-human-gate-named-action-bridge.md`
- `governance/ADR/ADR-0037-fgcn-durable-persistence-seam.md`
- `governance/ADR/ADR-0038-fgcn-contribution-delivery-provenance.md`
- `backend/domains/service/fgcn/application.py`
- `database/migrations/versions/0005_fgcn_assignment_request_idempotency.py`

## 边界

本 ADR 不实现持久化 HumanTask、通知/超时 worker、FastAPI 路由、重启时的
完整 engine rehydration、资源准入、返工、争议、质量池释放、支付或资金结算。
它也不放行任何外部模型供应商；模型调用仍只能经 Model Gateway，当前测试
使用 fake adapter 不能证明生产 AI 供应商已可用。
