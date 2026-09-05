---
id: ADR-0038
title: FGCN 贡献必须保留交付来源
status: accepted
date: 2026-08-30
decision_owner: project-owner
---

# ADR-0038：FGCN 贡献必须保留交付来源

## 背景

FGCN 的贡献事实只能由通过验收的交付产生。历史
`service_contributions` 表只保留了案件、任务、提供方和质量状态，没有保留
`delivery_id`。如果直接把 `ServiceContribution.delivery_id` 丢弃，进程重启后就
无法证明贡献来自哪一次交付，也无法可靠拒绝同一交付被重复记账。

## 决策

1. 在 `0004_fgcn_p0_persistence` 增加可空的 `service_contributions.delivery_ref`；
   历史行没有 P0 来源时保留为空，但通过 FGCN P0 Repository 新写入的贡献必须有值。
2. 对非空 `delivery_ref` 建唯一索引，仓储层同时校验任务已 `VERIFIED`、交付凭证存在、
   提供方与责任人一致、案件范围一致且质量状态为 `VERIFIED`。
3. FGCN Repository 的加载路径也必须重新验证这些关系；不能因为数据库里有一行就把
   它提升成可信业务事实。

## 正向与反向验收

正向：交付凭证 → 通过质量验收 → 贡献落库；重启后加载贡献仍能得到同一个
`delivery_id`，allocation 可以使用该贡献作为依据。

反向：缺失或错误交付来源、未验收任务、跨案件/跨提供方引用、同一交付第二条贡献、
篡改后的贡献行均 fail closed。

## 边界

这只是 FGCN 事实可追溯性修正，不是支付、佣金、钱包、结算或质量争议功能；真实
`service_deliveries` 独立表和生产 API/worker 仍按 ADR-0037 的后续边界处理。
