---
id: SYS-PRODUCT-MAP-001
title: AiFamily Current Product Map
type: system
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# 当前产品地图 (Current Product Map)

> 本文件回答一个问题：**AiFamily 现在有哪些产品/端，各自真实到什么程度。**
> 它不描述代码结构（见 `CURRENT_SYSTEM_BASELINE.md`），不描述目标拓扑（见 `TARGET_ARCHITECTURE.md`）。

---

## 0. 全局前置声明（读本文件前必须先读这一节）

**本文件所有 UI 级状态词（`COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV` / `E2E_READY` / `BACKEND_READY` / `READ_ONLY_READY` / `UI_READY_BACKEND_GAP` / `GATE_BOUNDARY`）都是在源仓库 `D:\family-ai` 的 NestJS 后端下测得的状态**，证据来源是 `docs/14_reference/legacy_audits/FAMILY_CONSUMER_UI_FRONTEND_BACKEND_CONSISTENCY_MATRIX_001.md`（下称"矩阵001"）。

在 AiFamily 内：

```text
AiFamily 后端当前可用业务端点数 = 0
（backend/apps/family_api 只有 /health 与 /ready，见 CURRENT_SYSTEM_BASELINE.md §1）

Mobile 前端依赖端点数 ≈ 40+ 业务路径 + 4 个 /auth/* 端点
（governance/MIGRATION_MANIFEST.yaml → frontend_mobile.evidence）

∴ 34 个 UI 屏幕在 AiFamily 内 100% 不可真正工作。
```

因此每个屏幕的状态必须读作两列：

| 列 | 含义 |
|---|---|
| **Legacy Status** | 该屏幕在源仓库 NestJS 后端下的实测成熟度（矩阵001） |
| **AiFamily Runnable** | 在 AiFamily 内是否真的能跑。当前**全部为 `NO — NO_BACKEND`**，无一例外 |

把 Legacy Status 读成"AiFamily 已具备这个能力"是本文件要防止的第一号误读，也是 `SYSTEM_MANIFEST.md` §6（Current Truth ≠ Evidence）在产品层的具体应用。

---

## 1. 产品清单总览

| 产品 / 端 | 代码是否在 AiFamily | 位置 | 状态 |
|---|---|---|---|
| **Family App**（家长端，移动） | 是 | `frontend/mobile/` | 代码已迁入（411 文件 / 35.62MB，34 UI 屏幕 + 35 测试文件 + 99 张设计基线图），**后端未就绪** |
| **Family API**（后端服务） | 是 | `backend/apps/family_api/` | 真实 FastAPI 实例，仅 `/health` `/ready`，**零业务 API** |
| Teacher Workspace（教师工作台） | **否** | — | **PLANNED_NO_CODE** |
| Institution Console（机构控制台，B2B2C） | **否** | — | **PLANNED_NO_CODE** |
| Operations Console（运营控制台） | **否** | — | **PLANNED_NO_CODE** |
| Web 消费端 | **否** | — | 源仓库 `apps/web` disposition = `REVIEW_REQUIRED / BLOCKED`，未迁入 |

只有前两行是 AiFamily 内实际存在的产品资产。

---

## 2. Family App（家长端）—— 唯一已迁入的用户产品

```text
位置          frontend/mobile/
技术栈        TypeScript / Expo / React Native
规模          411 文件 / 35.62MB
屏幕          34 个（UI-01 ～ UI-34，另有 UI-02-result 结果页）
测试          35 个测试文件
设计资产      99 张设计基线图
disposition   MIGRATE（project_owner_override，2026-08-29 推翻此前 KEEP_NON_PYTHON）
manifest 状态 MIGRATED_PENDING_BACKEND_INTEGRATION
```

**屏幕编号与文件的对应关系**（易错点，明确记录）：

- UI-02 ～ UI-34 → `frontend/mobile/app/ui/UI-02.tsx` … `UI-34.tsx`
- **UI-01 不在 `app/ui/` 下**，它是 `frontend/mobile/app/(tabs)/index.tsx`（Expo Router 的首页 tab）
- `app/ui/UI-02-result.tsx` 是 UI-02 的测评结果页，不是独立编号屏幕

### 2.1 按六类业务闭环分组

分组沿用 `docs/11_delivery/migration/MIGRATION_PLAN_V2.md` §3 的六类闭环命名。

#### ASSESSMENT — 测评与假设解读

| UI | 名称 | Legacy Status | AiFamily Runnable |
|---|---|---|---|
| UI-02 | 家庭支持需要确认（测评） | `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV` | NO — NO_BACKEND |
| UI-02-result | 测评结果页 | （随 UI-02） | NO — NO_BACKEND |
| UI-03 | 成长解读假设与家庭确认 | `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV` | NO — NO_BACKEND |

