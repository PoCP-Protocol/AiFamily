---
id: DATA-SCENARIO-MAP-001
title: AiFamily 业务场景驱动的总数据架构设计（WIP 整合版）
type: data
status: draft
version: 0.2
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: null
---

# AiFamily 业务场景驱动的总数据架构设计（WIP 整合版）

> 本稿把 `BUSINESS_SCENARIO_CLOSURE_CATALOG.md` 的 24 个业务闭环（S01-S24）和 14 个平台运营闭环（O01-O14）映射为数据主体、聚合、事件、读模型、权限和留存规则。它是目标数据架构工作稿，不把现有 151 张历史表误认为已经完成的目标模型。
>
> 整合原则见 `governance/ADR/ADR-0021-business-scenario-data-architecture-wip-integration.md`；本稿主动纳入现有 Agent WIP，不覆盖或抹平其未决冲突。

## 1. 数据架构原则

1. **业务场景先于表**：一个场景的权威事实只有一个写入域；UI、报表和 AI 只读投影。
2. **事实与推断分离**：Fact、Perspective、Recommendation、Action、Outcome 分开存储和审计，AI 不直接写业务事实。
3. **聚合内一致、跨域只读**：聚合内事务保持一致；跨域通过 Query Port/事件构建投影，不跨 schema 直写。
4. **事件可追溯、修正不覆盖**：原始事实不可更新覆盖，纠错用补偿事件；所有副作用走 Outbox/幂等。
5. **家庭边界优先**：`tenant_id`、`family_id`、`subject_id`、purpose、consent_version 是敏感数据访问的共同键。
6. **环境功能等价**：开发、测试、生产使用同一 schema、状态机、权限、错误码、审计和工作流；测试环境只替换数据和外部适配器。

## 2. 数据对象分类与数据分级

### 2.1 对象分类

| 类型 | 定义 | 存储要求 | 示例 |
|---|---|---|---|
| `Fact` | 家庭或系统实际发生并可验证的事实 | 业务域权威表，版本/来源/时间完整 | 回答、预约、签到、支付回调 |
| `Perspective` | AI/人对事实的解释、观察或假设 | 独立表，带 provenance 和限制 | 成长假设、过程观察 |
| `Recommendation` | AI/规则提出的建议 | 不得直接改变事实 | 下一步建议、提醒建议 |
| `Action` | 经过授权并产生副作用的动作 | 幂等键、Actor、审计、状态机 | 创建计划、扣积分、退款 |
| `Outcome` | 由家庭/服务方/证据确认的结果 | 需要确认主体或证据链 | 成果记录、质量验收 |
| `Projection` | 面向 UI/运营的可重建读模型 | 可删除、可重放，不是事实源 | UI-05 计划投影、运营队列 |
| `Audit` | 谁在何时以何目的访问或改变了什么 | 追加写、不可由业务覆盖 | AccessLog、ConsentHistory |

### 2.2 数据分级与目的

| 级别 | 范围 | 典型字段 | 默认策略 |
|---|---|---|---|
| L0 | 公开内容 | 已发布课程、活动公开信息 | 可缓存；无家庭标识 |
| L1 | 账户与运营 | account_id、联系方式、角色 | 加密传输/存储；按角色最小可见 |
| L2 | 家庭业务 | family、计划、预约、订单、服务记录 | tenant/family 隔离；目的绑定 |
| L3 | 儿童与敏感成长 | child profile、自由文本回答、风险信号 | 监护依据、字段脱敏、人工复核 |
| L4 | 安全、支付、AI 追踪 | 密钥、支付令牌、完整 prompt/trace | 独立权限、短留存或受控留存、不可导出明文 |

目的码统一使用：`assessment`、`journey`、`service_delivery`、`commerce`、`community`、`operations`、`compliance`、`ai_runtime`。同意必须绑定 purpose，不能用一个“平台同意”覆盖所有用途。

## 3. 数据域与权威写入边界

| schema/域 | 权威聚合 | 允许写入 | 对外只读投影 |
|---|---|---|---|
| `identity` | User、Session、OTP | 身份认证、会话撤销 | ActorContext |
| `tenancy` | Tenant、FamilyMembership、TenantBinding | 租户和成员绑定 | FamilyAccessProjection |
| `family` | Family、Person、Relationship、FamilyProfile | 家庭与成员事实 | FamilyContextProjection |
| `consent` | ConsentRecord、PurposeGrant | 同意、撤回、版本 | ConsentSnapshot |
| `assessment` | AssessmentVersion、Session、Response、Evidence | 测评会话和证据 | AssessmentProjection |
| `growth` | Perspective、Hypothesis、GrowthIntent、GrowthNeed、Outcome | 解读、意图、结果确认 | GrowthReadback |
| `journey` | JourneyPlan、Phase、ActionTask、ActionRecord | 21/90 天计划和行动事实 | JourneyProjection |
| `program/content` | BlueprintVersion、ContentVersion、Template | 内容、模板、版本发布 | CatalogProjection |
| `service` | ServiceCase、Task、Assignment、Booking、Record、Quality、Contribution | 服务交付、验收、协作 | ServiceCustomerProjection、OpsQueueProjection |
| `commerce` | Product、Order、Payment、Membership、Entitlement、PointsLedger | 交易、权益、积分、对账 | CommerceCustomerProjection |
| `community` | Post、ModerationCase、Interaction、Report | 内容、审核和申诉 | CommunityFeedProjection |
| `partner` | Partner、Offering、Capacity、Agreement | 机构/专家准入与供给 | ProviderDirectoryProjection |
| `ops` | Queue、SLA、Metric、Experiment、Decision | 运营任务、指标和决策 | OpsDashboardProjection |
| `ai_runtime` | Knowledge、Prompt、ModelAttempt、Provenance、Evaluation | AI 调用与评估追踪 | AITraceProjection |
| `security/audit` | AccessLog、SecurityIncident、RightsCase、RetentionJob | 安全、数据权利、留存 | ComplianceDashboardProjection |

