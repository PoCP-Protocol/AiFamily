---
id: APP-LEDGER-001
title: AiFamily A3-A6 应用实现台账（34 UI、39 流程）
type: delivery-ledger
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# AiFamily A3-A6 应用实现台账

本台账把应用架构落到可核验的实现证据：每一条业务/运营流程必须能定位到
应用模块、Handler 或 Application Service、接口、权威数据对象/表、事件或
投影、测试证据和当前状态。它不把 UI 迁入、路由挂载、fixture 返回或文档
设计当成业务能力完成。

业务真相来自：

- docs/02_business/BUSINESS_ARCHITECTURE.md
- docs/02_business/BUSINESS_SCENARIO_CLOSURE_CATALOG.md
- docs/06_platform/APPLICATION_ARCHITECTURE.md
- docs/07_data/DATA_OBJECT_TABLE_RELATIONSHIP_CATALOG.md
- docs/07_data/MASTER_AND_BUSINESS_DATA_DECOMPOSITION.md

## 1. 状态与证据规则

| 状态 | 可接受证据 | 含义 |
|---|---|---|
| IMPLEMENTED | Handler、端口、事实表、事务事件、成功/拒绝测试，以及可调用运行时接线 | 纵向切片可重复验收 |
| PARTIAL | 至少有部分应用代码或路由，但缺少一个或多个完成条件 | 不能向生产宣称完成 |
| DESIGN_ONLY | 只有业务/应用/数据设计或 UI 基线 | 尚未开始实现 |
| NOT_IMPLEMENTED | 当前没有可调用的应用实现 | 必须建立新的 Handler/端口/路由 |
| BLOCKED | 实现存在，但被身份、数据库、外部适配器或治理前置条件阻断 | 需先解除阻断再验收 |

证据优先级为：可调用 HTTP/应用测试 > 领域/仓储集成测试 > 代码存在 >
路由/OpenAPI 注册 > UI 调用代码 > 设计文档。PostgreSQL 集成测试如果未
提供测试数据库变量，只能证明测试存在，不能替代一次真实执行记录。

## 2. 当前纵向切片结论（S04-S07 + Family Need N0-N1）

| 场景 | 当前判断 | 已具备 | 关键缺口 |
|---|---|---|---|
| S04 测评执行、提交与证据冻结 | IMPLEMENTED（域切片） | AssessmentCommandHandler、Query Handler、SQL/ fake 仓储、幂等、审计/Outbox、UI-02 投影测试 | 生产身份/同意存储接线；UI-02-result 专用投影契约 |
| S05 假设解读、家庭确认与成长入营 | PARTIAL | 确定性解释适配器、UI-03 投影、人工确认写入 growth_intents、决策幂等 | Perspective/Hypothesis 持久化、Onboarding 创建与事件、真实 Model Gateway、风险升级 |
| S06 90 天计划生成、确认与阶段复盘 | PARTIAL | JourneyService、计划/阶段表、优先级确认、创建/确认/复盘路由、事务审计/Outbox | 阶段到期推进、Action 生成、Plan Projection 重建、完整人工复盘和补偿 |
| S07 21 天行动、今日任务与过程回读 | NOT_IMPLEMENTED | 仅有 growth_actions 完成数查询和 Mobile 客户端调用声明 | ActionTask/Record Handler、今日任务/状态/签到路由、提醒 Worker、过程回读、21 天结项 |
| VS-01 Family Need N0-N1 家庭表达与需求捕获 | IMPLEMENTED（首条需求纵切片） | `FamilyNeedApplicationService.capture_signal`、FastAPI `POST /families/{family_id}/needs/signals`、幂等重放、NeedEvent、scope/consent/subject 校验、证据引用 | N1 需求澄清之后的 NeedProfile/SolutionDraft API、真实持久化/同意存储、Principal 需求解释与记忆确认桥接 |

### 2.1 S04 节点实现证据

