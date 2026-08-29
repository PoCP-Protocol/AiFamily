# Family API 移动端接入审计

## 1. 结论

移动 App 不需要新建第二套家庭成长后端。现有 NestJS Family API 已包含 account-scoped Bearer 认证、家庭上下文解析、UI-02 至 UI-10 的 Dev 读投影、六循环持久回执、正式 90 天 Journey Plan、Today projection 和幂等 check-in。移动端应通过独立的 `EXPO_PUBLIC_FAMILY_API_BASE_URL` 调用该服务；WebDev 模板自带的 tRPC/OAuth 后端继续负责移动工程自身的运行能力，不替代 Family API。

在 `PLATFORM_AUTH_MODE=required` 时，Family API 只接受有效会话 token。URL 中的 `familyId` 不能作为授权来源；服务会把 account token 解析为当前家庭中的 person、role 和 membership，再执行 Named Action 权限矩阵。仅提交 `x-actor-id` 会返回 401，跨家庭访问会返回 403。移动端原生 token 使用 SecureStore 保存，Family API 请求不携带 cookie。

## 2. 认证与家庭上下文

| 步骤 | Family API | 移动端行为 |
|---|---|---|
| Dev 会话 | `POST /auth/account-session`，仅 `FPAI_INTERNAL_OPS=true` | 传入稳定的 Dev `external_ref`，保存返回 token；正式环境不使用 |
| 正式身份 | `POST /auth/otp/request` → `POST /auth/otp/verify` | 后续接入真实手机号 OTP；本轮保留接口能力 |
| 账户确认 | `GET /auth/me` | 验证 token 可用，失败时清除失效 token |
| 家庭发现 | `GET /auth/contexts` | 获取 account 的全部家庭上下文，由家庭明确选择 |
| 首家庭 | `POST /auth/families` | 仅零家庭账户使用；不由 App 自动创建 |
| 撤销 | `POST /auth/session/revoke` | 清除服务端会话和 SecureStore token |

Family API 的 token 是 account-scoped，而不是永久绑定单一 family。每次 `/families/:familyId/...` 请求都会重新解析该账户在目标家庭中的有效 membership，因此移动端需要分别保存 `token`、`selectedFamilyId` 和最近一次 context 快照，不能把 `familyId` 编进伪 token。

## 3. UI-02 至 UI-08 端点映射

| UI | 读端点 | 写端点 | 移动端用途 |
|---|---|---|---|
| UI-02 | `GET /families/:familyId/dev/core-growth` | `POST /families/:familyId/dev/flow-events` | 选择一个 synthetic 家庭关注场景，写入幂等 Dev flow receipt |
| UI-03 | `GET /families/:familyId/dev/core-growth` | `POST /families/:familyId/dev/core-growth/commands` | 显示成长解读入口；命令仅返回 no-op acknowledgement |
| UI-04 | `GET /families/:familyId/growth/onboardings/:onboardingId/report-explanation` | 无核心写入 | 分开展示 Perspective、Hypothesis、Recommendation 和 Evidence lineage |
| UI-05 | `GET .../plan-preview` | `POST .../plan-preview/refresh` | 读取 90 天草稿；刷新必须带幂等键且 `external_effect=false` |
| UI-06 | `GET .../service-journey` | `POST .../service-journey/checkin-drafts` | 回读家庭私有陪伴记录；只能创建私有草稿 |
| UI-07 | `GET .../growth-profile-readback` | UI-02 flow receipt | 回读家庭选择的成长重点和计划上下文 |
| UI-08 | `GET .../family-review-readback` | 无核心写入 | 回读行动、成长营与 Journey action receipt；不推导 Outcome |

没有 onboardingId 时，移动端先读取 `GET /families/:familyId/growth/onboarding/active`。若仍为空，UI-02 使用 Dev core-growth projection 和本地 synthetic fallback，不自动创建正式 onboarding。正式创建链路仍需家庭明确同意，并通过 `POST /families/:familyId/growth/onboarding` 和后续 Perspective Named Action。

## 4. 90 天计划

正式计划状态为 `DRAFT | ACTIVE | PAUSED | COMPLETED | ARCHIVED`，四阶段为 `SEE | PARENT_FIRST | CO_CREATE | STABILIZE`。阶段转换必须经过 review 和家庭决定；`current_day`、阶段状态和完成行动只是进度事实，不能作为成长结果。

| 动作 | 端点 | 约束 |
|---|---|---|
| 读取计划 | `GET /families/:familyId/growth/journey-plan` | ReadFamily |
| 创建计划 | `POST .../growth/onboardings/:onboardingId/journey-plan` | priorityId、幂等键、CreateJourneyPlan 权限 |
| 家庭确认 | `POST .../growth/journey-plans/:planId/confirm` | 幂等键、ConfirmJourneyPlan 权限 |
| 暂停 | `POST .../growth/journey-plans/:planId/pause` | 幂等键、PauseJourneyPlan 权限 |
| 阶段复盘 | `POST .../growth/journey-plans/:planId/phase-review` | `CONTINUE | ADJUST | PAUSE | HUMAN_REVIEW_REQUIRED` |

## 5. 移动客户端策略

所有请求采用 `Authorization: Bearer <token>`、`credentials: omit`、8 秒默认超时和统一 `FamilyApiError`。写请求额外发送 `idempotency-key`、`x-correlation-id` 和 `x-source: family-ai-mobile`。401 表示 token 缺失或失效；403 表示账户没有目标家庭 membership 或角色无权执行动作；这两类错误不能静默切到别的 family。

当 `EXPO_PUBLIC_FAMILY_API_BASE_URL` 未配置、网络不可达或 Dev token 未建立时，移动 App 使用明确标记的 local synthetic projection。fallback 只用于 UI 演示和本地操作，不伪装为服务端同步；界面显示“本机体验数据”，所有写入保持 `externalEffect=false`。一旦服务端可用，用户明确选择同步，不自动覆盖本机反思草稿。

## 6. 数据边界

| 层次 | 移动端处理 |
|---|---|
| Fact | 仅展示服务端已确认对象、行动回执、时间和来源 |
| Perspective | 家长答案和反思以 Perspective 保存，不写为孩子事实 |
| Hypothesis | 报告中的可能视角保留不确定度，不显示为结论 |
| Recommendation | 规则建议显示来源，家庭确认后才能生成 Action |
| Action | 通过 Named Action + 幂等键写入；Dev 无外部效果 |
| Outcome | UI-02 至 UI-08 不自动生成，需独立证据和人工确认 |

## 7. 代码来源

- `/home/ubuntu/family-ai/50_开发_dev/apps/api/src/modules/auth/auth.controller.ts`
- `/home/ubuntu/family-ai/50_开发_dev/apps/api/src/modules/auth/family-platform-auth.guard.ts`
- `/home/ubuntu/family-ai/50_开发_dev/apps/api/src/modules/family/family.controller.ts`
- `/home/ubuntu/family-ai/50_开发_dev/apps/api/src/modules/family/dev-core-growth.service.ts`
- `/home/ubuntu/family-ai/50_开发_dev/packages/contracts/src/dev-core-growth.ts`
- `/home/ubuntu/family-ai/50_开发_dev/packages/contracts/src/journey-plan.ts`
