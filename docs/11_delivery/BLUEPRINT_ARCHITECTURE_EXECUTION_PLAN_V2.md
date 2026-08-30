---
id: DEL-ARCH-EXEC-002
title: Family 新蓝图五层架构执行计划 V2
type: delivery-architecture-plan
status: draft
version: 0.1
owner: project-assistant
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: null
---

# Family 新蓝图五层架构执行计划 V2

> 本计划把 `FAMILY_GROWTH_PLATFORM_MASTER_DESIGN_V1`、`ARCHITECTURE_ALIGNMENT_CHANGELOG_V2` 和
> 当前五层架构转成可执行的领域纵切片。它不是新的业务真相；所有“目标/规格/计划”必须先经过
> `SYSTEM_MANIFEST`、ADR、Registry 和 owner sign-off 才能成为 canonical。当前开发、测试、生产的
> 功能/流程/权限/错误码/审计/Human Gate/删除能力必须同构，只能替换数据集和外部适配器。

## 0. 使用方式和证据分区

每个执行单元都必须同时维护四个分区，避免把设计表当成已完成能力：

| 分区 | 含义 | 允许的证据 |
|---|---|---|
| `Current Truth` | 当前仓库确实可调用的能力 | tracked 代码、OpenAPI、Registry、迁移、可重复测试和 commit |
| `Specification` | 已对齐但尚未承诺交付的业务/架构合同 | 蓝图、流程、对象/表/关系、API/事件合同、ADR 草案 |
| `Planned` | 有 owner、依赖和退出条件的下一切片 | Sprint 工单、文件边界、测试命令、发布闸门 |
| `Evidence` | 本轮实际命令、版本、数据集、失败和缺口 | 新鲜 stdout、Fresh Postgres、HTTP/TestClient、Web/mobile 报告 |

### 0.1 当前新鲜证据（2026-08-30）

- Architecture：`uv run pytest tests/architecture -q` = 109 passed、1 skipped、1 failed；Ruff debt ratchet 失败。
- Ruff：`uv run ruff check . --output-format concise` = 3 errors（1 E501、2 I001）。
- Alembic：HEAD 仅追踪 `0001..0010`；工作树存在未追踪 `0011..0029`，Alembic 单头为 `0029`。Docker healthy 下真实 PG `test_full_chain_up_0016_down_and_rebuild` 运行 154s，`1 failed`：`0016→0025` 升降通过，但 `0025→0026` 在写入 `0026_experience_outbox_delivery_attempts`（40 chars）时触发 `alembic_version.version_num VARCHAR(32)` `StringDataRightTruncationError`；`0027`（35）与 `0029`（39）同类风险。结构测试 FULL_CHAIN 仍旧只覆盖到 `0023`，不能证明 `0024..0029`。DATA-01 保持 BLOCKED。
- FGCN：`31c95cb` 补质量重做 replay 契约；本轮无 PG 执行 `uv run pytest tests/domains/service/fgcn -q` = 133 passed/3 skipped（真实 PG 用例因未设 URL 跳过）；历史 Fresh Postgres 113 passed 证据仍不能替代真实 production composition/worker/outbox/audit。
- Journey/growth：`VS-GROWTH-01` HTTP/PG seam（`78fff77`、`520e2ed`、`e5f7c41`、`c60729b`、`090976e`）独占测试 11 passed/1 warning；`090976e` 将 PG audit/outbox event name 对齐 canonical `AssessmentSignalAccepted`。本轮全 journey `uv run pytest tests/domains/journey -q` = 75 passed/15 skipped（未设 PG URL）。路由未挂载 `family_api`，`production_ready=False`，Hypothesis/Intent/Action/Review 仍未 durable；仍缺真实 HTTP/PG composition、常驻 worker、identity/consent sink。
- Web：`766c164` 的 `clientFactory` 定向验收通过；但生产 build 缺 `index.html`、lint 未配置且未进入默认检查，后端 401/403/tenant/consent smoke 未闭合，CLIENT-01 仍 BLOCKED。
- Service P1.1：`d9a130b` 隔离 PostgreSQL 测试 95 passed；共享库迁移仍漂移，不能据此宣称主线或生产完成。
- AI experience/evaluation/agent：定向契约测试通过，但 Model Gateway/Principal/Memory/Deletion/Release Gate 尚非生产接线。

这些数字只说明某次测试环境的证据，不代表生产能力；下一轮必须重新运行，不得复用缓存。

## 1. Primary Contradiction 与治理前置

### 1.1 主要矛盾

当前存在三类不能被代码“猜解”的矛盾：

1. 新蓝图（V2/V3/CORE/FAMILY_NEEDS/IPD/AI Deep Design/Master Design）均标注
   `draft/canonical:false`，且未完全登记在 `SYSTEM_MANIFEST`，不能替换 `CURRENT_*` 真相；
2. `GENERATIVE_SYSTEM_ARCHITECTURE` 记录“主要矛盾没有一手来源”和旧 FGCN“零代码”的历史，当前代码已出现 FGCN/AI 契约但并不等于生产交付；
3. HEAD 仅追踪 `0001..0010`，工作树 `0011..0029` 均未登记/未审批；Docker 真实 PG 在 `0025→0026` 因 `alembic_version` 32 字符限制失败，结构 FULL_CHAIN 测试仍旧于 `0024..0029`。文档、ORM、迁移、对象清单和真实数据库不一致，DATA-01 必须 BLOCKED。
4. 场景编号出现语义冲突：`BUSINESS_SCENARIO_CLOSURE_CATALOG` 的 canonical S01 是“内容/直播/活动触达与家庭进入”，
   而 `b37b1b6` 曾将 S-01 用作“assessment signal→家庭确认→Action”。现裁决将后者改名为独立交付切片
   `VS-GROWTH-01`，明确横跨 canonical S01+S04+S05+S07；在 ADR/场景目录更新前，不得让 API/数据/测试出现两套 canonical S01。

### 1.2 ADR/Manifest 前置

在任何新域或新表进入实现前必须完成：

