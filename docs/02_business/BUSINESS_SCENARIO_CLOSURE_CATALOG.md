---
id: BIZ-CLOSURE-CATALOG-001
title: Family 业务场景闭环目录与节点契约
type: business
status: draft
version: 0.2
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
supersedes: null
superseded_by: null
---

# Family 业务场景闭环目录与节点契约

> 本稿将商业蓝图、Word 汇总、三份核心 PPT 与其他合作/治理方案、34 个 UI、既有业务文档和 Python 代码重新拆成可验收的业务场景。它是重建工作稿，不把设计愿景冒充为已实现能力。

## 1. 输入资料与边界

| 输入 | 本稿使用方式 | 可信层级 |
|---|---|---|
| 商业蓝图图片 | 五个商业支柱、七段客户链、FGCN 主链、双飞轮 | 商业意图，不是系统事实 |
| 三份榜样教育 PPT | 产品阶梯、AI 定位、交付与长期关系 | 产品/战略证据 |
| 《家庭教育大模型平台科技公司项目合作方案》 | 平台化、伙伴、数据与协作网络 | 平台/合作证据 |
| 《榜样科技创业合伙人股权架构设计》 | 组织、人才、股权与退出 | 公司治理证据 |
| Word《项目纲领与五份 PPT 逐页解读》 | 五份材料登记、冲突裁决、30/90/180/365 闸门 | 战略汇总证据 |
| 34 个 UI 与 `ui-registry.ts` | 用户入口、展示状态和交互边界 | 产品基线 |
| `docs/02_business/*`、`docs/04_domains/*`、`docs/07_data/*`、`docs/10_engineering/*` | 领域、数据、工程约束 | 当前仓库规范 |
| Python 代码与测试 | 已运行能力和缺口 | 当前实现事实，优先于资料 |

本目录覆盖家庭客户、服务供给、协作网络、商业交易、社区、AI、运营、机构伙伴和公司治理；支付渠道、短信、模型供应商等外部系统作为参与者，不把外部系统当作领域事实源。

## 2. 拆解方法与完成度

每个场景均有触发、角色、节点、结束条件；每个节点写清 `输入 → 活动 → 输出 → 业务规则`。节点输出必须标注为 Fact、Perspective、Recommendation、Action 或 Outcome。UI 只消费输出，不定义事实。

| 状态 | 含义 |
|---|---|
| `IMPLEMENTED` | Python/API/持久化/测试已形成可运行纵向切片 |
| `PARTIAL` | 有部分 API、投影或 UI，但闭环或异常路径不完整 |
| `DESIGN_ONLY` | 有业务设计，尚未形成可运行能力 |
| `GATE_BOUNDARY` | 受数据、合规、支付或真实交付闸门约束，暂不接生产事实 |

## 3. 24 个场景总目录

| 编号 | 业务闭环 | 主要角色 | 主要 UI | 当前判断 |
|---|---|---|---|---|
| S01 | 内容/直播/活动触达与家庭进入 | 家长、运营、内容方 | UI-01、22、23 | PARTIAL |
| S02 | 账户、家庭成员、角色与可见性 | 家长、家庭成员、平台 | UI-33、跨页 | PARTIAL |
| S03 | 测评目录、目的说明与同意 | 家长、平台、合规 | UI-07 | PARTIAL |
| S04 | 测评执行、提交与证据冻结 | 家长、孩子、平台 | UI-02、UI-02-result | IMPLEMENTED |
| S05 | 假设解读、家庭确认与成长入营 | 家长、AI、平台 | UI-03 | PARTIAL |
| S06 | 90 天计划生成、确认与阶段复盘 | 家长、AI、陪跑 | UI-04、05、08 | PARTIAL |
| S07 | 21 天行动、今日任务与过程回读 | 家庭、AI、陪跑 | UI-09、10、11 | PARTIAL |
| S08 | 家庭过程报告、成果记录与私有故事 | 家庭、陪跑、平台 | UI-08、12、29 | GATE_BOUNDARY / PARTIAL |
| S09 | AI 助手、提醒、解释与人工升级 | 家庭、AI、人工服务 | UI-03、05、09、10 | DESIGN_ONLY / PARTIAL |
| S10 | 陪跑服务、客户服务与服务记录 | 家长、管家、平台 | UI-05、06、31、34 | PARTIAL |
| S11 | 专家/教师供给发现与服务时段 | 专家、教师、运营 | UI-19、20 | PARTIAL |
| S12 | 咨询预约、沙龙报名、取消与履约 | 家长、专家、活动方 | UI-21、22、23、24 | PARTIAL |
| S13 | FGCN 案件、任务、资源匹配与验收 | 平台、资源方、管家 | UI-21、24、31、34 | DESIGN_ONLY |
| S14 | 质量反馈、投诉、恢复与争议裁决 | 家庭、服务方、运营 | UI-24、34 | DESIGN_ONLY |
| S15 | 商品目录、方案详情与购买意向 | 家长、商品运营 | UI-13、14 | PARTIAL |
| S16 | 会员方案、权益激活与年度续购 | 家长、平台、支付 | UI-06、18、30 | PARTIAL |
| S17 | 积分账本、订单资产与权益回读 | 家长、平台、财务 | UI-17、32 | GATE_BOUNDARY / PARTIAL |
| S18 | 邀请、同行计划与增长激励 | 家长、被邀请家庭、运营 | UI-15、16 | PARTIAL |
| S19 | 家庭社区内容、审核、互动与撤回 | 家长、社区、审核员 | UI-25、26、27、28 | GATE_BOUNDARY / PARTIAL |
| S20 | 家庭数据权利、删除、留存与安全 | 家长、孩子、合规、安全 | UI-33、跨页 | PARTIAL |
| S21 | 运营工作台、质量监控与经营指标 | 运营、管理、财务 | 运营端 | DESIGN_ONLY |
| S22 | AI Runtime、知识、上下文、评估与学习 | AI、评估员、平台 | 跨页/后台 | DESIGN_ONLY |
| S23 | 机构/城市伙伴合作与供给准入 | 机构、城市伙伴、运营 | UI-19～24、运营端 | DESIGN_ONLY |
| S24 | 合作、组织、人才与股权治理 | 管理层、法务、人力 | 管理/法务端 | DESIGN_ONLY |

