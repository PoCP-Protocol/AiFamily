---
id: DEL-MIGPLAN-001
title: AiFamily 精选式迁移计划
type: delivery
status: current
version: 2.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-30
canonical: true
supersedes: null
superseded_by: null
---

# AiFamily — 精选式迁移计划 V2.0（取代最初的 Wave 0-10 总计划与源仓库V1）

```text
DOC_KIND        = GOVERNANCE_SSOT / TECHNICAL_ARCHITECTURE_FREEZE
ARCHITECTURE_ID = AIFAMILY_PYTHON_SELECTIVE_V2
SUPERSEDES      = (1) 本会话最初给出的"AiFamily Re-foundation & Migration Master Plan"(Wave 0-10版,
                      其"全量分批搬家"假设与下方第0节指出的问题相同)
                  (2) D:\family-ai\50_开发_dev\architecture\FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md
                      (源仓库自己的Python-only计划,同样犯"全量迁移"错误,标记DEPRECATED,原地保留不删除)
CANONICAL_HOME  = D:\AiFamily (本仓库是迁移计划与实施的唯一权威落地位置, 不是 D:\family-ai)
DATE            = 2026-08-29
STATUS          = TARGET_FROZEN (冻结目标拓扑与边界，不冻结允许业务能力的开发)
AUTHORIZED_BY   = project-owner (verbal in-session override)
GROUNDING       = 基于对源仓库 D:\family-ai (baseline 1ff1681) 的 apps/api(NestJS)、
                  backend/domains/*(Python)、legacy-system(FELS)、packages/*、
                  database/migrations(58个文件)、apps/mobile+web(前端)、测试资产、治理文档
                  的独立只读代码审计(非文档自述) —— 详见 governance/MIGRATION_MANIFEST.yaml,
                  以及源仓库 FAMILY_COMMERCIAL_VALUE_STRATEGY_V2.md 的三区方法论、
                  FAMILY_UI_BACKEND_SCENARIO_CONSISTENCY_AUDIT_V1.md 的34UI真实状态、
                  docs/14_reference/legacy_audits/FAMILY_CONSUMER_UI_FRONTEND_BACKEND_CONSISTENCY_MATRIX_001.md(矩阵001)、
                  法咪莉教育战略白皮书/新商业模式PPT/家庭教育大模型平台合作方案(见docs/01_strategy/source_materials/)
```

## 0. 与V1的关系：纠正一个根本性错误，不是延续微调

V1（`FAMILY_AI_PYTHON_ONLY_MIGRATION_PLAN_V1.md`，2026-08-28，`TARGET_FROZEN`，Batch 1 IN_PROGRESS）判定作废。

**V1没有做错的部分（保留）**：
- 目标技术栈：Python 3.12 + FastAPI + Pydantic v2 + SQLAlchemy 2 + Alembic + PostgreSQL + Redis + Temporal + httpx + pytest + Ruff + mypy + OpenTelemetry + uv。
- 三进程划分：`family-api`(业务) / `ai-runtime`(智能) / `workflow-worker`(长流程)。
- 领域四层结构约定：`api/{routes,requests,responses}` / `application/{commands,queries,handlers,ports}` / `domain/{entities,value_objects,policies,events,errors}` / `infrastructure/{sqlalchemy_models,repositories,projections}`。
- AI Runtime隔离规则：`may_mutate_business_state=false`，AI Runtime不得直接import业务域repository，只能产出Draft/Hypothesis/Explanation/Proposal，canonical写入只能经业务域自己的Named Action。
- 单向域接管节奏：`NEST_ACTIVE → PYTHON_READY → CUTOVER → PYTHON_ACTIVE → NEST_REMOVED`，禁止双写、禁止双主。
- 安全/治理保真要求（第10节）：`fact_boundary`/`hypothesis_not_fact`标签、构念白名单、安全筛查的批量可见性、同意撤回即时生效、AI输出永不直写canonical。

**V1的根本性错误（本文档存在的理由）**：

第8节把迁移范围写成"Batch 1到Batch 8覆盖全部业务域，终点是`Batch 8 = Full NestJS deletion`"——即默认**全部代码都要迁**，只是分批而已。这个假设本身就是错的，原因有独立代码审计实测支持：

