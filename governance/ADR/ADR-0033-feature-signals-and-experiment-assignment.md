---
id: ADR-0033
title: 将体验指标与实验分流建设为独立的平台能力
status: proposed
date: 2026-08-30
owner: chief-architect
---

# ADR-0033：体验指标与实验分流独立于业务事实

## 背景

技术驱动的平台必须保留停留时长、完成率和交易金额等真实信号，并具备 A/B 与灰度能力。
这些信号如果直接写入家庭画像或推荐排序，会造成目的漂移；如果测试环境删掉，又无法验证
生产路径。数据架构已定义 `MetricDefinition`、`Experiment` 和
`ExperimentAssignment`，本 ADR 给出第一版运行契约。

## 决策

1. `FeatureSignal` 统一记录停留时长、完成率和交易金额，强制携带 scope、用途、粒度、
   provenance、幂等键和环境；dev/test/prod 只替换数据与外部适配器。
2. 金额信号只允许用于收入报表或容量规划；原始事件级停留时长不能直接调节推荐，必须先
   聚合为明确的体验/策略特征。
3. `ExperimentAllocator` 以租户/区域/家庭和策略版本做稳定哈希分流，生成可退出的家庭级
   `ExperimentAssignment`；不使用家庭之间的表现排序。
4. 未成年人数据不得进入 marketing/upsell/sales 实验；实验停止、退出和历史分配不可静默
   删除，后续由 Ops/Analytics 域接管持久化与投影。

## 架构对齐

- **业务/流程**：指标服务体验质量、成长采纳、服务质量和经营报表；实验只改变版本触达，
  不改变 Family/Journey/Service/Commerce 事实。
- **数据**：特征是派生数据，继承 tenant/region/family/subject/purpose/consent；实验分配
  对应 `experience_experiment_assignments`，可审计、可重放、可退出。
- **应用/技术**：`FeatureStore` 和 `ExperimentAllocator` 属于 ExperienceApplication 的
  A6 运行组件，后续接入 Outbox、在线/离线 Feature Store、AnalyticsOpsProjection 和灰度
  回滚；不调用模型供应商。

## 验收证据

- `backend/intelligence/experience/features.py`
- `backend/intelligence/experience/experiments.py`
- `tests/intelligence/experience/test_features_experiments.py`

当前实现为 dev/test 内存适配器，状态为 `proposed`，不宣称在线实验平台或生产特征存储已经
上线。
