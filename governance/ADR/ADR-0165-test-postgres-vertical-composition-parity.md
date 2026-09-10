---
id: ADR-0165
title: Test PostgreSQL 与生产 Vertical Composition 同构
status: Proposed
date: 2026-09-10
owner: chief-architect
---

# ADR-0165：Test PostgreSQL 与生产 Vertical Composition 同构

## Decision

当 `AIFAMILY_ENV=test` 同时配置 PostgreSQL `DATABASE_URL` 时，`family_api`
不得安装内存/合成的 vertical family-growth runtime。只有显式传入
`ProductionVerticalFamilyGrowthComposition` 才安装 durable runtime；否则 canonical
vertical routes 保持 503 fail-closed。

没有显式 PostgreSQL 时，test/dev 仍可使用合成 runtime 进行快速契约测试。这样
测试环境一旦选择真实数据库，就不会出现“数据库是生产形态、AI runtime 却是内存
fixture”的混合状态。

此外，staging/production composition 的 scope factory 返回 `SYNTHETIC` 数据分类
时，在创建 Context snapshot 前即 fail closed；合成数据不能穿过生产组合根。

staging/production 的显式 composition 还必须携带 live Consent port；缺少实时
同意检查的 runtime 在组合构造阶段直接拒绝。

## Consequence

真实 PostgreSQL 测试必须显式构造同一 session factory、durable Context、durable
Experience Ledger、scope resolver 和已准入 Gateway 的 composition。该门槛提高了
测试启动成本，但使 test/staging/production 的依赖形状一致。