历史 baseline 表仍是迁移事实；目标域表通过后续 Alembic revision 演进，不能直接修改 baseline 或以新表绕开原事实。

## 3A. 现有 WIP 数据面纳入总设计

本节是本次总设计的关键：以下 WIP 不是“另一个项目”，而是现有数据架构的输入。设计只做归属、边界和迁移裁决，不覆盖各 Agent 的未提交文件。

| WIP 来源 | 已有数据对象/表 | 对应场景 | 总设计裁决 | 当前状态/后续 |
|---|---|---|---|---|
| `backend/domains/family` | `Family`、`FamilyMember`、`FamilyRelationship`、`LifeStageAssignment`、`Consent`；baseline `families/persons/family_relationships/life_stage_assignments/consents` | S02、S03、S20、O01/O11 | 保留 `persons.person_type` 单一主体模型；关系事实不自动授权；同意记录与 ConsentGate 分离 | WIP 域对象已具备；真实 repository、成员可见性投影待补 |
| `backend/platform/identity`、`authorization`、`consent` | `ActorContext`、`TenantContext`、`TenantDirectory`、`ConsentGrant`、`PolicyEngine` | S02/S03、S09、S20、O01/O11 | 这些是边界值对象/策略，不是第二套身份表；持久化归 `identity/tenancy/consent` | InMemory/DenyAll 仅为接线；生产目录和同意查询适配器待接入 |
| `backend/domains/assessment` | `family_assessment_tools`、`family_assessment_sessions`、`family_assessment_responses`、`family_assessment_operations`、`family_assessment_ai_runs`、`family_assessment_capability_memory_assets` | S03-S05、S09、O02/O12 | 继续兼容 baseline 0043/0047/0049；测评回答和证据是 Fact，AI run 是追踪，不回写事实 | Python repository 已读写旧 schema；切换唯一写入者前需 Alembic/PG 验收 |
| `backend/domains/journey` | `family_journey_plans`、`family_journey_plan_phases`、`growth_priorities`、`growth_actions`，以及 `growth_profiles/growth_intents` | S05-S07、O02/O04 | 计划/阶段/行动按 `journey` 聚合；priority 必须是家庭确认的实践焦点；不新增家庭分数/排名 | SQL repository 和状态机 WIP；行动事件、阶段推进和 Projection 仍缺 |
| `backend/domains/service` | `family_service_providers`、`family_service_offerings`、`family_service_availability_slots`、`family_booking_requests`、`family_booking_service_records`、`family_service_private_checkin_drafts` | S10-S14、O05-O07 | 预约子链保留；FGCN 的 `service_cases/service_tasks/task_assignments/task_quality_reviews/service_contribution_allocations` 纳入同一 service 域，不再另建平行服务库 | ORM/Port/迁移 0003 已有；案件、任务、验收与争议链仍需汇合 |
| `backend/domains/commerce` | `family_product_offerings`、`family_order_intents`、`family_entitlements`；baseline 另有 `family_order_intent_lines`、`family_product_events` | S15-S18、O08/O09 | 目录、意向、订单、权益、支付、事件分层；fixture/no-op 只替换数据和外部适配器 | 目录和意向已接 DEV/TEST；line/event 映射、支付回调和真实 session wiring 待补 |
| `backend/domains/membership` | `family_membership_plans`、`family_membership_tier_definitions`、`family_membership_benefit_definitions`、`family_membership_subscriptions`、`family_membership_periods`、`family_membership_tier_transitions`、`family_membership_benefit_grants`、`family_membership_benefit_reservations`、`family_membership_benefit_ledger` | S16/S17、O08/O09 | `tier_code` 只表示会员权益档位；不得解释为成长等级、家庭排名或分数 | ORM、生命周期命令和 Projection WIP；支付订单与会员订阅的关联待统一 |
| `backend/domains/loyalty_points` | `family_loyalty_points_earn_rules`、`family_loyalty_points_redemption_items`、`family_loyalty_points_accounts`、`family_loyalty_points_ledger`、`family_loyalty_points_redemptions` | S17/S18、O08/O09 | 账本追加写，余额由 `SUM(points_delta)` 聚合；`balance_after` 只是写入快照，不是权威余额；禁止 1280 等默认值 | 新建 ORM/commands/tests WIP；Alembic revision、对账和订单来源事件待接 |
| `backend/domains/product_intelligence`、`product_strategy`、`market_intelligence` | `product_intelligence_market_signals`、`product_intelligence_signal_clusters`、`product_intelligence_market_trends`、`product_intelligence_customer_segments`、`product_intelligence_evidence`、`product_intelligence_customer_insights`、`product_intelligence_unmet_needs`、`product_intelligence_opportunities`、`product_intelligence_growth_problems`、`product_intelligence_growth_hypotheses`、`product_intelligence_contradiction_models`、`product_intelligence_value_architectures`、`product_intelligence_growth_strategies`、`product_intelligence_product_concepts`、`product_intelligence_product_components`、`product_intelligence_product_patterns`、`product_intelligence_product_definitions`、`product_intelligence_service_blueprint_versions`；`product_intelligence_zone_policy_versions`、`product_intelligence_zone_assessments_v0` | S21/S22/S23/S24、O02/O06/O12/O13 | 这是产品/运营智能数据，不是家庭成长事实；所有模型输出仍是 Draft/Perspective/Recommendation | ORM 与 zone WIP 已有；baseline 0062 与私有 0058/0059/0060 存在漂移，必须新增 Alembic revision 后才能生产 |
| `backend/intelligence/context_engine`、`model_gateway` | `StateObservation`、`ContextSnapshot`、`AttemptRecord`、`ModelAttempt`、`Provenance`；当前主要为内存/Port | S09、S22、O12 | `ai_runtime` 只存上下文快照、调用尝试、来源和评估，不拥有家庭事实；删除主体时索引、缓存、trace 一并处理 | Context/Attempt durable store 尚未完成；Gateway 仍需统一持久化和评估闭环 |
| `backend/platform/audit`、`persistence`、`idempotency` | `platform_audit_events`（WORM）、`audit_logs`（legacy）、`outbox_events`、`idempotency_keys`、UnitOfWork | 全部 S/O、O14 | 新审计表追加写且 Postgres 触发器防 UPDATE/DELETE；legacy 只读；业务写入与 outbox 同事务 | migration 0002、平台服务和测试 WIP 已有；留存归档和跨域 outbox 监控待补 |
| `backend/domains/service/application/master_data.py`、frontend data contracts | `family_activity_catalog`、服务/商品/会员/积分目录 Projection、UI-01～34 contracts | S01、S11、S12、S15-S19 | 目录主数据无 `family_id`；家庭浏览、预约、意向和消费才产生私有事实 | DEV/TEST fixture 已接；生产 SQL 目录写入、缓存失效和版本回读待补 |
| `database/baseline`、`database/migrations/versions` | 62 个历史 SQL 线性化为 151 表/7 视图；Alembic 0001 baseline、0002 audit、0003 service additions | 全部 S/O、O14 | baseline 只读、不可改写；新域变更必须是 baseline 之后的 Alembic revision；集成测试必须用 `alembic upgrade head` | 迁移骨架已存在；product_intelligence、loyalty、commerce 等后续 revision 尚未齐全 |

