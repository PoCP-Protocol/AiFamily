---
id: ARCH-REVIEW-003
title: Family 对标抖音体验与游戏化成长的五层架构修正版评审
type: architecture-review
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# Family 对标抖音体验与游戏化成长的五层架构修正版评审

## 1. 评审边界

两张核心商业蓝图是业务目标；34 个 UI 是体验基线；业务、流程、数据、应用和 AI
文档是当前设计资产；本文件是一次“反向对标评审”，不是把抖音的内部代码或专利实现
复制到 Family。

本次只对标可观察的产品机制：内容发现、兴趣反馈、短反馈循环、连续体验、传播和推荐。
不假设抖音内部的私有服务拆分、模型实现或商业规则。

评审结论先行：Family 应该借鉴抖音的“顺滑和反馈速度”，但价值顺序必须不同：

```text
被看见/被理解
  → 一个小胜利
  → 愿意再次回来
  → 连续成长和关系改善
  → 家庭主动选择服务
  → 经济价值和平台复购
```

经济价值不能抢在情绪价值和成长证据之前；家庭尤其是未成年人不能被当成广告和
算法优化燃料。

## 2. 对标转换：借鉴机制，不复制副作用

| 可观察机制 | Family 借鉴方式 | 必须拒绝的副作用 | 架构承载 |
|---|---|---|---|
| 兴趣推荐 | 按家庭已授权的成长意图、节奏、语言和反馈推荐下一条内容/行动 | 不用未成年人画像做商业营销；不跨租户召回 | Experience Context + Principal Router |
| 短内容/短反馈 | 每次只呈现一个可理解的观点或一个小行动 | 不把连续滑动、停留时长当作唯一价值 | Feed Projection + Growth Action |
| 即时反馈 | 完成、跳过、改写、暂停都即时给出下一步 | 不用羞辱、倒计时、强制连续打卡制造焦虑 | Event Stream + Rhythm Policy |
| 连续体验 | 章节、旅程、家庭故事和可选徽章形成成长感 | 不做家庭总分、家庭排名、孩子之间比较 | Journey Projection + Reward Ledger |
| 内容传播 | 家长确认后分享脱敏案例、邀请和家庭故事 | 不默认公开家庭或孩子内容；不向孩子发商业邀请 | Visibility/Consent + Referral |
| 直播/服务承接 | 在信任和需求出现后提供真人、课程和服务入口 | 不把情绪脆弱时刻直接变成强营销弹窗 | Commercial Gate + Human Service |
| 推荐系统 | 解释“为什么推荐”，允许不感兴趣、稍后、暂停和清空 | 不黑箱操纵、不无限刺激、不跨目的训练 | Recommendation Provenance |

## 3. 修正后的北极星与指标

### 3.1 北极星

不是“用户使用时长”或“转化率最大化”，而是：

> 家庭在被尊重的前提下，持续完成适合当前节奏的小行动，感受到关系改善，
> 并在有真实需要时主动选择服务。

### 3.2 四层指标

1. **情绪价值**：首次被理解时间、回应采纳/改写率、主动返回率、暂停后安全返回率、
   家长对“被看见”的反馈。
2. **成长价值**：行动完成/跳过的可解释性、家庭确认的计划、过程观察、服务验收和
   结果证据；不把这些合成为家庭总分。
3. **经济价值**：体验到服务意向、会员主动确认、复购、推荐和贡献结算；不以孩子
   的行为数据直接触发商业动作。
4. **平台健康**：投诉率、误召回率、人工升级及时性、租户隔离、删除完成率、模型
   成本和区域可用性。

## 4. 业务架构修正

### 4.1 业务域

```text
X0 Experience & Trust（跨域体验与信任）
   情绪价值、内容发现、节奏、可见性、推荐解释、暂停和反馈

B1 Family Growth OS
   测评、证据解释、意图、21 天验证、90 天交付、结果沉淀

B2 FGCN Service Network
   ServiceCase、任务、授权、匹配、交付、质量、贡献

B3 Growth & Commercial Flywheel
   体验入口、挑战营、产品、订单、会员、权益、邀请、续购

B4 Family Trust & Community
   家庭成员、同意、社区、申诉、未成年人保护、数据权利

B5 Platform Evolution
   内容、组件、知识、AI、实验、运营、质量、版本和组织治理
```

X0 是跨域能力，不拥有家庭事实、服务事实或商业事实。法咪莉校长位于 X0 与 B5
之间，负责理解、编排和解释，不取代业务域。

### 4.2 情绪价值到经济价值的业务闸门

