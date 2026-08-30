---
id: DELIVERY-ARCH-ALIGNMENT-REVIEW-001
title: AiFamily 五层架构与商业蓝图对标评审
type: delivery-review
status: current
version: 1.0
owner: project-assistant
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: null
---

# AiFamily 五层架构与商业蓝图对标评审

> 评审结论：**NO-GO（可继续敏捷开发，不可宣称生产就绪）**。
> 本文是 PMA-1 在 2026-08-30 的反向审查结果。目标态文档只说明应当建成什么，
> 代码、OpenAPI、迁移和可重现实测才说明已经建成什么。测试环境必须与生产保持同一
> 路由、状态机、权限、错误码、审计、人工闸门和失败路径；测试只替换合成数据与外部
> 适配器，不能因为是 test/dev 而删能力。

**分支状态（2026-08-30）**：远端已推送的版本仍为测试候选，发布判定为 **NO-GO**；
`origin/codex/cleanup-superseded` 当前可见为 `dd7051b`（已包含 `e7cbb0b` FGCN S-01
绑定和 PMA 文档）；本地总控与远端同步。工作树仍包含
其他 Agent 的 WIP，不能将这些提交视为远端已发布。
最近提交链含 0cd53fb、9b10d2d、6b4a8e9、cbc055e、736ae19、d2196bc、02a80c4、
6a88625、6150169、573a86d、a91ad3a、0ca62d2、f8ee917。提交可追踪不等于生产接线完成；生产与 dev/test 仍须功能同构，
只允许数据和外部适配器不同。

## 0. 审查范围、证据和状态语义

对照材料：

- 商业蓝图两张图及 `docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md`；
- `docs/02_business/BUSINESS_ARCHITECTURE.md`、`BUSINESS_SCENARIO_CLOSURE_CATALOG.md`；
- `docs/07_data/DATA_ARCHITECTURE.md`、`MASTER_AND_BUSINESS_DATA_DECOMPOSITION.md`、
  `DATA_OBJECT_TABLE_RELATIONSHIP_CATALOG.md`、`FAMILY_MEMORY_ARCHITECTURE.md`；
- `docs/06_platform/APPLICATION_ARCHITECTURE.md`、`APPLICATION_IMPLEMENTATION_LEDGER.md`；
- `docs/05_ai/AI_TECHNICAL_ARCHITECTURE_DEEP_DESIGN.md`、`AI_ARCHITECTURE.md`、
  `GENERATIVE_SYSTEM_ARCHITECTURE.md`、`docs/06_platform/PRINCIPAL_AI_APPLICATION_ARCHITECTURE.md`；
- `frontend/mobile/app/ui/UI-01.tsx`…`UI-34.tsx`、mobile tests、`frontend/web`；
- `docs/11_delivery/AGILE_REBUILD_PLAN_V1.md`、`PROJECT_MANAGEMENT_CHARTER.md`；
- 当前 Python/FastAPI、OpenAPI、Alembic、Registry 和以下新鲜命令输出。

状态采用：`IMPLEMENTED_TESTED`（可调用纵切片，有事实写入、拒绝/重放和环境证据）、
`PARTIAL`（有代码但缺闭环/生产接线）、`CONTRACTED`（契约/适配器测试，不是生产能力）、
`DESIGN_ONLY`（只有设计）、`BLOCKED`（存在发布阻断）。`PARTIAL` 不得写成完成。

新鲜证据摘要：

| 检查 | 实测结果 | 解释 |
|---|---|---|
| `uv run pytest tests/architecture -q` | **109 passed, 1 skipped, 1 failed** | 当前唯一失败为 Ruff debt ratchet（Ruff 当前 1 E501）；PIPL auto-promotion 闸门已通过，但总闸门仍红，不能把 WIP 清单当成已完成 |
| `uv run ruff check . --output-format concise` | **1 error** | `backend/domains/family/domain/entities.py:E501`；另有临时目录拒绝访问告警，质量闸门仍未清零 |
| `uv run alembic heads` | `0017_ai_model_attempts (head)` | 0011-0017 revision 均有未跟踪/WIP 变更；未知/未审批 head 必须阻断，不能沿用旧 allow-list |
| Postgres `tests/database/test_alembic_baseline_applies.py`（`AIFAMILY_TEST_DATABASE_URL`） | **8 passed, 1 failed, 1 skipped** | 失败为未知 0017 head；0010 已登记跳过，说明“不跳过未知 head”有效，不能报全绿 |
| `uv run pytest tests/intelligence/experience -q` | **220 passed, 1 warning** | P4 media/share/achievement runtime contract 已通过 synthetic/in-memory 测试；仍不能把契约测试当 production wiring |
| `uv run pytest tests/intelligence/evaluation tests/intelligence/experience -q` | **220 passed, 1 warning** | P4 contract 测试绿，但两套 gate 尚有职责重叠、registry/生产接线缺失，不能视为唯一准入真相 |
| `uv run pytest tests/domains/journey -q`（无 DB） | **40 passed, 4 skipped** | Growth S05→S08→Annual/Renewal 契约通过；Postgres URL 下 **44 passed**，仍为内存应用闭环，无 HTTP/审计/outbox |
| `uv run pytest tests/intelligence/context_engine -q` | **25 passed** | durable deletion/legacy worker/async+SQL context contracts；仍是 synthetic/SQLite adapter |
| `cd frontend/mobile; pnpm test -- --run` | **249 passed, 1 skipped, 5 failed** | UI-02 旧契约 2；registry/service 契约 3；全量不能报绿 |
| `cd frontend/web; pnpm test -- --run; pnpm typecheck` | **22 passed；typecheck 0** | 68fc0ce/d403998 已注入 Authorization、X-Session-Id、request locale；仍缺真实 backend 401/403/跨租户 smoke |
| `tests/apps/family_api/test_experience_wiring.py` + `tests/intelligence/experience -q` | **220 passed, 1 warning** | composition hook、P4 media contracts 和 SQL context integration 测试通过；没有真实 SQL/session/identity/consent 组合根，生产默认仍 503 |
| FastAPI OpenAPI | unset/test **61** paths；production **57** paths（最近核验） | unset 默认 `development`，仍暴露 dev auth；production 隐藏 `/auth/account-session` 但 experience resolver 仍 503 |

## 1. 五层架构对标矩阵

| 层 | 商业/设计目标 | 当前实现与证据 | 偏移、严重度、判定 |
|---|---|---|---|
| 业务架构 | 家庭教育为入口，拓展家庭需求服务/产品/方案；家庭拥有数据、AI 不替人；六引擎形成情绪→成长→经济价值闭环；S01-S24/O01-O14 有唯一边界 | 业务文档已完整定义 Fact/Perspective/Recommendation/Action/Outcome、FGCN、三层价值网络和 24+14 场景；代码形成 S04 测评、N0-N1 Need 首片及 FGCN Named Action→Assignment 片段 | **业务设计完整，运行兑现不足，P1**。S07/S08/S09、FGCN 常驻交付/质量、支付/社区/运营大部分未实现；不能以 34 UI 或路由存在代替闭环 |
| 流程架构 | L0 VS-01…VS-05 → L1 P01…P06 → L2 S/O → L3 子流程 → L4 节点 → L5 API/Command/Event/Job/Human Task，异常可退出、可重放、可接管 | 目录已列出 L0-L5；S04 节点有 Handler/SQL/fake/幂等；S05/S06 只有部分；S07 action worker、S14 dispute、S20 deletion、O05/O09/O12/O14 等仍无完整执行器 | **流程“画出来”多于“跑起来”，P1**。每个 L4 必须绑定输入/活动/输出/规则/异常/owner/API/数据/测试，缺一只能 PARTIAL |
| 数据架构 | 主数据与业务数据分离；租户/locale/主体/同意/删除/审计贯穿；Postgres 事实、事件和投影可重放；Family Context/Growth Graph 让平台长期懂家庭 | Alembic baseline、Assessment/Growth/Journey/FGCN 部分表及 outbox 存在；数据目录覆盖目标对象和关系；Family Context、三类记忆、embedding、删除证明仍无完整 durable production runtime；当前 head 已漂移至 0017，0011-0017 为未跟踪/WIP revision | **P0/P1**：家庭记忆与跨会话图谱为独占区空白；0009+ migration 虽有局部 manifest 行但未形成全链可信审批；`product_intelligence` ORM/迁移漂移及公共 schema 目标态未落地；未知 0017 直接阻断 roundtrip |
| 应用架构 | A0-A6 分层，唯一应用服务和写入者；Family API、Web、Android/iOS/Harmony/小程序同一契约；dev/test/prod 功能同构 | FastAPI 已挂 assessment、journey、service、commerce、membership、family-need、FGCN、experience；OpenAPI 生产 57 paths；Web client 22 tests；mobile 34 UI 可渲染 | **P0/P1**：生产身份/同意/租户链未完整接线；experience 默认 resolver 503；Web 仅注入请求上下文、无真实 backend 401/403；mobile 五个失败；service journey duplicate operationId；多端 parity 尚无一套 CI 闸门 |
| AI 技术架构 | 单一法咪莉校长控制面：Context/Memory/Principal/Soul/Knowledge/Model Gateway/Prompt-Schema/Eval/Human Gate/Observability/Deletion；AI 只产 Draft/Recommendation/Proposal，Named Action 才写事实 | `backend/intelligence` 有 principal/context_engine/knowledge/human_gate/experience/model_gateway/agent_runtime 契约；18 个 context tests、durable human gate/agent runtime 测试；但 gateway/provider、Soul/Knowledge registry、Context durable projection、Eval/trace/worker/真实多模态适配未形成生产链 | **P1，生产阻断**：契约和 in-memory adapter 不等于运行能力；AAIR-6 仍 `CONTRACTED/adapter-only`；未接入唯一 Principal 家庭请求→人工闸门→Named Action 的完整链 |