- `ADR`：确定 B1-B5/X0/Principal 边界、L0-L5 编号、唯一 writer、事实与 Draft 边界、Need OS、IPD、全球 cell、环境等价、删除与评测准入；
- `DOCUMENTATION_MAP/SYSTEM_MANIFEST`：确定 supersedes/canonical 唯一真相；
- `DOMAIN_REGISTRY`、`MIGRATION_MANIFEST`、AI/Capability/Use Case Registry：登记 owner、路径、状态、版本和迁移 disposition；
- OpenAPI operationId、事件 envelope、对象/表/关系、审计/outbox、错误码和正反向 contract tests；
- Fresh Postgres up/down/up、HTTP/TestClient、删除/恢复、并发/replay 和三环境 parity 证据。

未知 migration head、未登记能力、没有 owner 的“完成”声明一律 `BLOCKED`；不允许通过抬高基线、skip、fixture 或截图关闭。

## 2. 跨域不变量和流程分级

### 2.1 L0-L5 统一编号

```text
L0 价值流 VS-01..VS-05
  L1 端到端流程 P01..P06
    L2 家庭/运营场景 S01..S24、O01..O14
      L3 子流程（如 P02.4 AI 助手与人工升级）
        L4 Principal/Trust 横切节点 PR-N01..PR-N10、X0-N01..N06
          L5 API / Command / Event / Job / Human Task / Projection
```

每个 L4/L5 节点必须给出输入、活动、输出、业务规则、成功/拒绝/暂停/撤回/删除/超时/重放/人工接管、
唯一 writer、对象/表、operationId、事件和测试。Principal 和 X0 只能编排/提案，不能成为 B1-B5 事实 writer。

### 2.2 贯穿字段和错误

业务、AI、事件对象都应具备不可变 `id`、`tenant_id`、`region_id`、适用时的 `family_id/subject_id`、
`purpose`、`consent_ref`、`data_class`、`locale`、`provenance_ref`、时间戳、删除状态/receipt 和 audit correlation。
前端的 `familyId` 仅是路由提示，不可信任；身份、租户、家庭、主体和同意由 trusted `ActorContext`/`ConsentResolver` 解析。

统一错误语义：无/无效凭证=401 + `WWW-Authenticate`；已认证但 tenant/family scope 不符=403；同意撤回/用途不符=403 `CONSENT_REQUIRED`；未知 capability/model/schema/migration=fail-closed；任何环境不能用 dev auth 替代。

### 2.3 AI 事实边界

AI 只允许产生 `Perspective`、`Draft`、`Recommendation`、`ActionProposal`、`HumanTask`、`EvalReport`。
业务域的 Named Action（家庭确认、Outcome 确认、ServiceCase、Delivery、Order/Payment、Quality/Contribution）
才可写权威事实。AI 不得写家庭总分、排名、儿童商业画像、疗效保证或自动续费/营销。

## 3. B1 Family Growth OS 执行单元

### 3.1 四区记录

- **Current Truth**：assessment 有测评/证据纵切片；journey/growth 有状态机、Outcome/Annual/Renewal 契约；FGCN admission 已增加 entry evidence/provenance。
- **Specification**：`assessment → AI evidence interpretation → family confirmation → GrowthIntent → 21-day action → 90-day outcome → annual/renewal → NextNeed`；S01-S09 属 B1，X0/Principal 嵌入。
- **Planned**：唯一业务主线先收敛为 `VS-GROWTH-01`（横跨 canonical S01+S04+S05+S07，对应 `UI-03→UI-05→UI-09`）：assessment signal→Perspective/Hypothesis draft→人类确认/驳回→GrowthIntent/ActionTask→canonical outcome loop；随后再接 S06/S08/S09。
- **Evidence**：`b37b1b6` 的物理文件仍为 `s01_vertical_slice.py`，但业务交付标识统一为 `VS-GROWTH-01`；随后 `78fff77` 新增独立 HTTP/PG seam，`520e2ed` 修 replay hash，`e5f7c41` 补事务 rollback，`c60729b` 强化 consent subject-family binding，`090976e` 将 PG audit/outbox event name 对齐 canonical `AssessmentSignalAccepted`。独占测试 11 passed/1 warning，本轮全 journey 75 passed/15 skipped（PG URL 未设）；clean snapshot 仍缺共享 `journey/domain/errors.py`（被多模块引用，owner 未定）。路由未挂 `family_api`，`production_ready=False`，Hypothesis/Intent/Action/Review 仍未 durable，且 legacy `audit_logs/outbox_events` 尚未统一 canonical platform ledger。状态仍 `CONTRACTED/PARTIAL`，所有提交虽在分支历史，未通过真实 PG/HTTP/构建/主线合入闸门，不能写成生产完成。

### 3.2 L0-L5 流程

| 层级 | 过程和场景 | 输入→活动→输出/规则 |
|---|---|---|
| L0 | VS-01 家庭看见需要并持续成长 | 触达/家庭边界/同意→成长证据→行动与结果；不以分数/排名衡量 |
| L1 | P01 评估理解、P02 计划行动、P03 复盘续期 | 每个 P 共享 Actor/Tenant/Consent/Context；失败可暂停/重试/人工接管 |
| L2 | S01-S04 进入、测评、假设、意图；S05-S09 计划、今日行动、21/90 复盘、结果/年度 | `AssessmentEvidence`→AI `Perspective/Hypothesis Draft`→家庭确认→`GrowthIntent/Plan`→`ActionTask/Record`→`OutcomeRecord`（仅家庭确认）→`NextNeed` |
| L3 | P02.1 今日行动、P02.2 提醒/跳过、P02.3 ChallengeReview、P02.4 AI/人工升级 | 缺失日显式记录；重复 operationId 必须幂等；未确认/撤回不可写 Outcome |
| L4 | PR-N01~N10 + X0-N01~N06 | 身份/同意→冻结 Context→Safety→路由→知识引用→Draft→Schema/Provenance→用户/人工 gate→Named Action |
| L5 | `/assessment/*`、`/journeys/*`、`/outcomes/*`、`RecordActionFact`、`CloseChallenge`、事件/worker/projection | 由 B1 application 唯一写事实；Principal/AI 只发命令或提案，不直接 repository 写入 |

### 3.3 数据与应用绑定

