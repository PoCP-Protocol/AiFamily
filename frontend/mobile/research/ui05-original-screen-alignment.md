# UI-05 陪跑服务原图对齐记录

更新时间：2026-08-24

## 场景定位

UI-05 承接 UI-04 家庭确认后的 90 天成长方案，是陪跑服务过程页。它展示家庭顾问、班主任陪跑、AI 提醒、专家答疑四类支持入口，以及本周打卡进度、家庭过程记录和进入 UI-09 的打卡出口。

本页不是 AI 诊断页，不是公开社区页，也不是服务效果证明页。可见内容只能表达家庭私有过程、服务入口和已接入投影中的过程状态。

## BA 业务架构

| 项目 | 结论 |
| --- | --- |
| 用户角色 | 家长或家庭共同照护者 |
| 前置状态 | 理想路径为 UI-04 已确认 90 天计划；无计划时仍可看到入口布局，但不能显示已服务或已完成事实 |
| 主要动作 | 查看陪跑服务入口、查看本周家庭过程、进入 UI-09 打卡、在阶段到期时提交继续或调整节奏 |
| 退出路径 | 主出口为 `UI-09` 打卡；阶段回顾只更新 journey plan，不跳转商业或外部服务 |
| 业务边界 | 不做跨家庭排名，不承诺孩子变化，不伪称真人服务已发生，不触发支付、购买、分享 |

## DA 数据架构

| 对象/状态 | 来源 | 边界 |
| --- | --- | --- |
| `ServiceJourney.process_summary.completed_actions` | `familyApi.getServiceJourney` 只读投影 | 缺失时默认为 `0`，不能用静态示例进度替代事实 |
| `ServiceJourney.process_summary.label` | 后端服务旅程投影 | 缺失时使用“本周家庭过程记录”，不使用“超过伙伴”等比较口径 |
| `JourneyPlanProjection.plan` | `familyApi.getJourneyPlan` 只读投影 | 只有 `REVIEW_DUE` 时展示阶段回顾动作 |
| `lastReceipt` / `campCompletedDays` | 本机家庭状态 | 仅可辅助当前家庭任务勾选，不代表跨家庭成果或公开状态 |
| 动态记录 | 当前为基线静态内容 | 文案标为家庭私有记录，互动区不显示点赞/评论计数 |

## AA 应用架构

| 模块 | 当前实现 |
| --- | --- |
| 页面入口 | `app/ui/UI-05.tsx` |
| 服务卡 | `SERVICE_CARDS` 保留原图四卡布局和 accessibility label |
| 进度卡 | `progress` 从 service journey 投影计算，缺失时 `0/9`、`0%` |
| 阶段回顾 | `reviewPhase("CONTINUE" \| "ADJUST")` 调用 `familyApi.reviewJourneyPhase` |
| 打卡出口 | Floating action button 仅 `router.push("/ui/UI-09")` |
| 测试 | `ui05-companion-baseline.test.ts`、`ui05-ui09-real-session-harness.test.ts` |

## TA / IT 与 AI 架构

| 能力 | 约束 |
| --- | --- |
| Family API | 读取 `getServiceJourney`、`getJourneyPlan`；阶段回顾写入 `reviewJourneyPhase` |
| 幂等 | 阶段回顾使用 `ui05-review-${plan.plan_id}-${decision}` |
| Named Action | 本页不直接写核心状态；阶段回顾由服务端受控 API 承接 |
| Model Gateway | 本页没有直接模型调用；AI 提醒只作为服务入口文案，不生成核心 Ontology |
| Human Gate | 专家答疑只作为入口分类；不得伪称专家已确认或真人服务已发生 |
| Audit/Outbox | 真实阶段回顾应由后端记录，移动端不自行伪造服务记录 |

## 本轮修正

| 问题 | 修正 |
| --- | --- |
| 无 service journey 投影时默认 `7/9`、`78%` | 改为 `0/9`、`0%`，只显示“本周家庭过程记录” |
| `超过 78% 的伙伴` 构成跨家庭比较 | 删除比较口径 |
| 动态文案“看到孩子的变化”接近效果断言 | 改为记录观察和感受，供家庭复盘 |
| 动态区 `♧ 23`、`◯ 8` 像公开社区互动计数 | 改为“家庭私有记录 / 用于复盘” |

## 验证

| 验证项 | 结果 |
| --- | --- |
| `pnpm --dir .\50_开发_dev\apps\mobile exec vitest run tests/ui05-companion-baseline.test.ts tests/ui05-ui09-real-session-harness.test.ts` | 9/9 通过 |
| 浏览器运行态 `/ui/UI-05` | 显示 `本周任务 0/9`、`0%`、`本周家庭过程记录`、`家庭私有记录 / 用于复盘` |
| diagnostics | `UI-05.tsx` 与 UI05 测试无错误 |

## 待复核

1. 使用真实已确认 plan 与 service journey fixture 验证 `REVIEW_DUE` 阶段回顾面板。
2. 使用 UI09 打卡链路验证完成动作回写后 UI05 进度显示。
3. 后续如接入真人顾问或专家答疑，必须补服务状态、资格、同意与 Human Gate。
