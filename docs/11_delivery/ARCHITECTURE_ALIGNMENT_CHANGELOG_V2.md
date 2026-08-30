---
id: ARCH-CHANGELOG-002
title: Family 新蓝图与现有五层架构变更日志 V2
type: architecture-change-log
status: draft
version: 0.1
owner: project-assistant
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: null
---

# Family 新蓝图与现有五层架构变更日志 V2

> 本日志记录新加入的总体设计与商业蓝图相对 V1/当前基线的增量、冲突和落地要求。
> 它是项目助理的变更控制输入，不是新的系统真相。所有新蓝图目前均为
> `status: draft`、`canonical: false`，且尚未全部登记到 `SYSTEM_MANIFEST`；在完成文档治理、ADR、
> Registry、契约测试和 owner 签字前，不得用本日志把目标态表述为已实现。

## 0. 评审范围、证据和状态语义

### 0.1 本轮对照文件

本轮只读对照了以下新蓝图与现有真相层：

- `docs/00_system/ARCHITECTURE_ALIGNMENT_V2.md`；
- `docs/00_system/ARCHITECTURE_BENCHMARK_REVIEW_V3.md`；
- `docs/00_system/CORE_BLUEPRINT_GLOBAL_SCALE_ALIGNMENT.md`；
- `docs/00_system/FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md`；
- `docs/01_strategy/AIFAMILY_EVIDENCE_LED_IPD_REDESIGN_V2.md`；
- `docs/01_strategy/AIFAMILY_IPD_PRODUCT_SYSTEM_REDESIGN_V1.md`；
- `docs/01_strategy/IPD_PLATFORM_IMPLEMENTATION_BLUEPRINT_V1.md`；
- `docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md`；
- `docs/02_business/FAMILY_GROWTH_PLATFORM_MASTER_DESIGN_V1.md`；
- `docs/02_business/BUSINESS_ARCHITECTURE.md`、`BUSINESS_SCENARIO_CLOSURE_CATALOG.md`、
  `BUSINESS_SCENARIOS_AND_PROCESSES.md`；
- `docs/03_product/FAMILY_UX_EXPERIENCE_ARCHITECTURE.md`；
- `docs/05_ai/AI_TECHNICAL_ARCHITECTURE_DEEP_DESIGN.md`、`AI_ARCHITECTURE.md`、
  `PRINCIPAL_AI_APPLICATION_ARCHITECTURE.md`、`GENERATIVE_SYSTEM_ARCHITECTURE.md`、
  `SERVICE_PRODUCT_DESIGN_AI_PLATFORM.md`、`SERVICE_PRODUCT_AI_PLATFORM_ARCHITECTURE_V1.md`；
- `docs/06_platform/APPLICATION_ARCHITECTURE.md`、`docs/06_platform/APPLICATION_IMPLEMENTATION_LEDGER.md`；
- `docs/07_data/DATA_ARCHITECTURE.md`、`BUSINESS_SCENARIO_DATA_ARCHITECTURE.md`、
  `DATA_OBJECT_TABLE_RELATIONSHIP_CATALOG.md`、`FAMILY_MEMORY_ARCHITECTURE.md`；
- `docs/00_system/SYSTEM_MANIFEST.md`、`CURRENT_SYSTEM_BASELINE.md`、`CURRENT_AI_MAP.md`；
- 当前代码、OpenAPI、Alembic、Registry 和定向测试输出。

### 0.2 状态语义

| 状态 | 证据要求 |
|---|---|
| `CURRENT_TRUTH` | 已在当前提交中、可定位到代码/Registry/测试，并非只存在于设计文档。 |
| `CONTRACTED` | 有稳定契约和定向测试，但缺少真实 HTTP、Postgres、生产组合或外部适配器。 |
| `WIP` | 工作树/未追踪提交或局部实现，尚未满足登记、回滚、审计和环境等价。 |
| `DESIGN` | 蓝图、接口草案或目标模型，未证明被代码消费。 |
| `GAP` | 目标需要但没有可复现实证，或存在明确越界/冲突。 |
| `BLOCKED` | P0 红线、未知迁移 head、owner/依赖未明确，不能进入候选发布。 |

### 0.3 当前新鲜基线

- `uv run pytest tests/architecture -q`：109 passed、1 skipped、1 failed；失败为 Ruff debt ratchet（基线 0，
  当前 `backend/domains/family/domain/entities.py:331` 有 1 个 E501）。