> 实现切片说明：`VS-01` 不是新增的第 25 个业务场景，而是把 S05（成长解读/确认）与
> S09（AI/需求表达）之间缺失的 N0→N1 需求捕获先落成可运行链路。它使用
> `NeedSignal → FamilyNeed` 和 `POST /families/{family_id}/needs/signals`，后续 N1→N8
> 仍按本目录的场景节点逐步补齐。

## 4. 34 个 UI 覆盖矩阵

| UI | 场景 | UI | 场景 |
|---|---|---|---|
| UI-01 | S01、S02 | UI-18 | S16、S17 |
| UI-02 | S04 | UI-19 | S11、S23 |
| UI-03 | S05、S09 | UI-20 | S11 |
| UI-04 | S06 | UI-21 | S12、S13 |
| UI-05 | S06、S07、S10 | UI-22 | S01、S12、S23 |
| UI-06 | S10、S16 | UI-23 | S01、S12 |
| UI-07 | S03 | UI-24 | S10、S12、S13、S14 |
| UI-08 | S06、S08 | UI-25 | S19 |
| UI-09 | S07、S09 | UI-26 | S19 |
| UI-10 | S07、S09 | UI-27 | S19 |
| UI-11 | S07、S08 | UI-28 | S19 |
| UI-12 | S08、S19 | UI-29 | S08、S20 |
| UI-13 | S15 | UI-30 | S16 |
| UI-14 | S15 | UI-31 | S10、S13 |
| UI-15 | S18 | UI-32 | S17 |
| UI-16 | S18 | UI-33 | S02、S20 |
| UI-17 | S17 | UI-34 | S10、S12、S14 |

## 5. 场景节点契约

### S01 内容/直播/活动触达与家庭进入

闭环：内容或活动被发现 → 了解价值与适用人群 → 家长授权进入 → 建立可追踪来源。

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S01-N01 内容发布（运营） | 内容稿、适用年龄、渠道 | 审核、版本化、发布/下架 | `ContentVersion(PUBLISHED)` | 来源、版权、失效日期和适用人群必填 |
| S01-N02 直播/活动排期（运营） | 主讲人、时间、容量、报名规则 | 建立活动场次和报名窗口 | `ActivitySlot` | 容量、候补、取消截止时间不可由 UI 绕过 |
| S01-N03 家庭发现（家长） | 渠道、推荐位、分享链接 | 查看内容/活动详情 | `ReachEvent` | 只记录最小必要行为，不把浏览当成购买同意 |
| S01-N04 进入家庭（家长） | 登录会话、来源、进入目的 | 创建或选择家庭，转入 S02/S03 | `EntryEvent`、路由状态 | 入口归因可追溯；未登录不得创建家庭事实 |

### S02 账户、家庭成员、角色与可见性

闭环：账户注册/登录 → 家庭建立 → 成员邀请或绑定 → 角色与可见性生效。

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S02-N01 身份建立（平台） | 登录凭证、验证结果 | 建立用户与会话 | `User`、`Session` | 身份认证与家庭授权分离；会话可撤销 |
| S02-N02 创建家庭（家长） | 家庭名称、地区、目的 | 创建租户边界和家庭档案 | `Family(ACTIVE)` | 家庭不是用户别名；一个用户可有多个家庭 |
| S02-N03 成员邀请/绑定（家长） | member、关系、邀请渠道 | 发送邀请或绑定孩子档案 | `FamilyMembership(PENDING/ACTIVE)` | 未成年人关系需监护依据；重复邀请幂等 |
| S02-N04 角色与可见性（家长/平台） | role、purpose、资源范围 | 授权读取/写入范围 | `VisibilityPolicy`、审计事件 | 最小权限；孩子、服务方和运营不可互看无关家庭 |

### S03 测评目录、目的说明与同意

闭环：选择测评 → 阅读用途和风险 → 分离同意 → 取得可执行的测评版本。

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S03-N01 测评目录（平台） | 测评版本、年龄、目的 | 展示测评说明和适用范围 | `AssessmentCatalogItem` | 题目版本、用途、预计时长、退出方式可见 |
| S03-N02 目的选择（家长） | subject、purpose | 选择成长诊断/计划/服务等目的 | `PurposeSelection` | 每个目的单独授权，不以勾选换服务 |
| S03-N03 同意采集（家长） | purpose、privacy notice、监护关系 | 记录同意、拒绝或撤回 | `ConsentRecord` | 撤回后停止新增处理；同意版本不可覆盖 |
| S03-N04 启动资格（平台） | consent、成员关系、测评版本 | 校验并返回启动令牌 | `AssessmentStartToken` | 无有效同意、越权或过期版本必须拒绝 |

### S04 测评执行、提交与证据冻结

闭环：回答题目 → 暂存 → 提交 → 证据冻结 → 可供解释但不直接成为事实。

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S04-N01 创建会话（平台） | start token、版本 | 建立草稿会话和题目游标 | `AssessmentSession(DRAFT)` | 版本冻结；幂等键不得重复建会话 |
| S04-N02 保存回答（家长/孩子） | question、answer、actor | 校验类型、保存草稿 | `AssessmentResponse(DRAFT)` | 只能写当前会话；不可写他人 subject |
| S04-N03 提交测评（家长） | 完整响应、同意快照 | 校验完整性并冻结 | `AssessmentSubmission(COMPLETED)` | 提交后回答不可变；撤回同意或缺题拒绝 |
| S04-N04 生成证据（平台） | 冻结响应、版本 | 生成可追溯证据包 | `EvidenceSet` | 证据保留来源、时间、范围；不含推断标签 |
| S04-N05 查看结果（家长） | evidence、解释权限 | 返回结果投影 | `AssessmentResultProjection` | 结果只展示授权范围，不展示内部敏感评分细节 |

### S05 假设解读、家庭确认与成长入营

