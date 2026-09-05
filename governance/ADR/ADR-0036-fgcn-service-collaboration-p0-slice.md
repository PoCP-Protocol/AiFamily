---
id: ADR-0036
title: FGCN P0 服务协作链先实现影子分配与人工确认边界
status: accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0036：FGCN P0 服务协作链先实现影子分配与人工确认边界

## 背景

数据库 baseline 已有 `service_cases`、`service_tasks`、`task_assignments`、
`service_contributions` 和 allocation 相关表，但 Python 服务域只有预约子链。
如果直接把这些表当作“能力已完成”，会掩盖六条 FGCN 运行规则、AI 人工闸门和
贡献/资金分离尚未在业务代码执行的事实。

## 决策

新增 `backend/domains/service/fgcn`，先落地一个不产生外部副作用的 P0 运行时：

1. 案件必须引用 `PUBLISHED` 的蓝图快照；任务只能来自快照中的模板，并冻结验收标准。
2. 任务分配只接受 Human Gate 产生的 `CONFIRM_SERVICE_TASK_ASSIGNMENT` 请求，且再次校验
   租户、家庭、主体、用途、同意版本和真人 Actor。
3. 每个任务最多一个有效 `ACCEPTED` 责任人；交付必须带凭证引用；只有通过质量验收的
   交付才能形成 `ServiceContribution`。
4. 案件关闭后只允许运行一次 100 单位影子分配：固定池为 20/15/15/10，交付资源池
   40 按已验证贡献对应任务权重拆分。结果是分配依据，不是支付、佣金、钱包或结算。
5. 每个事实变更都通过 `AuditRecorder` 记录；所有拒绝路径保持 fail closed。
6. 第一版使用 `InMemoryFGCNEngine` 形态的 `FGCNEngine` 作为契约实现。接入 SQLAlchemy、
   事务、workflow worker、资源准入和争议裁决前，不标记为生产能力。

## 正向与反向验收

正向：`ModelGateway → ModelDraft → HumanTask → NamedActionRequest → TaskAssignment →
Delivery → QualityReview(PASSED) → ServiceContribution → AllocationStatement(100)`。

反向：未发布蓝图、未配置任务、跨家庭/租户/主体请求、第二责任人、未分配交付、同人验收、
非通过质量状态、未验收贡献、未完成案件、二次 allocation 和重复/冲突幂等键均不能越过边界。

## 后续接入

下一步由 service 域提供正式 repository/UnitOfWork 和 API/worker 适配器，把本 ADR 的
不变量映射到 baseline 表，并在同一事务中提交领域事实与审计；随后再实现返工、质量池释放、
争议裁决和真实资金通道。AI 仍只负责推荐，不能绕过 Human Gate 或直接写入上述事实。