**这是源仓库唯一真正端到端验证过的核心链路**（版本化 Tool/Session/Response/Evidence + 真实 PostgreSQL E2E + Hypothesis 非事实非诊断断言）。`MIGRATION_PLAN_V2.md` 因此把 ASSESSMENT 排为 Batch 1。注意矩阵001 的 `*_TESTED_DEV` 后缀含义是 DEV/TEST 环境已测，**不是生产已上线**。

#### PLAN — 报告与 90 日成长方案

| UI | 名称 | Legacy Status | AiFamily Runnable |
|---|---|---|---|
| UI-04 | 家庭成长说明（报告） | `UI_READY_BACKEND_GAP` | NO — NO_BACKEND |
| UI-05 | 90 日成长方案 | `UI_READY_BACKEND_GAP` | NO — NO_BACKEND |
| UI-09 | 今日任务 | `COMMERCIAL_SLICE_IMPLEMENTED_TESTED_DEV` | NO — NO_BACKEND |
| UI-31 | 我的服务（计划与服务） | `UI_READY_BACKEND_GAP` | NO — NO_BACKEND |

已知缺口（来自 UI 审计 V1 的精确拆分，不是笼统 GAP）：UI-05 的 phase-review 已接线（`reviewJourneyPhase`），但 **pause 完全无前端入口且客户端 SDK 层缺方法**；UI-04 只有 LLM draft/说明，无报告事实 DTO。

#### GROWTH — 成长效果类页面（按业务语义分路径治理）

| UI | 名称 | Legacy Status | AiFamily Runnable |
|---|---|---|---|
| UI-08 | 成长报告 | `GATE_BOUNDARY` | NO — NO_BACKEND |
| UI-10 | 孩子侧成长助手 | `GATE_BOUNDARY` | NO — NO_BACKEND |
| UI-11 | 成长榜单 | `GATE_BOUNDARY` | NO — NO_BACKEND |
| UI-12 | 成长成果海报 | `GATE_BOUNDARY` | NO — NO_BACKEND |
| UI-29 | 成长成果 | `GATE_BOUNDARY` | NO — NO_BACKEND |

**这一组不能一概视为产品冻结。** 当前源实现形态中，UI-11 的跨家庭榜单/家庭总分/等级化比较触碰
`governance/REPOSITORY_CONSTITUTION.md` R9 红线，不得直接挂载为任何环境的业务能力；UI-08、UI-12、
UI-29 的家庭私有回顾、证据绑定成果和经同意分享属于允许路径，必须在当前目标态重建，并在开发、
测试、生产使用同一套功能、状态机和权限。UI-10（儿童直接作答）另有独立的产品与隐私评审。

#### SERVICE — 名师、咨询预约、沙龙活动

| UI | 名称 | Legacy Status | AiFamily Runnable |
|---|---|---|---|
| UI-06 | 陪跑服务/社群 | `UI_READY_BACKEND_GAP` | NO — NO_BACKEND |
| UI-19 | 名师专区 | `BACKEND_READY` | NO — NO_BACKEND |
| UI-20 | 名师详情 | `BACKEND_READY` | NO — NO_BACKEND |
| UI-21 | 在线咨询预约 | `E2E_READY` | NO — NO_BACKEND |
| UI-22 | 线下沙龙列表 | `UI_READY_BACKEND_GAP` | NO — NO_BACKEND |
| UI-23 | 活动详情/报名 | `E2E_READY` | NO — NO_BACKEND |
| UI-24 | 我的咨询和活动 | `E2E_READY` | NO — NO_BACKEND |
| UI-34 | 服务记录 | `READ_ONLY_READY` | NO — NO_BACKEND |

UI-19→UI-21→UI-24 是源仓库**第二条端到端验证的链路**，也是唯一验证过的付费方向闭环（`GET /services/offerings`、`GET /services/slots`、`POST /services/booking-requests`、`GET /services/customer-projection`）。已知缺口：UI-21 的**取消入口完全不存在**（不是"部分实现"）。`MIGRATION_PLAN_V2.md` 因此把 SERVICE 预约子链提前到 Batch 2。

矩阵001 的两处状态版本差异需注意：UI-19/UI-20 在矩阵主表标 `GATE_BOUNDARY`（尚无供给 catalog DTO），在服务对象链回归表中标 `BACKEND_READY`（`/services/offerings`、`/services/slots` 已通过 integration）。本文件采用后者（更新的一轮回归结果），但这一处不一致本身应记入文档漂移清单。

#### COMMERCE — 商城、拼团、积分、会员、订单

