# ADR-0108：Engagement Draft 生成前的授权实时复核

- 状态：Accepted
- 日期：2026-08-30
- 范围：`backend/intelligence/experience/engagement.py`

## 决策

`EngagementAuthorization` 在构造时校验 consent 和 `expires_at`，但这不足以覆盖
排队或模型调用耗时。`EngagementDraftService.generate_draft` 在调用 Model Gateway
之前再次执行 `assert_active()`，因此授权过期或 consent 已失效时不会发生模型外呼。

服务支持注入时钟，生产由组合根提供可信时钟，测试使用固定时钟验证边界；授权失效
只返回稳定的 `EngagementContractError`，不把事件 payload 或 provider 错误暴露给调用方。

## 约束

- AI 输出仍固定为 `DRAFT`，不可写入 Family/Journey/Service/Commerce canonical fact。
- 事件必须来自服务端已授权的 `ExperienceEvent`，不能由客户端伪造。
- 过期复核发生在 Gateway 之前，失败时 provider invocation 数必须为零。

## 未完成事项

事件读取、授权解析和真实 identity/consent resolver 仍由 production composition root
提供；本 ADR 不将内存测试事件存储宣称为生产实现。