| 节点 | Handler/Query | 接口 | 权威对象/表 | 事件/审计 | 测试证据 | 状态 |
|---|---|---|---|---|---|---|
| S04-N01 创建会话 | AssessmentCommandHandler.start | POST /families/{family_id}/assessments/sessions | AssessmentSession / family_assessment_sessions | AssessmentSessionStarted；family_assessment_operations | tests/domains/assessment/test_assessment_flow.py；test_sqlalchemy_repository_integration.py | IMPLEMENTED |
| S04-N02 保存回答 | AssessmentCommandHandler.save_response | POST /families/{family_id}/assessments/sessions/{session_id}/responses | AssessmentResponse / family_assessment_responses | AssessmentResponseSaved；audit/outbox 同事务 | test_assessment_flow.py；test_transactional_outbox_invariant.py | IMPLEMENTED |
| S04-N03 提交测评 | AssessmentCommandHandler.submit | POST /families/{family_id}/assessments/sessions/{session_id}/submit | AssessmentSubmission / family_assessment_sessions | AssessmentSessionSubmitted；操作收据 | test_assessment_flow.py；test_transactional_outbox_invariant.py | IMPLEMENTED |
| S04-N04 证据冻结 | AssessmentCommandHandler.submit 内 insert_assessment_evidence | 同 S04-N03 | EvidenceSet / evidence_records | 与提交事务绑定 | test_assessment_flow.py；test_sqlalchemy_repository_integration.py | IMPLEMENTED |
| S04-N05 查看结果 | AssessmentQueryHandler.get_ui02_projection | GET /families/{family_id}/ui/02/assessment | AssessmentResultProjection（当前由会话/回答查询组装） | READ audit 尚未独立落账 | test_assessment_flow.py；test_cached_query_handler.py | PARTIAL |

### 2.2 S05 节点实现证据

| 节点 | Handler/Query | 接口 | 权威对象/表 | 事件/审计 | 测试证据 | 状态 |
|---|---|---|---|---|---|---|
| S05-N01 解释证据 | DeterministicInterpretationAdapter.interpret | GET /families/{family_id}/ui/03/growth-hypothesis 内部调用 | Perspective（当前为运行时 draft） | 可选 AiRunRecord；无 durable perspective 事件 | test_deterministic_interpretation.py；test_interpretation_boundary.py | PARTIAL |
| S05-N02 形成假设 | AssessmentQueryHandler.get_ui03_projection + _map_hypothesis | GET /families/{family_id}/ui/03/growth-hypothesis | GrowthHypothesis（当前由 Evidence + draft 映射） | 无独立 hypothesis projection 重建 | test_assessment_flow.py | PARTIAL |
| S05-N03 家庭确认/驳回 | GrowthHypothesisCommandHandler.decide | POST /families/{family_id}/growth-hypotheses/decisions | GrowthIntent / growth_intents；family_growth_hypothesis_decisions | 决策收据持久化；跨域事件尚未统一 | test_assessment_flow.py；test_sqlalchemy_repository_integration.py | PARTIAL |
| S05-N04 成长入营 | 未发现 Onboarding Handler | Mobile 期望 orchestration/intents；当前无对应 Python 路由 | Onboarding / growth_journeys（只被 Journey 读取） | 无 GrowthOnboardingStarted 写入用例 | Journey policy 与路由测试只能验证前置读取 | NOT_IMPLEMENTED |

### 2.3 S06 节点实现证据

| 节点 | Handler/Query | 接口 | 权威对象/表 | 事件/审计 | 测试证据 | 状态 |
|---|---|---|---|---|---|---|
| S06-N01 计划草案 | JourneyService.get_plan_preview | GET /families/{family_id}/growth/onboardings/{onboarding_id}/plan-preview；POST refresh | PlanPreview（规则草案） | refresh 通过 JourneyTransactionRunner 写审计/Outbox | tests/domains/journey/test_journey_routes.py | PARTIAL |
| S06-N02 创建计划 | JourneyService.create | POST /families/{family_id}/growth/onboardings/{onboarding_id}/journey-plan | JourneyPlan / family_journey_plans；JourneyPhase / family_journey_plan_phases | JourneyPlanCreated | test_journey_routes.py；test_sqlalchemy_application.py | PARTIAL |
| S06-N03 确认计划 | JourneyService.confirm | POST /families/{family_id}/growth/journey-plans/{plan_id}/confirm | JourneyPlan.status=ACTIVE | JourneyPlanConfirmed | test_journey_routes.py；test_postgres_transaction_integration.py | PARTIAL |
| S06-N04 阶段执行 | 目前没有 Action Handler；仅 count_completed_actions | Mobile 今日任务路由尚未实现 | growth_actions（只读计数） | 无 ActionTaskAssigned/ActionRecorded | test_sqlalchemy_repository_contract.py 仅验证查询 SQL | NOT_IMPLEMENTED |
| S06-N05 阶段复盘 | JourneyService.review | POST /families/{family_id}/growth/journey-plans/{plan_id}/phase-review | PhaseDecision / plan phase status | JourneyPhaseReviewed | test_journey_state_machine.py；test_sqlalchemy_application.py | PARTIAL |

