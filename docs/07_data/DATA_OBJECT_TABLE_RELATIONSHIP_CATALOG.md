---
id: DATA-OBJECT-TABLE-RELATION-001
title: AiFamily 数据对象、数据表与数据关系目录
type: data
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: null
---

# AiFamily 数据对象、数据表与数据关系目录

> 本目录把业务架构和流程架构继续向下落到三种可执行定义：**数据对象**回答“业务上是什么”，**数据表**回答“如何持久化”，**数据关系**回答“谁拥有谁、基数是多少、何时可删除”。表名优先采用当前 baseline/WIP 的真实名称；没有落地表的对象明确标记 `TARGET_REQUIRED`，不把设计对象冒充已实现能力。

## 1. 目录规则

### 1.1 三种视图

```text
业务对象（Object）
  └─ 一个或多个聚合/事实/版本
       └─ 一个或多个物理表（Table）
            └─ 主键、外键、唯一约束、状态机、审计与留存
```

### 1.2 表状态

| 标记 | 含义 |
|---|---|
| `BASELINE` | `database/baseline` 已有表，需按线性化迁移执行 |
| `WIP_ORM` | Python WIP 已有 ORM/仓储，但 Alembic revision 或生产接线未完成 |
| `TARGET_REQUIRED` | 业务架构要求存在，当前尚无可证明的权威表 |
| `PROJECTION` | 派生读模型/视图，可删除、可重放，不是事实源 |
| `LEGACY_READONLY` | 迁移兼容表，只读或待退役，禁止新增业务写入 |

### 1.3 全表共同字段

所有家庭/运营业务表必须有或能通过关联获得：

```text
tenant_id、family_id（无家庭时显式为空）、subject_person_id（适用时）
actor_id/actor_type、purpose、consent_version、source_system、environment
correlation_id、idempotency_key、provenance、classification、created_at
```

主数据表另外必须有：

```text
version_id/version_no、status、effective_from、effective_to、owner
approved_by、approved_at、rollback_of、row_version
```

## 2. 数据对象 → 数据表目录

### 2.1 身份、租户、家庭与同意

| 业务对象 | 类型 | 权威物理表 | 主键 | 关键外键/唯一关系 | 状态 |
|---|---|---|---|---|---|
| Tenant | 主体/主数据 | `tenants` | `tenant_id` | — | BASELINE |
| Account | 主体 | `accounts` | `account_id` | 与 `persons` 通过绑定表关联 | BASELINE |
| UserSession | 业务事实 | `identity_sessions`、`sessions`（兼容） | `session_id` | `account_id`、`tenant_id` | BASELINE/LEGACY_READONLY |
| OTPChallenge | 业务事实 | `otp_challenges` | `challenge_id` | `account_id`/联系方式引用 | BASELINE |
| Person | 主体主数据 | `persons` | `person_id` | `family_id → families` | BASELINE |
| Family | 主体主数据 | `families` | `family_id` | `primary_contact_person_id → persons`（可延迟 FK） | BASELINE |
| AccountPersonBinding | 业务关系 | `account_person_bindings` | `(account_id, person_id)` | `account_id → accounts`、`person_id → persons` | BASELINE |
| FamilyMembership | 业务关系 | `family_memberships` | `membership_id` | `family_id`、`person_id`、`invited_by_person_id` | BASELINE |
| TenantAccountMembership | 业务关系 | `tenant_account_memberships` | `tenant_account_membership_id` | `tenant_id`、`account_id` | BASELINE |
| TenantFamilyBinding | 业务关系 | `tenant_family_bindings` | `tenant_family_binding_id` | `tenant_id`、`family_id` | BASELINE |
| FamilyRelationship | 业务事实 | `family_relationships` | `relationship_id` | `family_id`、`person_a_id`、`person_b_id` | BASELINE |
| LifeStageAssignment | 业务事实 | `life_stage_assignments` | `assignment_id` | `family_id`、`child_id → persons` | BASELINE |
| RoleDefinition | 主数据 | `family_reference_code_sets`、`family_reference_code_values` | `(set_ref, code)` | `validation_rules` 约束取值 | BASELINE |
| VisibilityPolicy | 策略/业务授权 | `tenant_policy_profiles`、`case_access_grants` | policy/grant id | `tenant_id`、资源引用 | BASELINE/WIP_ORM |
| PurposeDefinition/PrivacyNotice | 主数据/策略 | `family_reference_code_sets`（目标独立表待补） | versioned code | ConsentGate 读取 | TARGET_REQUIRED |
| ConsentRecord | 业务事实 | `consents` | `consent_id` | `family_id`、`subject_person_id`、`guardian_person_id` | BASELINE |
| ConsentSnapshot | 事件/业务快照 | `multimodal_consents` 等场景快照；目标统一表待补 | snapshot id | 关联 `consent_id`/purpose/version | WIP_ORM/TARGET_REQUIRED |

