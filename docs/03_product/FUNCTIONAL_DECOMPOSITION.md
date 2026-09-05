---
id: PRODUCT-FUNCDECOMP-001
title: AiFamily 四级功能分解书（含 UI 对应）
type: product
status: current
version: 1.0
owner: project-manager
created: 2026-08-29
updated: 2026-08-30
canonical: true
supersedes: null
superseded_by: null
---

# AiFamily 四级功能分解书

> **状态判定以磁盘与测试为准，不以文档自述为准。**
> UI↔方法映射由 `grep -oE "familyApi\.[a-zA-Z]+"` 逐屏实测得出；端点实现状态由
> `grep '@router\.' ` 核对后端真实路由得出。与任何文档记载冲突时，本文件采信代码。


## 0. 分级定义

```text
1 级  业务域        六类业务闭环 + 平台内核 + AI Runtime + 运营侧
2 级  能力群        域内按职责聚合
3 级  功能          一件可被用户/系统感知的事
4 级  操作          一个端点或一次具体动作
```

## 1. 一页总览

| 层级 | 数量 |
|---|---|
| 1 级业务域 | 9 |
| 2 级能力群 | 24 |
| 3 级功能 | 58 |
| 4 级操作 | 79 |

### 4 级操作状态分布

| 状态 | 数量 | 占比 | 含义 |
|---|---|---|---|
| `已实现可用` | 11 | 13.9% | 端点存在且已挂载 `family_api`，有测试 |
| `已实现未挂载` | 11 | 13.9% | 代码与端点存在，router 未 include，前端调不通 |
| `合成数据支撑` | 9 | 11.4% | 由 `/dev/*` 自述 `SYNTHETIC_DEV_ONLY` 的服务提供 |
| `半成品` | 5 | 6.3% | 有部分层落盘，不构成可用能力 |
| `待建设（按批次）` | 8 | 10.1% | COMMERCE 按 Batch 6 建设；测试环境仍须完整实现 |
| `红线禁止` | 6 | 7.6% | 宪章 R9 或合规绝对禁止 |
| `未实现` | 29 | 36.7% | 无任何代码 |

**可用率 13.9%。** 前端 34 个 UI 屏幕中，仅 UI-02 / UI-03 两屏的后端链路真实可用。

### 缺口热力图（按 1 级域）

| 1 级域 | 4 级操作 | 已实现可用 | 缺口率 |
|---|---|---|---|
| 平台内核 | 6 | 6 | **0%** |
| ASSESSMENT 测评 | 8 | 7 | 12.5% |
| COMMERCE 商业 | 14 | 0 | **100%**（按 Batch 6 建设） |
| SERVICE 服务 | 9 | 0 | **100%** |
| PLAN 计划 | 10 | 0 | **100%** |
| GROWTH 成长 | 12 | 0 | **100%**（6 项红线禁止） |
| COMMUNITY 社区 | 6 | 0 | **100%** |
| AI Runtime | 8 | 0 | **100%**（2 项 EXPERIMENT） |
| 运营侧 | 6 | 0 | **100%**（11 项未挂载在此计入） |

**缺口最大的三个域**：PLAN（10 项全无）、GROWTH（12 项中 6 项还是红线禁止）、SERVICE（9 项全无，但它是计划要求提前的 Batch 2 关键路径）。

---

## 2. 功能菜单树（含 UI 对应）

图例：`✅`已实现可用 `⚠️`已实现未挂载 `🎭`合成数据支撑 `🚧`半成品 `⛔`红线禁止 `❌`未实现

### 1️⃣ ASSESSMENT 家庭成长测评 ｜ UI-02, UI-03

```
1. ASSESSMENT 家庭成长测评
├── 1.1 测评执行                                    [UI-02]
│   ├── 1.1.1 测评投影获取
│   │   └── ✅ GET  /families/{id}/ui/02/assessment
│   ├── 1.1.2 测评会话管理
│   │   ├── ✅ POST /families/{id}/assessments/sessions
│   │   └── ✅ POST /families/{id}/assessments/sessions/{sid}/submit
│   └── 1.1.3 逐题作答
│       └── ✅ POST /families/{id}/assessments/sessions/{sid}/responses
├── 1.2 成长假设生成与确认                          [UI-03]
│   ├── 1.2.1 假设投影获取
│   │   └── ✅ GET  /families/{id}/ui/03/growth-hypothesis
│   ├── 1.2.2 假设生成（确定性解读）
│   │   └── ✅ POST /families/{id}/assessments/{sid}/growth-hypothesis
│   └── 1.2.3 人工确认转 GrowthIntent
│       └── ✅ POST /families/{id}/growth-hypotheses/decisions
└── 1.3 成长入营                                    [UI-03]
    └── 1.3.1 入营流程
        └── ❌ POST /families/{id}/growth/onboarding  （前端在调，后端无）
```