闭环：证据解释 → 形成假设 → 家庭确认/驳回 → 建立成长意图和入营状态。

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S05-N01 解释证据（AI/规则） | EvidenceSet、规则版本 | 生成维度解释与限制 | `GrowthPerspective` | AI 输出是 Perspective，必须带来源、版本和置信限制 |
| S05-N02 形成假设（AI/平台） | perspective、家庭上下文 | 生成可讨论的成长假设 | `GrowthHypothesis(PROPOSED)` | 不写 canonical fact；高风险主题转人工 |
| S05-N03 家庭确认/驳回（家长） | hypothesis、问题清单 | 确认、修改、驳回或稍后处理 | `GrowthIntent` 或 `HypothesisDismissed` | 未确认不得生成计划；确认人和时间可审计 |
| S05-N04 入营（平台/陪跑） | GrowthIntent、服务选择 | 建立 onboarding 和服务入口 | `Onboarding(ACTIVE)` | 不能把购买直接当作成长确认；重复入营幂等 |

### S06 90 天计划生成、确认与阶段复盘

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S06-N01 计划草案（AI/规则） | GrowthIntent、模板、优先级 | 生成阶段目标和候选行动 | `PlanPreview` | 草案不是承诺；显示依据、限制和可编辑项 |
| S06-N02 创建计划（家长） | preview、优先级、幂等键 | 建立四阶段计划 | `JourneyPlan(DRAFT)` | 当前 onboarding 只能有一个主计划 |
| S06-N03 确认计划（家长） | plan、家庭确认 | 激活首阶段 | `JourneyPlan(ACTIVE)` | 必须有有效同意、权限和已确认意图 |
| S06-N04 阶段执行（家庭） | action facts、日期 | 记录过程并生成进度投影 | `PhaseProgress` | 进度不是家庭总分，不推断疗效或排名 |
| S06-N05 阶段复盘（家长/陪跑） | progress、观察、家庭决定 | CONTINUE/ADJUST/PAUSE | `PhaseDecision`、新状态 | 阶段迁移需明确决策；AI 只能提出建议 |

### S07 21 天行动、今日任务与过程回读

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S07-N01 生成今日任务（平台） | active phase、day、家庭节奏 | 选择任务并设定截止时间 | `ActionTask(ASSIGNED)` | 任务来源、难度和适用成员可解释 |
| S07-N02 提醒与开始（AI/家庭） | task、提醒偏好 | 推送提醒，记录开始 | `TaskStarted` | 尊重免打扰和撤回；不得以提醒代替同意 |
| S07-N03 完成/跳过（家庭） | task、check-in、note | 记录完成、部分完成或跳过 | `ActionRecord` | 只记录行为事实；重复提交幂等 |
| S07-N04 过程回读（AI/陪跑） | action records、家庭反馈 | 生成观察与下一步建议 | `ProcessPerspective`、`Recommendation` | 不生成家庭总分；高风险反馈升级人工 |
| S07-N05 21 天结项（家长/陪跑） | day 1-21 records、家庭决定 | 复盘并进入 S08 或调整 | `ChallengeReview` | 结项不等于结果达成，缺失数据要显式标注 |

### S08 家庭过程报告、成果记录与私有故事

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S08-N01 过程报告（平台） | action facts、phase decisions | 汇总时间线、参与度和观察 | `ProgressReport` | 只呈现可追溯事实与标注的观点 |
| S08-N02 成果确认（家庭/陪跑） | report、家庭证据 | 选择可确认成果或继续观察 | `OutcomeRecord(PENDING/CONFIRMED)` | Outcome 需主体确认或明确证据，不由完成率自动生成 |
| S08-N03 私有故事（家长） | text、media、visibility | 创建、编辑、撤回家庭故事 | `FamilyStory` | 默认私有；公开前再次确认，不得用于商业画像默认授权 |
| S08-N04 年度沉淀（平台） | confirmed outcomes、story consent | 生成年度回顾投影 | `AnnualReviewProjection` | 不做家庭排名；可删除、导出、限制用途 |

### S09 AI 助手、提醒、解释与人工升级

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S09-N01 提问（家庭） | prompt、purpose、context permission | 接收问题并分类风险 | `AIRequest` | 目的限定、最小上下文；儿童敏感话题默认收紧 |
| S09-N02 上下文回答（AI Gateway） | ContextSnapshot、knowledge version | 生成草稿回答 | `ModelDraft` | 领域不直连供应商；记录模型、提示词版本和 provenance |
| S09-N03 建议与提醒（AI） | draft、task、preferences | 生成 Recommendation 或提醒 Action | `Recommendation` / `ReminderAction` | AI 不直接改事实；外部副作用需用户授权和幂等 |
| S09-N04 解释与反馈（家庭） | draft、sources | 展示依据、限制并接受反馈 | `ExplanationView`、`AIFeedback` | 不能宣称诊断/疗效；用户可拒绝建议 |
| S09-N05 风险升级（AI/人工） | risk signal、conversation | 建立人工工单，必要时暂停自动化 | `HumanEscalationCase` | 自伤、虐待、医疗/法律等高风险必须人工处置并留痕 |

### S10 陪跑服务、客户服务与服务记录

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S10-N01 服务开通（平台/管家） | membership、service plan | 分配服务层级和责任人 | `ServiceEntitlement` | 权益来自有效订单/会员，不因 UI 展示自动生效 |
| S10-N02 服务触达（管家） | family context、open tasks | 消息、电话、回访或资料发送 | `ServiceInteraction` | 触达目的、主体、时间和授权可审计 |
| S10-N03 客户问题（家长） | issue、attachments | 建立并跟踪客服工单 | `SupportTicket` | 工单状态可追踪；敏感附件最小可见 |
| S10-N04 服务记录（管家） | interaction、notes、evidence | 记录服务事实和下一步 | `ServiceRecord` | 服务记录不是 AI 事实；不得回写未确认成长结果 |
| S10-N05 服务结束（管家/家长） | completion、feedback | 关闭服务或转 S14 | `ServiceCase(CLOSED)` / `QualitySignal` | 关闭前必须有交付证据或明确未完成原因 |

