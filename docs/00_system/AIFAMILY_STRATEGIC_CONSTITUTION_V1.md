---
id: SYS-STRATEGIC-CONSTITUTION-001
title: AiFamily 战略宪法 V1
type: system
status: current
version: 1.1
owner: project-owner
created: 2026-09-13
updated: 2026-09-13
canonical: true
supersedes: null
superseded_by: null
authorized-by-adr: governance/ADR/ADR-0169-family-agi-species-change-and-strategic-constitution.md, governance/ADR/ADR-0171-platform-core-six-gate-admission-test.md
relates-to: governance/ADR/ADR-0168-child-family-society-boundary.md, governance/ADR/ADR-0170-runtime-convergence-acceptance.md, docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md
---

# AiFamily 战略宪法 V1

> **本文件的定位**：以后任何商业计划书、产品蓝图、技术架构文档、给 Claude/Codex
> 的开发指令，最前面都应放这份宪法的引用或摘要。它不描述"现在做到哪一步"
> （那是 `CURRENT_SYSTEM_BASELINE.md`），不描述"具体怎么实现"（那是
> `docs/04_domains/`/`docs/06_platform/`），只回答**这个系统的物种是什么、
> 什么绝对不能变**。
>
> **与 `SYSTEM_MANIFEST.md` 的关系**：`SYSTEM_MANIFEST.md` 仍是全仓库唯一的
> 最高入口文档（"任何人或 AI Agent 进入仓库后必须首先读取"这一条不变）。本
> 文件是其 §2（服务谁、解决什么问题）的权威全文展开，由 `ADR-0169` 授权写入
> canonical。两者冲突时以本文件为准（因为本文件更新、内容更完整），但读者仍
> 应先读 `SYSTEM_MANIFEST.md` 建立整体导航。

## 0. 一句话：这是一次物种变化，不是一次升级

> **不是从家庭教育平台升级成 AGI，而是一开始就按照 Family AGI Platform 来
> 建设，只是用孩子成长完成第一阶段产品验证。**

这次纠正的最大价值，是把三个此前被混在一起的概念彻底分开：

```text
战略边界     可以很大
技术底座     必须通用
第一阶段产品范围  必须足够窄
```

任何人（人类或 AI Agent）在提出"要建 X"之前，必须先说清楚 X 属于这三层里的
哪一层。混用是本平台历史上反复出现的错误模式的根源——把"战略变宽"误执行成
"现在就多做几个垂类"，或者反过来"文档说边界宽，代码继续按教育平台的方式长"。

## 1. 六条不可破坏原则

| 原则 | 冻结定义 |
|---|---|
| 基本服务单位 | **Family，而不是 Student/User** |
| 核心业务对象 | **FamilyNeed，而不是 Course/Product** |
| 长期智能对象 | **FamilyWorldState，而不是 User Profile**（不叫 World Model，见 §4，强调"持续演化的状态"而非"静态大宽表"） |
| 解决问题方式 | **AI + Family + Human + Society Resources** |
| 价值评价方式 | **Outcome，而不是点击、消费、课程完成率** |
| 第一阶段垂直场景 | **Child Growth / Education 是 First Wedge，不是 Platform Boundary** |

系统主循环永远是：

```text
Family
  ↓ What is happening?
  ↓ What does this family actually need?
  ↓ What do we know / not know?
  ↓ What outcome does the family want?
  ↓ What options exist?
  ↓ What should AI / family / professionals / institutions each do?
  ↓ Action
  ↓ Outcome
  ↓ Learn
```

**不是**：`用户 → 测评 → 推荐课程 → 找老师 → 买服务`。

## 2. 平台是什么：四个系统，不是一个"家庭 AI 助手"

```text
① Family Intelligence System  长期理解家庭
② Family Decision System      帮助家庭识别问题、设定目标、做决策
③ Family Action System        帮助家庭真正执行，不是只聊天
④ Family Resource Network     把家庭连接到社会资源
```

> AiFamily ≠ Chatbot。AiFamily ≠ Education SaaS。AiFamily ≠ Family Super App。
> **AiFamily = Family Intelligence Infrastructure。**

App、Web、法咪莉校长数字人、语音、直播、智能硬件、家庭机器人，全部只是
**Interface**；不可替代的是背后的 **Family Intelligence Core**。

