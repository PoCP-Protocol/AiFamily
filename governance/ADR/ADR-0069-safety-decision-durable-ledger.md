# ADR-0069：SafetyDecision 持久化与 fail-closed 事务边界

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/intelligence/safety/persistence.py`、Model Gateway

## 决策

每次 Model Gateway 请求都在输入和结构化输出阶段执行 Safety Runtime。若配置了
SafetyDecision sink，Gateway 保存 `stage/status/risk_level/reasons/use_case/data_class`
等策略元数据；不保存原始家庭文本、完整 prompt、媒体字节或模型输出。

生产组合根必须把 `SqlAlchemySafetyDecisionSink` 与 Model Attempt、ModelDraft、AgentRun/
Trace 绑定到同一个请求级 `UnitOfWork`。Safety 记录写入失败时 Gateway 以
`POLICY_REJECTED` fail-closed，禁止模型外呼或发布不完整的 Draft。

## 结果

- 安全判定可按 request/stage 回放，支持人工复核、事故调查和删除审计。
- 测试环境可使用 `InMemorySafetyDecisionSink` 或 SQLite/PostgreSQL adapter，但仍执行
  相同的判定顺序和失败语义。
- 供应商 moderation、人工反馈闭环以及 retention/deletion worker 仍属于后续部署能力，
  不得用本地 sink 冒充生产合规完成。
