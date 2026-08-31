---
id: BIZ-CAPABILITY-PRIORITY-002
title: AiFamily 业务能力地图与建设优先级 V1
type: business
status: draft
version: 1.0
owner: chief-architect
created: 2026-08-31
updated: 2026-08-31
canonical: false
supersedes: null
superseded_by: null
---

# AiFamily 业务能力地图与建设优先级 V1

> 本文件是 `AIFAMILY_BUSINESS_SCENARIO_CAPABILITY_BLUEPRINT_V1.md` 的能力与建设视图，吸收项目负责人提供的《AiFamily 业务能力地图与建设优先级 V1.0》作为研究输入。它描述 Target 与建设顺序，不替代 canonical `BUSINESS_CAPABILITY_MAP.md` 对 Current Truth 的登记，也不授权直接新增 Domain、数据库表或服务。

## 1. 这张地图解决什么

这张地图把战略和场景转换为可排期、可验收的能力增量：

```text
家庭场景与结果
  → 业务能力
  → 产品交互与专业服务
  → canonical 对象/receipt
  → AI 工作流
  → 应用与平台接口
  → 场景 Backlog、测试与证据
```

它回答五个问题：

1. 哪些能力构成 AiFamily 的差异化内核；
2. 哪些能力必须跨场景复用，哪些可以独立演进；
3. 全量 MVP 的六个场景分别调用哪些能力；
4. 每项能力现在真实到什么程度，下一次增量是什么；
5. 如何按依赖并行建设，而不是按页面、团队或技术目录堆功能。

业务能力不是组织架构，也不是代码包。一个能力可以由多个 Domain 协作，一个 Domain 也可以承载多个相邻能力；映射必须经 Registry、ADR 和 owner 裁决。

## 2. 八个能力系统

研究输入名为“八大能力域”，正文实际出现 A–J 十组。为避免把 ACN、Data 或小橘灯各自复制成平台，本版收敛为八个稳定能力系统：

| 编号 | 能力系统 | 主要家庭价值 | 定位 |
|---|---|---|---|
| A | Family Foundation | 知道谁在什么家庭上下文中获得服务 | 共享基础 |
| B | Family Growth Kernel | 把问题转成可观察的成长过程与结果 | 差异化核心 |
| C | Family Intelligence Runtime | 理解、澄清、检索、提出方案并支持复盘 | 差异化核心 |
| D | Family Service Network | 在 AI/自助不足时连续升级真人服务 | 服务网络 |
| E | Knowledge & Evidence Network | 让理解和介入有来源、适用范围与版本 | 专业基础 |
| F | Relationship & Media Network | 连接家庭经验、活动、内容与小橘灯 | 网络扩展 |
| G | Product & Supply Platform | 把验证过的介入设计成可交付方案 | 供给平台 |
| H | Platform Operations, Data & Governance | 让全链可运行、可回读、可运营和可评估 | 横向底座 |

原 ACN Collaboration 并入 D 的协同交付能力；原 Data Platform 并入 H；小橘灯保留独立产品边界，但通过 AiFamily Platform Core 与主链对接。三项最深内核仍是：

```text
Family Foundation
  + Family Growth Kernel
  + Family Intelligence Runtime
```

## 3. 能力分解

### A｜Family Foundation

| 能力簇 | 目标语义 | 首个场景增量 |
|---|---|---|
| A01 Identity & Session | Account、登录、会话与设备可信上下文 | 成人可进入并恢复会话 |
| A02 Family Aggregate | Family 生命周期与家庭锚点 | 创建/加入并回读一个家庭 |
| A03 Membership & Relationship | 成员、关系与生命阶段 | 选择当前服务对象，不自动推断权限 |
| A04 Guardian & Purpose Grant | Guardian 关系与按目的授权 | 明确谁可确认、分享和撤回 |
| A05 Family Context | 与当前问题有关的最小上下文 | 渐进补充，不以首次完整画像为门槛 |