| 数据对象（规格） | 表/投影建议 | 关系和唯一 writer | 应用/API/事件/作业 |
|---|---|---|---|
| Assessment/Evidence/InterpretationDraft | `assessment*`、`evidence*` | Assessment→Evidence→Perspective；AI draft 不写事实 | Assessment API；`AssessmentSubmitted`；interpretation worker |
| GrowthIntent/JourneyPlan | `growth_intents`、`journey_plans` | 家庭确认后由 GrowthIntent command 写入 | Journey API；`GrowthIntentConfirmed` |
| ActionTask/ActionRecord/ChallengeReview | `growth_actions`、`action_records`、`challenge_reviews` | Action command 是唯一 writer；同 tenant/family/intent 幂等 | `/journeys/{id}/actions`；reminder/timeout/DLQ worker |
| OutcomeRecord/FamilyStory/AnnualReview/Renewal | `outcomes`、`stories`、`annual_reviews`、`renewals` | Outcome 只接受人类/家庭确认；共享 story 需 consent | `/outcomes/*`；`OutcomeConfirmed`、`AnnualReviewed` |
| NextNeed/Feedback | `next_needs`、`feedback` | 由确认结果和反馈投影生成，不以推荐点击替代 | Feedback API；`NextNeedDetected` |

### 3.4 AI、工具和闸门

- profiles：`family_understanding`、`growth_reasoning`、`growth_planning`、`action_coaching`、`relationship_coaching`、`delivery_reflection`；
- skills：解释测评、形成假设、拆解小行动、复盘提问、沟通改写；tools：只读 Context/Knowledge、`RecordActionFact`、`CloseChallenge` 命令 port；
- gates：家庭/监护人确认、敏感主题人工升级、Outcome/Story/Recommendation consent；AI 不能确认自己生成的结果。

AI 不是 FGCN 之后才加入的独立阶段：`VS-GROWTH-01` 第一阶段就必须由 Principal/Model Gateway 服务
“内容/问题表达→Perspective/Hypothesis/Draft→家庭确认”。产品工厂、知识库和多 Agent
只以这条主线的输入/输出、来源、同意和 Human Gate 验收；任何 AI 结果都不得越过 Named Action 直写事实。

### 3.5 B1 退出验收和依赖

```text
uv run pytest tests/domains/journey -q
uv run pytest tests/domains/journey/test_fastapi_postgres_e2e.py -q
uv run pytest tests/apps/family_api/test_journey_onboarding_mount.py tests/apps/family_api/test_production_experience_wiring.py -q
```

退出条件：Fresh PG up/down/up、HTTP 401/403/CONSENT_REQUIRED、跨租户/撤回/删除/replay/timeout/DLQ、审计/outbox、
S05-S09 UI e2e 和中英文 locale 均通过。依赖 P0 ENV-01、DB-01、Principal/Context durable；未满足时只进测试分支 `PARTIAL`。

## 4. B2 FGCN Service Network 执行单元

### 4.1 四区记录

- **Current Truth**：FGCN admission、Human Gate、Named Action、assignment、delivery/quality/contribution contracts 有实现和 113 个 Fresh PG 测试通过。
- **Specification**：FGCN 不是 `VS-GROWTH-01` 之前的独立入口，而是“问题/授权→内容/AI理解/家庭确认→Action/Review”之后的必要服务路径：家庭需要→ServiceCase→蓝图/任务→资源匹配与授权→交付留痕→质量验收→贡献凭证；一案一管家、一任务一责任人、未验收不贡献。
- **Planned**：`VS-GROWTH-01` HTTP+PG+outbox 稳定后再接常驻 durable worker/outbox、容量原子预留、争议/退款/补偿、真实 provider/identity/tenant/consent composition；先补 replay/locale/canonical dependency evidence。
- **Evidence**：当前 reviewer/worker/action context 有 RuntimeError 默认；one-shot worker、双事务 crash/retry、replay 状态和多语言校验仍有缺口，生产 `NO-GO`。113 PG tests 只能证明契约，不证明主线接线。

### 4.2 L0-L5 流程

| 层级 | 过程和场景 | 输入→活动→输出/规则 |
|---|---|---|
| L0 | VS-02 社会资源高质量交付 | 已确认需要→合资格供给→可审计履约与质量→贡献/结算 |
| L1 | P04 服务发现与匹配、P05 案件交付与质量 | 供给准入和履约状态必须可回放；资源不足返回 `RESOURCE_GAP` |
| L2 | S10-S14 专家/机构匹配、预约、交付、质量、争议 | 家庭/租户/locale/consent scope→provider capability→case/task→delivery/verification→quality/dispute |
| L3 | admission、blueprint freeze、assignment、delivery、verification、appeal | 每一步都有 human gate、超时、取消、补偿、DLQ；capacity reservation 必须原子 |
| L4 | PR-N02/N03/N05/N08/N09 | 目的化同意/最小上下文→服务匹配 draft→人工/家庭采纳→Named ServiceCase/Task |
| L5 | FGCN commands、`TaskAssignment`、`DeliveryReceipt`、`QualityDecision`、worker/outbox | Service Application 唯一写 case/task/delivery/quality；贡献 ledger 只消费已验收事件 |

### 4.3 数据与应用绑定

`Provider/Capability/Offering/Slot/ServiceCase/TaskAssignment/DeliveryReceipt/QualityDecision/Contribution/AllocationStatement`
分别对应 provider、供给、案件、任务、交付、质量和贡献表/投影；关系为
`Need→ServiceCase→Task→Delivery→Verification→Quality→Contribution`。应用边界为 Service/FGCN API、匹配与质量 worker、
审计/outbox；不可让 AI、commerce 或 loyalty 直接创建 ServiceCase。AI profiles 为 `service_matching`、`resource_coordinator`、
`service_guardian`，工具仅使用 capability/availability 查询和命令 port，供给准入、派单、验收、结算必须人工闸门。

### 4.4 验收和依赖

```text
AIFAMILY_TEST_DATABASE_URL=postgresql+asyncpg://... uv run pytest tests/domains/service/fgcn -q
uv run pytest tests/domains/service/fgcn tests/domains/journey -q
uv run pytest tests/apps/family_api/test_service_loop_dev_wiring.py -q
```

