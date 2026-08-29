---
id: CONTRACT-ENDPOINTS-001
title: Mobile UI 后端 API 端点清单
type: contract
status: current
version: 1.0
owner: chief-architect
created: 2026-08-29
updated: 2026-08-29
canonical: true
supersedes: null
superseded_by: null
---

# Mobile UI 后端 API 端点清单

本文件为任务 T-04a 产出：从 mobile 前端提取其调用的后端 API 端点清单。

**唯一来源**：`frontend/mobile/lib/family/family-api-client.ts`（509 行，全部端点集中在 `FamilyApiClient` 类内）。
**实现状态判据**：仅以 `backend/domains/assessment/api.py` 的路由注册为依据。该文件是当前后端唯一注册这些路径的模块；未出现在其中的端点标 `MISSING`。

## 总览

> 权威计数见文末「逐方法核算」节（按 `this.request` 调用点逐行核算）。

| 指标 | 数量 |
|---|---|
| 端点总数 | 46 |
| IMPLEMENTED | 11 |
| MISSING | 35 |

分组统计（权威）：

| 组 | 端点数 | IMPLEMENTED | MISSING |
|---|---|---|---|
| AUTH | 4 | 4 | 0 |
| ASSESSMENT | 7 | 7 | 0 |
| PLAN | 8 | 0 | 8 |
| GROWTH | 12 | 0 | 12 |
| SERVICE | 6 | 0 | 6 |
| COMMERCE | 5 | 0 | 5 |
| COMMUNITY | 0 | 0 | 0 |
| DEV_SYNTHETIC | 3 | 0 | 3 |
| REVIEW_REQUIRED | 1 | 0 | 1 |
| **合计** | **46** | **11** | **35** |

> 说明：`COMMUNITY` 组在 mobile client 中**没有任何端点**（`projectionCollectionKeys` 里出现了 `posts`/`contents` 等社区语义键名，但无对应端点方法）。
> 下文各分组小节为按语义域的明细展开，其中 `/ui/03/growth-hypothesis` 同时出现在 ASSESSMENT 与 GROWTH 小节（读侧投影跨域），权威归属为 ASSESSMENT。

## 后端已实现端点（`backend/domains/assessment/api.py`）

| 行号 | 方法 | 路径 |
|---|---|---|
| 68 | POST | `/auth/account-session` |
| 109 | GET | `/auth/me` |
| 114 | GET | `/auth/contexts` |
| 131 | POST | `/auth/session/revoke` |
| 156 | GET | `/families/{family_id}/ui/02/assessment` |
| 164 | POST | `/families/{family_id}/assessments/sessions` |
| 180 | POST | `/families/{family_id}/assessments/sessions/{session_id}/responses` |
| 205 | POST | `/families/{family_id}/assessments/sessions/{session_id}/submit` |
| 222 | GET | `/families/{family_id}/ui/03/growth-hypothesis` |
| 238 | POST | `/families/{family_id}/assessments/{session_id}/growth-hypothesis` |
| 257 | POST | `/families/{family_id}/growth-hypotheses/decisions` |

共 11 条。**前端调用的 46 个端点中只有这 11 个有后端实现（23.9%）。**

---

## AUTH（`/auth/*`）

| 方法 | 路径 | client 方法 | 行号 | 实现状态 |
|---|---|---|---|---|
| POST | `/auth/account-session` | `issueDevAccountSession` | 160-165 | IMPLEMENTED |
| GET | `/auth/me` | `getAccount` | 167-169 | IMPLEMENTED |
| GET | `/auth/contexts` | `getContexts` | 171-173 | IMPLEMENTED |
| POST | `/auth/session/revoke` | `revokeSession` | 175-177 | IMPLEMENTED |

请求体/响应类型：

| client 方法 | 请求体关键字段 | 响应类型 |
|---|---|---|
| `issueDevAccountSession` | `external_ref` | `AccountSessionResponse` |
| `getAccount` | —（Bearer token） | 内联 `{ account_id, session_id }` |
| `getContexts` | —（Bearer token） | `FamilyContextsResponse` |
| `revokeSession` | —（无 body） | 内联 `{ revoked: boolean }` |

