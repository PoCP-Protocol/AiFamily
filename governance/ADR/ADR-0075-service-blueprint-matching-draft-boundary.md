# ADR-0075: Service Blueprint matching draft boundary

- 状态：Accepted for experiment
- 日期：2026-08-30
- 范围：`backend/intelligence/intervention/blueprint_matching.py`

## 决策

Blueprint 的权威对象仍由 `product_intelligence`/`service` 业务域管理。AI 侧只接收已发布 BlueprintVersion 的只读快照，匹配 `primary_contradiction_ref` 后输出 `BlueprintRecommendation`。推荐固定为 `DRAFT`，保留 evidence refs，不创建、修改、发布或执行 Blueprint。

未成年人数据和高影响场景自动进入 Human Gate 标记；`to_pending_named_action` 只生成 `PROPOSE_SERVICE_BLUEPRINT` pending Named Action，不执行任何命令。真实模型推理仍必须经 Model Gateway 和 Evaluation/Release Gate，只有人工确认后的 Named Action 才能进入服务域命令路径。