## 2. 商业蓝图六引擎和精神对齐

| 蓝图引擎 | 期望商业作用 | 当前承载 | 评审结论/缺口 |
|---|---|---|---|
| 拼多多式增长 | 低门槛测评、挑战/裂变、让用户带来用户 | UI-01/15/16、部分邀请/商城 fixture | 体验入口存在；真实邀请、单层激励、反伪造进度和归因账本未闭环，不能生成虚假拼团数字 |
| 字节式算法分发 | 用户画像、行为反馈、内容/服务精准匹配 | deterministic assessment、部分 recommendations、feature/experiment 契约 | 跨会话 Family Context/Growth Graph 尚空白；无生产检索、事件指标和可解释推荐链 |
| 海底捞式服务 | 情绪价值优先、即时响应、真人兜底、复购 | service booking/records、FGCN Human Gate 契约、UI-05/19-24 | 预约子链和控制面是 PARTIAL；客服队列、SLA、质量恢复、常驻 worker、真实身份/资源未完成 |
| 贝壳式 ACN/FGCN | 一客一案、一案一管家、一任务一责任、验收贡献 | FGCN schema、a031007 durable Named Action→TaskAssignment、one-shot worker、Postgres chain 测试 | P0 assignment writer 已形成；仍缺常驻 queue/lease/通知/DLQ、生产 session/consent、返工/质量/贡献结算；应与挂牌预约模型做 ADR 融合，不得两套写入者并存 |
| 教育长期陪伴 | 21 天→90 天→年度服务，结果沉淀和复购 | Journey plan/phase 部分，UI-04/05/08 | 今日任务、结项、Outcome、年度回读和会员续购未闭环；不能将静态文案当长期陪伴 |
| 游戏化体验 | 情绪价值、节奏、成就、反馈，非家庭排名 | mobile achievement/view-model 契约、部分 UI 美化 | 有成就轨道和多模态接口，但 UI-03 score/peer_reference、Lv.3/伪造进度等历史债仍需清除；应使用证据绑定成就，不做总分/排名 |

“We are 伐木累！We are family！”已在战略和 UX 原则中表达，当前尚未形成可度量的体验闭环：
先让家长/孩子被理解（情绪价值）→愿意尝试小行动（成长价值）→真人/网络兜底（信任）→
透明会员/服务/产品复购（经济价值）。目前只有测评→解释→计划前段能运行，其余箭头仍是
设计或 fixture；平台扩展到家庭需求服务/产品/方案的方向没有偏移，但不能提前宣称生态已成立。

## 3. L0-L5 流程与节点闭环核验

### 3.1 价值流、流程组和场景覆盖

| 层级 | 完整目录 | 当前证据 | 状态 |
|---|---|---|---|
| L0 | VS-01 家庭成长交付；VS-02 服务协作；VS-03 商业关系；VS-04 关系与信任；VS-05 平台经营与能力进化 | 业务架构、数据架构有定义；仅 VS-01 前段和 VS-02 预约/FGCN 片段可调用 | PARTIAL |
| L1 | P01 触达身份入营；P02 测评假设计划行动；P03 陪跑服务 FGCN；P04 商品会员资产；P05 社区权利安全；P06 运营 AI 指标治理 | 应用架构 A1-A6 映射存在；P04/P05/P06 多数目标态 | PARTIAL |
| L2 | S01-S24 业务场景、O01-O14 平台运营场景 | `BUSINESS_SCENARIO_CLOSURE_CATALOG.md` 有 38 个闭环目录；APPLICATION ledger 给出状态 | S04/N0-N1 IMPLEMENTED_TESTED；S05/S06/S10/S12/S15/S16/S23 PARTIAL/BLOCKED；其余 DESIGN_ONLY 或 GATE |
| L3 | P01.1-.3；P02.1-.4；P03.1-.4；P04.1-.3；P05.1-.2；P06.1-.3 | 子流程目录、状态/异常规则在业务/数据架构存在；常驻 Job、运营台、投影重建缺失 | PARTIAL |
| L4/L5 | 每个 S/O 节点须有输入→活动→输出→业务规则→异常→数据对象→API/Command/Event/Job/Human Task→UI/运营入口 | S04-N01..N05 具备较完整证据；S05-N04、S07-N01..N05、S14、S20、O09/O12 等关键节点没有可调用闭环 | NO-GO |

### 3.2 节点级反向抽样（输入/活动/输出/规则/异常/映射）

| 节点 | 输入 → 活动 → 输出 | 业务规则/异常 | 数据/API/AI-人工/UI/运营映射 | 现状 |
|---|---|---|---|---|
| S03-N02/N03 测评目的与同意 | subject/purpose → 选择、ConsentGate → PurposeSelection/ConsentRecord | 目的分离、未成年人监护、撤回立即生效；无同意拒绝 | consent/family；assessment start API；UI-07；O01/O11 | PARTIAL（统一生产持久化缺失） |
| S04-N01..N05 测评冻结 | token/版本/回答 → 建会话、保存、提交、冻结证据 → Session/Response/Evidence | 版本冻结、幂等、提交后不可变；缺题/撤回拒绝 | assessment tables、outbox/audit；`/families/{id}/ui/02/assessment`；UI-02/result | IMPLEMENTED_TESTED（结果独立审计仍缺） |
| S05-N01..N04 假设入营 | Evidence/Context → 解释、假设、家庭决定 → Perspective/Hypothesis/GrowthIntent | AI 不写事实；高风险人工；拒绝可重放 | growth_intents；UI-03；Principal/Model Gateway/Human Gate 尚未全接 | PARTIAL，N04 NOT_IMPLEMENTED |
| S06-N01..N05 90 天计划 | Intent/策略 → 预览、创建、确认、阶段复盘 → JourneyPlan/PhaseDecision | 计划版本、暂停/调整；到期补偿和投影不可反写 | journey tables/routes；UI-04/05；O02 | PARTIAL |
| S07-N01..N05 21 天行动 | active phase → 生成今日任务、提醒、开始/完成/跳过、回读 → ActionTask/ActionRecord/Review | 幂等、提醒失败重试、Outcome 不由完成率自动生成 | 目标 `/growth/actions/today` 等 API；UI-09/10/11/12/29；O04/O05 | NOT_IMPLEMENTED，商业链断点 |
| S09-N01..N05 校长助手 | message/目的/同意 → Context/Route/Knowledge/Generate/Safety → Draft/Proposal/HumanTask | 统一错误码、模型不可用降级、Human Gate；禁止直写 | Principal API 目标存在，experience routes 可见但 production resolver 503；UI-03/05/09 | DESIGN/PARTIAL |
| S10-S14/S23 FGCN | Need/Blueprint/资源 → 建案、拆任务、授权、交付、验收、贡献 → ServiceCase/Contribution | 一客一案/一任务一责、验收后贡献；超时/争议人工 | FGCN routes/one-shot worker；UI-19-24/31/34；O05-O07 | PARTIAL（常驻队列、生产 identity、质量/资金缺） |
| S15-S18 商业关系 | Catalog/intent/payment → 订单、支付、权益、积分、邀请 → Ledger/Entitlement/Invite | 支付验签、退款反向失效、余额由账本聚合；不伪造倒计时/进度 | commerce/membership 部分 API；UI-06/13-18/30/32；O08/O09 | PARTIAL/BLOCKED |
| S19-S20 信任权利 | post/request → 审核、申诉、导出、删除、保全 → Moderation/Rights/DeletionProof | 默认私有、未成年人保护、法定留存；派生媒体/向量/缓存级联 | 目标表/契约，AAIR durable worker 为 adapter-only；UI-25-29/33；O10/O11 | DESIGN/GATE |
| S21-S24/O12-O14 平台经营 | events/claims/changes → 队列、指标、评估、发布、事故复盘 → OperatingDecision/Release/Postmortem | 指标不可冒充疗效；模型/知识审批回滚；环境同构 | 运营端目标，Registry/CI 有漂移；运营 UI/worker 未形成 | DESIGN/PARTIAL |

## 4. 数据架构完整性

### 4.1 主数据、业务数据与 AI 数据

- 主数据（Tenant、Family、Person、Relationship、Consent、Locale、Content/Service/Product/
  Prompt/Knowledge/Model/Policy version）必须版本化、不可原地覆盖；业务数据（Session、
  Need、Intent、Plan、Action、Case、Order、Payment、Outcome、Review、Ledger）只能由其
  所属应用写入。当前目录已分解对象/表/关系，但正式 Order/Payment/Refund、Community、Rights、
  Ops、Membership period/points、AI runtime durable 表仍为 `TARGET_REQUIRED` 或 WIP。
- AI 数据（ContextSnapshot、ModelAttempt/Draft、HumanTask/Decision、Prompt/Knowledge refs、
  EvalCase、Trace/Cost/Provenance）必须与家庭事实物理/权限隔离。现有 Principal/Human Gate/
  Experience 以值对象、SQLite/in-memory adapter 为主，尚未形成 Postgres + outbox + replay 的
  production wiring；AI 不能直接 import 业务 ORM。
