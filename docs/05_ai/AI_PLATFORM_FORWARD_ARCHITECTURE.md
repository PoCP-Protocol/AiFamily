---
id: AI-FORWARD-ARCH-001
title: AiFamily 前瞻 AI 平台架构（目标态）
type: specification
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: false
supersedes: null
superseded_by: null
---

# 前瞻 AI 平台架构（目标态）

```text
DOC_KIND   = SPECIFICATION / TARGET_STATE
NOT_CURRENT_TRUTH — 本文件描述"应该建成什么"，不描述"现在是什么"。
当前真相在 docs/00_system/CURRENT_AI_MAP.md。

★ 本文件全部六个组件的当前成熟度均为 ABSENT。零代码、零测试、零调用方。
  引用本文件的任何内容时，不得表述为"平台具备"或"平台已支持"。
  按 SYSTEM_MANIFEST.md §6（Current Truth ≠ Specification）与
  AI_NATIVE_PRINCIPLES.md 的口径："设计过 / 研究过" ≠ "已实现"。

排期约束：本文件描述的全部内容排在真实交付之后。
  当前 34 个 mobile 屏幕可工作数 = 0（CURRENT_PRODUCT_MAP.md）。
  一份前瞻架构不得插到"让第一个屏幕能用"之前。
```

---

## 0. 本文件的立论：赌哪个方向，决定架构长什么样

「模型会更强」是所有人都在赌、且不由本平台决定的部分。可下注的判断是另一句：

> **未来 AI 的竞争力是「可信自主」，而不是「更强」；平台的护城河在治理层。**

这个判断对 AiFamily 产生一次**定位反转**。本仓库当前已有的治理资产——

| 资产 | 位置 | 实测状态 |
|---|---|---|
| 架构护栏 10 个 | `tests/architecture/` | 真运行；其中 `test_compliance_constraints.py` 用真 AST 解析查 R9 打分字段与 PIPL 自动晋升 |
| Provenance 强制 | `backend/packages/contracts/evidence.py:44-51` | `Provenance.level` 无默认值，强迫每个调用方声明来源 |
| AI 输出封印 | `backend/intelligence/model_gateway/contracts.py:184-214` | `ModelDraft` 只有 `DRAFT` 一个合法状态；`may_mutate_business_state` 为无 setter 的 property |
| 能力的缺席作为护栏 | `backend/domains/loyalty_points/` | `PointsAccount` **无 `balance` 字段**（余额永远由 entries 计算）；repository port **故意不提供** `rank_families` —— 那个方法的缺席就是 R9 的执行机制 |
| 法定硬约束进架构 | `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` + ADR-0006 | 3 票对抗性核验，带法源条文 |

——在「模型更强」的赌注下是**合规税**；在「可信自主」的赌注下是**唯一难以被复制的资产**。
模型能力会被拉平（今天的 SOTA 是明年的开源基线），**能安全地把决策权交给 AI 的执行记录不会。**

因此本文件不是「在现有架构上加 AI 功能」，而是：**把治理层从「防御设施」升级为「授权设施」。**
防御设施回答"AI 不许做什么"；授权设施回答"在什么证据下，可以让 AI 多做一点"。

以下六条全部从既有 canonical 文档推出，未引入外部概念。

---

## 1. 从「一次调用」升级为「可授权、可撤销、有预算的自主循环」

### 现状形态与它的问题

`model_gateway` 当前是 request/response：业务代码决定何时调一次模型
（`contracts.py:75-118` 的 `StructuredRequest` 是单次结构化生成请求）。
这是 ADR-0005 §Context 自己批判的「AI 作为被业务模块调用的工具」形态的残留——
`ADR-0005` 否决替代方案 A 时的理由同样适用于此：**当 AI 是被调用方，它就不可能是主路径。**

### 目标形态：声明与授权分离

```text
AgentDefinition      「这类 agent 能做什么」    静态 · 代码 + governance/AI_USE_CASE_REGISTRY.yaml
AgentAuthorization   「这个 agent 现在被允许做什么」 动态 · 有 TTL · 有预算 · 可撤销 · 有签发人
```

`AgentDefinition` 已在 `AI_NATIVE_PRINCIPLES.md` §3.5 定义（`allowed_skills` / `allowed_tools` /
`context_policy` / `safety_policy` / `human_handoff_policy`，统一 `may_mutate_business_state = false`）。
**缺的是 `AgentAuthorization` 这一层**：某个 agent 在某个家庭的某段时间内，
被授权使用哪些工具、花多少预算、自主执行几步、由谁签发、**可随时撤销**。