### B｜Family Growth Kernel

| 能力簇 | 目标语义 | 首个场景增量 |
|---|---|---|
| B01 Problem Intake | 表达一次真实事件、困扰或需要 | 保存原始表达与相关人物/情境 |
| B02 Need/Case Continuity | 需要持续处理时维持责任与历史 | 以现有 `GrowthIntent`/Case 引用承接，FamilyNeed 待 ADR |
| B03 Assessment | 按明确证据缺口调用版本化评估 | 轻量专项评估；证据足够时允许跳过 |
| B04 Goal | 定义 baseline、观察窗口与目标状态 | 家长确认一个可观察目标 |
| B05 Intervention | 管理介入候选、依据、适用与升级条件 | 选择一个最小充分家庭成长介入 |
| B06 Action & Observation | 计划、执行、障碍和具体观察 | 记录发生了什么，不把完成等同效果 |
| B07 Reflection | 比较预期与实际，形成继续/调整/暂停决定 | 完成首次阶段复盘 |
| B08 Outcome | 分层记录改善、未变、恶化或未知 | 形成带不确定性的阶段结果 |
| B09 Escalation | 从自助/AI升级到具名真人责任链 | 明确升级原因与上下文交接 |

Family Growth Kernel 不是一张巨型表或一个全局状态机。Problem/Need、Assessment、Goal、Intervention、Action、Service 各自维护边界内生命周期，通过 versioned ref、event 与 receipt 衔接；跨域旅程状态是投影，不成为第二事实源。

### C｜Family Intelligence Runtime

| 能力簇 | AI 工作 | 必须输出的产品价值 |
|---|---|---|
| C01 Conversation Workflow | 维持一次有目标的多轮协作 | 用户知道当前在解决什么 |
| C02 Understanding | 从多模态表达提取 Situation/People/Behavior/Emotion/Frequency/Context/History/Unknown | 可编辑的“我们目前这样理解” |
| C03 Clarification | 判断关键缺口并生成少量高价值追问 | 每个问题说明为什么要问 |
| C04 Confirmation | 对比原话、理解与修正 | 家长可确认、修改、拒绝或暂停 |
| C05 Context Assembly | 按目的组装 Family、历史 Need、Assessment、Action、Outcome | 有关且不过载的上下文 |
| C06 Evidence Retrieval | 检索版本化知识与证据 | 显示依据、适用范围和未知 |
| C07 Intervention Drafting | 形成多个可比较介入候选 | 为什么适合、负担、替代和停止条件 |
| C08 Next Best Support | 在知识、评估、行动、真人服务和资源间导航 | 给出一项最有价值的下一支持，不是无限推荐流 |
| C09 Reflection Copilot | 归纳观察、矛盾与实施偏差 | 帮家长看清变化与仍未知 |
| C10 Risk & Human Handoff | 形成风险草案并结构化交给具名责任人 | 不中断用户、不过度承诺的人工接管 |
| C11 Evaluation & Learning | 固定回放、修正样本与结果评估 | 知道模型在哪些家庭场景真正有帮助 |

不要求所有 Agent 自由输出同一个大段文本。按任务使用 `UnderstandingDraft`、`InterventionDraft`、`ReflectionDraft` 等类型化结果，并共享以下 envelope：

```text
purpose / context_refs / evidence_refs
output_type / output_version
model / prompt / tool provenance
unknowns / confidence_boundary
requires_confirmation / requires_human
next_options / recovery
```

### D｜Family Service Network