1. **合成数据不是业务代码**：`dev-platform-surfaces.service.ts`/`dev-core-growth.service.ts`自述`data_source: 'SYNTHETIC_DEV_ONLY'`，24张硬编码UI卡片+文案字典，零DB读写。V1把这类代码也算作"最终要迁移的NestJS业务API"的一部分，若照单迁移就是把假数据服务原样搬进Python，不解决任何问题。
2. **零测试的Python域不能被当作"已完成的迁移基础"**：`backend/domains/membership`(2627行，最大Python域)零测试目录，其`FORBIDDEN_TIER_FIELD_TOKENS`不变量注释自称"由guardrail test强制"但该测试不存在。V1的Batch划分完全没有对现有Python域做真伪核验，隐含假设"Python代码=已验证的迁移进度"。
3. **死代码不该有迁移批次**：`waf-domain.service.ts`纯内存Map、零路由引用；`apps/ai-runtime`源码已从磁盘删除只剩`.pyc`；`apps/fes-api`声明Nest依赖却无`@Module`；`apps/consumer-web`/`apps/ops-web`目录内只有node_modules。这些如果混在Batch 1-8的"最终会迁移"范围里，会让批次范围虚高。
4. **34个UI的真实完成度和V1的批次顺序脱节**：`FAMILY_UI_BACKEND_SCENARIO_CONSISTENCY_AUDIT_V1.md`证实六类业务闭环中只有ASSESSMENT(UI-02→UI-03)和SERVICE的预约子链(UI-21/24)是端到端真实打通的,其余(PLAN按钮接线、GROWTH效果类页面、COMMERCE目录积分、COMMUNITY社区流)仍是`UI_READY_BACKEND_GAP`或`GATE_BOUNDARY`。V1的Batch 2-7是按"业务域名称的完整性"排列(Family/Growth/Program/Resource/Content...)，不是按"哪条链已经被真实验证值得投入Python重写"排列。
5. **没有区分"值得深度重建"和"够用就行"**：`FAMILY_COMMERCIAL_VALUE_STRATEGY_V2.md`第8节的三区方法论(同质区/优势区/独占区)明确指出，只有独占区候选(Family Context/Family Growth Graph/Growth Intervention Engine/Service Blueprint Library)值得押注核心研发资源，同质区能力(通用AI问答、通用打卡)不该被当作和独占区一样重的迁移单元。V1把所有域一视同仁地列进Batch，没有体现这个优先级差异。

**本文档做的事**：把V1的"全量分批搬家"改为"证据分类后的精选迁移"——沿用V1所有正确的技术决定(第0节保留清单)，重新定义"哪些代码真正进入Python目标态"，并给出每个能力的**disposition**(不是"批次序号"，是"是否迁移、迁多深、以什么形态迁移")。

## 1. Disposition分类法（替代V1"批次=全迁移"的默认假设）

每一项现有能力（NestJS模块、Python域、契约包、测试资产、数据库表）必须先被归入以下六类之一，才允许进入本计划的施工范围：

| Disposition | 含义 | 施工方式 |
|---|---|---|
| `MIGRATE` | 有真实业务价值、有测试或可补测试、值得原样迁移语义 | 按V1第3节四层结构重写，测试先行 |
| `REIMPLEMENT` | 有真实业务价值但设计需要重做(如平台内核原语在Python侧完全不存在) | 重新设计，不参照现有代码结构 |
| `CONTRACT_ONLY` | 只有契约/规则值得保留，代码本身不迁 | 提取为docs/schema，原代码归档 |
| `ARCHIVE` | 有历史/参考价值但不进入生产目标态 | 保留在legacy-system或`archive/`标注，不删除 |
| `DELETE` | 已确认零价值(空壳/死代码/重复文件) | 标记待清理，需二次确认后删除 |
| `REVIEW_REQUIRED` | 证据不足以判定，需要人类或补充调研裁决 | 阻塞，不得假设为MIGRATE |

