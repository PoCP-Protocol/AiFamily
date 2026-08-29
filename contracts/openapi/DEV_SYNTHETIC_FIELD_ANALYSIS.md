---
id: CONTRACT-DEVSYNTH-001
title: /dev/* 合成路由字段级拆解 —— 真需求 vs 假需求
type: contract
status: current
version: 1.0
owner: project-owner
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
scope: T-04b（仅 /dev/* 字段分析；端点总清单见 UI_API_ENDPOINT_INVENTORY.md）
---

# /dev/* 合成路由字段级拆解

## 0. 结论摘要

源仓库两个服务 `dev-core-growth.service.ts`（534 行）与 `dev-platform-surfaces.service.ts`（202 行）自述
`data_source: 'SYNTHETIC_DEV_ONLY'`、`model_gateway: 'NOOP_NOT_INVOKED'`、`external_effect_adapter: 'NOOP_NOT_INVOKED'`，
零 DB 读写。但它们被 AiFamily 前端 9 个屏幕消费。

**最关键发现：前端实际消费面远小于服务产出面。**
证据在 `D:\AiFamily\frontend\mobile\lib\family\family-api-projections.ts` —— 该文件为两个投影手写了
**窄化 TypeScript 接口**，只声明前端真正读的字段：
- `FamilyApiCoreGrowthProjection`（第 11–23 行）只声明 4 个顶层字段 + `cards[].surface` + `cards[].child_action_prompt`。
  服务实际产出的 `family_growth_os_path`、`loop`、`business_capability`、`primary_objects`、`state_boundary`、
  `report_draft`、`plan_preview`、`companion_progress`、`action_review`、`growth_profile_progress`、
  以及 8 张卡的 `title`/`summary`/`next_hint`/`fact_boundary`/`command` **全部未被前端类型声明，即未被消费**。
- `FamilyApiPlatformSurfacesProjection`（第 74–87 行）只声明 5 个顶层字段 + `cards[].surface` + 4 个嵌套块。
  24 张卡片中**只有 5 张（UI-11 / UI-12 / UI-22 / UI-25，UI-17 的 `family_self_record` 也未被声明）**的嵌套块进入类型；
  24 张卡的 `domain`/`title`/`state`/`boundary`/`summary`/`next_hint`/`command` 元组字面量**一个都没被消费**。

也就是说：`AI_NATIVE_PRINCIPLES.md` 第 96 行点名批评的"24 张硬编码卡片 + `GROWTH_FOCUS_CONTENT` 文案字典"
——**这批文案本体在 AiFamily 前端里是死负载**。Python 后端不需要移植它们。

---

## 1. 两个合成服务的返回体字段结构

### 1.1 `/families/{familyId}/dev/core-growth` → `DevCoreGrowthProjection`

来源：`D:\family-ai\50_开发_dev\apps\api\src\modules\family\dev-core-growth.service.ts` 第 25–72 行（`getProjection`）。

| 字段 | 行号 | 性质 |
|---|---|---|
| `projection_version: 'DEV_CORE_GROWTH_V1'` | L44 | 字面量常量 |
| `family_id` | L45 | 入参回显 |
| `generated_at` | L46 | `new Date().toISOString()` |
| `data_source: 'SYNTHETIC_DEV_ONLY'` | L47 | **自我标注**：声明自身是合成数据 |
| `family_growth_os_path[7]` | L48–56 | 硬编码 7 元素字符串数组（GrowthOnboarding→…→GrowthReview） |
| `model_gateway.status: 'NOOP_NOT_INVOKED'` | L57–60 | **自我标注**：模型未被调用 |
| `model_gateway.rule` | L59 | 硬编码规则字符串 |
| `cards[]`（8 张：UI-02…UI-08, UI-10） | L61–70, L311–374 | 硬编码卡片字面量 + 架构绑定 merge |

每张卡（`private cards()`，L298–375）字段：
`surface` / `kind` / `title` / `state` / `fact_boundary` / `data_source` / `summary` / `next_hint` /
`command{name,mode}`，另加 L62–68 从 `getLegacyFamilyGrowthSurfaceArchitectureBinding()` merge 进来的
`loop` / `business_capability` / `primary_objects` / `state_boundary`。

条件挂载的嵌套块（**全部由入参 `flowEvents` 决定是否出现**，L305–310）：

| 嵌套块 | 挂在哪张卡 | 出现条件 | 构造函数 |
|---|---|---|---|
| `report_draft` | UI-04 (L332) | 总是 | `buildReportDraft` L435–451 |
| `plan_preview` | UI-05 (L340) | 总是 | `buildPlanPreview` L507–534 |
| `companion_progress` | UI-06 (L348) | `flowEvents` 含 UI-09 `OPEN_SYNTHETIC_FAMILY_ACTION_REVIEW` | `buildFamilyCompanionProgress` L479–491 |
| `growth_profile_progress` | UI-07 (L356) | `flowEvents` 含 UI-02 `SELECT_SYNTHETIC_ASSESSMENT_DIMENSION` | `buildGrowthProfileProgress` L453–464 |
| `action_review` | UI-08 (L364) | 同 companion_progress | `buildFamilyActionReview` L493–505 |
| `child_action_prompt` | UI-10 (L372) | 同 companion_progress | `buildChildActionPrompt` L466–477 |

**硬编码文案字典**：`GROWTH_FOCUS_CONTENT`，L378–426。5 个 focus 键
（`PARENT_CHILD_COMMUNICATION` / `LEARNING_HABITS` / `EMOTION_REGULATION` / `SELF_REGULATION` / `DEVICE_USE_CONTEXT`），
每键 6 个字段（`reportHeadline` / `reportSummary` / `observations[3]` / `action` / `fallback` / `planHeadline`），
全部是写死的中文句子。`selectedFocus()`（L428–433）只从 `flowEvents` 里挑一个 key，**无任何推理**。
`buildPlanPreview` 的 4 个阶段（SEE/ADJUST/CO_CREATE/STABILIZE，L518–523）同为硬编码字面量。

**注**：该 service 还有 5 个方法 `getReportExplanation`(L74) / `getPlanPreview`(L111) / `getServiceJourneyProjection`(L143) /
`getGrowthProfileReadback`(L196) / `getFamilyReviewReadback`(L225) 与 `acknowledgeNoop`(L283)。
这些**不由 `/dev/core-growth` 路由暴露**，走 UI-04/05/06/07/08 各自的专属路由（属 T-04a 范围）。
它们全部内部调用 `this.getProjection()` 取合成文案，因此合成污染面比单个端点更大——本文件仅登记事实，不展开。

### 1.2 `/families/{familyId}/dev/platform-surfaces` → `DevPlatformSurfacesProjection`

来源：`D:\family-ai\50_开发_dev\apps\api\src\modules\family\dev-platform-surfaces.service.ts` 第 26–46 行。

| 字段 | 行号 | 性质 |
|---|---|---|
| `projection_version: 'DEV_PLATFORM_SURFACES_V1'` | L28 | 字面量常量 |
| `family_id` | L29 | 入参回显 |
| `generated_at` | L30 | 当前时间 |
| `data_source: 'SYNTHETIC_DEV_ONLY'` | L31 | **自我标注** |
| `external_effect_adapter: 'NOOP_NOT_INVOKED'` | L32 | **自我标注**：不发通知/支付/分享/预约 |
| `model_gateway: 'NOOP_NOT_INVOKED'` | L33 | **自我标注** |
| `cards[24]`（UI-11…UI-34） | L34–44, L64–95 | **24 个数组字面量元组** |

**24 张硬编码卡片**：L64–87，每行是一个 9 元素元组
`[surface, domain, title, state, boundary, summary, next_hint, command, mode]`，
L88–89 解构成对象，L38–42 再 merge `data_source` + `getLegacyFamilyUiArchitectureBinding()` 的
`loop`/`business_capability`/`primary_objects`/`state_boundary`。

5 个嵌套块（L90–94）：

| 嵌套块 | 卡 | 构造函数 | 数据来源 |
|---|---|---|---|
| `personal_growth_journey` | UI-11 | `buildPersonalGrowthJourney` L139–159 | **纯 flowEvents 回声**：把事件 ui_id 映射到 4 条硬编码 label/detail（L140–145），取最近 4 条 |
| `private_growth_story` | UI-12 | `buildPrivateGrowthStory` L178–202 | **纯 flowEvents 回声**：`switch(ui_id)` 返回 4 句硬编码中文（L184–190） |
| `family_self_record` | UI-17 | `buildFamilySelfRecord` L161–176 | flowEvents 布尔判定（L162）→ 二选一硬编码文案 |
| `family_growth_activity_catalog` | UI-22 | `buildFamilyGrowthActivityCatalog` L99–111 | **零入参**，2 条完全写死的活动 fixture（L105–106） |
| `family_learning_exchange_feed` | UI-25 | `buildFamilyLearningExchangeFeed` L113–137 | **零入参**，2 条完全写死的"其他家庭经验"（L119–132） |

---

## 2. 九屏幕 × 消费字段矩阵

| 屏幕 | 文件（`D:\AiFamily\frontend\mobile\app\ui\`） | 调用端点 | 实际读取的字段（含行号） |
|---|---|---|---|
| UI-10 | `UI-10.tsx` L30 | `/dev/core-growth` | `cards[surface=UI-10].child_action_prompt.headline`、`.shared_action`（L38，经 `selectChildActionPrompt` projections L305）。**其余全部不读**，且无 prompt 时回落本地 `getChildPrompt()` |
| UI-11 | `UI-11.tsx` L25 | `/dev/platform-surfaces` | `cards[UI-11].personal_growth_journey.entries[].event_id/label/detail`（L31，取最后 3 条）。`state`/`headline`/`plan_route`/`review_route`/`fact_boundary` **未读** |
| UI-12 | `UI-12.tsx` L24 | `/dev/platform-surfaces` | `cards[UI-12].private_growth_story.title`、`.summary`、`.moments`（L31、L48）。`state`/`journey_route`/`fact_boundary` 未读；无远端时回落 `buildPrivateGrowthStory(localEvents,…)` |
| UI-22 | `UI-22.tsx` L28 | `/dev/platform-surfaces` | `cards[UI-22].family_growth_activity_catalog.activities[].activity_ref/title/summary/age_hint`（L34–37）。`headline`/`introduction`/`support_topics_route`/`fact_boundary` **未读**。`theme`/`scheduleLabel`/`locationLabel`/`highlights`/`agenda`/`accent` 由前端 `service-support.ts` L171–189 本地补齐 |
| UI-23 | `UI-23.tsx` L29 | `/dev/platform-surfaces` + POST `/dev/flow-events`（L46） | 同一个 catalog（L35–36）里按 `activityRef` 找一条；渲染 `title`/`summary`/`theme`/`ageHint`（L67、L76）。POST 只写 `ui_id`/`command`/`selection` |
| UI-25 | `UI-25.tsx` L34 | `/dev/platform-surfaces` | `cards[UI-25].family_learning_exchange_feed.entries[].title/summary/topic`（L40–48、L79）。`headline`/`introduction`/`activity_catalog_route`/`fact_boundary`/`state` 未读；频道过滤靠**前端硬编码 topic 字符串比对**（L45） |
| UI-27 | `UI-27.tsx` L28 | `/dev/platform-surfaces` | 同 feed，`entries[].exchange_ref/title/summary/topic`（L34、L37–40、L72）。有前端硬编码 fallback 文案（L37–38） |
| UI-28 | `UI-28.tsx` L28 | `/dev/platform-surfaces` | 同 feed 的 `entries[]`，仅作为**本地收藏草稿的标题解析表**（L34–35）。四个统计数字（L47）全部来自本地 `communityInteractionDrafts`，与后端无关 |
| UI-29 | `UI-29.tsx` L35–36 | `/dev/core-growth` **和** `/dev/platform-surfaces` | `platform.cards[UI-11].personal_growth_journey.entries[]`（L27、L30）+ `core.model_gateway.status`（L59，仅用来切换一句提示文案）。**core 端点的其他一切均未读** |

**回落行为共性**：9 个屏幕全部把远端投影当"可选增强"（`?? local` / `catch(console.error)`）。
远端 404 时**没有一个会白屏**——都有本地 fixture 兜底。这直接决定了实现优先级。

---

## 3. 逐字段判定表

只列**被实际消费**的字段。判定依据：R9（`governance/REPOSITORY_CONSTITUTION.md` L68、L76、L84）、
`docs/05_ai/AI_NATIVE_PRINCIPLES.md` 第 4 节（L92–100）、CLAUDE.md L65（合成数据不得挂生产路由）。

### 3.1 `/dev/core-growth`

| # | 字段 | 消费方 | 判定 | 理由 |
|---|---|---|---|---|
| 1 | `child_action_prompt.headline` | UI-10 L38 | `FRONTEND_COPY` | 值恒为字面量 `'和孩子一起选一件小事'`（源 L471），与 family_id、DB、focus 无关。纯标题。 |
| 2 | `child_action_prompt.shared_action` | UI-10 L38 | `REAL_DATA`（改造后） | 当前是 `GROWTH_FOCUS_CONTENT[focus].action` 模板拼接（源 L472）。**语义上是真需求**：它是"本周家庭行动建议"，应来自真实 GrowthAction / Recommendation（R9：`status=DRAFT`，非 Fact）。但**不得照抄 5 条硬编码文案**——那正是 AI_NATIVE_PRINCIPLES L96 点名的反模式。 |
| 3 | `child_action_prompt.pause_hint` | 未读 | — | 前端类型 projections L6 声明了但屏幕未渲染 → 不实现 |
| 4 | `child_action_prompt.state`/`focus`/`action_route`/`fact_boundary` | 未读 | `FRONTEND_COPY` / 删除 | `action_route` 是硬编码路由名，属前端路由表职责，后端不该发路由字符串 |
| 5 | `model_gateway.status` | UI-29 L59 | `DERIVED` | UI-29 只用它二选一切换提示语。真实系统里"是否调用了模型"应由 AI 用例的 provenance/`recommendation_source` 承载，不需要一个顶层布尔。前端可直接固定文案，或读 Recommendation 的 `source` 字段。 |
| 6 | `data_source`/`projection_version`/`family_id`/`generated_at` | 未读（类型声明了 L12–14） | `REVIEW_REQUIRED` → 建议保留 `family_id` + `as_of` | `data_source: 'SYNTHETIC_DEV_ONLY'` **必须不在新后端出现**——新端点若返回该值即违反 CLAUDE.md L65 |
| 7 | `family_growth_os_path` | 未读 | 删除 | 7 个阶段名的静态数组，属文档/前端常量，非运行时数据 |
| 8 | 8 张卡的 `title`/`summary`/`next_hint`/`kind`/`state`/`command` | **零消费** | `FRONTEND_COPY` | AiFamily 前端类型（projections L19–22）根本没声明这些字段。这就是 `GROWTH_FOCUS_CONTENT` 死负载的证据 |
| 9 | `loop`/`business_capability`/`primary_objects`/`state_boundary` | 零消费 | 删除（属治理元数据） | 应存在于 `governance/DOMAIN_REGISTRY.yaml`，不该走 HTTP 响应 |
| 10 | `report_draft` / `plan_preview` / `companion_progress` / `action_review` / `growth_profile_progress` | 零消费（经 `/dev/core-growth`） | 见 §5 | 这些语义（成长报告、90 天计划、行动回顾）是**真业务对象**，但应由 Growth 域自己的端点提供，不该挂在一个 dev 聚合投影上 |

### 3.2 `/dev/platform-surfaces`

| # | 字段 | 消费方 | 判定 | 理由 |
|---|---|---|---|---|
| 11 | `personal_growth_journey.entries[].event_id` | UI-11 L31, UI-29 L30 | `REAL_DATA` | 家庭真实做过的动作的事件主键。必须来自真实事件流（`flow_events` 或 Growth 域事件表），是 provenance 锚点 |
| 12 | `personal_growth_journey.entries[].label` / `.detail` | UI-11 L31, UI-29 L30 | `FRONTEND_COPY` | 源 L140–145 是 `ui_id → 固定中文` 的静态查找表。事件类型是数据，**它的人类可读描述是前端 i18n**。后端只该发事件 `kind` 枚举 |
| 13 | `personal_growth_journey.state` / `.headline` | 未读 | `DERIVED` / `FRONTEND_COPY` | `state` 由 `entries.length>0` 派生（源 L152）；`headline` 是二选一硬编码文案（L153） |
| 14 | `personal_growth_journey.fact_boundary` | 未读 | 删除 | `'PROCESS_EVENTS_NOT_OUTCOME_OR_RANKING'` 是自我标注护栏字符串，屏幕上的边界提示（UI-11 已在 L74 区自带）由前端写 |
| 15 | `private_growth_story.title` | UI-12 L31/L48 | `FRONTEND_COPY` | 二选一硬编码（源 L194） |
| 16 | `private_growth_story.summary` | UI-12 L31 | `FRONTEND_COPY` | 二选一硬编码（源 L195–197） |
| 17 | `private_growth_story.moments[]` | UI-12 L31 | `FRONTEND_COPY`（结构 `DERIVED`） | 源 L184–190 `switch(ui_id)` 返回 4 句写死中文。**内容是文案**；"家庭做过哪几步"是 #11 同一份真实事件流的另一种渲染 → 不需要独立端点 |
| 18 | `private_growth_story.journey_route: 'growth-ranking'` | 未读 | `R9_BLOCKED`（命名层面） | 路由字面量叫 **`growth-ranking`**（源 L199）。R9（宪章 L84）明令不做家庭排行；同 registry 已把 `legacy_profile.ranking` 判 `RETIRE`（L76）。即使当前内容不是排行榜，**这个名字不得迁入 AiFamily**，需产品侧改名 |
| 19 | `family_growth_activity_catalog.activities[].activity_ref` | UI-22 L34–37, UI-23 L36 | `REAL_DATA` | 活动的稳定标识，UI-23 靠它做路由参数查找。必须来自真实活动目录表 |
| 20 | `…activities[].title` / `.summary` / `.age_hint` | UI-22 L73, UI-23 L67/L76 | `REAL_DATA` | 活动名称/简介/适龄参考是**运营录入的真实业务内容**，不是 UI 文案。必须来自 DB（活动目录域），当前 2 条 fixture（源 L105–106）是假数据 |
| 21 | `…activities[].detail_route` | 未读 | 删除 | 后端不发前端路由名 |
| 22 | `activity_catalog.headline`/`introduction`/`support_topics_route`/`state`/`fact_boundary` | 未读 | `FRONTEND_COPY` / 删除 | 全部零消费的静态文案（源 L102–103、L108–109） |
| 23 | `family_learning_exchange_feed.entries[].exchange_ref` | UI-27 L34/L40, UI-28 L35 | `REAL_DATA` | 社区内容主键，UI-27 路由参数、UI-28 收藏草稿的外键。必须真实 |
| 24 | `…entries[].title` / `.summary` | UI-25 L79, UI-27 L60–61, UI-28 L51 | `REAL_DATA` | 这是**其他家庭的经验分享内容**，是真实用户生成内容（需过审核/可见性）。当前 2 条 fixture（源 L119–132）是编造的"有家长会…"，属虚构他人言论——上线前必须换真数据或明确标记为平台示例 |
| 25 | `…entries[].topic` | UI-25 L45（频道过滤）, UI-27 L72, UI-28 L51 | `REAL_DATA` | 被当分类键用。注意 UI-25 L45 把 `topic` 与前端硬编码字符串 `'亲子沟通'`/`'家庭阅读'`/`'同城活动'` 比对——这是**契约耦合缺陷**，应改为枚举 |
| 26 | `…entries[].detail_route` | 未读 | 删除 | 同 #21 |
| 27 | `feed.headline`/`introduction`/`state`/`fact_boundary`/`activity_catalog_route` | 未读 | `FRONTEND_COPY` / 删除 | 零消费静态文案（源 L115–116、L134–135） |
| 28 | `family_self_record.*`（UI-17） | **零消费** | 不实现 | AiFamily 的 projections 类型（L80–86）未声明；且 UI-17 走 membership `dev_points`（AI_NATIVE_PRINCIPLES L99 已点名 `?? 1280` 硬编码兜底） |
| 29 | 24 张卡的 `title`/`domain`/`state`/`boundary`/`summary`/`next_hint`/`command` | **零消费** | `FRONTEND_COPY` | 源 L64–87 的 24 个元组。AiFamily 前端一个字段都没读 → **整块不迁移** |
| 30 | `data_source`/`external_effect_adapter`/`model_gateway`（顶层，platform） | 零消费 | 删除 | 自我标注字段；新后端返回 `SYNTHETIC_DEV_ONLY` 即违反 CLAUDE.md L65 |
| 31 | `cards[].surface` | 全部 9 屏（经 projections L305–321 的 `find`） | `REVIEW_REQUIRED` → 建议废弃 | 它只是"从大袋子里找我那一格"的索引键。按域拆端点后不再需要（见 §4） |

### 3.3 POST `/dev/flow-events`（附带，因 UI-23 调用）

| # | 字段 | 消费方 | 判定 | 理由 |
|---|---|---|---|---|
| 32 | 请求体 `ui_id` / `command` / `selection` | UI-15 L35, UI-16 L30, UI-23 L46, UI-26 L47 | `REAL_DATA` | 这是**唯一真正写入的东西**，且是 #11/#23 读回的数据源。是真需求：家庭意向草稿/交互事件流。但字段设计有问题：`ui_id` 把**界面编号当业务语义**，新后端应改为域事件（如 `ActivityInterestDraftSaved`），不要以屏幕 ID 为主键维度 |

### 3.4 判定统计

| 判定 | 条目数 | 条目号 |
|---|---|---|
| `REAL_DATA` | 8 | #2(改造后)、#11、#19、#20、#23、#24、#25、#32 |
| `FRONTEND_COPY` | 10 | #1、#4、#8、#12、#15、#16、#17、#22(部分)、#27(部分)、#29 |
| `DERIVED` | 3 | #5、#13、#17(结构) |
| `R9_BLOCKED` | 1 | #18 |
| `REVIEW_REQUIRED` | 2 | #6、#31 |
| 直接删除（治理元数据/路由名/自我标注） | 7 | #3、#7、#9、#14、#21、#26、#30 |

> `#17` 同时计入 `FRONTEND_COPY`（内容）与 `DERIVED`（结构），故合计大于唯一字段数。
> `#10` 未计入统计（零消费的真业务对象，处置见 §5）。

---

## 4. 后端实现建议

**建议形态：不实现这两个端点，改为「大部分字段前端化 + 三个按域的小端点 + 一个事件写入端点」。**

理由：§2 已证明前端消费面只有 8 个 `REAL_DATA` 字段，且分属三个互不相干的域（成长事件流 / 活动目录 / 社区内容）。
把它们塞进一个自述 SYNTHETIC 的聚合投影，是源仓库为"让 24 个静态页看起来连在一个 OS 上"（源服务 L22 注释自述）
而做的**演示脚手架**，不是业务边界。照搬会：
- 违反 CLAUDE.md L65（合成数据不得挂生产路由）与 R5；
- 违反 R2（一个 capability 一个 canonical_path）——一个端点横跨 Growth / Activity / Community 三域；
- 把 `AI_NATIVE_PRINCIPLES.md` L96 明确否定的硬编码文案字典固化进新架构。

### 4.1 目标端点（各需在 `governance/DOMAIN_REGISTRY.yaml` 登记后再实现）

| 新端点 | 取代 | 返回（仅 REAL_DATA） | 服务屏幕 |
|---|---|---|---|
| `GET /families/{id}/growth/timeline` | `personal_growth_journey` + `private_growth_story` | `entries[]: {event_id, kind(枚举), occurred_at}` | UI-11、UI-12、UI-29 |
| `GET /activities` | `family_growth_activity_catalog` | `activities[]: {activity_ref, title, summary, age_hint}` | UI-22、UI-23 |
| `GET /community/exchanges` | `family_learning_exchange_feed` | `entries[]: {exchange_ref, title, summary, topic(枚举), visibility, moderation_state}` | UI-25、UI-27、UI-28 |
| `POST /families/{id}/interaction-events`（改名自 `/dev/flow-events`） | 同名 | 域事件语义，非 `ui_id` | UI-15/16/23/26 写入 |
| UI-10 的 `shared_action` | `child_action_prompt` | 归入 Growth 域 Recommendation 端点（`status=DRAFT`，R9 闸门） | UI-10 |

`kind` / `topic` 必须是后端枚举，人类可读文案（`label` / `detail` / `headline` / `title` 等 §3 判为 `FRONTEND_COPY` 的）
放前端 i18n。这解掉 §3 #25 记录的 UI-25 L45 硬编码字符串比对缺陷。

### 4.2 不该实现的

- 任何返回 `data_source: 'SYNTHETIC_DEV_ONLY'` / `model_gateway: 'NOOP_NOT_INVOKED'` / `external_effect_adapter` 的字段（#30）；
- 24 张卡片元组、`GROWTH_FOCUS_CONTENT` 5×6 文案字典、4 个计划阶段字面量（#8、#29）；
- `loop` / `business_capability` / `primary_objects` / `state_boundary`（#9，属 registry 不属 HTTP）；
- 一切 `*_route` 路由名字段（#4、#21、#26）；
- `growth-ranking` 路由名（#18，见 §5）。

### 4.3 九屏幕影响评估

前提（§2 末已核实）：9 个屏幕全部对远端投影做 `?? local` / `.catch()` 兜底，**移除 `/dev/*` 后没有一个白屏**。

| 屏幕 | 建议实施后状态 | 说明 |
|---|---|---|
| UI-10 | **部分降级** | `child_action_prompt` 直到 Growth Recommendation 端点就绪前，落回本地 `getChildPrompt()`（UI-10 L38 已有此分支）。功能可用，行动建议非个性化 |
| UI-11 | **正常工作** | 只需 `growth/timeline` 的 `entries[]`；label/detail 前端 i18n |
| UI-12 | **正常工作** | 与 UI-11 同一事件流，只是另一种渲染；已有 `buildPrivateGrowthStory(localEvents)` 兜底 |
| UI-22 | **正常工作**（需 DB 数据） | 端点结构一致；但需运营录入真实活动，否则空列表（UI-22 L93 已有 empty state） |
| UI-23 | **正常工作**（需 DB 数据） | 同上；`theme`/`scheduleLabel` 等本来就由前端 `service-support.ts` L180–186 补齐 |
| UI-25 | **正常工作**（需 DB 数据 + `topic` 改枚举） | 频道过滤逻辑（L45）必须同步改，否则枚举化后过滤失效 |
| UI-27 | **正常工作** | 已有硬编码 fallback（L37–38），建议改为 empty state |
| UI-28 | **正常工作** | 后端只提供收藏草稿的标题解析表；四个统计数字本就来自本地（L47） |
| UI-29 | **需产品重新设计** | 见 §5。当前 hero 区（L48–50）展示三个数字 + `ring` 环形指标，标题「成长成果」。`model_gateway.status`（L59）在新架构无对应字段 |

---

## 5. 需产品侧裁决的清单

### R9-01 — `journey_route: 'growth-ranking'`（判定 #18）
- 位置：`dev-platform-surfaces.service.ts` L199。
- 冲突：宪章 L84「AiFamily 不计算、不存储、不暴露家庭总分与家庭排行」；L76 已把 `legacy_profile.ranking` 判 `RETIRE`。
  UI-11 卡片自述「DEV 用个人历史轨迹替代跨家庭排行」（源 L64）——即源仓库**自己也知道**这是排行榜的遗留壳。
- 裁决请求：确认 `growth-ranking` 路由名及其屏幕在 AiFamily 中改名（建议 `growth-timeline`），并确认前端路由文件是否同步改名（本任务禁止改前端代码，未执行）。

### R9-02 — UI-29「成长成果」屏幕定位（影响评估已列"需重新设计"）
- 位置：`D:\AiFamily\frontend\mobile\app\ui\UI-29.tsx` L44（标题「成长成果」）、L48–50（三个数字 + 环形指标）、
  源服务 L82 该卡 `boundary: 'OBSERVATION_IS_NOT_FACT_OR_CAUSAL_EFFECT'`。
- 冲突风险：屏幕名与三数字指标+环形进度的组合，视觉上是"成果证明/评分"。R9 禁止 AI 输出自动成为事实，
  宪章 L84 禁止家庭总分。当前实现虽在 L52 加了免责文案，但**指标本身仍是"成果"呈现**。
- 裁决请求：明确 UI-29 是「已留下的过程片段回看」还是「成长成果证明」。若前者，标题与三指标需重设计；
  若后者，需产品侧书面承担 R9 风险并说明为何不构成家庭评分。

### R9-03 — `family_learning_exchange_feed` 的虚构他人言论（判定 #24）
- 位置：源服务 L119–132，写死"有家长会在情绪上来时先停一停"、"有家庭从一小段喜欢的故事开始"。
- 问题：这不是文案，是**冒充真实用户的经验分享**，会被家长读作"别人家真的这么做"。属虚假内容而非合成 fixture 标注问题。
- 裁决请求：真实社区内容就绪前，UI-25/27/28 是走空状态，还是展示**明确标注为平台编辑内容**的示例条目。

### 待确认 — UI-10 行动建议的来源（判定 #2）
- `shared_action` 语义上是真需求，但 R9 要求它作为 `Recommendation`/`status=DRAFT` 存在，
  且 `AI_NATIVE_PRINCIPLES.md` 判据 3（L47）要求生成式而非硬编码文案字典。
- 裁决请求：确认在 Growth Recommendation 能力就绪前，UI-10 接受本地兜底降级（不显示个性化建议），
  而非移植 `GROWTH_FOCUS_CONTENT` 的 5 条硬编码 action。

---

## 6. 本文件的边界

- 端点总清单、HTTP 方法、认证要求 → 见 `contracts/openapi/UI_API_ENDPOINT_INVENTORY.md`（T-04a）。
- UI 本地状态与远端字段的交叉核对 → T-04c。
- 本文件不修改任何前端代码、不修改源仓库。§4 的端点建议**尚未登记进 `governance/DOMAIN_REGISTRY.yaml`**，
  实现前需按 CLAUDE.md 铁律 3 补登记行；`growth/timeline` 等命名需 ADR 或 owner 确认后固化。
- `dev-core-growth.service.ts` 的 5 个非 `/dev/core-growth` 方法（§1.1 末注）合成污染面更大，未在本任务范围内展开。