- **代码**：`backend/domains/assessment/{api,service}.py`
- **测试**：`tests/domains/assessment/test_acceptance_chain.py`、`tests/apps/family_api/test_assessment_routes.py`
- **约束**：幂等（idempotency-key 必填，缺失 400）；审计（全链路记 AuditEvent，测试断言 ≥5 条）；R9（`canonical_fact` 恒 false）
- **⚠️ 已知合规缺口**：**未接 ConsentGate**。采集未成年人测评数据却无同意校验，违反 `COMPLIANCE_HARD_CONSTRAINTS §1`
- **架构缺口**：非四层结构（`api.py`+`service.py` 两模块）；内存 repository，进程重启数据全失

---

### 2️⃣ PLAN 成长计划 ｜ UI-04, UI-05, UI-08, UI-09

```
2. PLAN 成长计划
├── 2.1 成长优先级                                  [UI-04]
│   └── 2.1.1 优先级获取
│       └── ❌ GET  /families/{id}/growth/priority
├── 2.2 旅程计划管理                                [UI-04, UI-05]
│   ├── 2.2.1 计划预览
│   │   └── ❌ GET  /families/{id}/growth/plan-preview
│   ├── 2.2.2 计划创建
│   │   └── ❌ POST /families/{id}/growth/journey-plans
│   ├── 2.2.3 计划确认
│   │   └── ❌ POST /families/{id}/growth/journey-plans/{pid}/confirm
│   ├── 2.2.4 计划获取
│   │   └── ❌ GET  /families/{id}/growth/journey-plan
│   ├── 2.2.5 阶段复盘
│   │   └── ❌ POST /families/{id}/growth/journey-plans/{pid}/phase-review
│   └── 2.2.6 计划暂停
│       └── ❌ POST /families/{id}/growth/journey-plans/{pid}/pause
│           └── 注：前端连 client 方法都没有（源仓库后端有 pausePlan() 但无入口）
├── 2.3 今日任务                                    [UI-09]
│   ├── 2.3.1 今日投影
│   │   └── ❌ GET  /families/{id}/today
│   ├── 2.3.2 任务打卡
│   │   └── ❌ POST /families/{id}/tasks/{tid}/check-in
│   └── 2.3.3 任务状态变更
│       └── ❌ POST /families/{id}/tasks/{tid}/state
└── 2.4 家庭复盘回读                                [UI-08]
    └── 2.4.1 复盘回读
        └── ❌ GET  /families/{id}/growth/family-review-readback
```

- **状态**：**10 项 4 级操作全部未实现**。`backend/domains/growth_plan/` 仅有 `domain/errors.py`（37 行错误类型枚举），无实体模型
- **UI 现状**：UI-09 在源仓库 NestJS 下曾端到端验证，在 AiFamily 不可用
- **计划位置**：MIGRATION_PLAN_V2 Batch 4

---

### 3️⃣ GROWTH 成长成果 ｜ UI-10, UI-11, UI-12, UI-29