## 3. Family 是一级对象，Person 是二级对象

不是 `User { profile, memory, preference, conversation }`，而是：

```text
Family
├── Members (Child A/B, Parent A/B, Grandparent...)
├── Relationships
├── Shared Context / Shared Goals / Individual Goals
├── Shared Resources / Constraints / Risks
├── Needs / Decisions / Plans / Outcomes
```

家庭内部存在共同目标、不同目标、利益冲突、认知差异、隐私边界、监护关系、
决策权差异、责任分配、资源约束、情感关系——这是与通用助手的本质区别：
通用助手回答"我需要什么"，Family Intelligence 回答**"我们这个家庭真正
需要什么"**。

### 3.1 Family Relationship & Decision Model：不选一个"真相"

家庭成员对同一件事的陈述可能互相矛盾（孩子说"妈妈逼我学习"，妈妈说"孩子没有
自律性"）。系统不得替家庭选定一个真相，必须显式区分信息类型：

```text
FACT / SIGNAL / SELF_REPORT / OTHER_REPORT / PREFERENCE / GOAL / CONSTRAINT
/ RISK / HYPOTHESIS / UNKNOWN / INFERENCE / PROFESSIONAL_OPINION
```

**禁止把 AI 推断（INFERENCE/HYPOTHESIS）静默升级为家庭事实（FACT）。** 这是
`governance/REPOSITORY_CONSTITUTION.md` R9 在信息类型层面的具体化：任何持久化
的家庭相关记录必须携带上述类型标签之一。

## 4. Family World State：动态状态，不是大宽表

刻意不叫 "World Model"（暗示静态建模），改叫 **Family World State**，强调
随时间演化、带证据链接、带置信度：

```text
FamilyWorldState
├── Identity / Membership / Relationships / Life Stage / Environment
├── Member States (Child Development / Adult Development / Health /
│   Education / Work / Wellbeing)
├── Family System (Communication / Routines / Roles / Rules / Resources /
│   Stressors)
├── Needs / Goals / Constraints / Preferences / Decisions / Plans / Actions
├── Risks / Outcomes / Resource Relations
└── Unknowns
```

底层实现原则：**Stable Core Schema + Extensible Domain Objects + Temporal
State + Evidence Links**，不是现在就建 `health_xxx`/`finance_xxx`/
`elder_xxx`/`travel_xxx` 这类专用数据库——**架构边界宽，业务实现窄**，见 §7。

## 5. FamilyNeed：平台第一业务对象，Expression ≠ Need

以后系统最重要的 ID 是 `family_need_id`，不是 `course_id`/`assessment_id`/
`teacher_id`。

```text
FamilyNeed
├── family_id / expressed_by / original_expression / need_domain
├── affected_members / urgency / severity
├── evidence / hypotheses / unknowns / risks / constraints
├── desired_outcomes / current_state / need_status / confidence
```

**Expression ≠ Need**：用户说"给孩子找英语老师"是 Expression，不是 Need。
系统必须先判断背后真正的问题（成绩/口语/考试/信心/学习方法/缺陪伴/家长期望/
学校教学不匹配），再决定是否需要 Resource——跳过这一步直接映射为商品，等价于
把未经验证的表达当成了家庭事实,违反 R9。

长期演化方向：**Family Need Graph**——一次需求不是孤立 ticket,而是
`Need ↔ Cause ↔ Context ↔ Intervention ↔ Resource ↔ Action ↔ Outcome`
的网络,最终形成 **Need-to-Outcome Knowledge Graph**,这是比"哪个课程点击率高"
价值高得多的数据资产（架构上允许,当前不要求实现,见 §7/§9）。

## 6. 四 Brain 模型

```text
                Family Brain
              (Understand Family)
                     │
                Need / Goal
                     ↓
                Action Brain
        (Decide / Plan / Coordinate)
                     │
          ┌──────────┴──────────┐
          ↓                     ↓
         AI                Society Brain
                    (Resource Intelligence Network:
                     Human / Institution / Service)
          └──────────┬──────────┘
                     ↓
                   Action
                     ↓
                  Outcome
                     ↓
              Evolution Brain
       (Learn / Evaluate / Controlled Evolution)
```

