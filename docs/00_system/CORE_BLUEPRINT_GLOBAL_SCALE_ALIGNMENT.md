---
id: CORE-BLUEPRINT-ALIGN-001
title: Family 核心商业蓝图与全球规模架构对齐设计
type: architecture-alignment
status: draft
version: 0.1
owner: chief-architect
created: 2026-08-30
updated: 2026-08-30
canonical: false
---

# Family 核心商业蓝图与全球规模架构对齐设计

## 1. 两张核心蓝图的稳定含义

两张蓝图表达的是同一个平台，只是抽象层级不同：

### 1.1 家庭客户价值链（详细版）

```text
家庭测评
  → AI 诊断画像/证据解释
  → 个性化方案
  → 21 天行动验证
  → 90 天陪跑交付
  → 成长结果沉淀
  → 年度服务/复购
```

这条链回答“一个家庭为什么持续留下来”。其中 21 天是低门槛验证和激活子流程，
90 天是深度交付，不与年度服务混成同一个订单状态。

### 1.2 平台商业增长飞轮（经营版）

```text
免费测评
  → 低价体验挑战营
  → 90 天成长计划
  → 年度会员服务
  → 案例分享/裂变传播
  → 数据沉淀与算法优化
  ↺ 回到免费测评
```

这条链回答“平台如何低成本获客、转化、留存和学习”。裂变只面对家长/授权主体，
不能使用未成年人画像做自动化商业营销。

### 1.3 FGCN 资源质量飞轮

```text
家庭成长需要
  → ServiceCase
  → 任务拆解与授权
  → 资源匹配
  → 交付留痕
  → 质量验收
  → 贡献凭证/分配依据
  ↺ 形成更好的服务组件和蓝图
```

FGCN 不是教师市场，也不是多级分销；平台只向家庭呈现 Family，资源按任务进入，
交付完成后退出。分配依据来自已验收贡献，不能由 AI 或家庭结果分数直接决定。

## 2. 蓝图差异的裁决

| 表面差异 | 架构裁决 |
|---|---|
| 一张图有 7 步，另一张图有 6 步 | 7 步是客户价值链；6 步是商业增长飞轮；21 天属于客户价值链中的激活子流程 |
| 一张图显式画出 FGCN，另一张图未画 | FGCN 是服务协作底座，横切家庭价值链，不因经营图省略而消失 |
| 一张图写“AI 诊断画像” | 工程实现必须拆为 Evidence → Perspective/Hypothesis → Human/Family Decision，不输出临床诊断或家庭总分 |
| 一张图写“成长结果” | Outcome 必须由家庭/服务人员确认并带证据，不等同于完成率、打卡数或满意度分数 |
| 一张图写“算法优化” | 只优化已授权的上下文、组件、提示词和路由；不得把家庭变成跨目的训练数据 |
| 一张图写“复购/裂变” | 商业动作只能由家长/授权主体确认，未成年人端禁用画像驱动营销 |

## 3. 业务架构对齐

### 3.1 五个核心业务域

```text
B1 Family Growth OS
   assessment / context / hypothesis / plan / 21-day / 90-day / outcome
B2 FGCN Service Network
   case / task / assignment / delivery / quality / contribution / allocation
B3 Growth & Commercial Flywheel
   entry / campaign / product / order / membership / entitlement / referral
B4 Family Trust
   community / consent / visibility / rights / safety / complaint
B5 Platform Evolution
   product intelligence / knowledge / AI runtime / metrics / release / organization
```

法咪莉校长是五个域之上的跨域体验和 AI 编排能力，不拥有任何一个域的事实表。

### 3.2 核心业务对象边界

| 蓝图对象 | 权威域 | AI 可以做什么 | 事实写入者 |
|---|---|---|---|
| 家庭测评 | Assessment | 解释证据、提出假设 | Assessment/家庭确认 |
| AI 画像 | Family Growth / AI Projection | 形成带来源的 Perspective | 不得直接成为画像事实 |
| 个性化方案 | Journey | 生成 Draft、解释取舍 | 家庭确认计划 |
| 21 天行动 | Journey | 提出 ActionProposal、提醒 | 用户确认/记录行动 |
| 90 天陪跑 | Journey + Service | 计划、服务和复盘建议 | 家庭/管家/服务人员 |
| 成长结果 | Outcome | 组织证据和解释 | 家庭/服务人员确认 |
| 年度会员 | Commerce | 解释权益和候选服务 | Commerce Named Action |
| FGCN 贡献 | Service | 推荐资源、提示质量风险 | 管家验收后形成贡献 |

## 4. 流程架构对齐

### 4.1 分级流程

