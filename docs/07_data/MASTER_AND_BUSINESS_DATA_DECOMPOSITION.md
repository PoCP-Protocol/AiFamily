---
id: DATA-MASTER-BUSINESS-001
title: AiFamily 主数据与业务数据详细分解
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

# AiFamily 主数据与业务数据详细分解

> 本文件是 `BUSINESS_ARCHITECTURE.md` 六级流程架构和 `BUSINESS_SCENARIO_CLOSURE_CATALOG.md` 节点契约的数据落地附录。主数据解决“流程使用什么稳定对象和规则”，业务数据解决“这一次家庭/运营动作实际发生了什么”。两者均必须落到 PostgreSQL、事件、投影、审计和环境等价测试。

## 1. 使用方式与符号

### 1.1 数据类型

| 符号 | 类型 | 判断标准 | 典型存储 |
|---|---|---|---|
| `M` | 主数据 Master | 可被多个流程复用、具有版本和 owner、发布后冻结 | 版本表、目录表、规则表 |
| `B` | 业务数据 Business | 某个家庭、主体、案件、交易或运营任务产生的事实/状态 | 聚合表、事实表、账本、案件表 |
| `C` | 策略/配置 Policy | 决定流程如何执行，不代表家庭事实 | policy、SLA、路由、留存配置 |
| `E` | 领域事件 Event | 业务事实发生后的不可变消息 | outbox、event store、inbox |
| `P` | 读模型 Projection | 从 M/B/E 重建的 UI、运营和分析视图 | query table、materialized view、cache |
| `A` | 审计 Audit | 访问、授权、状态变化和人工决定的证据 | WORM audit、access log |

### 1.2 节点数据链路

```text
M/C 主数据与策略版本
   ↓ 选择、校验、冻结
L5 Command/API + Domain Policy
   ↓ 聚合内事务
B 业务数据状态/事实
   ↓ 同事务写入
E Success / Failure / Compensation Event + A AuditEvent
   ↓ 幂等消费、可重放
P Customer / Ops / Analytics Projection
```

节点表中的 `M` 只表示依赖或更新主数据版本，`B` 只表示本节点产生/改变的业务事实；如果一个对象既是主体主数据又带有过程事实，必须拆成“主体记录 + 过程记录”，不能用一个状态字段混合两种语义。

### 1.3 全局字段契约

所有 `B/E/A` 记录至少包含：

```text
id、tenant_id、family_id（无家庭时显式为空）、subject_id、actor_id、actor_type
purpose、consent_version、source、occurred_at、created_at、schema_version
idempotency_key、correlation_id、causation_id、classification、provenance
```

`M` 记录至少包含：`version_id`、`status`、`effective_from`、`effective_to`、`owner`、`approved_by`、`approved_at`、`rollback_of`。任何业务记录必须保存实际使用的 `master_version_id`，不能运行时读取“最新版本”而丢失历史口径。

## 2. L0-L5 数据架构分解

| 流程层级 | 数据架构问题 | 必须产物 | 完成判据 |
|---|---|---|---|
| L0 价值流 | 价值流需要哪些跨域事实证明交付完成 | 价值流数据产品、结果事件、经营指标口径 | 能从事实事件重建起点、关键交付和终点；不使用家庭总分/排名 |
| L1 流程组 | 哪个域拥有写入边界，哪些域只读 | 聚合边界、跨域事件、流程组投影 | 每个 P01-P06 只有明确主写入域，跨域只用 Query Port/Event |
| L2 场景 | 一次闭环由哪些主数据和业务事实组成 | 场景数据契约、成功/失败事件、场景投影 | 每个 S/O 至少有 M 依赖、B 聚合、E、P、A 和留存策略 |
| L3 子流程 | 哪些状态迁移可复用，哪些异常需人工接管 | 状态机、策略快照、补偿边界 | 每个子流程有前置状态、终态、拒绝码、超时和补偿 |
| L4 节点 | 一次活动读什么、写什么、发什么 | 节点数据表（本文第 4 节）、输入 DTO、输出事件 | 每个 Nxx 都能回答主数据输入、业务写入、事件、投影和控制 |
| L5 系统操作 | 如何保证真实运行和环境等价 | API/Command、Repository、Outbox、Job、Human Task、测试 fixture | dev/test/prod 同一 schema、状态机、权限、审计和错误路径 |

## 3. L1 流程组数据拓扑

| L1 | 价值流 | 主数据入口 | 业务数据主链 | 关键跨域事件 | 终端投影 |
|---|---|---|---|---|---|
| P01 | VS-01 家庭触达、身份与入营 | 内容/活动版本、角色/目的目录、身份策略 | Reach/Entry → User/Family/Person → Membership/Visibility → Consent/StartToken | `FamilyEntered`、`FamilyCreated`、`ConsentGranted`、`AssessmentAuthorized` | Entry、FamilyHome、AssessmentStart |
| P02 | VS-01 测评、假设、计划与行动 | 测评版本、解释规则、计划/任务模板、提醒策略 | Session/Response/Evidence → Perspective/Hypothesis/Intent → Plan/Phase/Action → Outcome/Story | `EvidenceFrozen`、`HypothesisDecided`、`PlanConfirmed`、`TaskCheckedIn`、`OutcomeConfirmed` | Assessment、Hypothesis、Plan、TodayTask、Outcome |
| P03 | VS-02 陪跑、专业服务与 FGCN | 服务供给、SLA、质量、资质、蓝图版本 | Entitlement → Booking/Case/Task → Assignment/Delivery → Quality/Contribution → Complaint/Recovery | `BookingConfirmed`、`DeliveryVerified`、`ContributionRecorded`、`DisputeDecided` | ServiceJourney、Booking、FGCNCase、Quality |
| P04 | VS-03 商品、会员、资产与关系增长 | 商品/价格/权益/促销/积分规则 | Intent → Order/Payment → Membership/Entitlement → Usage/Points/Invite | `PaymentConfirmed`、`EntitlementActivated`、`PointsCredited`、`InviteAccepted` | Product、Membership、Asset、Points、Cohort |
| P05 | VS-04 社区、数据权利与安全信任 | 可见性、审核、留存、事件分级策略 | Post/Interaction → Moderation/Appeal → Rights/Deletion → SecurityIncident | `PostPublished`、`AppealDecided`、`DeletionExecuted`、`IncidentResolved` | CommunityFeed、Rights、Compliance |
| P06 | VS-05 运营、AI、指标、发布与组织治理 | 指标、实验、知识/模型、组织/合同、发布策略 | OpsQueue/Metric → AI Attempt/Review/Eval → Partner/Org/Change/Incident | `MetricPublished`、`AIReviewed`、`PartnerAdmitted`、`ParityVerified`、`PostmortemClosed` | Ops、AITrace、Partner、Governance、Release |

## 4. L2/L4 节点数据分解

以下矩阵逐节点引用 `BUSINESS_SCENARIO_CLOSURE_CATALOG.md` 的输入、活动、输出和规则。`M/C` 是主数据或策略，`B` 是本节点权威业务写入，`E` 是应发布的事实事件，`P/A` 是读取或控制面。

### 4.1 P01：家庭触达、身份与入营