- **Family Brain**：我们正在面对什么？
- **Action Brain**（新增于此次修订）：下一步该怎么办？防止系统停在"很会理解、
  很会建议，但事情没有真正发生"。
- **Society Brain**：谁或什么资源可以帮助？长期升级为 **Resource
  Intelligence Network**（见 §7），不是"找老师的大脑"。
- **Evolution Brain**：哪些方法真正有效，以后如何做得更好？必须是**受控进化**
  （见 §8），不是自动修改自己。

## 7. Society Brain = Resource Intelligence Network，资源统一抽象为 Capability

```text
Resource --provides--> Capability --applies_to--> Need --produces--> Outcome
```

课程、教师、医生、心理师、AI Agent、社区、学校，全部是 `Resource Type +
Capability` 的具体实例，不污染平台内核：

```text
课程   = Resource Type: Program,      Capability: structured_learning
教师   = Resource Type: Human,        Capability: mathematics_tutoring
心理师 = Resource Type: Professional, Capability: licensed_mental_health_service
```

**可执行判据**：任何新品类接入如果要求修改 Family/Need/World State/Goal/Plan
这条主链的 schema，说明设计违反了本条——这条判据同时是 §11 Vertical Pack
机制的验收标准。

**资源排序禁止商业化污染**：目标函数方向性冻结为

```text
Expected Outcome × Family Fit × Evidence Quality × Trust × Safety ×
Availability × Preference Fit ÷ Cost / Burden
```

商业利益（佣金/广告位/出价）只能作为独立变量存在，**不得**作为排序目标函数的
输入项。违反本条等价于把 AiFamily 退化成"家庭版大众点评/电商/广告平台"，
是对 Family Intelligence 战略价值的直接破坏。

## 8. Outcome 与受控进化

### 8.1 Outcome Contract

任何 Plan 执行前应尽量明确：期望发生什么变化、多久观察、如何判断改善、谁反馈、
何时停止、何时升级。Outcome 类型必须多元：`Self-reported / Observed /
Behavioral / Assessment / Professional / System Inferred / Long-term`，且
必须能记录 `No Change / Negative Outcome / Unexpected Outcome`——Evolution
Brain 不能只学习成功案例。

### 8.2 受控进化，不是自动修改自己

```text
Outcome Data → Pattern Discovery → Hypothesis → Offline Evaluation →
Expert Review → Experiment → Safety/Outcome Gate → Limited Rollout →
Production
```

不是 `AI发现规律 → 直接修改生产策略`。涉及孩子/健康/心理/财务/养老的场景，
治理能力是核心产品能力，不是合规负担。

## 9. Family Memory 分区：基础架构，不是后加的隐私功能

```text
Private Member Memory / Shared Family Memory / Guardian-visible Memory /
Professional Shared Context / System Operational Memory / Derived Intelligence
```

每类信息必须携带 `owner / visibility / consent / purpose / source /
confidence / retention`。**禁止把某一家庭成员私下表达的内容默认同步给其他
成员**（例如孩子私下表达默认进入父母共享档案）。这是 R6/R9 在家庭多主体场景下
的具体化，不是新增合规要求。

## 10. Family Principal Agent（"法咪莉校长"技术定位）

"法咪莉校长"这个中文 IP 保留，因为有认知度和温度，但技术角色冻结为
**Family Principal Agent**：家庭长期总协调人 + 家庭智能伙伴 + 资源导航者 +
行动组织者，**不是**万能老师/万能医生/万能心理师/万能人生导师。

必须具备 **Know / Don't Know / Escalate** 能力，能明确输出以下判断之一而不
伪装全知：

```text
I know. / I have a hypothesis. / I don't know yet, need more information. /
AI should not decide this. / A professional should evaluate this. /
The family must make this decision.
```

## 11. Vertical Pack 机制：解决"战略宽、产品窄"的具体办法

```text
Family Intelligence Core
（Family/Members/Relationships/Consent/Family World State/Needs/Goals/
 Decisions/Plans/Resources/Actions/Outcomes/Evidence/Unknowns/Risks）
        ↑ 只能被 Vertical Pack 通过 Capability/Resource 接口调用
        │ 不得被 Vertical Pack 要求修改主链 schema
        │
Vertical Packs
（Child Growth ← FIRST WEDGE / Education / Family Relationship / Health /
 Career / Elder Care / ...）
```

