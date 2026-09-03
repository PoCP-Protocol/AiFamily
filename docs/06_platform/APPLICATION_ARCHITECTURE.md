---
id: APP-ARCH-001
title: AiFamily 应用架构总设计（业务/流程/数据对齐版）
type: application
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: null
---

# AiFamily 应用架构总设计（业务/流程/数据对齐版）

> 本文件回答“业务流程如何被应用实现”。它不重新定义业务边界，也不拥有数据事实：业务边界以 `docs/02_business/BUSINESS_ARCHITECTURE.md` 为准，节点契约以 `BUSINESS_SCENARIO_CLOSURE_CATALOG.md` 为准，数据对象/表/关系以 `docs/07_data/DATA_OBJECT_TABLE_RELATIONSHIP_CATALOG.md` 和 `docs/07_data/MASTER_AND_BUSINESS_DATA_DECOMPOSITION.md` 为准。应用层负责用例编排、权限/同意/幂等/审计接入、接口契约、投影和外部适配器。

## 1. 应用架构原则

1. **流程先于应用**：每个应用用例必须挂到一个 `VS/P/S/O/L3/L4` 标识；不能从 UI 路由或数据库表反向创造业务流程。
2. **应用不拥有领域事实**：应用服务调用领域聚合和仓储端口；不直接更新其他域表，不把 Projection 当作写模型。
3. **一个用例一个写入意图**：Command 只表达一次业务意图；Query 只读取 DTO/Projection；副作用由 Outbox/Worker 处理。
4. **平台内核统一接入**：所有写入经过 identity → authorization → consent → idempotency → transaction → audit/outbox；领域不能直连模型、支付或消息供应商。
5. **人机边界显式**：AI 只能产生 Perspective/Recommendation/Draft；计划确认、服务分派、验收、退款、申诉和高风险动作必须有 Human Gate。
6. **34 个 UI 是渠道投影**：UI 保持基线，但每个按钮必须映射到 Command、Query 或导航；没有对应应用用例的按钮不能声称可用。
7. **三环境功能等价**：dev/test/prod 的路由、用例、状态机、权限、错误码、审计和工作流相同，只替换数据工厂和外部适配器。

应用上下文统一携带 `tenant_id`、`family_id`、`actor_id`、`purpose`、`consent_version`、`idempotency_key` 和 `correlation_id`；这些字段由平台内核注入，不能由 UI 请求体自行冒充。

## 2. A0-A6 应用分级

| 应用层级 | 回答的问题 | 设计产物 | 与业务/数据层对应 |
|---|---|---|---|
| A0 应用系统 | 整个 Family 应用系统向谁提供什么交付 | 应用地图、运行边界、渠道清单 | L0 价值流；数据产品 |
| A1 应用渠道/进程 | 哪个端/进程承载交互和作业 | Mobile、Family API、Worker、AI Runtime、运营/伙伴端 | L1 流程组；跨域事件 |
| A2 应用模块 | 哪个模块负责一组相关用例 | Entry、Growth、Service、Commerce、Community、Ops | L1/L2；数据域写入边界 |
| A3 用例/应用服务 | 一次业务意图由谁接收和编排 | Command Handler、Query Handler、Application Service | L2 场景；数据聚合 |
| A4 工作流/编排 | 多个节点如何串联、重试、人工接管 | Saga/Workflow、Human Gate、Job、Compensation | L3 子流程；事件/状态机 |
| A5 接口/契约 | 外部调用看到什么请求、响应和错误 | REST/Query DTO、Command DTO、Event Contract | L4 节点；表/投影 |
| A6 运行组件/适配器 | 代码如何运行并连接存储和外部系统 | Router、Service、Repository、Outbox、Projection、Adapter | L5 API/Command/Event/Job/Human Task |

对应关系固定为：

```text
业务 L0/L1  → 应用 A0/A1/A2
业务 L2     → 应用 A3 用例
业务 L3     → 应用 A4 工作流
业务 L4     → 应用 A5 接口契约
业务 L5     → 应用 A6 运行组件
数据对象/表/关系 → 由 A3/A4 通过 Domain Port 使用，不由应用层重新定义
```