| 节点 | M/C 主数据与策略输入 | B 业务数据写入/读取 | E 事实事件 | P/A 与关键控制 |
|---|---|---|---|---|
| S01-N01 内容发布 | `ContentSource`、`ContentPolicy`、版权规则 | `M ContentVersion(REVIEW→PUBLISHED)` | `ContentPublished` / `ContentRejected` | `CatalogProjection`；版本冻结、owner、适用范围、版权到期 |
| S01-N02 直播/活动排期 | `ActivityTemplate`、容量/取消规则 | `M ActivitySlot(OPEN)` | `ActivityScheduled` / `ActivityScheduleRejected` | `ActivityProjection`；容量、候补、时区、截止时间 |
| S01-N03 家庭发现 | `ChannelConfig`、推荐位规则、退订策略 | `B ReachEvent` | `FamilyContentViewed`（行为事实，不是购买） | `EntryProjection`；purpose、最小行为字段、频控 |
| S01-N04 进入家庭 | `EntryPolicy`、身份策略 | `B EntryEvent`；读取 `User/Session` | `FamilyEntered` / `EntryRejected` | `EntryProjection`；未登录不得创建家庭事实，来源可追溯 |
| S02-N01 身份建立 | `IdentityVerificationPolicy`、OTP/登录策略 | `B User`、`B Session(ACTIVE)` | `IdentityVerified` / `SessionRejected` | `ActorContext`、`AccessLog`；会话可撤销，认证与授权分离 |
| S02-N02 创建家庭 | `FamilyFieldDictionary`、地区/生命周期枚举 | `B Family(ACTIVE)`、`B FamilyProfile` | `FamilyCreated` / `FamilyCreateRejected` | `FamilyHomeProjection`；一个用户可多家庭，租户边界独立 |
| S02-N03 成员邀请/绑定 | `RelationshipType`、监护规则、邀请模板 | `B Person`、`B FamilyMembership(PENDING/ACTIVE)`、`B FamilyRelationship` | `MemberInvited`、`MemberBound` / `MemberBindingRejected` | `FamilyAccessProjection`；监护依据、重复邀请幂等 |
| S02-N04 角色与可见性 | `RoleDefinition`、`ResourceCatalog`、`VisibilityPolicy` | `B RoleGrant`、`B VisibilityPolicyAssignment` | `RoleGranted`、`VisibilityChanged` / `AccessDenied` | `FamilyHomeProjection`、`AccessLog`；最小权限、撤权即时生效 |
| S03-N01 测评目录 | `M AssessmentTool/Version/Question`、适用范围 | 读取 `AssessmentCatalogItem` | `AssessmentCatalogPublished` | `AssessmentCatalogProjection`；版本、用途、时长、退出方式 |
| S03-N02 目的选择 | `M PurposeDefinition`、目的组合规则 | `B PurposeSelection` | `PurposeSelected` / `PurposeSelectionRejected` | `ConsentSnapshot`；逐目的选择，不以勾选换服务 |
| S03-N03 同意采集 | `M PrivacyNotice/ConsentPolicy`、监护关系 | `B ConsentRecord(GRANTED/REFUSED/REVOKED)` | `ConsentGranted`、`ConsentRevoked` / `ConsentRejected` | `ConsentHistory`、`AuditEvent`；不可覆盖原同意版本 |
| S03-N04 启动资格 | `M AssessmentVersion`、`C ConsentGatePolicy` | 读取 `ConsentSnapshot`、`FamilyMembership`，生成 `B AssessmentStartToken` | `AssessmentAuthorized` / `AssessmentAuthorizationDenied` | `AssessmentStartProjection`；token 过期、越权、幂等 |
| O01-N01 租户开通 | `TenantPlan`、环境/配额策略、密钥策略 | `B Tenant(ACTIVE)`、`B TenantBinding` | `TenantOpened` / `TenantOpenRejected` | `AccessAdminProjection`；租户隔离、配额和密钥分域 |
| O01-N02 角色授权 | `RoleDefinition`、职责矩阵、高风险权限策略 | `B RoleGrant`、`B ApprovalRecord` | `RoleGranted` / `RoleGrantRejected` | `AccessAdminProjection`、`AuditEvent`；高风险双人审批、定期复核 |
| O01-N03 账号支持 | `AccountSupportPolicy`、身份核验规则 | `B AccountAction`、`B SupportTicket` | `AccountActionCompleted` / `AccountActionDenied` | `SupportOpsProjection`；支持人员不得绕过核验 |
| O01-N04 离职/撤权 | `RevocationPolicy`、SLA | `B AccessRevocation`、Session/Grant 状态变更 | `AccessRevoked` / `RevocationFailed` | `AccessAdminProjection`、`AuditEvent`；撤权幂等、限时完成 |
| O03-N01 渠道配置 | `ChannelType`、归因与频控策略 | `M ChannelConfig(ACTIVE)` | `ChannelConfigured` / `ChannelConfigRejected` | `CampaignOpsProjection`；归因规则版本化 |
| O03-N02 活动排期 | `ActivityTemplate`、容量/候补/取消策略 | `M ActivitySlot`、`B RegistrationWindow` | `CampaignScheduled` / `ScheduleConflict` | `ActivityProjection`；容量锁、时区和通知规则 |
| O03-N03 触达编排 | `ContentVersion`、`PurposeDefinition`、频控/退订策略 | `B TouchpointAction(PLANNED/SENT/FAILED)` | `TouchpointSent` / `TouchpointSuppressed` | `CampaignOpsProjection`、`AccessLog`；同意、退订、幂等、失败回调 |
| O03-N04 活动复盘 | `MetricDefinition`、活动目标版本 | 读取 `ReachEvent/Registration/Attendance`，写 `B ActivityReview` | `ActivityReviewed` / `ActivityReviewRejected` | `AnalyticsProjection`；浏览/点击不等于购买或成长事实 |
| O04-N01 线索接收 | `LeadSource`、去重/分配规则 | `B FamilyLead(NEW/ASSIGNED)` | `LeadReceived` / `LeadDeduplicated` | `LifecycleOpsProjection`；线索与家庭事实分离 |
| O04-N02 入营跟进 | `FollowUpPolicy`、提醒偏好、SLA | `B OnboardingFollowUp(SCHEDULED/SENT)` | `FollowUpSent` / `FollowUpSuppressed` | `LifecycleOpsProjection`；不得替家庭确认决定 |
| O04-N03 流失识别 | `RetentionSignalPolicy`、指标窗口 | 读取行动/服务/会员事实，写 `B RetentionSignal` | `RetentionSignalRaised` / `RetentionSignalSuppressed` | `LifecycleOpsProjection`；不以单一行为贴标签 |
| O04-N04 重新激活 | `ReactivationPolicy`、ConsentGate | `B ReactivationAction`、重新读取 Consent/Plan | `FamilyReactivated` / `ReactivationDenied` | `FamilyHomeProjection`；原事实不覆盖，权限重新校验 |

### 4.2 P02：测评、假设、计划与行动