> 注：`issueDevAccountSession` 方法名带 `Dev` 但路径不在 `/dev/*` 下且后端已实现，故按路径语义归入 AUTH（R5「合成数据不得挂生产路由」相关风险留待 T-04c 交叉核对）。

## ASSESSMENT

| 方法 | 路径 | client 方法 | 行号 | 实现状态 |
|---|---|---|---|---|
| GET | `/families/{familyId}/ui/02/assessment` | `getFamilyAssessment` | 390-392 | IMPLEMENTED |
| POST | `/families/{familyId}/assessments/sessions` | `startFamilyAssessment` | 394-399 | IMPLEMENTED |
| POST | `/families/{familyId}/assessments/sessions/{sessionId}/responses` | `saveFamilyAssessmentResponse` | 401-406 | IMPLEMENTED |
| POST | `/families/{familyId}/assessments/sessions/{sessionId}/submit` | `submitFamilyAssessment` | 408-413 | IMPLEMENTED |
| GET | `/families/{familyId}/ui/03/growth-hypothesis` | `getGrowthHypothesis` | 415-417 | IMPLEMENTED |
| POST | `/families/{familyId}/assessments/{sessionId}/growth-hypothesis` | `generateGrowthHypothesis` | 419-424 | IMPLEMENTED |
| POST | `/families/{familyId}/growth-hypotheses/decisions` | `decideGrowthHypothesis` | 426-431 | IMPLEMENTED |

请求体/响应类型：

| client 方法 | 请求体关键字段 | 响应类型 |
|---|---|---|
| `getFamilyAssessment` | — | 泛型 `T`（无 TS 接口） |
| `startFamilyAssessment` | `subject_person_id`, `tool_ref?` | 泛型 `T` |
| `saveFamilyAssessmentResponse` | `item_ref`, `response_type`(`SINGLE_CHOICE`\|`TEXT`\|`BOOLEAN`), `response_value` | 泛型 `T` |
| `submitFamilyAssessment` | `{}`（空 body） | 泛型 `T` |
| `getGrowthHypothesis` | — | 泛型 `T` |
| `generateGrowthHypothesis` | `{}`（空 body） | 泛型 `T` |
| `decideGrowthHypothesis` | `assessment_session_id`, `hypothesis_ref`, `decision_type`(`CONFIRM`\|`DISMISS`) | 泛型 `T` |

## PLAN

含 onboarding 计划预览、journey-plan 生命周期（创建/确认/阶段复盘）。

| 方法 | 路径 | client 方法 | 行号 | 实现状态 |
|---|---|---|---|---|
| GET | `/families/{familyId}/growth/onboardings/{onboardingId}/plan-preview` | `getPlanPreview` | 283-285 | MISSING |
| POST | `/families/{familyId}/growth/onboardings/{onboardingId}/plan-preview/refresh` | `refreshPlanPreview` | 287-297 | MISSING |
| GET | `/families/{familyId}/growth/journey-plan` | `getJourneyPlan` | 324-326 | MISSING |
| POST | `/families/{familyId}/growth/onboardings/{onboardingId}/journey-plan` | `createJourneyPlan` | 332-343 | MISSING |
| POST | `/families/{familyId}/growth/journey-plans/{planId}/confirm` | `confirmJourneyPlan` | 345-356 | MISSING |
| POST | `/families/{familyId}/growth/journey-plans/{planId}/phase-review` | `reviewJourneyPhase` | 358-369 | MISSING |
| GET | `/families/{familyId}/growth/actions/today` | `getTodayGrowthAction` | 371-373 | MISSING |
| GET | `/families/{familyId}/today` | `getFamilyToday` | 375-377 | MISSING |

请求体/响应类型：

