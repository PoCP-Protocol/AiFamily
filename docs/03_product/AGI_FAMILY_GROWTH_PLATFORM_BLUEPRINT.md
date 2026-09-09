---
id: PRODUCT-BLUEPRINT-AGI-FAMILY-001
title: AiFamily AGI 原生家庭成长平台蓝图
type: product-blueprint
status: draft
owner: chief-architect
created: 2026-09-08
updated: 2026-09-08
canonical: false
---

# AiFamily AGI 原生家庭成长平台蓝图

> 本文件是总控用于组织研发的目标态蓝图，不是实现证明。当前实现必须以
> `docs/00_system/CURRENT_SYSTEM_BASELINE.md` 为准；架构决策以 `governance/ADR/`
> 为准。本蓝图不解除现有工程宪章、生产门禁或人工闸门。

## 1. 一句话定义

AiFamily 不是内容库、测评表或聊天机器人，而是一个以家庭为长期主体的
**家庭成长智能操作系统**：它把家庭表达、知识理解、成人判断、专家与服务、
行动结果和反馈沉淀成可追溯的成长上下文，并为每个家庭动态生成下一条合适的成长路径。

AGI 原生的判据不是“模型更大”，而是：

1. 家庭面对的是一个连续的智能伙伴，而不是互相割裂的页面；
2. Agent 根据真实上下文组合能力原语，而不是从固定页面流程中挑选；
3. 每个结论都是可解释、可修订的 Perspective/Draft，不冒充事实或诊断；
4. 家长的确认、修改、拒绝和结果反馈会形成版本化学习信号；
5. 关闭生成式理解后，产品核心价值明显下降；
6. 系统能在不越权的前提下，把理解转化为内容、专家、行动和复盘。

## 2. 用户价值闭环

```text
家庭表达
  ↓ 文字 / 语音 / 图片 / 视频 / 表单 / 历史互动
AI Understanding
  ↓ 最少必要澄清，形成可编辑 Perspective Draft
成人确认 FamilyNeed
  ↓ 需要、对象、情境、目标、边界、紧迫性
Context + Knowledge Grounding
  ↓ 读取经授权的家庭上下文与已发布知识
Agent 生成成长路径草案
  ↓ 内容 / 对话 / 专家 / 服务 / 家庭实践 / 复盘组合
成人选择、修改或拒绝
  ↓ Human Gate + provenance
执行与服务履约
  ↓ 家庭行为、专家服务、内容学习、阶段性回访
结果与反馈
  ↓ Outcome Reflection + Guardian Feedback
Growth Graph 更新
  └──────────────→ 下一轮更懂这个家庭
```

产品首页只承担三件事：让家长表达、让家长看见系统理解、让家长进入下一步。
复杂能力在后台完成，不能把开发术语、治理术语和模型状态直接暴露在用户界面。

## 3. AGI 能力原语

所有产品场景必须由下列原语组合；不得为测评、直播、课程、专家、社区各建一套
孤立的“AI 大脑”。

| 原语 | 作用 | 输入 | 输出 | 必须经过 |
|---|---|---|---|---|
| `UNDERSTAND` | 理解家庭表达与情境 | 多模态表达、历史上下文 | Perspective Draft、澄清问题 | Model Gateway、知识证据、可修订 |
| `ASSESS` | 形成多维成长观察 | 成人回答、观察、证据 | 维度画像与解释，不输出家庭总分 | published knowledge、成人确认 |
| `MATCH_KNOWLEDGE` | 找到适用的知识与经验 | FamilyNeed、Growth Context | 带来源的知识片段与适用边界 | Knowledge Registry、版本/来源 |
| `DESIGN_PATH` | 动态组合成长路径 | Need、Context、候选能力 | Path Draft、节点、理由、替代方案 | Agent Runtime、Human Gate |
| `PROPOSE_ACTION` | 生成可选择的下一步 | Path Draft、家庭偏好、投入能力 | Action Proposal | 成人选择，不自动落事实 |
| `COORDINATE` | 连接专家、课程、活动和服务 | 已确认需要、授权范围 | 供给候选、履约草案 | 资质、范围、费用、人工履约 |
| `REFLECT` | 复盘执行结果 | 行动反馈、成人叙述、证据 | Outcome Reflection、下一轮问题 | 不作疗效/诊断承诺 |
| `LEARN` | 把人类反馈变成可追溯学习信号 | 接受、修改、拒绝、结果 | Feedback lineage、评估样本 | 不直接改写家庭事实 |