### S11 专家/教师供给发现与服务时段

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S11-N01 供给档案（专家） | identity、qualification、specialty | 建立并验证教师/专家档案 | `ProviderProfile` | 资质、服务范围、有效期可核验 |
| S11-N02 服务产品（运营/专家） | service type、price、SLA | 定义可预约服务 | `OfferingVersion` | 价格、交付物、取消规则和版本冻结 |
| S11-N03 时段发布（专家） | timezone、availability、capacity | 发布可预约时段 | `AvailabilitySlot` | 时区、容量、冲突和临时关闭必须处理 |
| S11-N04 家庭匹配（平台） | family need、consent、filters | 过滤并排序候选供给 | `ProviderRecommendation` | 只用授权范围；推荐不是强制分配，不泄露无关家庭信息 |

### S12 咨询预约、沙龙报名、取消与履约

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S12-N01 查看详情（家长） | offering/activity、slot | 展示服务内容、价格、须知 | `BookingPreview` | 关键条款、适用对象和取消窗口在确认前可见 |
| S12-N02 创建预约（家长） | slot、family、consent、幂等键 | 锁定时段并创建预约 | `Booking(PENDING/CONFIRMED)` | 一个时段不可超卖；重复提交幂等 |
| S12-N03 取消/改期（家长/平台） | booking、reason、time | 释放时段并计算规则结果 | `Booking(CANCELLED/RESCHEDULED)` | 按服务规则退款/扣次；不可伪造已履约 |
| S12-N04 履约签到（家庭/服务方） | booking、attendance | 记录开始、参与和结束 | `AttendanceRecord` | 签到不等于质量或 Outcome；缺席要有原因 |
| S12-N05 服务回读（家长/平台） | attendance、feedback | 评分、反馈、转 S14 | `ServiceFeedback` | 评价不可修改原始事实；争议进入独立处理 |

### S13 FGCN 案件、任务、资源匹配与验收

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S13-N01 建立 ServiceCase（平台） | confirmed intent、service need | 建立服务案件和边界 | `ServiceCase(OPEN)` | 一个案件一个责任边界；家庭、服务接受者和付款方可分离 |
| S13-N02 拆分 ServiceTask（管家） | blueprint version、deliverables | 拆解任务、期限和验收标准 | `ServiceTask(ASSIGNED)` | 任务必须可验收；不得用模糊目标结算 |
| S13-N03 资源匹配与授权（平台） | task、provider capacity、consent | 匹配资源并授予最小访问权 | `TaskAssignment` | 先授权后访问；冲突、拒绝和替补可追踪 |
| S13-N04 交付留痕（资源方） | assignment、deliverable、evidence | 上传交付物和服务记录 | `DeliveryRecord(SUBMITTED)` | 交付物版本化；AI 草稿不能替代资源方确认 |
| S13-N05 质量验收（管家/家庭） | delivery、acceptance criteria | 验收、驳回、返工 | `QualityCheck(VERIFIED/REWORK)` | 验收标准在任务创建时冻结；驳回必须有原因 |
| S13-N06 贡献确认（平台） | verified delivery、contribution policy | 生成贡献凭证和分配依据 | `ServiceContribution`、`AllocationStatement` | 贡献不是付款；只有 VERIFIED 才能进入分配计算 |

### S14 质量反馈、投诉、恢复与争议裁决

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S14-N01 反馈/投诉（家庭） | service、rating、evidence | 提交质量信号 | `QualitySignal` | 不得因差评阻止事实留存；匿名与实名按规则处理 |
| S14-N02 分级与响应（运营） | signal、SLA、risk | 分级、指派、通知 | `ComplaintCase(OPEN)` | 高风险优先；响应时限可监控不可静默改写 |
| S14-N03 恢复方案（服务方/运营） | complaint、delivery facts | 补交付、退款、改派或道歉 | `RecoveryPlan` | 恢复动作须得到授权并记录成本/责任 |
| S14-N04 争议裁决（运营/合规） | evidence、双方陈述 | 独立复核并作出裁决 | `DisputeDecision` | 裁决与原始事实分离；当事人可申诉 |
| S14-N05 关闭与学习（平台） | decision、follow-up | 关闭案件、更新质量指标 | `ComplaintCase(CLOSED)`、`QualityLearning` | 不删除原始记录；学习结果需去标识化和权限控制 |

### S15 商品目录、方案详情与购买意向

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S15-N01 商品上架（运营） | product、price、benefits | 审核并发布版本 | `ProductVersion(PUBLISHED)` | 价格、库存/容量、适用人群和退订规则明确 |
| S15-N02 查看方案（家长） | product id、family context | 展示详情、交付边界和权益 | `ProductDetailProjection` | 不夸大疗效；商业承诺与服务事实分离 |
| S15-N03 购买意向（家长） | product、purpose、family | 生成咨询/加入购物车意向 | `PurchaseIntent` | 意向不等于订单；不得未经确认收费 |
| S15-N04 方案校验（平台） | entitlement needs、existing orders | 校验冲突、重复购买和资格 | `PurchaseEligibility` | 结果可解释；失败原因对用户可见 |

### S16 会员方案、权益激活与年度续购

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S16-N01 会员下单（家长） | plan、payer、payment intent | 创建订单并请求支付 | `MembershipOrder(PENDING)` | 付款方是家长/组织主体；未支付不得激活权益 |
| S16-N02 支付确认（支付/平台） | gateway event、idempotency key | 验签、入账、更新订单 | `PaymentRecord(SUCCEEDED/FAILED)` | 只接受可信回调；重复回调幂等 |
| S16-N03 权益激活（平台） | paid order、benefit version | 激活会员和服务权益 | `Membership(ACTIVE)`、`Entitlement` | 权益版本冻结；退款/撤销反向失效 |
| S16-N04 会员使用（家庭） | entitlement、service request | 消耗次数/服务窗口 | `EntitlementUsage` | 使用必须授权、幂等；不可超额消耗 |
| S16-N05 年度续购（家长/平台） | expiry、renewal choice、price | 提醒、续购或结束 | `RenewalDecision` | 自动续费需单独授权；不续购不得继续计费 |