- `uv run ruff check .`：1 个 E501（同一位置）。
- `uv run pytest tests/intelligence/observability tests/intelligence/memory tests/intelligence/evaluation -q`：23 passed。
- `uv run pytest tests/apps/family_api/test_production_agent_wiring.py tests/intelligence/agent_runtime tests/intelligence/model_gateway tests/intelligence/evaluation/test_release_persistence.py -q`：162 passed；这些是契约/局部组合证据，不等于生产闭环。
- FGCN：无数据库 112 passed/1 skipped；设置 `AIFAMILY_TEST_DATABASE_URL` 后 113 passed、无 skip（含 e7cbb0b S-01 场景门）；仍有 replay、语言和 canonical fact 绑定缺口。
- Journey：含 Postgres 证据 44 passed；内存/HTTP/生产 identity、outbox、audit、真实删除仍未闭合。
- Web：主线已有 4b9a4b4，候选 `5cfccee` 仅两文件、`pnpm test` 26 passed、`pnpm typecheck` 0；Web lint 未配置，待 AG-04 复核。
- Alembic 当前 head=`0023_ai_growth_graph_projection`；`tests/database/test_alembic_baseline_applies.py` 新鲜结果为 8 passed、1 skipped、1 failed，失败是未知 head 0023 未满足登记/allow-list。0011-0023 多为未追踪 WIP，不能当作生产 schema。
- 当前发布判定：**NO-GO**。测试分支可以收纳有明确边界的 `CONTRACTED/PARTIAL` 切片，但不得将 synthetic adapter 或设计文档升格为生产能力。

## 1. 战略和商业模型变更

| 维度 | V1/当前基线 | 新蓝图增量 | 当前证据/状态 | owner 与下一切片 |
|---|---|---|---|---|
| 平台定位 | 家庭教育成长平台，以测评→计划→21/90 天为主链 | 从教育入口扩为 Family Need OS；教育只是首个模板，长期覆盖家庭关系、服务、产品和解决方案 | `FAMILY_GROWTH_PLATFORM_MASTER_DESIGN_V1`、`FAMILY_NEEDS_PLATFORM_TARGET_MODEL` 为 DESIGN；当前代码仍以成长/服务域为主 | PMA + B1/B2；先将 `NeedSignal→FamilyNeed→NeedProfile` 作为不写事实的契约，补 ADR/对象清单 |
| 客户和交易 | 主要是 B2C 家庭购买成长服务 | 明确 B2C（关系/现金流根）、B2B2C（学校/机构/企业福利渠道）、C2C（家庭互助/传播网络）三边分工，不是三个孤立产品 | 业务文档有设计；B2B2C/C2C 运行时和结算证据不足 | B3/B4/B5；先补机构项目、家庭授权、贡献结算和争议状态机，禁止私域导流 |
| 价值顺序 | 情绪价值和成长结果已提出 | E0 看见→E1 小胜→E2 持续成长→E3 明确服务需要→E4 经济选择；商业动作必须在 E3 后且家长确认 | E0-E4 与 ExperienceEvent 为 DESIGN/CONTRACTED；无真实漏斗审计 | X0 + B3；补事件、频控、撤回、家长确认和“不得自动续费/营销”测试 |
| 六引擎 | 拼多多、字节、海底捞、贝壳、教育、游戏作为对标描述 | 变成六个能力引擎：增长裂变、分发、服务体验、供需匹配、教育结果、游戏化成就；借机制，不复制副作用 | V3 映射为 DESIGN；当前无统一引擎指标/归因 | B3/B4/X0；建立可解释事件与质量指标，禁止刷屏、家庭总分、跨家庭排名 |
| 平台精神 | `We are 伐木累！We are family！` 品牌叙事 | 变成产品约束：先温暖和安全，再行动和经济价值；家庭是关系单元而不是流量对象 | ADR/蓝图有原则，尚无端到端体验闸门 | X0/AFE；把欢迎、陪伴、暂停、求助、复盘和投诉纳入 UI/API 验收 |
| 供给形态 | 内容、课程、专家服务 | Product、Service、Solution 三种供给；SolutionBlueprint 是可执行版本，不得由 AI 直接发布 | 产品设计工厂/目标模型为 DESIGN；`design_copilot` 仍占位 | B2/B3/B5；完成 ProductPackage/Blueprint/Compiler/Gate/Pilot/Release 链路 |
| 经济账 | 会员/商品/服务收入分散描述 | 四本账（成长、奖励/贡献、服务履约、现金/订单）分离；贡献不能伪装成成长分数或家庭分红 | loyalty/commerce WIP，未完成 durable ledger/结算/退款 | B3/B5；先完成唯一 writer、幂等、退款/争议/审计，再开放外部支付 |
| 规模目标 | 单区域、家庭级应用 | 千亿级家庭、全球 cell、冷热分层、分片/配额/区域故障切换 | 规模/多租户设计为 DESIGN；尚无容量压测、分区、灾备证据 | PLT/B5；先做 tenant/region/locale 基础字段与压测预算，不能用架构图宣称可扩展 |

## 2. 业务与流程架构变更

### 2.1 业务域重排

新蓝图把业务域稳定为 `B1-B5 + X0`，Principal 是横切编排面而非第六个业务域：