默认状态是`REVIEW_REQUIRED`，不是`MIGRATE`。任何域进入Batch施工前，必须先有明确的disposition记录（存放于`governance/PYTHON_MIGRATION_DISPOSITION_REGISTRY.yaml`，本文档第6节给出初始版本）。

## 2. 三区方法论驱动的投入深度分级（沿用V2第8节，落到工程执行）

Disposition只回答"迁不迁"，不回答"迁得多深"。三区方法论回答后者：

| 区域 | 迁移深度 | 对应能力 |
|---|---|---|
| 同质区 | 够用即可，不重新设计，直接照抄现有语义搬到Python | 通用打卡记录、通用内容展示、UI-13/14目录浏览类 |
| 优势区 | 值得做深，但用现有FGCN设计(V1.1第五六章，V2第5节已确认保留)指导，不重新发明 | 21/90天真人+AI协同计划、专家咨询预约网络(SERVICE闭环，已端到端验证) |
| 独占区候选 | 核心研发资源倾斜，允许从零设计，不受"抢进度"约束 | Family Context检索层、GrowthHypothesis的primary_contradiction排序、Service Blueprint接入matches、Growth Intervention Engine雏形 |

**结论**：Batch排期的优先级不是"域名字母顺序"或"业务重要性直觉"，是"该域当前证据状态×它所属的区域"两个维度的乘积。ASSESSMENT域(独占区雏形所在地，且已端到端验证)排第一，是两个维度同时最优——这与V1把Assessment排Batch 1的直觉判断偶然一致，但本文档给出的是可复用的判断方法，不是巧合。

## 3. 六类业务闭环的证据状态（决定哪些域现在就该进Batch，哪些该推迟）

沿用`FAMILY_UI_BACKEND_SCENARIO_CONSISTENCY_AUDIT_V1.md`第1节的命名，回指矩阵001：

| 闭环 | 对应UI | 矩阵001状态 | 本计划的处理 |
|---|---|---|---|
| ASSESSMENT | UI-02→UI-03 | 已端到端验证(`COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV`) | Batch 1，维持V1原定范围 |
| SERVICE(预约子链) | UI-19→UI-21→UI-24 | UI-19/20=`BACKEND_READY`，UI-21/24=`E2E_READY` | 提前到Batch 2，理由：已验证的付费主力闭环(V2第2节"层2")，FGCN机制的价值最大化场景，晚做等于让已验证价值悬空 |
| PLAN(按钮接线) | UI-04→UI-05→UI-09 | UI-09已验证；UI-04/05=`UI_READY_BACKEND_GAP`(pause入口连客户端SDK都没有) | 与GrowthPlan域一并处理，但明确排除"先补齐前端pause按钮"作为Python迁移的前置阻塞项——那是独立的前端任务，不占用Python域迁移工时 |
| GROWTH(成长过程、回顾与分享) | UI-08/11/12/29 | UI-11跨家庭排名/总分属于禁止正向行为；UI-08/12/29允许的私有回顾、证据绑定成果和经同意分享仍需建设 | **允许路径必须迁移并在测试环境完整验证**；禁止路径保留拒绝、审计和人工处理，不因UI-11的违规设计放弃整个GROWTH闭环 |
| COMMERCE(目录/积分) | UI-13/14/16/17/18 | UI-15/16=`E2E_READY`；UI-13/14=`UI_READY_BACKEND_GAP`；UI-17为积分账本/兑换/权益接线缺口，硬编码1280必须清理 | 排入Batch 6；测试环境完整实现目录、订单、支付 sandbox、会员、权益、积分、退款和续购，生产再替换真实商品、库存、支付和外部结算适配器 |
| COMMUNITY(社区流) | UI-25→UI-26→UI-27/28 | UI-26=`E2E_READY`；其余为`UI_READY_BACKEND_GAP`或尚未形成后端闭环 | 排入Batch 7；测试环境用合成家庭和 fake 外部适配器完整验证发布、审核、互动、举报、申诉和撤回，生产再接真实用户与外部通知 |

## 4. 精选式批次划分（取代V1第8节）