```text
L0 价值流：家庭价值 / 资源质量 / 商业增长 / 信任 / 平台进化
  L1 主流程：触达入营、成长交付、服务协作、商业关系、信任治理、平台运营
    L2 蓝图场景：测评、计划、21天、90天、会员、FGCN、裂变、学习
      L3 子流程：激活、陪跑、验收、续购、反馈、发布
        L4 节点：输入 → 活动 → 输出 → 业务规则
          L5 系统：API / Command / Event / Job / Human Task / Projection
```

### 4.2 核心闭环节点契约

| 节点 | 输入 | 活动 | 输出 | 关键规则 |
|---|---|---|---|---|
| B-N01 免费测评 | 入口来源、主体、目的同意 | 创建测评会话、冻结版本 | EvidenceSet | 未授权不采集；测评版本不可原地修改 |
| B-N02 AI 证据解释 | EvidenceSet、最小 Context | Principal 解释、引用、限制 | Perspective/Hypothesis Draft | 不叫诊断；不含家庭总分/排名 |
| B-N03 方案草案 | 已确认假设、家庭节奏、资源目录 | 生成 21/90 天方案候选 | Plan Draft | 计划必须由家庭确认 |
| B-N04 21 天验证 | 计划阶段、当天上下文 | 提出一个小行动、记录观察 | ActionProposal/ActionRecord | 行动不是 Outcome；可暂停/跳过 |
| B-N05 90 天交付 | JourneyPlan、ServiceBlueprint | 分阶段陪跑、复盘和服务协作 | Delivery/Review/Outcome Candidate | 服务交付与成长结果分开记账 |
| B-N06 FGCN 案件 | GrowthIntent、Blueprint | 建案、拆任务、授权、匹配、交付 | ServiceCase/Task/Quality | 一客一案、一任务一责任人 |
| B-N07 质量与贡献 | Delivery、验收、投诉 | 质量复核、返工、贡献确认 | Quality/Contribution | VERIFIED 后才产生贡献依据 |
| B-N08 年度服务 | 会员、权益、家庭意向 | 展示候选、续购、转人工 | PurchaseIntent/Decision | AI 不支付、不升级权益 |
| B-N09 裂变传播 | 家长确认的案例/邀请 | 脱敏、可见性、邀请 | Invite/Referral | 不向孩子营销；不暴露他人家庭信息 |
| B-N10 数据学习 | Feedback、Outcome、Quality | 形成评估样本和版本候选 | EvalCase/ImprovementCandidate | 不覆盖历史事实；需人工发布 |

## 5. 数据架构对齐

### 5.1 四类数据

1. **平台主数据**：租户、区域、语言、角色、产品、会员、组件、知识、Soul、策略和版本。
2. **家庭/服务业务数据**：Family、Person、Assessment、Journey、ServiceCase、Task、
   Quality、Contribution、Order、Entitlement、Outcome、Invite。
3. **AI 技术数据**：PrincipalSession、ContextSnapshot、RouteDecision、KnowledgeRef、
   ModelRun、Attempt、Draft、HumanTask、Feedback、Eval、Trace、Cost。
4. **事件与投影数据**：Outbox/Inbox、家庭时间线、FGCN 队列、商业飞轮指标、质量和审计投影。

### 5.2 全局身份和租户边界

所有对象都使用不可变全局 ID，并携带：

```text
global_id / tenant_id / region_id / family_id / subject_id
purpose / consent_version / data_class / locale / created_at / expires_at
correlation_id / causation_id / provenance_ref / deletion_ref
```

`tenant_id` 是权限边界，`family_id` 是家庭数据边界，`subject_id` 是未成年人数据边界，
`region_id` 是数据主权和部署边界；三者不能互相替代。

### 5.3 飞轮数据关系

```text
EntryEvent → AssessmentEvidence → GrowthIntent → JourneyPlan
   → ActionRecord → ServiceCase/Delivery → Outcome/Feedback
   → EvalCase/ComponentCandidate → New Blueprint/Prompt/Knowledge Version
```

商业飞轮的传播数据和资源飞轮的质量数据只能引用脱敏、授权后的证据；不能以家庭间比较
或单一分数作为算法优化目标。

## 6. 应用架构对齐

### 6.1 产品侧

```text
Mobile 34 UI
  → API Gateway / Tenant Resolver / Locale Resolver
  → Family Growth Application / Commerce / Trust
  → PrincipalApplicationFacade（AI 入口）
  → Read Projection + Named Action Receipt
```

### 6.2 平台侧

```text
Operations Console
  → Product Intelligence
  → Principal/service_product_architect
  → Component/Pattern/Knowledge Workbench
  → Compiler/Simulation/Evaluation
  → Human Publish Gate
  → ServiceBlueprintVersion
```

### 6.3 全球单元化部署