| 节点 | M/C 主数据与策略输入 | B 业务数据写入/读取 | E 事实事件 | P/A 与关键控制 |
|---|---|---|---|---|
| S04-N01 创建会话 | `AssessmentVersion`、`AssessmentStartToken` | `B AssessmentSession(DRAFT)` | `AssessmentSessionCreated` / `SessionCreateRejected` | `AssessmentProjection`；版本冻结、幂等建会话 |
| S04-N02 保存回答 | `QuestionSchema`、回答校验规则 | `B AssessmentResponse(DRAFT)` | `ResponseSaved` / `ResponseRejected` | `AssessmentDraftProjection`；只写当前会话/subject |
| S04-N03 提交测评 | `AssessmentVersion`、`ConsentSnapshot`、完整性规则 | `B AssessmentSubmission(COMPLETED)`，冻结 Response | `AssessmentSubmitted` / `AssessmentSubmissionRejected` | `AuditEvent`；提交后不可变、撤回同意即拒绝 |
| S04-N04 生成证据 | `EvidenceSchema`、来源规则 | `B EvidenceSet(FROZEN)` | `EvidenceFrozen` / `EvidenceGenerationFailed` | `AssessmentResultProjection`；只含来源事实，不含推断标签 |
| S04-N05 查看结果 | `ResultDisplayPolicy`、字段脱敏策略 | 读取 `EvidenceSet`、生成 `P AssessmentResultProjection` | `AssessmentResultViewed` / `ResultAccessDenied` | `AccessLog`；授权范围内展示，内部评分不可泄露 |
| S05-N01 解释证据 | `InterpretationRuleVersion`、风险词典 | `B GrowthPerspective(DRAFT)` | `PerspectiveProposed` / `PerspectiveBlocked` | `HypothesisProjection`；provenance、限制、模型/规则版本 |
| S05-N02 形成假设 | `HypothesisTemplate`、`SafetyPolicy` | `B GrowthHypothesis(PROPOSED)` | `HypothesisProposed` / `HypothesisEscalated` | `HypothesisProjection`；不写 canonical Fact，高风险转人工 |
| S05-N03 家庭确认/驳回 | `DecisionPolicy`、确认表单版本 | `B GrowthIntent(CONFIRMED)` 或 `B HypothesisDismissed` | `HypothesisDecided` / `HypothesisDecisionRejected` | `AuditEvent`；确认人/时间/原版本可追溯 |
| S05-N04 入营 | `OnboardingPolicy`、服务目录/权益版本 | `B Onboarding(ACTIVE)` | `OnboardingStarted` / `OnboardingRejected` | `OnboardingProjection`；购买不等于成长确认，重复幂等 |
| S06-N01 计划草案 | `JourneyTemplate`、`TaskTemplate`、优先级词典 | `B PlanPreview`、读取 `GrowthIntent` | `PlanDraftGenerated` / `PlanDraftBlocked` | `PlanProjection`；草案不是承诺，显示依据和限制 |
| S06-N02 创建计划 | `JourneyTemplate`、计划版本 | `B JourneyPlan(DRAFT)`、`B Phase(DRAFT)` | `PlanCreated` / `PlanCreateRejected` | `PlanProjection`；一个 onboarding 一个主计划 |
| S06-N03 确认计划 | `ConsentPolicy`、权限策略、意图版本 | `B JourneyPlan(ACTIVE)`、首阶段激活 | `PlanConfirmed` / `PlanConfirmationRejected` | `AuditEvent`；确认前置齐全，AI 不能代确认 |
| S06-N04 阶段执行 | `PhaseSchedule`、行动/提醒策略 | `B PhaseProgress`、读取 `ActionRecord` | `PhaseProgressRecorded` / `ProgressRecordRejected` | `JourneyProjection`；进度不是分数/疗效/排名 |
| S06-N05 阶段复盘 | `PhaseDecisionPolicy`、服务 SLA | `B PhaseDecision(CONTINUE/ADJUST/PAUSE)`、状态迁移 | `PhaseReviewed` / `PhaseReviewEscalated` | `PlanProjection`；决策主体、原因、下一状态完整 |
| S07-N01 生成今日任务 | `TaskTemplate`、`FamilyRhythmPolicy`、active phase | `B ActionTask(ASSIGNED)` | `TaskAssigned` / `TaskGenerationSkipped` | `TodayTaskProjection`；来源、难度、适用成员可解释 |
| S07-N02 提醒与开始 | `ReminderPolicy`、家庭免打扰配置 | `B ReminderAction`、`B ActionTask(IN_PROGRESS)` | `TaskReminderSent`、`TaskStarted` / `ReminderSuppressed` | `NotificationLog`；撤回/免打扰优先，提醒不等于同意 |
| S07-N03 完成/跳过 | `ActionCompletionPolicy`、任务版本 | `B ActionRecord(COMPLETED/PARTIAL/SKIPPED)` | `TaskCheckedIn` / `TaskCheckinRejected` | `TodayTaskProjection`；行为事实、重复提交幂等 |
| S07-N04 过程回读 | `ReflectionTemplate`、风险升级策略 | 读取 `ActionRecord`、写 `B ProcessPerspective`、`B Recommendation` | `ProcessReadbackGenerated` / `ReadbackEscalated` | `RhythmProjection`；不生成总分，高风险人工 |
| S07-N05 21 天结项 | `ChallengePolicy`、结项模板 | `B ChallengeReview(COMPLETED/PAUSED)` | `ChallengeClosed` / `ChallengeClosureRejected` | `OutcomeProjection`；缺失数据显式标注，结项不等于结果 |
| S08-N01 过程报告 | `ReportTemplate`、指标口径 | 读取行动/阶段事实，写 `B ProgressReport` | `ReportGenerated` / `ReportGenerationFailed` | `ProgressReportProjection`；事实与观点分层 |
| S08-N02 成果确认 | `OutcomeType`、证据要求 | `B OutcomeRecord(PENDING/CONFIRMED)` | `OutcomeConfirmed` / `OutcomeRejected` | `OutcomeProjection`；主体确认/证据，不由完成率自动生成 |
| S08-N03 私有故事 | `StoryVisibilityPolicy`、媒体留存策略 | `B FamilyStory(DRAFT/PUBLISHED/WITHDRAWN)`、`B MediaReference` | `StoryCreated`、`StoryWithdrawn` / `StoryPublishRejected` | `StoryProjection`；默认私有，公开前再次确认 |
| S08-N04 年度沉淀 | `AnnualReviewTemplate`、导出/删除策略 | `P AnnualReviewProjection`，读取 confirmed outcomes | `AnnualReviewGenerated` / `AnnualReviewBlocked` | `FamilyStoryProjection`；不排名，可导出/删除 |
| S09-N01 提问 | `PurposeDefinition`、`AIRequestPolicy`、敏感主题策略 | `B AIRequest`、`B ConversationTurn` | `AIRequestReceived` / `AIRequestRejected` | `AssistantProjection`、`AccessLog`；最小上下文、儿童敏感话题收紧 |
| S09-N02 上下文回答 | `KnowledgeVersion`、`ModelRoutingPolicy`、`ContextPolicy` | `B ContextSnapshot`、`B ModelDraft`、`B ModelAttempt` | `ModelAttempted`、`DraftGenerated` / `ModelCallFailed` | `AITraceProjection`；Gateway、provenance、成本和模型版本 |
| S09-N03 建议与提醒 | `RecommendationPolicy`、`ReminderPolicy` | `B Recommendation` 或 `B ReminderAction(PENDING/SENT)` | `RecommendationIssued`、`ReminderAuthorized` / `SideEffectDenied` | `AssistantProjection`；AI 不改事实，副作用需授权/幂等 |
| S09-N04 解释与反馈 | `ExplanationTemplate`、来源展示策略 | `B ExplanationView`、`B AIFeedback` | `AIExplanationViewed`、`AIFeedbackRecorded` | `AITraceProjection`；不得宣称诊断/疗效 |
| S09-N05 风险升级 | `SafetyPolicy`、人工接管规则、SLA | `B HumanEscalationCase(OPEN)`、`B SupportTicket` | `HumanEscalated` / `EscalationRejected` | `SupportOpsProjection`、`AuditEvent`；高风险暂停自动化 |
| O02-N01 内容编审 | `ContentSchema`、版权/敏感级别策略 | `M ContentVersion(REVIEW)`、`B ReviewDecision` | `VersionSubmitted` / `ContentReviewRejected` | `VersionOpsProjection`；来源、许可、失效日 |
| O02-N02 测评版本 | `AssessmentSchema`、目的和题目规则 | `M AssessmentVersion(DRAFT/REVIEWED)` | `AssessmentVersionFrozen` / `AssessmentVersionRejected` | `VersionOpsProjection`；已被会话引用的版本不可原改 |
| O02-N03 计划/任务模板 | `PhaseTemplateSchema`、验收/风险规则 | `M JourneyTemplate`、`M TaskTemplate` | `TemplatePublished` / `TemplateRejected` | `VersionOpsProjection`；不得内含家庭事实/疗效承诺 |
| O02-N04 发布/回滚 | `ReleasePolicy`、灰度策略、回滚点 | `B ReleaseDecision(PUBLISHED/ROLLED_BACK)` | `VersionPublished`、`VersionRolledBack` / `ReleaseBlocked` | `ReleaseOpsProjection`；历史事实不删除 |
| O12-N01 知识/提示词登记 | `KnowledgeSchema`、许可/适用范围规则 | `M KnowledgeVersion`、`M PromptVersion` | `KnowledgeRegistered` / `KnowledgeRegistrationRejected` | `AIOpsProjection`；owner、来源、许可、失效期 |
| O12-N02 模型路由策略 | `ModelRegistry`、风险/成本/降级策略 | `C ModelRoutingPolicy`、`C CircuitBreakerPolicy` | `RoutingPolicyPublished` / `RoutingPolicyRejected` | `AIOpsProjection`；高风险不得降级无审模型 |
| O12-N03 评估与红队 | `EvaluationPolicy`、评估集/限制说明 | `B EvaluationRun`、`B RedTeamFinding` | `ModelEvaluated` / `EvaluationFailed` | `AIQualityProjection`；失败阻断发布，合成数据不宣称真实有效 |
| O12-N04 发布/回滚 | `AIRuntimeReleasePolicy`、canary 配置 | `B AIRuntimeRelease(PUBLISHED/ROLLED_BACK)` | `AIRuntimeReleased`、`AIRuntimeRolledBack` / `AIReleaseBlocked` | `AITraceProjection`；历史回答不被回写 |

