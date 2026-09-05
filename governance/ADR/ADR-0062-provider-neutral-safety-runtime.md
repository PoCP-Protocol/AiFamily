---
id: ADR-0062
title: Provider-neutral AI safety pre/post runtime
status: Accepted
date: 2026-08-30
owners: [ai-architecture]
---

# ADR-0062：Provider-neutral Safety Runtime

## 背景

Model Gateway 负责供应商准入和结构化生成，但 AI 请求还需要统一执行未成年人、
高影响动作和 R9 禁止字段约束。若这些检查散落在各个 Agent 或 UI，测试环境与
生产环境会产生不同的安全行为。

## 决策

新增 `backend/intelligence/safety`，提供纯函数式 `SafetyRuntime`：

1. 输入侧检查禁止用例和家庭总分/排名等结构化字段；
2. 输出侧强制 `ModelDraft` 且 `may_mutate_business_state=false`；
3. 高影响用例或未成年人主体统一返回 `REVIEW` 并要求 Human Gate；
4. 禁止用例返回 `BLOCK`，不调用模型、不写业务事实。

供应商特定的内容安全能力仍由 Model Gateway adapter 提供，不能替代本层的确定性
治理规则。

## 后果与缺口

测试和生产共享同一 Safety port，安全结果可审计、可回放；当前仍需将其接入
真实 Model Gateway/Agent composition root，并补充持久化安全决策与人工复核反馈。