### 2.2 测评、成长、计划与行动

| 业务对象 | 类型 | 权威物理表 | 主键 | 关键外键/唯一关系 | 状态 |
|---|---|---|---|---|---|
| AssessmentToolVersion | 主数据 | `family_assessment_tools` | `(tool_ref, version_no)` | 题目/边界 JSON，版本唯一 | BASELINE |
| AssessmentSession | 业务聚合 | `family_assessment_sessions` | `assessment_session_id` | `tenant_id/family_id/subject_person_id`、tool version | BASELINE |
| AssessmentResponse | 业务事实 | `family_assessment_responses` | `assessment_response_id` | `assessment_session_id`、`author_person_id` | BASELINE |
| AssessmentOperation | 幂等业务事实 | `family_assessment_operations` | `assessment_operation_id` | session、family、`(action_name,idempotency_key)` 唯一 | BASELINE |
| EvidenceSet | 事实证据 | `evidence_records`、`family_assessment_evidence`（目标统一） | `evidence_id` | family、来源引用 | BASELINE/TARGET_REQUIRED |
| AssessmentAIRun | AI 派生追踪 | `family_assessment_ai_runs` | `assessment_ai_run_id` | session、evidence、family | BASELINE |
| CapabilityMemoryAsset | 主数据 | `family_assessment_capability_memory_assets` | `memory_asset_id` | capability/version/kind 唯一 | BASELINE |
| GrowthProfile | 派生/业务快照 | `growth_profiles` | `profile_id` | family、subject、前一版本 | BASELINE/LEGACY_READONLY |
| GrowthProfileDimension | 业务子对象 | `growth_profile_dimensions` | `(profile_id, dimension_id)` | `profile_id → growth_profiles` | BASELINE |
| GrowthPriority | 家庭确认事实 | `growth_priorities` | `priority_id` | profile、family | BASELINE |
| GrowthNeedInput | 原始输入事实 | `growth_need_inputs` | `input_id` | family、subject、actor | BASELINE |
| GrowthNeedSignal | 推断 Perspective | `growth_need_signals` | `signal_id` | `raw_ref → growth_need_inputs` | BASELINE |
| GrowthIntent | 家庭确认意图 | `growth_intents` | `intent_id` | signal、family、subject、confirmed_by | BASELINE |
| EligibilityEvaluation | 资格判断事实 | `eligibility_evaluations` | `eligibility_evaluation_ref` | intent、offer snapshot | BASELINE |
| ResourceRecommendation | 推荐快照 | `resource_recommendations` | `recommendation_id` | intent | BASELINE |
| FamilyServiceDecision | 家庭选择事实 | `family_service_decisions` | `decision_id` | intent、recommendation、actor | BASELINE |
| GrowthJourneyLegacy | 兼容聚合 | `growth_journeys` | `journey_id` | family | BASELINE/LEGACY_READONLY |
| JourneyPlan | 90 天计划聚合 | `family_journey_plans` | `plan_id` | `onboarding_id → growth_journeys`、priority | BASELINE |
| JourneyPhase | 计划子对象 | `family_journey_plan_phases` | `plan_phase_id` | `plan_id → family_journey_plans` | BASELINE |
| ActionTask/ActionRecord | 21 天行动事实 | `growth_actions`、`growth_events` | `action_id`/`event_id` | journey、plan、intervention、assigned person | BASELINE |
| InterventionDefinition | 主数据 | `interventions` | `intervention_id` | 生命周期/适用阶段 | BASELINE |
| GrowthReview/PhaseDecision | 复盘事实 | `growth_reviews`、`next_step_decisions` | review/decision id | journey、phase、priority | BASELINE |
| OutcomeRecord | Outcome 事实 | `outcomes`、`outcome_observations` | `outcome_id`/`observation_id` | family、subject、journey/episode | BASELINE |
| FamilyStory | 业务内容 | `family_stories`（目标表） | `story_id` | family、owner、媒体引用 | TARGET_REQUIRED |