必须补容量并发、同 operationId 重放、assignment 后完成/撤回重放、中文/多 locale、跨 tenant/撤回 consent、worker restart/DLQ、
Audit/Outbox/PG transaction 和真实 HTTP。依赖 B1 confirmed intent、DB-01、ENV-01；未满足只能 `PARTIAL`。

## 5. B3 Growth & Commercial Flywheel 执行单元

### 5.1 四区记录

- **Current Truth**：移动端有 34 UI 基线；commerce/membership/loyalty/product catalog 有局部 WIP 与测试；Web client 已有 auth/session/locale 注入候选。
- **Specification**：内容/直播触达→家庭需要/行动→E3 明确服务需要→透明 offer/order/payment/entitlement→交付/质量→续购/推荐；B2C 是根，B2B2C 是渠道放大器，C2C 是网络层。
- **Planned**：四本账和经济事实 durable 化，完成取消/退款/争议/过期/撤回/删除/审计；商业动作一律家长显式确认。当前冻结只暂停真实运营、开放流量、商业实验和范围扩张，不能删掉未来生产形状的订单/支付/权益/退款/结算状态机、权限、Consent、tenant、幂等、Audit/Outbox、回滚、重启和人工审核契约。
- **Evidence**：会员/支付/贡献和直播/内容仍 WIP/DESIGN；不得用家庭分数、排名、伪造社会证明、自动续费或未成年人画像驱动商业化。

### 5.2 L0-L5 流程

| 层级 | 过程和场景 | 输入→活动→输出/规则 |
|---|---|---|
| L0 | VS-03 真实帮助形成透明经济价值 | 已确认 need/服务结果→offer→订单/权益→履约质量→续购；商业不能早于 E3 |
| L1 | P03 内容/活动增长、P06 订单/会员/权益 | 内容是入口不是事实；所有广告/营销用途有 purpose/consent |
| L2 | S15-S18 内容/直播/产品/会员/邀请/续购 | E0-E2 只提供安全体验和行动；E3 后由家长确认；取消/退款/争议可回放 |
| L3 | content publish、live session、offer select、order pay、entitlement reserve/consume、refund/renewal | 四账独立，产品账不得替交付账，贡献账不得绕质量账 |
| L4 | X0-N01~N06、PR-N05~N10 | CandidateSet/ActionProposal→家庭选择→商业 Human Gate→Named Order/Entitlement |
| L5 | `/content/*`、`/offers/*`、`/orders/*`、`/memberships/*`、`/entitlements/*`、事件/对账作业 | Commerce/Membership 是唯一 writer；Experience/Principal 只投影/推荐 |

### 5.3 数据与四本账

| 账 | 对象/表 | 约束 |
|---|---|---|
| 产品账 | Offer、Order、Payment、Entitlement | 回答卖了什么/谁付款/获得什么；退款和过期可回放 |
| 交付账 | ServiceCase、Task、Delivery、Verification | 只记录已授权服务和验收；不由产品账推断交付 |
| 贡献账 | Contribution、AllocationStatement | 仅消费已验证任务；不得变家庭成长分数或家庭分红 |
| 质量账 | Complaint、Rework、Refund、QualityReserve、Release | 质量/争议在贡献或结算前决定释放/保留 |

### 5.4 AI、验收和依赖

profiles：`experience_curator`（受控推荐）、`service_product_architect`（内部设计草案）、`operations_insight`；
skills：内容到行动、offer 解释、成本/SLA 说明；tools：只读 catalog/availability/entitlement，订单/支付/续购都进家长 Human Gate。

```text
cd frontend/mobile; pnpm test -- --run
cd frontend/web; pnpm test -- --run; pnpm typecheck
uv run pytest tests/domains/membership tests/domains/loyalty_points tests/apps/family_api -q
```

退出条件：四账独立 PG schema/唯一 writer、订单/退款/争议/删除/审计/幂等，E0-E4 频控与 consent，Web/mobile/API parity，
不含总分/排名/儿童营销。依赖 B1/B2 Outcome/Delivery、ENV-01、DB-01 和唯一 `AiReleaseGate`。

## 6. B4 Family Trust & Community 执行单元

### 6.1 四区记录

- **Current Truth**：mobile community/share UI 和数据权利/consent contracts 有局部测试；家庭关系和记忆设计文件已存在。
- **Specification**：家庭成员关系→私有回顾→显式分享/组队→社区互助→投诉/撤回/删除；C2C 不等同于社会排名或私域导流。
- **Planned**：可信分享、可见性、内容审核、投诉/申诉、未成年人保护、删除 cascade、关系记忆读写边界。
- **Evidence**：运营回传显示可信分享/组队、社区治理、主动回访未完成；不能以静态 UI 代替安全闭环。

### 6.2 L0-L5 流程和数据

L0 VS-04 家庭关系与社会信任；L1 P03/P06 社区和权益；L2 S19-S20 社区/分享/关系；L3 `create→moderate→share→revoke→complain→delete`；
L4 PR-N02/N03/N08/N09 + X0 trust/frequency；L5 `/families/{id}/sharing`、`/community/*`、`Complaint`、`DataSubjectRequest` 命令和删除 worker。

核心对象为 `FamilyMember/Relationship/VisibilityGrant/ShareGrant/CommunityPost/GroupActivity/ModerationCase/Complaint/
Appeal/DataSubjectRequest/DeletionReceipt`，关系必须带 tenant/family/subject/consent/provenance。AI profile 为
`relationship_coaching`、`safety_moderator`，只能生成沟通/审核草案；公开分享、儿童可见性、申诉裁决和删除必须人工/家长 gate。

### 6.3 验收和依赖

```text
uv run pytest tests/platform/consent tests/intelligence/context_engine -q
cd frontend/mobile; pnpm test -- --run
uv run pytest tests/apps/family_api -k 'share or complaint or deletion' -q
```

必须证明撤回后不能读取/重放、跨租户 403、儿童默认非商业、删除 receipt 覆盖媒体/向量/缓存/审计投影、社区投诉和人工接管可恢复。
依赖 ENV-01、AAIR durable deletion、B3 内容治理；未完成时 C2C 只保持 `DESIGN/PARTIAL`。

## 7. B5 Platform Evolution & Operations 执行单元

### 7.1 四区记录