### 4.3 P03：陪跑、专业服务与 FGCN 交付

| 节点 | M/C 主数据与策略输入 | B 业务数据写入/读取 | E 事实事件 | P/A 与关键控制 |
|---|---|---|---|---|
| S10-N01 服务开通 | `MembershipPlan`、`BenefitVersion`、服务层级规则 | `B ServiceEntitlement(ACTIVE)` | `ServiceOpened` / `ServiceOpenRejected` | `ServiceJourneyProjection`；权益必须来自有效订单/会员 |
| S10-N02 服务触达 | `TouchpointPolicy`、SLA、权限策略 | `B ServiceInteraction`、`B ContactRecord` | `ServiceContactRecorded` / `ServiceContactDenied` | `ServiceJourneyProjection`、`AccessLog`；目的、主体、时间完整 |
| S10-N03 客户问题 | `SupportCategory`、风险/SLA 策略 | `B SupportTicket(OPEN)`、附件引用 | `TicketCreated` / `TicketCreateRejected` | `SupportOpsProjection`；敏感附件最小可见 |
| S10-N04 服务记录 | `ServiceRecordSchema`、记录模板 | `B ServiceRecord(DRAFT/FINAL)` | `ServiceRecordRecorded` / `ServiceRecordRejected` | `ServiceRecordProjection`；不回写未确认成长结果 |
| S10-N05 服务结束 | `ClosurePolicy`、质量/反馈规则 | `B ServiceCase(CLOSED)` 或 `B QualitySignal` | `ServiceClosed` / `ServiceClosureRejected` | `ServiceJourneyProjection`；交付证据/未完成原因必须存在 |
| S11-N01 供给档案 | `QualificationType`、服务分类、地区字典 | `B ProviderProfile`、资质引用 | `ProviderProfileCreated` / `ProviderProfileRejected` | `ProviderDirectoryProjection`；资质有效期、范围可核验 |
| S11-N02 服务产品 | `ServiceType`、定价、SLA、取消规则 | `M OfferingVersion(PUBLISHED)` | `OfferingPublished` / `OfferingRejected` | `ProviderDirectoryProjection`；版本冻结、交付物明确 |
| S11-N03 时段发布 | `CapacityRule`、时区/排班策略 | `B AvailabilitySlot(OPEN)` | `SlotReleased` / `SlotConflict` | `AvailabilityProjection`；容量、冲突、临时关闭 |
| S11-N04 家庭匹配 | `MatchingPolicy`、服务资格、家庭偏好字段 | `P ProviderRecommendation`、读取 Family Need/Consent | `ProviderRecommended` / `MatchingDenied` | `ProviderDirectoryProjection`；最小必要上下文，推荐不等于分配 |
| S12-N01 查看详情 | `OfferingVersion`、`ActivitySlot`、条款模板 | 读取主数据，生成 `P BookingPreview` | `BookingPreviewViewed` / `BookingPreviewDenied` | `BookingPreviewProjection`；价格、取消、对象、条款可见 |
| S12-N02 创建预约 | `BookingPolicy`、Slot/Cancellation 规则 | `B Booking(PENDING/CONFIRMED)`、容量锁 | `BookingConfirmed` / `BookingRejected` | `BookingProjection`；不超卖、幂等、tenant/family 隔离 |
| S12-N03 取消/改期 | `CancellationPolicy`、退款/扣次策略 | `B Booking(CANCELLED/RESCHEDULED)`、`B RecoveryAction` | `BookingCancelled`、`BookingRescheduled` / `CancellationRejected` | `BookingProjection`；不可伪造履约，结果可解释 |
| S12-N04 履约签到 | `AttendancePolicy`、签到窗口 | `B AttendanceRecord(STARTED/COMPLETED/ABSENT)` | `AttendanceRecorded` / `AttendanceRejected` | `AttendanceProjection`；签到不等于质量或 Outcome |
| S12-N05 服务回读 | `FeedbackFormVersion`、争议策略 | `B ServiceFeedback`、必要时 `B QualitySignal` | `ServiceFeedbackRecorded` / `FeedbackRejected` | `QualityProjection`；不可修改原始签到/交付事实 |
| S13-N01 建立 ServiceCase | `ServiceBlueprintVersion(PUBLISHED)`、服务边界策略 | `B ServiceCase(OPEN)` | `CaseOpened` / `CaseOpenRejected` | `FGCNCaseProjection`；一客一案，付款方/接受者可分离 |
| S13-N02 拆分 ServiceTask | `BlueprintVersion`、`TaskTemplate`、验收标准 | `B ServiceTask(ASSIGNED)`、期限/验收快照 | `TaskAssigned` / `TaskSplitRejected` | `FGCNCaseProjection`；一任务一责任人、标准冻结 |
| S13-N03 资源匹配与授权 | `ProviderProfile`、能力/容量、`AccessPolicy` | `B TaskAssignment(ACCEPTED/OFFERED)`、最小权限 grant | `TaskResourceAssigned` / `TaskAssignmentRejected` | `AssignmentProjection`、`AccessLog`；先授权后访问 |
| S13-N04 交付留痕 | `DeliverySchema`、附件/媒体留存策略 | `B DeliveryRecord(SUBMITTED)`、版本附件 | `DeliverySubmitted` / `DeliveryRejected` | `DeliveryProjection`；交付物版本化，AI 草稿不替代确认 |
| S13-N05 质量验收 | `QualityPolicy`、冻结的验收标准 | `B QualityCheck(VERIFIED/REWORK)`、返工任务 | `DeliveryVerified`、`DeliveryReturned` / `QualityCheckRejected` | `QualityProjection`；驳回原因、验收人、时间完整 |
| S13-N06 贡献确认 | `ContributionPolicy`、分配比例和质量池规则 | `B ServiceContribution`、`B AllocationStatement` | `ContributionRecorded` / `ContributionBlocked` | `AllocationProjection`；仅 VERIFIED 可进入分配，贡献不等于付款 |
| S14-N01 反馈/投诉 | `QualitySignalType`、匿名/实名策略 | `B QualitySignal`、附件引用 | `ComplaintOpened` / `ComplaintRejected` | `QualityProjection`；差评不阻止事实留存 |
| S14-N02 分级与响应 | `ComplaintSeverity`、SLA/升级规则 | `B ComplaintCase(OPEN)`、`B OpsQueueItem` | `ComplaintTriaged` / `ComplaintEscalated` | `SupportOpsProjection`；高风险优先，不静默改写 |
| S14-N03 恢复方案 | `RecoveryPolicy`、退款/改派规则 | `B RecoveryPlan`、成本/责任记录 | `RecoveryApplied` / `RecoveryRejected` | `QualityProjection`；动作授权、成本、责任可审计 |
| S14-N04 争议裁决 | `DisputePolicy`、证据/申诉规则 | `B DisputeDecision` | `DisputeDecided` / `DisputeEscalated` | `DisputeProjection`；独立复核，原始事实分离 |
| S14-N05 关闭与学习 | `QualityMetricDefinition`、匿名化策略 | `B ComplaintCase(CLOSED)`、`B QualityLearning` | `ComplaintClosed`、`QualityLearningRecorded` / `ClosureRejected` | `QualityProjection`；不删原始记录，学习去标识化 |
| S23-N01 合作申请 | `PartnerType`、合作范围模板 | `B PartnerApplication(SUBMITTED)` | `PartnerApplied` / `PartnerApplicationRejected` | `PartnerProjection`；付款方/接受者/数据访问者分离 |
| S23-N02 资质与协议 | `QualificationType`、DPA/SLA/合同模板 | `B PartnerAdmission`、`B CooperationAgreement` | `PartnerAdmitted`、`AgreementSigned` / `PartnerRejected` | `PartnerProjection`；删除、保密、转委托边界 |
| S23-N03 供给上架 | `OfferingSchema`、capacity/price policy | `M PartnerOffering(PUBLISHED)` | `OfferingListed` / `OfferingListingRejected` | `ProviderDirectoryProjection`；能力、价格、半径、有效期 |
| S23-N04 伙伴交付 | `ServiceBlueprintVersion`、伙伴 SLA、授权策略 | `B PartnerDeliveryRecord`、读取 `ServiceCase/Task` | `PartnerDeliverySubmitted` / `PartnerDeliveryRejected` | `FGCNCaseProjection`；交付进入 S13 验收，不跨授权访问 |
| S23-N05 续期/退出 | `PartnerRenewalPolicy`、质量/投诉阈值 | `B PartnerDecision(RENEW/REMEDIATE/SUSPEND/EXIT)` | `PartnerRenewed`、`PartnerSuspended` / `PartnerExitBlocked` | `PartnerProjection`；质量、安全和权限不可绕过 |
| O05-N01 工单入队 | `QueueType`、风险/SLA/去重规则 | `B OpsQueueItem(QUEUED)`、关联 Ticket | `TicketQueued` / `QueueRejected` | `SupportOpsProjection`；原始请求不可丢失 |
| O05-N02 责任分派 | `SkillCatalog`、容量/冲突策略 | `B Assignment(ASSIGNED/DECLINED)` | `TicketAssigned` / `AssignmentRejected` | `SupportOpsProjection`；拒绝、替补、冲突留痕 |
| O05-N03 超时升级 | `SLA`、Severity、值班表 | `B EscalationEvent`、队列状态迁移 | `SlaBreached` / `EscalationFailed` | `AuditEvent`；高风险不得静默关闭 |
| O05-N04 关闭回访 | `ClosurePolicy`、回访表单 | `B TicketClosure(CLOSED/REOPENED)` | `TicketClosed` / `TicketClosureRejected` | `SupportOpsProjection`；无解决证据不能关闭 |
| O06-N01 供给申请 | `ProviderSchema`、资质/利益冲突策略 | `B ProviderApplication`、候选 `ProviderProfile` | `ProviderApplied` / `ProviderApplicationRejected` | `SupplyOpsProjection`；身份/资质/有效期 |
| O06-N02 准入审核 | `AdmissionPolicy`、协议/培训要求 | `B ProviderAdmission(ADMITTED/REJECTED)` | `ProviderAdmitted` / `ProviderAdmissionRejected` | `ProviderDirectoryProjection`；未准入不得接触家庭 |
| O06-N03 容量排班 | `CapacityRule`、SLA/时区策略 | `B CapacitySchedule`、`B AvailabilitySlot` | `CapacityPublished` / `CapacityConflict` | `SupplyOpsProjection`；冲突、锁定、关闭可追踪 |
| O06-N04 续期/暂停 | `ProviderReviewPolicy`、投诉/质量规则 | `B ProviderDecision`、状态/授权变更 | `ProviderRenewed`、`ProviderSuspended` / `ProviderDecisionRejected` | `SupplyOpsProjection`、`AuditEvent`；离场回收权限 |
| O07-N01 预约监控 | `BookingPolicy`、支付/slot 状态规则 | 读取 Booking/Slot/Payment，写 `P BookingOpsView` | `BookingConflict` / `BookingMonitorAlert` | `DeliveryOpsProjection`；读模型不创造预约事实 |
| O07-N02 缺席/改派 | `RecoveryPolicy`、改派/退款规则 | `B RecoveryAction`、Booking/Assignment 状态 | `ServiceRecovered` / `RecoveryBlocked` | `DeliveryOpsProjection`；家庭获知影响，规则版本化 |
| O07-N03 质量抽检 | `QualitySamplingPolicy`、风险抽样规则 | `B QualitySample`、`B QualityCheck` | `QualitySampled` / `QualitySampleRejected` | `QualityProjection`；范围、结论、申诉可解释 |
| O07-N04 履约结案 | `FulfillmentClosurePolicy` | `B FulfillmentClosure`、读取 verified quality/feedback | `FulfillmentClosed` / `FulfillmentClosureRejected` | `DeliveryOpsProjection`；不自动生成 Outcome |