### WIP 冲突必须在数据层统一裁决

1. **同一概念多套表**：服务预约链与 FGCN 案件链不是两套 service 数据库，而是同一 service 域的两个聚合子链，必须通过 `ServiceCase → ServiceTask → Booking/Delivery → Quality` 关联。
2. **ORM 领先 SQL**：product_intelligence 的 `validated_by/validated_at/validation_reason`、`contradiction_models` 新字段和 `value_architectures` 等不得直接改 baseline 或私有 SQL；统一转为 baseline 后 revision。
3. **测试建库漂移**：任何集成测试若自行 `Base.metadata.create_all` 而绕过 Alembic，就不能证明生产 schema；测试环境必须从同一 migration 建库，再用 fixture 注入数据。
4. **目录与家庭事实分离**：服务、活动、商品、会员和积分规则是主数据；预约、订单意向、权益、ledger 和出席是家庭事实，禁止混表。
5. **运营智能与家庭事实分离**：product intelligence 的问题、假设、策略和 zone assessment 只能影响产品/运营决策，不能直接写入儿童画像、成长结果或商业分佣事实。

## 4. 24 个业务场景的数据架构映射

| 场景 | 权威聚合/数据表 | 关键事件 | 主要读模型 | 数据风险与 owner |
|---|---|---|---|---|
| S01 内容/活动进入 | ContentVersion、ActivitySlot、ReachEvent、EntryEvent | ContentPublished、ActivityScheduled、FamilyEntered | EntryProjection | L0/L1；content/marketing |
| S02 身份/家庭/成员 | User、Session、Family、Person、FamilyMembership、VisibilityPolicy | FamilyCreated、MemberBound、RoleGranted | FamilyHomeProjection | L1-L3；identity/tenancy/family |
| S03 测评目录/同意 | AssessmentCatalog、PurposeSelection、ConsentRecord、StartToken | ConsentGranted、ConsentRevoked、AssessmentAuthorized | AssessmentStartProjection | L2-L3；consent |
| S04 测评/证据 | AssessmentSession、Response、Submission、EvidenceSet | ResponseSaved、AssessmentSubmitted、EvidenceFrozen | AssessmentResultProjection | L3；assessment |
| S05 假设/入营 | GrowthPerspective、GrowthHypothesis、GrowthIntent、Onboarding | HypothesisProposed、HypothesisDecided、OnboardingStarted | HypothesisProjection | L3；growth |
| S06 90 天计划 | JourneyPlan、Phase、PhaseDecision、PhaseProgress | PlanCreated、PlanConfirmed、PhaseReviewed | PlanProjection | L2-L3；journey |
| S07 21 天行动 | ActionTask、TaskStarted、ActionRecord、ChallengeReview | TaskAssigned、TaskCheckedIn、ChallengeClosed | TodayTaskProjection、RhythmProjection | L2-L3；journey |
| S08 成果/故事 | ProgressReport、OutcomeRecord、FamilyStory、AnnualReview | ReportGenerated、OutcomeConfirmed、StoryWithdrawn | OutcomeProjection、StoryProjection | L2-L3；growth/community |
| S09 AI/人工升级 | AIRequest、ContextSnapshot、ModelDraft、Recommendation、HumanEscalationCase | ModelAttempted、RecommendationIssued、Escalated | AssistantProjection | L3-L4；ai_runtime |
| S10 陪跑/客服 | ServiceEntitlement、ServiceInteraction、SupportTicket、ServiceRecord | ServiceOpened、ContactRecorded、TicketClosed | ServiceJourneyProjection | L2-L3；service |
| S11 专家供给 | ProviderProfile、OfferingVersion、AvailabilitySlot | ProviderAdmitted、OfferingPublished、SlotReleased | ProviderDirectoryProjection | L1-L2；partner/service |
| S12 预约/履约 | Booking、AttendanceRecord、ServiceFeedback | BookingConfirmed、BookingCancelled、AttendanceRecorded | BookingProjection | L2-L3；service |
| S13 FGCN 交付 | ServiceCase、ServiceTask、TaskAssignment、DeliveryRecord、QualityCheck、Contribution、Allocation | CaseOpened、TaskAssigned、DeliverySubmitted、DeliveryVerified、ContributionRecorded | FGCNCaseProjection、AllocationProjection | L2-L3；service |
| S14 质量/争议 | QualitySignal、ComplaintCase、RecoveryPlan、DisputeDecision | ComplaintOpened、RecoveryApplied、DisputeDecided | QualityProjection | L2-L3；service/ops |
| S15 商品/购买意向 | ProductVersion、ProductDetail、PurchaseIntent、Eligibility | ProductPublished、IntentCreated | ProductCatalogProjection | L0-L2；commerce |
| S16 会员/权益/续购 | MembershipOrder、PaymentRecord、Membership、Entitlement、Usage、Renewal | PaymentConfirmed、EntitlementActivated、RenewalDecided | MembershipProjection | L1-L2/L4 payment；commerce |
| S17 积分/订单/对账 | OrderAsset、PointsLedgerEntry、PointsRedemption、ReconciliationCase | PointsCredited、PointsRedeemed、ReconciliationOpened | AssetProjection | L2/L4 payment；commerce/finance |
| S18 邀请/同行/激励 | InviteToken、InviteAcceptance、Cohort、IncentiveLedgerEntry、CohortExit | InviteAccepted、CohortJoined、IncentiveRecorded | CohortProjection | L1-L2；growth/commerce |
| S19 社区/审核 | Post、ModerationDecision、Interaction、Report、PostRevision、ModerationCase | PostSubmitted、PostPublished、PostWithdrawn、AppealDecided | CommunityFeedProjection | L2-L3；community/safety |
| S20 数据权利/安全 | DataSubjectRequest、RightsAssessment、ExportPackage、DeletionJob、SecurityIncident、RetentionAudit | RightsRequested、DeletionExecuted、IncidentOpened | ComplianceProjection | L3-L4；security/audit |
| S21 运营/经营指标 | OpsQueueItem、DeliveryMetric、BusinessMetric、ComplianceAlert、OperatingDecision | QueueAssigned、MetricPublished、DecisionRecorded | OpsDashboardProjection | L1-L3；ops |
| S22 AI Runtime | KnowledgeVersion、PromptVersion、ContextSnapshot、ModelAttempt、HumanReview、Evaluation | KnowledgePublished、ModelCalled、AIReviewed、EvalCompleted | AITraceProjection | L3-L4；ai_runtime |
| S23 伙伴准入/交付 | PartnerApplication、PartnerAdmission、PartnerOffering、PartnerDeliveryRecord、PartnerDecision | PartnerAdmitted、OfferingListed、PartnerSuspended | PartnerProjection | L1-L3；partner |
| S24 组织/人才/股权 | OrgCapabilityMap、CooperationAgreement、StaffAccessGrant、EquityGrant、GovernanceDecision | AgreementSigned、AccessGranted、EquityVested、GovernanceDecided | GovernanceProjection | L1-L4；governance |

