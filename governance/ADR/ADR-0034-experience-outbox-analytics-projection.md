---
id: ADR-0034
title: 体验信号通过 Outbox 投影到 Analytics 读模型
status: proposed
date: 2026-08-30
owner: chief-architect
---

# ADR-0034：体验信号通过 Outbox 投影到 Analytics 读模型

## 背景

推荐、特征和实验不能只存在于请求进程，否则重试、宕机和跨环境验证都会产生不一致。
数据架构已经要求事件信封、Outbox、AnalyticsOpsProjection 和可重放；当前体验层只有
内存 Gateway、Feature Store 和 ExperimentAllocator，需要补齐运行时骨架。

## 决策

1. `InMemoryExperienceOutbox` 接受体验事件、推荐决定、反馈、特征信号和实验分配，按租户
   幂等键追加；相同记录重放返回原消息，冲突拒绝。
2. `AnalyticsProjection` 只消费 Outbox 消息，按精确 scope 聚合特征、统计交互事件并保存
   实验分配；同一消息重复投影不重复计数。
3. 只有投影成功后才标记消息 published；投影失败保留 pending，供 Worker 重试。
4. 读模型不合成家庭分数、不跨租户/区域/主体 join，也不把金额或停留时长直接提升为家庭
   价值判断。
5. 当前实现是 dev/test 适配器；生产替换为事务数据库、Outbox Worker 和 Analytics
   Projection，不改变输入输出契约或三环境功能路径。

## 架构对齐

- **技术架构**：事件驱动、可重放、失败可重试，符合 `family_api` → Outbox → Worker →
  Projection 的进程边界。
- **业务/流程**：体验信号只为触达、推荐、反馈、运营分析提供证据，不创建 Family/Journey/
  Service/Commerce 事实。
- **数据**：继承事件信封的 tenant/region/family/subject/purpose/consent/provenance/
  idempotency，投影为派生读模型。
- **应用**：`ExperiencePipeline` 是 ExperienceApplication 的 A4/A6 运行骨架，后续由
  OperationsGovernanceApplication 接管 Metric/Experiment/Decision 的正式主数据。

## 验收证据

- `backend/intelligence/experience/pipeline.py`
- `tests/intelligence/experience/test_pipeline.py`
- `tests/intelligence/experience/test_features_experiments.py`

当前状态为 `proposed`，内存实现不能宣称生产级消息中间件或分析仓库已经上线。