### 2.3 内容、服务、伙伴与 FGCN

| 业务对象 | 类型 | 权威物理表 | 主键 | 关键外键/唯一关系 | 状态 |
|---|---|---|---|---|---|
| ContentVersion | 主数据 | `family_curriculum_drafts`、`family_admitted_catalog_items`（目标统一） | content/version | 内容/版权/适用范围 | BASELINE/TARGET_REQUIRED |
| ActivityTemplate/Slot | 主数据/库存 | `family_activity_catalog`、`family_page_task_items`（目标拆分） | activity/slot id | 活动版本、容量、时区 | BASELINE/TARGET_REQUIRED |
| ChannelConfig | 主数据 | `channel_configs`（目标表） | `channel_id` | 归因、频控、退订策略 | TARGET_REQUIRED |
| ServiceProvider | 供给主数据 | `family_service_providers`、`provider_profiles` | provider id | tenant/资质引用 | BASELINE/WIP_ORM |
| ServiceOfferingVersion | 供给主数据 | `family_service_offerings` | `service_offering_id` | provider、版本、价格/SLA | BASELINE |
| AvailabilitySlot | 供给库存 | `family_service_availability_slots` | `availability_slot_id` | provider、offering | BASELINE |
| BookingRequest | 家庭业务事实 | `family_booking_requests` | `booking_request_id` | family、offering、slot | BASELINE |
| Attendance/ServiceRecord | 履约事实 | `family_booking_service_records`、`family_service_records` | record id | booking/case、family | BASELINE/TARGET_REQUIRED |
| ServiceBlueprintVersion | FGCN 主数据 | `service_collaboration_blueprints` | `(blueprint_ref, version)` | 任务模板、角色、分配/释放策略 | BASELINE |
| ServiceCase | FGCN 业务聚合 | `service_cases` | `case_id` | family、intent、plan、blueprint snapshot | BASELINE |
| ServiceTask | FGCN 任务事实 | `service_tasks` | `task_id` | `case_ref → service_cases`、rework self-FK | BASELINE |
| TaskAssignment | 责任关系事实 | `task_assignments` | `assignment_id` | task、assignee；一个 ACCEPTED 唯一 | BASELINE |
| DeliveryRecord | 交付事实 | `service_deliveries`（目标表；当前 deliverable JSON 在 task） | `delivery_id` | task/assignment、媒体/版本 | TARGET_REQUIRED |
| TaskQualityReview | 质量事实 | `task_quality_reviews` | `quality_review_id` | task、reviewer | BASELINE |
| ServiceContribution | 贡献事实 | `service_contributions` | `contribution_id` | case、task/provider、`delivery_ref` 来源引用 | BASELINE + 0004 |
| AllocationRun | 分配批次 | `service_case_allocation_runs` | `allocation_run_id` | case 唯一、policy snapshot | BASELINE |
| ContributionAllocation | 分配依据 | `service_contribution_allocations` | `allocation_id` | case/task/contribution/allocation run | BASELINE |
| Complaint/Recovery/Dispute | 质量争议事实 | `quality_signals`、`complaint_cases`、`recovery_plans`、`dispute_decisions`（目标表） | 各自 id | service/case、证据引用 | TARGET_REQUIRED |
| PartnerApplication/Admission | 伙伴业务事实 | `partner_applications`、`partner_admissions`（目标表） | application/admission id | organization、agreement | TARGET_REQUIRED |
| PartnerAgreement | 主数据/合同事实 | `cooperation_agreements`（目标表） | agreement id | partner、DPA/SLA、有效期 | TARGET_REQUIRED |

### 2.4 商品、会员、积分与资产

