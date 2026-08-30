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
| `uv run pytest tests/architecture -q` | **106 passed, 1 skipped, 4 failed** | DOMAIN_REGISTRY YAML 缩进、Ruff debt 3>0、未登记 `product_management`/`prompt_registry`/`__pycache__` |
| `uv run ruff check . --output-format concise` | **3 errors** | `family/domain/entities.py:E501`、`prompt_registry/contracts.py:SIM102`、`prompt_registry/registry.py:E501` |
| `uv run alembic heads` | `0010_experience_run_interactions (head)` | 0009/0010/ADR-0047 当前仍有未跟踪文件；未知/未提交 head 必须阻断 |
| Postgres `tests/database/test_alembic_baseline_applies.py`（`AIFAMILY_TEST_DATABASE_URL`） | **5 passed, 1 failed** | 失败为 0010 追踪/审批闸门；说明“不跳过未知 head”有效，不能报全绿 |
| `uv run pytest tests/intelligence/context_engine -q` | **18 passed** | durable deletion 6 + legacy worker/其它 12；仍是 synthetic in-memory adapter |
| `cd frontend/mobile; pnpm test -- --run` | **249 passed, 1 skipped, 5 failed** | UI-02 旧契约 2；registry/service 契约 3；全量不能报绿 |
| `cd frontend/web; pnpm test -- --run; pnpm typecheck` | **21 passed；typecheck 0** | HTTP client 可用，但未带 Authorization/session/tenant 注入 |
| FastAPI OpenAPI | unset/test **61** paths；production **57** paths | unset 默认 `development`，仍暴露 dev auth；production 隐藏 `/auth/account-session` 但 experience resolver 仍 503 |

## 1. 五层架构对标矩阵

| 层 | 商业/设计目标 | 当前实现与证据 | 偏移、严重度、判定 |
|---|---|---|---|
| 业务架构 | 家庭教育为入口，拓展家庭需求服务/产品/方案；家庭拥有数据、AI 不替人；六引擎形成情绪→成长→经济价值闭环；S01-S24/O01-O14 有唯一边界 | 业务文档已完整定义 Fact/Perspective/Recommendation/Action/Outcome、FGCN、三层价值网络和 24+14 场景；代码只形成 S04 测评、N0-N1 Need 首片及部分服务/商品读写 | **业务设计完整，运行兑现不足，P1**。S07/S08/S09、FGCN 完整交付、支付/社区/运营大部分未实现；不能以 34 UI 或路由存在代替闭环 |
| 流程架构 | L0 VS-01…VS-05 → L1 P01…P06 → L2 S/O → L3 子流程 → L4 节点 → L5 API/Command/Event/Job/Human Task，异常可退出、可重放、可接管 | 目录已列出 L0-L5；S04 节点有 Handler/SQL/fake/幂等；S05/S06 只有部分；S07 action worker、S14 dispute、S20 deletion、O05/O09/O12/O14 等仍无完整执行器 | **流程“画出来”多于“跑起来”，P1**。每个 L4 必须绑定输入/活动/输出/规则/异常/owner/API/数据/测试，缺一只能 PARTIAL |
| 数据架构 | 主数据与业务数据分离；租户/locale/主体/同意/删除/审计贯穿；Postgres 事实、事件和投影可重放；Family Context/Growth Graph 让平台长期懂家庭 | Alembic baseline、Assessment/Growth/Journey/FGCN 部分表及 outbox 存在；数据目录覆盖目标对象和关系；Family Context、三类记忆、embedding、删除证明仍无 durable production runtime；当前 head 0010 WIP 未追踪 | **P0/P1**：家庭记忆与跨会话图谱为独占区空白；0009/0010 未提交且 manifest 变更未形成可信链；`product_intelligence` ORM/迁移漂移及公共 schema 目标态未落地 |
| 应用架构 | A0-A6 分层，唯一应用服务和写入者；Family API、Web、Android/iOS/Harmony/小程序同一契约；dev/test/prod 功能同构 | FastAPI 已挂 assessment、journey、service、commerce、membership、family-need、FGCN、experience；OpenAPI 生产 57 paths；Web client 21 tests；mobile 34 UI 可渲染 | **P0/P1**：生产身份/同意/租户链未完整接线；experience 默认 resolver 503；Web 请求无 Authorization；mobile 五个失败；service journey duplicate operationId；多端 parity 尚无一套 CI 闸门 |
| AI 技术架构 | 单一法咪莉校长控制面：Context/Memory/Principal/Soul/Knowledge/Model Gateway/Prompt-Schema/Eval/Human Gate/Observability/Deletion；AI 只产 Draft/Recommendation/Proposal，Named Action 才写事实 | `backend/intelligence` 有 principal/context_engine/knowledge/human_gate/experience/model_gateway/agent_runtime 契约；18 个 context tests、durable human gate/agent runtime 测试；但 gateway/provider、Soul/Knowledge registry、Context durable projection、Eval/trace/worker/真实多模态适配未形成生产链 | **P1，生产阻断**：契约和 in-memory adapter 不等于运行能力；AAIR-6 仍 `CONTRACTED/adapter-only`；未接入唯一 Principal 家庭请求→人工闸门→Named Action 的完整链 |

