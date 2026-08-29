---
id: BIZ-SCENARIO-001
title: 业务场景与流程架构、功能组件
type: business
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# 业务场景与流程架构、功能组件 (Business Scenarios, Process Architecture & Functional Components)

- **状态**: 见上方 front matter `status: current` — 依据 `governance/REPOSITORY_CONSTITUTION.md` R13，本文件是本主题唯一当前真相
- **生效**: 2026-08-29
- **与 `BUSINESS_ARCHITECTURE.md` 的关系**: 该文件回答"为什么做、钱从哪来、底线是什么"；本文件回答"具体场景是什么样、流程怎么走、由哪些功能组件承载、每个组件现在做到了什么程度"
- **GROUNDING**: `docs/14_reference/legacy_audits/FAMILY_UI_BACKEND_SCENARIO_CONSISTENCY_AUDIT_V1.md`（下称"审计V1"）、`docs/14_reference/legacy_audits/FAMILY_CONSUMER_UI_FRONTEND_BACKEND_CONSISTENCY_MATRIX_001.md`（下称"矩阵001"）、`docs/11_delivery/migration/MIGRATION_PLAN_V2.md`、`docs/01_strategy/COMMERCIAL_VALUE_STRATEGY.md`（下称"V2战略"）、三份原始战略材料

---

## 0. 本文件的性质

本文件不新造场景。所有场景/流程/组件的完成度判断，一律回指矩阵001的34页UI状态或审计V1的代码级核实结果，不使用"预计"、"应该能"这类无证据表述。凡是标注为`GATE_BOUNDARY`的场景，本文件如实呈现其"当前不能做"的状态，不描述成"即将上线"。

---

## 1. 核心业务场景：家长视角用户路径七阶段

来源：新商业模式PPT Slide 7（用户路径：从孩子问题进入，在父母成长中完成价值交付）。

| 阶段 | 家长当下心理 | 平台动作 | 核心产品/场景 | 对应功能组件 | 矩阵001/审计V1 真实完成度 |
|---|---|---|---|---|---|
| 1. 触发 | 孩子出现现实问题 | 以问题场景吸引进入 | 内容、沙龙、家庭测评入口 | UI-01首页、UI-02测评启动 | UI-01=`COMMERCIAL_READ_SLICE_READY`；UI-02=`COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV`（已端到端验证） |
| 2. 觉醒 | 想找到问题原因 | 温和呈现家庭互动影响 | AI诊断与父母成长报告 | UI-02测评→UI-03假设解读 | UI-02→UI-03已端到端验证：真实版本化测评会话+`CONFIRM_GROWTH_HYPOTHESIS`/`DISMISS_GROWTH_HYPOTHESIS` Named Action+E2E。注意："AI诊断"在实现层不是诊断，是`GrowthHypothesis`（假设），确认后才成`GrowthIntent`，这正是R9约束在此场景的落地 |
| 3. 行动 | 愿意尝试改变 | 把学习变成每日小行动 | 21天挑战、每日任务 | UI-09今日任务 | `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV`：GrowthAction持久化生命周期，开始/暂停/继续/取消/完成均幂等并写Audit/Outbox，真实PostgreSQL状态机与重启回读已测 |
| 4. 改变 | 希望看到真实效果 | 提供系统陪跑与反馈 | 90天计划、顾问、社群 | UI-04/05计划、UI-06陪跑服务 | UI-04/05=`UI_READY_BACKEND_GAP`（原图和路由完成，正式API/DTO未接入；pause入口连客户端SDK都没有，见审计V1 3a节）；UI-06=`UI_READY_BACKEND_GAP` |
| 5. 长期 | 需要持续支持 | 沉淀会员、档案和关系 | 年度会员、活动、AI管家 | UI-07会员中心、UI-30年度会员 | 均为`GATE_BOUNDARY`：无正式会员/权益读模型，不接真实支付/权益 |
| 6. 传播 | 愿意展示成长成果 | 生成可分享的身份与结果 | 成长报告、社区、邀请权益 | UI-12成果海报、UI-15邀请有礼 | UI-12=`GATE_BOUNDARY`（无成果事实DTO，不得生成效果证明）；UI-15=`E2E_READY`（邀请机制本身已打通，`CREATE_INVITE` Named Action） |

**结论**（沿用V2战略第1节）：七阶段里只有"触发→觉醒→行动"这一段（阶段1-3，对应UI-02→UI-03→UI-09）是端到端真实打通的商业闭环。"改变"阶段部分打通（服务预约子链，见第2节SERVICE闭环）。"长期"和"传播"阶段的大部分场景仍受宪法边界限制或存在前后端缺口。