| 目标域 | 责任 | 与旧 V1 的关系 | 当前状态 |
|---|---|---|---|
| B1 Family Growth OS | 测评、证据解释、家庭确认、21/90 天计划、行动、结果和下一需要 | 继承家庭成长主链，新增“需要→下一需要” | assessment/journey 有局部实现；结果闭环和真实持久化 PARTIAL |
| B2 FGCN Service Network | 供给准入、ServiceCase、任务、资源匹配、交付、质量、贡献、争议 | 将专家/机构服务从附属功能升级为网络型交付域 | FGCN 测试较完整但 worker/HTTP/outbox/audit/真实资源仍 PARTIAL |
| B3 Growth & Commercial Flywheel | 内容/直播入口、体验漏斗、会员、产品、订单、权益、续购/推荐 | 将“增长”和“商业”统一为 E0-E4 受控飞轮 | commerce/membership/points WIP；不得用家庭分数刺激付费 |
| B4 Family Trust & Community | 家庭关系、社区、分享、互助、数据权利、安全、申诉 | 将 C2C 和关系安全正式纳入核心域 | UI/契约局部；可信分享、组队、申诉、内容治理缺生产证据 |
| B5 Platform Evolution & Operations | 产品工厂、知识、AI 治理、组织运营、指标、发布、事故和全球控制面 | 将平台运营从支撑文档提升为业务域 | O12-O14/S21/S24 多为 DESIGN/PARTIAL，生产运维闭环缺失 |
| X0 Experience & Trust | E0-E4、体验事件、频控、推荐、成就、跨域同意/安全 | 在原五层架构上增加体验控制面，防止“增长”绕过信任 | Experience contracts/curator 有 WIP，尚无真实推荐/策略/审计闭环 |
| Principal | 统一 Soul、Context、Router、Knowledge、Model Gateway、Human Gate、Named Action | 从“AI 助手”升级为家庭端与运营端统一入口 | runtime/planned/contracted；无生产 auth/consent/HTTP 组合 |

### 2.2 分级流程增量

流程层级仍保持 `L0 价值流 → L1 流程组 → L2 S/O 场景 → L3 子流程 → L4 横切节点 → L5 API/命令/事件/作业/人工任务`，新增三组覆盖：

1. **体验覆盖 P0/N01-N06**：`ExperienceEvent → CandidateSet → EmotionalResponse → ActionProposal → FeedbackSignal → GrowthProgress`。
   它负责情绪价值和游戏化安全，但不能直接创建成长事实或商业订单。
2. **家庭需要 N0-N8**：`NeedSignal → FamilyNeed → NeedProfile → SolutionBlueprintVersion → Resource/Assignment → Delivery → Quality → Outcome/Relationship → NextNeed`。
   教育 21/90/年度仅是首个可复用模板。
3. **Principal PR-N01-PR-N10**：意图、身份/同意、上下文快照、安全预检、能力路由、知识引用、结构化 Draft、输出复核、人/用户闸门、Named Action/反馈。

### 2.3 S01-S24/O01-O14 对齐矩阵

新蓝图不删除原 24 个家庭场景和 14 个运营场景，而是将它们挂到 B1-B5/X0/Principal；场景原子清单仍以 `BUSINESS_SCENARIO_CLOSURE_CATALOG.md` 为准。

| 场景组 | 场景编号 | 主要落点 | 新增流程/Principal 节点 | 当前判断 |
|---|---|---|---|---|
| 家庭进入/理解 | S01、S02、S03、S04 | B1 + X0 | E0/E1、评估证据、PR-N01~08；S01 需 family request + self-help evidence + GrowthIntent | FGCN S-01 已有 PG 113 pass；canonical fact/多语言/replay 仍 PARTIAL |
| 计划/行动/成长 | S05、S06、S07、S08、S09 | B1 + Principal | N04/N05、ActionProposal、Human confirmation、21/90 结果 | journey contract 40/4（含 PG 44）；无生产 HTTP/outbox/worker/identity |
| 服务网络 | S10、S11、S12、S13、S14 | B2 + Principal | need→matching→case/task→delivery/quality/contribution | FGCN contract/测试较多；一站式生产交付与真实质量结算缺失 |
| 商业与关系 | S15、S16、S17、S18 | B3 + X0 | E3/E4、产品/会员/订单/权益、邀请/续购显式确认 | commerce/membership/points WIP；不允许自动续费/营销或总分排名 |
| 社区/信任 | S19、S20 | B4 + X0 | 分享同意、家庭可见性、撤回/投诉/删除 | 多为局部 UI/契约，可信分享和治理运营未生产化 |
| 内容/活动/专家/机构 | S21、S22、S23、S24 | B5 + B2/B3/X0 | 内容→行动、直播/活动、专家目录、机构/学校项目 | S21/S24、部分运营能力 DESIGN_ONLY；需内容治理、机构授权与履约 |
| 家庭成功运营 | O01、O02、O03、O04 | B5 + B1 | onboarding、风险预警、家庭成功、复盘 | O01/O02 部分契约，自动化接管/SLA/补救不完整 |
| 内容/供给/产品运营 | O05、O06、O07、O08 | B5 + B2/B3 | 创作者/供给准入、产品工厂、直播/活动、服务质量 | IPD/产品工厂为 DESIGN；缺 API、PLM、审计和真实组织角色 |
| 交易/社区/平台治理 | O09、O10、O11、O12、O13、O14 | B3/B4/B5 + X0 | 订单/支付/权益、社区治理、指标、发布、事故、全球运营 | O12/O14、可信分享、事故闭环多为 PARTIAL/DESIGN；不能候选发布 |