| UI | 名称 | Legacy Status | AiFamily Runnable |
|---|---|---|---|
| UI-07 | 我的会员中心 | `GATE_BOUNDARY` | NO — NO_BACKEND |
| UI-13 | 家庭成长商城 | `UI_READY_BACKEND_GAP` | NO — NO_BACKEND |
| UI-14 | 商品详情 | `UI_READY_BACKEND_GAP` | NO — NO_BACKEND |
| UI-15 | 邀请有礼 | `E2E_READY` | NO — NO_BACKEND |
| UI-16 | 拼团专区 | `E2E_READY` | NO — NO_BACKEND |
| UI-17 | 积分商城 | `GATE_BOUNDARY` | NO — NO_BACKEND |
| UI-18 | 成长合伙人/我的 | `READ_ONLY_READY` | NO — NO_BACKEND |
| UI-30 | 年度会员服务 | `GATE_BOUNDARY` | NO — NO_BACKEND |
| UI-32 | 订单与资产 | `READ_ONLY_READY` | NO — NO_BACKEND |

UI-15/UI-16 的 `E2E_READY` 成立条件是"Named Action + fixture + 幂等 + **零外部 effect**"，即**没有真实扣款**。
这只说明当前外部适配器未接入，不能推导出功能不应建设。所有触及定价/支付/权益兑换的屏幕，
都必须在测试环境使用 sandbox/fake adapter 完整验证；生产环境再切换真实渠道。

**明确反面案例**：UI-17 的积分余额是硬编码兜底值 `membership?.dev_points?.balance ?? 1280`，`DAILY_TASKS` / `REWARDS` 的积分数值也是硬编码常量。`docs/05_ai/AI_NATIVE_PRINCIPLES.md` §4 第 4 条把这一模式明确列为反面清单。COMMERCE 完成前必须用正式 ledger 和投影替代该硬编码，并用可失败的 guardrail 证明不会向未成年人进行自动化决策商业营销；这属于实现质量与生产准入要求，不是阻止测试环境建设完整流程的 Stop Condition。上位约束仍是《未成年人网络保护条例》第 24 条第 3 款，见 `SYSTEM_MANIFEST.md` §3.2。

#### COMMUNITY — 家长社区

| UI | 名称 | Legacy Status | AiFamily Runnable |
|---|---|---|---|
| UI-25 | 家长社区 | `GATE_BOUNDARY` | NO — NO_BACKEND |
| UI-26 | 发布动态 | `E2E_READY` | NO — NO_BACKEND |
| UI-27 | 动态详情 | `UI_READY_BACKEND_GAP` | NO — NO_BACKEND |
| UI-28 | 我的社区 | `GATE_BOUNDARY` | NO — NO_BACKEND |

UI-26 的 `E2E_READY` 同样是"模板白名单 + 零外发"下成立。COMMUNITY 排到 Batch 7，但 `MIGRATION_PLAN_V2.md` §3 明确标注：依 `SYSTEM_MANIFEST.md` §2 的"家庭与家庭之间的关系"价值定位，**Batch 排期靠后 ≠ 产品价值判断为低**，这不是可随意砍掉的边缘功能。

#### FAMILY / 基础（不属六闭环，但屏幕存在）

| UI | 名称 | Legacy Status | AiFamily Runnable |
|---|---|---|---|
| UI-01 | 家庭首页（`app/(tabs)/index.tsx`） | `COMMERCIAL_READ_SLICE_READY` | NO — NO_BACKEND |
| UI-33 | 家庭档案 | `UI_READY_BACKEND_GAP` | NO — NO_BACKEND |

### 2.2 合成数据依赖：一个必须显式处置的产品级风险

`governance/MIGRATION_MANIFEST.yaml` 条目 `family_dev_surface_services` 记录：源仓库 `dev-platform-surfaces.service.ts` 与 `dev-core-growth.service.ts` 自述 `data_source: 'SYNTHETIC_DEV_ONLY'`、`model_gateway: 'NOOP_NOT_INVOKED'`，内容是 24 张硬编码 UI 卡片 + 一本中文文案字典、零 DB 读写，却挂在生产路由 `/:familyId/dev/*` 上，并被 **9+ 个真实屏幕（UI-10 / 11 / 12 / 22 / 23 / 25 / 27 / 28 / 29）消费**。

产品含义：这些屏幕**从未有过真实数据来源**。Python 后端建设时必须为它们显式决定数据来源，否则结果不是"清理了假数据"，而是"移动端白屏"。这是 disposition `ARCHIVE` 条目里唯一带阻塞条件的一条。

### 2.3 CI 状态