### S17 积分账本、订单资产与权益回读

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S17-N01 订单资产（平台） | paid order、refund events | 建立可追溯资产 | `OrderAsset` | 订单、支付、权益三者分离；退款可反向关联 |
| S17-N02 积分事件（平台） | verified contribution、campaign rule | 记入积分账本 | `PointsLedgerEntry` | 只能由授权事件记账；账本不可直接覆盖 |
| S17-N03 积分使用（家长） | ledger、redemption、幂等键 | 冻结、扣减、兑换 | `PointsRedemption` | 余额不足拒绝；重复兑换幂等 |
| S17-N04 资产回读（UI） | orders、entitlements、ledger | 汇总订单、权益、积分状态 | `AssetProjection` | 读模型不能创造交易事实；展示以账本为准 |
| S17-N05 对账（财务/运营） | gateway、ledger、orders | 对账、挂起、人工修复 | `ReconciliationCase` | 差异不可静默抹平；修复需双人/审计规则 |

### S18 邀请、同行计划与增长激励

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S18-N01 创建邀请（家长） | family、invite purpose | 生成一次性邀请 | `InviteToken` | 令牌过期、单次使用；不暴露家庭数据 |
| S18-N02 接受邀请（被邀请人） | token、identity、consent | 加入同行计划/家庭关系 | `InviteAcceptance` | 被邀请人独立同意；不能强制创建家庭成员 |
| S18-N03 同行计划（平台） | cohort、period、content | 建立同行任务和可见范围 | `CohortMembership`、`CohortPlan` | 只共享明确允许的内容；不展示家庭排名 |
| S18-N04 激励结算（平台/运营） | verified referral、campaign rule | 计算透明单层激励 | `IncentiveLedgerEntry` | 禁止多层返佣；必须以真实有效事件为依据 |
| S18-N05 退出与撤回（家长） | membership、withdraw reason | 退出同行计划并关闭分享 | `CohortExit` | 退出不删除个人事实；撤回后停止新增曝光 |

### S19 家庭社区内容、审核、互动与撤回

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S19-N01 发布草稿（家长） | text、media、visibility | 创建草稿并选择可见范围 | `Post(DRAFT)` | 默认私有；未成年人内容需监护与敏感项检查 |
| S19-N02 审核发布（审核员/规则） | post、risk policy | 机审、人工复核、发布或拒绝 | `ModerationDecision`、`Post(PUBLISHED)` | AI 只能辅助审核；拒绝原因可申诉 |
| S19-N03 浏览互动（社区） | post、viewer、reaction/comment | 展示、点赞、评论、举报 | `Interaction`、`Report` | 按可见性策略过滤；互动不改写成长事实 |
| S19-N04 编辑/撤回（家长） | post、actor | 编辑、隐藏、删除或撤回公开 | `PostRevision` / `Post(WITHDRAWN)` | 保留审计；撤回后停止推荐和新互动 |
| S19-N05 社区处置（运营） | report、policy | 限流、封禁、申诉复核 | `ModerationCase` | 处置与商业激励分离，不因付费获得免审 |

### S20 家庭数据权利、删除、留存与安全

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S20-N01 权利请求（家长/孩子） | identity、request type | 访问、更正、导出、删除或撤回 | `DataSubjectRequest` | 请求人和代理关系必须验证 |
| S20-N02 范围评估（合规） | records、purpose、legal hold | 确认可处理范围和例外 | `RightsAssessment` | 最小范围；法定留存需说明期限和原因 |
| S20-N03 执行导出/删除（平台） | approved request、scope | 生成导出包或删除/匿名化 | `ExportPackage` / `DeletionJob` | 删除幂等、可验证；备份按期限清理 |
| S20-N04 安全事件（安全） | alert、access logs | 分级、隔离、通知、修复 | `SecurityIncident` | 事件不静默；最小知情和证据保全 |
| S20-N05 留存审计（合规） | retention policy、deletion logs | 检查超期数据和访问 | `RetentionAudit` | 不以测试数据冒充生产事实；敏感访问全量留痕 |

### S21 运营工作台、质量监控与经营指标

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S21-N01 运营队列（运营） | open cases、SLA、risk | 聚合待办、分配责任人 | `OpsQueueProjection` | 队列不绕过领域权限；每项待办有来源 |
| S21-N02 交付监控（运营） | service tasks、quality checks | 监控按时率、返工、投诉 | `DeliveryMetric` | 指标来自事实事件；不以 UI 点击代替交付 |
| S21-N03 商业监控（管理/财务） | orders、payments、renewals | 监控转化、续购、退款 | `BusinessMetric` | 只统计已确认交易；不把意向算收入 |
| S21-N04 安全与合规监控（合规） | consents、access、incidents | 检查越权、超期、未处理风险 | `ComplianceAlert` | 高风险告警必须有处置闭环 |
| S21-N05 经营复盘（管理） | metrics、outcomes、limitations | 形成决策、实验或闸门 | `OperatingDecision` | 指标不能推出因果疗效；决策版本化、可追溯 |

### S22 AI Runtime、知识、上下文、评估与学习

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S22-N01 知识发布（内容/AI） | source、license、version | 审核并发布知识 | `KnowledgeVersion(PUBLISHED)` | 来源、适用范围、失效日期和许可必填 |
| S22-N02 上下文组装（平台） | authorized query、facts、permissions | 组装最小上下文快照 | `ContextSnapshot` | 目的限定、字段最小化、敏感字段脱敏 |
| S22-N03 模型调用（Gateway） | context、model policy | 路由模型、记录 attempt | `ModelDraft`、`ModelAttempt` | 领域不得直连供应商；供应商需合规准入 |
| S22-N04 人工确认（专家/运营） | draft、risk、review policy | 通过、驳回或修改 | `HumanReviewDecision` | AI 不写 canonical fact；高风险必须人工 |
| S22-N05 评估学习（评估员） | outcomes、limitations、eval set | 质量、偏差、回归评估 | `EvaluationRecord`、`LearningAction` | 合成数据证明工程正确性，不宣称真实有效性 |