## 3. A0 应用系统与 A1 渠道/进程

### 3.1 应用地图

| A1 渠道/进程 | 代码/目标位置 | 承载职责 | 当前状态 |
|---|---|---|---|
| Family Mobile App | `frontend/mobile/` | UI-01～UI-34、导航、表单、投影消费、用户确认 | UI 代码已迁入；多数后端用例未完成 |
| Family API | `backend/apps/family_api/` | 认证上下文、REST 路由、应用服务装配、错误契约 | FastAPI 已运行；业务路由部分挂载 |
| Workflow Worker | `backend/apps/workflow_worker/`（目标） | 提醒、超时、重试、补偿、留存/删除、对账、投影重建 | TARGET_REQUIRED |
| AI Runtime | `backend/intelligence/` | Context、Model Gateway、Prompt/Knowledge、Human Gate、Evaluation、Trace | 结构/WIP；durable runtime 未完成 |
| Operations Console | `frontend/operations/`（目标） | O01～O14 运营、审核、质量、指标、发布和事故 | TARGET_REQUIRED |
| Partner/Provider Workspace | `frontend/partner/`（目标） | S11/S23 供给、资质、时段、任务交付 | TARGET_REQUIRED |
| External Adapter Boundary | `backend/platform/adapters/`（目标） | 支付、消息、文件、搜索、模型供应商 sandbox/production 适配 | Port 需统一；当前多为 WIP |

### 3.2 Family API 当前路由与目标职责

| 路由组 | 主要用例 | UI/场景 | 当前证据 | 目标补齐 |
|---|---|---|---|---|
| `/auth/*` | AccountSession、ActorContext、SessionRevoke | 全部 UI | `assessment/api/dev_auth.py` 已挂载（开发接线） | 生产身份目录、租户/家庭解析、读取审计 |
| `/families/{id}/assessments/*`、`/ui/02`、`/ui/03` | 测评会话、回答、提交、假设决定 | UI-02、UI-02-result、UI-03、UI-07；S03-S05 | assessment router 已挂载，S04 为当前真实切片 | 证据冻结、投影持久化、生产身份与同意适配器 |
| `/families/{id}/needs/signals` | 捕获家庭需求信号并形成 N1 FamilyNeed | UI-02/03/05/09 与后续需求中心；VS-01 | family_need router 已挂载，N0→N1 应用服务和 dev/test 同构适配器可调用 | N1→N8 澄清/画像/方案/交付、PostgreSQL、真实身份/同意和记忆确认桥接 |
| `/families/{id}/growth/*` | 优先级、计划预览、计划确认、阶段复盘 | UI-04、05、08；S05-S08 | journey router 已挂载，需 PostgreSQL | Action/Outcome 全链、事件/投影/人工复盘 |
| `/families/{id}/orchestration/test-loop/services/*` | 供给、时段、预约、客户投影 | UI-19～24、31、34；S10-S12 | service router 已挂载；当前含 DEV/TEST adapter | 生产同等路由和 adapter，FGCN 案件/任务/验收 |
| `/families/{id}/membership/*` | 会员订阅、权益、周期、会员投影 | UI-06、18、30 | router 已挂载；依赖缺口会 fail-closed | 支付订单关联、持久化审计、完整投影 |
| `/families/{id}/orchestration/test-loop/commerce/*` | 商品目录、购买意向、客户投影 | UI-13、14 | DEV/TEST fixture 路由已挂载 | 统一 Product/Order/Payment/Entitlement，不以 test-loop 代替生产语义 |
| `/product-intelligence/*` | 产品/市场/策略智能 | O02、O06、O12、O13 | router 有代码但未在 family_api 挂载 | Operations Console、Gateway/权限/审计接线 |
| `/community/*`、`/rights/*`、`/ops/*`、`/release/*` | 社区、数据权利、运营、发布事故 | UI-25～28、33；O10/O11/O14 | TARGET_REQUIRED | 完整应用服务、审核/权利/事故状态机 |

## 4. A2 应用模块与责任边界

