---
id: ADR-0029
title: 三区方法论服务产品 AI 平台的领域边界与首个交付切片
status: proposed
date: 2026-08-30
owner: chief-architect
---

# ADR-0029：三区方法论服务产品 AI 平台的领域边界与首个交付切片

## 背景

Family 的三区方法论把同质区、优势区和独占区候选区分开。当前仓库已经有产品智能域
的产品设计实体骨架、服务域的预约/履约运行时以及 Principal/Model Gateway 原语，
但设计编译器、模拟器、知识治理和发布投影尚未形成闭环。若直接在服务域加入 AI
推荐接口，会混淆设计真相与交付事实，也会绕过 AI 原生原则、R7/R8/R9 和未成年人数据约束。

## 决策

1. 以 `backend/domains/product_intelligence` 作为服务产品设计主数据的唯一业务归属，
   不新建平行的 service-product domain。
2. 以 `backend/domains/service` 作为服务供给与交付事实的唯一归属；它只消费发布后的
   不可变 `ServiceBlueprintVersion` 引用。
3. 将确定性编译器与模拟器实现于 `backend/intelligence/design_copilot`，通过 Protocol
   接收设计投影，不运行时依赖领域实体，不直接连接模型供应商。
4. 所有服务产品 AI 用例必须经 Principal → Model Gateway → Schema/Provenance → Human Gate；
   AI 只产生 Draft、Recommendation 或 HumanTask。
5. 首个代码切片为“主数据扩展 + 12 项确定性编译器 + CompileRun/finding”，随后才做
   知识、模拟、发布接线和反馈学习。

## 结果

正向结果：领域边界清晰，编译可重放，发布可审计，服务历史不被新版本污染，三区方法论
能够沉淀为可复用蓝图资产。

代价：需要扩展现有轻量产品实体和仓储投影；现有 `packages/contracts/product_factory.py`
不能继续作为第二套业务真相，迁移期间只能作为兼容的传输契约并最终收敛。

## 不采用的方案

- 不在 `service` 域创建 AI 直接生成/修改服务产品的入口。
- 不把知识快照、Prompt 或模型响应当作产品事实。
- 不先做多 Agent 协同或家庭端自动售卖；这两者都超出首个服务产品设计切片。
- 不用满意度、成长结果或合成模拟结果生成家庭总分、家庭排名或疗效承诺。

## 验收与回滚

ADR 进入 accepted 前需产品、服务、教研、AI 治理和合规负责人联合评审。实现阶段若发现
产品设计实体与既有 canonical contract 冲突，回滚到 Draft-only 读路径，不迁移或覆盖
历史 ServiceCase；任何发布操作必须保留审计、幂等和版本校验和。

## 关联

- `docs/05_ai/SERVICE_PRODUCT_AI_PLATFORM_ARCHITECTURE_V1.md`
- `docs/05_ai/SERVICE_PRODUCT_DESIGN_AI_PLATFORM.md`
- `governance/REPOSITORY_CONSTITUTION.md` R2/R7/R8/R9/R14