### S23 机构/城市伙伴合作与供给准入

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S23-N01 合作申请（机构） | organization、scope、contact | 提交合作申请 | `PartnerApplication` | 付款方、服务接受者、数据访问者分离 |
| S23-N02 资质与协议（运营/法务） | qualification、DPA、SLA | 审查并签署协议 | `PartnerAdmission` | 数据处理、保密、删除、转委托边界明确 |
| S23-N03 供给上架（伙伴/运营） | offerings、capacity、price | 发布伙伴供给版本 | `PartnerOffering` | 能力、价格、服务半径、有效期可追溯 |
| S23-N04 伙伴交付（伙伴） | assigned cases、SLA | 承接、交付、反馈 | `PartnerDeliveryRecord` | 不得跨授权访问家庭；交付进入 S13 验收 |
| S23-N05 续期/退出（运营） | quality、volume、complaints | 续期、整改、暂停或退出 | `PartnerDecision` | 商业关系不能绕过质量、权限和安全规则 |

### S24 合作、组织、人才与股权治理

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| S24-N01 组织职责（管理层） | strategy、domain registry | 确认产品、交付、数据 AI、运营边界 | `OrgCapabilityMap` | 业务责任和技术责任均有 owner；不得职责真空 |
| S24-N02 合作协议（法务） | partner terms、IP、data boundary | 审核合同、知识产权和数据边界 | `CooperationAgreement` | 代码、品牌、数据、模型和客户关系分别归属 |
| S24-N03 人才准入与授权（人力/安全） | role、qualification、training | 入职、培训、最小权限、离职回收 | `StaffAccessGrant` | 高风险角色需资质检查和定期复核 |
| S24-N04 股权与激励（董事会） | cap table、vesting、performance | 授予、归属、回购、退出 | `EquityGrant`、`VestingEvent` | 归属约定版本化；不得以未验收贡献直接结算 |
| S24-N05 治理决策（管理层） | risk、metrics、agreements | 形成决策、例外和审计记录 | `GovernanceDecision` | 重大例外需授权、期限、补偿措施和复盘 |

## 6. 平台运营场景全集

S01～S24 描述业务价值闭环；下面 O01～O14 描述平台运营为这些闭环提供的日常可执行后台场景。运营动作同样必须有输入、活动、输出、规则、权限、审计和可回滚路径，不能用“后台手工处理”代替业务能力。

| 编号 | 平台运营闭环 | 服务的业务场景 | 主要责任角色 | 当前判断 |
|---|---|---|---|---|
| O01 | 账户、租户、角色与权限运营 | S02、S20 | 身份管理员、安全 | PARTIAL |
| O02 | 内容、测评、计划与任务版本运营 | S03～S07、S22 | 内容/产品运营 | DESIGN_ONLY |
| O03 | 直播、活动、渠道与触达运营 | S01、S12、S18 | 市场/活动运营 | DESIGN_ONLY |
| O04 | 家庭线索、入营与留存运营 | S01、S05～S08、S16 | 家庭运营/管家 | DESIGN_ONLY |
| O05 | 工单、队列、SLA 与人工升级运营 | S09、S10、S14 | 客服/值班运营 | PARTIAL |
| O06 | 专家、教师、机构供给运营 | S11、S23 | 供给/伙伴运营 | DESIGN_ONLY |
| O07 | 预约、履约、改派与质量抽检运营 | S12～S14 | 交付运营/质量负责人 | DESIGN_ONLY |
| O08 | 商品、会员、权益与促销运营 | S15、S16、S18 | 商品/会员运营 | PARTIAL |
| O09 | 支付、退款、结算与对账运营 | S16、S17、S13 | 财务/支付运营 | GATE_BOUNDARY |
| O10 | 社区审核、风控、申诉与处置运营 | S19 | 社区审核/安全 | DESIGN_ONLY |
| O11 | 数据权利、留存、安全与合规运营 | S02、S09、S19、S20 | 合规/安全 | PARTIAL |
| O12 | AI 知识、模型、提示词与评估运营 | S05、S09、S22 | AI 产品/评估 | DESIGN_ONLY |
| O13 | 指标、实验、分群与经营复盘运营 | S08、S14、S16、S21 | 数据/经营分析 | DESIGN_ONLY |
| O14 | 发布、环境一致性、审计与事故运营 | 全部 S/O | 工程、SRE、审计 | PARTIAL |

### O01 账户、租户、角色与权限运营

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| O01-N01 租户开通 | 合同、组织、环境 | 创建租户和隔离边界 | `Tenant(ACTIVE)` | 租户数据、密钥、配额隔离；不得跨租户查询 |
| O01-N02 角色授权 | 角色申请、职责、范围 | 审批并授予最小权限 | `RoleGrant` | 高风险权限双人审批、定期复核 |
| O01-N03 账号支持 | 工单、验证材料 | 解锁、改绑、重置或冻结 | `AccountAction` | 支持人员不得绕过身份核验；操作全量审计 |
| O01-N04 离职/撤权 | 离职事件、权限清单 | 撤销会话、回收密钥和授权 | `AccessRevocation` | 撤权必须幂等并在 SLA 内完成 |

### O02 内容、测评、计划与任务版本运营

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| O02-N01 内容编审 | 草稿、来源、版权 | 编辑、审核、标注适用范围 | `ContentVersion(REVIEW)` | 来源、版权、失效日、敏感级别完整 |
| O02-N02 测评版本 | 题目、量表、目的 | 配置、试运行、冻结版本 | `AssessmentVersion` | 已被会话引用的版本不可原地修改 |
| O02-N03 计划/任务模板 | 阶段目标、行动、风险 | 编排模板和验收标准 | `JourneyTemplate`、`TaskTemplate` | 模板不得内含家庭事实或默认疗效承诺 |
| O02-N04 发布/回滚 | 审批、灰度范围、回滚点 | 发布、监控、下线或回滚 | `ReleaseDecision` | 回滚保留已产生事实；不可删除历史版本 |