## 5. 14 个平台运营场景的数据架构映射

| 运营场景 | 权威数据 | 关键事件 | 运营读模型 | 主要控制 |
|---|---|---|---|---|
| O01 账户/租户/权限 | Tenant、RoleGrant、AccountAction、AccessRevocation | TenantOpened、RoleGranted、AccessRevoked | AccessAdminProjection | 最小权限、双人审批、审计 |
| O02 内容/版本/模板 | ContentVersion、AssessmentVersion、JourneyTemplate、ReleaseDecision | VersionSubmitted、VersionPublished、VersionRolledBack | VersionOpsProjection | 版本冻结、灰度、回滚 |
| O03 活动/渠道/触达 | ChannelConfig、ActivitySlot、TouchpointAction、ActivityReview | CampaignScheduled、TouchpointSent、ActivityReviewed | CampaignOpsProjection | purpose、同意、退订、频控 |
| O04 线索/入营/留存 | FamilyLead、OnboardingFollowUp、RetentionSignal、ReactivationAction | LeadAssigned、FollowUpSent、FamilyReactivated | LifecycleOpsProjection | 线索不冒充事实、不可替家庭确认 |
| O05 工单/SLA/升级 | OpsQueueItem、Assignment、EscalationEvent、TicketClosure | TicketQueued、TicketAssigned、SlaBreached、TicketClosed | SupportOpsProjection | 高风险升级、不可静默关闭 |
| O06 供给准入 | ProviderApplication、ProviderAdmission、CapacitySchedule、ProviderDecision | ProviderApplied、ProviderAdmitted、ProviderSuspended | SupplyOpsProjection | 资质、利益冲突、离场回收 |
| O07 预约/履约/抽检 | BookingOpsView、RecoveryAction、QualitySample、FulfillmentClosure | BookingConflict、ServiceRecovered、QualitySampled | DeliveryOpsProjection | 改派/退款规则版本化 |
| O08 商品/会员/促销 | ProductVersion、BenefitVersion、CampaignVersion、EntitlementRevocation | ProductPublished、BenefitChanged、EntitlementRevoked | CommerceOpsProjection | 权益版本、预算、退订 |
| O09 支付/退款/对账 | PaymentRecord、RefundDecision、ReconciliationCase、SettlementStatement | PaymentReceived、RefundIssued、ReconciliationClosed | FinanceOpsProjection | 验签、幂等、权限分离 |
| O10 社区审核/申诉 | ModerationQueueItem、ModerationDecision、AppealDecision、PolicyChange | ModerationDecided、AppealResolved、PolicyChanged | ModerationOpsProjection | AI 辅助、人工复核、不可免审 |
| O11 权利/留存/安全 | RightsCase、AccessReview、RetentionJob、SecurityIncident | RightFulfilled、AccessReviewed、IncidentResolved | ComplianceOpsProjection | 删除可验证、事件证据保全 |
| O12 AI 知识/模型/评估 | KnowledgeVersion、PromptVersion、ModelRoutingPolicy、EvaluationRun、AIRuntimeRelease | KnowledgeReleased、ModelEvaluated、AIRuntimeRolledBack | AIOpsProjection | Gateway、红队、失败阻断发布 |
| O13 指标/实验/复盘 | MetricDefinition、Experiment、CohortInsight、OperatingDecision | MetricPublished、ExperimentStopped、DecisionRecorded | AnalyticsOpsProjection | 去标识化、不做家庭排名 |
| O14 发布/一致性/事故 | ChangeRequest、EnvironmentParityReport、AuditFinding、IncidentRecord、Postmortem | ChangeApproved、ParityVerified、IncidentOpened、PostmortemClosed | ReleaseOpsProjection | 三环境功能等价、可回滚、审计 |

