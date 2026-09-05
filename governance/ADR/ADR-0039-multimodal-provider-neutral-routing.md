---
id: ADR-0039
title: 多模态模型采用供应商无关的能力路由
status: proposed
date: 2026-08-30
owner: chief-architect
---

# ADR-0039：多模态模型采用供应商无关的能力路由

## 背景

AiFamily 需要图片、音频、视频和文本理解来支撑测评解释、成长规划、陪伴和复盘。
Qwen、豆包、Gemini 等模型在中文体验、延迟、价格、区域和数据处理条款上各有差异，
不能因为一次报价或单次 Demo 就把业务代码绑定到某一家。平台还必须满足 R7（供应商
调用集中到 Model Gateway）、R8/R9（人工确认与事实边界）以及未成年人数据的委托、
转委托、删除和区域约束。

## 决策

1. 业务用例只声明能力需求：模态集合、数据分类、环境、结构化输出、延迟/成本预算和
   路由策略，不声明供应商 SDK 或 URL。
2. `MultimodalRouter` 只负责候选能力匹配、预算过滤、确定性排序和安全的 provenance
   输入；真正的网络调用仍只能由 `backend/intelligence/model_gateway` 完成。
3. 每个候选供应商必须先有 Provider Registry 的状态、区域、安全评估、处理协议、转
   委托结论和删除承诺。`TECHNICALLY_VALIDATED` 只能用于隔离技术评测，不能接收家庭或
   未成年人数据；未完成准入时路由必须 fail-closed。
4. Qwen 与豆包作为第一批候选进入同一 gold set 和同一 schema 的离线评测；Gemini 等
   后续供应商沿用同一契约。评测结果只能形成 `PILOT_CANDIDATE` 证据，不能自动成为生产
   准入决定。
5. 测试环境与生产环境使用相同路由、schema、错误语义、权限、同意、审计和人工闸门；
   测试环境只允许使用 Fake/隔离 adapter 或经审批的 sandbox，不能删掉多模态路径。

## 当前实现与缺口

- `backend/intelligence/experience/multimodal_routing.py` 已提供候选能力声明、成本/延迟
  策略、数据分类和 fail-closed 路由；Qwen/Doubao 当前均为 `TECHNICALLY_VALIDATED`，
  不可接收真实家庭数据。
- `backend/intelligence/experience/multimodal_eval.py` 已提供本地、无媒体内容的 GoldCase
  评测 runner，覆盖 schema、拒绝、安全、provenance、延迟和成本汇总。
- 尚缺供应商法务/安全审查、真实 sandbox adapter、持久化 trace/cost、Context Broker 接线、
  Human Gate 纵向流程和至少一条 UI-03→UI-05→UI-09 的可调用 API；因此本 ADR 不代表任何
  外部模型已经获准生产使用。

## 验收证据

- `tests/intelligence/experience/test_multimodal_routing.py`
- `tests/intelligence/experience/test_multimodal_eval.py`
- `docs/11_delivery/AI_MULTIMODAL_EXPERIENCE_AGILE_BACKLOG_V1.md`

当前状态为 `proposed`。下一次决策评审必须附 gold set 报告、供应商委托/转委托结论、
DPIA/删除证明和 sandbox/staging parity 证据，才能将候选提升为可调用状态。