| 模块 | 负责的流程组 | 主要领域/平台依赖 | 允许写入 | 不负责 |
|---|---|---|---|---|
| `EntryApplication` | P01 / S01-S03 / O01/O03/O04 | identity、tenancy、family、consent、content、ops | Entry、Family、Membership、Consent、Reach/Lead | 测评答案、交易、成长结果 |
| `GrowthApplication` | P02 / S04-S09 / O02/O12 | assessment、growth、journey、ai_runtime、consent | Session、Response、Evidence、Intent、Plan、Action、Outcome 请求 | 直接调用模型供应商、直接改 Family Fact |
| `ServiceCollaborationApplication` | P03 / S10-S14/S23 / O05-O07 | service、partner、growth intent、authorization、audit | Entitlement 使用、Booking、Case、Task、Assignment、Delivery、Quality、Contribution | 订单支付、家庭拥有关系、自动分佣 |
| `CommerceRelationshipApplication` | P04 / S15-S18 / O08-O09 | commerce、membership、loyalty_points、payment adapter | Intent、Order、Payment、Entitlement、Subscription、Ledger、Invite | 基于儿童画像的商业营销、家庭排名 |
| `CommunityTrustApplication` | P05 / S19-S20 / O10-O11 | community、security/audit、consent、retention | Post、Moderation、Appeal、Rights、Deletion、Incident | 直接删除审计/支付法定留存 |
| `OperationsGovernanceApplication` | P06 / S21-S24 / O12-O14 | ops、ai_runtime、partner、governance、release | Queue、Metric、Experiment、Evaluation、Agreement、Change、Postmortem | 把指标推断成疗效、绕过业务域写事实 |
| `SharedApplicationKernel` | 全部 | identity、authorization、consent、idempotency、persistence、audit、outbox | 事务编排、错误码、审计和事件 envelope | 任何家庭/成长/订单业务判断 |

应用模块可以跨域**编排**，但每个业务事实只有一个 Domain Owner。模块之间使用 Command/Query Port 或事件，不共享 ORM 实体；禁止跨域直写。

## 5. A3 用例/应用服务与 39 个流程绑定

以下是应用层的用例命名基线。名称是应用契约，不表示所有实现已完成；`current` 以 `CURRENT_SYSTEM_BASELINE.md` 和测试证据为准。

### 5.1 P01/P02：家庭进入、测评与成长行动