## 6. 事件与存储技术契约

### 6.1 事件信封

所有跨域事件必须包含：

```text
event_id             全局唯一且不可变
event_type           版本化事件名
aggregate_type/id    权威聚合类型与标识
tenant_id/family_id  租户与家庭边界（无家庭则显式为空）
subject_id           被处理成员，尤其是儿童数据
actor_id/actor_type  发起者与角色（human/system/ai）
purpose              处理目的码
consent_version      当时生效的同意快照
occurred_at          业务发生时间
schema_version       事件 payload 版本
idempotency_key      外部重试去重键
correlation_id       跨节点追踪链
causation_id         直接因果事件
classification       L0-L4 数据级别
provenance           来源、规则/模型/人工依据
environment          dev/test/prod，仅用于审计，不改变业务语义
```

### 6.2 写入与读取规则

- 权威写入：领域应用服务 → 聚合事务 → Outbox；不允许 UI、报表或 AI 直接写表。
- 消费：Inbox 以 `event_id` 幂等；失败进入重试队列和死信队列，不能静默丢弃。
- 修正：事实表不覆盖原值，使用 `CorrectionEvent` 或版本记录；读模型可重放。
- 查询：跨域只返回 DTO/Projection，不泄露 ORM 实体、未授权字段或原始 prompt。
- 文件与媒体：对象存储保存加密对象，数据库只保存 URI、hash、分类、owner、purpose 和留存到期日。
- 搜索/向量：只存经过 purpose/consent 过滤的脱敏文本；索引不是事实源，删除请求必须级联到索引和缓存。

## 7. 留存、删除与级联规则

| 数据类别 | 默认留存起点 | 默认策略 | 删除/撤回动作 |
|---|---|---|---|
| 公开内容与版本 | 下线日 | 按版权/合同期限 | 下线投影，保留版本审计 |
| 账户与家庭档案 | 账户关闭日 | 业务关系存续 + 法定期限 | 匿名化或删除，保留必要审计 |
| 儿童测评/成长材料 | 服务结束或撤回日 | 目的期限 + 最短必要期 | 停止新增处理，删除主表/缓存/索引 |
| 预约/服务/质量 | 服务关闭日 | 合同、争议和财务期限 | 到期删除可识别附件，保留聚合统计 |
| 订单/支付/结算 | 交易完成日 | 财务法定留存 | 令牌化；不可删除的分录脱敏 |
| 社区内容与审核 | 撤回/处置日 | 申诉期 + 安全审计期 | 停止曝光，媒体和搜索索引级联处理 |
| AI prompt/trace | 调用日 | 评估/安全所需最短期限 | 脱敏或删除原文，保留不可逆统计 |
| 安全/审计日志 | 事件关闭日 | 安全与合规期限 | 只允许受控归档，不由业务角色覆盖 |

