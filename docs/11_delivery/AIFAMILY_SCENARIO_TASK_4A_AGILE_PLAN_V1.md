---
id: AIFAMILY-SCENARIO-TASK-4A-AGILE-PLAN-001
title: AiFamily 场景—任务—4A 架构—敏捷迭代计划
type: delivery-plan
status: draft
version: 0.1
owner: AG-00
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# AiFamily 场景—任务—4A 架构—敏捷迭代计划

本计划把 IPD 主链 `Demand → Requirement → Market/Competitor → Concept → ProductPackage → Pilot → Lifecycle` 转成可验收的 Web-only AI 产品工厂。它是交付计划，不把设计目标或已有 DTO 冒充生产能力。

## 1. 依据、范围与判断规则

依据：

- `docs/02_business/BUSINESS_SCENARIO_CLOSURE_CATALOG.md`：24 个业务场景和节点契约；
- `docs/05_ai/AI_TECHNICAL_ARCHITECTURE_DEEP_DESIGN.md`：Model Gateway、Context、Safety、Run 和人工闸门；
- `docs/06_platform/APPLICATION_ARCHITECTURE.md`：应用边界、Command/Query/Projection；
- `docs/07_data/MASTER_AND_BUSINESS_DATA_DECOMPOSITION.md`：主数据、业务数据和事件链；
- `docs/11_delivery/AIFAMILY_MULTIMODAL_AGENT_TEAM_CHARTER.md`：Sprint 0～6 和团队职责；
- 当前代码、测试和生产 wiring：优先于文档中的目标态描述。

范围只包含 Web UI、Family API 和 AI Runtime；移动端不在本计划内。所有 AI 产物默认是 `DRAFT`、`PERSPECTIVE` 或 `RECOMMENDATION`，不得直接写入家庭事实、疗效、积分、排名或高影响决定。

状态含义：

| 状态 | 判定 |
|---|---|
| `DONE_WITH_EVIDENCE` | 代码、接口、成功/拒绝路径和自动化测试均存在 |
| `PARTIAL` | 有代码或测试，但缺生产接线、持久化、异常路径或治理证据 |
| `PLANNED` | 已定义验收标准，尚未形成可运行切片 |
| `BLOCKED` | 依赖缺失，继续开发会制造不可审计的假能力 |

## 2. 场景分层与任务分解

### P0：信任优先的体验闭环

| 场景 | 触发与用户 | 关键输入 | AI/系统任务 | 输出与人工点 | 验收指标 | 当前 |
|---|---|---|---|---|---|---|
| P0-S0 契约与准入 | PM/教研提交新需求或新模态 | DemandFrame、gold set、schema、供应商资料、purpose/consent | 结构化需求、schema 校验、安全拒绝、Gateway 路由、评测 | 版本化契约、provenance、准入结论；法务/DPIA/QA 复核 | schema 通过率≥99%；关键安全拒绝 100%；证据完整 100% | `PARTIAL` |
| P0-S1 表达→DRAFT | 家庭提交文字、图片或受控媒体引用 | scope、purpose、locale、consent、media refs、表达 | Context Snapshot、Safety、Model Gateway、多模态生成、成本/延迟控制 | DRAFT、限制、provenance、route；家庭确认/改写/拒绝/人工升级 | 无 consent/越权/未准入时 provider invocation=0；成功/拒绝/超时/重试可复现 | `DONE_WITH_EVIDENCE` |
| P0-S2 DRAFT→选择与恢复 | 家庭确认/改写/拒绝、反馈、删除、回放 | run、draft/version、幂等键、真实事件引用 | append-only Run、Human Gate、删除 scrub、只读 replay | Decision/Feedback/Human/Delete receipts、replay；人工顾问处理高风险 | 同 key 无重复副作用；跨 session replay 不重调模型；scope mismatch=403 | `DONE_WITH_EVIDENCE` |

### P1：IPD 产品工厂

