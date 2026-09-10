---
id: ADR-0167
title: Family AGI Runtime 架构定位（Family Domain AGI Platform）
status: Proposed
date: 2026-09-10
owner: chief-architect
---

# ADR-0167：Family AGI Runtime 架构定位

## 决策

正式采纳用户提出的长期技术定位：**AiFamily = Family Domain AGI Platform**——
面向家庭成长领域的领域通用智能平台，而不是"很多AI功能拼起来的平台"。

**大模型是基础设施，不是核心**：不训练自研AGI大模型，模型经`Model Gateway`
可替换路由；AiFamily真正要建设的是模型之上的 **Family Intelligence
Runtime + Family World Model + Skill/Agent/Tool Network + Outcome
Learning System**。

## 与ADR-0158 / ADR-0162的关系（避免两份文档各说各话）

- **不取代**。ADR-0158记录的具体契约（`FamilyPathContext`/`PathDraft`/
  `PathFeedbackSignal`/`PathDraftPersistencePort`等）仍然有效，归入本ADR
  "Skill/Agent System"层下的一个具体实现（`path_orchestration`），本ADR
  只是给它一个更大的架构坐标，不改动其代码契约。
- ADR-0158的"唯一主线"（成人授权→家庭表达→AGI理解与因果假设→可修改方案→
  Guardian确认→低风险行动→结果回读→失败复盘）与本ADR的七步闭环
  （PERCEPTION→WORLD MODEL→GOALS→REASON&PLAN→ACT&COORDINATE→OBSERVE→
  LEARN）是**同一个闭环的两种表述**，以本ADR的七步闭环为准，ADR-0158的
  主线八段表格继续作为该闭环在"path_orchestration"这一具体切片上的落地
  追踪，不重复定义。
- ADR-0162的G0-G6生产就绪阶段门（证据等级纪律：fixture≠证据、内存
  ledger≠持久化证明等）作为**横切纪律**，适用于本ADR下所有子系统的推进
  ——本ADR定义"要建什么"，ADR-0162继续管"怎么证明建好了"。
- 本ADR新增的"Governed Autonomy"五级（回答→建议→生成计划→用户授权执行→
  低风险自主执行→专业监督）回答的是另一个正交问题——"允许AI自主到什么
  程度"，跟G0-G6"证明到了哪个阶段"并存，不是互相替代。

## Runtime 分层（简化版，完整版见用户原文档）

```
EXPERIENCE（App/Web/Voice/直播/设备）
RUNTIME（Perception/Understanding/Reasoning/Goal/Planner/Agent Loop/Reflection/Evaluation）
WORLD MODEL（Family Graph / Evidence Graph / Experience Graph / Service Graph / Skill Graph）
MEMORY（Working / Episodic / Semantic / Family State）
SKILL / AGENT SYSTEM（Assessment / Course / Coach / Expert / Community / Live / Navigator）
TOOL BUS（MCP / API / DB / Search / Payments / IoT）
AGENT NETWORK（A2A / External Agents）
MODEL GATEWAY（多provider路由，已有`backend/intelligence/model_gateway`）
SAFETY / GOVERNANCE / EVAL（Consent / Guardian / RBAC / Audit / Evals，已有多个域雏形）
```

## 五张世界模型图 —— 诚实现状核对（不是全部从零开始）

| 图 | 现状 |
|---|---|
| Family Graph | `Growth Graph`（PR#22刚接的hypothesis/action事件outbox）是雏形，远未到"state随时间演化"的完整家庭世界模型 |
| Evidence Graph | `backend/intelligence/knowledge/registry.py`（`KnowledgeRegistry`）是雏形——确定性发布/检索/证据等级门槛已具备，但内容为空（无真实审查知识） |
| Experience Graph | 未建立 |
| Service Graph | 未建立（`governance/CAPABILITY_REGISTRY.yaml`是平台自身能力登记，不是"谁擅长解决什么问题"的服务图） |
| Skill Graph | 刚起步——本轮`knowledge_candidate_source.py`+`candidate_explanation_adapter.py`是"检索到的知识→可执行候选"这一条窄切片，远未到完整Skill Package（课程=Human-readable Skill Package这个设计还未落地） |

## 五级AGI演进 —— 当前诚实定位

介于 **AGI-0（AI Assistant）与AGI-1（Family Copilot）之间**：
- 有真实模型调用（`GatewayBackedUnderstandAdapter`/`GatewayBackedCandidateExplanationAdapter`），但没有Family World Model、没有跨会话Memory、没有Goal Engine、没有Hierarchical Planner
- `path_orchestration`目前只是"读取一次context→打分→返回候选"，不构成AGI-1要求的"家庭画像+Memory+测评+课程+Tool Calling"完整闭环

## 不做的事（范围边界，不是留白）

- 不训练自研AGI大模型
- 不一次性搭建全部Runtime目录骨架（`family-intelligence-runtime/`下29个子目录）——空目录本身就是骨架冒充能力，是本ADR明确要避免的反面案例；目录结构按需在AGI-1目标驱动下逐个长出真实内容
- MCP/A2A暂不接入——本ADR记录方向（工具/多Agent协作走标准协议，不自建私有集成），实际接入时机等有真实的第三方Agent协作需求出现

## 下一步

邀请Codex在此ADR下回应/反驳——本ADR直接决定`path_orchestration`及其后续切片的架构坐标，不是单方面的技术决策。当前具体推进目标：把AGI-0→AGI-1的差距（Family World Model的最小雏形、跨会话Memory）列为下一个可验证增量，而不是继续在"回答变得更聪明"这个维度上打磨。