这一层是判据 5（AI 权限边界显式建模）的真实形态。缺了它，「自主」只能靠「不给自主」来保证安全——
即当前状态。

### 自主必然出错，所以补偿路径与闸门同等重要

闸门（R8）防的是"不该做"；**补偿处理的是"做了但错了"**。
AI 原生系统里后者的发生频率会远高于传统系统，而当前架构对它零设计。

每个 agent 可发起的动作必须满足二者之一：**可逆**（有明确的撤销动作），
或**有补偿**（有明确的反向业务动作 + 补偿记录）。
不满足的动作不得授权给 agent 自主执行，只能走 Human Gate。
这一条应成为 `AgentAuthorization` 的准入判据，而非事后约定。

### 与 R9 的关系：不放宽，是把边界写得更细

`AgentAuthorization` **不**赋予 agent 写 canonical Fact 的能力——
`may_mutate_business_state = false` 不可协商（`AI_ARCHITECTURE.md` §4.3）。
它授权的是「自主产出 Draft 的范围与成本」，不是「自主落库的权限」。
把这两件事分开，正是为了让前者可以放宽而后者永远不放宽。

---

## 2. Provenance 从「字段」升级为「决策来源图」

### 现状

`AiProvenance`（`contracts.py:128-181`）是挂在单条记录上的字段集：
`provider_id` / `model` / `model_version` / `prompt_version` / `schema_version` /
`context_snapshot_ref` / `latency_ms` / `data_class` / `use_case` / `confidence`。
`CURRENT_AI_MAP.md` §3 第 12 行对此的定性精确：「**只有类型，没有记录机制**」。

字段集足以应付一次审计问询，但撑不起判据 4（越用越准）。

### 目标形态

一张图，而非一组字段：

```text
Evidence ──▶ Hypothesis ──▶ Recommendation ──▶ HumanDecision(确认/驳回/改写)
   │             │                │                      │
   └─── 引用 ────┘                └──── prompt_version ───┘
                                                          │
                                          三个月后 ──▶ Outcome(实际发生了什么)
```

这张图同时是三件东西的唯一载体：

1. **PIPL 第 24 条的可解释性**——不是「我们记录了 model 名」，是「这条建议为什么是这条」。
2. **判据 4 的学习闭环**——`AI_NATIVE_PRINCIPLES.md` 判据 4 要求「交互→证据沉淀→下一次更准，
   且该闭环有代码落地不只是设计意图」。没有 Recommendation→Outcome 的连边，闭环不存在。
3. **「哪些建议后来被证明有用」的唯一真实来源**——这是平台能力自证的基础。

### 落点：与 ADR-0010 的投影层是同一套基础设施

这张图应存在 ADR-0010 定义的 `graph_projection.*` 只读投影内，**不另建一份**。
Family Growth Graph 与决策来源图是同一张图的两个视图
（`AI_ARCHITECTURE.md` §2.2 已就三层画像与两个独占区候选做过同样判断：
「应该是同一套底层存储与检索能力的两个视图，不应该分别重复建设」）。

**红线沿用**：投影上禁止任何聚合分值字段（R9），
`test_no_scoring_or_ranking_fields_anywhere` 自动覆盖。

---

## 3. 记忆的一等操作是**遗忘**，而这是合规逼出来的架构优势

### 约束来源

`COMPLIANCE_HARD_CONSTRAINTS.md` §6：删除权覆盖派生数据，**embedding / 向量属于必须可删除的范围**，
这是法定义务而非最佳实践。ADR-0006 已把它写入架构。

### 这个约束把架构逼到了正确形态上

多数平台的 RAG 做不到按主体删除——向量库通常只支持整体重建。
所以本平台**被法律逼着**把记忆做成可寻址、可撤回的。

而「能忘、能纠正」恰好是可信自主的必要条件：
**一个不能撤回错误记忆的 agent，其错误会永久污染后续所有判断。**

因此：合规约束在此处不是成本，是把架构逼向了「可信自主」所需的形态。
这也是选 pgvector（行级删除）而非批量重建型向量库的**真实理由——不是性能，是可删除性**。

### 目标形态

记忆分三态，各有独立的保留期与删除路径：

| 态 | 内容 | 删除语义 |
|---|---|---|
| 事实记忆 | 引用业务域 Fact 的只读投影 | 随业务域主体删除级联 |
| 情境记忆 | 上下文快照（`context_snapshot_ref` 指向的实体） | 有明示保留期，到期自动过期 |
| 派生记忆 | embedding / 向量 / 聚类 | **按主体级联删除，可重建** |