| 场景 | 触发与用户 | 关键输入 | AI/系统任务 | 输出与人工点 | 验收指标 | 当前 |
|---|---|---|---|---|---|---|
| P1-S3 需求→市场洞察/竞品 | PM/教研进入需求评审 | 家庭原话、问题卡、官方/二手竞品证据、区域和时间 | 提出澄清问题；生成 `MarketInsight`、`CompetitorEvidence`、差距假设；逐条绑定 evidence refs | `RequirementHypothesis`、洞察和实验请求；产品/证据负责人复核 | 结论 100% 可追溯；UNKNOWN、过期、矛盾显式；不生成主观排名 | `PLANNED` |
| P1-S4 洞察→21 天产品包 | IPMT 通过 G0 后进入概念设计 | demand/insight/competitor refs、三区假设、组件/Skill 版本、SLA/预算 | 组合任务、节奏、难度、反馈和成就触发条件；校验组件兼容性 | `ProductPackage`/`ProductDefinition` 草案；IPMT 做概念 Gate | 每个候选有证据、预算、SLA、停止/回滚条件；不写事实 | `PLANNED` |
| P1-S5 试点→90 天升级 | 试点负责人启动小范围交付 | 冻结蓝图、受控家庭、行动事件、反馈、质量/成本/安全 telemetry | 解释试点结果；提出 `REVISE/SCALE/KILL`；组合 90 天计划 | Pilot report、Outcome evidence、Lifecycle recommendation；质量/合规 Gate | 完成/暂停/人工升级/退出可见；教育效果未测量时保持 `NOT_MEASURED` | `PLANNED` |

### P2：多模态资产和组件工厂

| 场景 | 触发与用户 | 关键输入 | AI/系统任务 | 输出与人工点 | 验收指标 | 当前 |
|---|---|---|---|---|---|---|
| P2-S6 媒体→家庭资产 | 家庭提交音频/视频或生成分享素材 | MediaAsset、Transcript、Evidence、visibility、retention | 异步转写/OCR/摘要；生成图片、PPT、视频或短剧候选 | 独立 provenance/deletion 链、私有分享、素材包；适龄审核 | 源删除级联到派生物；跨家庭泄露为 0；各模态 P95 可测 | `PARTIAL` |
| P2-S7 组件/Skill→PLM | 平台管理员发布、升级或退役组件 | 组件兼容矩阵、Skill 评测、成本、反馈、依赖 | 推荐复用/替代；执行版本和回滚检查 | Catalog、Release Gate、`SCALE/REVISE/KILL`；发布委员会审批 | 版本可追溯、回滚成功、未审组件不可上线 | `PLANNED` |

## 3. 4A 架构映射

4A 不是四套孤立系统，而是同一场景从价值、用例、事实到运行时的四个视图。

### 3.1 业务架构（Business Architecture）

价值流：

```text
Demand → Requirement → Market/Competitor Evidence → Concept
      → ProductPackage → Pilot → Lifecycle
      → Family Need → Action/Service Outcome → Feedback
```

角色与边界：家庭/家长、孩子（成长主体）、教研/PM、陪跑/Service Steward、教师/专家/机构、运营/合规、AI Runtime。业务对象分为 `Fact / Perspective / Recommendation / Action / Outcome`；AI 只能产生前三类中的非事实草案，只有授权的领域 Command 才能写入事实。

三区假设作为产品决策输入而非宣传口号：

- 同质区：通用问答、内容、打卡，验证可用性和成本；
- 优势区：21/90 天 AI+真人陪伴、可恢复体验、FGCN 服务协作，验证交付质量；
- 独占区候选：Family Context、Growth Graph、Intervention、Blueprint Library，必须以试点证据和可复用组件证明，当前不得标为生产优势。

### 3.2 应用架构（Application Architecture）

```text
Web UI
  → ExperienceApiClient / ProductIntelligence API
  → Family API（身份、scope、consent、幂等）
  → Application Workflow（Growth / Service / Commerce / Trust / Ops）
  → AI Runtime（Context → Safety → Prompt/Schema → Model Gateway）
  → ModelDraft + Provenance + Durable Run
  → Human Gate / Named Action / Outbox
  → Query Projection / Replay / Web 状态机
```

应用规则：