---

## 2. 六类业务闭环（沿用审计V1第1节命名，回指矩阵001状态；`MIGRATION_PLAN_V2.md`第3节给出处理排期）

### 2.1 ASSESSMENT（测评→假设解读）

- **流程步骤**：家庭选择孩子/边界 → 完成版本化测评（UI-02）→ 提交不可变Evidence → AI生成`Hypothesis`（不评分不诊断）→ 家庭确认或驳回假设（UI-03）→ 确认后才形成`GrowthIntent`。
- **涉及功能组件**：`UI02_FAMILY_ASSESSMENT_V1`契约、`UI03_GROWTH_HYPOTHESIS_V1`契约、`START_ASSESSMENT`/`SAVE_ASSESSMENT_RESPONSE`/`SUBMIT_ASSESSMENT`/`CONFIRM_GROWTH_HYPOTHESIS`/`DISMISS_GROWTH_HYPOTHESIS` Named Action。
- **当前状态**：`COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV`——矩阵001唯一标注"已具备真实版本化测评会话、正式PostgreSQL持久化、跨端Named Action、幂等、family scope/consent、不可变提交证据与E2E"的闭环。生产路径仍是NestJS，`PYTHON_READY`目前只在test/staging环境生效（审计V1 3e节，尚未`NEST_REMOVED`）。
- **下一步**：UI-04以已确认Intent生成私有报告/方案，不把Hypothesis写成结果（矩阵001 UI-03行"下一步"）。

### 2.2 PLAN（计划按钮接线）

- **流程步骤**：确认GrowthIntent后生成90天计划（UI-04说明→UI-05计划）→ 每日任务落到UI-09 → 阶段复盘（review）或暂停（pause）。
- **涉及功能组件**：`journey-plan.service.ts`的`pausePlan()`/`reviewCurrentPhase()`（源TS侧真实存在，走事务+状态转换+审计）。
- **当前状态**：**必须拆开看**（审计V1 3a节精确纠正）——
  - phase-review**已接线**：UI-05第63-68行`reviewPhase()`已调用`familyApi.reviewJourneyPhase(...)`，"继续下一阶段"/"先调整节奏"两个真实按钮存在。
  - pause**完全没有接线**，且客户端SDK层从未生成/编写`pausePlan`/`pauseJourney`方法——不是"UI没接后端已有能力"，而是比这更靠前一步的缺失。
  - UI-04整体仍是`UI_READY_BACKEND_GAP`（仅LLM draft/说明，无报告事实DTO）；UI-05因pause缺口整体标注`UI_READY_BACKEND_GAP`，但phase-review子功能已验证。
- **下一步**：`MIGRATION_PLAN_V2.md`第3节明确"不把补齐前端pause按钮作为Python迁移的前置阻塞项——那是独立的前端任务"。

### 2.3 GROWTH（成长效果类页面）

- **对应UI**：UI-08成长报告、UI-11成长榜单、UI-12成长成果海报、UI-29成长成果。
- **当前状态**：**全部`GATE_BOUNDARY`**。不是技术缺口，是产品边界主动限制：不得计算跨家庭排名（UI-11永久禁止跨家庭统计/排序）、不得生成成果证明或效果断言（UI-12/29）、不得把静态分值视为事实（UI-08）。UI-29的`BADGES`核实为页面内硬编码数组（审计V1 3b节）。
- **下一步**：`MIGRATION_PLAN_V2.md`第3节明确判断——**不迁移，不重建**，"这类UI本身处于产品边界不允许的状态，Python重写只会把违规语义带过去。需要产品侧先决定这些UI要不要存在，不是技术迁移问题"（本文件不擅自建议方向，留作待人类裁决项，见文末）。

### 2.4 SERVICE（专家咨询预约子链）

- **流程步骤**：浏览名师专区（UI-19）→ 查看详情/可预约时段（UI-20）→ 提交预约请求（UI-21）→ 查看我的预约（UI-24）。
- **涉及功能组件**：`Provider→ServiceOffering→AvailabilitySlot→BookingRequest→BookingServiceRecord→ProductEvent`对象链；`GET /services/offerings`/`GET /services/slots`/`POST /services/booking-requests`（`SubmitServiceBooking` Named Action）/`GET /services/customer-projection`。数据库迁移`0032_family_service_booking_objects.sql`。
- **当前状态**：UI-19/20=`BACKEND_READY`（真实`GET /services/offerings`API，从早期GAP升级）；UI-21/24=`E2E_READY`（PostgreSQL 3/3集成测试通过，幂等回放、row-version取消、时段容量释放、Consent缺失负例均覆盖）。**这是六类闭环里除ASSESSMENT外唯一端到端打通的**，且V2战略判断为"当前唯一验证过的付费主力闭环"，`MIGRATION_PLAN_V2.md`把此域提前到Batch 2。
- **已知缺口**：UI-21无取消预约文案/按钮，客户端也没有`cancelBooking`方法（审计V1 3c节，"入口完全不存在"而非"部分实现"）。