规则引擎只负责权限、状态、不变量和拒绝条件；不能用标签交集或硬编码候选池
冒充理解。开发占位必须显式标为 fixture，不能宣称 AGI 能力。

## 4. 家庭成长数据与知识闭环

### 4.1 四种语义必须分离

```text
Observation   家庭表达、回答、事件、服务结果等可追溯输入
Perspective    AI 或专家基于证据形成的解释草案，可被修改/拒绝
Decision       成人确认的 FamilyNeed、路径选择或授权决定
Fact           经业务流程确认并按域规则落库的事实
```

AI 只能产出 Observation 的整理、Perspective、Recommendation 和 Draft；不能自动
把推断写成 Fact，不能生成家庭总分、家庭排名或临床诊断。

### 4.2 Growth Graph 最小节点

`Family`、`Member`、`Relationship`、`Observation`、`AssessmentResponse`、
`PerspectiveDraft`、`ConfirmedFamilyNeed`、`KnowledgeEvidence`、`PathDraft`、
`ActionProposal`、`GuardianDecision`、`ServiceEngagement`、`OutcomeReflection`、
`GuardianFeedback`。

每个 AI 产物必须带：`family_id`、授权范围、输入快照引用、知识版本、模型/提示版本、
来源、生成时间、状态、修订链和人工决策引用。Context 是经授权的读取投影；
Growth Graph 才是可回放的业务成长历史，不能用进程内缓存替代。

### 4.3 知识库不是静态文章表

知识单元必须可检索、可组合、可解释：

`KnowledgeUnit → Evidence → Applicability → Contraindication → Practice → OutcomeSignal`

测评不是“打分报告”，而是把家长的回答与多维知识框架连接，形成一张可理解、可讨论、
可继续修订的家庭成长地图。雷达图可以作为观察视图，但不得被解释为家庭排名或诊断分数。

## 5. 产品形态：一个智能入口，多个能力面

前端采用简洁的 App-like 单列体验，不把三栏工作台、内部状态和技术名词暴露给家长。
用户看到的是一条动态成长流：

1. **今日入口**：系统基于最近的家庭需要，邀请家长继续表达或查看进展；
2. **家庭理解**：五维及其他维度的观察卡，显示“我为什么这样理解”，家长可改写；
3. **AI 对话**：少量高价值追问，支持文字、语音、图片和可选视频；
4. **成长路径**：不是页面菜单，而是按当前需要生成的节点序列；
5. **选择器**：内容、专家、家庭实践、服务和复盘候选，展示来源、投入、适用边界；
6. **成长记忆**：家长能看到自己的确认、修改、反馈如何改变后续理解；
7. **直播/社区/商品**：只有在某个已确认 FamilyNeed 下作为能力节点出现，不独立争夺注意力。

## 6. 平台技术蓝图

```text
App-like Experience
        │
Family API / Composition Root  ── Identity / Tenant / Consent / Audit / Idempotency
        │ ports
AI Runtime
  Context Engine ─ Growth Graph Reader ─ Knowledge Retrieval
  Agent Runtime ─ Tool Runtime ─ Model Gateway ─ Provider Adapters
  Prompt/Schema Registry ─ Provenance ─ Evaluation ─ Cost/Trace
        │ proposals only
Human Gate / Workflow Worker
        │ confirmed commands
Domain Services: FamilyNeed / Assessment / Growth / Service / Content / Community
        │
PostgreSQL + Outbox/Event Log + Object/Vector indexes + Replay/Evaluation store
```

硬性架构判断：

- 领域只通过唯一 Model Gateway 调模型；
- Agent 无权直接写权威事实；
- Context 读取必须受 tenant/family/consent 限制；
- Knowledge 必须有 published 状态与版本；
- PathDraft 必须按 `need_id + context_snapshot_ref` 持久化幂等；
- 家长反馈、修改和拒绝必须形成 lineage；
- 多模态输入统一进入 Observation，不为每种媒介复制一套业务语义；
- 任何第二套 Identity、Consent、Audit、Deletion 或事实账本均禁止。