1. Web 只消费 Query DTO/Projection，不拼接供应商请求，也不写权威事实。
2. 领域不直接依赖模型供应商，统一经过 `Model Gateway`。
3. `ContextBroker` 按 tenant/region/family/subject/purpose/TTL/consent 过滤；跨家庭读取必须拒绝。
4. 外部副作用使用 Human Gate、Named Action、幂等键和 Outbox；失败进入重试/DLQ，不能静默成功。
5. 生产 resolver 未配置或不安全时返回明确 503；synthetic 只能用于显式 dev/test。

### 3.3 数据架构（Data Architecture）

固定数据链：

```text
Master/Policy Version
  → Command + scope/purpose/consent/idempotency
  → Business Aggregate（事实/交易状态）
  → Domain Event + Audit + Outbox（同一事务）
  → Projection / Analytics / Replay
```

核心对象：

- 主数据：需求类型、目的目录、Prompt/Schema、Model/Provider、组件/Skill、21/90 天模板、服务/商品/权益版本；
- 业务数据：Demand、RequirementHypothesis、MarketInsight、ProductPackage、Pilot、ExperienceRun、ContextSnapshot、ModelDraft、Decision、Feedback、HumanReview、MediaAsset、ActionRecord；
- 派生数据：Web 投影、评测报告、成本/延迟指标、运营队列、搜索/向量索引；派生数据可重建，不是事实源。

每条 L3/L4 数据必须具备 `tenant_id/family_id/subject_id/actor_id/purpose/consent_version/classification/provenance/retention`；删除必须覆盖媒体派生物、缓存、embedding、snapshot、trace 和评测样本，并返回可验证 proof。

当前数据风险：Context SQL 三张表的 migration/登记仍需冻结；Context、ModelDraft、Run 当前不是统一事务；因此生产状态只能是 `PARTIAL/BLOCKED`。

### 3.4 技术架构（Technology Architecture）

| 层 | 选型/组件 | 责任 | 当前证据 | 缺口 |
|---|---|---|---|---|
| Web | TypeScript、React、Vite、Playwright | 状态机、无障碍、DRAFT/人工/删除/回放体验 | Vitest、Playwright、build 已通过 | 真实生产 API E2E |
| API | FastAPI、Family API、显式 resolver | 身份、授权、同意、错误码、幂等 | synthetic/production fail-closed smoke | 真实身份/同意接线 |
| AI Runtime | Context、Safety、Prompt/Schema Registry、Model Gateway | provider-neutral 调用、schema/provenance、成本/延迟、拒答 | contracts、fake/sandbox、评测骨架 | 合规 provider 和 release gate |
| Durable | PostgreSQL、SQLAlchemy、Alembic、Run ledger、Outbox | run、attempt、snapshot、interaction、删除和重放 | SQL ledger/Context 代码及单测 | Context migration、统一 UoW、重启证据 |
| 协作 | Human Gate、Named Action、worker、DLQ | 人工确认和外部副作用 | 部分持久化/consumer | 常驻 worker、真实业务 handler、通知 |
| 治理 | ADR、Capability/Use Case Registry、DPIA、审计 | 版本、准入、回滚、留存、供应商合规 | 治理文档和注册表 WIP | migration head、法务和运营证据 |

## 4. 敏捷迭代计划

节奏：一周一个 Sprint；每个 Sprint 只承诺一个可演示、可回归的纵向切片。计划顺序固定为“先信任闭环，再产品工厂，最后多模态规模化”。

