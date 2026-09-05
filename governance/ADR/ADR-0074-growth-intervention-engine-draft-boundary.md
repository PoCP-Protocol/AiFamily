# ADR-0074: Growth Intervention Engine draft boundary

- 状态：Accepted for experiment
- 日期：2026-08-30
- 范围：`backend/intelligence/intervention`

## 决策

Growth Intervention Engine 消费已验证的 `hypotheses`、`action_candidates`、Context Snapshot 引用和证据引用，输出 `InterventionDraft`。引擎只做主要矛盾筛选、置信度排序和人工闸门标记，不调用供应商、不写 Family/Journey/Service/Commerce 事实。

所有候选固定为 `DRAFT`，必须带 evidence refs；未成年人数据或高影响场景自动标记 `human_gate_required`。`to_payload()` 是 Experience/UI 的受限投影，禁止把候选升级为最终决策。

## 取舍

本轮不创建新的 GrowthProblemModel，也不把置信度当成家庭评分/排名。后续接入真实模型时仍必须经 Model Gateway，并通过 Evaluation/Release Gate；人工确认后的 Named Action 才能进入业务域命令路径。
