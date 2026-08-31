---
id: DEL-PROGRAM-001
title: AiFamily 当前平台开发主计划 V3
type: delivery
status: current
version: 3.0
owner: chief-architect
created: 2026-09-01
updated: 2026-09-01
canonical: true
supersedes: null
superseded_by: null
---

# AiFamily 当前平台开发主计划 V3

> 本文件把战略蓝图、全量 MVP PRD、领域边界、Slice 01 规格与现有代码候选收敛成唯一执行主计划。版本 3 取代本文件历史中的 Wave 计划；历史版本继续由 Git 保存。主计划生效不等于候选实现、migration、main 或生产自动获准，具体施工仍按 owner、Task Card 和证据门执行。

## 1. 唯一目标

第一阶段交付一个符合蓝图的全量 MVP：家庭不只是看页面或完成测评，而能围绕一个真实需要完成理解、行动、复盘，并在需要时获得知识、关系或真人服务支持。

核心价值链：

```text
家庭表达
→ 共同理解与家长确认
→ 按证据缺口调用 Assessment/Knowledge
→ 确认阶段性 GrowthIntent
→ 选择最小充分家庭介入
→ 执行 Action
→ Reflection / Outcome Observation
→ 继续、调整、暂停或升级真人服务
```

这是一条主业务链，不是唯一开发任务。S1–S6 六个业务场景都属于全量 MVP，通过稳定 receipt、共享家庭上下文和 Platform Core 并行汇入主链。

## 2. 计划依据与文档链

主计划只消费下列候选输入，不再派生平行蓝图：

```text
价值主张
→ 场景与能力蓝图
→ 全量 MVP PRD
→ 领域模型与系统边界
→ Slice 产品规格
→ 本开发主计划
→ Task Card / Sprint Evidence
```

关键输入：

- `docs/01_strategy/AIFAMILY_VALUE_PROPOSITION_V3.md`；
- `docs/02_business/AIFAMILY_BUSINESS_SCENARIO_CAPABILITY_BLUEPRINT_V1.md`；
- `docs/02_business/AIFAMILY_BUSINESS_CAPABILITY_MAP_PRIORITY_V1.md`；
- `docs/04_domains/AIFAMILY_DOMAIN_MODEL_SYSTEM_BOUNDARIES_V1.md`；
- `docs/03_product/FAMILY_GROWTH_MVP_PRD_V2.md`；
- `docs/03_product/AIFAMILY_SLICE_01_PROBLEM_UNDERSTANDING_SPEC_V1.md`；
- `docs/03_product/AIFAMILY_SLICE_01_FULL_STACK_DELIVERY_SPEC_V1.md`。

旧版 `CURRENT_PROGRAM_PLAN.md` 的“唯一真实状态”和 Wave 叙述已与代码/路由事实漂移。版本 3 将真相核销列为 Sprint 0 首项，不用计划文本替代仓库证据。

## 3. Current / Candidate / Target

### 3.1 Current

- local `main=0fa84a1`，`origin/main=4c2b772`；
- Assessment、Membership、Service 已有不同程度的路由与实现，但正式依赖和真实环境成熟度不一致；
- Platform 的 Identity/Authorization/Consent/Audit/Idempotency/Persistence 与 Model Gateway 有局部实现和测试；
- Journey、FamilyNeed、Context Engine、Human Gate、Web、Service/FGCN 等存在多个候选 ref，不等于 main 能力；
- migration、组合根、owner、Registry 与真实 HTTP/PG/E2E 仍有漂移和分叉；
- UI-01/02/03 有可复用体验，但现有职责、评分表达、远程状态和主链衔接需要收敛。

### 3.2 Candidate

`family_need` 候选中已经出现 `NeedSignal`、`FamilyNeed`、澄清/确认及作用域语义，值得优先评审；但它不在 main，且其长生命周期状态、GrowthIntent、Journey、Assessment、ServiceCase 的边界尚未 Accepted。

其他 WIP 同样按逐提交/逐文件审查：

```text
REUSE       原语义与 owner 均正确，可直接消费
PORT        语义正确，从候选 ref 窄迁入
ADAPT       可复用但需按新契约改造
SUPERSEDE   已被更清晰实现替代
SANDBOX     仅研究/实验，不进入主链
DROP        重复、错误或无消费者
```