| client 方法 | 请求体关键字段 | 响应类型 |
|---|---|---|
| `getPlanPreview` | — | 泛型 `T` |
| `refreshPlanPreview` | —（无 body，仅 idempotency-key 头） | 泛型 `T` |
| `getJourneyPlan` | — | 泛型 `T` |
| `createJourneyPlan` | `priority_id` | 泛型 `T` |
| `confirmJourneyPlan` | `{}`（空 body） | 泛型 `T` |
| `reviewJourneyPhase` | `decision`(`CONTINUE`\|`ADJUST`\|`PAUSE`\|`HUMAN_REVIEW_REQUIRED`) | 泛型 `T` |
| `getTodayGrowthAction` | — | 泛型 `T` |
| `getFamilyToday` | — | 泛型 `T` |

## GROWTH

含 onboarding 生命周期、成长画像回读、优先级、任务打卡/状态机、orchestration 意图链。

| 方法 | 路径 | client 方法 | 行号 | 实现状态 |
|---|---|---|---|---|
| GET | `/families/{familyId}/growth/onboarding/active` | `getActiveOnboarding` | 179-181 | MISSING |
| POST | `/families/{familyId}/growth/onboarding` | `startGrowthOnboarding` | 183-194 | MISSING |
| GET | `/families/{familyId}/growth/onboardings/{onboardingId}/report-explanation` | `getReportExplanation` | 279-281 | MISSING |
| GET | `/families/{familyId}/growth/onboardings/{onboardingId}/growth-profile-readback` | `getGrowthProfileReadback` | 316-318 | MISSING |
| GET | `/families/{familyId}/growth/onboardings/{onboardingId}/family-review-readback` | `getFamilyReviewReadback` | 320-322 | MISSING |
| GET | `/families/{familyId}/growth/onboardings/{onboardingId}/priority` | `getGrowthPriority` | 328-330 | MISSING |
| GET | `/families/{familyId}/ui/03/growth-hypothesis` | `getGrowthHypothesis` | 415-417 | IMPLEMENTED |
| POST | `/families/{familyId}/tasks/{taskId}/state` | `changeTodayTaskState` | 379-384 | MISSING |
| POST | `/families/{familyId}/tasks/{taskId}/check-in` | `checkInTodayTask` | 479-490 | MISSING |
| GET | `/families/{familyId}/ui/01/home` | `getFamilyHome` | 386-388 | MISSING |

> 消歧（权威归属，避免双算）：
> - `/families/{familyId}/ui/03/growth-hypothesis`（415-417）→ 权威归 **ASSESSMENT**（读侧投影），本表仅因 UI 分屏在成长页而并列展示，不计入 GROWTH 的 12。
> - `/families/{familyId}/ui/01/home`（386-388）→ 权威归 **REVIEW_REQUIRED**，不计入 GROWTH 的 12。
> - 因此 GROWTH 权威计数 12 = 本表除上两条外的 8 条 + orchestration 意图链 4 条。

请求体/响应类型：

| client 方法 | 请求体关键字段 | 响应类型 |
|---|---|---|
| `getActiveOnboarding` | — | `ActiveOnboarding \| null` |
| `startGrowthOnboarding` | `childId`, `guardianPersonId`, `structuredSafetySignals[]`（**camelCase，与后端 snake_case 惯例不一致，待 T-04b 核实**） | 泛型 `T` |
| `getReportExplanation` | — | 泛型 `T` |
| `getGrowthProfileReadback` | — | 泛型 `T` |
| `getFamilyReviewReadback` | — | 泛型 `T` |
| `getGrowthPriority` | — | 泛型 `T` |
| `getGrowthHypothesis` | — | 泛型 `T` |
| `changeTodayTaskState` | `action`(`START`\|`PAUSE`\|`RESUME`\|`CANCEL`), `occurred_at` | 泛型 `T` |
| `checkInTodayTask` | `completion_status`(`COMPLETED`\|`PARTIAL`\|`NOT_COMPLETED`), `reflection`, `occurred_at` | 泛型 `T` |