## 2. 商业蓝图六引擎和精神对齐

| 蓝图引擎 | 期望商业作用 | 当前承载 | 评审结论/缺口 |
|---|---|---|---|
| 拼多多式增长 | 低门槛测评、挑战/裂变、让用户带来用户 | UI-01/15/16、部分邀请/商城 fixture | 体验入口存在；真实邀请、单层激励、反伪造进度和归因账本未闭环，不能生成虚假拼团数字 |
| 字节式算法分发 | 用户画像、行为反馈、内容/服务精准匹配 | deterministic assessment、部分 recommendations、feature/experiment 契约 | 跨会话 Family Context/Growth Graph 尚空白；无生产检索、事件指标和可解释推荐链 |
| 海底捞式服务 | 情绪价值优先、即时响应、真人兜底、复购 | service booking/records、FGCN Human Gate 契约、UI-05/19-24 | 预约子链和控制面是 PARTIAL；客服队列、SLA、质量恢复、常驻 worker、真实身份/资源未完成 |
| 贝壳式 ACN/FGCN | 一客一案、一案一管家、一任务一责任、验收贡献 | FGCN schema/one-shot worker/Named Action 测试 | 业务设计正确，内存编排和缺生产 session/worker/贡献结算；应与挂牌预约模型做 ADR 融合，不得两套写入者并存 |
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
| schema/migration | baseline 0001→0008 的 159 固定边界；0009/0010 只能在 ADR、Manifest、ORM、对象清单、Fresh Postgres 后 allow-list | 当前 head=0010；0009/0010/ADR-0047 未跟踪，manifest 工作树修改会让测试谓词误判；5/6 DB 测试通过但 downgrade/upcycle 仍失败，P1 阻断 |

## 5. 应用、API 与四端 parity

1. FastAPI 生产 OpenAPI 仍有 57 paths，开发/测试有 61 paths；`dev_auth` 在 `AIFAMILY_ENV`
   未设置时因 `current_environment()` 默认 `development` 而暴露（生产明确设置时 404）。默认值
   是 P0：启动配置必须 fail-closed，且 real auth/session route 要与 dev/test 具备同一功能集合。
2. Experience 多模态路由在生产 OpenAPI 可见，但默认 resolver 返回 503；dev/test 依赖进程内
   synthetic runtime。不能把“生产不泄露 dev auth”误写成“生产功能同构已完成”。
3. Web `HttpExperienceApiClient` 的 21 个测试和 typecheck 全绿，但 `ClientOptions` 没有 token/
   session/tenant/consent 注入，请求无 `Authorization`。和 backend Bearer resolver、trusted
   context 的契约不一致，必须在 client、fake fetch test、production composition 统一。
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

## 7. 当前开发计划与 WIP 偏移

1. `AGILE_REBUILD_PLAN_V1` 将 DB-01/AAIR-6/AFE-4/PMA-1 标为阶段切片；本轮把 AAIR-6
   统计刷新为 context-engine **18 passed**，mobile 为 **249/1/5**，不沿用旧的 13/247。
2. DB-01 0001 baseline 与 0004-0008 159 边界可复测；0009/0010 文件和 ADR/Manifest 工作树
   WIP 尚未形成可审计提交，不能把 0010 `MIGRATED_TESTED` registry 行视为发布事实。
3. AFE-4 的 UI-19/20/21/22/23/24/31 图标化与成就组件方向符合 UX；但全量测试红灯，
   旧 UI-02 断言和 service contract 没有收敛，状态必须 PARTIAL。
4. PMA-1 的历史文档已记录 dev_auth、Ruff、Registry、mobile/Web gaps；本评审新增了应用/
   AI/商业/流程/数据的交叉断点，不得只修一个测试而忽略链路。
5. WIP `backend/intelligence/product_management`、`prompt_registry`、多项 ADR/迁移、
   frontend/mobile 新目录大量未登记/未提交；任何“完成”必须同时更新 owner、Manifest、ADR、
   测试和可回滚证据，不能靠目录出现推断完成。

## 8. 纠偏后的迭代设计

### 8.1 未来两周（只做可验收纵切片）