### 2.5 COMMERCE（商城目录/积分）

- **对应UI**：UI-13商城首页、UI-14商品详情、UI-15邀请有礼、UI-16拼团专区、UI-17积分商城、UI-18我的资产。
- **当前状态**：UI-15/16=`E2E_READY`（`CREATE_INVITE`/`CREATE_GROUP` Named Action，0022表，PostgreSQL+Web已测，无扣款）；UI-13/14=`UI_READY_BACKEND_GAP`（尚无正式catalog DTO，客户端不得传价格）；UI-17=`GATE_BOUNDARY`——核实代码确认`DAILY_TASKS`/`REWARDS`数组积分数值（`+50`/`99积分`/`200积分`）是硬编码常量，且`pointsBalance = membership?.dev_points?.balance ?? 1280`有硬编码兜底值1280（审计V1 3b节）。
- **技术骨架实际比预想扎实**：`family-commerce-intent.service.ts`是真实SQL服务，含幂等重放、乐观锁、consent校验，`family_product_offerings`/`family_order_intents`/`family_entitlements`等表结构完备，但被`requireDevSyntheticTestLoop()`限定在DEV/TEST合成环境（`fixture_only=true`的CHECK约束），价格是前端展示层派生文案，不接真实支付（V2战略第2节层3）。
- **下一步**：`MIGRATION_PLAN_V2.md`要求迁移前先解决UI-17硬编码积分和"未成年人商业场景权限规则不明确"的Stop Condition，不得把硬编码常量原样搬进Python。

### 2.6 COMMUNITY（社区流）

- **对应UI**：UI-25家长社区、UI-26发布动态、UI-27动态详情、UI-28我的社区。
- **当前状态**：UI-26=`E2E_READY`（`PUBLISH_TEMPLATE` Named Action，模板白名单，零外发）；其余（UI-25/27/28）为`GATE_BOUNDARY`/`UI_READY_BACKEND_GAP`（禁止真实外发/跨家庭推荐，不得显示真实社区数据，禁止公开画像/等级事实）。
- **重要定性**：V2战略0.1节明确——这条线不是可以随意砍掉的边缘功能，是"家庭与家庭的关系"这一顶层定位（`BUSINESS_ARCHITECTURE.md`第1.1节）在产品上的直接承载，只是当前证据不足以支撑现在投入，`MIGRATION_PLAN_V2.md`排在Batch 7，"排期靠后≠产品价值判断为低"。

---

## 3. FGCN资源协作流程

来源：V1.1第五、六章（V2战略第5节确认保留、不重写），本文件把设计内容整理为文字流程。

### 3.1 资源槽位模板 → 资源准入匹配 → 任务分派 → 贡献确认 → 收入分配（端到端流程）

```
step 1  产品设计台发布 ServiceBlueprintVersion（配置任务模板/资源槽位/SLA/访问范围/分配策略）
        └─ 已发布版本不可修改（"配置先于执行"）

step 2  家庭确认成长需要 → 创建 ServiceCase（冻结蓝图/授权/目标/分配策略快照）
        └─ 每个案件只有一个有效 ServiceSteward（一案一管家）

step 3  按资源槽位模板匹配候选资源：
        硬门槛（身份有效/ProviderProfile为ACTIVE/租户准入ADMITTED/年龄与专业范围匹配/
                能力键覆盖/当前可用）
        → 访问门槛（存在有效ServiceRelationship；读取案件需CaseAccessGrant）
        → 排序（家庭连续性→能力匹配→相似场景经验→交付可靠性→当前容量→时间费用适配）
        └─ 失败关闭：任何门槛不满足不得"先分派后补资料"

step 4  任务分派为 ServiceTask（PENDING→OFFERED→ACCEPTED→IN_PROGRESS→DELIVERED→VERIFIED）
        └─ 同一任务同一时刻只允许一个有效ACCEPTED责任人（一任务一责任人，TaskAssignment）

step 5  交付物通过验收 → 生成 ServiceContribution（绑定真实责任人、角色、任务）
        └─ 未VERIFIED任务不产生贡献

step 6  案件满足关闭条件 → finalizeShadowAllocation 按冻结策略运行一次
        （一个案件一次分配：案件总池100个"影子贡献单位"，不能每验收一个任务再复制100）
        └─ P0阶段不直接按金额结算，先验证规则是否公平/可执行/会否被操纵

step 7  回访和服务恢复完成 → 质量池从HELD转为RELEASED
        └─ 家庭回访结果决定案件动作：
           HELPFUL/SOMEWHAT_HELPFUL → 满足关闭条件即RELEASED
           NOT_HELPFUL_YET → 保留已验收基础贡献，创建返工任务，质量池HELD
           重大违规/应退款 → 转人工调查，质量池FROZEN

step 8  产生争议 → 先由运营复核事实凭证，再由独立质量负责人裁决
        → 所有人工改动必须记录原因/操作者/前后值/时间，不能删除历史行
```