| 流程 | 应用用例/服务 | Command/Query | 主数据 | 业务数据/投影 | UI |
|---|---|---|---|---|---|
| S01 | `EntryApplication.publishContent` / `scheduleActivity` / `recordReach` / `enterFamily` | PublishContent、ScheduleActivity、RecordReach、EnterFamily | ContentVersion、ActivityTemplate、ChannelConfig | ReachEvent、EntryEvent → EntryProjection | UI-01、22、23 |
| VS-01 | `FamilyNeedApplication.captureSignal` | CaptureFamilyNeedSignal | NeedSignal、FamilyNeed | FamilyNeed、NeedEvent → NeedProjection | UI-02/03/05/09（第一条需求纵切片） |
| S02 | `EntryApplication.manageFamilyMembership` | CreateFamily、InviteMember、BindMember、GrantRole | RoleDefinition、RelationshipType | Family、Person、Membership、VisibilityPolicy → FamilyHomeProjection | UI-33、全局上下文 |
| S03 | `AssessmentApplication.authorizeAssessment` | SelectPurpose、GrantConsent、AuthorizeAssessment | AssessmentToolVersion、PurposeDefinition、ConsentPolicy | PurposeSelection、ConsentRecord、StartToken → AssessmentStartProjection | UI-07 |
| S04 | `AssessmentApplication.executeSession` | StartAssessment、SaveResponse、SubmitAssessment、FreezeEvidence | AssessmentToolVersion、QuestionSchema | Session、Response、Submission、EvidenceSet → AssessmentResultProjection | UI-02、UI-02-result |
| S05 | `GrowthApplication.decideHypothesis` | GeneratePerspective、ProposeHypothesis、DecideHypothesis、StartOnboarding | InterpretationRule、HypothesisTemplate、SafetyPolicy | Perspective、Hypothesis、GrowthIntent、Onboarding → HypothesisProjection | UI-03 |
| S06 | `JourneyApplication.managePlan` | GeneratePlanPreview、CreatePlan、ConfirmPlan、ReviewPhase | JourneyTemplate、TaskTemplate、PhasePolicy | JourneyPlan、Phase、PhaseDecision → PlanProjection | UI-04、05、08 |
| S07 | `JourneyApplication.executeDailyAction` | AssignTask、StartTask、RecordAction、CloseChallenge | ActionTemplate、ReminderPolicy、ChallengePolicy | ActionTask、ActionRecord、ChallengeReview → TodayTask/RhythmProjection | UI-09、10、11 |
| S08 | `GrowthApplication.recordOutcomeStory` | GenerateReport、ConfirmOutcome、SaveStory、GenerateAnnualReview | ReportTemplate、OutcomeType、StoryVisibilityPolicy | ProgressReport、Outcome、FamilyStory → Outcome/StoryProjection | UI-08、12、29 |
| S09 | `AssistantApplication.handleConversation` | ReceiveAIRequest、GenerateDraft、IssueRecommendation、EscalateRisk | KnowledgeVersion、PromptVersion、RoutingPolicy、SafetyPolicy | AIRequest、ContextSnapshot、ModelAttempt、Draft、HumanEscalationCase → AssistantProjection | UI-03、05、09、10 |
| O01 | `AccessAdministrationApplication.manageAccess` | OpenTenant、GrantRole、SupportAccount、RevokeAccess | RoleDefinition、TenantPlan、RevocationPolicy | Tenant、RoleGrant、AccountAction、AccessRevocation → AccessAdminProjection | 运营端 |
| O02 | `ContentReleaseApplication.releaseVersions` | ReviewContent、FreezeAssessment、PublishTemplate、RollbackVersion | Content/Assessment/Journey/Task Version | ReviewDecision、ReleaseDecision → VersionOpsProjection | 运营端 |
| O03 | `CampaignApplication.orchestrateTouchpoints` | ConfigureChannel、ScheduleCampaign、SendTouchpoint、ReviewActivity | ChannelConfig、Frequency/OptOut Policy | TouchpointAction、ActivityReview → CampaignOpsProjection | 运营端 |
| O04 | `LifecycleApplication.manageRetention` | ReceiveLead、FollowUpOnboarding、RaiseRetentionSignal、ReactivateFamily | Lead/FollowUp/Retention Policy | FamilyLead、FollowUp、RetentionSignal、ReactivationAction → LifecycleOpsProjection | 运营端 |
| O12 | `AIRuntimeOperationsApplication.releaseAI` | RegisterKnowledge、PublishPrompt、SetRoutingPolicy、RunEvaluation、RollbackRuntime | Knowledge/Prompt/Model/Evaluation Policy | EvaluationRun、AIRuntimeRelease → AIOpsProjection | 运营端 |

### 5.2 P03/P04：服务协作、FGCN 与商业关系