```
3. GROWTH 成长成果
├── 3.1 成长活动目录                                [UI-11, UI-12, UI-22, UI-25, UI-27, UI-28]
│   ├── 3.1.1 平台界面投影
│   │   └── 🎭 GET  /families/{id}/dev/platform-surfaces
│   │       └── 真实数据源应为：活动目录（独立域）+ 社区内容（独立域）
│   └── 3.1.2 24 张 UI 卡片文案
│       └── ⛔ 硬编码文案字典 + 卡片元组
│           └── 依据：AI_NATIVE_PRINCIPLES §4「硬编码文案冒充智能」
│           └── 实测：前端手写窄化 TS 接口，24 张卡**一个字段都没被消费**（死负载）
├── 3.2 核心成长投影                                [UI-10, UI-29]
│   ├── 3.2.1 成长事件流
│   │   └── 🎭 GET  /families/{id}/dev/core-growth
│   │       └── 真实数据源应为：成长事件流（真实 DB）
│   └── 3.2.2 行动建议
│       └── 🎭 shared_action 字段（5 条硬编码 action）
│           └── 真需求，但须走 Recommendation/DRAFT + 生成式，不得移植硬编码
├── 3.3 成长效果展示                                [UI-08, UI-11, UI-12, UI-29]
│   ├── 3.3.1 成长排行
│   │   └── ⛔ journey_route: 'growth-ranking'
│   │       └── 依据：R9；FELS 语义表已判 legacy_profile.ranking = RETIRE
│   ├── 3.3.2 成长成果证明
│   │   └── ⛔ UI-29「成长成果」标题 + 三数字 + 环形指标
│   │       └── 依据：R9；视觉上仍是评分/成果证明
│   ├── 3.3.3 成果勋章
│   │   └── ⛔ BADGES 页面内硬编码数组
│   └── 3.3.4 家庭经验分享流
│       └── ⛔ family_learning_exchange_feed
│           └── 写死「有家长会在情绪上来时先停一停」等**虚构他人言论**
│           └── 这不是 fixture 标注问题，是冒充真实用户分享
└── 3.4 流程事件记录                                [UI-15, UI-16, UI-23, UI-26]
    └── 3.4.1 交互事件写入
        └── 🎭 POST /families/{id}/dev/flow-events
            └── 真需求，建议改名 /families/{id}/interaction-events
```

- **矩阵001 状态**：UI-11 的跨家庭排名、家庭总分和等级化比较属于禁止行为；UI-08/12/29 的私有回顾、证据绑定成果和经同意分享属于允许能力，不能把四个页面一概标为 `GATE_BOUNDARY`
- **MIGRATION_PLAN_V2 第3节处置**：允许的成长回顾、成果分享和社区互动路径必须在测试环境完整建设；只有禁止的正向行为保留拒绝、审计和人工处理路径，整个 GROWTH 闭环仍需继续迁移和重建
- **9 个屏幕影响评估**（来自 `DEV_SYNTHETIC_FIELD_ANALYSIS.md`）：全部有 `?? local` / `.catch()` 兜底，**移除 `/dev/*` 无一白屏**。7 屏正常、1 屏部分降级（UI-10）、1 屏需重新设计（UI-29）

---

### 4️⃣ SERVICE 服务网络 ｜ UI-19, UI-20, UI-21, UI-24, UI-31, UI-34

```
4. SERVICE 服务网络
├── 4.1 服务供给
│   ├── 4.1.1 服务目录查询                          [UI-19, UI-20, UI-21, UI-24]
│   │   └── ❌ GET  /families/{id}/services/offerings
│   └── 4.1.2 可预约时段查询                        [UI-20, UI-21]
│       └── ❌ GET  /families/{id}/services/slots
├── 4.2 预约履约
│   ├── 4.2.1 提交预约                              [UI-21]
│   │   └── ❌ POST /families/{id}/services/booking-requests
│   ├── 4.2.2 取消预约                              [UI-21]
│   │   └── ❌ 端点与 client 方法均不存在（源仓库审计确认"入口完全不存在"）
│   └── 4.2.3 服务客户投影                          [UI-24, UI-31, UI-34]
│       └── ❌ GET  /families/{id}/services/customer-projection
├── 4.3 服务对象建模（FGCN 基础）
│   ├── 4.3.1 ServiceProvider
│   │   └── 🚧 backend/domains/service/domain/ 部分落盘，无 entities.py
│   ├── 4.3.2 ServiceOffering
│   │   └── 🚧 同上
│   ├── 4.3.3 AvailabilitySlot
│   │   └── 🚧 同上
│   └── 4.3.4 BookingRequest / ServiceRecord
│       └── 🚧 同上
└── 4.4 FGCN 协作分配（Batch 7）
    ├── 4.4.1 任务分派
    │   └── ❌ 未实现
    └── 4.4.2 贡献确认与分账
        └── ❌ 未实现
```

