# Family AI 原始 legacy UI 基线清单

## 恢复来源

所有下列原始资料均从公开源仓库 `PoCP-Protocol/Family` 的分支 `platform/family-growth-vertical-slice-001` 恢复，并复制到本项目 `research/baselines/ui35-original/`。本清单用于限制后续实现：每次只以对应原图或原始页面函数为依据，不以当前移动实现反推设计。

| UI | 原始页面 | 原图/原始页面依据 | 状态 |
|---|---|---|---|
| UI-01 | 家庭成长平台首页 | `ui18/core-01-home.png`；`home-screen-reference-654x1138.png` | 已恢复 |
| UI-02 | 家庭测评第 2 步 | `ui18/core-02-assessment.png`；`family-assessment-step2-reference-326x862.png` | 已恢复 |
| UI-03 | 家庭成长解读 | `ui18/core-03-ai-report.png`；`ai-growth-diagnosis-reference-436x1118.png` | 已恢复 |
| UI-04 | 90 天成长方案 | `ui18/core-04-growth-plan.png`；`growth-plan-90day-reference-434x1130.png` | 已恢复 |
| UI-05 | 陪跑服务 | `ui18/core-05-delivery-community.png`；`delivery-community-reference-458x1128.png` | 已恢复 |
| UI-06 | 会员与我的 | `ui18/core-06-mine-member.png`；`mine-member-reference-434x1124.png` | 已恢复 |
| UI-07 | 家庭成长体检入口 | `ui18/growth-01-assessment-entry.png`；`family-assessment-entry-reference-428x952.png` | 已恢复 |
| UI-08 | 家庭成长报告 | `ui18/growth-02-ai-report.png` | 已恢复 |
| UI-09 | 今日成长任务 | `ui18/growth-03-daily-task.png`；`daily-growth-task-reference-448x916.png` | 已恢复 |
| UI-10 | 成长小助手 | `ui18/growth-04-child-assistant.png`；`growth-child-assistant-reference-448x920.png` | 已恢复 |
| UI-11 | 成长榜单原图 | `ui18/growth-05-family-ranking.png`；`growth-ranking-reference-450x918.png` | 已恢复 |
| UI-12 | 成长成果海报原图 | `ui18/growth-06-growth-poster.png`；`growth-poster-reference-444x970.png` | 已恢复 |
| UI-13 | 家庭成长商城 | `ui18/commerce-01-mall-home.png`；`family-growth-mall-reference-424x978.png` | 已恢复 |
| UI-14 | 商品详情 | `ui18/commerce-02-product-detail.png`；`product-detail-reference-418x970.png` | 已恢复 |
| UI-15 | 邀请有礼 | `ui18/commerce-03-invite.png`；`invite-rewards-reference-432x992.png` | 已恢复 |
| UI-16 | 拼团专区 | `ui18/commerce-04-group-buy.png`；`group-buy-reference-440x960.png` | 已恢复 |
| UI-17 | 积分商城 | `ui18/commerce-05-points-task.png`；`points-mall-reference-472x982.png` | 已恢复 |
| UI-18 | 成长合伙人/会员 | `ui18/commerce-06-mine-member.png`；`partner-mine-reference-440x994.png` | 已恢复 |
| UI-19 | 名师专区 | `teacher-zone-reference-458x1008.png` | 已恢复 |
| UI-20 | 名师详情 | `teacher-detail-reference-426x1002.png` | 已恢复 |
| UI-21 | 在线咨询预约 | `consultation-booking-reference-492x1008.png` | 已恢复 |
| UI-22 | 线下沙龙 | `salon-list-reference-466x1008.png` | 已恢复 |
| UI-23 | 活动详情 | `activity-detail-reference-470x1016.png` | 已恢复 |
| UI-24 | 我的咨询与活动 | `service-mine-reference-472x1018.png` | 已恢复 |
| UI-25 | 家长社区 | `parent-community-reference-552x1034.png` | 已恢复 |
| UI-26 | 发布动态 | `publish-dynamic-reference-548x1028.png` | 已恢复 |
| UI-27 | 动态详情 | `dynamic-detail-reference-524x1022.png` | 已恢复 |
| UI-28 | 我的社区 | `my-community-reference-560x1030.png` | 已恢复 |
| UI-29 | 成长成果 | `growth-outcomes-reference-522x1110.png` | 已恢复 |
| UI-30 | 我的年度会员服务 | `annual-member-mine-reference-532x994.png` | 已恢复 |
| UI-31 | 我的服务 | `my-services-reference-532x1000.png` | 已恢复 |
| UI-32 | 订单与资产 | `orders-assets-reference-552x1010.png` | 已恢复 |
| UI-33 | 家庭档案 | `family-profile-reference-542x1002.png` | 已恢复 |
| UI-34 | 服务记录 | `service-records-reference-566x1008.png` | 已恢复 |
| UI-35 | 家庭成长计划/21 天挑战 | 原始 `apps/web/src/test-loop.js` 的 `plan()` 页面函数；含阶段头、今日计划及推荐卡 | 已恢复为源码基线 |

## 使用规则

1. 对齐页面前先查看该行对应的原图或原始函数。
2. 原图与当前产品安全边界冲突时，保持原图结构和出口，数据语义遵守既有平台边界。
3. 不允许以当前移动代码、截图或文字摘要替代缺失的原图依据。