| 流程 | 应用用例/服务 | Command/Query | 主数据 | 业务数据/投影 | UI |
|---|---|---|---|---|---|
| S10 | `ServiceApplication.manageSupport` | OpenService、RecordContact、CreateTicket、RecordService、CloseService | ServiceEntitlementPolicy、SLA、RecordSchema | ServiceEntitlement、Interaction、Ticket、Record → ServiceJourneyProjection | UI-05、06、31、34 |
| S11 | `SupplyApplication.publishProviderSupply` | CreateProviderProfile、PublishOffering、ReleaseSlot、RecommendProvider | Qualification、ServiceType、Offering/SLA、CapacityRule | ProviderProfile、OfferingVersion、AvailabilitySlot、Recommendation → ProviderDirectoryProjection | UI-19、20 |
| S12 | `BookingApplication.manageFulfillment` | PreviewBooking、CreateBooking、CancelBooking、RecordAttendance、RecordFeedback | Booking/Cancellation/Attendance Policy | Booking、Attendance、Feedback → BookingProjection | UI-21～24 |
| S13 | `FGCNApplication.executeCase` | OpenCase、SplitTask、AssignResource、SubmitDelivery、VerifyDelivery、RecordContribution | BlueprintVersion、TaskTemplate、Quality/Contribution Policy | Case、Task、Assignment、Delivery、Quality、Contribution、Allocation → FGCNCase/AllocationProjection | UI-21、24、31、34 |
| S14 | `QualityApplication.resolveDispute` | OpenComplaint、TriageComplaint、ApplyRecovery、DecideDispute、CloseComplaint | Severity/SLA/Recovery/Dispute Policy | QualitySignal、ComplaintCase、RecoveryPlan、DisputeDecision → QualityProjection | UI-24、34、运营端 |
| S23 | `PartnerApplication.manageAdmission` | ApplyPartner、AdmitPartner、ListOffering、RecordPartnerDelivery、DecideRenewal | Qualification、DPA/SLA、PartnerPolicy | Application、Admission、Agreement、PartnerDelivery、Decision → PartnerProjection | UI-19～24、运营端 |
| O05 | `SupportOperationsApplication.manageQueue` | QueueTicket、AssignOwner、EscalateSLA、CloseTicket | QueueType、SLA、Severity | QueueItem、Assignment、Escalation、Closure → SupportOpsProjection | 运营端 |
| O06 | `SupplyOperationsApplication.reviewSupply` | ReviewProvider、AdmitProvider、ScheduleCapacity、SuspendProvider | Admission/Capacity/Review Policy | ProviderApplication、Admission、CapacitySchedule、Decision → SupplyOpsProjection | 运营端 |
| O07 | `DeliveryOperationsApplication.monitorFulfillment` | MonitorBooking、RecoverAbsence、SampleQuality、CloseFulfillment | Recovery/Sampling/Fulfillment Policy | BookingOpsView、RecoveryAction、QualitySample、FulfillmentClosure → DeliveryOpsProjection | 运营端 |
| S15 | `CommerceApplication.manageCatalogIntent` | PublishProduct、ViewProduct、CreatePurchaseIntent、ResolveEligibility | Product/Price/Benefit/Eligibility Policy | ProductVersion、PurchaseIntent、Eligibility → ProductProjection | UI-13、14 |
| S16 | `CommerceApplication.manageMembership` | CreateMembershipOrder、ConfirmPayment、ActivateEntitlement、ConsumeBenefit、DecideRenewal | MembershipPlan、BenefitVersion、Price/Renewal Policy | Order、Payment、Subscription、Membership、Entitlement、Usage、Renewal → MembershipProjection | UI-06、18、30 |
| S17 | `AssetApplication.manageLedger` | CreateOrderAsset、CreditPoints、RedeemPoints、ReadAssets、Reconcile | EarnRule、RedemptionItem、Asset/Reconciliation Policy | OrderAsset、PointsLedger、Redemption、ReconciliationCase → Asset/PointsProjection | UI-17、32 |
| S18 | `RelationshipGrowthApplication.manageInvites` | CreateInvite、AcceptInvite、JoinCohort、RecordIncentive、ExitCohort | Invite/Cohort/Incentive Policy、CampaignVersion | Invite、CohortMembership、IncentiveLedger、CohortExit → CohortProjection | UI-15、16 |
| O08 | `CommerceOperationsApplication.manageCommercialConfig` | ConfigureProduct、ConfigureBenefit、PublishPromotion、RevokeEntitlement | Product/Benefit/Campaign/Refund Policy | ProductReview、BenefitVersion、CampaignVersion、Revocation → CommerceOpsProjection | 运营端 |
| O09 | `FinanceOperationsApplication.reconcilePayments` | ReceivePaymentCallback、ApproveRefund、ReconcileDay、GenerateSettlement | PaymentProvider、Refund/Settlement Policy | Payment、RefundDecision、ReconciliationCase、SettlementStatement → FinanceOpsProjection | 运营端 |

### 5.3 P05/P06：社区、权利、运营与治理