### GROWTH / orchestration 意图链（同组，路径前缀 `/orchestration/*`）

| 方法 | 路径 | client 方法 | 行号 | 实现状态 |
|---|---|---|---|---|
| POST | `/families/{familyId}/orchestration/needs` | `requestGrowthHelp` | 433-444 | MISSING |
| POST | `/families/{familyId}/orchestration/intents` | `confirmGrowthIntent` | 446-455 | MISSING |
| POST | `/families/{familyId}/orchestration/intents/{intentId}/recommendations` | `requestGrowthRecommendation` | 457-466 | MISSING |
| POST | `/families/{familyId}/orchestration/decisions` | `decideGrowthService` | 468-477 | MISSING |

请求体：

| client 方法 | 请求体关键字段 |
|---|---|
| `requestGrowthHelp` | `subject_person_id`, `raw_text` |
| `confirmGrowthIntent` | `signal_id`, `goal_text` |
| `requestGrowthRecommendation` | `{}`（空 body） |
| `decideGrowthService` | `intent_id`, `recommendation_id`, `recommendation_version`, `decision_type`(`ACCEPT_RECOMMENDATION`\|`SELECT_ALTERNATIVE`\|`DISMISS`), `selected_offer_refs[]` |

> 上表 4 条 orchestration 端点 + 前表消歧后 8 条 = 本组权威计数 12。

## SERVICE

| 方法 | 路径 | client 方法 | 行号 | 实现状态 |
|---|---|---|---|---|
| GET | `/families/{familyId}/orchestration/test-loop/services/offerings?page_id=UI-19&service_type&age_band&available_only` | `getServiceOfferings` | 233-239 | MISSING |
| GET | `/families/{familyId}/orchestration/test-loop/services/slots?service_offering_ref&service_offering_version` | `getServiceSlots` | 241-247 | MISSING |
| POST | `/families/{familyId}/orchestration/test-loop/services/booking-requests` | `submitServiceBooking` | 249-260 | MISSING |
| GET | `/families/{familyId}/orchestration/test-loop/services/customer-projection` | `getServiceCustomerProjection` | 262-264 | MISSING |
| GET | `/families/{familyId}/growth/onboardings/{onboardingId}/service-journey` | `getServiceJourney` | 299-301 | MISSING |

（另有 `POST /families/{familyId}/growth/onboardings/{onboardingId}/service-journey/checkin-drafts`，`createPrivateCheckinDraft`，303-314，MISSING —— 见下条注）

> 计数口径：`service-journey/checkin-drafts`（303-314）计入 SERVICE，故本组权威计数 **6**（上表 5 条 + checkin-drafts 1 条）。

请求体：

| client 方法 | 请求体关键字段 |
|---|---|
| `getServiceOfferings` | 查询参数 `page_id=UI-19`, `service_type?`, `age_band?`, `available_only?` |
| `getServiceSlots` | 查询参数 `service_offering_ref`, `service_offering_version` |
| `submitServiceBooking` | `page_id="UI-21"`, `service_offering_ref`, `service_offering_version`, `availability_slot_ref`, `attributes?` |
| `getServiceCustomerProjection` | — |
| `getServiceJourney` | — |
| `createPrivateCheckinDraft` | `action_ref`(`WEEKLY_ACTION_SEE`\|`WEEKLY_ACTION_ADJUST`\|`PAUSE_AND_RETURN`) |

## COMMERCE

含商品与会员套餐（membership 按商业语义归 COMMERCE）。

| 方法 | 路径 | client 方法 | 行号 | 实现状态 |
|---|---|---|---|---|
| GET | `/families/{familyId}/orchestration/test-loop/commerce/products` | `getCommerceProducts` | 204-206 | MISSING |
| POST | `/families/{familyId}/orchestration/test-loop/commerce/order-intents` | `submitCommerceIntent` | 208-219 | MISSING |
| GET | `/families/{familyId}/orchestration/test-loop/commerce/customer-projection` | `getCommerceCustomerProjection` | 221-223 | MISSING |
| GET | `/families/{familyId}/orchestration/test-loop/membership/plans` | `getMembershipPlans` | 225-227 | MISSING |
| GET | `/families/{familyId}/orchestration/test-loop/membership/customer-projection` | `getMembershipCustomerProjection` | 229-231 | MISSING |

