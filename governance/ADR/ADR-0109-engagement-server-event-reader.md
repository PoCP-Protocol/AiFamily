# ADR-0109：Engagement 使用服务端授权事件读取端口

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/intelligence/experience/engagement.py`

## 决策

Engagement AI 生成入口不再要求调用方直接组装 `ExperienceEvent`。新增
`EngagementEventReader` 与 `EngagementDraftApplication`：调用方只提交
`event_ids`，由受信任的 reader 按 `ExperienceScope` 读取事件；应用层要求返回的
事件集合与请求集合完全一致，并按请求顺序构造 `EngagementDraftCommand`。

事件读取可以是同步或异步实现；当前提供 `SqlAlchemyEngagementEventReader`，复用
Experience Outbox 的事务表并执行租户/家庭/主体和删除范围过滤，持久化 session 与
identity/consent 解析仍由组合根注入。读取失败、缺失事件或 reader 返回非法对象时，
在 Model Gateway 调用前 fail-closed。

## 约束

- 客户端不能提交事件 payload、scope、provider 或授权字段来伪造证据。
- AI 仍只能产生 evidence-bound `DRAFT`，Achievement 仍必须经过 Human Gate。
- 测试 reader 与生产 reader 使用同一应用契约，不以 synthetic reader 代替生产接线。

## 未完成事项

真实 identity/consent resolver、主入口 wiring、PostgreSQL 并发演练与告警仍需在
production composition root 接入；本 ADR 已冻结端口与 SQL reader 的 fail-closed 行为。