## 7. 场景地图与 MVP

真正的 MVP 不是单一接口，也不是一次测评，而是以下最小可感知闭环：

### MVP-A 家庭首次理解

`首页表达 → 多模态澄清 → 五维家庭观察 → AI Understanding Draft → 家长修订确认 → 成长方向`

这是第一优先级，必须让家长感到“系统真的听懂了我”，而不是只看到一张漂亮雷达图。

### MVP-B 家庭成长路径

`ConfirmedFamilyNeed → 知识证据 → 2~3条不同路径候选 → 家长选择/修改 → 执行记录 → 复盘`

候选必须来自真实能力/知识目录；不能继续使用三条硬编码占位候选冒充个性化。

### MVP-C 人机协同服务

`需要确认 → 内容/专家/课程/活动候选 → 范围与费用披露 → 家长授权 → 人工履约 → 结果反馈`

直播、专家和商业化属于路径节点，不是脱离 FamilyNeed 的流量孤岛。

### MVP-D 越用越懂

`GuardianFeedback → 版本化 lineage → Context/Growth Graph 更新 → 下一次理解变化可解释`

至少用两个家庭、两个不同反馈和一次进程重启证明差异与回读，才可称为 AGI 原生 MVP。

## 8. 团队与工作包

| 归口 | 唯一职责 | 近期交付 |
|---|---|---|
| PMO/总控 | 依赖DAG、冲突裁决、证据台账 | 每日目标与阻断清单，不重复施工 |
| AGI Runtime | Model Gateway、Agent、Context、Tool、Provenance | 真实模型调用闭环与失败证据 |
| 家庭测评 | Observation/Assessment/五维解释/成人修订 | 首次理解场景真实 HTTP + PG |
| Platform Core | Identity、Consent、Audit、Outbox、Idempotency、Persistence | canonical adapter 与重启回读 |
| Experience | 单列 App UI、多模态输入、草案修订、成长路径 | 浏览器真实场景，不展示内部术语 |
| Growth Service | FamilyNeed、PathDraft、Action、Outcome | MVP-B/D durable 闭环 |
| 小橘灯 | 独立直播产品，仅通过 Platform Core 接入 | 只做已确认需要下的直播节点 |
| QA/红方 | 同 ref 真实 HTTP/PG/浏览器、双家庭、反例 | 只按可运行场景裁决 |
| 顾问组 | 家庭教育、发展心理、服务履约、内容、商业、交互 | 研究结论必须转成能力/测试/决策 |

团队规则：每个工作包一个 owner、一个 branch、一个 pathspec、一个可运行场景；
重复 Chat 合并，孤儿分支在窗口期内接入或归档。文档只能作为输入，不能计为产品进度。

## 9. 依赖 DAG 与阶段门

```text
P0 目标与语义冻结
  → P1 Context/GrowthGraph + Knowledge/Capability真实来源
  → P2 ModelGateway真实调用 + Agent生成Draft
  → P3 Assessment/Path/Feedback持久化
  → P4 Composition Root接线
  → P5 浏览器 + 真实HTTP + PG/restart + 双家庭差异
  → P6 QA红方验收
  → P7 小流量/生产评审
```

允许并行的是不共享文件、不复制语义的工作：知识目录、模型调用、数据 adapter、
单列 UI、测试 harness 可以并行；Composition Root、schema、canonical registry、
同一 domain owner 不并行写。任何冲突先回 PMO，总控裁决后再动手。

## 10. 本阶段不可宣称的能力

当前不能把以下内容写成已实现：默认主线的 Knowledge→ModelGateway→Draft 完整链路、
真实持久化 PathDraft、真实 Growth Graph 学习、双家庭动态差异、浏览器端到端、
真实 PostgreSQL 重启回读、直播生产能力、AGI 能力本身。

本蓝图的第一个成功标准不是“页面数量增加”，而是家长完成一次真实表达后，系统基于
可回读上下文生成一份有来源、可修订的理解草案；家长修改/确认后得到不同且相关的
成长路径，刷新或重启仍能回读，并能在下一次反馈中解释变化原因。