禁止整分支合并，也禁止以测试文件、commit message 或 WIP 状态宣称能力已完成。

### 3.3 Target

- 一条 Family Growth Journey；
- S1–S6 全量 MVP 场景；
- 六个稳定交付团队，不再按临时 Chat 无限增殖；
- 一条受控 Integration→Main 晋升路径；
- 每个增量都是 Full-Stack Vertical Slice；
- branch、commit、main、artifact、real environment、production 分层报告。

## 4. 核心业务语义待裁决

Sprint 0 的最小稳定主链先冻结为：

```text
NeedInput → UnderstandingSignal/version → GuardianDecision
→ GrowthIntent receipt → Journey → Action/Reflection/Outcome
```

`FamilyNeed` 是否成为覆盖多个阶段的长期 Aggregate 仍待 ADR；不得因为候选代码存在就直接接受。候选中的 `SOLUTIONING/FULFILLING/FULFILLED` 等状态可能侵入 Journey、Service 与 Commerce，必须逐项拆解 owner 后才能采用。

目标业务词汇建议：

```text
NeedSignal       家庭不可变的原始表达/Evidence
FamilyNeed       家庭正在面对什么、希望发生什么改变
GrowthIntent     家庭当前决定从哪个方向开始
Intervention     为什么采用某种支持方法
Action           谁在何时做什么
Reflection       参与者如何描述过程与体验
OutcomeObservation  在观察窗口中看见什么变化或未知
ServiceCase      真人服务的履约过程
```

若 ADR 接受 FamilyNeed 长期语义，一个 FamilyNeed 可以产生多个阶段性 GrowthIntent；若不接受，则由稳定 receipt/projection 组织过程，不另建超级聚合。ServiceCase 只在真人支持被选择后创建，不与 Need/Intent 合并。

但 `FamilyNeed` 当前仍是候选而非 canonical owner。进入实现前必须通过 ADR 证明：

1. 是否采用候选 `family_need` 作为唯一需求生命周期 owner；
2. 它与既有 `growth_need_inputs/signals/intents` baseline 的映射；
3. Assessment 只提供 Evidence/Hypothesis，不再直接拥有 GrowthIntent 写入；
4. Journey 拥有 Intervention/Action/Reflection 的范围；
5. ServiceCase 与 FamilyNeed/GrowthIntent 的引用关系；
6. 不新增平行 Problem、GrowthCase、ConfirmedProblem 或第二套 Intent。

## 5. 全量 MVP 六场景

### S1｜家庭表达、理解与确认

家长从 UI-01 用文字开始，也可选语音/图片；平台形成可修正理解，必要时按需进入 UI-02 Assessment，并在 UI-03/Understanding Map 确认当前重点。结果是版本锁定、可回读的 confirmation receipt。

### S2｜成长介入、行动与复盘

confirmed intent 进入最小充分 Intervention，家长选择并执行 Action，次日/约定时间记录 Reflection，系统支持继续、调整、暂停和 Outcome Observation。

### S3｜知识与多模态 AI

针对一个具体家庭主题，提供可理解的知识依据、Context Snapshot、typed AI Draft、可修正解释和 provenance。S3 服务 S1/S2，不是泛化聊天 Demo。

### S4｜真人服务履约

家庭主动选择真人帮助后，完成 Provider/服务说明、预约、履约、反馈和补救；专家获得经授权的必要上下文，家长不必从头重讲。

### S5｜受控家庭关系网络

围绕明确主题提供真实/明确 synthetic 的经验、活动、收藏/加入、退出/举报与审核撤回。MVP 不以无限流、陌生人私聊或家庭排名为核心。

### S6｜方案、权益与价值转化

从家庭已经确认的需要出发，比较方案、价格与权益，由家长主动形成购买意向。MVP 必须明确是“价值/购买意向验证”还是完整 sandbox 交易闭环，不能混称收入能力。

## 6. 组织重组：唯一 PMO + 六个交付团队

不新增同名团队或 Chat。现有人员/Agent 归入以下六队，每队一个 DRI；接口仍由 canonical owner 会签。