- **⚠️ 这是全项目最高优先业务缺口**：MIGRATION_PLAN_V2 第3节把 SERVICE 预约子链**从 Batch 5 提前到 Batch 2**，原文理由「已验证的付费主力闭环，晚做等于让已验证价值悬空」
- **矩阵001 状态**：UI-19/20 = `BACKEND_READY`，UI-21/24 = `E2E_READY`（源仓库 NestJS 下已端到端打通）
- **当前状态**：`service_booking` 登记为 `PARTIAL_ABANDONED`（前次 agent 卡死），已重派
- **FGCN 可行性研究结论**：ACN 地基是「可独立验真的标的物」，家庭教育无等价物且该方向被 R9 禁止；FGCN 用「已验收贡献」替换地基，方向正确（见 `docs/13_research/market/`）

---

### 5️⃣ COMMERCE 商业化 ｜ UI-06, UI-13, UI-14, UI-17, UI-18, UI-30, UI-32

> **当前状态：尚未完成，按 Batch 6 建设。** 批次是交付顺序，不是禁止开发。
> 测试环境必须完整实现目录、订单、支付 sandbox、会员、权益、积分、退款和续购；生产环境再切换真实商品、库存、支付和结算适配器。未成年人自动化决策商业营销在所有环境都必须拒绝、审计并保留人工处理路径。

```
5. COMMERCE 商业化
├── 5.1 商品目录                                    [UI-13, UI-14]
│   ├── 5.1.1 商品列表
│   │   └── ❌ GET  /families/{id}/commerce/products（待实现）
│   └── 5.1.2 商品投影
│       └── ❌ GET  /families/{id}/commerce/customer-projection（待实现）
├── 5.2 下单意图                                    [UI-14]
│   └── 5.2.1 提交订单意图
│       └── ❌ POST /families/{id}/commerce/order-intents（待实现）
├── 5.3 会员体系                                    [UI-06, UI-17, UI-18, UI-30, UI-32]
│   ├── 5.3.1 会员方案查询
│   │   └── ❌ GET  /families/{id}/membership/plans（待实现）
│   ├── 5.3.2 会员投影
│   │   └── ❌ GET  /families/{id}/membership/customer-projection（待实现）
│   ├── 5.3.3 档位生命周期
│   │   ├── ⚠️ POST /subscriptions
│   │   ├── ⚠️ POST /tier-activations
│   │   ├── ⚠️ POST /period-renewals
│   │   └── ⚠️ POST /period-expirations
│   └── 5.3.4 权益台账
│       ├── ⚠️ POST /benefit-grants
│       ├── ⚠️ POST /benefit-reservations
│       ├── ⚠️ POST /benefit-reservations/{id}/release
│       ├── ⚠️ POST /benefit-consumptions
│       └── ⚠️ POST /benefit-revocations
├── 5.4 积分体系                                    [UI-17]
│   ├── 5.4.1 积分余额
│   │   └── ❌ 服务端积分账本余额投影（待实现）
│   │       └── 必须清理 `pointsBalance = membership?.dev_points?.balance ?? 1280` 硬编码兜底值
│   └── 5.4.2 积分兑换
│       └── ❌ backend/domains/loyalty_points/（1984 行，待补齐持久化与验收）
│           └── ⛔ 不得面向孩子端：《未成年人网络保护条例》第24条3款**绝对禁止**
└── 5.5 会员界面投影
    ├── ⚠️ GET  /projection
    └── ⚠️ GET  /screens/{surface_id}
```

- **membership 端点已挂载 `family_api`**（`main.py:29`），但依赖注入按设计抛异常，端点在依赖层 fail-closed → 标 `⚠️已实现未挂载` 的实质是"挂了但不可用"
- **建设验收项**：① loyalty_points 的账本与兑换状态机必须登记并有验收测试 ② 必须有能真实失败的 guardrail，证明积分流程无法以孩子为营销对象 ③ UI-17 硬编码值必须由正式账本投影替代。上述验收项约束实现质量和生产准入，不阻止测试环境建设完整流程。

---

### 6️⃣ COMMUNITY 社区 ｜ UI-25, UI-26, UI-27, UI-28

