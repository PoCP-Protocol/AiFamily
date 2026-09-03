# ADR-0073: Growth Graph read projection runtime

- 状态：Accepted for experiment
- 日期：2026-08-30
- 范围：`backend/intelligence/growth_graph`

## 决策

Growth Graph 不是业务域，也不拥有 Family/Journey/Service/Commerce 事实。业务域事件由 worker 投影为 `GrowthGraphEdge`，AI 侧只通过 `GrowthGraphQueryPort.query` 读取。投影保存事件引用、证据引用、关系、作用域和保留期，不保存原始 payload 或模型输出。

`GrowthGraphOutboxConsumer` 从现有 Experience Outbox 重建受治理 `ExperienceEvent`，仅投影事件/节点/证据引用；`SqlAlchemyGrowthGraphProjection` 提供稳定指纹幂等投影、严格作用域/同意/期限查询，以及按主体的级联删除证明。Alembic `0023_ai_growth_graph_projection` 创建投影表和删除证明表。

## 边界

本轮不伪造全域 DomainEvent，也不引入图数据库或 embedding。生产接入必须由 workflow worker 消费已治理 outbox，并使用只读投影数据库权限；任何检索排序仍需 evidence/provenance 约束和独立评测门禁。