`COMPLIANCE_HARD_CONSTRAINTS.md` §1 要求「每个存储未成年人数据的字段须有明示留存期限与到期处理方式」
——三态划分是该要求在记忆层的落地形式。

**当前状态**：`CURRENT_AI_MAP.md` §3 第 5 项已升为 `EXPERIMENT`；`SqlAlchemyMemoryStore` 与迁移 0022 提供可重启、可撤回的引用存储，向量检索仍未启用；
源仓库 `FamilyMemoryDialogueRuntime` **未接入任何调用方**，embedding / pgvector 完全不存在于代码。
三态一态都没有。

---

## 4. Eval 从「测试阶段」搬到「运行时」

`AI_NATIVE_PRINCIPLES.md` §5 已经承认：判据 4 的验证「需要真实 eval 框架与回归测试，**不是靠声明**」。
`CURRENT_AI_MAP.md` §3 第 10 项记 Evaluation 为 `ABSENT`，零 eval 代码。

目标形态是常驻组件而非 CI 步骤：

- **升级门**：任何能力升级（换 provider / 换 model_version / 改 prompt_version）
  必须先过回归集才允许对真实家庭生效。这与 `provider_registry` 已有的
  `approved_environments` 门控是同一思路的延伸。
- **影子评估**：线上输出旁路评估，不阻塞响应。
- **回归集来源**：第 2 节的决策来源图——被人工驳回的建议是最有价值的负样本。

**为什么这条是硬要求而非改善项**：向一个未成年人教育产品的用户声明「越用越准」，
在没有 eval 的情况下接近虚假承诺。而「不做虚假承诺」是既有约束
（`COMPLIANCE_HARD_CONSTRAINTS.md` 与 R9 的「非疗效承诺」）。

---

## 5. 人在环的形态必须升级，否则所有护栏形式通过

### 这是全部约束里最危险的一条不可检验项

**点击 ≠ 审阅。** R8 要求高影响行为过 Human Gate、闸门决策落库可审计；
`test_compliance_constraints.py` 能检查「晋升函数是否有人类 actor 参数」，
但**没有任何机制能判断那个人是否真的看了**。

若闸门退化为橡皮章，则每一条护栏在形式上全绿而实质失效——
这比没有闸门更危险，因为它提供虚假安全感（R14 伤疤的形状）。

### 目标形态：按风险分级 + 把闸门健康度变成可监测指标

| 风险级 | 形态 |
|---|---|
| 低 | agent 自主 + 事后抽样复核 |
| 中 | 人工确认（单人） |
| 高 | 双人 + 强制留痕 + 不可批量操作 |

关键设计：**把闸门自身的健康度当作可监测指标**——审阅耗时分布、驳回率、
批量确认比例、同一 actor 的确认速率。

> **一个驳回率为零的闸门，是坏了的闸门。**

这条的价值在于：它把「人工确认是否实质审阅」从**完全不可检验**变成**可统计监测**。
不是完美的证明，但比现在的零好一个量级。这是本文件里唯一把一条不可检验项部分转化为可执行护栏的设计。

R8 的过闸清单（类诊断输出 / 家庭计划变更 / 教师推荐 / 服务购买 / 对外沟通 / 会员升级 /
涉未成年人的敏感动作）与上表的映射需单独出 ADR，本文件不预先规定。

---

## 6. 模型无关，且为自建行业模型预留位置

`model_gateway` 已经是抽象层，这一步做对了（`provider_registry.py` 按 provider 记
`credential_env_var` 变量**名**而非值，`ProviderRecord` 携带合规准入字段）。

需要补的是：**能力声明与具体模型解耦**——
一个用例声明它需要什么等级的推理与什么安全约束，而不是声明它要用哪个模型。
路由层按声明选 provider（`routing.py` 已有雏形）。

收益：将来用自建的家庭教育行业模型替换通用模型时，改的是**路由表**而非业务代码。
这同时缓解 ADR-0005「需要接受的风险」中记录的两条：
「AI 原生依赖外部 LLM 供应商，而不得转委托约束可能实质限制供应商选型」、
「判据 1 使 AI 失效等于核心能力失效，可用性风险集中于模型供应链」。

---

## 7. 明确不赌的方向（这一节与上面六节同等重要）

