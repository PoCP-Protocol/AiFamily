# Family / 伐木累 34 页 UI 前后端一致性矩阵

> **用途：** 本矩阵是继续开发的逐页基线，不把“原图可渲染”误认为“前后端业务已完成”。页面显示名使用 Family / 伐木累；`bangyang-reference`、历史 source_file 与 asset id 保持原样，仅作为原素材可追溯路径。所有 DEV/TEST 写入只使用固定 fixture、family_test PostgreSQL、测试账户和零外部副作用适配器。

## 状态定义

| 状态 | 含义 |
|---|---|
| `E2E_READY` | UI 热点、服务端 API/DTO、数据库状态、Named Action、集成测试和安全回执均已贯通。 |
| `READ_ONLY_READY` | 页面有真实只读数据或固定投影契约；不允许把静态原图当作业务写入完成。 |
| `UI_READY_BACKEND_GAP` | 原图和路由已完成，但仍需正式 API/DTO/数据库或页面状态接入。 |
| `GATE_BOUNDARY` | 当前 UI 只能保留受控只读/说明路径；涉及跨家庭排名、真实支付、真实外发、诊断或高风险服务时，不得自行实现为业务能力。 |

## 逐页矩阵

| UI | Route | 页面/闭环 | 当前前端能力 | 后端契约与数据状态 | Named Action / LLM | 测试现状 | 状态 | 下一步 |
|---|---|---|---|---|---|---|---|---|
| UI-01 | `home` | 家庭首页 | 原图首页、导航与入口 | `GET /families/:familyId/ui/01/home`；可信 Tenant/Family、今日行动、旅程、准入供给 | 首页读不调用模型；求助必须显式走 `RequestGrowthHelp` | API 单元/E2E、App/Web 与视觉热点已测 | `COMMERCIAL_READ_SLICE_READY` | 补生产提醒、跨端求助输入和运营 SLO 后再进入生产 Gate |
| UI-02 | `growth-assessment` | 家庭支持需要确认 | 原图第2/5步与版本/边界/孩子选择 | `UI02_FAMILY_ASSESSMENT_V1`；版本化Tool/Session/Response/Evidence | `START_ASSESSMENT` / `SAVE_ASSESSMENT_RESPONSE` / `SUBMIT_ASSESSMENT`；不评分不诊断 | ASSESSMENT同意、幂等、修订历史、提交不可变、跨端契约与PostgreSQL E2E | `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV` | UI-03接入提交Evidence并形成Hypothesis/家庭确认 |
| UI-03 | `core-report` | 成长解读假设与家庭确认 | 原图报告结构、来源、局限、确认/暂不形成方向 | `UI03_GROWTH_HYPOTHESIS_V1`；Assessment/Evidence/NeedType来源链 | `CONFIRM_GROWTH_HYPOTHESIS` / `DISMISS_GROWTH_HYPOTHESIS` | Hypothesis非事实非诊断、AI未调用、同意复验、确认后才成GrowthIntent、NO_ACTION、幂等/Audit/Outbox/E2E | `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV` | UI-04以已确认Intent生成私有报告/方案，不把Hypothesis写成结果 |
| UI-04 | `core-report` | 家庭成长说明 | 原图清晰报告母版 | 当前仅 LLM draft/说明；无报告事实 DTO | Gateway 输出验证；不得生成诊断 | LLM 阻断已测 | `UI_READY_BACKEND_GAP` | 建立只读报告投影与来源字段 |
| UI-05 | `core-plan` | 90 日成长方案 | 原图计划与开始入口 | 尚无正式计划投影/任务状态 DTO | Named Action 需独立登记；模型不能自动建计划 | 路由已测 | `UI_READY_BACKEND_GAP` | 接入家庭明确 Decision 后的计划投影 |
| UI-06 | `core-community` | 陪跑服务/社群 | 原图服务卡与打卡入口 | 可关联服务记录/活动投影；尚无专属读 DTO | 仅受控说明；不得真实外发 | 路由已测 | `UI_READY_BACKEND_GAP` | 建立服务旅程只读 DTO |
| UI-07 | `core-mine` | 我的会员中心 | 原图会员与权益视觉 | 当前无正式会员/权益读模型接入 | 不得接真实支付/权益 | 路由已测 | `GATE_BOUNDARY` | 先建立沙箱资产投影；生产权益另行 Gate |
| UI-08 | `growth-report` | 成长报告 | 原图报告视觉 | 无独立报告 DTO；不能把静态分值视为事实 | 禁止成长评分/诊断/永久标签 | 路由已测 | `GATE_BOUNDARY` | 改为支持记录/家庭表达投影并移除事实性分数 |
| UI-09 | `growth-daily-task` | 今日任务 | 原图蓝色提醒、三项编号视觉、真实任务状态与反思/暂停/取消操作 | `UI01_UI09_FAMILY_TODAY_V1`；GrowthAction持久化生命周期；`/tasks/:taskId/state`与`/check-in` | 家庭动作授权；开始/暂停/继续/取消/完成均幂等并写Audit/Outbox；AI不调用 | API单元、真实PostgreSQL状态机与重启回读、App/Web契约与Web交互已测 | `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV` | 接生产任务模板运营、提醒SLO与可观测性后进入生产 Gate |
| UI-10 | `growth-child` | 孩子侧成长助手 | 原图孩子页 | 无儿童直接作答/成长结果写入契约 | 儿童直接作答继续 HOLD | 路由已测 | `GATE_BOUNDARY` | 仅保留家庭监护人只读投影与文本等价 |
| UI-11 | `growth-ranking` | 成长榜单 | 原图榜单视觉 | 不得接跨家庭排名、比较或家庭画像 | 永久禁止跨家庭统计/排序 | 路由已测 | `GATE_BOUNDARY` | 只保留个人旅程/家庭自有记录，不实现榜单事实 |
| UI-12 | `growth-poster` | 成长成果海报 | 原图海报与分享热点 | 无成果事实 DTO；不得生成效果证明 | 不得公开分享或成长结果断言 | 路由已测 | `GATE_BOUNDARY` | 先接家庭私有记录投影；分享保持关闭 |
| UI-13 | `commerce-mall` | 家庭成长商城 | 原图商品目录 | 尚无正式 catalog DTO；客户端不得传价格 | 只读候选/商品 fixture | 路由已测 | `UI_READY_BACKEND_GAP` | 建立 catalog read API 与版本/准入字段 |
| UI-14 | `commerce-product` | 商品详情 | 原图详情与拼团入口 | 尚无商品详情 DTO；价格/权益必须服务端派生 | `CREATE_GROUP` 前置页 | 路由/LLM 入口已测 | `UI_READY_BACKEND_GAP` | 接商品 fixture 详情和受控购买意图，不接真实支付 |
| UI-15 | `commerce-invite` | 邀请有礼 | 原图热点到客户资产 | `POST /experience/operations`；`CREATE_INVITE`；0022 表 | Named Action、fixture、幂等、无外部 effect | PostgreSQL + Web 已测 | `E2E_READY` | 增加取消/回放 UI 状态 |
| UI-16 | `commerce-group` | 拼团专区 | 原图热点到客户资产 | `CREATE_GROUP`；0022 表 | Named Action、fixture、幂等、无扣款 | PostgreSQL + Web 已测 | `E2E_READY` | 补充只读团状态与取消回执 |
| UI-17 | `commerce-points` | 积分商城 | 原图积分与兑换视觉 | 尚无积分 ledger/兑换 DTO | 不得写真实权益/兑换 | 路由已测 | `GATE_BOUNDARY` | 先设计测试 ledger；需独立商业化 Gate |
| UI-18 | `commerce-mine` | 成长合伙人/我的 | 原图资产视觉 | 可显示 customer projection；缺少专属 DTO | 只读投影 | 路由已测 | `READ_ONLY_READY` | 将 operation projection 映射到正式卡片状态 |
| UI-19 | `teacher-zone` | 名师专区 | 原图名师列表 | 尚无服务供给 catalog DTO | 不得显示未准入真人供给 | 路由已测 | `GATE_BOUNDARY` | 建立测试 provider fixture 与资格字段 |
| UI-20 | `teacher-detail` | 名师详情 | 原图详情 | 尚无名师详情 DTO/资格版本 | 仅受控说明 | 路由已测 | `GATE_BOUNDARY` | 接 admitted provider 只读详情；真人服务仍沙箱 |
| UI-21 | `consultation-booking` | 在线咨询预约 | 原图确认预约热点 | `CREATE_BOOKING`；0022 表；需 SERVICE consent | Named Action、固定 slot、零真人联系 | PostgreSQL + Web 已测 | `E2E_READY` | 增加取消与服务记录投影 |
| UI-22 | `salon-list` | 线下沙龙列表 | 原图活动列表 | 尚无活动 catalog DTO | 不得真实占座/派单 | 路由已测 | `UI_READY_BACKEND_GAP` | 接测试活动 catalog 与状态 |
| UI-23 | `activity-detail` | 活动详情/报名 | 原图确认报名热点 | `CREATE_EVENT`；0022 表；需活动资格 | Named Action、fixture、无收费 | PostgreSQL + Web 已测 | `E2E_READY` | 增加活动详情 DTO 与取消 |
| UI-24 | `service-mine` | 我的预约和活动 | 原图服务资产 | 可由 customer projection 提供基础 operation | 只读投影 | 路由已测 | `READ_ONLY_READY` | 建立 service record DTO 与状态映射 |
| UI-25 | `parent-community` | 家长社区 | 原图内容流与入口 | 尚无只读 feed DTO | 禁止真实外发/跨家庭推荐 | 路由已测 | `GATE_BOUNDARY` | 先做合成 feed read model；发布仍沙箱 |
| UI-26 | `publish-dynamic` | 发布动态 | 原图确认发布热点 | `PUBLISH_TEMPLATE`；0022 表；固定模板 | Named Action、模板白名单、零外发 | PostgreSQL + Web 已测 | `E2E_READY` | 增加撤回/私有草稿回执 |
| UI-27 | `dynamic-detail` | 动态详情 | 原图详情 | 无只读 dynamic DTO | 不显示真实社区数据 | 路由已测 | `UI_READY_BACKEND_GAP` | 接合成内容详情与权限边界 |
| UI-28 | `my-community` | 我的社区 | 原图个人社区 | 无 profile/community DTO | 禁止公开画像/等级事实 | 路由已测 | `GATE_BOUNDARY` | 只做家庭私有记录投影 |
| UI-29 | `growth-outcomes` | 成长成果 | 原图成果/勋章 | 不得把过程指标写成成长效果 | 仅家庭自有记录 | 路由已测 | `GATE_BOUNDARY` | 改为记录回顾，不输出效果结论 |
| UI-30 | `annual-member-mine` | 年度会员服务 | 原图会员资产 | 尚无正式会员/服务 entitlement DTO | 不接真实支付/会员权益 | 路由已测 | `GATE_BOUNDARY` | 先建立沙箱会员资产投影 |
| UI-31 | `my-services` | 我的服务 | 原图计划与服务 | 可关联 projection；无专属服务 DTO | LLM 只解释当前状态 | 路由/LLM 阻断已测 | `UI_READY_BACKEND_GAP` | 接服务旅程与计划只读状态 |
| UI-32 | `orders-assets` | 订单与资产 | 原图客户资产 | `GET /experience/customer-projection`；操作投影 | 只读，无支付/权益副作用 | PostgreSQL + Web 已测 | `READ_ONLY_READY` | 接订单/资产分类 DTO（仍为沙箱） |
| UI-33 | `family-profile` | 家庭档案 | 原图家庭档案 | 尚无最小家庭档案读 DTO | family scope 必须服务端派生 | 路由已测 | `UI_READY_BACKEND_GAP` | 接脱敏测试家庭 profile 投影 |
| UI-34 | `service-records` | 服务记录 | 原图咨询/活动记录 | 可由 operation projection 基础提供 | 只读；不得声称真人服务已发生 | 路由已测 | `READ_ONLY_READY` | 接 service record 分类与取消状态 |