- Family Context、ChildMemory、GuardianMemory、RelationshipMemory 的对象定义正确地要求
  candidate→家庭确认→可检索记忆；但当前 `FamilyMemoryDialogueRuntime` 无调用方、无
  embedding/pgvector、无跨会话 durable retrieval。它是独占区 **0→1 的 P0**，不是“已有能力优化”。

### 4.2 租户、locale、删除、审计与迁移

| 维度 | 设计要求 | 当前证据/偏移 |
|---|---|---|
| 租户/家庭绑定 | Account→Person→Membership→TenantFamilyBinding→Session；每层 Router/Context/Knowledge/Cache/Eval 再校验 | `trusted_context` 和 scope tests 有契约；生产 identity/consent/family binding 组合根仍未贯通，P0 |
| locale/多语言 | canonical concept + content/model/policy locale；无可靠翻译时人工降级，不能静默机翻敏感建议 | `backend/platform/localization` 和 locale 契约存在；未见完整 API/内容/模型/检索/审计四端闭环，P1 |
| 删除/留存 | 原始事实、媒体转写/OCR、记忆、embedding、缓存、评估副本和供应商回执级联；Proof/WORM audit；legal hold 有期限 | `durable_deletion.py` 6 tests 通过，但 `InMemoryDurableDeletionStore.production_ready=False`；没有 Postgres/outbox、五类真实 adapter、重启和跨进程 lease，P0/P1 |
| 审计/事件 | 每次命令同事务 Audit + Outbox；可重放、补偿、死信 | Assessment/Journey/部分 FGCN 有局部；Worker、运营和 AI 全链未统一，P1 |
| schema/migration | baseline 0001→0008 的 159 固定边界；0009+ 只能在 ADR、Manifest、ORM、对象清单、Fresh Postgres 后 allow-list | 当前 head=0017；0011-0017 migration 与对应 ADR/ORM/对象清单未形成可审计提交链，测试 8 passed/1 failed/1 skipped（失败为未知 0017 head）；manifest 工作树行不能替代提交证据，P1 阻断 |

## 5. 应用、API 与四端 parity

1. FastAPI 生产 OpenAPI 仍有 57 paths，开发/测试有 61 paths；`dev_auth` 在 `AIFAMILY_ENV`
   未设置时因 `current_environment()` 默认 `development` 而暴露（生产明确设置时 404）。默认值
   是 P0：启动配置必须 fail-closed，且 real auth/session route 要与 dev/test 具备同一功能集合。
2. Experience 多模态路由在生产 OpenAPI 可见，但默认 resolver 返回 503；dev/test 依赖进程内
   synthetic runtime。不能把“生产不泄露 dev auth”误写成“生产功能同构已完成”。
3. Web `HttpExperienceApiClient` 的 22 个测试和 typecheck 全绿；68fc0ce/d403998 已注入
   `Authorization`、`X-Session-Id` 和 request locale（scope.locale 优先）。但仍无真实 backend
   TestClient 的 401/403、tenant/consent 绑定，必须在 client、API 和 production composition 统一。
4. Mobile 34 UI 是基线而不是业务事实。全量 249/1/5 说明：UI-02 测试仍断言旧文案/函数，
   registry 仍断言 35 屏，service offering/slot 契约已改为内部 id 但测试未同步。UI-19 等
   已移除 UI-xx 低质编号并有成就/图标组件，这是体验进步，但不能用视觉通过掩盖 API/状态失败。
5. 当前 OpenAPI 生成有 duplicate operation id（service journey）；移动、Web、未来 Android/
   iOS/Harmony/小程序应从同一 OpenAPI/contract package 生成或校验，所有端共享 scope/error/
   idempotency/provenance 字段。必须加入 dev/test/prod 同一接口的 CI parity，而不是人工点验。

## 6. AI 技术架构成熟度

| 维度 | 目标设计 | 当前判断 |
|---|---|---|
| Principal/Soul | 一个法咪莉校长控制面，家庭/产品设计/运营 profile 共享 Soul、策略和网关 | 控制面文档和 agent_runtime 基础存在；没有完整家庭请求运行链，Soul compiler/版本回滚未上线，PARTIAL |
| Context/Memory | 最小作用域快照、三类关系记忆、可重放/过期/删除 | Context engine 18 tests；主要是内存原语，跨会话和 durable projection 为空，P0 |
| Knowledge | reviewed claim、许可、版本、适用范围，家庭私有上下文与公共知识隔离 | 静态 compiled JSON/assessment grounding；registry/retrieval/license/deletion 未形成生产，P1 |
| Model Gateway | provider-neutral、schema/provenance/cost/timeout，领域不直连供应商 | Gateway/experience 协议测试有；无准入生产 provider/统一 application port，P1 |
| Prompt/Schema | 版本冻结、编译、回滚、输出强制 Draft | prompt_registry WIP 未登记、Ruff 失败；`ModelDraft` 表迁移 0009 未追踪，P1 |
| Evaluation | contract/safety/grounding/IP/usefulness/workflow、golden/影子/漂移 | 文档和少量多模态评估存在；没有 release gate、长期样本和运营闭环，P1 |
| Human Gate/Named Action | 高风险 100% 人工；决定后由 domain Named Action 写 Fact | durable human gate/FGCN bridge 契约 通过；无常驻 queue/lease/通知和生产 identity，CONTRACTED |
| Observability/Provenance | trace、token/cost/latency、输入来源、版本、决策、删除引用 | 部分 provenance/value object；无统一 durable trace、指标、告警、事故操作台，P1 |
| Deletion/多模态 | TEXT/MEDIA/VECTOR/CACHE/DERIVED 五类适配器、收据、重启恢复 | synthetic in-memory worker 6/6；真实外部媒体/vector/供应商回执不存在，RELEASE BLOCKED |
| 多语言/多租户/规模 | 作用域缓存、分片、区域和 locale 策略；千亿家庭下容量/成本/灾备 | 设计文档定义字段和边界；没有容量压测、分区/归档、跨区灾备和租户配额，P2（但上线前需安全最小集） |

### 6.1 b74 async ledger bridge 复核（2026-08-30）

`b74b29f feat: bridge async run ledger into experience api` 把 Experience API 的同步/异步
调用统一到 `dispatch_ledger_call`，并允许 `AsyncExperienceRunLedgerPort` 实现
`preflight_create/finalize_create/release_create`。当前工作树的后续改动已让具有 durable
lifecycle 的 adapter 直接委托 preflight/finalize，避免原先仅靠进程内 reservation map；
定向 `test_async_ledger_bridge.py` + `test_sql_run_ledger.py` **14 passed**，说明调用不使用
`asyncio.run` 阻塞事件循环，输入 scope、幂等键、DRAFT 状态和删除/重放契约在 SQLite 测试中成立。

但这不是生产接线完成：

- `rg AsyncExperienceRunLedgerBridge|SqlAlchemyExperienceRunLedger backend frontend` 显示
  生产组合根尚未注入 SQL `AsyncSession`/bridge；`dev_wiring.py` 仍使用进程内
  `InMemoryExperienceRunLedger`，production resolver 默认 503；
- bridge 的 durable path 只有在组合根把 reservation、model draft、audit/outbox 放到同一
  事务边界时才成立；当前没有 HTTP TestClient 的真实 production-like transaction/rollback
  证据，也没有跨进程 concurrent idempotency/lease、进程重启 replay 的 API 验收；
- SQL ledger 删除目前只 scrub run checkpoint/response，外部媒体、向量、缓存、评估副本和
  供应商收据仍由 AAIR-6 未实现的 durable deletion worker 负责，不能把 `DELETE` interaction
  当成完整权利履行。

因此该切片状态为 **CONTRACTED/PARTIAL，P1 发布阻断**。验收前置：production composition
注入唯一 SQL ledger + bridge；dev/test 只替换数据/外部 adapter；补 401/403、跨租户、并发
幂等、重启 replay、事务回滚、删除级联收据和 OpenAPI parity 测试。不能因为 14 个 adapter
测试通过就把 Experience 能力标为 `INTEGRATED` 或 `PRODUCTION`。

## 7. 当前开发计划与 WIP 偏移

1. `AGILE_REBUILD_PLAN_V1` 将 DB-01/AAIR-6/AFE-4/PMA-1 标为阶段切片；本轮把 AAIR-6
   统计刷新为 context-engine **25 passed**，mobile 为 **249/1/5**，不沿用旧的 13/247。
2. DB-01 0001 baseline 与 0004-0008 159 边界可复测；当前 `alembic heads` 已继续漂移到
   0017。0011-0017 文件及其 ADR/Manifest/ORM 仍未形成可审计提交/审批链，不能把
   `agent_runtime: MIGRATED_TESTED` manifest 行或任何工作树 WIP 视为发布事实。
3. AFE-4 的 UI-19/20/21/22/23/24/31 图标化与成就组件方向符合 UX；但全量测试红灯，
   旧 UI-02 断言和 service contract 没有收敛，状态必须 PARTIAL。
4. PMA-1 的历史文档已记录 dev_auth、Ruff、Registry、mobile/Web gaps；本评审新增了应用/
   AI/商业/流程/数据的交叉断点，不得只修一个测试而忽略链路。