删除作业必须有范围评估、法定留存例外、幂等 job、校验报告和完成事件；不能只删除一张主表。

## 8. UI 读模型匹配（34 个基线屏幕）

| UI | 主要 Projection | UI | 主要 Projection |
|---|---|---|---|
| UI-01 | FamilyHomeProjection | UI-18 | MembershipProjection |
| UI-02 | AssessmentProjection | UI-19 | ProviderDirectoryProjection |
| UI-03 | HypothesisProjection、AssistantProjection | UI-20 | AvailabilityProjection |
| UI-04 | PlanProjection | UI-21 | BookingPreviewProjection |
| UI-05 | JourneyProjection、ServiceJourneyProjection | UI-22 | ActivityProjection、ProviderDirectoryProjection |
| UI-06 | MembershipProjection、ServiceEntitlementProjection | UI-23 | ActivityDetailProjection |
| UI-07 | AssessmentCatalogProjection | UI-24 | ServiceCustomerProjection、QualityProjection |
| UI-08 | ProgressReportProjection | UI-25 | CommunityFeedProjection |
| UI-09 | TodayTaskProjection | UI-26 | ActionRecordProjection、PostProjection |
| UI-10 | AssistantProjection、ActionRecordProjection | UI-27 | CommunityPostProjection |
| UI-11 | RhythmProjection（不含总分/排名） | UI-28 | CommunityProfileProjection |
| UI-12 | FamilyStoryProjection | UI-29 | OutcomeProjection |
| UI-13 | ProductCatalogProjection | UI-30 | RenewalProjection、MembershipProjection |
| UI-14 | ProductDetailProjection、PurchaseIntentProjection | UI-31 | ServiceRecordProjection |
| UI-15 | InviteProjection | UI-32 | AssetProjection、OrderProjection |
| UI-16 | CohortProjection | UI-33 | FamilyProfileProjection、RightsProjection |
| UI-17 | PointsLedgerProjection | UI-34 | ServiceRecordProjection、QualityProjection |

UI 投影必须可由权威表和事件重建；没有真实 ledger、订单或服务记录时返回显式 `NOT_AVAILABLE`，禁止硬编码余额、积分、排名或服务结果。

## 9. 测试环境与生产环境的数据等价

| 项目 | 开发/测试 | 生产 | 必须相同 |
|---|---|---|---|
| schema/migration | 同一 Alembic revision | 同一 Alembic revision | 表结构、约束、索引、枚举 |
| API/workflow | 同一路由、状态机、错误码 | 同一路由、状态机、错误码 | 功能行为和拒绝路径 |
| 权限/同意/审计 | 同一 policy，使用模拟主体 | 同一 policy，真实主体 | 授权边界、审计字段 |
| 数据 | 工厂生成的合成家庭/订单/服务 | 真实业务数据 | 字段形状、关系、生命周期 |
| 外部适配器 | sandbox/noop/fake，保留失败回调 | 真实支付、消息、模型供应商 | port、重试、幂等、超时、错误语义 |
| AI | 固定模型桩或受控 sandbox | 合规模型 Gateway | provenance、人工升级、拒答路径 |
| 删除/事故 | 使用合成数据演练真实 job | 真实删除和事故流程 | job、审计、校验、回滚 |

测试环境禁止通过 `/dev` 路由、静态 JSON 或缺少权限/审核/支付节点来“阉割”功能。允许模拟的是数据和外部副作用，不允许模拟业务状态机本身。

## 10. 当前实现缺口与数据架构施工顺序

1. **P0 数据契约**：为 S02-S07/O01/O02/O04/O05 建立 Family、Consent、Assessment、Growth、Journey、Action、OpsQueue 的 SQLAlchemy 模型、事件信封和测试 fixture。
2. **P1 服务数据**：为 S10-S14/O06/O07 建立 Booking、ServiceCase、Task、Delivery、Quality、Complaint、Contribution 聚合和验收事件。
3. **P2 商业数据**：为 S15-S18/O08/O09 建立 Product、Order、Payment、Membership、Entitlement、PointsLedger、Reconciliation；在 ledger 未存在前，UI-17/32 只能返回显式不可用。
4. **P3 信任数据**：为 S19/S20/S22/O10/O11/O12 建立 Community、Rights、Retention、SecurityIncident、Knowledge、Prompt、Evaluation 数据链。
5. **P4 运营与伙伴**：为 S21-S24/O03/O13/O14 建立指标、实验、伙伴、组织、变更、环境一致性和事故复盘数据。

当前可确认的真实切片仍主要是 S04 测评；其余场景的“有 UI/有 DTO”不等于权威数据、事件、留存和运营闭环已经实现。

## 11. 从工作稿升为数据基线的验收条件