| 业务对象 | 类型 | 权威物理表 | 主键 | 关键外键/唯一关系 | 状态 |
|---|---|---|---|---|---|
| ProductOfferingVersion | 主数据 | `family_product_offerings` | `product_id` | tenant scope、版本/价格快照 | BASELINE/WIP_ORM |
| ProductEvent | 业务/集成事实 | `family_product_events` | `event_id` | product、source page、envelope | BASELINE |
| PurchaseIntent | 家庭意向事实 | `family_order_intents` | `order_intent_id` | family、actor、product | BASELINE/WIP_ORM |
| PurchaseIntentLine | 意向子对象 | `family_order_intent_lines` | `line_id` | order intent、product | BASELINE |
| Order | 交易聚合 | `orders`（目标表） | `order_id` | payer、family、line | TARGET_REQUIRED |
| PaymentRecord | 支付事实 | `payments`（目标表） | `payment_id` | order、provider event、idempotency | TARGET_REQUIRED |
| RefundRecord/Decision | 退款事实 | `refunds`、`refund_decisions`（目标表） | refund/decision id | payment/order、审批人 | TARGET_REQUIRED |
| Entitlement | 权益事实 | `family_entitlements` | `entitlement_id` | source order intent、family | BASELINE/WIP_ORM |
| MembershipPlan | 会员主数据 | `family_membership_plans` | `plan_id` | plan/version | BASELINE/WIP_ORM |
| TierDefinition | 会员主数据 | `family_membership_tier_definitions` | `tier_definition_id` | plan、tier/version | WIP_ORM/PENDING_MIGRATION |
| BenefitDefinition | 权益主数据 | `family_membership_benefit_definitions` | `benefit_definition_id` | plan、benefit/version | BASELINE/WIP_ORM |
| MembershipSubscription | 会员业务聚合 | `family_membership_subscriptions` | `membership_subscription_id` | family、plan、payer | BASELINE/WIP_ORM |
| MembershipPeriod | 会员周期事实 | `family_membership_periods` | `membership_period_id` | subscription | WIP_ORM/PENDING_MIGRATION |
| BenefitGrant/Reservation | 权益使用事实 | `family_membership_benefit_grants`、`family_membership_benefit_reservations` | grant/reservation id | subscription、benefit definition/grant | BASELINE/WIP_ORM |
| BenefitLedgerEntry | 权益账本事实 | `family_membership_benefit_ledger` | `membership_benefit_ledger_id` | grant、source page | BASELINE/WIP_ORM |
| PointsEarnRule | 积分主数据 | `family_loyalty_points_earn_rules` | `rule_id` | rule/version | WIP_ORM/PENDING_MIGRATION |
| RedemptionCatalogItem | 积分主数据 | `family_loyalty_points_redemption_items` | `item_id` | item/version | WIP_ORM/PENDING_MIGRATION |
| PointsAccount | 积分业务聚合 | `family_loyalty_points_accounts` | `points_account_id` | family | WIP_ORM/PENDING_MIGRATION |
| PointsLedgerEntry | 积分账本事实 | `family_loyalty_points_ledger` | `ledger_id` | account、rule/redemption/evidence | WIP_ORM/PENDING_MIGRATION |
| PointsRedemption | 积分兑换事实 | `family_loyalty_points_redemptions` | `redemption_id` | account/item/ledger | WIP_ORM/PENDING_MIGRATION |
| ReconciliationCase/Settlement | 财务运营事实 | `reconciliation_cases`、`settlement_statements`（目标表） | case/statement id | order/payment/ledger/contribution | TARGET_REQUIRED |
| Invite/Cohort/Incentive | 关系增长事实 | `invite_tokens`、`cohort_memberships`、`incentive_ledger_entries`（目标表） | 各自 id | inviter/invitee、family/cohort | TARGET_REQUIRED |

### 2.5 社区、AI、运营与安全