每个 S/O 场景在实现前都必须列出 L4/L5 的输入、活动、输出、规则、拒绝/撤回/删除/重放/超时/人工接管，并绑定一个 canonical writer、数据对象、OpenAPI operationId、UI/运营入口和测试环境同构证据。仅有目录或流程图不算完成。

## 3. 角色和组织模型变更

| 角色/主体 | 新职责 | 约束 | 当前状态/缺口 |
|---|---|---|---|
| 孩子 | 成长参与者和被保护的数据主体 | 不作为广告/返佣对象；不得以分数或排名比较 | 家庭 UI 有基线，主体/年龄/可见性运行时不完整 |
| 家长/监护人 | 家庭授权人、计划确认者、付款/续购决定者 | 只能授权自己可见范围；重大行动和商业动作需确认 | Actor/Consent contracts 有局部证据，production resolver NO-GO |
| 家庭 | 长期关系与商业单元 | 无“家庭总分”；成员可见性和关系状态显式存储 | Family/journey WIP；跨租户/删除/审计未闭合 |
| 老师/专家/机构 | 受准入的服务供给和交付责任人 | 最小必要上下文；不能拥有家庭、绕过平台结算 | FGCN contracts/测试；资质、质量、争议和结算生产链缺失 |
| 学校/企业/渠道伙伴 | B2B2C 项目发起或购买方 | 只得聚合/目的限定输出，不得成为家庭数据所有者 | 机构模型为 DESIGN，缺合同、项目、授权、报告投影 |
| 家庭社区成员 | C2C 互助、共同活动、可信分享 | 共享需显式 consent；不能把分享当社会证明或排名 | community/share 多为 DESIGN/PARTIAL |
| 内容创作者/主播 | 内容、直播和活动供给 | 需版权/未成年人/商业标识/投诉处理 | 内容平台和直播中心为 DESIGN |
| Family 校长 Principal | 跨域人格、解释、编排、AI 协作中枢 | 不拥有 Family/Outcome/Order/ServiceCase；输出必须 Draft/Recommendation/ActionProposal | Soul/Context/Router planned/contracted；未接入真实身份和业务写入 |
| 产品/教研/运营/治理人员 | 需求、产品工厂、知识、质量、人工闸门、事故处置 | AI 草案须人审；每次发布可回滚、可追踪 | IPD/PLM/运营台为 DESIGN/PARTIAL |

## 4. 数据架构变更

### 4.1 数据分层从三类扩成四类并保持事实隔离

1. **平台主数据**：Tenant、Region、Locale、Actor、Family、Subject、Provider、Capability、Product、Policy、Consent。
2. **家庭/服务/商业业务数据**：Need、AssessmentEvidence、GrowthIntent、Plan、Action、Outcome、ServiceCase、Task、Delivery、Quality、Content、Order、Entitlement、Community、Contribution。
3. **AI 技术数据**：PrincipalSession、ContextSnapshot、SoulVersion、Prompt/Schema/Knowledge 引用、AgentRun、ToolCall、ModelAttempt、SafetyDecision、HumanTask、EvalReport、Memory、GrowthGraph、Telemetry。
4. **事件与投影**：ExperienceEvent、FeedbackSignal、CandidateSet、ActionProposal、AuditEvent、Outbox、指标/推荐/运营投影；所有投影都必须注明来源和可重建性。

AI 只写 Draft/Recommendation/Perspective/ActionProposal/HumanTask；家庭确认、服务履约、订单支付、结果确认等 Named Action 才能写业务事实。任何“AI 把评测质量当 Outcome”“把推荐点击当成长结果”“把贡献账当家庭总分”的实现均为架构违规。

### 4.2 新增对象关系