### 4.4 P04：商品、会员、资产与关系增长

| 节点 | M/C 主数据与策略输入 | B 业务数据写入/读取 | E 事实事件 | P/A 与关键控制 |
|---|---|---|---|---|
| S15-N01 商品上架 | `ProductSchema`、价格/权益/适用范围规则 | `M ProductVersion(PUBLISHED)` | `ProductPublished` / `ProductRejected` | `ProductCatalogProjection`；版本、库存/容量、退订 |
| S15-N02 查看方案 | `ProductVersion`、`BenefitVersion`、承诺边界 | 读取主数据，生成 `P ProductDetailProjection` | `ProductDetailViewed` / `ProductAccessDenied` | `AccessLog`；商业承诺与服务事实分离 |
| S15-N03 购买意向 | `PurchaseIntentPolicy`、产品目的 | `B PurchaseIntent(CREATED)` | `IntentCreated` / `IntentRejected` | `PurchaseIntentProjection`；意向不等于订单/收费 |
| S15-N04 方案校验 | `EligibilityPolicy`、权益兼容规则 | 读取 Order/Entitlement，写 `B PurchaseEligibility` | `PurchaseEligibilityResolved` / `PurchaseEligibilityDenied` | `ProductProjection`；冲突、重复购买、失败原因 |
| S16-N01 会员下单 | `MembershipPlan`、`PriceVersion`、支付策略 | `B MembershipOrder(PENDING)`、`B PaymentIntent` | `MembershipOrderCreated` / `OrderCreateRejected` | `OrderProjection`；付款方/服务接受者分离 |
| S16-N02 支付确认 | `PaymentProviderPolicy`、签名/幂等策略 | `B PaymentRecord(SUCCEEDED/FAILED)`、Order 状态 | `PaymentConfirmed` / `PaymentRejected` | `FinanceOpsProjection`；只接受可信回调，重复幂等 |
| S16-N03 权益激活 | `BenefitVersion`、权益激活规则 | `B Membership(ACTIVE)`、`B Entitlement(ACTIVE)` | `EntitlementActivated` / `EntitlementActivationRejected` | `MembershipProjection`；退款/撤销反向失效 |
| S16-N04 会员使用 | `EntitlementUsagePolicy`、服务目录 | `B EntitlementUsage`、读取 Entitlement | `EntitlementConsumed` / `EntitlementUsageDenied` | `MembershipProjection`；授权、幂等、不可超额 |
| S16-N05 年度续购 | `RenewalPolicy`、价格版本、自动续费授权 | `B RenewalDecision(RENEW/EXPIRE)`、新 Order 意向 | `RenewalDecided` / `RenewalRejected` | `RenewalProjection`；自动续费单独授权 |
| S17-N01 订单资产 | `AssetType`、退款/失效规则 | `B OrderAsset`、读取 Order/Payment/Refund | `OrderAssetCreated` / `OrderAssetRejected` | `AssetProjection`；订单、支付、权益三者分离 |
| S17-N02 积分事件 | `EarnRule`、贡献/活动规则、有效期 | `B PointsLedgerEntry(CREDIT)` | `PointsCredited` / `PointsCreditRejected` | `PointsLedgerProjection`；追加写，来源事件可追溯 |
| S17-N03 积分使用 | `RedemptionItem`、余额/限额规则 | `B PointsRedemption(PENDING/COMPLETED)`、Ledger DEBIT | `PointsRedeemed` / `PointsRedemptionRejected` | `PointsLedgerProjection`；余额聚合、兑换幂等 |
| S17-N04 资产回读 | `ProjectionSchema`、脱敏策略 | 读取 Order/Entitlement/Ledger，写 `P AssetProjection` | `AssetViewed` / `AssetReadDenied` | `AssetProjection`；投影不能创造交易事实 |
| S17-N05 对账 | `ReconciliationPolicy`、财务口径 | `B ReconciliationCase(OPEN/CLOSED)`、修复分录 | `ReconciliationOpened`、`ReconciliationClosed` / `ReconciliationEscalated` | `FinanceOpsProjection`；差异不抹平，双人/审计修复 |
| S18-N01 创建邀请 | `InvitePolicy`、目的/过期/单层激励规则 | `B InviteToken(ISSUED)` | `InviteCreated` / `InviteCreateRejected` | `InviteProjection`；一次性/过期，不泄露家庭数据 |
| S18-N02 接受邀请 | `ConsentPolicy`、同行计划资格 | `B InviteAcceptance`、必要时 `B CohortMembership` | `InviteAccepted` / `InviteAcceptanceRejected` | `CohortProjection`；独立同意，不能强制建成员 |
| S18-N03 同行计划 | `CohortPlanTemplate`、可见性策略 | `B CohortPlan`、`B CohortMembership` | `CohortJoined` / `CohortJoinRejected` | `CohortProjection`；只共享明确允许内容，不排名 |
| S18-N04 激励结算 | `CampaignVersion`、`IncentiveRule`、封顶策略 | `B IncentiveLedgerEntry` | `IncentiveRecorded` / `IncentiveBlocked` | `IncentiveProjection`；仅单层、真实有效事件、可审计 |
| S18-N05 退出与撤回 | `CohortExitPolicy`、分享撤回策略 | `B CohortExit`、可见性状态变更 | `CohortExited` / `CohortExitRejected` | `CohortProjection`；退出不删个人事实，停止新增曝光 |
| O08-N01 商品配置 | `ProductSchema`、价格/退订规则 | `M ProductVersion`、`B ProductReview` | `ProductPublished` / `ProductConfigRejected` | `CommerceOpsProjection`；适用人群、权益边界 |
| O08-N02 权益配置 | `BenefitSchema`、次数/期限/SLA | `M BenefitVersion`、Membership plan 更新 | `BenefitPublished` / `BenefitConfigRejected` | `CommerceOpsProjection`；版本冻结，不追溯修改订单 |
| O08-N03 促销活动 | `CampaignSchema`、预算/资格/激励策略 | `M CampaignVersion` | `CampaignPublished` / `CampaignRejected` | `CommerceOpsProjection`；预算、期限、撤销、禁多层返佣 |
| O08-N04 退款/失效 | `RefundPolicy`、Entitlement revocation rules | `B EntitlementRevocation`、退款关联项 | `EntitlementRevoked` / `RevocationRejected` | `MembershipProjection`、`FinanceOpsProjection`；不抹除订单事实 |
| O09-N01 支付回调 | `PaymentProviderConfig`、签名/幂等策略 | `B PaymentRecord`、Order 状态 | `PaymentReceived` / `PaymentCallbackRejected` | `FinanceOpsProjection`；未验签拒绝，原始回调保全 |
| O09-N02 退款审批 | `RefundPolicy`、权限分离规则 | `B RefundDecision`、`B RefundRecord` | `RefundIssued` / `RefundRejected` | `FinanceOpsProjection`、`AuditEvent`；金额/原因/审批人完整 |
| O09-N03 日终对账 | `SettlementPolicy`、财务口径 | `B ReconciliationCase`、原始对账文件引用 | `ReconciliationOpened` / `ReconciliationEscalated` | `FinanceOpsProjection`；差异不可静默抹平 |
| O09-N04 结算输出 | `ContributionPolicy`、SettlementPolicy | `B SettlementStatement`、平台/服务方分录 | `SettlementGenerated` / `SettlementBlocked` | `FinanceOpsProjection`；仅 VERIFIED 贡献可结算 |