| 业务对象 | 类型 | 权威物理表 | 主键 | 关键外键/唯一关系 | 状态 |
|---|---|---|---|---|---|
| Post/PostRevision | 社区业务事实 | `community_posts`、`community_post_revisions`（目标表） | post/revision id | family、author、parent post | TARGET_REQUIRED |
| Interaction/Report | 社区业务事实 | `community_interactions`、`community_reports`（目标表） | interaction/report id | post、actor | TARGET_REQUIRED |
| ModerationCase/Decision/Appeal | 审核业务事实 | `moderation_cases`、`moderation_decisions`、`appeal_decisions`（目标表） | 各自 id | post/report、reviewer | TARGET_REQUIRED |
| KnowledgeVersion | AI 主数据 | `knowledge_versions`（目标表） | knowledge/version | source/license/expiry | TARGET_REQUIRED |
| PromptVersion | AI 主数据 | `prompt_versions`（目标表） | prompt/version | use case、owner | TARGET_REQUIRED |
| ModelRegistry/RoutingPolicy | AI 主数据/策略 | `model_registry`、`model_routing_policies`（目标表） | model/policy id | provider/risk/cost | TARGET_REQUIRED |
| AIRequest/ConversationTurn | AI 业务事实 | `ai_requests`、`conversation_turns`（目标表） | request/turn id | family、actor、purpose | TARGET_REQUIRED |
| ContextSnapshot | AI 处理快照 | `context_snapshots`（目标表） | `context_snapshot_id` | request、授权事实、subject | TARGET_REQUIRED |
| ModelAttempt/ModelDraft | AI 追踪/派生 | `principal_model_attempts`、`family_assessment_ai_runs` | attempt/run id | request/context/evidence | BASELINE/TARGET_REQUIRED |
| HumanReview/Evaluation | AI 人工与评估事实 | `human_review_decisions`、`evaluation_runs`（目标表） | review/eval id | draft/model version | TARGET_REQUIRED |
| OpsQueueItem/Assignment | 运营业务事实 | `ops_queue_items`、`ops_assignments`（目标表） | queue/assignment id | source aggregate、owner/SLA | TARGET_REQUIRED |
| MetricDefinition | 运营主数据 | `metric_definitions`（目标表） | metric/version | event schema、口径 | TARGET_REQUIRED |
| MetricSnapshot/CohortInsight/OperatingDecision | 运营分析事实 | `metric_snapshots`、`cohort_insights`、`operating_decisions`（目标表） | 各自 id | metric/experiment/decision | TARGET_REQUIRED |
| DataSubjectRequest/RightsAssessment | 数据权利事实 | `data_subject_requests`、`rights_assessments`（目标表） | request/assessment id | subject、purpose/legal hold | TARGET_REQUIRED |
| DeletionJob/RetentionAudit | 留存作业事实 | `deletion_jobs`、`retention_audits`（目标表） | job/audit id | request、policy、scope | TARGET_REQUIRED |
| SecurityIncident | 安全事件事实 | `security_incidents`（目标表） | `incident_id` | alert、evidence、severity | TARGET_REQUIRED |
| AuditEvent | 审计事实 | `platform_audit_events`、`audit_logs`（legacy） | `audit_event_id`/`log_id` | polymorphic resource reference | BASELINE/LEGACY_READONLY |
| OutboxEvent/IdempotencyKey | 集成控制事实 | `outbox_events`、`idempotency_keys` | event/key id | aggregate/correlation/action | BASELINE |

### 2.6 孩子、家长与家庭关系记忆体

| 业务对象 | 类型 | 权威物理表 | 主键 | 关键外键/唯一关系 | 状态 |
|---|---|---|---|---|---|
| MemoryCandidate | AI/家庭确认候选 | `memory_candidates`（目标表） | `candidate_id` | tenant/family/subject/purpose/idempotency | TARGET_REQUIRED |
| MemoryConsent | 授权事实 | `memory_consents`（目标表） | `memory_consent_id` | candidate、subject、purpose、consent_version | TARGET_REQUIRED |
| ChildMemory | 家庭记忆事实 | `child_memory_items`（目标表） | `memory_id` | candidate、child subject、deletion_ref | TARGET_REQUIRED |
| GuardianMemory | 家庭记忆事实 | `guardian_memory_items`（目标表） | `memory_id` | candidate、guardian subject、deletion_ref | TARGET_REQUIRED |
| RelationshipMemory | 家庭关系记忆事实 | `family_relationship_memory_items`（目标表） | `memory_id` | candidate、≥2 subjects、family | TARGET_REQUIRED |
| MemoryRetrieval | AI/应用访问审计 | `memory_retrievals`（目标表） | `retrieval_id` | memory、purpose、actor、context snapshot | TARGET_REQUIRED |
| MemoryCorrection | 纠正/撤回事实 | `memory_corrections`（目标表） | `correction_id` | memory/candidate、actor、reason | TARGET_REQUIRED |
| MemoryDeletionJob/Proof | 删除作业/证明 | `memory_deletion_jobs`、`memory_deletion_proofs`（目标表） | job/proof id | source + derived media/embedding/cache refs | TARGET_REQUIRED |
| MediaAsset/Transcript | 多模态原文及派生 | `media_assets`、`media_transcripts`（目标表） | media/transcript id | provenance、locale、retention、deletion_ref | TARGET_REQUIRED |

## 3. 数据关系目录

### 3.1 主体与家庭关系

