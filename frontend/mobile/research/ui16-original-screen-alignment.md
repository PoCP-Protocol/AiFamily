# UI-16 原图对齐记录：拼团专区

原图 `group-buy-reference-440x960.png` 与 `commerceGroup()` 确认标题、副标题、四类标签、四张拼团卡、团长/倒计时/参与者、原价/拼团价和去拼团按钮。当前按钮仅保存同行草稿；无订单、真实邀请或扣款。

## S6 场景与 4A 对齐

| 架构视角 | UI-16 当前处理 |
| --- | --- |
| BA | UI-16 属于 S6“会员、积分、订单与资产”中的家庭同行参与入口；家庭按分类浏览拼团商品并选择加入，表达同行学习意向，但本页不完成真实拼团撮合、订单或支付。 |
| DA | 商品与分类来自只读展示配置 `EXISTING_COMMERCE_PRESENTATION`；同行意向只写入本机 `studyGroupDraft`（productRef、title、familyCount）。 |
| AA | 保留原图标题、筛选标签、拼团卡（团长/倒计时/参与者/价格）和去拼团按钮；筛选切换只改变本机展示，去拼团按钮只保存草稿并触发 Haptics 反馈。 |
| TA | 仅调用 `familyApi.recordDevFlowEvent`（DEV 受控 no-op 遥测）；不调用真实拼团撮合、订单创建或支付接口；不经 Named Action 写核心 Ontology。 |