每个 Vertical Pack 只声明：`Domain Ontology / Need Types / Evidence Types /
Risk Rules / Capability Types / Outcome Metrics / Professional Boundaries /
Workflows / UI Components`。

**第一阶段只交付 Child Growth Vertical Pack V1**，其余 Pack 是架构预留，
不在当前阶段建表——这正是"战略边界宽、产品边界窄"在工程上的落地形式。

## 12. R2–R10：新主干（供后续排期参考，不直接改写现有 Wave/Sprint 编号）

| 蓝图 | 新定位 | 核心问题 |
|---|---|---|
| R2 Family Foundation | Family Identity / Member / Relationship / Consent | 这是哪个家庭？谁和谁是什么关系？ |
| R3 Family World State | Family World State + Evidence + Unknown | 我们真正知道这个家庭什么？ |
| R4 Need Intelligence | Expression → Need → Hypothesis | 这个家庭真正需要解决什么？ |
| R5 Goal & Decision Intelligence | Goals / Options / Decision | 希望发生什么变化？应该做什么选择？ |
| R6 Action Intelligence | Plan / Task / Workflow / Agent | 怎么把决定变成行动？ |
| R7 Capability & Resource Network | Capability Registry + Society Brain | 谁能够帮助？ |
| R8 Outcome Intelligence | Outcome Contract / Measurement / Feedback | 事情最后有没有改善？ |
| R9 Evolution Intelligence | Learn / Experiment / Evaluate / Governance | 系统如何从真实结果中学习？ |
| R10 Family Experience Layer | Principal / App / Web / Voice / Avatar / Live | 家庭如何和整套智能系统持续互动？ |

课程/测评/专家/教师/直播/21天成长营不再是 R2-R10 的一级结构，全部进入
Vertical Pack 层（§11）。

**本表是否正式 Supersede `docs/11_delivery/CURRENT_PROGRAM_PLAN.md` 现有的
Wave/P0-P6 排期，需要总架构师与项目负责人另行确认，本文件不越权直接生效为
执行排期**（`ADR-0169` Enforcement 段第 4 条）。

## 13. 第一阶段仍然极度聚焦孩子成长——本次战略扩大不等于研发范围扩大

第一阶段完整验证的唯一路径：

```text
Parent/Child Expression → Family Context → Need Discovery → Evidence/Unknown
→ Goal → Plan → AI/Parent/Child/Teacher/Expert → Action → Outcome →
Family World State Update → Learning
```

跑通这一条，AiFamily 就已经是 Family AGI，不是课程平台——不需要先跑通养老/
保险/医疗才算数。

## 14. 当前明确不做（与上述本体决定具有同等约束力）

```text
不建"大而全家庭超级App"
不一次性建完 Family World State 全部字段
不做医疗诊断
不做家庭理财产品
不建养老商城
不建复杂社会资源市场（当前只需 Distribution 雏形）
不给每个垂直业务单独开发 Agent
不把课程/教师/专家写入平台 Core（ADR-0168 已冻结，本条重申并泛化到任何 Vertical）
不把所有聊天自动写入永久 Family Memory
不让 Agent 无审计地修改 Family World State
```

## 15. 技术纪律：AGI-native，但不是一个超级 Agent

不是"一个巨大 Prompt + 一个超级 Agent + 所有家庭数据"，而是：

```text
Family Intelligence Runtime
├── World State Service       ├── Capability Registry
├── Need Intelligence          ├── Resource Intelligence
├── Goal / Decision Engine     ├── Agent Runtime
├── Planner                    ├── Workflow Runtime
├── Outcome Engine              ├── Memory & Evidence
├── Policy / Consent / Safety   └── Evolution System
```

LLM 是其中的 Intelligence Engine，**LLM ≠ Platform**——与既有 Python-only
方向一致：统一的 Family Intelligence Runtime，不为课程/测评/教师分别写一套
AI 逻辑。

## 16. 护城河：五类长期资产