| 流程 | 应用用例/服务 | Command/Query | 主数据 | 业务数据/投影 | UI |
|---|---|---|---|---|---|
| S19 | `CommunityApplication.managePost` | CreatePostDraft、ModeratePost、RecordInteraction、WithdrawPost、HandleModeration | Visibility、Moderation、Interaction Policy | Post、Revision、Interaction、Report、ModerationCase → CommunityFeedProjection | UI-25～28 |
| S20 | `TrustApplication.manageDataRights` | RequestRights、AssessScope、ExportData、DeleteData、OpenIncident、AuditRetention | Purpose、Retention、LegalHold、Incident Policy | RightsRequest、Assessment、Export/DeletionJob、SecurityIncident、RetentionAudit → ComplianceProjection | UI-33、运营端 |
| O10 | `ModerationOperationsApplication.reviewCommunity` | QueueModeration、DecideModeration、ResolveAppeal、ChangePolicy | Moderation/Appeal Policy | QueueItem、Decision、AppealDecision、PolicyChange → ModerationOpsProjection | 运营端 |
| O11 | `ComplianceOperationsApplication.executeRights` | OpenRightsCase、ReviewAccess、RunRetentionJob、ResolveIncident | Rights/Retention/Access/Incident Policy | RightsCase、AccessReview、RetentionJob、SecurityIncident → ComplianceOpsProjection | 运营端 |
| S21 | `OperationsApplication.monitorBusiness` | BuildQueue、PublishDeliveryMetric、PublishBusinessMetric、RaiseComplianceAlert、RecordOperatingDecision | MetricDefinition、SLA、Compliance Policy | Queue、DeliveryMetric、BusinessMetric、Alert、Decision → OpsDashboardProjection | 运营端 |
| S22 | `AIRuntimeApplication.runAI` | PublishKnowledge、AssembleContext、CallModel、ReviewDraft、EvaluateRuntime | Knowledge/Prompt/Model/Evaluation Policy | ContextSnapshot、ModelAttempt、HumanReview、Evaluation → AITraceProjection | 跨页/后台 |
| S24 | `GovernanceApplication.manageOrganization` | DefineResponsibility、SignAgreement、GrantStaffAccess、VestEquity、RecordDecision | Capability/Agreement/Role/Equity/Governance Policy | OrgCapability、Agreement、StaffAccess、EquityGrant、GovernanceDecision → GovernanceProjection | 管理/法务端 |
| O13 | `AnalyticsOperationsApplication.manageInsights` | DefineMetric、StartExperiment、AnalyzeCohort、RecordDecision | Metric/Event/Cohort/Experiment Policy | MetricDefinition、Experiment、CohortInsight、OperatingDecision → AnalyticsOpsProjection | 运营端 |
| O14 | `ReleaseOperationsApplication.manageChange` | SubmitChange、VerifyParity、ReviewAudit、OpenIncident、ClosePostmortem | Change/Parity/Audit/Incident Policy | ChangeRequest、ParityReport、AuditFinding、IncidentRecord、Postmortem → ReleaseOpsProjection | 工程/SRE/审计端 |

## 6. A4 工作流与编排模式

### 6.1 同步写入用例

```text
HTTP/Screen Intent
 → Router/DTO 校验
 → ActorContext + Tenant/Family scope
 → Authorization
 → ConsentGate（适用时）
 → Idempotency reserve
 → Application Service
 → Domain Aggregate + Repository
 → AuditEvent + Outbox（同一事务）
 → Mutation Receipt / Query Projection
```

同步用例只能返回“事实已写入/请求已受理”的收据，不能把 AI 草稿、支付意向或投影计数伪装成已完成结果。

### 6.2 异步节点、人工闸门和补偿

| 编排类型 | 适用流程 | 应用组件 | 必须保存 |
|---|---|---|---|
| Event consumer | 跨域投影、指标、通知、权益激活 | Outbox → Inbox → Handler | event_id、消费状态、重试次数、死信原因 |
| Scheduled Job | 提醒、SLA、续购、留存删除、对账 | Workflow Worker | deadline、retry、compensation、审计 |
| Human Gate | 假设确认、计划确认、资源分派、验收、退款、申诉、AI 高风险 | HumanTaskService | reviewer、decision、reason、before/after |
| Saga/Process Manager | 支付→会员→权益、案件→任务→贡献、权利→删除 | ProcessManager | correlation/causation、阶段状态、补偿命令 |
| Projection rebuild | UI/运营/分析读模型 | ProjectionWorker | projection_version、last_event_id、重放范围 |