### 2.4 S07 节点实现证据

| 节点 | Handler/Query | Mobile 期望接口 | 权威对象/表 | 当前证据 | 状态 |
|---|---|---|---|---|---|
| S07-N01 生成今日任务 | 未发现 | GET /families/{family_id}/growth/actions/today | ActionTask / growth_actions | Journey 仓储只有完成数查询 | NOT_IMPLEMENTED |
| S07-N02 提醒与开始 | 未发现；Workflow Worker 不存在 | POST /families/{family_id}/tasks/{task_id}/state | ActionTask / task state history | Mobile client 有调用声明，后端无路由 | NOT_IMPLEMENTED |
| S07-N03 完成/跳过 | 未发现 | POST /families/{family_id}/tasks/{task_id}/check-in | ActionRecord / growth_events | Mobile client 有调用声明，后端无路由 | NOT_IMPLEMENTED |
| S07-N04 过程回读 | 未发现 | UI-10/UI-11 查询契约待建 | ProcessPerspective、Recommendation | 无 Model Gateway/Projection Worker 闭环 | NOT_IMPLEMENTED |
| S07-N05 21 天结项 | 未发现 | UI-12/UI-29 结项/故事接口待建 | ChallengeReview / growth_reviews | 无结项状态机和人工决策 | NOT_IMPLEMENTED |

## 3. 39 条业务/运营流程 A3-A6 总账

下表是全量流程的实现入口。未实现流程先登记唯一 owner 和第一条纵向切片，
不能通过复制 UI 或新增数据库表绕过应用层。