5. WIP `backend/intelligence/product_management`、`prompt_registry`、多项 ADR/迁移、
frontend/mobile 新目录大量未登记/未提交；任何“完成”必须同时更新 owner、Manifest、ADR、
测试和可回滚证据，不能靠目录出现推断完成。

6. GROWTH agent 的 `ccd3d87` 新增 `backend/domains/journey/application/outcome_loop.py`，
   以独占测试覆盖 ActionFact→ChallengeReview→Outcome(PENDING/CONFIRMED)→Story→
   Recommendation(DRAFT)→ServiceCase→AnnualReview/Renewal。当前属于 CONTRACTED/PARTIAL，
   不能改变 APPLICATION ledger 对 S07/S08 的 NOT_IMPLEMENTED/PARTIAL 判定。

### 7.1 a031007 FGCN Human Gate→durable worker 复核

`a031007 feat: connect human gate actions to durable FGCN worker` 的范围是窄而正确的：
`execute_task_assignment_named_action` 成为唯一将 accepted `NamedActionRequest` 转为
`TaskAssignment` 的应用命令；它重新校验 tenant/family/subject/purpose/consent/correlation
scope、真人 actor、任务/案件终态和单责任人约束，以 source request id 幂等，并把 Assignment、
Task/Case 状态和 AuditRecorder 放进同一个 repository commit。`consume_accepted_human_task`
只消费 `DECIDED + action_request`，不直连模型或支付。

实测证据：`uv run pytest tests/domains/service/fgcn/test_persistence.py
tests/domains/service/fgcn/test_workflow_worker.py -q` 在真实
`AIFAMILY_TEST_DATABASE_URL` 下 **23 passed**（无 DB 时为 22 passed/1 skipped）；
`uv run pytest tests/database/test_fgcn_migration_chain.py -q` 为 **2 passed**，且 0004/0005/0006
revision 文件已 tracked。这证明了 P0 Named Action 写入边界和 SQLite/Postgres repository
契约，不证明 FGCN 服务交付闭环已生产化。

仍有四个架构断点：

1. worker 是 one-shot handler，没有常驻 queue、lease/claim、通知、超时调度或 DLQ；进程崩溃
   的安全重试依赖调用方再次提交，不能当作 workflow worker；
2. `family_api` production composition 仍未绑定真实 identity/consent/session/reviewer role，
   FGCN routes 默认 fail-closed，dev/test 仅 synthetic adapter；三环境功能集合尚未同构；
3. 0004 已进入链，但 0011-0017 未追踪的 migration head 仍使总迁移发布 NO-GO；不能以 FGCN
   23 项测试掩盖全局 schema 漂移；
4. 资源准入、交付/返工、质量/争议、贡献与资金结算尚未由该命令实现，不能把 TaskAssignment
   事实等同于完整 ACN/FGCN 商业引擎。

结论：a031007 **GO（可进入测试分支的 P0 纵切片）/NO-GO（生产发布）**。下一步必须由
workflow owner 补持久队列与 lease/retry/DLQ、生产身份/同意接线、生产-like HTTP+Postgres
并发/重启/回滚/撤权测试，并保持 AI draft→human gate→Named Action→domain fact 单向边界。

### 7.2 ccd3d87→b431eda/78cb9c1 Growth 结果闭环复核

Growth agent 的 `ccd3d87` 原始切片先将 S07 ActionFact→ChallengeReview→Outcome→Story→
Recommendation→ServiceCase→Annual/Renewal 全部放在 journey 进程内；复核发现本地创建
`ServiceCase` 会与 `service/fgcn` 形成第二写入者，且 delivery/story consent 只做字符串检查。
`b431eda`/`78cb9c1` 已返工为 `ServiceCaseCommand`→canonical service port、
`ServiceDeliveryReceipt`、人类 actor 校验和每次 recommendation/annual/story/delivery 的
实时 `ConsentGate`；`dcc0802` 仅补充边界文档。`snapshot`/`deletion_refs` 现覆盖 action、
review、outcome、story/media、recommendation、case command、delivery、annual、renewal，
并保留无分数/无排名限制。

新鲜实测：

- `uv run pytest tests/domains/journey -q`（无数据库）**40 passed, 4 skipped**；
  设置 `AIFAMILY_TEST_DATABASE_URL=postgresql+asyncpg://aifamily:aifamily@localhost:55442/aifamily_test`
  后 **44 passed**；Ruff 对两份独占文件 clean；
- 负向用例覆盖 AI actor delivery、撤回 consent、跨租户、幂等冲突、共享故事授权和删除
  引用。该结果说明契约和测试数据库接缝可进入测试分支，不能证明生产闭环。

仍有五个发布断点：

1. `GrowthOutcomeLoop.production_ready=False`，状态全是进程内 dict；没有 Journey HTTP、
   Postgres ORM/repository、同事务 Audit+Outbox、跨进程幂等/重启 replay 或 durable worker；
2. `ServiceCaseCommand` 尚无实际 service port/sink 调用，delivery receipt 也不是 FGCN
   交付/验收/返工/质量/贡献/结算事实；不得把 REQUESTED/DELIVERED 值对象当成案件履约；
3. actor 只做字符串黑名单（`ai:`/`SYSTEM`），真实 Account→Membership→Family、reviewer
   角色、主体授权和服务资格仍未接线；
4. consent loader 是注入式 adapter，未与生产 ConsentRecord 撤回、过期、目的分离和审计
   事务绑定；删除 refs 仍只供未来 worker，外部媒体/向量/缓存回执不在本切片内；
5. S07 今日任务/提醒/跳过/超时/DLQ/补偿、S08 结果审核和 S09 复购 API 尚未接入
   Application ledger/UI/Web，故业务架构 S07/S08 不能从 NOT_IMPLEMENTED/PARTIAL 升级。

结论：**GO（测试分支契约切片）/CONTRACTED-PARTIAL（生产前置）/NO-GO（生产）**。下一步
由 GROWTH/ADOM/API owner 定义 canonical service port、Journey ORM/API 和 outbox，补
Postgres 并发、ConsentRecord 撤回/过期、审计、删除级联和 UI-03/04/05/09/10/11 vertical
e2e；未完成前禁止新增第二个 journey writer 或以 completion percentage 生成 outcome。

### 7.3 128fb57/4924506 Experience SQL ledger 复核

`128fb57` 增加 HTTP 生命周期的 `CommittedExperienceRunLedger`，`4924506` 增加
`SessionPerCallExperienceRunLedger`，使 preflight reservation 在 provider 边界前提交，
每次 mutation 由独立 `AsyncSession` commit/rollback，读取在新 session replay；两者都委托
`SqlAlchemyExperienceRunLedger`，不直连模型或业务事实。新鲜 `uv run pytest
tests/intelligence/experience -q` **220 passed、1 warning**（P4 media/share/achievement runtime contract 已通过 synthetic/in-memory 契约；仍非 production wiring），证明 session
关闭、preflight/release、重放、DELETE scrub 和幂等在测试适配器中可行。

但这仍不是 production composition：

- `backend/apps/family_api/main.py`/`experience_wiring.py` 没有注入
  `SessionPerCallExperienceRunLedger` 或真实 `AsyncSession` factory；`dev_wiring.py` 仍绑定
  `InMemoryExperienceRunLedger`，生产 resolver 无配置时返回 503；
- HTTP TestClient 尚无真实 FastAPI→Postgres→ledger→Audit/Outbox 的 commit/rollback、
  401/403/跨租户、并发 idempotency、进程重启 replay 证据；
- SQL 交互表 0010 的 deletion 只清理 run checkpoint/response，外部媒体、向量、缓存、
  评估副本和供应商回执仍依赖 AAIR durable worker（当前 adapter-only）；
- 新增 0011-0017 agent/human-task/authorization/tool/achievement/onboarding/model-attempt migration 尚未形成
  完整 ADR、Manifest、ORM/对象表、tracked head 和 Fresh Postgres roundtrip，数据库总闸门仍 NO-GO。

结论：**CONTRACTED/PARTIAL，P1 发布阻断**。只能把该切片作为测试环境同构的 SQL adapter
候选；提升至 INTEGRATED 前必须由 ARCH/APLT/AAIR 提交 production composition、身份/同意
上下文、同事务 audit/outbox、HTTP parity、Postgres restart/concurrency 以及五类删除
adapter receipts。

### 7.4 3f56089 Experience composition hook 复核

`3f56089 feat: expose explicit experience runtime composition root` 让 `create_app` 可以接收
一个显式、非 synthetic 的 `MultimodalDraftRuntimeResolver`，并在 dependency override 中覆盖
默认 resolver；对 `SyntheticRuntimeResolver` 有类型拒绝，避免把测试适配器偷偷当生产组件。
这解决了“如何注入”的应用架构缺口，但没有解决“注入什么”：当前主入口未创建
`SessionPerCallExperienceRunLedger`、SQL `AsyncSession` factory、生产 Account→Tenant→Family
绑定、ConsentGate、Audit/Outbox 或 provider policy。`AIFAMILY_ENV=production` 下若未传 resolver，
experience route 仍 fail-closed 503；开发/测试仍由 `dev_wiring.py` 绑定进程内 synthetic runtime。