### Team 1｜Family Growth

负责 S1/S2 的端到端用户结果：Need Input/Understanding/Intent、Intervention、Action、Reflection、Outcome，以及与 Assessment/Journey 的交接。它不拥有 Platform 原语或 AI Provider；FamilyNeed 只有在 ADR 接受后才进入其 canonical 范围。

### Team 2｜Family Experience & Contract

负责 Mobile-first 体验、共享 API/Projection/Error contract、Web 消费端、恢复、可访问性、视觉质量和 artifact。不是静态页面团队，也不决定业务事实。

### Team 3｜Assessment, Knowledge & AI

负责版本化 Assessment、Evidence、Knowledge grounding、Context adapter、AI use case、eval 与专业解释。Assessment 不拥有 Generic Action/Reflection/GrowthIntent，AI 不拥有业务状态。

### Team 4｜Service & Value

负责 S4/S6：Provider、Booking、Delivery、Feedback/Remedy、Offering/Entitlement 与购买意向/交易候选。不得从孩子画像自动推销。

### Team 5｜Family Relationship

负责 S5 的主题、内容/活动来源、加入/收藏、退出/举报和 Moderator/Ops 接口。不得为了填页面伪造社区活跃度。

### Team 6｜Platform Reliability & Release

由三个互相制衡的 cell 组成：

- Platform Core：Identity/Tenant/Family scope、Consent、Audit/Outbox、Idempotency、UoW、Environment；
- Data/Architecture：Alembic、PostgreSQL、schema owner、Event/Receipt、Registry、架构测试；
- QA/Release：contract、Golden E2E、恢复/并发/重启、artifact、观测和发布回滚。

这三个 cell 共用计划和队列，但 Data owner 与 QA signoff 不能由业务 DRI 自行替代。

### 常驻辅助角色

- 唯一 PMO：优先级、依赖、owner、冲突、Evidence Board 与晋升裁决；
- 总架构师/总设计师：战略、产品/架构一致性和跨域最终裁决；
- 专家顾问组：研究、专业与竞品评审，不冒充代码 owner；
- 小橘灯：独立产品队列，通过 Platform Core contract 汇报，不进入 AiFamily 主线 WIP。

### 现有队列归并

| 新团队 | 现有队列归入 | 当前状态 |
|---|---|---|
| Team 1 Family Growth | 场景 S1-S2、Journey/Route C | 已有队列，DRI 待 PMO 回填 |
| Team 2 Experience & Contract | 体验系统｜全场景 UX·Web·Mobile | 已有队列，需指定 API contract owner |
| Team 3 Assessment, Knowledge & AI | 场景 S3、Assessment、AI Runtime 工作 | 已有队列，AI/Evidence owner 待统一 |
| Team 4 Service & Value | 场景 S4-S6、Service/Commerce/Membership 工作 | 已有队列，交易范围待裁决 |
| Team 5 Family Relationship | 原 Community/关系工作 | `MISSING_OWNER`，只能由 PMO 从现有成员指派，不新建平行团队 |
| Team 6 Platform Reliability & Release | 平台底座、Data/Migration、质量发布 | 已有队列归入一个计划；三类 signoff 仍相互独立 |

重复的 S1/S2、Assessment/AI、Service/Commerce、Platform/Data/QA 计划停止单独排优先级；专业 owner 保留，但只消费本主计划 Task Card。两个 PMO、多个 Integration Owner 或同名团队不得并存。

### 最小 RACI

- 产品范围与优先级：Accountable=Project Owner；Responsible=唯一 PMO；
- S1/S2：Accountable=Team 1 DRI；Teams 2/3/6 参与交付与会签；
- S3：Accountable=Team 3 DRI；Teams 1/2/6 提供场景、体验和发布接口；
- S4/S6：Accountable=Team 4 DRI；Teams 1/2/6 参与；
- S5：Accountable=Team 5 DRI；Teams 2/3/6 参与；
- UI/Projection/Error contract：Accountable=Team 2 contract owner；
- Platform、Migration、Release：分别由 Team 6 三个 cell owner Accountable；
- 跨域 ADR：Accountable=总架构师；Main/Production：Accountable=Release Authority。