```
6. COMMUNITY 社区
├── 6.1 社区内容
│   ├── 6.1.1 经验交流流                            [UI-25, UI-27, UI-28]
│   │   └── 🎭 由 /dev/platform-surfaces 承载
│   │       └── 真实数据源应为：社区内容独立域
│   └── 6.1.2 内容发布
│       └── ❌ 未实现
├── 6.2 社区互动
│   ├── 6.2.1 打卡分享                              [UI-26]
│   │   └── 🎭 recordDevFlowEvent
│   └── 6.2.2 导师点评
│       └── ❌ 未实现
└── 6.3 家庭间连接（"家庭与家庭的关系"）
    ├── 6.3.1 同城圈子
    │   └── ❌ 未实现
    └── 6.3.2 身份等级
        └── ⛔ 需审查：身份等级不得成为家庭排名变体（R9）
```

- **战略定位**：`COMMERCIAL_VALUE_STRATEGY §0.1` 明确「家庭与家庭的关系」是"家是港湾"定位的直接承载，**不是可随意砍掉的边缘功能**，只是当前证据不足
- **计划位置**：Batch 7

---

### 7️⃣ 平台内核（支撑域，不要求 AI 原生）

```
7. 平台内核
├── 7.1 身份与租户
│   └── 7.1.1 ActorContext / TenantContext
│       └── ✅ backend/platform/identity/context.py
│           └── ⚠️ TenantContext.is_active 零调用方 → 暂停租户未被执行
├── 7.2 授权
│   └── 7.2.1 策略裁决（fail-closed + deny-overrides）
│       └── ✅ backend/platform/authorization/policy.py
│           └── 已修 R9 绕过：human_only 现为集合级否决，与注册顺序无关
├── 7.3 同意
│   └── 7.3.1 按目的校验（撤回立即生效，无缓存）
│       └── ✅ backend/platform/consent/{models,gate}.py
│           └── ⚠️ 无 REFUSED 状态、无 expires_at（EXPIRED 不可达）、无年龄校验
├── 7.4 审计
│   └── 7.4.1 变更留痕 + 读取留痕（第36条）
│       └── ✅ backend/platform/audit/{models,recorder,store}.py
├── 7.5 幂等
│   └── 7.5.1 命令去重
│       └── ✅ backend/platform/idempotency/keys.py
│           └── ⚠️ 仅内存实现；无 tenant 维度 → 跨租户 key 碰撞
└── 7.6 持久化
    └── 7.6.1 UnitOfWork 事务边界
        └── ✅ backend/platform/persistence/{session,unit_of_work}.py
            └── ⚠️ 无租户隔离；lru_cache 逐出 engine 不 dispose（连接池泄漏）
```

- **唯一缺口率 0% 的域**，6 项全部有代码有测试
- 各项 `⚠️` 缺口来自 `docs/06_platform/` 的逐模块规格审查，已登记为 T-14

---

### 8️⃣ AI Runtime ｜ 全域支撑

```
8. AI Runtime
├── 8.1 模型网关
│   ├── 8.1.1 供应商准入（含第16条五项）
│   │   └── ⚠️ backend/intelligence/model_gateway/provider_registry.py
│   │       └── shipped registry 零个外部供应商可调用（sub_delegates=None 即拒）
│   └── 8.1.2 结构化生成（Draft-only）
│       └── ⚠️ backend/intelligence/model_gateway/gateway.py
├── 8.2 独占区候选（三区方法论：唯一值得押注核心研发资源的部分）
│   ├── 8.2.1 Family Context
│   │   └── ❌ 完全空白（FamilyMemoryDialogueRuntime 零调用方，embedding 不存在）
│   │       └── ⚠️ 研究结论：不得用「单表+单HNSW+后置 family_id 过滤」
│   │           pgvector 过滤在索引扫描**之后**执行，10% 命中率下平均只返回约 4 行且不报错
│   ├── 8.2.2 Family Growth Graph
│   │   └── ❌ 完全空白
│   ├── 8.2.3 Growth Intervention Engine
│   │   └── ❌ 未实现（最小落地：GrowthHypothesis 加 primary_contradiction_ref + 置信度排序）
│   └── 8.2.4 Service Blueprint Library
│       └── ❌ 未实现
├── 8.3 五类业务 Agent
│   ├── 8.3.1 家长顾问 / 孩子陪练 / 助教助手 / 成长规划师 / 经营助手
│   │   └── ❌ 全部未实现
│   └── 8.3.2 输出约束
│       └── ⛔ 所有 Agent 输出必须是 Draft/Hypothesis/Proposal，
│           `may_mutate_business_state = False`（R9）
└── 8.4 Prompt Registry / Context Broker / Eval
    └── ❌ 全部未实现
        └── 后果：provenance 的 prompt_version 目前只强制非空、不校验指向真实 prompt
            → PIPL 第24条可解释性**部分满足**，非完全满足
```