新鲜 `uv run pytest tests/apps/family_api/test_experience_wiring.py tests/intelligence/experience -q`
为 **220 passed、1 warning**，仅证明 hook 和契约测试，不证明 HTTP→Postgres→AI runtime 的真实组合根、
三环境同构或跨进程生命周期。结论：**CONTRACTED/PARTIAL，P1**。下一步 owner 必须提交
production-like resolver（真实 ledger/session/identity/consent，外部 provider 可替换为合成适配器）
并补 TestClient 401/403、tenant/family scope、幂等冲突、rollback、restart replay、audit/outbox
和 deletion proof；在此以前不能把 `create_app(resolver=...)` 的可注入性写成生产就绪。

### 7.5 ec109a7/0494aa8 多模态评测复核

`ec109a7` 新增 `MultimodalEvalRunner`、`GoldCase`、`MultimodalAdapterResult` 和
`ProviderEvaluationSummary`；`0494aa8` 为汇总报告增加稳定的 `benchmark:multimodal:*` 引用。
实现保持 provider-neutral、离线和 media-free：GoldCase 只允许 `synthetic`/`anonymous`
fixture，拒绝 bytes/data URL/原始媒体字段；每个适配器结果校验 provider/model/version、
schema、安全标签、拒答准确率、provenance、延迟和成本，输出只保留聚合指标。新鲜
`uv run pytest tests/intelligence/experience -q` **220 passed、1 warning**；P4 media/share/achievement contracts 已在 synthetic runtime 通过，但尚无 durable storage/production wiring，不能因此提升等级。

`69f6508` 又在 `multimodal_eval.py` 增加 `EvaluationReleaseGate`（ELIGIBLE/BLOCKED 和
自定义阈值）。但仓库已有 `backend/intelligence/evaluation/release_gate.py:AiReleaseGate`
（ADMITTED/BLOCKED、ProviderRegistry、environment/data_class 和质量阈值）；两者目前都可被
调用，构成两个准入真相。`uv run pytest tests/intelligence/evaluation tests/intelligence/experience -q`
当前 **220 passed、1 warning**；P4 contract 已绿但仍未证明唯一 gate、registry lookup 或生产 provider admission，不得升级为生产。

这与 AI 技术架构的“评测先于准入、AI 输出必须有 provenance”一致，但边界必须保持清晰：

- `report_ref` 是聚合摘要哈希，不是可重放的 EvalCase/Trace，也不是教育疗效或家庭成长
  结果；`quality_score` 只能表示基准样本质量，不能写入 Outcome/Fact 或激励账本；
- 评测对象没有 tenant/family scope、ConsentRecord、DeletionProof、Audit/Outbox 或持久化
  approval/revoke 状态，因为设计上不应承载家庭 PII；但当前没有独立 registry/gate 阻止
  调用方将匿名报告混入生产 provider admission；
- 没有 Postgres 评测账本、gold 版本发布审批、长期漂移/影子样本、成本预算告警或模型回滚，
  也没有与 Principal→Human Gate→Named Action 的事实边界相连。

结论：**CONTRACTED（离线评测原语）/PARTIAL（AI 发布门）/NO-GO（生产准入）**。AAIR
必须合并为唯一 canonical `AiReleaseGate`：统一 ProviderRegistry、environment/data_class、
case/candidate/version/provenance 和阈值，增加“仅一个 gate 实现”的 architecture test；补
EvalCase/Report registry（版本、owner、数据分类、许可、删除策略）、人工/QA 审批和
provider admission gate。所有生产候选必须以 report_ref+provenance+审计关联入库，未经审批
不得进入 Model Gateway，且不得以“评测通过”替代真实家庭结果。

### 7.6 941feae/ a11f643 评测引用与耐久投影复核

`941feae` 为 FEEDBACK 增加 `benchmark_report_ref`/`real_event_refs` 的命名空间和长度
校验；`a11f643` 增加 `record_evaluation`，把不含媒体的 benchmark 汇总投影追加到 run
interaction ledger，并强制 `education_outcome_status=NOT_MEASURED`；`96905db` 又增加
`persist_evaluation_projection` coordinator，把 gate 决策和 report ref 交给 Run ledger。
这是正确的 AI→业务事实隔离，但仍只是 projection coordinator。新鲜
`uv run pytest tests/intelligence/evaluation tests/intelligence/experience -q` **220 passed、1 warning**，
目标文件 Ruff clean。

但当前校验仍是**形状校验而非真实性校验**：`benchmark_report_ref` 只需以
`benchmark:` 开头，未查 EvalReport registry 是否存在、是否已审批、case version/model/
candidate/provenance 是否与该 run 一致，也没有 tenant/locale/consent 绑定。`record_evaluation`
只暴露 Python ledger/bridge，未挂 FastAPI endpoint；SQL adapter 持久化的仍是 interaction
projection，不是独立 EvalReport registry，也没有统一 Audit/Outbox、删除证明、跨进程并发/
restart 和生产 composition。当前 acceptance 测试验证 unknown prefix 和“不得 MEASURED”，
不能证明“真实 report 只能被授权 run 引用”。96905db 没有新增 migration、registry lookup
或 provider/tenant/consent binding，因此不能把 coordinator 当第二个评测真相或生产准入；
反而进一步要求停止扩张并合并唯一 `AiReleaseGate`。

结论：**CONTRACTED/PARTIAL，P1 发布阻断**。补齐 EvalReport registry/lookup、版本与
candidate/draft/provenance/tenant/locale/consent 关联，unknown/mismatch/revoked/deleted/
跨租户/replay 均拒绝；记录 audit/outbox correlation，保持 projection media-free，且任何
评测指标不得写入教育 Outcome/Fact。未补齐前只能作为测试环境同构的内部适配器。

### 7.7 96905db 评测投影协调器复核

`96905db feat: coordinate evaluation report persistence` 只新增
`persist_evaluation_projection()` 与对应内存 ledger 测试：它计算/校验
`EvaluationReleaseDecision`，再调用现有 `record_evaluation` 写入 Run interaction。该函数
支持 sync/async ledger，确保 report ref、case version、gate 状态和
`education_outcome_status=NOT_MEASURED` 进入幂等/租户 scoped 的 Run projection；新鲜
evaluation+experience 测试为 **220 passed、1 warning**；P4 runtime contract 已通过但仍是 in-memory/contract 证据，不能以“相关 Ruff clean”替代生产接线缺口。

反向核验发现它不是独立的持久化评测报告库，也没有新增 migration、EvalReport registry
lookup、ProviderRegistry/environment/data_class 检查、tenant/locale/consent/provenance
绑定、Audit/Outbox、删除回执或 FastAPI endpoint。SQL adapter 的事务/幂等只覆盖 interaction
projection；内存 ledger 仍是测试替身。更重要的是，`multimodal_eval.py:EvaluationReleaseGate`
与 `backend/intelligence/evaluation/release_gate.py:AiReleaseGate` 仍可独立调用，96905db
继续叠加 coordinator 会扩大“双 gate/双真相”风险。

结论：**CONTRACTED/PARTIAL（测试分支可用）/NO-GO（生产）**。该 commit 不应单独推送为
“评测持久化完成”；在 P1 `EVAL-REF-01` 关闭前冻结新增 evaluation/release-gate 代码，
只允许补 canonical gate、registry lookup、负向测试和迁移/审计证据。验收必须证明单一
`AiReleaseGate`、report registry 版本/主体/租户绑定、幂等/跨租户/撤回/删除/重放和生产
FastAPI→Postgres→Audit/Outbox 组合根；评测指标仍不得写入教育 Outcome/Fact。

### 7.8 5703266 总体设计工作稿对标

`docs/02_business/FAMILY_GROWTH_PLATFORM_MASTER_DESIGN_V1.md`（5703266，1577 行）明确标注
`status: draft`、`canonical: false`，并把商业蓝图、S01-S24/O01-O14、五层架构、
Principal/Context/Memory、FGCN、测试/生产同构、数据权利和运营指标合并为一份讨论基线。
文稿对当前实现的关键约束是正确的：教育只是入口，家庭是服务单元；先情绪价值再成长/经济
价值；AI 只能写 draft/proposal，业务事实由领域 Command 唯一写入；服务交付、验收、争议、
贡献和结算必须可追踪；测试环境只替换数据/外部 adapter，功能/错误/状态机必须与生产相同。

本轮代码没有证据表明这些目标已整体落地：S07 行动、FGCN 质量/结算、会员/支付、社区/运营、
家庭记忆、生产 AI composition 仍为 PARTIAL/DESIGN_ONLY；当前 109/1/1 architecture、Ruff
1 error、mobile 249/1/5、Alembic head=0017 未通过总闸门。该工作稿不应被 Registry 或应用 ledger
引用为“已实现”依据；每个目标必须回链到 L4/L5 命令、数据对象/表、API、AI/人工闸门、UI/运营
入口及 Fresh 测试证据。

结论：**设计对齐，无事实升级**。后续如要把该工作稿设为 canonical，必须先冻结对象/流程版本，
由 ARCH+DATA+AAIR+API 完成 traceability review 和 ADR，避免再产生与现有业务/数据/应用设计
竞争的第二套蓝图。

`3107d30` 新增 `docs/02_business/FAMILY_MEMBERSHIP_CONTRIBUTION_ECONOMY_BLUEPRINT.md`，
明确孩子是价值中心、家庭是服务单元、贡献/权益/现金四本账分离，会员与 FGCN 需可验收结算，
并重复确认“测试环境功能同构、数据/外部适配器可模拟”“不做家庭总分/排名”“AI 不写事实”等
红线。内容与商业蓝图及 FGCN/ledger 方向一致，但文件标注 `draft/canonical:false`，当前没有
对应会员状态机、Contribution/Entitlement/Settlement 表、API、审计/退款/争议实现；应登记为
**DESIGN_ONLY**，不能作为已实现商业能力，也不能驱动继续堆叠未登记 migration。