### 6.3 应用错误契约

每个应用模块必须统一返回：

```text
error_code、http_status、message_key、field_errors[]
correlation_id、retryable、human_action_required、source_node_id
```

`error_code` 来自 L4 节点拒绝规则；不能把数据库异常、供应商异常或未授权访问直接泄漏给 UI。dev/test/prod 必须使用同一错误码和拒绝路径。

## 7. A5 接口与 34 UI 对齐

### 7.1 UI → 应用模块 → 投影/用例

| UI 范围 | 应用模块 | 主要 Query/Projection | 主要 Command/用例 |
|---|---|---|---|
| UI-01、UI-33 | EntryApplication / TrustApplication | FamilyHome、FamilyProfile、RightsProjection | CreateFamily、ManageMember、RequestRights |
| UI-02、UI-02-result、UI-03、UI-07 | AssessmentApplication / GrowthApplication | Assessment、AssessmentResult、Hypothesis、AssessmentCatalog | Start/Save/SubmitAssessment、DecideHypothesis |
| UI-04、UI-05、UI-08、UI-09、UI-10、UI-11、UI-12、UI-29 | JourneyApplication / GrowthApplication | Plan、Journey、TodayTask、Rhythm、Story、Outcome | Create/ConfirmPlan、RecordAction、ConfirmOutcome、SaveStory |
| UI-06、UI-13、UI-14、UI-15、UI-16、UI-17、UI-18、UI-30、UI-32 | CommerceRelationshipApplication | Product、Membership、Asset、Points、Cohort、Renewal | PurchaseIntent、Membership、PointsRedeem、Invite/Cohort |
| UI-19、UI-20、UI-21、UI-22、UI-23、UI-24、UI-31、UI-34 | ServiceCollaborationApplication | Provider、Availability、Booking、Service、Quality、FGCN | CreateBooking、Cancel、Fulfil、OpenCase、VerifyDelivery |
| UI-25、UI-26、UI-27、UI-28 | CommunityTrustApplication | CommunityFeed、Post、Moderation | CreatePost、Moderate、Interact、Withdraw |

`UI-02-result` 是 UI-02 测评用例的结果子路由，不新增业务场景或独立数据事实。所有 UI 读模型必须可由数据架构的权威表和事件重建；没有真实业务数据时返回显式 `NOT_AVAILABLE`。

### 7.2 接口命名规则

| 接口类型 | 命名 | 示例 | 数据权限 |
|---|---|---|---|
| Query | `GET /families/{family_id}/...` | `GET .../ui/02/assessment` | 只读 Projection/DTO，记录 READ audit |
| Command | `POST /families/{family_id}/...` | `POST .../assessments/sessions/{id}/submit` | 必须 actor、purpose、consent、idempotency |
| Event | `domain.aggregate.action.v1` | `assessment.session.submitted.v1` | Outbox 同事务，跨域只消费 |
| Job | `job.<domain>.<action>` | `job.rights.deletion.v1` | 重试、死信、完成事件 |
| Human Task | `human.<domain>.<decision>` | `human.service.delivery.verify.v1` | reviewer、reason、审计 |

## 8. A6 运行组件与代码组织

```text
backend/apps/family_api/
  routers/                 # A5 HTTP contract
  dependencies/            # Actor/Tenant/Consent/Policy/UoW wiring
  exception_handlers/      # application error contract

backend/domains/<domain>/
  application/              # A3 Command/Query Handler + A4 orchestration
  domain/                   # business aggregate/state/policy
  infrastructure/           # A6 repository/event adapter
  api/                      # A5 router/DTO (domain semantics only)

backend/platform/
  identity authorization consent idempotency persistence audit outbox

backend/intelligence/
  context_engine model_gateway agent_runtime prompt_registry safety human_gate evaluation trace

backend/apps/workflow_worker/ # A4 scheduled/retry/compensation/projection jobs (target)
frontend/mobile/              # A1 channel; UI reads projections and sends commands
```

强制依赖方向：