| 新对象族 | 关键关系 | 当前代码/证据 | 状态 |
|---|---|---|---|
| `NeedSignal/FamilyNeed/NeedProfile` | signal→need→profile→solution | 目标模型与 master design；无 canonical handler/table | DESIGN |
| `SolutionDraft/SolutionBlueprintVersion` | draft→human review→compiled version→ServiceCase/Product | design_copilot/compiler 占位；无 PLM 发布 | DESIGN/WIP |
| `ExperienceEvent/CandidateSet/EmotionalResponse/FeedbackSignal/GrowthProgress` | event→candidate→response→feedback→progress | experience contracts/curator 局部 | CONTRACTED/PARTIAL |
| `PrincipalSession/ContextSnapshot/KnowledgeRef/SoulVersion` | session→consent→snapshot→refs→response | principal/context 代码和迁移 WIP，未接生产 API | WIP/DESIGN |
| `MediaAsset/Transcript/Evidence` | asset→transcript→evidence→draft/provenance/deletion | multimodal contracts/adapter；真实 provider/delete 缺失 | CONTRACTED/PARTIAL |
| `ServiceCase/Task/Delivery/Quality/Contribution` | case→task→delivery→quality→contribution | FGCN 纵向测试/PG evidence；worker/audit/settlement 缺失 | PARTIAL |
| `MemoryReference/GrowthGraphEdge` | source fact→scoped memory/edge→projection | migrations 0022/0023 未被接受 head；SQL store WIP | WIP/BLOCKED |
| `EvalReport/ReleaseDecision` | benchmark→registry/version→gate→bounded projection | 0020/evaluation 双 gate 问题，registry lookup 缺失 | CONTRACTED/PARTIAL |

### 4.3 全局字段和治理要求

所有可持久化业务/AI/事件对象至少要有 `id`（全局不可变）、`tenant_id`、`region_id`、`family_id`（如适用）、
`subject_id`（如适用）、`purpose`、`consent_ref`、`data_class`、`locale`、创建/更新时间、`provenance_ref`、
删除状态/收据和审计关联。跨租户、撤回同意、删除后重放、区域迁移和过期读取必须负向测试。

### 4.4 Schema 漂移

当前 Alembic head 0023 未进入稳定 allow-list，0011-0023 的 ORM、ADR、Manifest、对象清单和 Fresh Postgres roundtrip 尚未全部可核验；未知 head 必须 fail，不能 skip。ADOM 在完成登记前只能保留 0008→159 的固定边界。任何以“工作树存在 migration 文件”宣称数据库完成均降级为 `WIP/BLOCKED`。

## 5. 应用架构变更

### 5.1 新边界

- `PrincipalApplication`：统一 PrincipalSession、ConsentResolver、ContextBroker、CapabilityRouter、KnowledgeRetriever、ResponseComposer、HumanGate、ActionBridge、FeedbackService；不得成为业务事实 writer。
- `ExperienceApplication (X0)`：实现 E0-E4、推荐/频控、体验事件和成就投影；推荐只能产候选/提案，不能偷偷优化停留时间。
- `FamilyNeedApplication`：捕获多模态需要、澄清、解决方案草案、资源编排、交付和关系回访；与 B1/B2/B3 通过命令/事件交接。
- `ServiceProductFactory`（B5）：Demand Studio、Market Insight、Product Studio、Component/Skill Library、Pilot/Gate Board、PLM Console；设计 AI 的草案与服务运行时分离。
- `Content/Live/Community`：内容、直播、活动、可信分享和社区治理是增长/关系入口，不得绕过家庭授权和结果闭环。
- `Global Control Plane + Regional Cell`：多租户控制面、区域数据面、策略/模型/知识版本；当前仅为设计。

### 5.2 34 UI 与多端

34 UI 仍是迁移基线，不是能力边界。新蓝图要求把每个 UI 的 `UI-xx` 迁移标识隐藏在开发元数据，用户界面使用语义标题、图标、状态、成就和下一步行动；支持文字、图片、音频、视频、实时/异步反馈，并保留空态、拒绝、撤回、失败、重试、删除和人工帮助。

移动端、Web、Android、iOS、鸿蒙、小程序必须共享 OpenAPI/错误码/作用域/幂等协议。当前 Web `5cfccee` 是候选分支（fake client 仅 Vite 开发，生产 fake fail-closed），但 Web lint 未配置，且后端真实 401/403/Consent/tenant wiring 未闭合；不能把 26 个 Web 测试当作四端 parity 完成。

## 6. AI 技术架构变更

### 6.1 从“模型调用”升级为 19 维生产系统

新 Deep Design 明确 D01-D19：战略/用例、Soul、Context/记忆、知识、Agent/Skill/Tool/Workflow、模型供应、Gateway、编排、
安全、Human Ops、评估、资产生命周期、数据删除、观测/审计/Provenance、可靠性/成本、部署灾备、环境/组织治理、
体验/推荐/游戏化。目标拓扑是：

`Entry → Principal Session → Actor/Tenant/Consent → Context → Safety → Soul → Router → Knowledge → Agent/Tool → Model Gateway → Schema/Safety/Provenance → Human/User Gate → Named Action → Outcome/Feedback/Eval`。

### 6.2 目标能力与当前证据