### 4.5 P05：社区、数据权利与安全信任

| 节点 | M/C 主数据与策略输入 | B 业务数据写入/读取 | E 事实事件 | P/A 与关键控制 |
|---|---|---|---|---|
| S19-N01 发布草稿 | `VisibilityType`、媒体/儿童敏感项策略 | `B Post(DRAFT)`、`B MediaReference` | `PostDraftCreated` / `PostDraftRejected` | `CommunityPostProjection`；默认私有、监护依据 |
| S19-N02 审核发布 | `ModerationPolicy`、风险等级/人工复核规则 | `B ModerationDecision`、`B Post(PUBLISHED/REJECTED)` | `PostPublished` / `PostRejected` | `CommunityFeedProjection`；AI 仅辅助，拒绝可申诉 |
| S19-N03 浏览互动 | `VisibilityPolicy`、InteractionPolicy | `B Interaction`、`B Report` | `InteractionRecorded`、`ReportSubmitted` / `InteractionDenied` | `CommunityFeedProjection`；互动不改成长事实 |
| S19-N04 编辑/撤回 | `PostRevisionPolicy`、留存/索引删除规则 | `B PostRevision`、`B Post(WITHDRAWN)` | `PostRevised`、`PostWithdrawn` / `PostMutationRejected` | `CommunityFeedProjection`、`AuditEvent`；停止推荐/新互动 |
| S19-N05 社区处置 | `ModerationActionPolicy`、申诉规则 | `B ModerationCase`、处置/封禁状态 | `ModerationDecided` / `ModerationEscalated` | `ModerationOpsProjection`；处置与商业激励分离 |
| S20-N01 权利请求 | `RightType`、代理/监护验证策略 | `B DataSubjectRequest(OPEN)` | `RightsRequested` / `RightsRequestRejected` | `RightsProjection`；请求人和代理关系验证 |
| S20-N02 范围评估 | `RetentionPolicy`、LegalHold、目的目录 | `B RightsAssessment(APPROVED/PARTIAL/DENIED)` | `RightsScopeAssessed` / `RightsScopeRejected` | `ComplianceProjection`；法定留存例外写明原因 |
| S20-N03 执行导出/删除 | `DeletionPolicy`、备份/索引级联规则 | `B ExportPackage` 或 `B DeletionJob` | `ExportGenerated`、`DeletionExecuted` / `DeletionFailed` | `RightsProjection`、`AuditEvent`；幂等、可验证、备份按期清理 |
| S20-N04 安全事件 | `IncidentSeverity`、响应/通知策略 | `B SecurityIncident(OPEN/CONTAINED/RESOLVED)` | `IncidentOpened` / `IncidentEscalated` | `ComplianceProjection`；证据保全，最小知情 |
| S20-N05 留存审计 | `RetentionPolicy`、分类与到期规则 | `B RetentionAudit`、`B RetentionFinding` | `RetentionAudited` / `RetentionViolationFound` | `ComplianceOpsProjection`；敏感访问全量留痕 |
| O10-N01 审核入队 | `ModerationPolicy`、队列/去重规则 | `B ModerationQueueItem` | `ModerationQueued` / `ModerationQueueRejected` | `ModerationOpsProjection`；AI 建议不可替人工决策 |
| O10-N02 风险处置 | `ModerationActionPolicy`、时限/证据规则 | `B ModerationDecision`、Post 状态 | `ModerationDecided` / `ModerationEscalated` | `ModerationOpsProjection`；理由、证据、时限完整 |
| O10-N03 申诉复核 | `AppealPolicy`、职责分离规则 | `B AppealDecision` | `AppealResolved` / `AppealEscalated` | `AppealProjection`；初审与复核角色分离 |
| O10-N04 规则复盘 | `PolicyVersion`、误报/漏报指标口径 | `M ModerationPolicyChange`、`B ReviewFinding` | `PolicyChanged` / `PolicyChangeRejected` | `ModerationOpsProjection`；不回写历史裁决 |
| O11-N01 权利工单 | `RightType`、监护/代理策略、SLA | `B RightsCase(OPEN)` | `RightsCaseOpened` / `RightsCaseRejected` | `ComplianceOpsProjection`；未成年人依据必查 |
| O11-N02 访问复核 | `AccessPolicy`、目的/角色矩阵 | `B AccessReview`、必要时 `B AccessRevocation` | `AccessReviewed`、`AccessRevoked` / `AccessReviewEscalated` | `AccessAdminProjection`；异常访问先隔离 |
| O11-N03 留存/删除执行 | `RetentionPolicy`、LegalHold、删除作业策略 | `B RetentionJob`、主表/缓存/索引删除状态 | `RightFulfilled`、`DeletionExecuted` / `DeletionBlocked` | `ComplianceOpsProjection`；法定留存显式期限与原因 |
| O11-N04 安全事件响应 | `IncidentResponsePolicy`、通知规则 | `B SecurityIncident`、响应任务 | `IncidentResolved` / `IncidentEscalated` | `ComplianceOpsProjection`；事件时间线不可静默修改 |

### 4.6 P06：运营、AI、指标、发布与组织治理