每一事项只能有一个 Accountable。未回填真实负责人时明确标 `MISSING_OWNER`，不得用团队名称伪装 owner 已落实。

## 7. 两条后续业务线

在全量 MVP 保留薄入口，但不抢占 Family Growth 主链：

1. Standalone Live / 小橘灯：直播问题可转换为 NeedSignal，后续接 Family Growth Journey；其媒体、运营和产品节奏独立；
2. Platformization / B2B2C：Knowledge、Intervention/Product Studio、机构能力采购和长期 Growth Timeline，在核心闭环稳定后扩大。

复杂 Creator、开放式专家市场、ACN 自动结算、复杂 Commerce/Community 与大规模多 Agent 保持 Sandbox/Backlog，不伪装成第一阶段能力。

## 8. 6 Sprint × 2 周路线

Sprint 是规划窗口；独立场景可以在契约和 owner 明确后并行，不要求所有工作串行等待。

### Sprint 0｜真相核销与主干收敛

用户结果：一个 synthetic family 能从主客户端经真实 HTTP/PG 保存并恢复一条最小业务记录。

交付：

- 核销 Current docs、路由、Registry、migration head 与 WIP refs；
- 每个重要候选标记 REUSE/PORT/ADAPT/SUPERSEDE/SANDBOX/DROP；
- 裁决 FamilyNeed/GrowthIntent/Journey/Assessment/ServiceCase owner；
- 确定唯一 Integration owner 和受保护 branch；
- 关闭 Golden Slice 所需 ENV、DATA、IDP、LEDGER、AI、CLIENT 六门；
- 冻结共享 Projection、Error、Event/Receipt 与 Task Card 模板。

退出：Mobile→API→PostgreSQL→Audit/Outbox→restart/readback 在同一 ref 可复核。Web 当前缺正式运行基础，不伪造双端通过。

### Sprint 1｜M1 Family Understands Me

S1+S3 首片：表达→保存→1–3 个高价值澄清→结构化理解→修正→家长确认/拒绝→重启恢复。

交付 Mobile-first Full-Stack Slice、`family_problem_understanding_v1`、必要知识依据和真实 HTTP/PG。Assessment 是 Evidence 不足时的可选桥，不是固定第一关。

退出：家长能分别反馈“表达是否准确”和“是否感到被理解”；确认锁定其看到的版本，AI 不直接创建 business intent/fact。

### Sprint 2｜M2 Family Helps Me Act

S2 前半：FamilyNeed/confirmed intent→最小充分 Intervention→Action 选择→执行/未执行状态→恢复。

优先审查并适配 action-loop、today-action 与 Journey 候选；Generic Action 不留在 Assessment。

退出：真实用户场景跨进程可回读；Action 有 owner、时间、完成/放弃/调整语义，不以页面打卡等同效果。

### Sprint 3｜Reflection & Outcome

S2 后半：Action→Reflection→Barrier→Outcome Observation→继续/调整/暂停/升级。

Outcome 默认允许 UNKNOWN，必须包含 baseline、观察窗口、Evidence 充分性、来源差异和替代解释；服务完成或满意度不能自动关闭 Need。

退出：Need→Intent→Action→Reflection→Next Decision 的 Family Growth Kernel V1 可连续演示。

### Sprint 4｜M3 Human Help & Value

并行交付 S4 与 S6：

- AI/自助不足→家长确认共享→Provider/Booking→Delivery→Feedback/Remedy；
- 已确认需要→方案/价格/权益→主动购买意向，或完整 sandbox Order/Payment/Entitlement/Cancel/Refund 闭环。

退出：家长知道谁负责、买的是什么、失败怎么恢复；若只有购买意向，明确不宣称交易或收入。

### Sprint 5｜关系网络与全量 MVP Release

交付 S5 受控关系薄闭环，并将 S1–S6 串到同一家庭上下文和导航：`今天 / 问法咪莉 / 发现 / 成长 / 我的家庭`。

退出：六个场景分别有非 fixture UI、正反/恢复脚本、真实 HTTP/PG（适用时）、版本化 artifact、owner、观测和回滚；未达标场景标 `NOT_IMPLEMENTED`，不能用 Golden Loop 替代。