| 父对象 | 子对象 | 基数 | 物理关系 | 删除/更新规则 |
|---|---|---:|---|---|
| Tenant | TenantFamilyBinding | 1:N | `tenant_family_bindings.tenant_id` | 租户关闭先冻结子绑定，不级联删除家庭事实 |
| Tenant | TenantAccountMembership | 1:N | `tenant_account_memberships.tenant_id` | 撤权为状态迁移，保留审计 |
| Family | Person | 1:N | `persons.family_id` | 家庭删除需经过权利评估，不直接 cascade |
| Family | FamilyMembership | 1:N | `family_memberships.family_id` | 成员退出关闭关系，不删除 Person |
| Person | AccountPersonBinding | 1:N | `account_person_bindings.person_id` | 解绑不删除 Account/Person |
| Family | FamilyRelationship | 1:N | `family_relationships.family_id` | 关系纠错新增修正事实；禁止覆盖历史 |
| Person | LifeStageAssignment | 1:N（当前有效 0..1） | `child_id` | 当前有效唯一；过期记录保留 |
| Family | ConsentRecord | 1:N | `consents.family_id` | 撤回关闭当前授权，保留原版本与时间 |
| Person(subject) | ConsentRecord | 1:N | `consents.subject_person_id` | 未成年人监护依据必须可追溯 |
| Family | VisibilityPolicyAssignment | 1:N | policy resource ref | 撤权即时失效，访问日志不可删 |

### 3.2 测评、成长与计划关系

| 父对象 | 子对象 | 基数 | 物理关系 | 删除/更新规则 |
|---|---|---:|---|---|
| AssessmentToolVersion | AssessmentSession | 1:N | `(tool_ref,tool_version)` FK | 会话保存版本快照；工具不可原地改 |
| AssessmentSession | AssessmentResponse | 1:N | `assessment_session_id` | 草稿回答可修订；提交后只追加 |
| AssessmentSession | AssessmentOperation | 1:N | `assessment_session_id` | `action_name + idempotency_key` 唯一 |
| AssessmentSession | EvidenceSet | 1:N | evidence source ref | 证据冻结后不可覆盖 |
| EvidenceSet | AssessmentAIRun | 1:N | `assessment_evidence_id` | AI run 删除不删除证据事实 |
| Family | GrowthProfile | 1:N | `growth_profiles.family_id` | Profile 是快照/推断，不升格为 Fact |
| GrowthProfile | GrowthProfileDimension | 1:N | `profile_id` FK | profile 删除可 cascade 子维度，但需保留审计 |
| GrowthProfile | GrowthPriority | 1:N | `profile_id` FK | priority 必须有家庭确认人/时间 |
| GrowthNeedInput | GrowthNeedSignal | 1:N | `raw_ref` FK | Signal 可撤回/删除，原始输入按目的留存 |
| GrowthNeedSignal | GrowthIntent | 0..1:N | `signal_ref` FK | Intent 只有确认后可进入计划 |
| GrowthIntent | EligibilityEvaluation | 1:N | `intent_ref` FK | 每个阶段/offer/version 可重复评估 |
| GrowthIntent | ResourceRecommendation | 1:N | `intent_ref` FK | 推荐是 Perspective，不是服务事实 |
| ResourceRecommendation | FamilyServiceDecision | 1:N | `recommendation_ref` FK | 决定记录版本化，不覆盖推荐 |
| GrowthJourneyLegacy | JourneyPlan | 1:N（当前主计划 0..1） | `onboarding_id` FK | 兼容 journey 不再新增第二套计划真相 |
| JourneyPlan | JourneyPhase | 1:4 | `plan_id` FK | phase 不能脱离 plan；删除遵循计划留存 |
| JourneyPlan | ActionTask/Record | 1:N | `journey_plan_id` FK | action 追加事实；不能由投影写入 |
| ActionTask | GrowthEvent/ActionRecord | 1:N | `action_id` FK | 完成、跳过、修正均有事件 |
| Journey/Phase | OutcomeRecord | 1:N | journey/phase ref | Outcome 需主体确认/证据，非完成率自动生成 |

### 3.3 服务、FGCN 与商业关系