```text
Batch 1 = Platform foundation + Assessment domain (UI-02/UI-03)
          [源仓库NestJS侧证据完整(见MIGRATION_MANIFEST.yaml family_core条目),
           但Python侧实现在AiFamily(本仓库backend/)里从零开始写,不是继续源仓库backend/domains/product_intelligence的半成品]

Batch 2 = SERVICE预约子链(TeacherProfile/ProviderProfile/BookingRequest/ServiceRecord)
          [从V1 Batch 5提前, 理由见第3节, disposition=MIGRATE]

Batch 3 = Family/Relationship/Consent核心聚合(family-core-integration.e2e-spec.ts为验收口径)
          [对应V1 Batch 2的子集, disposition=REIMPLEMENT, 平台内核原语(ActorContext等)在此批次一并建立]

Batch 4 = GrowthIntent/GrowthPlan + GROWTH允许的回顾与成果路径
          [对应V1 Batch 2剩余部分, disposition=REIMPLEMENT]

Batch 5 = Principal/Conversation/Human Handoff
          [维持V1 Batch 3, disposition=MIGRATE, 但AttemptRecordingGateway等fail-closed机制必须先于业务逻辑迁移]

Batch 6 = 21-Day Program + COMMERCE闭环（建设验收项：清理UI-17硬编码积分/落实家长端商业权限规则）
          [合并V1 Batch 4与部分Batch 6, disposition=MIGRATE；测试环境完整跑业务流程，生产再接真实数据与支付适配器]

Batch 7 = COMMUNITY闭环 + Organization/Teacher(B2B2C, 沿用V1.1原文FGCN设计, disposition=REIMPLEMENT]
          [对应V1 Batch 5剩余+Batch 6剩余]

Batch 8 = 收尾: 完成允许的GROWTH路径 cutover，并固化禁止行为的拒绝与审计路径
          [不是"全部NestJS删除"这一单一目标, 而是"所有disposition=MIGRATE/REIMPLEMENT的域已完成cutover"这个状态达成后, 才评估NestJS删除范围——删除范围=已迁移域, 不是无条件删除全部]
```

**与V1第8节最大的结构差异**：V1的Batch 8是固定目标("删除全部NestJS")；本计划的Batch 8是条件性的("删除范围取决于前7批实际迁移了什么")。GROWTH中的禁止正向行为不迁移为业务能力，允许的私有回顾、证据绑定成果和经同意分享必须迁移并通过等价测试；具体外部数据源和适配器可以在生产准入阶段切换。

## 5. 明确不进入本计划施工范围的代码（disposition=ARCHIVE/DELETE，直接列出，不留歧义）

- `dev-platform-surfaces.service.ts` / `dev-core-growth.service.ts`：ARCHIVE。自述`SYNTHETIC_DEV_ONLY`，但注意——这两个服务当前被`apps/mobile`9+个真实屏幕(UI-10/11/12/22/23/25/27/28/29)消费，**下线前必须先确认这些屏幕的数据来源替代方案**，不是可以直接删的死代码，是"合成数据服务+真实消费者"的组合，需要产品侧对这些屏幕的最终去向表态（这批屏幕大概率落在第3节的GROWTH/COMMUNITY闭环，与GATE_BOUNDARY页面的处理一并决定）。
- `apps/api/src/modules/family/../waf/waf-domain.service.ts`：DELETE。纯内存Map，零路由引用，唯一消费者是自己的spec文件。
- `apps/ai-runtime`：DELETE(如果找不到人能解释源码删除的原因)。git从未跟踪，源码已从磁盘删除只剩`.pyc`。
- `apps/fes-api`：ARCHIVE。声明Nest依赖却无`@Module`/`NestFactory`，从未真正监听端口。
- `apps/consumer-web`/`apps/ops-web`：DELETE。目录内只有node_modules，零源码。
- `apps/web/src/case-access-client.spec.js`：DELETE。与同目录`.spec.ts`逐字节相同的重复文件。
- `legacy-system/`(FELS)全部运行时代码：ARCHIVE。仅`contracts/src/index.ts`的RETIRE语义表和`flm-anti-corruption.spec.ts`按CONTRACT_ONLY处理(已内嵌进AiFamily审计的宪章R9,此处同样适用)。
- `orchestration/llm-gateway/family-llm-gateway.service.ts`：REVIEW_REQUIRED，且**Batch 3/5迁移Principal/Orchestration时不得重复此违规**——该文件内部裸`new OpenAICompatibleAiGateway`绕过网关，违反自身声明的`AI_GATEWAY_POLICY.business_module_direct_provider_call='forbidden'`，Python侧的ai-runtime隔离规则(第0节保留清单)正是为了防止同类问题在新架构里再次出现。