### 7.9 674b764/050361f/b3fffbb 多模态准入与 production composition 复核

- `674b764` 仅收紧 `EvaluationGatePolicy` 类型和 `EvaluationReleaseDecision` 引用校验，并补负向单测；这是安全的 fail-closed 修正，状态 **GO（测试切片）**，不改变生产边界。
- `050361f` 为 SQL ledger 的 evaluation projection 补 SQLite 持久化测试；它证明 interaction projection 可在现有 session 中重放，但未提供真实 Postgres、EvalReport registry、Audit/Outbox、删除证明或 HTTP 入口，状态 **CONTRACTED/PARTIAL**。
- `b3fffbb` 新增 `ProductionExperienceRuntimeResolver`，为请求构造 SQL `SessionPerCallExperienceRunLedger`、`SqlAlchemyModelDraftRegistry` 和 Model Gateway，并拒绝 synthetic scope。可是 `MultimodalDraftRuntimeResolver.resolve(family_id)` 只接收 URL family，`experience/api.py` 路由没有 `Authorization`/ActorContext 依赖；其新增 TestClient 以无 token 仍可生成 200 响应。`scope_resolver` 由调用方注入且可静态返回 scope，不能证明真实身份、租户家庭绑定或实时 ConsentGate。resolver 也没有接入 `main.py` 默认 production composition，Audit/Outbox、外部删除和 report registry 仍缺。

结论：674 为 **GO（契约）**；050 为 **CONTRACTED/PARTIAL**；b3 为 **P0 返工、测试分支可保留、生产 NO-GO**。必须由明确 owner 在 `api.py` 与
`production_experience_wiring.py` 接入可信 ActorContext/ConsentGate，补无 token、跨租户和撤回同意的 401/403 TestClient，接入 `main.py` production
composition，并证明 Postgres transaction、Audit/Outbox、deletion receipts 和 provider/report registry。三提交作者均为本地 `Claude Code`，当前无可识别在线 owner，已登记 unowned blocker；在唯一 canonical gate 与 registry 关闭前冻结新增 evaluation/gate/persistence 代码。

### 7.10 02a80c4 AsyncContextBrokerPort 复核

`02a80c4 feat: add async context broker port` 新增 `AsyncContextBrokerPort` 协议和
`AsyncContextBrokerAdapter`，以 `asyncio.to_thread` 将同步 `ContextBroker` 暴露给异步应用，
并补充 ADR-0065 及 3 项异步端口测试。新鲜 `uv run pytest tests/intelligence/context_engine/test_async_port.py tests/intelligence/context_engine -q`
为 **25 passed**，说明 snapshot/read/delete 的 scope、过期、租户和线程切换契约成立。

反向核验确认 adapter 的 `durability_mode` 仍为 `IN_MEMORY`，没有 SQL/事务/outbox、跨进程
并发、重启恢复、ConsentRecord 撤回版本、外部媒体/向量删除回执，也未接入
`ProductionExperienceRuntimeResolver` 或 `main.py` 组合根。它改善了异步接口边界，但不是
durable Context/Memory 运行能力，状态为 **CONTRACTED/PARTIAL，P1**；禁止以 25 项绿测升为
`INTEGRATED`/`PRODUCTION`。验收需提供 Postgres Context store、同事务审计/删除 outbox、
tenant/locale/consent 负向与重放/重启测试，并证明 dev/test/prod 只替换数据和外部 adapter。

### 7.11 6a88625/6150169 SQL Context Broker 复核

`6a88625 feat: add durable sql context broker` 新增 `AsyncSqlContextBroker` 及 observation、
snapshot、snapshot-observation 三个 SQLAlchemy 表；`6150169` 修复跨会话 replay 时
correlation/causation 与 locale scope 的保留。当前定向 context-engine 测试为 **25 passed**，
Ruff 对新增 adapter 与测试全绿；这证明 fresh session 的 scope/expiry/delete/幂等契约在
SQLite synthetic store 中可运行。

`9b10d2d` 新增 disposable Postgres 临时 schema probe；`AIFAMILY_TEST_DATABASE_URL=...`
下 `uv run pytest tests/intelligence/context_engine/test_sql_store_postgres.py -q` 当前
**1 passed**。该测试仍以 `metadata.create_all` 建表并在同一 engine 内完成 append/snapshot/read/delete，
没有执行 Alembic、真实应用重启或生产组合根，故只能作为 **CONTRACTED/PARTIAL** 的数据库探针，
不能将 Context 标为 durable production。

反向检查发现这些表只由测试 fixture `metadata.create_all` 创建，尚无 Alembic revision、
MIGRATION_MANIFEST、数据对象清单或生产 resolver/main 组合根；`AsyncSqlContextBroker` 的
session-per-operation 也未与业务事实、ConsentRecord、Audit/Outbox 组成同一事务，删除仅清理
本地三表，没有媒体/向量/缓存/派生 projection 的 durable receipts。`read()` 重建 scope
目前将 `consent_granted` 固定为 `True`，没有验证持久化快照撤回/过期版本。结论为
**CONTRACTED/PARTIAL，P1**：可作为测试分支 adapter，不能把类名 `DURABLE` 当作生产数据权利
已完成。验收必须增加迁移与 ORM/Registry 登记、Fresh Postgres upgrade/downgrade/restart、
撤回同意/跨租户/并发 replay、审计/outbox 和完整删除回执，并接入 production Context resolver。

### 7.12 0ca62d2 会员权益与贡献经济合同复核

`0ca62d2 feat(membership): harden entitlement lifecycle contracts` 为会员权益生命周期补充
租户/家庭作用域、幂等冲突、人工 actor 和 repository/UoW 合同。Fresh Postgres 下
`uv run pytest tests/domains/membership -q`（含 security contract）当前 **50 passed、1 warning**，
证明合同和 SQL 适配器测试层可运行；但尚无 production API/main 组合根、真实 Account→Membership→Family
身份链、Consent/审计/outbox/退款与删除回执，不能将会员/贡献经济蓝图的 DESIGN_ONLY 提升为生产商业能力。
状态为 **CONTRACTED/PARTIAL，P1**；下一步必须补真实 HTTP+Postgres、跨租户/撤回同意/重放和结算审计，
同时保持贡献账、权益账、现金账分离，禁止家庭总分/排名或未经验证的贡献写入。

### 7.13 0cd53fb/6b4a8e9 Growth Onboarding HTTP/PG 纵切片复核

`0cd53fb` 新增 GrowthIntent→GrowthOnboarding 领域、fake/SQL repository 与同事务
audit/outbox/idempotency；`6b4a8e9` 新增 Family API route 和显式 dev/production 安装器，
路由不在 handler 内创建 adapter。无 DB 的 journey/route 契约通过，Fresh Postgres 批量首跑
曾出现一次 `actor_family_scope_denied`，同一用例隔离重跑通过，说明 fixture/时钟隔离仍需稳定性证据。
对应 migration 0016/0017 当前均未形成 tracked/Manifest/ADR/ORM 审批链。

结论：**GO（契约测试）/CONTRACTED-PARTIAL（测试候选）/NO-GO（生产）**。HTTP 默认依赖
fail-closed 503，显式生产安装器才使用 PostgreSQL identity resolver；main.py 的环境挂载仍受
未收口的 `is_dev_environment()` 默认值影响。必须补重复 PG 稳定运行、跨租户/撤回 consent/非法
UUID=400、三环境无 token=401 与跨租户=403 后，方可提升状态。

### 7.14 cbc055e/736ae19/d2196bc 环境与 Experience 错误语义验收

ADR-0069 和 acceptance tests 锁定了 AIFAMILY_ENV 显式 allow-list、Experience
`401 + WWW-Authenticate: Bearer`、`403 family_access_denied` 与 `403 CONSENT_REQUIRED`；
`736ae19`/`d2196bc` 允许启动时明确拒绝不安全环境，但当前 unset `AIFAMILY_ENV` 仍因
`dev_wiring.current_environment()` 默认 development 而测试红灯。测试通过仅说明边界合同，
未修改冲突的 `dev_wiring.py`/`production_experience_wiring.py`，也未证明真实 auth/session/
tenant/consent。状态为 **CONTRACTED/PARTIAL，P0 BLOCKED**，生产仍 NO-GO。

### 7.15 本轮 Agent 总控交付矩阵（2026-08-30）