| 父对象 | 子对象 | 基数 | 物理关系 | 删除/更新规则 |
|---|---|---:|---|---|
| ServiceProvider | ServiceOfferingVersion | 1:N | `provider_id` FK | provider 停用不删除历史 offering |
| ServiceOfferingVersion | AvailabilitySlot | 1:N | `service_offering_id` FK | slot 关闭释放库存，不抹预约历史 |
| Family | BookingRequest | 1:N | `family_id` FK | 预约取消为状态事实 |
| BookingRequest | ServiceRecord | 1:0..1 | `source_booking_request_id` FK | 记录可补交付，但不伪造已履约 |
| ServiceBlueprintVersion | ServiceCase | 1:N | snapshot ref（不反向更新） | case 创建时冻结版本和策略 |
| ServiceCase | ServiceTask | 1:N | `service_tasks.case_ref` FK | case 关闭前任务必须终态或有未完成原因 |
| ServiceTask | TaskAssignment | 1:N（当前 ACCEPTED 0..1） | `task_id` FK + partial unique | 只有一个当前责任人 |
| ServiceTask | TaskQualityReview | 1:N | `task_id` FK | review 追加写，reviewer 不得为交付人 |
| ServiceTask | DeliveryRecord | 1:N | task/assignment ref | 交付版本化，返工新建任务/记录 |
| ServiceCase | ServiceContribution | 1:N | `case_ref` FK | 只有 VERIFIED 交付才可贡献 |
| ServiceCase | AllocationRun | 1:0..1 | `allocation_run_ref.case_ref` unique | 一个案件一次最终分配批次 |
| AllocationRun | ContributionAllocation | 1:N | `allocation_run_ref` FK | 总单位 ≤100；不可当支付记录 |
| Contribution | ContributionAllocation | 1:N | `contribution_ref` FK（case-level 可为空） | contribution/weight basis 必须带 contribution |
| ProductOfferingVersion | PurchaseIntentLine | 1:N | `product_id` FK | 目录版本快照进入意向/订单 |
| PurchaseIntent | PurchaseIntentLine | 1:N | `order_intent_id` FK | 意向可取消，不等于订单 |
| PurchaseIntent | Entitlement | 1:N | `source_order_intent_id` FK | 仅支付/授权后激活；退款反向失效 |
| MembershipPlan | BenefitDefinition | 1:N | `plan_id` FK/逻辑 ref | benefit 版本冻结 |
| MembershipSubscription | MembershipPeriod | 1:N | subscription ref | 周期顺序唯一，续购新建周期 |
| MembershipSubscription | BenefitGrant | 1:N | subscription ref | grant 的单位和有效期来自 benefit version |
| BenefitGrant | BenefitReservation | 1:N | `benefit_grant_id` FK | reservation 过期/释放/消费状态明确 |
| BenefitGrant | BenefitLedgerEntry | 1:N | `benefit_grant_id` FK | ledger 追加写，余额由分录聚合 |
| PointsAccount | PointsLedgerEntry | 1:N | `points_account_id` FK | `SUM(points_delta)` 是余额权威 |
| PointsRedemption | PointsLedgerEntry | 0..N | `redemption_id` ref | 兑换和冲正均有分录，不覆盖余额 |

### 3.4 社区、AI、运营与治理关系

| 父对象 | 子对象 | 基数 | 物理关系 | 删除/更新规则 |
|---|---|---:|---|---|
| Post | PostRevision | 1:N | `post_id` FK/逻辑 ref | 撤回停止曝光，历史修订按留存保留 |
| Post | Interaction | 1:N | `post_id` FK/逻辑 ref | 互动不能改写成长事实 |
| Post/Report | ModerationCase | 1:N | resource ref | 初审、复核、申诉职责分离 |
| ModerationCase | ModerationDecision | 1:N | case ref | 决策追加写，规则变更不改历史 |
| AIRequest | ContextSnapshot | 1:N | request ref | snapshot 只含授权最小字段 |
| ContextSnapshot | ModelAttempt | 1:N | context ref | attempt 记录 provider/model/cost/provenance |
| ModelAttempt | ModelDraft | 1:N | attempt ref | draft 永不自动写 Fact |
| ModelDraft | HumanReview | 0..N | draft ref | 高风险必须有人工决定 |
| KnowledgeVersion/PromptVersion | ModelAttempt | 1:N | version refs | 调用保存使用版本；版本发布后冻结 |
| MetricDefinition | MetricSnapshot | 1:N | metric/version ref | 口径变更新版本，不回写旧指标 |
| OpsQueueItem | Assignment | 1:N（当前负责人 0..1） | queue ref | 超时升级产生新事件，不静默改派 |
| DataSubjectRequest | RightsAssessment | 1:N | request ref | 范围评估先于导出/删除 |

### 3.5 记忆体、媒体与删除关系