```text
E0 被看见       → 首次内容/对话/测评反馈
E1 小胜利       → 一个可完成的小行动或关系表达
E2 连续成长     → 21/90 天节奏、观察和家庭确认
E3 服务需要     → 家庭主动表达需要或授权匹配
E4 经济选择     → 会员、服务、复购、邀请
```

E0-E2 未形成有效反馈前，商业域只能提供被动查询，不得主动推销。E3 之后仍须家长
或授权主体确认，AI 不支付、不升级权益、不自动续费。

## 5. 流程架构修正

### 5.1 分级流程

```text
L0 价值流：情绪价值 / 家庭成长 / 资源质量 / 商业增长 / 平台信任
  L1 端到端：发现与陪伴 / 测评与入营 / 21 天验证 / 90 天交付 / FGCN 协作 /
               服务与复购 / 传播与学习 / 运营与治理
    L2 场景：S/O 场景总账中的家庭、服务、商业和运营场景
      L3 子流程：推荐、反馈、章节、行动、验收、人工升级、发布
        L4 节点：输入 → 活动 → 输出 → 规则 → 异常分支
          L5 系统：API / Command / Event / Job / Human Task / Projection
```

### 5.2 新增体验闭环 P0

| 节点 | 输入 | 活动 | 输出 | 规则 |
|---|---|---|---|---|
| P0-N01 触达 | 来源、租户、语言、家庭节奏、目的 | 解析入口和最小上下文 | FeedRequest | 不以停留时长单独决定推荐 |
| P0-N02 内容候选 | 已发布内容、成长意图、历史反馈 | 过滤授权、年龄、语言、区域和频控 | CandidateSet | 过期、越权、未审核内容不可见 |
| P0-N03 情绪承接 | 候选内容、家庭当前状态 | 先共情/解释，再提供一个选择 | EmotionalResponse | 不利用脆弱状态直接营销 |
| P0-N04 小行动 | 家庭选择、当前阶段、可用时间 | 提出一个可跳过、可改写的小行动 | ActionProposal | 不自动写入 GrowthAction |
| P0-N05 反馈 | 完成、跳过、改写、暂停、投诉 | 记录原因和下一步偏好 | FeedbackSignal | 负反馈必须降低频率并可清空 |
| P0-N06 成长承接 | 连续证据、家庭确认、服务需要 | 进入 21/90 天或真人服务 | GrowthIntent/ServiceIntent | 商业入口由家庭主动触发 |

### 5.3 与原蓝图流程的关系

P0 不是第八个业务域，而是横切在“免费测评 → AI 解读 → 方案 → 21 天 → 90 天 →
结果 → 年度服务”之前和之间的体验编排。FGCN 仍独立完成案件、任务、交付、质量和
贡献；商业飞轮仍独立完成产品、订单、会员、权益和复购。

## 6. 数据架构修正

### 6.1 新增逻辑数据对象

| 数据对象 | 建议表/投影 | 事实或派生 | 关键边界 |
|---|---|---|---|
| ExperienceEvent | `experience_events` | 事实事件 | 入口、展示、选择、暂停、投诉；不等于兴趣画像 |
| ContentCandidate | `content_candidates` | 派生候选 | 带原因、版本、适用区域/语言和失效时间 |
| RecommendationDecision | `recommendation_decisions` | 技术审计 | 记录候选、策略、反馈和拒绝原因 |
| EmotionalResponse | `emotional_responses` | AI Draft/投影 | 只能记录被展示和反馈，不写家庭状态 |
| GrowthProgress | `growth_progress_projection` | 只读投影 | 章节、阶段、完成/跳过，不是总分 |
| RhythmPreference | `family_rhythm_preferences` | 家庭确认主数据 | 时段、频率、暂停和通知偏好 |
| RewardLedger | `growth_reward_ledger` | 业务账本 | 只记录非比较性的章节/权益奖励，禁止家庭排名 |
| ExperimentAssignment | `experience_experiment_assignments` | 运营实验事实 | 租户/区域/家庭范围、版本和退出方式 |

### 6.2 数据关系

```text
ExperienceEvent
  → CandidateSet
  → RecommendationDecision
  → EmotionalResponse / ActionProposal
  → FeedbackSignal
  → GrowthProgressProjection
  → GrowthIntent / ServiceIntent
  → Commercial Decision（家长确认）
```

推荐特征和运营实验是派生数据，不能反写 Family、Outcome、Membership 或孩子画像。
在线特征、离线评估、Embedding、缓存和日志必须继承 `tenant_id`、`region_id`、
`family_id`、`subject_ids`、`purpose`、`consent_version`、`data_class`、四类 locale、
`deletion_ref` 和 `provenance_ref`。

### 6.3 特征与指标红线

