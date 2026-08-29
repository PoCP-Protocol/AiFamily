# UI-29 至 UI-34 原图对齐记录

本批依据 `research/ui35-original-baseline-manifest.md` 所列的六张原图执行。UI-29 保留原图的顶部、蓝色成长回顾、荣誉/过程区和家庭档案出口，但将成长值、儿童前后变化等语义替换为家庭过程记录。UI-30 至 UI-32 保留会员摘要、服务/资产统计与快捷入口，续费、开通、订单和支付仍为受控意向或只读投影。UI-33 至 UI-34 保留档案/记录层级、时间线和服务回看，限制为家庭范围内的角色、同意、过程与意向，不生成儿童诊断、公开资料或外部联络。

原图清单：`growth-outcomes-reference-522x1110.png`、`annual-member-mine-reference-532x994.png`、`my-services-reference-532x1000.png`、`orders-assets-reference-552x1010.png`、`family-profile-reference-542x1002.png`、`service-records-reference-566x1008.png`。

## S6 场景与 4A 对齐（UI-30、UI-32）

UI-29、UI-31、UI-33、UI-34 属于 S9“家庭档案、服务历史与年度回看”，4A 解构见 `architecture/SCENARIO_DRIVEN_4A_BASELINE.md` 第 5 节 S9 表格。以下仅解构 UI-30、UI-32 所属的 S6“会员、积分、订单与资产”。

| 架构视角 | UI-30 当前处理 | UI-32 当前处理 |
| --- | --- | --- |
| BA | 家庭查看年度陪伴方案摘要和六项快捷入口（报告/计划/咨询/活动/订单/邀请），本页不完成续费、开通或扣款。 | 家庭查看方案意向、可用权益、积分与课程资产的汇总，本页不生成新订单、不下载文件、不发放权益。 |
| DA | `MembershipPlansProjection`、`MembershipProjection`、`CommerceCustomerProjection` 三个只读投影；无写入状态。 | `CommerceCustomerProjection.order_intents/entitlements`、`MembershipProjection.benefits/dev_points`，叠加本机 `commerceIntentDraft`、`campCompletedDays`；无投影时展示“这里会慢慢汇集家庭资产”空态。 |
| AA | 保留原图摘要卡和六项快捷入口，全部导航至既有 UI-08、UI-04、UI-24、UI-23、UI-32、UI-15。 | 保留原图顶部统计（方案意向/可用权益/成长积分/课程资产）、资产列表和权益中心；无写入交互，纯投影展示。 |
| TA | 仅调用三个只读 Projection API；无订单提交、续费或支付接口。 | 仅调用 `getCommerceCustomerProjection`、`getMembershipCustomerProjection`（只读）；无支付、下载或分享接口。 |