```text
① Longitudinal Family World State   长期家庭理解
② Family Need Graph                 家庭真实需求图谱
③ Need → Action → Outcome Graph     哪些方法对哪些家庭真正有效
④ Resource Outcome Graph            谁在什么条件下最适合解决什么问题
⑤ Family Trust Graph                家庭与AI/专家/机构长期形成的可信关系
```

模型可以更换、Agent 框架可以更换、数字人模型可以更换、UI 都可以彻底换；
十年的家庭理解+需求变化+行动结果+资源履约结果难以复制——这才是战略数据资产。

## 17. 商业模式：三层收入体系

```text
① Family Intelligence Membership   长期理解/记忆/规划/陪伴/协同/追踪
② Professional / Resource Services 教师/教练/专家/健康/生活/养老/家庭服务交易
③ Family Infrastructure Services   面向学校/机构/保险/健康机构/企业福利/政府社区
```

商业飞轮：`Better Family Understanding → Better Need Discovery → Better
Decisions → Better Resource Matching → Better Outcomes → Higher Trust →
More Family Context → Better Family Intelligence`，不是传统电商
`Traffic → Product → Transaction`。

## 18. 北极星：Family Outcome，不是服务家庭数或日活

```text
有没有更准确理解家庭？
有没有发现真正问题？
有没有减少无效行动？
有没有促成正确资源介入？
有没有产生实际改善？
家庭是否越来越有能力自己解决问题？
```

**最后一条尤其重要**：好的 Family AGI 不应该让家庭越来越依赖 AI，而应该让
家庭本身变得更有能力——从"AI 替家庭做事情"升级为"AI 帮助家庭形成更好的理解力、
判断力、行动力和连接社会资源的能力"。

## 19. 使命陈述（正式版）

> **AiFamily 不以教育为边界，而以 Family 为边界。**
> **我们从孩子成长进入家庭，但最终服务的是整个家庭系统。**
> **AiFamily 长期理解家庭成员、关系、环境、需求、目标、约束与变化，帮助家庭
> 发现真正的问题、形成更好的决策、采取有效行动，并连接最适合的 AI、人和社会
> 资源。**
> **每一次行动都产生 Outcome，每一次 Outcome 都让系统更理解家庭，也让整个
> Family Intelligence Network 变得更聪明。**
> **最终，我们希望让每一个家庭都拥有一套真正属于自己的 Family Intelligence。**

三个核心资产：**One Family / One Family Intelligence / One Connected
Resource Network。**

> We are not building an education platform for families. We are building
> the intelligence infrastructure through which families understand,
> decide, act, and connect with society.

## 20. Platform Core 六门准入测试（`ADR-0171`）

任何要进入 Platform Core 的新增代码，必须能回答"这项改动增强了以下六项中的
哪一项"，否则归入 Vertical Pack 层（§11），不得进入 Core：

```text
1. World Model      是否让系统更准确理解家庭状态？
2. Memory            是否改善了跨会话/跨时间的家庭记忆？
3. Goal / Planning   是否改善了目标澄清或行动规划的质量？
4. Action / Tool     是否改善了行动执行或工具调用的可靠性？
5. Outcome Learning  是否改善了从真实结果中学习的能力？
6. Safety / Evaluation 是否改善了安全边界或评估治理？
```

课程/测评/教师/直播/活动无论多重要，都不能以"业务很重要"为理由绕过这条
测试直接进入 Core。当前仅为文档层判据，无自动化测试，靠 code review 人工
把关（见 `ADR-0171` Enforcement 段）。

## 21. 本文件的维护规则

- 本文件描述**不可破坏原则**，变更频率应当很低，且任何修改必须先有新 ADR
  （参照 `SYSTEM_MANIFEST.md` §9 的同等纪律）。
- 具体排期变化 → 改 `docs/11_delivery/CURRENT_PROGRAM_PLAN.md`，不改本文件。
- 具体域实现/代码结构变化 → 改对应 `docs/04_domains/`/`docs/06_platform/`
  文档，不改本文件。
- `docs/01_strategy/FAMILY_AGI_PLATFORM_BLUEPRINT.md` 记录本文件背后的完整
  推理过程与仍在演化的细节设计（`canonical: false`），本文件是其被 `ADR-0169`
  正式冻结的摘要，两者不重复维护，前者修订时应对照本文件核实是否产生冲突。