- 每个 S/O 场景至少有一个权威聚合、一个成功事件、一个拒绝/失败事件和一个可重建 Projection；
- 每个写入动作具备 `tenant_id/family_id/actor/purpose/consent_version/idempotency_key`；
- 每个 L3/L4 字段完成脱敏、访问审计、留存和删除级联设计；
- 每个跨域读取通过 Query Port 或事件投影，不跨 schema 直写；
- 开发、测试、生产执行同一 migration、API、状态机、权限和审计验收；
- 架构测试能证明 24 个 S、14 个 O、34 个 UI 均被覆盖，且禁止家庭总分/排名与硬编码权益余额回归。

## 12. 主数据与业务数据分层

仅列出“数据域”和“聚合”还不够。每个流程必须区分可复用、版本化的主数据与由家庭/运营动作产生的业务数据；二者不能共表、共写入者或互相冒充。

### 12.1 两类数据的边界

| 类型 | 定义 | 典型内容 | 写入方式 | 生命周期 | 禁止事项 |
|---|---|---|---|---|---|
| 主数据（Master Data） | 被多个流程复用、相对稳定、具有唯一身份和版本的业务对象 | 角色、目的、测评版本、内容版本、服务供给、商品、会员权益、积分规则、伙伴资质 | 由对应运营/治理域以版本化命令发布 | 发布、冻结、下线、归档 | 不携带某次家庭交易结果；不因一次订单/预约而覆盖历史版本 |
| 业务数据（Business Data） | 某个家庭、主体、案件或运营任务在流程中产生的事实、交易和决定 | 成员关系、同意、回答、计划、行动、预约、交付、支付、积分账本、帖子、权利请求 | 由场景 L5 Command/API 经聚合事务写入 | 创建、状态迁移、完成/撤回、纠错、留存/删除 | 不由 UI、AI、报表或投影直接写入；不得把意向当成交付/收入 |
| 配置/策略数据（Policy & Configuration） | 决定流程如何执行但不代表业务事实 | 权限策略、SLA、审核规则、路由策略、留存策略、实验护栏 | 治理审批后版本化发布 | 生效、替换、回滚 | 不得隐藏在代码常量中；不得回写历史事实 |
| 派生数据（Projection/Analytics） | 从主数据、业务数据和事件重建的读取结果 | UI 投影、运营队列、指标、分群洞察、缓存、搜索索引 | 事件消费者/查询服务重建 | 可重放、可失效、可删除 | 不是事实源；不得反向修改主数据或业务数据 |

### 12.2 主数据 → 业务数据 → 事件 → 投影的固定链路

```text
主数据/策略版本
   ↓（选择、校验、冻结）
L5 Command/API + Policy
   ↓（聚合内事务）
业务数据事实/交易状态
   ↓（同事务 Outbox）
Domain Event + AuditEvent
   ↓（幂等消费）
UI Projection / Ops Projection / Analytics Projection
```

固定规则：

1. 主数据必须有 `version_id`、`status`、`effective_from/to`、`owner` 和发布/回滚记录；业务记录必须保存实际使用的主数据版本。
2. 业务数据必须有 `tenant_id`、`family_id`（无家庭时显式为空）、`subject_id`、`actor_id`、`purpose`、`consent_version`、`idempotency_key`。
3. 主数据变更只影响后续新业务；已产生的业务事实保留其版本快照，不能被“最新配置”回写。
4. 任何业务写入都同时产生成功事件、拒绝/失败事件或补偿事件，并写入审计；投影只消费事件，不跨域直写。
5. 开发、测试、生产使用同一主数据 schema、业务 schema、版本状态机和规则；测试只替换主数据内容、业务主体和外部适配器。

### 12.3 15 个数据域的主数据/业务数据目录

| 数据域 | 主数据（可复用/版本化） | 业务数据（流程事实/交易） | 权威 owner | 主要消费方 |
|---|---|---|---|---|
| identity/tenancy | 角色定义、权限资源、目的目录、租户目录、身份验证策略 | User、Session、FamilyMembership、RoleGrant、AccountAction、AccessRevocation | identity/tenancy | S02、S20、O01 |
| family | 地区/关系/生命周期枚举、家庭档案字段字典 | Family、Person、FamilyRelationship、LifeStageAssignment、FamilyProfileChange | family | S02、S05、S08、S20 |
| consent | PrivacyNotice、PurposeDefinition、ConsentPolicy、监护关系类型 | ConsentRecord、PurposeSelection、ConsentGrant/Revoke、ConsentSnapshot | consent | S03、S09、S20、O11 |
| assessment | AssessmentTool、AssessmentVersion、Question、Scoring/解释规则 | AssessmentSession、Response、Submission、EvidenceSet、AssessmentOperation | assessment | S03-S05、S09 |
| content/program | ContentVersion、ActivityTemplate、JourneyTemplate、TaskTemplate、BlueprintVersion | ReachEvent、EntryEvent、Onboarding、TemplateUsage | content/program | S01、S05-S07、O02/O03 |
| growth | 主题/需要/Outcome 类型、解释词典、风险分级 | GrowthPerspective、GrowthHypothesis、GrowthIntent、OutcomeRecord、FamilyStory | growth | S05-S09、S18 |
| journey/action | 行动类型、阶段模板、日程规则、提醒策略 | JourneyPlan、Phase、ActionTask、ActionRecord、PhaseDecision、ChallengeReview | journey | S06-S08、O04 |
| service/partner | ServiceType、OfferingVersion、SLA、QualityPolicy、Qualification、CapacityRule | ServiceEntitlement、ServiceCase、ServiceTask、Booking、Attendance、Delivery、Quality、Contribution | service/partner | S10-S14、S23、O05-O07 |
| commerce | ProductVersion、Price、BenefitVersion、Promotion/Campaign、Tax/RefundPolicy | PurchaseIntent、Order、Payment、Refund、Entitlement、Usage、Renewal | commerce | S15-S18、O08/O09 |
| membership | TierDefinition、BenefitDefinition、MembershipRule | Subscription、Period、TierTransition、BenefitGrant/Reservation/Ledger、Usage | membership | S16-S17、O08/O09 |
| loyalty_points | EarnRule、RedemptionItem、ExpiryRule、LimitPolicy | PointsAccount、PointsLedger、Redemption、ReconciliationCase | loyalty_points | S17-S18、O08/O09 |
| community | VisibilityType、ModerationPolicy、ReportType、InteractionPolicy | Post、PostRevision、Interaction、Report、ModerationCase、Appeal | community | S19、O10 |
| ai_runtime | KnowledgeVersion、PromptVersion、ModelRegistry、RoutingPolicy、EvaluationPolicy | AIRequest、ContextSnapshot、ModelAttempt、ModelDraft、HumanReview、EvaluationRecord | ai_runtime | S09、S22、O12 |
| ops/analytics | QueueType、SLA、MetricDefinition、ExperimentGuardrail、CohortPolicy | OpsQueueItem、Assignment、MetricSnapshot、CohortInsight、OperatingDecision | ops | S21、O03-O07、O13 |
| security/audit | DataClassification、RetentionPolicy、LegalHold、IncidentSeverity、AuditSchema | DataSubjectRequest、RightsAssessment、DeletionJob、SecurityIncident、AuditEvent、Postmortem | security/audit | S20、O11、O14 |