| 父对象 | 子对象 | 基数 | 物理关系 | 删除/更新规则 |
|---|---|---:|---|---|
| MemoryCandidate | MemoryConsent | 1:0..N | `memory_consents.candidate_id` | 未确认候选可撤回；不自动成为记忆 |
| MemoryCandidate | Child/Guardian/RelationshipMemory | 1:0..1 | `*_memory_items.candidate_id` | 只有家庭/人工确认后 materialize，确认版本不可覆盖 |
| Memory | MemoryRetrieval | 1:N | `memory_retrievals.memory_id` | 读取必须记录目的、范围、同意版本；审计不可随记忆删除 |
| Memory | MemoryCorrection | 1:N | `memory_corrections.memory_id` | 纠正新增版本/事实，不覆盖原始审计 |
| Memory | MediaTranscript/Embedding/Cache | 1:N | provenance + `deletion_ref` | 源记忆删除时级联删除派生物并产生 DeletionProof |
| Memory | MemoryDeletionJob/Proof | 1:N | deletion ref | 作业可重试、证明幂等；跨租户/家庭读取拒绝 |
| RightsAssessment | DeletionJob/ExportPackage | 1:N | assessment ref | 幂等、可验证、法定留存例外 |
| SecurityIncident | AuditEvent | 1:N | correlation/resource ref | 证据保全，事件时间线不可覆盖 |
| AnyAggregate | OutboxEvent | 1:N | polymorphic `aggregate_type/id` | 与聚合事务同提交，消费可重放 |
| AnyResource | AuditEvent | 1:N | polymorphic resource ref | 追加写/WORM，业务角色不可覆盖 |

## 4. 跨域关系与物理约束

### 4.1 允许的关系

1. 同一聚合内：使用数据库 FK、唯一约束、检查约束和事务保证一致性。
2. 跨域只读：使用 Query Port 返回 DTO，或消费 Domain Event 维护 Projection。
3. 跨域命令：通过应用服务/工作流传递 `command_id` 和 `correlation_id`，目标域自行校验并写入自己的聚合。
4. 事件关联：跨域事件使用 `aggregate_type + aggregate_id`、`causation_id`、`correlation_id`；不要为方便查询跨 schema 直写。
5. 物理 FK：只在“子对象生命周期明确依附父聚合、不会造成跨域级联删除”的场景使用；跨域主体可使用受控 FK，但删除必须由权利/留存作业编排。

### 4.2 禁止的关系

- UI Projection → 业务事实表的反向写入；
- AI ModelDraft → Family/Outcome/GrowthState 的直接 FK 写入；
- Product/Promotion → Child subject 的个性化商业推荐关系；
- `balance`/`score`/`ranking` 作为家庭事实主表字段；
- 用 `family_id` 把主数据（商品、内容、服务供给、规则）复制成每家庭一份；
- 通过删除父行 cascade 清除儿童数据、审计、支付或法律留存数据；
- 在开发/测试环境删除表、状态、权限、审核或支付失败路径。

## 5. 从对象到表的实施状态

当前可证明的物理落地主要集中在：Family/Identity、Assessment、Growth/Journey 基础表、Service Booking/FGCN allocation、Commerce intent/entitlement、Audit/Outbox。以下仍不能称为完成能力：

- `Order/Payment/Refund` 正式交易表及回调幂等链；
- `Complaint/Recovery/Dispute`、社区审核和数据权利全链；
- `Knowledge/Prompt/Context/Review/Evaluation` 的 durable AI runtime 表；
- 运营队列、指标、实验、伙伴、组织、发布一致性、事故复盘表；
- Membership tier/period/reservation、loyalty points 的统一 Alembic revision、对账和生产 wiring；
- `family_journey_plans` 与历史 `growth_journeys` 的唯一写入者裁决和迁移；
- 所有 Projection 的可重放、删除级联和 PostgreSQL migration 集成测试。

## 6. 表级验收清单

每一张新表进入实现前必须登记：

```text
object_id / domain / process_ids / scenario_ids
data_class (M/B/C/P/A) / classification / purpose
table_name / schema / status / owner
primary_key / natural_key / unique_constraints / check_constraints
foreign_keys / cardinality / on_delete / cross_domain_policy
state_machine / command_writer / event_types / projection_consumers
retention_policy / deletion_cascade / legal_hold_behavior
fixture_factory / alembic_revision / postgres_test / environment_parity_test
```

没有对象定义、表定义、关系定义和测试证据的表，只是孤立的数据库结构，不算业务数据架构完成。
