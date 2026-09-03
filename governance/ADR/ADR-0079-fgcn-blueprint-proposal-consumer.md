# ADR-0079: FGCN Blueprint proposal consumer

- 状态：Accepted for experiment
- 日期：2026-08-30
- 范围：`backend/domains/service/fgcn/blueprint_proposal.py`

## 决策

FGCN 注册 `PROPOSE_SERVICE_BLUEPRINT` accepted-action handler。Human Gate 接受后，
handler 将 evidence-bound 的 Blueprint recommendation 写入
`family_service_blueprint_proposals`，以 `request_id` 做租户内幂等，并记录
`accepted_by_actor_id`、scope、provenance、contradiction/action/evidence refs。

## 明确不做的事

该动作只确认“提案已被人工接受”，不等于打开 `ServiceCase`，不分配服务提供者，
不预约时段，不通知外部系统，不支付，不写成长事实。后续 `OPEN_SERVICE_CASE` 仍须
单独通过 Growth intent、consent、entry dependency 和 FGCN case command。

## 结果

AI Intervention → Human Gate → Accepted Named Action 的 Blueprint 分支不再因未注册
动作进入死信，同时保持服务域对业务事实、审计和事务的唯一所有权。表中只保存引用和
结构化元数据，不保存模型原文、媒体字节或家庭总分/排名。