## 当前工程结论

当前 34 页并非全部同一完成度。UI-02 已具备真实版本化测评会话、正式 PostgreSQL 持久化、跨端 Named Action、幂等、family scope/consent、不可变提交证据与 E2E；UI-15、UI-16、UI-21、UI-23、UI-26 已具备真实 DEV/TEST 工作流。其余页面需要按本矩阵逐批补齐正式只读 DTO、状态投影或受控写动作，不能通过继续增加静态热点来宣称前后端一致。

“成长榜单、效果成果、会员权益、真实支付、真人咨询、真实社区外发、儿童直接作答和跨家庭比较”属于产品边界或独立 Gate 范围，不能为了完成页面数量而伪造为普通业务接口。

## 逐页验收最低条件

每个页面在标记 `E2E_READY` 前必须同时具备：服务端派生 `family_id`、认证与可信上下文、明确 DTO、数据库状态或明确只读投影、Named Action（如有写入）、固定/版本化 fixture、幂等策略、撤回/取消或安全停止语义、LLM Gateway 页面策略（如使用模型）、文本等价路径、API 集成测试、Web 测试和浏览器证据。真实 API key 不属于代码或测试 fixture；只能在测试时由受控环境注入，且不得进入日志、审计或回放。

## 对象结构基线

本矩阵的对象、关系、DTO、状态上限、来源/可见性、审计字段和 LLM Context 统一以 [`FAMILY_CONSUMER_UI_OBJECT_MODEL_AND_CONTRACT_DESIGN_001.md`](./FAMILY_CONSUMER_UI_OBJECT_MODEL_AND_CONTRACT_DESIGN_001.md) 为配套契约。任何新增 UI 字段、API 字段或数据库列必须先映射到该对象模型；不能以页面临时字段绕过对象关系与 family scope。

