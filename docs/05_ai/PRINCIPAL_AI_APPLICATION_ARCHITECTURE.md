---
id: AI-PRINCIPAL-APPLICATION-001
title: 法咪莉校长 AI 控制平面与体验闭环纵向切片
type: ai-application-architecture
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
delivery_state: PLANNED
---

# 法咪莉校长 AI 控制平面与体验闭环纵向切片

> 本文描述 S1-A 的可测试契约与下一步落点，不宣称生产能力已经上线。当前实现是
> `PrincipalRuntime` 的 draft-only 适配器：路由 → 受审核知识检索 → Model Gateway →
> 结构化草稿。家庭、服务、订单、权益、交付和结果仍由各自业务域的 Named Action
> 写入；AI 不能把模型输出直接变成业务事实。

## 1. 对齐约束

### 1.1 业务目标与 N0-N8

校长横跨 X0 Experience & Trust、B1 Family Education & Growth OS、B2 FGCN Resource
Collaboration、B5 Platform Evolution，但不拥有任何一个业务域的权威状态。一次运行
必须能追溯到需求目标模型的节点：

```text
N0 需求信号 → N1 需求澄清 → N2 需求分级 → N3 方案设计 → N4 资源组织
  → N5 交付执行 → N6 质量验收 → N7 结果与关系 → N8 新需求回流
```

`ExperienceEvent.node` 保存 N0-N8 之一；Principal 只读取事件、上下文和已发布
`KnowledgeClaim`，返回 Perspective、Draft、Recommendation、ActionProposal 或
HumanTask。N1 需求确认、N4 资源分派、N6 质量验收、N7 结果确认必须由家庭/人工/业务
Named Action 完成。

### 1.2 五层架构位置

| 层 | 本切片落点 | 不越界的事实边界 |
|---|---|---|
| 业务架构 | Principal Experience + AI Orchestration 横切能力；六引擎统一入口 | 不拥有 Family、ServiceCase、Order、Outcome |
| 流程架构 | L0 家庭需求价值流 → L2 N0-N8 → L4 API/Command/Event/Human Task | AI 节点只能产生候选草案，不能推进业务状态 |
| 数据架构 | `ExperienceEvent`、`RecommendationDecision`、`FeedbackSignal`、`MemoryRef`、`KnowledgeClaim`、`AiProvenance` | 记忆、媒体和知识均有租户/家庭/主体/目的/删除边界 |
| 应用架构 | `PrincipalCapabilityRouter` + `PrincipalRuntime` + KnowledgeRegistry + ModelGateway | 业务域通过 Action Bridge 采纳草稿，不能访问模型 SDK |
| AI 技术架构 | Soul/Context/Knowledge/Router/Gateway/Schema/Provenance/Human Gate | `may_mutate_business_state` 恒为 false，生产准入仍待治理 |

统一作用域 envelope 至少包含：`tenant_id`、`region`、`family_id`、`subject_id(s)`、
`purpose`、`consent_version`、`consent_granted`、`data_class`、四类 locale、
`provenance`、`deletion_ref`、`correlation_id`、`causation_id`。缺一则拒绝，不做
“默认公共家庭”或跨租户回退。

## 2. 六引擎与平台精神

校长是六引擎的受治理编排面，而不是第七个业务域：

| 引擎 | Principal 可做 | 明确禁止 |
|---|---|---|
| 拼多多式增长 | 低门槛教育入口、可选邀请、案例传播草案 | 未成年人商业画像、多级返佣、强拉新 |
| 字节式分发 | 按目的/语言/节奏/反馈召回内容和行动 | 以停留或脆弱情绪驱动黑箱操纵 |
| 海底捞式服务 | 感知“被看见”、准备响应和补救建议 | 自动承诺、赔付、关闭投诉 |
| 贝壳式 ACN | 解释资源匹配、任务拆解和贡献证据 | 自动分派、直接分佣、家庭结果排名 |
| 教育方法论 | 解释证据、21/90/年度计划草案、复盘 | 诊断、疗效保证、家庭总分/排名 |
| 游戏化体验 | 非比较性章节、小行动、即时反馈、可选徽章 | 沉迷刺激、随机奖赏、打卡惩罚、儿童比较 |