请求体：

| client 方法 | 请求体关键字段 |
|---|---|
| `submitCommerceIntent` | `page_id="UI-14"`, `product_ref`, `product_version`, `attributes?` |
| 其余 4 条 | —（GET，无 body） |

## COMMUNITY

**空组。** mobile client 未调用任何社区/内容/帖子端点。

## DEV_SYNTHETIC（`/dev/*`）

| 方法 | 路径 | client 方法 | 行号 | 实现状态 |
|---|---|---|---|---|
| GET | `/families/{familyId}/dev/core-growth` | `getDevCoreGrowth` | 196-198 | MISSING |
| GET | `/families/{familyId}/dev/platform-surfaces` | `getDevPlatformSurfaces` | 200-202 | MISSING |
| POST | `/families/{familyId}/dev/flow-events` | `recordDevFlowEvent` | 266-277 | MISSING |

请求体：

| client 方法 | 请求体关键字段 |
|---|---|
| `recordDevFlowEvent` | `ui_id`, `command`, `selection?` |
| 其余 2 条 | —（GET，无 body） |

> 字段级分析由 T-04b 负责，本节不展开。

## REVIEW_REQUIRED（路径语义拿不准，不猜）

| 方法 | 路径 | client 方法 | 行号 | 实现状态 | 疑点 |
|---|---|---|---|---|---|
| GET | `/families/{familyId}/ui/01/home` | `getFamilyHome` | 386-388 | MISSING | `/ui/01/*` 是首页聚合投影，跨 GROWTH/PLAN/COMMERCE 多域，无法归单一组 |

## 逐方法核算（权威）

按 `family-api-client.ts` 内出现顺序，全部 `this.request` 调用点（唯一权威计数）：