- **Current Truth**：有产品智能、知识、AI 运行时、Registry、Telemetry、Evaluation 和部分运营契约；产品工厂 Web/API/PLM 尚未闭合。
- **Specification**：需求/证据→产品/组件/Skill→SolutionBlueprint→模拟/人工 Gate→Pilot→Release/Rollback；运营覆盖 O01-O14、全球 cell 和事故闭环。
- **Planned**：六工作台（Demand Studio、Market Insight、Product Studio、Component/Skill Library、Pilot/Gate Board、PLM Console）及 S21-S24 内容/专家/机构运营。
- **Evidence**：运营只读回传 79 passed/1 skipped/1 warning，Onboarding 35/11 skipped；S21/S24/O13 DESIGN_ONLY，S22/S23/O12/O14 PARTIAL；唯一 skip 为真实 PG WORM。

### 7.2 L0-L5 流程

| 层级 | 过程和场景 | 输入→活动→输出/规则 |
|---|---|---|
| L0 | VS-05 平台能力和供给持续进化 | 家庭需求/服务反馈/质量/成本→证据→产品/策略→受控发布→监控/回滚 |
| L1 | P06 产品工厂、知识治理、运营治理、全球 cell | 发布必须有 G0-G6/审批/回滚；事故和数据权利是业务流程，不是后台脚本 |
| L2 | S21-S24 内容/专家/活动/机构；O01-O14 家庭成功、内容/供给、交易/社区、发布/事故/全球运营 | 每个场景绑定队列、SLA、owner、audit/outbox、人工接管 |
| L3 | DemandFrame、EvidenceCard、ProductPackage、Blueprint compile、Pilot、Release、Incident、SLA、WORM deletion | AI 只生成草案/洞察；发布/准入/事故关闭由人批准 |
| L4 | PR-N05~N10 + X0 frequency/experience quality | route→knowledge/evidence→draft→review→release/rollback；不得把点击/停留当质量 |
| L5 | Product Intelligence/PLM API、Knowledge registry、Ops queue/worker、Audit/Telemetry/Incident jobs | B5 是平台状态 writer；不写 B1 Outcome 或 B3 Order |

### 7.3 数据、应用、AI 和验收

对象/表：`DemandFrame/ResearchTask/EvidenceCard/ProductInitiative/RequirementBaseline/ArchitectureBaseline/
ProductPackage/Component/Skill/BlueprintVersion/CompilerCheck/PilotRun/GateDecision/ReleaseBaseline/KnowledgeSource/
KnowledgeVersion/KnowledgeClaim/OpsCase/SLATimer/Incident/Runbook/RegionCell/Quota`。关系为
`Demand→Evidence→Product→Blueprint→Pilot→Gate→Release→Feedback`，知识为 `Source→Version→Chunk→Claim→Review→Publish→Retrieve→Citation`。

应用模块：Product Intelligence API、six workbenches、Knowledge/Prompt/Schema Registry、AI Release/Operations console、global control plane。
AI profiles：`service_product_architect`、`knowledge_steward`、`operations_insight`；skills 为 evidence synthesis、blueprint compile、cost/SLA/red-team；
tools 仅调用 registry/benchmark/telemetry/read models；G0-G6、质量/安全/法律/家庭代表人工 gate。

```text
uv run pytest tests/intelligence/test_ipd_contracts.py tests/intelligence/evaluation -q
uv run pytest tests/intelligence/observability tests/intelligence/memory -q
uv run pytest tests/architecture/test_application_architecture.py tests/architecture/test_business_scenario_catalog.py -q
```

退出条件：每个 O 场景均有 queue/worker/timeout/DLQ/audit/delete/incident runbook；IPD compiler 12 项检查、PLM release/rollback、知识 citation/version、
全球 region/cell/locale policy、Fresh PG WORM 和真实 ops HTTP。依赖唯一 `AiReleaseGate`、DB-01、ENV-01；未满足不得扩张 Agent 或 migration。

## 8. X0 Experience & Trust 执行单元

### 8.1 四区记录和流程

- **Current Truth**：Experience contracts、curator、feature/experiment、SQL run ledger、multimodal 合同和成就 projection 有局部实现。
- **Specification**：E0 看见→E1 小胜→E2 持续成长→E3 服务需要→E4 经济选择；P0 `N01 ExperienceEvent → N02 CandidateSet → N03 EmotionalResponse → N04 ActionProposal → N05 FeedbackSignal → N06 GrowthProgress`。
- **Planned**：真实推荐/频控/反馈/多模态投影、跨端语义 UI、删除/重放和隐私指标；不增加隐藏 engagement objective。
- **Evidence**：Experience/evaluation 契约测试通过但 synthetic；evaluation 双 gate 和 report registry 未统一，故 `CONTRACTED/PARTIAL`。

数据：`ExperienceEvent/CandidateSet/EmotionalResponse/ActionProposal/FeedbackSignal/GrowthProgress/FeatureSignal/ExperimentAssignment/
AchievementProjection`；表/事件必须引用 source/provenance/tenant/family/locale/consent。应用为 ExperienceApplication、Curation/Frequency、Feedback、Achievement、SQL ledger 和 projection worker。

AI profile `experience_curator` 只产候选/解释/ActionProposal；skill 是 relevance/frequency/safe gamification；tool 为 read-only catalog/context/feature，商业和成长写入必须回 B1/B3 Named Action；人工 gate 负责敏感推荐、儿童内容、商业/分享。

### 8.2 验收和依赖

```text
uv run pytest tests/intelligence/experience tests/intelligence/evaluation -q
uv run pytest tests/intelligence/experience/test_api_contract.py tests/intelligence/experience/test_multimodal_vertical_slice.py -q
```

必须有唯一 `AiReleaseGate`、真实 report registry lookup（case/candidate/version/provenance/tenant/locale/consent）、unknown/revoked/deleted/replay/跨租户负向；
所有成就必须证据绑定且无家庭总分/排名。依赖 AAIR canonical gate、B1 Outcome、B3 E3、Deletion/Observability。

## 9. Principal Experience + AI Orchestration 执行单元

### 9.1 四区记录