| AI 维度 | 目标增量 | 当前证据 | 状态 |
|---|---|---|---|
| Principal/Soul | 六维版本化人格（价值、语言、关系、行动、安全等），家庭端与运营端 profile 共 runtime | `backend/intelligence/principal` contracts/runtime；无正式路由和生产组合 | PLANNED/WIP |
| Context/Memory | M0 会话→M1 授权偏好→M2 只读家庭上下文→M3 关系/成长图，快照冻结且可删除 | context engine 内存原语、SQL memory WIP、0022 unknown head | WIP/BLOCKED |
| Knowledge | Source→Version→Chunk→Claim→Review→Publish→Retrieve→Citation，按 locale/tenant/purpose 隔离 | 9 份 compiled JSON 和 grounding；无统一 registry/retrieval/delete | PARTIAL |
| Model Gateway | provider-neutral、Attempt/Provenance/Schema/Safety、确定性降级 | gateway/attempt/provenance contracts 测试 | EXPERIMENT/CONTRACTED |
| Agent/Tool | AgentRun/Trace/Authorization lease/ToolCall outbox，唯一 Principal Router | agent_runtime 与 migration WIP；无业务消费者/生产 auth | PLANNED/WIP |
| Human Gate | 敏感建议、服务派单、内容发布、商业动作必须人工/家长确认 | contracts/worker/FGCN gate tests | CONTRACTED/PARTIAL |
| Evaluation/Release | 唯一 canonical `AiReleaseGate` + EvalReport registry，绑定 case/candidate/version/tenant/locale/provenance | 69f6508/96905db/a11f643/674/050 等连续 WIP，双 gate/lookup 缺口 | PARTIAL/BLOCKED |
| Observability/Deletion | Telemetry/trace/audit、durable queue、五类外部删除 adapter、receipt | telemetry/memory/deletion synthetic adapter；真实 PG/outbox/媒体/vector 删除无证据 | CONTRACTED/PARTIAL |
| Product Design AI | `service_product_architect` 只生成设计草案，compiler 12 checks，人工发布/回滚 | `design_copilot` 占位；IPD 文档完整但 Web/API/PLM 未完成 | DESIGN |
| Multimodal | provider-neutral image/audio/video/transcript/evidence；儿童保护和 provenance | multimodal contracts/benchmark tests | CONTRACTED/PARTIAL |

### 6.3 生成式系统历史矛盾的裁决

`GENERATIVE_SYSTEM_ARCHITECTURE.md` 已指出历史问题：主要矛盾没有一手来源，旧 FGCN 曾“零代码”，并且曾把模型输出误当业务能力。当前裁决是：

- 以业务域 canonical fact、事件、审计和 Named Action 为事实来源；模型只能提供有 provenance 的 Draft/Recommendation/Perspective；
- 确定性护栏、安全、同意、权限、状态机和删除规则不可交给模型生成；
- 记忆、媒体、向量、缓存和评测派生必须存在可验证删除收据；
- 任何文档宣称“Principal 已上线”“FGCN 已生产”“AI 已自动完成结果”而没有 HTTP+PG+identity/consent/audit/outbox 证据，均降级为 `DESIGN/WIP`。

## 7. 多租户、多语言、全球规模与环境等价

### 7.1 多租户/多语言

租户边界必须在 middleware、ActorContext、ConsentResolver、ContextBroker、Repository、事件和删除 worker 全链路保持；
`tenant_id` 不能由前端 body 信任，`family_id` 只是路由提示，必须由可信身份解析。多语言不是翻译文件，而是四个独立维度：用户 locale、内容 locale、模型 locale、政策/法律 locale；所有 Draft、引用、错误码、审计和评估都需记录 locale。

### 7.2 千亿级家庭的分阶段现实

目标设计包含全局 ID、region/cell、热/温/冷存储、事件分区、租户配额、向量隔离、故障切换和成本预算，但当前没有压测、分片、备份恢复和区域演练证据。先完成单家庭纵切片的租户/删除/审计/幂等，再做 cell 模板和容量模型；不得因为“未来千亿级”提前复制未验证的服务和 migration。

### 7.3 三环境功能同构

开发、测试、生产的路由集合、状态机、权限、错误码、审计、Human Gate、删除、重试、支付失败和多端契约必须相同；仅允许数据集和外部适配器不同。当前 `ENV-01` 仍 BLOCKED：`dev_wiring.py` 与 `production_experience_wiring.py` 存他人 WIP，unset 环境 acceptance 仍红，真实 auth/session/tenant/consent 尚未接线。APLT 的 cbc055e/736ae19/d2196bc 是合同测试，可保留为红灯信号，不能计为修复。

## 8. IPD、产品工厂和运营变更

新 IPD 设计把产品开发变成可审计流水线：`DemandFrame → AI research tasks → evidence cards → 21-day product candidates → compiler → G0-G6 gate → pilot → SCALE/REVISE/KILL → PLM release/rollback/retire`。对应六个 Web 工作台（需求、市场证据、产品、组件/Skill、试点闸门、PLM）。

当前只能确认产品智能领域和设计文档存在；Product Intelligence HTTP/catalog/gate/PLM、知识来源、竞品证据卡、组织角色、发布回滚均不完整。IPD 设计不得直接创建家庭 `Outcome`、订单或服务事实；必须经过人工批准的 `ProductPackage/BlueprintVersion` 和业务域交付。

