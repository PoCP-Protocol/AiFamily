# ADR-0065：Model Gateway Attempt 持久化

## 状态

Accepted — 2026-08-30

## 背景

Model Gateway 已在外呼前创建 Attempt，但默认的 `InMemoryAttemptSink` 随进程重启丢失。AI 生产运行需要知道哪些请求已经离开系统、是否超时、由哪个模型响应以及失败原因，不能只保留成功草案。

## 决策

1. 新增 AI-runtime-owned 表 `ai_model_attempts`（migration 0017）及 `SqlAlchemyAttemptSink`。
2. Sink 在 provider 调用前写入 `STARTED`，在返回/超时/schema/safety 失败后写入 `SUCCESS` 或 `FAILURE`，保留 provider、use case、data class、environment、route、request/session、model、latency 与 failure kind。
3. Gateway 的 AttemptSink 协议同时支持同步和 awaitable 实现；调用链统一 `await` 异步 sink，原有内存测试实现无需改造。
4. Sink 只 `flush`，不 `commit`；生产组合根负责把 Attempt 与 ModelDraft、Trace、Outbox 放进同一事务，失败时整体回滚。
5. 生产默认不得依赖进程内 sink；在最终 composition root 完成 `SqlAlchemyAttemptSink` 注入前，运行状态保持 EXPERIMENT，不宣称生产观测已完成。

## 验证

- `tests/intelligence/model_gateway/test_attempt_persistence.py`
- `uv run pytest tests/intelligence/model_gateway -q`
- `uv run alembic heads` → `0017_ai_model_attempts`