| 流程 | 应用模块/用例 | 当前入口 | 主要数据事实 | 当前状态 | 第一缺口 |
|---|---|---|---|---|---|
| S01 | EntryApplication.publishContent / scheduleActivity / recordReach / enterFamily | UI-01/22/23；Python入口未形成 | ContentVersion、ActivityTemplate、ReachEvent | DESIGN_ONLY | 内容/活动/线索 Handler |
| VS-01 | FamilyNeedApplication.captureSignal | `POST /families/{family_id}/needs/signals`；dev/test 已由同构合成适配器接线 | NeedSignal、FamilyNeed、NeedEvent | IMPLEMENTED（N0-N1） | N1 澄清、Profile、SolutionDraft 和生产仓储接线 |
| S02 | EntryApplication.manageFamilyMembership | UI-33；Family API目标 | Family、Person、Membership | PARTIAL | Family 聚合、成员/角色命令 |
| S03 | AssessmentApplication.authorizeAssessment | UI-07；当前由 consent 前置检查隐式承担 | PurposeSelection、ConsentRecord | PARTIAL | purpose 选择与同意记录接口 |
| S04 | AssessmentApplication.executeSession | assessment router；见本台账 §2.1 | Session、Response、EvidenceSet | IMPLEMENTED | 生产接线与结果投影 |
| S05 | GrowthApplication.decideHypothesis | assessment router；见本台账 §2.2 | Perspective、Hypothesis、GrowthIntent | PARTIAL | Onboarding 写入与事件 |
| S06 | JourneyApplication.managePlan | journey router；见本台账 §2.3 | JourneyPlan、Phase、PhaseDecision | PARTIAL | 阶段推进与投影 |
| S07 | JourneyApplication.executeDailyAction | Mobile 有 client 调用；后端无路由 | ActionTask、ActionRecord、ChallengeReview | NOT_IMPLEMENTED | 建立完整 21 天行动子域 |
| S08 | GrowthApplication.recordOutcomeStory | UI-08/12/29；入口未形成 | ProgressReport、Outcome、FamilyStory | DESIGN_ONLY | Outcome 人工确认链 |
| S09 | AssistantApplication.handleConversation | 仅 deterministic assessment adapter | AIRequest、Draft、HumanEscalationCase | PARTIAL | Model Gateway、上下文、人工升级 |
| S10 | ServiceApplication.manageSupport | service router；部分 DEV wiring | Entitlement、Ticket、ServiceRecord | PARTIAL | 生产 identity/consent/repository |
| S11 | SupplyApplication.publishProviderSupply | service admin 目标路由 | Provider、Offering、AvailabilitySlot | PARTIAL | 供给域 owner 与审批事件 |
| S12 | BookingApplication.manageFulfillment | service booking router | Booking、Attendance、Feedback | PARTIAL | PostgreSQL 持久化与状态闭环 |
| S13 | FGCNApplication.executeCase | `backend/domains/service/fgcn/api/routes.py` + `application.py` + one-shot worker | Case、Task、Assignment、Delivery | PARTIAL | 常驻 worker、案件拆分、交付/贡献工作流与生产 wiring |
| S14 | QualityApplication.resolveDispute | 未发现 Python Handler | Complaint、RecoveryPlan、DisputeDecision | DESIGN_ONLY | 申诉和质量人工闸门 |
| S15 | CommerceApplication.manageCatalogIntent | commerce router；fixture/read path | ProductVersion、PurchaseIntent | PARTIAL | 真实 catalog owner 与意向状态机 |
| S16 | CommerceApplication.manageMembership | membership router；依赖 fail-closed | Order、Payment、Subscription、Entitlement | BLOCKED | 统一身份/支付适配器/真实事务 |
| S17 | AssetApplication.manageLedger | Mobile 调用目标；入口未形成 | OrderAsset、PointsLedger、Redemption | DESIGN_ONLY | 资产账本和对账 |
| S18 | RelationshipGrowthApplication.manageInvites | Mobile UI；入口未形成 | Invite、CohortMembership、IncentiveLedger | DESIGN_ONLY | 邀请/拼团状态机 |
| S19 | CommunityApplication.managePost | UI-25～28；入口未形成 | Post、Interaction、ModerationCase | DESIGN_ONLY | 社区写入、审核、申诉 |
| S20 | TrustApplication.manageDataRights | UI-33/运营端；入口未形成 | RightsRequest、ExportJob、DeletionJob | DESIGN_ONLY | 权利请求与留存/删除 Worker |
| S21 | OperationsApplication.monitorBusiness | 运营端目标 | Queue、DeliveryMetric、ComplianceAlert | DESIGN_ONLY | 指标定义和运营决策 |
| S22 | AIRuntimeApplication.runAI | intelligence WIP | ContextSnapshot、ModelAttempt、HumanReview | PARTIAL | durable runtime 与安全闸门 |
| S23 | PartnerApplication.manageAdmission | service provider 目标路由 | Application、Admission、Agreement | PARTIAL | 伙伴准入和协议生效 |
| S24 | GovernanceApplication.manageOrganization | 管理/法务端目标 | OrgCapability、Agreement、GovernanceDecision | DESIGN_ONLY | 组织、能力、授权与决策 |
| O01 | AccessAdministrationApplication.manageAccess | 运营端目标 | Tenant、RoleGrant、AccessRevocation | DESIGN_ONLY | 运营身份与撤权 |
| O02 | ContentReleaseApplication.releaseVersions | 运营端目标 | Version、ReleaseDecision | DESIGN_ONLY | 版本审核/发布/回滚 |
| O03 | CampaignApplication.orchestrateTouchpoints | 运营端目标 | TouchpointAction、ActivityReview | DESIGN_ONLY | 触达编排和频控 |
| O04 | LifecycleApplication.manageRetention | 运营端目标 | Lead、FollowUp、RetentionSignal | DESIGN_ONLY | 生命周期事件和任务 |
| O05 | SupportOperationsApplication.manageQueue | 运营端目标 | QueueItem、Escalation、Closure | DESIGN_ONLY | 队列、SLA、升级 |
| O06 | SupplyOperationsApplication.reviewSupply | 运营端目标 | ProviderApplication、CapacitySchedule | DESIGN_ONLY | 供给审核和停用 |
| O07 | DeliveryOperationsApplication.monitorFulfillment | service 运营目标 | BookingOpsView、QualitySample | PARTIAL | 运营投影和抽检闭环 |
| O08 | CommerceOperationsApplication.manageCommercialConfig | commerce 目标 | ProductReview、BenefitVersion、CampaignVersion | DESIGN_ONLY | 商业配置审批 |
| O09 | FinanceOperationsApplication.reconcilePayments | 财务端目标 | RefundDecision、ReconciliationCase、Settlement | DESIGN_ONLY | 支付回调、退款、日结 |
| O10 | ModerationOperationsApplication.reviewCommunity | 审核端目标 | ModerationQueue、AppealDecision | DESIGN_ONLY | 审核队列和申诉 |
| O11 | ComplianceOperationsApplication.executeRights | 合规端目标 | RightsCase、RetentionJob、Incident | DESIGN_ONLY | 权利/留存/安全事故 |
| O12 | AIRuntimeOperationsApplication.releaseAI | intelligence/design_copilot 仅有结构 | EvaluationRun、AIRuntimeRelease | PARTIAL | 模型/提示词/知识发布 |
| O13 | AnalyticsOperationsApplication.manageInsights | 分析端目标 | MetricDefinition、Experiment、CohortInsight | DESIGN_ONLY | 事件口径和实验 |
| O14 | ReleaseOperationsApplication.manageChange | 工程治理文档/测试存在 | ChangeRequest、ParityReport、Postmortem | PARTIAL | 可执行发布和事故工作流 |