```text
Global Control Plane
  ├─ tenant catalog / policy / locale / release / billing metadata
  └─ model capability registry / public knowledge release

Regional Cell
  ├─ family_api + ai_runtime + workflow_worker
  ├─ tenant/family shards + regional knowledge index
  ├─ local human operations and compliance boundary
  └─ event stream + projections + deletion worker
```

跨区域只传递最小化、脱敏、经过授权的控制事件；家庭正文、未成年人数据和局部知识索引
默认留在所属区域。

## 7. AI 技术架构对齐

### 7.1 校长是统一 AI 控制面

```text
Principal Soul
  → Locale/Tenant Policy Overlay
  → Context Broker
  → Capability Router
  → Knowledge / Agent / Tool
  → Model Gateway
  → Safety / Schema / Provenance
  → Human Gate / User Confirmation
  → Domain Named Action
```

核心 Soul 全球一致；租户可以配置品牌语气、服务目录、地区法规和语言偏好，但不得覆盖
安全底线、事实边界、身份克隆禁止和儿童商业营销禁止。

### 7.2 多语言架构

语言必须拆成四个维度，而不是只在 UI 加翻译：

```text
user_locale       用户阅读/输入语言
content_locale    知识和服务内容语言
model_locale      模型能力支持的语言
policy_locale     法规、风险和人工队列语言
```

每次请求携带四者和 fallback 顺序。知识 Claim、Prompt、Schema、错误码和 Human Gate
都要有 locale 版本；缺少可靠翻译时必须降级为人工或明确不可用，不得静默机翻敏感建议。
多语言检索以 canonical concept_id 连接，不以翻译文本作为唯一主键；家庭原话保留原语言
引用，输出语言与引用语言分开记录。

### 7.3 多租户架构

租户采用“共享控制面、隔离数据面、可配置策略面”：

- 控制面共享版本和能力目录；
- 数据面按 region→tenant→family 分片；
- 策略面保存租户套餐、语言、品牌、知识范围、预算、SLA 和人工队列；
- 公共知识版本可被多个租户引用，租户私有知识只能在本租户命名空间检索；
- 租户之间禁止共享 Context、Memory、Embedding、缓存和评估样本；
- 超级管理员也必须通过显式租户授权和读取审计，不能使用“跨租户查询”快捷路径。

## 8. 千亿级家庭的规模设计

“千亿级”在现阶段是容量边界，不代表现在立即建设同等规模基础设施。架构必须从第一天
避免未来无法分片、无法迁移和无法删除。

### 8.1 容量分层

| 层 | 数据 | 设计 |
|---|---|---|
| 热路径 | 当前会话、今日任务、待审阅任务、近期投影 | 区域内低延迟存储，按租户/家庭分区 |
| 温路径 | 家庭时间线、服务记录、会员周期、近期反馈 | 分区表 + 事件重放 + 读模型 |
| 冷路径 | 历史审计、已脱敏评估、归档来源 | 对象存储/归档库，保留删除索引 |
| 计算路径 | 指标、推荐特征、评估、模型成本 | 流式聚合 + 批处理；不回写家庭事实 |

### 8.2 必须具备的规模原语

- 全局 ID 不依赖单库自增，支持跨区域生成和迁移。
- 事件按 `tenant_id/family_id` 分区，消费者幂等，允许重放和乱序修复。
- 业务查询不做跨租户全表扫描；运营统计使用预聚合和授权范围。
- AI 请求设置租户、家庭、Agent、模型能力四级预算和并发配额。
- 长文本、向量、附件与事务事实分离存储，均保留 deletion_ref。
- 区域故障时，家庭数据不跨主权边界自动漂移；只切换已批准的区域内备用单元。
- 发布采用 cell-by-cell rollout、影子流量、回滚和版本冻结，不做全球一次性切换。

### 8.3 可用性与一致性

强一致只用于：同意、成员权限、计划确认、任务责任人、支付/权益、人工决定和删除状态。
最终一致可用于：时间线、运营指标、推荐候选、搜索索引和评估聚合。任何最终一致投影
都必须显示时间戳和来源，不得伪装为最新业务事实。

## 9. 正反向审查与规模风险

| 设计 | 可能收益 | 可能失败 | 约束 |
|---|---|---|---|
| 统一 Principal | 品牌和体验一致 | 全球单点瓶颈、人格耦合 | cell-local runtime + capability contract |
| 多租户共享控制面 | 版本和能力复用 | 配置泄漏、跨租户检索 | namespace、policy、audit、deny-by-default |
| 多语言统一 Soul | IP 复用 | 翻译损失边界和文化误读 | canonical concept + locale eval + 人工升级 |
| 千亿级分片 | 可横向扩展 | 事务跨片复杂、数据迁移困难 | 事件驱动、局部事实、避免跨片 join |
| 数据飞轮 | 越用越好 | 把家庭变成训练燃料、目的漂移 | purpose/consent/retention/deletion 全链路 |
| AI 深度介入 | 服务更个性化 | 自动诊断、过度干预、幻觉 | Draft-only、Human Gate、Evidence、可撤回 |