- **Current Truth**：`backend/intelligence/principal` 有 contracts/runtime/router 原语；agent_runtime、model_gateway、context_engine、memory、human_gate、knowledge、observability 有局部合同。
- **Specification**：Principal 是跨域控制面，不是第六业务域；家庭端和运营端共享 runtime、Knowledge/Provenance/Evaluation，但 profile/权限不同。
- **Planned**：`PrincipalSessionService/ConsentResolver/ContextBroker/CapabilityRouter/KnowledgeRetriever/ResponseComposer/HumanGate/ActionBridge/FeedbackService` 真实 FastAPI+Postgres composition。
- **Evidence**：Principal API 未正式挂载；生产 identity/consent/tenant/context durable 仍缺；AI production provider 未通过准入，故 `PLANNED/WIP/BLOCKED`。

### 9.2 PR-N01-PR-N10 映射

| 节点 | 输入→活动→输出 | writer/gate |
|---|---|---|
| PR-N01 Intent | actor/tenant/family/entry/purpose→开 session→SessionOpened | PrincipalSession；未知入口拒绝 |
| PR-N02 Identity/Consent | ActorContext/ConsentGrant/年龄→用途/可见性校验→ConsentDecision | ConsentResolver；无授权拒绝 |
| PR-N03 Context | 允许的事实投影→冻结 snapshot→ContextSnapshot | ContextBroker 只读；跨家庭拒绝 |
| PR-N04 Safety | 文本/媒体/主体→风险分类→SafetyPrecheck/HumanTask | Safety gateway；HIGH 风险只能提醒/人工 |
| PR-N05 Route | intent/context→登记 capability/profile→RouteDecision | Capability Router；不按模型名路由 |
| PR-N06 Knowledge | purpose/locale/年龄→已发布 Claim→KnowledgeRefs | Knowledge registry；未知/过期 citation 清空 |
| PR-N07 Generate | Soul/prompt/schema/context→Model Gateway→ModelDraft | AI draft-only；Attempt/Provenance 必须先登记 |
| PR-N08 Review | draft/policy/provenance→schema/safety/引用检查→PrincipalResponse | fail-closed；不可自动成为事实 |
| PR-N09 Human/User Gate | 敏感 draft/商业/服务/分享→家庭或人工审批→Approved/Rejected | HumanGate/Consent；AI 不能自审 |
| PR-N10 Action/Feedback | approved proposal→Named Action→Outcome/Feedback | B1-B5 唯一 writer；Principal 只发 command/读 projection |

### 9.3 数据、应用、AI 验收

对象：`PrincipalSession/ContextSnapshot/SoulVersion/PromptVersion/SchemaVersion/KnowledgeRef/ModelAttempt/AgentRun/ToolCall/
SafetyDecision/HumanTask/Provenance/Feedback`；建议表 `principal_*`、`ai_*`、`knowledge_*`、`human_tasks`、`audit_events`、`outbox`。
应用 API 目标为 `/families/{id}/principal/sessions`、messages、context、action cards/confirm，内部运营 API 不能越权读取家庭事实。

profiles/agents：`principal/family_understanding`、`growth_reasoning`、`growth_planning`、`action_coaching`、`service_matching`、
`service_product_architect`、`knowledge_steward`、`operations_insight`；skills/tools 必须经 Model Gateway、Authorization lease、ToolCall outbox。

```text
uv run pytest tests/apps/family_api/test_production_agent_wiring.py tests/intelligence/agent_runtime tests/intelligence/model_gateway -q
uv run pytest tests/intelligence/context_engine tests/intelligence/memory tests/intelligence/human_gate -q
```

退出条件：三环境同一 route/error/state；真实 actor/tenant/consent/context PG；model unavailable/schema invalid/knowledge revoked/Human Gate/Named Action/删除/replay；
真实 provider 通过 registry、成本、安全、版本和 `AiReleaseGate`。在此以前，Principal 只能标 `CONTRACTED/WIP`。

## 10. 场景全量挂接索引

下表保证 24 个家庭场景和 14 个运营场景不因新增蓝图而丢失；每组仍须在实现工单展开为完整 L4/L5：

| 业务场景 | 业务域 | 流程主链 | 数据/应用主线 | Principal/X0 |
|---|---|---|---|---|
| S01-S04 | B1 | 进入→测评→证据→意图 | Assessment/Evidence/GrowthIntent | PR-N01~08, E0/E1 |
| S05-S09 | B1 | 计划→行动→复盘→Outcome→Annual/Renewal | Journey/Action/Outcome | PR-N03~10, E1/E2 |
| S10-S14 | B2 | 需要→匹配→Case/Task→Delivery→Quality/Dispute | FGCN/Service | PR-N02/03/05/09 |
| S15-S18 | B3 | 内容/直播→E3 need→Offer/Order/Membership→续购 | Content/Commerce/Entitlement | X0 E0-E4, PR-N09 |
| S19-S20 | B4 | 关系→分享/互助→投诉/撤回/删除 | Community/Trust/DSR | X0 trust, PR-N02/09 |
| S21-S24 | B5+B2+B3 | 内容/专家/活动/机构供给与协同 | Content/Provider/Institution/Service | PR-N05~10, E3 |
| O01-O04 | B5+B1 | onboarding→家庭成功→风险→回访 | OpsCase/SLA/Feedback | PR-N03/04/10 |
| O05-O08 | B5+B2+B3 | 内容/供给/产品/服务质量运营 | Evidence/Product/Provider/Quality | service_product_architect/ops_insight |
| O09-O11 | B3+B4 | 交易、会员、社区与贡献运营 | Order/Entitlement/Community/Contribution | X0 E3/E4 |
| O12-O14 | B5+X0 | 指标、发布、事故、全球 cell | Telemetry/Incident/Release/Region | PR-N04/08/09 |

### 10.1 场景原子名称（不可删除，只能补充实现证据）

为防止“范围映射”掩盖漏场景，以下原子编号必须逐一建立 L3/L4/L5 合同（名称和当前判断来自
`BUSINESS_SCENARIO_CLOSURE_CATALOG.md`，不是本计划重新发明）：