| Sprint | 目标与用户旅程 | 主要任务 | 退出门（DoD） | 状态 |
|---|---|---|---|---|
| S0 | 契约与可测基座：空输入/非法 scope 被拒绝 | 冻结 API/错误/事件/schema；gold set；Provider/Prompt/Schema registry；基础安全与审计 | 版本化契约；成功/拒绝/超时夹具；无 provider 误调用 | `PARTIAL` |
| S1 | 文字+图片：表达→DRAFT | Web 输入、Consent、Context snapshot、Gateway、provenance、limitations、人工确认入口 | Web 成功/拒绝/超时/重试；provider invocation=0 证据；无事实写入 | `DONE_WITH_EVIDENCE` |
| S2 | 选择与恢复：DRAFT→决策/反馈/人工/删除/回放 | Durable Run interaction、幂等、replay、delete scrub、反馈引用 | 同 key 幂等；409/403/404/410；回放不重调模型；删除 receipt | `DONE_WITH_EVIDENCE` |
| S3 | 真实 API sandbox：Web→Family API resolver | HTTP client 工厂、synthetic/production resolver、scope/consent 403/503、API smoke | TestClient 通过；生产未配置 fail-closed；Web 状态机不分叉 | `PARTIAL` |
| S4 | 运行韧性：刷新/断网/超时/重复点击可恢复 | preflight/reserve/finalize/release；session-per-call；trace/cost/latency；retry-after/conflict UI | provider invocation=1；不同 payload 409；刷新 replay 不重算；SLO 指标 | `PLANNED` |
| S5 | Durable 生产证据：跨进程/重启仍可回放 | Context migration；统一 transaction-aware UoW；PostgreSQL upgrade/downgrade；Run/Attempt/Safety/Human Gate/Outbox 持久化 | fresh DB；成功/失败/重试原子性；重启回放；删除级联 proof | `BLOCKED/PARTIAL` |
| S6 | IPD 产品工厂：Demand→Market/Competitor→21 天 ProductPackage | Product Intelligence API；证据引用；三区假设；组件/Skill Catalog；Product Gate；Pilot report | typed refs；每个结论可追溯；`REVISE/SCALE/KILL`；Web 只读投影 | `PLANNED` |
| S7 | 多模态规模：音频/视频→资产→90 天生命周期 | 异步 media pipeline、对象存储、转写/OCR、素材/PPT/视频候选、删除 proof、PLM 发布回滚 | 按模态 gold set；人工适龄审核；派生删除 SLA；真实 provider/legal Gate | `PLANNED` |

## 5. 任务卡模板与团队协作

每张任务卡必须填写：

```text
Task ID / Scenario ID / User / Trigger
Input contract / Master-data versions / Business aggregate
AI capability / Human gate / Output type（Fact/Perspective/Recommendation/Action/Outcome）
API + event + projection / Error and retry / Consent and retention
Success metric / Evidence links / Owner / Dependencies / Rollback
```

团队分工：

- AG-00：集成、优先级、依赖、发布门禁和 Sprint Review；
- AG-01：场景、IPD/三区、市场/竞品证据、验收指标和产品 Gate；
- AG-02：Model Gateway、Context、Safety、Run、Durable、供应商准入技术证据；
- AG-03：Web UI、API client、E2E、可访问性、体验状态机和真实 HTTP smoke；
- QA/合规/运营：独立复核，不以测试变绿替代数据、法务和人工证据。

跨 Agent 协作要求：每个 Sprint 开始前写依赖和不可做事项；中途只通过任务卡和契约交流；结束时联合 Review，记录代码、测试、证据、缺口和下一 Sprint 入口条件。

## 6. 当前发布判断与下一步

当前已形成可运行的 AI 体验 Experiment 骨架：Web 文本/图片 DRAFT、决策/反馈/人工/删除/回放、Run ledger、Context async port、P4 media/achievement contract 均有代码或测试证据；这不等于生产 ADMITTED。

下一次迭代只做 S5 的第一个可验收任务：

1. 冻结 migration head 和登记关系；
2. 新增 Context 三张表的正式 Alembic migration，并做 fresh DB upgrade/downgrade smoke；
3. 设计 transaction-aware ContextBroker，让 Context snapshot、ModelDraft、Run checkpoint 和 Outbox 在同一 UoW；
4. 补成功、供应商失败、重试、进程重启和删除级联测试；
5. 通过后再进入真实 provider/legal admission，不提前扩展音频、视频或自动化副作用。

发布前必须同时满足：4A 四层映射可追溯、Web/API/数据库环境等价、provider 合规准入、DPIA/留存/删除证据、gold set 评测、人工闸门、真实 PostgreSQL 重启回放和全链路可观测。任何一项缺失，状态保持 `PARTIAL` 或 `BLOCKED`。