## 9. 关键依赖 DAG

```text
Truth/Owner/Contract/Migration
          ↓
S1 表达理解确认 ─────→ S2 Action/Reflection/Outcome
   │                          │
   ├── S3 Knowledge/AI ───────┤
   ├── S5 Relationship入口     │
   └── S6 Value入口            ├──→ S4 Human Service
                              ↓
                       Full MVP Release
```

并行规则：

- Experience 可先做真实内容的交互样机，但 fixture 不算能力；
- Knowledge/eval、migration research、accessibility 和 API contract 可并行；
- S5 的内容/审核闭环可独立构建，但接入家庭上下文前不宣称全量 MVP；
- S4/S6 可以强化现有候选，但不得绕过明确家庭需要；
- 小橘灯独立运行，不阻塞 DAG，也不改写主线对象。

## 10. 第一轮八张任务卡

### ARCH-01｜Branch Reality & Integration Plan

逐 ref 形成 disposition ledger，指定 Integration owner、merge order、组合热点和回滚点。输出证据，不创建“万能集成分支”吞并所有 WIP。

### DOM-01｜FamilyNeed Ownership Review

对候选 `family_need`、baseline growth 对象、Assessment、Journey 与 ServiceCase 做逐对象边界裁决，形成 ADR/Registry 建议。未接受前不新建 Domain 或表。

### PLT-01｜Golden Slice Platform Contract

交可消费的 tenant/family/actor、Consent、Idempotency、UoW、Audit/Outbox 合同；至少被 S1 一条真实场景消费，平台单测不能单独计完成。

### DAT-01｜Migration Chain Repair

解决重复 revision/多 head、baseline 与 ORM 差距，交 PostgreSQL upgrade→downgrade→restart→upgrade、schema 和 rollback 证据。

### AIR-01｜Family Understanding AI Contract

冻结 Context Snapshot、typed Draft、knowledge refs、provenance、eval dataset 与失败语义；通过 Model Gateway，不拥有 FamilyNeed/GrowthIntent 状态。

### EXP-01｜S1 Mobile Experience Skeleton

将 UI-01/02/03 收敛为 Concern、按需 Assessment、Understanding Map、Correction、Confirmation 与恢复体验；交真实中文内容、完整状态、视觉 artifact。Fixture 只计样机。

### API-01｜Workspace Projection & Error Contract

冻结 Mobile-first 的 Input→Signal/version→Decision→receipt Projection、Command、错误和幂等契约；Web 后续复用同一语义，不建立第二 API。

### QA-01｜S1 Golden E2E Harness

建立 Mobile→HTTP→PG→AI Draft→Correction/Confirmation→restart/readback 的逐片测试骨架；每片都跑 E2E，不到 Sprint 末补票。

## 11. 统一 Task Card

每个 Agent 任务必须在 1–2 天内可验证，并包含：

```text
Task ID
User scenario and observable result
Owner / interface owners
Exclusive pathspec
Dependencies and accepted input refs
Input / output contract
Positive acceptance
Negative / recovery acceptance
HTTP / database / restart evidence
Artifact and reproduction command
Files changed
Known gap and stop condition
```

前端、API、Domain/Data、AI 与 QA 可以由不同专业 Agent 承担，但它们属于同一个 Vertical Slice；任何一层不能脱离场景单独宣布 Done。

## 12. Integration 与晋升策略

```text
Feature branch
→ owner review
→ contract/domain tests
→ real PostgreSQL/HTTP
→ client scenario + recovery
→ architecture/quality
→ Integration candidate
→ Golden E2E + artifact
→ Main decision
```

- Integration branch 由唯一 owner 管理，不是长期第二 main；
- 所有候选必须记录 base、commit、pathspec 和依赖 ref；
- 共享热点 `main.py`、Registry、migration、contracts 分别由具名 owner 组合；
- 禁止整分支 cherry-pick、自动合入、reset/force push 或覆盖他人 WIP；
- unit test 通过不等于用户场景、main、真实环境或 production 通过。

## 13. DoR 与 DoD

### Definition of Ready