```text
UI/Router → Application Service → Domain Port/Aggregate → Repository
                                         ↓
                                  Event/Outbox → Projection/Worker
```

禁止方向：UI → ORM、Application → 其他域表、Domain → Model Provider、Projection → Fact、AI Draft → Canonical Fact。

## 9. 应用架构与业务/数据架构的修正项

本次对齐发现并裁决以下问题：

1. **S16 只归属 P04/VS-03**：会员权益是商业关系增长的业务事实；它可以支撑 VS-01 的家庭成长交付，但不再作为 VS-01 的主场景，避免同一 L2 场景双写。
2. **`family_journey_plans` 是计划主表**：`growth_journeys` 仅作为 onboarding/历史兼容聚合；应用层不得同时创建两套主计划。
3. **`family_order_intents` 不是订单**：CommerceApplication 只能创建购买意向；Order/Payment/Refund 用例与表必须补齐后才能宣称支付/会员能力。
4. **Service test-loop 是路径兼容，不是测试专属应用**：应用契约和状态机保持生产等价，DEV/TEST 只替换 fixture/sandbox/noop adapter；不能以路径名称删减节点。
5. **`product_intelligence` 属 Operations/AI 应用**：它的 Perspective/Recommendation 只能影响产品和运营决策，不得写入儿童成长事实或服务分佣。
6. **社区、权利、运营、伙伴工作台是应用缺口**：有 UI/数据对象设计不等于有可调用应用服务，必须补路由、handler、repository、workflow、projection 和测试。

## 10. 应用能力完成定义

一个应用用例只有同时具备以下证据，才能从 `DESIGN_ONLY/PARTIAL` 提升为 `IMPLEMENTED`：

- 有 `scenario_id/process_group_id/node_id` 与业务/流程架构的唯一映射；
- 有输入/输出 DTO、错误码、权限和同意检查；
- 有唯一 Command Handler/Query Handler，写入者和数据域 owner 明确；
- 有对象→表→关系映射，事务边界和 migration 可运行；
- 有成功、失败/拒绝、补偿（适用时）事件，Outbox 与事实同事务；
- 有 UI/运营 Projection，能从事件重建并执行脱敏、留存、删除；
- 有 Human Gate、审计、幂等、重试、死信和外部适配器契约；
- dev/test/prod 使用同一应用路由、状态机、权限、错误码和工作流；
- 有 Python 验收测试和 PostgreSQL/Alembic 集成证据；
- 当前状态与 `CURRENT_SYSTEM_BASELINE.md` 一致，不以“代码迁入/路由挂载/fixture 返回”冒充能力完成。

## 11. A3-A6 实现台账与第一条纵向切片

应用架构的静态分解由本文件维护；可执行证据由
`docs/11_delivery/APPLICATION_IMPLEMENTATION_LEDGER.md` 维护。台账逐节点记录
Handler、接口、权威对象/表、事件/投影、测试证据和缺口，并覆盖 34 个 UI、
24 个业务场景和 14 个运营场景。

当前第一条纵向切片的裁决如下：

- **S04 = IMPLEMENTED（域切片）**：测评会话、回答、提交、证据冻结和 UI-02
  查询投影已有 Handler、SQL/fake 仓储、幂等、审计/Outbox 与测试证据；生产
  身份/同意接线及 UI-02-result 专用投影仍是发布前置条件。
- **S05 = PARTIAL**：假设投影和人工确认写入 GrowthIntent 已存在，但
  Onboarding 写入、GrowthOnboardingStarted 事件、真实 Model Gateway 与风险
  升级尚未形成闭环。
- **S06 = PARTIAL**：优先级、计划预览、计划创建/确认/复盘路由已有；阶段到期
  推进、Action 生成、投影重建和完整人工复盘仍待补齐。
- **S07 = NOT_IMPLEMENTED**：Mobile 已有今日任务、任务状态和签到调用声明，
  Python 侧尚无对应 Handler、路由、提醒 Worker、过程回读和 21 天结项。

这份台账是实现状态的单一交付视图；任何“UI 可点击”“路由已挂载”“fixture
有返回”都不能替代台账规定的完成证据。