---

### 9️⃣ 运营侧（product_intelligence，非家庭侧）

```
9. 运营侧产品智能
├── 9.1 市场信号 → 洞察 → 假设 → 验证
│   ├── 9.1.1 假设人工验证（R9 参考实现）
│   │   └── ⚠️ AI actor 调 validate 被拒（test_hypothesis_validation_guardrail 断言）
│   └── 9.1.2 其余链路端点
│       └── ⚠️ api/routes.py 未挂载
└── 9.2 三区战略引擎
    ├── 9.2.1 六维度确定性打分
    │   └── ⚠️ api/zone_routes.py 未挂载（6 端点）
    └── 9.2.2 Portfolio 六桶口径
        └── ⚠️ 同上
```

- **⚠️ T-03 发现的生产路径缺陷**：该域私藏源仓库 SQL 副本，比 baseline 多 `validated_by`/`validated_at`/`validation_reason` 三列，而 ORM **要求**这三列 → 只跑过 `alembic upgrade head` 的库上 `validate_growth_hypothesis` 会失败。集成测试因自建 schema 而未暴露（**测试与生产用了两份不同 schema**）

---

## 3. UI ↔ 功能对应总表

| UI | 屏幕职责 | 调用的 client 方法 | 后端状态 |
|---|---|---|---|
| index (UI-01) | 家庭首页 | getFamilyHome, requestGrowthHelp, requestGrowthRecommendation, decideGrowthService, confirmGrowthIntent | ❌ 全无 |
| UI-02 | 测评填写 | getFamilyAssessment, startFamilyAssessment, saveFamilyAssessmentResponse, submitFamilyAssessment | ✅ 全可用 |
| UI-02-result | 测评结果 | （复用 UI-02/03 数据） | ✅ |
| UI-03 | 假设确认 | getGrowthHypothesis, generateGrowthHypothesis, decideGrowthHypothesis, getActiveOnboarding, startGrowthOnboarding | ✅ 3/5，❌ onboarding 2 项 |
| UI-04 | 90 天计划 | getGrowthPriority, getPlanPreview, createJourneyPlan, confirmJourneyPlan, getJourneyPlan | ❌ 全无 |
| UI-05 | 计划执行 | getJourneyPlan, reviewJourneyPhase, getServiceJourney | ❌ 全无 |
| UI-06 | 会员/商品 | getMembershipPlans, getMembershipCustomerProjection, getCommerceCustomerProjection | ❌ 待实现（Batch 6） |
| UI-07 | 静态页 | 无调用（93 行） | — |
| UI-08 | 复盘回读 | getFamilyReviewReadback | ❌ 后端缺口；允许建设家庭私有、证据绑定的回顾 |
| UI-09 | 今日任务 | getFamilyToday, checkInTodayTask, changeTodayTaskState | ❌ 全无 |
| UI-10 | 核心成长 | getDevCoreGrowth | 🎭 合成 |
| UI-11 | 成长效果 | getDevPlatformSurfaces | 🎭；跨家庭排名/总分正向路径禁止 |
| UI-12 | 成长榜单 | getDevPlatformSurfaces | 🎭；按事实、同意和非比较方式重建 |
| UI-13 | 商城首页 | getCommerceProducts | ❌ 待实现（Batch 6） |
| UI-14 | 商品下单 | getCommerceProducts, getCommerceCustomerProjection, submitCommerceIntent | ❌ 待实现（Batch 6） |
| UI-15 | 流程事件 | recordDevFlowEvent | 🎭 合成 |
| UI-16 | 流程事件 | recordDevFlowEvent | 🎭 合成 |
| UI-17 | 积分商城 | getMembershipCustomerProjection | ❌ 待实现；硬编码 1280 需清理 |
| UI-18 | 会员权益 | getMembershipPlans, getMembershipCustomerProjection, getCommerceCustomerProjection | ❌ 待实现（Batch 6） |
| UI-19 | 名师专区 | getServiceOfferings | ❌ 未实现 |
| UI-20 | 服务时段 | getServiceOfferings, getServiceSlots | ❌ 未实现 |
| UI-21 | 提交预约 | getServiceOfferings, getServiceSlots, submitServiceBooking | ❌ 未实现（取消入口本就不存在） |
| UI-22 | 平台界面 | getDevPlatformSurfaces | 🎭 合成 |
| UI-23 | 平台界面 | getDevPlatformSurfaces, recordDevFlowEvent | 🎭 合成 |
| UI-24 | 服务投影 | getServiceCustomerProjection, getServiceOfferings | ❌ 未实现 |
| UI-25 | 社区流 | getDevPlatformSurfaces | 🎭 合成 |
| UI-26 | 社区打卡 | recordDevFlowEvent | 🎭 合成 |
| UI-27 | 社区内容 | getDevPlatformSurfaces | 🎭 合成 |
| UI-28 | 社区内容 | getDevPlatformSurfaces | 🎭 合成 |
| UI-29 | 成长成果 | getDevCoreGrowth, getDevPlatformSurfaces | 🎭；按真实证据和分享同意重建 |
| UI-30 | 会员续费 | getMembershipPlans, getMembershipCustomerProjection, getCommerceCustomerProjection | ❌ 待实现（Batch 6） |
| UI-31 | 服务记录 | getServiceCustomerProjection | ❌ 未实现 |
| UI-32 | 会员/商城 | getMembershipCustomerProjection, getCommerceCustomerProjection | ❌ 待实现（Batch 6） |
| UI-33 | 静态页 | 无调用（30 行） | — |
| UI-34 | 服务投影 | getServiceCustomerProjection | ❌ 未实现 |