| 能力簇 | 目标语义 | 建设阶段 |
|---|---|---|
| D01 Provider & Organization | Teacher/Expert/Advisor/Organization 统一供给主体 | MVP 最小；P1深化 |
| D02 Capability Profile | 领域、年龄段、方法、资质、形式与容量 | MVP 最小 |
| D03 Matching | Need、适用、语言、时间、地点与历史履约匹配 | 先人工/规则，再 AI 辅助 |
| D04 Booking & Order Intent | 可用时间、预约、价格和取消 | 全量 MVP 最小闭环 |
| D05 Service Case & Session | 责任人、目标、交付、观察和 SLA | 全量 MVP 最小闭环 |
| D06 Remedy | 缺席、改期、失败、投诉、退款/补救 | 全量 MVP 必须可恢复 |
| D07 Family Advocate | 跨阶段连续性与资源协调 | 先作为 ServiceCase coordinator 角色投影 |
| D08 Collaboration & Contribution | 多角色贡献事件、争议与分配 | MVP只留可追踪交付；复杂结算后置 |

### E｜Knowledge & Evidence Network

| 能力簇 | 目标语义 | 首个增量 |
|---|---|---|
| E01 Problem Taxonomy | 统一但可版本化的问题语言 | 覆盖首个 Golden Journey 主题 |
| E02 Evidence Registry | 来源、版本、质量、适用、限制与复核 | 一个可引用证据包 |
| E03 Intervention Evidence Map | Evidence 支持/反对哪些介入及条件 | 支撑一个介入选择 |
| E04 Knowledge Item | 面向家长/专业人员的可读知识单元 | 一个有版本和引用的主题包 |
| E05 Experience Evidence | 区分家庭经验、专业观点与研究证据 | 首版仅受控经验卡 |
| E06 Evidence Graph | Problem/Need—Evidence—Intervention—Observation/Outcome 关系 | 从引用链开始，不先造大图谱 |

### F｜Relationship & Media Network

| 能力簇 | 目标语义 | 全量 MVP 深度 |
|---|---|---|
| F01 Search & Discovery | 按明确查询/Need发现知识、行动、服务和媒体 | 可搜索一个主题，诚实空态 |
| F02 Content & Collection | 文章、音频、视频、收藏与版本失效 | 一个审核内容包 |
| F03 Family Experience & Activity | 受控经验、活动和互助 | 主题活动/经验卡/加入/退出/举报 |
| F04 Xiaojudeng | 直播发现、观看、互动、回放与运营 | MVP仅接一个已审核资源分支；产品队列独立演进 |
| F05 Resource-to-Growth | 将资源带回理解、介入、行动或服务主链 | 观看/收藏不冒充 Outcome |

### G｜Product & Supply Platform

| 能力簇 | 目标语义 | 建设策略 |
|---|---|---|
| G01 Offering Studio | Problem/Audience/Outcome/Intervention/Delivery/Price | 先配置一个方案 |
| G02 Intervention Studio | 适用、依据、流程、负担、风险、停止和结果 | 先人工配置+版本审核 |
| G03 Program Studio | 7/14/21天等结构化服务编排 | P1，复用 Journey/Action |
| G04 Assessment Studio | 测评工具版本、维度、问题与解释配置 | P1，首版可代码配置 |
| G05 Course/Live Studio | 课程和直播作为 Delivery | P2；不新建家庭事实源 |

### H｜Platform Operations, Data & Governance

| 能力簇 | 目标语义 | 首个增量 |
|---|---|---|
| H01 Named Action & Authorization | 谁能执行什么业务动作 | 每个写操作具名并 fail-closed |
| H02 Consent, Audit, Outbox, Idempotency | 同意、追溯、可靠事件与重放 | 与首个 durable 场景同事务验证 |
| H03 Retention & Deletion Lineage | 原始、派生、缓存、索引与供应商副本一致处理 | 覆盖首个多模态输入 |
| H04 Event & Receipt Model | 稳定跨场景交接 | 为 S1→S2 定义最小 receipt |
| H05 Operations | Growth/AI/Risk/Evidence/Service/Media 运营 | 先提供断点和补救队列 |
| H06 AI Evaluation Data | 修正、拒绝、失败、人工接管与 Outcome 样本 | 从首个场景开始积累 |
| H07 Analytics | 旅程、帮助感、履约、成本和恢复 | 先定义指标分母、窗口和数据源 |