| 不赌 | 理由 |
|---|---|
| **模型更强就能把家庭打分打得更准** | R9 红线不是能力不足的妥协。恰恰因为 AI 能轻易生成一个看起来专业的分数，这条线才更需要守。这是「家是港湾」定位的工程化，不是技术限制 |
| **追前沿模型排行** | 平台价值在治理层与领域数据，不在选对了哪个模型。模型是可替换件（§6） |
| **AI 自主性越高越先进** | 自主性的上限由**可信度证据的积累速度**决定，不由模型能力决定。§1 的 `AgentAuthorization` 是为了让自主可以被证据驱动地放宽，不是为了尽快放宽 |
| **用 AI 补齐孩子端商业化** | ADR-0006 已实质关闭该路径：《未成年人网络保护条例》第 24 条第 3 款绝对禁止向未成年人做自动化决策商业营销，无年龄例外 |

---

## 8. 成熟度汇总（与 CURRENT_AI_MAP.md 一致，不做乐观化改写）

```text
§1 AgentAuthorization / 自主循环 / 补偿路径      ABSENT   零代码
§2 决策来源图（provenance 图化）                ABSENT   仅字段，无记录机制
§3 记忆三态 / 派生记忆可删除                    ABSENT   Memory 整层空白
§4 运行时 Eval / 升级门 / 影子评估              ABSENT   零 eval 代码
§5 风险分级 Human Gate / 闸门健康度监测          ABSENT   闸门本身尚未建立
§6 能力声明与模型解耦                          PARTIAL  provider_registry + routing 有雏形，
                                                       能力声明层不存在
```

**六项中五项 ABSENT、一项 PARTIAL。没有任何一项达到 PILOT。**

本文件与 `CURRENT_AI_MAP.md` §7 的成熟度汇总不冲突：那里记的是当前，这里记的是目标。
**两份文件出现分歧时，以 `CURRENT_AI_MAP.md` 为准**——它是 Current Truth，本文件是 Specification。

---

## 9. 晋升路径（本文件如何变成架构而不是停留为设想）

按 `docs/12_governance/DOCUMENT_GOVERNANCE.md` 的三级晋升链，本文件当前是 `draft` / `canonical: false`。
任一节要成为正式架构，须：

1. 该节单独出 ADR（ADR-0015 起），带实测证据、替代方案、以及**诚实的 Enforcement 段**；
2. 同 PR 落地对应的架构测试（R14：无护栏的规则只是意图）；
3. 更新 `CURRENT_AI_MAP.md` 的成熟度行——**且只在有可运行代码 + 通过的测试时才更新**。

**优先序建议**（依赖关系决定，非重要性排序）：

```text
§2 决策来源图  ──依赖──▶ ADR-0010 的 outbox + graph_projection（当前 DomainEvent = 0 命中）
§5 闸门健康度  ──依赖──▶ Human Gate 本体存在（当前不存在）
§1 AgentAuthorization ──依赖──▶ AgentDefinition 落地 + AI_USE_CASE_REGISTRY.yaml（当前缺失）
§3 记忆三态    ──依赖──▶ Alembic baseline + pgvector（T-03 进行中）
§4 运行时 Eval ──依赖──▶ §2 的图（负样本来源）
§6 能力声明层  ──可独立推进，成本最低
```

**§5 的闸门健康度监测是性价比最高的一项**：它把当前完全不可检验的「人工确认是否实质审阅」
部分转化为可统计指标，且不依赖任何尚不存在的机制。

---

## References

- `docs/00_system/CURRENT_AI_MAP.md`（Current Truth；本文件的成熟度断言以它为准）
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §1 判据 4/5、§3.5、§5（三项待补检查）
- `docs/05_ai/AI_ARCHITECTURE.md` §2.2、§4.3（AI Runtime 隔离规则）
- `docs/12_governance/COMPLIANCE_HARD_CONSTRAINTS.md` §1、§6
- `docs/00_system/TARGET_ARCHITECTURE.md`（目标拓扑；本文件是其 AI 侧展开）
- `governance/ADR/ADR-0005`（AI 原生定位与其"需要接受的风险"）、`ADR-0006`（合规硬约束）、
  `ADR-0010`（只读投影，本文件 §2 的落点）
- `governance/REPOSITORY_CONSTITUTION.md` R6 / R8 / R9 / R10 / R14
- `backend/intelligence/model_gateway/contracts.py`、`provider_registry.py`、`routing.py`
- `backend/domains/loyalty_points/domain/entities.py`（"能力的缺席作为护栏"的既有先例）
