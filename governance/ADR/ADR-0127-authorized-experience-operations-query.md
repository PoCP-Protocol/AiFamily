# ADR-0127：授权的 Experience 运维查询边界

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/intelligence/experience/operations_query.py`、
  `backend/apps/family_api/production_experience_outbox_wiring.py`

## 决策

dashboard 与告警通过 `AuthorizedExperienceOperationsQueryService` 查询 AI runtime
delivery metadata。每次查询先由外部 `OperatorIdentityPort` 解析 operator identity，
要求环境匹配和 `ai.experience.operations.read` scope；缺失、过期或错误身份均
fail-closed。服务只委托 bounded cursor page 与状态 summary，不接受家庭 ID 或
业务主体作为查询条件。

查询返回 message ID、attempt/status、时间、lease 和脱敏错误摘要，不返回 outbox
payload、family/subject scope、模型输出或通知正文。查询使用独立只读 session，
不参与投递事务、不改变 lease/retry/DLQ 状态。staging/production 使用相同授权和
数据最小化语义，部署平台负责 endpoint、分页 cursor 签名、审计和 dashboard 展示。

## 取舍

- 优点：运维可观测性与家庭 API 隔离，operator 权限和数据最小化在服务端固定。
- 限制：实际 operator identity endpoint、访问日志和 cursor 签名仍由部署平台接入。
- 安全边界：只读、不调用模型、不发送家庭通知、不执行领域命令，也不绕过 Human Gate。
