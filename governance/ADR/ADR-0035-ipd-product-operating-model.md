---
id: ADR-0035
title: 采用 IPD 作为 AiFamily 产品与研发运营主流程
status: proposed
date: 2026-08-30
owner: chief-architect
---

# ADR-0035：采用 IPD 作为 AiFamily 产品与研发运营主流程

## 背景

`docs/03_product/FUNCTIONAL_DECOMPOSITION.md` 已盘点 9 个一级域、24 个二级能力群、58 个
三级功能和 79 个四级操作，但“已实现可用”只有 11 项（13.9%）。继续按 UI 逐屏开发会
把渠道投影误当产品需求，无法建立市场证据、版本边界、跨职能责任和发布质量证据。

## 决策

1. 采用 IPD 的 MM → CDCP → PDCP → ADCP → LDCP → GA → Lifecycle 作为产品与研发共同主流程。
2. 将 34 个 UI 编号定义为渠道投影 ID；以 `IPD-{product}-{capability}-{feature}-{operation}`
   作为需求主键，需求必须绑定 ProductCharter、版本、Domain Owner、接口和验收测试。
3. 将平台重组为 Family Growth Core、Service Collaboration、Commerce Relationship、
   Community Trust、Principal & AI Runtime、Platform & Operations 六条产品线；首个版本
   聚焦 UI-02 → UI-03 → UI-05 → UI-09 的 Family Growth Core 纵向切片。
4. IPMT 决定产品组合和 Gate；PDT 负责跨职能实现；领域 Owner 仍是业务事实唯一写入方；
   SharedApplicationKernel 统一接入 identity、authorization、consent、idempotency、
   transaction、audit、outbox。
5. 停留时长、完成率、交易金额和实验分配作为正式平台信号保留，但必须带 purpose、粒度、
   同意、版本和环境，不能合成家庭/儿童排名或绕过商业/人工闸门。

## 结果

正向结果：产品、流程、数据、应用和技术有共同版本边界；需求优先级可以由客户价值和证据
决定；开发、测试和生产共享同一能力路径；技术平台（事件、特征、实验、AI、观测）能够
形成复利。

代价：需要补齐 MRD、ProductCharter、PRD、ReleaseBaseline、Gate、MetricDefinition 和
LifecycleDecision 等治理对象；早期会减少并行 UI 数量，但能降低返工和静态假成功。

## 不采用的方案

- **继续按 UI 编号逐屏开发**：启动快，但无法表达产品价值、依赖、版本和发布责任。
- **只做技术平台后再找业务**：能快速堆事件/模型，却可能没有客户问题和可验收结果。
- **把 IPD 变成重审批瀑布流程**：不符合轻内核原则；本决策采用小批量、短 Gate、可回滚的
  PDT 迭代，而不是一次性大项目。

## 执行与验收

- 产品蓝图：`docs/01_strategy/AIFAMILY_IPD_PRODUCT_SYSTEM_REDESIGN_V1.md`；
- 首个版本必须产生 ProductCharter、需求基线、版本计划和 G0-G4 证据；
- 架构测试继续验证 Domain Owner、AI Gateway、R9、Outbox、环境等价和租户隔离；
- 当前 ADR 状态为 `proposed`，在 IPMT/产品/研发/教研/合规评审前不宣称 IPD 已正式运行。