- 可用于成长体验的特征：明确授权的成长意图、内容反馈、家庭节奏、语言和服务偏好。
- 不可用于商业推荐的特征：未成年人情绪脆弱、家庭冲突、敏感健康信息和隐性行为标签。
- 不把观看时长、连续打卡、消费金额合成家庭价值分。
- 不做家庭之间的总分、排行榜、隐性排序或跨租户相似家庭召回。

## 7. 应用架构修正

### 7.1 新增应用模块

```text
ExperienceApplication
  ├─ ContentDiscoveryService       # 内容/章节/服务候选读取
  ├─ RecommendationPolicyService   # 授权、频控、解释和退出
  ├─ EmotionalJourneyService       # 被看见、小胜利、关系承接
  ├─ GrowthRhythmService           # 21/90 天节奏和暂停
  ├─ FeedbackApplication            # 采纳、改写、跳过、投诉
  ├─ CommercialGateService         # 情绪/成长闸门后的主动商业入口
  └─ ExperienceProjectionWorker     # 时间线、进度、运营投影
```

这些模块读取业务域投影，不直接读 ORM；AI 只返回候选、解释、ActionProposal 或
HumanTask，最终由 Family/Journey/Service/Commerce Named Action 写入事实。

### 7.2 34 UI 的体验角色

- UI-01、UI-02、UI-03：首次被看见、测评解释和家庭确认，不用销售卡片打断。
- UI-04、UI-05、UI-09、UI-10、UI-11、UI-12：章节化成长、一个小行动、过程反馈和故事沉淀。
- UI-06、UI-19～UI-24、UI-31、UI-34：真人服务、服务记录、交付复盘和质量信任。
- UI-07、UI-13～UI-18、UI-30、UI-32：在主动表达服务需要后展示产品、会员和资产。
- UI-25～UI-28：家长社区和案例传播，默认私密、确认可见、可撤回。
- UI-29、UI-33：家庭成果、档案、权利和删除，不把结果做成排名。

UI 基线不改编号和核心语义；增加的是统一体验投影、反馈、推荐解释、暂停和商业闸门。

## 8. AI 技术架构修正

### 8.1 Principal 的新增体验职责

Principal 统一承担四种体验判断：

1. 现在家庭需要被理解，还是需要一个具体行动；
2. 内容、行动或真人服务哪个更适合当前目的；
3. 如何用游戏感表达进度，但不制造比较和成瘾；
4. 什么时候必须停止推荐、转人工或等待家庭主动选择。

建议新增一个受治理的 `experience_curator` profile。它不是新的模型，也不是自由营销
Agent，必须经过 Registry、Knowledge、Safety、Model Gateway、Human Gate 和 Eval。

### 8.2 AI 链路

```text
ExperienceEvent
  → Consent/Tenant/Locale Resolver
  → Context Broker（最小家庭上下文）
  → Principal/experience_curator
  → Reviewed Knowledge + Content Catalog
  → Recommendation Policy + Frequency Guard
  → Model Gateway（唯一模型边界）
  → Schema/Safety/Provenance
  → EmotionalResponse / ActionProposal / HumanTask
  → User Feedback
  → Growth/Commercial Named Action（仅确认后）
```

任何“让用户多停留、让孩子多消费、让家庭多购买”的隐式目标都不得进入模型提示、
奖励函数或评估集。体验优化目标必须拆为情绪安全、成长采纳、服务质量和平台健康。

### 8.3 游戏化安全设计

- 使用章节、任务、选择、反馈、收藏、家庭故事和可选徽章表达进度。
- 允许跳过、暂停、降低频率、清空推荐和撤回分享。
- 奖励完成过程或关系表达，不奖励家庭排名、孩子比较或消费金额。
- 不能用随机奖赏、倒计时、连续签到惩罚、未成年人消费激励制造压力。
- 所有 AI 文案带来源、目的、风险、版本和“为什么给我看”的解释。

## 9. 正反向架构评审

| 设计 | 正向收益 | 反向风险 | 必须具备的证据 |
|---|---|---|---|
| 类抖音内容发现 | 降低理解成本，提高首次价值速度 | 变成无限信息流和注意力收割 | 可暂停、频控、退出、反馈降频测试 |
| 游戏化成长 | 让 21/90 天有连续感 | 打卡焦虑、家庭比较、伪成长 | 非比较进度、跳过/暂停、关系证据 |
| 情绪先于经济 | 先建立信任，再产生服务需要 | 情绪被包装成销售漏斗 | E0-E2 商业禁推测试和投诉监控 |
| Principal 统一体验 | 语言、方法、边界一致 | 超级 Agent 绑架所有域 | 单 profile、Registry、Named Action |
| 推荐数据飞轮 | 内容和服务越来越适配 | 目的漂移、跨租户泄漏 | purpose/consent/deletion/provenance |
| 全球多租户 | 能服务不同地区和机构 | 语言、法规和数据主权冲突 | region cell、locale eval、租户隔离 |