平台精神是 **We are 伐木累！We are family！**：先让家庭被理解、获得情绪价值和
一个可完成的小胜利，再在授权、成长证据和人工服务基础上提供经济价值。商业闸门
必须晚于情绪/成长体验，不能把脆弱时刻直接变成购买压力。

## 3. 最小运行时闭环（PLANNED）

```text
入口/会话
  → scope + consent + context_snapshot_ref
  → PrincipalCapabilityRouter（profile / tools / human gate）
  → KnowledgeRegistry.retrieve_reviewed（scope + purpose + publish + expiry）
  → 仅经 ModelGateway.generate_structured
  → schema 校验 + AiProvenance + attempt ledger
  → PrincipalDraft(status=DRAFT, human_confirmation_required=true)
  → 家庭/人工 Review
  → 业务 Named Action（域内事实）
  → ExperienceEvent / FeedbackSignal 回流 N8
```

当前代码可执行的最小 capability 为：

- `experience_curation`：检索 `family_growth_reviewed`，输出 Recommendation Draft，
  `EXPLICIT_CONFIRMATION`；
- `memory_candidate_draft`：只生成受作用域约束的 MemoryCandidate 草案，输出不能直接
  确认记忆，仍需 `confirm/retract/retrieve/delete-proof` 适配器和人类同意。

当知识不在目的/范围、来源未发布/已过期、主体/家庭/租户不匹配时，在调用模型前拒绝。
私有文本和未成年人数据还要经过 Model Gateway 的 provider admission；当前
`fake-deterministic` 只允许 test/development 的 synthetic/operational 数据，不能被
描述为生产模型。

## 4. 知识、记忆和多模态边界

### 4.1 知识库

知识链是 `Source → Claim → Review → Publish → Retrieve → Citation`。运行时只接受
已核验来源、`PUBLISHED` claim、匹配 scope/purpose 且未过期的内容；模型不能自报引用。
家庭私有内容不能进入共享知识注册表；N8 的改进候选需先去标识化、审查和人工发布。

### 4.2 记忆体

记忆分为 `child`、`guardian`、`family_relationship` 三类 scope，保留 M0（回合）至
M3（有限长期）层级。每条 `MemoryRef` 必须有主体集合、用途、同意版本、过期时间、
provenance 和删除级联清单；不可无限采集、跨家庭读取、按未成年人建立商业画像。读取
越权、用途不匹配、过期、撤回和删除级联均 fail-closed。

### 4.3 多模态

支持 `text`、`voice`、`image`、`audio`、`video`、`interactive_card`。媒体只以
`ExperienceMediaRef` 引用跨边界，并声明 `input`、`output`、`transcription`、`ocr` 或
`playback` 操作；原始媒体、转写/OCR 派生物和可展示输出分别保存 provenance 与
deletion_ref。缺少同意、媒体过期、不支持 modality、跨租户/主体媒体一律拒绝。

## 5. 测试环境与生产等价

test/development/production 使用相同的路由、scope envelope、schema、错误码、人工
闸门和 Named Action 接口；环境差异只允许是数据与 provider/adapters（测试使用合成
知识、FakeProvider、sandbox 存储）。本切片的自动化证据覆盖：成功 draft、知识目的
过滤、跨租户/家庭/主体拒绝、记忆作用域、私有数据 provider admission、DRAFT 不可
提升。仍缺少真实持久化、Context Broker、媒体存储、Human Gate API、Action Bridge、
审计/outbox、评估集、删除作业和生产供应商合规准入，因此状态保持 `PLANNED`。

## 6. 完成定义与下一步

不得以“模型能回答”或“页面存在”标记完成。一个 Principal 用例达到
`IMPLEMENTED_TESTED` 前，必须补齐：

1. N0-N8 场景、actor、purpose、consent 和错误分支；
2. ContextSnapshot 的只读投影和最小字段策略；
3. Soul/Prompt/Schema/Knowledge/Model provenance 版本链；
4. Human Review、Action Bridge、幂等、审计、outbox 和补偿；
5. 真实与合成环境的同构回归、漂移/成本/安全评估；
6. 导出、删除级联、回滚、人工接管和事故演练。

S1-A 之后建议按纵向切片迭代：先接 `N0→N1` 需求澄清，再接 `N3` 方案草案和 N8
反馈回流；每次只扩展一个 capability/profile，保持 34 个 UI 的体验基线和上述事实边界。