### O03 直播、活动、渠道与触达运营

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| O03-N01 渠道配置 | 渠道、预算、素材 | 创建渠道和归因规则 | `ChannelConfig` | 归因规则版本化；不采集超出目的的行为 |
| O03-N02 活动排期 | 主讲人、场地、容量 | 建立场次、报名和候补 | `ActivitySlot` | 容量、取消、候补和通知规则可见 |
| O03-N03 触达编排 | 目标人群、内容、频率 | 发送站内/短信/邮件触达 | `TouchpointAction` | 必须有目的、同意、退订和频控 |
| O03-N04 活动复盘 | 到场、转化、反馈 | 汇总活动效果和问题 | `ActivityReview` | 浏览/点击不等于购买或成长事实 |

### O04 家庭线索、入营与留存运营

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| O04-N01 线索接收 | EntryEvent、来源、目的 | 去重、分层、分配责任人 | `FamilyLead` | 线索不是家庭事实；目的和来源必须保留 |
| O04-N02 入营跟进 | 未完成节点、提醒偏好 | 发送提醒、安排人工跟进 | `OnboardingFollowUp` | 尊重免打扰；不可替家庭确认决定 |
| O04-N03 流失识别 | 活动事实、服务状态 | 识别中断并提供恢复路径 | `RetentionSignal` | 不以单一行为给家庭贴标签；AI 仅建议 |
| O04-N04 重新激活 | 家庭请求、有效同意 | 恢复计划/服务入口 | `ReactivationAction` | 原事实不覆盖；恢复需重新检查权限和同意 |

### O05 工单、队列、SLA 与人工升级运营

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| O05-N01 工单入队 | SupportTicket、risk、SLA | 分类、去重、建立队列 | `OpsQueueItem` | 原始请求不可丢失；敏感工单最小可见 |
| O05-N02 责任分派 | queue、skill、capacity | 指派管家/专家/安全值班 | `Assignment` | 分派冲突、拒绝和替补必须留痕 |
| O05-N03 超时升级 | SLA clock、风险级别 | 自动提醒、升级值班主管 | `EscalationEvent` | 高风险不得静默关闭；升级有明确接收人 |
| O05-N04 关闭回访 | resolution、customer feedback | 验证解决、关闭或转 S14 | `TicketClosure` | 无解决证据不能标记已解决 |

### O06 专家、教师、机构供给运营

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| O06-N01 供给申请 | ProviderProfile、资质、服务范围 | 初审并建立候选档案 | `ProviderApplication` | 资质有效期、身份和利益冲突可核验 |
| O06-N02 准入审核 | qualification、协议、培训 | 复核、签约、授予供给权限 | `ProviderAdmission` | 未准入不得接触家庭或发布时段 |
| O06-N03 容量排班 | availability、capacity、SLA | 发布、锁定、调整服务容量 | `CapacitySchedule` | 时区、冲突、临时关闭可追踪 |
| O06-N04 续期/暂停 | quality、complaints、expiry | 续期、整改、暂停或退出 | `ProviderDecision` | 商业关系不能绕过质量与安全规则 |

### O07 预约、履约、改派与质量抽检运营

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| O07-N01 预约监控 | bookings、slots、payment | 监控确认、待支付、冲突 | `BookingOpsView` | 读模型不创造预约事实；冲突必须阻断 |
| O07-N02 缺席/改派 | attendance、reason、capacity | 改期、改派、退款或补交付 | `RecoveryAction` | 按版本化规则执行；家庭需获知影响 |
| O07-N03 质量抽检 | delivery、feedback、risk sample | 抽样复核交付物和记录 | `QualitySample` | 抽检范围和结论可解释、可申诉 |
| O07-N04 履约结案 | verified quality、feedback | 关闭服务并回写指标 | `FulfillmentClosure` | 关闭必须有交付或未完成原因，不自动生成 Outcome |

### O08 商品、会员、权益与促销运营

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| O08-N01 商品配置 | product、price、benefit | 创建、审核、发布商品版本 | `ProductVersion` | 价格、权益、适用人群和退订边界明确 |
| O08-N02 权益配置 | membership plan、limits、SLA | 配置权益、次数、有效期 | `BenefitVersion` | 权益版本冻结；不能追溯修改已生效订单 |
| O08-N03 促销活动 | campaign、eligibility、budget | 配置优惠或单层激励 | `CampaignVersion` | 不得多层返佣；预算、期限、撤销规则明确 |
| O08-N04 退款/失效 | refund event、reason | 失效权益、通知家庭、生成对账项 | `EntitlementRevocation` | 退款与权益反向关联，不抹除订单事实 |

### O09 支付、退款、结算与对账运营

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| O09-N01 支付回调 | gateway event、signature | 验签、幂等处理、更新订单 | `PaymentRecord` | 未验签事件拒绝；重复回调不重复入账 |
| O09-N02 退款审批 | refund request、policy、evidence | 审批、执行退款、通知 | `RefundDecision` | 权限分离；退款原因和金额可审计 |
| O09-N03 日终对账 | gateway、orders、ledger | 比对差异、挂起异常 | `ReconciliationCase` | 差异不可静默抹平；保留原始对账文件 |
| O09-N04 结算输出 | verified contribution、settlement policy | 生成服务方应付和平台分录 | `SettlementStatement` | VERIFIED 才可结算；贡献不等于支付事实 |

### O10 社区审核、风控、申诉与处置运营

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| O10-N01 审核入队 | post、report、risk policy | 机审、人工队列、去重 | `ModerationQueueItem` | AI 只给建议；高风险内容优先人工 |
| O10-N02 风险处置 | queue item、evidence | 通过、拒绝、限流、封禁 | `ModerationDecision` | 处置理由、时限、证据完整 |
| O10-N03 申诉复核 | appeal、original decision | 独立复核、维持或撤销 | `AppealDecision` | 申诉人与初审职责分离 |
| O10-N04 规则复盘 | incidents、false positives | 调整规则、培训和抽检集 | `ModerationPolicyChange` | 规则变更版本化，不回写历史裁决 |