## 10. 全球规模、环境等价和治理

### 10.1 全球规模

```text
Global Control Plane
  → tenant catalog / locale policy / content release / capability registry
Regional Cell
  → family api / experience worker / ai runtime / local human operations
Tenant Shard
  → family scope / projection / feature namespace / deletion index
```

内容、上下文、Embedding、缓存、评估样本和推荐候选默认不得跨租户；跨区域只传递
最小化、脱敏、授权的控制事件。千亿级设计先保证可分片、可迁移、可删除，再扩容基础设施。

### 10.2 三环境功能等价

开发、测试、生产必须拥有相同的内容发现、推荐解释、游戏化状态机、商业闸门、人工闸门、
审计、Outbox、重试、删除和错误码。测试环境只替换：

- 合成家庭/主体/事件/反馈数据；
- FakeProvider、sandbox 支付和通知适配器；
- 合成内容和评估集。

不能用删除推荐、删除人工闸门、删除商业状态机的方式“简化测试环境”。

## 11. 进入开发前的冻结门槛

1. 接受本评审的 E0-E4 情绪到经济价值闸门；
2. 将 `experience_curator` 登记到 AI Use Case Registry，并补充工具、知识范围、输出 schema、
   风险和人工闸门；
3. 冻结 `ExperienceEvent`、`RecommendationDecision`、`FeedbackSignal`、`GrowthProgress`
   和 `CommercialGate` 数据契约；
4. 把 P0 体验流程挂到现有 S/O 场景和 34 UI 投影，不新增平行业务事实；
5. 完成多租户、多语言、区域和三环境 parity contract tests；
6. 先做 UI-03 → UI-05 → UI-09 的家庭纵向切片，再扩展服务、商业、社区和全球 Cell；
7. 任何未通过安全、删除、人工闸门和可重放测试的能力保持 `PLANNED`，不得对外称已上线。

## 12. 与现有设计文件的关系

- 核心商业蓝图与全球规模：`docs/00_system/CORE_BLUEPRINT_GLOBAL_SCALE_ALIGNMENT.md`
- 五层架构对齐：`docs/00_system/ARCHITECTURE_ALIGNMENT_V2.md`
- AI 深度技术架构：`docs/05_ai/AI_TECHNICAL_ARCHITECTURE_DEEP_DESIGN.md`
- 校长应用架构：`docs/06_platform/PRINCIPAL_AI_APPLICATION_ARCHITECTURE.md`
- 校长数据架构：`docs/07_data/PRINCIPAL_AI_DATA_ARCHITECTURE.md`
- 服务产品设计 AI：`docs/05_ai/SERVICE_PRODUCT_DESIGN_AI_PLATFORM.md`

本文件是修正版评审稿，当前 `canonical: false`；进入开发前必须经过架构决策登记、
文档地图更新和对应 contract tests。

## 13. 六引擎模型：拼多多 + 字节 + 海底捞 + 贝壳 + 教育 + 游戏

这六个词不是六个孤立产品，也不是把六家公司的页面拼在一起，而是平台必须同时具备
的六种能力。每种能力都要有业务目标、流程闭环、数据对象、应用模块和 AI 边界。

| 引擎 | Family 要借鉴的能力 | 业务闭环 | 核心数据/应用 | AI 边界 |
|---|---|---|---|---|
| 拼多多引擎 | 低门槛、拼团、社交传播、低成本获客 | 免费测评 → 体验挑战 → 家长邀请/案例传播 → 新家庭进入 | Campaign、GroupChallenge、Invite、Referral、GrowthMetrics | 只能推荐公开/授权内容，不用孩子画像驱动营销，不做多级分销 |
| 字节引擎 | 内容分发、兴趣反馈、推荐、实验和快速迭代 | 触达 → 内容候选 → 展示 → 反馈 → 下一次推荐 | Content、Candidate、ExperienceEvent、Experiment、RecommendationDecision | 以成长目的和授权反馈为特征；不以停留时长、脆弱情绪或消费金额为唯一目标 |
| 海底捞引擎 | 被重视、主动响应、服务补救、前线授权 | 需求 → 接待 → 响应 → 交付 → 质量 → 补救/复购 | ServiceCase、Queue、SLA、Delivery、Quality、Recovery | 识别风险和准备建议；不自动承诺、赔付、分派或关闭投诉 |
| 贝壳引擎 | ACN 协作、任务拆解、跨角色贡献和带证据分配 | 案件 → 拆任务 → 授权匹配 → 交付 → 验收 → 贡献 | ServiceCase、ServiceTask、Assignment、Contribution、Allocation | 推荐资源和解释匹配；不直接分佣、不按家庭结果分配贡献 |
| 教育引擎 | 方法论、学习目标、21/90/年度节奏和长期陪伴 | 评估 → 假设 → 方案 → 行动 → 复盘 → 结果 | Assessment、GrowthIntent、JourneyPlan、Action、Outcome、Knowledge | 证据解释和计划草案；不做诊断、疗效保证或家庭总分 |
| 游戏引擎 | 任务、章节、反馈、难度适配、解锁和故事 | 选择目标 → 小任务 → 即时反馈 → 进度解锁 → 下一章 | GrowthProgress、ActionRecord、RewardLedger、Badge、RhythmPolicy | 生成非比较性的行动和反馈；不做排名、沉迷刺激、随机奖赏或打卡惩罚 |