## 6. 初始 Disposition Registry（供施工前登记，详细版另建`governance/PYTHON_MIGRATION_DISPOSITION_REGISTRY.yaml`）

| 能力 | Disposition | 证据 |
|---|---|---|
| auth/identity | MIGRATE | 1546行,真实Postgres(identity_sessions等),仅StubOtpSender需替换 |
| family core | REIMPLEMENT | 2293行核心服务,60+路由,e2e覆盖完整,但要建平台内核原语(现状=0) |
| orchestration core | MIGRATE | 5519行,明确设计为不写Growth权威表 |
| orchestration/llm-gateway | REVIEW_REQUIRED | 违反自身AI_GATEWAY_POLICY,见第5节 |
| principal core | MIGRATE | 2337行,真实Postgres,DI工厂fail-closed |
| principal/*.livecheck.ts | TEST_ORACLE(非业务代码) | 命名规避CI收集,真实外部调用手动烟雾测试 |
| backend/domains/product_intelligence(Python) | MIGRATE,前置补测试 | 唯一有tests的Python域,但路由未挂载,仅SQLite无Postgres集成测试 |
| backend/domains/membership(Python) | REVIEW_REQUIRED,阻塞 | 2627行最大域但零测试,FORBIDDEN_TIER_FIELD_TOKENS的guardrail test不存在 |
| backend/domains/market_intelligence/product_strategy/growth_plan(Python) | ARCHIVE | 均为空壳(52-159行),无测试无真实持久化 |
| waf-domain.service | DELETE | 死代码,见第5节 |
| dev-platform-surfaces/dev-core-growth | ARCHIVE,需先决定消费方 | 见第5节 |
| database/migrations(58个SQL) | MIGRATE(Alembic baseline) | 唯一权威schema来源,但4组文件名重号(0022/0023/0024/0053)须先线性化 |
| apps/mobile(前端) | 不属于Python迁移范围 | TypeScript保留,34UI真实状态见第3节决定各闭环排期 |

## 7. 验收标准（沿用V1第9节的严格性，应用到每个Batch而不只是Batch 1）

每个Batch完成时必须能回答：

1. 该Batch范围内所有disposition=MIGRATE/REIMPLEMENT的能力，NestJS对应路径是否已停止注册。
2. 是否存在双写——如有，视为该Batch未完成，不得进入下一Batch。
3. AI Runtime产出是否仍然只是Draft/Hypothesis，未直写canonical状态。
4. 该Batch是否有对应的Python验收测试通过（不接受"文档声称测试存在但磁盘找不到"这类membership域的既往问题重演）。
5. 该Batch涉及的disposition=DELETE/ARCHIVE范围是否已经过人工二次确认（尤其是dev-platform-surfaces/dev-core-growth这类"合成但被真实消费"的边界情况）。

完成后：STOP等待架构复核，不得连续启动下一Batch。

## 8. 待人类裁决的开放项

- GROWTH闭环中允许路径的数据来源、分享范围和 Outcome 证据契约仍需细化；跨家庭排名、家庭总分和无依据效果断言保持禁止。该细化不阻塞测试环境建设，测试环境应先以合成数据完成完整流程和拒绝路径。
- COMMUNITY闭环的投入时机——V2第0.1节"家庭与家庭的关系"定位认为这条线有长期价值但当前证据不足，需要项目负责人明确是否在Batch 7之前就开始投入调研（即使暂不写代码）。
- `backend/domains/membership`的REVIEW_REQUIRED状态——建议的解锁路径是先补齐`FORBIDDEN_TIER_FIELD_TOKENS`的guardrail test，但这个工作量是否现在就投入、还是等Batch 6临近再做，需要排期裁决。
