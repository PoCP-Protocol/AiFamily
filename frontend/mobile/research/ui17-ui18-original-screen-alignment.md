# UI-17 至 UI-18 原图对齐记录：积分与成长合伙人

UI-17 原图确认积分卡、签到、五任务、四兑换卡；UI-18 原图确认成长合伙人资料、四项统计、等级、菜单和年度会员横幅。移动端复用积分/会员投影，按钮仅记录家庭过程或进入既有页面，不自动发放、兑换、开通、续费或扣款。

## S6 场景与 4A 对齐

| 架构视角 | UI-17 当前处理 | UI-18 当前处理 |
| --- | --- | --- |
| BA | 家庭查看成长积分余额、任务和兑换目录，点击任务只跳转或标记查看，不自动发放积分；兑换按策略阻断为只读。 | 家庭查看会员/权益中心的资料、统计、等级和年度横幅，菜单只导航到既有 UI，不完成开通、续费或扣款。 |
| DA | 积分数据来自 `getMembershipCustomerProjection`（`dev_points.balance`）；无投影时回退固定占位 1280，须在测试中标注为 fixture 而非真实余额。 | 会员/权益/商业资产来自 `getMembershipPlans`、`getMembershipCustomerProjection`、`getCommerceCustomerProjection` 三个只读投影组合。 |
| AA | 保留原图积分卡、签到、五任务列表和四兑换卡；任务/兑换点击经 `getUiActionPolicy("UI-17")` 判定为只读并提示，不弹出真实兑换成功态。 | 保留原图资料卡、四项统计、等级、六项菜单和年度会员横幅；菜单跳转到 UI-32、UI-15、UI-17、UI-12、UI-30、UI-19。 |
| TA | 仅调用 `getMembershipCustomerProjection`（只读）；无积分发放、兑换核销或支付接口；写入前经 `ui-action-policies` 策略阻断。 | 仅调用三个只读 Projection API；无会员开通、续费、支付或权益发放接口。 |