| 节点 | M/C 主数据与策略输入 | B 业务数据写入/读取 | E 事实事件 | P/A 与关键控制 |
|---|---|---|---|---|
| S21-N01 运营队列 | `QueueType`、SLA、优先级/风险策略 | `B OpsQueueItem`、`B Assignment` | `QueueAssigned` / `QueueAssignmentRejected` | `OpsQueueProjection`；每项待办有来源，不绕过权限 |
| S21-N02 交付监控 | `MetricDefinition`、QualityPolicy | 读取 ServiceTask/Quality/Complaint，写 `B DeliveryMetric` | `MetricSnapshotPublished` / `MetricBuildFailed` | `OpsDashboardProjection`；指标来自事实事件 |
| S21-N03 商业监控 | `BusinessMetricDefinition`、财务口径 | 读取 Order/Payment/Renewal，写 `B BusinessMetric` | `BusinessMetricPublished` / `MetricBuildFailed` | `OpsDashboardProjection`；意向不算收入 |
| S21-N04 安全合规监控 | `ComplianceMetricDefinition`、风险阈值策略 | 读取 Consent/Access/Incident，写 `B ComplianceAlert` | `ComplianceAlertRaised` / `AlertSuppressed` | `ComplianceProjection`；高风险告警必须闭环 |
| S21-N05 经营复盘 | `DecisionTemplate`、实验/闸门策略 | `B OperatingDecision`、行动项 | `DecisionRecorded` / `DecisionBlocked` | `OpsDashboardProjection`；相关性不等于疗效因果 |
| S22-N01 知识发布 | `KnowledgeSchema`、来源/许可/适用范围 | `M KnowledgeVersion(PUBLISHED)` | `KnowledgePublished` / `KnowledgeBlocked` | `AITraceProjection`；版本、owner、失效日 |
| S22-N02 上下文组装 | `ContextPolicy`、字段脱敏/目的策略 | `B ContextSnapshot` | `ContextAssembled` / `ContextDenied` | `AITraceProjection`；最小字段、授权范围、可删除 |
| S22-N03 模型调用 | `ModelRegistry`、RoutingPolicy、Gateway Policy | `B ModelAttempt`、`B ModelDraft` | `ModelCalled` / `ModelCallFailed` | `AITraceProjection`；唯一 Gateway、provider、成本、provenance |
| S22-N04 人工确认 | `HumanGatePolicy`、风险分级/审核职责 | `B HumanReviewDecision(APPROVED/REJECTED/EDITED)` | `AIReviewed` / `HumanReviewEscalated` | `AuditEvent`；AI 不写 canonical Fact，高风险必人工 |
| S22-N05 评估学习 | `EvaluationPolicy`、指标/偏差/安全规则 | `B EvaluationRecord`、`B LearningAction` | `EvalCompleted` / `EvalFailed` | `AIQualityProjection`；失败阻断发布，合成数据不冒充真实有效 |
| S24-N01 组织职责 | `CapabilityCatalog`、Domain Registry、责任矩阵 | `B OrgCapabilityMap`、变更记录 | `OrgResponsibilityDefined` / `OrgDefinitionRejected` | `GovernanceProjection`；业务/技术 owner 不得缺失 |
| S24-N02 合作协议 | `AgreementTemplate`、IP/DPA/SLA 规则 | `B CooperationAgreement(SIGNED)` | `AgreementSigned` / `AgreementRejected` | `GovernanceProjection`；代码、品牌、数据、模型和客户关系分离 |
| S24-N03 人才准入与授权 | `RoleDefinition`、资质/培训/定期复核策略 | `B StaffAccessGrant`、培训/复核记录 | `AccessGranted` / `StaffAccessRejected` | `AccessAdminProjection`；离职回收，高风险定期复核 |
| S24-N04 股权与激励 | `EquityPlan`、vesting/回购规则 | `B EquityGrant`、`B VestingEvent` | `EquityGranted`、`EquityVested` / `VestingRejected` | `GovernanceProjection`；不得以未验收贡献直接结算 |
| S24-N05 治理决策 | `GovernanceDecisionPolicy`、例外/补偿规则 | `B GovernanceDecision`、例外与期限 | `GovernanceDecided` / `GovernanceEscalated` | `GovernanceProjection`、`AuditEvent`；重大例外需授权和复盘 |
| O13-N01 指标定义 | `EventSchema`、业务问题、指标口径 | `M MetricDefinition(VERSIONED)` | `MetricDefined` / `MetricDefinitionRejected` | `AnalyticsOpsProjection`；只引用事实事件，口径版本化 |
| O13-N02 实验配置 | `ExperimentPolicy`、Guardrail、Consent/敏感数据规则 | `B Experiment(DRAFT/RUNNING/STOPPED)` | `ExperimentStarted`、`ExperimentStopped` / `ExperimentBlocked` | `AnalyticsOpsProjection`；未成年人敏感数据先过合规 |
| O13-N03 分群分析 | `CohortPolicy`、最小样本/去标识化策略 | `B CohortInsight`、聚合结果 | `CohortInsightPublished` / `CohortInsightSuppressed` | `AnalyticsOpsProjection`；不产家庭排名 |
| O13-N04 经营决策 | `DecisionPolicy`、质量/成本/风险口径 | `B OperatingDecision`、行动项 | `DecisionRecorded` / `DecisionEscalated` | `GovernanceProjection`；相关性不能推出疗效 |
| O14-N01 变更申请 | `ChangePolicy`、ADR/回滚/影响面模板 | `B ChangeRequest(SUBMITTED)` | `ChangeRequested` / `ChangeRejected` | `ReleaseOpsProjection`；状态机变更需业务 owner + ADR |
| O14-N02 环境验收 | `EnvironmentParityPolicy`、版本/配置清单 | `B EnvironmentParityReport` | `ParityVerified` / `ParityFailed` | `ReleaseOpsProjection`；三环境同功能、只换数据/外部适配器 |
| O14-N03 审计复核 | `AuditSchema`、完整性/不可抵赖策略 | `B AuditFinding`、修复任务 | `AuditReviewed` / `AuditFindingEscalated` | `ComplianceOpsProjection`；WORM 日志不可覆盖 |
| O14-N04 事故与复盘 | `IncidentResponsePolicy`、Postmortem 模板 | `B IncidentRecord`、`B Postmortem`、改进项 | `IncidentOpened`、`PostmortemClosed` / `RecoveryFailed` | `ReleaseOpsProjection`；先保护家庭和数据，改进项有 owner/期限 |

### 4.7 跨流程记忆体与多模态派生

| 节点 | M/C 主数据与策略输入 | B 业务数据写入/读取 | E 事实事件 | P/A 与关键控制 |
|---|---|---|---|---|
| Memory-N0 候选生成 | `MemoryPolicy`、用途/留存/主体规则、模态解析策略 | `B MemoryCandidate(PROPOSED)`、`B MediaAsset` 引用 | `MemoryCandidateProposed` / `MemoryCandidateBlocked` | AI 只能提候选；候选带 tenant/family/subject/purpose/consent/deletion |
| Memory-N1 家庭确认 | `MemoryConsentPolicy`、可见性和确认人规则 | `B MemoryConsent`、`B ChildMemory` / `B GuardianMemory` / `B RelationshipMemory` | `MemoryConfirmed` / `MemoryConfirmationRejected` | M0-M3 都有 TTL；关系记忆至少两个主体；不写诊断/商业画像 |
| Memory-N2 最小检索 | `ContextPolicy`、目的与区域策略 | 读取 `B Memory*`，写 `B MemoryRetrieval` | `MemoryRetrieved` / `MemoryRetrievalDenied` | 只读最小范围；用途/同意版本/过期/租户隔离不符即拒绝 |
| Memory-N3 纠正/删除 | `RetentionPolicy`、法定留存和删除级联 | `B MemoryCorrection`、`B MemoryDeletionJob/Proof` | `MemoryCorrected`、`MemoryDeleted` / `MemoryDeletionBlocked` | 原文、转写/OCR、Embedding、缓存、评估副本级联；证明可重放 |

## 5. 数据状态机、事件和补偿规则

### 5.1 主数据状态机

```text
DRAFT → REVIEW → APPROVED → PUBLISHED → RETIRED
                    ↘ REJECTED       ↘ ROLLED_BACK（保留历史版本）
```

主数据发布后不可原地修改。修订必须创建新 `version_id`；新业务选择新版本，存量业务继续引用原版本。回滚只改变“后续选择的默认版本”，不得删除已产生的业务事实。

