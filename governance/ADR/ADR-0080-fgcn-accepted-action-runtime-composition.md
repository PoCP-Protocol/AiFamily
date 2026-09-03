# ADR-0080: FGCN accepted-action runtime composition

- 状态：Accepted for experiment
- 日期：2026-08-30
- 范围：`backend/apps/family_api/accepted_action_wiring.py`

## 决策

在应用组合根提供 `FGCNAcceptedActionRuntime`，由部署注入
`async_sessionmaker`、workflow worker identity 与 provider admission boundary。
每次 bounded scheduler 运行使用新的 SQL session，并在同一 session 中组装
Human Gate、accepted-action delivery ledger、FGCN repository、Blueprint proposal
store 与 dispatcher worker。

队列读取以 Human Gate 的 accepted candidate 为源，再用 delivery ledger 过滤
`SUCCEEDED`/`DEAD_LETTERED` 终态，避免已完成动作被无限重复轮询。运行时同时提供
metadata-only dead-letter 查询；不返回 action payload、模型原文或家庭总分/排名。

## 结果

staging 与 production 使用同一组装路径，只替换显式依赖，不因为测试环境而删减
Human Gate、幂等、审计、重试、接管或 Blueprint 提案能力。真实部署仍需接入持久化
调度器、worker 身份和 provider admission 实现。