| # | 行号 | 方法 | 路径 | client 方法 | 组 | 状态 |
|---|---|---|---|---|---|---|
| 1 | 161 | POST | `/auth/account-session` | `issueDevAccountSession` | AUTH | IMPLEMENTED |
| 2 | 168 | GET | `/auth/me` | `getAccount` | AUTH | IMPLEMENTED |
| 3 | 172 | GET | `/auth/contexts` | `getContexts` | AUTH | IMPLEMENTED |
| 4 | 176 | POST | `/auth/session/revoke` | `revokeSession` | AUTH | IMPLEMENTED |
| 5 | 180 | GET | `/families/{familyId}/growth/onboarding/active` | `getActiveOnboarding` | GROWTH | MISSING |
| 6 | 184 | POST | `/families/{familyId}/growth/onboarding` | `startGrowthOnboarding` | GROWTH | MISSING |
| 7 | 197 | GET | `/families/{familyId}/dev/core-growth` | `getDevCoreGrowth` | DEV_SYNTHETIC | MISSING |
| 8 | 201 | GET | `/families/{familyId}/dev/platform-surfaces` | `getDevPlatformSurfaces` | DEV_SYNTHETIC | MISSING |
| 9 | 205 | GET | `/families/{familyId}/orchestration/test-loop/commerce/products` | `getCommerceProducts` | COMMERCE | MISSING |
| 10 | 209 | POST | `/families/{familyId}/orchestration/test-loop/commerce/order-intents` | `submitCommerceIntent` | COMMERCE | MISSING |
| 11 | 222 | GET | `/families/{familyId}/orchestration/test-loop/commerce/customer-projection` | `getCommerceCustomerProjection` | COMMERCE | MISSING |
| 12 | 226 | GET | `/families/{familyId}/orchestration/test-loop/membership/plans` | `getMembershipPlans` | COMMERCE | MISSING |
| 13 | 230 | GET | `/families/{familyId}/orchestration/test-loop/membership/customer-projection` | `getMembershipCustomerProjection` | COMMERCE | MISSING |
| 14 | 238 | GET | `/families/{familyId}/orchestration/test-loop/services/offerings` | `getServiceOfferings` | SERVICE | MISSING |
| 15 | 246 | GET | `/families/{familyId}/orchestration/test-loop/services/slots` | `getServiceSlots` | SERVICE | MISSING |
| 16 | 250 | POST | `/families/{familyId}/orchestration/test-loop/services/booking-requests` | `submitServiceBooking` | SERVICE | MISSING |
| 17 | 263 | GET | `/families/{familyId}/orchestration/test-loop/services/customer-projection` | `getServiceCustomerProjection` | SERVICE | MISSING |
| 18 | 267 | POST | `/families/{familyId}/dev/flow-events` | `recordDevFlowEvent` | DEV_SYNTHETIC | MISSING |
| 19 | 280 | GET | `/families/{familyId}/growth/onboardings/{onboardingId}/report-explanation` | `getReportExplanation` | GROWTH | MISSING |
| 20 | 284 | GET | `/families/{familyId}/growth/onboardings/{onboardingId}/plan-preview` | `getPlanPreview` | PLAN | MISSING |
| 21 | 288 | POST | `/families/{familyId}/growth/onboardings/{onboardingId}/plan-preview/refresh` | `refreshPlanPreview` | PLAN | MISSING |
| 22 | 300 | GET | `/families/{familyId}/growth/onboardings/{onboardingId}/service-journey` | `getServiceJourney` | SERVICE | MISSING |
| 23 | 304 | POST | `/families/{familyId}/growth/onboardings/{onboardingId}/service-journey/checkin-drafts` | `createPrivateCheckinDraft` | SERVICE | MISSING |
| 24 | 317 | GET | `/families/{familyId}/growth/onboardings/{onboardingId}/growth-profile-readback` | `getGrowthProfileReadback` | GROWTH | MISSING |
| 25 | 321 | GET | `/families/{familyId}/growth/onboardings/{onboardingId}/family-review-readback` | `getFamilyReviewReadback` | GROWTH | MISSING |
| 26 | 325 | GET | `/families/{familyId}/growth/journey-plan` | `getJourneyPlan` | PLAN | MISSING |
| 27 | 329 | GET | `/families/{familyId}/growth/onboardings/{onboardingId}/priority` | `getGrowthPriority` | GROWTH | MISSING |
| 28 | 333 | POST | `/families/{familyId}/growth/onboardings/{onboardingId}/journey-plan` | `createJourneyPlan` | PLAN | MISSING |
| 29 | 346 | POST | `/families/{familyId}/growth/journey-plans/{planId}/confirm` | `confirmJourneyPlan` | PLAN | MISSING |
| 30 | 359 | POST | `/families/{familyId}/growth/journey-plans/{planId}/phase-review` | `reviewJourneyPhase` | PLAN | MISSING |
| 31 | 372 | GET | `/families/{familyId}/growth/actions/today` | `getTodayGrowthAction` | PLAN | MISSING |
| 32 | 376 | GET | `/families/{familyId}/today` | `getFamilyToday` | PLAN | MISSING |
| 33 | 380 | POST | `/families/{familyId}/tasks/{taskId}/state` | `changeTodayTaskState` | GROWTH | MISSING |
| 34 | 387 | GET | `/families/{familyId}/ui/01/home` | `getFamilyHome` | REVIEW_REQUIRED | MISSING |
| 35 | 391 | GET | `/families/{familyId}/ui/02/assessment` | `getFamilyAssessment` | ASSESSMENT | IMPLEMENTED |
| 36 | 395 | POST | `/families/{familyId}/assessments/sessions` | `startFamilyAssessment` | ASSESSMENT | IMPLEMENTED |
| 37 | 402 | POST | `/families/{familyId}/assessments/sessions/{sessionId}/responses` | `saveFamilyAssessmentResponse` | ASSESSMENT | IMPLEMENTED |
| 38 | 409 | POST | `/families/{familyId}/assessments/sessions/{sessionId}/submit` | `submitFamilyAssessment` | ASSESSMENT | IMPLEMENTED |
| 39 | 416 | GET | `/families/{familyId}/ui/03/growth-hypothesis` | `getGrowthHypothesis` | ASSESSMENT | IMPLEMENTED |
| 40 | 420 | POST | `/families/{familyId}/assessments/{sessionId}/growth-hypothesis` | `generateGrowthHypothesis` | ASSESSMENT | IMPLEMENTED |
| 41 | 427 | POST | `/families/{familyId}/growth-hypotheses/decisions` | `decideGrowthHypothesis` | ASSESSMENT | IMPLEMENTED |
| 42 | 434 | POST | `/families/{familyId}/orchestration/needs` | `requestGrowthHelp` | GROWTH | MISSING |
| 43 | 447 | POST | `/families/{familyId}/orchestration/intents` | `confirmGrowthIntent` | GROWTH | MISSING |
| 44 | 458 | POST | `/families/{familyId}/orchestration/intents/{intentId}/recommendations` | `requestGrowthRecommendation` | GROWTH | MISSING |
| 45 | 469 | POST | `/families/{familyId}/orchestration/decisions` | `decideGrowthService` | GROWTH | MISSING |
| 46 | 480 | POST | `/families/{familyId}/tasks/{taskId}/check-in` | `checkInTodayTask` | GROWTH | MISSING |