### 3.2 分配池比例（21天/90天含人工服务的首个分配模板，V1.1第六章）

| 分配池 | 单位 | 贡献依据 | 释放状态 |
|---|---|---|---|
| PLATFORM | 20 | 获客、技术、支付、运营、客服、风控和服务保障 | 案件成立后确认，关闭时完成 |
| CONTENT_RESOURCE | 15 | 实际被案件使用的方案、内容、AI能力与工具版本 | 内容激活并留存使用凭证 |
| CASE_STEWARD | 15 | 建案、解释、协调、跟进、回访与恢复任务 | 管家任务VERIFIED |
| DELIVERY_RESOURCE | 40 | 教师、教练、顾问、专家等实际交付任务 | 按VERIFIED任务权重拆分 |
| QUALITY_RESERVE | 10 | 替换、返工、投诉恢复和闭环奖励 | 默认HELD，满足质量门后RELEASED |

**当前实现状态**：本流程在源仓库中是设计文档层面的完整规格（有明确对象状态机），未在AiFamily任何代码层落地。`MIGRATION_PLAN_V2.md`把SERVICE预约子链（3.4节里的一个薄切片：UI-19~24）列为Batch 2优先迁移，但完整的FGCN分配/贡献/争议流程（贝壳ACN机制映射的全部内容）目前没有独立的Batch，需在Batch 5-7涉及Resource/Organization域时一并处理（`MIGRATION_PLAN_V2.md`第4节Batch 7"沿用V1.1原文FGCN设计"）。

---

## 4. 功能组件清单

按六类闭环 + FGCN协作 + 独占区候选分组。"所属层"标注同质区/优势区/独占区候选（依据`BUSINESS_ARCHITECTURE.md`第6节三区方法论）；"对应Python domain"标注`governance/DOMAIN_REGISTRY.yaml`登记的canonical_path（若无对应登记则标注"未登记"）。

### 4.1 ASSESSMENT闭环

| 组件 | 所属层 | 当前完成度 | 对应Python domain |
|---|---|---|---|
| 测评会话（UI02_FAMILY_ASSESSMENT_V1） | 同质区（测评本身是通用能力） | `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV`，生产路径仍NestJS | `backend/domains/family`（family_core，REIMPLEMENT） |
| 假设解读（UI03_GROWTH_HYPOTHESIS_V1） | 独占区候选雏形（primary_contradiction排序落地点） | 同上，已验证但无`primary_contradiction`层判断 | 未登记独立domain，属于`family_core`范畴 |

### 4.2 PLAN闭环

| 组件 | 所属层 | 当前完成度 | 对应Python domain |
|---|---|---|---|
| 90天计划生成/阶段复盘（journey-plan） | 优势区（真人+AI协同） | phase-review已接线；pause无前端入口且客户端SDK缺失 | 未登记；`MIGRATION_PLAN_V2.md`归入Batch 4 GrowthIntent/GrowthPlan（REIMPLEMENT） |

### 4.3 GROWTH闭环（GATE_BOUNDARY）

| 组件 | 所属层 | 当前完成度 | 对应Python domain |
|---|---|---|---|
| 成长报告/榜单/海报/成果（UI-08/11/12/29） | 不适用三区分类——处于产品边界禁止状态 | 全部`GATE_BOUNDARY`，部分含硬编码假数据（UI-29的BADGES） | 不迁移不重建，待产品侧裁决存续 |

### 4.4 SERVICE闭环