运营场景必须与 S/O 同等完整：主动欢迎、SLA、风险补救、回访、供给准入、机构项目、质量争议、可信分享、发布/事故和全球 cell 运营都要有输入/活动/输出、责任人、队列、审计和恢复。现有只读运营证据 79 passed/1 skipped/1 warning，Onboarding 35 passed/11 skipped；S21/S24/O13 DESIGN_ONLY，S22/S23/O12/O14 PARTIAL，不能升生产。

## 9. 变更影响、冻结项和 ADR 前置

### 9.1 必须先治理再升 canonical

新蓝图文件当前均未被 `SYSTEM_MANIFEST` 登记或声明 canonical。升 canonical 前必须完成：

1. 文档冲突表和 `DOCUMENTATION_MAP` 更新，明确唯一真相和 supersedes 关系；
2. ADR（业务域、流程层级、Principal 边界、Need OS、IPD、全球 cell、环境等价、数据删除）；
3. `DOMAIN_REGISTRY`、`MIGRATION_MANIFEST`、AI/Capability/Use Case Registry 的 owner、路径、状态和版本；
4. 每个 S/O/N/PR 节点的 OpenAPI、对象/表/关系、唯一 writer、审计/outbox、成功与负向 contract tests；
5. 当前 architecture/Ruff、Fresh Postgres、HTTP/TestClient、四端 parity 和删除/恢复演练全绿。

### 9.2 暂停扩张/合并/优先补齐

- **冻结**：在唯一 `AiReleaseGate + EvalReport registry` 统一前，停止新增 evaluation/release-gate/report-persistence 代码；只允许合并 canonical gate、版本/租户/同意负向测试。
- **停止伪装**：不得把 InMemory deletion、deterministic provider、fixture catalog、one-shot worker、未登记 migration、设计文档或截图算生产。
- **合并**：将挂牌/预约/履约与 FGCN 案件/任务/交付/质量合并到一个 Service Application 边界；保留不同投影但只有一个 writer。
- **优先**：ENV-01 身份/同意/租户/默认值；S05→S07 成长结果；Context/Memory/Principal 单一闭环；Postgres/outbox/删除收据；Web/mobile API parity。
- **保留但延后自治**：社区、B2B2C、直播、商品、积分、支付和运营台不是删除项，但必须在测试环境实现完整状态机，生产等待真实适配器和合规闸门。

## 10. 纠偏后的交付切片

### 10.1 未来两周：测试环境同构最小纵切片

| 周期 | owner | 战场 | 输入→活动→输出 | 验收闸门 |
|---|---|---|---|---|
| W1-P0 | APLT/原 `dev_wiring` WIP owner | `main.py`、环境组合、Actor/Consent | unset/非法环境→fail-closed→真实 auth/session/tenant/consent→统一 401/403/CONSENT_REQUIRED | TestClient 三环境 negative/positive；OpenAPI/route parity；owner 明确前 BLOCKED |
| W1-P1 | ADOM/ARCH | migration 0011-0023、Manifest/ADR/ORM | 未知 head→阻断；登记→Fresh PG up/down/up→对象清单 | 0023 或后续 head 全部可追踪；未知 head 不能 skip；当前 0023 仍 BLOCKED |
| W1-P1 | AAIR | 唯一 AiReleaseGate/EvalReport | report_ref→registry/version/provenance/tenant/locale/consent→bounded projection | unknown/mismatch/revoked/deleted/replay/跨租户拒绝；不写 Outcome/Fact |
| W1-P1 | AFE/APLT | Web/mobile contract | actor token/session/locale/idempotency→API→UI semantic projection | Web 26 + typecheck；mobile 5 failures 清零；lint 配置；同错误码/撤回/删除 |
| W2-P1 | GROWTH/FGCN | S05→S07→S08/annual | confirmed intent→action→review→human-confirmed outcome→private story/recommendation→service case | Journey/FGCN PG+HTTP/outbox/audit/idempotency；中文/多语言、跨租户、撤回/删除；AI 不写事实 |
| W2-P1 | B2/B5/运营 owner（需 root 派发） | O01-O04 最小运营闭环 | onboarding→SLA→risk/remedy→follow-up→audit | queue/worker/timeout/DLQ/人工接管；79/1 证据仅作基线，不升生产 |

### 10.2 六周：候选测试环境完整业务链

完成 B1 成长、B2 FGCN、B3 会员/订单/权益、B4 社区/信任、B5 最小运营的真实 FastAPI+Postgres 状态机；
覆盖 S01-S24/O01-O14 每个节点的 schema、唯一 writer、审计/outbox、删除/重放/补偿、四端契约和 synthetic 外部适配器。
此阶段允许测试环境发布 `CANDIDATE`，但 production 仍需真实身份、支付、模型、媒体、vector、组织准入和灾备证据。

### 10.3 九十天：生产候选与全球扩展准备