**权威总计：46 个端点。IMPLEMENTED 11，MISSING 35。**

> 各分组小节为语义展开视图；本节为唯一权威计数来源。

## 关键发现

1. **前端已实现 46 个端点调用，后端只落地 11 个（23.9%）**。缺口集中在 PLAN（8/8 缺）、GROWTH（12/12 缺）、SERVICE（6/6 缺）、COMMERCE（5/5 缺）。
2. **后端唯一注册这些路径的模块是 `backend/domains/assessment/api.py`**，其覆盖面恰好等于 AUTH + ASSESSMENT 两组。这与 R4「无测试不得声称能力可用」需交叉核对（T-04c）。
3. **`test-loop` 路径段（13 个端点）语义可疑**：`/orchestration/test-loop/*` 出现在 COMMERCE 与 SERVICE 全部端点上，疑为源仓库测试回路残留挂在生产路由前缀下，触及 R5「合成/演示/夹具数据不得挂生产路由」。**登记为风险，不在本任务内裁决。**
4. **`startGrowthOnboarding`（行 183-194）请求体用 camelCase**（`childId` / `guardianPersonId` / `structuredSafetySignals`），与其余全部端点的 snake_case 不一致 —— 与记忆中「camelCase 绕过契约安全检查」的历史坑同型，交 T-04b 字段级核实。
5. **COMMUNITY 组为空**：`projectionCollectionKeys`（行 28-30）预留了 `posts` / `contents` 等社区语义键，但无任何端点方法，说明社区能力在 mobile 尚未接线。

## 待后续任务

- **T-04b：字段级拆解**。展开每个端点的请求/响应字段（含 `/dev/*` 端点的字段级分析）、类型、必填性、枚举取值；核实 `startGrowthOnboarding` 的 camelCase 命名是否为契约违规；确认泛型 `T` 返回处（本清单中除 AUTH 4 条外全部）的实际响应 schema。
- **T-04c：状态交叉核对**。将本清单的 `IMPLEMENTED`/`MISSING` 与 `governance/DOMAIN_REGISTRY.yaml` 的 `status`、`governance/MIGRATION_MANIFEST.yaml` 的迁移条目、以及实际测试覆盖交叉比对；裁决 `/orchestration/test-loop/*` 的 R5 合规性、`issueDevAccountSession` 的合成路由风险、`REVIEW_REQUIRED` 组 `/ui/01/home` 的最终归属，以及 `server/_core/llm.ts:290` 的 R7 适用性。