---

## 4. 红线禁止清单（6 项）

| # | 功能 | 依据 | UI |
|---|---|---|---|
| 1 | 家庭总分 / 家庭排名 | R9；FELS `family_score`/`ranking` = RETIRE | UI-11, UI-12 |
| 2 | `journey_route: 'growth-ranking'` | 同上，路由名直接叫 ranking | UI-11 |
| 3 | 成长成果证明（三数字+环形指标） | R9，视觉上是评分 | UI-29 |
| 4 | 虚构他人言论冒充用户分享 | 非 fixture 问题，是冒充真实分享 | UI-25/27/28 |
| 5 | 向未成年人自动化决策商业营销 | 《未成年人网络保护条例》第24条3款**绝对禁止** | UI-17 积分 |
| 6 | AI 输出自动成为家庭事实 | R9；`may_mutate_business_state=False` | 全域 |

**"我们明确不做什么"与"做什么"同等重要**，故列出而非省略。

---

## 5. 交叉核对发现的文档与代码不符

| # | 发现 |
|---|---|
| 1 | `UI_API_ENDPOINT_INVENTORY.md` 记 46 端点，本次实测 UI 层调用 client 方法去重后覆盖面一致，但 **UI-07/UI-33 零调用**未在该清单体现（它们是纯静态页） |
| 2 | membership 11 个端点已 `include_router`，但依赖注入按设计抛异常 → "已挂载"≠"可用"，两份 registry 的 `api` 字段均未表达这一区别 |
| 3 | `product_intelligence` 域私藏 SQL 副本比 baseline 多三列，ORM 要求这三列 → 测试与生产用两份不同 schema（T-03 发现） |
| 4 | `service` 域 `status: PARTIAL_ABANDONED`，domain 层落盘但无 `entities.py`，MIGRATION_MANIFEST 已如实登记 |

---

## 6. 排期建议（按计划批次，非按缺口大小）

| 优先 | 内容 | 依据 |
|---|---|---|
| **1** | SERVICE 预约子链（4.1/4.2） | 计划要求从 Batch 5 **提前到 Batch 2**，已验证的付费主力闭环 |
| **2** | Assessment 接 ConsentGate + 四层重构 | 现存合规缺口 + Batch 1 收尾 |
| **3** | PLAN 闭环（2.1–2.4） | Batch 4，10 项全无 |
| **4** | Family Context 最小检索层（8.2.1） | 独占区候选，其余三项都依赖它 |
| **按批次建设** | COMMERCE 全部 | Batch 6；测试环境完整实现，生产切换真实数据与外部适配器 |
| **按合规语义重建** | GROWTH 允许路径（3.3） | 私有回顾、证据绑定成果和经同意分享照常建设；仅排名/总分等禁止正向行为保留拒绝、审计和人工处理 |