- 用户、触发、结果和不做事项明确；
- canonical owner/接口 owner 和窄 pathspec 已确认；
- 输入 ref、契约版本、migration head 和依赖明确；
- 正向、反向、恢复脚本先于代码；
- fixture、synthetic、real provider 的证据级别明确。

### Definition of Done

- 用户能在真实客户端完成场景，而非只看静态页面；
- API/Domain/Data/AI 的业务结果可回读；
- 业务变化、canonical Audit、Outbox 与 idempotency receipt 同一事务提交或回滚；AI/外部 provider 调用不持有该数据库事务；
- 重复、冲突、拒绝、撤回、超时、重启和跨家庭反例成立；
- 真实 HTTP/PG 与适用的 provider 证据可复现；
- 视觉、文案、响应式/可访问性和失败恢复经过体验验收；
- 交付截图/录屏、日志、构建物或可运行 artifact；
- branch/commit/main/artifact/real environment/production 六层状态如实登记。

## 14. 项目沟通与汇报

### 每小时团队回报

```text
Task ID:
User scenario completed this hour:
Command/environment:
Positive path:
Negative/recovery path:
Branch/commit/clean:
Artifact:
One blocker / owner needed:
Next command:
```

“正在研究”“文档已写”“单测通过”“分支存在”只能作为 supporting evidence。

### PMO 节奏

- 每小时：更新 Golden Journey 阻断、owner 与 next command；
- 每日：Integration/branch disposition、场景 burn-up、质量债和决策日志；
- 每 Sprint：现场演示、证据审阅、Continue/Correct/Pause/Drop 裁决；
- 冲突发现后立即冻结冲突文件，30 分钟内提交 owner/path/ref 事实，由总控裁决；不允许静默复制或绕开。

## 15. 进度与质量计量

全量 MVP 进度不按文档、页面、API 或 commit 数量计算。每个 S1–S6 独立计分：

```text
0  NOT_STARTED
1  UX/Contract candidate
2  Branch implementation
3  Same-ref automated scenario
4  Real HTTP/PG + artifact
5  Main verified
6  Production observed
```

第一阶段目标是六个场景都至少达到 4，主链 S1/S2/S3/S4 达到 5；任何平均数不能掩盖单场景为 0。

质量仪表盘至少包括：

- 用户场景完成率与恢复率；
- contract/schema 漂移；
- duplicate/timeout/restart/cross-tenant 失败率；
- AI Draft schema/provenance/eval；
- Migration fresh/restart 成功；
- 视觉回归与工程语言泄漏；
- blocker age、owner missing age 与返工率。

## 16. 明确停止

- 停止以空闲 Agent 为理由随机开模块；
- 停止新建同主题蓝图、同名团队、平行 PMO 或第二真相；
- 停止把 A–H 能力地图直接变成八个 Domain；
- 停止整分支合并、共享文件多人同时施工和假绿色；
- 停止只写后端、最后接 UI，或只画页面、没有业务状态；
- 停止用 fixture/no-op/synthetic 替代真实业务事实；
- 停止用 Completed、打卡、满意度替代 Outcome；
- 停止让 Assessment、AI、Service 或直播各自成为平台中心。

平台中心只有 Family Growth Journey；专业团队的价值由其是否让家庭更快、更准确、更可靠地完成这一旅程来衡量。

## 17. Sprint 0 开工门

1. 唯一 PMO 将六队 DRI、Integration owner 与 Release Authority 回填到 Program Board；
2. 完成 Current Truth/L0/Registry/路由/migration 核销；
3. 六个团队 DRI、接口 owner 和现有 Chat 归并映射完成；
4. FamilyNeed/GrowthIntent/Journey/Assessment/ServiceCase ADR 裁决；
5. 第一轮八张 Task Card 的 pathspec、依赖 ref 和退出门签核；
6. 建立单一 Evidence Board 与 Integration owner；
7. Sprint 0 Golden Slice 演示通过后，才进入 Sprint 1 正式施工。

本计划是唯一排程入口；它本身不自动变更 main、Registry、migration 或生产状态。后续不得新增含 `PLAN/REPLAN/MASTER_PLAN` 的平行执行文档，只允许 Task Card、Sprint Evidence、Decision Log 与 ADR。