## 4. S1–S6 与能力调用

全量 MVP 的发布范围仍是 S1–S6；建设优先级只决定依赖顺序和每项能力做到多深，不允许用 P0 单链替代全量 MVP。

| MVP 场景 | 用户结果 | 主能力 | 依赖能力 |
|---|---|---|---|
| S1 首次被理解 | 问题被表达、理解、修正并确认 | A、B01–B04、C01–C06、E01–E03 | H01–H04 |
| S2 成长循环 | 选介入、实践、观察、复盘 | B05–B08、C07–C09 | E、H |
| S3 知识与 AI | 看见依据、选择与未知 | C、E | A、B、H |
| S4 专业服务 | 找到责任人、完成履约并可补救 | D | A、B09、E、H |
| S5 家庭关系 | 在受控主题中连接经验与活动 | F01–F03 | A、E、H |
| S6 价值转化 | 按明确需要选择方案、权益和购买意向 | G01、D04–D06 | A、B、H |

F04 小橘灯在第一阶段以“一个已审核资源能进入 J6 并返回主链”的接口深度参与，不要求完整直播产品成为 AiFamily 发布前置；它的独立路线自行建设完整能力。

## 5. 建设优先级：P0 / P1 / P2

### P0 / Now｜打通 Golden Family Loop，同时铺开全量 MVP 薄切片

主链：J0→J1→J2→J3→J4→J7。家庭能表达一个问题、修正理解、按需评估、确认目标、选择介入、记录观察并首次复盘。

并行薄切片：

- S3：一个知识包进入理解和介入，并可核对来源；
- S4：一个真人服务方案可查看、预约、履约、反馈和补救；
- S5：一个审核主题活动/经验可加入、退出、举报；
- S6：一个方案可比较、形成购买意向、读取权益并取消。

P0 的完成不是“对象都建了”，而是六个场景都能在同一家庭上下文中运行、退出和恢复；Golden Loop 达到较深闭环，其余场景达到真实而窄的最小深度。这里的 P0 等于第一阶段全量 MVP 发布候选，不等于只做 S1 或只做技术底座。

### P1 / Next｜证明 AI + 真人连续服务

深化 Provider/Organization、Capability Profile、Matching、ServiceCase、Human Handoff、SLA、Remedy；扩展专项 Assessment、Evidence Map、Intervention Studio 和长期 Outcome。目标是同一 Need 能从 AI/知识无缝升级到具名真人，再把服务观察带回家庭复盘。

### P2 / Later｜形成知识、媒体与平台网络

深化 Evidence Graph、Search、Family Experience、Community、小橘灯完整媒体链、Program/Course/Live Studio、机构协作和贡献分配。Later 不表示现在完全不做研究或隔离 PoC，而是不让网络规模化抢占 Golden Loop 与履约质量的主路径。

## 6. 能力依赖 DAG

```text
Family/Guardian Context (A)
  ├─→ Problem/Need/Goal (B01-B04)
  │     ├─→ Understanding/Clarification/Evidence (C02-C06 + E)
  │     ├─→ Intervention/Action/Reflection/Outcome (B05-B08 + C07-C09)
  │     └─→ Escalation/Service (B09 + D)
  ├─→ Relationship/Media access (F)
  └─→ Offering/Entitlement/Order Intent (G + D04)

Platform actions, Consent, Audit/Outbox, Idempotency,
Deletion, Receipts and Evaluation (H) support every edge.
```

并行规则：不同团队可以同时实现互不重叠的场景薄片、adapter、UI、测试或知识包；共享对象、组合根、Registry 和 migration 由单一 owner 收口。发生接口冲突时暂停冲突文件，不暂停所有无冲突工作。

## 7. 能力成熟度