1. Principal/Context/Memory/Knowledge/Soul/Agent 形成单一 runtime；真实模型 provider 通过 Registry、safety、成本、版本和 Human Gate 准入；
2. Product Factory/IPD/PLM 完成从 DemandFrame 到 Service/Product Blueprint 发布、回滚和交付反馈；
3. B2B2C 学校/机构项目、C2C 可信社区、直播/商品、支付/退款/争议与四本账全链路；
4. tenant/region/locale、冷热存储、分片、配额、删除、备份恢复、区域 failover 和容量压测；
5. Android/iOS/Harmony/小程序/Web/mobile OpenAPI parity、可访问性、多模态 UX 和游戏化安全闸门；
6. 所有 P0/P1 关闭、architecture/Ruff/Fresh PG/HTTP/删除/审计/事故演练全绿，才能进入 `PRODUCTION_CANDIDATE`。

## 11. 当前交付矩阵摘要

| 交付 | owner/thread | commit/ref | 证据 | 状态 | 下一动作 |
|---|---|---|---|---|---|
| FGCN durable gate + S-01 | FGCN owner | `e7cbb0b`（前含 41ad120） | 113 PG tests pass；无 PG 112/1 | PARTIAL | 修 replay 状态、locale 规则、canonical FamilyRequest/ActionRecord 绑定；补 HTTP/outbox/audit |
| Growth outcome loop | growth_action_loop | `b431eda` + `78cb9c1` + `dcc0802` | journey 40/4；含 PG 时 growth 44 | CONTRACTED/PARTIAL | ServiceCase/Delivery canonical port、真实 runtime/PG/delete/audit；不升生产 |
| B2C service vertical slice | P1 service | `e99d499` remote branch | SQLite/HTTP/ORM 59/26 skip；HTTP 10/1 skip；PG 4；ORM 2 | CANDIDATE TEST/PARTIAL | provenance、Audit flush、worker/DLQ、FGCN bridge、identity/consent/Commerce gate |
| Web authenticated context | APLT/AG-03 | `5cfccee` remote candidate | Web 26 pass；typecheck 0 | CANDIDATE TEST/PARTIAL | AG-04 review；配置 lint；backend 401/403/tenant/consent parity |
| AI eval persistence/gates | AAIR | 941feae/a11f643/69f6508/96905db/674b764/050361f | evaluation/experience tests green but synthetic;双 gate/registry 缺口 | PARTIAL/BLOCKED | 冻结扩张，合并唯一 AiReleaseGate + EvalReport registry + bounded projection |
| AI memory/telemetry/growth graph | AAIR/ADOM | migrations 0021-0023（WIP） | contracts/局部 tests；Alembic unknown 0023 | WIP/BLOCKED | ADR/Manifest/ORM/object list/Fresh PG；unknown head fail |
| Product factory/IPD | B5/产品运营（owner 待 root 派发） | design docs only | six workbenches/PLM/compiler design | DESIGN_ONLY | 注册能力、API、证据卡、G0-G6、pilot/release/rollback |
| Operations S/O | 运营 Chat | read-only 79/1/1；Onboarding 35/11 skip | welcome/SLA/remedy/follow-up/incident missing | DESIGN/PARTIAL | 派 owner 做 O01-O14 最小 queue/worker/audit/delete |
| Environment/auth gate | APLT + 原 dev_wiring owner | `d2196bc` acceptance | 401/403/consent tests；unset acceptance intentional red | BLOCKED | 原 WIP owner 收口 fail-closed + trusted composition；三环境同构后才关闭 |

## 12. 发布判定

### 测试环境

允许进入测试分支的条件：切片文件边界明确、contract tests 可重复、synthetic 数据与外部 adapter 可替换、
失败/撤回/删除/重放路径存在、跨租户和同意负向测试存在，并明确标为 `CONTRACTED/PARTIAL`。测试环境不得为了省事删除生产需要的路由、状态机、权限或 UI 功能。

### 生产候选

当前 **NO-GO**。至少以下阻断仍成立：

1. ENV-01：unset/非法环境、真实 auth/session/tenant/consent 和 production composition 未闭合；
2. Alembic unknown head 0023，迁移/ORM/Manifest/ADR/对象清单不一致；
3. Principal/Context/Memory/Knowledge/Agent 仍无真实生产调用链；
4. deletion worker 仍是 synthetic adapter，缺 durable queue/store、外部媒体/vector/cache receipts；
5. eval/release 双 gate 和 report registry 未统一；
6. B2B2C/C2C、内容/直播/社区、运营事故/申诉/机构交付未完成；
7. 多语言、多租户、四端 parity、容量/灾备和 Web lint 尚无全量证据；
8. architecture/Ruff 有 1 个真实失败，不能以缓存或 skip 关闭。

本日志没有修改代码、Registry 或其他 Agent 文件；它只把新蓝图的变更、证据边界和下一步责任落盘。下一次架构复审必须重新运行上述测试，不得复用缓存输出。