完整的场景级和节点级映射见 `docs/07_data/MASTER_AND_BUSINESS_DATA_DECOMPOSITION.md`；该文件按 P01-P06、S01-S24、O01-O14 展开每个节点的主数据输入、业务数据写入、状态、事件、投影和控制。

对象、物理表、主外键、基数、删除策略和当前落地状态详见 `docs/07_data/DATA_OBJECT_TABLE_RELATIONSHIP_CATALOG.md`。本文件与该目录的关系是：本文件回答“场景需要哪些数据”，对象/表/关系目录回答“这些数据具体落在哪个对象、哪张表、如何关联”。

## 13. 数据架构分解的实现验收

每个 L4 节点只有在以下数据链路均存在时，才算“数据能力完成”：

```text
主数据版本/策略
 → 输入 DTO + purpose/consent/idempotency
 → 聚合写入业务事实
 → 状态迁移与拒绝码
 → Success/Failure/Compensation Event
 → AuditEvent + Outbox
 → Projection/Query DTO
 → 留存、删除、重放和环境等价测试
```

验收台账必须逐项填写：`scenario_id`、`process_level`、`node_id`、`master_data_ids`、`business_aggregate`、`command`、`pre_state`、`post_state`、`success_event`、`failure_event`、`projection`、`classification`、`retention_policy`、`test_fixture`、`implementation_status`。只填“有表/有 DTO/有 UI”不能通过验收。

## 14. 与应用架构的对齐

应用架构不新增数据事实，只负责通过用例和工作流使用本文件定义的对象、表和关系。对应关系如下：

```text
应用 A3 Command/Query
   → 数据对象（主数据选择 + 业务聚合）
   → 应用 A4 Workflow/Policy
   → 同事务写入业务表 + Outbox + Audit
   → 应用 A5 Projection/Query DTO
```

| 应用模块 | 主写入数据域 | 允许写入的业务数据 | 只读数据 | 明确禁止 |
|---|---|---|---|---|
| `EntryApplication` | identity/tenancy/family/consent | Family、Person、Membership、Consent、Reach/Lead | Content/Activity 目录 | 写测评回答、订单、Outcome |
| `GrowthApplication` | assessment/growth/journey | Session、Response、Evidence、Intent、Plan、Action、Outcome 请求 | 目的、模板、AI Perspective | AI Draft 直写 Fact，写服务/支付表 |
| `ServiceCollaborationApplication` | service/partner | Booking、Case、Task、Assignment、Delivery、Quality、Contribution | Family Intent、Offering、Entitlement | 写 Order/Payment，自动结算 |
| `CommerceRelationshipApplication` | commerce/membership/loyalty | Intent、Order、Payment、Entitlement、Subscription、Ledger、Invite | Product/Benefit/Promotion 主数据 | 向孩子做画像商业营销，写家庭排名 |
| `CommunityTrustApplication` | community/security/audit | Post、Moderation、Rights、Deletion、Incident | Family/Consent/Retention Policy | 删除审计/支付法定记录 |
| `OperationsGovernanceApplication` | ops/ai_runtime/governance | Queue、Metric、Experiment、Evaluation、Agreement、Change、Postmortem | 所有域的事件/投影 | 把指标当结果，把运营智能写入成长事实 |

`S16` 的数据主写入者固定为 `CommerceRelationshipApplication`（`P04/VS-03`）；Growth/Service 只能通过 `Entitlement` Query Port 读取可用权益，不能创建或修改会员事实。详细应用层映射见 `docs/06_platform/APPLICATION_ARCHITECTURE.md`。