| Agent/线程（标题） | Scope | Owner/提交 | 当前状态与实证 | 下一动作/闸门 |
|---|---|---|---|---|
| APLT-2（security gate） | 环境 fail-closed、Experience 401/403/同意错误码 | APLT；`cbc055e`、`736ae19`、`d2196bc` | `CONTRACTED/PARTIAL`；定向 7 passed/1 expected-red（unset env）；未改冲突 wiring | 原 WIP owner 收口 `AIFAMILY_ENV` 默认值、真实 auth/session/tenant/consent；TestClient 三环境 401/403 |
| ADOM-5/DB-01（migration） | Alembic baseline/head、ORM/Manifest/ADR | ADOM/ARCH；`5a67a1b` 及 0011-0017 WIP | `PARTIAL/BLOCKED`；head=0017；Fresh PG 8 passed/1 failed/1 skipped（unknown head） | tracked migration + ORM/对象清单/ADR/Manifest；Fresh PG up/down/re-up/restart；unknown head fail |
| AAIR-6（durable deletion） | deletion queue/lease/retry/DLQ/五类回执 | AAIR；durable deletion slice | `CONTRACTED/adapter-only`；context-engine 25 passed，内存 store；无真实 PG/outbox/外部 receipts | durable Postgres/outbox、跨进程 lease、projection cascade 和审计回执；未完成保持 RELEASE BLOCKED |
| AFE-4（UI experience） | 34 UI 语义图标、成就、多模态、跨端契约 | AFE；UI slice、Web `4b9a4b4` | `PARTIAL`；mobile 249 passed/1 skipped/5 failed，Web clientFactory 26 passed/typecheck0 | 修复 UI-02、registry/service contract 五失败；禁止 production 显式 fake client（`DEV:false` fail-closed/强制 HTTP）；四端视觉/无障碍/locale parity |
| GROWTH（S05→S08） | Action→Outcome→Story→Recommendation→Annual/Renewal | growth_action_loop；`b431eda`、`78cb9c1`、`dcc0802` | 测试分支 `GO`；journey 无 DB 40/4、PG 44；无 HTTP/worker/真实 sink | Journey ORM/API、常驻 worker、Audit/Outbox、consent/replay/deletion、UI vertical e2e |
| FGCN / service collaboration | Human Gate→Named Action→TaskAssignment→delivery/quality/contribution | FGCN；`41ad120`→`e7cbb0b` | Fresh `uv run pytest tests/domains/service/fgcn -q` **113 passed**（Postgres URL）；S-01 family-request/self-help gate 与场景 provenance 已绑定 | `GO（测试契约）/NO-GO（生产）`；reviewer/worker/action context 默认 RuntimeError，one-shot worker 无 queue/通知/DLQ，capacity reservation 非原子，gate/assignment 双事务 crash/retry；同一 request replay 在 assignment 已 COMPLETED/REVOKED 时可能误判 mismatch；补 canonical request hash replay、生产 identity/consent/duplicate operationId |
| GROWTH-ONBOARDING | Confirmed Intent→Onboarding HTTP/PG | growth owner；`0cd53fb`、`6b4a8e9` | `CONTRACTED/PARTIAL`；route/domain tests 29 passed；PG 13 passed后重复 12/1 fail；0016/0017 untracked | 修复时钟/search_path flake；非法 UUID=400、跨租户/撤回同意；migration 登记后再升级 |
| AAIR/PLT（Context） | Async/SQL Context Broker、scope/replay/delete | AAIR；`02a80c4`、`6a88625`、`6150169`、`9b10d2d` | `CONTRACTED/PARTIAL`；context 25 passed，PG probe 1 passed（create_all/同 engine）；无 Alembic/restart | Alembic/ORM/Consent durable、真正重启/并发/删除 receipts、production resolver |
| AAIR/EVAL（Experience/评测） | SQL ledger/session、benchmark ref、唯一 AI gate | AAIR/API；`941feae`、`a11f643`、`96905db`、`69f6508`、`674b764`、`050361f`、`b3fffbb`、`5df865e`、`eb33c06` | `CONTRACTED/PARTIAL`；eval+experience 220 passed/1 warning；双 gate、registry lookup、真实 auth/PG/audit/outbox 缺 | 冻结扩张；合并唯一 `AiReleaseGate`+EvalReport registry；接可信 ActorContext/Consent/PG transaction |
| MEMBERSHIP-01 | Entitlement/Contribution/Settlement 合同 | DOM；`0ca62d2` | `CONTRACTED/PARTIAL`；Fresh PG membership 50 passed/1 warning；生产 API/身份/consent/结算审计缺 | 真实 HTTP+PG、退款/争议/删除回执；账本分离、无家庭总分/排名 |
| P1 服务垂直切片（B2C service） | ServiceOffering→Slot→预约→履约→反馈与 provenance | P1 service owner；`e99d499`（分支 `codex/p1-service-vertical-slice`，已推送） | `PARTIAL/测试候选`；SQLite/HTTP/ORM 59 passed/26 skipped，HTTP 10/1 skipped，Fresh PG 4 passed，ORM drift 2 passed，Alembic upgrade→downgrade 0010→upgrade 全通过 | family_api provenance、Audit flush、常驻 worker/DLQ、FGCN bridge 和 Commerce 边界仍缺；补真实身份/同意/租户/删除/审计后才可进生产候选 |
| 运营 Chat（只读回传，标题/commit 未提供） | S21/S24/O13 运营触达、S22/S23/O12/O14 运营服务与事故闭环 | 运营 Chat；无可追踪 commit（只读证据） | `PARTIAL/DESIGN_ONLY`；79 passed/1 skipped/1 warning；唯一 skip 为真实 PG WORM；Onboarding 35/11 skipped；未证明主动欢迎、SLA/补救/回访、可信分享/组队、机构运营或发布事故闭环 | 指派运营 owner；补真实 PG WORM、HTTP/权限/租户/审计/删除和通知 worker；将 DESIGN_ONLY 场景拆成 L4/L5→对象/API/UI/运营队列验收，未完成不得升生产 |

## 8. 纠偏后的迭代设计

### 8.1 未来两周（只做可验收纵切片）

| 切片/owner | 战场 | 输入→活动→输出 | 依赖 | 测试与发布闸门 |
|---|---|---|---|---|
| SEC/ENV-01（APLT/ARCH，P0，owner 未明确） | `main.py`、`dev_wiring.py`、auth/tenant context（当前与他人 WIP 冲突，不能安全接手） | 环境启动配置→显式 allow-list + real session seam→同一 auth/scope API 与拒绝码 | identity/consent port、ADR-0010/环境规范；先由原 WIP owner 收口 | production OpenAPI 无 dev auth 且 real auth 可用；unset/prod/test 负向 404/401/403；三环境 route/error parity；owner 未明确或缺 fail-closed 证据即 BLOCKED/NO-GO |
| DB-01（ADOM/ARCH，P1） | migrations 0009-0017、Manifest、ADR、ORM | WIP revision→登记/校验对象清单→Fresh Postgres up/down/up→提交可追踪 head | ADR-0045/0047/0048/0052/0053/0054/0055/0057/0058/0059、ORM ownership | `git ls-files` + manifest/ADR/ORM 一致；unknown head fail；`AIFAMILY_TEST_DATABASE_URL` roundtrip/concurrency 全绿；否则保持 0008 boundary |
| API-PARITY-01（APLT/AFE，P1） | OpenAPI、Web client、mobile contracts | scope/token envelope→client 注入 Authorization/session/locale→生成契约→四端拒绝/重放 | SEC/ENV-01、trusted_context | OpenAPI duplicate operationId=0；Web 22 auth-context tests；mobile 5 failures=0；production/dev/test paths 与错误码一致 |
| S05→S07（GROWTH / growth_action_loop，P1） | Onboarding、ActionTask/Record、Journey worker | confirmed hypothesis/plan→今日任务/提醒/完成/复盘→Outcome/Feedback draft | S04 evidence、Journey persistence、AI Draft/Human Gate | 当前 journey contract 40/4（PG 44）可进测试；仍需 HTTP/Postgres/outbox、timeout/DLQ/compensation；UI-03/04/05/09/10/11 vertical e2e；无总分/排名 |
| EXPERIENCE-LEDGER-01（AAIR/API，P1） | `sql_run_ledger.py` + composition root | HTTP preflight→provider→finalize/replay→interaction/delete | 0010 schema、identity/consent、Audit/Outbox | `tests/intelligence/experience` 220/1 仍仅契约；需真实 FastAPI+Postgres session/transaction、401/403、并发/restart/deletion receipts；否则 CONTRACTED/PARTIAL |
| EVAL-REF-01（AAIR/API） | `multimodal_eval.py`、`backend/intelligence/evaluation/release_gate.py`、`run_http.py`、EvalReport registry | benchmark→唯一 gate lookup/版本校验→run evaluation projection→feedback | ProviderRegistry、environment/data_class、tenant/locale/consent/provenance、Human/QA admission | 当前 220/1（evaluation+experience）且 P4 contract 已绿但仍仅 synthetic；仍存在双 gate；96905db 仅 coordinator；需合并为唯一 `AiReleaseGate`、真实 report lookup、审批/撤销/删除、版本/candidate/draft 绑定和跨租户拒绝；不得写 Outcome/Fact |
| AI-FOUNDATION-01（AAIR，P1） | Context projection、Prompt/Schema/Knowledge registry、Principal facade | authorized family refs→snapshot/retrieval/schema draft→HumanTask/NamedAction receipt | identity/consent、DB head、Model Gateway | tenant/locale/deletion/provenance tests；model unavailable/schema invalid/human gate；synthetic provider 与 production adapter 同契约；不得升 Production |
| CONTEXT-ASYNC-01（AAIR/PLT，P1） | `backend/intelligence/context_engine/async_port.py` 与 durable composition | async observation→scoped snapshot/read/delete→Postgres projection/outbox | Identity/Consent、Context durable store、DB-01 | 当前 02a80c4 仅 InMemory adapter，25 项契约测试；需 Fresh Postgres 事务、重启/并发 replay、撤回同意/删除 receipts 和三环境 parity 后方可 INTEGRATED |
| UI-GAME-01（AFE，P1） | 全 34 UI 与 Web responsive | canonical object/status→图标/成就/多模态卡片→可解释下一步 | API-PARITY、evidence-bound achievement | 视觉快照 + 语义无 UI-xx；删 score/peer/rank/虚假 social proof；screen reader/locale；5 failures 清零 |