### O11 数据权利、留存、安全与合规运营

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| O11-N01 权利工单 | DataSubjectRequest、identity | 验证、分类、设定时限 | `RightsCase` | 代理关系和未成年人监护依据必查 |
| O11-N02 访问复核 | access logs、purpose、role | 识别越权、撤权、补救 | `AccessReview` | 最小权限；异常访问先隔离后调查 |
| O11-N03 留存/删除执行 | retention policy、legal hold | 导出、删除、匿名化、验证 | `RetentionJob` | 删除幂等；法定留存需明示期限与原因 |
| O11-N04 安全事件响应 | alert、severity、evidence | 分级、隔离、通知、复盘 | `SecurityIncident` | 证据保全；不可静默关闭或修改时间线 |

### O12 AI 知识、模型、提示词与评估运营

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| O12-N01 知识/提示词登记 | source、license、prompt、owner | 版本化、审批、发布 | `KnowledgeVersion`、`PromptVersion` | 来源、许可、适用范围和失效日期完整 |
| O12-N02 模型路由策略 | risk tier、cost、model policy | 配置 Gateway 路由、降级、熔断 | `ModelRoutingPolicy` | 领域不直连供应商；高风险不自动降级到无审模型 |
| O12-N03 评估与红队 | eval set、limitations、traces | 质量、偏差、安全、回归评估 | `EvaluationRun` | 合成数据不宣称真实有效；失败阻断发布 |
| O12-N04 发布/回滚 | approved versions、canary | 灰度、监控、回滚 | `AIRuntimeRelease` | 每次回答带 provenance；回滚不改历史输出 |

### O13 指标、实验、分群与经营复盘运营

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| O13-N01 指标定义 | event schema、business question | 定义口径、维度、窗口 | `MetricDefinition` | 指标只引用事实事件；口径版本化 |
| O13-N02 实验配置 | hypothesis、cohort、guardrail | 配置实验、分流、停止条件 | `Experiment` | 不以儿童敏感数据做无目的实验；先过合规 |
| O13-N03 分群分析 | authorized facts、consent | 生成聚合分析和限制说明 | `CohortInsight` | 最小样本、去标识化；不产家庭排名 |
| O13-N04 经营决策 | insight、quality、cost | 形成继续、调整、停止或闸门决策 | `OperatingDecision` | 相关性不等于疗效因果；决策可追溯 |

### O14 发布、环境一致性、审计与事故运营

| 节点 | 输入 | 活动 | 输出 | 业务规则 |
|---|---|---|---|---|
| O14-N01 变更申请 | code、schema、business rule | 评审影响面、回滚方案、审批 | `ChangeRequest` | 业务状态机变更需业务 owner 和 ADR |
| O14-N02 环境验收 | build、config、synthetic data | 在开发/测试/生产同一功能路径验收 | `EnvironmentParityReport` | 只替换数据与外部副作用，不能删功能、权限或错误路径 |
| O14-N03 审计复核 | audit log、release、access | 检查完整性、不可抵赖、异常 | `AuditFinding` | 审计日志不可由业务人员覆盖；修复需留痕 |
| O14-N04 事故与复盘 | alert、timeline、impact | 处置、恢复、根因分析、改进 | `IncidentRecord`、`Postmortem` | 先保护家庭和数据，再恢复服务；改进项有 owner/期限 |

## 7. 跨场景状态与事实边界

```text
Fact           家庭、成员、同意、回答、预约、交付等权威事实
Perspective    AI 或人对事实的解释、假设、观察
Recommendation AI/规则提出的建议
Action         经过授权、审计、幂等校验的状态写入动作
Outcome        行动或服务后由主体/证据确认的结果
```

禁止把以下对象互相替代：

- `Hypothesis = Fact`
- `Recommendation = Decision`
- `Check-in = Outcome`
- `Completed actions = Growth score`
- `Service contribution = Payment settlement`
- `Child behavior = Commercial targeting permission`

所有环境（开发、测试、生产）功能和状态机必须一致；测试环境只替换数据源、密钥和外部副作用为模拟实现，不得删除节点、权限、审核、支付、异常、审计或安全流程。

## 8. 依赖关系、优先级与缺口

```text
S01 → S02 → S03 → S04 → S05 → S06 → S07 → S08
                         └→ S09（AI 横切）
S06/S07 → S10 → S11 → S12 → S13 → S14
S15 → S16 → S17；S01/S02 → S18 → S19
S20 横切全部家庭数据；S21 横切交付、商业、质量和合规
S22 横切所有 AI 调用；S23 为供给网络入口；S24 为组织与合作治理
O01～O14 是所有 S 场景的运营执行面，不能作为“人工后台例外”省略
```

建议施工顺序：

1. **P0 真实交付基线**：S02～S07，补齐家庭成员、同意、测评、假设确认、90 天计划、21 天行动的异常路径；
2. **P1 服务闭环**：S10～S14，落地预约、履约、FGCN、验收、投诉和恢复；
3. **P2 商业闭环**：S15～S18，接通商品、会员、支付、资产、积分和单层邀请激励；
4. **P3 信任边界**：S19、S20、S22，完成社区审核、数据权利、安全事件、模型网关和人工升级；
5. **P4 运营与扩展**：S01、S21、S23、S24，完善内容/活动入口、运营台、机构伙伴与组织治理。

当前最大的实现缺口不是 UI 数量，而是：S06/S07 的行动事实写入与推进、S10～S14 的真实服务交付、S16/S17 的支付/对账、S19/S20 的安全与数据权利、S21～S24 的运营和治理闭环。

## 9. 从工作稿升为基线的验收条件

- 每个 S 场景由业务负责人确认触发、结束、参与者和拒绝路径；
- 每个节点补齐字段级输入输出、敏感级别、权限、Consent、Audit、Idempotency 和 Outbox；
- 每个 UI 至少消费一个节点输出，且 UI 不定义业务事实；
- S02～S07、S10～S14、S16～S17 各有测试环境可重复的纵向验收；
- 测试环境与生产环境功能、权限、状态机、错误码和审计行为一致，仅数据和外部副作用模拟；
- 所有 `DESIGN_ONLY` / `GATE_BOUNDARY` 在能力注册、迁移登记和发布闸门中保持诚实状态。