## Phase 2 对象链实现记录（DEV/TEST）

本轮新增并已应用 `database/migrations/0023_family_growth_page_objects.sql`，正式建立 `family_profile_snapshots`、`family_support_report_snapshots`、`family_page_task_items` 和 `family_service_records` 四类对象。API 新增：

| API | 对象能力 | Named Action | 验证 |
|---|---|---|---|
| `GET /families/:familyId/orchestration/test-loop/page-objects` | 家庭私有档案、支持报告、任务和服务记录统一投影 | `ReadFamily` | PostgreSQL 集成通过 |
| `POST /families/:familyId/orchestration/test-loop/page-objects/actions` | 任务完成/暂停/取消、家庭报告撤回 | `ExecuteFamilyPageObjectAction` | family scope、幂等、状态转换与负例通过 |

本轮对象链回归结果：原 L0/L1 集成 `5/5`，正式体验与对象投影集成 `5/5`，合计 `2 files / 10 tests passed`；API typecheck 通过。`UI-09`、`UI-29`、`UI-31`、`UI-33`、`UI-34` 已从“只有原图路由”推进为对象 API 可读取/受控更新；仍需后续将对应热点逐页接入这些 API，并继续补齐 UI-01、UI-04、UI-05、UI-06 等对象投影。

对象级安全结果：跨家庭 task id 返回失败；未登记 page/action 返回 `403`；任务状态使用数据库 enum 显式转换；测试清理已按外键顺序覆盖新增四张表；所有对象均为 `FAMILY_PRIVATE`，服务记录 `external_effect=false`。