| 切片/owner | 战场 | 输入→活动→输出 | 依赖 | 测试与发布闸门 |
|---|---|---|---|---|
| SEC/ENV-01（APLT/ARCH，P0） | `main.py`、`dev_wiring.py`、auth/tenant context | 环境启动配置→显式 allow-list + real session seam→同一 auth/scope API 与拒绝码 | identity/consent port、ADR-0010/环境规范 | production OpenAPI 无 dev auth 且 real auth 可用；unset/prod/test 负向 404/401/403；三环境 route/error parity；否则 NO-GO |
| DB-01（ADOM/ARCH，P1） | migrations 0009/0010、Manifest、ADR、ORM | WIP revision→登记/校验对象清单→Fresh Postgres up/down/up→提交可追踪 head | ADR-0045/0047、ORM ownership | `git ls-files` + manifest/ADR/ORM 一致；unknown head fail；`AIFAMILY_TEST_DATABASE_URL` roundtrip/concurrency 全绿；否则保持 0008 boundary |
| API-PARITY-01（APLT/AFE，P1） | OpenAPI、Web client、mobile contracts | scope/token envelope→client 注入 Authorization/tenant/locale→生成契约→四端拒绝/重放 | SEC/ENV-01、trusted_context | OpenAPI duplicate operationId=0；Web 21+auth tests；mobile 5 failures=0；production/dev/test paths 与错误码一致 |
| S05→S07（GROWTH owner 待指定，P1） | Onboarding、ActionTask/Record、Journey worker | confirmed hypothesis/plan→今日任务/提醒/完成/复盘→Outcome/Feedback draft | S04 evidence、Journey persistence、AI Draft/Human Gate | success/reject/idempotency/timeout/DLQ/compensation；UI-03/04/05/09/10/11 vertical e2e；无总分/排名 |
| AI-FOUNDATION-01（AAIR，P1） | Context projection、Prompt/Schema/Knowledge registry、Principal facade | authorized family refs→snapshot/retrieval/schema draft→HumanTask/NamedAction receipt | identity/consent、DB head、Model Gateway | tenant/locale/deletion/provenance tests；model unavailable/schema invalid/human gate；synthetic provider 与 production adapter 同契约；不得升 Production |
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
  更多 migration head，不把未跟踪 0009/0010 当完成。

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
| P0 | APLT/ARCH：`backend/apps/family_api/main.py`、`dev_wiring.py`、auth | 默认环境开发值让 dev_auth 暴露；生产仅 404 无真实等价 auth；租户/同意缺失 | `AIFAMILY_ENV=production uv run pytest tests/apps/family_api/test_production_dev_auth_gate.py -q`；unset/test/prod OpenAPI 与 401/403/404 smoke | 未设置环境也 fail-closed；real session/tenant/consent route 与 dev/test 同功能集合；无 synthetic auth 生产暴露 |
| P1 | AQA/GOV：`DOMAIN_REGISTRY.yaml`、Ruff、Manifest/CI | YAML 解析、lint debt、未登记 `product_management`/`prompt_registry`/pycache、branch protection 失效 | `uv run pytest tests/architecture -q`; `uv run ruff check .`; CI clean + `gh api repos/PoCP-Protocol/AiFamily/branches/main/protection` |  architecture 0 failures；Ruff 0 errors；每个 backend 目录有唯一登记；CI/主分支保护可证明 |
| P1 | ADOM/ARCH：`0009/0010`、ADR-0045/0047、Manifest、ORM | 未跟踪 migration 被工作树 manifest 误放行；head 漂移、不可回滚/不可审计 | `git ls-files` 检查；`uv run alembic heads`; Postgres `tests/database/test_alembic_baseline_applies.py`/`test_fgcn_migration_chain.py` | 0008=159 固定；0009/0010 仅提交后 allow-list；ORM/对象表/ADR/Manifest/Fresh Postgres/concurrency 全一致；unknown head fail |
| P1 | AAIR：`context_engine/durable_deletion.py`、生产 wiring | 内存 adapter 丢作业，不能删除外部媒体/vector/cache/评估副本，误宣称合规 | `uv run pytest tests/intelligence/context_engine -q`; Postgres restart/lease/DLQ/五 adapter receipts | durable queue/store、跨进程 lease/retry/DLQ、五类真实 adapter 和删除 proof/audit；在此以前保持 CONTRACTED/RELEASE BLOCKED |
| P1 | AFE/API：mobile 全量 UI 与 `frontend/web/src/api/httpClient.ts` | 249/1/5 红灯；Web 无 Authorization/tenant，四端契约漂移；UI 视觉通过但业务不通 | `cd frontend/mobile; pnpm test -- --run`; `cd frontend/web; pnpm test -- --run; pnpm typecheck`; OpenAPI parity | mobile 5→0 failures；client 注入 token/scope/locale/idempotency；UI 图标/成就无 UI-xx、无 score/rank/伪造进度；Web/mobile/后端同一拒绝/重放路径 |
| P1 | GROWTH/无 owner：S05-N04、S07 ActionTask/Worker | 价值链在“计划后”断裂，情绪价值不能转成长结果；无法复盘/复购 | `pytest` domain/API/Postgres e2e + UI-03/04/05/09/10/11 vertical tests | Onboarding、今日任务、提醒、完成/跳过、21d 结项、Outcome 人工确认、超时/补偿/审计/outbox 全闭环 |

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