### 8.2 六周

完成 S05-S10 纵向闭环（Principal→Context→Draft→家庭确认→21 天行动→真人陪跑），
FGCN 常驻 worker/质量/争议状态机，真实 Postgres projection/outbox，Membership/Payment/
Points ledger 的测试环境完整状态机；补 O01-O12 的最小运营队列、评估、审核和删除作业。
每个场景必须有 owner、L4/L5 清单、OpenAPI、对象表、审计/outbox、成功/拒绝/重放/超时/
死信/补偿及三环境 parity 证据。六周结束仍不能提供这些证据的功能留在 PARTIAL，不扩张第二
个模型供应商或第二套 Agent Runtime。

### 8.3 九十天

以真实但受控的 B2C 家庭成长闭环为主线，逐步接入 B2B2C 机构和 C2C 社区：

1. Family Context/Growth Graph/记忆删除达到 Postgres、分区/归档、跨租户拒绝、备份恢复和 DPIA
   演练；embedding/vector 只有在删除收据和区域策略成立后启用。
2. Service Blueprint Library、产品设计 AI、12 项 compiler、simulation/red-team、人工发布/
   回滚与 service runtime 接入，校长对外统一 IP、对内统一能力路由。
3. 多语言 canonical concept/content/model/policy locale、Android/iOS/Harmony/小程序 contract
   parity、区域租户配额、容量/成本/灾备与运营事故台账；通过影子评估后才放宽低风险自治。
4. 经济价值建立在透明订单/支付/权益/贡献账本和长期复购上，不以家庭总分、儿童排名或 AI
   伪造社会证明驱动增长。

## 9. 停止扩张、删除/合并与优先补齐

### 立即停止或删除

- 停止新增任何家庭总分、peer reference、成长等级、跨家庭排名、伪造打卡/团长/倒计时/邀请
  进度；删除 UI-03 score/radar 对比、UI-06/10/18 `Lv.*` 和静态 social proof，保留法律/边界
  文案。会员付费档位可保留，但必须与成长评价隔离。
- 停止把 `InMemoryDurableDeletionStore`、deterministic interpretation、fixture catalog、
  one-shot FGCN worker 说成生产 AI/服务能力；它们只能作为同构测试替身。
- 停止新建第二套模型网关、第二套 Principal 或 Node/Express 业务路径；未完成 ADR 前不扩充
  更多 migration head，不把未跟踪 0009-0017 当完成。
- 在 `multimodal_eval.py:EvaluationReleaseGate` 与 `evaluation/release_gate.py:AiReleaseGate`
  合并为唯一 canonical gate、完成 report registry lookup 前，冻结新增 evaluation/release-gate/
  report-persistence 代码；只允许补 canonical gate、registry/版本/租户负向测试和审计删除证据。

### 合并和优先补齐

- 合并“挂牌—预约—履约”与 FGCN“案件—任务—责任—贡献”为一个 service application 边界，
  保留不同场景投影但只有一个 canonical writer。
- 优先补 P0 身份/同意/租户/环境默认值；随后 S05→S07、Context/Memory/Principal 单一闭环、
  Postgres/outbox/worker/删除收据、Web/mobile contract parity。
- 社区、B2B2C、积分、支付、运营台不是删除项；在测试环境按完整状态机建设，生产只等待真实
  外部适配器、主体准入和合规闸门，不得另造“测试简化版”。

## 10. 已发出的反向整改意见（本轮）

以下意见已通过协作消息发送给 PM/owner；没有可安全修改的 owner 战场时记录为“待派发”，
不把建议误报为完成：

| 优先级 | owner/文件模块 | 风险 | 补测命令 | 验收标准 |
|---|---|---|---|---|
| P0 | APLT/ARCH（owner 未明确，当前与他人 WIP 冲突）：`backend/apps/family_api/main.py`、`dev_wiring.py`、auth | 默认环境开发值让 dev_auth 暴露；生产仅 404 无真实等价 auth；租户/同意缺失 | `AIFAMILY_ENV=production uv run pytest tests/apps/family_api/test_production_dev_auth_gate.py -q`；unset/test/prod OpenAPI 与 401/403/404 smoke | 未设置环境也 fail-closed；real session/tenant/consent route 与 dev/test 同功能集合；无 synthetic auth 生产暴露；owner 明确前保持 BLOCKED |
| P1 | AQA/GOV：`DOMAIN_REGISTRY.yaml`、Ruff、Manifest/CI | YAML 解析、lint debt、未登记 `product_management`/`prompt_registry`/pycache、branch protection 失效 | `uv run pytest tests/architecture -q`; `uv run ruff check .`; CI clean + `gh api repos/PoCP-Protocol/AiFamily/branches/main/protection` |  architecture 0 failures；Ruff 0 errors；每个 backend 目录有唯一登记；CI/主分支保护可证明 |
| P1 | ADOM/ARCH：`0009-0017`、ADR/Manifest/ORM | 未跟踪 migration 被工作树 manifest 误放行；head 漂移、不可回滚/不可审计；当前未知 0017 | `git ls-files` 检查；`uv run alembic heads`; Postgres `tests/database/test_alembic_baseline_applies.py`/`test_fgcn_migration_chain.py` | 0008=159 固定；0009-0017 仅提交后 allow-list；ORM/对象表/ADR/Manifest/Fresh Postgres/concurrency 全一致；unknown head fail |
| P1 | AAIR：`context_engine/durable_deletion.py`、生产 wiring | 内存 adapter 丢作业，不能删除外部媒体/vector/cache/评估副本，误宣称合规 | `uv run pytest tests/intelligence/context_engine -q`; Postgres restart/lease/DLQ/五 adapter receipts | durable queue/store、跨进程 lease/retry/DLQ、五类真实 adapter 和删除 proof/audit；在此以前保持 CONTRACTED/RELEASE BLOCKED |
| P1 | AFE/API：mobile 全量 UI 与 `frontend/web/src/api/httpClient.ts` | 249/1/5 红灯；Web 已注入 Authorization/session/locale 但缺 backend 401/403 smoke，四端契约仍漂移；UI 视觉通过但业务不通 | `cd frontend/mobile; pnpm test -- --run`; `cd frontend/web; pnpm test -- --run; pnpm typecheck`; OpenAPI parity | mobile 5→0 failures；client 注入 token/session/locale/idempotency；UI 图标/成就无 UI-xx、无 score/rank/伪造进度；Web/mobile/后端同一拒绝/重放路径 |
| P1 | GROWTH/无 owner：S05-N04、S07 ActionTask/Worker | 价值链在“计划后”断裂，情绪价值不能转成长结果；无法复盘/复购 | `pytest` domain/API/Postgres e2e + UI-03/04/05/09/10/11 vertical tests | Onboarding、今日任务、提醒、完成/跳过、21d 结项、Outcome 人工确认、超时/补偿/审计/outbox 全闭环 |
| P1 | AAIR/GOV：`multimodal_eval.py`、`evaluation/release_gate.py`、`run_http.py` | 69f6508 与既有 gate 双真相；96905db 只协调 interaction projection，未做 registry/主体/租户绑定 | `uv run pytest tests/intelligence/evaluation tests/intelligence/experience -q`; 新增 architecture test 断言单 gate；Postgres registry/审计/删除 smoke | 合并唯一 `AiReleaseGate`；EvalReport registry lookup（case/candidate/version/provenance/tenant/locale/consent）；unknown/revoked/deleted/replay/跨租户拒绝；report projection 仅 NOT_MEASURED，不写 Outcome/Fact；在此以前冻结扩张 |

## 11. 发布判定和持续检查

当前发布判定：**NO-GO**。任一以下红线未通过均阻断 dev→test→production promotion：

1. 默认环境或任何 composition 能暴露 synthetic dev auth；真实身份/租户/同意/撤权未可调用；
2. 三环境路由、状态机、错误码、权限、审计、Human Gate、删除/支付失败路径不一致；
3. 未知或未追踪 Alembic head、ORM/迁移/对象清单不一致，或 Fresh Postgres roundtrip 不全绿；
4. AI Draft/Recommendation 直写 Fact、绕过 Model Gateway/Consent/Human Gate，或记忆/媒体派生
   无可验证删除证明；
5. 家庭总分/排名/儿童等级或虚假社会证明仍作为产品事实；
6. OpenAPI、Web、mobile（及未来 Android/iOS/Harmony/小程序）契约不一致，关键测试红灯；
7. P0/P1 运营、审计、回滚、死信、事故接管没有 owner 和证据。

项目助理每个工作日做一次代码/Registry/迁移/测试快照；每个敏捷切片合并前做一次五层
对标，至少重跑 architecture、Ruff、相关 domain/API/mobile/Web、OpenAPI parity 和必要的
Fresh Postgres；每周给 PM 输出“已解决/仍成立/证据不足/已过时”清单。任何没有证据的完成
声明自动降级为 PARTIAL，并向 owner 发返工消息；连续两次偏移不纠正则升级为 NO-GO。