```text
S01 内容/直播/活动触达与家庭进入       S02 账户/家庭成员/角色与可见性
S03 测评目录/目的说明与同意             S04 测评执行/提交与证据冻结
S05 假设解读/家庭确认与成长入营         S06 90天计划/确认与阶段复盘
S07 21天行动/今日任务与过程回读         S08 家庭过程报告/成果记录与私有故事
S09 AI助手/提醒/解释与人工升级          S10 陪跑服务/客户服务与服务记录
S11 专家教师供给发现与服务时段          S12 咨询预约/沙龙报名/取消与履约
S13 FGCN案件/任务/资源匹配与验收        S14 质量反馈/投诉/恢复与争议裁决
S15 商品目录/方案详情与购买意向         S16 会员方案/权益激活与年度续购
S17 积分账本/订单资产与权益回读         S18 邀请/同行计划与增长激励
S19 家庭社区内容/审核/互动与撤回        S20 家庭数据权利/删除/留存与安全
S21 运营工作台/质量监控与经营指标       S22 AI Runtime/知识/上下文/评估与学习
S23 机构/城市伙伴合作与供给准入         S24 合作/组织/人才与股权治理

O01 账户/租户/角色与权限运营            O02 内容/测评/计划与任务版本运营
O03 直播/活动/渠道与触达运营            O04 家庭线索/入营与留存运营
O05 工单/队列/SLA与人工升级运营         O06 专家/教师/机构供给运营
O07 预约/履约/改派与质量抽检运营        O08 商品/会员/权益与促销运营
O09 支付/退款/结算与对账运营            O10 社区审核/风控/申诉与处置运营
O11 数据权利/留存/安全与合规运营        O12 AI知识/模型/提示词与评估运营
O13 指标/实验/分群与经营复盘运营        O14 发布/环境一致性/审计与事故运营
```

原子场景的状态不是“有页面就完成”：当前 S04 有可运行测评证据；S01/S05-S12、S15-S20 多为
`PARTIAL/GATE_BOUNDARY`；S13/S14、S21-S24 和 O02/O03/O04/O06/O07/O10/O12/O13/O14 多为
`DESIGN_ONLY/PARTIAL`。每个状态都必须回链到 API、对象/表、唯一 writer、AI/人工 gate 和新鲜测试。

## 11. Sprint 依赖与退出路线

### 11.1 两周（测试环境同构切片）

本轮重新裁决：**Sprint 0 不是普通准备工作，而是六门 P0 发布阻断**。六门全部通过前，
只允许在隔离分支补合同/负向测试，不得扩张 Commerce、C2C、B2B2C、第二套 Agent 或新的
migration head。测试环境必须保留生产同样的路由、权限、状态机、错误码、审计、重试、删除和
人工闸门；仅数据集和外部适配器可以使用 synthetic/sandbox。

| P0 门 | owner 角色 | 明确文件边界 | 依赖 | 正向/反向验收 | 退出证据 |
|---|---|---|---|---|---|
| ENV-01 环境与真实身份 | APLT + 原 `dev_wiring.py` WIP owner | `main.py`、`dev_wiring.py`、production composition、Actor/Session/Consent resolver；不覆盖并发 WIP | ADR-0069、trusted auth port | unset/非法 env fail-closed；无 token→401；跨 tenant→403；撤回→CONSENT_REQUIRED；dev/test/prod route/error parity | 三环境 OpenAPI/404/401/403 TestClient、启动日志和 owner sign-off；当前 unset acceptance 仍 expected-red，BLOCKED |
| DATA-01 迁移与真实 PG | ADOM/ARCH | migrations 0011-0029、ORM、Manifest/ADR、对象清单 | DB-01、Fresh Postgres URL | upgrade→downgrade→upgrade、重启、并发、未知 head 必须 fail；未设 `AIFAMILY_TEST_DATABASE_URL` 的 skip 不算通过 | Docker healthy 真实 PG：`test_full_chain_up_0016_down_and_rebuild` 154s，1 failed；0016→0025 通过，0025→0026 因 `alembic_version VARCHAR(32)` 写入 40 字符 revision 失败；0027/0029 同类；FULL_CHAIN 旧于 0024-0029，BLOCKED |
| IDP-01 tenant/consent/idempotency | Platform/API | `ActorContext`、`ConsentResolver`、tenant scoped `IdempotencyStore`；不得信任 body tenant | ENV-01、DB-01 | 同 key 跨 tenant 不污染；重复 replay 返回同结果；冲突拒绝；撤回/过期/跨主体拒绝 | Fake 与 PG 同契约，401/403/CONSENT_REQUIRED、删除后 replay 负向；当前 platform store 仍 InMemory/未生产接线，BLOCKED |
| LEDGER-01 Audit/Outbox | Platform/AAIR | canonical AuditEvent、Outbox、worker/lease/DLQ/restart；各域只接 port | IDP-01、DB-01 | 命令与 audit/outbox 同事务；crash/retry 不重复；DLQ/补偿/重启可恢复 | PG 事务日志、audit correlation、outbox receipt、worker restart；各切片局部证据，跨域组合缺，BLOCKED |
| AI-01 唯一准入与 Principal 边界 | AAIR/GOV | `AiReleaseGate`、EvalReport registry、Principal/Context/Memory/Delete；冻结第二 gate | ENV-01、IDP-01、DB-01 | unknown/revoked/deleted/mismatch benchmark、跨 tenant/locale 拒绝；AI 只能 Draft/Proposal，Named Action 才写事实 | 单一 gate architecture test、registry/version/provenance/consent 证据；当前双 gate/报告 lookup 缺，BLOCKED |
| CLIENT-01 Web/mobile 生产安全 | AFE/APLT | Web `clientFactory`、mobile contracts、OpenAPI error/locale/session；不改后端 WIP | ENV-01、IDP-01 | `DEV:false + fake` 必须 fail-closed；token/session/locale/idempotency 注入；五端错误/重放一致；build/lint/typecheck | `766c164` clientFactory 定向验收通过；生产 build 缺 `index.html`，lint 未配置且未进默认检查，mobile 全量 5 failures→0、OpenAPI parity 未闭合，BLOCKED |