## 服务预约对象链实现记录（DEV/TEST）

本轮新增并应用 `database/migrations/0032_family_service_booking_objects.sql`，正式建立服务供给、服务者、可预约时段、家庭预约请求、服务记录回执和只读客户投影。服务供给主数据不与家庭预约事实混表；预约/服务记录按 `tenant_id + family_id + actor_person_id`（适用时）隔离，外部副作用固定为 `false`。

| 页面 | 对象链 | 受控 API / Named Action | 当前状态 | 验证 |
|---|---|---|---|---|
| UI-19 名师专区 | Provider → ServiceOffering | `GET /services/offerings` / `ReadFamily` | `BACKEND_READY` | 服务预约 integration 通过 |
| UI-20 名师详情 | ServiceOffering → AvailabilitySlot | `GET /services/slots` / `ReadFamily` | `BACKEND_READY` | 服务预约 integration 通过 |
| UI-21 在线咨询预约 | BookingRequest → BookingServiceRecord → ProductEvent | `POST /services/booking-requests` / `SubmitServiceBooking` | `E2E_READY` | PostgreSQL 3/3；Web API 窄测试通过 |
| UI-24 我的咨询和活动 | CustomerServiceBookingProjection | `GET /services/customer-projection` / `ReadFamily` | `E2E_READY` | PostgreSQL 与 Web 投影断言通过 |

UI-21 已从旧 `CREATE_BOOKING` 固定体验入口切换为正式预约请求 API；UI-24 可读取家庭私有预约/服务记录投影。集成测试覆盖幂等回放、row-version 取消、时段容量释放、服务记录取消、Consent 缺失、错误页面、跨租户服务供给与 zero external effect。真实通知、外部日历、真人确认和生产预约继续不在本纵切范围。