| 等级 | 定义 | 可声称的结果 |
|---|---|---|
| L0 Absent | 无 owner、contract、实现或证据 | 仅 Target |
| L1 Manual Validated | 人工可完成且责任清楚 | 场景假设被验证 |
| L2 Structured | 对象、状态、接口、receipt 与恢复结构化 | 可重复交付 |
| L3 AI Assisted | AI在明确任务中辅助，人可修正/接管 | 效率与体验提升有评测 |
| L4 AI Native | Context、工具和评测驱动的主动工作流 | 在稳定质量与成本边界内持续优化 |

成熟度不等于环境晋级。L3/L4 的 synthetic 证据不能自动成为真实环境或生产能力；同一能力必须分别记录 branch、commit、main、artifact、real environment 与 production evidence。

## 8. Current Truth 与 Target 的分离

正式 Current Truth 以 `governance/CAPABILITY_REGISTRY.yaml`、`governance/DOMAIN_REGISTRY.yaml`、`governance/MIGRATION_MANIFEST.yaml` 和 `docs/00_system/CURRENT_SYSTEM_BASELINE.md` 为准。本文件只给规划快照：

| 能力系统 | 当前判断 | 证据入口 | 近期决策/缺口 |
|---|---|---|---|
| A Family Foundation | Platform identity/authorization/consent 有测试基础；完整 Family 聚合与真实账号接线未闭合 | `backend/platform/{identity,authorization,consent}`、`governance/DOMAIN_REGISTRY.yaml` | Family/Account/Person/GuardianRelation 边界与实施 owner |
| B Growth Kernel | Assessment 已挂载；Journey 有持久化候选但未形成完整主链；Problem/FamilyNeed/Intervention/Outcome 运行时对象缺失 | `backend/domains/{assessment,journey}`、`backend/apps/family_api/main.py`、`database/migrations/versions/0004_journey_mvp_persistence.py` | FamilyNeed 与 GrowthIntent/Case；Intervention、Outcome owner |
| C Family Intelligence | Model Gateway 的 provider、structured draft、timeout、provenance 与 fail-closed 有测试；尚无完整业务调用链 | `backend/intelligence/model_gateway`、`docs/00_system/CURRENT_AI_MAP.md` | typed drafts、Context、Human Gate、eval 与场景接线 owner |
| D Service Network | ServiceProvider/Offering/Availability/Booking/Record 有代码与测试；真实家庭身份、SLA、Remedy 未闭合 | `backend/domains/service`、`tests/domains/service` | Provider/Organization/Advocate 与补救责任链 |
| E Knowledge & Evidence | Evidence/Provenance contract、Assessment grounding 与研究材料存在；不是完整 Knowledge Runtime | `backend/packages/contracts/evidence.py`、`backend/domains/assessment/domain/knowledge_grounding.py`、`docs/13_research/knowledge_compiled` | 一个真实主题包、Evidence Registry/Map 与审核 owner |
| F Relationship & Media | Mobile 有页面/内容 helper，S5 有 synthetic 候选；没有 Community/Search/Media canonical 后端 | `frontend/mobile/lib/family/community-content.ts`、`database/baseline/0026_expert_live_session_operation.sql` | Community backend、ContentVersion/MediaAsset 与小橘灯接口 owner；SQL 快照不算运行能力 |
| G Product & Supply | ServiceOffering、Membership、Product Intelligence 是相邻候选，不能冒充各类 Studio | `backend/domains/{service,membership,product_intelligence}` | 统一 Offering/Delivery Blueprint、Entitlement/Order Intent owner |
| H Platform Ops/Data | Audit、idempotency、persistence 和局部 Outbox/SQLAlchemy 已存在；完整运营、receipt、删除和跨场景原子闭环未形成 | `backend/platform/{audit,idempotency,persistence}`、`database/migrations` | Event/Receipt/Outbox、Deletion、Analytics、AI Evaluation owner |

任何 `Candidate`、`MIGRATED_TESTED` 或局部测试通过都不等于全量产品、main、真实环境或 production。