**真实 PG URL 缺失是硬阻断**：任何 `skip`、`create_all`、同进程 disposable probe 或未设置
`AIFAMILY_TEST_DATABASE_URL` 的成功都只能记作 `CONTRACTED`，不得关闭 DATA-01/LEDGER-01。
**远端 push 443 失败也是交付阻断证据**：提交未出现在 remote 前不能称“已推送”，必须记录 local SHA、
remote SHA、命令和 exact error；本轮复测前远端曾为 `bd59c91`，随后远端已出现
`9eeb19a`、`b37b1b6` 和 `e0c16d0` 均已进入分支历史；本计划证据快照基线为 `82f038c`，其后
`7355ca5` 更新了本计划。SHA 进入分支只证明提交可追踪，
不等于生产完成：`b37b1b6` 仍是内存 CONTRACTED/PARTIAL，需 HTTP+PG+outbox+deletion/replay；
`e0c16d0` 仅为场景计划。任何未出现在 remote 的 SHA 仍保持 `LOCAL_ONLY`，必须记录 exact error。

六门 P0 必须绑定同一条业务验收，而不是只做技术绿灯：一个真实（测试数据可合成）家庭由家长进入，
完成身份/目的化授权，确认一个家庭问题和一个主结果，收到一个可执行的 ActionProposal，家庭确认后
记录一条 Action/Review；否则即便单项 API 或 migration 通过，Sprint 0 仍为 `NOT_DONE`。该业务链
固定为 `问题/授权 → 内容/AI理解/家庭确认 → Action/Review →（必要时）Service/FGCN → 质量/经营门`，
P0 技术门是每个节点的放行条件，不是业务终点。

1. **P0 ENV-01（APLT + 原 dev_wiring owner）**：unset/非法环境 fail-closed、真实 Actor/Consent/Tenant、三环境 401/403/consent parity；不改冲突 WIP，owner 未明确即 BLOCKED。
2. **P1 DB-01（ADOM）**：0011-0029 ADR/Manifest/ORM/对象清单、Fresh PG up/down/up；Docker 实测 0016→0025 通过、0025→0026 因 revision 长度失败，unknown head=0029 必须 fail，不能 skip；结构 FULL_CHAIN 需升级覆盖 0024-0029。
3. **P1 Principal/Context（AAIR）**：单一 session→consent→snapshot→draft→human gate→Named Action，先使用同构 synthetic provider，不添加第二 runtime；未过 AI-01 只做合同。
4. **P1 `VS-GROWTH-01`（growth + AFE/API）**：唯一业务主线 `UI-03→UI-05→UI-09`，横跨 canonical S01+S04+S05+S07：Assessment signal→Perspective/Hypothesis draft→家庭确认→GrowthIntent/ActionTask→回读/ChallengeReview；`b37b1b6` 仅内存 CONTRACTED/PARTIAL，下一阶段必须 HTTP+PG+outbox+deletion/replay。
5. **P1 FGCN（B2）**：仅在 `VS-GROWTH-01` 已确认 need 后进入 admission→assignment→delivery→quality；先修 replay/locale/dependency evidence，不得抢跑成第二主线。
6. **P1 AFE/Web**：34 UI 语义化、多模态/成就、Web/mobile/OpenAPI token/session/locale/idempotency parity；mobile 5 failures→0，Web lint 闭合；`DEV:false + fake` 必须 fail-closed。

本轮明确**暂缓扩张**：Commerce/支付/会员、C2C 社区、B2B2C 学校/机构、直播商品化、更多
Agent/Skill/Tool、第二个 Gate/Registry。冻结仅针对真实运营、开放流量、商业实验和范围扩张；
上述能力仍必须保留未来生产形状的状态机、权限、Consent、tenant、幂等、Audit/Outbox、回滚、
重启、人工审核以及支付/退款/结算契约。待六门 P0 关闭、`VS-GROWTH-01` HTTP+PG 闭环和唯一写入者稳定后按依赖解冻。

两周退出条件：architecture/Ruff/Fresh PG/HTTP/相关 mobile/Web/删除/审计全部可重复；每个切片标记 `CONTRACTED/PARTIAL`，没有生产升级。

### 11.2 六周（测试环境功能完整）

完成 B1-B5/X0/Principal 的真实 FastAPI+Postgres 状态机（外部 provider 可 sandbox），覆盖 S01-S24/O01-O14 的 success/reject/pause/revoke/delete/replay/timeout/DLQ/compensation，四账、Context/Memory、FGCN、内容/社区/机构/运营均有唯一 writer 和 HTTP/PG evidence。任何场景只完成设计或 fixture 仍标 `DESIGN/PARTIAL`。

### 11.3 九十天（生产候选）

补真实身份、支付、模型/媒体/vector adapters、durable deletion receipts、Audit/Outbox、容量/分片/region failover、四端 parity、IPD/PLM、B2B2C/C2C 运营和事故演练；完成所有 P0/P1、未知 migration、双 gate、Ruff、license/合规、恢复演练，才允许 `PRODUCTION_CANDIDATE`。

## 12. 发布红线、停止扩张和责任

- **D10 质量/商业门（不可省略）**：每个切片必须同时证明家庭获得真实帮助、服务质量和安全可追踪、
  退款/返工/供给成本可对账、商业动作在 E3 后并经家长确认；不得用点击/停留、家庭总分/排名、
  虚假社会证明或合成收入替代结果证据。D10 未通过时，即便技术测试全绿也只能 `PARTIAL`。
- 未完成 ENV-01 不得把 dev/test auth 或默认环境暴露到生产；
- 未完成 DB-01 不得合并新的 migration head；
- 未完成唯一 `AiReleaseGate`/EvalReport registry 不得新增评测/准入层；
- 不得扩张第二套 Principal、Model Gateway、ServiceCase writer、ledger 或 Node/Express 业务路径；
- 不得用家庭总分、排名、儿童带货、虚假社会证明、自动续费/营销替代真实帮助；
- InMemory deletion、deterministic provider、fixture、one-shot worker、设计文档和截图只能作为同构测试替身；
- 任一场景没有 owner、输入/活动/输出/规则/异常、对象/表/关系、API/事件/作业、AI/人工 gate、测试证据，状态就是 `OPEN/PARTIAL`。

项目助理每个工作日做一次代码/Registry/迁移/测试快照；每个切片合并前做五层反向评审并向 owner 发文件级返工意见。没有新鲜证据的“已完成”自动降级，连续两轮不纠偏升级 `NO-GO`。

本文件只新增计划文档，未修改代码、Registry 或其他 Agent WIP；新增设计不得在未完成治理前置时被当作 canonical。
