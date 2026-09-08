---
id: AI-AGI-VERTICAL-CONTRACTS-001
title: 家庭成长垂直 AGI Runtime 契约 V1
type: specification
status: draft
canonical: false
---

# 家庭成长垂直 AGI Runtime 契约

本文件是长期设计产物，不代表能力已实现。生产输出必须经唯一 Model Gateway，且只能产生 Draft。

## 能力原语

| 原语 | 输入 | 输出 | 禁止 |
|---|---|---|---|
| UNDERSTAND | FamilyContext, Observation[] | PerspectiveDraft | 写入 Fact |
| ASSESS | EvidenceSet, KnowledgeRef | AssessmentDraft | 临床诊断 |
| CLARIFY | QuestionState, GuardianReply | ClarificationDraft | 自动替 Guardian 决策 |
| MATCH_KNOWLEDGE | PublishedKnowledgeRef, Query | KnowledgeMatch[] | 使用未发布版本 |
| DESIGN_PATH | PerspectiveDraft, Decision[] | GrowthPathDraft | 自动执行高影响动作 |
| REFLECT | Outcome[], Feedback[] | ReflectionDraft | 改写历史事实 |
| LEARN | Feedback, Decision, Outcome | LearningSignalDraft | 自动更新模型权重 |

## Agent/Tool 契约

Agent 输入必须包含 `family_id`, `actor_id`, `context_snapshot_ref`, `knowledge_refs`, `request_id`。
Tool 输出必须包含 `status`, `payload`, `provenance`, `human_gate_required`；失败状态只能是 `FAILED_CLOSED`。

## 统一 provenance

所有 Observation、PerspectiveDraft、Decision、Fact、Outcome、Feedback 必须带：

`entity_id`, `version`, `family_id`, `scope`, `created_at`, `source_ref`, `actor_ref`, `request_id`, `model_ref`, `prompt_ref`, `schema_ref`, `knowledge_refs`, `decision_ref`。

其中 AI 生成对象的初始状态固定为 `DRAFT`；只有 Named Action + Human Gate 才能产生 Decision/Fact 变更。

## 运行时决策

- RAG：Knowledge 已发布且请求需要来源可追溯时使用。
- 微调：仅在有批准的标注集、隐私评估、离线回归收益时使用；当前 P0 不依赖微调。
- 规则/工作流：用于权限、状态机、幂等、Human Gate、成本和失败闭合；不得伪装成理解。

## 状态与闸门

`DRAFT → REVIEW_REQUIRED → ACCEPTED | MODIFIED | REJECTED | DEFERRED`。

四态决策必须持久化 `decision_ref`，重启后可改变后续问题、候选或路径；跨 scope 请求必须在授权层终止，且不得产生 provider invocation。