| 组件 | 所属层 | 当前完成度 | 对应Python domain |
|---|---|---|---|
| Provider/ServiceOffering/AvailabilitySlot（名师专区/详情） | 优势区 | `BACKEND_READY` | 未登记；`MIGRATION_PLAN_V2.md`Batch 2（MIGRATE） |
| BookingRequest/BookingServiceRecord（预约/我的预约） | 优势区 | `E2E_READY`，但无取消入口 | 同上 |

### 4.5 COMMERCE闭环

| 组件 | 所属层 | 当前完成度 | 对应Python domain |
|---|---|---|---|
| 邀请有礼/拼团（CREATE_INVITE/CREATE_GROUP） | 同质区 | `E2E_READY` | 未登记；Batch 6 |
| 商城目录/商品详情 | 同质区 | `UI_READY_BACKEND_GAP` | 同上 |
| 积分商城 | 同质区（但含GATE_BOUNDARY约束） | `GATE_BOUNDARY`，硬编码1280兜底值需先清理 | 同上，前置条件见3.5节 |
| 商城意图服务（family-commerce-intent.service.ts） | 优势区（技术骨架比预想扎实） | DEV/TEST合成环境闭环，未接生产支付 | 未登记 |

### 4.6 COMMUNITY闭环

| 组件 | 所属层 | 当前完成度 | 对应Python domain |
|---|---|---|---|
| 发布动态（PUBLISH_TEMPLATE） | 独占区候选（"家庭与家庭的关系"定位承载者） | `E2E_READY` | 未登记；Batch 7（REIMPLEMENT） |
| 家长社区/动态详情/我的社区 | 同上 | `GATE_BOUNDARY`/`UI_READY_BACKEND_GAP` | 同上 |

### 4.7 FGCN协作组件

| 组件 | 所属层 | 当前完成度 | 对应Python domain |
|---|---|---|---|
| ServiceBlueprintVersion/ServiceCase/ServiceTask/TaskAssignment/ServiceContribution/AllocationStatement状态机 | 优势区（核心运行对象设计完整） | 设计文档层面完整，代码层面未落地（除SERVICE子链薄切片外） | 未登记独立domain，需在Batch 5-7涉及Resource/Organization时补建 |
| 资源准入匹配（硬门槛+排序） | 优势区 | 设计完整，代码未落地 | 同上 |
| 贡献确认/分配池释放 | 优势区 | 设计完整，代码未落地（P0阶段本就不接真实支付） | 同上 |

### 4.8 独占区候选组件（当前基本是空白，恰恰因此才最值得投入——V2战略8.2节原话）

| 组件 | 所属层 | 当前完成度 | 对应Python domain |
|---|---|---|---|
| Family Context（持续数年的成长数字上下文） | 独占区候选 | 空白——目前只有单会话内规则聚合，`FamilyMemoryDialogueRuntime`未接入任何调用方，embedding/pgvector完全不存在于代码 | 未登记，`AI_ARCHITECTURE.md`第3节展开 |
| Family Growth Graph（时间序列图谱） | 独占区候选 | 空白——`perspectives`/`evidence_records`表严格限定在单次onboarding内查询，从未跨会话检索 | 未登记 |
| Growth Intervention Engine（主要矛盾判断决策能力） | 独占区候选 | 雏形数据结构存在（`AssessmentInterpretationPort`已产出`hypotheses`/`action_candidates`），但无primary_contradiction层判断，无跨会话历史证据输入 | 未登记，`AI_ARCHITECTURE.md`第4节展开 |
| Service Blueprint Library（谋略库） | 独占区候选 | `ServiceBlueprintVersion`发布后冻结版本的设计已存在，但目前装的是课程内容，还不是"针对某类家庭主要矛盾的标准化谋略" | 未登记 |

---

## 5. 待人类裁决事项（本文件范围内识别，不做技术性代答）

1. GROWTH闭环（UI-08/11/12/29）的最终去向——下线还是等产品设计补齐依据后重新打开——直接影响`MIGRATION_PLAN_V2.md`Batch 8的NestJS删除范围，本文件与该迁移计划一样，无法自行裁决（见`MIGRATION_PLAN_V2.md`第8节）。
2. `dev-platform-surfaces.service.ts`/`dev-core-growth.service.ts`（自述`SYNTHETIC_DEV_ONLY`但被9+个真实移动端屏幕消费）的下线方案——需要产品侧先确认这些屏幕（UI-10/11/12/22/23/25/27/28/29）的数据来源替代方案，不是可以直接删的死代码。