## 4. 34 UI 的应用接线状态

UI 是渠道，不是业务事实。下列分组覆盖 UI-01 至 UI-34；UI-02-result
是 UI-02 的结果子路由，不另造场景。

| UI | 目标应用模块 | 当前接线判断 |
|---|---|---|
| UI-01、UI-33 | Entry / Trust | 前端路由存在；家庭主页和权利 API 未形成 |
| UI-02、UI-02-result、UI-07 | Assessment | UI-02 读写与 UI-07 前置可映射；结果专用投影待补 |
| UI-03 | Growth / Assessment | 假设投影和确认已存在；入营缺失 |
| UI-04、UI-05、UI-08 | Journey / Growth | 计划/预览路由存在；报告/结果待补 |
| UI-09、UI-10、UI-11、UI-12、UI-29 | Journey / Growth | 客户端有任务/节奏/故事调用；Python 后端 S07/S08 缺失 |
| UI-06、UI-13、UI-14、UI-15、UI-16、UI-17、UI-18、UI-30、UI-32 | Commerce / Membership / Asset / Relationship | 商品读取和部分会员路由存在；支付、资产、邀请未闭环 |
| UI-19、UI-20、UI-21、UI-22、UI-23、UI-24、UI-31、UI-34 | Service / Supply / Booking / FGCN | Service 部分路由和 DEV wiring 存在；FGCN Human Gate 控制面已挂载，真实资源协作和生产闭环未完成 |
| UI-25、UI-26、UI-27、UI-28 | Community / Trust | UI 基线存在；社区写入/审核/申诉未形成 |

## 5. 三环境功能等价闸门

目标是不删减测试环境功能，而是只替换数据工厂和外部适配器：

| 检查项 | 当前观察 | 判定 |
|---|---|---|
| 路由和错误码相同 | dev 会安装 assessment/service/commercial fake wiring；生产默认依赖仍有 fail-closed stub | BLOCKED |
| 状态机和业务规则相同 | S04/S06 的域规则可复用；S07 尚无规则实现 | BLOCKED |
| 数据仅替换为合成数据 | dev/test 使用 fake 或 sandbox；生产数据库接线不完整 | PARTIAL |
| 审计、Outbox、重试相同 | Assessment/Journey mutation 有局部事务 Outbox；Worker 不存在 | BLOCKED |
| 外部适配器可替换 | deterministic interpretation 与 service fake 存在；统一 adapter registry 未形成 | PARTIAL |

在上述闸门全部通过前，不能以“测试环境可点击”作为生产就绪证明。

## 6. 下一批实现顺序

1. **S05-N04**：建立 Onboarding Command、growth_journeys 写入者、GrowthOnboardingStarted
   事件和幂等/审计；让 S05 → S06 有真实连接。
2. **S06-N04/S07**：建立 ActionTask/ActionRecord 应用端口和 PostgreSQL/fake 双实现，
   补齐今日任务、状态、签到、过程回读、21 天结项。
3. **S06 projection**：将 JourneyPhase 到期、Action 记录和 PhaseDecision 接入
   Projection Worker，禁止由投影反写事实。
4. **身份/同意统一接线**：assessment、journey、service、membership 使用同一
   Actor/Tenant/Consent/UoW 上下文；dev/test/prod 只替换 provider。
5. **S08/S09 与 S10**：在 S07 有事实后再实现 Outcome/Story、AI 过程建议和服务
   协作，避免先造只有 UI 的结果页。

每个批次必须同时提交应用契约、数据关系、成功/拒绝/重放测试和三环境 parity
测试；没有这些证据，状态只能保持 PARTIAL。

## 7. 与当前系统基线的文档漂移

本轮核对发现，canonical 的 docs/00_system/CURRENT_SYSTEM_BASELINE.md 仍保留
“零业务 API、业务路由未挂载”的旧快照；而当前工作区的 family_api 已挂载
assessment、journey、service、commerce、membership 路由，且对应 WIP 测试存在。
两者不是同一个结论：路由挂载也不等于生产能力完成。

因此本台账只按当前磁盘和测试证据登记实现状态，同时把“基线快照刷新”列为
发布治理动作。刷新时必须逐路由重跑开发、测试、生产三环境 parity 验证，不能
仅把旧数字替换成新数字。
