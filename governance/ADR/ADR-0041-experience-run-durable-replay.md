# ADR-0041：ExperienceRun 持久化与可重放执行边界

- 状态：Accepted
- 日期：2026-08-30
- 决策人：AiFamily AI 架构负责人
- 范围：`backend/intelligence/experience/`

## 背景

多模态体验链路包含 Context Snapshot、模型路由、Model Gateway、草稿生成和人工闸门。它可能跨越多个请求、模型重试和 worker 重启。仅保存在进程内会导致重复生成、状态丢失和无法解释，因此需要可恢复的 `ExperienceRun` 执行记录。

## 决策

1. `ExperienceRun` 采用 append-only event log + checkpoint 的持久化形态；读取侧通过重放事件得到运行快照。
2. 运行记录必须带 `tenant_id`、`family_id`、`subject_ids`、`request_ref` 等作用域，任何跨租户/家庭/运行的读取或写入都 fail-closed。
3. 事件和检查点使用幂等键。相同键相同内容的重放是 no-op；相同键不同内容必须拒绝，避免 silent overwrite。
4. checkpoint 中的模型结果只能是 `DRAFT`，媒体和大对象只能保存 opaque reference；ExperienceRun 不拥有家庭、成长、服务或商业事实，也不直接写这些领域表。
5. SQLAlchemy adapter 是可替换的基础设施 seam；测试使用 SQLite 元数据路径，生产由 Alembic/PostgreSQL 提供同构表结构。
6. 人工确认与 Named Action 仍是唯一事实变更入口；ExperienceRun 的 `SUCCEEDED` 只表示草稿生成完成，不表示业务事实已生效。

## 后果

- 优点：支持 worker 重启后的重放、幂等重试、审计追踪和故障恢复，并保持 AI 与领域事实隔离。
- 代价：需要额外的事件/检查点表、版本控制和清理策略；不能把进程内对象直接当作生产存储。
- 未决项：本 ADR 不决定具体供应商、消息队列或长期归档介质；这些由 Model Gateway 和数据治理 ADR 分别决定。

## 验证

- `tests/intelligence/experience/test_runs.py`：状态机与重放不变量。
- `tests/intelligence/experience/test_run_store.py`：SQLAlchemy round-trip、作用域隔离、幂等冲突和 DRAFT-only。
- `uv run alembic heads`：持久化迁移保持单一 head。