### 8.1 已发现的治理漂移

本快照还发现四项需要单独修复的事实漂移：

1. 部分 L0 文档或 Registry 注释仍称“无业务 API”，但当前组合根已经存在 Assessment、Membership、Service 等挂载；
2. Model Gateway 在 Domain Registry 与 Migration Manifest 的状态表述不完全一致；
3. 数据库迁移在 Registry、Manifest 与磁盘之间存在 `NOT_STARTED`、`IN_PROGRESS` 和真实文件并存；
4. Assessment 在 Migration Manifest 中存在不同代际条目，Capability Registry 头部说明也未完全反映当前实况。

这些漂移必须由相应 registry owner 基于代码、测试和环境证据校正。本文件不通过挑选有利条目自行宣布能力完成，也不直接修改共享登记。

## 9. 对象与 Domain 裁决清单

本地图中的对象名是目标业务语义，不是建表指令。实施前优先裁决：

1. `FamilyNeed` 与现有 `GrowthNeed`、`GrowthIntent`、`Problem`、`ServiceCase` 的关系；
2. Problem 与持续 Case 是否同一聚合的不同阶段；
3. Assessment Evidence、通用 Evidence 与 KnowledgeReference 的所有权；
4. Goal 归 Growth，Plan/PhaseReview 归 Journey，Action/Observation 与 Outcome 的边界；
5. Provider、Teacher、Expert 与 Organization 的统一主体模型；
6. Offering、ServiceOrder/OrderIntent、Entitlement 与真实资金订单的关系；
7. Community、Content 与小橘灯 Media 的事实、审核和删除接口；
8. Contribution Event 属 Service 协作，现金 Settlement 属 Commerce/Finance，二者不得混账。

不得直接按研究输入末尾的 `family-domain`、`growth-domain` 等目录清单创建十一个 Domain。先完成语义、owner、引用、生命周期和责任裁决，再决定一个或多个 canonical 实现边界。

## 10. 每项能力进入 Backlog 的标准

能力卡必须同时写清：

```text
capability_id / user_scenario / desired_outcome
actor / trigger / preconditions
canonical_inputs / canonical_outputs / receipt
current_evidence / target_maturity
owner / interface_owners / pathspec
positive_path / refusal / withdrawal / failure / recovery
environment / observable_metric
dependencies / stop_condition
```

缺用户结果、owner、输入输出或可运行验收的事项保持 `IDEA`；有文档而无代码/场景证据的事项保持 `DESIGNED`；只有用户可运行、可回读且正反路径通过后才能标 `SCENARIO_VERIFIED`。

## 11. 第一阶段完成定义

第一阶段不是“只完成 P0 内核模块”，而是全量 MVP 的六场景发布候选：

- S1 家长第一次感到被理解，并可修正；
- S2 家庭从理解进入介入、实践和复盘；
- S3 知识与 AI 给出有依据、可核对的帮助；
- S4 真人服务有责任人、履约和补救；
- S5 家庭通过受控主题获得经验或活动连接；
- S6 家长按明确需要比较方案、权益和购买意向。

六个场景必须共享 A/B/C 内核和 H 底座，具备可展示 UI、真实业务状态或明确只读事实、场景测试、恢复路径和相邻 contract。不能用文档数量、表数量、接口数量或单条技术链代替家庭结果。

## 12. 后续设计输出

本文件联合评审后，下一批输出应按顺序形成：

1. `Capability × Scenario × Owner × Current Evidence` 可执行矩阵；
2. FamilyNeed/GrowthIntent/Problem/Case/Outcome 的领域语义 ADR；
3. 每个 S1–S6 的 capability increment backlog；
4. 跨场景 receipt 与事件最小合同；
5. 领域模型与系统边界图；
6. 前端、API、AI、数据与 QA 的 Sprint 级 pathspec 和场景验收包。

领域边界图必须从能力和对象所有权推导，不能从希望创建的代码目录反推业务架构。