## 10. 当前实现与目标差距

已经存在：

- 34 UI 基线；
- Python 平台内核和身份/租户上下文原语；
- Model Gateway 结构化协议；
- Principal 部分 SQL baseline；
- FGCN 相关 SQL baseline；
- Principal 能力路由契约和测试；
- 多租户/多语言字段的设计入口。

仍缺：

- Family API 的 Principal 正式路由和应用服务；
- 租户解析、区域路由、语言解析和策略覆盖的实际中间件；
- Context/Knowledge/Soul/Route 的持久化和版本发布；
- Human Gate、Evaluation、Deletion Worker 和跨区域事件；
- FGCN handler、Service Blueprint 编译器和真实交付闭环；
- cell 部署、分片、限流、灾备和大规模压测。

## 11. 实施顺序

1. **Foundation**：统一全局 ID、TenantContext、LocaleContext、Purpose、DataClass、
   Correlation/Causation 和错误码。
2. **Vertical Slice**：完成 UI-03→UI-05→UI-09 的 Principal 家庭闭环。
3. **Trust & Knowledge**：接入 Soul、知识 Claim、引用、安全、Human Gate、删除和评估。
4. **FGCN & Commercial**：接入服务案件/任务/验收/贡献，以及会员、邀请和商业边界。
5. **Cell Scale**：先做单区域多租户，再做多区域 cell、分片、事件流、区域容灾和多语言评估。
6. **Global Scale**：以容量压测、迁移演练、删除演练、供应商故障演练和 cell 发布证据为准，
   而不是以“部署了多少服务”作为规模完成度。

## 12. 六引擎对标补充

核心蓝图中的“拼多多 + 字节 + 海底捞 + 贝壳 + 教育 + 游戏”已拆解为六种可治理能力：

- 拼多多：低门槛体验、社交传播、挑战营和家长邀请；禁止多级分销和未成年人营销。
- 字节：内容分发、兴趣反馈、推荐解释和实验；不以停留时长作为唯一目标。
- 海底捞：被重视、即时响应、服务补救和前线服务质量；赔付/承诺仍由真人业务流程负责。
- 贝壳：FGCN/ACN 案件协作、任务拆解、授权、验收和贡献凭证；不按家庭结果直接分佣。
- 教育：测评、证据、21/90/年度节奏、方法论和长期陪伴；不做诊断或家庭总分。
- 游戏：章节、任务、小胜利、反馈、解锁和故事；不做排名、随机奖赏或连续打卡惩罚。

六引擎不是六个业务域。它们通过 `Experience & Trust`、Family Growth OS、FGCN、
Commerce 和 Platform Evolution 五个业务域落地，并由法咪莉校长统一编排和设定边界。
详细评审见 `docs/00_system/ARCHITECTURE_BENCHMARK_REVIEW_V3.md`。

## 13. 从家庭教育入口扩展到家庭需求平台

家庭教育是第一条可验证的需求闭环，不是平台终局。平台后续统一使用：

```text
NeedSignal → FamilyNeed → NeedProfile → SolutionBlueprintVersion
  → ServiceCase/Task → Delivery → Quality → Outcome → NextNeed
```

产品是标准化供给，服务是交付过程，解决方案是围绕家庭需求组合产品、服务和资源的
可执行蓝图。需求编排是跨域能力，不拥有订单、服务或成长事实；高质量满足必须由
资源能力、责任人、交付证据、验收和补救共同证明。详细目标模型见
`docs/00_system/FAMILY_NEEDS_PLATFORM_TARGET_MODEL.md`。

## 14. 平台精神

**We are 伐木累！We are family！** 是平台精神，不是单纯的营销口号。它要求平台先让
家庭、服务伙伴和团队感到被接纳、被尊重、有人一起走，再通过可靠的教育、服务、产品和
解决方案创造经济价值。精神表达可以亲切，但不能伪装亲属关系、制造情感依赖，或绕过
同意、价格、隐私、退款和人工服务边界。

它的真实故事是：父母和孩子在成长、家庭关系和生活里都会无奈、疲惫；平台通过法咪莉
校长把 AI、教育方法、真人服务和伙伴资源聚合起来，先接住处境，再陪家庭完成一个小行动，
让一次次小胜利变成温暖、温馨和共同成长，最终从“伐木累”变成“family”，成为一个真正的
大家庭。这个“大家庭”必须由可验证的响应、交付、质量和补救构成，不能由情感操纵构成。