### 13.1 六引擎在五层架构中的归属

```text
业务架构：六引擎是能力来源，B1-B5 是权威业务域，X0 是体验与信任横切面
流程架构：六引擎各自有闭环，但共享 E0-E4 情绪→成长→经济闸门
数据架构：事件、事实、投影、账本、推荐特征分层；tenant/family/subject 隔离
应用架构：34 UI 继续是家庭渠道；Feed、Journey、Service、Commerce、Ops 是模块
AI 技术架构：Principal 统一 Soul 和边界，按 capability/profile 调用不同引擎能力
```

### 13.2 六引擎的优先级

第一阶段先建设“教育 + 游戏 + 字节”的家庭纵向切片，让家庭感受到被理解、能完成和
愿意回来；第二阶段建设“海底捞 + 贝壳”的服务协作和质量闭环；第三阶段再放大“拼多多”
的传播、挑战营和商业增长。任何阶段都不能跳过情绪价值和成长证据直接放大交易。

## 14. 平台精神：We are 伐木累！We are family！

这句话是平台精神，不只是品牌口号。它定义平台与家庭、服务伙伴和内部团队之间的
关系方式：让人感到被接纳、被尊重、有人一起走，并把这种关系转化为真实的共同成长。

### 14.1 精神内核的五条原则

1. **先接纳，再解决问题**：家庭先被看见和理解，平台才进入测评、方案或服务。
2. **一起成长，不替家庭做主**：平台提供证据、选择和陪伴，家庭保留决定权和退出权。
3. **家庭之间互助，不互相比较**：可以分享经验和资源，但不展示家庭总分、排名或隐私。
4. **伙伴共同交付，不争抢归属**：资源角色按案件和任务协作，贡献以验收证据为依据。
5. **有温度，也有边界**：平台可以使用亲切表达，但不能假装真人亲属、制造情感依赖，
   也不能用“我们是一家人”绕过价格、同意、隐私和退款规则。

### 14.2 五层架构落点

```text
业务：Family Trust & Community 成为所有价值流的关系底座
流程：欢迎/被看见 → 共同行动 → 互助服务 → 共同庆祝 → 新需求回流
数据：只记录明确反馈、可见性和协作关系，不推断“归属感分数”
应用：家庭首页、社区、服务、成果和伙伴工作台共享同一关系语言
AI：Principal Soul 继承尊重、陪伴、证据谦逊和可退出，不模拟家庭成员身份
```

精神内核的本地化版本必须使用 canonical concept ID 和人工审核的 locale 文案；不能
用自动翻译改变“family”在不同文化中的关系边界。所有语言版本都必须保留退出、隐私、
商业和人工服务的明确边界。

### 14.3 从“伐木累”到“family”的平台故事

```text
父母和孩子在成长、家庭关系和生活里感到无奈、疲惫
  → 平台先看见这种处境，不责备、不制造焦虑
  → 法咪莉校长理解家庭需要，提出一个能开始的小行动
  → AI、老师、专家、管家和伙伴资源共同进入
  → 家庭完成一次行动，得到真实反馈和一点小胜利
  → 家庭关系变得温暖，愿意继续一起成长
  → We are 伐木累！逐渐变成 We are family！
```

这里的“大家庭”不是让用户对平台产生依赖，也不是模糊家庭、平台和服务商的责任；
它表示一种可验证的关系体验：家庭被尊重，困难有人接住，资源有人组织，交付有人负责，
结果有人共同确认。平台的温暖必须落到响应、陪伴、质量、补救和可退出，而不是只停留在
情绪文案。