源仓库中 `frontend/mobile` 的前身是唯一处于活跃 CI 的前端（`.github/workflows/family-35ui-alignment.yml`，且被 path filter 限定在 mobile/api/contracts 三处）。**在 AiFamily 中，CI workflow 文件已写但从未在远端运行过** —— GitHub 远端仓库尚未创建（`SYSTEM_MANIFEST.md` §1）。当前对 mobile 的验证只能在本地执行。

---

## 3. Family API（后端服务）—— 唯一已存在的后端产品

```text
位置      backend/apps/family_api/
状态      真实可运行的 FastAPI 实例
端点      GET /health, GET /ready  —— 仅此两个
业务端点  0
```

它是一个**真实的进程**（不是骨架文件），但作为"产品"它当前只能回答"我活着吗"。所有 34 个屏幕需要的 ~40+ 业务端点与 4 个 `/auth/*` 端点均不存在。

---

## 4. 规划中但尚无代码的产品

以下三端在战略与 FGCN 设计中已有定位，但**在 AiFamily 与源仓库中都不存在可用实现**，状态一律 `PLANNED_NO_CODE`：

| 产品 | 规划依据 | 为何是"规划中"而非"已有" |
|---|---|---|
| **Teacher Workspace**（教师工作台） | FGCN 一案一管家 / 一任务一责任人；`MIGRATION_PLAN_V2.md` Batch 7（Organization/Teacher，disposition = REIMPLEMENT） | 源仓库无教师端应用。名师相关代码只有家长侧消费的 `/services/offerings`（UI-19/20），不是教师自己的工作台 |
| **Institution Console**（机构控制台，B2B2C） | FGCN 完整形态（多机构协作、贡献分配、影子结算）；Batch 7 | 源仓库无机构端应用；`backend/domains/organization` 尚未存在于 DOMAIN_REGISTRY |
| **Operations Console**（运营控制台） | 运营侧需要（服务履约、Human Gate 审批队列、安全筛查批量可见性） | 源仓库 `apps/ops-web` **目录内只有 node_modules，无 package.json、无源码**，disposition = `DELETE`（`MIGRATION_MANIFEST.yaml` → `frontend_empty_scaffolds`） |

同理，源仓库 `apps/consumer-web` 也是只含 node_modules 的空壳，disposition = `DELETE`。**"源仓库有一个叫 ops-web 的目录"不等于"运营控制台已有雏形"** —— 这是本文件要防止的第二号误读。

## 5. 明确不作为产品存在的历史资产

| 资产 | disposition | 依据 |
|---|---|---|
| `apps/fes-api` | ARCHIVE | 声明 NestJS 依赖却无 `@Module`/`NestFactory`，运行即打印一行 JSON 后退出，从未监听端口 |
| `apps/fes-web` | ARCHIVE | 11 行单函数，零网络调用，零 UI 框架 |
| `apps/ai-runtime` | ARCHIVE / DELETE | git 从未跟踪；`.py` 源码已从磁盘删除只剩 `.pyc` |
| `apps/web` | REVIEW_REQUIRED / BLOCKED | 无组件框架、无 bundler，build 脚本只是 `tsc --noEmit`；24 个 spec 更像后端路由契约参照而非可部署 UI |
| `legacy-system/`（FELS） | ARCHIVE | 自述 `REFERENCE_IMPLEMENTATION=TRUE / REAL_BANGYANG_SOURCE=FALSE`，零生产运行时引用。其否定语义已内嵌进宪章 R9 |
| `products/we-are-family/apps/wf1-lab` | KEEP_NON_PYTHON | 零后端耦合的纯前端 React demo |

---

## 6. 一句话产品现状

**AiFamily 目前有一个界面完整、后端为零的家长端 App，和一个只会回答"我活着"的后端。** 34 个屏幕的成熟度证据全部来自源仓库 NestJS，在 AiFamily 内尚未有任何一个屏幕被 Python 后端点亮过。

## 7. 上游依据

- `docs/14_reference/legacy_audits/FAMILY_CONSUMER_UI_FRONTEND_BACKEND_CONSISTENCY_MATRIX_001.md`（34 UI 逐页状态，Evidence 层，非当前真相）
- `docs/11_delivery/migration/MIGRATION_PLAN_V2.md` §3（六类业务闭环证据状态与 Batch 排期）
- `governance/MIGRATION_MANIFEST.yaml`（`frontend_mobile` / `frontend_empty_scaffolds` / `family_dev_surface_services` 条目）
- `governance/REPOSITORY_CONSTITUTION.md` R5（合成数据不得伪装为业务能力）、R9（AI 输出不得自动成为事实）
- `docs/05_ai/AI_NATIVE_PRINCIPLES.md` §4（反面清单）