### 5.2 业务数据状态机

```text
CREATED/DRAFT → PENDING → ACTIVE/IN_PROGRESS → COMPLETED/VERIFIED
                     ↘ REJECTED/CANCELLED/PAUSED/REWORK
任何终态 → CorrectionEvent / CompensationEvent（不覆盖原记录）
```

支付、权益、积分、FGCN 贡献和删除作业还必须支持幂等重试、死信和人工接管。`balance_after`、运营汇总、UI 计数都不是权威事实；权威余额/状态必须能由账本或事件重放得到。

### 5.3 最小事件集

每个 L2 场景至少需要：

1. 一个成功事件（例如 `EvidenceFrozen`、`BookingConfirmed`）；
2. 一个拒绝/失败事件（例如 `AssessmentSubmissionRejected`、`BookingRejected`）；
3. 一个取消、撤回或补偿事件（适用于可撤回/可退款/可删除流程）；
4. 一个审计事件，包含 actor、purpose、before/after、reason；
5. 一个可重建投影消费位置，记录 `last_event_id` 和投影版本。

## 6. 数据库与物理落地

### 6.1 Schema 边界

```text
identity / tenancy / consent
family
assessment / growth / journey
program / content
service / partner
commerce / membership / loyalty_points
community
ai_runtime
ops / analytics
security / audit
```

同一 schema 内可以有多个聚合，但不能把主数据和业务事实只靠一个 `status` 字段混合。跨 schema 只允许：

- Query Port 返回只读 DTO；
- Domain Event + Outbox 建立投影；
- 明确的工作流命令调用目标域；
- 不允许跨 schema 直接写对方表。

### 6.2 表命名和字段要求

| 数据类型 | 命名建议 | 必须字段 | 额外要求 |
|---|---|---|---|
| 主数据 | `*_definitions`、`*_versions`、`*_catalog`、`*_policies` | `version_id/status/effective_from/to/owner` | 唯一约束覆盖业务键 + 版本；发布后不可变 |
| 业务聚合 | `family_*`、`service_*`、`order_*`、`rights_*` | `tenant_id/family_id/subject_id/state` | 状态迁移只能经 Command/Policy |
| 业务事实 | `*_events`、`*_records`、`*_ledger` | `occurred_at/source/actor/provenance` | 追加写；纠错用补偿事件 |
| 投影 | `*_projection`、`*_view` | `projection_version/last_event_id` | 可删除、可重放、不可写事实 |
| 审计 | `platform_audit_events`、`access_logs` | `action/resource/before/after/reason` | WORM/追加写，业务角色不可覆盖 |

### 6.3 现有 WIP 的归类裁决

| 现有 WIP 面 | 主数据归类 | 业务数据归类 | 不能混淆的点 |
|---|---|---|---|
| `family` | 关系类型、地区/生命周期枚举、字段字典 | Family、Person、Membership、Relationship、ProfileChange | Family 是主体主数据；关系变化是业务事实 |
| `assessment` | Tool、Version、Question、解释规则 | Session、Response、Submission、Evidence、Operation | 证据是 Fact；AI run 不是答案事实 |
| `journey` | Journey/Phase/Task Template、提醒策略 | Plan、Phase、ActionTask、ActionRecord、Decision | 计划版本冻结；行动完成不等于 Outcome |
| `service`/FGCN | ServiceType、Offering、SLA、Blueprint、QualityPolicy | Booking、Case、Task、Assignment、Delivery、Quality、Contribution | 验收后才贡献；贡献不等于付款 |
| `commerce`/`membership` | Product、Price、Benefit、Tier、Promotion | Intent、Order、Payment、Subscription、Entitlement、Usage | 意向不等于订单；退款反向失效权益 |
| `loyalty_points` | EarnRule、RedemptionItem、ExpiryRule | Account、Ledger、Redemption、Reconciliation | Ledger 是权威；禁止默认余额 |
| `product_intelligence`/`ai_runtime` | Knowledge、Prompt、Model、Routing、Evaluation Policy | Signal、Attempt、Draft、Review、Evaluation、Learning | 运营/AI 输出不能写儿童成长 Fact |
| `audit`/`outbox`/`idempotency` | AuditSchema、RetentionPolicy、EventSchema | AuditEvent、OutboxEvent、IdempotencyKey、DeletionJob | 所有业务写入必须同事务出站 |

## 7. 环境等价与数据工厂

开发、测试、生产必须执行同一份 migration、API、状态机、权限、审计、事件和作业。三环境差异只允许出现在：

| 可替换项 | 开发/测试 | 生产 | 不得改变 |
|---|---|---|---|
| 主数据内容 | 合成的商品、测评、模板、伙伴、策略版本 | 真实经审批的版本 | 表结构、版本状态机、发布/回滚规则 |
| 业务主体 | 合成家庭、成员、预约、订单、服务 | 真实主体和交易 | 字段、关系、状态迁移、权限 |
| 外部适配器 | sandbox/fake/noop，保留签名、失败、超时、重试语义 | 真实支付、消息、模型供应商 | port、幂等、错误码、补偿路径 |
| AI | 固定模型桩/受控 sandbox | 合规 Model Gateway | provenance、人工升级、拒答和审计 |
| 删除/事故 | 合成数据演练真实 job | 真实数据执行同一 job | 校验、回滚、审计、完成事件 |

禁止通过 `/dev` 路由、静态 JSON、缺少支付/审核节点或“测试专用简化状态机”降低功能。测试数据必须具备完整主数据版本、业务关系和生命周期，才能证明生产路径。

## 8. 数据架构实施台账

每个节点按以下字段建立机器可读台账（建议后续落为 YAML/数据库表）：

```text
scenario_id
process_group_id
process_level
node_id
master_data_ids[]
policy_ids[]
business_aggregate
business_tables[]
command
pre_state
post_state
success_event
failure_event
compensation_event
projection
audit_event
classification
retention_policy
deletion_cascade[]
fixture_factory
environment_parity_test
implementation_status
owner
```

### 8.1 迁移/实现顺序

1. **P0：P01-P02 主链**——Family、Consent、Assessment、Growth、Journey、Action、AI Context 的主数据版本和业务事实，先让 `S04→S07` 通过真实 PostgreSQL migration、事件和投影。
2. **P1：P03 服务协作**——ServiceCase、Task、Booking、Delivery、Quality、Contribution，补齐 FGCN 验收和争议补偿。
3. **P2：P04 商业链**——Product、Order、Payment、Membership、Entitlement、PointsLedger、Reconciliation，确保 UI-17/UI-32 不再依赖硬编码。
4. **P3：P05 信任链**——Community、Rights、Retention、SecurityIncident，验证删除级联到投影、缓存、媒体和 AI trace。
5. **P4：P06 经营治理**——Ops、Metrics、AI Evaluation、Partner、Organization、Parity、Incident，形成可审计的运营闭环。

## 9. 完成定义

只有同时满足以下条件，场景数据架构才可从 `DESIGN_ONLY/PARTIAL` 提升为 `IMPLEMENTED`：

- 主数据有版本、owner、审批、发布、回滚和历史冻结；
- 业务数据有权威聚合、完整状态机、事务边界和唯一写入者；
- 每个 L4 节点有成功、失败/拒绝、补偿（如适用）事件；
- 事件包含全局 envelope，Outbox 与业务写入同事务，消费者可幂等重放；
- UI/运营/分析全部由 Projection 或 Query DTO 提供，不能反写事实；
- 访问、同意、人工闸门、状态变化和数据权利全部可审计；
- 留存、删除、备份、搜索/向量索引和媒体级联已验证；
- dev/test/prod 使用同一功能和数据 schema，只替换数据与外部副作用；
- Python 验收测试从同一 Alembic migration 建库，禁止仅 `create_all` 证明能力。

## 10. 应用层调用边界

对象、表和关系由 Domain Owner 维护；应用层只能通过 `Application Service → Domain Port → Repository` 使用它们。用例、接口和工作流的详细分解见 `docs/06_platform/APPLICATION_ARCHITECTURE.md`。任何应用用例登记时必须同时填写 `scenario_id/node_id` 与 `business_aggregate/table_name/relationship`，否则不能进入实现台账。
